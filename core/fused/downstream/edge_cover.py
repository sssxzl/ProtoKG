"""core/fused/downstream/edge_cover.py —— ① 结构覆盖层（贪心最小边覆盖，确定性）。

对齐 local/three_layer_seedgen_design.md §四-①：
    把状态机的「边」作为覆盖单位（路径无限、边有限），用贪心 set-cover 从 Init
    出发反复找一条「经过最多未覆盖边」的路径（避免在状态对上死循环），直到所有
    边都被覆盖。不调 LLM、不依赖漏洞，任何有状态机的协议都能产出「结构不遗漏」
    的种子。

    输入：bundle["transitions"]（(from_state, method, to_state) 三元组）。
    产出：list[SeedCorpus]，每条种子对应一条路径，messages 顺序 = 路径上的边顺序。
"""
from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

from core.models import SeedCorpus, SeedMessage
from core.fused.downstream.protocol_flags import cseq_with_method

_INIT_STATE = "Init"

# 注意：不再硬编码任何协议默认字段值（如 Transport/Accept/Range 等）。
# 字段值遵循 AutoSeeder 思想——由 LLM 现场生成的字段级实例（message_instance）提供；
# 无实例时回退知识中枢 headers 取值池首值，再否则留空，交给 fuzzer 变异探索。


