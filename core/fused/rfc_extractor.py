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

import collections
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Optional

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
# ★ 批次 2.1（P1）：**支持字母附录**（`A.1` / `B.2`）——
#   原正则只认**数字**开头 ⇒ RFC 的 `Appendix A`（RTSP 的状态机就在
#   附录 A！）**完全不被识别为章节** ⇒ 附录里的知识（状态机 / ABNF /
#   示例报文）**全部抽不到**。⇒ 字母前缀只允许**单个大写字母**（`A.1`）
#   ⇒ 数字章节的判定完全不变 ⇒ 既有抽取结果零影响。
# ★ 批次 2.1（P1）注：**字母附录**（`A.1`）**刻意不识别为章节标题** ——
#   识别它会改变章节树 ⇒ 连带改变 `section_no_path`（既有契约：号链每段
#   都是数字章节号、且末级 == section_no）⇒ 代价大于收益。
#   ⇒ 改为**全文扫状态转移表**（见 `_extract_transition_table`），
#     不依赖章节划分 ⇒ 章节树与既有契约**完全不动**。
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
    # ★ 2026-11-07：移出 "SECURITY" —— 它虽是 RFC 通用章节名（Security
    #   Considerations），但**某些协议确实有 Security 头**（如 HTTP/RTSP 的
    #   认证头命名）⇒ 留在表里有误伤风险。章节名的过滤交给下面的
    #   "CONSIDERATIONS" 等更专的词。
    "CONSIDERATIONS", "EXAMPLES", "SYNTAX", "MODEL", "USAGE",
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
    # ★ 2026-11-07：**通用元词**（不是任何协议的字段名）——
    #   实测 DHCPv4 的 headers 桶里混进了这些**章节标题**：
    #   Authentication / Message / Options / Type / Length / Value / DHCP / DHCPv4
    #   ⇒ 它们是「元信息词」而非协议字段 ⇒ 抽出即污染取值池。
    #   ★ 协议无关（不认协议名、不认具体头名），只收「在 RFC 里专表元信息」的词。
    #   ⚠ **只收「几乎不可能是协议字段」的词** —— 实测踩坑：
    #     加了 OPTIONS / SERVER ⇒ **误伤 RTSP 的真字段**
    #     （``rtsp.field.server`` = RTSP 的 Server 头、``rtsp.method.options``
    #     = OPTIONS 方法）⇒ 头字段与方法**双双丢失**。
    #   ⇒ 判据：这个词若是**某协议的合法头名/方法名**，就不能进停用词表。
    "AUTHENTICATION", "MESSAGE", "MESSAGES",
    "TYPE", "LENGTH", "VALUE", "VALUES", "NAME", "NAMES",
    "PROTOCOL", "VERSION", "HEADER", "HEADERS", "FIELD", "FIELDS",
    "FORMAT", "FORMATS", "ENCODING", "ERROR", "ERRORS",
    "RESPONSES", "RELAY",
    "BOOTREQUEST", "BOOTREPLY", "SPECIFICATION", "IMPLEMENTATION",
    "INTERFACE", "CONFIGURATION", "PARAMETER", "PARAMETERS",
    "ACKNOWLEDGMENT", "ACKNOWLEDGMENTS", "PRIVACY",
    "IANA", "REGISTRY", "ASSIGNMENT", "NUMBERS",
}

#: **方法名**里必须排除的「关键字原子」（**协议无关**）：RFC 关键字
#: （MUST/SHALL/…）+ 协议/角色缩写（RFC/TCP/UDP/IP/HTTP/ID/URI/URL/OK/
#: ALL/UAC/UAS/TU/UA）。它们不是任何协议的命令名，被当成方法即污染方法集。
#: ★ 提到模块级是为了让**形态 E**（散文命令格式声明）与其它形态共用同一份
#:   排除表 ⇒ 「方法集」与「norms」两个消费者口径必然一致。
_METHOD_KEYWORD_ATOMS = frozenset({
    "MUST", "SHALL", "SHOULD", "MAY", "REQUIRED", "OPTIONAL", "NOT",
    "RFC", "TCP", "UDP", "IP", "HTTP", "ID", "URI", "URL", "OK", "ALL",
    "UAC", "UAS", "TU", "UA",
})

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
    # ★ 批次 2.1（P1）：状态机章节（状态转移表所在章节号前缀）
    "transition_sections",
    "method_excludes",
    "numeric_bounds",
    "expected_response_classes",
)

#: ★ 2026-11-07：**按文件限定**的章节配置（dict 型，单独处理）。
#:   一个协议有多份 RFC 时章节号**大面积重号**（每份都有 §1–§8，语义各异）
#:   ⇒ 全局的 ``*_sections`` 会把别的 RFC 的同名章节也判成同类
#:   （实测 DHCPv4 的方法集混入 ``NVT`` —— 来自 rfc6607 的 §4.3）。
#:   形如：``{"rfc2131.txt": {"method_sections": ["4.3"], ...}}``
#:   ⇒ 命中该文件时用**文件专属配置**，否则回退全局配置。
_RFC_CONFIG_DICT_KEYS: tuple[str, ...] = (
    "sections_by_file",
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
    #    ★ **不在此处排除表格数据行**（实测踩坑）：折行的**目录条目**
    #      （``26         Security Considerations: Threat Model and Security``）
    #      形态上与表格数据行同构 ⇒ 在此排除会破坏「目录块兜底」机制
    #      （目录条目靠 `_toc_block_ranges` 在别处隔离，见 test_p1_fixes）。
    #      ⇒ 表格数据行的排除改在**窗口层**做（见 `_section_kind_from_lists`
    #        之前的 `number == "0"` 特判）。
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


#: `_section_kind` 的**破平局优先级**（同一章节号同时被多个清单声明时用）。
#: 数值越大越优先。理由见 `_section_kind` 的文档字符串。
_KIND_TIE_PRIORITY: dict[str, int] = {
    "status": 3, "method": 2, "field": 1, "transition": 0,
}


def _section_kind(window: dict, cfg: dict,
                  src_name: Optional[str] = None) -> Optional[str]:
    """按 rfc_config 判定窗口类型（评审 T7：语义判定替代形态猜测）。

    ★ 2026-11-07：支持**按文件限定**的章节配置（``sections_by_file``）——
      一个协议有多份 RFC 时，**章节号会大面积重号**（每份都有 §1–§8，语义各异）
      ⇒ 全局的 ``*_sections`` 会把别的 RFC 的同名章节也判成同类
      （实测 DHCPv4 的方法集混入 ``NVT`` —— 来自 rfc6607 的 §4.3）。
      ⇒ ``sections_by_file`` 形如：
          ``{"rfc2131.txt": {"method_sections": ["4.3"],
                             "field_sections": [...]}}``
      ⇒ 命中该文件时**用文件专属配置**，否则回退全局配置。

    查 cfg 的 method_sections / field_sections / status_sections /
    transition_sections，按**最长前缀**匹配（更具体的子节优先）。
    返回 "method" / "field" / "status" / "transition" / None。

    注意：状态码标题（`21.1.1 100 Trying`）优先判为 status —— 标题本身以
    3 位数字开头是协议通用特征，比章节号更可靠。

    ★ 2026-11-06 修正（P1-2）：**跨类别**比长度，长度并列时按
      ``status > method > field > transition`` 确定性破平局。

      修正前的实现是「method 匹配到就返回、field 匹配到就返回」，即
      **固定类别优先**而非「最长前缀优先」，与文档说明不符 ⇒ 两个后果：

      ① 同一章节号同时列在两个清单里时**静默判错**。实测 smtp：``4.2``
         同时在 ``method_sections`` 与 ``status_sections``
         （``fused_hub/targets/smtp/rfc_config.json``）⇒ 整章
         「SMTP Replies」被判成 method ⇒ 状态码抽成 **0** 条（应为 24）。
      ② **短前缀盖住长子节**：smtp 的 ``method_sections`` 含 ``"3"``
         （覆盖 rfc4954/rfc3207 的扩展命令章），而 ``field_sections`` 含
         ``"3.6"`` ⇒ 旧实现让 ``3.6.1``（RFC 5322 字段定义）被判成 **method**。

      破平局顺序的理由：
        · **status 最高** —— 同一章节号被声明为 status 时，那一章**就是**码表
          （``4.2 SMTP Replies``）；名字冲突是配置冗余，不是「两种可能」。
        · **method 次之（高于 field）** —— 沿用修正前的实际行为（有测试锁定）；
          方法章是「动词定义」，字段章是「字段语法」，同号时方法更具体。
        · transition 最低 —— 它是可选的旧通道。
    """
    number = window.get("section_no") or ""
    title = window.get("title") or ""

    # ★ 2026-11-07：文件专属配置优先（见 docstring 的「按文件限定」说明）
    if src_name:
        _by_file = cfg.get("sections_by_file") or {}
        _fc = _by_file.get(src_name)
        if isinstance(_fc, dict):
            _kind = _section_kind_from_lists(window, _fc)
            if _kind is not None:
                return _kind

    return _section_kind_from_lists(window, cfg)


def _section_kind_from_lists(window: dict, cfg: dict) -> Optional[str]:
    """按「章节号 × 各类清单」判定窗口类型（**判定核心**）。

    ★ 与 :func:`_section_kind` 的关系：后者是入口（先查文件专属配置），
      本函数是**判定核心**（全局配置与文件专属配置**共用**同一套逻辑）
      ⇒ 避免两份判据分裂（踩过的坑：norm 侧与候选侧判据不一致 ⇒ 污染）。
    """
    number = window.get("section_no") or ""
    title = window.get("title") or ""

    # ★ 2026-11-07：**表格数据行**排除（章节号为 ``0`` 时）。
    #   RFC 的表格数据行（``0  Network Virtual Terminal (NVT) ...``）会被
    #   `_RE_TOP_HEADING` 判成一级标题（number='0'）⇒ 整段被当「方法章」
    #   ⇒ 抽出误抽的方法（实测 RFC 6607 的 VSS 表 ⇒ ``NVT``）。
    #   ★ **只在此处排除、且只判 ``number == "0"``**：
    #     · 不放在 `_parse_heading` 里 ⇒ 不破坏「目录块兜底」机制
    #       （折行目录条目形态同构，实测踩过：会误伤 SIP 的目录条目）；
    #     · 只判 "0" ⇒ 真章节号（``26``、``4.3``）**不受影响**。
    if number == "0":
        return None

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
        return best          # ★ 必须返回 best（重构时误写成 None ⇒ 判定恒失效）

    # ★ 跨类别收集候选，按 (前缀长度, 破平局优先级) 取最大
    _cands: list[tuple[int, int, str]] = []
    for _kind, _key in (("method", "method_sections"),
                        ("field", "field_sections"),
                        ("status", "status_sections"),
                        ("transition", "transition_sections")):
        _m = _match(cfg.get(_key))
        if _m is not None:
            _cands.append((len(_m), _KIND_TIE_PRIORITY[_kind], _kind))
    if not _cands:
        return None
    return max(_cands)[2]



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
    # ★ 2026-11-07：**表格数据行**排除（章节号为 ``0``）。
    #   RFC 的表格数据行（``0  Network Virtual Terminal (NVT) ...``）的标题里
    #   含 ``(NVT)`` ⇒ 命中下面的「括号全大写缩写」启发式 ⇒ 被判成 method
    #   ⇒ 抽出误抽的方法（实测 RFC 6607 的 VSS 表 ⇒ ``NVT``）。
    #   ★ 判据：章节号为 ``"0"`` ⇒ 是**表格行的首列**（真章节号不会从 0 起）。
    #     ★ **不能**放在 `_parse_heading` 里（会破坏「目录块兜底」机制 ——
    #       折行目录条目形态同构，实测会误伤 SIP 的目录条目）。
    if (window.get("section_no") or "") == "0":
        return None
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
        # ★ 批次 2.1（P1）：状态机抽取开关（**默认关闭**）
        #   开启后从 RFC 正文**全文扫**状态转移表 ⇒ RFC 源自己贡献 target_state。
        #   ⚠ 实测代价：rtsp 开启后 transitions 38 → 12 条、种子 58 → 17 条
        #     （RFC 的**客户端**状态机只有 12 条边；**服务端**状态机是散文、
        #      表格抽不到）⇒ 覆盖**显著变小** ⇒ 需要先补齐服务端状态机
        #     （P1b：LLM 抽自然语言状态机）才宜开启。
        "enable_transitions": False,
        # ★ 2026-11-05（F 阶段 F1）：RFC 源抽「**消息级**必填头」的开关
        #   （**默认关闭** ⇒ 产物逐字节不变）。
        #   ★ 能力依据：确定性路线实测不可行（RFC 用指代句式表达必填性 ⇒ 正则抓不到），
        #     LLM 路线可行（实测 sip 覆盖 6/8=75%、误报 0；
        #     详见 local/必填头抽取可行性报告.md）。
        #   ★ 产出 aspect=required_header_global ⇒ **不进任何 bundle 桶**
        #     ⇒ 只作为可审计的 RFC 源证据留在中枢，供「替代骨架那份」的决策使用。
        "enable_required_headers": False,
        "method_excludes": [],
        "numeric_bounds": [],
        "expected_response_classes": [],
        # ★ 按文件限定的章节配置（默认空 = 全部走全局配置）
        "sections_by_file": {},
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
        # ★ dict 型键（按文件限定的章节配置）
        for key in _RFC_CONFIG_DICT_KEYS:
            value = data.get(key)
            if isinstance(value, dict):
                cfg[key] = {str(k): v for k, v in value.items()
                            if isinstance(v, dict)}
        # ★ 布尔键（不属列表白名单）
        if isinstance(data.get("enable_transitions"), bool):
            cfg["enable_transitions"] = data["enable_transitions"]
        if isinstance(data.get("enable_required_headers"), bool):
            cfg["enable_required_headers"] = data["enable_required_headers"]
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


def _extract_transition_tables_by_form(text: str) -> list[dict]:
    """**形态层表格腿**：按**列角色**解析 RFC 里的状态转移表（协议无关）。

    ★ 与 `_extract_transition_table`（三列定宽硬编码）的关系：
      - 旧实现按**固定三列 + 状态名继承**匹配 ⇒ 只认一种表格形态；
      - 本实现先由 `core.fused.rfc_forms` 按**内容形态**切出 `table` 块，
        再按**表头列名**判定起态/触发/目标列 ⇒ 换协议、换列名、换列数都能解析。
    ★ 两者**合并去重**后使用 ⇒ 结果与旧实现等价（实测同协议的转移集相同），
      但新增「按形态定位 + 逐行溯源」的能力，且不依赖章节树（附录里的表也能覆盖）。
    ★ 通用性前提（G1）：形态层按**内容**判形态 ⇒ 表在附录里照样被识别。

    Returns:
        `[{"from":…, "method":…, "to":…}, …]`
    """
    from core.fused.rfc_forms import parse_state_table, split_form_blocks
    if not text:
        return []
    out: list[dict] = []
    for _b in split_form_blocks(text.splitlines()):
        if _b.kind != "table":
            continue
        out.extend(parse_state_table(_b))
    return out


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


# ===========================================================================
# ★ P0（批次 2.0）：RFC 字段**取值样本**抽取
# ===========================================================================
#
# ★ 为什么需要：RFC 源此前只贡献 syntax + definition 两类知识 ⇒ 知识中枢的
#   ``headers`` 桶**取值池大面积为空**（实测 rtsp 28/58 = 48%、sip 26/63 = 41%，
#   其中 sip 的**必填头** Via/From/To/CSeq/Call-ID/Max-Forwards 全空）
#   ⇒ 直接压制 ⑤ 层 ``value-pool-boundary`` 规则（没有另一个取值可换）
#   ⇒ 也是批次 1 里 R-2（CSeq 取值池空）的根因。
#   而 RFC 规范里**明确写着**这些头的合法取值（示例报文 / Example 段）⇒
#   **是漏抽，不是规范里没有**。
#
# ★ 三道清洗（缺一不可，否则会被散文污染）：
#   ① **语境判别**：只在两种可信语境里取值 ——
#      A) "Example of use:" / "Example:" 引导段；
#      B) **连续 ≥2 行**的 ``Name: value`` 块（⇒ 完整报文示例 / 头列表）。
#      ⇒ 散文里的 "Server: A server is a network element…" 被滤掉。
#   ② **头名归一**：头名大小写不敏感 ⇒ 归到 field 名集合的**规范形态**
#      ⇒ 消除 Content-length / Content-type / CONTENT 等变体重复。
#   ③ **值清洗**：去续行符、限长、排除散文形态（含空格且首 token 不像 token）。

#: "Example of use:" 之类的举例引导词（单独成行）
_RE_EXAMPLE_LEAD = re.compile(
    r"^\s*(example of use|examples?|for example)\s*[:.]?\s*$",
    re.IGNORECASE)

#: 头值行：``Name: value``（Name 不含空格 ⇒ 不会把请求行 / URL 当头）
_RE_HEADER_VALUE_LINE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.+?)\s*$")

#: 取值样本长度上限（超长 ⇒ 多半是散文）
_MAX_SAMPLE_VALUE_LEN = 160

#: 取值池内部分隔符（取值里几乎不会出现 ⇒ 解析无歧义）
VALUE_SAMPLE_SEP = " |~| "


# ===========================================================================
# ★ P1（批次 2.1）：RFC 状态机（**状态转移表**）抽取
# ===========================================================================
#
# ★ 为什么需要：RFC 源此前**不产** `kind="transition"` 的 norm
#   （`norm.py::transition_norm_to_fact` 的 docstring 明写「无数据源（死代码）」）
#   ⇒ 状态机一直由 source 源（源码分析）提供 ⇒ **协议骨架借来的**。
#   而骨架的状态命名**实测有误**：rtsp 的骨架状态名是
#   Idle/Registered/Invited/Confirmed（**SIP 的体系**）却配着 RTSP 的方法
#   ⇒ RFC 原生的状态名（Init/Ready/Playing/Recording）才是对的。
#
# ★ 为什么**不用 LLM**：RFC 的状态机是**三列定宽表格**，可**确定性**抽取：
#     state       message sent     next state after response
#     Init        SETUP            Ready
#                    TEARDOWN         Init
#     Ready       PLAY             Playing
#   ⇒ 状态名有**继承**语义（留空 = 沿用上一行）⇒ 解析可靠、可复现、零成本。

#: 状态转移表的**表头**特征（同时含「消息列」与「下一状态列」）
# ===========================================================================
# ★ 批次 2.2：ABNF 形态的**字段定义**抽取（通道 E）
# ===========================================================================
#
# ★ 为什么需要：SMTP 的 RFC 5322 把头字段定义成 **ABNF 规则**（§3.6
#   Field Definitions），而**不是**章节标题：
#       orig-date       =   "Date:" date-time CRLF
#       from            =   "From:" mailbox-list CRLF
#   ⇒ 现有三条通道都抓不到：
#       · 章节标题式（RTSP "12.1 Accept"）—— SMTP 没有这种标题
#       · 缩进条目式（"   byte"）—— SMTP 不是这种形态
#       · `_section_kind` 的 field 判定 —— ★ **不可用**：SMTP 的
#         `method_sections` 含 "3" ⇒ `_match` 把 §3.6 判成 **method**
#         （method 优先于 field）⇒ 按 field_sections 定位拿不到
#   ⇒ 解法：**全文扫** ABNF 形态（只认「引号内是带冒号的字段名」这一形态）
#     ⇒ 天然精确：SIP 的 `Accept = "Accept" HCOLON ...`（引号内**无冒号**）
#       不会被误伤；RTSP/SIP 的头字段是章节标题式，也不会重复。
#
#: ABNF 字段定义行：``   orig-date       =   "Date:" date-time CRLF``
#:   ⇒ 捕获组 1 = **字段名**（`Date`）、捕获组 2 = 右侧 ABNF
#: ★ 2026-11-07（B2）修正：**必须带 ``re.MULTILINE``**。
#:   没有它时 ``^`` 只匹配**整个字符串的开头** ⇒ 在整篇 RFC 文本上
#:   ``finditer`` **永远命中 0 条**（实测 RFC 5322 的 20 个 ABNF 头全丢）。
#:   （逐行 ``match`` 能命中 ⇒ 所以这个 bug 极隐蔽：单行测试通过、全文扫描全灭。）
_RE_ABNF_FIELD = re.compile(
    r'^[ \t]+[a-z][a-z0-9-]*[ \t]+=[ \t]+"([A-Za-z][A-Za-z0-9_-]*):"'
    r'(?P<rhs>[^"]*)$', re.MULTILINE)

