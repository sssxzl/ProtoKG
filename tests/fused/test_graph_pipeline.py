# -*- coding: utf-8 -*-
"""tests/fused/test_graph_pipeline.py —— GraphRAG 改造**批次 1**的护栏。

★ 覆盖：
  ① 图模式注册表的自洽性（节点/边类型引用、遍历配置）；
  ② Phase A 的确定性抽取（状态/消息/定时器节点 + 图形消息序列 + 散文迁移）；
  ③ B0 投影（中枢 16 桶 → 显式图，**中枢零改动**）；
  ④ B1 分层（精确图 / 社区图**不混**）+ 图质量度量。

★ 关键回归护栏：
  · 抽取**零 LLM**（纯确定性）；
  · 图的构造**不修改**中枢产物；
  · 四个协议都能建图且**孤立节点比**在可接受区间。
"""
from __future__ import annotations

import json

import pytest


# ===========================================================================
# ① 图模式注册表
# ===========================================================================

def test_graph_schema_is_self_consistent():
    """★ 注册表自洽（边的端点必须是**已定义的节点类型**）。

    ★ 踩过的坑：初版把 ``transitions_to``（**边类型**）写进 ``triggers.to``
      ⇒ 校验器抓到（这是校验器的价值）。
    """
    from core.fused.graph.graph_schema import validate_schema
    problems = validate_schema()
    assert not problems, problems


def test_graph_schema_has_two_graphs():
    """★ D2：两类知识分开 ⇒ schema 里有 structure / semantic 两张图。"""
    from core.fused.graph.graph_schema import edge_type_names, node_type_names
    assert "state" in node_type_names("structure")
    assert "message" in node_type_names("structure")
    assert "header" in node_type_names("semantic")
    assert "constraint" in node_type_names("semantic")
    # 精确图的边不能出现在社区图里
    assert "transitions_to" in edge_type_names("structure")
    assert "transitions_to" not in edge_type_names("semantic")


def test_traversal_is_data_driven():
    """★ 遍历配置是**数据**（加边类型不改代码）。"""
    from core.fused.graph.graph_schema import traversal
    tr = traversal()
    assert "state_to_state" in tr
    assert "transitions_to" in tr["state_to_state"]


# ===========================================================================
# ② Phase A：确定性抽取
# ===========================================================================

def test_state_definition_list_extraction():
    """★ N1b：状态**定义列表**形态（rtsp 附录 A.1）。

    ★ 踩过的坑：该形态**不是 ASCII 图** ⇒ 形态层的 diagram 判据识别不出
      ⇒ 只靠图形块收状态会漏掉 rtsp 全部状态（实测 0 个）。
    """
    from core.fused.graph.rfc_graph import extract_state_definitions
    lines = [
        "A.1 Client State Machine",
        "",
        "   The client can assume the following states:",
        "",
        "   Init:",
        "          SETUP has been sent, waiting for reply.",
        "          the client changes state on receipt of replies",
        "",
        "   Ready:",
        "          SETUP reply received or PAUSE reply received.",
        "          in Ready state the client waits for PLAY",
        "",
        "   Recording:",
        "          RECORD reply received",
        "          state Recording is entered on RECORD reply",
    ]
    got = {n.name for n in extract_state_definitions(lines, "x.txt")}
    assert "Init" in got and "Ready" in got and "Recording" in got, got


def test_state_definitions_reject_non_states():
    """★ 迁移语义交叉校验：术语/方法定义**不是**状态。

    ★ 实测：rtsp 的 ``Conference:`` / ``SETUP:`` 形态与状态定义**完全同构**
      ⇒ 纯形态无法区分 ⇒ 必须靠「迁移语义上下文」过滤。
    """
    from core.fused.graph.rfc_graph import extract_state_definitions
    lines = [
        "   Conference:",
        "          A conference is a set of participants.",
        "",
        "   SETUP:",
        "          The SETUP method request URI.",
        "",
        "   Playing:",
        "          PLAY reply received",
        "          the client changes state on receipt of replies",
        "          in Playing state the client is streaming",
    ]
    got = {n.name for n in extract_state_definitions(lines, "x.txt")}
    assert "Playing" in got, got
    assert "Conference" not in got, got
    assert "SETUP" not in got, got


def test_message_extraction_excludes_protocol_name():
    """★ N2：消息名不是协议自身名（DHCP vs DHCPDISCOVER）。"""
    from core.fused.graph.rfc_graph import extract_message_nodes
    lines = ["   DHCP messages: DHCPDISCOVER, DHCPOFFER and DHCPACK"]
    got = {n.name for n in extract_message_nodes(lines, "x.txt",
                                                  ["DHCPDISCOVER"], "DHCPv4")}
    assert "DHCPDISCOVER" in got
    assert "DHCP" not in got, got


