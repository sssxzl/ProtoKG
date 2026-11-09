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


def build_one(protocol: str, use_llm: bool = False) -> dict:
    """构建一个协议的图（含 B2：社区检测 + 社区报告）。"""
    from core.fused.graph.graph_ops import (project_bundle_to_graph, split_by_graph,
                                      write_graph)
    from core.fused.graph.rfc_graph import extract_graph

    # ---- ① Phase A：确定性抽节点/边 ----
    phase_a_nodes, phase_a_edges = extract_graph(protocol)

    # ---- ② B0：中枢 16 桶 → 显式图 ----
    # ★★ 阶段 D1：改用**中枢视图层**（core/fused/hub_view.py）
    #   ⇒ GraphRAG 整理层**不再依赖消费层**（消除层次倒置）
    bundle = {}
    try:
        from core.fused.hub import hub_view as HV
        from core.fused.downstream import rag_seedgen as RS
        bundle = HV.build_view(RS.load_fact_views(protocol), protocol)
    except Exception as exc:                       # noqa: BLE001
        print(f"[图] {protocol}: 中枢不可用（{type(exc).__name__}: {exc}）"
              f" ⇒ 只用 Phase A 的抽取结果")

    proj_nodes, proj_edges = project_bundle_to_graph(bundle, protocol)

    # ---- 合并（Phase A 的节点/边 + 投影的节点/边）----
    nodes: dict[str, dict] = {}
    # ★★ 阶段 D2：Phase A 节点也补 ``entity_id``（与中枢对齐）
    _eid_by_name = {}
    try:
        _eid_by_name = dict(bundle.get("entity_by_name") or {})
    except Exception:                                   # noqa: BLE001
        _eid_by_name = {}
    for n in phase_a_nodes:
        _d = n.as_dict()
        if not _d.get("entity_id"):
            _d["entity_id"] = _eid_by_name.get(str(_d.get("name") or ""), "")
        nodes[n.node_id] = _d
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
    # ---- B2：社区检测 + 社区报告（Phase B2.1~B2.5）----
    # ★★ **顺序修正**（2026-11-08 实测）：社区计算读的是**磁盘上的图**
    #   ⇒ 必须**先落盘再算社区**（之前在 write_graph 之前调用 ⇒
    #   读到的是**上一次的**图 ⇒ 社区数不稳/为 0）。
    from core.fused.graph.graph_reports import (generate_community_reports,
                                          write_communities)

    paths = write_graph(protocol, node_list, edge_list, extra_meta={
        "community_count": 0,
        "community_algorithm": "none",
        "communities_file": "communities.json",
        "phase_a_node_count": len(phase_a_nodes),
        "phase_a_edge_count": len(phase_a_edges),
        "projected_node_count": len(proj_nodes),
        "projected_edge_count": len(proj_edges),
        "structure_graph": {"nodes": len(struct_nodes), "edges": len(struct_edges)},
        "semantic_graph": {"nodes": len(sem_nodes), "edges": len(sem_edges)},
        "fingerprint": _fingerprint(node_list, edge_list),
    })
    # ---- B2'：**图已落盘** ⇒ 现在算社区（读的就是本次的图）----------
    reports = generate_community_reports(protocol, use_llm=use_llm)
    comms_path = write_communities(protocol, reports)
    # 回填 meta（社区数/算法/文件）
    try:
        _mp = paths["meta"]
        _meta = json.loads(_mp.read_text(encoding="utf-8"))
        _meta["community_count"] = len(reports)
        _meta["community_algorithm"] = (reports[0].get("algorithm")
                                          if reports else "none")
        _meta["communities_file"] = str(comms_path.name)
        _mp.write_text(json.dumps(_meta, ensure_ascii=False,
                                          indent=2) + "\n", encoding="utf-8")
    except (OSError, KeyError, json.JSONDecodeError):
        pass

    return {
        "nodes": len(node_list), "edges": len(edge_list),
        "structure": (len(struct_nodes), len(struct_edges)),
        "semantic": (len(sem_nodes), len(sem_edges)),
        "communities": len(reports),
        "paths": paths,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--llm", action="store_true",
                    help="用 LLM 生成社区报告（默认用缓存或确定性降级）")
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
            r = build_one(p, use_llm=args.llm)
        except Exception as exc:                   # noqa: BLE001
            print(f"[图] {p}: 失败 {type(exc).__name__}: {exc}")
            continue
        if not args.quiet:
            print(f"[图] {p:9s} 节点 {r['nodes']:4d} 边 {r['edges']:4d} | "
                  f"精确图 {r['structure'][0]:3d}/{r['structure'][1]:3d} | "
                  f"社区图 {r['semantic'][0]:3d}/{r['semantic'][1]:3d} | "
                  f"社区 {r['communities']:2d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
