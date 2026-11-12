# -*- coding: utf-8 -*-
"""core/fused/extraction/coverage_ledger.py —— **覆盖台账（两本）**（第一批）。

★ 对应改进计划 §4：

  | 台账 | 回答的问题 | 记录内容 |
  |---|---|---|
  | **文本覆盖** | 原文是否**到达**了抽取输入？ | 三段映射：**原始输入** →（清洗 / TOC 隔离）→ **清洗后正文** →（窗口归属）→ **抽取窗口** |
  | **抽取覆盖** | 哪些知识**尝试抽过**、哪些**仍有候选**？ | 通道执行情况、产出事实、LLM 触发原因、**拒收原因**、未处理候选 |

★ ★ **结构化命中 ≠ 知识覆盖完整**
  ⇒ 「某窗口的字段表解析成功」**不能**证明「该窗口里的条件性散文义务已被抽出」
  ⇒ ⇒ 两本台账**不可互相替代**。

★ ★ **两项覆盖率指标**（★ 不用单一分母）
  ① **原始输入核算率**：分母 = **原始输入全部行** ⇒ 每个原文区间都有明确去向
     （保留 / 合理排除 / 待检查）⇒ ⇒ 清洗误删会**暴露**
  ② **有效正文窗口覆盖率**：分母 = **已确认属于抽取范围的正文** ⇒ 衡量是否进入窗口
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: 行号的去向分类
KEPT = "kept"              # 保留（进入清洗后正文）
EXCLUDED = "excluded"      # 合理排除（清洗 / TOC / 页眉页脚）
PENDING = "pending"        # 待检查（★ 无法判定 ⇒ 不计入有效正文）
TRUNCATED = "truncated"    # 被预算截断
DEDUPED = "deduped"        # 因去重被丢弃
IN_WINDOW = "in_window"    # 进入抽取窗口


@dataclass
class TextCoverage:
    """**文本覆盖**台账（★ 原文是否到达了抽取输入）。"""

    protocol: str = ""
    source: str = "rfc"
    #: 原始行数
    raw_lines: int = 0
    #: 清洗后正文行数
    content_lines: int = 0
    #: 清洗/TOC 隔离掉的行数
    excluded_lines: int = 0
    #: 原始行 → 清洗后正文的映射（原始行号 → 新行号；不在映射内 ⇒ 被排除）
    line_map: dict[int, int] = field(default_factory=dict)
    #: 排除原因计数：``{原因: 行数}``
    excluded_reasons: dict[str, int] = field(default_factory=dict)
    #: 进入抽取窗口的正文行（新行号集合）
    in_window: set[int] = field(default_factory=set)
    #: 被预算截断的正文行
    truncated: set[int] = field(default_factory=set)
    #: 因去重被丢弃的正文行
    deduped: set[int] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "source": self.source,
            "raw_lines": self.raw_lines,
            "content_lines": self.content_lines,
            "excluded_lines": self.excluded_lines,
            "excluded_reasons": dict(self.excluded_reasons),
            "in_window_lines": len(self.in_window),
            "truncated_lines": len(self.truncated),
            "deduped_lines": len(self.deduped),
            # ★ 两项覆盖率
            "raw_accounting_rate": self.raw_accounting_rate(),
            "content_window_coverage_rate": self.content_window_coverage_rate(),
            "pending_lines": max(0, self.raw_lines - self.content_lines
                                 - self.excluded_lines),
        }

    def raw_accounting_rate(self) -> float:
        """**原始输入核算率**：每个原始行都有明确去向的比例（★ 分母 = 原始输入）。"""
        if not self.raw_lines:
            return 1.0
        _accounted = (self.content_lines + self.excluded_lines)
        return round(min(1.0, _accounted / self.raw_lines), 4)

    def content_window_coverage_rate(self) -> float:
        """**有效正文窗口覆盖率**：有效正文进入抽取窗口的比例（★ 分母 = 有效正文）。"""
        if not self.content_lines:
            return 1.0
        return round(min(1.0, len(self.in_window) / self.content_lines), 4)


@dataclass
class ExtractionCoverage:
    """**抽取覆盖**台账（★ 哪些知识尝试抽过、哪些仍有候选）。"""

    protocol: str = ""
    source: str = "rfc"
    #: 各通道的产出条数：``{通道名: 条数}``
    channel_outputs: dict[str, int] = field(default_factory=dict)
    #: LLM 触发原因计数：``{原因: 次数}``
    llm_triggers: dict[str, int] = field(default_factory=dict)
    #: LLM 调用次数 / 产出的候选数 / 确认数 / 拒收数
    llm_calls: int = 0
    candidates: int = 0
    confirmed: int = 0
    rejected: int = 0
    pending: int = 0
    #: 拒收原因计数
    reject_reasons: dict[str, int] = field(default_factory=dict)
    #: 未处理候选（★ 候选识别器从未识别 ⇒ 进不了这里 ⇒ 需独立抽样检查）
    unprocessed_candidates: list[dict] = field(default_factory=list)
    #: ★ 独立抽样漏检检查的结果
    sampling_check: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "source": self.source,
            "channel_outputs": dict(self.channel_outputs),
            "llm_triggers": dict(self.llm_triggers),
            "llm_calls": self.llm_calls,
            "candidates": self.candidates,
            "confirmed": self.confirmed,
            "rejected": self.rejected,
            "pending": self.pending,
            "reject_reasons": dict(self.reject_reasons),
            "unprocessed_candidates": len(self.unprocessed_candidates),
            "sampling_check": dict(self.sampling_check),
        }


@dataclass
class CoverageLedger:
    """**两本台账的容器**（★ 产物走元数据 ⇒ **不进 fact 空间** ⇒ 中枢零影响）。"""

    text: TextCoverage = field(default_factory=TextCoverage)
    extraction: ExtractionCoverage = field(default_factory=ExtractionCoverage)

    def to_dict(self) -> dict:
        return {"text_coverage": self.text.to_dict(),
                "extraction_coverage": self.extraction.to_dict()}

    def write(self, path: Path) -> Path:
        """写出台账（★ JSON ⇒ **不进 fact 空间** ⇒ 中枢零影响）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path


