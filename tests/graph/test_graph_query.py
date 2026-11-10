# -*- coding: utf-8 -*-
"""tests/test_graph_query.py —— Phase D（B3 检索层）的护栏。

★ 覆盖：
  ① M1 **k-hop 邻域**（图驱动，边类型数据驱动）；
  ② M2 **路径查询**（枚举简单路径 + 顺序正确 + 纯度闸）；
  ③ M3 **社区检索**（按查询返回社区报告）；
  ④ B3.2 **路径式种子**（与边覆盖式并存）；
  ⑤ B3.3 **图级纯度闸**（路径上每条边都要干净）。

★ 关键回归：
  · **不修改**既有 `rag_seedgen.retrieve_subgraph`（老消费链零回归）；
  · 路径的**方法顺序**必须与状态顺序对齐（实测踩过的坑）。
"""
from __future__ import annotations

import pytest


# ===========================================================================
# ① M1：k-hop 邻域
# ===========================================================================

def test_retrieve_neighborhood_expands_by_hops():
    """★ k-hop 邻域按跳数扩展。"""
    from core.fused.graph.graph_query import retrieve_neighborhood
    nodes = [{"node_id": "a", "name": "A", "type": "message"},
             {"node_id": "b", "name": "B", "type": "message"},
             {"node_id": "c", "name": "C", "type": "message"}]
    edges = [{"type": "required_by", "from": "a", "to": "b", "label": ""},
             {"type": "required_by", "from": "b", "to": "c", "label": ""}]
    r1 = retrieve_neighborhood(nodes, edges, ["a"], k_hops=1)
    assert r1["node_ids"] == {"a", "b"}, r1["node_ids"]
    r2 = retrieve_neighborhood(nodes, edges, ["a"], k_hops=2)
    assert r2["node_ids"] == {"a", "b", "c"}, r2["node_ids"]


def test_retrieve_neighborhood_respects_edge_types():
    """★ 边类型可限定（⇒ 扩展性）。"""
    from core.fused.graph.graph_query import retrieve_neighborhood
    nodes = [{"node_id": "a"}, {"node_id": "b"}]
    edges = [{"type": "required_by", "from": "a", "to": "b"},
             {"type": "followed_by", "from": "a", "to": "b"}]
    r = retrieve_neighborhood(nodes, edges, ["a"], k_hops=1,
                              edge_types={"required_by"})
    assert len(r["edges"]) == 1, r["edges"]


def test_retrieve_subgraph_graph_is_data_driven():
    """★ 图驱动子图检索的**边类型来自 graph_schema**（数据驱动）。"""
    from core.fused.graph.graph_query import retrieve_subgraph_graph
    from core.fused.graph.graph_schema import traversal
    tr = traversal()
    assert tr, "traversal 配置为空"
    nodes = [{"node_id": "message:setup", "name": "SETUP", "type": "message"},
             {"node_id": "entity:cseq", "name": "CSeq", "type": "entity"}]
    edges = [{"type": "required_by", "from": "message:setup",
              "to": "entity:cseq", "label": ""}]
    r = retrieve_subgraph_graph(nodes, edges, target_methods=["SETUP"], k_hops=1)
    assert "SETUP" in r["methods"], r
    assert "CSeq" in r["headers"], r


def test_old_retrieve_subgraph_unchanged():
    """★ **既有** `rag_seedgen.retrieve_subgraph` 保持原样（老消费链零回归）。

    ★ 批次 5 的设计调整：图里的 ``transitions_to`` 边**不带 method**
      （method 在 ``triggers`` 边上）⇒ 原地改旧函数会让 ``transitions``
      三元组变形 ⇒ 破坏既有消费链 ⇒ **保留旧函数不动**，另加图驱动版。
    """
    import inspect
    from core.fused.downstream import rag_seedgen as RS
    src = inspect.getsource(RS.retrieve_subgraph)
    # 旧函数仍走 bundle 的桶（不是显式图）
    assert "bundle[" in src
    assert "read_graph" not in src


# ===========================================================================
# ② M2：路径查询
# ===========================================================================

