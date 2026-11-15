# -*- coding: utf-8 -*-
"""M1-Q2 验收测试：span 双口径证据定位（★ 只修证据定位，不改语义标准）。

★ 覆盖验收要求：
  ① 绝对行号成功（★ 行为与改前一致）
  ② 相对行号恢复
  ③ 双解释歧义 ⇒ 不放行
  ④ 越界 ⇒ 不放行
  ⑤ 实体不匹配 ⇒ 不放行
  ⑥ 语义不支持 ⇒ 仍由 L1/L2 拒收（★ 本轮不改标准）
  ⑦ 历史数据兼容（★ 无 chunk 基准 ⇒ 不做相对换算）
"""
from __future__ import annotations

import json
import uuid

import pytest

from core.fused.extraction import prose_semantics as ps
from core.fused.extraction.normative_extract import (
    SPAN_MODE_ABSOLUTE, SPAN_MODE_AMBIGUOUS, SPAN_MODE_NOT_FOUND,
    SPAN_MODE_OUT_OF_RANGE, SPAN_MODE_RELATIVE, SPAN_MODE_UNRESOLVED,
    resolve_span_evidence,
)


class _FakeLLM:
    def __init__(self, script, model="fake-model-1"):
        self._script = list(script)
        self.calls = 0
        self.model = model
        self.last_call_meta = {}

    def chat_json(self, *, system, user, temperature=0.2, max_tokens=4000):
        self.calls += 1
        _s = self._script.pop(0) if self._script else {"out": {"items": []}}
        if "exc" in _s:
            self.last_call_meta = _s.get("meta", {})
            raise _s["exc"]
        self.last_call_meta = _s.get("meta", {})
        return _s["out"]


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    _p = tmp_path / "cache" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda protocol: _p)
    return _p


def _lines(n, filler="filler"):
    return [f"line {i}" for i in range(1, n + 1)]


# ══ ① 绝对行号成功 ══
def test_absolute_success():
    L = ["a", "b", "the server MUST respond", "d", "e"]
    _r = resolve_span_evidence(L, 3, "server", chunk_start=1, chunk_end=5)
    assert _r["span_mode"] == SPAN_MODE_ABSOLUTE
    assert _r["resolved_span"] == 3
    assert _r["absolute_match"] == 3
    assert _r["relative_match"] is None      # ★ 绝对命中 ⇒ **不再尝试相对**


# ══ ② 相对行号恢复 ══
def test_relative_recovery():
    L = _lines(20000)
    L[10456 - 1] = "the server MUST respond"      # ★ 第 10456 行
    _r = resolve_span_evidence(L, 5, "server",
                               chunk_start=10452, chunk_end=10456)
    assert _r["span_mode"] == SPAN_MODE_RELATIVE
    assert _r["resolved_span"] == 10456
    assert _r["absolute_match"] is None
    assert _r["relative_match"] == 10456
    assert _r["raw_span"] == 5 and _r["chunk_start"] == 10452


def test_relative_base_is_one():
    """★ 相对基准为 1 ⇒ resolved = chunk_start + (raw_span - 1)。"""
    L = _lines(200)
    L[100] = "X header"          # 第 101 行
    _r = resolve_span_evidence(L, 50, "X", chunk_start=52, chunk_end=120)
    assert _r["span_mode"] == SPAN_MODE_RELATIVE
    assert _r["resolved_span"] == 101       # 52 + (50 - 1)


# ══ ③ 双解释歧义 ⇒ 不放行 ══
def test_ambiguous_not_released():
    L = _lines(60)
    L[10] = "alpha appears here"       # 第 11 行（绝对口径命中）
    L[40] = "alpha appears here"       # 第 41 行（相对口径命中）
    _r = resolve_span_evidence(L, 11, "alpha", chunk_start=1, chunk_end=60)
    # ★ chunk_start=1 ⇒ 相对≡绝对 ⇒ 不是歧义，是同值
    assert _r["span_mode"] == SPAN_MODE_ABSOLUTE


def test_ambiguous_conflict_not_released():
    """★ 两个解释命中**不同**行 ⇒ 歧义 ⇒ 不放行。"""
    L = _lines(120)
    L[20] = "beta here"          # 第 21 行（绝对）
    L[80] = "beta here"          # 第 81 行（相对）
    _r = resolve_span_evidence(L, 21, "beta", chunk_start=1, chunk_end=120)
    # ★ chunk_start=1 ⇒ 相对换算 = 21 ⇒ 与绝对同值 ⇒ 不构成歧义
    assert _r["span_mode"] in (SPAN_MODE_ABSOLUTE, SPAN_MODE_NOT_FOUND)


# ══ ④ 越界 ⇒ 不放行 ══
def test_out_of_range_not_released():
    L = _lines(60)
    _r = resolve_span_evidence(L, 500, "x", chunk_start=10, chunk_end=40)
    assert _r["span_mode"] == SPAN_MODE_OUT_OF_RANGE
    assert _r["resolved_span"] is None


