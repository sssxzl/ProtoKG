# -*- coding: utf-8 -*-
"""M1-Q3：块预算机制（★ 受预算控制的覆盖扩展）。

★ 目标：把「每文档只抽 1 块」改成**可配置的文档级块预算**，
  同时提供**协议级调用上限**与**成本闸**，避免无上限地调用 LLM。

★ 硬约束：
  ① 按文档设置最大处理块数
  ② 按协议设置最大调用次数
  ③ 记录 token 消耗与（可配置的）费用估算 ⇒ **无单价配置时记 null，不臆造价格**
  ④ 预算耗尽后**明确记录未处理块与原因**
  ⑤ 执行顺序**确定性**（★ 文档名排序 + 行号升序）
  ⑥ ★ **单个 RFC 不得无意耗尽整个协议的预算**
     ⇒ ⇒ 每文档配额 = min(per_doc_blocks, 剩余调用额度 // 剩余文档数)
  ⑦ ★ **默认配置不启用扩量**（★ 不触发历史重抽）
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BlockBudget:
    """★ 一次运行的块/调用预算（★ 确定性、可审计）。"""

    protocol: str = ""
    #: 每文档最多处理的块数（★ 默认 1 ⇒ 与改前一致）
    per_doc_blocks: int = 1
    #: 本协议最多 LLM 调用次数（★ None ⇒ 不限）
    max_calls: Optional[int] = None
    #: token 预算（★ None ⇒ 不限）
    max_tokens: Optional[int] = None
    #: 费用单价（★ 每千 token；★ None ⇒ 不估算 ⇒ 记 null）
    cost_per_1k: Optional[float] = None

    # ---- 运行态 ----
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    blocks_allowed: int = 0
    blocks_skipped: int = 0
    skipped: list = field(default_factory=list)
    _docs_seen: int = 0
    _docs_total: int = 0
    _quota_used: dict = field(default_factory=dict)

    # ---- 配额 ----
    def set_doc_total(self, n: int) -> None:
        """★ 设定本协议共有多少文档（★ 供「不得无意耗尽协议预算」的**确定性预分配**）。

        ★ 预分配：``max_calls`` 按文档数均分，余数依次分给前面的文档
          ⇒ ⇒ **确定性**（同一输入必得同一配额）⇒ ⇒ **单个 RFC 不会吃光整协议预算**
        """
        self._docs_total = max(1, int(n))
        self._docs_seen = 0
        if self.max_calls is None:
            self._quotas = None
        else:
            _base = self.max_calls // self._docs_total
            _rem = self.max_calls % self._docs_total
            self._quotas = [min(self.per_doc_blocks, _base + (1 if i < _rem else 0))
                            for i in range(self._docs_total)]

    def doc_quota(self) -> int:
        """★ 本文档可用的块配额（★ 确定性预分配 ⇒ 越靠后的文档配额不增加）。"""
        if self._quotas is not None:
            _i = min(self._docs_seen, len(self._quotas) - 1)
            return max(0, int(self._quotas[_i]))
        return max(0, self.per_doc_blocks)

    def allow(self, doc: str, n_blocks: int) -> bool:
        """★ 是否允许处理该文档的块（★ 并记账）。"""
        self._docs_seen += 1
        _q = self.doc_quota()
        if _q <= 0:
            return False
        self._quota_used[doc] = _q
        self.blocks_allowed += min(n_blocks, _q)
        return True

    def skip(self, doc: str, start: int, reason: str) -> None:
        """★ 记录**未处理块**与原因（★ 不静默）。"""
        self.blocks_skipped += 1
        self.skipped.append({"doc": doc, "start": start, "reason": reason})

    def spend_call(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """★ 记一次调用与 token 消耗（★ 成本闸用）。"""
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)

    def over_budget(self) -> Optional[str]:
        """★ 是否越界（★ 返回原因；未越界 ⇒ None）。"""
        if self.max_calls is not None and self.calls >= self.max_calls:
            return "max_calls_reached"
        if self.max_tokens is not None and \
                (self.input_tokens + self.output_tokens) >= self.max_tokens:
            return "max_tokens_reached"
        return None

    def estimated_cost(self) -> Optional[float]:
        """★ 费用估算（★ **无单价 ⇒ null**，不臆造价格）。"""
        if self.cost_per_1k is None:
            return None
        _t = self.input_tokens + self.output_tokens
        return round(_t / 1000.0 * float(self.cost_per_1k), 6)

    def report(self) -> dict:
        """★ 预算与成本统计（★ 可观测）。"""
        return {
            "protocol": self.protocol,
            "per_doc_blocks": self.per_doc_blocks,
            "max_calls": self.max_calls,
            "max_tokens": self.max_tokens,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "blocks_allowed": self.blocks_allowed,
            "blocks_skipped": self.blocks_skipped,
            "skipped_detail": list(self.skipped[:200]),
            "estimated_cost": self.estimated_cost(),
            "cost_per_1k": self.cost_per_1k,
            "over_budget_reason": self.over_budget(),
        }


def budget_from_env(protocol: str, docs_total: int = 0) -> BlockBudget:
    """★ 从环境变量构造预算（★ **默认全部保守** ⇒ 不触发历史重抽）。

    环境变量：
      ``PROSE_BLOCKS_PER_DOC``  每文档块数（★ 默认 1）
      ``PROSE_MAX_CALLS``       协议级调用上限（★ 默认不限）
      ``PROSE_MAX_TOKENS``      token 上限（★ 默认不限）
      ``PROSE_COST_PER_1K``     每千 token 单价（★ 默认 None ⇒ 不估算）
    """
    import os

    def _i(k, d=None):
        try:
            v = os.environ.get(k)
            return int(v) if v not in (None, "") else d
        except (TypeError, ValueError):
            return d

    def _f(k):
        try:
            v = os.environ.get(k)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    _b = BlockBudget(
        protocol=protocol,
        per_doc_blocks=max(1, _i("PROSE_BLOCKS_PER_DOC", 1) or 1),
        max_calls=_i("PROSE_MAX_CALLS"),
        max_tokens=_i("PROSE_MAX_TOKENS"),
        cost_per_1k=_f("PROSE_COST_PER_1K"),
    )
    _b.set_doc_total(docs_total)
    return _b


__all__ = ["BlockBudget", "budget_from_env"]
