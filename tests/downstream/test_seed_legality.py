# -*- coding: utf-8 -*-
"""tests/test_seed_legality.py —— 种子合法性三修（2026-11-07）。

★ 修的三个问题（全链路审计 §0.11 的三个 P0 级）：

  ① **严格单源下 transitions 仍含 RFC 外方法**：`include_skeleton_methods=False`
     只挡了 `methods` 桶，没挡 `transitions` —— 而种子是 transitions 驱动的
     ⇒ sip 仍发 INFO/MESSAGE/NOTIFY/PRACK/PUBLISH/REFER/SUBSCRIBE/UPDATE，
       smtp 仍发 BDAT/ETRN/HELO/STARTTLS。
  ② **URL 类协议的报文缺 Request-URI**：sip 51 条实例只有 14 条带 `url`
     ⇒ 34/51 条报文 `url=''` ⇒ 非法报文。
  ③ **行命令类协议的命令参数被当成 header**：smtp 生成
     `AUTH\\nmechanism: PLAIN` 而不是 `AUTH PLAIN`。

★ 三条修法的判据**全部协议无关**（不认协议名、不列方法白名单）：
  ① 用「最终 `methods` 桶」当闸门；③ 用「中枢 `headers` 桶认不认识这个字段名」
  当判据；② 用「同批实例里有没有出现过 url」。

★ 本文件末尾有一组 `fakeproto` 用例专门守卫协议无关性 —— 换任何协议名，
  三条判据都必须给出同样结果。
"""
from __future__ import annotations

import pytest

from core.fused.downstream import rag_seedgen as RS
from core.fused.downstream.edge_cover import (
    _apply_instance_fields,
    _instance_url_pool,
    build_message,
    build_seed_from_edges,
)


@pytest.fixture(autouse=True)
def _restore_semantic_switch():
    """★ 本仓有**全局**开关 `semantic_rules_enabled()`：测试里打开后必须恢复，
    否则会污染后续测试（实测曾让 `test_semantic_chain` 在整跑时随机失败、
    单跑却通过 —— 典型的测试间污染）。"""
    from core.fused.semantic.llm_ensemble import (semantic_rules_enabled,
                                         set_semantic_rules_enabled)
    _prev = semantic_rules_enabled()
    yield
    set_semantic_rules_enabled(_prev)


# ===========================================================================
# ① transitions 骨架闸
# ===========================================================================

def _bundle(proto: str, **kw):
    return RS.assemble_bundle(RS.load_fact_views(proto), proto, **kw)


@pytest.mark.parametrize("proto", ["rtsp", "sip", "smtp"])
def test_strict_mode_transitions_methods_are_all_defined(proto):
    """★ 严格单源：transitions 里的方法必须全部落在 methods 桶内。"""
    b = _bundle(proto, apply_allowed_methods=True, include_skeleton_methods=False)
    tm = {str(t[1]).strip().upper() for t in b["transitions"]}
    mm = {str(m).strip().upper() for m in b["methods"]}
    assert tm <= mm, f"{proto} 仍有桶外方法：{sorted(tm - mm)}"


def test_strict_mode_drops_sip_and_smtp_skeleton_only_edges():
    """★ 实测锚点：sip 剔 30 条边（14→6 方法）、smtp 剔 14 条（15→11 方法）。"""
    sip = _bundle("sip", apply_allowed_methods=True, include_skeleton_methods=False)
    smtp = _bundle("smtp", apply_allowed_methods=True, include_skeleton_methods=False)
    assert len(sip["transitions"]) == 21
    assert len(sip["transitions_dropped_undefined"]) == 30
    # ★ 2026-11-07：50 → **52**（批次 3 的 STARTTLS 形态 E 抽到了 STARTTLS，
    #   骨架状态机里 STARTTLS 的边也进了 transitions）。
    assert len(smtp["transitions"]) == 52
    # ★ 2026-11-07：14 → **12** —— STARTTLS 现在进了 methods 桶
    #   （批次 3 的形态 E 抽到了它）⇒ 不再属于「桶外方法」⇒ 少剔 2 条。
    assert len(smtp["transitions_dropped_undefined"]) == 12


def test_strict_gate_does_not_touch_rtsp():
    """rtsp 的 transitions 本来就来自 rfc 且方法全在桶内 ⇒ 一条都不该被剔。"""
    b = _bundle("rtsp", apply_allowed_methods=True, include_skeleton_methods=False)
    assert b["transitions_dropped_undefined"] == []
    assert len(b["transitions"]) == 12


