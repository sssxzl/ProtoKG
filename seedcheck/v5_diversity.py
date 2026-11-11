# -*- coding: utf-8 -*-
"""seedcheck/v5_diversity.py —— **V5 结构多样性**（本次运行统计，阈值告警）。

★ 为什么用「本次运行」而不是历史分布
  · 本项目**没有历史语料分布**数据 ⇒ 用**本次生成内部的自洽性**判断：
    「这批种子自己跟自己比，是否重复得离谱」。
  · 优点：**零外部依赖**、可对任意历史语料重跑、结果可复现。

★ 5 个指标
  ┌─────────────────────────────┬────────────────────────────────┬──────────┐
  │ 指标                          │ 定义                            │ 阈值      │
  ├─────────────────────────────┼────────────────────────────────┼──────────┤
  │ content_dup_rate             │ 1 − 去重后内容数 / 总条数        │ > 5%     │
  │ seq_dup_rate                 │ 1 − 不同方法序列数 / 总条数       │ > 60%    │
  │ first_method_concentration   │ 最高频「首方法」占比              │ > 40%    │
  │ adjacent_identical_rate      │ 含连续两条完全相同报文的种子占比   │ > 20%    │
  │ layer_coverage               │ 五层中非空的层数                │ < 5      │
  └─────────────────────────────┴────────────────────────────────┴──────────┘
  ★ 阈值是**经验值**，首轮跑真实语料后校准 ⇒ 校准依据记进 docs（不拍脑袋）。
  ★ 本模块**只统计 + 告警**，不阻断（统计类阈值会随语料变 ⇒ 硬阻断会天天红）。
"""
from __future__ import annotations

import collections
from typing import Any

from .model import Report, SeedRecord, Violation

#: 默认阈值（经验值 ⇒ 首轮校准）
DEFAULT_THRESHOLDS = {
    "content_dup_rate": 0.05,
    "seq_dup_rate": 0.60,
    "first_method_concentration": 0.40,
    "adjacent_identical_rate": 0.20,
    "layer_coverage_min": 5,
}


def _method_sequence(seed: SeedRecord) -> tuple[str, ...]:
    return tuple(m.get("method", "") for m in seed.messages)


def compute_metrics(seeds: list[SeedRecord], report: Report | None = None) -> dict[str, Any]:
    """算 5 个指标 ⇒ 返回指标字典（同时写进 report.metrics）。"""
    n = len(seeds)
    if n == 0:
        return {}

    # ① 内容重复率
    contents = collections.Counter(s.raw_text for s in seeds)
    uniq_content = len(contents)
    content_dup_rate = 1.0 - (uniq_content / n)

    # ② 序列重复率
    seqs = collections.Counter(_method_sequence(s) for s in seeds)
    seq_dup_rate = 1.0 - (len(seqs) / n)

    # ③ 首方法集中度
    firsts = collections.Counter(
        (s.messages[0].get("method", "") if s.messages else "") for s in seeds)
    first_conc = (max(firsts.values()) / n) if firsts else 0.0

    # ④ 相邻全等率
    adj = 0
    for s in seeds:
        ms = s.messages
        for i in range(1, len(ms)):
            if _msg_key(ms[i]) == _msg_key(ms[i - 1]):
                adj += 1
                break
    adj_rate = adj / n

    # ⑤ 层覆盖（从 manifest 读）
    layers: set[str] = set()
    if report is not None:
        for sl in ((report.metrics or {}).get("_layers") or []):
            layers.add(str(sl))
    if not layers and report is not None:
        layers = set((report.metrics or {}).get("layers") or [])

    metrics = {
        "seed_count": n,
        "unique_content": uniq_content,
        "unique_sequences": len(seqs),
        "content_dup_rate": round(content_dup_rate, 4),
        "seq_dup_rate": round(seq_dup_rate, 4),
        "first_method_concentration": round(first_conc, 4),
        "adjacent_identical_rate": round(adj_rate, 4),
        "layer_coverage": len(layers),
        "layers": sorted(layers),
    }
    if report is not None:
        report.metrics.update(metrics)
    return metrics


def _msg_key(m: dict) -> str:
    """消息指纹（用于「完全相同」判定）。"""
    headers = m.get("headers") or {}
    hs = ";".join(f"{k}:{v}" for k, v in sorted(headers.items()))
    return f"{m.get('method','')}|{m.get('uri','')}|{m.get('version','')}|{hs}"


def check(seeds: list[SeedRecord], report: Report,
          thresholds: dict[str, Any] | None = None) -> list[Violation]:
    """V5 检查 ⇒ 只告警（**不阻断**）。"""
    th = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)
    out: list[Violation] = []

    def _warn(code: str, msg: str, actual: Any, expected: Any) -> None:
        out.append(Violation("V5", code, msg, "", "",
                             f"阈值 {expected}（本次 {actual}）"))

    m = report.metrics
    if m.get("content_dup_rate", 0) > th["content_dup_rate"]:
        _warn("high_content_dup_rate",
              f"内容重复率过高：{m['content_dup_rate']:.1%}"
              f"（{m['unique_content']}/{m['seed_count']} 条内容唯一）",
              f"{m['content_dup_rate']:.1%}", f"{th['content_dup_rate']:.0%}")
    if m.get("seq_dup_rate", 0) > th["seq_dup_rate"]:
        _warn("high_seq_dup_rate",
              f"方法序列重复率过高：{m['seq_dup_rate']:.1%}"
              f"（{m['unique_sequences']} 种序列 / {m['seed_count']} 条）",
              f"{m['seq_dup_rate']:.1%}", f"{th['seq_dup_rate']:.0%}")
    if m.get("first_method_concentration", 0) > th["first_method_concentration"]:
        _warn("first_method_concentrated",
              f"首方法过度集中：{m['first_method_concentration']:.1%}",
              f"{m['first_method_concentration']:.1%}",
              f"{th['first_method_concentration']:.0%}")
    if m.get("adjacent_identical_rate", 0) > th["adjacent_identical_rate"]:
        _warn("high_adjacent_identical_rate",
              f"相邻全等报文占比过高：{m['adjacent_identical_rate']:.1%}"
              "（注：重复**同一方法**是有意的变异维度，仅完全相同的连续报文才计）",
              f"{m['adjacent_identical_rate']:.1%}",
              f"{th['adjacent_identical_rate']:.0%}")
    if m.get("layer_coverage", 0) < th["layer_coverage_min"]:
        _warn("layer_coverage_low",
              f"种子层覆盖不足：{m.get('layer_coverage', 0)} 层"
              f"（期望 ≥ {th['layer_coverage_min']}）",
              m.get("layer_coverage", 0), th["layer_coverage_min"])
    return out