def build_text_coverage(protocol: str, *, raw_lines: int,
                        line_map: dict[int, int],
                        excluded_reasons: Optional[dict] = None,
                        source: str = "rfc") -> TextCoverage:
    """由「原始行 → 清洗后正文」的映射构造文本覆盖台账。

    Args:
        protocol: 协议名。
        raw_lines: 原始总行数。
        line_map: ``{原始行号: 新行号}``（只含**保留**的行）。
        excluded_reasons: ``{原因: 行数}``（清洗 / TOC 隔离等）。
        source: 源名。
    """
    _tc = TextCoverage(protocol=protocol, source=source,
                       raw_lines=raw_lines,
                       content_lines=len(line_map),
                       excluded_lines=max(0, raw_lines - len(line_map)),
                       line_map=dict(line_map),
                       excluded_reasons=dict(excluded_reasons or {}))
    return _tc


def merge_excluded_reason(counter: dict[str, int], reason: str,
                          count: int = 1) -> dict[str, int]:
    """排除原因计数累加（★ 便于定位「误删」）。"""
    counter[reason] = counter.get(reason, 0) + max(0, int(count))
    return counter


def sampling_miss_check(ledger: ExtractionCoverage, *, sampled: list[dict],
                        missed: int) -> dict:
    """**独立抽样漏检检查**的结果（★ 未触发 LLM 的段落抽样）。

    ★ 为什么需要（★ 逻辑必然）：候选识别器**从未识别**过的文本 ⇒ 进不了
      「未处理候选」集合 ⇒ ⇒ 只靠台账**发现不了**这类漏抽 ⇒ 必须有独立抽样路径。

    Args:
        ledger: 抽取覆盖台账（写回 ``sampling_check``）。
        sampled: 抽样命中的段落（每项含 ``doc`` / ``span`` / ``has_obligation``）。
        missed: 抽样中发现的**漏检**条数。

    Returns:
        抽样检查摘要。
    """
    _n = len(sampled)
    _rate = round(missed / _n, 4) if _n else 0.0
    ledger.sampling_check = {
        "sampled_paragraphs": _n,
        "missed_obligations": missed,
        "miss_rate": _rate,
        "note": ("★ 独立抽样检查（未触发 LLM 的段落）⇒ 用于调整触发规则；"
                 "★ 不要求全量调用 LLM"),
    }
    return ledger.sampling_check


__all__ = [
    "KEPT", "EXCLUDED", "PENDING", "TRUNCATED", "DEDUPED", "IN_WINDOW",
    "TextCoverage", "ExtractionCoverage", "CoverageLedger",
    "build_text_coverage", "merge_excluded_reason", "sampling_miss_check",
]
