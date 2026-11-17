# -*- coding: utf-8 -*-
"""V2-E4-R8 回归测试：人工审核回收核验与 Gold v4。

覆盖：v1/v2/v3 原件未改、30 项复核的 5 项修正已应用、
      R4A 零泄漏、A/B 机器身份一致、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R5A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
       / "R5A_H3第三方仲裁与Gold冻结")
R7D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R7_H3Gold字段复核与评测准入")
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R8_人工审核回收核验")
R8 = ROOT / "guard/_out/_n1c_v2/r8"

SHA_V1 = "f4bfbdb5da1746416321ff2f20bcbf070330fa606f79c0715fccd8545fec6044"
SHA_V2 = "4f3df1a33a4ffab5bb9579a66a7ef7995365ea1cb1b67729b23b9aeaebd09014"
SHA_V3 = "bdc76a56873baa2f6f8800a15cf6de789187c063b6257f66a2614e0096b18e76"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


# ===== 冻结版本未被覆盖 =====
def test_v1_v2_v3_frozen_files_unchanged():
    assert hashlib.sha256(
        (R5A / "H3_Gold冻结基线.jsonl").read_bytes()).hexdigest() == SHA_V1
    assert hashlib.sha256(
        (R5A / "H3_Gold冻结基线_v2.jsonl").read_bytes()).hexdigest() == SHA_V2
    assert hashlib.sha256(
        (R5A / "H3_Gold冻结基线_v3候选.jsonl").read_bytes()).hexdigest() == SHA_V3


def test_v4_is_candidate_not_frozen():
    _rows = _jl(R5A / "H3_Gold冻结基线_v4候选.jsonl")
    assert len(_rows) == 28
    assert all("v4 候选" in r["★ 版本"] for r in _rows)


# ===== 30 项复核的人工回填 =====
def test_review_table_fully_filled():
    _wb = openpyxl.load_workbook(R7D / "R7_H3_30项结构化字段人工复核.xlsx",
                                  data_only=True)
    _ws = _wb["30项字段复核"]
    _hdr = [str(c.value or "").strip() for c in _ws[1]]
    _i_status = next(i for i, h in enumerate(_hdr, 1)
                     if h.startswith("★ 第三方确认结果"))
    _i_who = next(i for i, h in enumerate(_hdr, 1)
                  if h.startswith("★ 复核人员"))
    _i_date = next(i for i, h in enumerate(_hdr, 1)
                   if h.startswith("★ 复核日期"))
    _n = 0
    for _r in range(2, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        _n += 1
        assert str(_ws.cell(row=_r, column=_i_status).value or "").strip()
        assert str(_ws.cell(row=_r, column=_i_who).value or "").strip()
        assert str(_ws.cell(row=_r, column=_i_date).value or "").strip()
    _wb.close()
    assert _n == 30


def test_five_fixes_applied_to_v4():
    _v = _j(R8 / "r8_review_verification.json")
    assert _v["r7_review"]["状态分布"].get("修正") == 5
    assert len(_v["applied_fixes"]) == 5
    _v4 = {g["gold_knowledge_id"]: g
           for g in _jl(R5A / "H3_Gold冻结基线_v4候选.jsonl")}
    for _a in _v["applied_fixes"]:
        _f = _v4[_a["gold_id"]]["★ 适用的结构化字段"][_a["field"]]
        assert _f["value"] == _a["v4_value"], _a
        assert "第三方" in _f["source"], _a


def test_no_unresolved_in_review():
    _v = _j(R8 / "r8_review_verification.json")
    assert _v["r7_review"]["状态分布"].get("unresolved", 0) == 0


# ===== R4A 回收核验 =====
def test_r4a_no_leak_in_filled_columns():
    _v = _j(R8 / "r8_review_verification.json")
    for _f in _v["r4a"]["files"]:
        assert _f["leak_hits"] == 0, _f["file"]
    for _h in _v["r4a"]["html"]:
        assert _h["leak_hits"] == 0, _h["file"]


def test_r4a_ab_machine_identity_identical():
    _v = _j(R8 / "r8_review_verification.json")
    for _a in _v["r4a"]["ab"]:
        assert _a["machine_identity_diff"] == 0, _a["protocol"]


# ===== 生产隔离 =====
def test_production_unchanged():
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21


def test_no_llm_calls_in_r8():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r8").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R8_人工审核回收核验.xlsx",
               "R8_Gold版本谱系与修正追溯.xlsx",
               "R8_人工审核回收核验报告.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n
