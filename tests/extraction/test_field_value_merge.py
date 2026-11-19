# -*- coding: utf-8 -*-
"""R27C：field_value 合并修复的**真实生产路径**回归。

这些用例直接调用 `core.fused.extraction.rfc_extractor._dedup_one` ——
即生产代码里协议级去重实际使用的那个函数，**不是**另写的模拟函数。

未应用 R27C 补丁时（`_dedup_one` 不存在）整体 skip，避免污染基线护栏。
"""
from __future__ import annotations

import pytest

from core.fused.extraction import norm as NM
from core.fused.extraction import rfc_extractor as RX

_dedup_one = getattr(RX, "_dedup_one", None)

pytestmark = pytest.mark.skipif(
    _dedup_one is None, reason="R27C field_value 补丁未应用（_dedup_one 不存在）")

SEP = RX.VALUE_SAMPLE_SEP


def _run(norms_in):
    """用生产函数逐条去重，返回最终 Norm 列表。"""
    merged_values, merged_anchor, seen, out = {}, {}, set(), []
    for n in norms_in:
        _dedup_one(dict(n), merged_values=merged_values,
                   merged_anchor=merged_anchor,
                   seen_protocol_level=seen, norms=out)
    return out


def _fv(nid, name, vals, source="file:a.txt#@1"):
    return {"norm_id": nid, "kind": "field_value", "name": name,
            "content": f"{name} | values: " + SEP.join(vals),
            "source": source, "kb_source_type": "rfc", "protocol": "p"}


def _vals(norm):
    body = str(norm.get("content") or "").split("| values:", 1)[-1]
    return [v.strip() for v in body.split(SEP) if v.strip()]


def test_three_values_merged_into_kept_norm():
    """同 norm_id 三个取值：最终保留的 Norm 必须拿到全部三个。"""
    out = _run([_fv("p.fv.accept", "Accept", ["a1"]),
                _fv("p.fv.accept", "Accept", ["a2"]),
                _fv("p.fv.accept", "Accept", ["a3"])])
    assert len(out) == 1
    assert _vals(out[0]) == ["a1", "a2", "a3"]
    assert out[0]["content"].startswith("Accept | values: ")


def test_different_norm_id_not_merged():
    """不同 norm_id 互不干扰。"""
    out = _run([_fv("p.fv.x", "Accept", ["x1"]),
                _fv("p.fv.y", "Content-Length", ["y1"]),
                _fv("p.fv.x", "Accept", ["x2"])])
    assert len(out) == 2
    assert _vals(out[0]) == ["x1", "x2"]
    assert _vals(out[1]) == ["y1"]


def test_single_value_unchanged():
    """单条记录完全不变。"""
    one = _fv("p.fv.single", "Date", ["s1"])
    out = _run([one])
    assert out[0]["content"] == one["content"]


def test_duplicate_values_deduped():
    """重复取值只保留一份。"""
    out = _run([_fv("p.fv.dup", "X", ["v1"]),
                _fv("p.fv.dup", "X", ["v1"]),
                _fv("p.fv.dup", "X", ["v2"])])
    assert _vals(out[0]) == ["v1", "v2"]


def test_source_not_overwritten():
    """不同来源支持同一字段：保留条来源不被后续条目覆盖。"""
    out = _run([_fv("p.fv.bcc", "Bcc", ["a"], "file:rfc1.txt#@10"),
                _fv("p.fv.bcc", "Bcc", ["b"], "file:rfc2.txt#@20")])
    assert out[0]["source"] == "file:rfc1.txt#@10"
    assert _vals(out[0]) == ["a", "b"]


def test_similar_names_stay_separate():
    """名称相似但 norm_id 不同：不合并。"""
    out = _run([_fv("p.fv.content_length", "Content-Length", ["1"]),
                _fv("p.fv.content.length", "Content.Length", ["2"])])
    assert len(out) == 2
    assert _vals(out[0]) == ["1"] and _vals(out[1]) == ["2"]


def test_merged_norm_maps_to_canonical_and_evidence():
    """合并后的 Norm 走 Canonical：Evidence 关联的是保留条来源。"""
    out = _run([_fv("p.fv.accept", "Accept", ["a1"], "file:rfc1.txt#@10"),
                _fv("p.fv.accept", "Accept", ["a2"], "file:rfc2.txt#@20")])
    facts = NM.map_norm_to_facts(out[0])
    assert facts, "合并后的 Norm 必须能映射为 Fact"
    ev = facts[0].claims[0].evidence
    ev = ev[0] if isinstance(ev, tuple) else ev
    assert ev.document == "file:rfc1.txt#@10"
    assert ev.evidence_id.startswith("e2_")
    assert ev.source_id == "p.fv.accept"


def test_lost_values_are_detected_if_regression_returns():
    """回归哨兵：若合并结果又写回被丢弃条目，本断言会失败。"""
    out = _run([_fv("p.fv.sentinel", "S", ["k1"]),
                _fv("p.fv.sentinel", "S", ["k2"]),
                _fv("p.fv.sentinel", "S", ["k3"])])
    assert set(_vals(out[0])) == {"k1", "k2", "k3"}
