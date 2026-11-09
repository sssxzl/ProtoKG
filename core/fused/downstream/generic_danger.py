"""core/fused/downstream/generic_danger.py —— ② 通用危险层（规则推导，不调 LLM，不依赖漏洞）。

对齐 docs/设计/three_layer_seedgen_design.md §四-②：
    从状态机拓扑自动推导「通用危险模式」，协议无关、永远生效：
      2.1 自环重复    —— 自环边 X --M--> X 连续 2 次（UAF/资源/断言）
      2.2 生命周期    —— 进入 B -> 离开 B -> 再进入 B（UAF）

    全部由规则推导，不调 LLM、不依赖漏洞库。每条种子 generated_by 标记
    "rule-based:generic-danger"。
    （注：2.3 边界取值已移除——它依赖 header 清单做字段类型判断，而 source 源已改
    AutoSeeder 字段级实例（不再有 header 清单），且 AutoSeeder 三策略本无此步。）
"""
from __future__ import annotations

from collections import deque

from .protocol_flags import cseq_with_method
from .edge_cover import (
    _detect_init,
    _normalize_transitions,
    _adjacency,
    build_seed_from_edges,
)

_GENERIC_DANGER_TAG = "rule-based:generic-danger"


def _shortest_path_to_state(adj: dict, target: str, init: str):
    """BFS 找 init -> target 的最短边序列（target == init 返回 []）。"""
    if target == init:
        return []
    queue = deque([(init, [])])
    visited = {init}
    while queue:
        state, path = queue.popleft()
        for m, d in adj.get(state, []):
            new_path = path + [(state, m, d)]
            if d == target:
                return new_path
            if d not in visited:
                visited.add(d)
                queue.append((d, new_path))
    return None


def _self_loop_seeds(trans: list, adj: dict, headers, required_headers, init: str,
                     precondition: dict = None, message_instances: dict = None,
                     protocol: str = "rtsp") -> list:
    """2.1 自环重复：对每个自环边生成「该边连续 2 次」的种子。

    规则（使 Ready --SETUP--> Ready 自然产 SETUP+SETUP）：
      - init 上的自环：直接 [M, M]。
      - 非 init 自环：优先找「同方法入口边 S --M--> src」（优先 S == init），
        得到 [入口, 自环] = M+M（入口非 init 时先加前缀）；找不到入口则
        [前缀到 src] + [自环, 自环]。
    """
    seeds = []
    for src, method, dst in trans:
        if src != dst:
            continue
        if src == init:
            edges = [(src, method, dst), (src, method, dst)]
        else:
            entry = None
            for s2, m2, d2 in trans:
                if m2 == method and d2 == src and s2 != src:
                    if s2 == init:
                        entry = (s2, m2, d2)
                        break
                    if entry is None:
                        entry = (s2, m2, d2)
            if entry is not None and entry[0] == init:
                edges = [entry, (src, method, dst)]
            elif entry is not None:
                prefix = _shortest_path_to_state(adj, entry[0], init)
                if prefix is None:
                    continue
                edges = prefix + [entry, (src, method, dst)]
            else:
                prefix = _shortest_path_to_state(adj, src, init)
                if prefix is None:
                    continue
                edges = prefix + [(src, method, dst), (src, method, dst)]
        # 会话语义：首方法的前置方法（如 SETUP 前置 DESCRIBE）由知识中枢驱动
        edges = _prepend_prerequisite(edges, trans, precondition)
        seeds.append(build_seed_from_edges(
            edges, required_headers=required_headers, headers=headers, init=init,
            message_instances=message_instances, protocol=protocol,
            cseq_with_method=cseq_with_method(protocol),
            description="generic-danger self-loop repeat %s at %s" % (method, src),
            generated_by=_GENERIC_DANGER_TAG,
        ))
    return seeds


def _lifecycle_seeds(trans: list, adj: dict, headers, required_headers, init: str,
                     precondition: dict = None, message_instances: dict = None,
                     protocol: str = "rtsp") -> list:
    """2.2 生命周期：进入 B -> 离开 B -> 再进入 B（entry/exit 边配对）。"""
    seeds = []
    for b, m_exit, a in trans:
        if b == a:
            continue  # 自环不参与生命周期
        for a2, m_entry, b2 in trans:
            if a2 == a and b2 == b:
                prefix = _shortest_path_to_state(adj, a, init)
                if prefix is None:
                    continue
                edges = prefix + [(a, m_entry, b), (b, m_exit, a), (a, m_entry, b)]
                # 会话语义：首方法的前置方法由知识中枢驱动
                edges = _prepend_prerequisite(edges, trans, precondition)
                seeds.append(build_seed_from_edges(
                    edges, required_headers=required_headers, headers=headers, init=init,
                    message_instances=message_instances, protocol=protocol,
                    cseq_with_method=cseq_with_method(protocol),
                    description="generic-danger lifecycle %s -> %s -> %s via %s/%s"
                                % (a, b, a, m_entry, m_exit),
                    generated_by=_GENERIC_DANGER_TAG,
                ))
    return seeds


