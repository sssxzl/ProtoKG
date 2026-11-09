# -*- coding: utf-8 -*-
"""tests/fused/test_m1_sensitivity.py —— M1 敏感性分析脚本的守卫（批次 4 / C1）。

★ 为什么有这个文件（2026-11-07）：
  M1 的敏感性分析原本只存在于一次**临时口径审计**里（未固化）⇒ 不可复现、
  写进论文会被要求给出可复现的敏感性分析。本文件把该审计固化为脚本
  （`tools/qa/_m1_sensitivity.py`）并锁住它的**关键结论**与**口径判据**。

★ 锁四件事：
  ① **存在类算子不得被排除**（present/absent 语义上无值域 ⇒ 免操作数）
     —— 排除它们会让 C0 被系统性低估，制造「E1 +10.83pp」的**口径假象**；
  ② 四档口径的**实测锚点**（防止数据或判据被改动而无人察觉）；
  ③ **M2 不可计算**必须如实标注（不臆造 F1 / κ）；
  ④ 人工标注上界 26.7% 只能**引用**、不得改写。
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "qa" / "_m1_sensitivity.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("_m1_sensitivity", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_mod()


@pytest.fixture(scope="module")
def report():
    """跑一次脚本，拿到 JSON 结果（脚本会写 derived/experiments/semantic_gain/m1_sensitivity.json）。"""
    m = _load_mod()
    assert m.main() == 0
    p = ROOT / "derived" / "experiments" / "semantic_gain" / "m1_sensitivity.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ===========================================================================
# ① 存在类算子免操作数（关键修正）
# ===========================================================================

def test_presence_operators_defined(mod):
    assert mod.PRESENCE_OPERATORS == {"present", "absent"}


def test_c0_executable_counts_presence_operators(mod):
    """★ 存在类算子即使没有 operand，也算「可执行」。"""
    item = {"decidable": True, "operator": "present", "operand": []}
    assert mod._c0_executable(item) is True
    item2 = {"decidable": True, "operator": "absent", "operand": []}
    assert mod._c0_executable(item2) is True


def test_c0_executable_requires_operand_for_non_presence(mod):
    """非存在类算子没有 operand ⇒ 不算可执行。"""
    item = {"decidable": True, "operator": "eq", "operand": []}
    assert mod._c0_executable(item) is False
    item2 = {"decidable": True, "operator": "eq", "operand": ["7"]}
    assert mod._c0_executable(item2) is True


def test_c0_executable_requires_decidable(mod):
    """没解析出算子 ⇒ 不算。"""
    assert mod._c0_executable({"decidable": False, "operator": "eq",
                               "operand": ["7"]}) is False


def test_existence_operators_do_not_shrink_c0(mod):
    """★ 核心守卫：存在类算子不得让 C0 的计数变小。

    （这是造成「带操作数口径 +10.83pp vs 主口径 −3.33pp 方向相反」的根因。）
    """
    c0 = mod.load_c0()
    legacy = sum(1 for i in c0 if i.get("decidable_with_operand"))
    corrected = sum(1 for i in c0 if mod._c0_executable(i))
    assert corrected > legacy, "存在类算子被排除了 ⇒ C0 被系统性低估"
    # 差额应恰为「可判定但无 operand 且是存在类算子」的条数
    presence = sum(1 for i in c0
                   if i.get("decidable")
                   and not i.get("decidable_with_operand")
                   and str(i.get("operator") or "") in mod.PRESENCE_OPERATORS)
    assert corrected - legacy == presence


# ===========================================================================
# ② 四档口径的实测锚点
# ===========================================================================

def test_main_口径_anchor(report):
    """主口径：E1−C0 = −3.33pp（不成立档）。"""
    t = report["main_total"]
    assert t["c0_decidable"] == 24
    assert t["e1_rules"] == 20
    assert t["denominator"] if "denominator" in t else report["denominator"]["candidates"] == 120
    assert abs(t["delta_pp"] - (-3.3333)) < 0.01, t
    assert t["verdict"] == "不成立"


def test_equal_strictness_anchor(report):
    """同等严格度：也是 −3.33pp（E1 规则全部 validated + 字段已绑定）。"""
    t = report["equal_strictness_total"]
    assert t["c0"] == 24
    assert t["e1_strict"] == 20
    assert abs(t["delta_pp"] - (-3.3333)) < 0.01, t


def test_value_domain_口径_anchor(report):
    """★ 值域口径：只有 6 条真带值域 ⇒ M1 的**含金量**远低于条数。"""
    t = report["value_domain_only_total"]
    assert t["e1"] == 6
    assert t["c0"] == 7
    assert abs(t["delta_pp"] - (-0.8333)) < 0.01, t


def test_protocol_breakdown(report):
    """逐协议：rtsp −10 / sip +5 / smtp −5（反号 ⇒ 不能只看合计）。"""
    bp = report["by_protocol"]
    assert abs(bp["rtsp"]["main"]["delta_pp"] - (-10.0)) < 0.01
    assert abs(bp["sip"]["main"]["delta_pp"] - 5.0) < 0.01
    assert abs(bp["smtp"]["main"]["delta_pp"] - (-5.0)) < 0.01


def test_e1_rule_composition(report):
    """★ E1 的 20 条里 14 条是存在类算子 ⇒ 条数高估「可执行约束」的实质数量。"""
    c = report["e1_rule_composition"]
    assert c["total"] == 20
    assert c["presence_operators"] == 14
    assert c["value_domain_operators"] == 6


def test_attribution_buckets(report):
    """逐候选归因：c0_only 17 条 = 「C0 能判、E1 拒」= 两把尺子的差来源。"""
    b = report["attribution"]["buckets"]
    assert b["c0_only"] == 17
    assert b["e1_only"] == 13
    assert b["both"] == 7
    assert sum(b.values()) == 120


# ===========================================================================
# ③ M2 不可计算 + 阈值可达性
# ===========================================================================

def test_m2_is_marked_not_computable(report):
    """★ M2 的 F1 / κ **不可计算** —— 必须如实标注，不得臆造。"""
    assert report["m2"]["computable"] is False
    assert "不可计算" in report["m2"]["reason"]


def test_threshold_is_unreachable(report):
    """★ 预登记 +15pp 在当前候选池上数学上不可达（人工上界 26.7% < 需 35%）。"""
    tf = report["threshold_feasibility"]
    assert tf["reachable"] is False
    assert tf["required_rate_pct"] == 35.0
    assert tf["required_rules"] == 42
    assert tf["annotation_upper_bound_pct"] == 26.6667


def test_annotation_upper_bound_is_quoted_not_rewritten(report):
    """人工上界只能**引用**（26.7% = 32/120），不得改写。"""
    ub = report["annotation_upper_bound"]
    assert ub["total"] == 32
    assert ub["denominator"] == 120
    assert abs(ub["pct"] - 26.6667) < 0.01


def test_verdict_thresholds_match_prereg(mod, report):
    """档位判定必须用**预登记**阈值（不新建口径）。"""
    assert mod.PREREG == {"成立": 15.0, "部分成立": 5.0}
    assert mod._verdict(20.0) == "成立"
    assert mod._verdict(15.0) == "成立"
    assert mod._verdict(10.0) == "部分成立"
    assert mod._verdict(5.0) == "部分成立"
    assert mod._verdict(4.9) == "不成立"
    assert mod._verdict(-3.33) == "不成立"


# ===========================================================================
# ④ 脚本可复现（同输入 ⇒ 同输出）
# ===========================================================================

def test_script_is_deterministic(report):
    """同输入两次跑 ⇒ 结果 JSON 相同（可复现）。"""
    m = _load_mod()
    assert m.main() == 0
    p = ROOT / "derived" / "experiments" / "semantic_gain" / "m1_sensitivity.json"
    again = json.loads(p.read_text(encoding="utf-8"))
    for key in ("main_total", "equal_strictness_total",
                "value_domain_only_total", "e1_rule_composition"):
        assert json.dumps(report[key], sort_keys=True) == \
            json.dumps(again[key], sort_keys=True), key


def test_denominator_is_shared_frozen_candidates(report):
    """分母必须是三组共用的**冻结候选句** 120 条。"""
    assert report["denominator"]["candidates"] == 120
    assert "candidates_frozen" in report["denominator"]["note"]
