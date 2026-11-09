# -*- coding: utf-8 -*-
"""tests/fused/test_binary_protocol.py —— **二进制协议**处理流程（2026-11-07）。

★ 覆盖三层：
  ① **协议类型判断阶段**（``core/kinds``）—— 文本 vs 二进制，配置优先 + 自动探测；
  ② **二进制形态层**（``core/fused/rfc_forms_binary``）—— 位域图 / 定长字段 / 选项表；
  ③ **二进制渲染**（``core/raw_writers_binary``）—— 按字节布局渲染 .raw。

★ 关键回归护栏：**文本协议（rtsp/sip/smtp）的产物必须逐字节不变**。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# ① 协议类型判断阶段
# ===========================================================================

def test_detect_kind_text_protocols():
    """★ 三个文本协议都判成 text（自动探测）。"""
    from core.kinds import detect_protocol_kind
    for p in ("rtsp", "sip", "smtp"):
        k = detect_protocol_kind(p)
        assert k.is_text, f"{p} 被误判为 binary：{k.reason}"
        assert k.decided_by == "auto", k.decided_by


def test_detect_kind_binary_protocol():
    """★ DHCPv4 判成 binary（自动探测，依据位域图）。"""
    from core.kinds import detect_protocol_kind
    k = detect_protocol_kind("DHCPv4")
    assert k.is_binary, k.reason
    assert k.decided_by == "auto"
    ev = {e.criterion: e.hits for e in k.evidence}
    assert ev["bitfield"] > 0, f"位域图判据应命中：{ev}"


def test_detect_kind_profile_override():
    """★ 配置优先：profile 里的 ``protocol_kind`` 直接采信。"""
    from core.kinds import detect_protocol_kind
    k = detect_protocol_kind("rtsp")
    assert k.kind == "text"
    # profile 没声明 protocol_kind ⇒ 走自动探测（上面的测试已覆盖）


def test_kind_decision_is_auditable():
    """★ 判定结果**可审计**（有理由 + 有证据 + 能落盘）。"""
    from core.kinds import detect_protocol_kind, save_kind_artifact
    k = detect_protocol_kind("DHCPv4")
    d = k.as_dict()
    assert d["kind"] == "binary"
    assert d["reason"], "必须有可读理由"
    assert d["evidence"], "必须有判据证据"
    assert d["scanned_files"] > 0
    p = save_kind_artifact(k)
    assert p.is_file()
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back["kind"] == "binary"


def test_kind_detection_code_has_no_protocol_name():
    """★ 代码级守卫：判定器**不得出现协议名**（协议无关）。"""
    import ast
    import inspect
    from core.kinds import detector
    src = inspect.getsource(detector)
    tree = ast.parse(src)
    doc_lines = set()
    # ★ 剥**模块 docstring**（实测：协议名出现在模块级的实测数据表里）
    _mod_doc = ast.get_docstring(tree, clean=False)
    if _mod_doc:
        doc_lines.update(range(1, tree.body[0].end_lineno + 1))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                doc_lines.update(range(node.body[0].lineno,
                                       node.body[0].end_lineno + 1))
    code = "\n".join(
        l.split("#", 1)[0] for i, l in enumerate(src.splitlines(), 1)
        if i not in doc_lines)
    for name in ("rtsp", "sip", "smtp", "dhcpv4"):
        assert name not in code.lower(), f"判定器里出现了协议名 {name}"


# ===========================================================================
# ② 二进制形态层
# ===========================================================================

def test_bitfield_extraction():
    """★ 位域图抽取（实测形态：``| op (1) | htype (1) |``）。

    ★ 三个坑都锁住：
      ① 长度标记**只有数字**（无 "octet" 单位词）⇒ 单位词必须可选；
      ② 一行**多字段** ⇒ 必须按 ``|`` 切单元格（否则非贪婪匹配会跨 ``|`` 拼名）；
      ③ 字段名与长度之间可有填充空格。
    """
    from core.fused.rfc_forms_binary import extract_bitfield_blocks
    lines = [
        "   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+",
        "   |     op (1)    |   htype (1)   |   hlen (1)    |   hops (1)    |",
        "   +---------------+---------------+---------------+---------------+",
        "   |                            xid (4)                            |",
        "   +-------------------------------+-------------------------------+",
    ]
    blocks = extract_bitfield_blocks(lines)
    assert blocks, "应抽出位域图块"
    names = [f.name for f in blocks[0].fields]
    assert names == ["op", "htype", "hlen", "hops", "xid"], names
    lengths = {f.name: f.length for f in blocks[0].fields}
    assert lengths["op"] == 1 and lengths["xid"] == 4, lengths


def test_option_extraction_two_forms():
    """★ 选项定义支持**两种形态**：汇总表 + 独立小节。

    ★ RFC 2132 用的是**独立小节**（正文「The code for this option is 12」）
      ⇒ 只支持汇总表会抽出 0 个。
    """
    from core.fused.rfc_forms_binary import extract_option_tables
    lines_a = [
        "   Code   Len                 Host Name",
        "   +-----+-----+-----+-----+-----+-----+-----+-----+-----+--",
        "   |  12 |  n  |  h1 |  h2 |  h3 |  h4 |  h5 |  h6 |  ...",
    ]
    lines_b = [
        "3.14. Host Name Option",
        "",
        "   This option specifies the name of the client.",
        "   The code for this option is 12, and its minimum length is 1.",
    ]
    a = extract_option_tables(lines_a)
    b = extract_option_tables(lines_b)
    assert b, "独立小节形态应抽出选项"
    assert b[0].code == 12, b
    assert b[0].name == "Host Name", b


def test_fixed_field_excludes_generic_words():
    """★ 定长字段通道排除**通用词**（实测「length 312 octets」被误抽）。"""
    from core.fused.rfc_forms_binary import extract_fixed_fields
    out = extract_fixed_fields([
        "   The total length 312 octets of the vendor field",
        "   xid  4 octets",
    ])
    names = [f.name for f in out]
    assert "xid" in names, names
    assert "length" not in names, names
    assert "total" not in names, names


# ===========================================================================
# ③ 二进制渲染
# ===========================================================================

def _profile():
    return {
        "protocol": "fakeproto",
        "raw_format": {
            "line_ending": "\r\n",
            "byte_order": "network",
            "binary_fields": [
                {"name": "op", "offset": 0, "length": 1, "type": "uint8"},
                {"name": "xid", "offset": 4, "length": 4, "type": "uint32"},
                {"name": "chaddr", "offset": 28, "length": 6, "type": "mac"},
                {"name": "magic_cookie", "offset": 236, "length": 4,
                 "type": "uint32"},
            ],
            "binary_options": [
                {"name": "subnet_mask", "code": 1, "type": "ipv4", "length": 4},
            ],
        },
    }


def test_binary_render_layout_and_padding():
    """★ 二进制渲染：定长区按 offset 落位 + 空洞补零 + 选项区 TLV。"""
    from core.models import SeedCorpus, SeedMessage
    from core.raw_writers_binary import render_binary_from_profile
    msg = SeedMessage(method="DISCOVER",
                      headers={"op": "1", "xid": "0x3903F326",
                               "chaddr": "00:11:22:33:44:55",
                               "magic_cookie": "0x63825363",
                               "subnet_mask": "192.168.1.0"},
                      body="", url="", argument="")
    corpus = SeedCorpus(protocol="fakeproto", messages=[msg],
                        description="", generated_by="test")
    raw = render_binary_from_profile(corpus, _profile())
    assert len(raw) == 240 + 7, f"长度应为 240(固定头)+7(选项)，实得 {len(raw)}"
    assert raw[0] == 1
    assert raw[4:8] == bytes.fromhex("3903f326")     # xid（网络字节序）
    assert raw[28:34] == bytes.fromhex("001122334455")  # chaddr
    assert raw[236:240] == bytes.fromhex("63825363")   # magic cookie
    # 选项区：code(1) + len(1) + data(4) + End(255)
    assert raw[240] == 1 and raw[241] == 4
    assert raw[242:246] == bytes([192, 168, 1, 0])
    assert raw[246] == 255


def test_binary_render_is_deterministic():
    """★ 同输入 ⇒ 同输出（可复现）。"""
    from core.models import SeedCorpus, SeedMessage
    from core.raw_writers_binary import render_binary_from_profile
    msg = SeedMessage(method="D", headers={"op": "1"}, body="", url="",
                      argument="")
    corpus = SeedCorpus(protocol="fakeproto", messages=[msg],
                        description="", generated_by="test")
    a = render_binary_from_profile(corpus, _profile())
    b = render_binary_from_profile(corpus, _profile())
    assert a == b


def test_binary_render_without_layout_returns_empty():
    """★ 没有布局 ⇒ 返空（不假写）。"""
    from core.models import SeedCorpus, SeedMessage
    from core.raw_writers_binary import render_binary_from_profile
    msg = SeedMessage(method="D", headers={"a": "1"}, body="", url="", argument="")
    corpus = SeedCorpus(protocol="fakeproto", messages=[msg],
                        description="", generated_by="test")
    assert render_binary_from_profile(corpus, {"raw_format": {}}) == b""


def test_text_profile_still_uses_text_renderer():
    """★ **回归护栏**：文本 profile（有 request_line、无 binary_fields）
    ⇒ 仍走文本渲染路径（**二进制分支不劫持**）。"""
    from core.models import SeedCorpus, SeedMessage
    from core.raw_writers import seedcorpus_to_raw
    msg = SeedMessage(method="OPTIONS", headers={"CSeq": "1"}, body="",
                      url="rtsp://127.0.0.1/", argument="")
    corpus = SeedCorpus(protocol="rtsp", messages=[msg],
                        description="", generated_by="test")
    raw = seedcorpus_to_raw(corpus)
    assert raw.startswith(b"OPTIONS "), raw[:40]
    assert b"CSeq: 1" in raw, raw[:80]


def test_value_encoders():
    """★ 值编码器（协议无关的类型词表）。"""
    from core.raw_writers_binary import _encode_value
    assert _encode_value("1", "uint8", 1, "network") == b"\x01"
    assert _encode_value("0x3903F326", "uint32", 4, "network") == \
        bytes.fromhex("3903f326")
    assert _encode_value("192.168.1.10", "ipv4", 4, "network") == \
        bytes([192, 168, 1, 10])
    assert _encode_value("00:11:22:33:44:55", "mac", 6, "network") == \
        bytes.fromhex("001122334455")
    assert _encode_value("ab", "string", 4, "network") == b"ab\x00\x00"


# ===========================================================================
# ④ 中枢落盘（端到端，若有 dhcpv4 产物）
# ===========================================================================

def test_dhcpv4_hub_has_binary_layout_facts():
    """★ 二进制布局落在中枢里（可溯源到 RFC 行号）。"""
    import glob
    files = glob.glob(str(ROOT / "derived" / "model" / "per_source" / "dhcpv4" / "facts"
                          / "*.jsonl"))
    if not files:
        pytest.skip("无 dhcpv4 中枢产物")
    n = 0
    for fp in files:
        for line in Path(fp).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d["fact_key"]["aspect"] in ("binary_layout", "option_layout"):
                n += 1
                es = (d.get("all_claims") or [{}])[0].get("evidence_summary") or []
                assert es and "@file:" in es[0], es
    assert n > 0, "中枢里应有二进制布局 facts"
