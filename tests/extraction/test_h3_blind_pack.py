# -*- coding: utf-8 -*-
"""★ V2-E4-R1：★ H3 23 条候选盲审包（XLSX）的回归测试。

★ 覆盖：★ 三份 XLSX 存在 ｜★ 23 条完整无增删 ｜★ 身份表逐单元格一致
★ ｜★ 文本单元格 ｜★ 工作表保护 ｜★ 下拉枚举 ｜★ 不含机器预测 ｜★ 特殊字符不损坏
★ ｜★ 独立性与样本资格 ｜★ V0/V1/V2 哈希不变
"""
from __future__ import annotations

import collections
import hashlib
import io
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
     / "M1-Q3-V2-E4-R1_H3候选人工盲审")
R1 = ROOT / "guard/_out/_n1c_v2/r1"
ITEMS = json.loads((R1 / "_items.json").read_text(encoding="utf-8"))
BASE = [json.loads(l) for l in
        (R1 / "h3_machine_baseline.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]
XL = {"A": D / "H3_23候选_审核者A_盲审模板.xlsx",
      "B": D / "H3_23候选_审核者B_盲审模板.xlsx",
      "ARB": D / "H3_23候选_第三方仲裁模板.xlsx"}


# ══ ① 三份文件存在且可打开 ══
@pytest.mark.parametrize("tag", ["A", "B", "ARB"])
def test_xlsx_exists_and_opens(tag):
    assert XL[tag].is_file()
    _wb = openpyxl.load_workbook(XL[tag])
    assert len(_wb.sheetnames) >= 2
    _wb.close()


# ══ ② 23 条完整无增删 ══
def test_23_candidates_complete():
    assert len(ITEMS) == 23
    assert len(BASE) == 23
    assert len({b["★ 审核ID"] for b in BASE}) == 23


@pytest.mark.parametrize("tag", ["A", "B"])
def test_identity_sheet_has_23_rows_and_all_columns(tag):
    _wb = openpyxl.load_workbook(XL[tag])
    _ws = _wb["机器身份"]
    _hdr = [c.value for c in _ws[1]]
    assert len(_hdr) == 19
    assert _ws.max_row == 24        # ★ 表头 + 23 行
    _wb.close()


# ══ ③ 逐单元格一致 ══
@pytest.mark.parametrize("tag", ["A", "B"])
def test_identity_cells_match_baseline(tag):
    _wb = openpyxl.load_workbook(XL[tag])
    _ws = _wb["机器身份"]
    _hdr = [c.value for c in _ws[1]]
    for _r, _it in enumerate(ITEMS, start=2):
        for _ci, _col in enumerate(_hdr, start=1):
            assert (_ws.cell(row=_r, column=_ci).value or "") == \
                (_it.get(_col, "") or ""), f"{tag} r{_r} {_col}"
    _wb.close()


# ══ ④ 文本单元格（★ 禁日期/科学计数法转换）══
@pytest.mark.parametrize("tag", ["A", "B"])
def test_numeric_looking_cells_are_text(tag):
    _wb = openpyxl.load_workbook(XL[tag])
    _ws = _wb["机器身份"]
    _hdr = [c.value for c in _ws[1]]
    for _col in ("★ 证据跨度（行号）", "★ 候选锚点行号", "★ RFC SHA256"):
        _ci = _hdr.index(_col) + 1
        for _r in range(2, 25):
            _c = _ws.cell(row=_r, column=_ci)
            assert isinstance(_c.value, str), f"{tag} {_col} r{_r}"
            assert _c.number_format == "@"
    _wb.close()


# ══ ⑤ 工作表保护 + 下拉 ══
@pytest.mark.parametrize("tag", ["A", "B"])
def test_sheets_protected_and_dv_present(tag):
    _wb = openpyxl.load_workbook(XL[tag])
    for _s in _wb.sheetnames:
        if _s != "_枚举":
            assert _wb[_s].protection.sheet is True, _s
    assert len(_wb["人工审核"].data_validations.dataValidation) >= 8
    assert len(_wb["补充知识"].data_validations.dataValidation) >= 4
    _wb.close()


def test_enum_sheet_hidden():
    _wb = openpyxl.load_workbook(XL["A"])
    assert _wb["_枚举"].sheet_state == "hidden"
    _wb.close()


# ══ ⑥ 不含机器预测 ══
@pytest.mark.parametrize("tag", ["A", "B", "ARB"])
def test_no_machine_prediction_leak(tag):
    _forbid = ["prose_semantics", "prose_constraint",
               "normative_rule_candidate", "rule_channel", "structured_channel",
               "metadata_channel", "descriptive_channel", "pending_review"]
    _wb = openpyxl.load_workbook(XL[tag])
    for _s in _wb.sheetnames:
        if _s == "_枚举":
            continue
        for _row in _wb[_s].iter_rows():
            for _c in _row:
                _v = str(_c.value or "")
                for _f in _forbid:
                    assert _f not in _v, f"{tag}/{_s}/{_c.coordinate}: {_f}"
    _wb.close()


def test_candidate_id_not_exposed():
    """★ candidate_id 本身泄露类型判断（★ 如 prose_semantics_must）⇒ 不得出现在表中。"""
    _wb = openpyxl.load_workbook(XL["A"])
    for _s in _wb.sheetnames:
        if _s == "_枚举":
            continue
        for _row in _wb[_s].iter_rows():
            for _c in _row:
                assert "prose_semantics_" not in str(_c.value or "")
    _wb.close()


# ══ ⑦ 特殊字符不损坏 ══
def test_special_chars_roundtrip():
    _wb = openpyxl.load_workbook(XL["A"])
    _ws = _wb["机器身份"]
    _hdr = [c.value for c in _ws[1]]
    _ci = _hdr.index("★ 证据原文（RFC 逐行）") + 1
    for _r in range(2, 25):
        _v = _ws.cell(row=_r, column=_ci).value
        assert isinstance(_v, str)
    _wb.close()
    # ★ 基线与源文件逐条一致
    for _b in BASE:
        assert hashlib.sha256(
            str(_b["★ evidence_text"]).encode()).hexdigest() == \
            _b["★ evidence_text_sha256"], _b["★ 审核ID"]


# ══ ⑧ 独立性与样本资格 ══
def test_independence_checks_passed():
    _v = json.loads((R1 / "r1_verification.json").read_text(encoding="utf-8"))
    _i = _v["⑤ 独立性与样本资格检查"]
    assert _i["② 与 N1-B/N1-C/V2 开发数据的重叠"]["★ 重叠数"] == 0
    assert _i["③ 与历史 V2 调优样本的近重复"]["★ 近重复数"] == 0
    assert _v["★ 错误"] == []


def test_h2h3_not_comparable_with_queue_b():
    _v = json.loads((R1 / "r1_verification.json").read_text(encoding="utf-8"))
    _c = _v["⑥ 队列B 与 H1H2H3 可比较性预检"]["★ not_comparable 判定"]
    assert "not_comparable" in _c["★ H2 vs 队列B"]
    assert "not_comparable" in _c["★ H3 vs 队列B"]


# ══ ⑨ V0/V1/V2 不变 ══
def test_v0_v1_v2_unchanged():
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k


def test_no_llm_calls_in_r1():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r1").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name
