"""tests/fused/test_edge_cover.py —— ① 结构覆盖层（贪心最小边覆盖）。"""
from __future__ import annotations

from core.fused.downstream.edge_cover import edge_cover
from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle


def _bundle():
    return assemble_bundle(load_fact_views())


def _seed_edges(seed):
    """从 target_state_path + messages 重建种子覆盖的边（三元组）。"""
    states = seed.target_state_path
    methods = [m.method for m in seed.messages]
    assert len(states) == len(methods) + 1, "target_state_path 长度应 = 消息数 + 1"
    return [(states[i], methods[i], states[i + 1]) for i in range(len(methods))]


def test_edge_cover_covers_all_reachable_edges():
    b = _bundle()
    trans = set(b["transitions"])
    assert trans, "应有状态机转移"
    seeds = edge_cover(b["transitions"], b["required_headers"], b["headers"])

    assert seeds, "应产出至少 1 条结构基线种子"
    assert len(seeds) <= 10, "结构覆盖种子数应 <= 10"

    covered = set()
    for s in seeds:
        for edge in _seed_edges(s):
            assert edge in trans, "每条消息序列都必须是合法状态转移"
            covered.add(edge)
    # 覆盖所有「从 Init 可达」的边（孤立状态如 Registering/Deregistering 无入边，
    # 从 Init 不可达，edge_cover 无法覆盖属正常）
    init = "Init"
    reachable = {init}
    adj: dict = {}
    for s, _m, d in trans:
        adj.setdefault(s, []).append(d)
    changed = True
    while changed:
        changed = False
        for s in list(reachable):
            for d in adj.get(s, []):
                if d not in reachable:
                    reachable.add(d)
                    changed = True
    reachable_edges = {e for e in trans if e[0] in reachable}
    assert covered == reachable_edges, "必须覆盖全部可达边"


def test_edge_cover_fills_required_headers():
    b = _bundle()
    seeds = edge_cover(b["transitions"], b["required_headers"], b["headers"])
    for s in seeds:
        assert s.generated_by == "rule-based:edge-cover"
        for m in s.messages:
            reqs = b["required_headers"].get(m.method, [])
            for h in reqs:
                assert h in m.headers, "必填头不能缺"


def test_edge_cover_empty_transitions_returns_empty():
    assert edge_cover([]) == []
