# -*- coding: utf-8 -*-
"""core/fused/graph_query.py —— Phase D：**图检索**（2026-11-08 新增）。

★ GraphRAG 的检索**不应**是「向量 top-k 段落」，而应是在**图上游走**。
  本模块提供三种检索模式（对应整合方案 §五 D.1）：

  ┌──────────────┬──────────────────────────────────────────┐
  │ 模式          │ 语义                                      │
  ├──────────────┼──────────────────────────────────────────┤
  │ **M1 邻域**   │ 给定状态/方法 ⇒ 返回 k-hop 邻居            │
  │ **M2 路径**   │ 给定 (from, to) ⇒ 枚举所有简单路径         │
  │ **M3 社区**   │ 给定查询 ⇒ 返回相关社区及其报告             │
  └──────────────┴──────────────────────────────────────────┘

★ **边类型是数据驱动的**（``graph_schema.json`` 的 ``traversal`` 段）
  ⇒ 加边类型**不改本文件、不改调用方**。

★ **图级纯度闸**（D.3）：路径上的每条边的 ``source_owner`` 必须
  ``owner_allowed(owner, source_set)`` ⇒ 路径式种子天然受纯度约束
  （比单边检查更强：整条路径都必须干净）。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from core.fused.graph_schema import traversal

#: 路径枚举的**默认深度上限**（防止组合爆炸）
DEFAULT_MAX_DEPTH = 8

#: 路径枚举的**默认条数上限**
DEFAULT_MAX_PATHS = 32


# ===========================================================================
# 图的加载
# ===========================================================================

def load_graph(protocol: str) -> tuple[list[dict], list[dict]]:
    """读回该协议的显式图（``nodes.jsonl`` / ``edges.jsonl``）。"""
    from core.fused.graph_ops import read_graph
    return read_graph(protocol)


def build_adjacency(edges: list[dict],
                    edge_types: Optional[Iterable[str]] = None
                    ) -> dict[str, list[tuple[str, dict]]]:
    """建**邻接表**（无向视图：检索时关系方向不重要，路径才用有向边）。

    Args:
        edges: 边列表。
        edge_types: 只用这些边类型；``None`` ⇒ 全部。
    """
    allow = {str(t) for t in edge_types} if edge_types is not None else None
    adj: dict[str, list[tuple[str, dict]]] = {}
    for e in edges:
        if allow is not None and str(e.get("type")) not in allow:
            continue
        a, b = e.get("from"), e.get("to")
        if not a or not b:
            continue
        adj.setdefault(a, []).append((b, e))
        adj.setdefault(b, []).append((a, e))
    return adj


# ===========================================================================
# M1：k-hop 邻域检索
# ===========================================================================

def retrieve_neighborhood(nodes: list[dict], edges: list[dict],
                          seeds: Iterable[str],
                          k_hops: int = 2,
                          edge_types: Optional[Iterable[str]] = None
                          ) -> dict[str, Any]:
    """M1：从 ``seeds`` 出发做 **k-hop** 邻域检索（结构化导航）。

    ★ 与 ``rag_seedgen.retrieve_subgraph`` 的区别：
      那个走 **bundle 的 16 桶**（边类型硬编码在函数里）；
      这个走**显式图**（边类型**数据驱动**）⇒ 可扩展。
    ★ 返回的 ``subgraph`` 形如 ``retrieve_subgraph`` 的返回（同结构 ⇒ 可替换）。
    """
    seed_set = {str(s) for s in seeds if s}
    if not seed_set:
        return {"nodes": [], "edges": [], "node_ids": set(), "edge_keys": set()}

    adj = build_adjacency(edges, edge_types)
    node_ids = set(seed_set)
    edge_keys: set[tuple] = set()
    frontier = set(seed_set)
    for _ in range(max(1, k_hops)):
        nxt: set[str] = set()
        for nid in frontier:
            for other, e in adj.get(nid, ()):
                edge_keys.add(_edge_key(e))
                if other not in node_ids:
                    nxt.add(other)
        node_ids |= nxt
        frontier = nxt
        if not frontier:
            break
    sel_edges = [e for e in edges if _edge_key(e) in edge_keys]
    sel_nodes = [n for n in nodes if n.get("node_id") in node_ids]
    return {
        "nodes": sel_nodes,
        "edges": sel_edges,
        "node_ids": node_ids,
        "edge_keys": edge_keys,
    }


def _edge_key(e: dict) -> tuple:
    """边的唯一键（与 ``merge_multidigraph`` 一致）。"""
    return (e.get("type"), e.get("from"), e.get("to"), e.get("label", ""))


# ===========================================================================
# B3.1：**图驱动**的子图检索（边类型数据驱动）
# ===========================================================================

def retrieve_subgraph_graph(nodes: list[dict], edges: list[dict],
                            target_methods: Optional[list[str]] = None,
                            target_states: Optional[list[str]] = None,
                            k_hops: int = 2,
                            traversal_map: Optional[dict] = None
                            ) -> dict[str, Any]:
    """**图驱动**的子图检索（边类型来自 ``graph_schema.traversal``）。

    ★ 与 ``rag_seedgen.retrieve_subgraph`` 的分工：
      · 那个走 **bundle 的 16 桶**（边类型硬编码在函数里）⇒ 服务既有消费链；
      · 这个走**显式图**（边类型**数据驱动**）⇒ 加边类型**不改代码**。
    ★ **两者并存**（实测依据）：图里的 ``transitions_to`` 边**不带 method**
      （method 在 ``triggers`` 边上）⇒ 原地改旧函数会让 ``transitions``
      三元组变形 ⇒ 破坏既有消费链 ⇒ 保留旧函数不动。

    Returns:
        ``{"nodes", "edges", "methods", "states", "headers",
          "transitions", "method_sequences"}``
        —— ``transitions`` 是**重建的三元组** ``(src, method, dst)``。
    """
    tr = traversal_map if traversal_map is not None else traversal()
    allow_types = {str(t) for lst in tr.values() for t in lst}

    # ---- 种子：方法节点 / 状态节点 ----
    seeds: set[str] = set()
    tm = {str(m).upper() for m in (target_methods or []) if m}
    ts = {str(s).lower() for s in (target_states or []) if s}
    for n in nodes:
        nid = str(n.get("node_id") or "")
        name = str(n.get("name") or "")
        if tm and name.upper() in tm and n.get("type") == "message":
            seeds.add(nid)
        elif ts and name.lower() in ts and n.get("type") == "state":
            seeds.add(nid)
    if not seeds:
        return {"nodes": [], "edges": [], "methods": [], "states": [],
                "headers": [], "transitions": [], "method_sequences": []}

    nb = retrieve_neighborhood(nodes, edges, seeds, k_hops=k_hops,
                               edge_types=allow_types)
    sel_nodes = nb["nodes"]
    sel_edges = nb["edges"]
    node_ids = nb["node_ids"]

    # ---- 重建三元组：(src_state, method, dst_state) ----
    trig: dict[tuple[str, str], str] = {}
    for e in sel_edges:
        if e.get("type") != "triggers":
            continue
        f = str(e.get("from") or "")
        t = str(e.get("to") or "")
        if ":" in f:
            trig[(t, f.split(":", 1)[1])] = f.split(":", 1)[1]
    transitions: list[tuple[str, str, str]] = []
    for e in sel_edges:
        if e.get("type") != "transitions_to":
            continue
        a, b = str(e.get("from") or ""), str(e.get("to") or "")
        m = trig.get((b, a)) or str(e.get("label") or "")
        sa = a.split(":", 1)[1] if ":" in a else a
        sb = b.split(":", 1)[1] if ":" in b else b
        transitions.append((sa, m, sb))

    methods, states, headers = [], [], []
    for n in sel_nodes:
        t = str(n.get("type") or "")
        name = str(n.get("name") or "")
        if t == "message":
            methods.append(name)
        elif t == "state":
            states.append(name)
        elif t in ("header", "entity"):
            headers.append(name)

    seq_edges = [(e.get("from"), e.get("to")) for e in sel_edges
                 if e.get("type") == "followed_by"]
    method_sequences = [(a.split(":", 1)[1] if ":" in str(a) else str(a),
                         b.split(":", 1)[1] if ":" in str(b) else str(b))
                        for a, b in seq_edges]

    return {
        "nodes": sel_nodes,
        "edges": sel_edges,
        "methods": sorted(set(methods)),
        "states": sorted(set(states)),
        "headers": sorted(set(headers)),
        "transitions": sorted(set(transitions)),
        "method_sequences": method_sequences,
    }


# ===========================================================================
# M2：路径查询
# ===========================================================================

def find_paths(nodes: list[dict], edges: list[dict],
               from_state: str, to_state: str,
               max_depth: int = DEFAULT_MAX_DEPTH,
               max_paths: int = DEFAULT_MAX_PATHS,
               edge_types: Optional[Iterable[str]] = None,
               source_set: Optional[set[str]] = None,
               ) -> list[dict[str, Any]]:
    """M2：枚举 ``from_state → to_state`` 的**所有简单路径**。

    ★ **纯度闸**（D.3）：若给了 ``source_set`` ⇒ 路径上**每条边**的
      ``source_owner`` 都必须 ``owner_allowed`` ⇒ 整条路径干净。

    Returns:
        ``[{"nodes": [...], "edges": [...], "methods": [...], "length": n}, ...]``
    """
    by_id = {n["node_id"]: n for n in nodes}
    # 有向邻接（路径必须尊重方向：state → state 的迁移方向有意义）
    out_adj: dict[str, list[tuple[str, dict]]] = {}
    for e in edges:
        if edge_types is not None and str(e.get("type")) not in edge_types:
            continue
        a, b = e.get("from"), e.get("to")
        if not a or not b:
            continue
        out_adj.setdefault(a, []).append((b, e))

    src, dst = str(from_state), str(to_state)
    if src not in by_id or dst not in by_id:
        return []

    # ★ **触发表**：``(source_state) -> [method, ...]``（来自 ``triggers`` 边）
    #   ★ 关键（实测修正）：``transitions_to`` 边**不带 method**
    #     （method 在 ``triggers`` 边上）⇒ 只走 transitions_to 会得到
    #     **没有方法名**的路径 ⇒ 会话种子无从生成。
    #   ★ `triggers` 边指向**源状态**（语义：「方法 M 触发 src → dst」）
    #     ⇒ 查表用**当前节点**（= 源状态）。
    #   ⇒ 路径的每一步 = (transitions_to 边, 对应的 triggers 边)。
    trig_by_target: dict[str, list[tuple[str, dict]]] = {}
    for e in edges:
        if edge_types is not None and str(e.get("type")) not in edge_types:
            continue
        if str(e.get("type")) != "triggers":
            continue
        f = str(e.get("from") or "")
        t = str(e.get("to") or "")
        if not f or not t:
            continue
        m = f.split(":", 1)[1] if ":" in f else f
        # ★ 方法名**大写**（图里的节点名是归一化的小写）
        trig_by_target.setdefault(t, []).append((m.upper(), e))

    paths: list[dict[str, Any]] = []
    visited: set[str] = set()

    def dfs(cur: str, node_seq: list[str], edge_seq: list[dict],
            method_seq: list[str], trig_seq: list[dict]) -> None:
        if len(paths) >= max_paths:
            return
        if cur == dst and len(node_seq) > 1:
            # ★ **顺序**：DFS 从 src 出发 ⇒ 收集到的序列**已是正序**
            #   （src → ... → dst）⇒ **不要反转**。
            #   ★ 曾经的坑：`triggers` 边指向**目标状态**时，
            #     方法序与状态序**错位**（实测得到
            #     ``[DHCPREQUEST, DHCPOFFER, DHCPDISCOVER, DHCPNAK]``）；
            #     改成指向**源状态**后两个序对齐 ⇒ 不需要反转。
            paths.append({
                "nodes": list(node_seq),
                "edges": list(edge_seq),
                "trigger_edges": list(trig_seq),
                "methods": list(method_seq),
                "length": len(node_seq) - 1,
            })
            return
        if len(node_seq) > max_depth:
            return
        for nxt, e in out_adj.get(cur, ()):
            if nxt in visited:
                continue
            # ★ **跳过占位源**（``state:?``）—— 源状态未知的迁移不能进路径
            #   （实测：会造出以「未知源」开头的荒谬路径）。
            if str(cur).endswith(":?") or str(nxt).endswith(":?"):
                continue
            # ★ 纯度闸：这条边的 owner 必须被允许
            if source_set is not None:
                from core.knowledge_channels import owner_allowed
                if not owner_allowed(str(e.get("source_owner") or "-"),
                                    source_set):
                    continue
            # ★ 找触发这条迁移的方法（``triggers`` 边指向**源状态** = cur）
            trigs = trig_by_target.get(cur, [])
            if not trigs:
                continue        # ★ 没有触发方法 ⇒ 这一步不是可执行的消息
            for m_name, t_e in trigs:
                if source_set is not None:
                    from core.knowledge_channels import owner_allowed
                    if not owner_allowed(str(t_e.get("source_owner") or "-"),
                                        source_set):
                        continue
                visited.add(nxt)
                node_seq.append(nxt)
                edge_seq.append(e)
                trig_seq.append(t_e)
                method_seq.append(m_name)
                dfs(nxt, node_seq, edge_seq, method_seq, trig_seq)
                method_seq.pop()
                trig_seq.pop()
                edge_seq.pop()
                node_seq.pop()
                visited.discard(nxt)

    visited.add(src)
    dfs(src, [src], [], [], [])
    return paths


def _edge_method(e: dict) -> str:
    """从边里取「触发方法名」（`triggers` 边的 from 节点名 / 边的 label）。"""
    t = str(e.get("type") or "")
    if t == "triggers":
        # triggers 边：from = message 节点 ⇒ 取名字
        f = str(e.get("from") or "")
        if ":" in f:
            return f.split(":", 1)[1]
    return str(e.get("label") or "")


# ===========================================================================
# M3：社区检索
# ===========================================================================

def retrieve_communities(protocol: str,
                         query: str = "",
                         top_k: int = 3) -> list[dict[str, Any]]:
    """M3：按查询返回**相关社区**及其报告（GraphRAG 的检索入口）。

    ★ 相关性判据（**确定性、零 LLM**）：社区成员名/摘要里命中查询词的数量。
      ⇒ 可复现、可解释；LLM 排序留作后续增强。
    """
    from core.fused.graph_reports import read_communities
    comms = read_communities(protocol)
    if not comms:
        return []
    q = (query or "").strip().lower()
    if not q:
        # 无查询 ⇒ 返回最大的几个社区
        return sorted(comms, key=lambda c: -c.get("member_count", 0))[:top_k]
    scored: list[tuple[int, dict]] = []
    for c in comms:
        hay = " ".join([
            str(c.get("summary") or ""),
            " ".join(c.get("members") or []),
            " ".join(c.get("facts") or []),
        ]).lower()
        score = sum(1 for w in {t for t in q.replace(",", " ").split() if t}
                    if w in hay)
        if score:
            scored.append((score, c))
    scored.sort(key=lambda kv: -kv[0])
    return [c for _s, c in scored[:top_k]]


# ===========================================================================
# 图级纯度闸
# ===========================================================================

def check_path_purity(path: dict[str, Any],
                       source_set: Optional[set[str]] = None) -> dict[str, Any]:
    """图级纯度闸：检查一条路径上的**所有边**是否都属于本次源集合。

    Returns:
        ``{"allowed": bool, "violations": [...], "owners": {...}}``
    """
    from core.knowledge_channels import owner_allowed
    violations: list[dict] = []
    owners: dict[str, int] = {}
    for e in path.get("edges") or []:
        ow = str(e.get("source_owner") or "-")
        owners[ow] = owners.get(ow, 0) + 1
        if source_set is not None and not owner_allowed(ow, source_set):
            violations.append({
                "edge_id": e.get("edge_id"), "type": e.get("type"),
                "owner": ow, "from": e.get("from"), "to": e.get("to"),
            })
    return {"allowed": not violations, "violations": violations,
            "owners": owners}


# ===========================================================================
# B3.2：**路径式种子**（与「边覆盖式」并存）
# ===========================================================================

def path_seeds(protocol: str,
               transitions: Optional[list] = None,
               message_instances: Optional[dict] = None,
               required_headers: Optional[dict] = None,
               headers: Optional[dict] = None,
               source_set: Optional[set[str]] = None,
               max_depth: int = DEFAULT_MAX_DEPTH,
               max_paths: int = DEFAULT_MAX_PATHS,
               strict_purity: bool = True) -> list:
    """B3.2：从图上的**路径**生成会话种子（完整黄金路径）。

    ★ 与 ``edge_cover``（边覆盖式）**并存**，目标不同：
      · ``edge_cover``：覆盖**尽可能多**的转移（边覆盖）；
      · ``path_seeds``：覆盖**完整会话**（路径）。

    ★ **纯度闸**（D.3）：``strict_purity=True`` ⇒ 只保留**整条路径都干净**
      （每条边的 owner 都 ∈ ``source_set``）的路径。
      ⇒ 路径式种子天然受纯度约束（比单边检查更强）。

    Returns:
        ``list[SeedCorpus]``
    """
    from core.models import SeedCorpus, SeedMessage

    nodes, edges = load_graph(protocol)
    if not nodes:
        return []
    # 候选端点：图里的 state 节点
    state_ids = [n["node_id"] for n in nodes if n.get("type") == "state"]
    if len(state_ids) < 2:
        return []

    mi = message_instances or {}
    rh = required_headers or {}
    hd = headers or {}

    out: list[SeedCorpus] = []
    seen_paths: set[tuple] = set()
    # 优先用「中枢的 transitions」里的 (src, method, dst) 作为端点对
    # ★ 端点对：**从初始状态出发**（不只中枢 transitions 给的那些）
    #   ⇒ 中枢 transitions 只给「直接相邻」的 (src, dst)，
    #     而**黄金路径**（INIT → BOUND）需要**跨多步**的端点对
    #     （实测：不这么做 ⇒ 只找到 2 步的短路径，找不到黄金路径）。
    #   ⇒ 全部状态对 ⇒ 路径枚举自己会挑出最长的那条。
    # ★ ★ **只从初始状态出发**（实测修正）：全状态对会产生**反向路径**
    #   （如 ``[DHCPRELEASE, DHCPDISCOVER, DHCPOFFER, DHCPREQUEST]``
    #   —— 从 BOUND 倒着走 ⇒ 会话顺序荒谬）。
    #   ⇒ 用既有的 ``_detect_init``（成熟判据：优先 "Init"，否则无入边状态）
    #     定位起点 ⇒ 只保留**正向**路径。
    _init_state = _detect_init_from_bundle(transitions)
    pairs: list[tuple[str, str]] = []
    if _init_state:
        _init_id = _nid_state(_init_state)
        if _init_id in state_ids:
            pairs = [(_init_id, b) for b in state_ids if b != _init_id]
    if not pairs:
        pairs = [(a, b) for a in state_ids for b in state_ids if a != b]

    for src, dst in pairs:
        # ★ 端点已是**节点 id**（``state:xxx``）⇒ 直接用，不��再套 _nid_state
        #   （套两次会得到 ``state:state:init`` ⇒ 找不到节点 ⇒ 0 条路径）。
        paths = find_paths(nodes, edges, src, dst,
                           max_depth=max_depth, max_paths=max_paths,
                           source_set=source_set if strict_purity else None)
        for path in paths:
            methods = [m for m in path.get("methods") or [] if m]
            if len(methods) < 2:
                continue          # 少于 2 个方法 ⇒ 不是有意义的会话
            key = tuple(methods)
            if key in seen_paths:
                continue
            if strict_purity and source_set is not None:
                chk = check_path_purity(path, source_set)
                if not chk["allowed"]:
                    continue
            seen_paths.add(key)
            msgs: list[SeedMessage] = []
            for m in methods:
                hdrs: dict[str, str] = {}
                for h in (rh.get(m) or []):
                    info = hd.get(h) or {}
                    vals = info.get("values") or []
                    if vals:
                        hdrs[h] = str(vals[0])
                # 消息实例里的字段取值（优先）
                for (s, mm, d), fields in mi.items():
                    if str(mm).upper() != m.upper():
                        continue
                    for fv in (fields or []):
                        if isinstance(fv, (list, tuple)) and len(fv) >= 2:
                            hdrs[str(fv[0])] = str(fv[1])
                msgs.append(SeedMessage(method=m, headers=hdrs))
            out.append(SeedCorpus(
                protocol=protocol,
                description=f"路径式种子：{' -> '.join(methods)}",
                target_state_path=list(path.get("nodes") or []),
                target_methods=methods,
                messages=msgs,
                generated_by="graph-path",
            ))
    return out


def _detect_init_from_bundle(transitions: Optional[list]) -> str:
    """从中枢的 transitions 里定位**初始状态**（复用既有判据）。"""
    if not transitions:
        return ""
    try:
        # ★ 阶段 D1：改用**中枢层**的 state_graph（原先反向 import 消费层）
        from core.fused.state_graph import _detect_init
        return _detect_init([tuple(t) for t in transitions
                             if isinstance(t, (list, tuple)) and len(t) >= 3])
    except Exception:                           # noqa: BLE001
        return ""


def _nid_state(name: str) -> str:
    """状态名 → 节点 id（与 ``graph_ops._nid`` 一致）。"""
    import re
    return f"state:{re.sub(r'\s+', '_', str(name).strip()).lower()}"


__all__ = [
    "DEFAULT_MAX_DEPTH", "DEFAULT_MAX_PATHS",
    "load_graph", "build_adjacency", "retrieve_neighborhood",
    "retrieve_subgraph_graph", "find_paths", "retrieve_communities",
    "check_path_purity", "path_seeds",
]
