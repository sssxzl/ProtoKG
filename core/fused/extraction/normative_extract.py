# -*- coding: utf-8 -*-
"""core/fused/extraction/normative_extract.py —— **规范语义抽取的确定性机制**。

★ 2026-11-13（人工核对意见 §三）新增：为让语义测试**真过机制**（而不是手工填
  payload 再比 hash），这里提供四个**确定性**机制：

  ① :func:`extract_condition` / :func:`extract_exception`
     —— 从**跨行原文**里按句式标记抽条件 / 例外（**跨行抽取**，不是手工填）
  ② :func:`extract_cross_ref` / :func:`locate_section_ref`
     —— 抽跨节引用 + **真实定位**目标章节（**不是测试手工指定** ``resolved``）
  ③ :func:`normalize_condition`
     —— 条件**归一化**（★ 带开关：未确认 ⇒ **不强制合并**；确认 ⇒ 允许合并）
  ④ :func:`semantic_support`
     —— **确定性的语义支持检查**（原文是否支持所声称的动作 / 对象）

★ 全部**无 LLM** ⇒ ⇒ 可复现、可离线测、零成本。
"""
from __future__ import annotations

import re
from typing import Optional

#: 条件句式标记
CONDITION_MARKERS: tuple[str, ...] = (
    "if ", "when ", "unless ", "except ", "in case", "provided that",
    "subject to", "as long as", "if and only if",
    "若", "如果", "除非", "当", "在……情况下",
)

#: 例外句式标记
EXCEPTION_MARKERS: tuple[str, ...] = (
    "unless", "except", "except for", "other than", "apart from",
    "with the exception of", "unless otherwise",
    "除非", "除外", "例外",
)

#: 跨节引用模式
XREF_PATTERN = re.compile(
    r"(?:see|refer to|as defined in|specified in)\s+"
    r"(?:section|clause|Section|Clause|Appendix)\s*([0-9]+(?:\.[0-9]+)*)",
    re.I)

#: ★ 条件归一化的**同义表**（★ 只在**可靠确认**时才用）
#:   key = 规范化形式；value = 触发该形式的原文标记
_CONDITION_SYNONYMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("before", ("before", "prior to", "ahead of", "in advance of")),
    ("after", ("after", "following", "once", "upon")),
    ("unless", ("unless", "except when", "except if")),
    ("while", ("while", "during", "whenever")),
    ("only_if", ("only if", "only when", "provided that")),
)

#: ★ **条件归一化开关**（★ 缺省 **False** ⇒ 不强制合并）
#:   ⇒ 人工核对 17：「未确认时不强制合并」⇒ 且**允许**将来可靠确认后合并
#:   ⇒ ⇒ 本开关打开时，**已列入同义表**的条件才算「确认」⇒ 允许归并
ENABLE_CONDITION_NORMALIZATION: bool = False


def _sentence_split(text: str) -> list[str]:
    """按句末标点切句（★ 跨行也成立）。"""
    _flat = " ".join(str(text or "").split())
    if not _flat:
        return []
    return [s.strip() for s in re.split(r"(?<=[.;。；])\s+", _flat) if s.strip()]


def extract_condition(text: str) -> tuple[Optional[str], str]:
    """从原文抽**生效条件**（★ 跨行 ⇒ 先合并空白再切句）。

    Returns:
        ``(条件原文片段, 状态)``；状态 ∈ ``stated`` / ``unknown``。
    """
    for _s in _sentence_split(text):
        _low = _s.lower()
        for _m in CONDITION_MARKERS:
            if _m in _low:
                return _s, "stated"
    return None, "unknown"


def extract_exception(text: str) -> tuple[Optional[str], str]:
    """从原文抽**例外**（★ 跨行）。

    Returns:
        ``(例外原文片段, 状态)``；状态 ∈ ``stated`` / ``unknown``。
    """
    for _s in _sentence_split(text):
        _low = _s.lower()
        for _m in EXCEPTION_MARKERS:
            if _m in _low:
                return _s, "stated"
    return None, "unknown"


def extract_cross_ref(text: str) -> tuple[Optional[str], str]:
    """从原文抽**跨节引用**（★ 与条件**分开**）。

    Returns:
        ``(引用串, 状态)``；状态 ∈ ``unknown``（未出现引用）。
    """
    _flat = " ".join(str(text or "").split())
    _m = XREF_PATTERN.search(_flat)
    if not _m:
        return None, "unknown"
    return f"section {_m.group(1)}", "stated"


#: ★ **外部文档引用**的模式（★ 跨文档 ⇒ 不能靠本地数字匹配）
#:   如 ``Section 4 of [BASE64]`` / ``[1] (Section 8, ...)`` / ``RFC 2119 Section 3``
_EXTERNAL_REF = re.compile(
    r"(?:\bof\s*\[([A-Za-z0-9_.-]+)\]\b)|(?:\[([A-Za-z0-9_.-]+)\])|"
    r"(?:\bRFC\s*(\d{3,5})\b)", re.I)


def parse_reference(ref: str) -> dict:
    """解析跨节引用 ⇒ ``{"section":…, "target_doc":…, "kind":…}``。

    ★ **关键**（2026-11-13 独立复核意见 P0-3）：
      · ``[BASE64] Section 4`` ⇒ ``target_doc="BASE64"`` ⇒ **外部文档**
        ⇒ ⇒ **不能**靠本地数字匹配 ⇒ ⇒ 必须解析目标文档
      · ``[1] (Section 8, sixth paragraph)`` ⇒ ``target_doc="1"``（参考文献编号）
        ⇒ ⇒ 同样**不能**当本地章节
      · ``Section 12`` ⇒ 无目标文档 ⇒ ⇒ **本地**引用 ⇒ 可在本地定位
    """
    _r = str(ref or "").strip()
    _m = re.search(r"([0-9]+(?:\.[0-9]+)*)", _r)
    _section = _m.group(1) if _m else None
    _doc = None
    _kind = "local"
    _ext = _EXTERNAL_REF.search(_r)
    if _ext:
        _doc = next((g for g in _ext.groups() if g), None)
        if _doc:
            _kind = "external"
    # ★ 「Section 4 of [BASE64]」里的 4 是**外部文档**的章节 ⇒ 本地无意义
    return {"section": _section, "target_doc": _doc, "kind": _kind,
            "raw": _r}


