# -*- coding: utf-8 -*-
"""★ N2.4：★ 可靠确认防护的**设计与影子验证**（★ 不修改正式发布策略）。

★ 职责划分（★ 用户指定）：
  · ★ **确定性校验**负责：原文证据、主体归属、强度与极性
  · ★ **L2** 作为：语义支持判断 + 风险筛查（★ 不作为唯一放行依据）
  · ★ 有 confirmed 分歧的候选 ⇒ **保持待审**
  · ★ 独立人工标签用于**校准**
  · ★ 缺少必要字段证据的候选 ⇒ **不得正式确认**

★ 本模块**只做影子运行**：★ 计算「若启用防护会怎样」，★ **不改变任何 final_state**。
★ 启用方式：``PROSE_CONFIRM_GUARD=1``（★ 默认关闭 ⇒ 行为不变）
"""
from __future__ import annotations

import collections
import json
import re
from typing import Optional

# ★ 必要字段证据（★ 缺少任一 ⇒ 不得正式确认）
REQUIRED_FIELD_EVIDENCE = ("subject", "action", "object", "strength")

_STRENGTHS = ("MUST NOT", "MUST", "SHALL NOT", "SHALL", "SHOULD NOT", "SHOULD",
              "REQUIRED", "RECOMMENDED", "MAY NOT", "MAY", "OPTIONAL")
_NEG = ("MUST NOT", "SHALL NOT", "SHOULD NOT", "MAY NOT", "NOT RECOMMENDED")


def deterministic_field_evidence(payload: dict, quote: str) -> dict:
    """★ 确定性字段证据检查（★ 不调 LLM）。

    Returns:
        ``{"ok": bool, "missing": [...], "strength_in_quote": bool,
        "polarity_consistent": bool, "notes": [...]}``
    """
    _notes = []
    _q = str(quote or "")
    _qu = _q.upper()
    _missing = []
    for f in REQUIRED_FIELD_EVIDENCE:
        _v = str(payload.get(f) or "").strip()
        if not _v:
            _missing.append(f)
    _str = str(payload.get("strength") or "").strip().upper()
    _str_in = bool(_str) and _str in _qu
    if _str and not _str_in:
        _notes.append(f"强度「{_str}」未在证据中出现")
    # ★ 否定极性：★ SHOULD NOT ⇒ 证据须含对应否定形式
    _pol = str(payload.get("polarity") or "").strip().lower()
    _neg_in_quote = any(k in _qu for k in _NEG)
    _pol_ok = True
    if _pol in ("negative", "neg"):
        _pol_ok = _neg_in_quote
        if not _pol_ok:
            _notes.append("候选为否定极性，但证据中未见对应否定形式")
    if _str in ("SHOULD", "MAY", "MUST", "SHALL") and _neg_in_quote:
        _pol_ok = _pol_ok and False
        _notes.append(f"★ 证据含否定形式，但候选强度为「{_str}」（★ 极性可能丢失）")
    return {"ok": (not _missing and _str_in and _pol_ok),
            "missing": _missing, "strength_in_quote": _str_in,
            "polarity_consistent": _pol_ok, "notes": _notes}


def confirm_guard(payload: dict, quote: str, l2_verdict: Optional[str],
                  *, attribution_status: str = "explicit_subject",
                  instability_candidates: Optional[set] = None,
                  human_labeled: Optional[bool] = None) -> dict:
    """★ 确认防护判定（★ 影子模式：★ 只返回建议，★ 不改 final_state）。

    Returns:
        ``{"allow_confirm": bool, "reason": str, "evidence": dict}``
    """
    _ev = deterministic_field_evidence(payload, quote)
    _reasons = list(_ev["notes"])
    if not _ev["ok"]:
        return {"allow_confirm": False,
                "reason": "★ 缺少必要字段证据或极性不一致 ⇒ 不得正式确认"
                          + ("（" + "；".join(_reasons) + "）" if _reasons else ""),
                "evidence": _ev}
    if attribution_status in ("coreference_ambiguous", "coreference_unresolved"):
        return {"allow_confirm": False,
                "reason": f"★ 主体归属未确定（{attribution_status}）⇒ 保持待审",
                "evidence": _ev}
    if instability_candidates is not None and l2_verdict == "confirmed" \
            and instability_candidates:
        return {"allow_confirm": False,
                "reason": "★ 该候选存在同输入 confirmed 分歧记录 ⇒ 保持待审",
                "evidence": _ev}
    if human_labeled is False:
        return {"allow_confirm": False,
                "reason": "★ 人工标注为非有效确认 ⇒ 不得发布",
                "evidence": _ev}
    if l2_verdict != "confirmed":
        return {"allow_confirm": False, "reason": "★ L2 未支持", "evidence": _ev}
    if human_labeled is None:
        return {"allow_confirm": False,
                "reason": "★ 尚无独立人工标签 ⇒ ★ 保持待审（★ 校准前不放行）",
                "evidence": _ev}
    return {"allow_confirm": True,
            "reason": "★ 确定性证据齐全 + 归属确定 + 无分歧记录 + 人工标签有效",
            "evidence": _ev}


__all__ = ["deterministic_field_evidence", "confirm_guard",
           "REQUIRED_FIELD_EVIDENCE"]
