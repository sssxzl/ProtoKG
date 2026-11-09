# -*- coding: utf-8 -*-
"""core/fused/semantic_lift.py —— **语义四库 → 中枢**（阶段 C4，2026-11-09 新增）。

★ 阶段 C4 的目标：**消解「两套体系」**。
  改造前：语义知识住在**自己的**四库里（``per_source/<协议>/rfc/semantic/``），
          且**故意**放在 ``*/facts/`` 之外 ⇒ 中枢读不到 ⇒ **两套体系**。
  改造后：语义知识**提升**进中枢的 ``C_constraints/``（约束类）⇒
          中枢成为**唯一真源**，旧路径只作**降级保险**。

★ 映射（authoritative 规则 ⇒ 中枢 fact）：

    rule_id            → claims[0].claim_id
    constraint         → claims[0].value.data（struct）
    subject_type/name  → fact_key.subject
    evidence           → claims[0].evidence_summary（source_anchor）
    （无）             → fact_key.aspect = legal_boundary（C_constraints 槽位）

★ **只提升 authoritative 库**（candidate / revoked / feedback 三库**不投影**）
  ⇒ 与 ``load_semantic_rules`` 的口径**完全一致**（规则状态过滤同源）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

#: 提升后的 aspect（⇒ 落位到 C_constraints/value_constraints）
LIFT_ASPECT = "legal_boundary"

#: 提升后的落盘文件（相对中枢根）
LIFT_FILE = "C_constraints/semantic_rules.jsonl"


def _norm_type(t: str) -> str:
    """实体类型归一（``field`` ⇒ ``header``；其余原样）。"""
    s = str(t or "").strip().lower()
    if s in ("field", "header_field"):
        return "header"
    return s


def rule_to_fact(rule: dict[str, Any], protocol: str) -> Optional[dict[str, Any]]:
    """一条 SemanticRule ⇒ 中枢 fact（``None`` = 结构不可用，跳过）。"""
    if not isinstance(rule, dict):
        return None
    rid = str(rule.get("rule_id") or "").strip()
    if not rid:
        return None
    stype = _norm_type(rule.get("subject_type"))
    sname = str(rule.get("subject_name") or "").strip()
    if not stype or not sname:
        return None
    constraint = rule.get("constraint")
    if not isinstance(constraint, dict):
        constraint = {"raw": constraint}
    ev = rule.get("evidence") or {}
    anchor = ""
    if isinstance(ev, dict):
        anchor = str(ev.get("source_anchor") or ev.get("evidence_id") or "")
    from core.fused.hub_entities import fact_entity_id
    fact = {
        "fact_key": {
            "protocol": str(protocol or ""),
            "version": "2.0",
            "subject": {"type": stype, "name": sname,
                        "qualifiers": {}, "path": []},
            "aspect": LIFT_ASPECT,
            "condition": {"type": "always"},
        },
        "resolution": {
            "strategy": "single_source",
            "decided": None,
            "winners": {"value": rid},
            "reason": "语义规则（authoritative 库）提升进中枢",
        },
        "all_claims": [{
            "claim_id": rid,
            "fact_id": rid,
            "value": {"type": "struct", "data": constraint},
            "epistemic_type": "normative",
            "authority": "rfc",
            "scope": None,
            "evidence_summary": [anchor] if anchor else [],
            "confidence": str(rule.get("model_confidence") or "medium"),
        }],
    }
    # ★ **保留完整规则**（C4 的关键）⇒ 读回时能用 ``_rule_to_plain``
    #   **原样还原** ⇒ 与旧四库路径**逐字段同构** ⇒ 消费端零改动。
    fact["semantic_rule"] = rule
    fact["entity_id"] = fact_entity_id(fact)
    return fact


def lift_library(protocol: str, rules_path: Optional[Path] = None) -> list[dict]:
    """把某协议的 **authoritative 规则库**提升成中枢 fact 列表。"""
    from core.fused.downstream.rule_store import library_path
    p = Path(rules_path) if rules_path else library_path(protocol, "authoritative")
    if not p.is_file():
        return []
    out: list[dict] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        # 行格式：{"kind": "semantic_rule", "rule": {...}}
        rule = row.get("rule") if isinstance(row, dict) and "rule" in row else row
        if not isinstance(rule, dict):
            continue
        # ★ 只投影 authoritative（行里带 kind 时按 kind 过滤）
        kind = str((row or {}).get("kind") or "").strip().lower()
        if kind and kind not in ("semantic_rule", "rule"):
            continue
        state = str(rule.get("rule_state") or "active").strip().lower()
        if state not in ("active", "", "authoritative"):
            continue
        f = rule_to_fact(rule, protocol)
        if f:
            out.append(f)
    return out


def write_lifted(hub_root: Path, protocol: str,
                 facts: list[dict[str, Any]]) -> int:
    """把提升出的 fact 写进中枢 ``C_constraints/semantic_rules.jsonl``。

    ★ **按协议替换**（中枢共用一套 ⇒ 其它协议的保留）。
    """
    hub_root = Path(hub_root)
    pk = str(protocol or "").strip().lower()
    dest = hub_root / LIFT_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    if dest.is_file():
        for ln in dest.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                v = json.loads(ln)
            except json.JSONDecodeError:
                continue
            _kp = str((((v.get("fact_key") or {}).get("protocol"))
                       or "")).strip().lower()
            if _kp and _kp != pk:
                kept.append(ln)          # ★ 别的协议 ⇒ 保留
    lines = kept + [json.dumps(f, ensure_ascii=False) for f in facts]
    dest.write_text(("\n".join(lines) + "\n") if lines else "",
                    encoding="utf-8")
    return len(facts)


def read_lifted(hub_root: Path, protocol: str) -> list[dict]:
    """读中枢里提升出的语义 fact（按协议过滤）。"""
    p = Path(hub_root) / LIFT_FILE
    if not p.is_file():
        return []
    pk = str(protocol or "").strip().lower()
    out: list[dict] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            v = json.loads(ln)
        except json.JSONDecodeError:
            continue
        _kp = str((((v.get("fact_key") or {}).get("protocol"))
                   or "")).strip().lower()
        if pk and _kp and _kp != pk:
            continue
        out.append(v)
    return out


__all__ = ["LIFT_ASPECT", "LIFT_FILE", "rule_to_fact", "lift_library",
           "write_lifted", "read_lifted"]
