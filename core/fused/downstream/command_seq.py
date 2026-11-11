# -*- coding: utf-8 -*-
"""core/fused/downstream/command_seq.py —— ⑥ 命令序列种子层（**无状态机协议的降级路**）。

★ **动机（2026-11-12 跨协议实测）**
  现有 ①② 层（``edge_cover`` / ``generic_danger``）**都以状态机为骨架**：
  · edge_cover  = 覆盖状态机的**转移边**
  · generic_danger = 状态机的**自环** + **生命周期**
  ⇒ ⇒ 对「规范里没有可确定性抽取的状态转移表」的协议
  （如 SIP：状态是散文；SMTP：规范根本没有状态机）
  ⇒ ⇒ 这两层**产出为空** ⇒ 种子层直接 ``!! 无状态机转移``（退出码 1）⇒
  ⇒ **rfc 单源在 sip / smtp 上到不了种子层**。

★ **本层的作用**
  为**无状态机**的协议提供一条**不依赖状态机**的种子路：
  以 ``profile.seedgen.canonical_flow``（协议档案里人工声明的**黄金命令流程**）
  为骨架 ⇒ 构造「命令序列」型种子。

★ **协议无关性**
  · 判据只用 **profile 的 canonical_flow** + **中枢的方法集** ⇒ **不认协议名**
  · 报文构造复用 ``edge_cover.build_message``（与 ①② 层同一套 ⇒ 必填头/字段实例
    的处理口径完全一致 ⇒ 不引入第二套报文拼装逻辑）

★ **与 ①② 层的关系**
  · **只在「无状态机」时启用** ⇒ 有状态机的协议（rtsp）**完全不受影响**
    （既有语料逐字节不变 ⇒ 回滚手段成立）
  · 产出的种子标 ``generated_by="rule-based:command-sequence"`` ⇒ 可溯源
"""
from __future__ import annotations

from typing import Optional

from core.fused.downstream.edge_cover import build_message
from core.fused.downstream.protocol_flags import cseq_with_method
from core.models import SeedCorpus

#: 本层的 generated_by 标记（写进 manifest ⇒ 可溯源）
COMMAND_SEQ_GENERATED_BY = "rule-based:command-sequence"


def _make_seed(methods: list[str], bundle: dict, protocol: str,
               description: str) -> SeedCorpus:
    """按方法序列构造一条种子（逐条 ``build_message`` ⇒ 与 ①② 层同口径）。"""
    insts = bundle.get("message_instances") or {}
    messages = []
    for i, m in enumerate(methods, start=1):
        messages.append(build_message(
            m,
            required_headers=bundle.get("required_headers"),
            headers=bundle.get("headers"),
            cseq=i,
            # ★ 无状态机 ⇒ 没有 (state, method, to) 三元组 ⇒ 只能按 method 找实例
            instance_fields=insts.get(("*", m, "*")) or _find_by_method(insts, m),
            cseq_with_method=cseq_with_method(protocol),
        ))
    return SeedCorpus(
        protocol=protocol,
        description=description,
        target_state_path=[m.method for m in messages],
        target_methods=[m.method for m in messages],
        messages=messages,
        generated_by=COMMAND_SEQ_GENERATED_BY,
    )


def _find_by_method(insts: dict, method: str) -> Optional[list]:
    """按 method 找一个字段级实例（无状态机时的退化取法）。

    ★ 中枢的 ``message_instances`` 的键是 ``(from_state, method, to_state)``
      ⇒ 无状态机时取不到精确键 ⇒ 这里退化为「**任一**含该 method 的实例」
      ⇒ ★ 取第一个 ⇒ 同一方法的多个实例里只用一个（可复现、稳定）。
    """
    for key, fields in insts.items():
        try:
            _f, m, _t = key
        except (TypeError, ValueError):
            continue
        if str(m).upper() == str(method).upper():
            return fields
    return None


def command_sequence_seeds(bundle: dict, *, protocol: str,
                           canonical_flow: Optional[list] = None
                           ) -> list[SeedCorpus]:
    """构造「命令序列」型种子（**不依赖状态机**）。

    Args:
        bundle: 中枢视图（``methods`` / ``required_headers`` / ``headers`` /
            ``message_instances``）。
        protocol: 协议名。
        canonical_flow: ``profile.seedgen.canonical_flow``（协议档案声明的
            **黄金命令流程**，如 SMTP 的 EHLO→MAIL→RCPT→DATA→QUIT）
            ⇒ 缺省时退化为「按方法集逐个单命令」。

    Returns:
        ``list[SeedCorpus]``（可能为空 ⇒ 说明该协议既无状态机也无黄金流程）。
    """
    methods_known = sorted((bundle.get("methods") or {}).keys())
    flow = [str(x).strip().upper() for x in (canonical_flow or [])
            if str(x).strip()]

    seeds: list[SeedCorpus] = []
    seen: set[tuple] = set()

    def _push(seq: list[str], desc: str) -> None:
        if not seq:
            return
        key = tuple(seq)
        if key in seen:
            return
        seen.add(key)
        seeds.append(_make_seed(seq, bundle, protocol, desc))

    # ① 黄金流程的**前缀**（逐步推进 ⇒ 覆盖命令的各个阶段）
    if flow:
        for i in range(1, len(flow) + 1):
            _push(flow[:i], "command sequence (prefix): " + " -> ".join(flow[:i]))

    # ② 方法集里的**单命令**（每个方法一条 ⇒ 覆盖每个命令的报文形态）
    for m in methods_known:
        _push([m], f"single command: {m}")

    # ③ 若既无黄金流程也无方法集 ⇒ 无产出（调用方据「产出为空」决定降级）
    return seeds
