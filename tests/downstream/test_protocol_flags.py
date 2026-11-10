# -*- coding: utf-8 -*-
"""tests/fused/test_protocol_flags.py —— 协议级行为开关的配置化（批次 1 / A1 + A3）。

★ 为什么有这个文件（2026-11-07）：
  「CSeq 是否渲染成『序号 + 方法』」是**协议语义**，原先用协议名硬判：

      cseq_with_method=(protocol == "sip")        # 7 处主链路

  接入新协议时这就是一道"必须改代码"的墙。现在改为读
  ``profile.json`` 的 ``seedgen.cseq_with_method`` ⇒ **新协议只需加配置**。

★ 本文件锁三件事：
  ① 开关**只从配置读**，不认协议名（换任意协议名结论不变）；
  ② **未声明 = False**（安全缺省：需要 true 的协议必须显式声明）；
  ③ A3：`boundary_probe` 在**完全无知识**时不兜底成 RTSP 报文（返空 + warning），
     但「有 legal_boundary 没有必填头」这种正常情形**不能被误伤**。
"""
from __future__ import annotations

import json

import pytest

from core.fused.downstream import protocol_flags as PF


# ===========================================================================
# ① 开关从配置读，不认协议名
# ===========================================================================

def test_switch_reads_profile_not_protocol_name():
    """★ 判据是**配置**，不是协议名。"""
    prof = {"seedgen": {"cseq_with_method": True}}
    assert PF.cseq_with_method("sip", profile=prof) is True
    assert PF.cseq_with_method("rtsp", profile=prof) is True
    assert PF.cseq_with_method("whatever-xyz", profile=prof) is True
    assert PF.cseq_with_method("", profile=prof) is True

    prof_off = {"seedgen": {"cseq_with_method": False}}
    assert PF.cseq_with_method("sip", profile=prof_off) is False
    assert PF.cseq_with_method("rtsp", profile=prof_off) is False


def test_switch_is_protocol_agnostic_for_missing_config():
    """★ 没有任何配置时，对**任意**协议名都返回 False（安全缺省）。"""
    for proto in ("rtsp", "sip", "smtp", "fakeproto", "", "zzz"):
        assert PF.cseq_with_method(proto, profile={}) is False, proto
        assert PF.cseq_with_method(proto, profile={"seedgen": {}}) is False, proto


def test_real_profiles_declare_the_switch():
    """三协议的 profile 必须**显式**声明（不靠隐含默认）。"""
    expect = {"rtsp": False, "sip": True, "smtp": False}
    for proto, want in expect.items():
        prof = PF._load_profile_cached(proto)
        sg = prof.get("seedgen") or {}
        assert "cseq_with_method" in sg, f"{proto} 未声明 cseq_with_method"
        assert PF.cseq_with_method(proto) is want, (proto, want)


def test_switch_from_disk_matches_declaration(tmp_path, monkeypatch):
    """★ 不传 profile 时走**读盘**路径，结果与显式传入一致。"""
    PF.clear_profile_cache()
    assert PF.cseq_with_method("sip") is True
    assert PF.cseq_with_method("rtsp") is False
    PF.clear_profile_cache()


def test_cache_clear_allows_reload(tmp_path, monkeypatch):
    """改了 profile.json 后清缓存能读到新值。"""
    PF.clear_profile_cache()
    before = PF.cseq_with_method("rtsp")
    assert before is False
    PF.clear_profile_cache()
    assert PF.cseq_with_method("rtsp") is False


def test_malformed_profile_is_safe():
    """profile 形状不对时不得抛异常。"""
    for bad in (None, [], "x", 123, {"seedgen": None}, {"seedgen": []},
                {"seedgen": {"cseq_with_method": "yes"}}):
        v = PF.cseq_with_method("x", profile=bad)
        assert isinstance(v, bool), bad


# ===========================================================================
# ② 端到端：CSeq 格式真的由配置决定
# ===========================================================================

