# -*- coding: utf-8 -*-
"""tests/test_multifile_and_table_rows.py —— 多 RFC 消歧 + 表格行排除（2026-11-07）。

★ 三个问题的回归护栏：
  ① **协议名大小写校验**（`build_hub.py`）—— 目录名含大写的协议双向都过不了；
  ② **按文件限定的章节配置**（`sections_by_file`）—— 多 RFC 协议章节号大面积重号；
  ③ **表格数据行排除** —— 「编号 + 名称（缩写）」的表格行被误当标题/方法。

★ 关键回归：**文本协议（rtsp/sip/smtp）的产物必须不变**。
"""
from __future__ import annotations

import inspect



# ===========================================================================
# ① 协议名大小写校验
# ===========================================================================

def test_build_hub_protocol_name_check_is_case_insensitive():
    """★ `build_hub` 的协议名校验**两侧都要折叠大小写**。

    ★ 改前：``known = {p.name ...}``（不折叠）vs ``protocol.lower() not in known``
      （折叠）⇒ 目录名含大写的协议（``DHCPv4``）**双向都过不了**。
    """
    from scripts import build_hub
    src = inspect.getsource(build_hub)
    assert "p.name.lower() for p in paths.kb_root().iterdir()" in src, \
        "known 集合必须折叠小写"
    assert "protocol.lower() not in known" in src


# ===========================================================================
# ② 按文件限定的章节配置
# ===========================================================================

def test_section_kind_supports_file_specific_config():
    """★ `_section_kind` 支持 ``sections_by_file``（按文件限定章节）。"""
    from core.fused.extraction import rfc_extractor as RX
    assert "sections_by_file" in inspect.getsource(RX._section_kind)
    assert "src_name" in inspect.signature(RX._section_kind).parameters


def test_file_specific_config_wins_over_global():
    """★ 文件专属配置**优先**于全局配置。"""
    from core.fused.extraction import rfc_extractor as RX
    cfg = {
        "method_sections": ["4.3"],          # 全局：所有文件的 §4.3 都算 method
        "field_sections": [],
        "status_sections": [],
        "transition_sections": [],
        "sections_by_file": {
            # 这个文件：§4.3 明确**不是** method
            "other.txt": {"method_sections": [], "field_sections": ["4.3"],
                         "status_sections": [], "transition_sections": []},
        },
    }
    w = {"section_no": "4.3", "title": "x"}
    assert RX._section_kind(w, cfg, "other.txt") == "field"
    # 不在文件专属表里的文件 ⇒ 回退全局
    assert RX._section_kind(w, cfg, "main.txt") == "method"


def test_config_reads_sections_by_file():
    """★ ``rfc_config.json`` 的 ``sections_by_file`` 段能被读到。"""
    from core.fused.extraction import rfc_extractor as RX
    cfg = RX._load_rfc_config("dhcpv4")
    sbf = cfg.get("sections_by_file") or {}
    assert sbf, "dhcpv4 应配 sections_by_file"
    assert "rfc2131.txt" in sbf
    # 主体规范的 §4.3 = 消息类型（method）
    assert "4.3" in (sbf["rfc2131.txt"].get("method_sections") or [])


def test_dhcpv4_method_set_has_no_false_positive():
    """★ DHCPv4 的方法集**只含真消息类型**（无表格行误抽的 NVT）。"""
    from core.fused.extraction.rfc_extractor import extract_rfc_norms
    ns = extract_rfc_norms("DHCPv4")
    methods = {n["norm_id"].split(".")[-1].upper()
               for n in ns if n.get("kind") == "method"}
    assert "NVT" not in methods, methods
    for m in ("DHCPDISCOVER", "DHCPREQUEST"):
        assert m in methods, methods


# ===========================================================================
# ③ 表格数据行排除
# ===========================================================================

def test_table_data_row_is_not_a_heading():
    """★ 表格数据行（``0  Network Virtual Terminal (NVT) ...``）不是标题。

    ★ 实测踩坑：它被 `_RE_TOP_HEADING` 判成一级标题（number='0'）
      ⇒ 整段被当「方法章」⇒ 抽出误抽的方法 ``NVT``。
    """
    from core.fused.extraction import rfc_extractor as RX
    assert RX._parse_heading_shape(
        "0       Network Virtual Terminal (NVT) ASCII VPN identifier") is not None
    # ★ 但**窗口层**（kind 判定）必须排除它
    w = {"section_no": "0",
         "title": "Network Virtual Terminal (NVT) ASCII VPN identifier"}
    cfg = {"method_sections": ["4.3"], "field_sections": [],
           "status_sections": [], "transition_sections": []}
    assert RX._section_kind(w, cfg) is None
    assert RX._infer_kind_from_content(w) is None


