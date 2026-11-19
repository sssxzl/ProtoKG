# -*- coding: utf-8 -*-
"""M1-③ 验收测试：LLM 失败结构化记录（★ 只观测，不改语义）。

★ 覆盖验收要求：
  ① 正常 JSON 响应记录成功
  ② JSONDecodeError 留下结构化证据
  ③ 模型输出截断能单独归因（finish_reason=length）
  ④ API 超时 / 失败 / 缓存命中可区分
  ⑤ 重试恢复与最终放弃可区分
  ⑥ 诊断写盘失败不影响抽取
"""
from __future__ import annotations

import json
import pathlib
import uuid

import pytest

from core.fused.extraction.llm_diagnostics import (LLMDiagnostics, summarize_runs)
from core.fused.extraction.prose_semantics import _extract_blocks


@pytest.fixture(autouse=True)
def _isolate_prose_cache(tmp_path, monkeypatch):
    """R27：把散文缓存目录重定向到临时目录，避免测试桩写进 derived/。

    背景：本文件多处调用 ``_extract_blocks("rtsp", ...)``，历史上会把块结果
    写进受版本管理的 ``derived/cache/source_blocks/rtsp.prose.json``，
    导致每次跑测试后都要手工 ``git checkout --`` 还原。
    """
    from core.fused.extraction import source_retrieval as _sr
    _d = tmp_path / "prose_cache"
    _d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_sr, "CACHE_DIR", _d, raising=False)
    return _d



class _FakeLLM:
    """★ 可编排的假 LLM（★ 记录调用次数，模拟各种失败）。"""

    def __init__(self, script, model="fake-model-1"):
        self._script = list(script)
        self.calls = 0
        self.model = model
        self.last_call_meta = {}

    def chat_json(self, *, system, user, temperature=0.2, max_tokens=4000):
        self.calls += 1
        _step = self._script.pop(0) if self._script else {"out": {"items": []}}
        if "exc" in _step:
            self.last_call_meta = _step.get("meta", {})
            raise _step["exc"]
        self.last_call_meta = _step.get("meta", {})
        return _step["out"]


def _blocks(n=1):
    """★ 块内容带**唯一后缀** ⇒ ⇒ 缓存键必不命中 ⇒ ⇒ 不会读到既有缓存。"""
    _u = uuid.uuid4().hex[:12]
    return [{"doc": "rfc2326.txt", "start": 10 + i,
             "text": f"The client MUST send X. [uid={_u}-{i}]"}
            for i in range(n)]


def _mk_diag(tmp_path):
    d = LLMDiagnostics(protocol="rtsp", entry_type="document",
                       out_dir=tmp_path / "diag")
    return d


