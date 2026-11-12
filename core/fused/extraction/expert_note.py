"""core/fused/expert_note.py —— expert_note 维度 JSON → Fact 的原生映射（v3 专家判断）。

从 kb/<protocol>/expert_note/*.json（schema v3, 4 维度）直接映射到 Fact。
v3 定位（对齐 docs/设计/各源设计/专家注记源/专家注记重新设计.md v3）：expert_note 是「专家的判断和引导」，
回答「哪里危险、怎么进入深层、该往哪使劲」，不重复客观源（rfc/source/traffic/vuln）
能给的客观事实。

4 维度 → security_property（统一挂 security_property aspect，value 带类型前缀区分）：
  hotspots            → 风险预判（subject 按 target_type：field→header / method→method）
  depth_keys          → 进入深层状态的钥匙（subject=入口 method）
  design_weaknesses   → 协议设计级弱点（subject=protocol）
  implicit_constraints→ 隐含约束/变异建议（subject=header）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from core import paths
from core.fused.hub.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.hub.canonical import (
    compute_fact_id, compute_claim_id, compute_evidence_id,
)

EXPERT_NOTE_DIR = paths.kb_root() / "expert_note"  # 旧单协议路径（向后兼容）


def _make_evidence(doc: str, source_id: str, quote: str, claim_id: str) -> Evidence:
    ev = Evidence(
        evidence_id="placeholder", claim_id=claim_id,
        source_type="expert_note", source_id=source_id,
        document=doc, locator=None, quote=quote,
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


def _make_fact(subject: Subject, value: str, doc: str,
               source_id: str, quote: str, protocol: str) -> Fact:
    """构造一条 security_property fact（epistemic=descriptive / authority=expert_note）。"""
    fact_key = FactKey(protocol=protocol, version="1.0",
                       subject=subject, aspect="security_property",
                       condition=ConditionAlways())
    fact_id = compute_fact_id(fact_key)
    tmp = Claim(claim_id="placeholder", fact_id=fact_id,
                value=Value(type="text", data=value),
                epistemic_type="descriptive", authority="expert_note",
                scope=Scope(), evidence=())
    cid = compute_claim_id(tmp)
    ev = _make_evidence(doc, source_id, quote, cid)
    claim = Claim(claim_id=cid, fact_id=fact_id,
                  value=Value(type="text", data=value),
                  epistemic_type="descriptive", authority="expert_note",
                  scope=Scope(), evidence=(ev,), confidence=None)
    return Fact(fact_id=fact_id, fact_key=fact_key, claims=(claim,),
                resolution=None, alignments=(),
                metadata=FactMetadata(created_at="2026-10-20",
                                      profile_version=f"{protocol}-v1"))


def _clean_method(s: str) -> str:
    """把 path 元素里的括号注释去掉（如 'QUERY(触发转发)' → 'QUERY'）。"""
    return re.sub(r"[\(（].*?[\)）]", "", s or "").strip()


# ===========================================================================
# v3 四维映射
# ===========================================================================

def _map_hotspots(d: dict, protocol: str) -> list[Fact]:
    """hotspots → security_property。target_type=field→header，否则→method。"""
    out = []
    for h in d.get("hotspots", []):
        stype = "header" if h.get("target_type") == "field" else "method"
        name = (h.get("subject") or "").strip()
        if not name:
            continue
        value = f"[风险热点] {h.get('why', '')}"
        mh = (h.get("mutation_hint") or "").strip()
        if mh:
            value += f"（变异：{mh}）"
        out.append(_make_fact(
            Subject(type=stype, name=name), value,
            "expert_note/hotspots.json", h.get("id", name), value, protocol))
    return out


def _map_depth_keys(d: dict, protocol: str) -> list[Fact]:
    """depth_keys → security_property（subject=入口 method）。"""
    out = []
    for k in d.get("depth_keys", []):
        path = k.get("path") or []
        entry = _clean_method(path[0]) if path else (k.get("method") or "")
        if not entry:
            continue
        value = f"[深度钥匙] 进入 {k.get('target_state', '')}：{' → '.join(path)}"
        out.append(_make_fact(
            Subject(type="method", name=entry), value,
            "expert_note/depth_keys.json", k.get("id", entry), value, protocol))
    return out


def _map_design_weaknesses(d: dict, protocol: str) -> list[Fact]:
    """design_weaknesses → security_property（subject=protocol）。"""
    out = []
    for w in d.get("design_weaknesses", []):
        name = (w.get("name") or "").strip()
        if not name:
            continue
        value = f"[设计弱点] {w.get('root_cause', '')}"
        eh = (w.get("exploit_hint") or "").strip()
        if eh:
            value += f"（利用：{eh}）"
        out.append(_make_fact(
            Subject(type="protocol", name=name), value,
            "expert_note/design_weaknesses.json", w.get("id", name), value, protocol))
    return out


def _map_implicit_constraints(d: dict, protocol: str) -> list[Fact]:
    """implicit_constraints → security_property（subject=header）。"""
    out = []
    for c in d.get("implicit_constraints", []):
        field = (c.get("field") or "").strip()
        if not field:
            continue
        value = f"[隐含约束] {c.get('constraint', '')}"
        vm = (c.get("violation_mutation") or "").strip()
        if vm:
            value += f"（违规变异：{vm}）"
        out.append(_make_fact(
            Subject(type="header", name=field), value,
            "expert_note/implicit_constraints.json", c.get("id", field), value, protocol))
    return out


#: 维度文件 → 映射函数（v3 四维）
_DIMENSION_MAPPERS = [
    ("hotspots.json", _map_hotspots),
    ("depth_keys.json", _map_depth_keys),
    ("design_weaknesses.json", _map_design_weaknesses),
    ("implicit_constraints.json", _map_implicit_constraints),
]


def expert_note_to_facts(expert_note_dir: Path = EXPERT_NOTE_DIR,
                         protocol: Optional[str] = None) -> list[Fact]:
    """读 expert_note 的维度 JSON，映射到 Fact 列表。

    protocol 给定且 expert_note_dir 未显式指定时，用 kb/<protocol>/expert_note/
    （协议×源二维解耦）；否则用传入目录（向后兼容）。
    """
    if protocol and expert_note_dir == EXPERT_NOTE_DIR:
        expert_note_dir = paths.kb_source_dir(protocol, "expert_note")
    facts: list[Fact] = []
    for fname, mapper in _DIMENSION_MAPPERS:
        fp = Path(expert_note_dir) / fname
        if not fp.is_file():
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        facts.extend(mapper(d, protocol or "rtsp"))
    return facts
