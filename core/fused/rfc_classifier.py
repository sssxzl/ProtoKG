# -*- coding: utf-8 -*-
"""core/fused/rfc_classifier.py —— **独立**的「从内容判定类别」通道（2026-11-08 新增）。

★ 这是 GraphRAG 改造 **批次 2 / S1** 的产物：一条**与旧通道（章节号配置）
  完全并行**的新判据通道，用来做 E-1 对照实验。

★ 与旧通道的关系：
  ┌────────────────────────────┬──────────────────────────────┐
  │ 旧通道（``_section_kind``）   │ 新通道（本模块）                │
  ├────────────────────────────┼──────────────────────────────┤
  │ 判据：**章节号** ∈ 配置清单   │ 判据：**内容**（形态/标题/句式）    │
  │ 配置：``rfc_config.json``    │ 配置：**无**（协议无关）           │
  │ 覆盖：6 类                  │ 覆盖：6 类（★ 必须对齐，见下）      │
  │ 失败模式：多 RFC 章节号撞车   │ 失败模式：内容形态歧义            │
  └────────────────────────────┴──────────────────────────────┘

★ **S3（清除旧通道）的前置条件**：本通道必须覆盖旧通道的**全部 6 类**
  （method / field / status / transition / outcome / required_header），
  否则删掉旧通道就没有分类依据。

★ **四层判据链**（优先级从高到低）：

  ┌────┬──────────────────┬────────────────────────────────────────┐
  │ 层 │ 判据              │ 例子                                    │
  ├────┼──────────────────┼────────────────────────────────────────┤
  │ L-A │ **形态**（块级）   │ table⇒field/transition；abnf⇒field；   │
  │     │                  │ diagram⇒transition/method               │
  │ L-B │ **标题形态**       │ PascalCase⇒field；全大写⇒method；      │
  │     │                  │ 3 位数字⇒status                        │
  │ L-C │ **正文句式**       │ "the format of the X command is"⇒method│
  │     │                  │ "X MUST be included in"⇒required_header │
  │ L-D │ **章节号兜底**     │ 复用旧通道（仅当 L-A/B/C 都判不出）    │
  └────┴──────────────────┴────────────────────────────────────────┘

★ **L-D 是兜底**：这让本通道在**任何**输入下都有答案 ⇒ 可以与旧通道
  做**逐条**对比（不会出现「旧通道有、新通道没有」的不可比状态）。
"""
from __future__ import annotations

import re
from typing import Any, Optional

# ===========================================================================
# L-A：形态判据
# ===========================================================================

#: 判定类别集合（★ 与旧通道对齐 —— 6 类）
KINDS: tuple[str, ...] = ("method", "field", "status", "transition",
                          "outcome", "required_header")

#: PascalCase / 连字符式头名（``Content-Length`` / ``User-Agent`` / ``ETag``）
RE_PASCAL_HEADER = re.compile(r"^[A-Z][a-z0-9]*(?:-[A-Za-z0-9]+)+$")

#: 单个**驼峰**词（``CSeq`` / ``ETag`` / ``Via`` / ``MD5``）
#:   ★ 形态要点：首字母大写 + **允许内部大写**（``CSeq`` 有内部的 S）
#:     ⇒ 但要排除「**纯全大写**」（那是方法名，如 ``OPTIONS``）。
RE_PASCAL_WORD = re.compile(r"^[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*$")

#: 全大写方法名（``OPTIONS`` / ``MAIL`` / ``DHCPDISCOVER``）
RE_UPPER_METHOD = re.compile(r"^[A-Z][A-Z0-9_-]{1,30}$")

#: 3 位状态码（``200`` / ``401``）
RE_STATUS_CODE = re.compile(r"^\d{3}$")

#: L-C：选项/字段的**登记形态**（RFC 的选项登记表）
#:   RFC 3679 §3.2.3：``Code:  114`` / ``Name:  URL`` ⇒ 这是**选项**，不是方法
RE_OPTION_REGISTRY = re.compile(
    r"^\s*(?:Code|Name|Defined in|Length|Data type)\s*:\s*\S",
    re.IGNORECASE | re.MULTILINE)

