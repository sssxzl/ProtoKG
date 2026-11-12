# -*- coding: utf-8 -*-
"""core/fused/extraction/window_candidates.py —— **窗口级 LLM 补漏**（第二批）。

★ 对应改进计划 §5：

  | 规则 | 内容 |
  |---|---|
  | **候选信号** | 规范性关键词 · 条件句式 · 异常/错误处理 · 跨节引用 ⇒ ★ **只是候选信号**，不是「存在未抽取知识」的证明 |
  | **判定粒度** | ★ **先在段落 / 语义块上判候选**，再组织所需上下文窗口 ⇒ ⇒ 不让边缘词触发整个大窗口 |
  | **独立抽样漏检检查** | ★ 从**未触发 LLM 的段落**中抽样 ⇒ ⇒ 检查是否含被触发策略漏掉的规范义务 ⇒ ⇒ 统计漏检迹象 |

★ ★ **去重**（两级）
  ① **声明级**：规范化语义身份 + 证据区间 ⇒ 去掉重叠窗口的重复抽取
  ② **事实级**：规范化语义身份 ⇒ 同一事实可关联多条证据
  ⇒ ⇒ 原则：**一条证据可支持多条事实；一条事实可有多条证据**。

★ ★ **运行保护**（★ 影子模式不是「零运行风险」）
  单请求超时 · 最大重试次数 · 并发限制 · 重复调用检测 · 异常熔断与失败日志。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

#: ★ **候选信号**（★ 只是信号，不是证明）
NORMATIVE_KEYWORDS: tuple[str, ...] = (
    "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT",
    "REQUIRED", "RECOMMENDED", "NOT RECOMMENDED", "MAY", "OPTIONAL",
)
CONDITION_PATTERNS: tuple[str, ...] = (
    r"\bif\b", r"\bwhen\b", r"\bunless\b", r"\bexcept\b", r"\bin case\b",
    r"\bprovided that\b", r"\bsubject to\b",
)
ERROR_PATTERNS: tuple[str, ...] = (
    r"\berror\b", r"\btimeout\b", r"\btime-out\b", r"\bretry\b",
    r"\bfailure\b", r"\bfail\b", r"\bmust not\b.*\baccept\b",
)
CROSS_REF_PATTERNS: tuple[str, ...] = (
    r"\bsee\s+(?:section|clause|Section|Clause)\s*[\d.]+",
    r"\bas defined in\s+(?:section|Section)\s*[\d.]+",
    r"\brefer to\s+(?:section|Section)\s*[\d.]+",
)

#: 触发原因标签
TRIGGER_NORMATIVE = "normative_keyword"
TRIGGER_CONDITION = "condition_pattern"
TRIGGER_ERROR = "error_handling"
TRIGGER_CROSS_REF = "cross_reference"


@dataclass
class Candidate:
    """一个**候选段落**（★ 判定粒度 = 段落 / 语义块）。"""

    doc: str
    start_line: int          # 段落起始行（原始行号，1 起始）
    end_line: int            # 段落结束行（含）
    text: str
    triggers: list[str] = field(default_factory=list)

    @property
    def span(self) -> tuple[int, int]:
        return (self.start_line, self.end_line)


def _paragraphs(lines: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """把内容行切成**段落**（★ 空行分段）。

    Args:
        lines: ``[(原始行号, 行文本), …]``。

    Returns:
        ``[(起始原始行号, 结束原始行号, 段落文本), …]``
    """
    _out: list[tuple[int, int, str]] = []
    _cur: list[tuple[int, str]] = []
    for _no, _tx in lines:
        if not _tx.strip():
            if _cur:
                _out.append((_cur[0][0], _cur[-1][0],
                             "\n".join(t for _n, t in _cur)))
                _cur = []
            continue
        _cur.append((_no, _tx))
    if _cur:
        _out.append((_cur[0][0], _cur[-1][0],
                     "\n".join(t for _n, t in _cur)))
    return _out


def detect_triggers(text: str) -> list[str]:
    """检测段落里的**候选信号**（★ 返回触发原因标签）。

    ★ ★ 边界（RFC 8174）：**「不含关键词」≠「不具规范性」**
      ⇒ ⇒ 这里只做**候选筛选**（宁可多召回，缺口由独立抽样检查兜底）
      ⇒ ⇒ **不**据此断言「该段落没有规范义务」。
    """
    _out: list[str] = []
    _u = text.upper()
    if any(_k in _u for _k in NORMATIVE_KEYWORDS):
        _out.append(TRIGGER_NORMATIVE)
    if any(re.search(_p, text, re.I) for _p in CONDITION_PATTERNS):
        _out.append(TRIGGER_CONDITION)
    if any(re.search(_p, text, re.I) for _p in ERROR_PATTERNS):
        _out.append(TRIGGER_ERROR)
    if any(re.search(_p, text, re.I) for _p in CROSS_REF_PATTERNS):
        _out.append(TRIGGER_CROSS_REF)
    return _out


def find_candidates(lines: list[tuple[int, str]], *,
                    min_paragraph_chars: int = 40,
                    max_paragraph_chars: int = 6000) -> list[Candidate]:
    """在**段落粒度**上找候选（★ 不让边缘词触发整个大窗口）。

    Args:
        lines: ``[(原始行号, 行文本), …]``（清洗后的内容行）。
        min_paragraph_chars: 短于此长度的段落**不判候选**（★ 避免噪声）。
        max_paragraph_chars: 超长段落**截断**（★ 控制单次上下文）。

    Returns:
        候选列表。
    """
    _out: list[Candidate] = []
    for _s, _e, _txt in _paragraphs(lines):
        if len(_txt) < min_paragraph_chars:
            continue
        _trig = detect_triggers(_txt)
        if not _trig:
            continue
        _body = _txt[:max_paragraph_chars]
        _out.append(Candidate(doc="", start_line=_s, end_line=_e,
                              text=_body, triggers=_trig))
    return _out


def dedup_declarations(candidates: list[Candidate], *,
                       semantic_keys: Optional[dict] = None) -> list[Candidate]:
    """**声明级去重**：同一「语义身份 + 证据区间」只留一条。

    ★ **不是**只按证据区间去重（★ 那会误删同一行里的不同义务）
    ⇒ ⇒ 键 = ``(语义身份, 起始行, 结束行)``；无语义身份时退化为证据区间。

    Args:
        candidates: 候选列表。
        semantic_keys: ``{候选索引: 语义身份键}``（可选 ⇒ 有则参与去重）。

    Returns:
        去重后的候选列表。
    """
    _seen: set = set()
    _out: list[Candidate] = []
    for _i, _c in enumerate(candidates or []):
        _sk = (semantic_keys or {}).get(_i, "")
        _key = (_sk, _c.start_line, _c.end_line)
        if _key in _seen:
            continue
        _seen.add(_key)
        _out.append(_c)
    return _out


# ===========================================================================
# 运行保护（★ 影子模式不是「零运行风险」）
# ===========================================================================

@dataclass
class RunGuard:
    """LLM 调用的**运行保护**（超时 / 重试 / 并发 / 熔断）。"""

    timeout_seconds: int = 180
    max_retries: int = 2
    max_concurrency: int = 4
    max_calls: int = 0            # 0 ⇒ 不限（★ 「不设硬成本上限」已拍板）
    circuit_breaker_threshold: int = 5     # 连续失败达此数 ⇒ 熔断

    calls: int = 0
    retries: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    tripped: bool = False
    duplicates: set = field(default_factory=set)

    def before_call(self, dedup_key: str) -> Optional[str]:
        """调用前检查 ⇒ 返回**拒绝原因**（None ⇒ 允许）。"""
        if self.tripped:
            return "熔断已触发（连续失败过多）"
        if self.max_calls and self.calls >= self.max_calls:
            return f"达到调用上限（{self.max_calls}）"
        if dedup_key and dedup_key in self.duplicates:
            return "重复调用检测命中（同一输入已发过）"
        if dedup_key:
            self.duplicates.add(dedup_key)
        self.calls += 1
        return None

    def on_success(self) -> None:
        self.consecutive_failures = 0

    def on_failure(self) -> None:
        self.failures += 1
        self.retries += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            self.tripped = True

    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "retries": self.retries,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "tripped": self.tripped,
            "max_calls": self.max_calls,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_concurrency": self.max_concurrency,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
        }


__all__ = [
    "NORMATIVE_KEYWORDS", "CONDITION_PATTERNS", "ERROR_PATTERNS",
    "CROSS_REF_PATTERNS", "TRIGGER_NORMATIVE", "TRIGGER_CONDITION",
    "TRIGGER_ERROR", "TRIGGER_CROSS_REF",
    "Candidate", "detect_triggers", "find_candidates", "dedup_declarations",
    "RunGuard",
]
