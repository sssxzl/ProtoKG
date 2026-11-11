"""tests/test_resolver.py —— 统一消解引擎（P2a）。"""
from __future__ import annotations

from core.fused.downstream.resolver import (
    resolve_claims, evidence_strength, SOURCE_PRIORITY,
)


def _c(value, epi="descriptive", auth="source", cid=""):
    return {
        "claim_id": cid or f"c_{auth}_{epi}",
        "value": {"type": "scalar", "data": value},
        "epistemic_type": epi,
        "authority": auth,
    }


def test_single_claim():
    r = resolve_claims([_c(True, "observed", "traffic")], "existence")
    assert r["method"] == "single"
    assert r["value"]["data"] is True
    assert r["authority"] == "traffic"


def test_empty_claims_insufficient():
    r = resolve_claims([], "existence")
    assert r["method"] == "insufficient"


def test_precedence_observed_over_descriptive():
    """existence：observed（traffic 实测）覆盖 descriptive（source 声明）。"""
    claims = [
        _c(True, "descriptive", "source"),
        _c(True, "observed", "traffic"),
    ]
    r = resolve_claims(claims, "existence")
    assert r["method"] == "precedence"
    assert r["authority"] == "traffic"
    assert r["epistemic"] == "observed"
    # 被覆盖的 claim 保留 superseded
    assert any("source" in s for s in r["superseded"])


def test_union_value_enum_merges_sources():
    """value_enum：多源取值并集合并（互补不冲突）。"""
    claims = [
        {"claim_id": "c1", "value": {"type": "set", "data": ["A", "B"]},
         "epistemic_type": "descriptive", "authority": "source"},
        {"claim_id": "c2", "value": {"type": "set", "data": ["B", "C"]},
         "epistemic_type": "observed", "authority": "traffic"},
    ]
    r = resolve_claims(claims, "value_enum_spec")
    assert r["method"] == "union"
    assert r["value"]["data"] == ["A", "B", "C"]
    assert len(r["basis_claim_ids"]) == 2
    assert r["superseded"] == []


def test_consensus_same_value():
    claims = [
        _c("hello", "descriptive", "source"),
        _c("hello", "normative", "rfc"),
    ]
    r = resolve_claims(claims, "definition")
    assert r["method"] == "consensus"
    assert r["value"]["data"] == "hello"


def test_conflict_same_priority_different_value():
    """同优先级但值不同 → conflict，不误选（保留）。"""
    claims = [
        _c("X", "descriptive", "source"),
        _c("Y", "descriptive", "expert_note"),
    ]
    r = resolve_claims(claims, "definition")
    assert r["method"] == "conflict"
    assert len(r["basis_claim_ids"]) == 2


def test_evidence_strength():
    assert evidence_strength([_c(1, "descriptive")]) == "low"
    assert evidence_strength([_c(1, "observed", "traffic")]) == "medium"
    assert evidence_strength([
        _c(1, "observed", "traffic", "c1"),
        _c(1, "observed", "traffic", "c2"),
    ]) == "high"


def test_source_priority_order():
    assert SOURCE_PRIORITY["observed"] > SOURCE_PRIORITY["normative"] \
        > SOURCE_PRIORITY["descriptive"]