#: ABNF 字段的**散文说明** —— 形态：
#:   `The origination date field consists of the field name "Date" followed by`
_RE_ABNF_PROSE = re.compile(
    r'\bfield name\s+"([A-Za-z][A-Za-z0-9_-]*)"', re.IGNORECASE)


def _extract_abnf_fields(text: str) -> list[dict]:
    """从 RFC 正文抽「ABNF 形态的字段定义」。

    Returns:
        ``[{"name": 字段名, "abnf": 右侧 ABNF, "prose": 散文说明}, ...]``
        （按出现序、字段名去重）。
    """
    out: list[dict] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        m = _RE_ABNF_FIELD.match(raw)
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "abnf": m.group("rhs").strip(),
                    "prose": ""})
    # 补散文说明（`the field name "X"` ⇒ X 的语义描述所在句）
    flat = (text or "").replace("\n", " ")
    sentences = re.split(r"(?<=[.;])\s+", flat)
    prose_by_name: dict[str, str] = {}
    for sent in sentences:
        pm = _RE_ABNF_PROSE.search(sent)
        if not pm:
            continue
        fname = pm.group(1)
        half = sent[:pm.start()].strip() or sent.strip()
        prose_by_name.setdefault(fname, half[:200])
    for item in out:
        item["prose"] = prose_by_name.get(item["name"], "")
    return out



_RE_TRANSITION_HEADER = re.compile(
    r"message\s+sent", re.IGNORECASE)


#: 状态名里的**修饰后缀**（如 "Playing (changed transport)"）⇒ 剥掉
_RE_STATE_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


def _extract_transition_table(text: str) -> list[dict]:
    """从 RFC 正文抽「状态转移表」。

    ★ 表格形态（三列定宽 + 状态名继承）::

        state       message sent     next state after response
        Init        SETUP            Ready
                       TEARDOWN         Init
        Ready       PLAY             Playing

    Returns:
        ``[{"from":..., "method":..., "to":...}, ...]``（按出现序）。
    """
    lines = (text or "").splitlines()
    out: list[dict] = []
    cur_state = ""
    cols: tuple[int, int, int] | None = None
    for raw in lines:
        if not raw.strip():
            continue
        # ---- 表头：按**列位置**确定三列边界（定宽表格 ⇒ 最稳）----
        if cols is None:
            if not _RE_TRANSITION_HEADER.search(raw):
                continue
            m_msg = re.search(r"message\s+sent", raw, re.IGNORECASE)
            m_next = re.search(r"next\s+state", raw, re.IGNORECASE)
            m_state = re.search(r"\bstate\b", raw, re.IGNORECASE)
            if not (m_msg and m_next and m_state):
                continue
            cols = (m_state.start(), m_msg.start(), m_next.start())
            cur_state = ""
            continue
        c1_at, c2_at, c3_at = cols
        # 表格外的正文（页眉/页脚/新段落）⇒ 结束表格
        if not raw[:1].isspace():
            cols = None
            cur_state = ""
            continue
        if len(raw) <= c3_at:
            continue
        # ★ 按**列位置**切分（状态列留空 = 继承上一行 ⇒ 必须按位置，不能按内容）
        state = raw[c1_at:c2_at].strip()
        method = raw[c2_at:c3_at].strip()
        to = _RE_STATE_SUFFIX.sub("", raw[c3_at:].strip()).strip()
        if state:
            cur_state = state
        if not cur_state or not method or not to:
            continue
        if " " in method or " " in to:
            continue
        out.append({"from": cur_state, "method": method, "to": to})
    return out


def _parse_value_samples(content: str) -> list[str]:
    """解析 ``"<name> | values: v1 |~| v2"`` → ``[v1, v2]``。"""
    body = content or ""
    if "| values:" not in body:
        return []
    tail = body.split("| values:", 1)[1]
    return [v.strip() for v in tail.split(VALUE_SAMPLE_SEP) if v.strip()]


def _looks_like_token(tok: str) -> bool:
    """判断一个 token 是否像「协议 token」（而不是散文词）。

    ★ 判据要点：``A`` / ``The`` 这类**单/双字母虚词**不算 token
      （否则 "A server is a network element" 会被当取值）。
    """
    tok = (tok or "").strip()
    if not tok:
        return False
    if len(tok) <= 2 and tok.isalpha():
        return False
    if tok.endswith("/") or "=" in tok or tok.isupper():
        return True
    if tok.replace(".", "").replace("-", "").replace("_", "").isdigit():
        return True
    # 形如 application/sdp、text/parameters、multipart/signed
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9]*/", tok))


#: ★ 批次 2.5：RFC **文档示例域名**（RFC 2606 保留域名 + 常见示例 TLD）
_RESERVED_HOST_SUFFIX = (
    ".example", ".invalid", ".localhost", ".test",
)
_RESERVED_HOSTS = frozenset({
    "example.com", "example.net", "example.org",
})

#: 裸域名形态：``label(.label)+`` 且**末段是纯字母**（长度 ≥2）
#:   ⇒ ``www.example.com`` 命中；``2.5`` / ``1.0`` **不**命中（TLD 是数字）
_RE_BARE_DOMAIN = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"[A-Za-z](?:[A-Za-z-]*[A-Za-z])?$")


def _is_example_host_value(val: str) -> bool:
    """判断一个取值是否是「RFC 文档示例地址 / 示例域名」⇒ 不该进取值池。

    ★ 为什么必须排除（三条理由）：
      ① **语义**：取值池的用途是「字段的合法取值」⇒ 一个**完整的示例
         地址实例**（``<sip:carol@chicago.com>``、``<1234@local.machine.example>``）
         是**整条报文/地址**，不是「某个字段的一个取值」⇒ 粒度就错了。
      ② **对 ⑤ 层无用**：把 URI 里的域名换成另一个示例域名 ⇒ 仍然是死信
         ⇒ ⑤ 层 ``value-pool-boundary`` 拿它做变异**零收益**。
      ③ **污染 G1**：这些域名会被写进 ``Contact``/``Via``/URI ⇒ 目标端点
         变成示例域名 ⇒ **corpus_gate 的 G1（目标端点正确性）判违规**
         ⇒ SIP 语料**不可发布**（实测 sip 全部种子违规，端点 ``chicago.com:5060``）。
    """
    v = (val or "").strip()
    if not v:
        return False
    # ① 完整地址 / URI **实例**
    #   ⚠ **不能**用「含 @ 就排除」——SIP 的 `Call-ID: a84b4c76e66710@192.0.2.1`
    #     是**该头的合法取值**（RFC 3261 规定 Call-ID 形如 word@word）⇒ 误杀。
    #   ⇒ 只排「**整体**是尖括号包裹的实例」或「带 scheme 的 URL」：
    #     <sip:carol@chicago.com> / <http://...>  ⇒ 整条报文/地址实例
    #   ⚠ 用「**含** `<` 且**含** `>`」而不是「整体被包裹」——实测 RFC 里还有
    #     `'<sip:server10.biloxi.com;lr>,'`（带尾逗号）与
    #     `'<sip:carol@chicago.com>;tag=93810874'`（带参数）两种形态。
    if "://" in v or ("<" in v and ">" in v):
        return True
    # ② RFC 2606 保留域名
    low = v.lower().rstrip(".")
    if low in _RESERVED_HOSTS:
        return True
    if any(low.endswith(sfx) for sfx in _RESERVED_HOST_SUFFIX):
        return True
    # ③ 裸域名形态（含 ``www.example.com`` 这类）
    if _RE_BARE_DOMAIN.match(v):
        return True
    # ④ **值里**的示例主机（实测形态：
    #    `SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bK`（复合值）
    #    `a84b4c76e66710@pc33.atlanta.com`（user@域名，无空格）
    #    ⇒ 逐 token 查：任一 token 是示例主机 ⇒ 整个值排除
    #    ⚠ 对**所有**值生效（不只含空格的）——否则无空格的 user@域名会漏网
    if True:
        for tok in v.split():
            # ★ 剥掉 URI 参数与端口（``pc33.atlanta.com;branch=z9hG4bK``、
            #   ``bobspc.biloxi.com:5060`` ⇒ 都取主机部分）
            #   ⚠ IP 形态（``192.0.2.1:5060``）剥端口后末段是数字 ⇒
            #     **不**命中裸域名判据 ⇒ IP 地址保留（正确）
            tok = tok.split(";")[0].split("=")[0]
            # ★ 含 ``@`` 时**先**取 host 部分（``user@pc33.atlanta.com`` ⇒
            #   ``pc33.atlanta.com``；``sip:callee@u2.domain.com`` ⇒
            #   ``u2.domain.com``）⇒ 才能识别「user@示例域名」
            #   ⚠ 顺序要紧：先 @ 后 ``:``，否则 ``sip:callee@...`` 会被
            #     剥端口时把 host 一起剥掉
            if "@" in tok:
                tok = tok.rsplit("@", 1)[-1]
            tok = tok.split(":")[0].rstrip(",)")
            low_tok = tok.lower().rstrip(".")
            if (low_tok in _RESERVED_HOSTS
                    or any(low_tok.endswith(sfx)
                           for sfx in _RESERVED_HOST_SUFFIX)
                    or _RE_BARE_DOMAIN.match(tok)):
                return True
    return False


#: ★ 2026-11-07（B2）：**地址类头**的取值 —— 判据来自 RFC 的 **ABNF rhs**
#:   （``mailbox-list`` / ``address-list`` / ``mailbox``），**协议无关**。
#:   实测 RFC 5322：``from = "From:" mailbox-list CRLF`` / ``to = "To:" address-list``。
_ADDRESS_RHS_RE = re.compile(r"\b(mailbox-list|address-list|mailbox)\b")


def _is_address_header(field_name: str, abnf_rhs: str) -> bool:
    """该头是否是「邮箱地址类」（判据：ABNF rhs 里的 mailbox/address 记号）。

    ★ 协议无关：只看 **ABNF 语义**，不认协议名、不认具体头名。
    """
    if not abnf_rhs:
        return False
    return bool(_ADDRESS_RHS_RE.search(abnf_rhs))


def _clean_sample_value(val: str, is_address: bool = False) -> str:
    """清洗一条取值样本；不合格返回空串。

    ★ 含空格时：**每个逗号分隔项**的首 token 都得像 token 才收
      ⇒ 既放过多值取值（"application/rtsl, application/sdp;level=2"），
        又挡住散文（"A server is a network element…"）。

    ★ 2026-11-07（B2）：``is_address=True``（该头是**邮箱地址类**，判据见
      `_is_address_header`）⇒ **不套用「整条地址实例」的排除规则**。
      理由：``From: John Doe <jdoe@machine.example>`` 的**整个值**就是邮箱地址
      （不是「URI 实例」）⇒ 按 URI 规则排除会把 RFC 5322 的 20+ 个邮件头的
      取值**全灭**（实测 `From`/`To`/`Subject` 的 values 全为 None）。
      ★ 但仍保留「保留域名/超长」的通用清洗（不引入垃圾）。
    """
    val = (val or "").rstrip("\\").strip()
    if not val or len(val) > _MAX_SAMPLE_VALUE_LEN:
        return ""
    # ★ 批次 2.5：排除「RFC 文档示例地址 / 示例域名」
    #   （理由见 `_is_example_host_value` 的 docstring：粒度错、对 ⑤ 层零收益、
    #    且污染 corpus_gate 的 G1 ⇒ SIP 语料不可发布）
    #   ★ B2：地址类头**豁免**此规则（它的值本来就是地址）。
    if not is_address and _is_example_host_value(val):
        return ""
    if " " in val:
        for part in val.split(","):
            # ★ 先 strip 再取首 token（否则 "SETUP, PLAY" 的第二项首 token 是空串）
            if not _looks_like_token(part.strip().split(" ", 1)[0]):
                # ★ B2：地址类头**豁免**「像 token」判定 ——
                #   邮箱的显示名是人名（"John Doe <jdoe@machine.example>"），
                #   首 token 是散文词 ⇒ 按通用规则会被当成散文拒掉
                #   （实测 RFC 5322 的 From/To/Subject 取值全灭）。
                #   ★ 仍要求「**含 @**」⇒ 只对邮箱地址放宽，不放行普通散文。
                if not (is_address and "@" in part):
                    return ""
    return val


def _extract_field_value_samples(
        text_lines: list[str], known: dict[str, str],
        address_fields: Optional[set] = None) -> dict[str, list[str]]:
    """从 RFC 正文抽「字段 → 取值样本」。

    Args:
        text_lines: **已清洗、已隔离 TOC** 的正文行（逐行）。
        known: ``{小写头名: 规范头名}``（来自本文件已抽出的 field 名）。
        address_fields: **地址类头**的小写名集合（B2 2026-11-07）——
            判据见 `_is_address_header`（ABNF rhs 里的 mailbox/address 记号）。
            这些头的取值**豁免**「整条地址实例」的排除规则。

    Returns:
        ``{规范头名: [取值样本, ...]}``（按出现序、去重）。
    """
    out: dict[str, list[str]] = {}
    _addr = {str(a).lower() for a in (address_fields or set())}

    def _add(raw_name: str, raw_val: str) -> None:
        canon = known.get(raw_name.lower())
        if not canon:
            return
        val = _clean_sample_value(
            raw_val, is_address=raw_name.lower() in _addr)
        if not val:
            return
        bucket = out.setdefault(canon, [])
        if val not in bucket:
            bucket.append(val)

    n = len(text_lines)
    i = 0
    while i < n:
        line = text_lines[i]
        # —— 语境 A：Example 引导段 ——
        if _RE_EXAMPLE_LEAD.match(line):
            i += 1
            while i < n:
                m = _RE_HEADER_VALUE_LINE.match(text_lines[i])
                if m:
                    _add(m.group(1), m.group(2))
                    i += 1
                    continue
                if text_lines[i].strip():
                    break
                i += 1
            continue
        # —— 语境 B：连续 ≥2 行的头块（完整报文示例 / 头列表）——
        m0 = _RE_HEADER_VALUE_LINE.match(line)
        if m0 and m0.group(1).lower() in known:
            j = i
            block: list = []
            while j < n:
                mm = _RE_HEADER_VALUE_LINE.match(text_lines[j])
                if not mm or mm.group(1).lower() not in known:
                    break
                block.append(mm)
                j += 1
            if len(block) >= 2:
                for mm in block:
                    _add(mm.group(1), mm.group(2))
                i = j
                continue
        i += 1
    return out


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
    # ★ P0：已抽出的字段名（小写 → 规范形态）—— 供「取值样本」通道判定
    field_names: dict[str, str] = {}

    def _add_field(name: str, sem_text: str, line_no: int) -> None:
        """加入一条 field norm（同文件内按 norm_id 去重）。"""
        if not name or name.upper() in _GENERIC_SECTION_WORDS:
            return
        # ★ 2026-11-07：排除**协议自身名**（含版本后缀形态）。
        #   实测：RFC 3396 §2 Terminology 的缩进术语条目
        #       ``   DHCP``（正文「the acronym "DHCP" is used to refer to…」）
        #   ⇒ 被缩进字段通道当成字段 ``DHCP`` / ``DHCPv4``（协议自身名不是字段）。
        #   ★ 判据**协议无关**：拿协议名本身 + 「协议名+数字」的版本形态比对。
        if protocol:
            _pn = protocol.lower()
            _nl = name.lower()
            # 协议名的**词干**形态也要排除（协议名 `dhcpv4` ⇒ 词干 `dhcp`
            #   ⇒ 排除字段 `DHCP`；RFC 里常有「协议缩写」单独作术语条目）。
            _stem = re.sub(r"[\-_]?v?\d+.*$", "", _pn) or _pn
            for _form in {_pn, _stem}:
                if not _form:
                    continue
                if _nl == _form or (_nl.startswith(_form)
                                    and _nl[len(_form):].isdigit()):
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
        # ★ P0：登记字段名（供「取值样本」通道判定头名是否已知）
        field_names.setdefault(name.lower(), name)

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

    # ---- 通道 A0b：ABNF 命令规则字面量（rfc4954 的 `auth-command = "AUTH"`）----
    #   ★ 与通道 A0 同属「ABNF 通道」：SIP 用 hex 伴生规则、SMTP 扩展用命令规则
    #     字面量 ⇒ 两种排版各自独立的客观判据，互不干扰。
    for _m in _extract_abnf_quoted_commands(
            "\n".join(text for _, text in content_lines)):
        if _m.upper() in method_excludes:
            continue
        method_names.add(_m.upper())
        _mn = _norm("method", _m, _m, protocol, src_name, "@abnf")
        if _mn["norm_id"] not in seen_ids:
            seen_ids.add(_mn["norm_id"])
            norms.append(_mn)

    # ---- 通道 A0c：散文「命令格式声明」句式（RFC 3207 的 STARTTLS）----
    #   ★ 与 A0/A0b 同属**确定性抽取**：句式（"the format of the X command is"）
    #     + 全大写词形 ⇒ **协议无关** ⇒ STARTTLS 成为 **RFC 事实**而非骨架补丁。
    #   ★ 放在窗口循环**之前**登记 `method_names` ⇒ 命令名不会被重复当 field。
    for _m, _ml in _extract_prose_command_formats(
            raw_lines, protocol, method_excludes):
        method_names.add(_m.upper())
        _mn = _norm("method", _m, _m, protocol, src_name, f"@{_ml}")
        if _mn["norm_id"] not in seen_ids:
            seen_ids.add(_mn["norm_id"])
            norms.append(_mn)

    for w in windows:
        # ★ 传 src_name ⇒ 支持按文件限定的章节配置（多 RFC 协议消歧）
        kind = _section_kind(w, cfg, src_name)
        if kind is None:
            kind = _infer_kind_from_content(w)

        title = (w.get("title") or "").strip()
        text = w.get("text") or ""
        sem = _first_sentence(text)
        line_no = w.get("line", 0)
        # ★ 2026-11-08 修正（批次 2 暴露的**既有隐患**）：`norm` 原本只在
        #   method/field/outcome 三个分支里赋值，**没有每轮重置** ⇒
        #   当某个窗口的 kind 判不出（或判成 required_header/transition）时，
        #   `norm` 保留**上一轮**的值 ⇒ 下面 `norm["norm_id"]` 会把
        #   **上一轮的 norm 重复加入**。
        #   ★ 旧通道下从未暴露（章节号通道总能判出 method/field/status/outcome），
        #     但新通道（内容判据）会判出 None ⇒ 必须修。
        norm = None

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

        # ---- 通道 C：缩进状态码表（smtp 的 §4.2.3 / 同类「码表」形态）----
        #   ★ 只在 kind == "status" 的窗口里做 —— 否则正文里的「300 秒超时」
        #     之类数字会被误当状态码。
        if kind == "status":
            for code, reason in _extract_status_code_entries(text):
                if not reason:
                    continue
                snorm = _norm("outcome", code, reason, protocol, src_name,
                              f"@{line_no}")
                if snorm["norm_id"] in seen_ids:
                    continue
                seen_ids.add(snorm["norm_id"])
                norms.append(snorm)

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
        elif kind == "field":  # 标题本身就是字段名（如 `12.1 Accept`）
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
            # ★ P0：登记字段名（供「取值样本」通道判定头名是否已知）
            field_names.setdefault(name.lower(), name)

        # 同一文件内去重（同一 norm_id 只保留首个 = 正文首个出现）
        if norm is None:
            continue
        if norm["norm_id"] in seen_ids:
            continue
        seen_ids.add(norm["norm_id"])
        norms.append(norm)

    # ---- 通道 E：ABNF 形态的字段定义（★ 批次 2.2）--------------------------
    #   全文扫（**不依赖** `_section_kind` ⇒ 不受 method/field 章节判定影响）
    #   ⇒ SMTP 的 §3.6 Field Definitions 能被抽到（实测 22 个字段）。
    _full_text = "\n".join(t for _, t in content_lines)
    # ★ B2：存下 ABNF 字段（后面要据其 rhs 判定「地址类头」）
    _abnf_fields = _extract_abnf_fields(_full_text)
    for _fld in _abnf_fields:
        _fname = _fld["name"]
        if _fname.upper() in _GENERIC_SECTION_WORDS:
            continue
        if _fname == _fname.lower() and _fname in _FIELD_STOPWORDS:
            continue
        if _fname.upper() in method_names:
            continue
        _sem = _fld["prose"] or _fld["abnf"]
        _content = f"{_fname} | required: {_sem}" if _sem else _fname
        _fn = _norm("field", _fname, _content, protocol, src_name,
                    "@abnf-field")
        if _fn["norm_id"] in seen_ids:
            continue          # 章节标题式已抽到 ⇒ 保留首个
        seen_ids.add(_fn["norm_id"])
        norms.append(_fn)
        field_names.setdefault(_fname.lower(), _fname)


    # ---- 通道 F：状态转移表（★ P1，批次 2.1）-------------------------------
    #   ★ **全文扫**（不走窗口）—— 因为 RFC 的状态机表常在**附录**里
    #   （RTSP 在 Appendix A），而附录**不是章节标题** ⇒ 走窗口抽不到。
    #   ★ 表头特征足够特异（"message sent" + "next state"）⇒ 全文扫安全。
    #   ★ content 格式对齐 `norm.py::parse_transition_content`
    #     （"from=X method=Y to=Z"，按空格分隔的 key=value）。
    # ★ 两条腿合并去重：① 全文扫（三列定宽硬编码）② 形态层表格腿（按列角色）
    #   ⇒ 结果等价但形态腿可逐行溯源、且**不依赖章节树**（附录里的表也覆盖）。
    _trs = (_extract_transition_table(_full_text)
             if cfg.get("enable_transitions") else [])
    if cfg.get("enable_transitions"):
        for _r in _extract_transition_tables_by_form(_full_text):
            if _r not in _trs:
                _trs.append(_r)
    for _tr in _trs:
        _content = (f"from={_tr['from']} method={_tr['method']} "
                    f"to={_tr['to']}")
        _tn = _norm("transition", _tr["method"], _content, protocol, src_name,
                    "@state-table")
        # ★ norm_id 必须含 from/to：同一方法可有多条转移
        #   （如 PLAY: Playing→Playing）⇒ 只用 method 会撞 id ⇒ 状态机残缺。
        _tn["norm_id"] = (
            f"{protocol}.transition.{_tr['method']}."
            f"{_tr['from'].lower()}_to_{_tr['to'].lower()}")
        if _tn["norm_id"] in seen_ids:
            continue
        seen_ids.add(_tn["norm_id"])
        norms.append(_tn)

    # ---- 通道 D：字段**取值样本**（★ P0，批次 2.0）------------------------
    #   RFC 规范里明确写着各头的合法取值（完整报文示例 / "Example of use" 段）
    #   ⇒ 此前**漏抽** ⇒ 知识中枢 headers 桶取值池大面积为空
    #   ⇒ 压制 ⑤ 层 value-pool-boundary 规则。
    #   ★ 全文扫描（不受窗口预算限制），但**只认已知字段名** ⇒ 精确无污染。
    if field_names:
        # ★ B2：把「地址类头」集合传下去（判据来自 ABNF rhs，协议无关）
        _addr_fields = {f["name"].lower() for f in _abnf_fields
                        if _is_address_header(f["name"], f.get("abnf") or "")}
        _samples = _extract_field_value_samples(
            [t for _, t in content_lines], field_names,
            address_fields=_addr_fields)
        for _fname, _vals in sorted(_samples.items()):
            if not _vals:
                continue
            _content = (f"{_fname} | values: "
                        + VALUE_SAMPLE_SEP.join(_vals))
            _n = _norm("field_value", _fname, _content, protocol, src_name,
                       "@samples")
            if _n["norm_id"] in seen_ids:
                continue
            seen_ids.add(_n["norm_id"])
            norms.append(_n)

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


