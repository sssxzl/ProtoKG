# -*- coding: utf-8 -*-
"""tests/fused/test_annotation_sheet.py —— 标注表的「导出 → 填写 → 回收」通道。

★ 为什么要有这组测试：117 条人工标注是 M2 的**唯一硬前提**，
  而人工填表与 JSON 之间的转换是**手工时代最容易出错**的一环
  （行错位、text 被 Excel 改写、词表拼错、holdout 混进 train）。
  这组测试把「表与冻结集必须逐字一致」「回收必须过标注器校验」固化成断言。

★ 只写临时目录，不碰 `derived/exp_semantic/truth/`。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("openpyxl")

from openpyxl import load_workbook  # noqa: E402

from scripts import annotation_sheet as AS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TRUTH = REPO / "derived" / "exp_semantic" / "truth"
FROZEN = REPO / "derived" / "exp_semantic" / "candidates_frozen.jsonl"


def _skip_if_no_data() -> None:
    if not TRUTH.is_dir() or not FROZEN.is_file():
        pytest.skip("无冻结候选集 / 标注集")


def _rows(xlsx: Path) -> list[tuple]:
    ws = load_workbook(xlsx)["标注表"]
    out, r = [], AS.FIRST_DATA_ROW
    while ws.cell(row=r, column=2).value:
        out.append(tuple(ws.cell(row=r, column=c).value
                         for c in range(1, len(AS.COLS) + 1)))
        r += 1
    return out


def _filled_copy(src: Path, dst: Path) -> int:
    """按「奇数行 否 / 偶数行 是+MUST+present」填一遍，返回填写行数。"""
    wb = load_workbook(src)
    ws = wb["标注表"]
    ws.cell(row=2, column=2, value="T")
    r, n = AS.FIRST_DATA_ROW, 0
    while ws.cell(row=r, column=2).value:
        if n % 2:
            ws.cell(row=r, column=7, value="是")
            ws.cell(row=r, column=8, value="MUST")
            ws.cell(row=r, column=9, value="present")
        else:
            ws.cell(row=r, column=7, value="否")
        r, n = r + 1, n + 1
    wb.save(dst)
    return n


# ===========================================================================
# ① 导出：行数、逐字一致、分层正确
# ===========================================================================

def test_export_row_count_matches_pending(tmp_path):
    _skip_if_no_data()
    frozen = AS.load_frozen()
    expect = AS.pending_rows(TRUTH, frozen)
    out = tmp_path / "sheet.xlsx"
    assert AS.main(["export", "--xlsx", str(out)]) == 0
    rows = _rows(out)
    assert len(rows) == len(expect) == 117
    assert [r[1] for r in rows] == [e["candidate_id"] for e in expect]


def test_export_text_is_verbatim(tmp_path):
    """★ Excel 不得改写候选文本（前后空格 / 换行 / 特殊字符）。"""
    _skip_if_no_data()
    frozen = AS.load_frozen()
    out = tmp_path / "sheet.xlsx"
    AS.main(["export", "--xlsx", str(out)])
    for r in _rows(out):
        cid, text = r[1], r[5]
        assert text == frozen[cid]["text"], f"{cid} 的 text 被改写"


def test_export_marks_holdout_and_prefills_nothing(tmp_path):
    """★ holdout 必须标出来；四个判定列必须**全空**（不预填答案）。"""
    _skip_if_no_data()
    out = tmp_path / "sheet.xlsx"
    AS.main(["export", "--xlsx", str(out)])
    rows = _rows(out)
    splits = {(r[2], r[3]) for r in rows}
    assert ("rtsp", "holdout") in splits and ("rtsp", "train") in splits
    for r in rows:
        assert r[6] is None and r[7] is None and r[8] is None and r[9] is None


def test_export_include_labeled_gives_120(tmp_path):
    """★ 给第二标注者出表时必须给**全 120 条** —— 只给 117 条会泄漏
    「这 3 条已标过」这一信息，且会让两人的可比样本不一致。"""
    _skip_if_no_data()
    out = tmp_path / "all.xlsx"
    AS.main(["export", "--xlsx", str(out), "--include-labeled"])
    rows = _rows(out)
    assert len(rows) == 120
    # 已标条目的答案**不得**出现在表里（B 必须盲标）
    for r in rows:
        assert r[6] is None and r[7] is None and r[8] is None and r[9] is None


def test_export_is_deterministic(tmp_path):
    _skip_if_no_data()
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    AS.main(["export", "--xlsx", str(a)])
    AS.main(["export", "--xlsx", str(b)])
    assert _rows(a) == _rows(b)


# ===========================================================================
# ② 回收：结构、校验、词表
# ===========================================================================

def test_import_roundtrip_preserves_ids_and_split(tmp_path):
    _skip_if_no_data()
    frozen = AS.load_frozen()
    expect = {(e["protocol"], e["split"]): set() for e in
              AS.pending_rows(TRUTH, frozen)}
    for e in AS.pending_rows(TRUTH, frozen):
        expect[(e["protocol"], e["split"])].add(e["candidate_id"])

    src = tmp_path / "sheet.xlsx"
    AS.main(["export", "--xlsx", str(src)])
    filled = tmp_path / "filled.xlsx"
    _filled_copy(src, filled)

    out_dir = tmp_path / "out"
    assert AS.main(["import", "--xlsx", str(filled),
                    "--out-dir", str(out_dir)]) == 0

    got = {(p, sp): set() for (p, sp) in expect}
    for f in sorted(out_dir.glob("*.json")):
        proto = f.name.split(".")[0]
        split = "holdout" if f.stem.endswith(".holdout") else "train"
        for rec in json.loads(f.read_text(encoding="utf-8")):
            got[(proto, split)].add(rec["candidate_id"])
    assert got == expect


def test_import_derives_required_defaults(tmp_path):
    """`否` ⇒ 强度「无」、算子「不可」；类别留空 ⇒ null（标注器 R6/R7 同口径）。"""
    _skip_if_no_data()
    src = tmp_path / "sheet.xlsx"
    AS.main(["export", "--xlsx", str(src)])
    filled = tmp_path / "f.xlsx"
    _filled_copy(src, filled)
    out_dir = tmp_path / "o"
    assert AS.main(["import", "--xlsx", str(filled),
                    "--out-dir", str(out_dir)]) == 0

    seen_no = seen_yes = 0
    for f in out_dir.glob("*.json"):
        for rec in json.loads(f.read_text(encoding="utf-8")):
            assert rec["pending"] is False
            assert rec["annotator"] == "T"
            if rec["has_normative_requirement"]:
                seen_yes += 1
                assert rec["modality"] == "MUST"
                assert rec["operator"] == "present"
            else:
                seen_no += 1
                assert rec["modality"] == "无"
                assert rec["operator"] == "不可"
            assert rec["expected_response_class"] is None
    assert seen_no > 0 and seen_yes > 0


def test_import_rejects_unknown_candidate(tmp_path):
    """candidate_id 不在冻结集 ⇒ 必须拒绝（防止拿旧表回收）。"""
    _skip_if_no_data()
    src = tmp_path / "sheet.xlsx"
    AS.main(["export", "--xlsx", str(src)])
    wb = load_workbook(src)
    ws = wb["标注表"]
    ws.cell(row=2, column=2, value="T")
    ws.cell(row=AS.FIRST_DATA_ROW, column=2, value="rtsp-DEADBEEF00")
    bad = tmp_path / "bad.xlsx"
    wb.save(bad)
    assert AS.main(["import", "--xlsx", str(bad),
                    "--out-dir", str(tmp_path / "o")]) == 1


def test_import_requires_annotator(tmp_path):
    """没填表内 B2 也没给 --annotator ⇒ 拒绝（R10 要求可追溯）。"""
    _skip_if_no_data()
    src = tmp_path / "sheet.xlsx"
    AS.main(["export", "--xlsx", str(src)])
    filled = tmp_path / "f.xlsx"
    _filled_copy(src, filled)
    wb = load_workbook(filled)
    # ★ 注意：`ws.cell(row, col, value=None)` 在 openpyxl 里是**空操作**
    #   （只有 value is not None 才赋值）⇒ 必须直接改 `.value`。
    wb["标注表"].cell(row=2, column=2).value = None
    wb.save(filled)
    assert AS.main(["import", "--xlsx", str(filled),
                    "--out-dir", str(tmp_path / "o")]) == 1


# ===========================================================================
# ③ 词表与标注器同源（防两处各写一套）
# ===========================================================================

def test_vocabulary_matches_annotator():
    from scripts import annotate_candidates as AC
    assert set(AS.MODALITIES) == AC.MODALITIES
    assert set(AS.OPERATORS) == AC.OPERATORS | {AC.NOT_EXECUTABLE}
    assert set(AS.RESPONSE_CLASSES) == AC.RESPONSE_CLASSES | {"null"}


def test_truth_files_unaffected_by_export(tmp_path):
    """★ 导出必须**只读** truth/（不许把 pending 顺手改成 false）。"""
    _skip_if_no_data()
    before = {f.name: f.read_bytes() for f in TRUTH.glob("*.json")}
    AS.main(["export", "--xlsx", str(tmp_path / "s.xlsx")])
    after = {f.name: f.read_bytes() for f in TRUTH.glob("*.json")}
    assert before == after
