# -*- coding: utf-8 -*-
"""tests/test_batch3_message_list_and_backfill.py —— 批次 3 的护栏。

★ 覆盖三件事：
  ① **通道 A0d：消息清单表**（RFC 2131 §3.1 的表 2）
     —— 解「服务器方向消息没有独立小节 ⇒ 抽不到」这个实测缺口；
  ② **S3 两通道互补**（config 优先 + content 补漏）；
  ③ **A1 候选定位换判据**（实体共现，与旧判据并集）。

★ 关键回归护栏：
  · 三个文本协议的**方法集必须不变**（rtsp 11 / sip 6 / smtp 12）；
  · DHCPv4 的方法集必须是**全部 8 个**消息（含 3 个服务器方向）。
"""
from __future__ import annotations

import pytest


# ===========================================================================
# ① 通道 A0d：消息清单表
# ===========================================================================

def test_message_list_entry_extraction():
    """★ 消息清单表形态（RFC 2131 §3.1 表 2）。

    ★ 形态：缩进 + 消息名 + ``-`` + 用途描述。
    ★ 与「命令条目」（``名称 (缩写)``）**不同构** ⇒ 不冲突。
    """
    from core.fused.extraction.rfc_extractor import _extract_message_list_entries
    text = ("   Message         Use\n"
            "   -------         ---\n"
            "\n"
            "   DHCPDISCOVER -  Client broadcast to locate available servers.\n"
            "\n"
            "   DHCPOFFER    -  Server to client in response to DHCPDISCOVER with\n"
            "                   offer of configuration parameters.\n")
    got = {n for n, _d in _extract_message_list_entries(text)}
    assert "DHCPDISCOVER" in got, got
    assert "DHCPOFFER" in got, got


def test_message_list_excludes_table_column_marks():
    """★ 排除**表格列标记**（SIP §28 的 ``Expires   -   -   -   o``）。

    ★ 那是**头字段表**，不是消息清单 ⇒ 排除。
    """
    from core.fused.extraction.rfc_extractor import _extract_message_list_entries
    text = ("      Expires                              -   -   -   o   -   o\n"
            "      From                    c       r    m   m   m   m   m   m\n")
    got = _extract_message_list_entries(text)
    assert not got, got


def test_message_list_does_not_hit_text_protocols():
    """★ 消息清单表在三个文本协议上**几乎不命中** ⇒ 不污染。"""
    from core.fused.extraction.rfc_extractor import _extract_message_list_entries
    import pathlib
    counts = {}
    for proto in ("rtsp", "sip", "smtp"):
        n = 0
        for f in sorted(pathlib.Path(f"kb/{proto}/spec").glob("*.txt")):
            n += len(_extract_message_list_entries(
                f.read_text(encoding="utf-8", errors="ignore")))
        counts[proto] = n
    # rtsp/smtp 必须 0；sip 允许少量（实测 1：Expires，已被表格列标记排除 ⇒ 0）
    assert counts["rtsp"] == 0, counts
    assert counts["smtp"] == 0, counts
    assert counts["sip"] <= 1, counts


def test_dhcpv4_methods_include_server_messages():
    """★ DHCPv4 的方法集必须是**全部 8 个**消息（含 3 个服务器方向）。

    ★ 这是「状态机断裂 ⇒ 只 1 条种子」的根因修复点
      （RFC 2131 的 DHCPOFFER/DHCPACK/DHCPNAK **没有独立小节**）。
    """
    from core.fused.extraction.rfc_extractor import extract_rfc_norms
    ns = extract_rfc_norms("DHCPv4")
    methods = {n["name"].upper() for n in ns if n.get("kind") == "method"}
    for want in ("DHCPDISCOVER", "DHCPOFFER", "DHCPREQUEST", "DHCPACK",
                 "DHCPNAK", "DHCPDECLINE", "DHCPRELEASE", "DHCPINFORM"):
        assert want in methods, (want, sorted(methods))
    assert "NVT" not in methods, methods


# ===========================================================================
# ② S3：两通道互补
# ===========================================================================

def test_backfill_kinds_default_empty():
    """★ 补漏白名单**缺省为空** ⇒ 旧行为完全不变。"""
    from core.fused.extraction.rfc_extractor import _load_rfc_config
    for proto in ("rtsp", "sip", "smtp"):
        assert _load_rfc_config(proto).get("content_backfill_kinds") == []


