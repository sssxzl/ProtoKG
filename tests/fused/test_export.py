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
from core.fused import export
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

# ===========================================================================
# ★ evidence_summary 带文件锚点（2026-11-07，多 RFC 协议可溯源）
# ===========================================================================

def test_evidence_summary_includes_document_anchor():
    """★ 多 RFC 协议时，中枢里要能分清某条知识来自**哪份 RFC**。

    ★ 旧形态只有 ``{source_type}:{source_id}``，而 source_id 是**协议级**的
      （norm_id = ``{protocol}.{kind}.{name}``）⇒ 一个协议有多份 RFC 时全混在一起。
    """
    ev = Evidence(evidence_id="e1_y", claim_id="c1_y",
                  source_type="rfc", source_id="smtp.method.starttls",
                  document="file:rfc3207.txt#@99",
                  locator=LocatorLine(file="rfc3207.txt", line=99, col=0),
                  quote=None, content_fingerprint="", extraction_fingerprint="")
    c = Claim(claim_id="c1_y", fact_id="f1_y",
              value=Value(type="text", data="STARTTLS"),
              epistemic_type="normative", authority="rfc", scope=Scope(),
              evidence=(ev,), confidence=None)
    item = export._evidence_summary_item(ev)
    assert item.startswith("rfc:smtp.method.starttls"), item
    assert "rfc3207.txt" in item, item
    assert "99" in item, item


def test_evidence_summary_prefix_unchanged():
    """★ **前缀不变** ⇒ 现有按 split(":")[1] / startswith 解析的代码不受影响。"""
    ev = Evidence(evidence_id="e1_z", claim_id="c1_z",
                  source_type="rfc", source_id="smtp.field.date",
                  document="file:rfc5322.txt#@abnf-field",
                  locator=None, quote=None,
                  content_fingerprint="", extraction_fingerprint="")
    item = export._evidence_summary_item(ev)
    assert item.split("@")[0] == "rfc:smtp.field.date", item


def test_evidence_summary_without_document_is_unchanged():
    """★ document 为空 ⇒ 输出与旧形态**完全一致**（不引入 @）。"""
    ev = Evidence(evidence_id="e1_w", claim_id="c1_w",
                  source_type="rfc", source_id="smtp.x",
                  document="", locator=None, quote=None,
                  content_fingerprint="", extraction_fingerprint="")
    assert export._evidence_summary_item(ev) == "rfc:smtp.x"


def test_evidence_summary_no_redundant_suffix():
    """★ document 与 source_id 重复 ⇒ 不重复附加（避免 rfc:X@X）。"""
    ev = Evidence(evidence_id="e1_v", claim_id="c1_v",
                  source_type="rfc", source_id="rfc2326.txt",
                  document="rfc2326.txt", locator=None, quote=None,
                  content_fingerprint="", extraction_fingerprint="")
    assert export._evidence_summary_item(ev) == "rfc:rfc2326.txt"


def test_real_multi_rfc_hub_has_file_anchors():
    """★ 端到端：smtp 有 4 份 RFC ⇒ 中枢里的 RFC 事实要能分出来源文件。"""
    import glob
    import json as _json
    from core import paths as _paths
    root = _paths.model_root() / "per_source" / "smtp" / "facts"
    if not root.is_dir():
        pytest.skip("无 smtp 中枢产物")
    files = set()
    for p in sorted(root.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = _json.loads(line)
            for cl in (d.get("all_claims") or []):
                for es in (cl.get("evidence_summary") or []):
                    if es.startswith("rfc:") and "@file:" in es:
                        files.add(es.split("@file:", 1)[1].split("#")[0])
    assert len(files) >= 2, f"多 RFC 协议应能分出来源文件，实得 {files}"