def _prepend_prerequisite(edges: list, trans: list, precondition: dict) -> list:
    """在边序列前加「首方法的前置方法」对应的边（会话语义：如 SETUP 前置 DESCRIBE）。

    前置方法来自知识中枢 bundle["precondition"]（facts 提取），非硬编码。若无前置方法
    或序列已以该前置方法开头，则不重复加。DESCRIBE 等前置方法取 stateless 边
    （Init→Init），不影响后续状态路径与 CSeq 编号。
    """
    if not edges or not precondition:
        return edges
    first_method = edges[0][1]
    prereqs = precondition.get(first_method) or []
    if not prereqs:
        return edges
    prereq = prereqs[0]
    if edges[0][1] == prereq:
        return edges
    # 优先 stateless 边（Init --prereq--> Init）
    for src, m, dst in trans:
        if m == prereq and src == "Init" and dst == "Init":
            return [(src, m, dst)] + edges
    for src, m, dst in trans:
        if m == prereq:
            return [(src, m, dst)] + edges
    return edges


def _ensure_session_headers(seed, session_header: dict) -> None:
    """按 session_header 知识给消息补会话头（第 N 次出现起携带）。

    会话头规则来自知识中枢 bundle["session_header"]（如 SETUP 第 2 次出现起带 Session），
    非硬编码。运行时占位符统一用 {{session_id}}。
    """
    if not session_header:
        return
    occurrence: dict = {}
    for msg in seed.messages:
        m = msg.method.upper()
        occurrence[m] = occurrence.get(m, 0) + 1
        for rule in session_header.get(m) or []:
            header = (rule or {}).get("header")
            from_occ = (rule or {}).get("from_occurrence", 1)
            if header and occurrence[m] >= from_occ:
                keys = {k.lower() for k in msg.headers}
                if header.lower() not in keys:
                    msg.headers[header] = "{{session_id}}"


def _dedupe_exact(seeds: list) -> list:
    """按 (方法序列, 全部头部) 完整签名去重（只删完全相同的种子，保留边界多样性）。"""
    seen: set = set()
    out: list = []
    for s in seeds:
        sig = (
            tuple(m.method.upper() for m in s.messages),
            tuple((k, v) for m in s.messages for k, v in sorted(m.headers.items())),
        )
        if sig in seen:
            continue
        seen.add(sig)
        out.append(s)
    return out


def _filter_minimal(seeds: list) -> list:
    """精简模式：只保留「序列型」关键危险种子，砍掉冗余的边界/自环。

    实验教训（2026-10-13）：种子过多会把变异预算摊薄到每条路径不足千次，
    导致 fuzzer 无法在关键路径上充分变异。live555 的崩溃根源是 matroska UAF
    （序列型），而非字段溢出。故精简模式只保留：
      - SETUP 自环（双 SETUP，UAF 关键）
      - 含 SETUP+TEARDOWN 的生命周期（建→拆→重建，UAF 关键）
    """
    kept: list = []
    for s in seeds:
        desc = (s.description or "").lower()
        methods = {m.method.upper() for m in s.messages}
        if "self-loop" in desc and "SETUP" in methods:
            kept.append(s)
        elif ("lifecycle" in desc and "SETUP" in methods
              and "TEARDOWN" in methods):
            kept.append(s)
    return kept


def generic_danger(transitions, headers=None, required_headers=None,
                   minimal: bool = False, precondition: dict = None,
                   session_header: dict = None, message_instances: dict = None,
                   protocol: str = "rtsp") -> list:
    """② 通用危险层：自环重复 + 生命周期，返回 list[SeedCorpus]。

    Args:
        transitions:       [(from_state, method, to_state)]
        headers:           {header: {syntax, values, occurrence}}
        required_headers:  {method: [header, ...]}
        minimal:           精简模式（True 时只保留序列型关键种子，见 _filter_minimal）
        precondition:      {method: [前置方法,...]}（知识中枢会话语义，驱动 DESCRIBE 前缀）
        session_header:    {method: [{header, from_occurrence},...]}（知识中枢会话语义，
                           驱动重复方法的 Session 补全）
        message_instances: {(from, method, to): [(field, value), ...]}
                           （AutoSeeder 字段级实例，自环/生命周期种子用实例字段值）
        protocol:          协议名（写入 SeedCorpus.protocol）
    """
    if not transitions:
        return []
    trans = _normalize_transitions(transitions)
    adj = _adjacency(trans)
    init = _detect_init(trans)
    precondition = precondition or {}
    session_header = session_header or {}
    seeds: list = []
    seeds += _self_loop_seeds(trans, adj, headers, required_headers, init,
                              precondition, message_instances, protocol)
    seeds += _lifecycle_seeds(trans, adj, headers, required_headers, init,
                              precondition, message_instances, protocol)
    # 会话语义：按 session_header 知识补会话头（重复方法第 N 次出现起）
    for s in seeds:
        _ensure_session_headers(s, session_header)
    if minimal:
        seeds = _filter_minimal(seeds)
    return _dedupe_exact(seeds)


__all__ = ["generic_danger"]
