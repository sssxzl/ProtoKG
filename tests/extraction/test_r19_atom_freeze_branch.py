# -*- coding: utf-8 -*-
"""V2-E4-R19 回归测试：原子 Gold v5 冻结与 V2-next 关键分支测试。

覆盖：门禁 10/10、冻结基线生成、字段变更记录、互斥口径登记、
      关键分支未覆盖如实报告、V2-next 未被修改、历史版本未覆盖、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r19"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R19_原子Goldv5冻结与独立验证门禁准备")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R13D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核")
R17D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R17_V2next定版核验与原子Gold字段回收")
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")
V2NEXT = ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py"

FZ = json.loads((OUTD / "r19_freeze.json").read_text(encoding="utf-8"))
BT = json.loads((OUTD / "r19_branch_tests.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 冻结门禁 =====
def test_gate_all_ten_passed():
    assert FZ["all_pass"] is True
    assert sum(1 for c in FZ["gate"] if c["结果"] == "通过") == 10


def test_frozen_baseline_generated_with_6_records():
    _rows = _jl(DELIV / "R19_原子Gold_v5冻结基线.jsonl")
    assert len(_rows) == 6
    assert len({r["gold_id"] for r in _rows}) == 6
    assert FZ["frozen_sha256"] == hashlib.sha256(
        (DELIV / "R19_原子Gold_v5冻结基线.jsonl").read_bytes()).hexdigest()


def test_single_field_change_recorded_with_old_values():
    assert len(FZ["changes"]) == 1
    _c = FZ["changes"][0]
    assert _c["gold_id"] == "RTSP-ATOM-X-rtsp-rfc7826-05-1"
    assert _c["★ 原 strength"] == "unknown"
    assert _c["★ 新 strength"] == "not_applicable"
    assert _c["★ 原 polarity"] == "positive"
    assert _c["★ 新 polarity"] == "not_applicable"
    assert _c["★ 审核者"] == "D"


def test_no_automatic_replacement_claim():
    """★ 不得自动替换 unknown/positive ⇒ 原值须保留在记录中。"""
    _t = (DELIV / "R19_原子Gold_v5人工回填与冻结验收报告.md").read_text(
        encoding="utf-8")
    assert "未自动替换" in _t


def test_exclusive_caliber_registered():
    _t = (DELIV / "R19_原子Gold_v5人工回填与冻结验收报告.md").read_text(
        encoding="utf-8")
    assert "互斥口径" in _t
    assert "须另立新版本" in _t
    assert len(FZ["exclusive"]) == 1


def test_enum_and_source_checks_clean():
    assert FZ["enum_issues"] == []


# ===== 关键分支测试 =====
def test_branch_tests_reported_as_not_covered():
    """★ 未覆盖须如实报告，★ 不得判定修复通过。"""
    _t = (DELIV / "R19_V2next关键分支合成测试报告.md").read_text(
        encoding="utf-8")
    assert "未覆盖" in _t
    assert "不能据此判定修复有效" in _t
    assert BT["triggered"] == 0
    assert BT["diff"] == 0
    assert BT["not_covered"] == len(BT["rows"])


def test_branch_tests_have_required_columns():
    for _r in BT["rows"]:
        assert _r["★ 预期输出"]
        assert _r["★ 原 V2 输出"]
        assert _r["★ V2-next 输出"]
        assert _r["★ 命中分支详情"]["★ 判定条件"]
        assert _r["★ 覆盖判定"]


def test_v2next_not_modified_by_this_round():
    _h = hashlib.sha256(V2NEXT.read_bytes()).hexdigest()
    assert _h == BT["v2_next_sha256"]
    assert _h == "cc2a9b822e8f3f0c7a457296bb3efee85de2f89a8c4fe886cac05d1a4aedf22f"


def test_production_v2_unchanged():
    assert hashlib.sha256(V2GATE.read_bytes()).hexdigest() == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")


# ===== 预注册与预算 =====
def test_prereg_isolation_discipline():
    _t = (DELIV / "R19_新RFC独立验证最终预注册草案.md").read_text(
        encoding="utf-8")
    assert "不得用新 Gold 调整模型后" in _t
    assert "事前" in _t
    assert "18→21 条正确" in _t


def test_prereg_discloses_known_limitations():
    _t = (DELIV / "R19_新RFC独立验证最终预注册草案.md").read_text(
        encoding="utf-8")
    assert "不可观察" in _t
    assert "空操作" in _t


def test_budget_gate_lists_ten_items_and_zero_llm():
    _t = (DELIV / "R19_独立验证预算与执行前门禁.md").read_text(encoding="utf-8")
    assert "本轮实际调用" in _t
    assert "0 次" in _t
    assert "费用上限" in _t
    assert "当前不可启动独立评估" in _t


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
        (R13D / "R13_候选级评估冻结基线.jsonl").read_bytes()
    ).hexdigest() == (
        "36742b0955339edb4a1d08ef936bf1270e5c70262ea37180f5a11ff9cc960f0b")
    assert hashlib.sha256(
        (R17D / "R17_原子Gold新候选基线.jsonl").read_bytes()
    ).hexdigest() == (
        "49b138759a144aed77ac9a1fc76d964d4c238be97b64982b1fa3429e2284a2bb")


def test_r3_and_r14_untouched():
    assert hashlib.sha256(
        (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl")
        .read_bytes()).hexdigest() == (
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a")
    for _n in ("R14_候选级分类评估结果.xlsx",
               "R14_评估执行日志与环境哈希.md"):
        assert (ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R14_候选级分类一次性评估" / _n).is_file(), _n


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R19_原子Gold_v5人工回填与冻结验收报告.md",
               "R19_原子Gold_v5冻结基线.jsonl",
               "R19_V2next关键分支合成测试报告.md",
               "R19_新RFC独立验证最终预注册草案.md",
               "R19_独立验证预算与执行前门禁.md",
               "R19_版本哈希与回归测试报告.md"):
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


def test_no_llm_calls_in_r19():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r19").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