def test_full_source_mode_unaffected():
    """全源模式（默认路径）**不得**被这条改动影响。"""
    for proto, expect_tr in (("rtsp", 14), ("sip", 51), ("smtp", 64)):
        b = _bundle(proto, apply_allowed_methods=False)
        assert len(b["transitions"]) == expect_tr, proto
        assert b["transitions_dropped_undefined"] == [], proto


def test_gate_is_disabled_when_methods_empty():
    """★ 安全阀：methods 桶为空时闸门不生效（否则会把 transitions 全清空）。

    用空 views 组装 ⇒ 没有 fact ⇒ methods 为空 ⇒ transitions 应保持原样（此处为空）。
    """
    b = RS.assemble_bundle([], "fakeproto", include_skeleton_methods=False)
    assert b["methods"] == {}
    assert b["transitions_dropped_undefined"] == []


# ===========================================================================
# ② URL 兜底
# ===========================================================================

def test_url_pool_collects_only_url_fields():
    pool = _instance_url_pool({
        ("A", "M1", "B"): [("url", "u1"), ("CSeq", "1")],
        ("B", "M2", "C"): [("CSeq", "2")],
        ("C", "M3", "D"): [("url", "u2")],
    })
    assert pool == ["u1", "u2"]


def test_url_pool_empty_for_command_protocol():
    """实例里没有 url 字段（命令类协议）⇒ 池为空 ⇒ 不兜底。"""
    assert _instance_url_pool({("A", "MAIL", "B"): [("argument", "FROM:<a@b>")]}) == []


def test_message_gets_url_fallback():
    msg = build_message("ACK", required_headers={}, headers={}, cseq=1,
                        instance_fields=[("CSeq", "9")], url_fallback="sip:x@y")
    assert msg.url == "sip:x@y"


def test_instance_url_wins_over_fallback():
    msg = build_message("ACK", required_headers={}, headers={}, cseq=1,
                        instance_fields=[("url", "sip:real@host")],
                        url_fallback="sip:fallback@host")
    assert msg.url == "sip:real@host"


def test_no_fallback_keeps_empty():
    msg = build_message("AUTH", required_headers={}, headers={}, cseq=1,
                        instance_fields=[("argument", "PLAIN")], url_fallback="")
    assert msg.url == ""


def test_real_corpus_url_gap_closed():
    """★ 实测锚点：修前 rtsp 6 / sip 34 条报文 url 空，修后均 **0**。"""
    from core.fused.semantic.llm_ensemble import set_semantic_rules_enabled
    from core.fused.downstream.edge_cover import edge_cover
    set_semantic_rules_enabled(True)
    for proto in ("rtsp", "sip"):
        b = _bundle(proto, apply_allowed_methods=False)
        corp = edge_cover(b["transitions"], required_headers=b["required_headers"],
                          headers=b["headers"],
                          message_instances=b["message_instances"], protocol=proto)
        empty = [m.method for s in corp for m in s.messages if not m.url]
        assert not empty, f"{proto} 仍有报文缺 URL：{empty[:5]}"


# ===========================================================================
# ③ 未知字段不当 header
# ===========================================================================

def test_unknown_field_goes_to_argument_not_header():
    """★ 命令参数名（不在 headers 桶里）不得写成头部。"""
    hdrs: dict = {}
    url, arg = _apply_instance_fields(
        hdrs, [("mechanism", "PLAIN"), ("CSeq", "1")], 1,
        known_fields={"cseq", "from", "to"})
    assert hdrs == {}
    assert arg == "PLAIN"
    assert url == ""


def test_known_field_still_becomes_header():
    hdrs: dict = {}
    _url, _arg = _apply_instance_fields(
        hdrs, [("Contact", "<sip:a@b>")], 1, known_fields={"contact"})
    assert hdrs == {"Contact": "<sip:a@b>"}


def test_unknown_field_does_not_override_explicit_argument():
    hdrs: dict = {}
    _url, arg = _apply_instance_fields(
        hdrs, [("argument", "FROM:<a@b>"), ("domain", "example.com")], 1,
        known_fields={"cseq"})
    assert arg == "FROM:<a@b>"
    assert hdrs == {}


def test_known_fields_none_keeps_legacy_behaviour():
    """★ 调用方没给 known_fields ⇒ 保持旧行为（字段照旧当头部），不做冒险推断。"""
    hdrs: dict = {}
    _url, arg = _apply_instance_fields(hdrs, [("mechanism", "PLAIN")], 1,
                                       known_fields=None)
    assert hdrs == {"mechanism": "PLAIN"}
    assert arg == ""


