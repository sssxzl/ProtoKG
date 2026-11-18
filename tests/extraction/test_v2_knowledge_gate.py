# -*- coding: utf-8 -*-
"""★ N2-B0-V2：★ **知识类型闸门单元测试**（★ 判据边界）。

★ 重点覆盖 §二/§四/§五 的禁止项与关键边界：
  · ★ 「包含 must ⇒ 规范规则」**被禁止**（★ 版权声明含 must）
  · ★ 「包含 copyright ⇒ 整块删除」**被禁止**（★ 证据跨度必须保留）
  · ★ 陈述式规范句（★ 无 BCP14 关键词）**不得**被描述性规则误排除
  · ★ strength 不得被擅自提升为 MUST
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/_fixtures/v2"))
import v2_knowledge_gate as V2


# ══ ① 非协议元数据（★ 含 must 但不是规范规则）══
def test_copyright_with_must_is_not_normative_rule():
    """★ ★ **禁止**「包含 must ⇒ 规范规则」：★ 版权声明含 must 仍判元数据。"""
    _s = ("However, this document itself may not be modified in any way, such as by "
          "removing the copyright notice or references to the Internet Society, "
          "except as needed for the purpose of developing Internet standards in "
          "which case the procedures for copyrights defined in the Internet "
          "Standards process must be followed.")
    _sk, _kk, _el, _r, _sig = V2.classify_sentence(_s, [_s])
    assert _kk != V2.NORMATIVE_RULE_CANDIDATE
    assert _el == "ineligible"
    assert _kk == V2.NON_PROTOCOL_METADATA


def test_copyright_clause_is_isolated_not_deleted():
    """★ ★ **禁止**「含 copyright ⇒ 整块删除」：★ 只判该句，★ 证据必须保留。"""
    _out = V2.classify_candidate(
        candidate_id="x", source_doc="rfc3207.txt", source_sha256="deadbeef",
        source_span=469,
        lines=["line1", "copyright notice", "must be followed"], anchor=3,
        entity="copyright", action="followed",
        object_="the procedures for copyrights defined in the Internet Standards process",
        strength="MUST")
    assert _out["route"] == V2.ROUTE_METADATA
    # ★ 证据跨度必须保留原文
    assert _out["evidence_span"]["text"]
    assert _out["evidence_span"]["line"]
    assert _out["reason"]


def test_metadata_zone_detected_by_structure():
    """★ 结构位置（元数据章节）⇒ 元数据，★ 不靠关键词一刀切。"""
    _lines = ["3. Definitions", "some text", "Copyright Notice",
              "The procedures for copyrights must be followed by all users."]
    _out = V2.classify_candidate(
        candidate_id="y", source_doc="rfc.txt", source_sha256="s", source_span=4,
        lines=_lines, anchor=4, entity="procedures", action="followed",
        object_="copyrights", strength="MUST")
    assert _out["knowledge_kind"] == V2.NON_PROTOCOL_METADATA
    assert _out["route"] == V2.ROUTE_METADATA


# ══ ② 协议语法（ABNF）══
def test_abnf_production_is_syntax():
    _lines = ["Status-Code =", '   "200" ; OK', '   "404" ; Not Found']
    _out = V2.classify_candidate(
        candidate_id="z", source_doc="rfc2326.txt", source_sha256="s",
        source_span=3, lines=_lines, anchor=3, entity="404",
        action="", object_="", strength="")
    assert _out["knowledge_kind"] == V2.PROTOCOL_SYNTAX
    assert _out["route"] == V2.ROUTE_STRUCTURED
    assert V2.STRUCTURED_ASPECT[V2.PROTOCOL_SYNTAX][0] == "syntax"


# ══ ③ 登记 / 枚举 ══
def test_registry_enumeration_is_structured():
    _lines = ["The following status codes are registered:",
              '   "100" ; Continue']
    _out = V2.classify_candidate(
        candidate_id="w", source_doc="rfc2326.txt", source_sha256="s",
        source_span=2, lines=_lines, anchor=2, entity="100", action="",
        object_="", strength="")
    assert _out["knowledge_kind"] == V2.PROTOCOL_REGISTRY
    assert V2.STRUCTURED_ASPECT[V2.PROTOCOL_REGISTRY][0] == "value_enum_spec"


# ══ ④ 规范规则候选 ══
def test_bcp14_with_protocol_actor_is_rule():
    _s = "The server MUST include a list of extensions in the response."
    _sk, _kk, _el, _r, _sig = V2.classify_sentence(_s, [_s])
    assert _kk == V2.NORMATIVE_RULE_CANDIDATE
    assert _el == "eligible"
    assert V2.route_of(_kk, _el) == V2.ROUTE_RULE


def test_strength_must_not_be_promoted_to_must():
    """★ ★ 无 BCP14 关键词时 **strength 保持 unknown**，★ 不得提升为 MUST。"""
    _s = ("If a DHCP server that is not configured to support BOOTP clients "
          "receives a BOOTREQUEST message from a BOOTP client, that server "
          "silently discards the BOOTREQUEST message.")
    _decl, _r = V2.is_declarative_normative(_s)
    assert _decl is True
    assert "unknown" in _r


def test_declarative_normative_not_treated_as_descriptive():
    """★ ★ 陈述式规范句 **不得**被描述性规则误排除。"""
    _s = ("If the recipient of the message does not understand the request, "
          "the sender should not attempt to use this method again.")
    _decl, _r = V2.is_declarative_normative(_s)
    assert _decl is True


def test_pure_description_is_descriptive():
    _s = "The format of DHCP messages is based on the format of BOOTP messages."
    _sk, _kk, _el, _r, _sig = V2.classify_sentence(_s, [_s])
    assert _kk == V2.PROTOCOL_DESCRIPTIVE
    assert _el == "ineligible"
    assert V2.route_of(_kk, _el) == V2.ROUTE_DESCRIPTIVE


# ══ ⑤ 不确定 ⇒ uncertain ══
def test_ambiguous_strength_only_is_uncertain():
    """★ 含强度词但主体/行为不明 ⇒ uncertain（★ 不猜测）。"""
    _s = "This must be done."
    _sk, _kk, _el, _r, _sig = V2.classify_sentence(_s, [_s])
    assert _kk == V2.MIXED_OR_UNCERTAIN
    assert _el == "uncertain"
    assert V2.route_of(_kk, _el) == V2.ROUTE_REVIEW


def test_empty_sentence_is_uncertain():
    _sk, _kk, _el, _r, _sig = V2.classify_sentence("", [])
    assert _el == "uncertain"


# ══ ⑥ 不新建 aspect / 不删除知识 ══
def test_no_new_aspect_introduced():
    """★ V2 **不得**引入新 aspect；★ 只引用既有通道。"""
    assert set(V2.STRUCTURED_ASPECT.values()) <= {
        ("syntax", "A_structure/headers"),
        ("value_enum_spec", "D_construction/case_rules"),
        ("definition", "A_structure/by_entity_type"),
    }


def test_all_routes_preserve_knowledge():
    """★ 每条都有 route（★ 不存在「丢弃」出口）。"""
    for _k in ("rule_channel", "structured_channel", "metadata_channel",
               "descriptive_channel", "pending_review"):
        assert _k in (V2.ROUTE_RULE, V2.ROUTE_STRUCTURED, V2.ROUTE_METADATA,
                      V2.ROUTE_DESCRIPTIVE, V2.ROUTE_REVIEW)


def test_v2_output_has_required_fields():
    _out = V2.classify_candidate(
        candidate_id="t", source_doc="rfc.txt", source_sha256="s", source_span=2,
        lines=["a", "The server MUST include a list."], anchor=2,
        entity="server", action="include", object_="list", strength="MUST")
    for _k in ("candidate_id", "source_doc", "source_sha256", "source_span",
               "source_kind", "knowledge_kind", "rule_eligibility",
               "evidence_span", "reason", "route"):
        assert _k in _out, _k


def test_no_llm_calls_in_v2():
    _t = (ROOT / "guard/_out/_n1c_v2/v2_knowledge_gate.py").read_text(encoding="utf-8")
    assert "DeepSeekClient" not in _t
    assert "chat_json" not in _t


def test_v0_v1_unchanged():
    """★ V0 / V1 **不得**被 V2 修改。"""
    import hashlib
    _base = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                        / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                        / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _base["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        _now = hashlib.sha256(_p.read_bytes()).hexdigest()
        assert _now == _h[_k], f"{_k}: ★ V2 不得修改 V0/V1"
