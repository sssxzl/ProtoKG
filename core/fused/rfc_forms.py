# -*- coding: utf-8 -*-
"""core/fused/rfc_forms.py —— RFC 内容形态分类（**协议无关 / 位置无关**）。

★ 定位：把 RFC 文本按**客观排版与语法特征**切成块并判定其**内容形态**，
  供抽取层**按形态分派**（表格走确定性解析、图走 artifact、散文走 LLM 推断）。

★ 三条硬约束（见 `local/RFC形态分类与通用抽取落地方案.md` §0.2）：
  **G1 位置无关** —— 判据**不得**依赖「在附录 / 第几章 / 章节号前缀」；
  **G2 协议无关** —— 判据**不得**出现协议名、方法名白名单、章节号特例；
  **G3 形态驱动** —— 抽取路径由内容形态决定，不由位置或协议决定。
  ⇒ 本模块**不含任何协议相关常量**；附录里的表格照样判为 `table`。

★ 形态清单（8 类）：
  boilerplate（抬头/页眉页脚/作者地址）· toc（目录）
  table（列式表格）· diagram（ASCII 图形）· abnf（文法规则）
  example（示例报文）· normative（规范性条款）· descriptive（其余散文）

★ 形态分布实测（`local/_census_rfc_forms.py`，三协议形状一致）：
  行级 descriptive 81-85% / normative 2.3-6.9% / diagram 1.8-4.0% /
        table 1.8-3.6% / abnf 2.1-2.2% / boilerplate 3.5% / toc 0.2-2.9%

★ 两条实测得来的实现要点（否则分类器不可靠）：
  ① 图形字符集必须**收紧** —— 含 `/ = # * { } v` 会把正文 `HTTP/1.1 [2]` 误判成图；
  ② **块切分不能只按空行** —— ASCII 图内部常有空行 ⇒ 需「图形窗口合并」规则 M2。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ===========================================================================
# 形态清单
# ===========================================================================

#: 全部形态（8 类，**顺序即判定优先级**）。
FORM_KINDS: tuple[str, ...] = (
    "boilerplate", "toc", "table", "diagram",
    "abnf", "example", "normative", "descriptive",
)

#: 噪声形态（**丢弃**，不作为抽取候选）—— PROSPER 的 RFC 清洗规则。
NOISE_KINDS: tuple[str, ...] = ("boilerplate", "toc")

#: 需要「同类合并 / 图形窗口合并」的形态（结构性内容常被空行切碎）。
STRUCTURED_KINDS: tuple[str, ...] = ("table", "diagram", "abnf", "example")


# ===========================================================================
# 行级判据（**全部基于排版/语法客观特征**，无协议特例）
# ===========================================================================

#: RFC 抬头：「Request for Comments: 2326」
RE_RFC_HEADER = re.compile(r"^\s*Request for Comments:\s*\d+", re.I)
#: 分页符 `[Page 77]`；页眉「RFC 2326   Real Time Streaming Protocol   April 1998」
RE_PAGE_BREAK = re.compile(r"\[Page\s+\d+\]"
                           r"|^\s*RFC\s+\d+\s+\S.*\s+\w+\s+\d{4}\s*$")
#: 作者地址段标题
RE_AUTHOR_ADDR = re.compile(r"Author'?s? Address", re.I)
#: 目录行：连续点号 + 页码
RE_TOC = re.compile(r"\.{4,}\s*\d+\s*$")
#: 图题：「Figure 3.」/「图 3」
RE_FIGURE_CAP = re.compile(r"^\s*(?:Figure|Fig\.?|图)\s*\d+", re.I)
#: ABNF 规则：`name = ...` 或 `::=`
RE_ABNF = re.compile(r"::=|^\s*[A-Za-z][A-Za-z0-9\-]{0,30}\s*=\s*\S")
#: 规范性关键词
RE_NORMATIVE = re.compile(
    r"\b(MUST NOT|SHALL NOT|SHOULD NOT|MUST|SHALL|SHOULD|REQUIRED|MAY|OPTIONAL)\b")
#: 示例报文行：缩进 ≥2 + 全大写首词 + 参数。
#: ★ 第二 token **不能是纯大写词** —— 否则状态转移表的「续行」
#:   （继承状态名的行，如 `TEARDOWN         Init`）会被误判成示例报文
#:   （实测踩过：它让整张 A.1 表被投票带偏成 example）。
RE_EXAMPLE = re.compile(r"^\s{2,}([A-Z][A-Z_]{1,15})\s+(?!\s*[A-Z][A-Z0-9_]*\s*$)(\S+)")
#: 纯大写词（用于示例判据的否定条件）
_RE_UPPER_WORD = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: 列式行：≥2 处「2+ 空格或 tab」分隔
RE_COLUMNS = re.compile(r"\S[ \t]{2,}\S")
#: 图形字符（**框线特征字符**：正文罕见）。
#: ★ 收紧过程（实测驱动）：
#:   初版含 `/ = # * { } v` ⇒ 正文 `HTTP/1.1 [2]` 被误判为图；
#:   再版含 `-` 与 `[]` ⇒ `+-----+` 这种纯框线行只有 2 种字符 ⇒ 阈值 ≥3 判不出；
#:   ⇒ 最终只保留**框线/箭头**字符 `+ | < > ^`，阈值 ≥2 个。
DIAGRAM_CHARS = frozenset("+|<>^")
#: 一行构成图形行所需的框线字符**出现次数**下限。
#: ★ 判据用「次数」而非「种类数」：`+-----+` 只有 1 **种**框线字符但有 5 **个**；
#:   用种类数会漏判纯框线行（实测踩过）。
#: ★ 阈值取 **2**：`+---+` 只有 1 个 `+`、`| Play |` 只有 2 个 `|` ⇒ 阈值 3 会漏判
#:   真实 ASCII 图（实测踩过）。行级可能对含少量框线字符的正文偶发误判，
#:   **块级 60% 投票是主要防线**。
DIAGRAM_MIN_CHARS = 2


def _graphic_hits(line: str) -> int:
    """一行里框线/箭头字符的**出现次数**。"""
    return sum(line.count(c) for c in DIAGRAM_CHARS)


# ===========================================================================
# 块对象
# ===========================================================================

@dataclass
class FormBlock:
    """一个形态块。

    kind:      形态（`FORM_KINDS` 之一）
    text:      块文本（形态合并后的完整内容）
    line_start: 源文件真实行号（1-based，闭区间起点）
    line_end:   源文件真实行号（1-based，闭区间终点）
    refs:      [(行号, 行文本)] ⇒ 逐行溯源到原文
    """

    kind: str
    text: str
    line_start: int
    line_end: int
    refs: list[tuple[int, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.refs)


# ===========================================================================
# 行级分类
# ===========================================================================

def classify_line(line: str) -> str:
    """单行形态判定（**块级判定的前置**，不是最终结论）。

    ★ 顺序有讲究：结构性判据（目录 / 抬头 / 文法 / 示例 / 规范性）优先，
      表格与图形放最后（它们的特征更弱）。
    """
    if RE_TOC.search(line):
        return "toc"
    if (RE_RFC_HEADER.search(line) or RE_PAGE_BREAK.search(line)
            or RE_AUTHOR_ADDR.search(line)):
        return "boilerplate"
    if RE_ABNF.search(line):
        return "abnf"
    if RE_EXAMPLE.match(line):
        return "example"
    if RE_NORMATIVE.search(line):
        return "normative"
    if len(RE_COLUMNS.findall(line.rstrip())) >= 2:
        return "table"
    if _graphic_hits(line) >= DIAGRAM_MIN_CHARS:
        return "diagram"
    return "descriptive"


def _is_diagram_line(line: str) -> bool:
    """图形行判定（**收紧**后的框线特征字符集）。"""
    return _graphic_hits(line) >= DIAGRAM_MIN_CHARS


# ===========================================================================
# 块级分类
# ===========================================================================

def classify_form(block_lines: list[str]) -> str:
    """块级形态判定（**位置无关、协议无关**）。

    ★ 关键：**形态必须在块级判** —— 行级会互相污染
      （表格块里每行都可能含 MUST；正文行可能含图形字符）。

    判定顺序：
      ① 图形块特判（块内 ≥60% 行是图形行，且块长 ≥3）
      ② 表格块特判（块内 ≥60% 行是列式行，且块长 ≥3）
      ③ 其余按行级投票：噪声多数 ⇒ 噪声；abnf/example ≥50%；normative ≥30%；
         table ≥50%；否则 descriptive
    """
    n = len(block_lines)
    if n == 0:
        return "descriptive"
    if n == 1:
        return classify_line(block_lines[0])

    votes: dict[str, int] = {}
    for ln in block_lines:
        k = classify_line(ln)
        votes[k] = votes.get(k, 0) + 1

    # ★ **噪声优先**（必须先于表格/图形特判）：
    #   目录块（`12.  Dialogs ....... 69`）的行**也是列式** ⇒ 若先做表格特判，
    #   整本 RFC 的目录会被判成一张大表（实测：多个协议的 table 块全是目录）。
    top = max(votes.items(), key=lambda kv: (kv[1], -list(votes).index(kv[0])))
    if top[0] in NOISE_KINDS:
        return top[0]

    if n >= 3:
        dg = sum(1 for ln in block_lines if _is_diagram_line(ln))
        if dg / n >= 0.6:
            return "diagram"
        # ★ **表头驱动**：表头行几乎必然是列式（≥2 处分隔）⇒ 有列式行即判表。
        #   旧判据「≥60% 的行是列式」会漏判**带续行**的表格 ——
        #   状态转移表的续行（继承状态名）只有 1 处分隔 ⇒ 列式占比低
        #   （实测某协议的状态转移表：15 行里只有 4 行是列式 = 27%）⇒ 被投票带偏。
        col = sum(1 for ln in block_lines
                  if len(RE_COLUMNS.findall(ln.rstrip())) >= 2)
        if col >= 1 and col / n >= 0.2:
            return "table"
    if votes.get("abnf", 0) / n >= 0.5:
        return "abnf"
    if votes.get("example", 0) / n >= 0.5:
        return "example"
    if votes.get("normative", 0) / n >= 0.3:
        return "normative"
    if votes.get("table", 0) / n >= 0.5:
        return "table"
    return "descriptive"


# ===========================================================================
# 切块（含形态感知合并）
# ===========================================================================

def _base_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """B1：连续非空行 = 一个基础块 ⇒ 返回 [(起始行号0, 结束行号0)]（0-based）。"""
    spans: list[tuple[int, int]] = []
    start = None
    for i, ln in enumerate(lines):
        if ln.strip():
            if start is None:
                start = i
        else:
            if start is not None:
                spans.append((start, i - 1))
                start = None
    if start is not None:
        spans.append((start, len(lines) - 1))
    return spans


def _merge_diagram_groups(lines: list[str],
                          spans: list[tuple[int, int]],
                          max_gap: int = 2) -> list[tuple[int, int]]:
    """M2：**图形窗口合并** —— 相邻的图形行即使被空行隔开也并成一块。

    ★ 必要性（实测）：ASCII 状态图内部常有空行 ⇒ 只按空行切会把图切碎
      （实测某协议 §17 的 ASCII 图被切成多块，只剩 1 块被判为 diagram）。
    ⇒ 规则：两段图形行之间若间隔空行 ≤ `max_gap`，则合并。
    """
    if not spans:
        return spans
    out: list[tuple[int, int]] = []
    cur = None
    for lo, hi in spans:
        body = lines[lo:hi + 1]
        has_dg = any(_is_diagram_line(ln) for ln in body)
        if cur is None:
            cur = [lo, hi, has_dg]
            continue
        gap = lo - cur[1] - 1
        if cur[2] and has_dg and gap <= max_gap:
            # 两段都含图形行且间隔不大 ⇒ 合并
            cur[1] = hi
            cur[2] = True
        else:
            out.append((cur[0], cur[1]))
            cur = [lo, hi, has_dg]
    if cur is not None:
        out.append((cur[0], cur[1]))
    return out


def _merge_same_kind(spans: list[tuple[int, int]],
                     kinds: list[str]) -> list[tuple[int, int]]:
    """M1：**同类合并** —— 相邻且形态同类（结构性形态）的块合并。

    ★ 必要性：RFC 的表格常被空行分段（如状态转移表中间有空行）。
    """
    if not spans:
        return spans
    out: list[tuple[int, int]] = []
    cur = [spans[0][0], spans[0][1], kinds[0]]
    for (lo, hi), k in zip(spans[1:], kinds[1:]):
        if k in STRUCTURED_KINDS and k == cur[2]:
            cur[1] = hi
        else:
            out.append((cur[0], cur[1]))
            cur = [lo, hi, k]
    out.append((cur[0], cur[1]))
    return out


def split_form_blocks(lines: list[str], *,
                      drop_noise: bool = True) -> list[FormBlock]:
    """把 RFC 文本切成**形态块**（协议无关 / 位置无关）。

    Args:
        lines:      RFC 文本的**全部行**（含空行）。
        drop_noise: 是否丢弃 `boilerplate` / `toc`（PROSPER 清洗规则，默认丢弃）。

    Returns:
        `FormBlock` 列表（按源文件行序）。

    ★ 合并规则：M2 图形窗口合并 → B1 基础切块 → 块级分类 → M1 同类合并。
    """
    if not lines:
        return []
    spans = _base_blocks(lines)
    # M2：图形窗口合并（先做，避免图被空行切碎后再无法按类合并）
    spans = _merge_diagram_groups(lines, spans)
    # 块级分类（此时块已是"结构单元"）
    kinds = [classify_form(lines[lo:hi + 1]) for lo, hi in spans]
    # M1：同类合并
    spans = _merge_same_kind(spans, kinds)
    # 重新分类（合并后形态可能变化 ⇒ 以合并后的内容为准）
    kinds = [classify_form(lines[lo:hi + 1]) for lo, hi in spans]

    blocks: list[FormBlock] = []
    for (lo, hi), kind in zip(spans, kinds):
        if drop_noise and kind in NOISE_KINDS:
            continue
        refs = [(i + 1, lines[i].rstrip()) for i in range(lo, hi + 1)
                if lines[i].strip()]
        text = "\n".join(lines[i].rstrip() for i in range(lo, hi + 1)
                         if lines[i].strip())
        blocks.append(FormBlock(kind=kind, text=text,
                                line_start=lo + 1, line_end=hi + 1,
                                refs=refs))
    return blocks


def form_candidates(lines: list[str], kinds: tuple[str, ...]) -> list[FormBlock]:
    """只取指定形态的块（抽取层按形态分派时用）。"""
    return [b for b in split_form_blocks(lines) if b.kind in kinds]


__all__ = [
    "FORM_KINDS", "NOISE_KINDS", "STRUCTURED_KINDS", "FormBlock",
    "classify_line", "classify_form", "split_form_blocks", "form_candidates",
]


# ===========================================================================
# 状态转移表解析（**按列角色**，协议无关）
# ===========================================================================

#: 表头列角色关键词（**协议无关**：按列名语义，不含任何协议/章节特例）。
COL_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "from": ("state", "current state", "from state", "old state"),
    "trigger": ("message", "trigger", "event", "command", "request",
                "action", "sent", "received"),
    "to": ("next state", "next", "new state", "resulting state",
           "to state", "new"),
}

#: 状态名里的修饰后缀（如 `Playing (changed transport)`）
RE_STATE_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


def _split_columns(line: str) -> list[str]:
    """按列分隔符切成列（**协议无关**：支持「2+ 空格 / tab / 竖线」）。

    ★ 必须支持竖线分隔：RFC 里的表格常用 `state | message | next state`
      形式（实测：只按 2+ 空格切会整行切成 1 列 ⇒ 表头角色匹配失败 ⇒
      该表被整段漏掉）。
    ★ 竖线优先（比多空格是更强的列边界信号）；表格块内才用本函数。
    """
    s = line.strip()
    if "|" in s:
        parts = [q.strip() for q in s.strip("|").split("|")]
        return [q for q in parts if q]
    parts = re.split(r"[ \t]{2,}", s)
    return [q.strip() for q in parts if q]


def _match_roles(header_cols: list[str]) -> dict[str, int]:
    """表头列 → 角色（from / trigger / to）的列序号。

    ★ 协议无关：按**列名语义**判定，不按固定列号 ⇒ 换协议/换列名/换列数都能用。
    """
    roles: dict[str, int] = {}
    for i, col in enumerate(header_cols):
        low = col.lower()
        for role, keys in COL_ROLE_KEYWORDS.items():
            if role in roles:
                continue
            if any(k in low for k in keys):
                # ★ 「next state」含 "state" ⇒ 必须先试 to 再试 from
                if role == "from" and any(k in low for k in COL_ROLE_KEYWORDS["to"]):
                    continue
                roles[role] = i
                break
    return roles


def parse_state_table(block: FormBlock) -> list[dict]:
    """按**列角色**解析一个 `table` 块里的状态转移（协议无关）。

    ★ 与既有「三列定宽 + 状态名继承」硬编码解析的差别：
      按**表头列名**判定哪一列是起态 / 触发 / 目标 ⇒ 列名不同、列数不同都能解析。
    ★ 支持**续行右对齐**：RFC 表格的续行会省略左侧列（如只有「触发 + 目标」），
      故列数不足时按**末尾对齐**（右对齐）映射到角色。
    ★ 状态名去掉修饰后缀（`Playing (changed transport)` → `Playing`）。

    Returns:
        `[{"from":…, "method":…, "to":…}, …]`；不是状态转移表时返回 `[]`。
    """
    if block.kind != "table" or len(block.refs) < 2:
        return []
    # ① 找表头行（含 ≥2 个角色关键词）
    header_idx = None
    roles: dict[str, int] = {}
    for i, (_ln, txt) in enumerate(block.refs):
        cols = _split_columns(txt)
        r = _match_roles(cols)
        if len(r) >= 2 and ("from" in r or "to" in r) and "trigger" in r:
            header_idx, roles = i, r
            break
    if header_idx is None or "trigger" not in roles:
        return []

    out: list[dict] = []
    last_from = ""
    for _ln, txt in block.refs[header_idx + 1:]:
        cols = _split_columns(txt)
        if not cols:
            continue
        n_roles = len(roles)
        if len(cols) >= n_roles:
            cols = cols[-n_roles:]            # 取末尾 n 个（右对齐）
        elif len(cols) < n_roles:
            cols = [""] * (n_roles - len(cols)) + cols   # ★ 右对齐（续行省左侧列）
        else:
            continue
        val = {role: cols[idx] if idx < len(cols) else ""
               for role, idx in roles.items()}
        frm = RE_STATE_SUFFIX.sub("", val.get("from", "")).strip()
        if frm:
            last_from = frm
        else:
            frm = last_from                     # ★ 状态名继承
        trig = val.get("trigger", "").strip()
        to = RE_STATE_SUFFIX.sub("", val.get("to", "")).strip()
        if not (frm and trig and to):
            continue
        out.append({"from": frm, "method": trig, "to": to})
    return out


__all__ += ["parse_state_table", "COL_ROLE_KEYWORDS"]
