"""tests/fused/test_models.py —— Layer 0 数据结构测试。"""
from __future__ import annotations

import pytest

from core.fused.models import (
    Subject, FactKey, ConditionAlways, ConditionPredicate, ConditionAnd,
    ConditionNot, ConditionRef, Value, Scope, Evidence, LocatorLine,
    LocatorField, Resolution, Support, Generalization, Claim, Fact,
    FactMetadata, Alignment,
)


def test_subject_frozen_and_field_default_independent():
    """frozen + qualifiers 缺省 dict 每次构造独立。"""
    a = Subject(type="method", name="SETUP")
    b = Subject(type="method", name="SETUP")
    assert a.qualifiers is not b.qualifiers
    with pytest.raises(Exception):  # frozen
        a.name = "PLAY"  # type: ignore[misc]


def test_subject_recursive_relation():
    """关系作为 Subject, qualifiers 嵌套 Subject。"""
    src = Subject(type="method", name="SETUP")
    tgt = Subject(type="method", name="PLAY")
    rel = Subject(type="relation", name="transitions_to",
                  qualifiers={"source": src, "target": tgt})
    assert rel.qualifiers["source"].name == "SETUP"
    assert rel.qualifiers["target"].name == "PLAY"


def test_value_12_types_via_string():
    """value_type 是字符串(开放), 12 种仅作为 Layer 1 候选参考。"""
    v = Value(type="sequence", data=["OPTIONS", "DESCRIBE", "SETUP"])
    assert v.type == "sequence"
    assert v.data[1] == "DESCRIBE"


def test_fact_key_minimal():
    fk = FactKey(protocol="rtsp", version="1.0",
                 subject=Subject(type="method", name="SETUP"),
                 aspect="existence", condition=ConditionAlways())
    assert fk.protocol == "rtsp"
    assert fk.condition.type == "always"


def test_condition_predicate_required_fields():
    c = ConditionPredicate(subject=Subject(type="method", name="SETUP"),
                           aspect="value_type", op="in",
                           value=Value(type="set", data={"string", "int"}))
    assert c.op == "in"
    assert c.value.type == "set"


def test_condition_compound_and_not():
    a = ConditionPredicate(subject=None, aspect="a", op="eq",
                           value=Value(type="scalar", data=1))
    b = ConditionPredicate(subject=None, aspect="b", op="eq",
                           value=Value(type="scalar", data=2))
    assert ConditionAnd(operands=(a, b)).type == "and"
    assert ConditionNot(operand=a).type == "not"
    assert ConditionRef(condition_id="c1_abc").type == "ref"


def test_evidence_with_locator_field():
    loc = LocatorField(file="rfc2326.txt", path=("10", "4"))
    ev = Evidence(evidence_id="e1_x", claim_id="c1_y",
                  source_type="rfc", source_id="rfc2326.txt",
                  document="rfc2326.txt", locator=loc)
    assert ev.locator.path == ("10", "4")


def test_resolution_minimum():
    r = Resolution(status="resolved", method="single",
                   basis_claim_ids=("c1_a",),
                   reason="single claim", reason_code="OK",
                   policy_version="v1")
    assert r.status == "resolved"
    assert r.support is None


def test_resolution_with_support_and_generalization():
    r = Resolution(
        status="resolved", method="consensus",
        basis_claim_ids=("c1_a", "c1_b"),
        reason="two independent", reason_code="OK", policy_version="v1",
        support=Support(independent=2, dependent=0, unknown=0, total=2),
        generalization=Generalization(scope="protocol-wide", confidence=0.95))
    assert r.support.independent == 2
    assert r.generalization.confidence == 0.95


def test_fact_minimal():
    f = Fact(
        fact_id="f1_x",
        fact_key=FactKey(protocol="rtsp", version="1.0",
                         subject=Subject(type="method", name="SETUP"),
                         aspect="existence", condition=ConditionAlways()),
        metadata=FactMetadata(created_at="2026-10-08", profile_version="v1"))
    assert f.fact_id == "f1_x"
    assert f.claims == ()
    assert f.resolution is None