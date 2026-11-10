# -*- coding: utf-8 -*-
"""core/fused/downstream/resolver.py —— 统一消解引擎（P2a）。

五源对同一 fact（相同 subject×aspect×condition → 相同 fact_id）可能给出不同 claim。
本模块把「方法白名单」（P1 已做）泛化为对所有 aspect 的统一消解：

  - precedence：取最高认识论优先级来源的值（existence/state_changing/target_state
    等「单值判定」aspect；observed 实测 > normative 规范 > descriptive 推断）。
  - union     ：合并所有来源的取值（value_enum 等「取值池」aspect，
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
    # ★ 阶段 E4：value_enum 拆成「规范值」与「实测样本」⇒ 两者都是**取值池**（union）
    #   · value_enum_spec      —— 来自 RFC 规范文本（落 D_construction）
    #   · value_enum_observed  —— 来自抓包观测（落 E_observation）
    "value_enum": "union",
    "value_enum_spec": "union",
    "value_enum_observed": "union",
    "case_sensitivity": "precedence",
    "value_type": "precedence",
}


def _priority(epistemic: str) -> int:
    return SOURCE_PRIORITY.get(epistemic, 0)


def _claim_key(claim: dict) -> str:
    """claim 的唯一键（claim_id 优先，退化为 authority）。"""
    return claim.get("claim_id") or claim.get("authority", "")


#: ★ 阶段 N-1：struct 内**明确无序**的字段（比较时按内容排序 ⇒ 顺序无关）
#:
#: ★ 为什么只列这几个（而不对 struct 一刀切）：
#:   struct 的 `data` 形态有 4 种（实测中枢 278 条 struct claim）：
#:     ① ``{"fields": [...]}``            —— 消息实例的字段集合 ⇒ **无序**
#:     ② ``{"headers": [...]}``           —— 必填头清单 ⇒ **无序**
#:     ③ ``{"action":…, "trigger_sequence": [...]}`` —— 触发序列 ⇒ **有序**（序列语义！）
#:     ④ ``{"target_field":…, "operator":…, "operand": [...]}`` —— 语义算子 ⇒ 逐字段定
#:   ⇒ 对 ③④ 无序化会**破坏语义**（序列被当成集合）⇒ 只对 ①② 无序化。
#:
#: ★ 规范见 ``docs/设计/顶层设计/值形态与比较语义.md``
UNORDERED_STRUCT_FIELDS = ("fields", "headers")


def _normalize_value(value: dict | None) -> object:
    """把 claim 的 ``value`` 归一到**可比较**的规范形态（阶段 N-1）。

    ★ 归一目标形态（按 ``value.type`` 分派）：
      · ``set`` / 裸 list ⇒ **无序**（排序后的字符串列表）
      · ``struct`` ⇒ 逐字段：``UNORDERED_STRUCT_FIELDS`` 内的**无序化**，
        其余**保持原样**（顺序敏感 ⇒ 序列语义不被破坏）
      · ``text`` / ``pattern`` / ``scalar`` ⇒ 原样
    """
    if not isinstance(value, dict):
        return value
    data = value.get("data")
    if isinstance(data, (list, set, tuple)):
        return sorted(map(str, data))
    if isinstance(data, dict) and value.get("type") == "struct":
        out = {}
        for k, v in data.items():
            if k in UNORDERED_STRUCT_FIELDS and isinstance(v, (list, set, tuple)):
                out[k] = sorted(map(str, v))
            else:
                out[k] = v
        return out
    return data


def _value_eq(a, b) -> bool:
    """两个 claim 的 value 是否**语义等价**（阶段 N-1：先归一再比较）。

    ★ 归一后：
      · ``set`` / list ⇒ 无序比较（顺序无关）
      · ``struct`` ⇒ ``fields`` / ``headers`` 无序，其余有序
      · 其余 ⇒ 原样相等
    """
    va, vb = a.get("value"), b.get("value")
    if va is None or vb is None:
        return va == vb
    return _normalize_value(va) == _normalize_value(vb)


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
