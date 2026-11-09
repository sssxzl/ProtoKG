# -*- coding: utf-8 -*-
"""core/fused/semantic_rules.py —— operator/operand 模式表 + 字段绑定（里程碑 B-5）。

设计依据：docs/RFC源里程碑BCD路线图.md
  · §3.5（行 496-581）：「规则优先 + LLM 兜底 + 结构校验」三层方案的第一层
    ——**有序**的确定性模式表；operand 的四种来源（数值常量 / 枚举集合 /
    字段引用 / 存在性）；单位归一必须显式；`target_field` 的两级绑定
    （精确或规范化匹配，**不做模糊匹配**）。
  · §3.4（行 476-528）：C4/C5/C6/C7 的判定条件。
  · §3.8 任务表 B-5 行（:673）：≥12 条有序模式 + 每条最小可执行样例。

★ **本模块是「规则资产」**：模式表独立成文件，便于版本化与回归
  （§3.7 落点表明确「与 `semantic.py` 分开」）。
  ⇒ 模式表**不修改** `semantic.py` 的任何判定，只**产出**一个符合
  `core.fused.semantic.try_convert` 的 resolver 契约的 callable。

★ **两个必须遵守的坑**（B-2 实测得出）：
  ① `\x0c` 换页符：RFC 正文含换页符，`str.splitlines()` 与 `count("\\n")`
     的行号口径**相差 9~11 行**（430/430 全不符）。⇒ 任何用行号回查的
     逻辑**必须用 splitlines 口径**（与 B-3 一致）。
  ② `\b` 词边界：`MAYBE` / `REQUIREDLY` **不得**被规范性动词误命中。

★ **模式表不「发明」信息**：模式表只产出**构造侧**（C）的 operator/operand/
  target_field 线索；**处理期望**（P）由调用方（B-6 / rfc_config）提供 ——
  本模块一律返回 `expected_behavior=""`（**无处理期望**），不猜。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from core.fused.semantic import (
    MODALITY_NONE,
    MODALITY_OPTIONAL,
    MODALITY_RECOMMENDED,
    REJECT_REASONS,
    detect_modality,
    normalize_field_name,
)

__all__ = [
    "LENGTH_UNITS",
    "NON_LENGTH_UNITS",
    "PATTERNS",
    "PatternMatch",
    "RulePattern",
    "bind_field",
    "extract_field_clue",
    "expectation_assertable",
    "make_resolver",
    "match_pattern",
    "normalize_unit",
    "resolve_evidence_kind",
]


# ===========================================================================
# 单位归一（§3.5 层次2）
# ===========================================================================

#: 长度单位 → 归一单位。**bytes 与 octets 归一到同一单位**（字节）；
#: bits 归一到「位」—— ★ **不可与字节混算**（§3.5 层次2）。
LENGTH_UNITS: dict[str, str] = {
    "octet": "byte",
    "octets": "byte",
    "byte": "byte",
    "bytes": "byte",
    "bit": "bit",
    "bits": "bit",
    "character": "char",
    "characters": "char",
    "char": "char",
    "chars": "char",
}

#: 时间单位 —— **不属于长度约束**：不可通过「改字节」违反 ⇒ **拒绝转换**
#: （§3.5 层次2：`seconds` → `reject_reason="non_length_operand"`）。
NON_LENGTH_UNITS: frozenset[str] = frozenset(
    {
        "second",
        "seconds",
        "sec",
        "secs",
        "minute",
        "minutes",
        "min",
        "mins",
        "hour",
        "hours",
        "hr",
        "hrs",
        "day",
        "days",
        "millisecond",
        "milliseconds",
        "ms",
        "time",
        "times",
        "timeout",
    }
)

#: 「看起来像计量名词」的判据：**复数形式**（以 s 结尾）。
#: ★ 用途：「单位不认识 → 拒绝转换，不猜」—— "70 hops" / "5 items" 这类
#:   **未知计量单位**必须拒转换（它们不是字节长度，改字节违反不了）。
#: ★ 非复数词（如 "Not"）**不当单位** —— 它只是句子里恰好跟着数字的词。
_PLURAL_SUFFIX = "s"

#: 英文数字 → 阿拉伯数字（RFC 里常见 "at least eight octets"）。
#: ★ 只覆盖 1~20；覆盖不到就**不匹配**（不猜）。
_WORD_NUMBERS: dict[str, str] = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}

#: 数值字面量（阿拉伯数字，或英文数字 1~20）
_NUM_LITERAL = (
    r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)


def _num(group: str = "num") -> str:
    r"""构造数值捕获组（同一正则里出现两次时**必须**用不同组名，否则重定义）。

    ★ `(?![\d*])` 负向前瞻：数字后面**不得**紧跟数字或 `*` ——
      否则 "less than 2**31" 会取到 "2"（**错误的操作数**，真实值是 2**31）。
      ⇒ 指数式**宁可不匹配**，也不产出错值（§3.5 层次2「不猜」）。
    """
    return rf"(?P<{group}>{_NUM_LITERAL})(?![\d*])"


#: 第一个数值捕获组
_NUM = _num("num")
#: 第二个数值捕获组（range 用）
_NUM2 = _num("num2")

#: 单位捕获组（可选；存在则参与单位归一）
_UNIT = r"(?:\s+(?P<unit>[A-Za-z][A-Za-z-]*))?"

#: 强制性动词（MUST / SHALL / REQUIRED）—— 用于「否定式」与「存在性」模式
_STRONG = r"(?:MUST|SHALL|REQUIRED)"
#: 全部规范性动词
_VERB = r"(?:MUST|SHALL|REQUIRED|SHOULD|RECOMMENDED|MAY|OPTIONAL)"

#: 动词与比较词之间的**有界间隔** —— 防止跨句贪婪匹配。
#: ★ 排除句号/分号（句子边界）；长度上限 40 字符（RFC 约束子句的实际长度）。
_GAP = r"[^.;]{0,40}?"

#: 字段名形状（首字母开头，可含连字符/下划线分段）
_FIELD = r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*"

#: 句首常见词（做字段线索时排除，避免把 "The client MUST ..." 的 "The" 当字段）
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those", "it", "its",
        "if", "when", "while", "each", "every", "all", "any", "some", "no",
        "not", "in", "for", "from", "to", "of", "by", "with", "as", "at",
        "on", "or", "and", "but", "however", "therefore", "then", "thus",
        "also", "only", "both", "either", "neither", "such", "same", "other",
        "another", "more", "less", "most", "least", "many", "much", "few",
        "several", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "receiving", "sending", "sent", "received",
        "return", "returns", "returned", "use", "used", "uses", "using",
        "include", "includes", "included", "contain", "contains",
        "contained", "generate", "generates", "generated", "produce",
        "produces", "produced", "set", "sets", "value", "values", "message",
        "client", "server", "user", "agent", "proxy", "sender", "receiver",
    }
)


def normalize_unit(unit: Optional[str]) -> Optional[str]:
    """单位归一（§3.5 层次2）。

    返回归一后的单位名（`"byte"` / `"bit"` / `"char"`），或：
      · `None` —— **无单位**（纯数值比较，如 "MUST be less than 2**31"）；
      · `"__reject__"` —— **不可换算 / 不认识** ⇒ **拒绝转换，不猜**。

    判定顺序：
      ① `octets`/`bytes` → `"byte"`；`bits` → `"bit"`（**不与字节混算**）；
      ② 时间单位（`seconds` 等）→ `"__reject__"`
         （**不属于字节长度约束**，改字节违反不了，§3.5 层次2）；
      ③ 未知的**计量名词**（复数形式，如 `hops` / `items`）→ `"__reject__"`
         （**单位不认识 → 拒绝转换，不猜**）；
      ④ 其余（非复数词，如 "Not"）→ `None`（**不是单位**，纯数值比较）。
    """
    if unit is None:
        return None
    word = unit.strip().lower()
    if not word:
        return None
    if word in LENGTH_UNITS:
        return LENGTH_UNITS[word]
    if word in NON_LENGTH_UNITS:
        return "__reject__"
    if len(word) >= 3 and word.endswith(_PLURAL_SUFFIX):
        # 未知的计量名词 ⇒ 拒绝转换（不猜它是不是字节长度）
        return "__reject__"
    return None


def _normalize_number(raw: str) -> str:
    """英文数字 → 阿拉伯数字；已是数字则原样返回。"""
    return _WORD_NUMBERS.get(raw.lower(), raw)


def _split_set(items: str) -> tuple[str, ...]:
    """解析集合字面量：`{a, b, c}` → `("a", "b", "c")`；去掉引号与空白。"""
    out: list[str] = []
    for raw in items.split(","):
        item = raw.strip().strip('"').strip("'").strip()
        # 列表里的 "or " 连接词（"one of a, b, or c"）不是元素本身
        if item.lower().startswith("or "):
            item = item[3:].strip()
        if item:
            out.append(item)
    return tuple(out)


# ===========================================================================
# 模式表（**有序** —— 第一个命中的生效）
# ===========================================================================


@dataclass(frozen=True)
class RulePattern:
    """一条模式 = 一个 RFC 常见句式 = 一个 (operator, operand 抽取) 对。

    ★ **有序**：`PATTERNS` 里第一个命中的生效 —— 避免「MUST NOT」被「MUST」
      先匹配（文档 §3.5 层次1 第1条明写的要求）。
    ★ 每条带 `kind` 标签（`normative` / `abnf` / `prose`）—— §3.5 层次1 第2条。
    """

    name: str
    regex: re.Pattern[str]
    operator: str
    kind: str = "normative"
    #: 取操作数的命名组（数值型）
    num_group: str = "num"
    #: 第二操作数（range 用）
    num2_group: Optional[str] = None
    #: 集合字面量组（`in` 用）
    items_group: Optional[str] = None
    #: 字段引用组（field_ref 用 —— operand_ref 与 operand 都取它）
    ref_group: Optional[str] = None
    #: 目标字段组（该组的值**直接作为** target_field，优先于线索抽取）
    field_group: Optional[str] = None
    #: 单位组（可选；存在则参与单位归一）
    unit_group: Optional[str] = None
    #: 操作数来源（constant / field_ref）
    operand_source: str = "constant"


def _p(
    name: str,
    regex: str,
    operator: str,
    kind: str = "normative",
    flags: int = re.IGNORECASE,
    **kw,
) -> RulePattern:
    """构造一条模式（正则默认大小写不敏感 —— RFC 正文有大小写两种风格）。"""
    return RulePattern(
        name=name,
        regex=re.compile(regex, flags),
        operator=operator,
        kind=kind,
        **kw,
    )


#: **有序**模式表 —— 第一个命中的生效。
PATTERNS: tuple[RulePattern, ...] = (
    # ── A 组：否定式（NOT）+ 比较 ⇒ **反向边界** ─────────────────────────
    # ⚠ 顺序要点 1：「or equal to」变体必须排在「than」变体**之前**，
    #   否则 "MUST NOT be greater than or equal to 70" 会被截成
    #   "greater than 70"（语义反了）。
    # ⚠ 顺序要点 2：「no greater than」必须排在「greater than」**之前**，
    #   否则 "MUST be no greater than 998" 会被判成 gt（反了）。
    _p(
        "must_not_ge",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\bgreater\s+than\s+or\s+equal\s+to\s+{_NUM}{_UNIT}",
        "lt",
        unit_group="unit",
    ),
    _p(
        "must_not_le",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\bless\s+than\s+or\s+equal\s+to\s+{_NUM}{_UNIT}",
        "gt",
        unit_group="unit",
    ),
    _p(
        "must_not_at_least",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\bat\s+least\s+{_NUM}{_UNIT}",
        "lt",
        unit_group="unit",
    ),
    _p(
        "must_not_at_most",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\bat\s+most\s+{_NUM}{_UNIT}",
        "gt",
        unit_group="unit",
    ),
    _p(
        "must_not_gt",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\b(?:greater|more|larger)\s+than\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "must_not_lt",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\b(?:less|fewer|smaller)\s+than\s+{_NUM}{_UNIT}",
        "ge",
        unit_group="unit",
    ),
    _p(
        "must_not_exceed",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\b(?:exceed|outnumber)\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "must_not_equal",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\b(?:be|equal(?:led)?\s+to)\s+{_NUM}{_UNIT}",
        "ne",
        unit_group="unit",
    ),
    # ── B 组：肯定式 + 比较 ────────────────────────────────────────────
    _p(
        "must_ge",
        rf"\b{_VERB}\b{_GAP}\b(?:at\s+least|greater\s+than\s+or\s+equal\s+to|"
        rf"no\s+less\s+than|no\s+fewer\s+than)\s+{_NUM}{_UNIT}",
        "ge",
        unit_group="unit",
    ),
    _p(
        "must_le",
        rf"\b{_VERB}\b{_GAP}\b(?:at\s+most|less\s+than\s+or\s+equal\s+to|"
        rf"no\s+more\s+than|no\s+greater\s+than)\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "must_gt",
        rf"\b{_VERB}\b{_GAP}\b(?:greater|more|larger)\s+than\s+{_NUM}{_UNIT}",
        "gt",
        unit_group="unit",
    ),
    _p(
        "must_lt",
        rf"\b{_VERB}\b{_GAP}\b(?:less|fewer|smaller)\s+than\s+{_NUM}{_UNIT}",
        "lt",
        unit_group="unit",
    ),
    _p(
        "must_eq",
        rf"\b{_VERB}\b{_GAP}\b(?:exactly|equal(?:led)?\s+to)\s+{_NUM}{_UNIT}",
        "eq",
        unit_group="unit",
    ),
    _p(
        "must_range",
        rf"\b{_VERB}\b{_GAP}\b(?:between|in\s+the\s+range\s+of)\s+{_NUM}"
        rf"\s*(?:and|through|to|-)\s*{_NUM2}{_UNIT}",
        "range",
        num2_group="num2",
        unit_group="unit",
    ),
    # ── C 组：无动词比较（文档 §3.4 给的示例形态）──────────────────────
    # ⚠ 必须排在 B 组之后 —— B 组带动词、更具体，先命中。
    _p(
        "at_least",
        rf"\bat\s+least\s+{_NUM}{_UNIT}",
        "ge",
        unit_group="unit",
    ),
    _p(
        "at_most",
        rf"\bat\s+most\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "no_more_than",
        rf"\bno\s+more\s+than\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "fewer_than",
        rf"\bfewer\s+than\s+{_NUM}{_UNIT}",
        "lt",
        unit_group="unit",
    ),
    _p(
        "more_than",
        rf"\bmore\s+than\s+{_NUM}{_UNIT}",
        "gt",
        unit_group="unit",
    ),
    _p(
        "limited_to",
        rf"\blimited\s+to\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "maximum_of",
        rf"\ba\s+maximum\s+of\s+{_NUM}{_UNIT}",
        "le",
        unit_group="unit",
    ),
    _p(
        "minimum_of",
        rf"\ba\s+minimum\s+of\s+{_NUM}{_UNIT}",
        "ge",
        unit_group="unit",
    ),
    # ── D 组：集合（枚举白名单）────────────────────────────────────────
    _p(
        "one_of_braces",
        rf"\b{_STRONG}\b{_GAP}\b(?:be|equal|one\s+of)[^.;]{{0,12}}?\{{(?P<items>[^}}]+)\}}",
        "in",
        items_group="items",
    ),
    _p(
        "one_of_list",
        rf"\b{_STRONG}\b{_GAP}\b(?:be\s+one\s+of|be\s+equal\s+to\s+one\s+of)\s+"
        rf"(?P<items>[^.;{{}}]+)",
        "in",
        items_group="items",
    ),
    # ── E 组：存在性（present / absent）─────────────────────────────────
    # ⚠ 否定式必须排在肯定式**之前**（"MUST NOT contain" vs "MUST contain"）。
    _p(
        "must_not_be_present",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\bbe\s+(?:present|defined)\b",
        "absent",
    ),
    _p(
        "must_not_contain",
        rf"\b{_STRONG}\s+NOT\b{_GAP}\b(?:contain|contains|contained|"
        rf"include|includes|included|carry|carries)\b",
        "absent",
    ),
    _p(
        "must_be_absent",
        rf"\b{_STRONG}\b{_GAP}\bbe\s+absent\b",
        "absent",
    ),
    _p(
        "must_be_present",
        rf"\b{_STRONG}\b{_GAP}\bbe\s+(?:present|defined)\b",
        "present",
    ),
    _p(
        "must_contain",
        rf"\b{_STRONG}\b{_GAP}\b(?:contain|contains|contained|"
        rf"include|includes|included|carry|carries)\b",
        "present",
    ),
    # ── F 组：字段引用（跨字段约束 —— §3.5 层次2「最有价值的一类」）─────
    _p(
        "size_of",
        rf"\b(?:the\s+)?(?:size|length)\s+of\s+(?:the\s+)?"
        rf"(?P<ref>{_FIELD}(?:\s+{_FIELD})?)",
        "eq",
        operand_source="field_ref",
        ref_group="ref",
    ),
    # ── G 组：ABNF 语法行（kind = "abnf"）──────────────────────────────
    _p(
        "abnf_rule",
        r"^[ \t]*(?P<ref>[A-Za-z][A-Za-z0-9-]*)[ \t]*(?::=|=)[ \t]*\S",
        "present",
        kind="abnf",
        field_group="ref",
    ),
)


# ===========================================================================
# 字段线索抽取与绑定
# ===========================================================================


def extract_field_clue(span_text: str) -> Optional[str]:
    """从约束句里抽取**字段线索**（纯语法位置，**不做模糊匹配**）。

    三条规则，**按优先级**（都要求特定句法位置，不是「猜」）：

      ① `<Token> header` / `<Token> field` ⇒ Token
         （"a Contact header field" → "Contact"）
      ② 动词**主语位**的 Token：`<Token> MUST/SHALL/...`
         （"Content-Length MUST be ..." → "Content-Length"）；
         ★ 排除句首常见词（"The client MUST ..." ⇒ "The" 不是字段）
      ③ `MUST (not) contain/include a <Token>` ⇒ Token
         （"MUST contain a Contact header" → "Contact"）

    ★ 返回的是**线索**，不是绑定结果 —— 真正的绑定由 `bind_field` /
      `try_convert` 的 C6 做**精确匹配**。
    """
    text = span_text or ""

    # ① "<Token> header|field"
    for m in re.finditer(
        rf"\b({_FIELD})\s+(?:header|field)\b", text, re.IGNORECASE
    ):
        return m.group(1)

    # ② 动词主语位
    m = re.search(
        rf"(?:^|[.;]\s*)(?P<t>{_FIELD})\s+(?:MUST|SHALL|REQUIRED|SHOULD|"
        rf"RECOMMENDED|MAY|OPTIONAL)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        token = m.group("t")
        if token.lower() not in _STOPWORDS:
            return token

    # ③ "contain/include a <Token>"
    m = re.search(
        rf"\b(?:contain|contains|contained|include|includes|included|"
        rf"carry|carries)\b\s+(?:a|an|the|any)?\s*(?P<t>{_FIELD})",
        text,
        re.IGNORECASE,
    )
    if m:
        token = m.group("t")
        if token.lower() not in _STOPWORDS:
            return token
    return None


def bind_field(clue: Optional[str], known_fields: Iterable[str]) -> Optional[str]:
    """把字段线索**精确绑定**到协议已知字段集（§3.5 层次4）。

    ★ **精确匹配或规范化匹配**（大小写、下划线/连字符）—— **不做模糊匹配**
      （§3.5 层次4 第3条：「模糊匹配是幻觉的主要来源」）。
    ★ 规范化复用 `core.fused.semantic.normalize_field_name` ⇒ 与 C6 **同口径**。

    返回**原始候选集里的那个字段名**（保持调用方拼写），绑不上返回 `None`
    ⇒ 调用方据此判 `field_unbound`。
    """
    if not clue:
        return None
    target = normalize_field_name(clue)
    if not target:
        return None
    for field in known_fields:
        if normalize_field_name(field) == target:
            return field
    return None


# ===========================================================================
# 动词 → 可断言性 / evidence_kind
# ===========================================================================


def expectation_assertable(span_text: str) -> bool:
    """该约束句能否携带「处理期望」（= 期望**可断言**）。

    ★ §3.5 层次1 第3条：
      · MUST / SHALL / REQUIRED ⇒ ✅ 期望**可断言**
      · SHOULD / RECOMMENDED ⇒ ❌ 期望**不可断言**（建议不是强制）
      · MAY / OPTIONAL ⇒ ❌ 落候选（`optional_modality`）
      · 无规范动词 ⇒ ❌ 非规范性证据
    """
    modality = detect_modality(span_text)
    return modality not in (
        MODALITY_NONE,
        MODALITY_OPTIONAL,
        MODALITY_RECOMMENDED,
    )


def resolve_evidence_kind(span_text: str, pattern_kind: str = "normative") -> str:
    """解析证据的 `evidence_kind`（`normative` / `abnf` / `prose`）。

    ★ §3.5 层次1 第2条（模式带 kind 标签）+ 第3条（规范性动词决定强度）：
      · 模式是 ABNF 语法行 ⇒ `"abnf"`
      · 句中含规范性动词 ⇒ `"normative"`
      · 其余（描述性）⇒ `"prose"`
    ★ 「无规范动词 → prose」这一行与 C3 的 `non_normative_kind` 对应。
    """
    if pattern_kind == "abnf":
        return "abnf"
    if detect_modality(span_text) != MODALITY_NONE:
        return "normative"
    return "prose"


# ===========================================================================
# 匹配与产出
# ===========================================================================


@dataclass(frozen=True)
class PatternMatch:
    """一次模式命中的结果（比 B-2 的 resolver 契约**更丰富**）。"""

    pattern: RulePattern
    operator: str
    operand: tuple[str, ...]
    operand_source: str
    operand_ref: Optional[str]
    target_field: str
    expected_behavior: str
    kind: str
    unit: Optional[str]
    reject_reason: Optional[str]

    def to_resolver_dict(self) -> dict:
        """转成 B-2 的 resolver 契约 dict。

        ★ `expected_behavior` 恒为 `""` —— **模式表不发明处理期望**
          （C/P 分离；P 由 B-6 / rfc_config 提供）。
        """
        out: dict = {
            "operator": self.operator,
            "operand": list(self.operand),
            "operand_source": self.operand_source,
            "operand_ref": self.operand_ref,
            "target_field": self.target_field,
            "expected_behavior": self.expected_behavior,
        }
        if self.reject_reason:
            out["reject_reason"] = self.reject_reason
        return out


def match_pattern(span_text: str) -> Optional[PatternMatch]:
    """用**有序**模式表匹配约束句，产出 `PatternMatch`（未命中返回 `None`）。

    ★ 第一个命中的模式生效。
    ★ 命中但**不可转换**（单位不可换算）⇒ 产出带 `reject_reason` 的
      `PatternMatch`（**不静默丢弃**）—— 调用方据此落知识候选。
    """
    text = span_text or ""
    for pattern in PATTERNS:
        m = pattern.regex.search(text)
        if not m:
            continue

        groups = m.groupdict()
        operand: tuple[str, ...] = ()
        operand_source = pattern.operand_source
        operand_ref: Optional[str] = None
        unit: Optional[str] = None
        reject_reason: Optional[str] = None

        if pattern.items_group:
            operand = _split_set(groups.get(pattern.items_group) or "")
        elif pattern.ref_group:
            ref = groups.get(pattern.ref_group)
            operand_ref = ref
            # ★ present/absent **不得**带 operand（B-1 构造校验第②条）
            operand = (ref,) if ref and pattern.operator not in (
                "present",
                "absent",
            ) else ()
        elif "num" in pattern.regex.groupindex:
            # 数值型模式：必须有 num 组
            raw = groups.get(pattern.num_group)
            if raw is None:
                continue
            operand = (_normalize_number(raw),)
            if pattern.num2_group:
                raw2 = groups.get(pattern.num2_group)
                if raw2 is None:
                    continue
                operand = operand + (_normalize_number(raw2),)
            if pattern.unit_group:
                normalized = normalize_unit(groups.get(pattern.unit_group))
                if normalized == "__reject__":
                    # ★ 单位不可换算成字节（seconds 等）⇒ **拒绝转换，不猜**
                    reject_reason = "non_length_operand"
                    unit = None
                else:
                    unit = normalized
        else:
            # 存在性模式（present / absent）：**无操作数**（§3.1 的约定：
            # present/absent 不带 operand，被约束的「东西」放在 target_field）
            pass

        if pattern.field_group:
            # 模式自带字段组（ABNF 产生式名）⇒ 直接作为 target_field
            target_field = groups.get(pattern.field_group) or ""
        else:
            target_field = extract_field_clue(text) or ""
        kind = resolve_evidence_kind(text, pattern.kind)

        return PatternMatch(
            pattern=pattern,
            operator=pattern.operator,
            operand=operand,
            operand_source=operand_source,
            operand_ref=operand_ref,
            target_field=target_field,
            expected_behavior="",
            kind=kind,
            unit=unit,
            reject_reason=reject_reason,
        )
    return None


def make_resolver(
    *,
    known_fields: Iterable[str] = (),
    expected_behavior: str = "",
) -> Callable[[str], Optional[dict]]:
    """产出符合 **B-2 resolver 契约**的 callable（§3.7：B-5 与 semantic.py 分开）。

    Args:
        known_fields: 协议已知字段集 —— 供字段**绑定**用；绑不上时
            `target_field` 置为 `""`（⇒ C6 判 `field_unbound`）。
        expected_behavior: 恒为 `""`（**无处理期望**）—— 模式表不发明 P。

    ★ 产出的 callable 满足：`resolver(span_text) -> Optional[dict]`。
    ★ 命中但不可转换时返回 `{"reject_reason": "non_length_operand"}`
      （B-2 会原样返回该原因 ⇒ 落知识候选）。
    """
    fields = tuple(known_fields)

    def resolver(span_text: str) -> Optional[dict]:
        match = match_pattern(span_text)
        if match is None:
            return None
        out = match.to_resolver_dict()
        if match.reject_reason:
            out["reject_reason"] = match.reject_reason
            return out
        # 字段绑定：线索绑不上 ⇒ 置空 ⇒ C6 判 field_unbound（**不模糊匹配**）
        bound = bind_field(match.target_field, fields)
        out["target_field"] = bound if bound is not None else ""
        return out

    return resolver


def _self_check() -> None:
    """模块自检：模式表与词表的一致性（导入时跑一次，极快）。"""
    valid_ops = {"eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent", "range"}
    for pattern in PATTERNS:
        if pattern.operator not in valid_ops:
            raise ValueError(
                f"模式 {pattern.name} 的 operator 非法: {pattern.operator}"
            )
        if pattern.kind not in ("normative", "abnf", "prose"):
            raise ValueError(f"模式 {pattern.name} 的 kind 非法: {pattern.kind}")
    if "non_length_operand" not in REJECT_REASONS:
        raise ValueError(
            "REJECT_REASONS 缺少 non_length_operand（B-5 单位拒转换依赖）"
        )


_self_check()