def locate_section_ref(doc_text: str, ref: str) -> tuple[Optional[str], str]:
    """**真实定位**跨节引用的目标章节（★ 不是测试手工指定）。

    ★ **外部引用不返回 resolved**（★ 独立复核意见 P0-3）：
      ``[BASE64] Section 4`` / ``[1] (Section 8)`` 指向**别的文档** ⇒ ⇒
      本地定位没有意义 ⇒ ⇒ 一律 ``unresolved``（⇒ 待审）。

    Returns:
        ``(定位到的章节号, 状态)``；状态 ∈ ``resolved`` / ``unresolved``。
    """
    _parsed = parse_reference(ref)
    if _parsed["kind"] == "external":
        # ★ 外部文档引用 ⇒ **不得**用本地数字匹配 ⇒ ⇒ 未解析目标文档前不算定位
        return None, "unresolved"
    _num = _parsed["section"]
    if not _num:
        return None, "unresolved"
    _pattern = re.compile(r"^\s*(\d+(?:\.\d+)*)\b")
    for _line in str(doc_text or "").split("\n"):
        _mm = _pattern.match(_line)
        if _mm and _mm.group(1) == _num:
            return _num, "resolved"
    return None, "unresolved"


def entity_in_span(lines: list[str], span: int, entity: str,
                   window: int = 3) -> Optional[int]:
    """★ **跨行**找实体名（★ 独立复核意见 P0-2）。

    旧逻辑只看 span **单行** ⇒ ⇒ 实体名在**相邻行**时会被**误拒**（如 S09/S19/S29/S39）。

    Returns:
        命中行号（1 起始）；未命中 ⇒ ``None``。
    """
    _ent = str(entity or "").strip().lower()
    if not _ent:
        return None
    if not lines:
        return None
    _lo = max(0, span - 1 - window)
    _hi = min(len(lines), span + window)
    for _i in range(_lo, _hi):
        if _ent in str(lines[_i]).lower():
            return _i + 1
    return None


def normalize_condition(text: str) -> tuple[str, bool]:
    """条件**归一化**（★ 带开关）。

    Returns:
        ``(规范化形式, 是否确认)``。
        ★ **确认**仅当：① 归一化开关**打开** **且** ② 命中同义表。
        ⇒ ⇒ 未确认 ⇒ 调用方**不得强制合并**（人工核对 17）。
    """
    _raw = " ".join(str(text or "").strip().lower().split())
    if not _raw:
        return "", False
    if not ENABLE_CONDITION_NORMALIZATION:
        # ★ 开关关闭 ⇒ 一律**不确认**（⇒ 不强制合并）
        return _raw, False
    for _canon, _markers in _CONDITION_SYNONYMS:
        for _m in _markers:
            if _m in _raw:
                return _canon, True
    return _raw, False


def semantic_support(text: str, action: str = "", object_: str = "",
                     *, strength: str = "") -> tuple[str, str]:
    """**确定性的语义支持检查**（★ LLM 之前的廉价前置）。

    规则（★ 可解释、可复现）：
      · 动作：原文须出现该动作词（或其词根）
      · 对象：原文须出现该对象名（若给出了对象）
      · 强度：若给出了强度，原文须出现该等级词（或其同义）

    Returns:
        ``(verdict, reason)``；verdict ∈ ``支持`` / ``不支持`` / ``不确定``。
    """
    _flat = " ".join(str(text or "").lower().split())
    if not _flat:
        return "不确定", "证据为空"

    def _norm(s: str) -> str:
        """名称归一：下划线 ↔ 空格、大小写、连续空白。"""
        return " ".join(str(s or "").lower().replace("_", " ").split())

    _flat_n = _norm(_flat)
    _reasons: list[str] = []
    if action:
        _a = _norm(action)
        if _a and _a not in _flat_n:
            # ★ 词根匹配（去掉常见的动词后缀）
            _stem = _a[:-1] if _a.endswith("e") else _a
            if _stem and _stem not in _flat_n:
                _reasons.append(f"原文未出现动作「{action}」")
    if object_:
        _o = _norm(object_)
        if _o and _o not in _flat_n:
            _reasons.append(f"原文未出现对象「{object_}」")
    if strength:
        _s = str(strength).strip().upper()
        _syn = {"MUST": ("must", "shall", "required"),
                "SHOULD": ("should", "recommended"),
                "MAY": ("may", "optional")}
        if _s and not any(w in _flat for w in _syn.get(_s, (_s.lower(),))):
            _reasons.append(f"原文未出现等级词「{strength}」")
    if _reasons:
        return "不支持", "；".join(_reasons)
    return "支持", "动作/对象/强度均在证据中出现"


__all__ = [
    "CONDITION_MARKERS", "EXCEPTION_MARKERS", "XREF_PATTERN",
    "ENABLE_CONDITION_NORMALIZATION",
    "extract_condition", "extract_exception", "extract_cross_ref",
    "parse_reference", "locate_section_ref", "normalize_condition",
    "semantic_support", "entity_in_span",
]
