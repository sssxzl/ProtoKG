# -*- coding: utf-8 -*-
"""V2-E4-R11 回归测试：原子边界复核表、来源追溯、版本保护与评估门禁。

覆盖：复核表恰 4 条且无锁、待填列全空、来源追溯修订恰 1 条、
      v1 冻结件未改、v2 为候选版、门禁两项未通过、原件与生产隔离。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R11_跨协议Gold原子边界复核与评估准入")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R7D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R7_H3Gold字段复核与评测准入")
R11 = ROOT / "guard/_out/_n1c_v2/r11"

V1 = R10D / "R10_跨协议Gold冻结基线.jsonl"
V2 = R10D / "R11_跨协议Gold冻结基线_v2候选.jsonl"
SHA_V1 = "bbce8979138605160f9af1c1c72a8c6c3b4750f31f808e9f03e2548f4b2a57eb"
TRACE = json.loads((R11 / "r11_trace.json").read_text(encoding="utf-8"))
GATE = json.loads((R11 / "r11_gate.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _header_row(ws, marker):
    for _r in range(1, min(ws.max_row, 20) + 1):
        if any(marker in str(ws.cell(row=_r, column=c).value or "")
               for c in range(1, ws.max_column + 1)):
            return _r
    raise AssertionError(f"未找到表头行（{marker}）")


# ===== 边界复核表 =====
def test_boundary_review_has_4_rows():
    _wb = openpyxl.load_workbook(DELIV / "R11_SC05SC06原子知识边界复核.xlsx")
    _ws = _wb["SC05SC06边界复核"]
    _hr = _header_row(_ws, "Gold ID")
    _ids = [str(_ws.cell(row=r, column=1).value or "").strip()
            for r in range(_hr + 1, _ws.max_row + 1)
            if str(_ws.cell(row=r, column=1).value or "").strip()]
    _wb.close()
    assert len(_ids) == 4, _ids
    assert sorted(_ids) == [
        "SMTP-ATOM-X-smtp-rfc3461-04-a", "SMTP-ATOM-X-smtp-rfc3461-04-b",
        "SMTP-ATOM-X-smtp-rfc6531-01-a", "SMTP-ATOM-X-smtp-rfc6531-01-b"]


def test_boundary_review_no_lock():
    _wb = openpyxl.load_workbook(DELIV / "R11_SC05SC06原子知识边界复核.xlsx")
    for _s in _wb.sheetnames:
        assert _wb[_s].protection.sheet is False, _s
        for _row in _wb[_s].iter_rows():
            for _c in _row:
                assert _c.protection.locked is False, f"{_s}!{_c.coordinate}"
    _wb.close()


def test_boundary_review_fill_columns_empty():
    _wb = openpyxl.load_workbook(DELIV / "R11_SC05SC06原子知识边界复核.xlsx")
    _ws = _wb["SC05SC06边界复核"]
    _hr = _header_row(_ws, "Gold ID")
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]
    _fill = [i for i, h in enumerate(_hdr, 1) if "待填" in h]
    assert len(_fill) == 12, _fill
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        for _ci in _fill:
            assert not str(_ws.cell(row=_r, column=_ci).value or "").strip()
    _wb.close()


def test_boundary_review_includes_required_context():
    _wb = openpyxl.load_workbook(DELIV / "R11_SC05SC06原子知识边界复核.xlsx")
    _ws = _wb["SC05SC06边界复核"]
    _hr = _header_row(_ws, "Gold ID")
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]
    for _need in ("★ RFC 原文证据", "★ 证据跨度（行号）", "★ A 审核理由",
                  "★ B 审核理由", "★ C 仲裁理由", "★ 当前 Gold 命题文本",
                  "★ 同组另一条的 Gold ID", "★ 是否应独立成条（待填）",
                  "★ 独立命题的准确文本（待填）", "★ 是否与其他 Gold 重复（待填）",
                  "★ 审核者（待填）", "★ 审核日期（待填）"):
        assert _need in _hdr, _need
    _wb.close()


# ===== 来源追溯 =====
def test_trace_covers_65():
    _t = TRACE["trace"]
    assert len(_t) == 65


def test_only_one_revision():
    assert len(TRACE["revisions"]) == 1
    assert TRACE["revisions"][0]["gold_id"] == "RTSP-ATOM-X-rtsp-rfc7826-03-1"


def test_revision_records_consensus_and_third_party():
    _r = TRACE["revisions"][0]
    assert "A" in _r["★ 实际来源审核者"]
    assert "B" in _r["★ 实际来源审核者"]
    assert "C" in _r["★ 实际来源审核者"]
    assert _r["★ 是否有第三方确认"] == "是"


def test_other_64_unchanged():
    _rev = {r["gold_id"] for r in TRACE["revisions"]}
    _all = {r["gold_id"] for r in TRACE["trace"]}
    assert len(_all - _rev) == 64


# ===== 版本保护 =====
def test_v1_frozen_unchanged():
    assert hashlib.sha256(V1.read_bytes()).hexdigest() == SHA_V1


def test_v2_is_candidate_with_same_count():
    _v1 = _jl(V1)
    _v2 = _jl(V2)
    assert len(_v1) == len(_v2) == 65
    assert all("v2 候选" in r.get("★ 版本", "") for r in _v2
               if r["gold_id"] == "RTSP-ATOM-X-rtsp-rfc7826-03-1")


def test_v2_only_changes_source_annotation():
    _d = TRACE["diff"]
    assert len(_d) == 1
    _ch = _d[0]["变化"]
    assert set(_ch) <= {"★ 人工来源", "★ 仲裁者", "★ 来源证据", "★ 版本",
                        "★ 基于版本 SHA256"}, _ch


def test_candidate_and_atom_still_counted_separately():
    _v2 = _jl(V2)
    _c = [r for r in _v2 if r["gold_level"] == "candidate"]
    _a = [r for r in _v2 if r["gold_level"] == "atom"]
    assert len(_c) == 57
    assert len(_a) == 8


# ===== 评估门禁 =====
def test_gate_has_two_open_items():
    assert sorted(GATE["open"]) == [5, 10]


def test_gate_report_states_posthoc():
    _t = (DELIV / "R11_正式分类评估执行门禁.md").read_text(encoding="utf-8")
    assert "事后分析" in _t
    assert "R10-P1 是否属于严格的未接触结果的事前预注册规则" in _t
    assert "不得启动" in _t


def test_h3_and_crossprotocol_separate():
    _t = (DELIV / "R11_正式分类评估执行门禁.md").read_text(encoding="utf-8")
    assert "不混合冻结、不混合计算" in _t


def test_rtsp_sample_limit_stated():
    _t = (DELIV / "R11_正式分类评估执行门禁.md").read_text(encoding="utf-8")
    assert "仅 7 条" in _t


# ===== 原件与生产隔离 =====
def test_r7_preregistration_unchanged():
    assert hashlib.sha256(
        (R7D / "R7_H3_V2版本哈希及预注册规则.md").read_bytes()
    ).hexdigest() == \
        "7cfa8430c4a1d07748bfbcc1fdb29fe12fdd034b2baa78c06bc4e73b40838a91"


def test_r3_baseline_unchanged():
    assert hashlib.sha256(
        (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl")
        .read_bytes()).hexdigest() == \
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a"


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


def test_no_llm_calls_in_r11():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r11").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R11_SC05SC06原子知识边界复核.xlsx",
               "R11_Gold人工来源追溯.xlsx",
               "R11_Gold版本差异与冻结验收.xlsx",
               "R11_正式分类评估执行门禁.md",
               "R11_评估分母及标签映射.xlsx"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n
