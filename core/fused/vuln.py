"""core/fused/vuln.py —— vuln 源（kb/历史漏洞/*.json）→ v2 Fact 的原生映射。

甲方案：直接读 kb/历史漏洞/*.json（结构化字段），不经过 norms.jsonl（与
expert_note 一致）。scope=seedgen 的漏洞才产 fact；其余 scope 值（历史漏洞数据
里的 not_<协议>_protocol / not_<协议>_client_side / insufficient_source /
not_trigger_vulnerability 等）均不相关 —— 判定只比较 scope == "seedgen"，
不依赖具体协议名。

映射：trigger.method.value（数组）→ method+security_property；
      trigger.field.value（str 或数组）→ header+security_property；
      value = description_raw（漏洞描述），epistemic = descriptive。

设计依据: local/layer2_extraction_methods.md §三 vuln 行
           （rule 抽固定字段，LLM 抽后果语义归入 security_property）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from core import paths
from core.fused.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.canonical import (
    compute_fact_id, compute_claim_id, compute_evidence_id,
)

VULN_DIR = paths.kb_root() / "历史漏洞"  # 旧单协议路径（向后兼容）


def _make_evidence(doc: str, source_id: str, quote: str, claim_id: str) -> Evidence:
    ev = Evidence(
        evidence_id="placeholder", claim_id=claim_id,
        source_type="vuln", source_id=source_id,
        document=doc, locator=source_id, quote=quote,
        content_fingerprint="", extraction_fingerprint="",
    )
    eid = compute_evidence_id(ev)
    return Evidence(
        evidence_id=eid, claim_id=claim_id,
        source_type=ev.source_type, source_id=ev.source_id,
        document=ev.document, locator=ev.locator, quote=ev.quote,
        content_fingerprint=ev.content_fingerprint,
        extraction_fingerprint=ev.extraction_fingerprint,
    )


def _make_fact(subject: Subject, value: Value, doc: str, source_id: str,
               quote: str, aspect: str = "security_property",
               protocol: str = "rtsp") -> Fact:
    fact_key = FactKey(protocol=protocol, version="1.0",
                       subject=subject, aspect=aspect,
                       condition=ConditionAlways())
    fact_id = compute_fact_id(fact_key)
    tmp = Claim(claim_id="placeholder", fact_id=fact_id, value=value,
                epistemic_type="descriptive", authority="vuln",
                scope=Scope(), evidence=())
    cid = compute_claim_id(tmp)
    ev = _make_evidence(doc, source_id, quote, cid)
    claim = Claim(claim_id=cid, fact_id=fact_id, value=value,
                  epistemic_type="descriptive", authority="vuln",
                  scope=Scope(), evidence=(ev,), confidence=None)
    return Fact(fact_id=fact_id, fact_key=fact_key, claims=(claim,),
                resolution=None, alignments=(),
                metadata=FactMetadata(created_at="2026-10-09", profile_version="rtsp-v1"))


def _field_values(field_value: Any) -> list[str]:
    """trigger.field.value 可能是 str / list / None，统一成 list[str]。"""
    if field_value is None:
        return []
    if isinstance(field_value, list):
        return [str(x).strip() for x in field_value if str(x).strip()]
    s = str(field_value).strip()
    return [s] if s else []


def vuln_entry_to_facts(entry: dict[str, Any],
                        protocol: str = "rtsp") -> list[Fact]:
    """单个漏洞 JSON → 0 或多个 security_property Fact。"""
    if entry.get("scope") != "seedgen":
        return []
    desc = (entry.get("description_raw") or "").strip()
    if not desc:
        return []
    case_id = entry.get("case_id", "unknown")
    doc = f"历史漏洞/{case_id}.json"

    # 元数据拼进 quote（保留 cwe/risk_level 溯源，不入 value）
    cwe = entry.get("cwe_avd", "") or ""
    risk = entry.get("risk_level_avd", "") or ""
    quote = desc
    if cwe or risk:
        quote = f"[{cwe}][{risk}] {desc}"

    facts: list[Fact] = []
    trig = entry.get("trigger", {}) or {}
    methods = trig.get("method", {}).get("value") or []
    for m in methods:
        if str(m).strip():
            facts.append(_make_fact(
                Subject(type="method", name=str(m).strip()),
                Value(type="text", data=desc), doc, case_id, quote,
                protocol=protocol))

    for f in _field_values(trig.get("field", {}).get("value")):
        facts.append(_make_fact(
            Subject(type="header", name=f),
            Value(type="text", data=desc), doc, case_id, quote,
            protocol=protocol))
    return facts


def vuln_entry_to_pattern_facts(entry: dict[str, Any], protocol: str = "rtsp",
                                llm=None) -> list[Fact]:
    """单个漏洞 JSON → 0/1 个 vuln_pattern Fact（结构化漏洞模式，借鉴 GLMFuzz）。

    漏洞模式由 core.fused.vuln_pattern.complete_vuln_pattern 抽取（rule 打底，
    llm 传入时补全 trigger_sequence/mutation_hint，否则降级为 rule 锚点）：
    {action, trigger_sequence, trigger_field, boundary, cwe, streams, mutation_hint}。
    subject 取触发主锚点（method 优先，否则 header）；epistemic=descriptive，authority=vuln。
    """
    from core.fused.vuln_pattern import complete_vuln_pattern
    pat = complete_vuln_pattern(entry, protocol=protocol, llm=llm)
    if pat is None:
        return []
    case_id = entry.get("case_id", "unknown")
    doc = f"历史漏洞/{case_id}.json"
    quote = entry.get("description_raw", "") or ""
    if pat["trigger_sequence"]:
        subject = Subject(type="method", name=pat["trigger_sequence"][0])
    else:
        subject = Subject(type="header", name=pat["trigger_field"])
    return [_make_fact(subject, Value(type="struct", data=pat), doc, case_id,
                       quote, aspect="vuln_pattern", protocol=protocol)]


def vuln_to_facts(vuln_dir: Path = VULN_DIR,
                  protocol: Optional[str] = None, llm=None) -> list[Fact]:
    """读 kb/历史漏洞/*.json，映射到 v2 Fact 列表。

    protocol 给定且 vuln_dir 未显式指定时，用 kb/<protocol>/历史漏洞/
    （协议×源二维解耦）；否则用传入目录（向后兼容）。
    llm 传入时，vuln_pattern 抽取做 LLM 补全（Phase 2），否则 rule 锚点。
    """
    if protocol and vuln_dir == VULN_DIR:
        vuln_dir = paths.kb_source_dir(protocol, "vuln")
    facts: list[Fact] = []
    vdir = Path(vuln_dir)
    if not vdir.is_dir():
        return facts
    for fp in sorted(vdir.glob("*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        facts.extend(vuln_entry_to_facts(d, protocol=protocol or "rtsp"))
        facts.extend(vuln_entry_to_pattern_facts(d, protocol=protocol or "rtsp",
                                                 llm=llm))
    return facts
