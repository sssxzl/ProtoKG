# -*- coding: utf-8 -*-
"""★ N1-R：★ 人工标注汇总脚本的**单元测试**（★ 用**模拟标签**验证逻辑）。

★ ★ 模拟标签仅用于**测试脚本**，★ **不是**人工标注，★ 不得当作质量结论。
"""
from __future__ import annotations

import csv
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
_SCRIPT = DELIV / "n1_汇总脚本.py"

_spec = importlib.util.spec_from_file_location("n1_summary", _SCRIPT)
n1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(n1)


def _rows(n=4, grp="R", labeled=True):
    _out = []
    for i in range(n):
        _r = {
            "sample_id": f"doc@1#{i}", "分组": grp, "chunk_id": "doc@1",
            "★ 绝对锚点行": str(10 + i),
            "★ 锚点行原文": "The server MUST include a list.",
            "★ RFC 原文上下文（锚点 ±6 行）": f"{10+i}: The server MUST include.",
            "★ A:subject": "server",
            "★ A:action": "include",
            "★ A:object": "a list",
            "★ A:strength": "MUST",
            "★ A:polarity": "positive",
            "★ A:condition": "null",
            "★ A:exception": "null",
            "★ A:evidence_support": "supported",
            "★ A:final_label": "valid_confirmed" if labeled else "",
            "★ B:final_label": "valid_confirmed" if labeled else "",
        }
        _out.append(_r)
    return _out


def _write(tmp_path, rows, name="a.csv"):
    _p = tmp_path / name
    with _p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return str(_p)


# ══ ① 输入检查 ══
def test_duplicate_sample_id_detected(tmp_path):
    _rs = _rows(2)
    _rs[1]["sample_id"] = _rs[0]["sample_id"]
    _errs = n1.check_inputs(_rs)
    assert any("重复 sample_id" in e for e in _errs)


def test_missing_source_detected(tmp_path):
    _rs = _rows(2)
    _rs[0]["★ RFC 原文上下文（锚点 ±6 行）"] = ""
    _errs = n1.check_inputs(_rs)
    assert any("缺少 RFC 原文上下文" in e for e in _errs)


def test_missing_chunk_id_detected(tmp_path):
    _rs = _rows(2)
    _rs[0]["chunk_id"] = ""
    _errs = n1.check_inputs(_rs)
    assert any("缺少 chunk_id" in e for e in _errs)


def test_valid_input_passes(tmp_path):
    assert n1.check_inputs(_rows(3)) == []


# ══ ② 标签枚举 ══
def test_illegal_label_detected():
    _rs = _rows(2)
    _rs[0]["★ A:final_label"] = "totally_valid_looking"
    _errs, _lab = n1.check_labels(_rs, "A")
    assert any("非法 final_label" in e for e in _errs)


def test_illegal_evidence_support_detected():
    _rs = _rows(2)
    _rs[0]["★ A:evidence_support"] = "maybe"
    _errs, _lab = n1.check_labels(_rs, "A")
    assert any("非法 evidence_support" in e for e in _errs)


# ══ ③ 未标注 ⇒ N/A（★ 绝不返回 0%）══
def test_unlabeled_returns_na_not_zero():
    _rs = _rows(3, labeled=False)
    _st = n1.group_stats(_rs, "A")
    assert _st["★ 已标注"] == 0
    assert _st["★ confirmed 精确率"] == "N/A"
    assert _st["★ 误拒收率"] == "N/A"
    assert _st["★ 完整度"] == 0.0     # ★ 完整度本身是 0（★ 分母非零）


def test_empty_group_returns_na():
    _st = n1.group_stats([], "A")
    assert _st["★ confirmed 精确率"] == "N/A"
    assert _st["★ 误拒收率"] == "N/A"


# ══ ⑤ confirmed 精确率与误拒收 ══
def test_confirmed_precision_and_false_rejection():
    _rs = _rows(4)
    _rs[0]["★ A:final_label"] = "valid_confirmed"
    _rs[1]["★ A:final_label"] = "false_confirmation"
    _rs[2]["★ A:final_label"] = "valid_rejection"
    _rs[3]["★ A:final_label"] = "false_rejection"
    _st = n1.group_stats(_rs, "A")
    # ★ confirmed 分母 = valid + false = 2；★ 正确 = 1 ⇒ 0.5
    assert _st["★ confirmed 精度分母"] == 2
    assert _st["★ confirmed 精确率"] == 0.5
    # ★ rejected 分母 = valid + false = 2；★ 误拒 = 1 ⇒ 0.5
    assert _st["★ 误拒收分母"] == 2
    assert _st["★ 误拒收率"] == 0.5


