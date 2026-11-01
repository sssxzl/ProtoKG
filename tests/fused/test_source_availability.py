"""tests/fused/test_source_availability.py —— 五源分工下游决策（方法白名单降级链）。

固化「方法白名单降级链」契约，尤其 2026-10-23 修复的「observed 非空就整体采用
导致白名单缩水」缺陷：observed 是 traffic 的**不完整实测子集**，只能用于确认
方法存在，不能限定白名单全集；正确语义是 observed ∪ declared 并集。
"""
from __future__ import annotations

from core.fused.downstream.source_availability import whitelist_methods


def _bundle(methods: dict) -> dict:
    return {"methods": methods}


def test_whitelist_prefers_profile_allowed():
    """第 1 步：profile.allowed_methods 存在时优先用它（并过滤掉 methods 里没有的）。"""
    b = _bundle({
        "A": {"declared_by": ["source"], "observed_by": ["traffic"]},
        "B": {"declared_by": ["source"]},
    })
    # allowed 里含一个 methods 里没有的 "X"，应被过滤掉
    wl = whitelist_methods(b, {"allowed_methods": ["A", "B", "X"]})
    assert wl == ["A", "B"]


def test_whitelist_union_not_shrink_when_observed_partial():
    """★修复契约：observed 只是 declared 的子集时，白名单不能缩水到 observed。

    原缺陷：observed 非空就返回 observed，会把「declared 声明但未实测观测到」的方法
    漏掉（ftp 实证：observed 10/42，白名单从 42 缩水到 10）。修复后应返回
    observed ∪ declared 并集 = 全部声明 + 实测确认的方法。
    """
    b = _bundle({
        "A": {"declared_by": ["source"], "observed_by": ["traffic"]},  # 声明 + 实测
        "B": {"declared_by": ["source"]},                              # 仅声明（未实测）
        "C": {"observed_by": ["traffic"]},                             # 仅实测（补充）
    })
    wl = whitelist_methods(b, {})  # 无 profile → 走降级链
    assert wl == ["A", "B", "C"], f"并集应含 A/B/C，实际 {wl}"


def test_whitelist_declared_only_fallback():
    """只有 declared（无 observed、无 profile）时返回 declared 全集。"""
    b = _bundle({
        "A": {"declared_by": ["source"]},
        "B": {"declared_by": ["rfc"]},
    })
    wl = whitelist_methods(b, {})
    assert wl == ["A", "B"]


def test_whitelist_empty_when_no_provenance():
    """无 profile、无 declared、无 observed → 兜底返回全部已知方法（非空则不缩水）。"""
    b = _bundle({"A": {}, "B": {}})
    wl = whitelist_methods(b, {})
    assert wl == ["A", "B"]


def test_whitelist_empty_bundle():
    """空 methods → 空白名单。"""
    assert whitelist_methods(_bundle({}), {}) == []