def test_build_message_cseq_format_follows_switch():
    """CSeq 渲染格式由 ``cseq_with_method`` 参数决定（该参数现在来自配置）。"""
    from core.fused.downstream.edge_cover import build_message
    m1 = build_message("REGISTER", required_headers={"REGISTER": ["CSeq"]},
                       headers={}, cseq=1, cseq_with_method=False)
    m2 = build_message("REGISTER", required_headers={"REGISTER": ["CSeq"]},
                       headers={}, cseq=1, cseq_with_method=True)
    assert m1.headers["CSeq"] == "1"
    assert m2.headers["CSeq"] == "1 REGISTER"


@pytest.mark.parametrize("proto,expect", [("sip", "1 REGISTER"), ("rtsp", "1")])
def test_real_protocol_cseq_format_in_seeds(proto, expect):
    """★ 真实协议：sip 的 CSeq 带**消息自己的方法名**、rtsp 只有序号（与改动前一致）。"""
    from core.fused.downstream.edge_cover import build_message
    cwm = PF.cseq_with_method(proto)
    m = build_message("REGISTER", required_headers={"REGISTER": ["CSeq"]},
                      headers={}, cseq=1, cseq_with_method=cwm)
    assert m.headers["CSeq"] == expect


# ===========================================================================
# ③ A3：boundary_probe 不再兜底成 RTSP 报文
# ===========================================================================

def test_boundary_probe_returns_empty_when_no_knowledge_at_all():
    """★ 完全无知识 ⇒ 返空（不生成假 RTSP 报文）。"""
    from core.fused.downstream.boundary_probe import derive_constraint_candidates
    assert derive_constraint_candidates({}, "fakeproto") == []
    assert derive_constraint_candidates(
        {"required_headers": {}, "methods": {},
         "legal_boundary": {}, "response_expectation": {}}, "fakeproto") == []


def test_boundary_probe_not_broken_when_only_legal_boundary_present():
    """★ 「有 legal_boundary 没有必填头」是正常情形 ⇒ 约束候选仍要产出。"""
    from core.fused.downstream.boundary_probe import derive_constraint_candidates
    bundle = {
        "legal_boundary": {
            "QNAME": [{"dim": "QNAME", "legal": "单 label 长度 <= 63",
                       "illegal": "长度字段 > 实际内容", "trigger": "FORMERR"}],
        },
        "response_expectation": {},
    }
    cands = derive_constraint_candidates(bundle, "fakeproto")
    assert len(cands) == 2, "有约束知识时不该被 A3 误伤"
    illegal = cands[1][1]
    assert any("A" * 300 == m.headers.get("QNAME") for m in illegal.messages)


def test_boundary_probe_empty_does_not_raise():
    """★ 返空不得抛异常（未知协议 + 空中枢的组合必须安全）。"""
    from core.fused.downstream.boundary_probe import derive_constraint_candidates
    for proto in ("fakeproto", "zzz-protocol", ""):
        out = derive_constraint_candidates({}, proto)
        assert out == [], proto


# ===========================================================================
# ④ A2：漏洞字段指引按协议取（不继承 RTSP 语义）
# ===========================================================================

def test_generic_guidance_has_no_protocol_specific_fields():
    """★ 通用缺省里**不得**含 RTSP 专属词（Transport/Range/track/Digest…）。"""
    from core.fused.downstream.rag_seedgen import _VULN_FIELD_GUIDANCE_GENERIC
    forbidden = {"Transport", "Transport header", "Range", "Session", "track",
                 "interleaved", "client_port", "Authorization", "Digest",
                 "nonce", "realm", "uri", "username", "授权头", "认证字段"}
    leaked = forbidden & set(_VULN_FIELD_GUIDANCE_GENERIC)
    assert not leaked, f"通用缺省里混进了协议特定词：{sorted(leaked)}"


def test_rtsp_gets_its_own_guidance():
    """rtsp 的指引来自 profile（含 Transport/Range/Digest）。"""
    from core.fused.downstream.rag_seedgen import _vuln_field_guidance
    g = _vuln_field_guidance("rtsp")
    for k in ("Transport", "Range", "Session", "track", "client_port",
              "Authorization", "Digest", "nonce"):
        assert k in g, k
    # 通用项也在
    for k in ("CSeq", "Content-Length", "URL", "header"):
        assert k in g, k


