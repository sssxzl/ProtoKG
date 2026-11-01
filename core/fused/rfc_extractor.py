# -*- coding: utf-8 -*-
"""core/fused/rfc_extractor.py —— 从 RFC 规范文本确定性抽取 rfc norm。

背景：rfc 源此前依赖 v1 norms.jsonl（已被 source 源覆盖），导致 0 facts。
本模块直接从 kb/<protocol>/spec/*.txt 抽取 rfc norm（method/field/outcome），
喂给 core.fused.norm.map_norm_to_facts 映射为 normative fact。

抽取策略（对齐 layer2_extraction_methods.md §三 rfc 行：FlowFSM/SpecGPT 的
「rule 解析固定格式 + LLM 补语义」——本模块先做 rule 部分，LLM 语义留 -m llm 钩子）：

  - method  ：§<method_section>.N 章节标题为全大写方法名（如「10.1 OPTIONS」）
  - field   ：§<header_section>.N 章节标题为字段名（如「12.1 Accept」）
  - outcome ：§<status_section>.N.M 章节标题为「NNN Reason」（如「11.1.1 250 Low...」）

章节号是协议特定的（RTSP RFC2326 = 10/11/12），默认值内置，可在 profile.json 的
rfc_sections 覆盖（换协议只换数据）。正文抽取时清理 RFC 页眉页脚（[Page N] /
RFC xxxx 标题行）。

注：状态机（transition）不在此确定性抽取范围——RFC 的状态机是自然语言场景描述
（§14），需 LLM 理解；source 源（AutoSeeder）已产出状态机，rfc 的 transition
留待后续 LLM 补（-m llm）。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core import paths
from core.fused.norm import constraint_identity_digest

#: 任意层级章节标题（协议无关，不限定层级数）：`N.N(...) Title`（标题为无空格单词）。
#: 要求至少一个 `.N`（二级及以上），排除一级标题（如「6 Request」「13 Caching」这类章节名）。
#: 不依赖「某章节号=方法」的 RTSP 特定假设，只看标题格式。
#:
#: ⚠ 这个正则**只认单词型标题**（标题组 `[A-Za-z][A-Za-z0-9\-_]*`），
#:   对 RFC 真实章节标题的命中率实测仅 **15.2%**（276/1815）——
#:   因为真实标题多为多词（「Basic Structure」「The OPTIONS method」
#:   「DATA REPRESENTATION」）。**这是 A1.3 要修的核心缺陷。**
#:   保留此正则仅作「单词型标题」快速路径，主路径改用 _parse_heading。
_RE_ANY_SECTION = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+([A-Za-z][A-Za-z0-9\-_]*)\s*$")
#: 状态码标题（任意层级，二级及以上）：`N.N(...) NNN Reason`（标题以 3 位数字开头，协议通用）
_RE_STATUS_ANY = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+(\d{3})\s+(.+?)\s*$")
#: 方法名：全大写（如 OPTIONS / GET_PARAMETER）
_RE_METHOD_NAME = re.compile(r"^[A-Z][A-Z_0-9]*$")
#: 字段名：首字母大写单词（含连字符，如 Accept / CSeq / Accept-Encoding）
_RE_FIELD_NAME = re.compile(r"^[A-Z][A-Za-z0-9\-]*$")
#: 任意标题（含多词/括号，用于 LLM 兜底收集）：`N.N(...) 任意文本`。
#: 比 _RE_ANY_SECTION 宽松，能匹配「Extended HELLO (EHLO)」这类带空格/括号标题，
#: 这些正则识别不了的标题交给 infer_structures 的 LLM 兜底。
_RE_ANY_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+(.+?)\s*$")
#: 一级标题：`N. Title` 或 `N Title`（RTSP 的 `5 General Header Fields` 无点号）
_RE_TOP_HEADING = re.compile(r"^(\d{1,2})\.?\s+(\S.*?)\s*$")
#: 全大写词组（含空格，如 `DATA REPRESENTATION` / `EXTENDED HELLO`）——方法名放宽形态
_RE_UPPER_PHRASE = re.compile(r"^[A-Z][A-Z0-9]*(?:[ -][A-Z0-9]+)*$")
#: 标题里带括号（`Extended HELLO (EHLO)`）——命令/方法的强特征
_RE_HAS_PAREN = re.compile(r"\([^)]+\)")
#: **数据行**（不是标题）：标题部分为纯数字/十六进制串。
#: RFC 正文里的协议数据图示（如 SSH RFC4251 的 `0 00 00 00 00`、
#: `80 00 00 02 00 80`）会形如「N 十六进制串」，若当标题会污染章节树
#: （实测 SSH 出现 2 个，扰乱父子关系）。此处显式排除。
_RE_DATA_ROW = re.compile(r"^[0-9a-fA-F]{2,}(?:\s+[0-9a-fA-F]{2,})*$")


#: RFC 通用章节词（几乎所有 RFC 都有的章节名，非方法/字段/状态码）。
#: 这是「RFC 文档通用结构」，非某协议专属，故放通用层。
_GENERIC_SECTION_WORDS = {
    "INTRODUCTION", "OVERVIEW", "TERMINOLOGY", "REQUIREMENTS", "PURPOSE",
    "CONVENTIONS", "NOTATION", "DEFINITIONS", "GLOSSARY", "HISTORY",
    "SECURITY", "CONSIDERATIONS", "EXAMPLES", "SYNTAX", "MODEL", "USAGE",
    "PARAMETERS", "PROPERTIES", "OPERATION", "REFERENCES",
    "ACKNOWLEDGEMENTS", "ACKNOWLEDGMENTS", "CONTENTS", "ABSTRACT",
    "COPYRIGHT", "AUTHORS", "PIPELINING", "STATUS",
    # 命令分组名（FTP 的 `4.1. FTP COMMANDS` / `4.1.1. ACCESS CONTROL COMMANDS`
    # 等）—— 它们是**章节标题**而非具体命令，需排除，否则会产出
    # 「FTP COMMANDS」这种伪方法。
    "COMMANDS", "FTP COMMANDS", "ACCESS CONTROL COMMANDS",
    "TRANSFER PARAMETER COMMANDS", "FTP SERVICE COMMANDS",
    "MESSAGES", "MESSAGE FORMATS", "COMMAND SYNTAX",
    "BACKGROUND",   # SMTP RFC5321 §2.2.1 的历史背景小节名（非协议字段）
}

#: RFC 页眉页脚（需清理）
_RE_PAGE_MARK = re.compile(r"\[Page\s+\d+\]")
_RE_RFC_TITLE = re.compile(r"^RFC\s+\d+")
_RE_EMPTY_OR_DOTS = re.compile(r"^\s*(\.+\s*)*$")

#: TOC（目录）行判定 —— 必须**在章节树构建之前**执行（评审 T7 + 改进v2 问题①）。
#:
#: RFC 目录行的四种典型形态：
#:   ① **连续**点线引导 + 尾页码：`   21.1.1 100 Trying ........................... 183`
#:   ② **连续**点线引导无页码：`   4.1.  Basic Structure .....................`
#:   ③ **间隔**点线引导 + 尾页码：`   1.  Introduction . . . . . . . . . . .  5`
#:      （RFC 5321/5322 的排版 —— ★ P0-1 修复新增的形态）
#:   ④ 纯点线分隔行：`   ..............................`
#:
#: ⚠ 关键：TOC 命中会污染知识库——同一状态码在 TOC 版与正文版各抽一次，
#:   产生**同一 fact_key 被抽两次**（实测 SIP 68 个 fact_id 冲突，根因在此）。
#:   且 TOC 的目录文字**不是有效规范证据**，不能进 all_claims。
#:
#: 判定用「点线数量」而非「是否含数字」：正文里的章节号/状态码本身也是数字，
#: 用数字会误删正文（实测 RFC 正文大量含数字行）。点线引导是 TOC 的可靠特征。
_RE_TOC_DOTS = re.compile(r"\.{3,}")
#: TOC 行尾页码：整行以「空白 + 数字」结尾，且行内出现过点线
_RE_TOC_TRAIL_PAGE = re.compile(r"\.\s*\d+\s*$")
#: ★ 间隔点线（spaced dot leader）：点与点之间夹空白 —— `. . . .`。
#:
#: RFC 5321/5322 的目录用**间隔点线**排版（不是 `....` 连续点线）：
#:     `   1.  Introduction . . . . . . . . . . . . . . . . . . . . . . . . .  5`
#:     `     1.1.  Transport of Electronic Mail . . . . . . . . . . . . . . .  5`
#: ⇒ 只认 `_RE_TOC_DOTS`（连续点线）会**整片漏判** SMTP 的目录
#:   （实测 SMTP 195 行间隔点线目录 0 命中 ⇒ 章节树里 39% 的节点是目录条目）。
#:
#: ⚠ **绝不能只凭间隔点线判 TOC**：正文里的省略号形态**完全相同**：
#:     `       Alice's  . . . . . . . . . . . . . . . . . . . .  Bob's`（SIP RFC3261）
#:   唯一可靠的区分特征是**行尾页码** —— 目录行必带页码，正文省略号不带。
#:   故本正则**必须**与 `_RE_TOC_TRAIL_PAGE` 联用（见 `_is_toc_line`）。
#:   （本正则要求**至少 3 个点**且点间有空白；2 个点的 `. .` 形态在正文里也常见。）
_RE_TOC_SPACED_DOTS = re.compile(r"(?:\.\s+){2,}\.")
#: 目录块锚点标题（`Table of Contents` / `Contents`）—— RFC 里目录的固定入口。
#: 用于「目录块兜底」（见 `_toc_block_ranges`）。
_RE_TOC_ANCHOR = re.compile(r"^\s*(?:table\s+of\s+contents|contents)\s*$",
                            re.IGNORECASE)
#: 目录块的**终止标志**：**零缩进**的一级章节标题（`1. Introduction` / `1 Introduction`）。
#:
#: 为什么用「零缩进」：RFC 的**目录条目一律有缩进**（3 空格起），而正文的一级
#: 章节标题**一律顶格**（RFC 2326/3261/5321/5322/4954 实测全部如此）⇒ 二者可
#: 无歧义区分。用「章节号 + 顶格」而不是「任意标题」做终止标志，可避免把目录里
#: 的**折行条目**（如 SIP 的 `26  Security Considerations: Threat Model and
#: Security` + 下一行补点线）误判成正文起点。
_RE_TOC_BLOCK_END = re.compile(r"^\d{1,2}\.?\s+\S")

#: rfc_config.json 中「值为字符串数组」的键（其余键忽略）。
#: 章节号前缀 / 排除词 / 数值边界 / 期望响应词表都按字符串数组处理，
#: 统一做 str() 归一，避免配置文件里写成数字（如 21 而非 "21"）时丢键。
_RFC_CONFIG_LIST_KEYS: tuple[str, ...] = (
    "method_sections",
    "field_sections",
    "status_sections",
    "method_excludes",
    "numeric_bounds",
    "expected_response_classes",
)


def _read_json(path: Path) -> Optional[dict]:
    """读 JSON 对象；失败（不存在/非法/非对象）返回 None（调用方决定降级策略）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_toc_line(line: str) -> bool:
    """判断一行是否为 RFC 目录（TOC）行。

    判定顺序（从严到宽）：
      ① 含**连续**点线引导（`\\.{3,}`）→ TOC
      ② 含**间隔**点线引导（`. . . .`）**且行尾带页码** → TOC
      ③ 整行以页码结尾且此前含点线 → TOC
      ④ 纯点线/纯空白行 → TOC（非内容行）
    正文行（含章节号、状态码、数字）**不**被判定为 TOC。

    ★ ② 的「必须带行尾页码」是**零误报的关键**（P0-1 修复）：
      间隔点线在正文里是**省略号**，形态与目录点线完全一样：
        目录：`   1.  Introduction . . . . . . . . . . . . . . . . . . . . . . . . .  5`
        正文：`       Alice's  . . . . . . . . . . . . . . . . . . . .  Bob's`（SIP RFC3261）
      目录行**必带页码**、正文省略号**不带** ⇒ 页码是唯一可靠判据。
      ⚠ 不得把本条放宽成「含点线就算目录」—— 那会把 SIP 的省略号误判成目录。
    """
    s = (line or "").strip()
    if not s:
        return True
    # ① 连续点线引导（传统目录排版）
    if _RE_TOC_DOTS.search(s):
        return True
    # ② 间隔点线引导 + 行尾页码（RFC 5321/5322 的目录排版）
    if _RE_TOC_SPACED_DOTS.search(s) and _RE_TOC_TRAIL_PAGE.search(s):
        return True
    # ③ 点线 + 行尾页码（旧口径兜底）
    if _RE_TOC_TRAIL_PAGE.search(s) and "..." in s:
        return True
    return False


def _has_dot_leader(line: str) -> bool:
    """一行是否带点线引导（连续或间隔形态）。

    用于「目录块兜底」：目录块里**没有点线**的行才会被兜底判为 TOC，
    带点线的行一律交给 `_is_toc_line` 处理 ⇒ 两条判定路径互不干扰，
    且 `_is_toc_line` 失效时（质量闸的检出力测试会 monkeypatch 它），
    目录块兜底**不会**顶替它把目录整片吃掉。
    """
    s = (line or "").strip()
    if not s:
        return False
    return bool(_RE_TOC_DOTS.search(s) or _RE_TOC_SPACED_DOTS.search(s))


