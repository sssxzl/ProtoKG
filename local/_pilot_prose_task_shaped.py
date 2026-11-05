#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""试点（任务形）：散文候选句经**真实约束提示词**能产出多少可用规则？

★ 与上一轮试点的**关键差异**：
  上一轮用的是「这条是不是约束？」的**分类式**提示 ⇒ 3.3% 产出率；
  但**生产链路真正做的事**是「把这句话结构化成约束」（field/operator/operand/
  expected_class）⇒ 分类式的拒绝会**误杀**那些「能结构化但不含 MUST」的句子。
  ⇒ 本轮用**生产同款提示词**（`_PROMPT_CONSTRAINT`）直接做抽取。

★ 指标口径（对齐生产链路）：
  「可用」= LLM 产出了 operator（在受控词表内）+ field 能绑到协议已知字段集
  ⇒ 这正是能进入 legal_boundary 桶、进而变成种子约束知识的条件。

★ 零写盘（除本脚本）、零仓库改动。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402
from core.fused.rfc_extractor import (  # noqa: E402
    _CONSTRAINT_RE, _MAX_SENT, _MIN_SENT, _PROMPT_CONSTRAINT,
    known_field_set,
)
from core.fused.semantic import OPERATORS  # noqa: E402
from core.fused.semantic_rules import bind_field  # noqa: E402

PROTOCOLS = ("rtsp", "sip", "smtp")
PER_PROTOCOL = 40

_RE_TOC = re.compile(r"\.{3,}")
_RE_SECTION_HEAD = re.compile(r"^\d+(\.\d+)*\s+[A-Za-z]")
_RE_CONTEXT = re.compile(
    r"\b(not|reject|error|invalid|respond|return|require|mandatory|forbidden"
    r"|only|absent|missing|shall|must|should|may)\b", re.IGNORECASE)


def collect(protocol: str, n: int) -> list[str]:
    """三层收窄 + 排除 TOC/标题行 + 均匀抽样（步长法 ⇒ 可复现）。"""
    pool: list[str] = []
    for f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        raw = f.read_text(encoding="utf-8", errors="ignore")
        for line in raw.splitlines():
            s = line.strip()
            if not (_MIN_SENT <= len(s) <= _MAX_SENT):
                continue
            if _CONSTRAINT_RE.search(s):
                continue                      # L2：已被确定性抽取覆盖
            if _RE_TOC.search(s) or _RE_SECTION_HEAD.match(s):
                continue                      # 目录行 / 章节标题行
            if not _RE_CONTEXT.search(s):
                continue                      # L3：无规范动词或无约束语境
            pool.append(s)
    if len(pool) > n:
        step = len(pool) / n
        return [pool[int(i * step)] for i in range(n)]
    return pool


def main() -> int:
    from core.llm import DeepSeekClient
    client = DeepSeekClient()
    print(f"LLM: {client.model}\n")

    total_sent = total_usable = total_field_bound = 0
    per_proto: dict[str, tuple[int, int]] = {}
    samples: list[str] = []

    for proto in PROTOCOLS:
        items = collect(proto, PER_PROTOCOL)
        if not items:
            continue
        text = "\n\n".join(f"[{i}] {t}" for i, t in enumerate(items))
        try:
            resp = client.chat_json(
                system="你输出 JSON。",
                user=_PROMPT_CONSTRAINT.format(protocol=proto.upper(), text=text),
                temperature=0.2, max_tokens=4000)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{proto}] 调用失败：{type(exc).__name__}: {exc}")
            continue

        fields = set(known_field_set(proto))
        n_usable = n_bound = 0
        rows = (resp or {}).get("constraints") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            op = str(row.get("operator") or "").strip()
            if op not in OPERATORS:
                continue
            operand = row.get("operand") or []
            if op not in ("present", "absent") and not operand:
                continue
            n_usable += 1
            field = str(row.get("field") or "").strip()
            if field and bind_field(field, fields):
                n_bound += 1
                if len(samples) < 5:
                    samples.append(f"    [{proto}] field={field!r} op={op} "
                                   f"operand={operand}")
        total_sent += len(items)
        total_usable += n_usable
        total_field_bound += n_bound
        per_proto[proto] = (n_usable, n_bound)
        print(f"  {proto:5s} 送样 {len(items):3d} → 有可用算子 {n_usable:3d} "
              f"→ 字段可绑 {n_bound:3d}")

    print()
    print("=== 任务形试点产出率 ===")
    print(f"  送样 {total_sent} 条")
    print(f"  产出可用算子 {total_usable} 条（{total_usable / max(1, total_sent) * 100:.1f}%）")
    print(f"  **字段可绑（能进种子知识）{total_field_bound} 条"
          f"（{total_field_bound / max(1, total_sent) * 100:.1f}%）**")
    if samples:
        print("\n  样例：")
        for s in samples:
            print(s)
    print()
    print("★ 判读：字段可绑率 ≥ 20% ⇒ 散文 LLM 值得铺开（按「性能优先」原则）；")
    print("  ≤ 5% ⇒ 确定性路线（扩池 + ABNF + 状态机表）仍是更优解。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
