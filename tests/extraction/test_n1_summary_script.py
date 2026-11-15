# -*- coding: utf-8 -*-
"""★ N1-R2：★ 盲审汇总脚本的单元测试（★ 真实空表 + 模拟标签）。

★ ★ 模拟标签仅用于**测试脚本**，★ **不是**人工标注，★ 不得当作质量结论。
"""
from __future__ import annotations

import csv
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
_SCRIPT = DELIV / "n1_汇总脚本.py"

_spec = importlib.util.spec_from_file_location("n1_summary2", _SCRIPT)
n1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(n1)


def _base_row(i=0, grp="R", truth="valid_confirmed", support="supported",
              blank_anchor=False):
    return {
        "sample_id": f"doc@1#{i}", "分组": grp, "chunk_id": "doc@1",
        "★ resolved_span": str(10 + i),
        "★ span_mode": "absolute",
        "★ 锚点行原文": "" if blank_anchor else "The server MUST include a list.",
        "★ 锚点行是否空白": "true" if blank_anchor else "false",
        "★ 证据句（含 entity 的非空行）": "12: The server MUST include a list.",
        "★ RFC 原文上下文（锚点 ±6 行）": f"{10+i}: The server MUST include.",
        "★ A:subject": "server", "★ A:action": "include",
        "★ A:object": "a list", "★ A:strength": "MUST",
        "★ A:polarity": "positive", "★ A:condition": "null",
        "★ A:exception": "null", "★ A:evidence_support": support,
        "★ A:truth_label": truth, "★ A:review_note": "★ 依据原文",
        "★ B:subject": "server", "★ B:action": "include",
        "★ B:object": "a list", "★ B:strength": "MUST",
        "★ B:polarity": "positive", "★ B:condition": "null",
        "★ B:exception": "null", "★ B:evidence_support": support,
        "★ B:truth_label": truth, "★ B:review_note": "★ 依据原文",
    }


def _write(tmp_path, rows, name="a.csv"):
    _p = tmp_path / name
    with _p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return str(_p)


def _models(rows, mapping=None):
    _out = []
    for r in rows:
        _ms = (mapping or {}).get(r["sample_id"], "confirmed")
        _out.append({"sample_id": r["sample_id"], "分组": r["分组"],
                     "★ 模型状态（★ 盲审阶段不可见）": _ms})
    return _out


# ══ ① 输入检查：区分四类 ══
def test_missing_source_is_error():
    _rs = [_base_row(0)]
    _rs[0]["★ RFC 原文上下文（锚点 ±6 行）"] = ""
    _errs, _notes = n1.check_inputs(_rs)
    assert any("原文缺失" in e for e in _errs)


def test_missing_resolved_span_is_error():
    _rs = [_base_row(0)]
    _rs[0]["★ resolved_span"] = ""
    _errs, _notes = n1.check_inputs(_rs)
    assert any("错误行号" in e for e in _errs)


def test_blank_anchor_with_evidence_line_is_note_only():
    """★ 合法空白锚点 ⇒ 只提示，★ 不算错误。"""
    _rs = [_base_row(0, blank_anchor=True)]
    _errs, _notes = n1.check_inputs(_rs)
    assert not any("错误行号" in e for e in _errs)
    assert any("合法空白锚点" in n for n in _notes)


def test_missing_evidence_line_is_note_only():
    """★ 无含实体的证据句 ⇒ 证据不充分（★ 提示）。"""
    _rs = [_base_row(0)]
    _rs[0]["★ 证据句（含 entity 的非空行）"] = ""
    _errs, _notes = n1.check_inputs(_rs)
    assert any("证据不充分" in n for n in _notes)


def test_duplicate_id_detected():
    _rs = [_base_row(0), _base_row(0)]
    _errs, _notes = n1.check_inputs(_rs)
    assert any("重复 sample_id" in e for e in _errs)


# ══ ② 标签合法性与完整度 ══
def test_illegal_truth_label_detected():
    _rs = [_base_row(0)]
    _rs[0]["★ A:truth_label"] = "false_confirmation"   # ★ 盲审**不应**出现
    _errs, _complete = n1.check_labels(_rs, "A")
    assert any("非法 truth_label" in e for e in _errs)


def test_illegal_support_detected():
    _rs = [_base_row(0)]
    _rs[0]["★ A:evidence_support"] = "maybe"
    _errs, _complete = n1.check_labels(_rs, "A")
    assert any("非法 evidence_support" in e for e in _errs)


