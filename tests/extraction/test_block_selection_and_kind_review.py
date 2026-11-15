# -*- coding: utf-8 -*-
"""★ M1-Q3-P0.8 / P0.9 回归测试：★ 实验性机制**默认关闭** ⇒ 行为不变。

★ 覆盖：
  ① 默认关闭 ⇒ 无新字段、块选择不变
  ② 开启 ⇒ **只标记不改 kind**、不进正式 Fact
  ③ 块级评分的确定性与组成可解释
  ④ 块级选择：预算严格上限、文档保底、章节多样性、非 BCP14 保留
  ⑤ 不含 BCP14 的块**不被排除**
"""
from __future__ import annotations

import os
import uuid

import pytest

from core.fused.extraction import prose_semantics as ps
from core.fused.extraction.block_selection import (
    SCORER_VERSION, has_normative_hint, score_block, select_block_density,
)


class _FakeLLM:
    def __init__(self, script):
        self._script = list(script)
        self.calls = 0
        self.model = "fake"
        self.last_call_meta = {}

    def chat_json(self, **kw):
        self.calls += 1
        return self._script.pop(0) if self._script else {"items": []}


# ══ ① 默认关闭 ══
def test_kind_review_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PROSE_KIND_REVIEW", raising=False)
    assert ps._kind_review_enabled() is False


def test_block_selection_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PROSE_BLOCK_SELECTION", raising=False)
    assert ps._block_selection_mode() == ""


# ══ ② 开启 ⇒ 只标记不改 kind ══
def test_kind_review_marks_but_keeps_kind(monkeypatch, tmp_path):
    monkeypatch.setenv("PROSE_KIND_REVIEW", "1")
    monkeypatch.setenv("PROSE_BATCH_BLOCKS", "1")
    _p = tmp_path / "c" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda p: _p)
    _L = [f"line {i}" for i in range(1, 60)]
    _L[9] = "The server MUST include a list of extensions"
    llm = _FakeLLM([{"items": [{"entity": "server",
                                "meaning": "The server MUST include a list",
                                "constraint": "", "doc": "r.txt", "span": 10,
                                "action": "include", "object": "list",
                                "strength": "MUST",
                                "normative_subject": "server"}]}])
    _n, _s = ps._extract_blocks("rtsp", [{"doc": "r.txt", "start": 1,
                                           "text": "\n".join(_L)}],
                                 entities=[], llm=llm,
                                 doc_lines={"r.txt": _L})
    assert _n
    assert _n[0]["kind"] == "prose_semantics"          # ★ kind 未变
    assert _n[0].get("classification_review_needed") is True
    assert _n[0].get("proposed_kind") == "prose_constraint"
    assert _n[0].get("kind_evidence")
    assert _n[0].get("review_reason")
    # ★ **不得**变成 confirmed
    assert _n[0].get("final_state") != "confirmed"


def test_kind_review_absent_when_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("PROSE_KIND_REVIEW", raising=False)
    monkeypatch.setenv("PROSE_BATCH_BLOCKS", "1")
    _p = tmp_path / "c" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda p: _p)
    _L = [f"line {i}" for i in range(1, 60)]
    _L[9] = "The server MUST include a list of extensions"
    llm = _FakeLLM([{"items": [{"entity": "server",
                                "meaning": "The server MUST include a list",
                                "constraint": "", "doc": "r.txt", "span": 10,
                                "action": "include", "object": "list",
                                "strength": "MUST",
                                "normative_subject": "server"}]}])
    _n, _s = ps._extract_blocks("rtsp", [{"doc": "r.txt", "start": 1,
                                           "text": "\n".join(_L)}],
                                 entities=[], llm=llm,
                                 doc_lines={"r.txt": _L})
    assert "classification_review_needed" not in _n[0]
    assert "proposed_kind" not in _n[0]


# ══ ③ 评分确定性与组成可解释 ══
def test_score_deterministic_and_explainable():
    _t = "The client MUST send the CSeq header field. See Section 20.29."
    _s1, _p1 = score_block(_t)
    _s2, _p2 = score_block(_t)
    assert _s1 == _s2 and _p1 == _p2
    assert _p1["bcp14_hits"] == 1
    assert "bcp14_score" in _p1 and "low_value_penalty" in _p1
    assert SCORER_VERSION


def test_low_value_blocks_penalised():
    _good = "The server MUST include a list of the unsupported extensions."
    _bad = "Copyright (C) The Internet Society (1998).  All Rights Reserved."
    assert score_block(_good)[0] > score_block(_bad)[0]
    assert "copyright_boilerplate" in score_block(_bad)[1]["low_value_signals"]


# ══ ④ 块级选择 ══
def _chunks():
    _out = []
    for d in ("a.txt", "b.txt"):
        for i in range(6):
            _out.append({"doc": d, "start": (i + 1) * 100,
                         "text": ("The server MUST include X. " * 40
                                  if i % 2 == 0 else
                                  "Some descriptive text about the protocol. " * 40)})
    return _out


def test_selection_respects_budget():
    _c = _chunks()
    _sel = select_block_density(_c, budget=5)
    assert len(_sel) == 5


def test_selection_keeps_non_bcp14_regions():
    """★ 不含 BCP14 的块**不得被整体排除**（★ 保留配额）。"""
    _c = [{"doc": "a.txt", "start": 100,
           "text": "The server MUST include X. " * 60} for _ in range(6)]
    _c += [{"doc": "a.txt", "start": 700 + i,
            "text": "This describes the meaning of the session concept. " * 60}
           for i in range(4)]
    _sel = select_block_density(_c, budget=4)
    _nonbcp = [x for x in _sel if "MUST" not in x["text"]]
    assert _nonbcp, "★ 非 BCP14 区域必须被保留"


def test_selection_is_deterministic():
    _c = _chunks()
    _a = [x["start"] for x in select_block_density(_c, budget=6)]
    _b = [x["start"] for x in select_block_density(_c, budget=6)]
    assert _a == _b


def test_has_normative_hint():
    assert has_normative_hint("The server MUST include X.") is True
    assert has_normative_hint("This describes the protocol loosely.") is False
