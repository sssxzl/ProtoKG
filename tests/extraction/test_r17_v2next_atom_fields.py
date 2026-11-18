# -*- coding: utf-8 -*-
"""V2-E4-R17 回归测试：V2-next 定版核验与原子 Gold 字段回收。

覆盖：V2-next 当前策略的实测结论、R15 勘误、原子 v5 字段齐备与时区、
      合成样本区分力限制、历史版本未覆盖、生产隔离。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r17"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R17_V2next定版核验与原子Gold字段回收")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R15D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R15_V2分类归因与原子Gold规范化")
R16D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R16_V2next影子验证与原子Gold补证")
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")
V2NEXT = ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py"

V = json.loads((OUTD / "r17_v2next_verify.json").read_text(encoding="utf-8"))
V5 = json.loads((OUTD / "r17_v5.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== V2-next 定版核验 =====
def test_current_shadow_measured_4_changes():
    """★ 实测变化 4 条（★ 修复 3、★ 反向 0、★ 对错不变 1）。"""
    assert V["changed_count"] == 4
    assert V["fix_count"] == 3
    assert V["break_count"] == 0


def test_three_fixes_are_downgrades():
    """★ 三条修复均为降级（★ 而非 R15 的 A 类方向）。"""
    _fix = [r for r in V["rows"] if r["★ 变化性质"] == "★ 修复"]
    assert len(_fix) == 3
    for _r in _fix:
        assert _r["★ V2 预测 kind"] == "normative_rule_candidate"
        assert _r["★ V2-next 预测 kind"] == "protocol_descriptive_semantics"


def test_no_reverse_misjudgment():
    _brk = [r for r in V["rows"] if r["★ 变化性质"] == "★★ 反向误判"]
    assert _brk == [], _brk


def test_production_v2_unchanged():
    assert hashlib.sha256(V2GATE.read_bytes()).hexdigest() == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")
    assert V["orig_sha256"] == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")


def test_synthetic_zero_change_explained():
    """★ 合成样本 0 变化的原因已写入报告。"""
    _t = (DELIV / "R17_V2next当前策略与四策略差异报告.md").read_text(
        encoding="utf-8")
    assert "区分力不足" in _t
    assert "全部不触发" in _t


def test_report_declares_not_generalization():
    _t = (DELIV / "R17_V2next影子候选冻结与哈希报告.md").read_text(
        encoding="utf-8")
    assert "不得称为独立泛化提升" in _t
    assert "未通过" in _t


# ===== R15 勘误 =====
def test_r15_erratum_distinguishes_five_categories():
    _t = (DELIV / "R17_R15错误归因勘误.md").read_text(encoding="utf-8")
    assert "关键词确实存在但未识别" in _t
    assert "关键词已识别却阻断跨句复核" in _t
    assert "原文本来没有显式关键词" in _t
    assert "Gold 与 V2 分类定义存在分歧" in _t
    assert "其他或 unresolved" in _t


def test_r15_erratum_keeps_counts():
    _t = (DELIV / "R17_R15错误归因勘误.md").read_text(encoding="utf-8")
    assert "39 条错误候选" in _t
    assert "106 条跨指标错误记录" in _t
    assert "不覆盖 R15 原始报告" in _t


# ===== 原子 Gold 字段回收 =====
def test_six_records_filled_with_fields():
    _rows = _jl(DELIV / "R17_原子Gold新候选基线.jsonl")
    assert len(_rows) == 6
    for _r in _rows:
        _f = _r["★ 结构化字段"]
        assert _f.get("主体"), _r["gold_id"]
        assert _f.get("动作"), _r["gold_id"]
        assert _f.get("对象"), _r["gold_id"]
        assert _r["★ 未决字段"] == [], _r["gold_id"]


def test_one_record_not_applicable():
    _rows = {r["gold_id"]: r for r in
             _jl(DELIV / "R17_原子Gold新候选基线.jsonl")}
    _f = _rows["RTSP-ATOM-X-rtsp-rfc7826-05-1"]["★ 结构化字段"]
    assert _f["主体"] == "not_applicable"
    assert _f["动作"] == "not_applicable"
    assert _f["对象"] == "not_applicable"


def test_timezone_present():
    _rows = _jl(DELIV / "R17_原子Gold新候选基线.jsonl")
    for _r in _rows:
        _d = str(_r.get("★ 字段确认来源", ""))
        assert "UTC" in _d or "Asia" in _d, _r["gold_id"]
        assert "D" in _d, _r["gold_id"]


def test_field_source_traced():
    for _r in _jl(DELIV / "R17_原子Gold新候选基线.jsonl"):
        assert _r.get("★ 字段确认来源"), _r["gold_id"]
        assert _r.get("★ 字段确认依据"), _r["gold_id"]


def test_deterministic_evidence_still_marked_as_source_link():
    """★ 两条确定性补全的证据位置不得伪装为新人工裁定。"""
    _t = (DELIV / "R17_原子Gold人工字段回收状态.md").read_text(encoding="utf-8")
    assert "非新人工裁定" in _t
    assert "来源关联" in _t


def test_field_gate_all_passed():
    _t = (DELIV / "R17_原子Gold人工字段回收状态.md").read_text(encoding="utf-8")
    assert "字段级门禁已满足" in _t
    assert "待申请" in _t


# ===== 历史版本保护 =====
def test_all_historical_versions_unchanged():
    _h = {
        "R10_跨协议Gold冻结基线.jsonl":
            "bbce8979138605160f9af1c1c72a8c6c3b4750f31f808e9f03e2548f4b2a57eb",
        "R11_跨协议Gold冻结基线_v2候选.jsonl":
            "0f9ab8350da73359153473aeb9428001f45441828482583a1d0fed8f4f6cc38b",
        "R12_跨协议Gold冻结基线_v3候选.jsonl":
            "eb66b74533c93b931e58db73cf4b2c36268f6e2fd885042bcb9ee1cc3f4ea570",
    }
    for _n, _e in _h.items():
        assert hashlib.sha256((R10D / _n).read_bytes()).hexdigest() == _e, _n
    assert hashlib.sha256(
        (R15D / "R15_原子知识Gold新版本候选.jsonl").read_bytes()
    ).hexdigest() == (
        "97d8986a7846380491478a8bd42bb73df149f6307cb6fe92addfce29ff399bc4")


def test_r3_and_r14_untouched():
    assert hashlib.sha256(
        (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl")
        .read_bytes()).hexdigest() == (
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a")
    for _n in ("R14_候选级分类评估结果.xlsx",
               "R14_评估执行日志与环境哈希.md"):
        assert (ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R14_候选级分类一次性评估" / _n).is_file(), _n


def test_candidate_level_gold_untouched():
    assert hashlib.sha256(
        (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核"
         / "R13_候选级评估冻结基线.jsonl").read_bytes()
    ).hexdigest() == (
        "36742b0955339edb4a1d08ef936bf1270e5c70262ea37180f5a11ff9cc960f0b")


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R17_V2next当前策略与四策略差异报告.md",
               "R17_3条修复与反向误判核验.xlsx",
               "R17_R15错误归因勘误.md",
               "R17_V2next影子候选冻结与哈希报告.md",
               "R17_原子Gold人工字段回收状态.md",
               "R17_版本保护与回归测试报告.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


# ===== 生产隔离 =====
def test_production_unchanged():
    import ast
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    for _n in ast.walk(ast.parse(_src)):
        if isinstance(_n, ast.Assign) and getattr(_n.targets[0], "id", "") \
                == "_PROMPT":
            assert hashlib.sha256(
                _n.value.value.encode()).hexdigest()[:16] \
                == "d97fbe611ac9aa61"
            break
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21


def test_no_llm_calls_in_r17():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r17").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