#: L-C：方法声明句式（**已有形态 E 的同一句式**，协议无关）
RE_CMD_FORMAT = re.compile(
    r"\b(?:[Tt]he\s+)?(?:[Ff]ormat|[Ss]yntax)\s+(?:of|for)\s+(?:[Tt]he\s+)?"
    r"([A-Z][A-Z0-9_\-]{1,19})\s+(?:command|method)\s+(?:is|are)\b")

#: L-C：必填头句式（「X MUST be included in every…」）
RE_REQUIRED_HEADER = re.compile(
    r"\b([A-Z][A-Za-z0-9\-]{1,30})\s+(?:MUST|SHALL)\s+"
    r"(?:be\s+)?(?:included|present|appear|used|carried)", re.IGNORECASE)

#: L-C：响应/结果句式（「The server MUST respond with…」）
RE_OUTCOME = re.compile(
    r"\b(?:respond|reply|answer|return)s?\s+with\b|"
    r"\b(?:error|status)\s+code\b", re.IGNORECASE)


def _classify_by_form(window: dict[str, Any]) -> Optional[str]:
    """L-A：按**窗口文本的形态**判定。

    ★ 窗口来自章节树，不带形态 ⇒ 这里用形态层对**窗口文本**重新分块。
    """
    text = window.get("text") or ""
    if not text.strip():
        return None
    from core.fused.rfc_forms import (classify_form, form_candidates,
                                      _match_roles, _split_columns)
    try:
        blocks = form_candidates(text.split("\n"))
    except Exception:                               # noqa: BLE001
        blocks = []
    kinds = [b.kind for b in blocks] or [classify_form(text.split("\n"))]
    has_table = "table" in kinds
    has_abnf = "abnf" in kinds
    has_diagram = "diagram" in kinds
    # ★ **不消费 example 形态**（2026-11-08，遵守项目铁律）：
    #   `example` 判据一旦收紧，抽取产物就会变 ⇒ 任何新消费方都必须
    #   同步补产物回归（tests/fused/test_example_form_tightened.py 的守卫
    #   会强制报红）。
    #   ⇒ 本通道**不需要**区分示例块（示例块本来就不该产出知识类别），
    #     直接交给 L-B/L-C 判；判不出就是 None。

    # 表格：表头有 from/trigger/to ⇒ 迁移表；否则是字段表
    if has_table:
        for b in blocks:
            if b.kind != "table":
                continue
            for ln in b.text.split("\n"):
                roles = _match_roles(_split_columns(ln))
                if roles and all(k in roles for k in ("from", "trigger", "to")):
                    return "transition"
        return "field"

    if has_abnf:
        return "field"

    # ★ **选项登记形态**（2026-11-08 实测修正）：RFC 的选项登记表
    #   （``Code: 114`` / ``Name: URL`` / ``Defined in: (none)``）
    #   ⇒ 是**选项/字段**，不是方法
    #   （实测 rfc3679 §3.2.3 的 ``URL`` 被误抽成方法）。
    if RE_OPTION_REGISTRY.search(text):
        return "field"

    if has_diagram:
        # 图形：可能是状态迁移图，也可能是命令/报文图
        # ⇒ 标题形态能区分（OPTIONS 单个词 ⇒ method；多词 ⇒ transition）
        t = (window.get("title") or "").strip()
        if RE_UPPER_METHOD.match(t) and " " not in t:
            return "method"
        return "transition"

    return None


