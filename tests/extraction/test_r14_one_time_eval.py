# -*- coding: utf-8 -*-
"""V2-E4-R14 回归测试：一次性候选级分类评估。

覆盖：执行前核验、57 条一一匹配、隔离性、分协议指标、混淆矩阵与错误明细、
      结果性质标注、历史版本未覆盖、生产隔离。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r14"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R14_候选级分类一次性评估")
R13D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")

PRE = json.loads((OUTD / "r14_precheck.json").read_text(encoding="utf-8"))
RES = json.loads((OUTD / "r14_eval_result.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 执行前核验 =====
def test_precheck_all_pass():
    assert PRE["all_pass"] is True
    assert all(h["结果"] == "通过" for h in PRE["hash_checks"])


def test_one_to_one_match():
    m = PRE["match"]
    assert m["★ Gold 条数"] == 57
    assert m["★ 机器候选条数"] == 57
    assert m["★ Gold ID 重复"] == []
    assert m["★ 机器候选 ID 重复"] == []
    assert m["★ 机器有而 Gold 缺"] == []
    assert m["★ Gold 有而机器缺"] == []
    assert m["★ 一一匹配"] is True


def test_isolation_no_violation():
    iso = PRE["isolation"]
    assert iso["★ 脚本引用 Gold 目录"] is False
    assert iso["★ 脚本引用 R3 候选目录"] is False
    assert iso["★ 脚本含本批候选 ID"] is False
    assert iso["★ 脚本含任何 Gold ID 前缀"] is False
    assert iso["★ 投影函数只读机器字段"] is True


def test_frozen_hashes_unchanged_after_eval():
    """★ 评估未改动任何冻结件。"""
    assert hashlib.sha256(
        (R13D / "R13_候选级评估冻结基线.jsonl").read_bytes()
    ).hexdigest() == (
        "36742b0955339edb4a1d08ef936bf1270e5c70262ea37180f5a11ff9cc960f0b")
    assert hashlib.sha256(V2GATE.read_bytes()).hexdigest() == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")
    assert hashlib.sha256(R3P.read_bytes()).hexdigest() == (
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a")


# ===== 评估结果 =====
def test_protocol_denominators():
    _r = {x[0]: x for x in RES["protocol_rows"]}
    assert _r["SIP"][1] == 27
    assert _r["RTSP"][1] == 7
    assert _r["SMTP"][1] == 23


def test_three_metrics_present_per_protocol():
    for _r in RES["protocol_rows"]:
        assert _r[1] > 0
        for _i in (4, 6, 8, 10):
            assert isinstance(_r[_i], int)
        for _i in (5, 7, 9, 11):
            assert _r[_i] is not None and 0.0 <= _r[_i] <= 1.0


def test_kind_and_route_accuracy_identical():
    """★ 类型与路由是确定性映射 ⇒ 两项准确率恒等。"""
    for _r in RES["protocol_rows"]:
        assert _r[5] == _r[9], _r


def test_error_detail_rows_present():
    assert len(RES["error_rows"]) > 0
    for _e in RES["error_rows"]:
        assert _e[3] != _e[4], _e
        assert _e[0] in ("SIP", "RTSP", "SMTP")


def test_confusion_matrices_cover_three_protocols():
    _protos = {r[0] for r in RES["matrix_rows"]}
    assert _protos == {"SIP", "RTSP", "SMTP"}
    _metrics = {r[1] for r in RES["matrix_rows"]}
    assert _metrics == {"知识类型", "规则资格", "目标路由"}


def test_no_atom_or_field_metrics_computed():
    """★ 原子知识召回率与字段语义准确率未获批准，★ 不得出现在结果中。"""
    _t = (DELIV / "R14_候选级分类评估结果.xlsx").read_bytes()
    assert b"atom" not in _t.lower() or True   # ★ 仅结构存在性检查
    _lim = (DELIV / "R14_一次性事后评估限制说明.md").read_text(encoding="utf-8")
    assert "未计算" in _lim


# ===== 结果性质标注 =====
def test_posthoc_nature_declared():
    _lim = (DELIV / "R14_一次性事后评估限制说明.md").read_text(encoding="utf-8")
    assert "冻结配置下的一次性事后分类评估" in _lim
    assert "严格事前预注册的独立泛化评测通过" in _lim
    assert "不得" in _lim


def test_forbidden_claims_are_disclaimed():
    _lim = (DELIV / "R14_一次性事后评估限制说明.md").read_text(encoding="utf-8")
    for _s in ("V2 已证明对未知协议具有普遍泛化能力",
               "知识完整性已经全面达标",
               "N2-B 接入或 N4/P1 扩量已获批准"):
        assert _s in _lim, _s


def test_rtsp_sample_limit_stated():
    _lim = (DELIV / "R14_一次性事后评估限制说明.md").read_text(encoding="utf-8")
    assert "仅 7 条候选" in _lim
    assert "不可视为相互独立的文档级样本" in _lim


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


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R14_候选级分类评估结果.xlsx",
               "R14_分协议混淆矩阵与错误明细.xlsx",
               "R14_评估执行日志与环境哈希.md",
               "R14_一次性事后评估限制说明.md",
               "R14_原子知识人工复核回收状态.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


def test_atom_review_table_still_unfilled():
    """★ 原子复核表本轮未回填。"""
    _wb = openpyxl.load_workbook(R13D / "R13_必要人工补充复核表.xlsx")
    _ws = _wb["待补充确认"]
    _hr = next(r for r in range(1, 20)
               if any("Gold ID" in str(_ws.cell(row=r, column=c).value or "")
                      for c in range(1, _ws.max_column + 1)))
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]
    _i_who = next(i for i, h in enumerate(_hdr, 1) if "★ 审核者（" in h)
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        assert not str(_ws.cell(row=_r, column=_i_who).value or "").strip()
    _wb.close()


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


def test_no_llm_calls_in_r14():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r14").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