def _toc_block_ranges(lines: list[str]) -> list[tuple[int, int]]:
    """定位 RFC **目录块**的下标区间（半开区间 ``[start, end)``）。

    目录块 = 锚点标题（`Table of Contents`）之后，到**下一个零缩进一级章节
    标题**之前的全部行。用于兜住**排版不规则**的目录条目 —— 典型是**折行条目**：

        SIP RFC3261 目录里：
            `   26         Security Considerations: Threat Model and Security`
            `              Usage Recommendations ...............................  232`
        第一行**没有点线**（点线在折行后的第二行）⇒ 只靠点线判据会漏判，
        它会被当成四级章节标题 `26` 进章节树 ⇒ 目录条目污染知识库。

    判定要点：
      - 锚点：`Table of Contents` / `Contents`（大小写不敏感）；
      - 终止：**零缩进**的一级章节标题（`_RE_TOC_BLOCK_END`，见其注释）；
      - ⚠ **找不到终止标志就不产出区间**（宁可漏兜底，也不可把整篇正文
        误当成目录剥掉）—— 这是本兜底的安全阀。

    Args:
        lines: 已清洗的文档行（保留原始缩进）。

    Returns:
        目录块下标区间列表（可为空）。
    """
    ranges: list[tuple[int, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        if not _RE_TOC_ANCHOR.match(lines[i]):
            i += 1
            continue
        start = i + 1
        end: Optional[int] = None
        for j in range(start, n):
            if _RE_TOC_BLOCK_END.match(lines[j]):
                end = j
                break
        if end is None:
            # ⚠ 安全阀：无终止标志 → 不产出目录块（避免误剥正文）
            i += 1
            continue
        if end > start:
            ranges.append((start, end))
        i = end
    return ranges


def _in_toc_block(index: int, ranges: list[tuple[int, int]]) -> bool:
    """下标是否落在任一目录块区间内。"""
    for start, end in ranges:
        if start <= index < end:
            return True
    return False



def _clean_body(lines: list[str]) -> str:
    """清理 RFC 正文：去页眉页脚、去纯分隔线、压缩空白，返回一段干净文本。"""
    kept: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _RE_PAGE_MARK.search(s):
            continue
        if _RE_RFC_TITLE.match(s):
            continue
        if _RE_EMPTY_OR_DOTS.match(s):
            continue
        if re.fullmatch(r"[A-Za-z]+,\s*et\.?\s*al\.?", s):
            continue  # 通用 RFC 作者页眉（"<作者姓>, et. al."），所有 RFC 均有，非某协议专属
        kept.append(s)
    return " ".join(kept)


def _first_sentence(text: str, limit: int = 300) -> str:
    """取正文首句/首段（截断到 limit 字符），作为方法/字段的语义摘要。"""
    text = text.strip()
    if not text:
        return ""
    # 首个句号/分号处截断，否则按长度截断
    m = re.search(r"[.;](?:\s|$)", text)
    if m:
        text = text[:m.start() + 1]
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text


# ===========================================================================
# A1.3　标题识别（宽松形态，替代只认单词的 _RE_ANY_SECTION）
# ===========================================================================

@dataclass(frozen=True)
class SectionHead:
    """一个章节标题（已识别）。

    level:  1 = 一级（N. / N），2 = 二级（N.N），3+ = 更深
    number: 章节号字符串（"10.1"）；一级标题可能为空串（无编号）
    title:  标题文本（可多词，可带括号）
    line:   ★ **源文件中的真实行号**（1-based，指向 RFC 原文的该标题行）。

    ⚠ P1-3 修复（2026-11-01）：此字段此前存的是**标题在 heads 列表中的序号**
      （`line_no=len(heads)`），**不是**源文件行号 —— 导致 `norm["source"]`
      的 `@N` 定位器指向错误位置（实测 RTSP `OPTIONS` 报 `@41`，真实行号 ≈1214），
      溯源链断裂。现在由抽取流程把**清洗前的原始行号**一路带下来。
    """
    level: int
    number: str
    title: str
    line: int


def _parse_heading_shape(line: str, line_no: int = 0) -> Optional[SectionHead]:
    """按**形态**解析一行是否为章节标题（**不做 TOC 判定**）。

    这是 `_parse_heading` 的内核，被单独抽出是为了让「目录块兜底」能复用
    同一套标题形态判据、而**不依赖** `_is_toc_line`（否则两者自证）。

    识别规则（从严到宽）：
      ① 状态码标题 `N.N NNN Reason` → level=章节号层级
      ② 二级+标题 `N.N... Title`（标题可多词）→ level=点分段数+1
      ③ 一级标题 `N. Title` / `N Title` → level=1
    """
    s = (line or "").strip()
    if not s:
        return None

    # ① 状态码标题：N.N NNN Reason
    m = _RE_STATUS_ANY.match(s)
    if m:
        number, code, reason = m.group(1), m.group(2), m.group(3).strip()
        return SectionHead(level=number.count(".") + 1, number=number,
                           title=f"{code} {reason}", line=line_no)

    # ② 二级及以下标题：N.N(.N)* Title（标题可多词）
    m = _RE_ANY_HEADING.match(s)
    if m:
        number = m.group(1)
        title = m.group(2).strip()
        return SectionHead(level=number.count(".") + 1, number=number,
                           title=title, line=line_no)

    # ③ 一级标题：N. Title / N Title
    #    排除「行首数字 + 空格 + 普通句子」——RFC 正文里常有 `1 概述` 这类
    #    列表项。用「标题长度受限 + 无句末标点」降低误判。
    #    ★ 再加「标题内不含句号」：RFC 编号列表项（`8. The registrar returns
    #      a 200 (OK) response.  The response MUST ...`）是**完整句子**、
    #      中间含句号，被误判成一级标题后，「(OK)」括号内全大写缩写又被
    #      `_normalize_method_name` 误当方法（实测 SIP 抽出伪方法 `OK`）。
    #      真实标题不含句号。
    m = _RE_TOP_HEADING.match(s)
    if m:
        number, title = m.group(1), m.group(2).strip()
        if (title and len(title) <= 80
                and not title.endswith((".", ",", ";"))
                and "." not in title
                and not _RE_DATA_ROW.match(title)):
            return SectionHead(level=1, number=number, title=title, line=line_no)
    return None


def _parse_heading(line: str, line_no: int = 0) -> Optional[SectionHead]:
    """解析一行是否为章节标题，返回 SectionHead 或 None。

    ★ A1.3 的核心（改进v2 问题①）：这是**放宽**的标题识别，取代原先只认
      单词的 `_RE_ANY_SECTION`。它必须能识别 RFC 里真实存在的多词标题：
        - `4.1.  Basic Structure`      （点号 + 多词 + 双空格）
        - `10.1 The OPTIONS method`     （多词，含小写）
        - `3.1.  DATA REPRESENTATION`   （多词，全大写）
        - `5 General Header Fields`     （一级标题，无点号）
        - `21.1.1 100 Trying`           （状态码标题）

    ⚠ **不做形态猜测分类**（是方法还是字段还是状态码）——分类由
      `_section_kind()` 查 rfc_config 决定（评审 T7：语义判定替代形态猜测）。

    ★ `line_no` 必须是**源文件真实行号**（P1-3）：它会一路写进
      `norm["source"]` 的 `@N` 定位器。传 0 只是占位（旧调用方语义）。
    """
    s = (line or "").strip()
    if not s:
        return None
    # TOC 行不是标题（必须在建树之前排除，见 _is_toc_line）
    if _is_toc_line(s):
        return None
    return _parse_heading_shape(s, line_no)


# ===========================================================================
# A1.4　章节树 + 有预算的自底向上合并（SpecGPT Algorithm 1）
# ===========================================================================

@dataclass
class SectionNode:
    """章节树节点。"""
    head: SectionHead
    children: list = field(default_factory=list)
    body_lines: list = field(default_factory=list)   # 本节正文（不含子节）
    parent: Optional["SectionNode"] = None
    #: ★ B-3：本节正文各行在**源文件**中的真实行号（与 `body_lines` 一一对应）。
    #:   为空列表 = 该节点**非行感知**构建（`body_nos` 缺省）⇒ 行号取 0。
    #:   作用：让章节窗口的文本可回溯到原文位置 —— 约束候选的 span 定位依赖它。
    body_line_nos: list = field(default_factory=list)

    @property
    def level(self) -> int:
        return self.head.level

    @property
    def number(self) -> str:
        return self.head.number

    @property
    def title(self) -> str:
        return self.head.title


@dataclass(frozen=True)
class MergeBudget:
    """自底向上合并的预算（评审 F2：上下文膨胀防护）。

    max_depth:     最多向上合并几层（防父节正文被子节反复携带）
    max_chars:     单个窗口的字符上限（超出截断）
    dedup:         是否对重复正文去重
    cycle_guard:   是否启用引用环检测
    """
    max_depth: int = 2
    max_chars: int = 4000
    dedup: bool = True
    cycle_guard: bool = True


def _build_section_tree(heads: list[SectionHead],
                        bodies: list[list[str]],
                        body_nos: Optional[list[list[int]]] = None
                        ) -> list[SectionNode]:
    """由标题序列 + 各标题之间的正文行，构建章节树。

    heads[i] 对应 bodies[i]（该标题到下一个标题之间的正文行）。
    返回顶层节点列表（按文档顺序）。

    实现要点：
      - 用栈维护「祖先链」，按 level 决定挂到哪个父节点；
      - 层级跳跃（level 差 > 1）时挂到最近的、level 更小的祖先；
      - 标题号本身已隐含层级（如 `10.1.2`），比 level 更可靠 —— 用它做
        父子判定兜底。

    ★ B-3：新增可选参数 `body_nos` —— 与 `bodies` **平行**的源文件真实行号
      列表（`body_nos[i][j]` = `bodies[i][j]` 所在源文件的行号，1-based）。
      缺省 None ⇒ 节点不带行号（行号取 0），**既有调用方行为完全不变**
      （既有测试直接用纯字符串 body 建树）。
    """
    roots: list[SectionNode] = []
    stack: list[SectionNode] = []

    for idx, (head, body) in enumerate(zip(heads, bodies)):
        nos: list[int] = (list(body_nos[idx])
                          if body_nos is not None and idx < len(body_nos) else [])
        node = SectionNode(head=head, body_lines=list(body), body_line_nos=nos)
        # 找父：栈顶往回找 level 更小的节点
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            node.parent = stack[-1]
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _body_text_with_refs(node: SectionNode) -> tuple[str, list[tuple[int, str]]]:
    """本节正文 → (拼接文本, [(源文件行号, 行文本)])。

    ★ B-3：正文行与**源文件真实行号**一一绑定 ⇒ 章节窗口的文本可回溯到
      原文位置（约束候选的 `span_start`/`span_end` 定位依赖它）。
    ★ 拼接口径与历史实现**逐字节一致**（rstrip + 丢空行 + 换行连接），
      故窗口的 `text` 字段行为不变（既有测试与 norm 抽取不受影响）。
    """
    parts: list[str] = []
    refs: list[tuple[int, str]] = []
    nos = node.body_line_nos or []
    for i, raw in enumerate(node.body_lines):
        text = raw.rstrip()
        if not text.strip():
            continue
        parts.append(text)
        refs.append((nos[i] if i < len(nos) else 0, text))
    return "\n".join(parts), refs


def _merge_leaf_windows(roots: list[SectionNode],
                        budget: MergeBudget = MergeBudget()) -> list[dict]:
    """自底向上合并章节窗口（SpecGPT Algorithm 1 的思路）。

    从叶子往上走：把本节正文 + （受预算约束的）子节正文合并成一个窗口。
    预算作用：
      - max_depth：向上合并的层数上限，防止父节正文被每个子节携带
      - max_chars：窗口字符上限，超出截断
      - dedup：合并时去掉重复段落
      - cycle_guard：同一节点不重复进入（防引用环）

    输入是**顶层节点列表**（`_build_section_tree` 的返回值），
    输出窗口 dict 列表：{path, section_no, title, level, line, text, kind_hint}
    """
    windows: list[dict] = []

    def visit(node: SectionNode, seen: set) -> None:
        if budget.cycle_guard:
            if id(node) in seen:
                return
            seen = seen | {id(node)}

        # 本节正文
        # ⚠ **保留行结构与左侧缩进**（用 rstrip 而非 strip，且不把多行
        #   压成一行）：RFC 的「缩进定义条目」（SSH §5 的 byte/uint32 等
        #   数据类型）靠缩进层级识别，压成一行后就再也找不回来。
        own, own_refs = _body_text_with_refs(node)
        # 子节正文（受 max_depth 限制：只合并直接子节，必要时再看孙节）
        child_parts: list[tuple[str, list]] = []
        if budget.max_depth > 0:
            for child in node.children:
                ct, cr = _body_text_with_refs(child)
                if ct:
                    child_parts.append((ct, cr))

        parts: list[tuple[str, list]] = []
        if own:
            parts.append((own, own_refs))
        if budget.dedup:
            seen_texts = set()
            for ct, cr in child_parts:
                if ct in seen_texts:
                    continue
                seen_texts.add(ct)
                parts.append((ct, cr))
        else:
            parts.extend(child_parts)

        text = "\n\n".join(p[0] for p in parts)
        # ★ B-3：参与 text 的全部正文行引用（行号 + 行文本）。
        #   ⚠ text 被 max_chars 截断后与 merged_refs **不再逐行对齐**
        #     （refs 是截断前的完整视图）—— 需要逐行对齐时请用 body_refs
        #     并确保 max_chars 足够大。
        merged_refs = [ref for p in parts for ref in p[1]]
        if len(text) > budget.max_chars:
            text = text[:budget.max_chars].rstrip() + "..."

        path = _section_path(node)
        windows.append({
            "path": path,
            "section_no": node.number,
            # ★ 章节**号**链（与 `path`（标题链）并列）—— 给机器做 rule_id
            #   派生用；标题措辞会变、章节号稳定（见 `_section_number_path`）。
            "section_no_path": _section_number_path(node),
            "title": node.title,
            "level": node.level,
            "line": node.head.line,
            "text": text,
            "kind_hint": None,
            # ★ B-3：本节**自身**正文的行引用（不含子节）—— 约束候选按节
            #   抽取时用它做 span 定位（父节窗口不重复携带子节文本 ⇒
            #   候选不重复、章节归属精确）。
            "body_refs": own_refs,
            "merged_refs": merged_refs,
        })

        # 继续向下
        for child in node.children:
            visit(child, seen)

    for node in roots:
        visit(node, set())
    return windows


def _section_path(node: SectionNode) -> tuple[str, ...]:
    """节点的章节路径（如 ("10", "10.1") → ('10', 'OPTIONS')）。"""
    chain: list[SectionNode] = []
    cur: Optional[SectionNode] = node
    while cur is not None:
        chain.append(cur)
        cur = cur.parent
    chain.reverse()
    return tuple(c.title for c in chain)


def _section_number_path(node: SectionNode) -> tuple[str, ...]:
    """节点的**章节号**路径（如 ('10', '10.1')）。

    ★ 与 `_section_path`（**标题**链）**并列**的第二条路径，用途不同：
      - `_section_path`（标题链）⇒ **给人看 / 溯源展示**
        （`EvidenceAnchor.section_path`；标题措辞会随 RFC 修订变化）。
      - `_section_number_path`（章节号链）⇒ **给机器做 rule_id 派生**
        （`compute_rule_id` 的 `section_path` 入参）。
        §3.2 要求「措辞微调 ⇒ id 不变」—— 章节号比标题**稳定**：
        标题改一个字不该让 rule_id 漂移（否则规则无法跨构建对齐/增量更新）。

    ⚠ **空 number 的层会被跳过**：无编号的一级标题（number 为空串）若塞进
      链里会产出 `("21", "", "1.1")` 这种形态 ⇒ id 会依赖**层数**，
      且不同 RFC 的链形不可比。跳过 ⇒ 链里**每一层都是真实章节号**。

    ⚠ **层数一一对应不是契约**：因「跳过空 number 层」，号链的层数
      **可能少于**标题链的层数（某层标题无编号时）。设计对号链的唯一要求是
      「**能区分不同章节**」—— rule_id 只需这一点；「层数与标题链一一对应」
      是**展示层**的关切，且在当前三份 RFC 上恰好成立（数据事实，
      非代码保证）。层数对齐**不**应被写成契约，否则换一份带无编号一级
      标题的 RFC 就会假失败。
    """
    chain: list[SectionNode] = []
    cur: Optional[SectionNode] = node
    while cur is not None:
        chain.append(cur)
        cur = cur.parent
    chain.reverse()
    return tuple(c.number for c in chain if c.number)


def _section_kind(window: dict, cfg: dict) -> Optional[str]:
    """按 rfc_config 判定窗口类型（评审 T7：语义判定替代形态猜测）。

    查 cfg 的 method_sections / field_sections / status_sections，按**最长前缀**
    匹配（更具体的子节优先）。返回 "method" / "field" / "status" / None。

    注意：状态码标题（`21.1.1 100 Trying`）优先判为 status —— 标题本身以
    3 位数字开头是协议通用特征，比章节号更可靠。
    """
    number = window.get("section_no") or ""
    title = window.get("title") or ""

    # 状态码：标题形如「100 Trying」
    if re.match(r"^\d{3}\s", title):
        return "status"

    def _match(sections) -> Optional[str]:
        best = None
        for sec in sections or []:
            sec = str(sec)
            if number == sec or number.startswith(sec + "."):
                if best is None or len(sec) > len(best):
                    best = sec
        return best

    m = _match(cfg.get("method_sections"))
    if m is not None:
        return "method"
    f = _match(cfg.get("field_sections"))
    if f is not None:
        return "field"
    s = _match(cfg.get("status_sections"))
    if s is not None:
        return "status"
    return None


def _infer_kind_from_content(window: dict) -> Optional[str]:
    """内容启发式兜底（仅当 rfc_config 未覆盖该章节时使用）。

    ★ 评审 T7 的要求是「**语义判定替代形态猜测**」——所以本函数**不再**
      返回 "method"：方法的判定必须来自 rfc_config 的 `method_sections`
      （协议作者显式声明「这一章是方法」）。

    ⚠ 曾经的「标题全大写 → method」启发式被实测证伪并移除：
      - RTSP `3.2 RTSP URL`（二级标题、全大写）→ 被误抽成方法；
      - DNS `1. STATUS OF THIS MEMO` / `2. DOMAIN NAME SPACE AND RR
        DEFINITIONS`（一级标题、全大写）→ 被误抽成方法。
      两者都是**文档结构名**，不是协议方法。
      「全大写」只能说明标题写法，不能说明它是方法。

    现保留的判定（**仅**歧义极低者）：
      - 标题含括号且括号内是全大写缩写（`MAIL (MAIL)` / `EHLO (EHLO)`）
        → method：命令/方法的强特征，且带括号的**小写标题**几乎必然是
        「方法全称（缩写）」句式。

    ⚠ 曾有的「正文含 ABNF 语法块 → method」也被实测证伪并移除：
      RTSP `3.2 RTSP URL` 的正文含 `url = ...` 语法定义 → 被误抽成方法；
      FTP 的多个章节正文含语法示例 → 判定大面积漂移（method 32 → 6）。
      **正文里出现语法块是常态，不是方法特征。**
    """
    title = (window.get("title") or "").strip()
    # 带括号的命令（括号内是全大写缩写）—— 强特征
    m = _RE_HAS_PAREN.search(title)
    if m:
        inner = m.group(0)[1:-1].strip()
        if inner and _RE_METHOD_NAME.match(inner):
            return "method"
    return None



def _load_rfc_config(protocol: str) -> dict:
    """加载 rfc 源的协议专属配置，返回统一结构的 cfg 字典。

    配置来源（优先级从高到低）：
      ① **fused_hub/targets/<protocol>/rfc_config.json**（推荐路径，A0.2 新增）
         —— 协议专属的 rfc 抽取配置独立成文件，与 profile.json 分层，避免
         profile 段膨胀（方案文档风险点 R3）。结构：
           {
             "protocol": "sip",
             "method_sections": ["7.1", "9", ...],   # 方法所在章节号前缀
             "field_sections":  ["7.3", "19", "20"], # 字段所在章节号前缀
             "status_sections": ["7.2", "21"],       # 状态码表所在章节号前缀
             "method_excludes": [],                 # 需排除的全大写词
             "numeric_bounds": [],                  # 该协议的数值边界
             "expected_response_classes": [...]     # 协议层期望响应类别词表
           }
      ② **profile.json 的 rfc 段**（旧路径，向后兼容）
           "rfc": {"method_excludes": [...], "numeric_bounds": [...]}

    缺失处理：①不存在且②也不存在时**显式警告**（不再静默返回空默认）——
    空配置会让调用方误以为「该协议没有协议差异」，从而静默产出错误 fact。
    警告走 stderr，不污染 stdout 的数据管道。

    职责边界：章节号（method/field/status_sections）属协议特定知识，必须由
    配置文件显式声明；通用层零内置任何协议的章节号。
    """
    cfg: dict = {
        "method_sections": [],
        "field_sections": [],
        "status_sections": [],
        "method_excludes": [],
        "numeric_bounds": [],
        "expected_response_classes": [],
    }

    # ① 优先读协议专属的 rfc_config.json
    rfc_cfg_path = paths.target_rfc_config(protocol)
    if rfc_cfg_path.exists():
        data = _read_json(rfc_cfg_path)
        if data is None:
            print(f"[警告] {protocol} 的 rfc_config.json 解析失败或不可读："
                  f"{rfc_cfg_path}；退回空配置（协议差异将无法识别）",
                  file=sys.stderr)
            return cfg
        for key in _RFC_CONFIG_LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                cfg[key] = [str(x) for x in value]
        # method_excludes 统一大写（与旧路径语义一致）
        cfg["method_excludes"] = [str(x).upper() for x in cfg["method_excludes"]]
        return cfg

    # ② 回落到 profile.json 的 rfc 段（向后兼容）
    prof = paths.target_profile(protocol)
    if not prof.exists():
        print(f"[警告] {protocol} 缺少 rfc 配置："
              f"既无 {rfc_cfg_path.name}，也无 {prof.name}；"
              f"使用空配置（协议差异将无法识别）",
              file=sys.stderr)
        return cfg
    data = _read_json(prof)
    if data is None:
        print(f"[警告] {protocol} 的 profile.json 解析失败或不可读：{prof}；"
              f"使用空配置", file=sys.stderr)
        return cfg
    rfc = data.get("rfc")
    if not isinstance(rfc, dict):
        print(f"[警告] {protocol} 的 profile.json 缺少 rfc 段，且无 "
              f"{rfc_cfg_path.name}；使用空配置（协议差异将无法识别）",
              file=sys.stderr)
        return cfg
    ex = rfc.get("method_excludes")
    if isinstance(ex, list):
        cfg["method_excludes"] = [str(x).upper() for x in ex]
    nb = rfc.get("numeric_bounds")
    if isinstance(nb, list):
        cfg["numeric_bounds"] = [str(x) for x in nb]
    return cfg


def _norm(kind: str, name: str, content: str, protocol: str,
          source: str, section: str) -> dict:
    """构造一条 rfc norm（字段对齐 norm.py 的映射器 + 溯源）。"""
    return {
        "norm_id": f"{protocol}.{kind}.{name.lower().replace(' ', '_')}",
        "kind": kind,
        "name": name,
        "content": content,
        "kb_source_type": "rfc",
        "source": f"file:{source}#{section}",
        "protocol": protocol,
    }


def _doc_content_lines(raw_lines: list[str]) -> list[tuple[int, str]]:
    """① 文档清洗 + ② TOC 识别与隔离 → 内容行列表 [(原始行号, 行文本)]。

    ★ **共享前置**（B-3）：约束候选抽取与 norm 抽取**必须走同一条清洗/TOC
      隔离路径** —— 两套路径必然出现「norm 侧已隔离、候选侧没隔离」的
      判据分裂，这正是 B-3 要修的 TOC 污染根因。

    ① 文档清洗（逐行，**保留原文行号**）：
       ⚠ 保留**左侧缩进**：RFC 的「缩进定义条目」（SSH §5 的 byte/uint32/
       boolean 等数据类型）靠缩进层级识别，strip 掉缩进就再也找不回来。
       只去掉行尾空白与纯空白行。
       ★ 每行携带 (原始行号, 行文本)：行号一路带到 `norm["source"]` 的
         `@N` 定位器（P1-3）—— 清洗会丢行，必须在这里就把行号钉住。

    ② TOC 识别与隔离（★ 必须在章节树之前）：
       TOC 行**不参与章节树构建**（A0.3：TOC 不是有效规范证据，进
       all_claims 会污染知识库）。
       ★ **目录块兜底**（P0-1 第 2 项）：先在**清洗后的全文**上定位目录块
         区间（锚点 `Table of Contents` → 下一个零缩进一级章节标题），
         再把落在目录块里、**形似章节标题**、但**没有点线引导**的行判为 TOC。
         这类行是**折行目录条目**（点线在折行的第二行），只靠点线判据会漏判，
         会被当成真章节标题进树。
       ⚠ 顺序依赖：目录块兜底**必须先于**「首个标题前内容丢弃」执行 ——
         目录块本身位于首标题之前，若先丢弃就再也定位不到目录块。
         故这里在 doc_lines 上算区间，丢弃动作留到步骤 ③。
    """
    doc_lines: list[tuple[int, str]] = []
    for lineno, ln in enumerate(raw_lines, start=1):
        s = ln.rstrip()
        if not s.strip():
            continue
        if _RE_PAGE_MARK.search(s):
            continue
        if _RE_RFC_TITLE.match(s.strip()):
            continue
        if _RE_EMPTY_OR_DOTS.match(s.strip()):
            continue
        if re.fullmatch(r"[A-Za-z]+,\s*et\.?\s*al\.?", s.strip()):
            continue
        doc_lines.append((lineno, s))

    toc_blocks = _toc_block_ranges([text for _, text in doc_lines])
    content_lines: list[tuple[int, str]] = []
    for idx, (lineno, s) in enumerate(doc_lines):
        if _is_toc_line(s):
            continue
        if (_in_toc_block(idx, toc_blocks)
                and not _has_dot_leader(s)
                and _parse_heading_shape(s.strip()) is not None):
            # 目录块内的折行目录条目（无点线，但形似章节标题）
            continue
        content_lines.append((lineno, s))
    return content_lines


def _split_heads_bodies(
        content_lines: list[tuple[int, str]]
) -> tuple[list[SectionHead], list[list[str]], list[list[int]]]:
    """③ 标题识别（宽松形态）+ body 切分。

    ★ body 与 head 的对应关系：`bodies[i]` 必须是 `heads[i]` **之后**到
      下一个标题**之前**的内容。
    ⚠ 曾经的 off-by-one 实现（遇到标题就 append 当前累积的 cur_body）
      把**标题之前**的内容挂给了该标题 —— 导致 SSH §5「Data Type
      Representations」拿到的是 §4.5 的正文，而 §5 真正的数据类型条目
      （byte/boolean/uint32…）被挂到了 §6 名下 → SSH 字段全部丢失。

    ★ P1-2（2026-11-01）：**首个标题之前**的内容（RFC 抬头、摘要、目录）
      **不进入任何章节窗口**。此前它被并入第一节的 body（off-by-one 的
      残留），使第一节的语义摘要变成「Network Working Group J. Klensin…」
      这类抬头文字。
      实现：遇到**第一个**标题时把累积的 cur_body 丢弃（而非挂给它）。
      （此时目录块兜底已在步骤 ② 完成，不会因此丢掉目录识别能力。）

    ★ B-3：新增第三个返回值 `body_nos` —— 与 `bodies` 平行的**源文件真实
      行号**列表，供章节窗口做 span 定位。

    Returns:
        (heads, bodies, body_nos) —— 三者逐下标一一对应。
    """
    heads: list[SectionHead] = []
    bodies: list[list[str]] = []
    body_nos: list[list[int]] = []
    cur_body: list[str] = []
    cur_nos: list[int] = []
    pending_head: Optional[SectionHead] = None
    for lineno, s in content_lines:
        head = _parse_heading(s.strip(), line_no=lineno)
        if head is not None:
            if pending_head is None:
                # ★ 首个标题之前的内容 → 丢弃（不进任何章节）
                cur_body = []
                cur_nos = []
            else:
                # 结算**上一个**标题的 body（它到本标题之间的内容）
                bodies.append(cur_body)
                body_nos.append(cur_nos)
                cur_body = []
                cur_nos = []
            pending_head = head
            heads.append(head)
        else:
            cur_body.append(s)
            cur_nos.append(lineno)
    # 结算最后一个标题的 body
    if pending_head is not None:
        bodies.append(cur_body)
        body_nos.append(cur_nos)
    return heads, bodies, body_nos


def _extract_rfc_file(rfc_path: Path, protocol: str,
                      cfg: dict) -> list[dict]:
    """从单个 RFC 文件抽取 method/field/outcome norm（协议无关）。

    ★ A1 重写后的执行顺序（评审 T7 + 改进v2 问题①，**顺序不可调换**）：

        文档清洗 → TOC 识别与隔离 → 标题识别 → 章节树 → 块解析 → 类型判定

      ① **清洗**：去页眉页脚/纯分隔线（`_clean_body` 语义，逐行版）
      ② **TOC 识别与隔离**：TOC 行**在章节树之前**剥离。
         ⚠ 原实现把 TOC 判定放在章节树之后 → TOC 行已进入树结构，
           事后过滤单个窗口无法恢复正确的树；且 TOC 的目录文字
           （`21.1.1 100 Trying .....183`）会被当成状态码标题，
           导致同一状态码被抽两次（实测 SIP 68 个 fact_id 冲突，
           50 个 outcome 来自 TOC 行 —— **知识污染，不只是 ID 冲突**）。
         ★ P0-1（2026-11-01）：点线判据扩展到**间隔点线**（`. . . .`）+ 行尾
           页码，并新增**目录块兜底**（`_toc_block_ranges`）兜住折行条目。
      ③ **标题识别**：宽松多词标题（`_parse_heading`），不再只认单词
      ④ **章节树**：按层级建树（`_build_section_tree`）
      ⑤ **块解析**：自底向上合并成窗口（`_merge_leaf_windows`，有预算）
      ⑥ **类型判定**：查 rfc_config 的 *_sections（`_section_kind`），
         内容启发式仅作兜底 —— **语义判定替代形态猜测**（评审 T7）

    ★ **行号语义（P1-3，2026-11-01）**：`content_lines` 携带的是**清洗前的
      原始行号**（1-based）⇒ `SectionHead.line` → 窗口 `"line"` →
      `norm["source"]` 的 `@N` 定位器**可在 RFC 原文里定位到该标题**。
      （此前存的是「标题在 heads 列表中的序号」，溯源链断裂。）

    类型判定后的名字归一：
      - method：全大写词组（`OPTIONS`）或带括号命令（`MAIL (MAIL)`）
      - field ：PascalCase 单词（`Content-Length`）
      - status：3 位数字（`100`）
    """
    raw_lines = rfc_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    method_excludes = {str(x).upper() for x in cfg.get("method_excludes", [])}
    src_name = rfc_path.name
    budget = MergeBudget()

    # ---- ①②③ 文档清洗 → TOC 隔离 → 标题识别 ----
    #    ★ 已抽成**共享**的模块级函数 `_doc_content_lines` / `_split_heads_bodies`
    #      （B-3）：约束候选抽取必须走**同一条**清洗/TOC 隔离路径 ——
    #      两套路径必然出现「norm 侧已隔离、候选侧没隔离」的判据分裂，
    #      那正是 B-3 要修的 TOC 污染根因。
    #    详细口径（页眉页脚清理 / 目录块兜底 / 首标题前内容丢弃 / off-by-one
    #    修复）见这两个函数的 docstring。
    content_lines = _doc_content_lines(raw_lines)
    heads, bodies, body_nos = _split_heads_bodies(content_lines)

    if not heads:
        return []

    # ---- ④ 章节树 ----
    tree = _build_section_tree(heads, bodies, body_nos)

    # ---- ⑤ 块解析（自底向上合并，有预算）----
    windows = _merge_leaf_windows(tree, budget)

    # ---- ⑥ 类型判定（语义判定 + 内容启发式兜底）----
    norms: list[dict] = []
    seen_ids: set[str] = set()
    # 已抽取的方法名（大写）—— field 抽取时排除，避免命令名重复当 field
    # （实测 SMTP 的 MAIL/RCPT/DATA 等既抽成 method 又抽成 field）。
    method_names: set[str] = set()

    def _add_field(name: str, sem_text: str, line_no: int) -> None:
        """加入一条 field norm（同文件内按 norm_id 去重）。"""
        if not name or name.upper() in _GENERIC_SECTION_WORDS:
            return
        # ★ 排除英语停用词（become/not/or 等正文虚词被缩进条目识别误抽）。
        #   ⚠ 只对**全小写**单词生效：From/To/Via 等大写开头的协议字段名
        #   （PascalCase 形态）**不得**被停用词过滤 —— 停用词是「全小写
        #   数据类型形态」才可能混入的正文虚词。
        if name == name.lower() and name in _FIELD_STOPWORDS:
            return
        # ★ 排除已抽取的方法名（命令名重复当 field）
        if name.upper() in method_names:
            return
        content = f"{name} | required: {sem_text}" if sem_text else name
        n = _norm("field", name, content, protocol, src_name, f"@{line_no}")
        if n["norm_id"] in seen_ids:
            return
        seen_ids.add(n["norm_id"])
        norms.append(n)

    # ---- 通道 A0：ABNF 方法枚举（SIP 的 `Method = INVITEm / ACKm / ...`）----
    #   SIP RFC 3261 的方法不是章节标题、也不是「全称（缩写）」条目，
    #   而是 §25 ABNF 里的 hex 伴生规则（`INVITEm = %x49... ; INVITE in caps`）。
    #   对整个正文做预扫描（不受窗口预算/章节归属限制），hex 反解 + 注释 +
    #   规则名三者交叉验证一致才采信（协议无关）。
    for _m in _extract_abnf_methods("\n".join(text for _, text in content_lines)):
        method_names.add(_m.upper())
        _mn = _norm("method", _m, _m, protocol, src_name, "@abnf")
        if _mn["norm_id"] not in seen_ids:
            seen_ids.add(_mn["norm_id"])
            norms.append(_mn)

    for w in windows:
        kind = _section_kind(w, cfg)
        if kind is None:
            kind = _infer_kind_from_content(w)

        title = (w.get("title") or "").strip()
        text = w.get("text") or ""
        sem = _first_sentence(text)
        line_no = w.get("line", 0)

        # ---- 通道 A：缩进命令条目（A1.5，FTP/SMTP 的命令是这种形态）----
        #   RFC 里命令常以「全称（缩写）」独占一行 + 深缩进正文排版：
        #     `USER NAME (USER)` / `RETRIEVE (RETR)` / `MAIL (MAIL)`
        #   它们**没有章节标题**（只是 §4.1 下的缩进条目），
        #   只从标题取会一个都抽不到（实测 FTP 命令 32 → 6）。
        for entry_name, entry_body in _extract_command_entries(text):
            cmd = _normalize_command_name(entry_name)
            if not cmd:
                continue
            if cmd.upper() in _GENERIC_SECTION_WORDS:
                continue
            if cmd.upper() in method_excludes:
                continue
            ccontent = _first_sentence(entry_body) or cmd
            cnorm = _norm("method", cmd, ccontent, protocol, src_name,
                          f"@{line_no}")
            if cnorm["norm_id"] in seen_ids:
                continue
            seen_ids.add(cnorm["norm_id"])
            method_names.add(cmd.upper())
            norms.append(cnorm)

        # ---- 通道 B：缩进字段/数据类型条目（协议无关，与窗口 kind 无关）----
        #   RFC 的「字段 / 数据类型」常以缩进条目排版，**没有章节标题**：
        #     - SSH RFC4251 §6：`   byte` / `   boolean` / `   uint32` …
        #     - TLS §3 的向量/编号定义
        #   只从章节标题取会全部漏掉（实测 SSH 字段归零）。
        for entry_name, entry_body in _extract_indented_entries(text):
            # ★ 命令形态的条目走通道 A（method），这里跳过，避免
            #   `PASSWORD (PASS)` 的全称被当成字段 `PASSWORD`（重复 + 伪字段）
            if re.search(r"\([A-Z]{2,6}\)\s*$", entry_name.strip()):
                continue
            fname = _normalize_field_name(entry_name)
            if fname:
                _add_field(fname, _first_sentence(entry_body), line_no)

        if kind is None:
            continue

        if kind == "status":
            # 状态码：标题形如「100 Trying」
            m = re.match(r"^(\d{3})\s+(.+?)$", title)
            if not m:
                continue
            code, reason = m.group(1), m.group(2).strip()
            content = f"{reason} | when: {sem}" if sem else reason
            norm = _norm("outcome", code, content, protocol, src_name,
                         f"@{line_no}")
        elif kind == "method":
            name = _normalize_method_name(title)
            if not name:
                continue
            if name.upper() in _GENERIC_SECTION_WORDS:
                continue
            if name.upper() in method_excludes:
                continue
            norm = _norm("method", name, sem or name, protocol, src_name,
                         f"@{line_no}")
            method_names.add(name.upper())
        else:  # field：标题本身就是字段名（如 `12.1 Accept`）
            name = _normalize_field_name(title)
            if not name:
                continue
            if name.upper() in _GENERIC_SECTION_WORDS:
                continue
            if name == name.lower() and name in _FIELD_STOPWORDS:
                continue
            if name.upper() in method_names:
                continue
            content = f"{name} | required: {sem}" if sem else name
            norm = _norm("field", name, content, protocol, src_name,
                         f"@{line_no}")

        # 同一文件内去重（同一 norm_id 只保留首个 = 正文首个出现）
        if norm["norm_id"] in seen_ids:
            continue
        seen_ids.add(norm["norm_id"])
        norms.append(norm)

    return norms


def _normalize_method_name(title: str) -> str:
    """把方法标题归一为方法名。

    - `OPTIONS` → `OPTIONS`
    - `MAIL (MAIL)` → `MAIL`（取括号前的命令名）
    - `Extended HELLO (EHLO)` → `EHLO`（有括号时优先取括号内的缩写）
    - `DATA REPRESENTATION` → `DATA REPRESENTATION`（全大写词组保留）
    - `The OPTIONS method` → `OPTIONS`（去掉冠词与尾随 "method"）
    """
    t = (title or "").strip()
    if not t:
        return ""
    # 带括号：优先取括号内的缩写（EHLO / MAIL）
    m = _RE_HAS_PAREN.search(t)
    if m:
        inner = m.group(0)[1:-1].strip()
        if inner and _RE_METHOD_NAME.match(inner):
            return inner
        t = t[:m.start()].strip()
    # 去掉尾随的 "method"/"command"/"Message" 等描述性后缀
    t = re.sub(r"\s+(method|command|message|request|response)$", "", t,
               flags=re.IGNORECASE).strip()
    # 去掉开头冠词
    t = re.sub(r"^(The|A|An)\s+", "", t).strip()
    if not t:
        return ""
    # 全大写词组（含空格）合法；混合大小写单词非法（如 "Basic Structure"）
    if _RE_UPPER_PHRASE.match(t):
        return t
    if _RE_METHOD_NAME.match(t):
        return t
    return ""


def _normalize_command_name(entry: str) -> str:
    """把命令条目归一为方法名（A1.5）。

    RFC 里命令的经典写法是「全称（缩写）」：
        `PASSWORD (PASS)`  → `PASS`
        `RETRIEVE (RETR)`  → `RETR`
        `USER (USER)`      → `USER`
        `MAIL (MAIL)`      → `MAIL`
    缩写才是**线上实际传输的命令字**（全称只是说明文字）。
    若括号内不是全大写缩写（如 `APPEND (with create) (APPE)`），
    取**最后一个**括号里的全大写缩写。

    无括号形态（如 `ABOR`）直接返回（需全大写才算命令）。
    """
    t = (entry or "").strip()
    if not t:
        return ""
    abbrevs = re.findall(r"\(([^)]*)\)", t)
    for ab in reversed(abbrevs):
        ab = ab.strip()
        if ab and _RE_METHOD_NAME.match(ab):
            return ab
    # 无括号：整行就是命令名（必须全大写）
    head = t.split("(")[0].strip()
    if head and _RE_METHOD_NAME.match(head):
        return head
    return ""


def _normalize_field_name(title: str) -> str:
    """把字段标题归一为字段名。

    接受两类形态：
      ① **PascalCase / 大写开头**（协议头部字段）：
         `Content-Length` / `Accept-Encoding` / `CSeq`
      ② **全小写单词或带连字符**（数据类型 / 数据结构条目）：
         `byte` / `boolean` / `uint32` / `string` / `mpint` / `name-list`
         —— SSH RFC4251 §5 的数据类型就是这种形态（实测 SSH 的 8 个
         数据类型全是小写，若只认大写开头会全部丢失）。

    拒绝：多词普通短语（`Basic Structure`）、含空格的标题。
    """
    t = (title or "").strip()
    if not t:
        return ""
    m = _RE_HAS_PAREN.search(t)
    if m:
        t = t[:m.start()].strip()
    if not t or " " in t:
        return ""
    # ① 大写开头（协议头部字段形态）
    if _RE_FIELD_NAME.match(t):
        return t
    # ② 全小写单词/带连字符（数据类型形态）
    if re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", t):
        return t
    return ""


#: **缩进定义条目**：RFC 里字段/数据类型/命令定义的经典排版 —— 条目名独占一行
#: 且**有缩进**（相对正文首行缩进），下一行开始是其定义正文。
#: 例（SSH RFC4251 §5）：
#:       byte[n], where n is the number of bytes in the array.
#:       boolean
#:          A boolean value is stored as a single byte. ...
#:       uint32
#:          Represents a 32-bit unsigned integer. ...
#:
#: 这类条目**没有章节号**，只从章节标题取字段会漏掉它们（实测 SSH 8 个
#: 数据类型全部丢失）。识别规则：条目名独占一行、缩进 > 0、下一行缩进更深。
#:
#: ★ A1.5 扩展：同时支持**命令条目**形态「全称（缩写）」+ 深缩进正文：
#:       PASSWORD (PASS)
#:          The argument field is a Telnet string ...
#:       RETRIEVE (RETR)
#:          ...
#:   （FTP RFC959 §4.1 的 30+ 个命令全是这种形态。）
_RE_INDENTED_ENTRY = re.compile(
    r"^(\s{1,12})"
    r"([A-Za-z][A-Za-z0-9\-]*(?:\s*\([^)]*\))?(?:\[[^\]]*\])?)"
    r"\s*$")



def _extract_indented_entries(text: str) -> list[tuple[str, str]]:
    """从一段文本里抽取「缩进定义条目」→ [(条目名, 定义正文), ...]。

    判定规则（保守，避免把普通缩进段落误当条目）：
      ① 条目行本身有缩进（1~12 空格）且去掉缩进后是「单词 / 单词（缩写） / 单词[n]」形态；
      ② 条目名长度 ≤ 40（排除长句）；
      ③ 下一非空行存在且缩进**更深**（说明它是标题，其后是缩进正文）；
      ④ 条目正文取「直到下一个同级或更浅缩进行」的内容；
      ⑤ ★ **排除本身是章节标题的行**（A1.5 实测修正）：
         章节标题（如 FTP 的 `FTP COMMANDS` / `ACCESS CONTROL COMMANDS`）
         也是「缩进 + 单词行」形态，会被误当条目/命令 ——
         但它们是**分组名**（Commands 类别），不是具体命令。
         判定：`_parse_heading` 能识别的行 → 是标题 → 跳过。
    """
    if not text:
        return []
    raw = text.split("\n")
    entries: list[tuple[str, str]] = []
    i = 0
    while i < len(raw):
        m = _RE_INDENTED_ENTRY.match(raw[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        name = m.group(2)
        if len(name) > 40:
            i += 1
            continue
        # ⑤ 本身是章节标题 → 跳过（它是分组名，不是条目）
        if _parse_heading(raw[i].strip(), 0) is not None:
            i += 1
            continue
        # ③ 下一非空行必须缩进**更深**（说明它是条目名，其后是缩进正文）
        #    ⚠ 条目名与定义正文之间**可能隔着空行**（RFC 常见排版：
        #      `   byte` / `` / `      A byte represents ...`），
        #      故向下找时**跳过空行**，直到遇到首个非空行再判缩进。
        j = i + 1
        body_lines: list[str] = []
        while j < len(raw) and not raw[j].strip():
            j += 1
        if j < len(raw):
            nxt = raw[j]
            nxt_indent = len(nxt) - len(nxt.lstrip())
            if nxt.strip() and nxt_indent > indent:
                while j < len(raw):
                    ln = raw[j]
                    if not ln.strip():
                        j += 1
                        continue
                    ind = len(ln) - len(ln.lstrip())
                    if ind <= indent:
                        break
                    body_lines.append(ln.strip())
                    j += 1
        if body_lines:
            entries.append((name, " ".join(body_lines)))
        i = max(j, i + 1)
    return entries


#: **命令条目**（A1.5 独立识别器）：「全称（缩写）」独占一行 + 深缩进正文。
#: 例（FTP RFC959 §4.1）：
#:          USER NAME (USER)
#:             The argument field is a Telnet string ...
#:
#: ★ 为什么要独立于 `_extract_indented_entries`：
#:   字段/数据类型条目要求「单词名 + 严格更深缩进」，而命令条目的名字
#:   含空格与括号（`USER NAME (USER)`），两者形态不同、边界规则也不同。
#:   混用会导致命令条目正文被吞进相邻条目（实测 FTP 命令 13 → 10）。
#:   命令条目的判据更严格：**括号内必须是全大写缩写**（2~6 字母）。
_RE_COMMAND_ENTRY = re.compile(
    r"^(\s{1,12})([A-Z][A-Z0-9]*(?:\s+[A-Z][A-Z0-9]*)*\s*\([A-Z]{2,6}\))\s*$")


def _extract_command_entries(text: str) -> list[tuple[str, str]]:
    """从一段文本里抽取「命令条目」→ [(条目名, 定义正文), ...]（A1.5）。

    判定规则：
      ① 条目行形如 `全称 (ABBR)`（括号内 2~6 位全大写字母）；
      ② 下一非空行的缩进**严格更深**（其后的正文属于本命令）；
      ③ 条目名本身不是章节标题（分组名如 `FTP COMMANDS` 不会被误当命令）。

    返回的条目名保留原始形态（`USER NAME (USER)`），由
    `_normalize_command_name` 归一为命令缩写（`USER`）。
    """
    if not text:
        return []
    raw = text.split("\n")
    entries: list[tuple[str, str]] = []
    i = 0
    while i < len(raw):
        m = _RE_COMMAND_ENTRY.match(raw[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        name = m.group(2)
        # ③ 本身是章节标题 → 跳过
        if _parse_heading(raw[i].strip(), 0) is not None:
            i += 1
            continue
        j = i + 1
        body_lines: list[str] = []
        while j < len(raw) and not raw[j].strip():
            j += 1
        if j < len(raw):
            nxt = raw[j]
            nxt_indent = len(nxt) - len(nxt.lstrip())
            if nxt.strip() and nxt_indent > indent:
                while j < len(raw):
                    ln = raw[j]
                    if not ln.strip():
                        j += 1
                        continue
                    ind = len(ln) - len(ln.lstrip())
                    if ind <= indent:
                        break
                    body_lines.append(ln.strip())
                    j += 1
        if body_lines:
            entries.append((name, " ".join(body_lines)))
        i = max(j, i + 1)
    return entries


#: **ABNF 方法 hex 伴生规则**（RFC 3261 §25 形态，协议无关）：
#:   `INVITEm  =  %x49.4E.56.49.54.45 ; INVITE in caps`
#: 规则名带 `m` 后缀（ABNF 终结符标记），值为十六进制 ASCII 码，注释
#: 「NAME in caps」直接给出方法名。三处来源（规则名剥 m / hex 反解 /
#: 注释名）交叉验证一致才采信，避免误抽 `extension-method` / `token`。
_RE_ABNF_HEX_METHOD = re.compile(
    r"^\s*([A-Z][A-Z0-9]*)m\s*=\s*%x([0-9A-Fa-f]+(?:\.[0-9A-Fa-f]+)*)"
    r"\s*;\s*([A-Z][A-Z0-9]*)\s+in\s+caps\s*$",
    re.MULTILINE)


def _extract_abnf_methods(text: str) -> list[str]:
    """从 ABNF 正文抽取「方法名」（hex 伴生规则交叉验证）。

    SIP RFC 3261 的方法不是章节标题，而是 ABNF 里的 hex 伴生规则：
        INVITEm   =  %x49.4E.56.49.54.45 ; INVITE in caps
        ACKm      =  %x41.43.4B ; ACK in caps
        ...
    三个独立来源必须**全部一致**才采信：
      ① 规则名剥 `m` 后缀（`INVITEm` → `INVITE`）；
      ② hex 值反解 ASCII（`49.4E.56.49.54.45` → `INVITE`）；
      ③ 注释名（`; INVITE in caps` → `INVITE`）。
    这样 `extension-method` / `token` 这类规则名（无 hex 伴生、非全大写）
    天然被排除。协议无关：任何 RFC 用这种 ABNF 形态定义命令都会被识别。
    """
    methods: list[str] = []
    for m in _RE_ABNF_HEX_METHOD.finditer(text):
        rule = m.group(1)      # 规则名剥 m（INVITE）
        hexval = m.group(2)    # 49.4E.56...
        comment = m.group(3)   # 注释名（INVITE）
        try:
            ascii_name = "".join(chr(int(h, 16)) for h in hexval.split("."))
        except ValueError:
            continue
        # 三者一致 + 全大写方法名形态
        if rule == comment == ascii_name and _RE_METHOD_NAME.match(rule):
            methods.append(rule)
    return methods


#: 英语**虚词/停用词**（正文普通句子里的短单词）。这些词会以「缩进 +
#: 单词 + 下一行更深缩进」的形态偶发命中缩进条目识别，被误当成 field
#: （实测 SIP 抽出 `become` / `not` / `or`）。协议数据类型（byte/boolean/
#: uint32/string…）不在表内，不受影响。
_FIELD_STOPWORDS = {
    "a", "an", "the", "and", "or", "not", "be", "is", "are", "was", "were",
    "been", "has", "have", "had", "do", "does", "did", "will", "would",
    "shall", "should", "may", "might", "can", "could", "must", "of", "to",
    "in", "on", "at", "by", "for", "with", "from", "as", "if", "then",
    "than", "that", "this", "these", "those", "it", "its", "become",
    "becomes", "becoming", "also", "only", "such", "each", "any", "all",
    "some", "no", "yes", "but", "so", "when", "where", "which", "who",
    "what", "how", "why", "into", "onto", "over", "under", "between",
    "through", "without", "within", "about", "against", "during", "before",
    "after", "above", "below", "up", "down", "out", "off", "via", "per",
}



def extract_rfc_norms(protocol: str) -> list[dict]:
    """遍历 kb/<protocol>/spec/*.txt，抽取全部 rfc norm（method/field/outcome）。

    多个 RFC 文件（如 SMTP 的 4 个 RFC、TLS 的 2 个 RFC）都会抽取。

    ★ A1.3 补充：**跨文件去重**。
      同一协议的多份 RFC 常有同名章节（如 TLS 的 RFC5246 与 RFC8446 都有
      §3.2 "Conventions"、§4 "Generic Cryptography"），去重若只做在文件内
      （`_extract_rfc_file` 的局部 seen_ids），跨文件同名会重复产出**同一
      fact_key** → 又一次 fact_id 冲突。
      故此处再做一层**协议级**去重：同 (kind, name) 只保留**首个出现**
      （按文件名排序，即按 RFC 编号升序 → 保留更早/更基础的规范版本）。
    """
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    cfg = _load_rfc_config(protocol)
    norms: list[dict] = []
    seen_protocol_level: set[str] = set()
    for f in sorted(spec_dir.glob("*.txt")):
        for norm in _extract_rfc_file(f, protocol, cfg):
            # ★ P2-3（2026-11-01）：去重键改为**按 norm_id 判定**，与 norm_id 的
            #   生成规则**同源**（大小写不敏感 + 空格转下划线）。
            #   改前的键 `(kind, name)` 大小写敏感 ⇒ 跨文件的 `Accept` / `accept`
            #   躲过去重，却产生**同一个 norm_id** ⇒ dup_norm_ids>0 ⇒
            #   **质量闸误阻断合法语料的构建**。
            #   语义澄清：`Accept` 与 `accept` 是**同一实体**（HTTP 头名大小写
            #   不敏感）⇒ 合并为一条、保留首个；而 `Content-Length` 与
            #   `content_length` 的 norm_id 不同（`content-length` vs
            #   `content_length`）⇒ **不会**被误合并。
            key = norm["norm_id"]
            if key in seen_protocol_level:
                continue
            seen_protocol_level.add(key)
            norms.append(norm)
    return norms


# ===========================================================================
# A0.4　rfc 源质量闸（构建质量闸 + 离线评测，**两类分开**）
# ===========================================================================

@dataclass
class QualityReport:
    """rfc 源质量报告。

    ★ A0.4 的关键设计（改进v2 问题③）：拆成**两类检查**，避免「新增协议
      没有人工标注真值集 → 永远构建失败」的死锁。

      ① **构建质量闸**（`blocking_issues` 非空 → 阻断构建）
         - schema 合法性、重复 fact_id、TOC 残留、结构完整性
         - **不依赖人工真值集**，纯确定性检查
      ② **离线评测**（`offline_metrics`）
         - P/R/F1、章节层级准确率、人工真值对比
         - **发布准入**用；缺真值集时**跳过**（不是失败）
    """
    protocol: str
    norm_count: int = 0
    fact_count: int = 0
    unique_fact_ids: int = 0
    dup_fact_ids: int = 0
    dup_norm_ids: int = 0
    toc_sourced_outcomes: int = 0
    toc_lines_removed: int = 0
    #: ★ 审查新增：标识文本**只出现在 TOC 行**的 norm 列表（非空 ⇒ TOC 隔离失效）。
    #: 对 outcome 有效；对 method/field 检出力 = 0（见 toc_sourced_by_line）。
    toc_only_norms: list = field(default_factory=list)
    #: ★ P0-2：按**溯源行**判定的目录来源 norm 列表（非空 ⇒ 有 norm 来自目录行）。
    #: 回查每个 norm 的 source 行号所在行是否被判为目录 —— 不依赖字符串匹配，
    #: 对 method / field / outcome **一律有效**。
    toc_sourced_by_line: list = field(default_factory=list)
    kinds: dict = field(default_factory=dict)
    blocking_issues: list = field(default_factory=list)      # 阻断构建
    offline_metrics: dict = field(default_factory=dict)      # 发布准入（可为空）
    warnings: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """是否通过构建质量闸。"""
        return not self.blocking_issues

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "norm_count": self.norm_count,
            "fact_count": self.fact_count,
            "unique_fact_ids": self.unique_fact_ids,
            "dup_fact_ids": self.dup_fact_ids,
            "dup_norm_ids": self.dup_norm_ids,
            "toc_sourced_outcomes": self.toc_sourced_outcomes,
            "toc_lines_removed": self.toc_lines_removed,
            "toc_only_norms": list(self.toc_only_norms),
            "toc_sourced_by_line": list(self.toc_sourced_by_line),
            "kinds": dict(self.kinds),
            "blocking_issues": list(self.blocking_issues),
            "offline_metrics": dict(self.offline_metrics),
            "warnings": list(self.warnings),
            "passed": self.passed,
        }


def rfc_quality_report(protocol: str, facts=None,
                       norms=None) -> QualityReport:
    """生成 rfc 源质量报告（A0.4）。

    参数：
      protocol: 协议名
      facts:    映射后的 Fact 列表（可选；不传则内部计算）
      norms:    norm 列表（可选；不传则内部重算）

    返回 QualityReport。调用方（build_hub）依据 `report.passed` 决定是否
    阻断构建；`report.offline_metrics` 仅用于发布准入。
    """
    from collections import Counter

    if norms is None:
        norms = extract_rfc_norms(protocol)
    if facts is None:
        from core.fused.norm import map_norm_to_facts
        facts = []
        for n in norms:
            facts.extend(map_norm_to_facts(n))

    rep = QualityReport(protocol=protocol, norm_count=len(norms),
                        fact_count=len(facts))

    # ---- 统计 ----
    rep.kinds = dict(Counter(n.get("kind") for n in norms))
    fact_ids = [f.fact_id for f in facts]
    fc = Counter(fact_ids)
    rep.unique_fact_ids = len(fc)
    rep.dup_fact_ids = sum(v - 1 for v in fc.values() if v > 1)
    nc = Counter(n.get("norm_id") for n in norms)
    rep.dup_norm_ids = sum(v - 1 for v in nc.values() if v > 1)

    # ---- ① 构建质量闸（阻断，不依赖真值集）----
    if rep.dup_fact_ids:
        rep.blocking_issues.append(
            f"重复 fact_id {rep.dup_fact_ids} 个（同一 fact_key 被抽多次）")
    if rep.dup_norm_ids:
        rep.blocking_issues.append(
            f"重复 norm_id {rep.dup_norm_ids} 个（同一 kind:name 多次出现）")
    if not norms:
        rep.blocking_issues.append("抽取结果为空（0 条 norm）")
    # TOC 污染：outcome 的 reason 文本若只出现在 TOC 行 → 知识污染
    toc_outcomes = _count_toc_sourced_outcomes(protocol, norms)
    rep.toc_sourced_outcomes = toc_outcomes
    if toc_outcomes:
        rep.blocking_issues.append(
            f"TOC 污染：{toc_outcomes} 个 outcome 的正文只出现在目录行")

    # ★ 审查新增（2026-11-01）：**有检出力的** TOC 隔离检查。
    #   背景：上面两个指标在「修正①/② 实施后」都**失去检出力**——
    #     · toc_sourced_outcomes：TOC 已被章节树前隔离 → outcome 的 reason
    #       必然也在正文出现 → 恒为 0；
    #     · dup_fact_ids/dup_norm_ids：TOC 行抽出的重复项被**去重机制掩盖**
    #       （实测 monkeypatch 令 _is_toc_line 恒 False，三协议 norms 数与
    #        dup_norm_id 全都不变）——这正是改进v2 问题②警告的
    #       「实现了重复 ID 为零，但没彻底消除知识污染」。
    #   本检查**不依赖去重**：对每个 norm 取其「关键标识文本」，要求它必须
    #   能在**非 TOC 行**里找到。TOC 隔离一旦失效即刻被检出。
    toc_only = _count_toc_only_norms(protocol, norms)
    rep.toc_only_norms = toc_only
    if toc_only:
        rep.blocking_issues.append(
            f"TOC 隔离失效：{len(toc_only)} 个 norm 的标识文本只出现在目录行"
            f"（示例：{toc_only[:3]}）")

    # ★ P0-2（2026-11-01）：**溯源行判据** —— 对 method/field 也有效的严格检查。
    #   上面的 `toc_only_norms` 对 outcome 有效、对 method/field 检出力 = 0
    #   （其标识文本 name 必然同时出现在正文）。本检查回查每个 norm 的
    #   **来源行**本身是否被判为目录行 —— 不依赖字符串匹配，三类 kind 一律有效。
    toc_by_line = _count_toc_sourced_by_line(protocol, norms)
    rep.toc_sourced_by_line = toc_by_line
    if toc_by_line:
        rep.blocking_issues.append(
            f"TOC 污染：{len(toc_by_line)} 个 norm 的**来源行**是目录行"
            f"（示例：{toc_by_line[:3]}）")

    # ---- ② 离线评测（发布准入；缺真值集则跳过，不是失败）----
    truth_path = paths.kb_root() / protocol.lower() / "rfc_truth.json"
    if truth_path.is_file():
        try:
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            rep.offline_metrics = _offline_metrics(norms, truth)
        except (json.JSONDecodeError, OSError) as exc:
            rep.warnings.append(f"真值集读取失败，离线评测跳过: {exc}")
    else:
        rep.warnings.append(
            "无人工真值集（kb/<协议>/rfc_truth.json），离线评测跳过"
            "（不影响构建）")

    return rep


def _count_toc_sourced_outcomes(protocol: str, norms: list[dict]) -> int:
    """统计「正文只出现在 TOC 行」的 outcome 数（TOC 污染检测）。

    口径：对每个 outcome，取其 reason 文本（content 中 `|` 之前的部分），
    回到该协议的 RFC 原文里找：
      - 只在 TOC 行出现 → 污染（+1）
      - 在正文出现 → 正常
    """
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return 0
    cache: list[str] = []
    for f in sorted(spec_dir.glob("*.txt")):
        cache.extend(f.read_text(encoding="utf-8", errors="ignore").splitlines())

    count = 0
    for n in norms:
        if n.get("kind") != "outcome":
            continue
        reason = (n.get("content", "") or "").split("|", 1)[0].strip()
        if not reason:
            continue
        found_toc = False
        found_body = False
        for ln in cache:
            if reason not in ln:
                continue
            if _is_toc_line(ln):
                found_toc = True
            else:
                found_body = True
            if found_toc and found_body:
                break
        if found_toc and not found_body:
            count += 1
    return count


def _independent_toc_lines(lines: list[str]) -> set[str]:
    """**独立**判定哪些行是 TOC 行（不复用 ``_is_toc_line``）。

    ★ 为什么必须独立（审查发现，2026-11-01）：
      质量闸若用 ``_is_toc_line`` 来划分 TOC/正文，就与被检查的抽取流程
      **共用同一个函数** —— 一旦该函数被破坏（正是本检查要检出的失效模式），
      划分也同时失效 → 检查变成自证、恒为 0（实测 monkeypatch 令
      ``_is_toc_line`` 恒 False 时，用它的版本检出 0 条）。

      本函数只用**形态特征**（RFC 目录的标准排版）独立判定：
        · 点线引导（`...` 连续 3 个以上）—— RFC 目录的标志性排版；
        · 「间隔点线 + 尾随页码」（`. . . .` 5）—— RFC 5321/5322 的目录排版；
        · 「章节号 + 标题 + 点线 + 页码」的目录行；
      三者都不依赖 ``_is_toc_line`` 的任何逻辑，故该函数坏掉时本判定仍有效。

      ⚠ P0-1 补充（2026-11-01）：原先只认**连续**点线 ⇒ 对 SMTP 的
        **间隔点线**目录**完全无检出力**（195 行目录全被判成正文）。
        现补上「间隔点线 + 行尾页码」这一形态（页码是目录行的必备特征，
        正文省略号不带页码 ⇒ 零误报）。
    """
    toc: set[str] = set()
    for ln in lines:
        if _RE_TOC_DOTS.search(ln):
            toc.add(ln)
            continue
        # 间隔点线 + 行尾页码（RFC 5321/5322 的目录排版）
        if (_RE_TOC_SPACED_DOTS.search(ln)
                and _RE_TOC_TRAIL_PAGE.search(ln.rstrip())):
            toc.add(ln)
            continue
        # 「N.N 标题 ... 183」型目录行（点线已被前一条覆盖，这里兜底
        # 「章节号 + 标题 + 尾随页码」形态）
        m = re.match(r"^\s*\d{1,2}(?:\.\d{1,2})*\s+\S.*\s(\d{1,4})\s*$", ln)
        if m and not ln.rstrip().endswith((".", ",", ";")):
            toc.add(ln)
    return toc


def _norm_source_line(norm: dict) -> Optional[tuple[str, int]]:
    """从 norm 的 ``source`` 解析出 ``(文件名, 原文行号)``；无行号 → None。

    ``source`` 形如 ``file:rfc3261.txt#@1683``（P1-3 后 ``@N`` 已是**原文真实
    行号**，1-based）。ABNF 通道用 ``#@abnf`` 之类的**非行号标记**（它来自
    全文预扫描、没有单一来源行）→ 返回 None。
    """
    src = str(norm.get("source") or "")
    if "#@" not in src:
        return None
    fname, _, sec = src.partition("#@")
    fname = fname.replace("file:", "").strip()
    sec = sec.strip()
    if not sec.isdigit():
        return None
    return fname, int(sec)


def _count_toc_sourced_by_line(protocol: str, norms: list[dict]) -> list[str]:
    """找出「**来源行本身**是 TOC 行」的 norm —— P0-2 的严格判据。

    ★ 为什么需要（QA 复核发现，2026-11-01）：
      :func:`_count_toc_only_norms` 用「标识文本只出现在目录行」作判据，对
      **outcome** 有效（其 reason 带点线污染痕迹），但对 **method/field**
      **检出力 = 0** —— 它们的标识文本是 name，而 name 必然同时出现在正文
      （即使该 fact 实际来自目录行），故永远不触发告警。

      本检查改用**溯源行判据**：每个 norm 的 ``source`` 现在带**原文真实行号**
      （P1-3 的成果）⇒ 直接回查**那一行**是否被判为目录行。
      这**不依赖字符串匹配**，对 method / field / outcome **一律有效**。

    Returns:
        泄漏的 norm 标识列表（空 = 隔离正常）。
    """
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    # 逐文件读入原文行（按行号索引）
    file_lines: dict[str, list[str]] = {}
    for f in sorted(spec_dir.glob("*.txt")):
        file_lines[f.name] = f.read_text(
            encoding="utf-8", errors="ignore").splitlines()

    leaked: list[str] = []
    for n in norms:
        parsed = _norm_source_line(n)
        if parsed is None:
            continue          # 无行号（如 ABNF 通道）→ 本判据不适用
        fname, lineno = parsed
        lines = file_lines.get(fname)
        if not lines or not (1 <= lineno <= len(lines)):
            continue
        raw = lines[lineno - 1]
        # ★ 用**独立**的形态判据判定该行是否为目录（不复用 _is_toc_line，
        #   否则与被检查对象自证 —— 见 _independent_toc_lines 的说明）。
        if _independent_toc_lines([raw]):
            leaked.append(f"{n.get('kind')}:{n.get('name')}@{fname}:{lineno}")
    return leaked


def _count_toc_only_norms(protocol: str, norms: list[dict]) -> list[str]:
    """找出「标识文本**只出现在 TOC 行**」的 norm —— TOC 隔离失效的直接证据。

    ★ 为什么需要这个检查（审查新增，2026-11-01）：
      `dup_fact_ids` / `toc_sourced_outcomes` 在「TOC 已被章节树前隔离」后
      **都失去检出力**（实测：monkeypatch 令 TOC 判定失效，三协议 norms 数与
      两个指标全都不变 —— 污染被去重机制掩盖）。这正是改进v2 问题②警告的
      「实现了重复 ID 为零，但没彻底消除知识污染」。

      实测失效场景：SIP 的 **50 个 outcome** 的 reason 全部被污染成
      「Trying ........  183」这类**目录文字**（点线 + 页码）—— 知识库被
      目录条目彻底顶替，而 dup 指标全绿。

      本检查**不依赖去重**，且用**独立的形态判据**划分 TOC/正文
      （见 :func:`_independent_toc_lines`）⇒ 抽取侧的 TOC 判定一旦失效，
      本检查即刻检出。

    ⚠ **覆盖范围**：对 **outcome** 有效；对 **method/field 检出力 = 0**
      （其标识文本 name 必然同时出现在正文）—— method/field 的目录污染由
      :func:`_count_toc_sourced_by_line`（溯源行判据）负责。

    Returns:
        泄漏的 norm 标识列表（空 = 隔离正常）。
    """
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    all_lines: list[str] = []
    for f in sorted(spec_dir.glob("*.txt")):
        all_lines.extend(f.read_text(encoding="utf-8", errors="ignore").splitlines())
    toc_text = _independent_toc_lines(all_lines)
    body_text = set(all_lines) - toc_text

    leaked: list[str] = []
    for n in norms:
        kind = n.get("kind")
        if kind == "outcome":
            ident = (n.get("content") or "").split("|", 1)[0].strip()
        else:
            ident = str(n.get("name") or "").strip()
        # 短标识（如 "OK"）在正文里偶然出现的概率高 → 不作为判据
        if not ident or len(ident) < 4:
            continue
        in_toc = any(ident in t for t in toc_text)
        in_body = any(ident in b for b in body_text)
        if in_toc and not in_body:
            leaked.append(f"{kind}:{ident}")
    return leaked


def _offline_metrics(norms: list[dict], truth: dict) -> dict:
    """离线评测：与人工真值集比对，算 P/R/F1（改进v2 问题③ 的发布准入部分）。

    truth 结构（人工标注）：
        {"methods": ["OPTIONS", ...], "fields": ["Accept", ...],
         "outcomes": ["100", ...]}
    """
    got = {
        "method": {n["name"] for n in norms if n.get("kind") == "method"},
        "field": {n["name"] for n in norms if n.get("kind") == "field"},
        "outcome": {n["name"] for n in norms if n.get("kind") == "outcome"},
    }
    out: dict = {}
    for kind, key in (("method", "methods"), ("field", "fields"),
                      ("outcome", "outcomes")):
        expected = {str(x) for x in (truth.get(key) or [])}
        actual = got[kind]
        if not expected:
            out[kind] = {"skipped": True, "reason": "真值集该类为空"}
            continue
        tp = len(expected & actual)
        precision = tp / len(actual) if actual else 0.0
        recall = tp / len(expected) if expected else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)
        out[kind] = {
            "expected": len(expected), "actual": len(actual), "tp": tp,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4),
            "missing": sorted(expected - actual),
            "extra": sorted(actual - expected),
        }
    return out


# ===========================================================================
# A0.5　幂等键与快照
# ===========================================================================

def compute_build_id(protocol: str, norms: list[dict], cfg: dict) -> str:
    """计算 rfc 源的 build_id（幂等键）。

    build_id = sha256(规范内容 + 配置内容 + 抽取器版本)[:16]

    - 规范内容：norms 的 canonical 序列化（内容变了 → id 变）
    - 配置内容：rfc_config + profile 的 relevant 段（配置变了 → id 变）
    - 抽取器版本：`_EXTRACTOR_VERSION`（代码改了 → id 变）

    用途：同输入两次 build 必须产出**同一 build_id**（字节一致的可验证前提）；
    不同输入/配置/版本必须产出不同 id（否则会误判为「已构建过」而跳过）。
    """
    import hashlib

    payload = {
        "protocol": protocol,
        "extractor_version": _EXTRACTOR_VERSION,
        "config": {k: cfg.get(k) for k in sorted(cfg)} if cfg else {},
        "norms": sorted(json.dumps(n, sort_keys=True, ensure_ascii=False)
                        for n in norms),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"))
    return "rb_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


#: 抽取器版本号 —— 任何影响抽取结果的改动都必须递增它
#: （否则 build_id 不变，会让「代码已改但产物未重建」的情况被误判为一致）。
#: ★ 2026-11-01 P1 批次：间隔点线 TOC 判据 + 目录块兜底（P0-1）、
#:   真实源文件行号（P1-3）、首标题前内容不入章节（P1-2）
#:   —— 三项均改变抽取结果 ⇒ 版本号必须变。
_EXTRACTOR_VERSION = "a1-p1-2026-11-01"


# ===========================================================================
# 语义约束抽取（借鉴 SemFuzz 的「构造约束 + 处理期望」）
# ===========================================================================

#: 通用约束措辞（RFC 2119 规范性动词 + 长度/范围边界措辞，协议无关）
_CONSTRAINT_RE = re.compile(
    r"(MUST\s+NOT|MUST|SHALL\s+NOT|SHALL|SHOULD\s+NOT|SHOULD|"
    r"length|octets?|bytes?|bits?|range|maximum|minimum|exceed|"
    r"greater than|less than|不得超过|不超过|不能超过|至少|范围)",
    re.IGNORECASE)

#: 通用网络长度/端口边界数值启发式（0-63 label 上限 / 1-255 域名总长 /
#: 65535 16 位长度上限）。这些是网络协议族常见边界值，非某协议专属；
#: 协议可通过 profile.json 的 rfc.numeric_bounds 覆盖/追加。
_DEFAULT_NUMERIC_BOUNDS = ("0-63", "1-255", "65535", "63", "255")

#: 约束句子长度范围（过滤太短/太长）
_MIN_SENT, _MAX_SENT = 15, 400


#: B-3：约束候选的**章节窗口预算**。
#:
#: - `max_depth=0`：**不合并子节** ⇒ 每个章节窗口只含**本节正文**
#:   ⇒ 候选不重复（父节窗口不再重复携带子节文本）、章节归属精确。
#: - `max_chars=200_000`：远大于任一章节正文长度 ⇒ **不截断**
#:   ⇒ 窗口覆盖率 100%（否则超长章节尾部句子会被静默丢弃）。
#: - `dedup` / `cycle_guard`：与 `_extract_rfc_file` 同款。
_CANDIDATE_WINDOW_BUDGET = MergeBudget(max_depth=0, max_chars=200_000,
                                        dedup=True, cycle_guard=True)

#: 句子切分分隔符（与历史实现「按句末标点后的空白串 / 换行串切分」同口径）。
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

#: RFC 抬头的「Request for Comments: NNNN」行 —— 规范版本号的权威来源。
_RE_RFC_NUMBER = re.compile(r"^\s*Request for Comments:\s*(\d+)", re.IGNORECASE)


def _line_offsets(raw_text: str) -> dict[int, int]:
    """行号（1-based）→ 该行首字符在整篇文本中的**绝对偏移**。

    ★ 与 `str.splitlines()` 的切分口径**完全一致**（都用 `splitlines`），
      故行号 ↔ 偏移的映射与 `_extract_rfc_file` 的行号语义严格对齐
      （P1-3 的真实行号语义）。

    ⚠⚠ **换页符陷阱（务必读）**：RFC 正文含**换页符 `\x0c`**（实测
      rtsp 92 / sip 269 / smtp 95 处），而 `str.splitlines()` 会把它
      （以及 `\v` `\x1c` `\x1d` `\x1e` `\x85` `\u2028` `\u2029`）
      **当作行边界**，而 `text.count("\n")` / `text.split("\n")` **不会**
      ⇒ 两种口径的行号相差**正好等于换页符处数**（实测 9~11 行）。
      ⇒ **下游若要用 `#@<行号>` 反查 span 落在第几行，必须用本函数口径
      （或 `splitlines`），不能用 `count("\n")`** —— 否则会 100% 对不上
      （实测 430/430 全不符）。
      本口径下的正确反查式：
      ``line_offsets[n] <= span_start < line_offsets[n + 1]``
      （实测对 430/430 候选全部成立）。
    """
    offsets: dict[int, int] = {}
    pos = 0
    for lineno, seg in enumerate(raw_text.splitlines(keepends=True), start=1):
        offsets[lineno] = pos
        pos += len(seg)
    return offsets


def _split_sentences_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """按句切分文本，返回每句的 (文本, 起偏移, 止偏移)（相对 `text`）。

    ★ 切分口径与历史实现（按句末标点后的空白串 / 换行串切分）**一致**
      （同一批分隔符、同样的先后顺序），差别只在**额外保留偏移**。
    ★ 切分后每句**不含换行** ⇒ 每句必然落在 `text` 的单行内 ⇒ 偏移可
      无歧义地映射回源文件（这是 span 能精确定位的前提）。
    """
    out: list[tuple[str, int, int]] = []
    pos = 0
    for m in _SENT_SPLIT_RE.finditer(text):
        seg = text[pos:m.start()]
        if seg.strip():
            out.append((seg, pos, m.start()))
        pos = m.end()
    seg = text[pos:]
    if seg.strip():
        out.append((seg, pos, len(text)))
    return out


def _spec_version_from_rfc(lines: list[str], file_name: str) -> str:
    """解析规范的版本标识（如 `RFC 2326`）。

    优先取抬头的 `Request for Comments: NNNN`；取不到时回落到**文件名**
    （`rfc2326.txt` → `RFC 2326`）。
    ★ 只用**确定性**来源 —— 同一份规范文件在任何机器上得到同一个版本串
      （规范版本是候选**稳定身份**的一部分，不能随环境变化）。
    """
    for ln in lines[:80]:
        m = _RE_RFC_NUMBER.match(ln)
        if m:
            return f"RFC {m.group(1)}"
    m = re.match(r"^rfc(\d+)", Path(file_name).stem, re.IGNORECASE)
    if m:
        return f"RFC {m.group(1)}"
    return Path(file_name).stem


def _constraint_candidates_from_file(f: Path, protocol: str,
                                     numeric_re, max_per_rfc: int) -> list[dict]:
    """从单个 RFC 文件产出约束候选（**经章节窗口**，B-3）。

    流程与 `_extract_rfc_file` **同一条主干**：
        文档清洗 → TOC 隔离 → 标题识别 → 章节树 → 窗口 → 逐窗口切句
    ⇒ 目录行在候选产生**之前**已被隔离（TOC 污染归零）。

    每个候选携带：
      - `span_start` / `span_end`：**源文件字符区间**，**半开区间**
        `[span_start, span_end)`（Python 切片语义 ⇒
        `raw[span_start:span_end] == text` **逐字相等**，可在原文核对）
      - `section_path`：**标题**链（**给人看 / 溯源**）、
        `section_no`：**单级**章节号、`section_no_path`：**章节号链**
        （**给机器做 rule_id 派生** —— 章节号比标题稳定，标题改一个字
        不应让 rule_id 漂移；见 `_section_number_path`）
      - `spec_version`：规范版本（如 `RFC 2326`）
      - `source`：`file:<name>#@<真实行号>`（**唯一** anchor 语义）
    """
    raw_text = f.read_text(encoding="utf-8", errors="ignore")
    raw_lines = raw_text.splitlines()
    content_lines = _doc_content_lines(raw_lines)
    heads, bodies, body_nos = _split_heads_bodies(content_lines)
    if not heads:
        return []
    tree = _build_section_tree(heads, bodies, body_nos)
    windows = _merge_leaf_windows(tree, _CANDIDATE_WINDOW_BUDGET)
    line_offsets = _line_offsets(raw_text)
    spec_version = _spec_version_from_rfc(raw_lines, f.name)

    out: list[dict] = []
    for w in windows:
        refs = w.get("body_refs") or []
        text = w.get("text") or ""
        if not refs or not text:
            continue
        # 窗口文本的行索引：(行内起偏移, 行长, 源文件行号)
        line_spans: list[tuple[int, int, int]] = []
        cursor = 0
        for lineno, line_text in refs:
            line_spans.append((cursor, len(line_text), lineno))
            cursor += len(line_text) + 1      # +1 = 行间换行符
        for sent, s_start, _s_end in _split_sentences_with_offsets(text):
            stripped = sent.strip()
            if not (_MIN_SENT <= len(stripped) <= _MAX_SENT):
                continue
            if not (_CONSTRAINT_RE.search(stripped) or numeric_re.search(stripped)):
                continue
            # 清理页眉页脚，且必须是「含字段/数值」的实质约束句
            clean = _clean_body([stripped])
            if not clean or len(clean) < _MIN_SENT:
                continue
            # 定位：句子首字符 → (源文件行号, 行内偏移)
            lead = len(sent) - len(sent.lstrip())
            pos = s_start + lead
            loc = None
            for start, length, lineno in line_spans:
                if start <= pos < start + length:
                    loc = (lineno, pos - start)
                    break
            if loc is None:
                continue
            lineno, offset_in_line = loc
            abs_start = line_offsets.get(lineno)
            if abs_start is None:
                continue
            abs_start += offset_in_line
            abs_end = abs_start + len(stripped)
            out.append({
                "text": stripped,
                "source": f"file:{f.name}#@{lineno}",
                "protocol": protocol,
                "span_start": abs_start,
                "span_end": abs_end,
                "section_path": list(w.get("path") or ()),
                "section_no": w.get("section_no") or "",
                "section_no_path": list(w.get("section_no_path") or ()),
                "spec_version": spec_version,
            })
            if len(out) >= max_per_rfc:
                return out
    return out


def extract_constraint_candidates(protocol: str, max_per_rfc: int = 80) -> list[dict]:
    """rule 抽取：从 RFC 文本中找含「规范性约束措辞」的句子，作约束候选。

    这是 SemFuzz 约束抽取的确定性前置（rule 打底）：只做粗筛（哪句话像约束），
    结构化（字段/约束/违反/响应）交给 LLM（infer_constraints）。零 LLM、可测。

    ★ B-3（2026-11-01）：改为**经章节窗口**产出（不再全文正则裸扫）：
      ① **不再绕过章节树** ⇒ 目录行在候选产生**之前**已被隔离
         （TOC 污染实测归零：rtsp 5 / sip 2 / smtp 1 → 0）；
      ② 每个候选带 `span_start`/`span_end`（**源文件字符区间**）、
         `section_path`（标题链）/ `section_no`（单级号）/
         `section_no_path`（**章节号链**）、`spec_version`（规范版本）
         ⇒ 改进v2 问题⑧「先验证证据再判显式」在数据上**物理可行**；
         ⇒ 章节**号**链供 rule_id 派生（标题链只给人看，见 ④）；
      ③ `source` 统一为 `file:<name>#@<真实行号>` —— **唯一** anchor 语义
         （此前全文裸扫产出的是**无行号**的 `file:<name>`）。
      ④ 章节归属**两条路径并存**：`section_path`（标题链，给人看/溯源）
         与 `section_no_path`（章节号链，给机器做 rule_id 派生）——
         章节号比标题稳定，标题措辞微调不应让 rule_id 漂移（§3.2）。
    """
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    # 数值边界来自 profile 的 rfc.numeric_bounds（可覆盖），默认通用边界启发式
    cfg = _load_rfc_config(protocol)
    numeric_bounds = cfg.get("numeric_bounds") or list(_DEFAULT_NUMERIC_BOUNDS)
    numeric_re = re.compile("|".join(re.escape(b) for b in numeric_bounds),
                            re.IGNORECASE)
    candidates: list[dict] = []
    for f in sorted(spec_dir.glob("*.txt")):
        candidates.extend(_constraint_candidates_from_file(
            f, protocol, numeric_re, max_per_rfc))
    return candidates


_PROMPT_CONSTRAINT = """你是 {protocol} 协议规范分析专家。下面是从 RFC 文档摘出的规范性约束句子。
请从中提取「字段语义约束」，并结构化输出。

对每条约束提取：
- field：受约束的字段名（如 QNAME、RDLENGTH、Transport）
- constraint：约束内容（该字段应满足的合法要求，如「单 label ≤ 63 字节」）
- violation：违反该约束的方式（非法输入，如「label 长度字段 > 实际内容」）
- expected_code：违反后接收方应返回的响应码/错误码（根据你对 {protocol} 协议的理解推断，推断不到留空字符串）
- expected_behavior：违反后接收方应有的行为（如「返回 FORMERR 错误」），推断不到留空字符串

约束句子：
<<<
{text}
>>>

只输出 JSON（不要解释），格式：
{{"constraints": [{{"field": "...", "constraint": "...", "violation": "...",
                    "expected_code": "...", "expected_behavior": "..."}}]}}"""


def infer_constraints(protocol: str, llm=None, max_candidates: int = 40,
                      batch_size: int = 8) -> list[dict]:
    """LLM 结构化约束：把 rule 候选段落喂 LLM，输出 (field/constraint/violation/
    expected_code/expected_behavior) 三元组（对齐 SemFuzz 的 C/P 配对）。

    llm 缺省用 DeepSeekClient；测试可传 StubLLMClient。分批喂避免逐条调用。
    """
    if llm is None:
        from core.llm import DeepSeekClient
        llm = DeepSeekClient()
    candidates = extract_constraint_candidates(protocol)[:max_candidates]
    if not candidates:
        return []
    out: list[dict] = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        text = "\n\n".join(f"[{j}] {c['text']}" for j, c in enumerate(batch))
        try:
            r = llm.chat_json(
                system="你输出 JSON。",
                user=_PROMPT_CONSTRAINT.format(protocol=protocol.upper(), text=text),
                temperature=0.2, max_tokens=3000)
        except Exception:
            continue
        if not isinstance(r, dict):
            continue
        for c in (r.get("constraints") or []):
            if not isinstance(c, dict):
                continue
            field = (c.get("field") or "").strip()
            constraint = (c.get("constraint") or "").strip()
            if not field or not constraint:
                continue
            out.append({
                "field": field,
                "constraint": constraint,
                "violation": (c.get("violation") or "").strip(),
                "expected_code": (c.get("expected_code") or "").strip(),
                "expected_behavior": (c.get("expected_behavior") or "").strip(),
                "source": batch[0]["source"],
                "protocol": protocol,
                # ★ B-3：候选的 span / 章节归属 / 规范版本随约束一起下沉。
                #   ⚠ 归属到**批次首条**候选：LLM 契约未变（LLM 不指明句子
                #     来源），故与 `source` 保持同源。B-2 若要精确到句，
                #     需扩展 LLM 契约返回句子下标。
                "span_start": batch[0].get("span_start"),
                "span_end": batch[0].get("span_end"),
                "section_path": list(batch[0].get("section_path") or []),
                "section_no": batch[0].get("section_no") or "",
                # ★ 章节号链（给 rule_id 派生用；与标题链 `section_path` 并列）
                "section_no_path": list(batch[0].get("section_no_path") or []),
                "spec_version": batch[0].get("spec_version") or "",
            })
    return out


def _constraint_norm_id(protocol: str, field: str, constraint: str,
                        violation: str, code: str) -> str:
    """约束 norm_id = `{protocol}.constraint.{field_slug}.{身份摘要}`。

    ★ B-4：历史实现**只用 field 做键** ⇒ **同字段的多条约束撞同一个
      norm_id** ⇒ `dup_norm_ids > 0` ⇒ 质量闸把 `--constraints` 构建
      **阻断**（实测撞 id 条数：rtsp 3 / sip 9 / smtp 7）。

    身份摘要 = `field + constraint + violation + code` 四个**结构化字段**的
    sha256 前 10 位（归一化后，见 `norm.constraint_identity_digest`）：
      - **不用 Python 的 `hash()`**：str 的 hash 按进程随机化
        （PYTHONHASHSEED）⇒ 同一约束在不同进程/机器上得到不同 id
        ⇒ 幂等键失效、build_id 漂移 ⇒ 必须用 hashlib。
      - **不用 LLM 自由措辞做判别位**（`expected_behavior` 是自由文本）：
        同一语义不同措辞会产生不同 id ⇒ 同一约束被当成多条重复入库。
    """
    digest = constraint_identity_digest(field, constraint, violation, code)
    slug = str(field or "").lower().replace(" ", "_") or "field"
    return f"{protocol}.constraint.{slug}.{digest}"


def extract_constraint_norms(protocol: str, llm=None,
                             max_candidates: int = 40) -> list[dict]:
    """约束 → norm（供 norm.py 的 constraint_norm_to_facts 映射）。

    content 用「field=... constraint=... violation=... code=... behavior=...」
    的 key=value 格式，对齐 norm.py 的约束解析器。

    ★ B-4：`norm_id` 加**唯一后缀**（结构化身份摘要）⇒ 同字段的多条约束
      不再撞 id ⇒ 质量闸不再阻断 `--constraints` 构建。
    """
    constraints = infer_constraints(protocol, llm, max_candidates=max_candidates)
    norms: list[dict] = []
    seen_ids: set[str] = set()
    for c in constraints:
        content = (f"field={c['field']} constraint={c['constraint']} "
                   f"violation={c['violation']} code={c['expected_code']} "
                   f"behavior={c['expected_behavior']}")
        norm_id = _constraint_norm_id(
            protocol, c["field"], c["constraint"], c["violation"],
            c["expected_code"])
        # ★ 同一**结构化身份** = 同一约束 ⇒ 只保留首条。
        #   否则两条措辞不同但四个身份字段相同的约束会撞同一个 norm_id
        #   ⇒ `dup_norm_ids > 0` ⇒ 质量闸阻断构建。
        if norm_id in seen_ids:
            continue
        seen_ids.add(norm_id)
        norms.append({
            "norm_id": norm_id,
            "kind": "constraint",
            "name": c["field"],
            "content": content,
            "kb_source_type": "rfc",
            "source": c["source"],
            "protocol": protocol,
            # ★ B-3：候选的 span / 章节归属 / 规范版本随 norm 下沉
            #   （可回溯到 RFC 原文的具体位置）。
            "span_start": c.get("span_start"),
            "span_end": c.get("span_end"),
            "section_path": list(c.get("section_path") or []),
            "section_no": c.get("section_no") or "",
            # ★ 章节号链（给 rule_id 派生用；与标题链 `section_path` 并列）
            "section_no_path": list(c.get("section_no_path") or []),
            "spec_version": c.get("spec_version") or "",
        })
    return norms


_PROMPT_STRUCTURES = """你是 {protocol} 协议规范分析专家。下面是 RFC 文档里正则规则识别不了的章节标题。
请识别每个标题属于哪一类：
- method：协议方法/命令（如 OPTIONS、EHLO、USER、REGISTER）
- field：字段/头部（如 Accept、CSeq、From、To）
- outcome：状态码/响应码（如 250、404）
- 都不是：跳过（如章节名 Introduction、Examples）

章节标题：
{titles}

只输出 JSON（不要解释），格式：
{{"methods": [{{"name": "...", "definition": "一句话语义"}}],
  "fields": [{{"name": "...", "definition": "一句话语义"}}],
  "outcomes": [{{"name": "...", "definition": "一句话语义"}}]}}"""


def infer_structures(protocol: str, llm=None, max_headings: int = 60) -> list[dict]:
    """LLM 兜底识别方法/字段/状态码，补齐正则标题格式识别的不足。

    对齐 SemFuzz 的「LLM 从自然语言抽语义」：正则（rule）打底 + LLM 补语义。
    只把「正则标题格式识别不了」的标题喂 LLM（多词标题如「Extended HELLO
    (EHLO)」、带括号标题等），控制 LLM 调用量；llm 缺省用 DeepSeekClient，
    测试可传 StubLLMClient。
    """
    if llm is None:
        from core.llm import DeepSeekClient
        llm = DeepSeekClient()
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    # 收集 rule 识别不了的多词/带括号标题（正则已识别的状态码/方法/字段/章节词跳过）
    ambiguous: list[dict] = []
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for ln in lines:
            s = ln.strip()
            m = _RE_ANY_HEADING.match(s)
            if not m:
                continue
            heading = m.group(2).strip()
            if re.search(r"\.{3,}|(?:\.\s+){2,}", heading):
                continue  # 目录(TOC)标题带点线页码，非正文章节标题
            if _RE_STATUS_ANY.match(s):
                continue  # 状态码已由正则识别
            if "(" not in heading:
                continue  # 只收带括号标题（命令/方法强特征，如「MAIL (MAIL)」；
                          # 不带括号的多词章节名「Transport of Electronic Mail」排除）
            m2 = _RE_ANY_SECTION.match(s)
            if m2:
                w = m2.group(2)
                if (w.upper() in _GENERIC_SECTION_WORDS
                        or _RE_METHOD_NAME.match(w)
                        or _RE_FIELD_NAME.match(w)):
                    continue  # 单词标题已由正则识别
            ambiguous.append({"heading": heading, "source": f"file:{f.name}"})
            if len(ambiguous) >= max_headings:
                break
        if len(ambiguous) >= max_headings:
            break
    if not ambiguous:
        return []
    titles = "\n".join(f"{i + 1}. {h['heading']}"
                       for i, h in enumerate(ambiguous))
    try:
        r = llm.chat_json(
            system="你输出 JSON。",
            user=_PROMPT_STRUCTURES.format(protocol=protocol.upper(), titles=titles),
            temperature=0.2, max_tokens=3000)
    except Exception:
        return []
    if not isinstance(r, dict):
        return []
    norms: list[dict] = []
    for kind, key in (("method", "methods"), ("field", "fields"),
                      ("outcome", "outcomes")):
        for item in (r.get(key) or []):
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            definition = (item.get("definition") or name).strip()
            # ★field 的 content 用「name | required: 语义」格式，与 _extract_rfc_file
            # 的 field norm 对齐——否则 norm.parse_field_content 找不到「| modality:」
            # 分隔，会把语义误当 syntax（产出 aspect=syntax 而非 definition）。
            # method/outcome 保持纯 definition（norm.py 的 method/outcome 映射不依赖该格式）。
            if kind == "field":
                content = f"{name} | required: {definition}"
            else:
                content = definition
            norms.append({
                # ★ B-4 附带修复：LLM 结构兜底的 norm_id 加 `llm.` 命名空间。
                #   原因：LLM 兜底抽出的方法/字段与**确定性抽取**同名
                #   （实测 smtp 10 个方法全撞：EHLO/MAIL/RCPT/DATA/RSET/VRFY/
                #   EXPN/HELP/NOOP/QUIT）⇒ norm_id 相同 ⇒ `dup_norm_ids > 0`
                #   ⇒ 质量闸把 `--constraints` 构建**阻断**（先于 B-3/B-4 既存）。
                "norm_id": (f"{protocol}.llm.{kind}."
                            f"{name.lower().replace(' ', '_')}"),
                "kind": kind,
                "name": name,
                "content": content,
                "kb_source_type": "rfc",
                "source": "llm:structure",
                "protocol": protocol,
                # ★ 来源标记 ⇒ norm.py 给 subject 加 `origin` 限定子，
                #   使「LLM 兜底事实」与「确定性抽取事实」身份可区分
                #   （fact_key 只含 subject/aspect/condition ⇒ 不区分就撞
                #   fact_id ⇒ `dup_fact_ids > 0` ⇒ 同样阻断构建）。
                #   ⚠ subject.name 不变 ⇒ 下游 bundle 的分桶行为不变。
                "origin": "llm_structure",
            })
    return norms


__all__ = ["extract_rfc_norms", "extract_constraint_candidates",
           "infer_constraints", "extract_constraint_norms",
           "infer_structures"]
