# -*- coding: utf-8 -*-
"""V2-E4-R12 回归测试：Gold v3 候选与 R11 审核接收。

覆盖：审核已回填、v3 原子 6 条、两条被排除、两条改写、历史版本未覆盖、
      枚举合法、原件与生产隔离。
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
         / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R11D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R11_跨协议Gold原子边界复核与评估准入")
R11 = ROOT / "guard/_out/_n1c_v2/r11"
REVIEW = R11D / "R11_SC05SC06原子知识边界复核.xlsx"

V1 = DELIV / "R10_跨协议Gold冻结基线.jsonl"
V2 = DELIV / "R11_跨协议Gold冻结基线_v2候选.jsonl"
V3 = DELIV / "R12_跨协议Gold冻结基线_v3候选.jsonl"
SHA_V1 = "bbce8979138605160f9af1c1c72a8c6c3b4750f31f808e9f03e2548f4b2a57eb"
SHA_V2 = "0f9ab8350da73359153473aeb9428001f45441828482583a1d0fed8f4f6cc38b"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _review_rows():
    _wb = openpyxl.load_workbook(REVIEW, data_only=True)
    _ws = _wb["SC05SC06边界复核"]
    _hr = next(r for r in range(1, 20)
               if any("Gold ID" in str(_ws.cell(row=r, column=c).value or "")
                      for c in range(1, _ws.max_column + 1)))
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]

    def _find(sub):
        for i, h in enumerate(_hdr, 1):
            if sub in h:
                return i
    _i_id = _find("★ Gold ID")
    _i_ind = _find("是否应独立成条")
    _i_txt = _find("独立命题的准确文本")
    _i_who = _find("★ 审核者（")
    _i_date = _find("★ 审核日期（")
    _out = []
    for _r in range(_hr + 1, _ws.max_row + 1):
        _g = str(_ws.cell(row=_r, column=_i_id).value or "").strip()
        if not _g:
            continue
        _out.append({
            "gold_id": _g,
            "independent": str(_ws.cell(row=_r, column=_i_ind).value or "").strip(),
            "text": str(_ws.cell(row=_r, column=_i_txt).value or "").strip(),
            "who": str(_ws.cell(row=_r, column=_i_who).value or "").strip(),
            "date": str(_ws.cell(row=_r, column=_i_date).value or "").strip(),
        })
    _wb.close()
    return _out


# ===== 审核接收 =====
def test_review_fully_filled():
    _rs = _review_rows()
    assert len(_rs) == 4
    for _r in _rs:
        assert _r["independent"] in ("是", "否"), _r["gold_id"]
        assert _r["text"], _r["gold_id"]
        assert _r["who"], _r["gold_id"]
        assert _r["date"], _r["gold_id"]


def test_review_has_two_independent_two_not():
    _rs = _review_rows()
    _c = collections.Counter(r["independent"] for r in _rs)
    assert _c["是"] == 2
    assert _c["否"] == 2


# ===== v3 =====
def test_v3_counts():
    _v3 = _jl(V3)
    _c = [r for r in _v3 if r["gold_level"] == "candidate"]
    _a = [r for r in _v3 if r["gold_level"] == "atom"]
    assert len(_c) == 57
    assert len(_a) == 6
    assert len(_v3) == 63


def test_v3_excluded_ids_absent():
    _ids = {r["gold_id"] for r in _jl(V3)}
    assert "SMTP-ATOM-X-smtp-rfc3461-04-b" not in _ids
    assert "SMTP-ATOM-X-smtp-rfc6531-01-b" not in _ids


def test_v3_rewritten_fields():
    _v3 = {r["gold_id"]: r for r in _jl(V3)}
    _a = _v3["SMTP-ATOM-X-smtp-rfc3461-04-a"]
    assert _a["strength"] == "MAY"
    assert _a["polarity"] == "positive"
    _b = _v3["SMTP-ATOM-X-smtp-rfc6531-01-a"]
    assert _b["rule_eligibility"] == "ineligible"
    assert _b["strength"] == "not_applicable"
    assert _b["polarity"] == "not_applicable"


def test_v3_has_human_source_for_rewritten():
    _v3 = {r["gold_id"]: r for r in _jl(V3)}
    for _gid in ("SMTP-ATOM-X-smtp-rfc3461-04-a",
                 "SMTP-ATOM-X-smtp-rfc6531-01-a"):
        assert "R11" in _v3[_gid]["★ 人工来源"], _gid
        assert _v3[_gid]["★ 仲裁者"] == "A", _gid


def test_v3_gold_ids_unique():
    _ids = [r["gold_id"] for r in _jl(V3)]
    assert len(_ids) == len(set(_ids))


def test_v3_enumerations_legal():
    _K = {"non_protocol_metadata", "protocol_syntax",
          "protocol_registry_or_enumeration", "protocol_descriptive_semantics",
          "normative_rule_candidate", "mixed_or_uncertain"}
    _E = {"eligible", "ineligible", "uncertain", "not_applicable"}
    _R = {"rule_channel", "structured_channel", "metadata_channel",
          "descriptive_channel", "pending_review", "not_applicable"}
    for _r in _jl(V3):
        assert _r["knowledge_kind"] in _K, _r["gold_id"]
        assert _r["rule_eligibility"] in _E, _r["gold_id"]
        assert _r["target_route"] in _R, _r["gold_id"]


def test_v3_candidate_level_unchanged_from_v2():
    _v2 = {r["gold_id"]: r for r in _jl(V2) if r["gold_level"] == "candidate"}
    _v3 = {r["gold_id"]: r for r in _jl(V3) if r["gold_level"] == "candidate"}
    assert set(_v2) == set(_v3)
    for _k in _v2:
        for _f in ("knowledge_kind", "rule_eligibility", "target_route",
                   "extract_completeness", "status"):
            assert _v2[_k][_f] == _v3[_k][_f], (_k, _f)


# ===== 版本保护 =====
def test_v1_and_v2_unchanged():
    assert hashlib.sha256(V1.read_bytes()).hexdigest() == SHA_V1
    assert hashlib.sha256(V2.read_bytes()).hexdigest() == SHA_V2


def test_v3_is_candidate_not_frozen():
    for _r in _jl(V3):
        assert "v3 候选" in _r.get("★ 版本", ""), _r["gold_id"]


def test_deliverables_exist():
    for _n in ("R12_跨协议Gold冻结基线_v3候选.jsonl",
               "R12_Gold版本差异报告.xlsx",
               "R12_Gold最终冻结候选与差异说明.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


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


def test_no_llm_calls():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r11").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
