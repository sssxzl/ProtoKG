# -*- coding: utf-8 -*-
"""core/fused/downstream/source_availability.py —— 五源分工的下游决策层。

统一回答「当前哪些源可用、该消费点用哪个策略」，实现优雅降级（有源则用、无源则退化）。
所有消费点（方法白名单 / 冲突消解 / 拓扑序）都问它，不自己判断，避免降级逻辑散落。

设计依据: docs/设计/各源设计/五源融合传导设计.md（五源融合传导方案 v16）。
协议无关：优先级表、白名单降级链均声明式，换协议零代码（未来下沉 profile）。
"""
from __future__ import annotations

from typing import Optional

#: 认识论优先级（声明式；observed=实测最可信，normative=规范，descriptive=推断/描述）。
#: 值域覆盖各抽取器实际产出：observed（traffic）、normative/must/normative_unspecified
#: （rfc，norm.py 的 RFC 2119 映射）、descriptive（source/expert_note/vuln）。
SOURCE_PRIORITY: dict[str, int] = {
    "observed": 3,
    "normative": 2,
    "must": 2,
    "normative_unspecified": 2,
    "descriptive": 1,
}


def available_sources(bundle: dict) -> set[str]:
    """本次参与的事实来源集合（P0 由 assemble_bundle 产出）。"""
    return set(bundle.get("available_sources") or [])


def source_priority() -> dict[str, int]:
    """冲突消解用的认识论优先级表。"""
    return dict(SOURCE_PRIORITY)


def has_source(bundle: dict, source: str) -> bool:
    """某源是否实际产出了 fact（按「实际产 fact」判定，防空源误判降级）。"""
    return source in available_sources(bundle)


def whitelist_methods(bundle: dict, profile: Optional[dict] = None, *,
                     use_profile_whitelist: bool = True) -> list[str]:
    """方法白名单：按降级链取「目标支持的方法」。

    降级链（过渡期，未来 traffic extractor 就绪后补 server_announce / observed_called）:
      1. profile.allowed_methods —— 手配白名单（当前最可靠，过渡期）
      2. observed ∪ declared    —— 实测观测（可靠子集）∪ 源码声明（全集）并集
      3. 兜底：全部已知方法

    全空则返回空列表（下游据此跳过种子生成并告警）。

    ★语义修正（2026-10-23，实证缺陷）：原「observed 非空就整体采用 observed」会让白名单
    缩水——observed 是 traffic 的**不完整实测子集**（实测覆盖率因协议而异, 如 rtsp 100%
    但 ftp 仅 24%）, 若 observed 非空就只用它, 低覆盖协议会从 42 个方法缩水到 10 个、
    漏掉 ABOR/APPE/STOR 等大量合法命令。
    observed 的价值是「确认某方法真实存在」，而非「限定白名单全集」；正确语义应为
    observed ∪ declared 并集，保证「源码声明的方法不漏 + 实测的方法必含」。
    """
    methods = bundle.get("methods") or {}

    # 1. profile 手配白名单（过渡期最可靠）
    #    ★ 批次 2.5（F6）：``profile.allowed_methods`` 是**源码侧**人工白名单
    #      （profile.note 自述「目标程序实际实现的方法子集」）⇒ 用它裁剪会
    #      砍掉 RFC 抽到的**真实方法**（rtsp 实测：ANNOUNCE/RECORD/REDIRECT）
    #      ⇒ ``use_profile_whitelist=False`` 时**跳过这一步**，
    #        改走第 2 步（observed ∪ declared ⇒ 来自 facts，随源集合自然变化）。
    if use_profile_whitelist:
        allowed = (profile or {}).get("allowed_methods")
        if allowed:
            return [m for m in allowed if m in methods]

    # 2. observed ∪ declared 并集（不缩水）：实测确认 + 源码声明全集
    declared = {m for m, info in methods.items() if info.get("declared_by")}
    observed = {m for m, info in methods.items() if info.get("observed_by")}
    union = declared | observed
    if union:
        return sorted(union)

    # 3. 兜底：全部已知方法（无 provenance 时）
    return sorted(methods)


__all__ = [
    "SOURCE_PRIORITY",
    "available_sources",
    "source_priority",
    "has_source",
    "whitelist_methods",
]