# ══════════════════════ ① 正常响应记录成功 ══════════════════════
def test_success_record(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([{"out": {"items": [{"entity": "client", "meaning": "m",
                                        "doc": "rfc2326.txt"}]},
                      "meta": {"input_tokens": 11, "output_tokens": 22,
                               "finish_reason": "stop",
                               "raw_response_sha256": "abc"}}])
    _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    # ★ 2 条：1 次 LLM 调用 + 1 条产物映射记录
    assert len(d.records) == 2
    r = d.records[0]
    assert r.outcome == "success"
    assert r.error_stage is None
    assert r.input_tokens == 11 and r.output_tokens == 22
    assert r.finish_reason == "stop"
    assert r.raw_response_sha256 == "abc"
    assert r.chunk_hash and r.prompt_digest
    assert r.attempt == 1
    assert r.model == "fake-model-1"
    assert r.error_type is None


# ══════════════════════ ② JSONDecodeError 结构化证据 ══════════════════════
def test_json_decode_error_recorded(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([{"exc": json.JSONDecodeError("Expecting value: line 1 column 1", "", 0)},
                    {"exc": json.JSONDecodeError("Expecting value: line 1 column 1", "", 0)}])
    _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    assert len(d.records) == 3   # ★ 2 次调用 + 1 条映射记录
    for r in d.records[:2]:
        assert r.error_stage == "json_parse"
        assert r.error_type == "JSONDecodeError"
        assert r.outcome in ("failed", "abandoned")
    # ★ 最终失败 ⇒ **调用记录**的最后一条标为 abandoned（★ 末尾还有一条映射记录）
    _calls = [r for r in d.records if r.error_stage != "mapping"]
    assert _calls[-1].outcome == "abandoned"


# ══════════════════════ ③ 截断单独归因（finish_reason=length）══════════════
def test_truncation_attributed(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([{"exc": json.JSONDecodeError("Expecting value: line 1 column 1", "", 0),
                      "meta": {"finish_reason": "length", "output_tokens": 16000,
                               "raw_response_sha256": "deadbeef"}},
                    {"exc": json.JSONDecodeError("x", "", 0),
                     "meta": {"finish_reason": "length"}}])
    _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    r0 = d.records[0]
    assert r0.finish_reason == "length"          # ★ 截断可单独归因
    assert r0.output_tokens == 16000
    assert r0.raw_response_sha256 == "deadbeef"
    assert r0.error_stage == "json_parse"


# ══════════════════════ ④ 请求失败 vs 缓存命中 可区分 ══════════════════════
def test_request_error_stage(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([{"exc": TimeoutError("read timed out")},
                    {"exc": TimeoutError("read timed out")}])
    _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    assert all(r.error_stage == "request" for r in d.records[:2])
    assert all(r.error_type == "TimeoutError" for r in d.records[:2])
    _calls = [r for r in d.records if r.error_stage != "mapping"]
    assert _calls[0].outcome == "failed"
    assert _calls[-1].outcome == "abandoned"


def test_cache_hit_recorded_without_call(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([])
    _b = _blocks()                    # ★ 同一批块（★ 否则块哈希不同 ⇒ 缓存不命中）
    # ★ 先跑一次制造缓存
    llm2 = _FakeLLM([{"out": {"items": []}}])
    _extract_blocks("rtsp", _b, llm=llm2)
    # ★ 再跑 ⇒ 命中缓存 ⇒ 不应再有 LLM 调用
    _n_before = llm.calls
    _extract_blocks("rtsp", _b, llm=llm, diagnostics=d)
    assert llm.calls == _n_before                # ★ 无新增调用
    assert d.records and all(r.cache_hit for r in d.records)
    assert d.records[0].outcome == "success"


# ══════════════════════ ⑤ 重试恢复 vs 最终放弃 ══════════════════════
def test_retry_recovered_vs_abandoned(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([{"exc": RuntimeError("boom")},
                    {"out": {"items": [{"entity": "e", "meaning": "m",
                                        "doc": "d"}]}}])
    _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    assert d.records[0].outcome == "failed"      # ★ 第一次失败
    assert d.records[1].outcome == "success"     # ★ 重试恢复
    assert d.records[0].attempt == 1 and d.records[1].attempt == 2


# ══════════════════════ ⑥ 诊断写盘失败不影响抽取 ══════════════════════
def test_flush_failure_does_not_raise(tmp_path):
    d = LLMDiagnostics(protocol="rtsp", entry_type="document",
                       out_dir=tmp_path / "no_such_dir" / "\0bad")
    llm = _FakeLLM([{"out": {"items": []}}])
    _norms, stats = _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    assert stats["calls"] == 1                   # ★ 抽取未受影响


# ══════════════════════ ⑦ 汇总与落盘 ══════════════════════
def test_summary_and_flush(tmp_path):
    d = _mk_diag(tmp_path)
    llm = _FakeLLM([{"exc": json.JSONDecodeError("x", "", 0)},
                    {"exc": json.JSONDecodeError("x", "", 0)}])
    _extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    p = d.flush()
    assert p and pathlib.Path(p).is_file()
    _s = d.summary()
    assert _s["counters"]["llm_calls"] == 2
    assert _s["counters"]["parse_failed"] == 2
    assert _s["error_stages"].get("json_parse") == 2
    assert _s["outcomes"].get("abandoned") == 1
    # ★ 落盘后可再汇总
    _all = summarize_runs(d.out_dir)
    assert d.run_id in _all


# ══════════════════════ ⑧ 不传 diagnostics ⇒ 行为不变（无记录）══════════════
def test_no_diagnostics_no_side_effect():
    llm = _FakeLLM([{"out": {"items": []}}])
    _norms, stats = _extract_blocks("rtsp", _blocks(), llm=llm)
    assert stats["calls"] == 1
    assert "diagnostics" not in stats


# ══════════════════════ ⑨ 真实缓存不被污染（R27 反向测试）══════════════
def test_real_prose_cache_untouched(tmp_path):
    """跑完抽取后，受版本管理的真实缓存必须逐字节不变。"""
    import hashlib

    _root = pathlib.Path(__file__).resolve().parents[2]
    _real = _root / "derived" / "cache" / "source_blocks" / "rtsp.prose.json"
    _before = hashlib.sha256(_real.read_bytes()).hexdigest() if _real.is_file() else None

    llm = _FakeLLM([{"out": {"items": []}}])
    _extract_blocks("rtsp", _blocks(), llm=llm)

    _after = hashlib.sha256(_real.read_bytes()).hexdigest() if _real.is_file() else None
    assert _before == _after                      # 真实缓存未变
    # 且缓存确实写进了临时目录（证明重定向生效，而不是根本没写）
    assert list((tmp_path / "prose_cache").glob("*.json"))
