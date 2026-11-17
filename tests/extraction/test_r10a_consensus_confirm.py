# -*- coding: utf-8 -*-
"""V2-E4-R10A 回归测试：5 条共识待确认表与分母对账。

覆盖：待确认表恰 5 条、无锁、C 列全空、A/B 值已填、R7 未改、
      R10 报告分母已修正为 52、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R10A = ROOT / "guard/_out/_n1c_v2/r10a"
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"
R7P = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R7_H3Gold字段复核与评测准入"
       / "R7_H3_V2版本哈希及预注册规则.md")

CONFIRM = DELIV / "R10_5条共识待确认.xlsx"
RECON = json.loads((R10A / "r10a_reconciliation.json").read_text(
    encoding="utf-8"))

TARGET = {"X-rtsp-rfc7826-07", "X-sip-rfc2543-01", "X-sip-rfc3428-03",
          "X-sip-rfc3428-04", "X-smtp-rfc8098-04"}


def _header_row(ws, marker):
    for _r in range(1, min(ws.max_row, 20) + 1):
        if any(marker in str(ws.cell(row=_r, column=c).value or "")
               for c in range(1, ws.max_column + 1)):
            return _r
    raise AssertionError(f"未找到表头行（{marker}）")


def _rows_of(path, sheet):
    _wb = openpyxl.load_workbook(path, data_only=True)
    _ws = _wb[sheet]
    _hr = _header_row(_ws, "candidate_id")
    _hdr = [str(_ws.cell(row=_hr, column=_c).value or "").strip()
            for _c in range(1, _ws.max_column + 1)]
    _out = []
    for _r in range(_hr + 1, _ws.max_row + 1):
        if str(_ws.cell(row=_r, column=1).value or "").strip():
            _out.append({_hdr[_c - 1]: _ws.cell(row=_r, column=_c).value
                         for _c in range(1, _ws.max_column + 1)})
    _wb.close()
    return _out


# ===== 待确认表 =====
def test_confirm_table_has_exactly_5_rows():
    _rs = _rows_of(CONFIRM, "5条共识待确认")
    assert len(_rs) == 5, len(_rs)
    assert {r["★ candidate_id"] for r in _rs} == TARGET


def test_confirm_table_has_no_protection():
    _wb = openpyxl.load_workbook(CONFIRM)
    for _s in _wb.sheetnames:
        assert _wb[_s].protection.sheet is False, _s
        for _row in _wb[_s].iter_rows():
            for _c in _row:
                assert _c.protection.locked is False, f"{_s}!{_c.coordinate}"
    _wb.close()


def test_c_confirmation_columns_filled_after_return():
    """★ 第三方已回填（R10B）：★ 7 个 C 列须有值且枚举合法。"""
    _rs = _rows_of(CONFIRM, "5条共识待确认")
    _fill = [k for k in _rs[0] if "待填" in k]
    assert len(_fill) == 7, _fill
    _K = {"non_protocol_metadata", "protocol_syntax",
          "protocol_registry_or_enumeration",
          "protocol_descriptive_semantics", "normative_rule_candidate",
          "mixed_or_uncertain"}
    _E = {"eligible", "ineligible", "uncertain", "not_applicable"}
    _R = {"rule_channel", "structured_channel", "metadata_channel",
          "descriptive_channel", "pending_review", "not_applicable"}
    for _r in _rs:
        for _k in _fill:
            assert str(_r.get(_k) or "").strip(), (_r["★ candidate_id"], _k)
        assert _r["★ C 确认知识类型（待填）"] in _K, _r["★ candidate_id"]
        assert _r["★ C 确认规则资格（待填）"] in _E, _r["★ candidate_id"]
        assert _r["★ C 确认目标路由（待填）"] in _R, _r["★ candidate_id"]
        assert _r["★ C 确认状态（待填）"] == "confirmed", _r["★ candidate_id"]
        assert _r["★ C 审核者 ID（待填）"] == "F", _r["★ candidate_id"]


def test_ab_values_prefilled_with_evidence():
    _rs = _rows_of(CONFIRM, "5条共识待确认")
    for _r in _rs:
        assert _r["★ A 知识类型"], _r["★ candidate_id"]
        assert _r["★ B 知识类型"], _r["★ candidate_id"]
        assert _r["★ A 规则资格"], _r["★ candidate_id"]
        assert _r["★ B 规则资格"], _r["★ candidate_id"]
        assert _r["★ A 目标路由"], _r["★ candidate_id"]
        assert _r["★ B 目标路由"], _r["★ candidate_id"]
        assert str(_r["★ 证据跨度（行号）"] or "").strip(), _r["★ candidate_id"]
        assert str(_r["★ RFC 原文证据"] or "").strip(), _r["★ candidate_id"]
        assert str(_r["★ source_sha256"] or "").strip(), _r["★ candidate_id"]


def test_ab_agreement_confirmed_by_fourth_reviewer():
    """★ A/B 一致者由第四位审核者 F 确认，★ 而非自动视为已确认。"""
    _rs = _rows_of(CONFIRM, "5条共识待确认")
    for _r in _rs:
        assert _r["★ C 当前裁定状态"] == "agreed"
        # ★ 确认者须与 A/B 不同
        assert _r["★ C 审核者 ID（待填）"] not in ("A", "B")
        assert str(_r.get("★ C 确认理由（待填）") or "").strip()


# ===== 分母对账 =====
def test_57_reconciliation_counts():
    _c = RECON["counts"]
    assert _c["SIP"]["总数"] == 27 and _c["SIP"]["已有 C 裁定"] == 24 \
        and _c["SIP"]["待确认"] == 3
    assert _c["RTSP"]["总数"] == 7 and _c["RTSP"]["已有 C 裁定"] == 6 \
        and _c["RTSP"]["待确认"] == 1
    assert _c["SMTP"]["总数"] == 23 and _c["SMTP"]["已有 C 裁定"] == 22 \
        and _c["SMTP"]["待确认"] == 1
    assert RECON["total"]["总数"] == 57
    assert RECON["total"]["已有 C 裁定"] == 52
    assert RECON["total"]["待确认"] == 5


def test_all_57_rows_have_destination():
    _rs = RECON["rows"]
    assert len(_rs) == 57
    for _r in _rs:
        assert _r["★ 去向"], _r["candidate_id"]
        assert _r["★ 计入分类主分母"] in ("是", "否"), _r["candidate_id"]
    _in = sum(1 for _r in _rs if _r["★ 计入分类主分母"] == "是")
    assert _in == 52, _in


def test_r10_report_denominator_corrected_to_52():
    """★ R10 执行前检查报告的分母算术已由 R10A 修正。"""
    _t = (DELIV / "R10_正式指标执行前检查报告.md").read_text(encoding="utf-8")
    assert "| 合计 | 57 | **52** | 5 | **52** |" in _t
    assert "勘误" in _t


# ===== 原件未改 =====
def test_r7_preregistration_unchanged():
    assert hashlib.sha256(R7P.read_bytes()).hexdigest() == \
        "7cfa8430c4a1d07748bfbcc1fdb29fe12fdd034b2baa78c06bc4e73b40838a91"


def test_r3_baseline_unchanged():
    _h = hashlib.sha256(R3P.read_bytes()).hexdigest()
    assert _h == "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a"


def test_frozen_gold_baseline_present_after_r10b():
    """★ R10B 起门禁已通过 ⇒ 冻结基线已生成。"""
    _p = DELIV / "R10_跨协议Gold冻结基线.jsonl"
    assert _p.is_file()
    assert _p.stat().st_size > 0


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


def test_no_llm_calls_in_r10a():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r10a").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R10_5条共识待确认.xlsx", "R10_57条候选去向对账.xlsx",
               "R10A_共识裁定补录与分母勘误说明.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n
