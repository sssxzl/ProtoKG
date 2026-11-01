# -*- coding: utf-8 -*-
"""core/fused/downstream/resolver.py —— 统一消解引擎（P2a）。

五源对同一 fact（相同 subject×aspect×condition → 相同 fact_id）可能给出不同 claim。
本模块把「方法白名单」（P1 已做）泛化为对所有 aspect 的统一消解：

  - precedence：取最高认识论优先级来源的值（existence/state_changing/target_state
    等「单值判定」aspect；observed 实测 > normative 规范 > descriptive 推断）。
  - union     ：合并所有来源的取值（value_enum/occurrence 等「取值池」aspect，
    多源互补不冲突，取并集）。
  - consensus ：多源一致取其一；值不同且同优先级 → 标记 conflict 保留（不误判）。

被覆盖的 claim 不丢弃，记入 superseded（供 RQ4 消融 + 可解释性追溯）。

声明式：优先级表、aspect 语义表均可下沉 profile，换协议零代码。
"""
from __future__ import annotations

from typing import Optional

#: 认识论优先级（与 source_availability.SOURCE_PRIORITY 一致，避免循环依赖在此复制）。
#: 值域必须覆盖各抽取器实际产出的 epistemic_type：
#:   - observed                → traffic 源（实测）
#:   - normative / must / normative_unspecified → rfc 源（norm.py：RFC 2119 的
#:     MUST→"must"、optional/should/may→"normative_unspecified"）
#:   - descriptive             → source/expert_note/vuln 源（推断/描述）
#: 统一「规范类」三种写法同为优先级 2，避免 rfc 规范知识被误判为最低优先级。
SOURCE_PRIORITY: dict[str, int] = {
    "observed": 3,
    "normative": 2,
    "must": 2,
    "normative_unspecified": 2,
    "descriptive": 1,
}

#: aspect → 消解语义（默认 consensus）。未列出的 aspect 走 consensus。
#  precedence：单值判定，取最高优先级来源
#  union     ：取值池，多源并集
_ASPECT_SEMANTICS: dict[str, str] = {
    "existence": "precedence",
    "state_changing": "precedence",
    "target_state": "precedence",
    "value_enum": "union",
    "occurrence": "union",
    "case_sensitivity": "precedence",
    "value_type": "precedence",
}


def _priority(epistemic: str) -> int:
    return SOURCE_PRIORITY.get(epistemic, 0)


def _claim_key(claim: dict) -> str:
    """claim 的唯一键（claim_id 优先，退化为 authority）。"""
    return claim.get("claim_id") or claim.get("authority", "")


def _value_eq(a, b) -> bool:
    """两个 claim 的 value 是否一致（对 set/list 做无序遍历比较）。"""
    va, vb = a.get("value"), b.get("value")
    if va is None or vb is None:
        return va == vb
    da, db = va.get("data"), vb.get("data")
    if isinstance(da, (list, set, tuple)) and isinstance(db, (list, set, tuple)):
        return sorted(map(str, da)) == sorted(map(str, db))
    return da == db


def resolve_claims(claims: list[dict], aspect: str,
                   priority: Optional[dict] = None) -> dict:
    """对同一 fact 的多个 claim 消解，返回消解结果 dict。

    Args:
        claims: 每个含 {value, epistemic_type, authority, claim_id(可选)}
        aspect: 消解的 aspect（决定 precedence / union / consensus 语义）
        priority: 优先级表（默认 SOURCE_PRIORITY）

    Returns:
        {
          "method": single|precedence|union|consensus|conflict|insufficient,
          "value": {...} | None,          # 消解后的 value（Value view）
          "epistemic": str,               # 胜出认识论类型（多源合并时取最高）
          "authority": str,               # 主权威（多源合并时取最高优先级的）
          "basis_claim_ids": [str],       # 采纳的 claim id
          "superseded": [str],            # 被覆盖的 claim id（保留，不丢弃）
        }
    """
    prio = priority or SOURCE_PRIORITY
    sem = _ASPECT_SEMANTICS.get(aspect, "consensus")

    if not claims:
        return {"method": "insufficient", "value": None, "epistemic": "",
                "authority": "", "basis_claim_ids": [], "superseded": []}
    if len(claims) == 1:
        c = claims[0]
        return {"method": "single", "value": c.get("value"),
                "epistemic": c.get("epistemic_type", ""),
                "authority": c.get("authority", ""),
                "basis_claim_ids": [_claim_key(c)], "superseded": []}

    ranked = sorted(claims, key=lambda c: prio.get(c.get("epistemic_type", ""), 0),
                    reverse=True)
    top_prio = prio.get(ranked[0].get("epistemic_type", ""), 0)

    if sem == "union":
        # 取值池：合并所有来源的取值（set 并集），保留全部 claim 为 basis
        merged: set = set()
        for c in ranked:
            v = (c.get("value") or {}).get("data")
            if isinstance(v, (list, set, tuple)):
                merged.update(map(str, v))
            elif v is not None:
                merged.add(str(v))
        val_type = (claims[0].get("value") or {}).get("type", "set")
        return {
            "method": "union",
            "value": {"type": val_type, "data": sorted(merged)},
            "epistemic": ranked[0].get("epistemic_type", ""),
            "authority": ranked[0].get("authority", ""),
            "basis_claim_ids": [_claim_key(c) for c in claims],
            "superseded": [],
        }

    # precedence / consensus：看最高优先级组
    top_claims = [c for c in ranked
                  if prio.get(c.get("epistemic_type", ""), 0) == top_prio]
    if sem == "precedence":
        winner = top_claims[0]
        superseded = [_claim_key(c) for c in ranked if c is not winner]
        return {
            "method": "precedence" if superseded else "consensus",
            "value": winner.get("value"),
            "epistemic": winner.get("epistemic_type", ""),
            "authority": winner.get("authority", ""),
            "basis_claim_ids": [_claim_key(winner)],
            "superseded": superseded,
        }

    # consensus：多源一致取一；值不同 → conflict（保留全部，不选边）
    if all(_value_eq(top_claims[0], c) for c in top_claims[1:]):
        winner = top_claims[0]
        superseded = [_claim_key(c) for c in ranked if c is not winner]
        return {
            "method": "consensus",
            "value": winner.get("value"),
            "epistemic": winner.get("epistemic_type", ""),
            "authority": winner.get("authority", ""),
            "basis_claim_ids": [_claim_key(winner)],
            "superseded": superseded,
        }
    # 同优先级但值冲突：保留冲突（不误选），下游按 priority 排序取首个兜底
    return {
        "method": "conflict",
        "value": top_claims[0].get("value"),
        "epistemic": top_claims[0].get("epistemic_type", ""),
        "authority": top_claims[0].get("authority", ""),
        "basis_claim_ids": [_claim_key(c) for c in top_claims],
        "superseded": [_claim_key(c) for c in ranked if c not in top_claims],
    }


def evidence_strength(claims: list[dict]) -> str:
    """证据强度（observed 采信门槛）。

    - 多个独立 observed claim（不同 authority/source）→ high
    - 单个 observed claim → medium
    - 无 observed（仅 descriptive/normative）→ low
    """
    observed = [c for c in claims
                if c.get("epistemic_type") == "observed"]
    if not observed:
        return "low"
    distinct_src = {_claim_key(c) for c in observed}
    return "high" if len(distinct_src) > 1 else "medium"


__all__ = [
    "SOURCE_PRIORITY",
    "resolve_claims",
    "evidence_strength",
]
