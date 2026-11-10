# -*- coding: utf-8 -*-
"""tests/fused/test_transition_merge.py —— D′ 跨块 PSM 合并（PSMBENCH 第③步）。

★ 设计要点（2026-11-06 实测，勿改回无条件合并）：
  · rtsp：表格腿 14 条 与 LLM 腿 14 条**集合完全相同**，0 冲突
    ⇒ 无条件合并收益 = 0；
  · sip：质量闸后 0 条；
  · smtp：RFC 无状态机表述。
  ⇒ 实现为**冲突驱动**：无冲突 ⇒ 仅去重（零 LLM）；有冲突 ⇒ 才调 LLM 消解。

★ 本文件锁住：
  1. 冲突检测语义（同 from+method 多 to 才算冲突；完全重复不算）；
  2. **无冲突时零 LLM 调用**（用会爆炸的 stub 证明）；
  3. 有冲突时合并结果受「method ∈ 已知方法集」约束；
  4. 合并失败 / 合并为空 ⇒ **保留原样**（防退化）；
  5. 真实 rtsp 上 merged=False（与表格腿一致，不该动）。
"""
from __future__ import annotations

import inspect
import re

import pytest

from core.fused.extraction import rfc_extractor as RX
from core import paths


class _Boom:
    """任何调用都爆炸 ⇒ 用于证明「不该调 LLM」。"""

    def chat_json(self, **kw):
        raise AssertionError("此处不应调用 LLM")


class _MergeStub:
    """返回固定合并结果，并记录调用次数。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def chat_json(self, **kw):
        self.calls += 1
        return self.payload


# ===========================================================================
# ① 冲突检测语义
# ===========================================================================

def test_conflict_detected_for_same_from_method_multiple_targets():
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PLAY", "to": "C"}]
    conf = RX._psm_conflicts(rows)
    assert len(conf) == 1
    assert conf[0]["from"] == "A" and conf[0]["method"] == "PLAY"
    assert conf[0]["targets"] == ["B", "C"]


def test_exact_duplicate_is_not_conflict():
    """★ 完全相同的重复**不算**冲突（只需去重）。"""
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PLAY", "to": "B"}]
    assert RX._psm_conflicts(rows) == []


def test_different_methods_same_targets_not_conflict():
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PAUSE", "to": "B"}]
    assert RX._psm_conflicts(rows) == []


# ===========================================================================
# ② 无冲突 ⇒ 零 LLM 调用 + 仅去重
# ===========================================================================

def test_no_conflict_does_not_call_llm():
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PLAY", "to": "B"}]   # 重复
    out, stat = RX._merge_partial_psms(rows, "rtsp", _Boom())
    assert out == [{"from": "A", "method": "PLAY", "to": "B"}]
    assert stat["conflicts"] == 0
    assert stat["merged"] is False


def test_empty_input_returns_empty():
    out, stat = RX._merge_partial_psms([], "rtsp", _Boom())
    assert out == [] and stat["merged"] is False


# ===========================================================================
# ③ 有冲突 ⇒ 调 LLM，且结果受 method 白名单约束
# ===========================================================================

def test_conflict_triggers_llm_and_filters_unknown_method(monkeypatch):
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PLAY", "to": "C"}]
    stub = _MergeStub({"transitions": [
        {"from": "A", "method": "PLAY", "to": "B"},        # 合法
        {"from": "A", "method": "BOGUS_EVENT", "to": "C"},  # 假方法 ⇒ 应被丢
    ]})
    # rtsp 的真实方法集（确保 PLAY 在内、BOGUS_EVENT 不在内）
    monkeypatch.setattr(RX, "_rfc_source_methods",
                        lambda *_a, **_k: {"PLAY", "PAUSE", "SETUP"})
    out, stat = RX._merge_partial_psms(rows, "rtsp", stub)
    assert stub.calls == 1, "有冲突时必须调用 LLM 合并"
    assert stat["merged"] is True
    assert {r["method"] for r in out} == {"PLAY"}


def test_merge_empty_result_keeps_original(monkeypatch):
    """★ 合并后为空 ⇒ **保留原样**（防退化），不得把结果清空。"""
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PLAY", "to": "C"}]
    stub = _MergeStub({"transitions": []})
    monkeypatch.setattr(RX, "_rfc_source_methods",
                        lambda *_a, **_k: {"PLAY"})
    out, stat = RX._merge_partial_psms(rows, "rtsp", stub)
    assert out == rows, "合并为空时必须保留原样"
    assert stat["merged"] is False
    assert "保留原样" in stat.get("note", "")


def test_merge_llm_unavailable_keeps_original(monkeypatch):
    rows = [{"from": "A", "method": "PLAY", "to": "B"},
            {"from": "A", "method": "PLAY", "to": "C"}]

    def _boom_ctor(*a, **k):
        raise RuntimeError("no key")

    import core.llm as _llm
    monkeypatch.setattr(_llm, "DeepSeekClient", _boom_ctor)
    out, stat = RX._merge_partial_psms(rows, "rtsp", None)
    assert out == rows
    assert stat["merged"] is False


# ===========================================================================
# ④ 真实 rtsp：无冲突 ⇒ merged=False（与表格腿一致，不该动）
# ===========================================================================

def test_rtsp_real_run_is_noop():
    """★ rtsp 的 LLM 腿与表格腿 14 条完全一致且 0 冲突 ⇒ 合并必须是**空操作**。"""
    if not paths.kb_source_dir("rtsp", "rfc").is_dir():
        pytest.skip("无 RFC 底料")
    sm = paths.per_source_root("rtsp") / "state_machines.json"
    if not sm.is_file():
        pytest.skip("无状态机产物")
    import json
    d = json.loads(sm.read_text(encoding="utf-8"))
    llm_rows = (d.get("sources") or {}).get("rfc:llm") or []
    if not llm_rows:
        pytest.skip("无 rfc:llm 产物")
    assert RX._psm_conflicts(llm_rows) == [], "rtsp 的 LLM 腿不该有冲突"


# ===========================================================================
# ⑤ 协议无关性守卫
# ===========================================================================

def test_no_protocol_hardcode_in_merge():
    src = inspect.getsource(RX._merge_partial_psms)
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"#[^\n]*", "", src)
    for bad in ("rtsp", "sip", "smtp", "CSeq", "PLAY", "SETUP"):
        assert not re.search(rf"\b{re.escape(bad)}\b", src), (
            f"合并实现出现协议/方法特例「{bad}」⇒ 违反 G2")


def test_merge_version_enters_cache_key():
    """★ 合并提示版本必须并入缓存键（否则改合并提示静默不生效）。"""
    src = inspect.getsource(RX.infer_transitions)
    assert "TRANSITION_MERGE_PROMPT_VERSION" in src