def _normalize_transitions(transitions: Iterable, method_order: Optional[dict] = None) -> list:
    """去重 + 规范化（method 大写、去空白）。排序：优先 traffic 会话语序（P2b），
    否则字典序兜底。method_order: {method: rank}（rank 越小越优先）。"""
    out: list = []
    seen: set = set()
    for src, method, dst in transitions:
        key = (str(src).strip(), str(method).strip().upper(), str(dst).strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    order = method_order or {}
    n = len(order)
    return sorted(out, key=lambda t: (order.get(t[1], n), t[0], t[1], t[2]))


def _detect_init(transitions: list) -> str:
    """确定起点：优先 "Init"，否则取无入边的状态，再否则字典序第一个状态。

    ★无入边判断须排除自环（src == dst）：自环边 X --M--> X 的 dst 也是 X，
    若不算自环，会导致「有自环的起点状态」被误判为「有入边」，进而错把
    字典序最小状态（可能是无出边的响应码状态）当起点，edge_cover 无从出发返回空。
    （实测 ftp：State_Connected 有 NOOP/SYST 自环且无真实入边，是唯一起点；
    旧逻辑因自环误判，落到字典序最小状态 '150'（响应码、无出边），种子生成为 0。）
    """
    states = {s for s, _, _ in transitions} | {d for _, _, d in transitions}
    if _INIT_STATE in states:
        return _INIT_STATE
    no_incoming = [s for s in states
                   if not any(d == s for src, _, d in transitions if src != s)]
    if no_incoming:
        # P2：优先选「出边最多」的无入边状态，而非字母序 sorted()[0]。
        # 会话入口（如 SIP 的 Idle、FTP 的 State_Connected）通常出度最大；
        # 字母序首个无入边状态可能落到中间态（如 SIP 的 Early，A < I），
        # 该状态无出边，edge_cover 无从出发返回空、种子生成为 0。
        out_degree = {s: sum(1 for src, _, _ in transitions if src == s)
                      for s in no_incoming}
        return max(no_incoming, key=lambda s: (out_degree[s], s))
    return sorted(states)[0] if states else _INIT_STATE


def _adjacency(transitions: list) -> dict:
    """from_state -> [(method, to_state)]（稳定序）。"""
    adj: dict = {}
    for src, method, dst in transitions:
        adj.setdefault(src, []).append((method, dst))
    return adj


def _lookup_header_info(headers: Optional[dict], name: str) -> dict:
    """按名字（大小写不敏感）在 headers 桶里找字段信息，找不到返回 {}。"""
    if not headers:
        return {}
    if name in headers:
        return headers[name] or {}
    low = name.lower()
    for k, v in headers.items():
        if k.lower() == low:
            return v or {}
    return {}


def _default_header_value(name: str, headers: Optional[dict]) -> str:
    """字段兜底值：只取知识中枢 headers 取值池首值（非协议硬编码），无则空串。"""
    info = _lookup_header_info(headers, name)
    values = info.get("values") or []
    if values:
        return str(values[0])
    return ""


#: 字段级实例里的元字段 + 非请求 header 字段（响应字段等），跳过
#: 注意：url 不在此列——它是消息级字段（request-line 的一部分），单独提取为 SeedMessage.url。
#: command 也不在此列（它复述 method，冗余），argument 单独提取为 SeedMessage.argument。
_NON_REQUEST_FIELDS = {
    "method", "body", "requestline", "request_line",
    "status", "status_line", "resultcode", "result_code", "reason",
    "command", "cmd", "verb",
}

#: argument 字段的别名（行命令协议的命令参数，如 SMTP 的 FROM:<addr>）
_ARGUMENT_FIELDS = {"argument", "arg", "operand", "param"}


def _apply_instance_fields(msg_headers: dict, instance_fields, cseq: int,
                           known_fields: Optional[set] = None) -> tuple[str, str]:
    """把 AutoSeeder 字段级实例的字段值写入 header（跳过元/响应字段，CSeq 用递增）。

    返回 (url, argument)：
      - url      消息级 URL（URL 类协议，LLM 现场生成的会话语义结构）
      - argument 消息级命令参数（行命令协议，如 SMTP 的 FROM:<addr>），无则为空串

    ``known_fields``：该协议**已知头部字段名**的小写集合（来自中枢 ``headers`` 桶）。

      ★ 为什么需要它（2026-11-07 修复）：行命令类协议的实例里，**命令参数名**与
        头部字段混在一起。旧实现只认 ``argument`` 等 4 个别名，其余字段名一律当
        头部塞进报文 ⇒ 实测 SMTP 生成出

            AUTH
            mechanism: <值>          ← 非法：smtp 是命令协议，没有头部

        而正确形态是 ``AUTH PLAIN``（命令 + 参数）。
        ⇒ 现在用**中枢自己的字段知识**判断「这是不是头部」：不在 ``known_fields``
          里的字段名不写头部；若 ``argument`` 尚空，就用它充当命令参数。
        ★ 该判据**协议无关**：不认协议名、不列字段白名单，只问「中枢认不认识这个头」。
          实测 rtsp 0 个、sip 1 个（``url``，已单独处理）未知字段 ⇒ 对它们零影响。
      ★ ``known_fields is None``（调用方没给，或该协议 headers 桶为空）⇒ **保持旧行为**
        （不做该判断），避免把真实头部误移进 argument。
    """
    url = ""
    argument = ""
    _unknown_value = ""      # 未知字段的值 ⇒ 候选命令参数
    for name, value in (instance_fields or []):
        name = (name or "").strip()
        if not name:
            continue
        low = name.lower()
        if low == "url":
            url = str(value) if value is not None else ""
            continue
        if low in _ARGUMENT_FIELDS:
            argument = str(value) if value is not None else ""
            continue
        if low in _NON_REQUEST_FIELDS:
            continue
        if low == "cseq":
            # CSeq 由 build_message 统一递增赋值（含 SIP 的「序号+方法」），
            # 实例里的 CSeq 序号是流量源原始值，会打乱递增序，这里跳过。
            continue
        if known_fields is not None and low not in known_fields:
            if value is not None and not _unknown_value:
                _unknown_value = str(value)
            continue
        msg_headers[name] = str(value) if value is not None else ""
    if not argument:
        argument = _unknown_value
    return url, argument


def _instance_url_pool(message_instances: Optional[dict]) -> list[str]:
    """实例里出现过的 URL 取值（**协议无关**：只认字段名 ``url``，不认协议）。

    ★ 用途（2026-11-07 修复）：URL 类协议里，部分方法的实例不带 ``url``
      （实测 sip 51 条实例只有 14 条带）⇒ 生成的报文缺 Request-URI ⇒ **非法报文**。
      而 ``url_template`` 桶可能为空（当前就是空的），没有别的兜底来源。
      ⇒ 用**同协议同批实例里已出现过的 url** 作为兜底（协议级迁移，不跨协议）。
      对命令类协议（实例里根本没有 url 字段）⇒ 池为空 ⇒ 不兜底，行为不变。
    """
    out = set()
    for fields in (message_instances or {}).values():
        for n, v in (fields or []):
            if str(n or "").strip().lower() == "url" and v:
                out.add(str(v))
    return sorted(out)


def build_message(method: str, *, required_headers: Optional[dict],
                  headers: Optional[dict], cseq: int,
                  instance_fields=None, cseq_with_method: bool = False,
                  url_fallback: str = "",
                  known_fields: Optional[set] = None,
                  entity_headers: Optional[list] = None) -> SeedMessage:
    """构造一条消息：填必填头 + 默认值，再用字段级实例覆盖；CSeq 用递增序号。

    cseq_with_method：SIP 等协议 CSeq 需「序号 + 方法」（如 ``CSeq: 1 REGISTER``），
    为 True 时 CSeq 渲染为 ``<cseq> <method>``；RTSP 等保持纯序号。

    url_fallback：实例没给 URL 时的兜底值（见 `_instance_url_pool`）。
      ★ 空串 ⇒ 不兜底（命令类协议本来就无 URL）。
    known_fields：传给 `_apply_instance_fields` 的「已知头部字段集」，见其 docstring。
    entity_headers：**实体头**清单（如 SMTP DATA 的邮件头 Date/From/To）。
      ★ 2026-11-07（B2）：这类头**不属于命令的头**，而是**消息内容里的头段**
        （RFC 5321 §2.3.9「message content includes the message header section」）
        ⇒ 单独一个参数，不混进 `required_headers`。
        值同样取自 `headers` 桶（RFC 抽取的取值池）⇒ **不硬编码**。
    """
    reqs = (required_headers or {}).get(method, []) or []
    msg_headers: dict = {}
    for h in reqs:
        if h.lower() == "cseq":
            msg_headers[h] = f"{cseq} {method}" if cseq_with_method else str(cseq)
        else:
            msg_headers[h] = _default_header_value(h, headers)
    # ★ 实体头（B2）：与命令头**分开**，值同样取自 headers 桶（RFC 抽取的取值池）
    for h in (entity_headers or []):
        _hn = str(h or "").strip()
        if _hn and _hn not in msg_headers:
            msg_headers[_hn] = _default_header_value(_hn, headers)
    url, argument = _apply_instance_fields(msg_headers, instance_fields, cseq,
                                           known_fields=known_fields)
    if not url and url_fallback:
        url = url_fallback
    return SeedMessage(method=method, headers=msg_headers, body="",
                       url=url, argument=argument)


def build_seed_from_edges(edges: list, *, required_headers: Optional[dict],
                          headers: Optional[dict], init: str,
                          description: str, generated_by: str,
                          message_instances: Optional[dict] = None,
                          protocol: str = "rtsp",
                          cseq_with_method: bool = False,
                          entity_headers: Optional[dict] = None) -> SeedCorpus:
    """把一条边序列（路径）转成 SeedCorpus，messages 顺序 = 边顺序。

    message_instances: {(from, method, to): [(field, value), ...]}，命中则用实例
    字段值填充消息（AutoSeeder 字段级实例），否则回退必填头 + 默认值。
    """
    # ★ 2026-11-07：本批实例的「已知头部字段集」与「URL 兜底值」各算一次
    #   （都在 build 前确定，逐报文复用 ⇒ 不改变确定性，也不引入协议特例）
    _known = ({str(k).strip().lower() for k in headers} if headers else None)
    _pool = _instance_url_pool(message_instances)
    _url_fb = _pool[0] if _pool else ""
    messages: list = []
    states: list = [init]
    for i, (_src, method, dst) in enumerate(edges, start=1):
        inst = (message_instances or {}).get(
            (_src, method.strip().upper(), dst))
        messages.append(build_message(method, required_headers=required_headers,
                                      headers=headers, cseq=i,
                                      entity_headers=(entity_headers or {}).get(
                                          method.strip().upper()),
                                      instance_fields=inst,
                                      cseq_with_method=cseq_with_method,
                                      url_fallback=_url_fb,
                                      known_fields=_known))
        states.append(dst)
    return SeedCorpus(
        protocol=protocol,
        description=description,
        target_state_path=states,
        target_methods=[m for _, m, _ in edges],
        messages=messages,
        generated_by=generated_by,
    )


def _out_edges(adj: dict, state: str, method_order: Optional[dict] = None) -> list:
    """state 的出边（三元组），优先 traffic 会话语序（P2b），否则字典序。"""
    order = method_order or {}
    n = len(order)
    return sorted(
        ((state, m, d) for m, d in adj.get(state, [])),
        key=lambda e: (order.get(e[1], n), e[1], e[2]),
    )


def _bfs_to_uncovered(adj: dict, start: str, uncovered: set, used: set):
    """从 start 出发、避开 used 边，找最近「有未覆盖出边」的状态。

    Returns:
        (target_state, edge_path) 或 (None, None)（找不到）。
        边路径从 start 到 target（不含 target 自身出边）。
    """
    queue = deque([(start, [])])
    visited_edges: set = set()
    while queue:
        state, path = queue.popleft()
        for m, d in adj.get(state, []):
            edge = (state, m, d)
            if edge in used or edge in visited_edges:
                continue
            visited_edges.add(edge)
            new_path = path + [edge]
            if any((d, mm, dd) in uncovered and (d, mm, dd) not in used
                   for mm, dd in adj.get(d, [])):
                return d, new_path
            queue.append((d, new_path))
    return None, None


def _greedy_walk(adj: dict, init: str, uncovered: set,
                 method_order: Optional[dict] = None) -> list:
    """从 init 出发贪心走：优先取当前状态的未覆盖出边；被卡住时经已覆盖边
    （避开本路径已用边）中转，直到覆盖所有可达的未覆盖边。

    每条边在本路径至多出现一次（天然防死循环），因此路径必然终止。
    """
    path: list = []
    used: set = set()
    state = init
    while True:
        cands = [e for e in _out_edges(adj, state, method_order)
                 if e in uncovered and e not in used]
        if cands:
            edge = cands[0]
            path.append(edge)
            used.add(edge)
            state = edge[2]
            continue
        target, transit = _bfs_to_uncovered(adj, state, uncovered, used)
        if target is None:
            break
        for edge in transit:
            path.append(edge)
            used.add(edge)
        state = target
    return path


def edge_cover(transitions, required_headers=None, headers=None,
               message_instances=None, protocol: str = "rtsp",
               method_order: Optional[list] = None,
               entity_headers: Optional[dict] = None) -> list:
    """① 结构覆盖层：贪心最小边覆盖，返回 list[SeedCorpus]。

    Args:
        transitions:       [(from_state, method, to_state)]
        required_headers:  {method: [header, ...]}（填必填头）
        headers:           {header: {syntax, values, occurrence}}（取值池）
        message_instances: {(from, method, to): [(field, value), ...]}
                           （AutoSeeder 字段级实例，命中则用实例字段值）
        protocol:          协议名（写入 SeedCorpus.protocol，供 raw_writer 派发）
        method_order:      traffic 观测的会话语序 [method, ...]（P2b），优先遵循
                           该顺序覆盖边，否则字典序兜底
        entity_headers:    {method: [header, ...]}（**实体头**，B2 2026-11-07）
                           —— 只该命令的**消息内容**里要带的头
                           （如 SMTP DATA 的邮件头 Date/From/To），
                           与「命令头」`required_headers` 分开。
    """
    if not transitions:
        return []
    rank = {m: i for i, m in enumerate(method_order or [])}
    trans = _normalize_transitions(transitions, rank)
    adj = _adjacency(trans)
    init = _detect_init(trans)
    uncovered: set = set(trans)
    seeds: list = []
    index = 0
    while uncovered:
        path = _greedy_walk(adj, init, uncovered, rank)
        if not path:
            break
        new_edges = set(path) & uncovered
        if not new_edges:
            break  # 剩余边从 init 不可达（理论上不应发生），兜底防死循环
        index += 1
        seeds.append(build_seed_from_edges(
            path, required_headers=required_headers, headers=headers,
            init=init, message_instances=message_instances,
            protocol=protocol,
            cseq_with_method=cseq_with_method(protocol),
            entity_headers=entity_headers,
            description="edge-cover path #%d: %s"
                        % (index, " -> ".join(m for _, m, _ in path)),
            generated_by="rule-based:edge-cover",
        ))
        uncovered -= new_edges
    return seeds


__all__ = ["edge_cover"]
