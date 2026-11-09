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

def graph_dir(protocol: str = "") -> Path:
    """``derived/graph/``（**GraphRAG 整理层**，与中枢 ``derived/hub/`` **并列**）。

    ★ 2026-11-08 重设计：图从中枢的**子目录**提到**并列层** ⇒
      中枢 = 知识本体（按分类），图 = 关系视图（按关系）。
    """
    from core import paths
    return paths.graph_root(protocol)


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

    # ★★ 阶段 D2：**name → entity_id** 索引（中枢视图提供）
    #   ⇒ 图与中枢可对齐（此前是两套命名 ⇒ P3 确诊缺陷）。
    _eid_by_name: dict = {}
    try:
        _eid_by_name = dict(bundle.get("entity_by_name") or {})
    except Exception:                                   # noqa: BLE001
        _eid_by_name = {}

    def add_node(nid: str, ntype: str, name: str, graph: str,
                 owner: str = "rfc", conf: str = "medium",
                 anchor: Optional[dict] = None) -> None:
        if nid in nodes:
            return
        nodes[nid] = {
            "node_id": nid, "type": ntype, "name": name, "graph": graph,
            "source_owner": owner, "confidence": conf,
            "defined_in": anchor or {},
            # ★ 图**共用一套** ⇒ 记录带协议（读取端按它过滤）
            "protocol": str(protocol).strip().lower(),
            # ★★ 阶段 D2：**entity_id** 指向中枢实体（C3 契约）
            #   ⇒ 图与中枢可对齐（此前是两套命名：图 ``entity:accept``
            #   vs 中枢 ``rtsp:header:accept``）。
            "entity_id": _eid_by_name.get(str(name or ""), ""),
        }

    def add_edge(etype: str, a: str, b: str, graph: str, label: str = "",
                 owner: str = "rfc", conf: str = "medium",
                 anchor: Optional[dict] = None) -> None:
        # ★ **丢弃空端点的边**（2026-11-08 实测）：散文迁移规则里源状态可能
        #   未知（``state:?``）⇒ 投影出 ``from=""`` 的边 ⇒ 路径检索时
        #   会产生**空节点**、纯度检查也失去意义。
        if not a or not b:
            return
        eid = f"{etype}:{a}->{b}" + (f":{label}" if label else "")
        if eid in edges:
            return
        edges[eid] = {
            "edge_id": eid, "type": etype, "from": a, "to": b, "graph": graph,
            "label": label, "source_owner": owner, "confidence": conf,
            "defined_in": anchor or {},
            # ★ 图**共用一套** ⇒ 记录带协议（读取端按它过滤）
            "protocol": str(protocol).strip().lower(),
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
    # ★ **owner 取真实来源**（2026-11-08 批次 5 修正）：
    #   原来**写死** ``owner="profile"`` ⇒ 但消解是 **RFC 优先**
    #   （`rag_seedgen._select_active_transitions`）
    #   ⇒ 中枢的 transitions 可能来自 **LLM（rfc）** ⇒ 图的 owner 标错
    #   ⇒ **图级纯度闸会把 RFC 来源的边当成 profile 拦掉**
    #   （实测：纯 RFC 口径下路径式种子 0 条）。
    # ⇒ 改用 ``bundle["transitions_by_source"]``（权威的逐条来源）。
    _tbs: dict[tuple, str] = {}
    for _src_name, _rows in (bundle.get("transitions_by_source") or {}).items():
        for _t in _rows or ():
            if isinstance(_t, (list, tuple)) and len(_t) >= 3:
                _tbs[(str(_t[0]), str(_t[1]), str(_t[2]))] = str(_src_name)

    def _owner_of(src: str, method: str, dst: str) -> str:
        return _tbs.get((src, method, dst), "profile")

    for t in (bundle.get("transitions") or []):
        if not (isinstance(t, (list, tuple)) and len(t) >= 3):
            continue
        src, method, dst = str(t[0]), str(t[1]), str(t[2])
        # ★ **状态节点补齐**（2026-11-08 实测修正）：中枢的 transitions 里
        #   可能出现**图里没有**的状态（如骨架的 ``Offered``，而 Phase A
        #   只从 RFC 抽出 RFC 出现过的状态）
        #   ⇒ 不补节点 ⇒ 迁移边的端点悬空 ⇒ 路径检索断链
        #   （实测 dhcpv4 的 ``state:offered`` 缺失 ⇒ 路径查询 0 条）。
        _own = _owner_of(src, method, dst)
        add_node(_nid("state", src), "state", src, "structure",
                 owner=_own, conf="high")
        add_node(_nid("state", dst), "state", dst, "structure",
                 owner=_own, conf="high")
        a, b = _nid("state", src), _nid("state", dst)
        add_edge("transitions_to", a, b, "structure", label="",
                 owner=_own, conf="high")
        if method:
            # ★ **`triggers` 边连「源状态」**（2026-11-08 实测修正）：
            #   语义应是「方法 M **触发** src → dst 这条迁移」⇒ 指向 **src**。
            #   ★ 之前连的是**目标状态** ⇒ 只能表达「到达 dst」，
            #     无法表达「从 src 离开」⇒ 路径枚举时方法与状态**错位**
            #     （实测得到 ``[DHCPREQUEST, DHCPOFFER, DHCPDISCOVER, DHCPNAK]``
            #       这种荒谬顺序 ⇒ 修好后是 ``[DHCPDISCOVER, DHCPOFFER,
            #       DHCPREQUEST, DHCPNAK]``）。
            add_edge("triggers", _nid("message", method), a, "structure",
                     label="", owner=_own, conf="high")
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
            # ★ **字段名归一**（2026-11-08 实测）：message_instances 的值
            #   可能是 ``('cseq', '5')`` 这样的 **(字段名, 取值)** 元组
            #   ⇒ 直接 str() 会把整个元组当节点名（实测产出
            #     ``entity:('cseq', '5')`` 这种垃圾节点 ⇒ 边端点悬空
            #     ⇒ 社区检测全部退化孤立）。
            #   ⇒ 只取**第一个元素**（字段名）。
            if isinstance(fname, (list, tuple)):
                if not fname:
                    continue
                fname = fname[0]
            fname = str(fname).strip()
            if not fname:
                continue
            add_edge("co_occurs", _nid("message", method),
                     _nid("entity", fname), "semantic",
                     owner="profile", conf="medium")

    # ---- 弱边：同方法的 required_headers（已在上面加过 required_by，
    #      这里补 co_occurs 以便未进 required_headers 的字段也有连接）----

    return list(nodes.values()), list(edges.values())


# ===========================================================================
# B1：图分层
# ===========================================================================

def split_by_graph(nodes: list[dict], edges: list[dict],
                   graph: str) -> tuple[list[dict], list[dict]]:
    """按 ``graph`` 字段分层（``structure`` = 精确图 / ``semantic`` = 社区图）。

    ★ **端点补全**（2026-11-08 实测）：社区图的边（``required_by`` /
      ``co_occurs``）的一端是 **message 节点**，而 message 节点在
      **structure 图**里 ⇒ 若只按 ``graph`` 字段切节点，边会**端点悬空**
      （实测 rtsp 的 36 条社区边全部悬空 ⇒ 社区检测退化成全孤立）。
    ⇒ 这里**补上被本层边引用到的端点节点**（不改它们的 graph 标记）。
    """
    ns = [n for n in nodes if n.get("graph") in (graph, "both")]
    es = [e for e in edges if e.get("graph") in (graph, "both")]
    have = {n["node_id"] for n in ns}
    need = set()
    for e in es:
        for side in ("from", "to"):
            nid = e.get(side)
            if nid and nid not in have:
                need.add(nid)
    if need:
        by_id = {n["node_id"]: n for n in nodes}
        for nid in sorted(need):
            n = by_id.get(nid)
            if n is not None:
                ns.append(n)
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


# ===========================================================================
# B2.1 / B2.4：图合并与**社区检测**（Leiden）
# ===========================================================================

def merge_multidigraph(nodes: list[dict], edges: list[dict]
                       ) -> tuple[list[dict], list[dict]]:
    """B2.1：合并成 **MultiDiGraph**（同对节点允许多条不同条件的边）。

    ★ 边的唯一性键 = ``(type, from, to, label)`` ⇒ 同对节点的不同条件**都保留**。
    ★ 节点按 ``node_id`` 去重（保留 confidence 更高者）。
    """
    nodes_out: dict[str, dict] = {}
    for n in nodes:
        nid = n["node_id"]
        prev = nodes_out.get(nid)
        if prev is None or (prev.get("confidence") == "medium"
                            and n.get("confidence") == "high"):
            nodes_out[nid] = dict(n)
    edges_out: dict[tuple, dict] = {}
    for e in edges:
        key = (e.get("type"), e.get("from"), e.get("to"), e.get("label", ""))
        edges_out.setdefault(key, dict(e))
    return list(nodes_out.values()), list(edges_out.values())


#: ★ **不参与社区划分**的边类型（2026-11-08 实测）
#:   ``defines``（协议 → 字段/状态码）是**归属边**（不是语义相似边）——
#:   它把**所有**字段连到协议节点 ⇒ 整图连通 ⇒ 社区检测必然只出 1 个社区
#:   （实测 rtsp 69 节点全部落进一个社区）。
#:   ⇒ 社区划分时排除它；但**保留在图里**（检索时仍可用）。
COMMUNITY_EXCLUDED_EDGE_TYPES: frozenset[str] = frozenset({"defines"})


def detect_communities(nodes: list[dict], edges: list[dict],
                       resolution: float = 1.0,
                       min_size: int = 2) -> tuple[list[list[str]], str]:
    """B2.4：**社区检测**（Leiden）⇒ 社区成员列表 + 实际用的算法名。

    ★ **三级降级**（实测：networkx 的 ``leiden_communities`` 只是
      **API 占位**，需 igraph / nx-cs 后端 ⇒ 不能依赖）：
      ① **Leiden**（若装了 igraph 等后端）
      ② **Louvain**（纯 Python；与 Leiden 同属 CPM 类模块度优化 ⇒ 效果接近）
      ③ **贪心模块度**（networkx 自带）
      ④ **连通分量**（兜底）
      ⇒ **零外部依赖也能跑**（只用 networkx）。
    ★ 只在**社区图**（semantic）上跑 ⇒ 状态机的精确边不会被社区切分打散（D2）。
    ★ 社区过小（< ``min_size``）的**合并到「未归类」**（不丢弃）。
    """
    ids = [n["node_id"] for n in nodes]
    if not ids:
        return [], "none"
    id_set = set(ids)
    # 只保留**两端都在节点集里**的边（投影后可能有悬挂端点）
    # ★ 且排除 ``COMMUNITY_EXCLUDED_EDGE_TYPES``（归属边 ⇒ 会把整图连成一片）
    usable = [e for e in edges
              if e.get("from") in id_set and e.get("to") in id_set
              and e.get("type") not in COMMUNITY_EXCLUDED_EDGE_TYPES]
    if not usable:
        return [[i] for i in ids], "isolated"

    # ---- 社区算法（**三级降级**，优先纯 Python ⇒ 零外部依赖）----
    try:
        import networkx as nx
    except ImportError:
        return [[i] for i in ids], "isolated"

    g = nx.MultiDiGraph()
    for n in nodes:
        g.add_node(n["node_id"], **{k: v for k, v in n.items()
                                    if k != "node_id"})
    for e in usable:
        g.add_edge(e["from"], e["to"], **{k: v for k, v in e.items()
                                         if k not in ("from", "to")})
    und = g.to_undirected()

    comms = None
    algo = "connected_components"
    # ① **Leiden**（最优，需 igraph / nx-cs 后端）
    try:
        comms = nx.community.leiden_communities(
            und, resolution=resolution, seed=42)
        algo = "leiden"
    except Exception:                           # noqa: BLE001
        comms = None
    # ② **Louvain**（纯 Python；与 Leiden 同属 CPM 类模块度优化 ⇒ 效果接近）
    if comms is None:
        try:
            comms = nx.community.louvain_communities(
                und, resolution=resolution, seed=42)
            algo = "louvain"
        except Exception:                       # noqa: BLE001
            comms = None
    # ③ **贪心模块度**（networkx 自带，无随机性）
    if comms is None:
        try:
            comms = nx.community.greedy_modularity_communities(und)
            algo = "greedy_modularity"
        except Exception:                       # noqa: BLE001
            comms = None
    # ④ **连通分量**（兜底）
    if comms is None:
        comms = list(nx.connected_components(und))
        algo = "connected_components"

    out: list[list[str]] = []
    for c in comms:
        members = sorted(c)
        if len(members) >= min_size:
            out.append(members)
    covered = {m for c in out for m in c}
    rest = sorted(set(ids) - covered)
    if rest:
        out.append(rest)          # ★ **不丢弃**（只标记未归类）
    return out, algo


def community_owner_mix(members: list[str], nodes: list[dict],
                        edges: list[dict]) -> dict[str, int]:
    """社区的**知识通道构成**（``owner_mix``）。

    ★ 融合点：GraphRAG 的社区摘要 + 知识通道台账 ⇒
      论文可用「按知识层分层的社区视图」（L1 规范层 / L2 实现层）。
    """
    member_set = set(members)
    mix: dict[str, int] = {}
    # ★ **只统计节点的 owner**（2026-11-08 实测修正）：
    #   若把**边**的 owner 也计入，``defines`` 边（owner=rfc，数量压倒性多）
    #   会把每个社区的 class 都压成 MIXED ⇒ 分类失去区分度。
    #   ⇒ owner 是**知识实体**的属性 ⇒ 只看节点。
    for n in nodes:
        if n["node_id"] in member_set:
            o = str(n.get("source_owner") or "rfc")
            mix[o] = mix.get(o, 0) + 1
    return dict(sorted(mix.items(), key=lambda kv: -kv[1]))


def community_class(mix: dict[str, int]) -> str:
    """社区的**知识层级**（L1 规范 / L2 实现 / MIXED）。

    ★ 判据：若贡献全部来自 ``rfc`` ⇒ L1（规范知识）；
      全部来自实现类源 ⇒ L2；混合 ⇒ MIXED。
    """
    if not mix:
        return "L1"
    total = sum(mix.values())
    rfc_n = mix.get("rfc", 0)
    if rfc_n == total:
        return "L1"
    if rfc_n == 0:
        return "L2"
    return "MIXED"


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

    def _dump(path: Path, rows: list[dict], pk: str) -> None:
        # ★ ★ **按协议替换**（2026-11-08 中枢重设计）：图**共用一套**
        #   ⇒ 保留**其它协议**的节点/边，只替换本协议的。
        _keep: list[dict] = []
        if path.is_file():
            for _ln in path.read_text(encoding="utf-8").splitlines():
                _ln = _ln.strip()
                if not _ln:
                    continue
                try:
                    _v = json.loads(_ln)
                except json.JSONDecodeError:
                    continue
                _kp = str(_v.get("protocol") or "").strip().lower()
                if _kp and _kp != pk:
                    _keep.append(_v)      # ★ 别的协议 ⇒ 保留
        _all = _keep + list(rows)
        with path.open("w", encoding="utf-8", newline="") as f:
            for r in sorted(_all, key=lambda x: x.get("node_id") or x.get("edge_id")):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    _pk = str(protocol).strip().lower()
    # ★ **统一补 protocol**（图共用一套 ⇒ 记录必须带协议才能过滤）。
    #   Phase A（rfc_graph）产出的节点/边也在这里补齐。
    for _r in list(nodes) + list(edges):
        if not str(_r.get("protocol") or "").strip():
            _r["protocol"] = _pk
    _dump(nodes_path(protocol), nodes, _pk)
    _dump(edges_path(protocol), edges, _pk)
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
        # ★ 图**共用一套** ⇒ 按协议过滤（否则读到别的协议的节点/边）
        _pk = str(protocol or "").strip().lower()
        if not _pk:
            return out
        return [v for v in out
                if (not str(v.get("protocol") or "").strip().lower())
                or str(v.get("protocol") or "").strip().lower() == _pk]
    return _load(nodes_path(protocol)), _load(edges_path(protocol))


__all__ = [
    "graph_dir", "nodes_path", "edges_path", "graph_meta_path",
    "project_bundle_to_graph", "split_by_graph", "graph_metrics",
    "isolated_nodes", "write_graph", "read_graph",
    "merge_multidigraph", "detect_communities", "community_owner_mix",
    "community_class",
]


