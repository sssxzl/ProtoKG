# -*- coding: utf-8 -*-
"""M1-Q3 前置修正的回归测试：★ 锚点 / 匹配行 / L1-L2 证据窗口 三者分离。

★ 锁定 M1-Q3 前置检查发现的**真实误伤**：
  `sip/rfc3261.txt@10452` 的 `server`（raw_span=15）
    · 锚点行 10466 = 「field.  The server MUST include a list of the unsupported extensions」
    · entity 首次匹配行 10464 = 「The server did not understand the protocol extension…」
  ⇒ ⇒ **改前** quote 取 10464 ⇒ ⇒ L2 认为 action=include 不受支持 ⇒ ⇒ **误拒**
  ⇒ ⇒ **改后** quote 取 [10464..10466] 完整窗口 ⇒ ⇒ ★ 原文**支持**该动作
"""
from __future__ import annotations

import uuid

import pytest

from core.fused.extraction import prose_semantics as ps
from core.fused.extraction.normative_extract import (
    SPAN_MODE_ABSOLUTE, SPAN_MODE_RELATIVE,
    resolve_span_evidence, span_quote_window,
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


def _sip_lines():
    """★ 复现 sip/rfc3261.txt 的 10460~10468 行（★ 真实原文）。"""
    _L = [f"line {i}" for i in range(1, 11000)]
    _L[10463] = "   The server did not understand the protocol extension specified in a"
    _L[10464] = "   Proxy-Require (Section 20.29) or Require (Section 20.32) header"
    _L[10465] = "   field.  The server MUST include a list of the unsupported extensions"
    _L[10466] = "   in an Unsupported header field in the response.  UAC processing of"
    return _L


# ══ ① 锚点 ≠ 匹配行：resolved_span 必须是锚点 ══
def test_resolved_span_is_anchor_not_match():
    L = _sip_lines()
    _r = resolve_span_evidence(L, 10466, "server",
                               chunk_start=10452, chunk_end=10520)
    assert _r["span_mode"] == SPAN_MODE_ABSOLUTE
    # ★ 锚点 = 10466（★ 改前这里返回的是 matched=10464）
    assert _r["resolved_span"] == 10466
    # ★ 匹配行单列（entity 在窗口内首次出现）
    assert _r["matched_evidence_lines"] == 10464


def test_relative_resolved_span_is_anchor():
    L = _sip_lines()
    _r = resolve_span_evidence(L, 15, "server",
                               chunk_start=10452, chunk_end=10520)
    assert _r["span_mode"] == SPAN_MODE_RELATIVE
    assert _r["resolved_span"] == 10466      # ★ 10452 + (15 - 1)
    assert _r["matched_evidence_lines"] == 10464


# ══ ② quote 窗口覆盖「锚点↔匹配行」完整句子 ══
def test_quote_window_covers_anchor_to_match():
    _info = {"resolved_span": 10466, "matched_evidence_lines": 10464}
    _w = span_quote_window(_info)
    assert _w == (10464, 10466)


def test_quote_window_single_line_when_no_match():
    assert span_quote_window({"resolved_span": 10,
                               "matched_evidence_lines": None}) == (10, 10)
    assert span_quote_window({"resolved_span": None}) is None


# ══ ③ 端到端：L2 看到的 quote 必须含「MUST include」 ══
def test_l2_quote_contains_must_include(tmp_path, monkeypatch):
    _p = tmp_path / "cache" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda protocol: _p)
    L = _sip_lines()
    _blocks = [{"doc": "rfc3261.txt", "start": 10452,
                "text": "\n".join(L[10451:10520])}]
    llm = _FakeLLM([{"out": {"items": [
        {"entity": "server", "meaning": "m", "doc": "rfc3261.txt",
         "span": 15, "action": "include", "object": "list of extensions",
         "constraint": "The server MUST include a list of the unsupported extensions",
         "strength": "MUST", "polarity": "", "keyword_raw": "MUST",
         "normative_subject": "server"}]}}])
    _norms, _stats = ps._extract_blocks("sip", _blocks, llm=llm,
                                        doc_lines={"rfc3261.txt": L})
    assert _norms, "★ 候选应通过映射"
    _n = _norms[0]
    assert _n["span_line"] == 10466            # ★ span_line = 锚点
    assert _n["span_matched_line"] == 10464    # ★ 匹配行单列
    # ★ L1/L2 的 quote 必须覆盖完整句子（含 MUST include）
    _q = (_n.get("_l1_quote") or "")
    assert "MUST include" in _q, _q
    assert "did not understand" in _q, _q


# ══ ④ 绝对口径下同样用锚点 ══
def test_absolute_uses_anchor_and_records_match():
    L = _sip_lines()
    _r = resolve_span_evidence(L, 10466, "server")
    assert _r["span_mode"] == SPAN_MODE_ABSOLUTE
    assert _r["resolved_span"] == 10466
    assert _r["matched_evidence_lines"] == 10464
