# -*- coding: utf-8 -*-
"""core/fused/state_graph.py —— **状态图通用分析**（中枢层，2026-11-09 新增）。

★ **为什么放这里**（层次分明的原则）：
  「哪个状态是初始状态」是**状态图本身的通用性质**，既被**消费层**
  （``edge_cover`` 选起点）用，也被 **GraphRAG 整理层**
  （``graph_query`` 路径检索的起点）用。
  ⇒ 放在**中枢层** ⇒ 两层**并列**依赖它 ⇒ 无倒置
  （原先 ``graph_query`` 反向 import 消费层的 ``edge_cover``）。

★ 判据（成熟判据，**协议无关**）：
  ① 优先 ``Init``；
  ② 否则取**无入边**的状态（**排除自环**：``src == dst`` 不算入边）；
  ③ 若多个无入边状态 ⇒ 取**出度最大**者（会话入口通常出度最大）；
  ④ 再否则取字典序第一个。
"""
from __future__ import annotations

_INIT_STATE = "Init"


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


__all__ = ["_detect_init", "_INIT_STATE"]
