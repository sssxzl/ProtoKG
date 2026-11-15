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
#: ★ 2026-11-13（任务书 P0-3）：★ **排除**会让步 / 目的 / 修饰 / 替代
#:   · ``even if``   ⇒ 让步/无条件适用（★ **不是**生效条件）
#:   · ``in order to`` ⇒ 目的（★ **不是**触发条件）
#:   · ``so that`` / ``in order that`` ⇒ 目的
CONDITION_MARKERS: tuple[str, ...] = (
    "if ", "when ", "unless ", "except ", "in case", "provided that",
    "subject to", "as long as", "if and only if",
    "若", "如果", "除非", "当", "在……情况下",
)

#: ★ **不是条件**的句式（让步 / 目的 / 主体修饰 / 替代方案）
NON_CONDITION_MARKERS: tuple[str, ...] = (
    "even if", "even though", "in order to", "in order that", "so that",
    "for the purpose of", "as a means of",
    "或者", "或包含", "or contain", "or contains",
)

#: ★ **不是例外**的句式（替代方案）
NON_EXCEPTION_MARKERS: tuple[str, ...] = (
    "or contain", "or contains", "or include", "or includes",
    "或包含", "或者",
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


def classify_clause_role(text: str) -> str:
    """判定一段文本的**语义角色**（★ 任务书 P0-3）。

    Returns:
        ``condition``（生效条件）/ ``exception``（例外）/ ``purpose``（目的）/
        ``qualifier``（主体修饰）/ ``alternative``（替代方案）/
        ``concession``（让步）/ ``explanatory``（解释性上下文）
    """
    _low = " ".join(str(text or "").lower().split())
    if not _low:
        return "explanatory"
    if any(m in _low for m in ("even if", "even though")):
        return "concession"
    if any(m in _low for m in ("in order to", "in order that", "so that",
                               "for the purpose of", "as a means of")):
        return "purpose"
    if any(m in _low for m in NON_EXCEPTION_MARKERS):
        return "alternative"
    if any(m in _low for m in ("unless", "except for", "other than",
                               "apart from", "with the exception of")):
        return "exception"
    if any(m in _low for m in CONDITION_MARKERS):
        return "condition"
    return "explanatory"


def extract_condition(text: str) -> tuple[Optional[str], str]:
    """从原文抽**生效条件**（★ 跨行 ⇒ 先合并空白再切句）。

    Returns:
        ``(条件原文片段, 状态)``；状态 ∈ ``stated`` / ``unknown``。
    """
    for _s in _sentence_split(text):
        _low = _s.lower()
        # ★ 让步 / 目的 / 替代 ⇒ **不是**生效条件 ⇒ 跳过
        if any(_m in _low for _m in NON_CONDITION_MARKERS):
            continue
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
        # ★ 替代方案（or contain "="）⇒ **不是**例外 ⇒ 跳过
        if any(_m in _low for _m in NON_EXCEPTION_MARKERS):
            continue
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


# ════════════════════════════════════════════════════════════════════
# ★ M1-Q2：span 双口径证据定位（★ 绝对优先；相对必须有据）
# ════════════════════════════════════════════════════════════════════
#: 解释模式
SPAN_MODE_ABSOLUTE = "absolute"        # ★ 绝对行号命中（★ 现状口径）
SPAN_MODE_RELATIVE = "relative"        # ★ 相对行号命中（★ 本轮新增）
SPAN_MODE_AMBIGUOUS = "ambiguous"      # ★ 两个解释都命中 ⇒ 冲突 ⇒ 不放行
SPAN_MODE_OUT_OF_RANGE = "out_of_range"  # ★ 换算后越出 chunk 范围 ⇒ 不放行
SPAN_MODE_NOT_FOUND = "not_found"      # ★ 两种解释都定位不到 ⇒ 不放行
SPAN_MODE_UNRESOLVED = "unresolved"    # ★ 缺基准（chunk 起始行未知）⇒ 不放行

#: 相对行号的基准（★ 明确 1 基准：raw_span 是块内第几行）
RELATIVE_BASE = 1


def resolve_span_evidence(lines: list[str], raw_span: int, entity: str, *,
                          chunk_start: Optional[int] = None,
                          chunk_end: Optional[int] = None,
                          window: int = 3) -> dict:
    """★ **双口径证据定位**（★ 绝对优先；相对必须由真实 chunk 起始行换算）。

    ★ **规则**（M1-Q2 实施要求）：
      ① 先按**绝对行号**解释（★ 现状口径 ⇒ 行为不变）
      ② 只有绝对解释**定位不到有效证据**时，才尝试**相对行号**
      ③ 相对行号 = ``chunk_start + (raw_span - RELATIVE_BASE)``
         （★ 基准明确为 1；★ **不猜测、不扫描任意附近行**）
      ④ 换算结果**必须落在 chunk 范围内**（``chunk_start..chunk_end``）⇒ 否则越界
      ⑤ 两个解释**都命中** ⇒ 歧义 ⇒ **不放行**
      ⑥ 缺基准（``chunk_start`` 未知）⇒ 不做相对换算 ⇒ 不放行

    Returns:
        ``{"resolved_span", "span_mode", "absolute_match", "relative_match",
           "chunk_start", "raw_span", "reason"}``
    """
    _out = {
        "raw_span": raw_span, "resolved_span": None,
        "span_mode": SPAN_MODE_UNRESOLVED,
        "absolute_match": None, "relative_match": None,
        # ★ M1-Q3：★ 锚点 / 匹配行 / 证据窗口 三者分离
        "matched_evidence_lines": None,
        "quote_span": None,
        "chunk_start": chunk_start, "chunk_end": chunk_end,
        "reason": "",
    }
    if not raw_span or raw_span <= 0:
        _out["reason"] = "raw_span 缺失或非正"
        return _out
    # ---- ① 绝对行号（★ 现状口径，优先）----
    _abs = entity_in_span(lines, raw_span, entity, window=window)
    _out["absolute_match"] = _abs
    if _abs is not None:
        # ★ ★ M1-Q3 修正：resolved_span = **锚点行**（★ 不是 entity 首次匹配行）
        _out["resolved_span"] = raw_span
        _out["matched_evidence_lines"] = _abs
        _out["span_mode"] = SPAN_MODE_ABSOLUTE
        _out["reason"] = "绝对行号命中"
        return _out
    # ---- ② 相对行号（★ 必须有真实 chunk 起始行）----
    if chunk_start is None or chunk_start <= 0:
        _out["reason"] = "绝对未命中；缺 chunk 起始行 ⇒ 不做相对换算"
        return _out
    _rel_span = int(chunk_start) + (int(raw_span) - RELATIVE_BASE)
    if chunk_end is not None and not (chunk_start <= _rel_span <= chunk_end):
        _out["span_mode"] = SPAN_MODE_OUT_OF_RANGE
        _out["reason"] = (f"相对换算行 {_rel_span} 越出 chunk 范围 "
                          f"[{chunk_start},{chunk_end}]")
        return _out
    _rel = entity_in_span(lines, _rel_span, entity, window=window)
    _out["relative_match"] = _rel
    if _rel is None:
        _out["span_mode"] = SPAN_MODE_NOT_FOUND
        _out["reason"] = f"绝对与相对均未命中（相对行 {_rel_span}）"
        return _out
    # ★ 块起始行=1 ⇒ 相对换算与绝对同值 ⇒ 不算歧义
    if _rel_span == raw_span:
        _out["span_mode"] = SPAN_MODE_NOT_FOUND
        _out["reason"] = "相对换算与绝对同值 ⇒ 仍无法定位"
        return _out
    # ★ ★ M1-Q3 修正：resolved_span = **换算锚点**（★ 不是匹配行）
    _out["resolved_span"] = _rel_span
    _out["matched_evidence_lines"] = _rel
    _out["span_mode"] = SPAN_MODE_RELATIVE
    _out["reason"] = f"绝对未命中；相对换算行 {_rel_span} 命中"
    return _out


def span_quote_window(span_info: dict) -> Optional[tuple]:
    """★ M1-Q3：由锚点与匹配行算出 **L1/L2 的证据窗口**。

    ★ 规则：``[min(anchor, matched) .. max(anchor, matched)]``
      ⇒ ⇒ 覆盖「LLM 指定位置」到「实体出现位置」之间的**完整句子**
      ⇒ ⇒ ★ **entity 校验窗口本身不变（仍是 ±3）** ⇒ ⇒ 不靠放宽匹配提高通过率
    Returns:
        ``(起行, 止行)``（1 起始，闭区间）；无法确定 ⇒ ``None``。
    """
    _a = span_info.get("resolved_span")
    _m = span_info.get("matched_evidence_lines")
    if _a is None:
        return None
    if _m is None:
        return (int(_a), int(_a))
    return (min(int(_a), int(_m)), max(int(_a), int(_m)))


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




# ════════════════════════════════════════════════════════════════════
# ★ M1-Q3-P0.6：规范证据**句界**恢复（★ 只改证据构造）
# ════════════════════════════════════════════════════════════════════
# ★ 目标：以证据锚点所在的**完整规范句**为中心，确定性恢复**最小充分证据**
# ★     （★ 不是无条件扩展到前后各一句）
# ★ 保留定位契约：raw_span / resolved_span / matched_evidence_lines / span_mode
# ★ 不改 entity_in_span() 的 ±3 匹配规则；★ 不改绝对/相对解释优先级
# ★ 不改 L1/L2 判定规则、Prompt、FactID、21 aspects、Rule Slot

_RE_TITLE = re.compile(r"^\d+(\.\d+)*\.?\s+\S")             # 章节标题
_RE_CAPTION = re.compile(r"^(Figure|Table|Note|Listing)\s+\d+", re.I)
_RE_ABNF = re.compile(r"^[=;]")                              # ABNF 生产式
_RE_PAGE = re.compile(r"^\[Page \d+\]")                      # 页脚
_RE_FOOT = re.compile(r"^Fischer & Springer|^RFC \d+")

_ABBREV = {
    "e.g", "i.e", "etc", "vs", "cf", "sec", "no", "fig", "vol", "pp",
    "mr", "mrs", "dr", "st", "jr", "sr", "al", "resp", "req",
    "msg", "hdr", "param", "id", "uri", "url",
}


def is_prose_line(s: str) -> bool:
    """★ 该行是否属于「散文正文」（★ 否则构成逻辑行边界 ⇒ **不并入规范句**）。"""
    t = str(s or "").strip()
    if not t:
        return False
    if _RE_TITLE.match(t):
        return False
    if _RE_CAPTION.match(t):
        return False
    if _RE_ABNF.match(t):
        return False
    if _RE_PAGE.match(t) or _RE_FOOT.match(t):
        return False
    if t.startswith("|"):
        return False
    if len(re.findall(r"\S {3,}\S", t)) >= 1:      # ★ 表格对齐行
        return False
    return True


def is_sentence_end(t: str, i: int) -> bool:
    """★ ``t[i] == '.'`` 时该点是否为**句末**（★ 排除小数点/章节引用/缩写）。"""
    if i < 0 or i >= len(t) or t[i] != ".":
        return False
    if 0 < i < len(t) - 1 and t[i - 1].isdigit() and t[i + 1].isdigit():
        return False                            # ★ 小数点 / 版本号
    m = re.search(r"([A-Za-z][A-Za-z.]*)\.$", t[:i + 1])
    if m and m.group(1).lower().rstrip(".") in _ABBREV:
        return False                            # ★ 缩写
    j = i + 1
    while j < len(t) and t[j] in "\"'\u2019)]}":
        j += 1
    if j < len(t) and not t[j].isspace():
        return False
    return True


def _logical_line(lines: list, anchor: int):
    """★ 从 anchor 起取**连续散文行**构成的逻辑行（★ 返回行范围/文本/偏移）。"""
    a = max(1, int(anchor))
    n = len(lines)
    lo = a
    while lo - 1 >= 1 and is_prose_line(lines[lo - 2]):
        lo -= 1
    hi = a
    while hi < n and is_prose_line(lines[hi]):
        hi += 1
    parts, offsets, pos = [], [], 0
    for ln in range(lo, hi + 1):
        txt = str(lines[ln - 1]).rstrip()
        if not txt:
            continue
        if parts and txt:
            if parts[-1].endswith("-"):          # ★ 行尾连字符 ⇒ 直接接续
                parts[-1] = parts[-1][:-1] + txt
                offsets[-1] = (offsets[-1][0], pos + len(txt))
                pos += len(txt)
                continue
            _seg = " " + txt.lstrip()
            parts.append(_seg)
            offsets.append((pos, pos + len(_seg)))
            pos += len(_seg)
        else:
            parts.append(txt)
            offsets.append((pos, pos + len(txt)))
            pos += len(txt)
    return lo, hi, "".join(parts), offsets


def _sentences_in(logical: str) -> list:
    """★ 逻辑行内的句子切分（★ 返回 ``(起偏移, 止偏移)`` 列表）。"""
    out, start, i = [], 0, 0
    while i < len(logical):
        if logical[i] == "." and is_sentence_end(logical, i):
            out.append((start, i + 1))
            start = i + 1
            while start < len(logical) and logical[start].isspace():
                start += 1
            i = start
            continue
        i += 1
    if start < len(logical) and logical[start:].strip():
        out.append((start, len(logical)))
    return out


def build_evidence(lines: list, span_info: dict, *,
                   entity: str = "", max_chars: int = 1200,
                   max_lines: int = 12) -> dict:
    """★ M1-Q3-P0.6：构造**句界证据**（★ 主要 quote + 单独标记的辅助证据）。

    Args:
        lines: 文档**全文**的行列表（★ 允许跨 chunk 取证 ⇒ 同一版本 RFC 真实原文）
        span_info: :func:`resolve_span_evidence` 的返回值
        max_chars: 主要 quote 的最大字符数（★ 超出 ⇒ 保守降级）
        max_lines: 主要 quote 的最大行数（★ 超出 ⇒ 保守降级）

    Returns:
        ``quote_span`` / ``quote`` / ``anchor_offset`` / ``boundary_reason`` /
        ``aux_evidence`` / ``cross_chunk`` / ``degraded`` / ``reason``
    """
    _out = {
        "quote_span": None, "quote": "", "anchor_offset": None,
        "boundary_reason": "", "aux_evidence": [],
        "cross_chunk": False, "degraded": False, "reason": "",
        "sentence_span": None, "prev_sentence_span": None,
        "logical_span": None,
        "anchor_normalized_to": None, "anchor_normalized_from": None,
        "entity_sentence_picked": None,
        "anchor_entity_relocated": None,
    }
    _anchor = span_info.get("resolved_span")
    _entity = str(entity or "").strip().lower()
    _chunk_start = span_info.get("chunk_start")
    _chunk_end = span_info.get("chunk_end")
    if not _anchor or not lines:
        _out["reason"] = "无锚点或无原文"
        _out["degraded"] = True
        return _out
    # ★ 锚点越界 ⇒ 保守降级（★ 不越界访问）
    if not (1 <= int(_anchor) <= len(lines)):
        _out["reason"] = f"锚点行 {_anchor} 越出原文范围（1..{len(lines)}）"
        _out["degraded"] = True
        return _out

    # ★ ★★ 有限窗口内**按 entity 出现行**定位锚点（★ **不扫描任意远处**）
    #   ⇒ 候选的义务句必然含 entity ⇒ ⇒ 用最近的匹配行作锚点最可靠
    #   ⇒ ★ 窗口 ±10 行（★ 与 entity_in_span 的 ±3 同阶）
    _anchor_locked = False
    if _entity:
        _best = None
        # ★ 优先**向上**（★ RFC 行号通常指向内容起始行）⇒ ★ 其次**向下**
        for _dir in (-1, 1):
            for _d in range(0, 11):
                _cand = _anchor + _dir * _d
                if 1 <= _cand <= len(lines) and _entity in str(lines[_cand - 1]).lower():
                    _best = _cand
                    break
            if _best is not None:
                break
        if _best is not None:
            if _best != _anchor:
                _out["anchor_entity_relocated"] = [_anchor, _best]
            # ★ ★ **锁定**锚点（★ 该行虽被判为「标题/非散文行」，
            #   ★ 但它**就是候选所指的内容行** ⇒ ⇒ 不再被后续归一化覆盖）
            _anchor = _best
            _anchor_locked = True

    # ★ ★ 锚点行若**不是散文行**（空行/标题/图注/表格）⇒ ⇒ **归一化**到最近的散文行
    #   ⇒ ★ 优先**向上**（RFC 的行号通常指向内容起始行）⇒ ★ 其次向下
    #   ⇒ ★ 归一化必须**记录**（★ 不得静默）
    _a = int(_anchor)
    _norm_from = None
    if not _anchor_locked and not is_prose_line(lines[_a - 1]):
        _k = _a - 1
        while _k >= 1 and not is_prose_line(lines[_k - 1]):
            _k -= 1
        if _k >= 1:
            _a = _k
            _norm_from = "up"
        else:
            _k = _a + 1
            while _k <= len(lines) and not is_prose_line(lines[_k - 1]):
                _k += 1
            if _k <= len(lines):
                _a = _k
                _norm_from = "down"
            else:
                _out["reason"] = "锚点行及其邻近均非散文行 ⇒ 无法构造证据"
                _out["degraded"] = True
                return _out
    _out["anchor_normalized_to"] = _a
    _out["anchor_normalized_from"] = _norm_from
    if _norm_from:
        _out["degraded"] = True
        _out["reason"] = (f"锚点行 {_anchor} 非散文行 ⇒ 归一化到第 {_a} 行"
                          f"（{_norm_from}）")

    _lo, _hi, _logical, _offsets = _logical_line(lines, _a)
    _out["logical_span"] = [_lo, _hi]
    _a_off = 0
    for _i, (_s, _e) in enumerate(_offsets):
        if _lo + _i == _a:
            _a_off = _s
            break
    _out["anchor_offset"] = _a_off

    def _span_of(s: int, e: int):
        _ls = _le = None
        for _i, (_os, _oe) in enumerate(_offsets):
            if _ls is None and _os <= s < _oe:
                _ls = _lo + _i
            if _os < e:
                _le = _lo + _i
        return (_ls or _lo, _le or _lo)

    _sents = _sentences_in(_logical)
    _cur = None
    _cur_idx = 0
    for _i, _pair in enumerate(_sents):
        if _pair[0] <= _a_off < _pair[1]:
            _cur = _pair
            _cur_idx = _i
            break
    # ★ ★ M1-Q3-P0.6：★ **句子选择以「含 entity」为准**（★ 候选的义务句必然含 entity）
    #   ⇒ ⇒ 锚点归一化后若锚点句不含 entity ⇒ ⇒ 在**邻近句**中找含 entity 的那一句
    #   ⇒ ⇒ ★ 找不到 ⇒ ⇒ 保守用锚点句（★ 并记录）
    if _cur is not None and _entity:
        _cur_txt = _logical[_cur[0]:_cur[1]].lower()
        if _entity not in _cur_txt:
            _found = None
            for _j, _pair in enumerate(_sents):
                if _j == _cur_idx:
                    continue
                if _entity in _logical[_pair[0]:_pair[1]].lower():
                    _found = _j
                    break
            if _found is not None:
                _out["entity_sentence_picked"] = "nearest_with_entity"
                _out["degraded"] = True
                _cur_idx = _found
                _cur = _sents[_cur_idx]
            else:
                _out["entity_sentence_picked"] = "anchor_sentence_without_entity"
                _out["degraded"] = True
                _out["reason"] = ("逻辑行内无任何一句包含实体 ⇒ 保守用锚点句"
                                  "（★ 不外扩、不猜测）")
    if _cur is None:
        # ★ ★ M1-Q3-P0.6：★ 锚点落在**句间缝隙**（句末与下一句起点之间）⇒ ⇒
        #   ① 优先取**含 entity 的句**（★ 候选的义务句必然含 entity）
        #   ② 否则取**锚点行所在的那一句**
        #   ③ 再否则 ⇒ 保守取逻辑行首句（★ 记原因）
        _found = None
        if _entity:
            for _j, _pair in enumerate(_sents):
                if _entity in _logical[_pair[0]:_pair[1]].lower():
                    _found = _j
                    break
        if _found is None:
            for _j, _pair in enumerate(_sents):
                _ls, _le = _span_of(_pair[0], _pair[1])
                if _ls <= _a <= _le:
                    _found = _j
                    break
        if _found is not None:
            _cur_idx = _found
            _cur = _sents[_cur_idx]
            _out["degraded"] = True
            _out["entity_sentence_picked"] = (
                "entity_sentence" if _entity and
                _entity in _logical[_cur[0]:_cur[1]].lower() else "anchor_row_sentence")
            _out["reason"] = ("锚点落在句间缝隙 ⇒ 改取含实体的句/锚点行所在句")
        else:
            _cur = _sents[0] if _sents else (0, len(_logical))
            _cur_idx = 0
            _out["degraded"] = True
            _out["reason"] = "锚点未能定位到完整句 ⇒ 保守取逻辑行首句"
    else:
        # ★ ★ M1-Q3-P0.6：★ **锚点行内含该句的句末** ⇒ ⇒ 该句在锚点行内**已结束**
        #   ⇒ ⇒ 锚点所指内容应是该句**之后**的部分 ⇒ ⇒ 取**下一句**
        #   ★ 例：sip@10466（"field.  The server MUST include …"）⇒ ⇒ 应取第 2 句
        #   ★ 保守：若下一句不存在 ⇒ ⇒ 保持当前句（★ 不外扩）
        # ★ ★ 判据：**锚点行内是否含句末**
        #   （★ 直接按锚点行的字符范围判定 ⇒ 不依赖句的行尾推算）
        _a_span = _span_of(_a_off, _a_off + 1)
        _a_line_txt = _logical[_a_span[0] - 0:] if False else None
        _has_end_in_anchor_line = False
        for _i, (_os, _oe) in enumerate(_offsets):
            if _lo + _i != _a:
                continue
            _seg = _logical[_os:_oe]
            for _k in range(len(_seg) - 1):
                if _seg[_k] == "." and is_sentence_end(_seg, _k):
                    _has_end_in_anchor_line = True
                    break
            break
        if _has_end_in_anchor_line and _cur_idx + 1 < len(_sents):
            _cur_idx += 1
            _cur = _sents[_cur_idx]
            _out["boundary_reason_note"] = (
                "★ 锚点行含上一句句末 ⇒ 取下一句")

    _qs, _qe = _span_of(_cur[0], _cur[1])
    _out["sentence_span"] = [_qs, _qe]
    _out["quote_span"] = [_qs, _qe]
    _out["quote"] = _logical[_cur[0]:_cur[1]].strip()
    _out["boundary_reason"] = (
        f"句界：逻辑行 {_lo}~{_hi} 内的第 "
        f"{(_sents.index(_cur) + 1) if _cur in _sents else 1} 句"
        f"（字符 {_cur[0]}~{_cur[1]}）")

    # ★ 辅助证据：前一句（★ **单独标记，★ 不并入主要 quote**）
    _idx = _sents.index(_cur) if _cur in _sents else 0
    if _idx > 0:
        _ps, _pe = _sents[_idx - 1]
        _pspan = _span_of(_ps, _pe)
        _out["prev_sentence_span"] = list(_pspan)
        _out["aux_evidence"].append({
            "span": list(_pspan),
            "text": _logical[_ps:_pe].strip(),
            "kind": "prev_sentence",
            "note": "★ **辅助证据，未并入主要 quote** ⇒ 不得据此认定跨句义务成立",
        })

    # ★ 跨块取证（★ 独立记录）
    if _chunk_start is not None and _chunk_end is not None:
        if _qs < _chunk_start or _qe > _chunk_end:
            _out["cross_chunk"] = True
            _out["boundary_reason"] += (
                f"；★ **跨块取证**（quote {_qs}~{_qe} 超出 chunk "
                f"{_chunk_start}~{_chunk_end}）")

    if len(_out["quote"]) > max_chars:
        _out["degraded"] = True
        _out["reason"] = f"quote 超长（{len(_out['quote'])} > {max_chars}）⇒ 保守保留"
    if (_qe - _qs + 1) > max_lines:
        _out["degraded"] = True
        _out["reason"] = f"quote 超行数（{_qe - _qs + 1} > {max_lines}）⇒ 保守保留"
    if not _out["reason"]:
        _out["reason"] = "句界确定"
    return _out

__all__ = [
    "CONDITION_MARKERS", "EXCEPTION_MARKERS", "XREF_PATTERN",
    "ENABLE_CONDITION_NORMALIZATION",
    "extract_condition", "extract_exception", "extract_cross_ref",
    "parse_reference", "locate_section_ref", "normalize_condition",
    "classify_clause_role", "NON_CONDITION_MARKERS", "NON_EXCEPTION_MARKERS",
    "semantic_support", "entity_in_span",
    "build_evidence", "is_prose_line", "is_sentence_end",
]
