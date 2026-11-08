# -*- coding: utf-8 -*-
"""tests/fused/test_hub_slots_and_entities.py —— 中枢重设计**阶段 A**的护栏。

★ 覆盖：
  ① 槽位契约（``knowledge_slots.json``）的自洽与落位判定；
  ② 实体主表（``entity_id`` 的稳定性、跨分类唯一性）；
  ③ 诊断矩阵（实体 × 分类）的正确性。

★ 关键回归：
  · **契约覆盖全部已注册 aspect**（漏一个 ⇒ 该维度的知识无处安放）；
  · 实体 id **跨源稳定**（同一实体任何源都是同一个 id ⇒ 图/事实可对齐）。
"""
from __future__ import annotations

import json

import pytest


# ===========================================================================
# ① 槽位契约
# ===========================================================================

def test_slots_contract_validates():
    """★ 槽位契约自洽（每个 aspect 有落位、槽位存在、entity_types 合法）。"""
    from core.fused.knowledge_slots import validate_slots
    problems = validate_slots()
    assert not problems, problems


def test_all_registered_aspects_have_a_location():
    """★ **每个已注册 aspect 都有落位**（漏一个 ⇒ 该维度无处安放）。"""
    from core.fused.knowledge_slots import aspect_map, load_slots
    from core import paths
    reg = json.loads(
        (paths.PROJECT_ROOT / "fused_hub" / "schema" / "aspect_registry.json")
        .read_text(encoding="utf-8"))
    am = aspect_map()
    missing = [str(a.get("name")) for a in (reg.get("registered_aspects") or [])
               if a.get("name") and str(a["name"]) not in am]
    assert not missing, f"未登记落位的 aspect: {missing}"


def test_locate_by_aspect_and_entity_type():
    """★ 落位判定：aspect + 实体类型 ⇒ (category, slot)。"""
    from core.fused.knowledge_slots import locate
    assert locate("definition", "method") == ("A_structure", "methods")
    assert locate("definition", "header") == ("A_structure", "headers")
    assert locate("definition", "status") == ("A_structure", "statuses")
    assert locate("target_state", "relation") == ("B_interaction", "transitions")
    assert locate("message_instance", "relation") == ("B_interaction", "instances")
    assert locate("required_headers", "method") == \
        ("C_constraints", "required_headers")
    assert locate("legal_boundary", "header") == \
        ("C_constraints", "value_constraints")
    assert locate("binary_layout", "header") == ("D_construction", "layout")
    assert locate("occurrence", "header") == ("E_observation", "frequency")


def test_locate_unknown_aspect_returns_none():
    """★ 未知 aspect ⇒ None（不静默落到某个桶）。"""
    from core.fused.knowledge_slots import locate
    assert locate("no_such_aspect", "header") is None


def test_six_categories_present():
    """★ 六个知识分类齐备（A~F）。"""
    from core.fused.knowledge_slots import category_ids
    ids = category_ids()
    for want in ("A_structure", "B_interaction", "C_constraints",
                 "D_construction", "E_observation", "F_security"):
        assert want in ids, ids


# ===========================================================================
# ② 实体主表
# ===========================================================================

def test_entity_id_is_stable():
    """★ 实体 id **跨源稳定**（同一实体任何源都是同一个 id）。"""
    from core.fused.hub_entities import entity_id, parse_entity_id
    eid = entity_id("SIP", "method", "INVITE")
    assert eid == "sip:method:invite", eid
    assert parse_entity_id(eid) == ("sip", "method", "invite")


def test_entity_id_normalizes_whitespace_and_case():
    """★ 名字归一（大小写 + 连续空白折叠成一个下划线）。"""
    from core.fused.hub_entities import entity_id
    assert entity_id("sip", "header", "Accept  Encoding") == \
        "sip:header:accept_encoding"
    assert entity_id("sip", "header", "Accept-Encoding") == \
        "sip:header:accept-encoding"


