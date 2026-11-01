"""tests/fused/test_canonical.py —— canonical 序列化与 ID 计算。"""
from __future__ import annotations

from core.fused.canonical import (
    canonical_serialize, compute_fact_id, compute_claim_id,
    compute_evidence_id, _self_tests,
)
from core.fused.models import (
    Subject, FactKey, ConditionAlways, ConditionPredicate, Value,
    LocatorField, Evidence, Claim,
)


def test_self_tests_pass():
    """模块加载时自测应当全过。"""
    passed, total = _self_tests()
    assert passed == total, f"canonical 自测 {passed}/{total}"


def test_deterministic_same_logical_content():
    a = FactKey(protocol="rtsp", version="1.0",
                subject=Subject(type="method", name="SETUP"),
                aspect="existence", condition=ConditionAlways())
    b = FactKey(protocol="rtsp", version="1.0",
                subject=Subject(type="method", name="SETUP"),
                aspect="existence", condition=ConditionAlways())
    assert canonical_serialize(a) == canonical_serialize(b)


def test_dict_key_sorting():
    a = Subject(type="method", name="SETUP",
                qualifiers={"z": 1, "a": 2})
    b = Subject(type="method", name="SETUP",
                qualifiers={"a": 2, "z": 1})
    assert canonical_serialize(a) == canonical_serialize(b)


def test_relation_subject_recursive():
    src = Subject(type="method", name="SETUP")
    tgt = Subject(type="method", name="PLAY")
    rel = Subject(type="relation", name="transitions_to",
                  qualifiers={"source": src, "target": tgt})
    out = canonical_serialize(rel)
    assert b"transitions_to" in out
    assert b"SETUP" in out and b"PLAY" in out


def test_condition_predicate_value_changes_id():
    c1 = ConditionPredicate(subject=None, aspect="a", op="eq",
                           value=Value(type="scalar", data=1))
    c2 = ConditionPredicate(subject=None, aspect="a", op="eq",
                           value=Value(type="scalar", data=2))
    assert canonical_serialize(c1) != canonical_serialize(c2)


def test_empty_fields_omitted():
    a = Subject(type="method", name="SETUP")
    b = Subject(type="method", name="SETUP", qualifiers={}, path=[])
    assert canonical_serialize(a) == canonical_serialize(b)


def test_fact_id_format():
    fk = FactKey(protocol="rtsp", version="1.0",
                 subject=Subject(type="method", name="SETUP"),
                 aspect="existence", condition=ConditionAlways())
    fid = compute_fact_id(fk)
    assert fid.startswith("f2_")    # Step A3 2026-10-08: v2 fact_id 前缀 f2_
    assert len(fid) == 3 + 16    # "f2_" + 16 hex


def test_fact_id_deterministic():
    fk = FactKey(protocol="rtsp", version="1.0",
                 subject=Subject(type="method", name="SETUP"),
                 aspect="existence", condition=ConditionAlways())
    assert compute_fact_id(fk) == compute_fact_id(fk)


def test_claim_id_format():
    c = Claim(claim_id="placeholder", fact_id="placeholder",
              value=Value(type="scalar", data=1),
              epistemic_type="normative",
              authority="rfc", scope=None, evidence=())
    cid = compute_claim_id(c)
    assert cid.startswith("c2_") and len(cid) == 3 + 16    # Step A3 2026-10-08: v2 claim_id 前缀 c2_


def test_evidence_id_format():
    loc = LocatorField(file="rfc.txt", path=("10",))
    e = Evidence(evidence_id="x", claim_id="y",
                 source_type="rfc", source_id="rfc.txt",
                 document="rfc.txt", locator=loc)
    eid = compute_evidence_id(e)
    assert eid.startswith("e2_") and len(eid) == 3 + 16    # Step A3 2026-10-08: v2 evidence_id 前缀 e2_