# -*- coding: utf-8 -*-
"""core/fused/graph_ops.py —— 图的**投影 / 分层 / 度量**（2026-11-08 新增）。

★ 职责（批次 1）：
  B0  把中枢的 16 个桶**投影**成显式属性图（节点 + 边）；
  B1  把图**分层**：精确图（structure）/ 社区图（semantic）；
  +   图质量度量（孤立节点比 / 最大连通分量比）。

★ 核心设计：**单向投影**（图 ⇐ 桶，桶 ⇐ 图）
  ⇒ 图是**派生视图**，中枢本身**完全不动** ⇒ 下游（bundle / seedgen / edge_cover）
    **零改动**。
  ★ 桶侧不回写图 ⇒ 不存在「两处判据分裂」。

★ 边的来源映射（**协议无关**，按中枢桶的语义）：
  ┌────────────────────────┬──────────────────────────────┐
  │ 中枢桶                  │ 图中的表示                     │
  ├────────────────────────┼──────────────────────────────┤
  │ methods                 │ 节点 message                    │
  │ headers                 │ 节点 entity                     │
  │ statuses                │ 节点 status                     │
  │ transitions             │ 边 transitions_to + triggers    │
  │ required_headers        │ 边 required_by                  │
  │ message_instances       │ 边 instance_of                  │
  │ method_sequences        │ 边 followed_by                  │
  │ precondition 等         │ 边 constrained_by               │
  │ legal_boundary 等       │ 边 bounded_by                   │
  │ security / vuln_pattern │ 边 marked_by                    │
  └────────────────────────┴──────────────────────────────┘
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from core.fused.graph_schema import edge_type_names, node_type_names

# ===========================================================================
# 落盘路径
# ===========================================================================

def graph_dir(protocol: str) -> Path:
    """``derived/per_source/<协议>/graph/``。"""
    from core import paths
    return paths.per_source_root(protocol) / "graph"


def nodes_path(protocol: str) -> Path:
    return graph_dir(protocol) / "nodes.jsonl"


def edges_path(protocol: str) -> Path:
    return graph_dir(protocol) / "edges.jsonl"


def graph_meta_path(protocol: str) -> Path:
    return graph_dir(protocol) / "graph_meta.json"


# ===========================================================================
# B0：中枢 → 图的投影
# ===========================================================================

def _nid(kind: str, name: str) -> str:
    import re
    return f"{kind}:{re.sub(r'\\s+', '_', str(name).strip()).lower()}"


def project_bundle_to_graph(bundle: dict[str, Any],
                            protocol: str = "") -> tuple[list[dict], list[dict]]:
    """把中枢的 bundle（16 桶）**投影**成 (nodes, edges)。

    ★ 只读 bundle ⇒ **中枢零改动**。
    ★ 每个节点/边带三个正交标注：``source_owner`` / ``confidence`` /
      ``defined_in``（与中枢台账同构）。
    """
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(nid: str, ntype: str, name: str, graph: str,
                 owner: str = "rfc", conf: str = "medium",
                 anchor: Optional[dict] = None) -> None:
        if nid in nodes:
            return
        nodes[nid] = {
            "node_id": nid, "type": ntype, "name": name, "graph": graph,
            "source_owner": owner, "confidence": conf,
            "defined_in": anchor or {},
        }

    def add_edge(etype: str, a: str, b: str, graph: str, label: str = "",
                 owner: str = "rfc", conf: str = "medium",
                 anchor: Optional[dict] = None) -> None:
        eid = f"{etype}:{a}->{b}" + (f":{label}" if label else "")
        if eid in edges:
            return
        edges[eid] = {
            "edge_id": eid, "type": etype, "from": a, "to": b, "graph": graph,
            "label": label, "source_owner": owner, "confidence": conf,
            "defined_in": anchor or {},
        }

    # ---- 节点 ----
    for m, info in (bundle.get("methods") or {}).items():
        add_node(_nid("message", m), "message", m, "structure",
                 owner="rfc", conf="high")
    for h in (bundle.get("headers") or {}):
        add_node(_nid("entity", h), "entity", h, "semantic",
                 owner="rfc", conf="medium")
    for st in (bundle.get("statuses") or {}):
        name = st[0] if isinstance(st, (list, tuple)) and st else str(st)
        add_node(_nid("status", name), "status", name, "semantic",
                 owner="rfc", conf="medium")

    # ---- 边 ----
    # transitions：三元组 (src_state, method, dst_state) ⇒ 拆两条边
    for t in (bundle.get("transitions") or []):
        if not (isinstance(t, (list, tuple)) and len(t) >= 3):
            continue
        src, method, dst = str(t[0]), str(t[1]), str(t[2])
        a, b = _nid("state", src), _nid("state", dst)
        add_edge("transitions_to", a, b, "structure", label="",
                 owner="profile", conf="high")
        if method:
            add_edge("triggers", _nid("message", method), b, "structure",
                     label="", owner="profile", conf="high")
            add_node(_nid("message", method), "message", method, "structure",
                     owner="rfc", conf="high")

    # required_headers：method → header
    for m, hs in (bundle.get("required_headers") or {}).items():
        for h in (hs or []):
            add_edge("required_by", _nid("message", m), _nid("entity", h),
                     "semantic", owner="profile", conf="high")

    # method_sequences：相邻对
    for pair in (bundle.get("method_sequences") or []):
        if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
            continue
        add_edge("followed_by", _nid("message", pair[0]),
                 _nid("message", pair[1]), "semantic",
                 owner="traffic", conf="medium")

    # message_instances：迁移 → 消息实例
    for key in (bundle.get("message_instances") or {}):
        if not (isinstance(key, (list, tuple)) and len(key) >= 3):
            continue
        src, method, dst = str(key[0]), str(key[1]), str(key[2])
        add_edge("instance_of", _nid("message", method),
                 _nid("state", dst), "structure", owner="profile", conf="high")

    # ---- 协议级 defines 边（协议 → 字段/状态码）----
    #   ★ headers 桶里的字段多数来自 **协议级** aspect
    #     （header/definition | syntax | value_enum）⇒ 不属于任何方法
    #     ⇒ 必须连到**协议节点**，否则在图里全是孤立的
    #     （实测 rtsp 78 节点里 65 个孤立，孤立比 0.83）。
    _proto_nid = _nid("entity", protocol or "protocol")
    if protocol:
        add_node(_proto_nid, "entity", protocol, "semantic",
                 owner="profile", conf="high")
    for h in (bundle.get("headers") or {}):
        add_edge("defines", _proto_nid, _nid("entity", h), "semantic",
                 owner="rfc", conf="medium")
    for st in (bundle.get("statuses") or {}):
        name = st[0] if isinstance(st, (list, tuple)) and st else str(st)
        add_edge("defines", _proto_nid, _nid("status", name), "semantic",
                 owner="rfc", conf="medium")

    # ---- 弱边 co_occurs：把「可能出现的头字段」织进图 ----
    #   ★ **社区图的结构基础**（实测）：headers 桶里 rtsp 有 58 个字段，
    #     但 required_headers 只覆盖 10 条 ⇒ 48 个字段节点**全是孤立的**
    #     ⇒ 孤立节点比 0.83（RFC-RAG-Agent 参照 0.1408）。
    #   ⇒ 用「同方法的消息实例里出现过的字段」做弱连接。
    for key, fields in (bundle.get("message_instances") or {}).items():
        if not (isinstance(key, (list, tuple)) and len(key) >= 3):
            continue
        method = str(key[1])
        for fname in (fields or []):
            if not fname:
                continue
            add_edge("co_occurs", _nid("message", method),
                     _nid("entity", str(fname)), "semantic",
                     owner="profile", conf="medium")

    # ---- 弱边：同方法的 required_headers（已在上面加过 required_by，
    #      这里补 co_occurs 以便未进 required_headers 的字段也有连接）----

    return list(nodes.values()), list(edges.values())


# ===========================================================================
# B1：图分层
# ===========================================================================

def split_by_graph(nodes: list[dict], edges: list[dict],
                   graph: str) -> tuple[list[dict], list[dict]]:
    """按 ``graph`` 字段分层（``structure`` = 精确图 / ``semantic`` = 社区图）。"""
    ns = [n for n in nodes if n.get("graph") in (graph, "both")]
    es = [e for e in edges if e.get("graph") in (graph, "both")]
    return ns, es


# ===========================================================================
# 图质量度量
# ===========================================================================

def graph_metrics(nodes: list[dict], edges: list[dict]) -> dict[str, Any]:
    """图质量指标：孤立节点比 / 最大连通分量比 / 节点度数分布。

    ★ 参照区间（RFC-RAG-Agent 在 RFC 2131 上的实测）：
      ``isolated_node_ratio`` ≈ 0.1408
      ``largest_connected_component_ratio`` ≈ 0.8002
    ★ 这两个是**诊断量**，不是通过/不通过闸。
    """
    n_total = len(nodes)
    if n_total == 0:
        return {"node_count": 0, "edge_count": 0,
                "isolated_node_ratio": 0.0,
                "largest_connected_component_ratio": 0.0,
                "degree_histogram": {}}
    deg: dict[str, int] = {n["node_id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["node_id"]: [] for n in nodes}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in deg:
            deg[a] += 1
        if b in deg:
            deg[b] += 1
        if a in adj and b in adj:
            adj[a].append(b)
            adj[b].append(a)

    isolated = [nid for nid, d in deg.items() if d == 0]
    # 连通分量（无向，迭代 DFS）
    seen: set[str] = set()
    largest = 0
    for start in adj:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        size = 0
        while stack:
            cur = stack.pop()
            size += 1
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        largest = max(largest, size)

    hist: dict[str, int] = {}
    for d in deg.values():
        k = str(d)
        hist[k] = hist.get(k, 0) + 1
    return {
        "node_count": n_total,
        "edge_count": len(edges),
        "isolated_node_count": len(isolated),
        "isolated_node_ratio": round(len(isolated) / n_total, 4),
        "largest_connected_component_ratio": round(largest / n_total, 4),
        "degree_histogram": dict(sorted(hist.items(), key=lambda kv: int(kv[0]))),
    }


def isolated_nodes(nodes: list[dict], edges: list[dict]) -> list[str]:
    """度为 0 的节点 id（**只标记不删除** ⇒ 避免掩盖箭头解析缺陷）。"""
    deg: dict[str, int] = {n["node_id"]: 0 for n in nodes}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in deg:
            deg[a] += 1
        if b in deg:
            deg[b] += 1
    return [nid for nid, d in deg.items() if d == 0]


# ===========================================================================
# 落盘
# ===========================================================================

def write_graph(protocol: str, nodes: list[dict], edges: list[dict],
                extra_meta: Optional[dict] = None) -> dict[str, Path]:
    """把图落盘到 ``derived/per_source/<协议>/graph/``。"""
    d = graph_dir(protocol)
    d.mkdir(parents=True, exist_ok=True)

    def _dump(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            for r in sorted(rows, key=lambda x: x.get("node_id") or x.get("edge_id")):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    _dump(nodes_path(protocol), nodes)
    _dump(edges_path(protocol), edges)
    meta = {"protocol": protocol, "metrics": graph_metrics(nodes, edges)}
    if extra_meta:
        meta.update(extra_meta)
    meta["isolated_nodes"] = isolated_nodes(nodes, edges)
    graph_meta_path(protocol).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"nodes": nodes_path(protocol), "edges": edges_path(protocol),
            "meta": graph_meta_path(protocol)}


def read_graph(protocol: str) -> tuple[list[dict], list[dict]]:
    """读回落盘的图。"""
    def _load(p: Path) -> list[dict]:
        if not p.is_file():
            return []
        out = []
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                out.append(json.loads(ln))
        return out
    return _load(nodes_path(protocol)), _load(edges_path(protocol))


__all__ = [
    "graph_dir", "nodes_path", "edges_path", "graph_meta_path",
    "project_bundle_to_graph", "split_by_graph", "graph_metrics",
    "isolated_nodes", "write_graph", "read_graph",
]
