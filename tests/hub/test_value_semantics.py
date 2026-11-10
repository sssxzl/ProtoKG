# -*- coding: utf-8 -*-
"""tests/hub/test_value_semantics.py —— **值形态与比较语义**（阶段 N-1）。

★ 为什么有这个用例
  旧契约层（``property_registry.json`` / ``comparison_policy.json`` /
  ``phase_a.py``）曾声明「9 种 normalizer + 9 种 comparator」，但**零实现**；
  该契约层已随重构移除 ⇒ 那份声明的载体不存在了。

  ⇒ 但**结构化 value 已经落地**（实测中枢：``struct`` 278 条 claim、
  ``set`` 117 条 ⇒ 占全部 claim 的 25%）⇒ 旧 backlog §1.4 警告的风险
  「**结构化 value 一旦落地，比较语义可能不完整**」**已经实际发生**。

  ⇒ 本用例锁定中枢**实际使用**的四种 value 形态的比较语义：
    · ``set`` / list ⇒ **无序**（顺序无关）
    · ``struct`` 的 ``fields`` / ``headers`` ⇒ **无序**
    · ``struct`` 的 ``trigger_sequence`` 等 ⇒ **有序**（序列语义不被破坏）
    · ``text`` / ``pattern`` / ``scalar`` ⇒ 原样相等
"""
from __future__ import annotations

import pytest

from core.fused.downstream.resolver import (
    UNORDERED_STRUCT_FIELDS,
    _normalize_value,
    _value_eq,
)


def _claim(data, vtype="struct"):
    """构造一个 claim（``_value_eq`` 期望的形态：``{"value": {...}}``）。"""
    return {"value": {"type": vtype, "data": data}}


# ===========================================================================
# ① set / list：无序
# ===========================================================================

def test_set_order_irrelevant():
    a = _claim(["a", "b"], "set")
    b = _claim(["b", "a"], "set")
    assert _value_eq(a, b), "set 的元素顺序不应影响相等判定"


def test_set_different_content_not_equal():
    a = _claim(["a", "b"], "set")
    b = _claim(["a", "c"], "set")
    assert not _value_eq(a, b)


def test_bare_list_treated_as_unordered():
    """``type`` 不是 set 但 ``data`` 是 list ⇒ 同样按无序比较（沿用旧行为）。"""
    a = _claim(["x", "y"], "text")
    b = _claim(["y", "x"], "text")
    assert _value_eq(a, b)


# ===========================================================================
# ② struct.fields / struct.headers：无序
# ===========================================================================

def test_struct_fields_order_irrelevant():
    """★ 消息实例的**字段集合** ⇒ 字段顺序不同应判为**相等**。"""
    a = _claim({"fields": [{"name": "url", "value": "rtsp://x/y"},
                           {"name": "CSeq", "value": "1"}]})
    b = _claim({"fields": [{"name": "CSeq", "value": "1"},
                           {"name": "url", "value": "rtsp://x/y"}]})
    assert _value_eq(a, b), "struct.fields 的字段顺序不应影响相等判定"


def test_struct_fields_missing_field_not_equal():
    """★ 少一个字段 ⇒ **不等**（不能因为「包含关系」而判等）。"""
    a = _claim({"fields": [{"name": "url", "value": "x"},
                           {"name": "CSeq", "value": "1"}]})
    b = _claim({"fields": [{"name": "url", "value": "x"}]})
    assert not _value_eq(a, b)


def test_struct_fields_different_value_not_equal():
    a = _claim({"fields": [{"name": "url", "value": "x"}]})
    b = _claim({"fields": [{"name": "url", "value": "y"}]})
    assert not _value_eq(a, b)


def test_struct_headers_order_irrelevant():
    """★ 必填头清单（``required_headers``）⇒ 头顺序不应影响相等判定。"""
    a = _claim({"headers": ["CSeq", "Transport"]})
    b = _claim({"headers": ["Transport", "CSeq"]})
    assert _value_eq(a, b)


# ===========================================================================
# ③ struct 的**有序**字段：序列语义不得被破坏
# ===========================================================================

def test_trigger_sequence_order_matters():
    """★ ``trigger_sequence`` 是**序列** ⇒ 顺序不同必须判为**不等**。

    ★ 这是「不做一刀切无序化」的关键守卫：
      若把 struct 整体当集合 ⇒ 触发序列会被当集合 ⇒ **语义被破坏**。
    """
    a = _claim({"action": "assert_seq", "trigger_sequence": ["SETUP", "PLAY"]})
    b = _claim({"action": "assert_seq", "trigger_sequence": ["PLAY", "SETUP"]})
    assert not _value_eq(a, b), "触发序列的顺序有语义 ⇒ 不应判等"


def test_unordered_fields_list_is_explicit_and_minimal():
    """★ 无序化字段清单必须**显式且最小** ⇒ 防止将来误加有序字段。"""
    assert "fields" in UNORDERED_STRUCT_FIELDS
    assert "headers" in UNORDERED_STRUCT_FIELDS
    # ★ 有序字段**不得**出现在清单里
    for ordered in ("trigger_sequence", "operand", "streams"):
        assert ordered not in UNORDERED_STRUCT_FIELDS, \
            f"{ordered} 有顺序语义 ⇒ 不得无序化"


# ===========================================================================
# ④ 标量形态：原样相等
# ===========================================================================

@pytest.mark.parametrize("vtype,data", [
    ("text", "OPTIONS"),
    ("pattern", "Status-Line"),
    ("scalar", True),
    ("scalar", 42),
])
def test_scalar_like_types_compare_exactly(vtype, data):
    a = _claim(data, vtype)
    b = _claim(data, vtype)
    assert _value_eq(a, b)
    c = _claim("__different__", vtype)
    assert not _value_eq(a, c)


# ===========================================================================
# ⑤ 归一函数本身的契约
# ===========================================================================

def test_normalize_value_returns_comparable_form():
    """★ ``_normalize_value`` 的输出可直接 ``==`` 比较。"""
    n = _normalize_value({"type": "set", "data": ["b", "a"]})
    assert n == ["a", "b"]
    n2 = _normalize_value({"type": "struct",
                            "data": {"fields": [{"n": 2}, {"n": 1}]}})
    assert n2["fields"] == ["{'n': 1}", "{'n': 2}"]


def test_normalize_value_passthrough_for_unknown():
    """★ 未知形态 ⇒ 原样返回（不猜、不丢）。"""
    v = {"type": "weird", "data": {"x": 1}}
    assert _normalize_value(v) == {"x": 1}
    assert _normalize_value(None) is None
