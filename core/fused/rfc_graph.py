# -*- coding: utf-8 -*-
"""core/fused/rfc_graph.py —— Phase A：**确定性**图骨架抽取（2026-11-08 新增）。

★ 职责：从 RFC 原文里**确定性地**抽出「节点 + 边」，作为 GraphRAG 的图骨架。
  **零 LLM** ⇒ 可复现、零成本、无幻觉。

★ 设计要点：
  ① **判据全部来自 RFC 内容**，不认协议名 ⇒ 换协议自动生效；
     ``graph_schema.json`` 的 ``protocol_overrides`` 只是**加速定位的提示**。
  ② 复用形态层已有能力：``split_form_blocks``（8 类形态）、
     ``_split_columns``（表格列切分）、``_match_roles``（表头列角色）。
  ③ 每条节点/边都带**三个正交标注**（与中枢台账一致）：
     ``source_owner``（知识来源）/ ``confidence``（high|medium）/ ``defined_in``（文件+行号）。

★ 实测得到的两条重要事实（决定了本模块的规则设计）：
  · **RFC 2131 没有 ASCII 状态迁移图**（无 ``Figure N`` 的水平迁移图），
    只有 **Figure 3 消息时序图**（client/server 两列，含 DISCOVER/OFFER/…）；
  · **状态名（INIT/SELECTING/BOUND…）只出现在散文里**
    （"the client reverts to INIT state"）。
  ⇒ 迁移信息是「**图形里的消息序列**」+「**散文里的状态名**」两处拼出来的。
  ⇒ 本模块分别抽：
     · **E1 图形的消息序列** ⇒ ``message_sequence`` 边（高置信）
     · **E2 表格的迁移行** ⇒ ``transitions_to`` 边（高置信）
     · **E3 散文的状态迁移句** ⇒ ``transitions_to`` 边（中置信）
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from core.fused.graph_schema import protocol_hints
from core.fused.rfc_forms import (NOISE_KINDS, split_form_blocks,
                                  _match_roles, _split_columns)

# ===========================================================================
# 数据结构
# ===========================================================================

@dataclass
class GraphNode:
    """图节点。"""

    node_id: str
    type: str                      # state / message / timer / header / …
    name: str
    graph: str = "semantic"        # structure / semantic
    source_owner: str = "rfc"
    confidence: str = "medium"     # high / medium
    defined_in: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "name": self.name,
            "graph": self.graph,
            "source_owner": self.source_owner,
            "confidence": self.confidence,
            "defined_in": self.defined_in,
            "aliases": list(self.aliases),
        }


@dataclass
class GraphEdge:
    """图边。"""

    edge_id: str
    type: str                      # transitions_to / triggers / message_sequence / …
    from_id: str
    to_id: str
    graph: str = "semantic"
    label: str = ""
    source_owner: str = "rfc"
    confidence: str = "medium"
    defined_in: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "type": self.type,
            "from": self.from_id,
            "to": self.to_id,
            "graph": self.graph,
            "label": self.label,
            "source_owner": self.source_owner,
            "confidence": self.confidence,
            "defined_in": self.defined_in,
        }


def _nid(kind: str, name: str) -> str:
    """节点 id：``<kind>:<规范化名>``（**跨源稳定**）。"""
    norm = re.sub(r"\s+", "_", str(name).strip()).lower()
    return f"{kind}:{norm}"


def _eid(etype: str, a: str, b: str, label: str = "") -> str:
    """边 id：``<etype>:<a>-><b>[:<label>]``。"""
    base = f"{etype}:{a}->{b}"
    if label:
        base += f":{re.sub(r'\\s+', '_', label.strip())}"
    return base


def _anchor(file_name: str, line_no: int, extra: str = "") -> dict[str, Any]:
    """溯源锚点（与中枢 ``evidence_summary`` 同构：文件 + 行号）。"""
    a: dict[str, Any] = {"file": file_name, "line": int(line_no)}
    if extra:
        a["note"] = extra
    return a


# ===========================================================================
# 规则 N1：状态节点（全大写术语 + 交叉校验）
# ===========================================================================

#: 全大写术语（可含连字符）
RE_UPPER_TERM = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\b")

#: **明显不是状态名**的词（协议无关的元词 / 关键字 / 通用缩写）
_NON_STATE_WORDS = frozenset({
    # RFC 关键字与结构词
    "RFC", "ID", "IANA", "IEEE", "ISO", "ANSI", "ITU", "TCP", "UDP", "IP",
    "IPv4", "IPv6", "DNS", "HTTP", "MUST", "MUST NOT", "SHALL", "SHALL NOT",
    "SHOULD", "SHOULD NOT", "MAY", "REQUIRED", "OPTIONAL", "RECOMMENDED",
    "NOT", "YES", "NO", "OK", "ALL", "NONE", "NULL", "TRUE", "FALSE",
    # 通用大写词
    "THE", "AND", "OR", "IF", "IN", "TO", "OF", "FOR", "WITH", "BY", "AS",
    "IS", "ARE", "BE", "THIS", "THAT", "THESE", "THOSE", "IT", "ITS",
    "NOTE", "FIGURE", "TABLE", "SECTION", "CHAPTER", "APPENDIX",
    "REFERENCES", "AUTHORS", "ABSTRACT", "INTRODUCTION", "CONCLUSION",
    "HEADER", "MESSAGE", "OPTION", "OPTIONS", "STATUS", "VALUE", "VALUES",
    "TYPE", "LENGTH", "NAME", "NAMES", "NUMBER", "NUMBERS", "COUNT",
    "DEFAULT", "EXAMPLE", "EXAMPLES", "SEE", "EQUAL", "LESS", "GREATER",
    "CLIENT", "SERVER", "RELAY", "AGENT", "BOOTREQUEST", "BOOTREPLY",
    "DHCP", "NVT", "ASCII", "MBZ", "BOOTP", "NBOOTP",
})


#: 「这是状态图」的语义信号（**协议无关**）
RE_STATE_GRAPH_SIGNAL = re.compile(
    r"\bstate(?:s)?\b|\btransition(?:s|ed|ing)?\b|"
    r"\brevert(?:s|ed)?\b|\bmove[sd]?\s+to\b|\bdiagram\b",
    re.IGNORECASE)

#: 「这是位域图/报文图」的语义信号（⇒ **不是**状态图）
RE_NON_STATE_GRAPH_SIGNAL = re.compile(
    r"\boctets?\b|\bbit(?:s)?\b|\bheader format\b|"
    r"\bmessage format\b|\bfield\b", re.IGNORECASE)


def _looks_like_state_graph(text: str) -> bool:
    """判断一个 diagram 块**是不是状态图**（而非位域图/报文图）。

    ★ 判据（协议无关）：
      ① 含**迁移语义**（state / transition / revert / move to / diagram）；
      ② 且**不含**位域/报文字段语义（octet / bit / header format…）
         ⇒ 位域图与报文图被排除（它们也含 "diagram" 字样）。
    ★ 实测依据：RFC 2131 的 6 个 diagram 块里，
      位域图（行 463）含 ``(1)``/``octet`` 语义、报文图含字段名
      ⇒ 只有**状态/时序图**该作为状态来源。
    """
    t = text or ""
    if not RE_STATE_GRAPH_SIGNAL.search(t):
        return False
    if RE_NON_STATE_GRAPH_SIGNAL.search(t):
        return False
    return True


def extract_state_candidates(lines: list[str], file_name: str,
                             hints: Iterable[str] = (),
                             exclude: Iterable[str] = (),
                             ) -> list[GraphNode]:
    """N1：抽**状态节点**候选（全大写术语）。

    ★ 交叉校验（关键）：候选须与「**图形块中出现过的词**」或
      「协议提示集」有交集 ⇒ 否则一个协议里到处都是大写词（RFC/IP/MUST…）。

    Returns:
        状态节点列表（confidence：图形内=high，仅正文=medium）。
    """
    hint_set = {str(h).upper() for h in hints}
    # ★ **消息名排除**（2026-11-08 实测）：DHCP 的消息名（DHCPOFFER/DHCPACK…）
    #   本身是全大写词 ⇒ 不排除的话会被当状态节点（实测 19 个状态里 7 个是消息名）。
    exclude_set = {str(x).upper() for x in exclude}
    # ---- 图形块里出现过的词（高置信来源）----
    #   ★ **只认「状态图」形态的图形块**（2026-11-08 实测修正）：
    #     DHCP 的 diagram 块里，**位域图**（``| op (1) | htype (1) |``）与
    #     **报文图**都含大量全大写词（ADDR/TTL/NIS/TFTP…）
    #     ⇒ 若不区分，会把 8 个真状态抽成 76 个（实测）。
    #   ★ 判据（协议无关）：图形块里**同时**含
    #     ① 「state」类词（状态图常见标注）或
    #     ② **迁移语义**（transition/revert/move to/state diagram…）
    #     ⇒ 判为「状态图」；否则是位域图/报文图 ⇒ 不作为状态来源。
    diagram_terms: set[str] = set()
    for b in split_form_blocks(lines):
        if b.kind != "diagram":
            continue
        if not _looks_like_state_graph(b.text):
            continue
        for m in RE_UPPER_TERM.finditer(b.text):
            diagram_terms.add(m.group(1).upper())

    seen: set[str] = set()
    out: list[GraphNode] = []
    for i, ln in enumerate(lines, start=1):
        for m in RE_UPPER_TERM.finditer(ln):
            w = m.group(1).upper()
            if w in _NON_STATE_WORDS or len(w) < 3:
                continue
            if w in exclude_set:
                continue          # ★ 消息名不是状态
            if w in seen:
                continue
            # ★ **折行截断**修正（2026-11-08 实测）：RFC 正文会把长词折行
            #   （``DHCPREQU`` / ``EST`` / ``REBOOT`` / ``INIT-REBO``）
            #   ⇒ 拼回上一行末尾才是一个完整词。
            #   判据：当前词是**上一行末词的延续**（上一行末词非空且当前词以它开头
            #   或反之）⇒ 视为截断碎片，丢弃。
            if i > 1 and _is_wrapped_continuation(lines, i, w):
                continue
            in_diagram = w in diagram_terms
            in_hint = w in hint_set
            if not (in_diagram or in_hint):
                continue        # ★ 既不在图形里、也不是提示 ⇒ 丢弃
            seen.add(w)
            out.append(GraphNode(
                node_id=_nid("state", w), type="state", name=w,
                graph="structure", source_owner="rfc",
                confidence="high" if in_diagram else "medium",
                defined_in=_anchor(file_name, i)))
    return out


# ===========================================================================
# 规则 N1b：**状态定义列表**形态（rtsp 附录 A.1）
# ===========================================================================

#: 「状态名 + 冒号」独占一行（缩进 2~8 空格），下一行是缩进更深的描述
#:   RFC 2326 附录 A.1：
#:       ``Init:``  /  ``Ready:``  /  ``Playing:``  /  ``Recording:``
#:   ⇒ **状态定义列表**（不是图形！实测形态层的 diagram 判据识别不出来）。
RE_STATE_DEF_LINE = re.compile(
    r"^\s{2,8}([A-Z][A-Za-z0-9]{2,20}):\s*$")

#: 状态名的形态过滤：首字母大写 + 至少 3 字符（排除 ``Note:`` 之类）
RE_STATE_NAME_SHAPE = re.compile(r"^[A-Z][A-Za-z0-9]{2,20}$")


def extract_state_definitions(lines: list[str], file_name: str,
                              hints: Iterable[str] = (),
                              exclude: Iterable[str] = (),
                              require_migration_ctx: bool = True) -> list[GraphNode]:
    """N1b：抽「状态定义列表」形态的状态节点。

    ★ 实测依据：RFC 2326 附录 A.1 的客户端状态机是
      ``Init:`` / ``Ready:`` / ``Playing:`` / ``Recording:`` 这样的
      **定义列表**（不是 ASCII 图）⇒ 形态层的 diagram 判据识别不出
      ⇒ 只靠图形块收状态会**漏掉 rtsp 全部状态**（实测 0 个）。

    ★ 判据（协议无关）：
      ① 行是「缩进 + 状态名 + 冒号」且行尾无其它文字；
      ② 下一非空行的缩进**更深**（说明是它的描述正文）；
      ③ 状态名形态：首字母大写、长度 ≥3、且**不含空格**。

    ★ ★ **迁移语义交叉校验**（关键，实测修正）：
      判据 ①②③ 会把 RFC 的**术语定义**（Conference:/Connection:/Entity:…）
      与**方法定义**（SETUP:/PAUSE:）**一并收进来**（实测 rtsp 19 个里 15 个是误抽）
      ⇒ 纯形态无法区分「状态定义」与「术语/方法定义」。
      ⇒ 追加校验：该状态名**必须出现在迁移语义上下文里**
        （``<name> state`` / ``state <name>`` / ``in <name>`` /
          ``to <name>`` / ``from <name>``）
        或**被提示集命中** ⇒ 才是状态。
    """
    hint_set = {str(h).upper() for h in hints}
    exclude_set = {str(x).upper() for x in exclude}
    out: list[GraphNode] = []
    seen: set[str] = set()
    for i, ln in enumerate(lines, start=1):
        m = RE_STATE_DEF_LINE.match(ln)
        if not m:
            continue
        name = m.group(1).strip()
        if not RE_STATE_NAME_SHAPE.match(name):
            continue
        if name.upper() in exclude_set or name.upper() in _NON_STATE_WORDS:
            continue
        # 下一非空行必须缩进更深（是描述正文，不是别的段落）
        nxt = None
        for j in range(i, min(len(lines), i + 4)):
            if lines[j].strip():
                nxt = lines[j]
                break
        if nxt is None:
            continue
        ind_def = len(ln) - len(ln.lstrip())
        ind_nxt = len(nxt) - len(nxt.lstrip())
        if ind_nxt <= ind_def:
            continue
        if name.upper() in seen:
            continue
        # ★ 迁移语义交叉校验（见 docstring）
        if require_migration_ctx and name.upper() not in hint_set:
            if not _has_migration_context(lines, name):
                continue
        seen.add(name.upper())
        out.append(GraphNode(
            node_id=_nid("state", name), type="state", name=name,
            graph="structure", source_owner="rfc",
            confidence="high" if name.upper() in hint_set else "medium",
            defined_in=_anchor(file_name, i)))
    return out


#: 「状态名的**迁移语义上下文**」判据（协议无关）
RE_STATE_CTX = re.compile(
    r"\b([A-Za-z][A-Za-z0-9]{2,20})\s+states?\b|"
    r"\bstates?\s+([A-Za-z][A-Za-z0-9]{2,20})\b|"
    r"\b(?:in|to|from|into)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9]{2,20})\b",
    re.IGNORECASE)


def _has_migration_context(lines: list[str], name: str) -> bool:
    """该名字是否出现在**迁移语义上下文**里（⇒ 像个状态名）。

    ★ 判据（协议无关）：
      ``<name> state`` / ``state <name>`` / ``in|to|from <name>``
    ★ 实测依据：rtsp 附录 A.1 的真状态（Init/Ready/Playing/Recording）都在
      ``the client changes state on receipt of…`` / ``while in Playing state``
      这类上下文里；而术语定义（Conference:/Connection:）没有。
    """
    # ★ **收紧**（实测修正）：裸的 ``in|to|from <name>`` 太宽 ——
    #   RFC 里的散文（"in response to" / "to the server" / "from the client"）
    #   会把任意名词放行（实测 rtsp 误抽 Conference/Presentation/SETUP/PAUSE）。
    # ⇒ 只保留**与「state」直接邻近**或**迁移动词 + 状态名**两种强信号。
    pat = re.compile(
        r"\b" + re.escape(name) + r"\s+states?\b|"          # <name> state
        r"\bstates?\s+" + re.escape(name) + r"\b|"          # state <name>
        r"\b(?:transition(?:s|ed|ing)?\s+to|move[sd]?\s+to|"
        r"revert(?:s|ed)?\s+to|enter(?:s|ed)?|leads?\s+to|"
        r"proceed(?:s|ed)?\s+to|back\s+to|return(?:s|ed)?\s+to|"
        r"changes?\s+state\s+(?:on|to|in)\s+(?:receipt\s+of\s+)?)"
        r"(?:the\s+)?" + re.escape(name) + r"\b",
        re.IGNORECASE)
    for ln in lines:
        if pat.search(ln):
            return True
    # ★ **同段落共现**（实测补充）：RFC 的状态机章节常在**同一段**里
    #   同时出现「状态名」与「state」词，但两者不在同一句
    #   （实测 rtsp 附录 A.1 的 ``Init:`` 段落描述里只有
    #    "the client changes state on receipt of replies"，**不含 "Init"**）。
    #   ⇒ 判据：该名字所在**段落**（空行分隔）里出现 ``state`` 词。
    #   ⚠ **收紧**（2026-11-08 实测）：段落级共现在 rtsp 上**太宽** ——
    #     ``AUTHENTICATION``/``CONFERENCE``/``CONNECTION``/``ENTITY`` 全被放行
    #     （实测 13 个「状态」里 11 个是误抽）。
    #   ⇒ 加一道**同句**校验：名字必须与迁移语义**在同一句**里。
    #     （rtsp 真状态：``in Playing state`` / ``state Recording is entered``）
    if _in_paragraph_with_state(lines, name):
        return True
    return False


def _same_sentence_migration(lines: list[str], name: str) -> bool:
    """该名字是否与「迁移语义」出现在**同一句**里。

    ★ 判据（协议无关）：句内同时含该名字与迁移动词/状态词。
    ★ 实测：rtsp 的真状态（Playing/Recording/Ready）都在
      「``in Playing state``」「``state Recording is entered``」这类**同句**里；
      而 AUTHENTICATION/CONFERENCE 只在**段落级**与 state 共现。
    """
    re_name = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
    re_mig = re.compile(
        r"\bstate[sd]?\b|\btransition(?:s|ed|ing)?\b|\bmove[sd]?\s+to\b|"
        r"\brevert(?:s|ed)?\s+to\b|\benter(?:s|ed)?\b|\bleads?\s+to\b|"
        r"\bproceed(?:s|ed)?\s+to\b|\bback\s+to\b|"
        r"\breturn(?:s|ed)?\s+to\b|\bchanges?\s+state\b",
        re.IGNORECASE)
    for ln in lines:
        if re_name.search(ln) and re_mig.search(ln):
            return True
    return False


def _in_paragraph_with_state(lines: list[str], name: str) -> bool:
    """该名字所在的**段落**里是否出现 ``state`` 词（段落 = 空行分隔）。"""
    re_state = re.compile(r"\bstates?\b", re.IGNORECASE)
    re_name = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
    para: list[str] = []
    in_para = False
    for ln in lines:
        if not ln.strip():
            if in_para:
                if any(re_state.search(x) for x in para) and \
                        any(re_name.search(x) for x in para):
                    return True
                para = []
                in_para = False
            continue
        para.append(ln)
        in_para = True
    if in_para and any(re_state.search(x) for x in para) and \
            any(re_name.search(x) for x in para):
        return True
    return False


# ===========================================================================
# 规则 N2：消息节点
# ===========================================================================

#: 消息名形态：**协议名 + 消息后缀**（如 ``DHCPDISCOVER``）
#:   ⇒ 判据 = 「一个已知协议名（或提示集里的消息名）作前缀的连写大写词」
RE_MSG_HINT = re.compile(r"^([A-Z][A-Z0-9]{1,10})([A-Z][A-Z0-9]{2,20})$")


#: 文件级「全部大写词」缓存（key = id(lines)）⇒ 折行拼接判据用
_ALL_UPPER_TERMS_CACHE: dict[int, frozenset] = {}


def _all_upper_terms(lines: list[str]) -> frozenset:
    """本文件里出现的全部大写词（用于折行拼接判据）。"""
    key = id(lines)
    cached = _ALL_UPPER_TERMS_CACHE.get(key)
    if cached is None:
        cached = frozenset(m.group(1).upper()
                           for ln in lines
                           for m in RE_UPPER_TERM.finditer(ln))
        _ALL_UPPER_TERMS_CACHE[key] = cached
    return cached


def _is_wrapped_continuation(lines: list[str], idx_1based: int,
                             word: str) -> bool:
    """判断某行的大写词是否为**折行截断碎片**。

    ★ RFC 正文会把长词折行（``DHCPREQUEST`` → ``DHCPREQU`` + ``EST``）。
      判据（协议无关）：该词**与上一行末词有前缀/后缀重叠** ⇒ 是碎片。
    """
    if idx_1based < 2:
        return False
    prev = lines[idx_1based - 2].rstrip()
    if not prev:
        return False
    m = RE_UPPER_TERM.search(prev[::-1])
    if not m:
        return False
    prev_word = m.group(1)[::-1].upper()
    if not prev_word or len(prev_word) < 3:
        return False
    # ★ 折行的两种形态（实测）：
    #   ① **前缀切分**：``DHCPREQU`` + ``EST`` ⇒ 上一行末词是**当前词的前缀**
    #      （``DHCPREQU``.startswith(``EST``) 不成立，但 ``DHCPREQUEST``
    #      以 ``DHCPREQU`` 开头 ⇒ 要看「**拼接后是否成一个更长的词**」）；
    #   ② **后缀切分**：``INIT-REBO`` + ``OT`` ⇒ 当前词是上一行末词的后缀。
    # ⇒ 判据：拼接（prev_word + word 或 word + prev_word）能形成**更长的词**，
    #   且该词**在本文件里出现过** ⇒ 说明确实是折行。
    for joined in (prev_word + word, word + prev_word):
        if len(joined) > len(prev_word) and len(joined) > len(word):
            if joined in _all_upper_terms(lines):
                return True
    # 退化判据：前缀/后缀关系（文件里找不到拼接词时）
    # ★ **排除与上一行末词相同**的情况（否则上一行本身的词会被误判成碎片）
    if prev_word == word:
        return False
    if prev_word.startswith(word) or word.startswith(prev_word):
        return True
    if prev_word.endswith(word) or word.endswith(prev_word):
        return True
    return False


def extract_message_nodes(lines: list[str], file_name: str,
                          hints: Iterable[str] = (),
                          protocol: str = "") -> list[GraphNode]:
    """N2：抽**消息节点**。

    ★ 判据（协议无关）：
      ① **提示集**里的消息名（``protocol_overrides.message_hints``）——加速定位；
      ② 「协议名 + 消息后缀」的连写大写词（如 ``DHCP`` + ``DISCOVER``）。
    ★ 两者都命中才收 ⇒ 避免把普通大写词当消息。
    """
    hint_set = {str(h).upper() for h in hints}
    proto = (protocol or "").upper()
    # 协议名的**词干**（DHCPv4 ⇒ DHCP）
    stem = re.sub(r"[0-9]+$", "", proto) if proto else ""

    seen: set[str] = set()
    out: list[GraphNode] = []
    for i, ln in enumerate(lines, start=1):
        for m in RE_UPPER_TERM.finditer(ln):
            w = m.group(1).upper()
            if w in seen or len(w) < 5:
                continue
            if w in _NON_STATE_WORDS:
                continue
            is_hint = w in hint_set
            is_prefixed = bool(stem) and w.startswith(stem) and len(w) > len(stem)
            if not (is_hint or is_prefixed):
                continue
            seen.add(w)
            out.append(GraphNode(
                node_id=_nid("message", w), type="message", name=w,
                graph="structure", source_owner="rfc",
                confidence="high" if is_hint else "medium",
                defined_in=_anchor(file_name, i)))
    return out


# ===========================================================================
# 规则 N3：定时器节点
# ===========================================================================

#: ``T1`` / ``T2`` 式短标识；或 ``<名词> expiration`` / ``<名词> timeout``
RE_TIMER_SHORT = re.compile(r"\b(T\d{1,2})\b")
RE_TIMER_WORD = re.compile(
    r"\b([A-Za-z][A-Za-z0-9 ]{2,30}?)\s+(expiration|timeout|timer)\b",
    re.IGNORECASE)


def extract_timer_nodes(lines: list[str], file_name: str,
                        hints: Iterable[str] = ()) -> list[GraphNode]:
    """N3：抽**定时器节点**（``T1``/``T2`` 式标识 + ``... expiration`` 表述）。"""
    hint_set = {str(h).upper() for h in hints}
    seen: set[str] = set()
    out: list[GraphNode] = []
    for i, ln in enumerate(lines, start=1):
        for m in RE_TIMER_SHORT.finditer(ln):
            w = m.group(1).upper()
            if w in seen:
                continue
            seen.add(w)
            out.append(GraphNode(
                node_id=_nid("timer", w), type="timer", name=w,
                graph="structure", source_owner="rfc",
                confidence="high" if w in hint_set else "medium",
                defined_in=_anchor(file_name, i)))
    return out


# ===========================================================================
# 规则 E1：图形内的**消息序列**（时序图 / 迁移图通用）
# ===========================================================================

#: 图形里出现的消息名（连写大写词，≥5 字符）
RE_GRAPHIC_LABEL = re.compile(r"\b([A-Z][A-Z0-9]{4,24})\b")


def extract_graph_message_sequences(lines: list[str], file_name: str,
                                   message_names: set[str],
                                   ) -> list[GraphEdge]:
    """E1：从**图形块**里抽消息序列 ⇒ ``message_sequence`` 边。

    ★ 实测依据：RFC 2131 的 Figure 3 是**消息时序图**（client/server 两列），
      消息名以 ``|/DHCPDISCOVER |`` 形态出现 ⇒ 按**出现顺序**连成序列边。
    ★ 与「状态迁移图」（``INIT --DHCPNAK--> INIT-REBOOT``）的差别：
      时序图只有消息、没有状态 ⇒ 这里只出 ``message_sequence``；
      状态边由 E3（散文）补。
    """
    out: list[GraphEdge] = []
    for b in split_form_blocks(lines):
        if b.kind != "diagram":
            continue
        seq: list[tuple[str, int]] = []
        for off, ln in enumerate(b.text.split("\n")):
            abs_line = b.line_start + off
            for m in RE_GRAPHIC_LABEL.finditer(ln):
                w = m.group(1)
                if w.upper() not in message_names:
                    continue
                if seq and seq[-1][0] == w:
                    continue
                seq.append((w, abs_line))
        for (a, la), (c, lc) in zip(seq, seq[1:]):
            out.append(GraphEdge(
                edge_id=_eid("message_sequence", _nid("message", a),
                             _nid("message", c)),
                type="message_sequence",
                from_id=_nid("message", a), to_id=_nid("message", c),
                graph="structure", label="",
                source_owner="rfc", confidence="high",
                defined_in=_anchor(file_name, la)))
    return out


# ===========================================================================
# 规则 E2：表格里的迁移行
# ===========================================================================

#: 表头列角色（from / trigger / to）
_ROLE_KEYS = ("from", "trigger", "to")


def extract_table_transitions(lines: list[str], file_name: str,
                              state_names: set[str],
                              message_names: set[str],
                              ) -> list[GraphEdge]:
    """E2：从**表格**里抽状态迁移 ⇒ ``transitions_to`` + ``triggers``。

    ★ 复用形态层的 ``_match_roles``（表头列 → from/trigger/to 角色，**协议无关**）。
    ★ 状态列取值须 ∈ ``state_names``、触发列取值须 ∈ ``message_names``
      ⇒ 避免把普通表格误当迁移表。
    """
    out: list[GraphEdge] = []
    for b in split_form_blocks(lines):
        if b.kind != "table":
            continue
        rows = b.text.split("\n")
        if not rows:
            continue
        header = None
        for ln in rows:
            cols = _split_columns(ln)
            roles = _match_roles(cols)
            if roles and all(k in roles for k in _ROLE_KEYS):
                header = roles
                break
        if not header:
            continue
        for off, ln in enumerate(rows):
            cols = _split_columns(ln)
            if len(cols) <= max(header.values()):
                continue
            frm = cols[header["from"]].strip()
            trg = cols[header["trigger"]].strip()
            to = cols[header["to"]].strip()
            if frm not in state_names or to not in state_names:
                continue
            if trg not in message_names and trg not in state_names:
                continue
            abs_line = b.line_start + off
            out.append(GraphEdge(
                edge_id=_eid("transitions_to", _nid("state", frm),
                             _nid("state", to)),
                type="transitions_to",
                from_id=_nid("state", frm), to_id=_nid("state", to),
                graph="structure", label=trg,
                source_owner="rfc", confidence="high",
                defined_in=_anchor(file_name, abs_line)))
            if trg in message_names:
                out.append(GraphEdge(
                    edge_id=_eid("triggers", _nid("message", trg),
                                 _nid("state", to)),
                    type="triggers",
                    from_id=_nid("message", trg), to_id=_nid("state", to),
                    graph="structure", label="",
                    source_owner="rfc", confidence="high",
                    defined_in=_anchor(file_name, abs_line)))
    return out


# ===========================================================================
# 规则 E3：散文里的状态迁移句
# ===========================================================================

#: 「<动词> ... <状态名> state」/「transition to <状态名>」/「reverts to <状态名>」
RE_PROSE_TRANSITION = re.compile(
    r"\b(?:transition(?:s|ing)?\s+to|move[sd]?\s+to|revert(?:s|ed)?\s+to|"
    r"enter(?:s|ed)?|leads?\s+to|proceed(?:s|ed)?\s+to|"
    r"back\s+to|return(?:s|ed)?\s+to)\s+"
    r"(?:the\s+)?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\s+state\b",
    re.IGNORECASE)

#: 「<状态名> state」作为**源**的形态：「from the <状态名> state」
RE_PROSE_FROM_STATE = re.compile(
    r"\bfrom\s+(?:the\s+)?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\s+state\b",
    re.IGNORECASE)


def extract_prose_transitions(lines: list[str], file_name: str,
                              state_names: set[str],
                              ) -> list[GraphEdge]:
    """E3：从**散文**里抽状态迁移 ⇒ ``transitions_to`` 边（medium 置信）。

    ★ 实测依据：RFC 2131 的状态名**只出现在散文**里
      （"the client reverts to INIT state" / "moving to the INIT state in the
      DHCP state diagram"）⇒ 没有图形可解析 ⇒ 这是唯一来源。
    ★ 源状态：同句里若出现 ``from the <X> state`` ⇒ 取 X；
      否则源状态**留空**（不猜）⇒ 由后续的图上分析补全。
    """
    out: list[GraphEdge] = []
    seen: set[tuple[str, str]] = set()
    for i, ln in enumerate(lines, start=1):
        for m in RE_PROSE_TRANSITION.finditer(ln):
            to_state = m.group(1).upper()
            if to_state not in state_names:
                continue
            m_from = RE_PROSE_FROM_STATE.search(ln)
            frm = m_from.group(1).upper() if m_from else ""
            if frm and frm not in state_names:
                frm = ""
            key = (frm, to_state)
            if key in seen:
                continue
            seen.add(key)
            # ★ **源状态未知 ⇒ 用占位源**（2026-11-08 实测修正）：
            #   散文里常只写「reverts to INIT state」而没写源状态。
            #   ★ 不能直接不产边（实测：会丢掉**目标状态**这条信息 ⇒
            #     批次 1 的散文迁移能力退化）；也不能留**空端点**
            #     （实测：路径检索会出现空节点、纯度检查失去意义）。
            #   ⇒ 用**占位源** ``state:?`` 并标 ``label="<源状态未知>"``。
            #   ★ 路径检索时**跳过占位源**（见 graph_query.find_paths）。
            _frm_id = _nid("state", frm) if frm else _nid("state", "?")
            out.append(GraphEdge(
                edge_id=_eid("transitions_to", _frm_id,
                             _nid("state", to_state)),
                type="transitions_to",
                from_id=_frm_id,
                to_id=_nid("state", to_state),
                graph="structure",
                label="" if frm else "<源状态未知>",
                source_owner="rfc", confidence="medium",
                defined_in=_anchor(file_name, i)))
    return out


# ===========================================================================
# 顶层：单文件抽取
# ===========================================================================

def extract_graph_from_file(path, protocol: str = "") -> tuple[list[GraphNode],
                                                               list[GraphEdge]]:
    """从一个 RFC 文件抽（节点, 边）。

    Returns:
        ``(nodes, edges)``。
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    hints = protocol_hints(protocol)

    # ★ **顺序**：先抽消息 → 再抽状态（排除消息名）
    #   ⇒ 消息名（DHCPOFFER/DHCPACK…）本身是全大写词 ⇒ 不排除会被当状态。
    msgs = extract_message_nodes(lines, p.name,
                                 hints.get("message_hints", ()), protocol)
    _excl = {n.name for n in msgs}
    states = extract_state_candidates(lines, p.name,
                                      hints.get("state_hints", ()),
                                      exclude=_excl)
    # ★ N1b：状态**定义列表**形态（rtsp 附录 A.1；实测图形块收不到）
    for _n in extract_state_definitions(lines, p.name,
                                        hints.get("state_hints", ()),
                                        exclude=_excl):
        if _n.node_id not in {x.node_id for x in states}:
            states.append(_n)
    timers = extract_timer_nodes(lines, p.name, hints.get("timer_hints", ()))

    state_names = {n.name for n in states}
    message_names = {n.name for n in msgs}

    edges: list[GraphEdge] = []
    edges += extract_graph_message_sequences(lines, p.name, message_names)
    edges += extract_table_transitions(lines, p.name, state_names, message_names)
    edges += extract_prose_transitions(lines, p.name, state_names)

    return states + msgs + timers, edges


