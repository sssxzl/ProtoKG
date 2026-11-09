# -*- coding: utf-8 -*-
"""core/fused/graph_schema.py —— 图模式加载与校验（2026-11-08 新增）。

★ 与 :mod:`core.fused` 里的 ``aspect_registry.json`` 并列：
    · aspect_registry 冻结「知识维度」（fact 的 aspect 契约）；
    · graph_schema 冻结「图结构」（节点类型 / 边类型 / 遍历配置）。

★ 核心设计：**判据一律来自 RFC 内容**；
  ``protocol_overrides`` 只是**加速定位的提示**，不是判据
  ⇒ 抽取逻辑不认协议名 ⇒ 换协议自动生效。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

#: 图模式的默认文件名（放在 core/fused/hub/registry/ 下，与 aspect_registry 同级）
SCHEMA_FILENAME = "graph_schema.json"


def schema_path() -> Path:
    """``core/fused/graph/graph_schema.json`` 的绝对路径。"""
    from core import paths
    # ★ 包内绝对路径（不依赖 cwd）
    return Path(__file__).resolve().parent / SCHEMA_FILENAME


@lru_cache(maxsize=1)
def load_graph_schema() -> dict[str, Any]:
    """读图模式注册表（带缓存）；文件缺失时返回**最小可用**模式。

    ★ 最小可用模式：保证「缺注册表也能跑」（便于单测与降级）。
    """
    p = schema_path()
    if not p.is_file():
        return {
            "core_version": "0.0-fallback",
            "node_types": [],
            "edge_types": [],
            "traversal": {},
            "community": {},
            "protocol_overrides": {},
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "core_version": "0.0-fallback",
            "node_types": [],
            "edge_types": [],
            "traversal": {},
            "community": {},
            "protocol_overrides": {},
        }


def node_types(graph: str = "") -> list[dict[str, Any]]:
    """某张图（``structure`` / ``semantic`` / ``both``）的节点类型列表。"""
    out = []
    for t in load_graph_schema().get("node_types") or []:
        g = str(t.get("graph") or "both")
        if not graph or graph == "both" or g == "both" or g == graph:
            out.append(t)
    return out


def edge_types(graph: str = "") -> list[dict[str, Any]]:
    """某张图的边类型列表。"""
    out = []
    for t in load_graph_schema().get("edge_types") or []:
        g = str(t.get("graph") or "both")
        if not graph or graph == "both" or g == "both" or g == graph:
            out.append(t)
    return out


def edge_type_names(graph: str = "") -> set[str]:
    """某张图的边类型**名字集合**（快速查）。"""
    return {str(t.get("name")) for t in edge_types(graph)}


def node_type_names(graph: str = "") -> set[str]:
    """某张图的节点类型名字集合。"""
    return {str(t.get("name")) for t in node_types(graph)}


def traversal() -> dict[str, list[str]]:
    """``retrieve_subgraph`` 的 BFS 边类型映射（**数据驱动**）。"""
    raw = load_graph_schema().get("traversal") or {}
    return {k: [str(x) for x in (v or [])]
            for k, v in raw.items() if k != "notes" and isinstance(v, list)}


def community_config() -> dict[str, Any]:
    """Leiden 社区检测的配置（含降级策略）。"""
    return dict(load_graph_schema().get("community") or {})


def protocol_hints(protocol: str) -> dict[str, list[str]]:
    """某协议的**提示**（状态名/消息名/定时器名）——仅加速定位，非判据。"""
    raw = (load_graph_schema().get("protocol_overrides") or {})
    over = raw.get(protocol.lower()) or {}
    return {k: [str(x) for x in (v or [])]
            for k, v in over.items() if k != "notes" and isinstance(v, list)}


def validate_schema() -> list[str]:
    """校验注册表自洽性 ⇒ 返回**问题列表**（空 = 通过）。

    ★ 这是**纯数据校验**，不依赖任何 RFC ⇒ 可在 CI 里跑。
    """
    problems: list[str] = []
    schema = load_graph_schema()
    if schema.get("core_version", "").endswith("fallback"):
        problems.append("graph_schema.json 缺失或不可读（用的是 fallback 模式）")
        return problems

    nt = {str(t.get("name")) for t in schema.get("node_types") or []}
    if not nt:
        problems.append("node_types 为空")
    for e in schema.get("edge_types") or []:
        ename = str(e.get("name") or "")
        if not ename:
            problems.append("有 edge_type 缺 name")
            continue
        for side in ("from", "to"):
            for src in e.get(side) or []:
                src = str(src)
                if src != "*" and src not in nt:
                    problems.append(f"边 {ename} 的 {side} 引用了未定义节点类型 {src}")
    # 遍历配置的边类型必须已定义
    for key, names in (schema.get("traversal") or {}).items():
        if key == "notes" or not isinstance(names, list):
            continue
        for n in names:
            if str(n) not in edge_type_names():
                problems.append(f"traversal.{key} 引用了未定义边类型 {n}")
    return problems


__all__ = [
    "SCHEMA_FILENAME", "schema_path", "load_graph_schema",
    "node_types", "edge_types", "edge_type_names", "node_type_names",
    "traversal", "community_config", "protocol_hints", "validate_schema",
]