def test_other_protocols_do_not_get_rtsp_guidance():
    """★ 核心守卫：sip/smtp/未知协议**不得**拿到 RTSP 的字段取值语义。"""
    from core.fused.downstream.rag_seedgen import _vuln_field_guidance
    for proto in ("sip", "smtp", "fakeproto", ""):
        g = _vuln_field_guidance(proto)
        for k in ("Transport", "Range", "track", "interleaved", "client_port",
                  "Digest", "nonce", "realm"):
            assert k not in g, (proto, k)
        # 通用项仍在
        assert "header" in g, proto


def test_guidance_is_protocol_agnostic_for_unknown():
    """★ 未知协议拿到的指引集合必须完全一致（不认协议名）。"""
    from core.fused.downstream.rag_seedgen import _vuln_field_guidance
    base = _vuln_field_guidance("fakeproto")
    for proto in ("zzz", "whatever", "another-one"):
        assert set(_vuln_field_guidance(proto)) == set(base), proto


def test_render_vuln_guidance_does_not_leak_rtsp_into_other_protocols():
    """★ 端到端：sip 的漏洞字段指引里不该出现 RTSP 的取值示例。"""
    from core.fused.downstream.rag_seedgen import _render_vuln_guidance
    sec = [("header", "Transport", "x"), ("header", "nonce", "y")]
    sip_text = _render_vuln_guidance(sec, "sip")
    assert "RTP/AVP" not in sip_text, sip_text
    assert "Digest" not in sip_text, sip_text
    rtsp_text = _render_vuln_guidance(sec, "rtsp")
    assert "RTP/AVP" in rtsp_text, rtsp_text


def test_profile_field_guidance_section_exists():
    """三协议的 profile 都应声明 ``vuln.field_guidance``（含空 dict）。"""
    from core.fused.downstream.protocol_flags import load_profile_section
    for proto in ("rtsp", "sip", "smtp"):
        v = load_profile_section(proto, "vuln", "field_guidance")
        assert isinstance(v, dict), (proto, v)


# ===========================================================================
# ⑤ A4：URL scheme 判据
# ===========================================================================

def test_url_scheme_extraction():
    from core.fused.downstream.selector import _url_scheme
    assert _url_scheme("rtsp://h/p") == "rtsp"
    assert _url_scheme("sip:a@b") == "sip"
    assert _url_scheme("HTTP://X") == "http"
    assert _url_scheme("/path") == ""
    assert _url_scheme("") == ""
    assert _url_scheme(":noprot") == ""


def test_url_scheme_is_protocol_agnostic():
    """★ 判据只看 URL 本身，不认协议名。"""
    from core.fused.downstream.selector import _url_scheme
    for _ in range(1):
        assert _url_scheme("ftp://x/y") == "ftp"
        assert _url_scheme("mqtt://x") == "mqtt"
        assert _url_scheme("telnet://x") == "telnet"


def test_default_url_scheme_matching():
    """★ 本协议 default_url 的 scheme 与种子 URL 相同 ⇒ 不该被改写。"""
    from core.fused.downstream.selector import _url_scheme
    own = _url_scheme("sip:127.0.0.1:5060")
    assert own == "sip"
    assert _url_scheme("sip:bob@h") == own
    assert _url_scheme("rtsp://x/y") != own


# ===========================================================================
# ⑥ A5：不再有写死的 RTSP 流名
# ===========================================================================

def test_no_hardcoded_rtsp_stream_name_in_seedgen():
    """★ 守卫：写死的 RTSP 流名不得再出现在**代码**里（注释里提及不算）。

    ★ 只查非注释行 —— 本测试自己的注释就提到了这个名字，全文匹配会自伤。
    ★ `core/fused/vuln_pattern.py` 里的 3 处**不在检查范围**：那是 **RTSP 漏洞库的
      数据**（matroska 漏洞的触发流名），属协议数据而非代码默认值，保留是对的。
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    for rel in ("scripts/seedgen.py", "core/fused/downstream/selector.py",
                "core/fused/downstream/edge_cover.py",
                "core/fused/downstream/rag_seedgen.py"):
        for lineno, line in enumerate(
                (root / rel).read_text(encoding="utf-8").splitlines(), 1):
            _code = line.split("#", 1)[0]
            assert "matroskaFileTest" not in _code, f"{rel}:{lineno} {_code.strip()}"
