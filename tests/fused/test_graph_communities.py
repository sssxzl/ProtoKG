# -*- coding: utf-8 -*-
"""tests/fused/test_graph_communities.py —— Phase B2（社区检测 + 社区报告）的护栏。

★ 覆盖：
  ① B2.1 **MultiDiGraph 合并**（同对节点多条边都保留）；
  ② B2.4 **社区检测**（四级降级：Leiden → Louvain → 贪心模块度 → 连通分量）；
  ③ B2.5 **社区报告**（LLM + 磁盘缓存 + 确定性降级 + 通道标注）。

★ 关键回归：
  · 社区检测**不得**让整图塌成 1 个社区（`defines` 归属边要排除）；
  · 社区报告**必须**带 `owner_mix` / `class`（知识通道标注）；
  · **零外部依赖也能跑**（networkx 缺失时降级不崩）。
"""
from __future__ import annotations

import json

import pytest


# ===========================================================================
# ① B2.1：MultiDiGraph 合并
# ===========================================================================

def test_merge_keeps_multiple_edges_between_same_pair():
    """★ 同对节点的**多条不同条件边**都要保留（MultiDiGraph 语义）。"""
    from core.fused.graph_ops import merge_multidigraph
    nodes = [{"node_id": "a", "confidence": "medium"},
             {"node_id": "b", "confidence": "high"}]
    edges = [
        {"type": "transitions_to", "from": "a", "to": "b", "label": "X"},
        {"type": "transitions_to", "from": "a", "to": "b", "label": "Y"},
        {"type": "transitions_to", "from": "a", "to": "b", "label": "X"},
    ]
    mn, me = merge_multidigraph(nodes, edges)
    assert len(mn) == 2
    assert len(me) == 2, me          # 完全重复的边去重，不同 label 的保留


def test_merge_keeps_higher_confidence_node():
    """★ 同 id 节点保留**置信度更高**的那份。"""
    from core.fused.graph_ops import merge_multidigraph
    nodes = [{"node_id": "a", "confidence": "medium"},
             {"node_id": "a", "confidence": "high"}]
    mn, _ = merge_multidigraph(nodes, [])
    assert len(mn) == 1
    assert mn[0]["confidence"] == "high"


# ===========================================================================
# ② B2.4：社区检测
# ===========================================================================

def test_defines_edge_excluded_from_communities():
    """★ `defines`（归属边）**不参与**社区划分。

    ★ 实测：它把协议节点连到**所有**字段 ⇒ 整图连通 ⇒ 社区检测必然
      只出 1 个社区（实测 rtsp 69 节点全落一个社区）。
    """
    from core.fused.graph_ops import COMMUNITY_EXCLUDED_EDGE_TYPES
    assert "defines" in COMMUNITY_EXCLUDED_EDGE_TYPES


def test_communities_not_collapsed_to_one():
    """★ 社区**不得**塌成 1 个（否则社区报告失去意义）。"""
    from core.fused.graph_ops import read_graph, split_by_graph
    from core.fused.graph_ops import merge_multidigraph, detect_communities
    for proto in ("rtsp", "dhcpv4"):
        nodes, edges = read_graph(proto)
        sn, se = split_by_graph(nodes, edges, "semantic")
        mn, me = merge_multidigraph(sn, se)
        comms, algo = detect_communities(mn, me)
        assert len(comms) >= 2, (proto, len(comms), algo)
        # 且不能全是单点
        assert max(len(c) for c in comms) >= 2, (proto, [len(c) for c in comms])


def test_community_detection_never_crashes():
    """★ 空图 / 无边图都不崩（降级路径）。

    ★ 无边图 ⇒ 每个节点**自成一社区**（不是合并成一个）
      ⇒ 断言：社区数 == 节点数，且每个社区只有 1 个成员。
    """
    from core.fused.graph_ops import detect_communities
    assert detect_communities([], []) == ([], "none")
    nodes = [{"node_id": "a"}, {"node_id": "b"}]
    comms, algo = detect_communities(nodes, [])
    assert len(comms) == 2, (comms, algo)
    assert all(len(c) == 1 for c in comms), comms


