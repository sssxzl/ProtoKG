# -*- coding: utf-8 -*-
"""M1-Q3：块预算机制测试（★ 预算受控、确定性、不得无意耗尽协议预算）。"""
from __future__ import annotations

import pytest

from core.fused.extraction.block_budget import BlockBudget, budget_from_env


def test_default_is_conservative():
    """★ 默认配置**不得**触发大规模重抽（★ 每文档 1 块、调用不限）。"""
    _b = budget_from_env("rtsp", docs_total=10)
    assert _b.per_doc_blocks == 1
    assert _b.max_calls is None
    assert _b.max_tokens is None
    assert _b.estimated_cost() is None      # ★ 无单价 ⇒ null，不臆造


def test_doc_quota_does_not_exhaust_protocol():
    """★ 单个 RFC 不得无意耗尽整个协议的调用预算。"""
    _b = BlockBudget(protocol="rtsp", per_doc_blocks=100, max_calls=10)
    _b.set_doc_total(4)
    _q = []
    for _i in range(4):
        _q.append(_b.doc_quota())
        _b._docs_seen += 1
    # ★ 10 次调用 / 4 个文档 ⇒ 每文档 ≈ 2 块（★ 而不是 100 块）
    assert all(x <= 3 for x in _q), _q
    assert sum(_q) <= 10


def test_allow_and_skip_are_recorded():
    _b = BlockBudget(protocol="rtsp", per_doc_blocks=2, max_calls=100)
    _b.set_doc_total(2)
    assert _b.allow("a.txt", 2) is True
    _b.skip("b.txt", 100, "budget_exhausted")
    _r = _b.report()
    assert _r["blocks_allowed"] == 2
    assert _r["blocks_skipped"] == 1
    assert _r["skipped_detail"][0]["reason"] == "budget_exhausted"


def test_call_and_token_accounting():
    _b = BlockBudget(protocol="rtsp", per_doc_blocks=1, max_calls=3)
    _b.spend_call(100, 50)
    _b.spend_call(200, 60)
    _r = _b.report()
    assert _r["calls"] == 2
    assert _r["input_tokens"] == 300
    assert _r["output_tokens"] == 110
    assert _r["total_tokens"] == 410
    assert _r["over_budget_reason"] is None
    _b.spend_call(1, 1)
    assert _b.report()["over_budget_reason"] == "max_calls_reached"


def test_cost_requires_explicit_price():
    _b = BlockBudget(protocol="rtsp", per_doc_blocks=1)
    _b.spend_call(1000, 1000)
    assert _b.estimated_cost() is None      # ★ 无单价 ⇒ null
    _b.cost_per_1k = 0.001
    assert _b.estimated_cost() == pytest.approx(0.002)


def test_token_budget_stops():
    _b = BlockBudget(protocol="rtsp", per_doc_blocks=10, max_tokens=1000)
    _b.spend_call(600, 500)
    assert _b.report()["over_budget_reason"] == "max_tokens_reached"


def test_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("PROSE_BLOCKS_PER_DOC", "7")
    monkeypatch.setenv("PROSE_MAX_CALLS", "33")
    monkeypatch.setenv("PROSE_COST_PER_1K", "0.002")
    _b = budget_from_env("rtsp", docs_total=3)
    assert _b.per_doc_blocks == 7
    assert _b.max_calls == 33
    assert _b.cost_per_1k == 0.002
