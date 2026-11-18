# -*- coding: utf-8 -*-
"""★ N1-C / N2-B0 回归测试。

★ 覆盖：★ N1-C 冻结集完整性（★ 无重叠/无泄漏/证据完整）｜
★ 三态语义检查的判定与边界（★ supported/contradicted/uncertain）｜
★ ★ **uncertain 绝不产生 confirmed**｜★ 影子对照口径（★ pending ≠ 放行）｜
★ ★ **本轮 0 次 LLM 调用**
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计")
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
import sys
sys.path.insert(0, str(ROOT / "tests/_fixtures/n1c"))
from n2b0_tristate import (CONTRADICTED, SUPPORTED, UNCERTAIN,
                           semantic_support_tristate, field_state)


def _rows(p):
    return list(csv.DictReader(pathlib.Path(p).read_text(encoding="utf-8").splitlines()))


# ══ ① N1-C 冻结集 ══
def test_n1c_has_50_rows_and_same_ids():
    _a = _rows(DELIV / "N1-C_盲审标注表_A.csv")
    _b = _rows(DELIV / "N1-C_盲审标注表_B.csv")
    _c = _rows(DELIV / "N1-C_仲裁表.csv")
    assert len(_a) == len(_b) == len(_c) == 50
    assert {r["sample_id"] for r in _a} == {r["sample_id"] for r in _b} \
        == {r["sample_id"] for r in _c}


def test_n1c_no_overlap_with_n1a():
    _n1a = {json.loads(l)["sample_id"] for l in
            (N1B / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()}
    _n1c = {r["sample_id"] for r in _rows(DELIV / "N1-C_盲审标注表_A.csv")}
    assert not (_n1a & _n1c)
    assert len(_n1a | _n1c) == 100


def test_n1c_is_the_complete_remainder_of_frame():
    """★ N1-C 必须等于抽样框（100 条）中未被 N1-A 审核的**完整**剩余。"""
    _pop = [json.loads(l) for l in
            (ROOT / "guard/_out/n1r2/n1r2_population.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    _frame = {r["sample_id"] for r in _pop
              if r["★ 类别"] in ("audited", "not_sampled_in_frame")}
    _n1a = {json.loads(l)["sample_id"] for l in
            (N1B / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()}
    _n1c = {r["sample_id"] for r in _rows(DELIV / "N1-C_盲审标注表_A.csv")}
    assert len(_frame) == 100
    assert _frame - _n1a == _n1c


def test_n1c_blind_files_have_no_model_state_leak():
    """★ 盲审文件不得含模型状态 / 错误归因 / 建议结论。"""
    _leak = ("L2", "verdict", "final_state", "模型状态", "误确认", "误拒",
             "错误归因", "人工真值", "批次")
    for _n in ("N1-C_盲审标注表_A.csv", "N1-C_盲审标注表_B.csv"):
        _rows_ = _rows(DELIV / _n)
        for _r in _rows_:
            for _k in _r:
                if _k.startswith(("★ A:", "★ B:")):
                    continue
                for _w in _leak:
                    assert _w not in _k, f"{_n}:{_k}"


def test_n1c_evidence_columns_complete():
    for _r in _rows(DELIV / "N1-C_盲审标注表_A.csv"):
        assert _r["★ resolved_span"].strip(), _r["sample_id"]
        assert _r["★ RFC 原文上下文（锚点 ±6 行）"].strip(), _r["sample_id"]
        assert _r["★ 证据句（含 entity 的非空行）"].strip(), _r["sample_id"]
        assert _r["rfc_sha256"].strip(), _r["sample_id"]
        assert _r["chunk_id"].strip(), _r["sample_id"]


def test_n1c_label_columns_are_filled_and_valid():
    """★ **N1-C 独立评估阶段**：★ 标签列必须**已填**且**枚举合法**。

    ★ ★ 发放前阶段的对应断言是「标签列全空」（★ 见提交历史）；
    ★ ★ 现已由真实人类审核者填毕 ⇒ ★ 断言更新为「已填 + 合法」。
    """
    _fields = ["subject", "action", "object", "strength", "polarity",
               "condition", "exception", "evidence_support", "truth_label",
               "review_note"]
    _truth_ok = {"valid_confirmed", "valid_rejection",
                 "pending_insufficient_evidence", "uncertain_requires_human"}
    _sup_ok = {"supported", "partially_supported", "contradicted",
               "evidence_insufficient"}
    for _n, _tag in (("N1-C_盲审标注表_A.csv", "A"), ("N1-C_盲审标注表_B.csv", "B")):
        for _r in _rows(DELIV / _n):
            for _f in _fields:
                assert f"★ {_tag}:{_f}" in _r
            _t = (_r.get(f"★ {_tag}:truth_label") or "").strip()
            _e = (_r.get(f"★ {_tag}:evidence_support") or "").strip()
            assert _t, f"{_n}:{_r['sample_id']}:truth_label 未填"
            assert _t in _truth_ok, f"{_n}:{_r['sample_id']}:{_t}"
            assert _e, f"{_n}:{_r['sample_id']}:evidence_support 未填"
            assert _e in _sup_ok, f"{_n}:{_r['sample_id']}:{_e}"
            assert (_r.get(f"★ {_tag}:review_note") or "").strip(), \
                f"{_n}:{_r['sample_id']}:review_note 未填"
            assert (_r.get(f"★ {_tag}:审核者") or "").strip(), \
                f"{_n}:{_r['sample_id']}:审核者 未填"


def test_n1c_arbitration_table_has_required_audit_columns():
    _h = list(csv.DictReader((DELIV / "N1-C_仲裁表.csv")
                             .read_text(encoding="utf-8").splitlines()))[0].keys()
    assert "★ 仲裁者 ID（★ 匿名编号）" in _h
    assert "★ 审核日期" in _h
    assert "★ 仲裁理由" in _h


# ══ ② 三态语义检查 ══
def test_supported_when_all_fields_present():
    _v, _r, _s = semantic_support_tristate(
        "The server MUST include a list of extensions.",
        "include", "list of extensions", strength="MUST")
    assert _v == SUPPORTED
    assert _s["action"]["state"] == SUPPORTED


def test_supported_when_verb_form_differs():
    """★ ★ 词形差异（ignore vs ignores）⇒ ★ **supported**（★ 同一动作）。"""
    _v, _r, _s = semantic_support_tristate(
        "that server silently ignores the BOOTREQUEST message",
        "silently ignore", "BOOTREQUEST message", strength="")
    assert _v == SUPPORTED
    assert _s["action"]["state"] == SUPPORTED


def test_uncertain_when_verb_absent_from_evidence():
    """★ 候选动作**根本不在**证据中 ⇒ ★ uncertain（★ **不是** contradicted）。"""
    _v, _r, _s = semantic_support_tristate(
        "that server silently discards the BOOTREQUEST message",
        "return", "BOOTREQUEST message", strength="")
    assert _v == UNCERTAIN
    assert _s["action"]["state"] == UNCERTAIN


def test_uncertain_when_object_is_generated_long_description():
    """★ ★ 候选 object 是**模型生成的长描述**（★ 原文无此词组）⇒ ★ uncertain。"""
    _v, _r, _s = semantic_support_tristate(
        "the procedures for copyrights defined in the Internet Standards process",
        "follow", "the procedures for copyrights defined in the Internet Standards process",
        strength="MUST")
    assert _v == UNCERTAIN


def test_contradicted_only_on_explicit_counter_evidence():
    """★ ★ 只有存在**明确相反强度**时才判 contradicted。"""
    _v, _r, _s = semantic_support_tristate(
        "A server MUST NOT include this option.",
        "include", "option", strength="MUST")
    assert _v == CONTRADICTED
    assert _s["strength"]["state"] == CONTRADICTED


def test_uncertain_never_yields_confirmed():
    """★ ★ 三态**没有** confirmed 出口。"""
    for _q, _a, _o, _s in (
            ("some text without the action", "include", "x", "MUST"),
            ("A server MUST NOT include it", "include", "it", "MUST"),
            ("The server MUST include a list.", "include", "list", "MUST")):
        _v, _r, _st = semantic_support_tristate(_q, _a, _o, strength=_s)
        assert _v in (SUPPORTED, CONTRADICTED, UNCERTAIN)
        assert _v != "confirmed"


def test_legal_default_does_not_block():
    """★ ★ **合法缺省不构成阻塞**（★ 三个字段都无值 ⇒ ★ supported，★ 非 uncertain/contradicted）。"""
    _v, _r, _s = semantic_support_tristate("Some text.", "", "", strength="")
    assert _v == SUPPORTED
    assert all(v["state"] == UNCERTAIN for v in _s.values())
    # ★ ★ 但**有值而未命中**仍 ⇒ uncertain
    _v2, _r2, _s2 = semantic_support_tristate(
        "Some text.", "absent-action", "", strength="")
    assert _v2 == UNCERTAIN
    assert _s2["action"]["state"] == UNCERTAIN


def test_empty_quote_is_uncertain():
    _v, _r, _s = semantic_support_tristate("", "include", "x", strength="MUST")
    assert _v == UNCERTAIN


def test_strength_synonyms_expanded_beyond_production():
    """★ 三态的强度同义词集比生产更宽（★ SHOULD ⇒ recommended 等）。"""
    _v, _r, _s = semantic_support_tristate(
        "This behavior is recommended for all endpoints.",
        "behavior", "endpoints", strength="SHOULD")
    assert _v == SUPPORTED


# ══ ③ 影子对照口径 ══
def test_shadow_comparison_csv_has_all_50():
    _rows_ = _rows(DELIV / "N2-B0_原版与影子状态对照.csv")
    assert len(_rows_) == 50


def test_shadow_never_increases_confirmed():
    """★ ★ 影子不得引入新的 confirmed。"""
    for _r in _rows(DELIV / "N2-B0_原版与影子状态对照.csv"):
        assert _r["★ 是否引入新的 confirmed"] == "False"


def test_pending_is_not_a_release():
    """★ ★ 「rejected→pending」不构成错误确认（★ pending ≠ 放行）。"""
    _rows_ = _rows(DELIV / "N2-B0_原版与影子状态对照.csv")
    for _r in _rows_:
        assert _r["★ 错误恢复人工认定不成立（★ 影子放行口径）"] == "False"


def test_blocking_trace_has_required_fields():
    _rows_ = [json.loads(l) for l in
              (DELIV / "N2-B0_首个阻塞点逐条台账.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert _rows_
    for _r in _rows_:
        for _k in ("candidate_id", "truth_label", "first_blocking_stage",
                   "blocking_reason", "rejection_rule",
                   "deterministic_or_LLM", "proposed_action"):
            assert _k in _r, _k
        assert _r["deterministic_or_LLM"].startswith("★")


# ══ ④ 0 次 LLM ══
def test_no_llm_calls_in_this_stage():
    for _f in sorted((ROOT / "guard/_out/_n1c").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name
