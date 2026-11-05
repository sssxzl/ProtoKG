# -*- coding: utf-8 -*-
"""byte-patch：新增 `_align_message_instances()` 并在 assemble_bundle 里调用。

★ 目的：状态机换源（RTSP：骨架 SIP 式 38 条 → RFC 原生 14 条）后，
  `message_instances` 的键（from, method, to）含状态名 ⇒ 旧键再也命中不了
  ⇒ `edge_cover` 取不到字段模板 ⇒ 消息只剩必填头 + **空值**
  （实测 `Transport: ''` / `Session: ''`）⇒ 字段级知识**静默失效**。
  ⇒ 让实例与「当前采用」的那套转移**同源**（不变量：实例键 ⊆ 转移键）。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "fused" / "downstream" / "rag_seedgen.py"

# ── 补丁 1：新增辅助函数（插在 _select_active_transitions 之后）──────
ANCHOR = '''    return sorted({t for rows in by_source.values() for t in rows})
'''

HELPER = '''    return sorted({t for rows in by_source.values() for t in rows})


def _align_message_instances(transitions: list, message_instances: dict,
                             *, allow_migrate: bool) -> dict:
    """把字段级实例对齐到**当前采用**的状态机转移上。

    ★ 为什么要对齐：``message_instances`` 的键是 ``(from, method, to)`` 三元组，
      其中 from/to 是**状态名** ⇒ 一旦状态机换了来源（RTSP 从骨架那套
      SIP 式状态名换成 RFC 原生那套），旧实例的键就再也命中不了
      ⇒ ``edge_cover`` 取不到字段模板 ⇒ 消息只剩必填头 + **空值**
      （实测 ``Transport: ''`` / ``Session: ''``）⇒ 字段级知识**静默失效**。
      ⇒ 必须让实例与采用的那套转移**同源**（不变量：实例键 ⊆ 转移键）。

    ★ 对齐规则：
      ① 原样命中的实例（键恰是采用的转移）⇒ **保留**；
      ② 未命中但**方法相同**的实例 ⇒ 按 method 迁移一份模板到该转移
         （字段取值本身是协议级合法值，与状态名无关 ⇒ 可迁移）；
      ③ 迁移后仍无实例的转移 ⇒ 留空（下游回退必填头 + 默认值）。

    ★ ``allow_migrate``：
      - True（全源 / 含 source 源，与 ``apply_allowed_methods`` 同义）
        ⇒ 执行 ②；
      - False（严格单源，如 ``--sources rfc``）⇒ **只保留命中的**、未命中的
        **剔除** ⇒ 桶与转移严格一致（**纯净度优先**，字段回退必填头）。
    """
    if not message_instances:
        return {}
    trans_set = {(str(s), str(m).strip().upper(), str(d))
                 for s, m, d in transitions}
    # 按 method 建模板索引（确定性：同方法多个实例取字典序最小键）
    by_method: dict[str, list] = {}
    for key in sorted(message_instances):
        by_method.setdefault(str(key[1]).strip().upper(), []).append(key)
    out: dict = {}
    for key in sorted(message_instances):
        k = (str(key[0]), str(key[1]).strip().upper(), str(key[2]))
        if k in trans_set:
            out[k] = message_instances[key]
    if allow_migrate:
        for k in sorted(trans_set):
            if k in out:
                continue
            cands = by_method.get(k[1]) or []
            if not cands:
                continue
            out[k] = message_instances[cands[0]]
    return out
'''

# ── 补丁 2：assemble_bundle 里调用（插在 _inject_vuln_self_loops 之后）─
ANCHOR2 = '''    transitions = _inject_vuln_self_loops(transitions, vuln_patterns, set(methods))
'''

CALL = '''    transitions = _inject_vuln_self_loops(transitions, vuln_patterns, set(methods))
    # ★ 2026-11-05：状态机换源后，字段级实例必须**同步对齐**到采用的那套转移
    #   （否则键命中不了 ⇒ `edge_cover` 取不到字段 ⇒ 消息字段值全空 ⇒
    #   字段级知识静默失效）。
    #   `allow_migrate` 复用 `apply_allowed_methods` —— 它与「本次源集合是否
    #   含 source 源」**完全同义**（见 scripts/seedgen.py:1039）：
    #   全源 ⇒ 允许把源码侧的字段模板迁到规范原生的转移上；
    #   严格单源（--sources rfc）⇒ **不迁移**，只留命中的 ⇒ 纯净度优先。
    message_instances = _align_message_instances(
        transitions, message_instances, allow_migrate=apply_allowed_methods)
'''


def main() -> None:
    text = TARGET.read_bytes().decode("utf-8")
    for name, old, new in (("辅助函数", ANCHOR, HELPER),
                           ("调用点", ANCHOR2, CALL)):
        cnt = text.count(old)
        if cnt != 1:
            print(f"!! 补丁「{name}」匹配数 = {cnt}（应为 1）⇒ 中止", file=sys.stderr)
            raise SystemExit(1)
        text = text.replace(old, new, 1)
        print(f"  补丁「{name}」已应用")
    TARGET.write_bytes(text.encode("utf-8"))
    ast.parse(TARGET.read_text(encoding="utf-8"))
    print("语法自检通过")


if __name__ == "__main__":
    main()