def test_split_by_graph_completes_endpoints():
    """★ 分层时**补上被本层边引用到的端点节点**。

    ★ 实测：社区图的边（`required_by`/`co_occurs`）一端是 message 节点，
      而 message 节点在 structure 图 ⇒ 若不补齐，边会**端点悬空**
      ⇒ 社区检测退化成全孤立。
    """
    from core.fused.graph_ops import split_by_graph
    nodes = [
        {"node_id": "entity:a", "graph": "semantic"},
        {"node_id": "message:m", "graph": "structure"},
    ]
    edges = [{"type": "required_by", "from": "message:m", "to": "entity:a",
              "graph": "semantic"}]
    sn, se = split_by_graph(nodes, edges, "semantic")
    ids = {n["node_id"] for n in sn}
    assert "entity:a" in ids
    assert "message:m" in ids, ids        # ★ 端点补全
    for e in se:
        assert e["from"] in ids and e["to"] in ids


# ===========================================================================
# ③ B2.5：社区报告
# ===========================================================================

def test_community_inputs_have_channel_annotation():
    """★ 每个社区都带 **owner_mix** 与 **class**（知识通道标注）。"""
    from core.fused.graph_reports import build_community_inputs
    items = build_community_inputs("dhcpv4")
    assert items, "没有社区"
    for it in items:
        assert "owner_mix" in it and it["owner_mix"], it
        assert it["class"] in ("L1", "L2", "MIXED"), it


def test_owner_mix_only_counts_nodes():
    """★ `owner_mix` **只统计节点**的 owner（不算边）。

    ★ 实测：若把边的 owner 也计入，`defines` 边（owner=rfc，数量压倒性多）
      会把每个社区的 class 都压成 MIXED ⇒ 分类失去区分度。
    """
    from core.fused.graph_ops import community_owner_mix
    nodes = [{"node_id": "a", "source_owner": "rfc"},
             {"node_id": "b", "source_owner": "profile"}]
    edges = [{"from": "a", "to": "b", "source_owner": "rfc"}]
    mix = community_owner_mix(["a", "b"], nodes, edges)
    assert mix == {"rfc": 1, "profile": 1}, mix


def test_community_class_rules():
    """★ 社区的**知识层级**判定规则。"""
    from core.fused.graph_ops import community_class
    assert community_class({"rfc": 3}) == "L1"
    assert community_class({"profile": 3}) == "L2"
    assert community_class({"rfc": 1, "profile": 2}) == "MIXED"
    assert community_class({}) == "L1"


def test_community_reports_fallback_when_no_llm():
    """★ **LLM 不可用时不阻断**（确定性降级）。"""
    from core.fused.graph_reports import generate_community_reports
    reports = generate_community_reports("dhcpv4", use_llm=False)
    assert reports
    for r in reports:
        assert r["summary"], r
        assert r["summary_source"] in ("fallback", "cache"), r


def test_community_reports_written_and_readable():
    """★ 社区报告落盘 + 可读回。"""
    from core.fused.graph_reports import (generate_community_reports,
                                          read_communities, write_communities)
    reports = generate_community_reports("dhcpv4", use_llm=False)
    p = write_communities("dhcpv4", reports)
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["community_count"] == len(reports)
    back = read_communities("dhcpv4")
    assert len(back) == len(reports)


def test_community_report_prompt_version_recorded():
    """★ prompt 版本**落盘**（改 prompt 必须升版 ⇒ 缓存键）。"""
    from core.fused.graph_reports import (COMMUNITY_REPORT_PROMPT_VERSION,
                                          write_communities)
    assert COMMUNITY_REPORT_PROMPT_VERSION
    write_communities("dhcpv4", [])
    from core.fused.graph_ops import graph_dir
    data = json.loads((graph_dir("dhcpv4") / "communities.json")
                      .read_text(encoding="utf-8"))
    assert data["prompt_version"] == COMMUNITY_REPORT_PROMPT_VERSION