def test_state_extraction_excludes_message_names():
    """★ 消息名（DHCPOFFER）本身是全大写 ⇒ 不得被当状态。"""
    from core.fused.graph.rfc_graph import extract_state_candidates
    lines = ["   The server responds with DHCPOFFER then DHCPACK."]
    got = {n.name for n in extract_state_candidates(
        lines, "x.txt", ("INIT",), exclude={"DHCPOFFER", "DHCPACK"})}
    assert "DHCPOFFER" not in got, got


def test_wrapped_word_not_treated_as_term():
    """★ 折行截断：``DHCPREQU`` + ``EST`` 不该是两个术语。"""
    from core.fused.graph.rfc_graph import _is_wrapped_continuation
    lines = ["   The client sends a DHCPREQUEST", "   EST message to server."]
    assert _is_wrapped_continuation(lines, 2, "EST")
    assert not _is_wrapped_continuation(lines, 2, "DHCPREQUEST")


def test_graph_message_sequence_extraction():
    """★ E1：图形里的消息序列（RFC 2131 Figure 3 时序图形态）。"""
    from core.fused.graph.rfc_graph import extract_graph_message_sequences
    lines = [
        "        v               v               v",
        "        |               |               |",
        "        | _____________/|\\____________  |",
        "        |/DHCPDISCOVER | DHCPDISCOVER  |",
        "        |               |               |",
        "        |\\             |  ____________/ |",
        "        | \\________    | /DHCPOFFER     |",
        "        | DHCPOFFER\\   |/               |",
    ]
    got = extract_graph_message_sequences(lines, "x.txt",
                                          {"DHCPDISCOVER", "DHCPOFFER"})
    kinds = {(e.from_id, e.to_id) for e in got}
    assert ("message:dhcpdiscover", "message:dhcpoffer") in kinds, kinds


def test_prose_transition_extraction():
    """★ E3：散文里的状态迁移（RFC 2131 的状态名**只在散文里**）。"""
    from core.fused.graph.rfc_graph import extract_prose_transitions
    lines = ["   the client reverts to INIT state and starts over."]
    got = extract_prose_transitions(lines, "x.txt", {"INIT", "SELECTING"})
    assert got and got[0].to_id == "state:init", [e.as_dict() for e in got]
    assert got[0].confidence == "medium"


def test_extraction_is_deterministic():
    """★ 抽取**零 LLM** ⇒ 同输入同输出（逐字节可复现）。"""
    from core.fused.graph.rfc_graph import extract_graph
    a_nodes, a_edges = extract_graph("dhcpv4")
    b_nodes, b_edges = extract_graph("dhcpv4")
    assert [n.node_id for n in a_nodes] == [n.node_id for n in b_nodes]
    assert [e.edge_id for e in a_edges] == [e.edge_id for e in b_edges]


# ===========================================================================
# ③ B0：投影
# ===========================================================================

def test_projection_does_not_touch_hub():
    """★ 投影是**只读**的 ⇒ 中枢产物零改动。"""
    from core import paths
    from core.fused.downstream import rag_seedgen as RS
    from core.fused.graph.graph_ops import project_bundle_to_graph
    facts_dir = paths.per_source_aspect_facts_dir("rtsp")
    before = {}
    for p in sorted(facts_dir.glob("*.jsonl")):
        before[p.name] = p.stat().st_mtime_ns
    bundle = RS.assemble_bundle(RS.load_fact_views("rtsp"), "rtsp")
    project_bundle_to_graph(bundle, "rtsp")
    after = {p.name: p.stat().st_mtime_ns for p in sorted(facts_dir.glob("*.jsonl"))}
    assert before == after, "投影改了中枢文件！"


def test_projection_makes_transitions_into_edges():
    """★ 三元组 (src, method, dst) ⇒ 拆成 transitions_to + triggers 两条边。"""
    from core.fused.graph.graph_ops import project_bundle_to_graph
    bundle = {
        "methods": {"OPTIONS": {}},
        "headers": {"CSeq": {}},
        "statuses": [("200", "OK")],
        "transitions": [("Init", "OPTIONS", "Ready")],
        "required_headers": {"OPTIONS": ["CSeq"]},
        "method_sequences": [],
        "message_instances": {},
    }
    nodes, edges = project_bundle_to_graph(bundle, "rtsp")
    etypes = {e["type"] for e in edges}
    assert "transitions_to" in etypes, etypes
    assert "triggers" in etypes, etypes
    assert "required_by" in etypes, etypes
    assert "defines" in etypes, etypes
    assert any(n["node_id"] == "message:options" for n in nodes)


