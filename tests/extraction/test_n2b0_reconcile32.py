# -*- coding: utf-8 -*-
"""★ N2-B0 联合验收补充：★ 影子状态 **32 条对账**的回归测试。

★ 覆盖：★ 对账全集恰为 32 且唯一 ID｜★ 原版 confirmed/pending/rejected 完整闭合｜
★ 影子路由合计闭合｜★ 每条含路由/是否真执行 LLM/是否待人工/是否允许发布｜
★ ★ 15 条原 pending 的去向**不得遗漏**｜★ 根因标签为**多标签**（★ 非互斥）
"""
from __future__ import annotations

import csv
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计")
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")


def _rows(p):
    return list(csv.DictReader(pathlib.Path(p).read_text(encoding="utf-8").splitlines()))


def _rec():
    return _rows(DELIV / "N2-B0_影子状态32条对账.csv")


def test_reconciliation_universe_is_exactly_32_unique_ids():
    _r = _rec()
    assert len(_r) == 32
    _ids = [x["candidate_id"] for x in _r]
    assert len(set(_ids)) == 32


def test_original_distribution_closes():
    import collections
    _c = collections.Counter(x["★ 原版状态"] for x in _rec())
    assert _c["confirmed"] == 3
    assert _c["pending"] == 15
    assert _c["rejected"] == 14
    assert sum(_c.values()) == 32


def test_shadow_routes_close_to_32():
    import collections
    _c = collections.Counter(x["★ 路由去向"] for x in _rec())
    assert sum(_c.values()) == 32
    assert set(_c) == {"★ rejected", "★ pending", "★ routed_to_LLM"}


def test_every_row_has_required_dimensions():
    for _r in _rec():
        assert _r["★ 路由去向"] in ("★ rejected", "★ pending", "★ routed_to_LLM")
        assert _r["★ 是否真正执行 LLM"] == "★ 否（★ 影子阶段不调 LLM）"
        assert _r["★ 是否仍待人工审核"] in ("是", "否")
        assert _r["★ 是否允许发布"].startswith("★ 否")


def test_no_row_is_allowed_to_publish():
    for _r in _rec():
        assert "否" in _r["★ 是否允许发布"]


def test_original_pending_fifteen_all_accounted():
    """★ ★ 15 条原 pending 的去向**不得遗漏**。"""
    import collections
    _p = [x for x in _rec() if x["★ 原版状态"] == "pending"]
    assert len(_p) == 15
    _c = collections.Counter(x["★ 路由去向"] for x in _p)
    assert sum(_c.values()) == 15


def test_original_rejected_fourteen_routes():
    import collections
    _r = [x for x in _rec() if x["★ 原版状态"] == "rejected"]
    assert len(_r) == 14
    _c = collections.Counter(x["★ 路由去向"] for x in _r)
    assert sum(_c.values()) == 14
    # ★ 按已冻结判据：★ 1 rejected + 7 pending + 6 routed_to_LLM
    assert _c["★ rejected"] == 1
    assert _c["★ pending"] == 7
    assert _c["★ routed_to_LLM"] == 6


def test_pending_change_and_human_burden_are_five():
    """★ ★ 口径一致后：★ pending 15→10（-5）｜人工负担 -5（★ 非 -7）。"""
    _r = _rec()
    _new_pending = sum(1 for x in _r if x["★ 路由去向"] == "★ pending")
    assert _new_pending == 10
    _human = sum(1 for x in _r if x["★ 是否仍待人工审核"] == "是")
    assert _human == 10


def test_potential_llm_call_delta_is_nine():
    """★ 潜在 LLM 调用：影子 19 vs 原版实际 10 ⇒ +9。"""
    _r = _rec()
    _shadow = sum(1 for x in _r if x["★ 路由去向"] == "★ routed_to_LLM")
    assert _shadow == 19
    _orig = sum(1 for x in _r if x["★ 原版状态"] == "confirmed")
    _orig += sum(1 for x in _r if x["★ 原版状态"] == "rejected"
                 and x["★ 原确定性 verdict"] == "支持")
    assert _orig == 10
    assert _shadow - _orig == 9


def test_errata_document_records_the_three_fixes():
    _t = (DELIV / "N2-B0_勘误_影子状态对账修正.md").read_text(encoding="utf-8")
    assert "1 rejected ＋ 7 pending ＋ 6 routed_to_LLM" in _t
    assert "15 → 10（-5）" in _t
    assert "可重叠多标签" in _t
    assert "仅在「本次未执行 LLM 的影子阶段」成立" in _t


def test_original_reports_are_preserved_with_errata_pointer():
    """★ ★ 原报告保留（★ 追加勘误指引，★ 不删原文）。"""
    for _f in ("N2-B0_恢复收益与错误放行风险.md",
               "N1-C-N2-B0_联合验收报告.md"):
        _t = (DELIV / _f).read_text(encoding="utf-8")
        assert "勘误指引" in _t, _f


def test_root_cause_labels_are_multi_label_not_exclusive():
    """★ 根因 A/B/C 为**可重叠多标签**（★ 计数之和 > 样本数）。"""
    _s = json.loads((ROOT / "guard/_out/n1c/n2b0_reconcile32.json")
                    .read_text(encoding="utf-8"))
    _m = _s["★ ⑦ 根因 A/B/C 互斥性"]
    assert "可重叠多标签" in _m["★ 声明"]
    _combos = _m["★ 多标签组合"]
    assert sum(_combos.values()) == 13
    assert any("+" in k for k in _combos)


def test_twelve_of_thirteen_denominator_difference_explained():
    _s = json.loads((ROOT / "guard/_out/n1c/n2b0_reconcile32.json")
                    .read_text(encoding="utf-8"))
    _d = _s["★ ⑧ 12/13 与 14 的分母差异"]
    assert _d["★ 原 rejected（全部 32 条有状态口径）"] == 14
    assert _d["★ 其中人工判 valid_confirmed"] == 13
    assert _d["★ 其中人工判 valid_rejection"] == 1
    assert "12" in _d["★ 12/13 的含义"]


def test_no_llm_calls_in_this_stage():
    for _f in sorted((ROOT / "guard/_out/_n1c").glob("p06*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t
        assert "chat_json" not in _t