def _tri_graph():
    """INIT --DISCOVER--> SELECTING --OFFER--> OFFERED --REQUEST--> REQUESTING"""
    nodes = [{"node_id": f"state:{n}", "name": n, "type": "state"}
             for n in ("init", "selecting", "offered", "requesting")]
    nodes += [{"node_id": f"message:{m}", "name": m, "type": "message"}
              for m in ("discover", "offer", "request")]
    edges = [
        {"type": "transitions_to", "from": "state:init",
         "to": "state:selecting", "label": "", "source_owner": "rfc"},
        {"type": "transitions_to", "from": "state:selecting",
         "to": "state:offered", "label": "", "source_owner": "rfc"},
        {"type": "transitions_to", "from": "state:offered",
         "to": "state:requesting", "label": "", "source_owner": "rfc"},
        # ★ triggers 指向**源状态**（语义：方法 M 触发 src → dst）
        {"type": "triggers", "from": "message:discover",
         "to": "state:init", "label": "", "source_owner": "rfc"},
        {"type": "triggers", "from": "message:offer",
         "to": "state:selecting", "label": "", "source_owner": "rfc"},
        {"type": "triggers", "from": "message:request",
         "to": "state:offered", "label": "", "source_owner": "rfc"},
    ]
    return nodes, edges


def test_find_paths_returns_method_sequence():
    """★ 路径查询返回**带方法名**的序列。"""
    from core.fused.graph.graph_query import find_paths
    nodes, edges = _tri_graph()
    paths = find_paths(nodes, edges, "state:init", "state:requesting")
    assert paths, "没找到路径"
    p = paths[0]
    assert p["methods"] == ["DISCOVER", "OFFER", "REQUEST"], p["methods"]
    assert p["nodes"] == ["state:init", "state:selecting", "state:offered",
                           "state:requesting"], p["nodes"]


def test_find_paths_method_order_matches_state_order():
    """★ ★ **方法顺序必须与状态顺序对齐**（实测踩过的坑）。

    ★ 坑：`triggers` 边指向**目标状态**时 ⇒ 方法序与状态序**错位**
      （得到 ``[REQUEST, OFFER, DISCOVER]`` 这种荒谬顺序）。
    ⇒ 改成指向**源状态**后对齐。
    """
    from core.fused.graph.graph_query import find_paths
    nodes, edges = _tri_graph()
    p = find_paths(nodes, edges, "state:init", "state:requesting")[0]
    # 第一个方法触发的迁移是 init→selecting ⇒ 方法是 DISCOVER
    assert p["methods"][0] == "DISCOVER", p["methods"]
    assert p["nodes"][0] == "state:init"
    assert p["nodes"][1] == "state:selecting"


def test_find_paths_respects_purity():
    """★ **纯度闸**：owner 不在 source_set 的边 ⇒ 路径不经过它。"""
    from core.fused.graph.graph_query import find_paths
    nodes, edges = _tri_graph()
    # 把中间那条边染成 traffic
    for e in edges:
        if e.get("type") == "transitions_to" and e["to"] == "state:offered":
            e["source_owner"] = "traffic"
    assert find_paths(nodes, edges, "state:init", "state:requesting",
                      source_set={"rfc"}) == []
    assert find_paths(nodes, edges, "state:init", "state:requesting",
                      source_set={"rfc", "traffic"})


def test_find_paths_respects_max_depth():
    """★ 深度上限生效（防组合爆炸）。"""
    from core.fused.graph.graph_query import find_paths
    nodes, edges = _tri_graph()
    assert find_paths(nodes, edges, "state:init", "state:requesting",
                      max_depth=2) == []


def test_find_paths_unknown_endpoints():
    """★ 端点不存在 ⇒ 空（不崩）。"""
    from core.fused.graph.graph_query import find_paths
    nodes, edges = _tri_graph()
    assert find_paths(nodes, edges, "state:nope", "state:init") == []


# ===========================================================================
# ③ M3：社区检索
# ===========================================================================

def test_retrieve_communities_by_query():
    """★ 社区检索按查询词命中（确定性、零 LLM）。"""
    from core.fused.graph.graph_query import retrieve_communities
    comms = retrieve_communities("dhcpv4", query="option")
    assert comms, "没匹配到社区"
    assert any("option" in (c.get("summary") or "").lower()
               or any("option" in str(m).lower() for m in c.get("members", []))
               for c in comms)


def test_retrieve_communities_returns_largest_without_query():
    """★ 无查询 ⇒ 返回最大的社区。"""
    from core.fused.graph.graph_query import retrieve_communities
    comms = retrieve_communities("dhcpv4")
    assert comms
    counts = [c.get("member_count", 0) for c in comms]
    assert counts == sorted(counts, reverse=True), counts


# ===========================================================================
# ④ B3.2：路径式种子
# ===========================================================================

def test_path_seeds_generates_session_seeds():
    """★ 路径式种子产出**有序的会话**（≥2 个消息）。"""
    from core.fused.graph.graph_query import path_seeds
    from core.fused.downstream import rag_seedgen as RS
    b = RS.assemble_bundle(RS.load_fact_views("DHCPv4"), "DHCPv4")
    seeds = path_seeds("DHCPv4", transitions=b["transitions"],
                       message_instances=b["message_instances"],
                       required_headers=b["required_headers"],
                       headers=b["headers"],
                       source_set={"rfc", "profile"})
    assert seeds, "没有路径式种子"
    for s in seeds:
        assert len(s.messages) >= 2, s.description
        assert s.generated_by == "graph-path"