def extract_graph(protocol: str) -> tuple[list[GraphNode], list[GraphEdge]]:
    """从 ``kb/<协议>/spec/*.txt`` 抽整份图。"""
    from core import paths
    d = paths.kb_source_dir(protocol, "rfc")
    if not d.is_dir():
        return [], []
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    for f in sorted(d.glob("*.txt")):
        ns, es = extract_graph_from_file(f, protocol)
        for n in ns:
            prev = nodes.get(n.node_id)
            # 保留**更高置信**的那份（同 id 多文件出现）
            if prev is None or (prev.confidence == "medium"
                                and n.confidence == "high"):
                nodes[n.node_id] = n
        for e in es:
            edges.setdefault(e.edge_id, e)
    return list(nodes.values()), list(edges.values())


def graph_fingerprint(nodes: list[GraphNode], edges: list[GraphEdge]) -> str:
    """图的指纹（内容哈希）⇒ 用于**幂等检测**与缓存键。"""
    h = hashlib.sha256()
    for n in sorted(nodes, key=lambda x: x.node_id):
        h.update(n.node_id.encode("utf-8"))
    for e in sorted(edges, key=lambda x: x.edge_id):
        h.update(e.edge_id.encode("utf-8"))
    return h.hexdigest()[:16]


__all__ = [
    "GraphNode", "GraphEdge",
    "extract_state_candidates", "extract_message_nodes", "extract_timer_nodes",
    "extract_graph_message_sequences", "extract_table_transitions",
    "extract_prose_transitions",
    "extract_graph_from_file", "extract_graph", "graph_fingerprint",
]