def test_partial_label_not_counted_as_complete():
    _rs = [_base_row(0)]
    _rs[0]["★ A:object"] = ""                  # ★ 部分标注
    _errs, _complete = n1.check_labels(_rs, "A")
    assert not _complete
    assert any("未填字段" in e for e in _errs)


def test_all_blind_fields_required():
    _rs = [_base_row(0)]
    for _f in n1.BLIND_FIELDS:
        _rs[0][f"★ A:{_f}"] = ""
    _errs, _complete = n1.check_labels(_rs, "A")
    assert not _complete


# ══ ③ 未标注 ⇒ N/A ══
def test_empty_table_returns_na():
    _st = n1.group_stats([], "A", set())
    assert _st["★ 完整标注数"] == 0
    assert _st["★ 完整度"] == "N/A"   # ★ 分母为 0 ⇒ N/A（★ 非 0%）
    assert _st["★ 真值分布"] == {}


def test_no_model_state_forbids_model_metrics(tmp_path):
    """★ 模型状态缺失 ⇒ 禁止输出误确认率/误拒收率/精确率。"""
    _rs = [_base_row(0)]
    _p = _write(tmp_path, _rs)
    _out = n1.main(_p)
    _m = _out["★ 模型相对指标"]
    assert _m["误确认率"] == "N/A"
    assert _m["误拒收率"] == "N/A"
    assert _m["确认精确率"] == "N/A"


# ══ ④ 模型相对标签自动生成 ══
def test_derive_model_relative():
    assert n1.derive_model_relative("valid_confirmed", "confirmed") == "valid_confirmed"
    assert n1.derive_model_relative("valid_rejection", "confirmed") == "false_confirmation"
    assert n1.derive_model_relative("valid_confirmed", "rejected") == "false_rejection"
    assert n1.derive_model_relative("valid_rejection", "rejected") == "valid_rejection"


def test_confusion_matrix_and_metrics(tmp_path):
    _rs = [_base_row(0, truth="valid_confirmed"),
           _base_row(1, truth="valid_rejection"),
           _base_row(2, truth="valid_rejection"),
           _base_row(3, truth="valid_confirmed")]
    _p = _write(tmp_path, _rs)
    _ms = tmp_path / "m.jsonl"
    _ms.write_text("\n".join(json.dumps(m, ensure_ascii=False)
                             for m in _models(_rs)), encoding="utf-8")
    _out = n1.main(_p, None, str(_ms))
    _m = _out["★ 模型相对指标"]
    # ★ 模型全 confirmed：★ 2 个 valid_rejection ⇒ false_confirmation
    assert _m["★ 模型相对标签分布"]["false_confirmation"] == 2
    assert _m["★ 模型相对标签分布"]["valid_confirmed"] == 2
    assert _m["确认精度分母"] == 4
    assert _m["确认精确率"] == 0.5
    assert _m["误确认数"] == 2


def test_confusion_matrix_with_mixed_model_states(tmp_path):
    _rs = [_base_row(0, truth="valid_confirmed"),
           _base_row(1, truth="valid_rejection")]
    _p = _write(tmp_path, _rs)
    _ms = tmp_path / "m.jsonl"
    _ms.write_text("\n".join(json.dumps(m, ensure_ascii=False)
                             for m in _models(_rs, {"doc@1#0": "confirmed",
                                                  "doc@1#1": "rejected"})),
                   encoding="utf-8")
    _out = n1.main(_p, None, str(_ms))
    _cm = _out["★ 模型相对指标"]["★ 混淆矩阵"]
    assert _cm["model=confirmed|truth=valid_confirmed"] == 1
    assert _cm["model=rejected|truth=valid_rejection"] == 1
    _d = _out["★ 模型相对指标"]["★ 模型相对标签分布"]
    assert _d.get("false_rejection", 0) == 0
    assert _d.get("false_confirmation", 0) == 0


# ══ ⑤ 逐字段原文支持率 ══
def test_field_support_rate_present():
    _rs = [_base_row(0), _base_row(1, support="evidence_insufficient")]
    _ids = {r["sample_id"] for r in _rs}
    _fs = n1.field_support(_rs, "A", _ids)
    assert _fs["object"]["★ ★ 原文支持率"] in (0.0, "N/A")
    assert _fs["★ evidence_support 分布"]["supported"] == 1
    assert _fs["★ evidence_support 分布"]["evidence_insufficient"] == 1
    assert _fs["★ ★ 整体原文支持率"] == 0.5