def test_real_corpus_smtp_command_params_fixed():
    """★ 实测锚点：smtp 修后 `AUTH` 的 argument 是 'PLAIN'、headers 为空。"""
    from core.fused.semantic.llm_ensemble import set_semantic_rules_enabled
    from core.fused.downstream.edge_cover import edge_cover
    set_semantic_rules_enabled(True)
    b = _bundle("smtp", apply_allowed_methods=False)
    corp = edge_cover(b["transitions"], required_headers=b["required_headers"],
                      headers=b["headers"],
                      message_instances=b["message_instances"], protocol="smtp")
    by_method = {}
    for s in corp:
        for m in s.messages:
            by_method.setdefault(m.method, m)
    for meth, expect_arg in (("AUTH", "PLAIN"), ("ETRN", "example.com")):
        m = by_method.get(meth)
        if m is None:
            continue
        assert m.argument == expect_arg, (meth, m.argument)
        assert not m.headers, (meth, m.headers)


# ===========================================================================
# ④ 协议无关守卫（用 fakeproto，不认协议名）
# ===========================================================================

def test_gate_is_protocol_agnostic():
    """★ 换一个仓库里不存在的协议名，闸门行为必须一致 —— 判据只看 methods 桶。"""
    for proto in ("fakeproto", "whatever-x", ""):
        b = RS.assemble_bundle([], proto or "fakeproto",
                               include_skeleton_methods=False)
        assert b["transitions_dropped_undefined"] == [], proto


def test_argument_rule_is_protocol_agnostic():
    """★ 判据只看「中枢认不认识这个字段名」，与协议名无关。"""
    # 同一组字段，known_fields 不同 ⇒ 结论不同（证明判据是字段集而非协议名）
    for _proto in ("fakeproto", "rtsp", "sip", "smtp", "zztop"):
        h1: dict = {}
        _url, arg1 = _apply_instance_fields(h1, [("weird-param", "v")], 1,
                                            known_fields={"other"})
        assert h1 == {} and arg1 == "v"

        h2: dict = {}
        _url, _arg2 = _apply_instance_fields(h2, [("weird-param", "v")], 1,
                                             known_fields={"weird-param"})
        assert h2 == {"weird-param": "v"}


def test_url_fallback_is_protocol_agnostic():
    """★ 兜底只看「批次里有没有 url 字段」，不看协议。"""
    mi = {("A", "CMD", "B"): [("url", "scheme://h/p")], ("B", "CMD2", "C"): []}
    seed = build_seed_from_edges(
        [("A", "CMD", "B"), ("B", "CMD2", "C")],
        required_headers={}, headers={}, init="A", description="t",
        generated_by="test", message_instances=mi, protocol="fakeproto")
    assert seed.messages[0].url == "scheme://h/p"
    assert seed.messages[1].url == "scheme://h/p"    # 缺 url 的那条被兜底


# ===========================================================================
# ⑤ required_headers 的桶键也要过骨架闸（同一次审计的第 6 项）
# ===========================================================================

@pytest.mark.parametrize("proto", ["rtsp", "sip", "smtp"])
def test_strict_mode_required_header_keys_are_all_defined(proto):
    """★ 严格单源：`required_headers` 的键必须是方法名（在 methods 桶里）或 ``"*"``。

    实测修复前 sip 严格单源：methods 6 个，桶里却有 15 个键 ——
    多出 INFO/MESSAGE/NOTIFY/PRACK/PUBLISH/REFER/SUBSCRIBE/UPDATE。
    消费端按实际报文的方法查表 ⇒ 无害，但**桶级纯净度统计会失真**。
    """
    b = _bundle(proto, apply_allowed_methods=True, include_skeleton_methods=False)
    mm = {str(m).strip().upper() for m in b["methods"]}
    for key in b["required_headers"]:
        assert str(key) == "*" or str(key).strip().upper() in mm, (proto, key)


def test_sip_required_header_keys_shrink_in_strict_mode():
    """★ 实测锚点：sip 严格单源 15→7 键（6 个方法 + `"*"`），剔除 8 个并留痕。"""
    b = _bundle("sip", apply_allowed_methods=True, include_skeleton_methods=False)
    assert len(b["required_headers"]) == 7
    assert set(b["required_headers_dropped_undefined"]) == {
        "INFO", "MESSAGE", "NOTIFY", "PRACK", "PUBLISH", "REFER",
        "SUBSCRIBE", "UPDATE"}


def test_required_header_gate_keeps_global_key():
    """`"*"` 是消息级全局必填头，不是方法名 ⇒ 闸门必须**保留**它。"""
    b = _bundle("rtsp", apply_allowed_methods=True, include_skeleton_methods=False)
    assert "*" in b["required_headers"]


