# -*- coding: utf-8 -*-
"""core/fused/downstream/protocol_flags.py —— 协议级**行为开关**（配置驱动）。

★ 存在的理由（2026-11-07，批次 1 / A1）：
  之前「CSeq 是否渲染成『序号 + 方法』」这个**协议语义**，是用协议名硬判的：

      cseq_with_method=(protocol == "sip")        # 7 处

  接入新协议时这就是"必须改代码"的一道墙。现在改成读
  ``profile.json`` 的 ``seedgen.cseq_with_method``：

      sip  → true   (RFC 3261 §8.1.1.7：CSeq = 序号 SP 方法)
      rtsp → false  (RFC 2326 §12.17：CSeq 只有序号)
      smtp → false  (无 CSeq 概念，纯防御)

★ 缺省行为：**未声明 = False**。这是安全的：需要 true 的协议必须显式声明，
  不会因为漏配置而意外拿到「序号 + 方法」的格式。

★ 本模块**只依赖 `core.paths` + json**，不 import 任何下游模块 ⇒ 无循环依赖，
  `edge_cover` / `generic_danger` / `boundary_probe` / `scripts/seedgen.py`
  都可以安全引用。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from core import paths

__all__ = ["cseq_with_method", "clear_profile_cache", "load_profile_section"]


#: 按协议缓存 profile（同一进程内 seeds 生成会反复问同一个问题）
_PROFILE_CACHE: dict[str, dict] = {}


def _load_profile_cached(protocol: str) -> dict:
    """读 ``fused_hub/targets/<protocol>/profile.json``（缓存；缺失 ⇒ 空 dict）。"""
    key = str(protocol or "").strip().lower()
    if key in _PROFILE_CACHE:
        return _PROFILE_CACHE[key]
    data: dict = {}
    try:
        p = paths.target_profile(key)
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError, AttributeError):
        data = {}
    if isinstance(data, dict):
        _PROFILE_CACHE[key] = data
        return data
    return {}


def clear_profile_cache() -> None:
    """清缓存（测试用：改了 profile.json 后需要重读）。"""
    _PROFILE_CACHE.clear()


def cseq_with_method(protocol: str,
                     profile: Optional[dict] = None) -> bool:
    """CSeq 是否渲染为 ``<序号> <方法>``。读 ``seedgen.cseq_with_method``，缺省 False。

    Args:
        protocol: 协议名（仅用于定位 ``profile.json``，**不是**行为判据）。
        profile: 已加载的 profile dict（调用方手上有就不用再读盘）。

    Returns:
        bool：``True`` ⇒ ``CSeq: 1 REGISTER``；``False`` ⇒ ``CSeq: 1``。
    """
    if isinstance(profile, dict):
        sg = profile.get("seedgen") or {}
    else:
        sg = _load_profile_cached(protocol).get("seedgen") or {}
    if not isinstance(sg, dict):
        return False
    return bool(sg.get("cseq_with_method"))


def load_profile_section(protocol: str, section: str,
                         *keys: str) -> Any:
    """读 ``profile.json`` 的某个**嵌套段**（协议无关的通用读取口）。

    用法::

        load_profile_section("rtsp", "vuln", "field_guidance")
        # ⇒ profile["vuln"]["field_guidance"]

    ★ 路径不存在 / 类型不对 ⇒ 返回 ``None``（不抛异常）⇒ 调用方自行取缺省。
    """
    node: Any = _load_profile_cached(protocol)
    for k in (section,) + tuple(keys):
        if not isinstance(node, dict):
            return None
        node = node.get(k)
        if node is None:
            return None
    return node
