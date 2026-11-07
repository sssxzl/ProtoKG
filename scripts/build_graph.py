"""构建协议知识图谱（GraphRAG 改造**批次 1**）。

★ 流程：
    ① Phase A：从 ``kb/<协议>/spec/*.txt`` **确定性**抽节点/边（零 LLM）
       ⇒ ``core/fused/rfc_graph.py``
    ② B0：把中枢的 16 个桶**投影**成显式图 ⇒ ``core/fused/graph_ops.py``
    ③ B1：分层（精确图 / 社区图）+ 质量度量 ⇒ 落盘

★ 产物（``derived/per_source/<协议>/graph/``）：
    ``nodes.jsonl`` / ``edges.jsonl`` / ``graph_meta.json``

★ **中枢零改动**：图是**派生视图** ⇒ bundle / seedgen / edge_cover 不受影响。

用法：
    E:/app/Anaconda3/python.exe scripts/build_graph.py --protocol dhcpv4
    E:/app/Anaconda3/python.exe scripts/build_graph.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _fingerprint(nodes: list[dict], edges: list[dict]) -> str:
    """图内容指纹（幂等检测用）。"""
    import hashlib
    h = hashlib.sha256()
    for n in sorted(nodes, key=lambda x: x["node_id"]):
        h.update(n["node_id"].encode("utf-8"))
    for e in sorted(edges, key=lambda x: x["edge_id"]):
        h.update(e["edge_id"].encode("utf-8"))
    return h.hexdigest()[:16]


def build_one(protocol: str) -> dict:
    """构建一个协议的图。"""
    from core.fused.graph_ops import (project_bundle_to_graph, split_by_graph,
                                      write_graph)
    from core.fused.rfc_graph import extract_graph

    # ---- ① Phase A：确定性抽节点/边 ----
    phase_a_nodes, phase_a_edges = extract_graph(protocol)

    # ---- ② B0：中枢 16 桶 → 显式图 ----
    bundle = {}
    try:
        from core.fused.downstream import rag_seedgen as RS
        bundle = RS.assemble_bundle(RS.load_fact_views(protocol), protocol)
    except Exception as exc:                       # noqa: BLE001
        print(f"[图] {protocol}: 中枢不可用（{type(exc).__name__}: {exc}）"
              f" ⇒ 只用 Phase A 的抽取结果")

    proj_nodes, proj_edges = project_bundle_to_graph(bundle, protocol)

    # ---- 合并（Phase A 的节点/边 + 投影的节点/边）----
    nodes: dict[str, dict] = {}
    for n in phase_a_nodes:
        nodes[n.node_id] = n.as_dict()
    for n in proj_nodes:
        nodes.setdefault(n["node_id"], n)
    edges: dict[str, dict] = {}
    for e in phase_a_edges:
        edges[e.edge_id] = e.as_dict()
    for e in proj_edges:
        edges.setdefault(e["edge_id"], e)

    node_list = list(nodes.values())
    edge_list = list(edges.values())

    # ---- ③ B1：分层 + 度量 + 落盘 ----
    struct_nodes, struct_edges = split_by_graph(node_list, edge_list, "structure")
    sem_nodes, sem_edges = split_by_graph(node_list, edge_list, "semantic")
    paths = write_graph(protocol, node_list, edge_list, extra_meta={
        "phase_a_node_count": len(phase_a_nodes),
        "phase_a_edge_count": len(phase_a_edges),
        "projected_node_count": len(proj_nodes),
        "projected_edge_count": len(proj_edges),
        "structure_graph": {"nodes": len(struct_nodes), "edges": len(struct_edges)},
        "semantic_graph": {"nodes": len(sem_nodes), "edges": len(sem_edges)},
        "fingerprint": _fingerprint(node_list, edge_list),
    })
    return {
        "nodes": len(node_list), "edges": len(edge_list),
        "structure": (len(struct_nodes), len(struct_edges)),
        "semantic": (len(sem_nodes), len(sem_edges)),
        "paths": paths,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    protos: list[str] = []
    if args.all:
        from core import paths
        protos = sorted(p.name.lower() for p in paths.kb_root().iterdir()
                        if p.is_dir())
    elif args.protocol:
        protos = [args.protocol]
    else:
        ap.error("需要 --protocol 或 --all")

    for p in protos:
        try:
            r = build_one(p)
        except Exception as exc:                   # noqa: BLE001
            print(f"[图] {p}: 失败 {type(exc).__name__}: {exc}")
            continue
        if not args.quiet:
            print(f"[图] {p:9s} 节点 {r['nodes']:4d} 边 {r['edges']:4d} | "
                  f"精确图 {r['structure'][0]:3d}/{r['structure'][1]:3d} | "
                  f"社区图 {r['semantic'][0]:3d}/{r['semantic'][1]:3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