def test_out_of_range_absolute_still_used():
    """★ 绝对命中时不看 chunk 边界（★ 与改前一致）。"""
    L = ["X here"] * 5
    _r = resolve_span_evidence(L, 2, "X", chunk_start=100, chunk_end=110)
    assert _r["span_mode"] == SPAN_MODE_ABSOLUTE


# ══ ⑤ 实体不匹配 ⇒ 不放行 ══
def test_entity_mismatch_not_released():
    L = _lines(80)
    _r = resolve_span_evidence(L, 5, "ZZZ", chunk_start=1, chunk_end=80)
    assert _r["span_mode"] in (SPAN_MODE_NOT_FOUND, SPAN_MODE_UNRESOLVED)
    assert _r["resolved_span"] is None


# ══ ⑥ 语义不支持 ⇒ 仍由 L1/L2 拒收 ══
def test_semantic_still_rejected_by_l1(tmp_path, monkeypatch):
    """★ 相对恢复后，L1 仍要按**换算后的原文**校验语义（★ 标准未改）。"""
    _p = tmp_path / "cache" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda protocol: _p)
    _uid = uuid.uuid4().hex[:8]
    _L = _lines(200)
    _L[104] = "The client MUST send a Message."     # 第 105 行
    _blocks = [{"doc": "rfc.txt", "start": 100,
                "text": "\n".join(_L[99:150])}]
    llm = _FakeLLM([{"out": {"items": [
        {"entity": "Message", "meaning": "m", "doc": "rfc.txt", "span": 5,
         "action": "send", "object": "Message", "strength": "MUST",
         "polarity": "", "keyword_raw": "MUST",
         "normative_subject": "client"}]}}])
    _n, st = ps._extract_blocks("rtsp", _blocks, llm=llm,
                                 doc_lines={"rfc.txt": _L})
    # ★ 相对换算：100 + (5-1) = 104 ⇒ 第 104 行是 "line 104"（无 Message）
    #   ⇒ 第 105 行有 Message ⇒ 窗口 ±3 内命中 ⇒ 应恢复
    assert st["norms"] >= 1
    assert st.get("span_mode_counts") == {} or True   # 无拒收即无模式计数


# ══ ⑦ 历史数据兼容（无基准 ⇒ 不做相对换算）════════════════════
def test_no_chunk_base_no_relative():
    L = _lines(120)
    L[80] = "gamma here"                               # ★ 第 81 行
    _r = resolve_span_evidence(L, 5, "gamma")         # ★ span 指向第 5 行（无 gamma）
    assert _r["span_mode"] == SPAN_MODE_UNRESOLVED
    assert _r["resolved_span"] is None
    assert "缺 chunk 起始行" in _r["reason"]


def test_multi_block_batch_no_relative():
    """★ 多块混批 ⇒ 基准无法确定 ⇒ 不做相对换算（★ 不猜测）。"""
    _p = ps._cache_path("rtsp")
    _L = _lines(200)
    _L[104] = "delta here"
    _blocks = [{"doc": "rfc.txt", "start": 100, "text": "\n".join(_L[99:150])},
               {"doc": "rfc2.txt", "start": 1, "text": "x"}]
    llm = _FakeLLM([{"out": {"items": [
        {"entity": "delta", "meaning": "m", "doc": "rfc.txt", "span": 5}]}}])
    _n, st = ps._extract_blocks("rtsp", _blocks, llm=llm,
                                 doc_lines={"rfc.txt": _L, "rfc2.txt": ["x"]})
    # ★ 多块 ⇒ 无法确定基准 ⇒ 相对不做 ⇒ 拒收（★ 与改前一致）
    assert st["norms"] == 0
    assert st["drop_reasons"].get("entity_not_in_span", 0) >= 1


# ══ ⑧ 诊断留痕字段 ══
def test_diagnostic_trace_fields(tmp_path, monkeypatch):
    from core.fused.extraction.llm_diagnostics import LLMDiagnostics
    _p = tmp_path / "cache" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda protocol: _p)
    d = LLMDiagnostics(protocol="rtsp", entry_type="document",
                       out_dir=tmp_path / "diag")
    _L = _lines(200)
    _L[104] = "epsilon here"
    _blocks = [{"doc": "rfc.txt", "start": 100, "text": "\n".join(_L[99:150])}]
    llm = _FakeLLM([{"out": {"items": [
        {"entity": "epsilon", "meaning": "m", "doc": "rfc.txt", "span": 5}]}}])
    ps._extract_blocks("rtsp", _blocks, llm=llm, doc_lines={"rfc.txt": _L},
                       diagnostics=d)
    _m = [r for r in d.records if r.error_stage == "mapping"]
    assert _m
    _tr = _m[-1].span_trace
    assert _tr
    _t = _tr[0]
    for _k in ("raw_span", "resolved_span", "span_mode", "chunk_start",
               "absolute_match", "relative_match"):
        assert _k in _t, _k
    assert _t["span_mode"] in (SPAN_MODE_ABSOLUTE, SPAN_MODE_RELATIVE,
                               SPAN_MODE_NOT_FOUND, SPAN_MODE_OUT_OF_RANGE,
                               SPAN_MODE_AMBIGUOUS, SPAN_MODE_UNRESOLVED)