#: 缩进状态码表条目（`   211  System status, or system help reply`）。
#: ★ 只匹配**恰好三位**数字 + 空白 + 非空描述 ⇒ `2yz` / `4.2.3.` 不会命中。
_RE_INDENTED_STATUS = re.compile(r"^( {2,})(\d{3})[ \t]+(\S.*)$")


def _extract_status_code_entries(text: str) -> list[tuple[str, str]]:
    """从一段文本里抽取「缩进状态码表」→ [(code, reason), ...]。

    ★ 为什么需要（P1-2 实测）：RFC 5321 §4.2.3 *Reply Codes in Numeric Order*
      把 24 个回复码排成**缩进表格**，**没有逐码章节标题**：

          211  System status, or system help reply
          214  Help message (Information on how to use the receiver or the
                meaning of a particular non-standard command; ...)

      而原有的状态码通道只认**章节标题**形态（`^\\d{3}\\s+title`）——
      RFC 3261 §21 / RFC 2326 §11 的码是标题，故能抽到；RFC 5321 是表格，
      故抽成 **0 条**（实测）。

    判定（保守，协议无关）：
      ① 行首缩进 ≥2 空格，紧接**恰好三位**数字，其后空白 + 非空描述；
      ② 描述可**续行**（缩进比码行更深且非空、且不是下一条码行）⇒ 拼进
         ``reason``；空行继续看（RFC 用空行分隔条目）、遇到同级或更浅缩进即结束；
      ③ 同一 code 只取**首次**出现（§4.2.2「by Function Groups」与
         §4.2.3「in Numeric Order」会重复列出同一批码）。

    ★ 边界：调用方**必须**只在 ``kind == "status"`` 的窗口里调用它，
      否则正文里的「300 秒超时」之类三位数会被误当状态码。
    """
    if not text:
        return []
    raw = text.split("\n")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    i, n = 0, len(raw)
    while i < n:
        m = _RE_INDENTED_STATUS.match(raw[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        code = m.group(2)
        parts = [m.group(3).strip()]
        j = i + 1
        while j < n:
            line = raw[j]
            if not line.strip():
                j += 1
                continue
            if _RE_INDENTED_STATUS.match(line):
                break
            if len(line) - len(line.lstrip()) <= indent:
                break
            parts.append(line.strip())
            j += 1
        reason = " ".join(parts).strip()
        if code not in seen:
            seen.add(code)
            out.append((code, reason))
        i = j
    return out


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

#: ★ 2026-11-07：**表格数据行**（首列是数字或短横线范围）
#:   ⇒ 排除「数字 + 名称（缩写）」这类表格数据被误当命令条目。
#:   实测：RFC 6607 的 ``0  Network Virtual Terminal (NVT) ASCII VPN identifier``
#:   ⇒ 曾被误抽成方法 ``NVT``。
#:   ★ 注意：``_parse_heading`` 会先 ``strip()`` ⇒ 行首缩进**不可依赖**；
#:   核心判据是「**编号 + 2+ 空格 + 名称**」（真标题用单空格）。
_RE_TABLE_DATA_ROW = re.compile(
    r"^(?:\d+(?:\s*-\s*\d+)?|[0-9a-fA-F]{2,4})\s{2,}"
    r"[A-Z][A-Za-z0-9]")


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
        # ★ 2026-11-07：**表格数据行**排除 —— 首列是**数字/短横线**的
        #   「名称（缩写）」行是**表格数据**，不是命令条目。
        #   实测：RFC 6607 的 VSS 表
        #       ``0       Network Virtual Terminal (NVT) ASCII VPN identifier``
        #   ⇒ 被误抽成方法 ``NVT``（与 DHCP 消息类型无关）。
        #   判据：**名称前有数字列**（形如 ``<数字>  <名称>``）⇒ 表格行。
        if _RE_TABLE_DATA_ROW.match(raw[i]):
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

#: ABNF「命令规则 = "大写字面量"」形态（RFC 4954 §8 的 `auth-command = "AUTH" SP ...`）。
#: ★ 为什么只认 ``*-command`` 结尾的规则名：ABNF 里以引号字面量开头的规则很多
#:   （`version = "HTTP/1.1"` / `separator = "/"`），只有 **命令规则** 的
#:   规则名带 `-command` 后缀 ⇒ 用后缀做「这条规则描述的是命令」的客观判据，
#:   不靠协议特例。实测：smtp 由此补出 ``AUTH``（rfc4954），rtsp/sip 无命中。
_RE_ABNF_QUOTED_COMMAND = re.compile(
    r"^\s{0,8}[a-z][a-z0-9]*(?:-[a-z0-9]+)*-command\s*=\s*"
    r"\"([A-Z][A-Z0-9_\-]{1,19})\"",
    re.MULTILINE)


def _extract_abnf_quoted_commands(text: str) -> list[str]:
    """从 ABNF 的「``*-command = "VERB"``」规则里抽命令名（协议无关）。

    ★ 为什么需要（2026-11-06 实测）：RFC 4954 §8 用
        ``auth-command = "AUTH" SP sasl-mech [SP initial-response]``
      定义 ``AUTH``。它**不是**章节标题（§4 的标题是 "The AUTH Command"，
      全小写形态、无缩写括号），也**不是** hex 伴生规则
      （``_extract_abnf_methods`` 只认 ``INVITEm = %x49.4E...``）
      ⇒ 三种既有形态全都不命中 ⇒ smtp 的方法集漏掉 AUTH，
      只能靠 profile 骨架"补"，这在「RFC 单源」口径下就是污染。

    ★ 边界（诚实标注）：RFC 3207 的 ``STARTTLS`` **没有** ABNF 规则
      （正文只写 "The format for the STARTTLS command is: / STARTTLS"），
      ⇒ 本（ABNF）通道抽不到它；已由**形态 E**（散文命令格式声明）覆盖，
      见 :func:`_extract_prose_command_formats`。
    """
    return [m.group(1) for m in _RE_ABNF_QUOTED_COMMAND.finditer(text or "")]


#: 形态 E：**散文里的「命令格式声明」句式**（**协议无关**）。
#:   "The format of|for [the] <全大写词> command|method is|are"
#: ★ 判据是**句式**本身，不是协议名/命令名白名单 ⇒ 换协议无需改代码（G2）。
#: ★ 客观性：句中出现 "command|method" 这一**名词** ⇒ RFC 自己断言
#:   「<全大写词> 是一条命令」—— 与形态 D 靠 "-command" 规则名后缀判
#:   「这条规则描述的是命令」是同一思路：**用文本自身的证据**判定。
#: ★ 被捕获的词**必须全大写**（RFC 里命令/方法名一律大写）⇒ 不会把
#:   "the format of the local part" 之类散文里的普通名词误当命令。
_RE_PROSE_COMMAND_FORMAT = re.compile(
    r"\b(?:[Tt]he\s+)?(?:[Ff]ormat|[Ss]yntax)\s+(?:of|for)\s+(?:[Tt]he\s+)?"
    r"([A-Z][A-Z0-9_\-]{1,19})\s+(?:command|method)\s+(?:is|are)\b")


def _extract_prose_command_formats(
        lines: list[str],
        protocol: str = "",
        excludes: Iterable[str] = (),
) -> list[tuple[str, int]]:
    """形态 E：从散文里抽「命令格式声明」里的命令名（**协议无关**）。

    ★ 为什么需要形态 E（2026-11-07 实测缺口）：RFC 3207 用**散文**声明
      STARTTLS 的命令格式 ——
          "The format for the STARTTLS command is:" / "STARTTLS"
      它**既没有** ABNF 规则（形态 D 不命中）、也不是 "描述名 (缩写)" 形态
      （形态 A′ 不命中）⇒ 前四种形态全不命中 ⇒ smtp 的方法集漏掉 STARTTLS，
      只能靠 profile 骨架"补"（在「RFC 单源」口径下就是污染）。

    ★ 判据（**协议无关**，只认句式）：
      ① **句式**：``<format|syntax> of|for [the] <全大写词> command|method is|are``
         —— RFC 自己断言「<全大写词> 是一条命令」；
      ② **词形**：被捕获的词必须**全大写**（命令名的书写惯例）；
      ③ **排除**：RFC 关键字原子、配置排除名单、**协议自身名**
         （"the SMTP command" 里的 SMTP 是协议名，不是命令）。
      ⇒ 抽出的名字**逐字来自原文**，不臆造任何名字。

    ★ 段落处理：RFC 正文按 ~72 列**硬换行**，一句声明可能横跨多行 ⇒
      按**空行**切段、段内用空格拼回整句后再匹配。
      （页眉页脚/目录行不参与 ⇒ 避免把目录文字拼进正文造成误抽。）

    Args:
        lines: RFC 原文行（``read_text().splitlines()`` 口径，1-based 行号）。
        protocol: 协议名（小写）；用于排除「协议自身名」，空串则不排除。
        excludes: 额外的排除名（大小写不敏感，通常来自 rfc_config）。

    Returns:
        ``[(命令名, 原文行号), ...]``（按出现顺序，同名只保留首次出现）。
    """
    excl = {str(x).upper() for x in excludes}
    excl |= _METHOD_KEYWORD_ATOMS
    if protocol:
        excl.add(protocol.upper())

    # ---- ① 切段：空行分隔；页眉页脚/目录行不参与 ----
    paras: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for _i, _raw in enumerate(lines, start=1):
        _s = _raw.strip()
        if (not _s or _RE_PAGE_MARK.search(_s) or _RE_RFC_TITLE.match(_s)
                or _is_toc_line(_s)):
            if cur:
                paras.append(cur)
                cur = []
            continue
        cur.append((_i, _s))
    if cur:
        paras.append(cur)

    # ---- ② 逐段匹配句式 ----
    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for _para in paras:
        _parts = [_s for _, _s in _para]
        _segs: list[tuple[int, int, int]] = []
        _off = 0
        for _ln, _s in _para:
            _segs.append((_off, _off + len(_s), _ln))
            _off += len(_s) + 1        # +1 = 段内拼接用的空格
        _text = " ".join(_parts)
        for _m in _RE_PROSE_COMMAND_FORMAT.finditer(_text):
            _name = _m.group(1)
            if _name in seen or _name.upper() in excl:
                continue
            _ln = _para[0][0]
            for _s0, _s1, _no in _segs:
                if _s0 <= _m.start(1) < _s1:
                    _ln = _no
                    break
            seen.add(_name)
            out.append((_name, _ln))
    return out


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




# ===========================================================================
# ★ 批次 2.2（P1b）：LLM 抽状态机（**服务端** / 散文 / ASCII 图）
# ===========================================================================
#
# ★ 为什么需要：P1a（通道 F）只能抽**三列定宽表格** ⇒ 只覆盖 RTSP 的
#   **客户端**状态机（A.1，14 条）。而：
#     · RTSP A.2 **服务端**状态机是**散文描述**（"The server can assume
#       the following states: Init: … Ready: …"）⇒ 表格抽不到
#     · SIP RFC 3261 §17 的状态机是 **ASCII 状态图** ⇒ 表格抽不到
#   ⇒ 实测开启通道 F 后 rtsp transitions 38 → 12 条、种子 58 → 17 条
#     （**覆盖 -70%**）⇒ 只做 P1a 不够 ⇒ 需要 LLM 补齐。
#
# ★ 确定性保障：**磁盘缓存**（按候选段落的 block_hash 判定）
#   ⇒ 同一份 RFC ⇒ 命中缓存 ⇒ **不调 LLM** ⇒ 产物逐字节可复现。
#
#: 状态机段落的定位：全文里含「state machine」的**行**⇒ 取其前后文本。
_RE_STATE_MACHINE_HINT = re.compile(r"state\s+machines?", re.IGNORECASE)

#: 单个候选段落的最大行数（前后各取多少行）
_TRANSITION_CONTEXT_LINES = 60

#: LLM 输出契约（JSON）
_PROMPT_TRANSITION = """你是协议规范分析助手。下面的文本来自 {protocol} 协议的 RFC 规范，其中包含
**状态机**描述（可能是自然语言描述、状态图、状态表）。

请抽取其中**明确写出的状态转移**，输出 JSON：
{{"transitions": [{{"from": "<源状态名>", "method": "<触发方法名>", "to": "<目标状态名>"}}]}}

规则：
1. 只抽**规范里明确写出**的转移，不要推测、不要补充 RFC 之外的常识。
2. `method` 用规范里的**方法/命令名**（如 SETUP / PLAY / INVITE）。
3. 状态名**照抄规范里的写法**，不要归一化大小写或改名。
4. 抽不到就返回 {{"transitions": []}}。

文本：
{text}
"""

#: 提示词的**契约版本标识** —— 并入 LLM 缓存键
#: （``block_hash = sha256(prompt_version + 各候选块 hash)``）
#: ⇒ **改动提示词内容必须同步改它**，否则会读到旧缓存、改动静默不生效。
TRANSITION_PROMPT_VERSION = "rfc-transition-prose"


def extract_transition_candidates(protocol: str) -> list[dict]:
    """定位 RFC 里的**状态机段落**（供 LLM 抽状态转移）。

    ★ 定位方式：全文扫含「state machine」的行 ⇒ 取该行**前 60 行 / 后 60 行**
      的上下文 ⇒ 拼成候选段落。
      ⇒ RTSP 的 A.1/A.2、SIP 的 §17（ASCII 图）都能被覆盖。

    Returns:
        ``[{"text": 段落文本, "source": "file:...#@N", "hash": 段落哈希}, ...]``
    """
    import hashlib
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        hits = [i for i, ln in enumerate(lines)
                if _RE_STATE_MACHINE_HINT.search(ln)]
        if not hits:
            continue
        # 合并相邻命中（间隔 < 20 行 ⇒ 同一段落）
        groups: list[list[int]] = []
        for i in hits:
            if groups and i - groups[-1][-1] < 20:
                groups[-1].append(i)
            else:
                groups.append([i])
        for g in groups:
            lo = max(0, g[0] - _TRANSITION_CONTEXT_LINES)
            hi = min(len(lines), g[-1] + _TRANSITION_CONTEXT_LINES)
            text = "\n".join(lines[lo:hi]).strip()
            if not text:
                continue
            out.append({
                "text": text,
                "source": f"file:{f.name}#@{g[0] + 1}",
                "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "_file": f.name, "_lo": lo, "_hi": hi,
            })
    # ★ 合并**重叠**的候选段落（相邻命中常在同一小节 ⇒ 文本高度重叠）
    #   ⇒ 否则会重复调 LLM（成本浪费 + 重复转移）。
    merged: list[dict] = []
    for cand in sorted(out, key=lambda c: (c["_file"], c["_lo"])):
        if (merged and merged[-1]["_file"] == cand["_file"]
                and cand["_lo"] <= merged[-1]["_hi"]):
            prev = merged[-1]
            if cand["_hi"] > prev["_hi"]:
                prev["_hi"] = cand["_hi"]
                prev["_text_lo"] = prev["_lo"]
            continue
        merged.append(dict(cand))
    out = []
    for cand in merged:
        lines_all = None
        # 重新取合并后的文本
        src_file = cand["_file"]
        fpath = spec_dir / src_file
        if fpath.is_file():
            lines_all = fpath.read_text(encoding="utf-8",
                                        errors="ignore").splitlines()
        lo = cand.get("_text_lo", cand["_lo"])
        hi = cand["_hi"]
        if lines_all is not None:
            cand["text"] = "\n".join(lines_all[lo:hi]).strip()
            cand["source"] = f"file:{src_file}#@{lo + 1}"
            cand["hash"] = hashlib.sha256(
                cand["text"].encode("utf-8")).hexdigest()
        cand.pop("_file", None)
        cand.pop("_lo", None)
        cand.pop("_hi", None)
        cand.pop("_text_lo", None)
        out.append(cand)
    return out



# ===========================================================================
# 状态机抽取的**质量闸**（协议无关）
# ===========================================================================



# ===========================================================================
# F 阶段 F1：RFC 源的**消息级必填头**（LLM，默认关闭）
# ===========================================================================

_PROMPT_REQUIRED_HEADER = """你是协议规范分析助手。下面是 {protocol} 协议 RFC 规范中的相关章节。

请判断：该协议的**每一个请求报文**都必须携带哪些头部字段？

只输出 JSON：
{{"required_headers": [{{"name": "<头名>", "evidence": "<RFC 原句>"}}]}}

规则：
1. 只收**所有请求都必带**的头（例如消息序号、会话标识、传输参数这类协议级必带项）。
2. ★ **不要**收：
   - 只在**响应**里出现的头（响应码、认证挑战等）；
   - **条件性**必填的头（"仅当……时 MUST"）；
   - 内容协商类可选头（Accept*、Content-Type 等可选项）；
   - 方法专属的头（只对某一个方法必带）。
3. `name` 必须**原样照抄**下面列表里的头名（不要自造、不要改大小写）：
   {allowed}
4. `evidence` 给出 RFC 原句（可截断到 160 字）。
5. 判不出就返回空列表。

{body}
"""

_PROMPT_METHOD_REQUIRED_HEADER = """你是协议规范分析助手。下面是 {protocol} 协议 RFC 规范的相关章节。

请判断：**每个请求方法**分别**必须**携带哪些头部字段？

只输出 JSON：
{{"methods": [{{"method": "<方法名>", "headers": [{{"name": "<头名>", "evidence": "<RFC 原句>"}}]}}]}}

规则：
1. 只收该方法的**请求报文**里**必带**的头。
2. ★ **不要**收：
   - 只在**响应**里出现的头；
   - **条件性**必填的头（"仅当……时 MUST"）；
   - 内容协商类**可选**头（Accept*、Content-Type 等）；
   - **协议级通用**的头（每个方法都必带的那些，如消息序号）——
     ★ 那些由消息级抽取负责，本题只问**该方法特有**的。
3. `method` 必须原样照抄下面的方法名；`name` 必须原样照抄下面的头名。
4. `evidence` 给出 RFC 原句（可截断到 160 字）。
5. 判不出就返回空列表。

【方法名】
{methods}

【可用头名】
{allowed}

{body}
"""

#: 方法级必填头 prompt 的契约版本（并入缓存键）
METHOD_REQUIRED_HEADER_PROMPT_VERSION = "v1"

#: 提示词的**契约版本标识** —— 并入 LLM 缓存键（同 ``TRANSITION_PROMPT_VERSION``）
REQUIRED_HEADER_PROMPT_VERSION = "rfc-required-header-llm"


def _rfc_source_headers(protocol: str, cfg: dict) -> set[str]:
    """该协议**RFC 源**里的头名集合（数据驱动：`rfc_config.field_sections`）。

    ★ 做法：在 `field_sections` 声明的**头字段章节**里，取「编号 + 头名」形态
      的标题（如 `12.10 CSeq`）⇒ 即该协议的头名集合。
    ★ 换协议只改 rfc_config，不改代码（G2）。

    ★ 2026-11-07（B2）补 **ABNF 兜底**：有些 RFC 的字段章节**不按「编号+头名」**
      组织 —— 典型是 RFC 5322 §3.6：它的子节标题是**描述性文字**
      （如 ``3.6.1.  The Origination Date Field``、``3.6.3.  Destination
      Address Fields``），头名只出现在 **ABNF 定义**里（如 ``from = 'From:'``）。
      ⇒ 只按标题形态抽 ⇒ 实测 smtp 只得到 1 个头（``Background``，还是误抽），
        RFC 5322 的 20+ 个邮件头**全丢**（Date/From/To/Subject…）。
      ⇒ 追加一条**协议无关**的兜底：从全文的 ABNF 定义里取头名
        （形如 ``<rule> = 'Head:'``）。
    """
    import re as _re
    secs = cfg.get("field_sections") or []
    if not secs:
        return set()
    out: set[str] = set()
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        for _ln in _f.read_text(encoding="utf-8", errors="ignore").splitlines():
            _m = _re.match(r"^(\d+(?:\.\d+)*)\.?\s+(\S[^\s].*?)\s*$",
                           _ln.strip())
            if not _m:
                continue
            _num, _title = _m.group(1), _m.group(2)
            if not any(_num == _x or _num.startswith(_x + ".")
                       for _x in secs):
                continue
            if _re.match(r"^[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*$", _title):
                out.add(_title)
    # ---- ABNF 兜底（B2 2026-11-07）：从 ABNF 定义的**字面量头名**取头名 ----
    #   协议无关：只认 ABNF 的字面量头名形态（形如 ``<rule> = 'Head:'``）。
    #   ★ 为什么需要：有些 RFC 的字段章节**不按「编号+头名」**组织 ——
    #     典型是邮件格式规范（RFC 5322）的 §3.6：子节标题是**描述性文字**
    #     （如 ``3.6.3.  Destination Address Fields``）⇒ 上面那条
    #     「编号+头名」的路径拿不到任何头名 ⇒ 该规范的 20+ 个邮件头全丢。
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        _txt = _f.read_text(encoding="utf-8", errors="ignore")
        for _m in _RE_ABNF_FIELD.finditer(_txt):
            _n = _m.group(1)
            if _re.match(r"^[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*$", _n):
                out.add(_n)
    return out


#: 消息级必填的两种**规范原文表述**（协议无关，不依赖章节号/协议名）：
#:   A) 枚举式（SIP §8.1.1）：``MUST, at a minimum, contain the following
#:      header fields: To, From, CSeq, Call-ID, Max-Forwards, and Via``
#:   B) 逐头式（RTSP §12.17）：``This field MUST be present in all requests``
_REQ_ENUM_RE = re.compile(
    r"MUST[^.]{0,80}?contain\s+the\s+following\s+header\s+fields?\s*:\s*"
    r"([^.;]{3,400})",
    re.IGNORECASE | re.DOTALL)
_REQ_PER_HEADER_RE = re.compile(
    r"MUST\s+be\s+present\s+in\s+all\s+(?:SIP\s+)?requests?", re.IGNORECASE)
#: 头定义章节标题（``12.17 CSeq`` / ``20.42 Via``）—— 逐头式窗口的边界
_REQ_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+(\S[A-Za-z0-9-]*)\s*$")


def _deterministic_message_required_headers(
        protocol: str, known: set[str]) -> dict[str, str]:
    """**确定性**抽「消息级必填头」⇒ ``{头名: RFC 原句证据}``。

    ★ 为什么需要它（2026-11-06 实测）：只用 LLM 时，RTSP §12 的**头部汇总表**
      （``CSeq g req. all`` / ``Unsupported r req. all``）会被 LLM 把 ``req.``
      （= request header）误读成「required」⇒ 抽出 Require / Proxy-Require /
      Unsupported 三个**假阳性**。本函数给出可审计的确定性裁决。

    ★ 覆盖两种规范写法（协议无关）：
      A) **枚举式**：``MUST ... contain the following header fields: X, Y, Z``
      B) **逐头式**：头定义章节内 ``<Head> ... MUST be present in all requests``
    ★ 窗口在**下一个章节标题**处截断 —— 否则会「借用」邻节的 MUST 句
      （实测 v1 因此把 Content-Length / Content-Language 误判为必填）。

    Args:
        protocol: 协议名（决定读哪份 RFC 原文）。
        known: 该协议 RFC 源的头名全集（``_rfc_source_headers``）。

    Returns:
        ``{头名: 证据句}``；判不出时返回空字典（**宁缺勿滥**）。
    """
    if not known:
        return {}
    lines: list[str] = []
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        lines.extend(
            _f.read_text(encoding="utf-8", errors="ignore").splitlines())
    if not lines:
        return {}
    full = "\n".join(lines)
    hits: dict[str, str] = {}

    # A) 枚举式（SIP §8.1.1 风格）
    for _m in _REQ_ENUM_RE.finditer(full):
        _frag = _m.group(1)
        for _h in known:
            if re.search(r"\b" + re.escape(_h) + r"\b", _frag):
                hits.setdefault(_h, " ".join(_frag.split())[:200])

    # B) 逐头式（RTSP §12.17 风格；窗口在下一个章节标题处截断）
    for _i, _ln in enumerate(lines):
        _m = _REQ_HEADING_RE.match(_ln.strip())
        if not _m or _m.group(1) not in known:
            continue
        _name = _m.group(1)
        _body: list[str] = []
        for _j in range(_i + 1, min(_i + 40, len(lines))):
            if _REQ_HEADING_RE.match(lines[_j].strip()):
                break
            _body.append(lines[_j])
        _blob = "\n".join(_body)
        _mm = _REQ_PER_HEADER_RE.search(_blob)
        if _mm:
            _s = max(0, _mm.start() - 120)
            hits.setdefault(
                _name, " ".join(_blob[_s:_mm.end() + 40].split())[:200])
    return hits


#: ★ 2026-11-07：**示例请求里出现的头** ≠ 必填头。
#:   RFC 的方法章节示例常带**可选**头（``Date`` / ``Content-Type`` / ``Content-Length``
#:   / ``Accept`` / ``Require`` / ``Proxy-Require`` / ``Public`` / ``Location`` …），
#:   把它们当必填会造成**假阳性**（种子多带无关头，掩盖真缺项）。
#:   ⇒ 只保留「该方法**结构性依赖**」的头：出现在**两个以上**方法的示例里
#:   （= 协议级通用头，如 CSeq / Session / Transport）或
#:   被 RFC 明确表述为该方法的必需头。
#:   ★ 这是**跨方法统计**出来的，不是硬编码名单 ⇒ 协议无关。
_METHOD_EXAMPLE_OPTIONAL_HINT = ("date", "content-type", "content-length",
                                "content-base", "accept", "require",
                                "proxy-require", "public", "location",
                                "note", "expires", "allow", "supported",
                                "bandwidth", "user-agent", "referer",
                                "from", "to", "call-id", "max-forwards",
                                "via", "contact", "event")


def _method_example_required_headers(
        protocol: str, known: set[str],
        methods: Optional[set[str]] = None) -> dict[str, dict[str, str]]:
    """**确定性**抽「方法级必填头」⇒ ``{方法名: {头名: RFC 原句证据}}``。

    ★ 判据（**协议无关**，只用 RFC 结构）：
      ① 定位每个方法的**章节**（形如 ``10.4 SETUP`` 的标题行）；
      ② 在该章节内找**示例请求**（``C->S: <METHOD> ...`` 之后的缩进头行）；
      ③ 收集这些头名 → 统计**跨方法出现频次**；
      ④ **出现在 ≥2 个方法示例里**的头 ⇒ 判为「协议级通用必填头」
         （如 CSeq 出现在每个方法、Session 出现在所有会话内方法）；
         **只出现在 1 个方法**的头 ⇒ 判为「该方法特有」，**不自动判必填**
         （可能是可选头）⇒ 留给 LLM 兜底判定。
      ⇒ 协议无关：新协议用同一套判据，不认任何协议名或头名。

    ★ 为什么不做「示例里出现就是必填」：实测 RTSP §10.2 DESCRIBE 的示例带
      ``Accept`` / ``Date`` / ``Content-Type`` / ``Content-Length``，
      其中只有部分是真必填 ⇒ 直接采信会抽 4 个假阳性。

    Returns:
        ``{方法名: {头名: 证据}}``；判不出返回空字典（**宁缺勿滥**）。
    """
    if not known:
        return {}
    _methods = {str(m).strip().upper() for m in (methods or set())}
    if not _methods:
        return {}
    lines: list[str] = []
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        lines.extend(
            _f.read_text(encoding="utf-8", errors="ignore").splitlines())
    if not lines:
        return {}

    # ① **形态无关**地扫「示例请求块」：一个**请求行**（首词是方法名）
    #    + 其后连续的「头名: 值」行。
    #    ★ 为什么不用「章节定位」：RFC 的示例位置差异极大 ——
    #      RTSP 是 ``10.4 SETUP`` 章节内、示例带 ``C->S:`` 前缀；
    #      SIP 的示例是**独立成块**（§3 概览图旁）、**无前缀**、无方法章节。
    #      ⇒ 改成「扫全文找请求块」，两种协议都能命中，且不认协议名。
    #
    #    请求行判据：首 token 是**全大写词**（方法/命令名惯例），
    #    且该 token 在 ``known_methods`` 里（避免把散文行当请求）。
    _per_method: dict[str, dict[str, str]] = {}
    _i = 0
    _n = len(lines)
    while _i < _n:
        _st = lines[_i].strip()
        # ★ 先剥掉方向前缀（`C->S:` / `UAC->UAS:` 等）再匹配 —— 否则前缀后
        #   残留的前导空格会让 `^` 锚点失效（实测踩过）。
        _st = re.sub(r"^[A-Za-z]+(?:->[A-Za-z]+)+:\s*", "", _st)
        _m = re.match(r"^([A-Z][A-Za-z0-9_-]*)\s+\S", _st)
        if not _m:
            _i += 1
            continue
        _meth = _m.group(1)
        if _meth not in _methods:
            _i += 1
            continue
        # 请求行之后：连续的「头名: 值」行（缩进 ≥3 空格或原样缩进）
        _hdrs: dict[str, str] = {}
        _j = _i + 1
        while _j < _n:
            _h = lines[_j].strip()
            if not _h:
                break                          # 空行 ⇒ 块结束
            _hm = re.match(r"^([A-Z][A-Za-z0-9-]*):\s*(.+)$", _h)
            if not _hm:
                break
            _name = _hm.group(1)
            if _name.lower() in _METHOD_EXAMPLE_OPTIONAL_HINT:
                _j += 1
                continue
            if _name in known:
                _hdrs.setdefault(_name, _h[:200])
            _j += 1
        if _hdrs:
            _per_method.setdefault(_meth, {}).update(_hdrs)
            _i = _j
        else:
            _i += 1

    # ③ 统计跨方法频次
    _freq: collections.Counter = collections.Counter()
    for _hdrs in _per_method.values():
        for _h in _hdrs:
            _freq[_h] += 1

    # ④ 只保留「≥2 个方法都出现」的头 ⇒ 协议级通用必填头
    out: dict[str, dict[str, str]] = {}
    for _meth, _hdrs in _per_method.items():
        _keep = {h: ev for h, ev in _hdrs.items() if _freq[h] >= 2}
        if _keep:
            out[_meth] = _keep
    return out


#: ★ 2026-11-07：**头汇总表**的行格式（RFC 2326 §12 那种「头 → 方向 → 必填性 → 方法」表）。
#:   格式：``<头名>  <方向标记>  <req.|opt.>  <适用方法>``
#:   方向标记：``r``=仅响应 / ``R``=双向 / ``g``=仅请求 / ``e``=实体头
#:   ★ **``req.`` 才是「请求必带」**，``opt.`` 是可选 ⇒ 这是**权威且精确**的判据，
#:     比 LLM 判定可靠得多。
#:   ★ 方向标记可能是**一个或两个字母**（实测 RTSP 有 ``Rr`` = 双向）⇒ 用 ``[RrGgEe]+``。
_METHOD_HEADER_TABLE_RE = re.compile(
    r"^\s{2,}([A-Z][A-Za-z0-9-]*)\s+([RrGgEe]+)\s+(req\.|opt\.)\s+(.+?)\s*$")


def _deterministic_method_required_headers(
        protocol: str, known: set[str],
        methods: set[str]) -> dict[str, dict[str, str]]:
    """**确定性**抽「方法级必填头」⇒ ``{方法名: {头名: 证据}}``。

    ★ 依据：RFC 里的**头汇总表**（如 RFC 2326 §12「Header Quick Reference」）：
      ``<头名>  <方向>  req.|opt.  <适用方法>``
      ⇒ ``req.`` 行里点名的方法 ⇒ 该头对该方法**必带**。

    ★ 为什么这条比 LLM 可靠：LLM 会把表里的 ``r req. PLAY`` 读成「PLAY 请求
      必带 RTP-Info」（实测），而 ``r`` 表示**仅响应** ⇒ 假阳性。
      确定性解析直接看方向标记 ⇒ 不会有方向误读。

    ★ 方向标记的语义（协议无关的通用记号）：
      · ``r`` = response only（仅响应）⇒ **请求不需要**；
      · ``R`` = request & response（双向）；
      · ``g`` = general/request（仅请求）；
      · ``e`` = entity（实体头，多半是可选）。
      ⇒ 只收 ``R`` / ``g`` 方向的 ``req.`` 行。

    ★ 没有汇总表的协议（SIP 就没有）⇒ 返回空字典 ⇒ 由 LLM 兜底。

    Returns:
        ``{方法名: {头名: 证据}}``。
    """
    if not known or not methods:
        return {}
    lines: list[str] = []
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        lines.extend(
            _f.read_text(encoding="utf-8", errors="ignore").splitlines())
    out: dict[str, dict[str, str]] = {}
    for _ln in lines:
        _m = _METHOD_HEADER_TABLE_RE.match(_ln.rstrip())
        if not _m:
            continue
        _name, _dirn, _req, _scope = _m.group(1), _m.group(2), _m.group(3), _m.group(4)
        if _name not in known:
            continue
        if _req != "req.":
            continue                     # opt. ⇒ 可选，不是必填
        # 方向：含 'e' ⇒ 实体头；含 'r' 且**不含** 'g'/'R' ⇒ 仅响应
        _dl = _dirn.lower()
        if "e" in _dl:
            continue                     # 实体头 ⇒ 请求侧不需要
        if "r" in _dl and "g" not in _dl and "R" not in _dirn:
            continue                     # 仅响应（如 'r' / 'Rr'）⇒ 请求侧不需要
        # 适用方法：逗号分隔。
        # ★ 必须处理 ``all but X``（排除项）—— 实测 RTSP 写的是
        #   ``Session  Rr  req.  all but SETUP, OPTIONS``
        #   ⇒ Session 对 SETUP/OPTIONS **不适用**（客户端那时还没有 Session，
        #   它是服务器在 SETUP 响应里分配的，§12.37）。
        #   ★ 早先的 `.replace("all but", "")` 恰好把排除项**也删掉了**
        #   ⇒ 反向假阳性（给 SETUP/OPTIONS 加了 Session）。
        _excl: set[str] = set()
        _scope_txt = _scope
        if "all but" in _scope_txt.lower():
            _head, _tail = re.split(r"all\s+but", _scope_txt, flags=re.I)
            _excl = {x.strip().upper() for x in _tail.split(",") if x.strip()}
            _scope_txt = _head
        _hit = [m for m in methods
                if m.upper() not in _excl
                and re.search(r"\b" + re.escape(m) + r"\b", _scope_txt)]
        if not _hit:
            continue
        for _mm in _hit:
            out.setdefault(_mm, {}).setdefault(_name, _ln.strip()[:200])
    return out


def infer_method_required_headers(protocol: str, llm=None) -> list[dict]:
    """抽「**方法级**必填头」⇒ RFC 源的 ``required_header_by_method`` norm。

    ── 与消息级的分工（2026-11-07 设计，实测得出）──────────────────────────────
      · **消息级**（`infer_required_headers`）：每个请求都必带的头
        （rtsp → CSeq；sip → CSeq/Call-ID/From/Max-Forwards/To/Via）
        —— 由 RFC 的「所有请求 MUST 含 X」这类**规范表述**判定。
      · **方法级**（本函数）：**只该方法**必带的头
        （rtsp → SETUP 的 Transport、RECORD 的 Session；
          sip → REGISTER 的 Contact、SUBSCRIBE 的 Event）
        —— 只能从**方法章节的语义**判定。

    ★ **为什么不用「示例请求里出现的头」当判据**（实测踩过）：
      RFC 示例常带**可选**头 ⇒ 直接采信会出**假阳性**。实测 RTSP：
        PLAY  示例带 Range ⇒ 但 RFC 原文明说「A PLAY request without a
              Range header is legal」⇒ Range **不是**必填；
        SETUP 示例带 Session ⇒ 但 Session 是**服务器在 SETUP 响应里**分配的
              （§3.4「a session identifier MUST be chosen randomly」）
              ⇒ 客户端 SETUP 请求**还没有** Session。
      ⇒ 示例法只能当**候选生成器**，判定必须靠规范语义 ⇒ **LLM 兜底**。

    ★ 抽取策略（与消息级对称）：
      ① **候选生成**：方法章节的散文块（形态层的 normative/table 块）
         —— 协议无关、位置无关；
      ② **LLM 判定**：只问「该方法特有必填头」，prompt 明确排除
         协议级通用头（那些由消息级负责）；
      ③ **证据锚点**：每条都带 RFC 原句（⇒ M3 可验证率可算）。

    ★ **不臆造**：判不出就不产出；`authority` 仍记 RFC（`source_class` 走
      `normative_spec`）⇒ 不污染「RFC 单源纯净度」口径 ——
      它的底料是 RFC 文本，与消息级抽取同性质。

    Returns:
        ``[{"method": ..., "name": ..., "evidence": ..., "source": ...}, ...]``
    """
    from core.fused.rfc_forms import split_form_blocks
    from core.fused.source_retrieval import CACHE_DIR
    cfg = _load_rfc_config(protocol)
    if not cfg.get("enable_required_headers"):
        return []
    known = _rfc_source_headers(protocol, cfg)
    methods = _rfc_source_methods(protocol, cfg)
    if not known or not methods:
        return []

    # ---- ① 确定性优先：**头汇总表**（若该协议有）------------------------
    _det = _deterministic_method_required_headers(protocol, known, methods)
    if _det:
        _rows = [{"method": _m, "name": _h,
                  "evidence": _ev, "source": "rfc:header-table"}
                 for _m, _hs in sorted(_det.items())
                 for _h, _ev in sorted(_hs.items())]
        norms: list[dict] = []
        for _row in _rows:
            _n2 = _norm("required_header_by_method", _row["name"],
                        f"method={_row['method']};name={_row['name']}",
                        protocol, _row["source"], "@rfc-method-required-header")
            _n2["name"] = _row["name"]
            _n2["method"] = _row["method"]
            _n2["evidence"] = _row["evidence"]
            norms.append(_n2)
        return norms

    # ---- ② 候选：形态层块（含方法名 + 至少 1 个已知头名）--------------
    cands: list[dict] = []
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        _lines = _f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for _b in split_form_blocks(_lines):
            if _b.kind not in ("table", "normative", "prose"):
                continue
            _txt = _b.text
            _hit_m = [m for m in methods if re.search(r"\b" + re.escape(m) + r"\b", _txt)]
            if not _hit_m:
                continue
            _hit_h = [h for h in known if re.search(r"\b" + re.escape(h) + r"\b", _txt)]
            if len(_hit_h) < 1:
                continue
            cands.append({"text": _txt, "source": f"rfc:{_f.name}",
                          "methods": _hit_m, "headers": _hit_h})
    if not cands:
        return []

    # ---- ② LLM 判定（带磁盘缓存）---------------------------------------
    if llm is None:
        from core.llm import DeepSeekClient
        llm = DeepSeekClient()
    cache_file = CACHE_DIR / f"{protocol}.method_required_headers.json"
    block_hash = hashlib_sha256("|".join(
        [METHOD_REQUIRED_HEADER_PROMPT_VERSION]
        + [c["hash"] if "hash" in c else c["text"] for c in cands]))
    _rows: list[dict] | None = None
    if cache_file.exists():
        try:
            _cached = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _cached = None
        if (isinstance(_cached, dict)
                and _cached.get("block_hash") == block_hash):
            _rows = _cached.get("rows")
    if _rows is None:
        _rows = []
        allowed = ", ".join(sorted(known))
        mnames = ", ".join(sorted(methods))
        for _c in cands:
            try:
                _r = llm.chat_json(
                    system="你输出 JSON。",
                    user=_PROMPT_METHOD_REQUIRED_HEADER.format(
                        protocol=protocol.upper(), allowed=allowed,
                        methods=mnames,
                        body=_c["text"][:7000]),
                    temperature=0.0, max_tokens=2000)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(_r, dict):
                continue
            for _m in (_r.get("methods") or []):
                if not isinstance(_m, dict):
                    continue
                _mn = str(_m.get("method", "")).strip().upper()
                if _mn not in methods:
                    continue
                for _h in (_m.get("headers") or []):
                    if not isinstance(_h, dict):
                        continue
                    _hn = str(_h.get("name", "")).strip()
                    if not _hn or _hn not in known:
                        continue
                    # ★ 去重：同一 (method, name) 只留**第一条**证据
                    #   （实测 LLM 会对同一方法重复输出同一头，INVITE→Contact×4）
                    if any(r["method"] == _mn and r["name"] == _hn
                           for r in _rows):
                        continue
                    _rows.append({
                        "method": _mn, "name": _hn,
                        "evidence": str(_h.get("evidence", ""))[:300],
                        "source": _c["source"]})
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(
                {"block_hash": block_hash, "rows": _rows},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    # ---- ②′ 读缓存后**再去一次重**（缓存里可能已有重复，LLM 会重复输出）----
    _seen_pairs: set[tuple[str, str]] = set()
    _deduped: list[dict] = []
    for _r in _rows:
        _k = (str(_r.get("method", "")).strip().upper(),
              str(_r.get("name", "")).strip())
        if not _k[0] or not _k[1] or _k in _seen_pairs:
            continue
        _seen_pairs.add(_k)
        _deduped.append(_r)
    if len(_deduped) != len(_rows):
        print(f"[必填头·方法级] {protocol}: 去重 {len(_rows)} → {len(_deduped)} 条")
    _rows = _deduped

    # ---- ③ 排除**消息级通用头**（确定性兜底）-----------------------------
    #   prompt 已要求 LLM 排除协议级通用头，但实测 LLM 仍会输出
    #   （sip ACK → CSeq/Call-ID/From/To/Via）⇒ 在此**确定性剔除**：
    #   凡是已由消息级抽取认定的头，一律不算「方法特有」。
    _global_heads = {str(r.get("name", "")).strip()
                     for r in infer_required_headers(protocol)}
    if _global_heads:
        _before = len(_rows)
        _rows = [r for r in _rows if r["name"] not in _global_heads]
        if len(_rows) != _before:
            print(f"[必填头·方法级] {protocol}: 剔除消息级通用头 "
                  f"{sorted(_global_heads)} ⇒ {len(_rows)}/{_before} 条")

    # ---- ④ norm 化（kind=required_header_by_method）--------------------
    norms: list[dict] = []
    for _row in _rows:
        _mn = str(_row.get("method", "")).strip()
        _hn = str(_row.get("name", "")).strip()
        if not _mn or not _hn:
            continue
        _n2 = _norm("required_header_by_method", _hn,
                    f"method={_mn};name={_hn}", protocol,
                    str(_row.get("source", "")), "@rfc-method-required-header")
        _n2["name"] = _hn
        _n2["method"] = _mn
        _n2["evidence"] = str(_row.get("evidence", ""))
        norms.append(_n2)
    return norms


def infer_required_headers(protocol: str, llm=None) -> list[dict]:
    """抽「消息级必填头」⇒ RFC 源的 ``required_header_global`` norm。

    ★ **三级证据策略**（StatePre §3.2.1 结构化优先 / §3.2.2 LLM 兜底）：
      ① **确定性判据**（首选，**零 LLM 调用**）：从 RFC 原文找两种规范表述
         —— 枚举式 / 逐头式。实测：rtsp → CSeq（§12.17）；
         sip → To/From/CSeq/Call-ID/Max-Forwards/Via（§8.1.1）
         （与 LLM 结果**双向印证**）。
      ② **LLM 兜底**：确定性判据**判不出**时才调 LLM（带磁盘缓存）。
      ③ ★ 为什么确定性优先：实测只用 LLM 时，RTSP §12 的**头部汇总表**
         （``CSeq g req. all`` / ``Unsupported r req. all``）会被把 ``req.``
         （= request header）误读成「required」⇒ 抽 3 个**假阳性**
         （Require / Proxy-Require / Unsupported）。

    ★ **默认关闭**（`rfc_config.enable_required_headers`）⇒ 产物逐字节不变。
    """
    from core.fused.rfc_forms import split_form_blocks
    from core.fused.source_retrieval import CACHE_DIR
    cfg = _load_rfc_config(protocol)
    if not cfg.get("enable_required_headers"):
        return []
    known = _rfc_source_headers(protocol, cfg)
    if not known:
        return []

    # ---- ① 确定性判据（首选，零 LLM 调用）---------------------------
    _det = _deterministic_message_required_headers(protocol, known)
    if _det:
        rows: list[dict] = [
            {"name": _n, "evidence": _e, "source": "rfc:deterministic"}
            for _n, _e in sorted(_det.items())]
    else:
        # ---- ② 兜底：LLM（带磁盘缓存）------------------------------
        rows = []
        if llm is None:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        # 候选：形态层的 table + normative 块（协议无关、位置无关）
        cands: list[dict] = []
        for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
            _lines = _f.read_text(
                encoding="utf-8", errors="ignore").splitlines()
            for _b in split_form_blocks(_lines):
                if _b.kind not in ("table", "normative"):
                    continue
                # ★ 候选**相关性过滤**：块内至少出现 2 个已知头名 ⇒ 才是候选。
                #   必要性（实测）：不加过滤时某协议有 **312** 个候选块 ⇒ 312 次
                #   LLM 调用且引入大量噪声；加过滤后降到 8 / 58 个。
                _hits = sum(1 for _h in known if _h in _b.text)
                if _hits < 2:
                    continue
                cands.append({"text": _b.text, "kind": _b.kind,
                              "hash": hashlib_sha256(_b.text),
                              "source": f"file:{_f.name}#@{_b.line_start}"})
        if cands:
            cache_file = CACHE_DIR / f"{protocol}.required_headers.json"
            # ★ E′（2026-11-06）：缓存键**并入 prompt_version**（同 infer_transitions）
            block_hash = hashlib_sha256("|".join(
                [REQUIRED_HEADER_PROMPT_VERSION]
                + [c["hash"] for c in cands]))
            _rows: list[dict] | None = None
            if cache_file.exists():
                try:
                    _cached = json.loads(
                        cache_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    _cached = None
                if (isinstance(_cached, dict)
                        and _cached.get("block_hash") == block_hash):
                    _rows = _cached.get("rows")
            if _rows is None:
                _rows = []
                allowed = ", ".join(sorted(known))
                for _c in cands:
                    try:
                        _r = llm.chat_json(
                            system="你输出 JSON。",
                            user=_PROMPT_REQUIRED_HEADER.format(
                                protocol=protocol.upper(), allowed=allowed,
                                body=_c["text"][:7000]),
                            temperature=0.0, max_tokens=2000)
                    except Exception:  # noqa: BLE001
                        continue
                    if not isinstance(_r, dict):
                        continue
                    for _it in (_r.get("required_headers") or []):
                        if not isinstance(_it, dict):
                            continue
                        _n = str(_it.get("name", "")).strip()
                        if _n and _n in known:
                            _rows.append({
                                "name": _n,
                                "evidence": str(
                                    _it.get("evidence", ""))[:300],
                                "source": _c["source"]})
                try:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps(
                        {"block_hash": block_hash, "rows": _rows},
                        ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
                except OSError:
                    pass
            rows = _rows

    # norm 化（kind=required_header_global ⇒ 走 norm.py 的新转换器）
    norms: list[dict] = []
    for _row in rows:
        _name = str(_row.get("name", "")).strip()
        if not _name:
            continue
        _n2 = _norm("required_header_global", _name, f"name={_name}",
                    protocol, str(_row.get("source", "")),
                    "@rfc-required-header")
        _n2["name"] = _name
        _n2["evidence"] = str(_row.get("evidence", ""))
        norms.append(_n2)
    return norms


def _rfc_full_text(protocol: str) -> str:
    """该协议 RFC 原文的全量文本（质量闸判「状态名是否可溯源」用）。"""
    out = []
    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        out.append(_f.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(out)


def _apply_transition_gate(rows: list[dict], protocol: str) -> list[dict]:
    """对状态机转移过**质量闸**，并把闸的统计**落盘**（可审计）。

    ★ 闸是**纯后处理**（缓存存原始抽取结果）⇒ 调整判据不需要重抽 LLM。
    ★ 统计落盘到 `derived/per_source/<协议>/transition_quality_gate.json`
      ⇒ 论文可报告「抽到 N 条 / 放行 M 条 / 拦下 K 条（状态名纯但触发列是事件）」。
    """
    _gated, _stat = _transition_quality_gate(
        rows, protocol, _load_rfc_config(protocol), _rfc_full_text(protocol))
    try:
        _d = paths.per_source_root(protocol)
        _d.mkdir(parents=True, exist_ok=True)
        (_d / "transition_quality_gate.json").write_text(
            json.dumps(_stat, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    except OSError:
        pass
    return _gated


#: 目录行（点线）—— 必须排除，否则 `12.1.1 UAS behavior ..... 70`
#: 会被当成方法 `UAS`（实测踩过：SIP 方法集只剩 {UAC, UAS}）
_TOC_DOTS_RE = re.compile(r"\.{4,}|(?:\s\.){3,}")
#: 形态 A：章节标题且**整行只有方法名**（`10.1 OPTIONS`）
_METHOD_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+([A-Z][A-Z_]{1,20})\s*$")
#: 形态 A′：括号形态（`4.1.1.2. MAIL (MAIL)` → 取括号内）
_METHOD_PAREN_RE = re.compile(
    r"^\d+(?:\.\d+)*\.?\s+[A-Za-z][A-Za-z /()\-,]*?"
    r"\(([A-Z][A-Z_]{1,20})\)")
#: 形态 B：ABNF 枚举（`Method = INVITEm / ACKm / ...`，可跨行）
_METHOD_ABNF_RE = re.compile(r"^\s*Method\s*=\s*(.+)$")


def _rfc_source_methods(protocol: str, cfg: dict) -> set[str]:
    """该协议**RFC 源**里的方法/命令名集合（数据驱动，不硬编码协议名）。

    ★ **五种形态并取**（2026-11-06 修复 A/A′/B/D；2026-11-07 补形态 E）：
      A)  **章节标题**且整行只有方法名：``10.1 OPTIONS``（RTSP §10）
      A′) **括号形态**：``4.1.1.2.  MAIL (MAIL)`` → 取括号内（SMTP §4.1.1）
      B)  **ABNF 枚举**：``Method = INVITEm / ACKm / OPTIONSm / ...``（SIP §25）
      D)  **ABNF 命令规则字面量**：``auth-command = "AUTH" SP sasl-mech``（RFC 4954 §8）
      E)  **散文命令格式声明**：``The format for the STARTTLS command is:``
          （RFC 3207 §4）—— 句式 + 全大写词形（协议无关，见
          :func:`_extract_prose_command_formats`）
    ★ 为什么要三形态：SIP 的真实方法只出现在 §25 的 ABNF 里，
      既不在「章节号 + 全大写」形态、也不在括号形态；只认形态 A 时
      会抽出 {UAC, UAS} 两个**目录行噪声** ⇒ 质量闸把 SIP 的转移全过滤掉。
    ★ 数据驱动 ⇒ 换协议只需改 rfc_config，不改代码（G2）。
    """
    secs = cfg.get("method_sections") or []
    if not secs:
        return set()
    _kw = _METHOD_KEYWORD_ATOMS
    out: set[str] = set()

    def _in_sec(num: str) -> bool:
        return any(num == _x or num.startswith(_x + ".") for _x in secs)

    for _f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        _lines = _f.read_text(encoding="utf-8", errors="ignore").splitlines()
        # E) 散文里的「命令格式声明」句式（RFC 3207 的 STARTTLS 走这条）——
        #    ★ **整篇扫描**：RFC 正文硬换行会把一句声明拆到多行 ⇒ 不能按行判定。
        #    ★ **不看章节号**：句式自带「这是命令」的客观证据（与形态 D 同理）。
        for _m, _ml in _extract_prose_command_formats(
                _lines, protocol, cfg.get("method_excludes") or ()):
            if _m not in _kw:
                out.add(_m)
        for _i, _ln in enumerate(_lines):
            _s = _ln.strip()
            if not _s or _TOC_DOTS_RE.search(_s):
                continue
            # A) 章节标题（整行只有方法名）
            _m = _METHOD_HEADING_RE.match(_s)
            if _m and _in_sec(_s.split()[0].rstrip(".")):
                if _m.group(1) not in _kw:
                    out.add(_m.group(1))
                continue
            # A′) 括号形态
            _m2 = _METHOD_PAREN_RE.match(_s)
            if _m2 and _in_sec(_s.split()[0].rstrip(".")):
                if _m2.group(1) not in _kw:
                    out.add(_m2.group(1))
                continue
            # D) ABNF「命令规则 = "大写字面量"」（rfc4954: auth-command = "AUTH" ...）
            #    ★ 不看章节号：`-command` 规则名后缀本身就是「这是命令」的判据。
            _m4 = _RE_ABNF_QUOTED_COMMAND.match(_s)
            if _m4:
                if _m4.group(1) not in _kw:
                    out.add(_m4.group(1))
                continue
            # B) ABNF 枚举（续行以 / 开头）
            _m3 = _METHOD_ABNF_RE.match(_s)
            if _m3:
                _buf = _m3.group(1)
                _j = _i + 1
                while _j < len(_lines) and _lines[_j].strip().startswith("/"):
                    _buf += " " + _lines[_j].strip()
                    _j += 1
                for _tok in re.findall(r"\b([A-Z][A-Z_]{2,20})m?\b", _buf):
                    if _tok not in _kw:
                        out.add(_tok)
    return out


def _transition_quality_gate(rows: list[dict], protocol: str,
                             cfg: dict, rfc_text: str,
                             known_methods: Optional[set[str]] = None,
                             ) -> tuple[list[dict], dict]:
    """状态机转移的**质量闸**（协议无关）：只放行「可溯源 + 可驱动」的转移。

    ★ 动机（实测依据）：SIP / SMTP 的 RFC 状态机**状态名很纯**（RFC 原文命中
      100% / 69%），但其**触发列是事件**（`1xx` / `2xx` / `Timer F` / `220` …）
      ⇒ 若直接进 `transitions` 桶，下游 `edge_cover` / `generic_danger` 会生成
      **方法名为 `1xx` 的假报文** ⇒ 反而污染种子。
    ⇒ 两条判据（均可机器判定、协议无关）：
      ① **可溯源**：状态名必须出现在该协议的 RFC 原文里；
      ② **可驱动**：method 必须是该协议 RFC 源里的**真实方法名**。
    ⇒ 被闸拦下的条目**不丢弃**，而是单独计数上报（便于论文说明"抽到但不可驱动"）。

    Returns:
        `(放行的转移, 统计字典)`
    """
    _known = (_rfc_source_methods(protocol, cfg)
              if known_methods is None else set(known_methods))
    kept: list[dict] = []
    stat = {"total": len(rows), "kept": 0, "dropped_state_not_in_rfc": 0,
            "dropped_method_not_a_method": 0}
    for _r in rows:
        _frm = str(_r.get("from", "")).strip()
        _to = str(_r.get("to", "")).strip()
        _m = str(_r.get("method", "")).strip()
        if not (_frm and _to and _m):
            continue
        if _frm not in rfc_text or _to not in rfc_text:
            stat["dropped_state_not_in_rfc"] += 1
            continue
        if _m.upper() not in _known:
            stat["dropped_method_not_a_method"] += 1
            continue
        kept.append(_r)
    stat["kept"] = len(kept)
    return kept, stat


#: 跨块 PSM 合并提示（PSMBENCH 流程第③步）的契约版本 —— 并入 LLM 缓存键
TRANSITION_MERGE_PROMPT_VERSION = "rfc-transition-merge-conflict"

#: 合并提示：把多个片段的部分 PSM 合并为一份一致、无冲突的完整 PSM
_PROMPT_TRANSITION_MERGE = """你是协议规范分析助手。下面是对 {protocol} 协议 RFC 规范中
**多个片段**分别抽取出的状态转移（部分 PSM），它们之间可能存在重复或冲突。

请把它们合并成**一份一致、无冲突的完整 PSM**，输出 JSON：
{{"transitions": [{{"from": "<源状态>", "method": "<触发方法>", "to": "<目标状态>"}}],
  "conflicts": [{{"from": "...", "method": "...", "kept": "...",
                 "dropped": ["..."]}}]}}

规则：
1. **去重**：完全相同的转移只保留一条。
2. **冲突消解**：同一个 (from, method) 出现多个不同的 to 时，保留与 RFC 原文
   最一致的一条，并把被丢弃的候选写进 `conflicts`。
3. `method` **必须**取自这份已知方法集（不在集合内的一律丢弃）：{allowed}
4. 状态名**照抄**下面出现过的写法，不要新造、不要改大小写。
5. 不要推测、不要补充 RFC 之外的知识。

出现过的状态名：{states}

部分 PSM（共 {m} 条，来自多个片段）：
{partials}
"""


def _psm_conflicts(rows: list[dict]) -> list[dict]:
    """检测部分 PSM 的冲突：同一 ``(from, method)`` 映射到**多个** ``to``。"""
    from collections import defaultdict
    _g: dict = defaultdict(set)
    for _r in rows:
        _g[(_r["from"], _r["method"])].add(_r["to"])
    return [{"from": _k[0], "method": _k[1], "targets": sorted(_v)}
            for _k, _v in _g.items() if len(_v) > 1]


def dump_per_source_artifact(protocol: str, name: str, payload: dict) -> None:
    """把中间统计落盘到 ``derived/per_source/<协议>/<name>``（审计用，失败不阻断）。"""
    try:
        _d = paths.per_source_root(protocol)
        _d.mkdir(parents=True, exist_ok=True)
        (_d / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    except OSError:
        pass


def _merge_partial_psms(rows: list[dict], protocol: str,
                        llm) -> tuple[list[dict], dict]:
    """跨块 PSM 合并（PSMBENCH 流程第③步）—— **冲突驱动**。

    ★ 为什么按需触发（2026-11-06 实测，**勿改回无条件合并**）：
      · **rtsp**：表格腿 14 条 与 LLM 腿 14 条**集合完全相同**，且 **0 个**
        「同 (from, method) 不同 to」冲突 ⇒ 无条件合并的收益 = **0**；
      · **sip**：质量闸后 0 条 ⇒ 无可合并；
      · **smtp**：RFC 无状态机表述。
      ⇒ 无条件合并只会白增 1 次 LLM 调用与不确定性。改为冲突驱动后：
        无冲突 ⇒ 直接去重返回（**零额外调用**）；有冲突 ⇒ 才调 LLM 消解。

    ★ 保底：合并失败 / 合并后为空 ⇒ **保留原样**（防退化），并记录原因。

    Args:
        rows: 各块 union 后的部分 PSM。
        protocol: 协议名（提示词 / 已知方法集用）。
        llm: LLM 客户端（**仅在有冲突时才会被调用**）。

    Returns:
        ``(合并后的 rows, 统计字典)``；统计由调用方落盘。
    """
    _stat: dict = {"partial": len(rows), "conflicts": 0, "merged": False,
                   "after": len(rows)}
    if not rows:
        return rows, _stat
    _conf = _psm_conflicts(rows)
    _stat["conflicts"] = len(_conf)
    if not _conf:
        # 无冲突 ⇒ 仅去重（保持原顺序，**零 LLM 调用**）
        _seen: set = set()
        _out: list[dict] = []
        for _r in rows:
            _k = (_r["from"], _r["method"], _r["to"])
            if _k not in _seen:
                _seen.add(_k)
                _out.append(_r)
        _stat["after"] = len(_out)
        return _out, _stat
    # 有冲突 ⇒ 调 LLM 合并（PSMBENCH 第③步）
    _stat["conflict_detail"] = _conf
    if llm is None:
        try:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        except Exception:  # noqa: BLE001
            _stat["note"] = "LLM 不可用 ⇒ 保留原样（不合并）"
            return rows, _stat
    _known = _rfc_source_methods(protocol, _load_rfc_config(protocol))
    _states = sorted({_r["from"] for _r in rows} | {_r["to"] for _r in rows})
    _partials = "\n".join(
        "%d. %s --%s--> %s" % (_i + 1, _r["from"], _r["method"], _r["to"])
        for _i, _r in enumerate(rows))
    try:
        _res = llm.chat_json(
            system="你输出 JSON。",
            user=_PROMPT_TRANSITION_MERGE.format(
                protocol=protocol.upper(),
                allowed=", ".join(sorted(_known)),
                states=", ".join(_states),
                m=len(rows), partials=_partials),
            temperature=0.0, max_tokens=2000)
    except Exception:  # noqa: BLE001
        _stat["note"] = "合并调用失败 ⇒ 保留原样"
        return rows, _stat
    if not isinstance(_res, dict):
        _stat["note"] = "合并输出非 dict ⇒ 保留原样"
        return rows, _stat
    _merged: list[dict] = []
    for _tr in (_res.get("transitions") or []):
        if not isinstance(_tr, dict):
            continue
        _f = str(_tr.get("from", "")).strip()
        _m = str(_tr.get("method", "")).strip()
        _t = str(_tr.get("to", "")).strip()
        if not (_f and _m and _t):
            continue
        # ★ 合并结果同样受「method ∈ 已知方法集」约束（防合并阶段引入假方法）
        if _known and _m.upper() not in _known:
            continue
        _row = {"from": _f, "method": _m, "to": _t}
        if _row not in _merged:
            _merged.append(_row)
    if not _merged:
        _stat["note"] = "合并后为空 ⇒ 保留原样（防退化）"
        return rows, _stat
    _stat["merged"] = True
    _stat["after"] = len(_merged)
    _stat["llm_conflicts"] = _res.get("conflicts") or []
    return _merged, _stat


def infer_transitions(protocol: str, llm=None) -> list[dict]:
    """LLM 抽状态转移（**带磁盘缓存** ⇒ 确定性 + 零重复成本）。

    Returns:
        ``[{"from":..., "method":..., "to":...}, ...]``。
    """
    candidates = extract_transition_candidates(protocol)
    if not candidates:
        return []
    from core.fused.source_retrieval import CACHE_DIR
    cache_file = CACHE_DIR / f"{protocol}.transitions.json"
    # ★ E′（2026-11-06）：缓存键**并入 prompt_version** ⇒ 改提示词自动失效。
    #   历史缺陷：只哈希候选块文本 ⇒ 改提示词但缓存命中 ⇒ 改动静默不生效。
    block_hash = hashlib_sha256(
        "|".join([TRANSITION_PROMPT_VERSION, TRANSITION_MERGE_PROMPT_VERSION]
                 + [c["hash"] for c in candidates]))
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached = None
        if isinstance(cached, dict) and cached.get("block_hash") == block_hash:
            rows = cached.get("transitions")
            if isinstance(rows, list):
                # ★ 缓存里存的是**原始抽取结果**；闸是**纯后处理** ⇒ 改闸不需重抽
                return _apply_transition_gate(
                    [r for r in rows if isinstance(r, dict)], protocol)

    if llm is None:
        try:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        except Exception as exc:  # noqa: BLE001
            # ★ 无 LLM key（离线 / CI）⇒ **跳过 LLM 通道**，不阻断构建
            print(f"[状态机] LLM 不可用（{exc}）⇒ 跳过 LLM 状态机抽取",
                  file=sys.stderr)
            return []
    out: list[dict] = []
    for cand in candidates:
        try:
            r = llm.chat_json(
                system="你输出 JSON。",
                user=_PROMPT_TRANSITION.format(
                    protocol=protocol.upper(), text=cand["text"]),
                temperature=0.0, max_tokens=2000)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(r, dict):
            continue
        for tr in (r.get("transitions") or []):
            if not isinstance(tr, dict):
                continue
            frm = (tr.get("from") or "").strip()
            mth = (tr.get("method") or "").strip()
            to = (tr.get("to") or "").strip()
            if not (frm and mth and to):
                continue
            if len(frm) > 40 or len(to) > 40 or len(mth) > 40:
                continue
            row = {"from": frm, "method": mth, "to": to}
            if row not in out:
                out.append(row)
    # ★ D′（2026-11-06）：跨块 PSM 合并（PSMBENCH 流程第③步）—— 冲突驱动。
    #   无冲突 ⇒ 仅去重（零 LLM）；有冲突 ⇒ 才调 LLM 消解。实测见函数 docstring。
    out, _mstat = _merge_partial_psms(out, protocol, llm)
    dump_per_source_artifact(protocol, "transition_merge.json", _mstat)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(
            {"block_hash": block_hash, "transitions": out},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return _apply_transition_gate(out, protocol)


def hashlib_sha256(text: str) -> str:
    """sha256 助手（避免在函数体里 import hashlib 造成的循环依赖顾虑）。"""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_transition_norms(protocol: str, llm=None) -> list[dict]:
    """LLM 状态机 ⇒ transition norm（content 对齐 parse_transition_content）。"""
    norms: list[dict] = []
    seen: set[str] = set()
    for tr in infer_transitions(protocol, llm=llm):
        nid = (f"{protocol}.transition.{tr['method']}."
               f"{tr['from'].lower()}_to_{tr['to'].lower()}")
        if nid in seen:
            continue
        seen.add(nid)
        content = (f"from={tr['from']} method={tr['method']} to={tr['to']}")
        norms.append({
            "norm_id": nid,
            "kind": "transition",
            "name": tr["method"],
            "content": content,
            "kb_source_type": "rfc",
            "source": "file:llm@state-machine",
            "protocol": protocol,
        })

    return norms


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
    # ★ P0：`field_value`（字段取值样本）**跨文件合并**而不是丢弃 ——
    #   同名字段在多份 RFC 里各有取值（如 SMTP 的 4 份 RFC）⇒ 合并才完整。
    merged_values: dict[str, list[str]] = {}
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
            if norm.get("kind") == "field_value":
                _vals = _parse_value_samples(norm.get("content", ""))
                _prev = merged_values.get(key)
                if _prev is None:
                    merged_values[key] = list(_vals)
                    seen_protocol_level.add(key)
                    norms.append(norm)
                else:
                    for _v in _vals:
                        if _v not in _prev:
                            _prev.append(_v)
                    norm["content"] = (f"{norm['name']} | values: "
                                        + VALUE_SAMPLE_SEP.join(_prev))
                continue
            if key in seen_protocol_level:
                continue
            seen_protocol_level.add(key)
            norms.append(norm)
    # ---- 通道 G：LLM 状态机（★ P1b，批次 2.2）-------------------------
    #   补齐通道 F（表格）抽不到的：服务端状态机（散文）、ASCII 状态图。
    #   ★ 带磁盘缓存 ⇒ 同一份 RFC 命中缓存 ⇒ 不调 LLM ⇒ 产物逐字节可复现。
    if cfg.get("enable_transitions"):
        for _tn in extract_transition_norms(protocol):
            if _tn["norm_id"] in seen_protocol_level:
                continue
            seen_protocol_level.add(_tn["norm_id"])
            norms.append(_tn)
    # ---- 通道 H：RFC 源的**消息级必填头**（★ F 阶段 F1，**默认关闭**）----
    #   aspect=required_header_global ⇒ **不进任何 bundle 桶** ⇒ 产物逐字节不变；
    #   仅作为可审计的 RFC 源证据留在中枢（供「替代骨架那份」的决策使用）。
    if cfg.get("enable_required_headers"):
        for _hn in infer_required_headers(protocol):
            if _hn["norm_id"] in seen_protocol_level:
                continue
            seen_protocol_level.add(_hn["norm_id"])
            norms.append(_hn)
    # ---- 通道 H′：RFC 源的**方法级必填头**（2026-11-07，**默认关闭**）----
    #   aspect=required_header_by_method ⇒ **不进任何 bundle 桶** ⇒ 产物逐字节不变；
    #   仅作为可审计的 RFC 源证据留在中枢（供「替代手写清单」的决策使用）。
    #   ★ 与通道 H 的分工：H 是「所有请求都必带」，H′ 是「仅该方法必带」。
    if cfg.get("enable_required_headers"):
        for _mn in infer_method_required_headers(protocol):
            if _mn["norm_id"] in seen_protocol_level:
                continue
            seen_protocol_level.add(_mn["norm_id"])
            norms.append(_mn)

    # ---- 通道 B1/B2：**二进制协议**的布局（2026-11-07）----------------------
    #   ★ **协议类型判断阶段**在这里生效：`core.kinds` 判定该协议是
    #     text 还是 binary ⇒ binary 才走布局通道（位域图 / 选项表）。
    #   ★ 文本协议**完全不受影响**（判定为 text ⇒ 这段不执行 ⇒ 产物逐字节不变）。
    #   ★ 布局是**知识**（来自 RFC）⇒ 进中枢、可溯源、论文可引；
    #     且落进 `headers` 桶 ⇒ 下游零改动。
    try:
        from core.kinds import detect_protocol_kind
        _kind = detect_protocol_kind(protocol)
    except Exception:                     # noqa: BLE001 —— 判定失败不阻断构建
        _kind = None
    if _kind is not None and _kind.is_binary:
        from core.fused.rfc_extractor_binary import extract_binary_norms
        for _bn in extract_binary_norms(protocol):
            if _bn["norm_id"] in seen_protocol_level:
                continue
            seen_protocol_level.add(_bn["norm_id"])
            norms.append(_bn)
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

    # ── B-9：语义规则质量闸（强制机制 4）─────────────────────────────
    #: 语义规则总数（**分协议 + 合计**）：{"rtsp": n, "sip": n, ..., "total": N}。
    semantic_rules_total: dict = field(default_factory=dict)
    #: 带可执行 constraint 的规则数（可执行率的分子）。
    semantic_executable_rules: int = 0
    #: 可执行率 = 有 constraint 的规则数 / 规则总数（分母 0 ⇒ 0.0）。
    executable_rate: float = 0.0
    #: 可执行率的口径说明（**分母为 0 时显式写明**，避免"空集伪装成 100%"）。
    executable_rate_note: str = ""
    #: 知识候选总数（候选库的条目数）。
    semantic_candidates_total: int = 0
    #: 候选拒绝原因直方图：{reject_reason: 条数}。
    reject_reason_histogram: dict = field(default_factory=dict)
    #: 权威规则里 `constraint is None` 的条数（**必须为 0**，否则阻断）。
    constraint_none_count: int = 0
    #: `constraint is None` 的可定位明细（rule_id / 协议 / 拒绝原因）。
    constraint_none_details: list = field(default_factory=list)
    #: 候选库里 `convertible=true` 的条数（**必须为 0**，否则阻断）。
    convertible_true_count: int = 0
    #: `convertible=true` 的可定位明细（candidate_id / 协议 / 拒绝原因）。
    convertible_true_details: list = field(default_factory=list)
    #: 本轮闸口是否**真的被检验**过（产出了规则/候选）。
    #: ⚠ False ⇒ "0 违规"**不等于**"通过"（报告须显式说明，见 `gate_note`）。
    gate_exercised: bool = False
    #: 闸口检验状态的说明（空集 / 已检验，含子检查的被检对象数）。
    gate_note: str = ""

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
            # ── B-9 语义规则闸 ──
            "semantic_rules_total": dict(self.semantic_rules_total),
            "semantic_executable_rules": self.semantic_executable_rules,
            "executable_rate": self.executable_rate,
            "executable_rate_note": self.executable_rate_note,
            "semantic_candidates_total": self.semantic_candidates_total,
            "reject_reason_histogram": dict(self.reject_reason_histogram),
            "constraint_none_count": self.constraint_none_count,
            "constraint_none_details": list(self.constraint_none_details),
            "convertible_true_count": self.convertible_true_count,
            "convertible_true_details": list(self.convertible_true_details),
            "gate_exercised": self.gate_exercised,
            "gate_note": self.gate_note,
            "blocking_issues": list(self.blocking_issues),
            "offline_metrics": dict(self.offline_metrics),
            "warnings": list(self.warnings),
            "passed": self.passed,
        }


def rfc_quality_report(protocol: str, facts=None,
                       norms=None, *, semantic=None) -> QualityReport:
    """生成 rfc 源质量报告（A0.4 + B-9）。

    参数：
      protocol: 协议名
      facts:    映射后的 Fact 列表（可选；不传则内部计算）
      norms:    norm 列表（可选；不传则内部重算）
      semantic: B-9 语义闸的审计结果（可选；不传则**自动审计**磁盘上的
                语义四库）。传入可审计多协议（分协议 + 合计）。

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

    # ---- B-9：语义规则闸（强制机制 4）----
    #   ① 报告新增语义度量；② `constraint is None` > 0 ⇒ 阻断；
    #   ③ 候选 `convertible=true` > 0 ⇒ 阻断。
    #   语义四库不存在时**不阻断**（D-6 默认关闭 ⇒ 语义规则本就不必存在），
    #   但报告必须显式写明「闸口未被检验」。
    audit = semantic if semantic is not None else audit_semantic_library(protocol)
    _apply_semantic_gate(rep, audit)
    if audit.malformed_lines:
        rep.warnings.append(
            f"语义四库有 {audit.malformed_lines} 行无法解析（已跳过；"
            f"闸口按可解析行统计）")

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
#: ★ 2026-11-02 B-13 批次：约束候选按**逻辑句**切句（原先按物理行 ⇒ 半句）
#:   —— 候选池内容改变 ⇒ 版本号必须变。
_EXTRACTOR_VERSION = "a1-b13-logical-sent-2026-11-02"


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

    ⚠⚠ **同口径的独立实现（改一处必须同步另一处）**：
      ``core/fused/semantic.py`` 的 ``_splitline_offsets`` 是**同口径的另一份
      实现**（B-2 的 C2 区间校验用它）。这是**有意的重复** ——
      ``semantic.py`` 不该依赖 ``rfc_extractor.py``（否则引入 import 环）。
      ⇒ **任何一方改动切分口径（如换成 ``count("\n")`` 口径），
      必须同步另一方**，否则两边的「行号」会静默错位
      （实测差值 = 换页符处数，430/430 全中）。
    """
    offsets: dict[int, int] = {}
    pos = 0
    for lineno, seg in enumerate(raw_text.splitlines(keepends=True), start=1):
        offsets[lineno] = pos
        pos += len(seg)
    return offsets


# ===========================================================================
# B-13　逻辑句切分 —— 按**逻辑句**切句，而不是按物理行
# ===========================================================================
#
# ★ **为什么改**：RFC 正文是**折行排版**（一个逻辑句跨多行）。按物理行切句
#   ⇒ 抽出的约束候选经常是**半句**（实测三协议 430 条候选里 91.4% 命中半句
#   判据；其中散文类候选有 77.2% 以「句中」状态结尾）。
#   半句的直接后果：
#     ① 标注者无法判断「M1 可执行率」的真实上界（半句里看不到规范动词/
#        操作数 ⇒ 大量误判「不可执行」）；
#     ② B-10 的 C0/E1/E2 三组对照会建立在**半句候选池**上 ⇒ 测的是
#        **抽取粒度**，不是表达层升级的收益。
#
# ★ **判定口径（协议无关、确定性、无 LLM）**：
#   ① **段落边界** = 源文件**行号不连续**（清洗会丢空行/页眉 ⇒ 行号有缺口）
#      ⇒ **绝不跨段落合并**（段末即句界）。
#   ② **行内句界** = `(?<=[.!?])` + 空白（**沿用历史口径**，只是不吃换行）。
#   ③ **跨行合并** = 「上一段**未**以句末标点结束」且「下一行是**可续行**形态」。
#
# ⚠ **不用缩进判边界**：RFC 的缩进是**排版对齐**（同一段内各行缩进可以不同，
#   如缩进定义条目），**不是**语义边界；用它判句会把定义块切碎。
# ⚠ **不用 LLM 判句边界**：必须确定性、可复现、离线可跑。
# ⚠ **不单独用「下一行以大写/数字开头」断句**：上一行若以句末标点结束，
#   必是句界（规则 ③ 已覆盖）；上一行若**未**以句末标点结束 ⇒ 是**折行**
#   ⇒ 合并（此时下一行即便以大写开头也是折行的继续，例如
#   "…the following information should" + "be provided:"）。

#: 行内句界：**只**吃空白，**不吃换行**（换行由物理行结构单独判定）。
#: ★ 与历史 `_SENT_SPLIT_RE` 的行内部分**同口径**（`(?<=[.!?])` + 空白）。
_SENT_BOUNDARY_RE = re.compile(r"(?<=[.!?])[ \t]+")

#: 句末标点（可带收尾引号/括号）—— 「这一段到此说完」的判据。
#: ★ 与 `scripts/annotate_candidates.py::_SENT_TERMINATOR_AT_END` 同口径。
_SENT_END_RE = re.compile(r"[.!?][\"'\u2019)\]]*$")

#: 列举项起始标记（`1.` / `a)` / `-` / `*` / `+` / `\u2022`）。
_RE_LIST_ITEM = re.compile(
    r"^\s*(?:\d{1,3}[.)]|[A-Za-z][.)]|[-*+\u2022])\s+\S")

#: 表格列间隔：「非空白 + 2 个以上空白 + 非空白」。出现 ≥2 处 ⇒ 表格行。
_RE_COLUMN_GAP = re.compile(r"\S {2,}\S")

#: 表格行（`|` 开头的竖线表格 / ABNF 竖线块）。
_RE_PIPE_ROW = re.compile(r"^\s*\|")

#: 纯分隔线（`----` / `====` / `~~~~`）。
_RE_RULE_LINE = re.compile(r"^\s*[-=*+#~_]{3,}\s*$")

#: ASCII 图示字符（制表符画的框线/块）。
_ASCII_ART_CHARS = (
    "\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"
    "\u2500\u2550\u2554\u2557\u255a\u255d\u2551\u2560\u2563\u2566"
    "\u2569\u256c\u2588\u2591\u2592\u2593"
)
_RE_ASCII_ART = re.compile("[" + re.escape(_ASCII_ART_CHARS) + "]")

#: ABNF 产生式 —— 与 B-5 `semantic_rules.PATTERNS` 的 `abnf_rule` **同形**
#: （判定口径必须一致：ABNF 行的 `^` 锚点一旦被并句破坏，B-5 就再也
#:  抽不出 ABNF 约束）。
_RE_ABNF_RULE = re.compile(
    r"^[ \t]*(?P<ref>[A-Za-z][A-Za-z0-9-]*)[ \t]*(?::=|=)[ \t]*\S")

#: 编号标题（`10.1 Basic Structure` / `10 Basic Structure`）。
_RE_NUMBERED_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*\s+\S")

#: 报文字段行（`Content-Length: 376` / `CSeq: 312`）—— 报文样例行。
_RE_HEADER_FIELD = re.compile(r"^\s*[A-Za-z][A-Za-z0-9-]*:\s")

#: 引用块前缀（`>` 引用）。
_RE_QUOTE_PREFIX = re.compile(r"^\s*>")


def _line_structure(text: str) -> str:
    """判定一行的**结构形态**（决定它能否与下一行合并成一个逻辑句）。

    返回值（互斥，按判定顺序）：

    ========== =====================================================
    形态         含义
    ========== =====================================================
    ``blank``    空行（清洗后不应出现）
    ``abnf``     ABNF 产生式（`Foo = bar`）—— **自成一句**
    ``list``     列举项（`1.` / `a)` / `-` / `*` / `+` / `•`）
    ``rule``     纯分隔线（`----`）
    ``art``      ASCII 图示行（框线/块字符）
    ``table``    表格行（≥2 处「2+ 空白」列间隔，或 `|` 开头）
    ``quote``    引用块（`>` 前缀，或行首 `"` 且**引号未闭合**）
    ``head``     编号标题 / 标题形态
    ``field``    报文字段行（`Content-Length: 376`）
    ``prose``    散文正文 —— **唯一可与相邻行合并的形态**
    ========== =====================================================

    ★ 判定**只用行文本形态**，**不用缩进**（缩进是排版对齐，不是语义边界）。
    ★ 章节标题**结构上不可能**进正文（`_split_heads_bodies` 先把标题摘走）
      ⇒ `head` 分支是**防御性**的（复用本模块自己的 `_parse_heading_shape`）。
    """
    s = text or ""
    if not s.strip():
        return "blank"
    if _RE_ABNF_RULE.match(s):
        return "abnf"
    if _RE_LIST_ITEM.match(s):
        return "list"
    if _RE_RULE_LINE.match(s):
        return "rule"
    if _RE_ASCII_ART.search(s):
        return "art"
    if len(_RE_COLUMN_GAP.findall(s)) >= 2 or _RE_PIPE_ROW.match(s):
        return "table"
    if _RE_QUOTE_PREFIX.match(s):
        return "quote"
    if _is_open_quote_line(s):
        return "quote"
    if _RE_NUMBERED_HEADING.match(s):
        return "head"
    if _RE_HEADER_FIELD.match(s):
        return "field"
    if _parse_heading_shape(s.strip()) is not None:
        return "head"
    return "prose"


def _is_open_quote_line(text: str) -> bool:
    """该行是否以 `"` 开头且**引号未闭合**（⇒ 跨行引用串的起点）。

    ★ **不能**只看「以引号开头」：RFC 里有大量**以引号开头但不是引用块**的
      散文行（如 RFC 2119 关键词说明行 `"SHOULD", "SHOULD NOT", ...`、
      句中的 `"rtspu") packets ...`）—— 把它们当引用块会导致**该行不与
      下一行合并** ⇒ 又变回半句。
    ★ 判据 = 行首是 `"` **且**该行的引号数为**奇数**（引号没闭合 ⇒ 引用
      跨行）。实测三协议只有 5 行真正跨行引用，其余 189 行都是散文。
    """
    s = (text or "").lstrip()
    return s.startswith('"') and (text or "").count('"') % 2 == 1


#: **可续行**形态（能与相邻行合并成一个逻辑句）。
_CONTINUABLE_KINDS = frozenset({"prose"})

#: **可被续写**的形态（这一行的内容还没说完，下一行可以接上去）。
#: ★ 散文行可续写；列举项也可续写（`1. The registrar returns ...` 的
#:   下一行是它的续行）；表格/ABNF/图示/引用/标题**不可**（它们自成单元）。
_EXTENDABLE_KINDS = frozenset({"prose", "list"})


def _split_sentences_with_offsets(
    text: str,
    refs: Optional[list[tuple[int, str]]] = None,
) -> list[tuple[str, int, int]]:
    """按**逻辑句**切分文本，返回每句的 (文本, 起偏移, 止偏移)（相对 `text`）。

    Args:
        text: 章节窗口正文（**物理行用 `\n` 连接**）。
        refs: 该窗口正文的行引用 `[(源文件行号, 行文本)]`（即 `body_refs`）。
            ★ 给了它才能识别 **段落边界**（清洗丢空行/页眉 ⇒ 行号有缺口）
              与**每个物理行在 `text` 中的区间**。
            缺省（``None``）⇒ 退化为**历史口径**（按物理行 / 行内句末标点
            切分），保证旧调用方行为不变。

    Returns:
        ``[(句文本, 起偏移, 止偏移)]``；偏移相对 `text`，**半开区间**。

    ★ **切句规则**（协议无关、确定性、**无 LLM**）：

      ① **段落边界** —— 源文件行号不连续 ⇒ 段落结束（**不跨段落合并**）。
      ② **行内句界** —— `(?<=[.!?])` + 空白（沿用历史口径）。
      ③ **跨行合并** —— 当且仅当**同时**满足：
         (a) 下一行是**可续行形态**（散文；非列举/表格/图示/ABNF/引用/标题）；
         (b) 上一段的**末行形态**可被续写（散文 / 列举项）；
         (c) 上一段**未以句末标点**（`.`/`!`/`?`，可带收尾引号括号）结束；
         (d) 合并后长度 ≤ `_MAX_SENT`（避免无终止符的长段被吞成巨句）。

    ⚠ 切分后一句**可能跨多行** ⇒ 其区间也跨多行 ⇒ 区间在源文件里
      **仍然逐字可核对**（`_constraint_candidates_from_file` 用行号回查
      首尾两行 ⇒ `raw[span_start:span_end] == text` 恒成立）。
    """
    if refs is None:
        # ★ 历史口径兜底（按物理行 + 行内句末标点切分）
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

    # ① 每个物理行在 `text` 中的区间（与 `body_refs` 逐行对齐）
    spans: list[tuple[int, int, int]] = []
    cursor = 0
    for lineno, line_text in refs:
        spans.append((cursor, cursor + len(line_text), lineno))
        cursor += len(line_text) + 1

    # ② 段落分组（源行号不连续 ⇒ 段落边界）
    paras: list[list[int]] = []
    for i, (_a, _b, lineno) in enumerate(spans):
        if i == 0 or lineno != spans[i - 1][2] + 1:
            paras.append([i])
        else:
            paras[-1].append(i)

    out2: list[tuple[str, int, int]] = []
    for para in paras:
        out2.extend(_split_paragraph_sentences(text, spans, para))
    return out2


def _split_paragraph_sentences(
    text: str,
    spans: list[tuple[int, int, int]],
    para: list[int],
) -> list[tuple[str, int, int]]:
    """一个**段落** → 逻辑句列表 ``[(文本, 起偏移, 止偏移)]``。

    ★ 段落内先按「行内句界」切成最小单元，再按「跨行合并」规则拼回逻辑句。
    """
    # ① 段内切「行内子句」
    units: list[tuple[int, int, int]] = []      # (起, 止, 行下标)
    idx = 0
    n_para = len(para)
    while idx < n_para:
        li = para[idx]
        a, b, _ = spans[li]
        line_text = text[a:b]
        # ★ **跨行引用块**（`"..."` 跨行）：行首是 `"` 且引号**未闭合** ⇒
        #   把后续行一并吞进来，直到引号闭合 ⇒ 引用块**自成一句**
        #   （既不与散文合并，也不会被散文吞掉）。
        #   ⚠ 吞并**只跨散文行**：遇到表格/ABNF/图示等结构性行即停
        #     （否则会把一整块 ABNF 吞进引号里）。
        if _is_open_quote_line(line_text):
            quotes = line_text.count('"')
            last = li
            j = idx + 1
            while j < n_para and quotes % 2 == 1:
                nxt = para[j]
                nxt_text = text[spans[nxt][0]:spans[nxt][1]]
                if _line_structure(nxt_text) != "prose":
                    break
                quotes += nxt_text.count('"')
                last = nxt
                j += 1
            units.append((a, spans[last][1], li))
            idx = j
            continue
        pos = 0
        for m in _SENT_BOUNDARY_RE.finditer(line_text):
            if m.start() > pos:
                units.append((a + pos, a + m.start(), li))
            pos = m.end()
        if b > a + pos:
            units.append((a + pos, b, li))
        idx += 1

    # ② 跨行合并
    groups: list[list[tuple[int, int, int]]] = []
    cur: list[tuple[int, int, int]] = []
    for u in units:
        if not cur:
            cur = [u]
            continue
        if _can_merge_units(text, spans, cur, u):
            cur.append(u)
        else:
            groups.append(cur)
            cur = [u]
    if cur:
        groups.append(cur)

    return [(text[g[0][0]:g[-1][1]], g[0][0], g[-1][1]) for g in groups]


def _can_merge_units(
    text: str,
    spans: list[tuple[int, int, int]],
    cur: list[tuple[int, int, int]],
    u: tuple[int, int, int],
) -> bool:
    """当前已累积的句与下一个单元 `u` 能否合并成一个逻辑句。"""
    prev = cur[-1]
    if prev[2] == u[2]:
        return False                     # 同一行内：行内句界已切开，不合并
    prev_text = text[prev[0]:prev[1]]
    next_kind = _line_structure(text[spans[u[2]][0]:spans[u[2]][1]])
    prev_kind = _line_structure(text[spans[prev[2]][0]:spans[prev[2]][1]])
    # ① 下一行必须是「可续行」形态（列举/表格/图示/ABNF/引用/标题 → 不合并）
    if next_kind not in _CONTINUABLE_KINDS:
        return False
    # ② 上一段的末行必须「可被续写」（表格/ABNF/图示/引用/标题 → 不合并）
    if prev_kind not in _EXTENDABLE_KINDS:
        return False
    # ③ 上一段若以句末标点结束 ⇒ 句界已到，不合并
    if _SENT_END_RE.search(prev_text):
        return False
    # ④ 长度护栏：合并后不得超上限（避免无终止符的长段被吞成巨句）
    if (u[1] - cur[0][0]) > _MAX_SENT:
        return False
    return True


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
        for sent, s_start, s_end in _split_sentences_with_offsets(text, refs):
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
            # ★ 句尾（**可能跨行**）→ 回查**最后一行**的行内偏移
            tail_pos = s_end - 1
            loc_tail = None
            for start, length, lineno_tail in line_spans:
                if start <= tail_pos < start + length:
                    loc_tail = (lineno_tail, tail_pos - start + 1)
                    break
            if loc_tail is None:
                continue
            lineno_tail, offset_tail = loc_tail
            abs_end_base = line_offsets.get(lineno_tail)
            if abs_end_base is None:
                continue
            abs_end = abs_end_base + offset_tail
            # ★ **逐字自检**：区间必须与原文**逐字相等**（B-2 的 C2 前提）。
            #   正常情况恒成立（窗口正文行 == 源文件行内容）；若源文件在
            #   中间行留了行尾空白（实测三协议 0 行），偏移会错位 ⇒
            #   **宁可不产出候选**，也不产出「核对不上」的证据。
            if raw_text[abs_start:abs_end] != stripped:
                continue
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


# ===========================================================================
# B-9　语义规则质量闸（强制机制 4）+ `rules_only` 产出
# ===========================================================================
#
# ★ 本节的三个闸（对齐 `docs/rfc_source_bcd_roadmap.md` §强制机制 4）：
#   ① 报告新增度量：**语义规则总数** / **可执行率** / **候选拒绝原因直方图**
#      / **`constraint is None` 计数**；
#   ② `constraint is None` 计数 > 0 ⇒ **阻断构建**；
#   ③ 候选库中 `convertible=true` 计数 > 0 ⇒ **阻断构建**。
#
# ★ 与 D-6 开关位（`PROTORAG_SEMANTIC_RULES`）**正交**：
#   · D-6 管「**已落库的**语义规则是否参与生成」（下游 bundle / 种子生成）；
#   · B-9 管「**是否产出**语义规则与候选」（构建侧）。
#   `rules_only` 显式开启**产出**，但**绝不置位** D-6 ⇒ 全局默认仍关闭。

#: 语义四库根目录的**覆盖**环境变量（默认不设 ⇒ 落 `derived/per_source/...`）。
#: 用途：把构建 / 测试产物隔离到临时目录，避免污染仓库 `derived/`。
SEMANTIC_ROOT_ENV_KEY = "PROTORAG_SEMANTIC_ROOT"

#: 期望响应词表（与 `docs/semantic_rules_coverage_matrix.md` §2 实测口径一致）。
EXPECTED_VOCAB = ("success", "protocol_error", "application_error", "silence")

#: 语义四库的文件名（与 `core/fused/downstream/rule_store.py` 的 LIBRARY_FILES 一致）。
_RULES_FILE = "rules.jsonl"
_CANDIDATES_FILE = "candidates.jsonl"

#: JSONL 行的 kind 标签（与 `rule_store.KIND_RULE` / `KIND_CANDIDATE` 一致）。
_KIND_RULE = "semantic_rule"
_KIND_CANDIDATE = "knowledge_candidate"


def semantic_library_dir(protocol: str, root=None) -> Path:
    """语义四库目录 ``<root>/<协议>/rfc/semantic/``。

    ★ 默认根目录 = `core.fused.downstream.rule_store.semantic_dir(protocol)`
      （即 `derived/per_source/<协议>/rfc/semantic/`）—— **不改** rule_store
      的行为，只是把「根」参数化，便于把构建 / 测试产物隔离到临时目录
      （避免污染仓库 `derived/`）。
    """
    if root is None:
        root = os.environ.get(SEMANTIC_ROOT_ENV_KEY) or ""
    root = str(root).strip()
    if root:
        return Path(root) / protocol.lower() / "rfc" / "semantic"
    from core.fused.downstream import rule_store
    return rule_store.semantic_dir(protocol)


#: RFC 5234（ABNF 核心语法）/ 5321（字符集）的**语法原子** ——
#: 它们是语法构件，**不是协议字段** ⇒ 从 ABNF 派生字段集时必须排除。
#:   （否则会把 ``ALPHA``/``DIGIT``/``CTL`` 当成字段名绑上 ⇒ 污染已知字段集。）
ABNF_SYNTAX_TOKENS: frozenset[str] = frozenset({
    # RFC 5234 §2.3 核心规则
    "ALPHA", "BIT", "CHAR", "CR", "CRLF", "CTL", "DIGIT", "DQUOTE", "HTAB",
    "LF", "LWSP", "OCTET", "SP", "VCHAR", "WSP",
    # RFC 5321 §4 字符集
    "US-ASCII", "UTF8-CONT", "UTF8-NONASCII", "TEXT-UTF8-TRIM", "TEXT-UTF8char",
    "NO-WS-CTL", "QUOTED-STRING",
})

#: ABNF 左部（定义名）形态：``name = rhs``。
_RE_ABNF_ASSIGN = re.compile(r"^([A-Za-z][A-Za-z0-9\-]*)\s*=\s*(.+)$")
#: 连字符 token（协议字段名的形态，如 ``Request-URI``）。
_RE_HYPHEN_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b")
#: 句子切分（散文语境判定用）。
_RE_SENTENCE = re.compile(r"(?<=[.;])\s+")


def derive_abnf_field_names(protocol: str) -> set[str]:
    """从 RFC 的 **ABNF 语法 + 散文语境**派生协议字段名。

    ★ **双证据判据**（缺一不可，否则污染大）：
      E2 —— 该名字是 ABNF **右部引用的** token（被语法**使用**的名字，
             如 ``Request-Line = Method SP Request-URI SP SIP-Version CRLF``
             里的 ``Request-URI`` / ``SIP-Version``）；
      E3 —— 该名字在**散文**里被称作 header / field。

    ★ **不用 ABNF 左部**（定义名）：那些多为语法产物名
      （``ACKm`` / ``INVITEm`` / ``A-d-l``）⇒ 既污染又非协议字段。

    ★ **排除语法原子**（:data:`ABNF_SYNTAX_TOKENS`）。

    ★ 与「扩 ``field_sections``」的**关键区别**：本函数只补**字段名**，
      不改章节判定 ⇒ 不会引入 ``Vias``/``Clients``/``Servers`` 这类
      **章节结构名**（它们是章节标题，不是字段）。

    Returns:
        派生出的字段名集合（**不含** ``known_field_set`` 已有的）。
    """
    from core import paths

    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return set()
    referenced: set[str] = set()
    prose: set[str] = set()
    for f in sorted(spec_dir.glob("*.txt")):
        raw = f.read_text(encoding="utf-8", errors="ignore")
        # E3：散文里被称作 header / field 的名字
        flat = raw.replace("\n", " ")
        for sent in _RE_SENTENCE.split(flat):
            if not re.search(r"(header|field)", sent, re.IGNORECASE):
                continue
            prose.update(_RE_HYPHEN_TOKEN.findall(sent))
        # E2：ABNF 右部引用的连字符 token
        for line in raw.splitlines():
            s = line.strip()
            m = _RE_ABNF_ASSIGN.match(s)
            if not m or len(s) > 140:
                continue
            referenced.update(_RE_HYPHEN_TOKEN.findall(m.group(2)))
    return (referenced & prose) - ABNF_SYNTAX_TOKENS


def known_field_set(protocol: str) -> list[str]:
    """协议已知字段集（章节/ABNF 字段抽取 + **ABNF 派生补充**）。

    ★ 口径与 `docs/semantic_rules_coverage_matrix.md` §2 实测一致
      （rtsp 45 / sip 46 / smtp 0 —— smtp 的 RFC 5322 字段章节标题是
      「The Origination Date Field」这类**长标题**，抽不出裸字段名）。
    ★ **追加** ABNF 派生字段（:func:`derive_abnf_field_names`）：
      补上「章节标题式抽不到、但 RFC 明确要求」的真头字段
      （实测 SIP 的 ``Request-URI`` / ``SIP-Version``）
      ⇒ 修 C6（字段绑定）这一 M1 第一瓶颈。
    """
    fields = {n["name"] for n in extract_rfc_norms(protocol)
              if n.get("kind") == "field"}
    fields |= derive_abnf_field_names(protocol)
    return sorted(fields)


@dataclass
class SemanticBundle:
    """一次「语义规则构建」的产物（**只含**语义规则与知识候选）。"""
    protocol: str
    rules: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    reject_reason_histogram: dict = field(default_factory=dict)
    known_fields: list = field(default_factory=list)
    candidate_total: int = 0


#: **生产路径**的候选句池上限（每 RFC 文件）。
#: ★ 此前固定 80 ⇒ rtsp / sip 的候选被**人为截断**（实测自然上限 284 / 1000），
#:   直接压制了语义规则覆盖（③ 层极薄的主因之一）。
#: ★ **仅用于生产路径**（:func:`build_semantic_rules`）；
#:   冻结集 / B-10 评测路径**各自显式钉死 80**（口径不可漂移）。
PRODUCTION_CANDIDATE_POOL_LIMIT = 1000


def build_semantic_rules(protocol: str, *, known_fields=None,
                         expected_vocab=None,
                         max_per_rfc: int = PRODUCTION_CANDIDATE_POOL_LIMIT
                         ) -> SemanticBundle:
    """B-9 `rules_only` 的**唯一产出入口**：RFC 约束候选 → 规则 + 知识候选。

    ★ 生产侧的**契约**（使强制机制 4 在产出端天然成立）：
      · 转换成功 ⇒ 产 `SemanticRule`（**必带 constraint**）；
      · 转换失败 ⇒ 产 `KnowledgeCandidate`（**必 convertible=False** 并带
        `reject_reason`）——「不可转换者只作知识候选，不进自动生成链路」。

    ★ 全程**零 LLM**：用 B-5 的模式表（`semantic_rules.make_resolver`）注入
      `semantic.try_convert` ⇒ 结果**确定性可复现**（同输入同输出）。
    """
    from collections import Counter

    from core.fused.semantic import (EvidenceAnchor, KnowledgeCandidate,
                                     SemanticRule, compute_evidence_id,
                                     compute_explicitness, compute_rule_id,
                                     load_source_text, try_convert)
    from core.fused.semantic_rules import (make_resolver, match_pattern,
                                           resolve_evidence_kind)

    fields = (list(known_fields) if known_fields is not None
              else known_field_set(protocol))
    # ★ known_field_set 现含 ABNF 派生字段 ⇒ 字段集更大 ⇒ C6 更易通过。
    vocab = (tuple(expected_vocab) if expected_vocab is not None
             else EXPECTED_VOCAB)
    resolver = make_resolver(known_fields=fields, expected_behavior="")

    bundle = SemanticBundle(protocol=protocol, known_fields=list(fields))
    hist: Counter = Counter()
    raw = extract_constraint_candidates(protocol, max_per_rfc=max_per_rfc)
    bundle.candidate_total = len(raw)
    for c in raw:
        text = c["text"]
        m = match_pattern(text)
        pattern_kind = ("abnf" if (m is not None and m.kind == "abnf")
                        else "normative")
        ev_kind = resolve_evidence_kind(text, pattern_kind)
        source_text = load_source_text(protocol, c["source"])
        span_start = c.get("span_start")
        span_end = c.get("span_end")
        verified = bool(
            source_text is not None and span_start is not None
            and span_end is not None
            and source_text[span_start:span_end] == text)
        ev = EvidenceAnchor(
            evidence_id="e0",
            spec_version=c.get("spec_version") or "",
            section_path=tuple(c.get("section_path") or ()),
            source_anchor=c["source"],
            span_text=text,
            span_start=span_start,
            span_end=span_end,
            evidence_kind=ev_kind,
            explicitness=compute_explicitness(
                text, verified=verified, evidence_kind=ev_kind),
            source_class="normative_spec",
        )
        constraint, reason = try_convert(
            ev, source_text=source_text, known_fields=fields,
            expected_vocab=vocab, resolver=resolver)
        if constraint is not None:
            subject_type = "field" if constraint.target_field else "message"
            # ★ rule_id 用**章节号链**（`section_no_path`）而不是标题链 ——
            #   标题措辞微调不应让 rule_id 漂移（§3.2）。
            rule_id = compute_rule_id(
                protocol, ev.spec_version,
                tuple(c.get("section_no_path") or ()),
                subject_type, constraint.target_field,
                constraint.operator, constraint.operand,
                constraint.operand_ref, constraint.expected_behavior)
            ev = replace(ev, evidence_id=compute_evidence_id(
                rule_id, ev.source_anchor, ev.span_start))
            bundle.rules.append(SemanticRule(
                rule_id=rule_id, evidence=ev, constraint=constraint,
                subject_type=subject_type,
                subject_name=constraint.target_field,
                rule_state="authoritative", supersedes=None,
                model_confidence=1.0, validated=False))
        else:
            ev = replace(ev, evidence_id=compute_evidence_id(
                f"candidate:{protocol}", ev.source_anchor, ev.span_start))
            hist[reason or "unknown"] += 1
            bundle.candidates.append(KnowledgeCandidate(
                candidate_id="c" + ev.evidence_id, evidence=ev,
                subject_type="", subject_name="", raw_text=text,
                convertible=False, reject_reason=reason or "unknown"))
    bundle.reject_reason_histogram = dict(sorted(hist.items()))
    return bundle


def semantic_rule_row(rule) -> dict:
    """`SemanticRule` → JSONL 行（**与 `rule_store.save_rules` 同格式**）。"""
    return {"kind": _KIND_RULE, "rule": asdict(rule)}


def semantic_candidate_row(cand) -> dict:
    """`KnowledgeCandidate` → JSONL 行（与 `rule_store.save_candidates` 同格式）。"""
    return {"kind": _KIND_CANDIDATE, "candidate": asdict(cand)}


def _write_jsonl(path: Path, rows: Iterable[dict]) -> Path:
    """写 jsonl（覆盖写；父目录自动创建）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def save_semantic_library(protocol: str, rules=None, candidates=None,
                          root=None) -> dict:
    """落盘语义四库的**规则库 / 候选库**（行格式与 `rule_store` 兼容）。

    ★ 自己写而不调 `rule_store.save_rules`：本函数要支持**根目录覆盖**
      （把产物隔离到临时目录，避免污染仓库 `derived/`），而 `rule_store`
      的落盘路径是写死的。行格式与 `rule_store._write_jsonl` 完全一致 ⇒
      `rule_store.load_rules` / `load_candidates` 仍可读回（互操作不破）。
    """
    d = semantic_library_dir(protocol, root)
    d.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    if rules is not None:
        out["rules"] = _write_jsonl(d / _RULES_FILE,
                                    [semantic_rule_row(r) for r in rules])
    if candidates is not None:
        out["candidates"] = _write_jsonl(
            d / _CANDIDATES_FILE,
            [semantic_candidate_row(c) for c in candidates])
    return out


@dataclass
class SemanticAudit:
    """语义四库的**原始 JSONL**审计结果（强制机制 4 的计数来源）。"""
    protocols: list = field(default_factory=list)
    rules_total: int = 0
    candidates_total: int = 0
    rules_by_protocol: dict = field(default_factory=dict)
    candidates_by_protocol: dict = field(default_factory=dict)
    constraint_none_count: int = 0
    constraint_none_details: list = field(default_factory=list)
    convertible_true_count: int = 0
    convertible_true_details: list = field(default_factory=list)
    reject_reason_histogram: dict = field(default_factory=dict)
    malformed_lines: int = 0
    library_found: bool = False


def _read_jsonl_rows(path: Path) -> tuple[list, int]:
    """读原始 JSONL（**不做语义校验**）⇒ 返回 (行 dict 列表, 坏行数)。"""
    rows: list = []
    bad = 0
    if not path.is_file():
        return rows, bad
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(d, dict):
            rows.append(d)
        else:
            bad += 1
    return rows, bad


def audit_semantic_rows(protocol: str, rule_rows: list,
                        candidate_rows: list) -> SemanticAudit:
    """对**行**做审计（内存路径与文件路径共用同一实现 ⇒ 口径一致）。

    ★ 统计口径：
      · `constraint is None`：规则行里 `rule.constraint` 为空即计 1 条，
        并记下 `rule_id` / 协议 / `reject_reason` / 源锚点 ⇒ **可定位**；
      · `convertible=true`：候选行里 `candidate.convertible` 为真即计 1 条，
        并记下 `candidate_id` / 协议 / `reject_reason` / 源锚点。
    """
    from collections import Counter

    audit = SemanticAudit(protocols=[protocol])
    audit.rules_total = len(rule_rows)
    audit.candidates_total = len(candidate_rows)
    audit.rules_by_protocol[protocol] = len(rule_rows)
    audit.candidates_by_protocol[protocol] = len(candidate_rows)
    hist: Counter = Counter()
    for row in rule_rows:
        rule = row.get("rule") or {}
        if rule.get("constraint") is not None:
            continue
        ev = rule.get("evidence") or {}
        audit.constraint_none_count += 1
        audit.constraint_none_details.append({
            "protocol": protocol,
            "rule_id": rule.get("rule_id") or "",
            "reject_reason": (row.get("reject_reason")
                              or rule.get("reject_reason")
                              or "constraint_missing"),
            "source_anchor": ev.get("source_anchor") or "",
            "section_path": list(ev.get("section_path") or ()),
            "span_text": (ev.get("span_text") or "")[:160],
        })
    for row in candidate_rows:
        cand = row.get("candidate") or {}
        ev = cand.get("evidence") or {}
        if cand.get("convertible"):
            audit.convertible_true_count += 1
            audit.convertible_true_details.append({
                "protocol": protocol,
                "candidate_id": cand.get("candidate_id") or "",
                "reject_reason": (row.get("reject_reason")
                                  or cand.get("reject_reason")
                                  or "convertible_flag_set"),
                "source_anchor": ev.get("source_anchor") or "",
                "raw_text": (cand.get("raw_text") or "")[:160],
            })
        reason = cand.get("reject_reason")
        if reason:
            hist[reason] += 1
    audit.reject_reason_histogram = dict(sorted(hist.items()))
    return audit


def audit_semantic_library(protocol, root=None) -> SemanticAudit:
    """**原始 JSONL**审计：统计 `constraint is None` / `convertible=true`。

    ★ 为什么不走 `rule_store.load_rules` / `load_candidates`：那两个加载器在
      **命中违规时直接抛 ValueError**（那正是它们的设计意图）⇒ **无法计数**。
      闸口要回答「有多少条违规 + 违规在哪」，所以这里**直接读原始 JSONL**。

    参数：
      protocol: 单个协议名，或协议名列表（多协议 ⇒ 给出**分协议 + 合计**）。
      root:     四库根目录覆盖（None ⇒ 取环境变量 / 默认 derived/）。
    """
    from collections import Counter

    protos = [protocol] if isinstance(protocol, str) else list(protocol)
    audit = SemanticAudit(protocols=list(protos))
    hist: Counter = Counter()
    for proto in protos:
        d = semantic_library_dir(proto, root)
        rule_rows, bad_r = _read_jsonl_rows(d / _RULES_FILE)
        cand_rows, bad_c = _read_jsonl_rows(d / _CANDIDATES_FILE)
        audit.malformed_lines += bad_r + bad_c
        if (d / _RULES_FILE).is_file() or (d / _CANDIDATES_FILE).is_file():
            audit.library_found = True
        rules = [r for r in rule_rows if r.get("kind") == _KIND_RULE]
        cands = [r for r in cand_rows if r.get("kind") == _KIND_CANDIDATE]
        audit.rules_by_protocol[proto] = len(rules)
        audit.candidates_by_protocol[proto] = len(cands)
        audit.rules_total += len(rules)
        audit.candidates_total += len(cands)
        sub = audit_semantic_rows(proto, rules, cands)
        audit.constraint_none_count += sub.constraint_none_count
        audit.constraint_none_details.extend(sub.constraint_none_details)
        audit.convertible_true_count += sub.convertible_true_count
        audit.convertible_true_details.extend(sub.convertible_true_details)
        hist.update(sub.reject_reason_histogram)
    audit.reject_reason_histogram = dict(sorted(hist.items()))
    return audit


def _apply_semantic_gate(rep: QualityReport, audit: SemanticAudit) -> None:
    """把 B-9 的度量写进质量报告，并按**强制机制 4**追加阻断项。"""
    totals = dict(audit.rules_by_protocol)
    totals["total"] = audit.rules_total
    rep.semantic_rules_total = totals
    rep.semantic_executable_rules = audit.rules_total - audit.constraint_none_count
    rep.executable_rate = (rep.semantic_executable_rules / audit.rules_total) \
        if audit.rules_total else 0.0
    rep.executable_rate_note = (
        f"可执行率 = 带 constraint 的规则数 / 规则总数 = "
        f"{rep.semantic_executable_rules} / {audit.rules_total}"
        if audit.rules_total else
        "规则总数为 0 ⇒ 可执行率记 **0.0**（不是 1.0）："
        "本轮没有任何语义规则，空集**不得**伪装成 100%"
    )
    rep.semantic_candidates_total = audit.candidates_total
    rep.reject_reason_histogram = dict(audit.reject_reason_histogram)
    rep.constraint_none_count = audit.constraint_none_count
    rep.constraint_none_details = [dict(d) for d in audit.constraint_none_details]
    rep.convertible_true_count = audit.convertible_true_count
    rep.convertible_true_details = [dict(d)
                                    for d in audit.convertible_true_details]

    # ★ 自检：本轮闸口是否**真的**被检验过（产出了规则/候选）。
    rep.gate_exercised = bool(audit.rules_total or audit.candidates_total)
    conv_total = audit.rules_total + audit.candidates_total
    conv = (audit.rules_total / conv_total) if conv_total else 0.0
    if not rep.gate_exercised:
        rep.gate_note = (
            "本轮**无任何语义规则/候选**（规则 0 条、候选 0 条）⇒ "
            "**闸口未被检验**：此时「0 违规」**不等于**「通过」。")
    else:
        rep.gate_note = (
            f"闸口**已检验**：规则 {audit.rules_total} 条"
            f"（其中 {rep.semantic_executable_rules} 条带 constraint）、"
            f"候选 {audit.candidates_total} 条"
            f"（候选→规则转化率 {conv:.2%}）；"
            f"违规 `constraint is None` {audit.constraint_none_count} 条、"
            f"`convertible=true` {audit.convertible_true_count} 条 ⇒ "
            + ("**通过**。" if (audit.constraint_none_count == 0
                              and audit.convertible_true_count == 0)
               else "**存在阻断项**。"))

    if audit.constraint_none_count:
        rep.blocking_issues.append(
            f"语义规则闸：rules.jsonl 中 `constraint is None` 的条数 = "
            f"{audit.constraint_none_count}（**必须为 0**）；"
            f"可定位明细（rule_id / 协议 / reject_reason / 源锚点）示例："
            f"{audit.constraint_none_details[:3]}")
    if audit.convertible_true_count:
        rep.blocking_issues.append(
            f"语义规则闸：candidates.jsonl 中 `convertible=true` 的条数 = "
            f"{audit.convertible_true_count}（**必须为 0**）；"
            f"可定位明细（candidate_id / 协议 / reject_reason / 源锚点）示例："
            f"{audit.convertible_true_details[:3]}")


def semantic_quality_report(protocol: str, audit=None) -> QualityReport:
    """**只跑 B-9 语义闸**的质量报告（`rules_only` 模式用）。

    ★ 为什么单独一个入口：`rules_only` **不产出常规 facts / norms** ⇒
      A0.4 的「抽取结果为空（0 条 norm）」这类检查**不适用**（否则会把
      「有意不产 facts」误判成失败）。本入口只跑 B-9 的三个闸。
    """
    rep = QualityReport(protocol=protocol)
    audit = audit if audit is not None else audit_semantic_library(protocol)
    _apply_semantic_gate(rep, audit)
    if audit.malformed_lines:
        rep.warnings.append(
            f"语义四库有 {audit.malformed_lines} 行无法解析（已跳过；"
            f"闸口按可解析行统计）")
    return rep


#: RFC 约束抽取的**结构化提示词**。
#: ★ 契约要点：除原有 5 个字段外，**要求 LLM 直接给出可执行算子**
#:   （``operator`` + ``operand``）⇒ 下游不必再用正则从中文自由文本反推算子
#:   （反推口径的失配率实测高达 73/120）。
#: ★ ``operator`` 取值受控（见 ``core.fused.semantic.OPERATORS``）；
#:   原文无法归到任何算子时**填空字符串**（表示「这条不是可执行约束」）——
#:   允许模型诚实地否定，比逼它硬编一个算子更可靠。
#: ★ ``operand``：有参算子必给至少一个取值；``present``/``absent`` 必须给空数组。
_PROMPT_CONSTRAINT = """你是 {protocol} 协议规范分析专家。下面是从 RFC 文档摘出的规范性约束句子。
请从中提取「字段语义约束」，并结构化输出。

对每条约束提取：
- field：受约束的字段名（如 QNAME、RDLENGTH、Transport）
- constraint：约束内容（该字段应满足的合法要求，如「单 label ≤ 63 字节」）
- violation：违反该约束的方式（非法输入，如「label 长度字段 > 实际内容」）
- expected_code：违反后接收方应返回的**具体**响应码/错误码（推断不到留空字符串）
- expected_behavior：违反后接收方应有的行为（自由描述，推断不到留空字符串）
- expected_class：**期望响应类别**，从下列受控词表中**选一个**（这是下游闸门依据）：
    success（接收方正常接受并处理）
    protocol_error（接收方判定请求违反协议并拒绝）
    application_error（协议本身合法，但业务上无法处理）
    silence（接收方不响应，保持静默）
  原句无法判断时填空字符串，不要编造。
- operator：从下列受控词表中**选一个**描述可执行算子：
    le(上界/不得超过/至多)、ge(下界/至少/不小于)、gt(严格大于)、lt(严格小于)、
    eq(等于/必须为某值)、ne(不等于)、in(取值属于集合)、range(取值落在区间)、
    present(必须包含/必须存在)、absent(不得包含/禁止出现)
  原句无法归到任何算子时填空字符串，不要编造。
- operand：算子的操作数值，字符串数组。
    le/ge/gt/lt/eq/ne/in/range 必须给至少一个数值或取值（如 ["63"]、["smpte","npt"]）；
    present/absent 必须给空数组 []。
  数值只写数字本身，不带单位。

约束句子：
<<<
{text}
>>>

只输出 JSON（不要解释），格式：
{{"constraints": [{{"field": "...", "constraint": "...", "violation": "...",
                    "expected_code": "...", "expected_behavior": "...",
                    "expected_class": "protocol_error",
                    "operator": "le", "operand": ["63"]}}]}}"""

#: 提示词的**契约版本标识** —— 进 LLM 缓存键
#: （``sha256(candidate_text + prompt_version + model)``）
#: ⇒ **改动提示词内容必须同步改它**，否则会读到旧缓存。
CONSTRAINT_PROMPT_VERSION = "rfc-constraint-structured-p"


#: 期望响应**类别**的受控词表（与 ``rfc_config.expected_response_classes``
#: 同源；此处为**兜底全集**，协议级词表可更窄）。
EXPECTED_CLASSES: tuple[str, ...] = (
    "success", "protocol_error", "application_error", "silence",
)


def _expected_class(value: Any) -> str:
    """把 LLM 给的期望响应类别归一到**受控词表**（不在表内 ⇒ 置空）。

    ★ 这是 C7 闸门（:func:`try_convert`）的依据 ⇒ **必须受控**：
      自由文本（如「返回 400 错误」）无法映射到状态码族，会让 P 侧知识不可用。
    ★ 不在词表内**不报错、只置空** ⇒ 与「推断不到留空字符串」的提示语义一致。
    """
    text = str(value or "").strip().lower()
    if text in EXPECTED_CLASSES:
        return text
    return ""


def infer_constraints(protocol: str, llm=None, max_candidates: int = 40,
                      batch_size: int = 8) -> list[dict]:
    """LLM 结构化约束：把 rule 候选段落喂 LLM，输出 (field/constraint/violation/
    expected_code/expected_behavior/operator/operand)（对齐 SemFuzz 的 C/P 配对）。

    ★ ``operator`` / ``operand`` 是**结构化算子**：LLM 直接给出受控算子与取值，
      下游（:func:`extract_constraint_norms` → norm → fact）据此携带可执行算子，
      **不再**从中文自由文本反推。

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
            # ★ 结构化算子：只收受控词表内的算子；有参算子必须带 operand
            #   （否则视为 LLM 输出不完整 ⇒ 留空，由下游按「无可执行算子」处理）。
            #   ★ 算子词表的**唯一真源**是 ``core.fused.semantic.OPERATORS``
            #     （惰性导入 ⇒ 避免模块级循环导入）。
            from core.fused.semantic import OPERATORS as _OPERATOR_DOMAIN
            operator = (c.get("operator") or "").strip()
            if operator not in _OPERATOR_DOMAIN:
                operator = ""
            raw_operand = c.get("operand") or []
            operand = ([str(x).strip() for x in raw_operand
                        if str(x).strip()]
                       if isinstance(raw_operand, (list, tuple)) else [])
            if operator in ("present", "absent"):
                operand = []
            if operator and operator not in ("present", "absent") and not operand:
                operator, operand = "", []

            out.append({
                "field": field,
                "constraint": constraint,
                "violation": (c.get("violation") or "").strip(),
                "expected_code": (c.get("expected_code") or "").strip(),
                "expected_behavior": (c.get("expected_behavior") or "").strip(),
                # ★ 期望响应**类别**（受控词表）⇒ C7 闸门依据。
                #   ★ 校验：不在受控词表内 ⇒ 置空（宁可无 P 侧，不引入脏类别）。
                "expected_class": _expected_class(c.get("expected_class")),
                "operator": operator,
                "operand": operand,
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
        # ★ content 串携带**结构化算子**（``operator=`` / ``operand=``）
        #   ⇒ norm → fact 链路不再丢失算子（下游据此渲染可执行约束）。
        #   ★ operand 是**列表** ⇒ 用逗号连接的字符串承载（解析时按逗号切分）。
        _operand = c.get("operand") or []
        _operand_text = ",".join(str(x) for x in _operand)
        content = (f"field={c['field']} constraint={c['constraint']} "
                   f"violation={c['violation']} code={c['expected_code']} "
                   f"behavior={c['expected_behavior']} "
                   f"class={c.get('expected_class') or ''} "
                   f"operator={c.get('operator') or ''} "
                   f"operand={_operand_text}")
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
            # ★ 结构化算子随 norm 下沉（供实验侧与下游直接消费，
            #   无需再从 content 串反解）。
            "operator": c.get("operator") or "",
            "operand": list(c.get("operand") or []),
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
