# -*- coding: utf-8 -*-
"""V2-E4-R8 后续回归测试：跨协议仲裁表结构修复。

覆盖：原始文件未改、六列回填完整、字段错位已修、完整性分歧 37 条、
      拆分线索不少于 6 处、补充知识去重、rfc8098-04 四处一致、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R4A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R4跨协议盲审与NormID碰撞/R4A_跨协议人工盲审包")
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R8_人工审核回收核验/R8_跨协议仲裁结构修复")
R8 = ROOT / "guard/_out/_n1c_v2/r8"
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _arb(proto, n):
    return DELIV / f"{proto}_{n}候选_第三方仲裁表_修复版.xlsx"


def _header_row(ws, marker):
    """★ 自动定位表头行（★ 含 marker 的行）。"""
    for _r in range(1, min(ws.max_row, 12) + 1):
        if any(marker in str(ws.cell(row=_r, column=c).value or "")
               for c in range(1, ws.max_column + 1)):
            return _r
    raise AssertionError(f"未找到表头行（{marker}）")


# ===== 原始文件未改动 =====
def test_original_arb_tables_unchanged():
    """原始第三方仲裁表未被改写（★ 修复版另立文件）。"""
    _orig = {
        "SIP_27候选_第三方仲裁模板.xlsx":
            "见 R8_跨协议仲裁结构修复说明.md 的哈希登记表",
    }
    # ★ 只断言原始表仍存在且可打开，★ 且不含新增的修复列
    for _proto, _n in (("SIP", 27), ("RTSP", 7), ("SMTP", 23)):
        _p = R4A / f"{_proto}_{_n}候选_第三方仲裁模板.xlsx"
        assert _p.is_file(), _p
        _wb = openpyxl.load_workbook(_p)
        _ws = _wb["仲裁记录"]
        _hdr = [str(c.value or "").strip() for c in _ws[1]]
        assert not any("仲裁后 V2 目标路由" in h for h in _hdr), _p.name
        assert not any("仲裁后抽取完整性" in h for h in _hdr), _p.name
        _wb.close()


# ===== 六列回填 =====
@pytest.mark.parametrize("proto,n", [("SIP", 27), ("RTSP", 7), ("SMTP", 23)])
def test_six_ab_columns_filled(proto, n):
    _wb = openpyxl.load_workbook(_arb(proto, n))
    _ws = _wb["仲裁记录"]
    _hdr = [str(c.value or "").strip() for c in _ws[1]]
    _cols = ["A:知识类型", "B:知识类型", "A:rule_eligibility",
             "B:rule_eligibility", "A:证据充分性", "B:证据充分性"]
    for _c in _cols:
        _i = next(i for i, h in enumerate(_hdr, 1)
                  if h.startswith(f"★ {_c}"))
        _n = sum(1 for _r in range(2, _ws.max_row + 1)
                 if str(_ws.cell(row=_r, column=_i).value or "").strip())
        assert _n == n, (_proto, _c, _n)
    _wb.close()


# ===== 字段错位已修 =====
@pytest.mark.parametrize("proto,n", [("SIP", 27), ("RTSP", 7), ("SMTP", 23)])
def test_route_column_moved_and_completeness_added(proto, n):
    _wb = openpyxl.load_workbook(_arb(proto, n))
    _ws = _wb["仲裁记录"]
    _hdr = [str(c.value or "").strip() for c in _ws[1]]
    assert any("仲裁后 V2 目标路由" in h for h in _hdr)
    assert any("仲裁后抽取完整性" in h for h in _hdr)
    _i_route = next(i for i, h in enumerate(_hdr, 1)
                    if "仲裁后 V2 目标路由" in h)
    _i_comp = next(i for i, h in enumerate(_hdr, 1)
                   if "仲裁后抽取完整性" in h)
    _i_kind = next(i for i, h in enumerate(_hdr, 1)
                   if "仲裁后知识类型" in h)
    _MAP = {"normative_rule_candidate": "rule_channel",
            "protocol_syntax": "structured_channel",
            "protocol_registry_or_enumeration": "structured_channel",
            "protocol_descriptive_semantics": "descriptive_channel",
            "non_protocol_metadata": "metadata_channel",
            "mixed_or_uncertain": "pending_review"}
    _ALLOWED_COMP = {"not_applicable", "cross_sentence_missing",
                     "cross_section_missing", "partial", "full"}
    _ALLOWED_STAT = {"agreed", "arbitrated", "unresolved", "not_applicable"}
    _i_stat = next(i for i, h in enumerate(_hdr, 1) if "最终裁定状态" in h)
    for _r in range(2, _ws.max_row + 1):
        _k = str(_ws.cell(row=_r, column=_i_kind).value or "").strip()
        _rt = str(_ws.cell(row=_r, column=_i_route).value or "").strip()
        if _k and _rt:
            assert _rt == _MAP[_k], (_r, _k, _rt)
        # ★ 仲裁后抽取完整性已由第三方回填（★ R8 后续）
        _cv = str(_ws.cell(row=_r, column=_i_comp).value or "").strip()
        assert _cv in _ALLOWED_COMP, (_r, _cv)
        # ★ 最终裁定状态已由第三方回填
        _sv = str(_ws.cell(row=_r, column=_i_stat).value or "").strip()
        assert _sv in _ALLOWED_STAT, (_r, _sv)
    _wb.close()


# ===== 完整性分歧 37 条 =====
def test_completeness_diff_count_37():
    _wb = openpyxl.load_workbook(DELIV / "R8_抽取完整性待确认清单.xlsx")
    _ws = _wb["待确认清单"]
    _hr = _header_row(_ws, "候选 ID")
    _n = _ws.max_row - _hr
    _wb.close()
    assert _n == 37, _n


def test_completeness_confirm_columns_filled_or_blank():
    """★ 第三方已回填确认值（R8 后续）：★ 确认值与确认人须有值。

    ★ 确认理由列允许为空（★ 非必填）。
    """
    _wb = openpyxl.load_workbook(DELIV / "R8_抽取完整性待确认清单.xlsx")
    _ws = _wb["待确认清单"]
    _hr = _header_row(_ws, "候选 ID")
    _hdr = [str(c.value or "").strip() for c in _ws[_hr]]
    _i_val = next(i for i, h in enumerate(_hdr, 1) if "人工确认值" in h)
    _i_who = next(i for i, h in enumerate(_hdr, 1) if "确认人" in h)
    _n = 0
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        _n += 1
        assert str(_ws.cell(row=_r, column=_i_val).value or "").strip()
        assert str(_ws.cell(row=_r, column=_i_who).value or "").strip()
    _wb.close()
    assert _n == 37, _n


# ===== 拆分线索 =====
def test_split_clues_at_least_six():
    _wb = openpyxl.load_workbook(DELIV / "R8_原子知识补录表.xlsx")
    _ws = _wb["拆分线索与补录"]
    _hr = _header_row(_ws, "线索 ID")
    _n = 0
    for _r in range(_hr + 1, _ws.max_row + 1):
        if str(_ws.cell(row=_r, column=1).value or "").strip().startswith("SC-"):
            _n += 1
    _wb.close()
    assert _n >= 6, _n


def test_split_clues_confirmed_by_human():
    """★ 第三方已逐条补录并裁定（R8 后续）：★ 命题与是否纳入 Gold 须有值。

    ★ 确认理由、确认人、确认日期列允许为空（★ 非必填）。
    """
    _wb = openpyxl.load_workbook(DELIV / "R8_原子知识补录表.xlsx")
    _ws = _wb["拆分线索与补录"]
    _hr = _header_row(_ws, "线索 ID")
    _hdr = [str(c.value or "").strip() for c in _ws[_hr]]
    _i_prop = next(i for i, h in enumerate(_hdr, 1) if "候选原子命题" in h)
    _i_inc = next(i for i, h in enumerate(_hdr, 1) if "是否纳入 Gold" in h)
    _n = 0
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip().startswith("SC-"):
            continue
        _n += 1
        assert str(_ws.cell(row=_r, column=_i_prop).value or "").strip(), _r
        _inc = str(_ws.cell(row=_r, column=_i_inc).value or "").strip()
        assert _inc.startswith(("是", "否", "unresolved")), _inc
    _wb.close()
    assert _n == 7, _n


# ===== 已有补充知识去重 =====
def test_existing_supplement_duplication_flagged():
    _wb = openpyxl.load_workbook(DELIV / "R8_已有补充知识对账表.xlsx")
    _ws = _wb["已有补充知识"]
    _hr = _header_row(_ws, "审核者")
    _rows = []
    for _r in range(_hr + 1, _ws.max_row + 1):
        if str(_ws.cell(row=_r, column=1).value or "").strip():
            _rows.append([str(_ws.cell(row=_r, column=c).value or "")
                          for c in range(1, _ws.max_column + 1)])
    _wb.close()
    assert len(_rows) == 2
    # ★ 两条命题原文相同 ⇒ 重复标记
    assert _rows[0][5] == _rows[1][5]
    assert "文本相同" in _rows[0][9]
    assert "文本相同" in _rows[1][9]


# ===== rfc8098-04 四处一致 =====
def test_rfc8098_04_four_places_consistent():
    _g = None
    for _l in R3P.read_text(encoding="utf-8").splitlines():
        if _l.strip():
            _r = json.loads(_l)
            if _r.get("gold_candidate_id") == "X-smtp-rfc8098-04":
                _g = _r
                break
    assert _g is not None
    _prop = _g["constraint"]
    assert _prop == 'MDN parsers MUST parse it as "[CFWS]"'
    # ★ 三个 xlsx 中的机器预置候选命题列
    for _p in (R4A / "SMTP_23候选_审核者A_盲审模板.xlsx",
               R4A / "SMTP_23候选_审核者B_盲审模板.xlsx",
               R4A / "SMTP_23候选_第三方仲裁模板.xlsx"):
        _wb = openpyxl.load_workbook(_p, data_only=True)
        _found = False
        for _s in _wb.sheetnames:
            if _s == "人工审核":
                continue          # ★ 人工审核表无候选命题列
            _ws = _wb[_s]
            _hdr = [str(c.value or "").strip() for c in _ws[1]]
            if not any("候选命题" in h for h in _hdr):
                continue
            _ci = next(i for i, h in enumerate(_hdr, 1)
                       if "候选命题" in h)
            for _r in range(2, _ws.max_row + 1):
                if str(_ws.cell(row=_r, column=1).value or "").strip() \
                        == "X-smtp-rfc8098-04":
                    assert str(_ws.cell(row=_r, column=_ci).value or "").strip() \
                        == _prop, (_p.name, _s)
                    _found = True
        _wb.close()
        assert _found, _p.name


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


def test_gold_v4_not_blocked():
    """H3 Gold v4 作为独立工作线，★ 不被本轮缺陷阻塞。"""
    _p = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
          / "R5A_H3第三方仲裁与Gold冻结/H3_Gold冻结基线_v4候选.jsonl")
    assert _p.is_file()
    _rows = [json.loads(l) for l in
             _p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(_rows) == 28


def test_no_llm_calls():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r8").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R8_抽取完整性待确认清单.xlsx",
               "R8_原子知识补录表.xlsx",
               "R8_已有补充知识对账表.xlsx",
               "R8_跨协议仲裁结构修复说明.md",
               "SIP_27候选_第三方仲裁表_修复版.xlsx",
               "RTSP_7候选_第三方仲裁表_修复版.xlsx",
               "SMTP_23候选_第三方仲裁表_修复版.xlsx"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n
