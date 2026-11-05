# -*- coding: utf-8 -*-
"""tests/fused/test_transition_quality_gate.py —— 状态机抽取的**质量闸**。

★ 闸的两条判据（均可机器判定、协议无关）：
  ① **可溯源**：状态名必须出现在该协议的 RFC 原文里；
  ② **可驱动**：method 必须是该协议 RFC 源里的**真实方法名**。

★ 为何必须有 ②（实测依据）：SIP / SMTP 的 RFC 状态机**状态名很纯**
  （RFC 原文命中 100% / 69%），但**触发列是事件**（`1xx` / `2xx` / `Timer F` / `220`）
  ⇒ 若直接进 `transitions` 桶，下游会生成**方法名为 `1xx` 的假报文**。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.fused import rfc_extractor as RX


# ===========================================================================
# ① 两条判据
# ===========================================================================

def test_gate_keeps_traceable_and_drivable():
    cfg = {"method_sections": ["10"]}
    rfc = "Init Ready SETUP OPTIONS PLAY"      # ★ 须同时含状态名与方法名
    rows = [{"from": "Init", "method": "SETUP", "to": "Ready"}]
    kept, stat = RX._transition_quality_gate(
        rows, "x", cfg, rfc, known_methods={"SETUP", "PLAY"})
    assert len(kept) == 1, f"应放行，实得 {kept}"
    assert stat["kept"] == 1 and stat["total"] == 1


def test_gate_drops_state_not_in_rfc():
    cfg = {"method_sections": ["10"]}
    rfc = "Init Ready SETUP OPTIONS PLAY"
    rows = [{"from": "Init", "method": "SETUP", "to": "Bogus"}]
    kept, stat = RX._transition_quality_gate(
        rows, "x", cfg, rfc, known_methods={"SETUP"})
    assert kept == []
    assert stat["dropped_state_not_in_rfc"] == 1


def test_gate_drops_event_like_method():
    """★ 事件型触发条件（`1xx` / `Timer F` / `220`）不是方法 ⇒ 必须拦下。"""
    cfg = {"method_sections": ["10"]}
    rfc = "Init Ready Trying Proceeding Terminated"
    rows = [{"from": "Trying", "method": "1xx", "to": "Proceeding"},
            {"from": "Trying", "method": "Timer F", "to": "Terminated"}]
    kept, stat = RX._transition_quality_gate(
        rows, "x", cfg, rfc, known_methods={"SETUP"})
    assert kept == []
    assert stat["dropped_method_not_a_method"] == 2
    assert stat["dropped_state_not_in_rfc"] == 0


def test_gate_drops_incomplete_rows():
    cfg = {"method_sections": ["10"]}
    rfc = "Init Ready SETUP"
    rows = [{"from": "Init", "method": "", "to": "Ready"},
            {"from": "", "method": "SETUP", "to": "Ready"}]
    kept, _stat = RX._transition_quality_gate(
        rows, "x", cfg, rfc, known_methods={"SETUP"})
    assert kept == []


# ===========================================================================
# ② 协议无关性守卫
# ===========================================================================

def test_gate_source_has_no_protocol_specific_constants():
    """★ G2：**闸函数本身**不得含协议名或协议特定方法名。

    ★ 守卫范围是**函数级**而非整文件 —— `rfc_extractor` 是协议相关模块
      （天然含协议名），G2 约束的是「**闸的判据**不得硬编码协议特例」。
    """
    import inspect
    code = "\n".join(inspect.getsource(f) for f in (
        RX._transition_quality_gate, RX._rfc_source_methods))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for name in ("rtsp", "sip", "smtp", "INVITE", "RCPT", "SETUP"):
        assert not re.search(rf"\b{re.escape(name)}\b", code), (
            f"质量闸出现了协议/方法特例「{name}」⇒ 违反 G2")


def test_rfc_source_methods_is_config_driven():
    """★ 方法集必须**由 rfc_config 驱动**（换协议只改配置，不改代码）。"""
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")
    cfg = RX._load_rfc_config("rtsp")
    assert cfg.get("method_sections"), "rtsp 配置未声明 method_sections"
    ms = RX._rfc_source_methods("rtsp", cfg)
    # 方法章节里声明的方法必须在集合内
    for name in ("SETUP", "PLAY", "PAUSE", "TEARDOWN"):
        assert name in ms, f"{name} 应在 RFC 源方法集内，实得 {sorted(ms)[:20]}"
    # ★ 非方法章节的标题词**不得**混入（method_sections 是白名单）
    assert "SUCCESS" not in ms, "非方法章节的词混进了方法集"
    # 配置为空 ⇒ 方法集为空（不猜、不硬编码）
    assert RX._rfc_source_methods("rtsp", {"method_sections": []}) == set()


# ===========================================================================
# ③ 真实协议回归（若底料与配置齐备）
# ===========================================================================

def test_real_protocol_gate_behaviour():
    """★ 真实回归：rtsp 的转移应**全部放行**（状态名纯 + method 是真方法）。"""
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")
    cfg = RX._load_rfc_config("rtsp")
    text = RX._rfc_full_text("rtsp")
    rows = [{"from": "Init", "method": "SETUP", "to": "Ready"},
            {"from": "Init", "method": "PLAY", "to": "Playing"},
            {"from": "Init", "method": "1xx", "to": "Ready"}]
    kept, stat = RX._transition_quality_gate(rows, "rtsp", cfg, text)
    assert len(kept) == 2, f"应放行 2 条（真方法），实得 {kept}"
    assert stat["dropped_method_not_a_method"] == 1


def test_gate_audit_file_written():
    """★ 闸的统计必须落盘（论文可审计）。"""
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")
    RX._apply_transition_gate(
        [{"from": "Init", "method": "SETUP", "to": "Ready"}], "rtsp")
    f = paths.per_source_root("rtsp") / "transition_quality_gate.json"
    assert f.is_file(), "闸统计未落盘"
    stat = json.loads(f.read_text(encoding="utf-8"))
    assert {"total", "kept", "dropped_state_not_in_rfc",
            "dropped_method_not_a_method"} <= set(stat)
