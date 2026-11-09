# -*- coding: utf-8 -*-
"""tests/fused/_v2_compat.py —— **v2 记录结构**的测试兼容辅助（阶段 C2/D1）。

★ 背景：
  阶段 C2 给中枢 fact **新增**了三个字段（**纯增量**）：
    · ``entity``    —— 实体引用（entity_id + participants）
    · ``epistemic`` —— fact 级四档判据
    · ``entity_id`` —— 顶层实体 id
  并把 ``resolution`` 从 ``null`` 补成实际内容。

★ 于是「**旧布局 vs 新布局**」的 bundle 比对会**不等**
  （旧布局的 fact 没有这些字段）⇒ 需要在比对前**剥离**。

★ 这**不是**放宽标准：被比对的仍是**旧契约的全部内容**
  （16 个桶、键序、值逐字节一致）⇒ 只是把 C2 的**新增字段**排除在外。
"""
from __future__ import annotations

from typing import Any

#: 阶段 C2 新增的字段（顶层）
C2_TOP_FIELDS = ("entity", "epistemic", "entity_id")

#: 阶段 D1 新增的 bundle 键
D1_VIEW_KEYS = ("by_category", "entities")


def strip_c2(fact: dict[str, Any]) -> dict[str, Any]:
    """把一条 fact 的 **C2 新增字段**剥掉（``resolution`` 还原为 ``null``）。"""
    if not isinstance(fact, dict):
        return fact
    out = dict(fact)
    for k in C2_TOP_FIELDS:
        out.pop(k, None)
    if out.get("resolution") is not None:
        out["resolution"] = None
    return out


def strip_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """把 bundle 里的 **C2 新增字段 + D1 新增键**剥掉 ⇒ 回到「旧契约」形态。"""
    if not isinstance(bundle, dict):
        return bundle
    out: dict[str, Any] = {}
    for k, v in bundle.items():
        if k in D1_VIEW_KEYS:
            continue
        if isinstance(v, dict):
            _nv = {}
            for _bk, _bv in v.items():
                if isinstance(_bv, dict) and "all_claims" in _bv:
                    _nv[_bk] = strip_c2(_bv)
                elif isinstance(_bv, list) and _bv and isinstance(_bv[0], dict) \
                        and "all_claims" in _bv[0]:
                    _nv[_bk] = [strip_c2(x) for x in _bv]
                else:
                    _nv[_bk] = _bv
            out[k] = _nv
        elif isinstance(v, list) and v and isinstance(v[0], dict) \
                and "all_claims" in v[0]:
            out[k] = [strip_c2(x) for x in v]
        else:
            out[k] = v
    return out


__all__ = ["C2_TOP_FIELDS", "D1_VIEW_KEYS", "strip_c2", "strip_bundle"]
