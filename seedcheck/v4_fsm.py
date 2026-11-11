# -*- coding: utf-8 -*-
"""seedcheck/v4_fsm.py —— **V4 状态机边合法性**（相邻消息是否是状态机里的边）。

★ 处置：**只打标，不阻断**
  「按了一个不该按的键」⇒ 可能触发状态机缺陷 ⇒ 有价值 ⇒ 只标注。

★ 判据来源：中枢 ``target_state``（协议的状态机边集合）
  ⇒ 形态 = ``(from_state, method, to_state)``。
  ★ 局限：中枢的边**不带「当前状态」**⇒ 只能做**弱校验**：
    ① 该方法**是否出现在任何状态机边里**（⇒ 完全没被状态机提到 ⇒ 可疑）
    ② 该方法是否会**改变状态**（有出边 ⇒ 改状态；无出边 ⇒ 不改）
  ⇒ 严格的「从哪个状态到哪个状态」需要**状态上下文**，当前中枢没有 ⇒ 标注「弱校验」。

★ 另有一个**强校验**可用：``state_changing``（方法是否改变状态）—— 若中枢无此知识则跳过。
"""
from __future__ import annotations

from .knowledge import Knowledge
from .model import SeedRecord, Violation


def check(seed: SeedRecord, k: Knowledge, _stats: dict | None = None) -> list[Violation]:
    """V4 检查 ⇒ 违规列表（打标，弱校验）。"""
    _stats = _stats if _stats is not None else _STATS
    if not k.fsm_edges:
        return []
    methods_in_fsm = {m for (_f, m, _t) in k.fsm_edges}

    # ★ 2026-11-11 修正：「方法不在状态机边里」**不是违规**
    #   （RTSP 的 DESCRIBE/OPTIONS 等合法方法本就不出现在 A.1/A.2 表里
    #     ⇒ 用它们并不违反协议 ⇒ 报成违规会产生大量误报）
    # ⇒ 改为**只统计**：哪些方法没被状态机覆盖 ⇒ 这是**知识完备度**信号（不是种子缺陷）
    uncovered = sorted({m.get("method", "") for m in seed.messages
                        if m.get("method") and m.get("method") not in methods_in_fsm})
    if uncovered:
        _stats.setdefault("fsm_uncovered_methods", [])
        for meth in uncovered:
            if meth not in _stats["fsm_uncovered_methods"]:
                _stats["fsm_uncovered_methods"].append(meth)
    return []


#: 统计累加器（由 run.py 取走 ⇒ 写进 metrics）
_STATS: dict = {}
