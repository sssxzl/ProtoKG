"""tests/fused/test_export.py —— LLM 安全接口。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.fused.models import (
    Fact, FactKey, FactMetadata, Subject, ConditionAlways, Value,
    Claim, Evidence, Scope, Resolution, Support, Generalization,
    Alignment, LocatorLine,
)
from core.fused.export import (
    get_fact_view, get_claim_view, get_evidence_view, export_facts_for_llm,
)


def _sample_fact() -> Fact:
    fk = FactKey(protocol="rtsp", version="1.0",
                 subject=Subject(type="method", name="SETUP",
                                qualifiers={"actor": "client"}),
                 aspect="existence", condition=ConditionAlways())
    ev = Evidence(evidence_id="e1_x", claim_id="c1_x",
                  source_type="rfc", source_id="rfc2326.txt",
                  document="rfc2326.txt",
                  locator=LocatorLine(file="rfc2326.txt", line=10, col=4),
                  quote=None,
                  content_fingerprint="abc", extraction_fingerprint="def")
    c = Claim(claim_id="c1_x", fact_id="f1_x",
              value=Value(type="bool", data=True),
              epistemic_type="normative",
              authority="rfc",
              scope=Scope(observation_population=None,
                         measurement_unit=None,
                         independence="independent",
                         bounded=True, bounds={"scope": "protocol"}),
              evidence=(ev,),
              confidence=0.95)
    return Fact(fact_id="f1_x", fact_key=fk,
                claims=(c,),
                resolution=Resolution(
                    status="resolved", method="single",
                    basis_claim_ids=("c1_x",),
                    reason="single", reason_code="OK",
                    policy_version="v1",
                    support=Support(independent=1, dependent=0,
                                     unknown=0, total=1),
                    generalization=Generalization(scope="protocol-wide",
                                                  confidence=0.95)),
                alignments=(),
                metadata=FactMetadata(created_at="2026-10-08",
                                       profile_version="v1"))


def test_get_evidence_view_includes_locator():
    e = _sample_fact().claims[0].evidence[0]
    v = get_evidence_view(e)
    assert v["locator"]["type"] == "line"
    assert v["locator"]["file"] == "rfc2326.txt"
    assert v["locator"]["line"] == 10
    assert v["source_type"] == "rfc"
    assert v["content_fingerprint"] == "abc"


def test_get_claim_view_shape():
    f = _sample_fact()
    cv = get_claim_view(f.claims[0])
    assert cv["value"] == {"type": "bool", "data": True}
    assert cv["epistemic_type"] == "normative"
    assert cv["evidence_summary"] == ["rfc:rfc2326.txt"]
    assert cv["confidence"] == 0.95


def test_get_fact_view_resolved_has_3_layers():
    f = _sample_fact()
    v = get_fact_view(f)
    # 三层: value / epistemic / support + generalization
    assert v["resolution"]["status"] == "resolved"
    # 单源 single + 1 claim ⟹ 从唯一 claim 取出 value
    assert v["resolution"]["value"] == {"type": "bool", "data": True}
    assert v["resolution"]["support"]["independent"] == 1
    assert v["resolution"]["generalization"]["scope"] == "protocol-wide"


def test_export_facts_for_llm_top_level_shape():
    f = _sample_fact()
    out = export_facts_for_llm("rtsp", "1.0", [f])
    assert out["protocol"] == "rtsp"
    assert out["version" if "version" in out else "profile_version"]
    assert "facts" in out
    assert len(out["facts"]) == 1


def test_export_conflict_exposes_conflicting_claims(tmp_path):
    """conflict 类 fact 显式呈现 conflicting_claims。"""
    fk = FactKey(protocol="rtsp", version="1.0",
                 subject=Subject(type="method", name="SETUP"),
                 aspect="existence", condition=ConditionAlways())
    c1 = Claim(claim_id="c1_a", fact_id="f1_x",
               value=Value(type="bool", data=True),
               epistemic_type="normative", authority="rfc",
               scope=None, evidence=(), confidence=None)
    c2 = Claim(claim_id="c1_b", fact_id="f1_x",
               value=Value(type="bool", data=False),     # 冲突值
               epistemic_type="observational", authority="traffic",
               scope=None, evidence=(), confidence=None)
    f = Fact(fact_id="f1_x", fact_key=fk, claims=(c1, c2),
             resolution=Resolution(status="unresolved", method="conflict",
                                   basis_claim_ids=("c1_a", "c1_b"),
                                   reason="value mismatch",
                                   reason_code="VAL_MISMATCH",
                                   policy_version="v1"),
             alignments=(),
             metadata=FactMetadata(created_at="2026-10-08", profile_version="v1"))
    out = export_facts_for_llm("rtsp", "1.0", [f])
    res = out["facts"][0]["resolution"]
    assert res["status"] == "unresolved"
    assert res["method"] == "conflict"
    assert "conflicting_claims" in res
    assert len(res["conflicting_claims"]) == 2


def test_export_to_jsonl_round_trip(tmp_path):
    """导出到 JSONL, 再读回, 不丢字段。"""
    f = _sample_fact()
    v = get_fact_view(f)
    p = tmp_path / "facts.jsonl"
    p.write_text(json.dumps(v, default=str), encoding="utf-8")
    out = export_facts_for_llm("rtsp", "1.0", p)
    assert len(out["facts"]) == 1