def test_backfill_kinds_is_configurable():
    """★ 补漏白名单可按协议配置（DHCPv4 配了 3 类）。"""
    from core.fused.extraction.rfc_extractor import _load_rfc_config
    cfg = _load_rfc_config("DHCPv4")
    assert "outcome" in cfg.get("content_backfill_kinds", [])


def test_backfill_only_when_config_judges_none():
    """★ 互补语义：**config 判出 ⇒ 不用 content**（config 优先）。"""
    from core.fused.extraction import rfc_extractor as RX
    cfg = {"method_sections": ["4.3"], "field_sections": [],
           "status_sections": [], "transition_sections": [],
           "sections_by_file": {},
           "content_backfill_kinds": ["outcome"]}
    # §4.3 在 method_sections 里 ⇒ config 判出 method ⇒ 不该被 content 覆盖
    w = {"section_no": "4.3", "title": "Prose Heading",
         "text": "   Just prose."}
    assert RX._section_kind(w, cfg) == "method"


# ===========================================================================
# ③ A1：候选定位换判据
# ===========================================================================

def test_entity_names_collected_from_deterministic_channels():
    """★ 实体名来自**已有确定性通道**（ABNF / 散文 / 消息清单表 / 章节标题）。

    ★ 不认协议名 ⇒ 换协议自动生效。
    """
    from core.fused.extraction.rfc_extractor import _protocol_entity_names
    dhcp = _protocol_entity_names("DHCPv4")
    assert "DHCPOFFER" in dhcp, sorted(dhcp)
    rtsp = _protocol_entity_names("rtsp")
    assert "SETUP" in rtsp, sorted(rtsp)


def test_dhcpv4_transition_candidates_found():
    """★ DHCPv4 的候选段落**不再是 0**（这是本批次的核心目的）。

    ★ 实测：旧判据（``state machine`` 字样）在 36 份 DHCP RFC 里命中 **0**
      ⇒ LLM 状态机通道从未被调用 ⇒ transitions 只能来自骨架。
    """
    from core.fused.extraction.rfc_extractor import extract_transition_candidates
    cands = extract_transition_candidates("DHCPv4")
    assert cands, "DHCPv4 没有候选段落 ⇒ LLM 通道仍是死的"
    files = {c["source"].split("/")[-1].split("#")[0] for c in cands}
    assert len(files) >= 3, files


def test_transition_prompt_has_skeleton_constraint():
    """★ prompt 含**骨架约束**（实体白名单）⇒ 抑制幻觉迁移。

    ★ 且 **prompt_version 必须同步升**（缓存键含它 ⇒ 不升会读旧缓存）。
    """
    from core.fused.extraction.rfc_extractor import (_PROMPT_TRANSITION,
                                          TRANSITION_PROMPT_VERSION)
    assert "{skeleton_constraint}" in _PROMPT_TRANSITION
    assert "skeleton" in TRANSITION_PROMPT_VERSION.lower()


def test_skeleton_constraint_built_from_entities():
    """★ 骨架约束能构造出**实体白名单**（状态 + 消息）。"""
    from core.fused.extraction.rfc_extractor import _build_skeleton_constraint
    text, states, msgs = _build_skeleton_constraint("DHCPv4")
    assert msgs, "消息白名单为空"
    assert "DHCPOFFER" in msgs, sorted(msgs)
    assert "不得引入列表外的新状态" in text or "不得引入列表外的新消息" in text


# ===========================================================================
# ④ 文本协议回归（硬护栏）
# ===========================================================================

@pytest.mark.parametrize("protocol,expected", [
    ("rtsp", {"ANNOUNCE", "DESCRIBE", "GET_PARAMETER", "OPTIONS", "PAUSE",
              "PLAY", "RECORD", "REDIRECT", "SETUP", "SET_PARAMETER",
              "TEARDOWN"}),
    ("sip", {"ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"}),
    ("smtp", {"AUTH", "DATA", "EHLO", "EXPN", "HELP", "MAIL", "NOOP",
              "QUIT", "RCPT", "RSET", "STARTTLS", "VRFY"}),
])
def test_text_protocol_methods_unchanged(protocol, expected):
    """★ 三个文本协议的**方法集完全不变**（批次 3 的硬护栏）。"""
    from core.fused.extraction.rfc_extractor import extract_rfc_norms
    ns = extract_rfc_norms(protocol)
    got = {n["name"].upper() for n in ns if n.get("kind") == "method"}
    assert got == expected, (protocol, sorted(got - expected),
                             sorted(expected - got))