def _classify_by_title(window: dict[str, Any]) -> Optional[str]:
    """L-B：按**标题形态**判定。"""
    title = (window.get("title") or "").strip()
    if not title:
        return None
    if RE_STATUS_CODE.match(title):
        return "status"
    # 状态码标题形如「100 Trying」（3 位数字 + 词）
    m = re.match(r"^(\d{3})\s+(\S.*)$", title)
    if m:
        return "status"
    if RE_PASCAL_HEADER.match(title):
        return "field"
    if RE_PASCAL_WORD.match(title):
        return "field"
    # ★ 全大写**单词** ⇒ 方法
    #   ⚠ **必须整体是单个全大写词**（不含空格、不含括号）——
    #     否则 `_normalize_method_name` 会把括号里的缩写提成方法名
    #     （实测 ``Post Office Protocol (POP3) Server Option`` ⇒ 误抽 ``POP3``；
    #      ``8.15. Post Office Protocol (POP3) Server Option`` 是**选项**章标题，
    #      不是方法）。
    # ★ **选项章标题**排除（2026-11-08 实测修正）：
    #   RFC 2132 的选项定义章标题形如
    #     ``8.16. Network News Transport Protocol (NNTP) Server Option``
    #   ⇒ `_normalize_method_name` 会把括号里的缩写提成方法名（⇒ ``NNTP``/``POP3``/
    #     ``IRC``/``STDA`` 全被误抽成方法）。
    #   ⇒ 判据（协议无关）：标题以 ``Option``/``Options`` 结尾 ⇒ 是**选项定义**，
    #     不是方法。
    #   ⚠ **必须排除「单个全大写词」**（``OPTIONS`` 方法名本身也匹配
    #     ``\bOptions?$``，因为不区分大小写时 OPTIONS == options）
    #     ⇒ 只有**多词标题**才是选项定义章。
    if (" " in title and
            re.search(r"\bOptions?$", title, re.IGNORECASE)):
        return "field"
    if RE_UPPER_METHOD.match(title) and " " not in title and "(" not in title:
        return "method"
    return None


def _classify_by_prose(window: dict[str, Any]) -> Optional[str]:
    """L-C：按**正文句式**判定。"""
    text = window.get("text") or ""
    if not text:
        return None
    head = text[:2000]
    if RE_CMD_FORMAT.search(head):
        return "method"
    if RE_REQUIRED_HEADER.search(head):
        return "required_header"
    if RE_OUTCOME.search(head):
        return "outcome"
    return None


def classify_window(window: dict[str, Any], cfg: Optional[dict] = None,
                    src_name: Optional[str] = None) -> Optional[str]:
    """**从内容判定类别**（新通道的入口）。

    ★ 判据链：L-A 形态 → L-B 标题 → L-C 句式 → L-D 章节号兜底。

    Args:
        window: 章节窗口（含 ``section_no``/``title``/``text``/``line``）。
        cfg: ``rfc_config``（**仅 L-D 兜底用**）。
        src_name: 当前文件名（L-D 的 ``sections_by_file`` 用）。

    Returns:
        ``method`` / ``field`` / ``status`` / ``transition`` / ``outcome`` /
        ``required_header`` / ``None``。
    """
    # L-A
    k = _classify_by_form(window)
    if k:
        return k
    # L-B
    k = _classify_by_title(window)
    if k:
        return k
    # L-C
    k = _classify_by_prose(window)
    if k:
        return k
    # L-D：章节号兜底（旧通道）
    if cfg is not None:
        try:
            from core.fused.rfc_extractor import _section_kind
            return _section_kind(window, cfg, src_name)
        except Exception:                           # noqa: BLE001
            return None
    return None


def coverage_table(windows: list[dict[str, Any]],
                   cfg: Optional[dict] = None,
                   src_name: Optional[str] = None) -> dict[str, Any]:
    """统计新通道在给定窗口上的**类别覆盖**（★ S3 的前置检查项）。"""
    counts: dict[str, int] = {k: 0 for k in KINDS}
    unknown = 0
    for w in windows:
        k = classify_window(w, cfg, src_name)
        if k in counts:
            counts[k] += 1
        else:
            unknown += 1
    return {"counts": counts, "unknown": unknown, "total": len(windows),
            "covered_classes": sorted(k for k, v in counts.items() if v > 0)}


__all__ = ["KINDS", "classify_window", "coverage_table",
           "_classify_by_form", "_classify_by_title", "_classify_by_prose"]