def test_real_headings_unaffected_by_table_row_exclusion():
    """★ 真标题**不受**表格行排除影响（章节号 "0" 之外全放行）。"""
    from core.fused.extraction import rfc_extractor as RX
    for t, num in (("10.1 OPTIONS", "10.1"), ("5 General Header Fields", "5"),
                   ("4.3.  Required Support", "4.3")):
        h = RX._parse_heading_shape(t)
        assert h is not None and h.number == num, (t, h)


def test_wrapped_toc_entry_still_treated_as_heading_shape():
    """★ 折行的**目录条目**在形态上仍像标题（靠目录块隔离，不靠标题排除）。

    ★ 这是与表格数据行排除**必须分开**的机制（实测踩过：
      在 `_parse_heading` 里排除表格行 ⇒ 破坏了目录块兜底 ⇒ SIP 目录条目污染）。
    """
    from core.fused.extraction import rfc_extractor as RX
    wrapped = "   26         Security Considerations: Threat Model and Security"
    assert RX._parse_heading_shape(wrapped) is not None


def test_text_protocols_method_sets_unchanged():
    """★ **回归护栏**：三个文本协议的方法集必须与基线一致。"""
    from core.fused.extraction.rfc_extractor import extract_rfc_norms
    expected = {
        "rtsp": {"ANNOUNCE", "DESCRIBE", "GET_PARAMETER", "OPTIONS", "PAUSE",
                 "PLAY", "RECORD", "REDIRECT", "SETUP", "SET_PARAMETER",
                 "TEARDOWN"},
        "sip": {"ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"},
        "smtp": {"AUTH", "DATA", "EHLO", "EXPN", "HELP", "MAIL", "NOOP",
                 "QUIT", "RCPT", "RSET", "STARTTLS", "VRFY"},
    }
    for proto, want in expected.items():
        ns = extract_rfc_norms(proto)
        got = {n["norm_id"].split(".")[-1].upper()
               for n in ns if n.get("kind") == "method"}
        assert got == want, f"{proto}: 多 {got - want} / 少 {want - got}"


# ===========================================================================
# ④ 停用词表：不能误伤真字段
# ===========================================================================

def test_generic_stopwords_do_not_hurt_real_fields():
    """★ 停用词表**不得**含某协议的合法头名/方法名。

    ★ 实测踩坑：加了 ``OPTIONS`` / ``SERVER`` ⇒ **误伤 RTSP 的真字段**
      （``rtsp.field.server`` = Server 头、``rtsp.method.options`` = OPTIONS 方法）
      ⇒ 头字段与方法**双双丢失**。
    """
    from core.fused.extraction import rfc_extractor as RX
    for word in ("OPTIONS", "SERVER", "REQUEST", "CLIENT", "SECURITY"):
        assert word not in RX._GENERIC_SECTION_WORDS, \
            f"停用词表含 {word} ⇒ 可能误伤某协议的真字段"


def test_protocol_own_name_excluded_from_fields():
    """★ 协议自身名（含词干形态）不该被当成字段。

    实测：RFC 3396 §2 Terminology 的缩进术语条目 ``   DHCP``
    ⇒ 被当成字段 ``DHCP`` / ``DHCPv4``。
    """
    from core.fused.extraction import rfc_extractor as RX
    src = inspect.getsource(RX._extract_rfc_file)
    assert "协议自身名" in src, "字段通道应排除协议自身名"


def test_dhcpv4_headers_bucket_has_no_protocol_name():
    """★ DHCPv4 的 headers 桶里**没有协议自身名**（``DHCP`` / ``DHCPv4``）。

    ★ 但**消息类型名**（``DHCPOFFER`` / ``DHCPACK`` …）是**真字段**（RFC 2131
      §4.3 定义的报文类型）⇒ 不在排除范围内。
    """
    from core.fused.downstream import rag_seedgen as RS
    b = RS.assemble_bundle(RS.load_fact_views("DHCPv4"), "DHCPv4")
    bad = [h for h in b["headers"] if h.lower() in ("dhcp", "dhcpv4")]
    assert not bad, bad