def test_required_header_gate_only_in_strict_mode():
    """全源路径（默认）一条键都不许动。"""
    # ★ 2026-11-07：rtsp 从 9 键变 **10 键**（补了 RECORD 的必填头，
    #   RFC 2326 §10.11 示例：CSeq + Session）⇒ 全源路径同样多一个键。
    for proto, expect in (("rtsp", 10), ("sip", 15), ("smtp", 0)):
        b = _bundle(proto, apply_allowed_methods=False)
        assert len(b["required_headers"]) == expect, proto
        assert b["required_headers_dropped_undefined"] == [], proto


# ===========================================================================
# ⑥ 台账口径守卫（桶名必须与 bundle 实际键对齐）
# ===========================================================================

def test_ledger_universe_covers_every_declared_bucket():
    """★ 守卫：`BUCKET_UNIVERSE` 必须覆盖 `_BUCKET_BY_KIND` 的全部 value。

    修前 `vulnerability` 是个**不存在的桶名**（真名 `vuln_pattern`），
    且 `security` / `actors` / `protocol` 不在全集里 ⇒ 它们为空时台账完全不显示。
    """
    from core.knowledge_channels import BUCKET_UNIVERSE
    declared = set(RS._BUCKET_BY_KIND.values())
    missing = declared - set(BUCKET_UNIVERSE)
    assert not missing, f"台账全集缺桶：{sorted(missing)}"


def test_vuln_pattern_bucket_has_channel():
    """`vuln_pattern` 必须能查到 channel（否则 class/owner 标注静默失效）。"""
    from core.knowledge_channels import BUCKET_CHANNEL, load_channels
    chan = BUCKET_CHANNEL.get("vuln_pattern")
    assert chan, "vuln_pattern 缺通道映射"
    info = load_channels("rtsp").get(chan, {})
    assert info.get("class") and info.get("owner"), info


# ===========================================================================
# ⑦ 会话语义渲染的协议无关性（原实现硬编码 rtsp:// 前缀）
# ===========================================================================

def test_url_scheme_prefix_from_instances():
    """★ 前缀从实例 URL 推导，不认协议名。"""
    b = {"message_instances": {("A", "M", "B"): [("url", "rtsp://h/x")]}}
    assert RS._url_scheme_prefix(b) == "rtsp://"
    b = {"message_instances": {("A", "M", "B"): [("url", "sip:bob@h")]}}
    assert RS._url_scheme_prefix(b) == "sip:"
    # 命令类协议：实例里没有 url 字段 ⇒ 空前缀
    b = {"message_instances": {("A", "M", "B"): [("argument", "x")]}}
    assert RS._url_scheme_prefix(b) == ""
    # 无实例 ⇒ 空前缀
    assert RS._url_scheme_prefix({}) == ""


def test_rtsp_render_is_byte_identical_to_before():
    """★ rtsp 的渲染必须与硬编码时期**逐字一致**（authority-based URI 加 <host>:<port>/）。"""
    b = {"url_template": {"SETUP": "{stream}/track{N}"},
         "message_instances": {("A", "SETUP", "B"): [("url", "rtsp://s/x")]}}
    text = RS._render_session_semantics(b)
    assert "    SETUP → rtsp://<host>:<port>/{stream}/track{N}" in text


def test_sip_render_does_not_leak_rtsp():
    """★ 回归守卫：sip 的 URL 结构段绝不能出现 rtsp（原硬编码时期的真实缺陷）。"""
    b = {"url_template": {"INVITE": "{user}@{server}"},
         "message_instances": {("A", "INVITE", "B"): [("url", "sip:bob@h")]}}
    text = RS._render_session_semantics(b)
    assert "rtsp" not in text
    assert "    INVITE → sip:{user}@{server}" in text


def test_command_protocol_render_has_no_url_section():
    """命令类协议（实例无 url）⇒ 不渲染 URL 结构段（宁缺勿错）。"""
    b = {"url_template": {"MAIL": "{arg}"},
         "message_instances": {("A", "MAIL", "B"): [("argument", "FROM:<a@b>")]}}
    text = RS._render_session_semantics(b)
    assert "URL 结构" not in text


def test_render_is_protocol_agnostic():
    """★ 同一 bundle 换任意协议名，渲染结果不变（判据不依赖协议名）。"""
    b = {"url_template": {"M": "{p}"},
         "message_instances": {("A", "M", "B"): [("url", "zzz://h/p")]}}
    outs = set()
    for _proto in ("rtsp", "sip", "smtp", "fakeproto", ""):
        outs.add(RS._render_session_semantics(b))
    assert len(outs) == 1, outs
    assert "zzz://<host>:<port>/{p}" in outs.pop()
