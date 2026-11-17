# -*- coding: utf-8 -*-
"""V2-E4-R7 回归测试：30 项字段复核表、Gold 版本、分母、预注册与 R4A 发放核验。"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R5A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
       / "R5A_H3第三方仲裁与Gold冻结")
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R7_H3Gold字段复核与评测准入")
R4A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R4跨协议盲审与NormID碰撞/R4A_跨协议人工盲审包")
R7 = ROOT / "guard/_out/_n1c_v2/r7"

V1_SHA = "f4bfbdb5da1746416321ff2f20bcbf070330fa606f79c0715fccd8545fec6044"
V2_SHA = "4f3df1a33a4ffab5bb9579a66a7ef7995365ea1cb1b67729b23b9aeaebd09014"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


# ===== 冻结版本未被覆盖 =====
def test_v1_and_v2_frozen_files_unchanged():
    assert hashlib.sha256(
        (R5A / "H3_Gold冻结基线.jsonl").read_bytes()).hexdigest() == V1_SHA
    assert hashlib.sha256(
        (R5A / "H3_Gold冻结基线_v2.jsonl").read_bytes()).hexdigest() == V2_SHA


def test_v3_is_candidate_not_frozen():
    """v3 为候选版，★ 须标记为未冻结。"""
    _rows = _jl(R5A / "H3_Gold冻结基线_v3候选.jsonl")
    assert len(_rows) == 28
    assert all("v3 候选" in r["★ 版本"] for r in _rows)


# ===== 30 项字段复核表 =====
def test_field_review_table_has_all_30():
    _wb = openpyxl.load_workbook(DELIV / "R7_H3_30项结构化字段人工复核.xlsx")
    _ws = _wb["30项字段复核"]
    _n = _ws.max_row - 1
    _wb.close()
    assert _n == 30


def test_field_review_human_columns_filled():
    """★ 第三方已回填（R8）：★ 确认结果、复核人、复核日期三列必须已填。

    ★ 修正值与修正理由两列只在「修正」行填写，★ 其余行为空是正确用法。
    """
    _wb = openpyxl.load_workbook(DELIV / "R7_H3_30项结构化字段人工复核.xlsx")
    _ws = _wb["30项字段复核"]
    _hdr = [str(c.value or "") for c in _ws[1]]
    _i_st = next(i for i, h in enumerate(_hdr, 1)
                 if h.startswith("★ 第三方确认结果"))
    _i_who = next(i for i, h in enumerate(_hdr, 1)
                  if h.startswith("★ 复核人员"))
    _i_date = next(i for i, h in enumerate(_hdr, 1)
                   if h.startswith("★ 复核日期"))
    _i_fix = next(i for i, h in enumerate(_hdr, 1)
                  if h.startswith("★ 修正值"))
    _n = 0
    for _r in range(2, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        _n += 1
        _st = str(_ws.cell(row=_r, column=_i_st).value or "").strip()
        assert _st in ("确认", "修正", "unresolved"), _st
        assert str(_ws.cell(row=_r, column=_i_who).value or "").strip()
        assert str(_ws.cell(row=_r, column=_i_date).value or "").strip()
        if _st == "修正":
            assert str(_ws.cell(row=_r, column=_i_fix).value or "").strip()
    _wb.close()
    assert _n == 30


def test_field_review_includes_evidence_and_versions():
    _wb = openpyxl.load_workbook(DELIV / "R7_H3_30项结构化字段人工复核.xlsx")
    _ws = _wb["30项字段复核"]
    _hdr = [str(c.value or "") for c in _ws[1]]
    for _need in ("RFC 原文证据", "A 原始取值", "B 原始取值", "C 仲裁原文",
                  "Gold v1 取值", "Gold v2 冻结取值", "Gold v3 候选取值"):
        assert _need in _hdr, _need
    _wb.close()


def test_key_two_fields_present():
    """GK-H3-03-1 与 GK-H3-05-1 必须在表中。"""
    _wb = openpyxl.load_workbook(DELIV / "R7_H3_30项结构化字段人工复核.xlsx")
    _ws = _wb["30项字段复核"]
    _ids = {str(_ws.cell(row=r, column=1).value)
            for r in range(2, _ws.max_row + 1)}
    _wb.close()
    assert "GK-H3-03-1" in _ids
    assert "GK-H3-05-1" in _ids


# ===== 分母 =====
def test_denominator_counts():
    _rows = _jl(R5A / "H3_Gold冻结基线_v3候选.jsonl")
    _cv = [g for g in _rows if g["gold_level"] == "candidate"
           and g["status"] == "confirmed_valid"]
    _meta = [g for g in _cv if g["knowledge_kind"] == "non_protocol_metadata"]
    _proto = [g for g in _cv if g["knowledge_kind"] != "non_protocol_metadata"]
    _excl = [g for g in _rows if g["status"] == "excluded"]
    _supp = [g for g in _rows if g["gold_level"] == "supplementary"]
    assert len(_rows) == 28
    assert len(_cv) == 22
    assert len(_proto) == 18
    assert len(_meta) == 4
    assert len(_excl) == 1
    assert len(_supp) == 5


def test_polarity_and_completeness_states():
    _rows = _jl(R5A / "H3_Gold冻结基线_v3候选.jsonl")
    for g in _rows:
        if g["gold_level"] == "candidate":
            assert g["polarity"] == "unavailable"
        assert g["extract_completeness"] in (
            "not_applicable", "cross_sentence_missing", "cross_section_missing",
            "partial", "full", "unavailable")


# ===== 预注册与门禁 =====
def test_preregistration_file_has_hashes_and_rules():
    _p = DELIV / "R7_H3_V2版本哈希及预注册规则.md"
    _t = _p.read_text(encoding="utf-8")
    assert "SHA256" in _t
    assert "匹配规则" in _t
    assert "排除条件" in _t
    assert "暴露样本" in _t
    assert "严禁" in _t


def test_gate_report_has_no_pending_items():
    _t = (DELIV / "R7_H3_正式评测门禁报告.md").read_text(encoding="utf-8")
    assert "待确认 | 0" in _t or "待确认 | 0 |" in _t


def test_v2_gate_hash_recorded():
    _p = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")
    assert hashlib.sha256(_p.read_bytes()).hexdigest() in \
        (DELIV / "R7_H3_V2版本哈希及预注册规则.md").read_text(encoding="utf-8")


# ===== R4A 发放核验 =====
def test_r4a_verification_clean():
    _v = _j(R7 / "r7_r4a_verification.json")
    for _r in _v["xlsx"]:
        assert _r["leak_hits"] == 0, _r["file"]
        assert _r["human_cells_filled"] == 0, _r["file"]
        assert _r["sheet_protection_nodes"] == 0, _r["file"]
        assert _r["locked_attributes"] == 0, _r["file"]
    for _h in _v["html"]:
        assert _h["leak_hits"] == 0, _h["file"]
    for _a in _v["ab_identity"]:
        assert _a["machine_identity_diff"] == 0, _a["protocol"]
        assert _a["machine_identity_content_hash_same"] is True, _a["protocol"]


@pytest.mark.parametrize("proto,n", [("SIP", 27), ("RTSP", 7), ("SMTP", 23)])
def test_r4a_candidate_counts(proto, n):
    _v = _j(R7 / "r7_r4a_verification.json")
    _got = [r["candidate_rows"] for r in _v["xlsx"]
            if r["file"].startswith(proto)]
    assert _got == [n, n, n], (proto, _got)


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


def test_no_llm_calls_in_r7():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r7").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R7_H3_30项结构化字段人工复核.xlsx",
               "R7_H3_Gold版本差异与追溯.xlsx",
               "R7_H3_评估分母与排除规则.xlsx",
               "R7_H3_V2版本哈希及预注册规则.md",
               "R7_H3_正式评测门禁报告.md",
               "R7_R4A三协议人工审核发放核验.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n