# ══ ⑥ 双审与仲裁 ══
def test_dual_agreement_and_disagreement(tmp_path):
    _a = [_base_row(0), _base_row(1)]
    _b = [_base_row(0), _base_row(1)]
    _b[1]["★ B:truth_label"] = "valid_rejection"
    _pa = _write(tmp_path, _a, "a.csv")
    _pb = _write(tmp_path, _b, "b.csv")
    _out = n1.main(_pa, _pb)
    _d = _out["★ 双审一致性"]
    assert _d["★ 一致"] == 1 and _d["★ 分歧"] == 1
    assert _d["★ 一致率"] == 0.5


def test_arbitration_resolves_disagreement(tmp_path):
    _a = [_base_row(0)]
    _b = [_base_row(0)]
    _b[0]["★ B:truth_label"] = "valid_rejection"
    _pa = _write(tmp_path, _a, "a.csv")
    _pb = _write(tmp_path, _b, "b.csv")
    _arb = tmp_path / "arb.csv"
    with _arb.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["sample_id", "分组", "★ A:truth_label", "★ B:truth_label",
                    "★ 是否分歧", "★ 仲裁后 truth_label", "★ 仲裁者", "★ 仲裁理由"])
        w.writerow(["doc@1#0", "R", "valid_confirmed", "valid_rejection",
                    "是", "valid_confirmed", "arbiter", "★ 原文支持"])
    _out = n1.main(_pa, _pb, None, str(_arb))
    assert _out["★ 双审一致性"]["★ 已仲裁"] == 1
    assert _out["★ 双审一致性"]["★ 未仲裁"] == 0


# ══ ⑦ R/K 独立分母 ══
def test_r_k_separate_denominators(tmp_path):
    _rs = [_base_row(0, grp="R"), _base_row(1, grp="K")]
    _p = _write(tmp_path, _rs)
    _out = n1.main(_p)
    _g = _out["★ 分组汇总(A)"]
    assert _g["R（★ 分层随机）"]["★ 完整标注数"] == 1
    assert _g["K（★ 风险富集）"]["★ 完整标注数"] == 1


# ══ ⑧ 可复算 ══
def test_recomputable(tmp_path):
    _rs = [_base_row(0)]
    _p = _write(tmp_path, _rs)
    assert n1.main(_p)["★ 分组汇总(A)"] == n1.main(_p)["★ 分组汇总(A)"]


# ══ ⑨ 交付物与盲审契约 ══
@pytest.mark.parametrize("name", ["N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv",
                                  "N1_盲审标注表.md", "N1_审核说明.md",
                                  "N1_仲裁表.csv", "n1_汇总脚本.py"])
def test_deliverable_exists(name):
    assert (DELIV / name).is_file(), name


def test_delivered_csv_evidence_complete():
    _rows_ = list(csv.DictReader((DELIV / "N1_盲审标注表_A.csv")
                                 .open(encoding="utf-8")))
    assert len(_rows_) == 50
    for _r in _rows_:
        assert _r["★ resolved_span"].strip(), _r["sample_id"]
        assert _r["★ RFC 原文上下文（锚点 ±6 行）"].strip(), _r["sample_id"]
        assert _r["★ 证据句（含 entity 的非空行）"].strip(), _r["sample_id"]
        assert _r["★ span_mode"].strip(), _r["sample_id"]
        assert _r["chunk_id"].strip(), _r["sample_id"]


def test_blind_files_have_no_model_relative_labels():
    """★ 盲审表**不得**出现 false_confirmation / false_rejection 标签列。"""
    for _name in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv"):
        _rows_ = list(csv.DictReader((DELIV / _name).open(encoding="utf-8")))
        for _r in _rows_:
            for _k in _r:
                assert "false_confirmation" not in _k
                assert "false_rejection" not in _k


def test_blind_files_have_no_model_state_leak():
    for _name in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv"):
        _rows_ = list(csv.DictReader((DELIV / _name).open(encoding="utf-8")))
        for _r in _rows_:
            for _k in _r:
                assert not any(_w in _k for _w in ("L2", "final_state", "verdict")), _k


def test_dual_reviewers_have_full_blind_columns():
    for _name, _tag in (("N1_盲审标注表_A.csv", "A"), ("N1_盲审标注表_B.csv", "B")):
        _rows_ = list(csv.DictReader((DELIV / _name).open(encoding="utf-8")))
        for _r in _rows_:
            for _f in n1.BLIND_FIELDS:
                assert f"★ {_tag}:{_f}" in _r