def test_entity_index_from_facts():
    """★ 实体主表能从 fact 构造，且**实体数 ≤ fact 数**（有归并）。"""
    from core.fused.hub_entities import build_entity_index
    facts = [
        {"fact_key": {"protocol": "sip", "aspect": "definition",
                      "subject": {"type": "method", "name": "INVITE"}}},
        {"fact_key": {"protocol": "sip", "aspect": "existence",
                      "subject": {"type": "method", "name": "INVITE"}}},
        {"fact_key": {"protocol": "sip", "aspect": "definition",
                      "subject": {"type": "header", "name": "Accept"}}},
    ]
    ents, detail = build_entity_index(facts)
    ids = {e["entity_id"] for e in ents}
    assert "sip:method:invite" in ids
    assert "sip:header:accept" in ids
    assert len(ents) == 2, ents
    assert detail["sip:method:invite"] == ["definition", "existence"]


def test_relation_entity_gets_participants():
    """★ 关系型实体独立登记，且带 **participants**（source/via/target）。"""
    from core.fused.hub_entities import build_entity_index
    facts = [{"fact_key": {
        "protocol": "sip", "aspect": "target_state",
        "subject": {"type": "relation", "name": "transitions_to",
                    "qualifiers": {
                        "source": {"type": "state", "name": "Idle"},
                        "target": {"type": "state", "name": "Registered"},
                        "method": {"type": "method", "name": "REGISTER"}}}}}]
    ents, _d = build_entity_index(facts)
    rel = [e for e in ents if e["type"] == "relation"]
    assert rel, ents
    roles = {p["role"] for p in rel[0]["participants"]}
    assert roles == {"source", "via", "target"}, rel[0]


def test_entity_index_is_deterministic():
    """★ 实体主表**确定性**（同输入同输出，逐字节可复现）。"""
    from core.fused.hub_entities import build_entity_index
    facts = [
        {"fact_key": {"protocol": "sip", "aspect": "definition",
                      "subject": {"type": "method", "name": "INVITE"}}},
        {"fact_key": {"protocol": "sip", "aspect": "definition",
                      "subject": {"type": "header", "name": "Accept"}}},
    ]
    a, _ = build_entity_index(facts)
    b, _ = build_entity_index(list(reversed(facts)))
    assert a == b, "实体主表不是确定性的"


# ===========================================================================
# ③ 诊断矩阵
# ===========================================================================

def test_category_matrix_detects_cross_category_entities():
    """★ 诊断矩阵能识别**跨分类重复**的实体（诊断 P2）。"""
    from core.fused.hub_entities import entity_category_matrix
    facts = [
        {"fact_key": {"protocol": "sip", "aspect": "definition",
                      "subject": {"type": "method", "name": "INVITE"}}},
        {"fact_key": {"protocol": "sip", "aspect": "required_headers",
                      "subject": {"type": "method", "name": "INVITE"}}},
        {"fact_key": {"protocol": "sip", "aspect": "definition",
                      "subject": {"type": "header", "name": "Accept"}}},
    ]
    m = entity_category_matrix(facts)
    assert m["cross_category"] == 1, m
    assert m["single_category"] == 1, m
    cats = m["by_entity"]["sip:method:invite"]
    assert cats == ["A_structure", "C_constraints"], cats


def test_category_matrix_counts_by_category():
    """★ 矩阵按分类计数。"""
    from core.fused.hub_entities import entity_category_matrix
    facts = [
        {"fact_key": {"protocol": "sip", "aspect": "target_state",
                      "subject": {"type": "relation", "name": "transitions_to",
                                  "qualifiers": {
                                      "source": {"type": "state",
                                                 "name": "Idle"},
                                      "target": {"type": "state",
                                                 "name": "Ready"},
                                      "method": {"type": "method",
                                                 "name": "INVITE"}}}}},
    ]
    m = entity_category_matrix(facts)
    assert m["by_category"].get("B_interaction", 0) >= 1, m
