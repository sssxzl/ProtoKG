# -*- coding: utf-8 -*-
"""V2-E4-R15 回归测试：V2 分类错误归因与原子知识 Gold 规范化。

覆盖：归因覆盖 57 条与 39 条错误候选、错误计数 106 与 39 的区分、
      mixed 专项、R14 首次结果未改、原子 Gold 新版本与映射、历史版本未覆盖、
      生产隔离。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r15"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R15_V2分类归因与原子Gold规范化")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R13D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核")
R14D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R14_候选级分类一次性评估")
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")

ATT = json.loads((OUTD / "r15_attribution.json").read_text(encoding="utf-8"))
INP = json.loads((OUTD / "r15_inputs.json").read_text(encoding="utf-8"))
ATOM = json.loads((OUTD / "r15_atom_gold.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 工作线 A：归因 =====
def test_ledger_covers_all_57():
    assert len(INP["ledger"]) == 57


def test_39_error_candidates_and_106_error_records():
    _err = [r for r in INP["ledger"]
            if not (r["kind_match"] and r["elig_match"] and r["route_match"])]
    assert len(_err) == 39
    _kg = sum(1 for r in INP["ledger"] if not r["kind_match"])
    _eg = sum(1 for r in INP["ledger"] if not r["elig_match"])
    _rg = sum(1 for r in INP["ledger"] if not r["route_match"])
    assert (_kg, _eg, _rg) == (39, 28, 39)
    assert _kg + _eg + _rg == 106


def test_every_error_row_has_attribution():
    for _r in ATT["rows"]:
        if _r["★ 错误分类"] == "★ 正确":
            continue
        assert _r["★ 错误分类"], _r["candidate_id"]
        assert _r["★ 归因理由"], _r["candidate_id"]
        assert _r["★ 归因确定程度"] in ("确定", "待定"), _r["candidate_id"]


def test_attribution_covers_all_error_classes():
    _c = ATT["class_counts"]
    assert sum(_c.values()) == 39
    for _k in _c:
        assert _k[0] in "ABCDEFGH", _k


def test_mixed_special_analysis_covers_all_mixed():
    _mix = [r for r in INP["ledger"] if r["pred_kind"] == "mixed_or_uncertain"]
    assert len(_mix) == 15
    _t = (DELIV / "R15_mixed_or_uncertain专项分析.md").read_text(encoding="utf-8")
    for _r in _mix:
        assert _r["candidate_id"] in _t, _r["candidate_id"]


def test_kind_and_route_accuracy_identical():
    _r = {x[0]: x for x in INP["protocol_rows"]}
    for _p in ("SIP", "RTSP", "SMTP"):
        assert _r[_p][5] == _r[_p][9], _p


def test_r14_first_result_unchanged():
    """★ R14 首次评估结果不得被覆盖或修改。"""
    _t = (DELIV / "R15_知识类型资格路由联动错误报告.md").read_text(
        encoding="utf-8")
    assert "39" in _t and "28" in _t and "106" in _t
    assert "不是 106 条独立候选" in _t
    # ★ R14 的交付物未被本轮改动
    for _n in ("R14_候选级分类评估结果.xlsx",
               "R14_分协议混淆矩阵与错误明细.xlsx",
               "R14_评估执行日志与环境哈希.md",
               "R14_一次性事后评估限制说明.md"):
        assert (R14D / _n).is_file(), _n


def test_improvement_plan_does_not_modify_v2():
    _t = (DELIV / "R15_V2最小兼容改进方案.md").read_text(encoding="utf-8")
    assert "不修改冻结 V2 判据" in _t
    assert "V2-next" in _t
    assert "未修改" in _t
    _v = (DELIV / "R15_新协议独立验证设计.md").read_text(encoding="utf-8")
    assert "独立泛化测试集" in _v
    # ★ V2 判据哈希未变
    assert hashlib.sha256(V2GATE.read_bytes()).hexdigest() == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")


# ===== 工作线 B：原子 Gold =====
def test_review_received_8_rows():
    assert len(ATOM["review_checks"]) == 8
    assert len(INP["review_rows"]) == 8


def test_reviewer_is_distinct_from_a_b_c_f():
    """★ 审核者须为 D，★ 与 A/B/C/F 均不同。"""
    assert ATOM["who"] == ["D"]


def test_two_records_judged_not_independent():
    _ind = {r["id"]: r["ind"] for r in INP["review_rows"]}
    _no = [k for k, v in _ind.items() if v.startswith("否")]
    assert len(_no) == 2
    assert set(_no) == {"SMTP-ATOM-X-smtp-rfc3461-04-b",
                        "SMTP-ATOM-X-smtp-rfc6531-01-b"}


def test_new_atom_gold_has_6_records():
    _rows = _jl(DELIV / "R15_原子知识Gold新版本候选.jsonl")
    assert len(_rows) == 6
    assert all(r["gold_level"] == "atom" for r in _rows)


def test_new_atom_gold_only_candidate_level_independent():
    """★ 候选级 57 条保持独立冻结，★ 原子文件不含候选级。"""
    _rows = _jl(DELIV / "R15_原子知识Gold新版本候选.jsonl")
    assert not any(r["gold_level"] == "candidate" for r in _rows)
    _frozen = _jl(R13D / "R13_候选级评估冻结基线.jsonl")
    assert len(_frozen) == 57


def test_old_to_new_id_mapping_present():
    _map = ATOM["map"]
    assert len(_map) == 6
    for _m in _map:
        assert _m["旧 Gold ID"] and _m["新 Gold ID"]


def test_atom_gold_has_human_source():
    for _r in _jl(DELIV / "R15_原子知识Gold新版本候选.jsonl"):
        assert _r.get("★ 人工来源"), _r["gold_id"]
        assert _r.get("★ 仲裁者"), _r["gold_id"]
        assert _r.get("★ 人工复核理由"), _r["gold_id"]


def test_two_records_missing_evidence_are_declared():
    """★ 两条记录的原文证据在 R13 表中为空，★ 须在未决项中声明。"""
    _rows = _jl(DELIV / "R15_原子知识Gold新版本候选.jsonl")
    _missing = [r["gold_id"] for r in _rows
                 if not str(r.get("★ 人工复核原文", "")).strip()]
    assert len(_missing) == 2, _missing
    assert set(_missing) == {"SMTP-ATOM-X-smtp-rfc3461-04-a",
                             "SMTP-ATOM-X-smtp-rfc6531-01-a"}
    _gate = (DELIV / "R15_原子知识Gold冻结门禁报告.md").read_text(
        encoding="utf-8")
    assert "原文证据" in _gate


def test_agent_did_not_invent_subject_action_object():
    """★ 未经人工确认的主体/动作/对象不得被 Agent 创造。"""
    for _r in _jl(DELIV / "R15_原子知识Gold新版本候选.jsonl"):
        _f = _r.get("★ 结构化字段", {})
        assert "★ 主体/动作/对象" in _f, _r["gold_id"]


# ===== 版本保护 =====
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


def test_r3_machine_candidates_unchanged():
    assert hashlib.sha256(
        (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl")
        .read_bytes()).hexdigest() == (
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a")


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R15_57条候选分类错误归因.xlsx",
               "R15_mixed_or_uncertain专项分析.md",
               "R15_知识类型资格路由联动错误报告.md",
               "R15_输入字段与Gold契约一致性检查.md",
               "R15_V2最小兼容改进方案.md",
               "R15_新协议独立验证设计.md",
               "R15_R13人工复核结果接收核验.xlsx",
               "R15_原子知识Gold新版本候选.jsonl",
               "R15_原子知识Gold版本差异与人工来源.xlsx",
               "R15_原子知识Gold冻结门禁报告.md"):
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


def test_no_llm_calls_in_r15():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r15").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
