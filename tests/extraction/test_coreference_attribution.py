# -*- coding: utf-8 -*-
"""M1-Q3-P0.7-A 验收测试：★ 指代主体归属核验。

★ 覆盖：明确主体不受影响 / 唯一先行词可解析 / 多先行词歧义 / 无先行词未解析 /
★       跨段指代 / 同上下文多字段 / 相邻义务不串 / 不得按「距离最近」推断。
"""
from __future__ import annotations

import pathlib

import pytest

from core.fused.extraction.coreference import (
    detect_coreference, resolve_subject_attribution,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SIP = ROOT / "kb/sip/spec/rfc3261.txt"
RTSP = ROOT / "kb/rtsp/spec/rfc2326.txt"


def _lines(p):
    return p.read_text(encoding="utf-8", errors="replace") \
        .replace("\r\n", "\n").split("\n")


# ══ ① 明确主体 ⇒ 不受影响 ══
def test_explicit_subject_unchanged():
    L = _lines(RTSP)
    _r = resolve_subject_attribution(
        lines=L, quote_span=[602, 603],
        quote="The server SHOULD list the methods it supports using the Public response header.",
        entity="server", subject="server")
    assert _r["status"] == "explicit_subject"
    assert detect_coreference(_r["reason"] or "") is None


# ══ ② 唯一先行词 ⇒ 可解析（★ 必验案例 @2747#1）══
def test_coreference_resolved_unique_antecedent():
    L = _lines(RTSP)
    _r = resolve_subject_attribution(
        lines=L, quote_span=[2776, 2777],
        quote="This field MUST be present in all requests and responses.",
        aux_evidence=[{"span": [2775, 2776],
                       "text": "The CSeq field specifies the sequence number for an RTSP request- response pair."}],
        entity="CSeq", subject="CSeq")
    assert _r["status"] == "coreference_resolved", _r
    assert _r["antecedents"]
    assert _r["antecedents"][0]["modifier"] == "CSeq"
    assert _r["antecedents"][0]["line"] == 2775
    assert 2775 in _r["evidence_lines"]      # ★ 有原文位置与证据链


# ══ ③ 多个可能先行词 ⇒ 歧义 ══
def test_coreference_ambiguous_multiple_antecedents():
    _L = [
        "   The Content-Length field specifies the length.",
        "   The CSeq field specifies the sequence number.",
        "   This field MUST be present in all requests and responses.",
    ]
    _r = resolve_subject_attribution(
        lines=_L, quote_span=[3, 3],
        quote="This field MUST be present in all requests and responses.",
        entity="CSeq", subject="CSeq")
    assert _r["status"] in ("coreference_ambiguous", "coreference_resolved")
    # ★ 两个同类型先行词 ⇒ 不得因「距离最近」而唯一确定 ⇒ ★ 歧义或按实体消歧
    assert len(_r["antecedents"]) >= 2


# ══ ④ 无先行词 ⇒ 未解析 ══
def test_coreference_unresolved_no_antecedent():
    _L = [
        "   This field MUST be present in all requests and responses.",
    ]
    _r = resolve_subject_attribution(
        lines=_L, quote_span=[1, 1],
        quote="This field MUST be present in all requests and responses.",
        entity="CSeq", subject="CSeq")
    assert _r["status"] == "coreference_unresolved"
    assert _r["antecedents"] == []


# ══ ⑤ 跨段指代 ⇒ 不跨段取先行词 ⇒ 未解析 ══
def test_cross_paragraph_coreference_not_resolved():
    _L = [""] * 30
    _L[0] = "   The CSeq field specifies the sequence number."
    _L[29] = "   This field MUST be present in all requests and responses."
    _r = resolve_subject_attribution(
        lines=_L, quote_span=[30, 30],
        quote="This field MUST be present in all requests and responses.",
        entity="CSeq", subject="CSeq")
    # ★ 先行词在 30 行之外 ⇒ **不得跨段取** ⇒ ⇒ 未解析
    assert _r["status"] == "coreference_unresolved"


# ══ ⑥ 同上下文多字段 ⇒ 不得按距离最近唯一确定 ══
def test_multiple_fields_not_by_distance():
    _L = [
        "   The Via field specifies the protocol version.",
        "   The CSeq field specifies the sequence number.",
        "   This field MUST be present in all requests and responses.",
    ]
    _r = resolve_subject_attribution(
        lines=_L, quote_span=[3, 3],
        quote="This field MUST be present in all requests and responses.",
        entity="Via", subject="Via")
    # ★ 「Via」虽是**更近**的，但「CSeq」也同类型 ⇒ ⇒ 不得仅凭距离唯一确定
    assert _r["status"] == "coreference_ambiguous"
    assert len(_r["antecedents"]) == 2


# ══ ⑦ 相邻义务不串（★ 主体不串到下一句）══
def test_adjacent_obligation_not_leaked():
    _L = [
        "   The UAS SHOULD NOT use this response unless it cannot provide any service.",
        "   The server SHOULD list the methods it supports using the Public header.",
    ]
    _r = resolve_subject_attribution(
        lines=_L, quote_span=[1, 1],
        quote="The UAS SHOULD NOT use this response unless it cannot provide any service.",
        entity="UAS", subject="UAS")
    assert _r["status"] == "explicit_subject"


# ══ ⑧ 指代表达识别 ══
@pytest.mark.parametrize("txt", [
    "This field MUST be present.",
    "This header MUST be present.",
    "It MUST be present.",
    "They SHOULD be sent.",
    "These requests MUST be sent.",
    "Such responses SHOULD be sent.",
])
def test_detect_coreference(txt):
    assert detect_coreference(txt) is not None


def test_detect_no_coreference():
    assert detect_coreference("The server SHOULD list the methods.") is None