# ══ ④ 合法缺省字段 ══
def test_null_condition_counted_as_legal_default():
    _rs = _rows(2)
    _rs[0]["★ A:condition"] = "null"
    _rs[1]["★ A:condition"] = "when the flag is set"
    _fs = n1.field_support(_rs, "A")["condition"]
    assert _fs["★ 已填写"] == 2
    assert _fs["★ 非缺省"] == 1
    assert _fs["★ 缺省率"] == 0.5
    assert _fs["★ 合法缺省字段"] is True


def test_exception_is_legal_default_field():
    assert n1.field_support(_rows(1), "A")["exception"]["★ 合法缺省字段"] is True


# ══ ⑥ 双审一致性 ══
def test_dual_reviewer_agreement(tmp_path):
    _a = _rows(4)
    _b = _rows(4)
    _b[0]["★ B:final_label"] = "false_rejection"     # ★ 制造 1 处分歧
    _pa = _write(tmp_path, _a, "a.csv")
    _pb = _write(tmp_path, _b, "b.csv")
    _out = n1.main(_pa, _pb)
    _d = _out["★ 双审一致性"]
    assert _d["★ 分歧"] == 1
    assert _d["★ 一致"] == 3
    assert _d["★ 一致率"] == 0.75
    assert len(_d["★ 分歧样本"]) == 1


# ══ ⑦ R/K 分组独立 ══
def test_r_k_groups_separate_denominators(tmp_path):
    _a = _rows(2, grp="R") + _rows(3, grp="K")
    _pa = _write(tmp_path, _a)
    _out = n1.main(_pa)
    _g = _out["★ 分组汇总(A)"]
    assert _g["R（★ 分层随机）"]["★ 样本数"] == 2
    assert _g["K（★ 风险富集）"]["★ 样本数"] == 3
    assert _g["R（★ 分层随机）"]["★ 已标注"] == 2
    assert _g["K（★ 风险富集）"]["★ 已标注"] == 3


# ══ ⑨ 可复算 ══
def test_results_recomputable(tmp_path):
    _a = _rows(3)
    _pa = _write(tmp_path, _a)
    _o1 = n1.main(_pa)
    _o2 = n1.main(_pa)
    assert _o1["★ 分组汇总(A)"] == _o2["★ 分组汇总(A)"]


# ══ 交付物存在性 ══
@pytest.mark.parametrize("name", ["N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv",
                                  "N1_盲审标注表.md", "N1_审核说明.md",
                                  "N1_仲裁表.csv", "n1_汇总脚本.py"])
def test_deliverable_exists(name):
    assert (DELIV / name).is_file(), name


def test_delivered_csv_has_complete_evidence():
    _rows_ = list(csv.DictReader((DELIV / "N1_盲审标注表_A.csv")
                                 .open(encoding="utf-8-sig")))
    assert len(_rows_) == 50
    for _r in _rows_:
        assert _r["★ RFC 原文上下文（锚点 ±6 行）"].strip(), _r["sample_id"]
        assert _r["chunk_id"].strip(), _r["sample_id"]
        assert _r["★ 绝对锚点行"].strip(), _r["sample_id"]
        assert _r["★ 原始 source_span"].strip(), _r["sample_id"]


def test_blind_audit_files_have_no_model_state_leak():
    for _name in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv"):
        _rows_ = list(csv.DictReader((DELIV / _name).open(encoding="utf-8-sig")))
        for _r in _rows_:
            for _k in _r:
                assert not any(_w in _k for _w in ("L2", "final_state", "verdict")), _k


def test_dual_reviewers_have_full_label_columns():
    _rows_a = list(csv.DictReader((DELIV / "N1_盲审标注表_A.csv")
                                  .open(encoding="utf-8-sig")))
    _rows_b = list(csv.DictReader((DELIV / "N1_盲审标注表_B.csv")
                                  .open(encoding="utf-8-sig")))
    for _r in _rows_a:
        for _f in ("subject", "action", "object", "strength", "polarity",
                   "condition", "exception", "evidence_support", "final_label"):
            assert f"★ A:{_f}" in _r
    for _r in _rows_b:
        for _f in ("subject", "action", "object", "strength", "polarity",
                   "condition", "exception", "evidence_support", "final_label"):
            assert f"★ B:{_f}" in _r