def test_projection_is_idempotent():
    """★ 同一 bundle 投影两次 ⇒ 同样的图。"""
    from core.fused.graph.graph_ops import project_bundle_to_graph
    bundle = {"methods": {"A": {}}, "headers": {}, "statuses": [],
              "transitions": [], "required_headers": {}, "method_sequences": [],
              "message_instances": {}}
    n1, e1 = project_bundle_to_graph(bundle, "x")
    n2, e2 = project_bundle_to_graph(bundle, "x")
    assert n1 == n2 and e1 == e2


# ===========================================================================
# ④ B1：分层与度量
# ===========================================================================

def test_split_by_graph_keeps_two_graphs_separate():
    """★ D2：精确图**不含** header 节点；社区图**不含** state 节点。"""
    from core.fused.graph.graph_ops import split_by_graph
    nodes = [{"node_id": "state:a", "graph": "structure"},
             {"node_id": "entity:b", "graph": "semantic"}]
    edges = [{"edge_id": "e1", "graph": "structure"},
             {"edge_id": "e2", "graph": "semantic"}]
    sn, se = split_by_graph(nodes, edges, "structure")
    mn, me = split_by_graph(nodes, edges, "semantic")
    assert [n["node_id"] for n in sn] == ["state:a"]
    assert [n["node_id"] for n in mn] == ["entity:b"]
    assert len(se) == 1 and len(me) == 1


def test_graph_metrics_computation():
    """★ 度量计算正确（孤立节点比 / 最大连通分量比）。"""
    from core.fused.graph.graph_ops import graph_metrics
    nodes = [{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"}]
    edges = [{"from": "a", "to": "b"}]
    m = graph_metrics(nodes, edges)
    assert m["node_count"] == 3
    assert m["edge_count"] == 1
    assert m["isolated_node_count"] == 1          # c
    # ★ 度量按 4 位小数取整 ⇒ 容差取 1e-3
    assert abs(m["isolated_node_ratio"] - 1 / 3) < 1e-3
    assert abs(m["largest_connected_component_ratio"] - 2 / 3) < 1e-3


def test_graph_metrics_empty_graph():
    """★ 空图不崩。"""
    from core.fused.graph.graph_ops import graph_metrics
    m = graph_metrics([], [])
    assert m["node_count"] == 0
    assert m["isolated_node_ratio"] == 0.0


# ===========================================================================
# ⑤ 端到端：四个协议都能建图
# ===========================================================================

@pytest.mark.parametrize("protocol", ["rtsp", "sip", "smtp", "dhcpv4"])
def test_graph_build_for_each_protocol(protocol):
    """★ 四个协议都能建图，且**孤立节点比**在可接受区间。

    ★ 参照区间（RFC-RAG-Agent 在 RFC 2131 上实测）：0.1408 / 0.8002。
      ★ 本项是**诊断性**断言（不是通过/不通过闸），但设了宽松上限
        （孤立比 ≤ 0.25）以防回归。
    """
    from core.fused.downstream import rag_seedgen as RS
    from core.fused.graph.graph_ops import graph_metrics, project_bundle_to_graph
    from core.fused.graph.rfc_graph import extract_graph
    nodes, edges = extract_graph(protocol)
    assert nodes, f"{protocol} 没抽出任何节点"
    # ★ 度量必须在**投影后**的图上算（Phase A 单独算时字段节点必然孤立
    #   —— 字段来自中枢的协议级事实，投影时才补上 defines 边）
    bundle = RS.assemble_bundle(RS.load_fact_views(protocol), protocol)
    pnodes, pedges = project_bundle_to_graph(bundle, protocol)
    ids = {n["node_id"] for n in pnodes}
    merged_nodes = {n.node_id: {"node_id": n.node_id} for n in nodes}
    merged_nodes.update({n["node_id"]: n for n in pnodes})
    merged_edges = [{"from": e.from_id, "to": e.to_id} for e in edges]
    merged_edges += [{"from": e["from"], "to": e["to"]} for e in pedges]
    m = graph_metrics(list(merged_nodes.values()), merged_edges)
    assert m["isolated_node_ratio"] <= 0.25, (protocol, m)


def test_dhcpv4_graph_has_expected_states():
    """★ DHCPv4 的图里有 RFC 2131 §4.4 的真状态。"""
    from core.fused.graph.rfc_graph import extract_graph
    nodes, _ = extract_graph("dhcpv4")
    states = {n.name for n in nodes if n.type == "state"}
    for want in ("INIT", "SELECTING", "REQUESTING", "BOUND"):
        assert want in states, (want, sorted(states))
