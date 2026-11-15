# -*- coding: utf-8 -*-
"""M1-Q3-P0.6 回归测试：★ 规范证据**句界**恢复（★ 11 项）。

★ 只测证据构造；★ 不改 L1/L2 判定规则、Prompt、FactID、21 aspects。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from core.fused.extraction.normative_extract import (
    build_evidence, is_prose_line, is_sentence_end,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SIP = ROOT / "kb/sip/spec/rfc3261.txt"
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"


def _lines():
    return SIP.read_text(encoding="utf-8", errors="replace") \
        .replace("\r\n", "\n").split("\n")


def _ev(L, anchor, cs=None, ce=None):
    return build_evidence(L, {"resolved_span": anchor,
                              "chunk_start": cs, "chunk_end": ce})


# ══ 1 单句跨物理行 ══
def test_single_sentence_across_lines():
    L = _lines()
    _e = _ev(L, 10464, 10452, 10544)
    assert _e["quote_span"] == [10464, 10466]
    assert "did not understand" in _e["quote"]
    assert _e["degraded"] is False


# ══ 2 前后存在不同规范强度的相邻句 ══
def test_adjacent_different_strength_not_merged():
    L = _lines()
    _a = _ev(L, 10486, 10452, 10544)
    assert "SHOULD NOT" in _a["quote"]
    assert "SHOULD process" not in _a["quote"], _a["quote"]
    _b = _ev(L, 10488, 10452, 10544)
    assert "SHOULD process" in _b["quote"]
    assert "SHOULD NOT" not in _b["quote"], _b["quote"]


# ══ 3 SHOULD NOT 与 SHOULD 相邻 ⇒ 分别取句 ══
def test_should_not_and_should_separated():
    L = _lines()
    _e = _ev(L, 10486, 10452, 10544)
    assert _e["quote"].startswith("A UAS SHOULD NOT")
    _aux = _e["aux_evidence"]
    # ★ 10486 处的逻辑行从该行起（★ 前一行是空行）⇒ ⇒ 无前一句 ⇒ aux 为空是正确的
    assert _aux == [] or _aux[0]["kind"] == "prev_sentence"


# ══ 4 条件句跨行 ══
def test_conditional_sentence_across_lines():
    L = _lines()
    _e = _ev(L, 7161, 7187, 7250)
    assert _e["quote_span"] == [7160, 7161]
    assert "If timer D fires" in _e["quote"]
    assert "MUST move to the terminated state" in _e["quote"]


# ══ 5 图注 / 章节标题与正文相邻 ⇒ 不拼入 ══
def test_caption_not_merged():
    L = _lines()
    _e = _ev(L, 7161, 7187, 7250)
    assert "Figure 5" not in _e["quote"], _e["quote"]
    assert is_prose_line("Figure 5: INVITE client transaction") is False
    assert is_prose_line("12.4.1 Some Section") is False
    assert is_prose_line("   The server MUST do X.") is True


# ══ 6 引用章节编号与句内标点 ⇒ 不误切分 ══
def test_section_ref_and_punctuation_not_split():
    _t1 = "Proxy-Require (Section 20.29) or Require header"
    assert is_sentence_end(_t1, _t1.index(".")) is False      # ★ 章节引用
    _t2 = "the terminated state."
    assert is_sentence_end(_t2, _t2.rindex(".")) is True
    _t3 = "e.g. this is an example"
    assert is_sentence_end(_t3, _t3.index(".")) is False      # ★ 缩写
    _t4 = "value 3.14 is allowed"
    assert is_sentence_end(_t4, _t4.index(".")) is False      # ★ 小数点


# ══ 7 证据句跨 chunk 边界 ⇒ 允许跨块取证并记录 ══
def test_cross_chunk_recorded():
    L = _lines()
    _e = _ev(L, 7161, 7187, 7250)
    assert _e["cross_chunk"] is True
    assert "跨块取证" in _e["boundary_reason"]


# ══ 8 越界 / 句界无法确定 ⇒ 保守处理 ══
def test_out_of_range_and_unresolved_conservative():
    L = _lines()
    _e = build_evidence(L, {"resolved_span": None})
    assert _e["quote"] == "" and _e["degraded"] is True
    _e2 = build_evidence(L, {"resolved_span": 10 ** 6})
    assert _e2["quote_span"] is None or _e2["degraded"] is True


# ══ 9 六条历史相对恢复候选 ══
def test_frozen_6_relative_candidates():
    L = _lines()
    rows = [json.loads(l) for l in
            (FREEZE / "frozen_recoverable_13.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(rows) == 6
    for r in rows:
        _e = _ev(L, (r.get("resolved_span_relative") or r["raw_span"]), r["chunk_start"], r.get("chunk_end_estimate"))
        assert _e["quote"], r
        assert _e["quote_span"]


# ══ 10 二十九条历史拒收候选 ══
def test_frozen_29_rejected_candidates():
    L = _lines()
    rows = [json.loads(l) for l in
            (FREEZE / "frozen_rejected_29.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(rows) == 29
    _built = 0
    for r in rows:
        _e = _ev(L, (r.get("resolved_span_absolute") or r["raw_span"]), r["chunk_start"], r.get("chunk_end_estimate"))
        if _e["quote"]:
            _built += 1
    assert _built >= 20, f"★ 仅 {_built} 条能构造 quote"


# ══ 11 127 条历史绝对命中候选 ══
def test_frozen_127_absolute_candidates():
    blocks = [json.loads(l) for l in
              (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
              if l.strip()]
    _n_abs = 0
    for b in blocks:
        doc = ROOT / f"kb/{b['protocol']}/spec/{b['document']}"
        if not doc.is_file():
            continue
        L2 = doc.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        for it in b["raw_items"]:
            if it["entity_in_span_hit"] is None:
                continue
            _n_abs += 1
            _e = _ev(L2, it["span"], b["chunk_start"],
                     b["chunk_start"] + str(b.get("chunk_text") or "").count("\n"))
            assert _e["quote_span"] is not None, it
    assert _n_abs == 127, _n_abs