def test_path_seeds_only_from_init_state():
    """★ 路径**从初始状态出发**（不产生反向路径）。

    ★ 实测踩过的坑：全状态对 ⇒ 得到 ``[DHCPRELEASE, DHCPDISCOVER, ...]``
      这种「从 BOUND 倒着走」的荒谬顺序。

    ★ 断言口径（2026-11-08 修正）：**不再**断言「第一个方法必须是
      DHCPDISCOVER」—— 那要求 LLM 抽的**第一条迁移边**完全正确，
      而 RFC 状态机的**首个消息**在散文里也可能被 LLM 读成别的
      （实测 ``Init --DHCPOFFER--> Selecting``）。
      ⇒ 契约是「**路径从初始状态出发**」⇒ 断言**状态路径的首个节点**
        是初始状态。
    """
    from core.fused.graph.graph_query import (_detect_init_from_bundle,
                                          path_seeds)
    from core.fused.downstream import rag_seedgen as RS
    b = RS.assemble_bundle(RS.load_fact_views("DHCPv4"), "DHCPv4")
    init = _detect_init_from_bundle(b["transitions"])
    assert init, "初始状态判定失败"
    _init_id = "state:" + init.strip().lower().replace(" ", "_")
    seeds = path_seeds("DHCPv4", transitions=b["transitions"],
                       message_instances=b["message_instances"],
                       required_headers=b["required_headers"],
                       headers=b["headers"],
                       source_set={"rfc", "profile"})
    for s in seeds:
        assert s.target_state_path, s.description
        assert s.target_state_path[0] == _init_id, (
            s.description, s.target_state_path, _init_id)


def test_path_seeds_strict_purity_filters():
    """★ 严格纯度 ⇒ 纯 RFC 口径下**没有**可用路径（迁移边来自骨架）。"""
    from core.fused.graph.graph_query import path_seeds
    from core.fused.downstream import rag_seedgen as RS
    b = RS.assemble_bundle(RS.load_fact_views("DHCPv4"), "DHCPv4")
    loose = path_seeds("DHCPv4", transitions=b["transitions"],
                       message_instances=b["message_instances"],
                       required_headers=b["required_headers"],
                       headers=b["headers"], source_set=None,
                       strict_purity=False)
    strict = path_seeds("DHCPv4", transitions=b["transitions"],
                        message_instances=b["message_instances"],
                        required_headers=b["required_headers"],
                        headers=b["headers"], source_set={"rfc"},
                        strict_purity=True)
    assert len(loose) >= len(strict)


# ===========================================================================
# ⑤ B3.3：图级纯度闸
# ===========================================================================

def test_check_path_purity():
    """★ 纯度闸报告违规的边。"""
    from core.fused.graph.graph_query import check_path_purity
    path = {"edges": [{"edge_id": "e1", "type": "transitions_to",
                       "source_owner": "rfc", "from": "a", "to": "b"},
                      {"edge_id": "e2", "type": "triggers",
                       "source_owner": "traffic", "from": "m", "to": "a"}]}
    ok = check_path_purity(path, {"rfc"})
    assert not ok["allowed"]
    assert len(ok["violations"]) == 1, ok
    assert ok["violations"][0]["edge_id"] == "e2"
    ok2 = check_path_purity(path, {"rfc", "traffic"})
    assert ok2["allowed"]


def test_owner_allowed_used_by_purity_gate():
    """★ 纯度闸复用知识通道的 ``owner_allowed``（口径一致）。"""
    from core.knowledge_channels import owner_allowed
    assert owner_allowed("rfc", {"rfc"})
    assert not owner_allowed("traffic", {"rfc"})
    assert owner_allowed("-", {"rfc"})          # L3 目标事实恒允许


# ===========================================================================
# ⑥ 路径式种子**层**（默认关闭 ⇒ 现有口径不变）
# ===========================================================================

def test_graph_path_layer_not_in_default_layers():
    """★ `graph_path` 层**不进 ALL_LAYERS** ⇒ 默认关闭 ⇒ 种子口径不变。

    ★ 与 ``action_seq`` 同理：回滚手段必须成立（关掉即回到基线）。
    """
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "scripts" / "seedgen.py"
    spec = importlib.util.spec_from_file_location("seedgen_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.GRAPH_PATH_LAYER_NAME == "graph_path"
    assert mod.GRAPH_PATH_LAYER_NAME not in mod.ALL_LAYERS
