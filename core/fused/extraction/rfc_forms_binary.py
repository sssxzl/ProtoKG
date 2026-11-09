# -*- coding: utf-8 -*-
"""core/fused/rfc_forms_binary.py —— **二进制协议**的 RFC 形态层（2026-11-07 新增）。

★ 与文本形态层（:mod:`core.fused.extraction.rfc_forms`）**并列**、互不依赖：
    · 文本形态层按**行**分类（table / normative / example / prose / …）；
    · 二进制形态层按**表块**分类（位域图 / 定长字段表 / 选项表）。

★ 三类新形态（全部**协议无关**，不认协议名）：

  ① ``bitfield``  —— **位域图**
     形态（RFC 2131 §4.1）：
         +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
         |     op (1)    |   htype (1)   |   hlen (1)    |   hops (1)    |
         +---------------+---------------+---------------+---------------+
         |                            xid (4)                            |
         +-------------------------------+-------------------------------+
     ⇒ 产出：字段名 + 字节长度 + 出现顺序（⇒ 可推 offset）

  ② ``fixed_field`` —— **定长字段表**
     形态：「``XID`` 4 octets」/「``htype`` 1 octet」这类「字段名 + 长度」的描述行。
     ⇒ 产出：字段名 + 字节长度

  ③ ``option_table`` —— **选项表**
     形态（RFC 2132）：「``Code`` / ``Name`` / ``Length``」三列表头 + 数据行。
     ⇒ 产出：选项 code + 名称 + 长度
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ===========================================================================
# ① 位域图
# ===========================================================================

#: 位域图里的字段：**实测形态** ``|     op (1)    |   htype (1)   |``
#:   ⇒ 长度标记**只有数字**（没有 "octet"/"byte" 单位词）⇒ 单位词必须**可选**。
#:   ★ 初版把单位词写成必需 ⇒ 实测 0 命中 ⇒ 判据完全失效（已修）。
#:   ★ 字段名字符类**不能含 ``|``** —— 否则同行多字段时，非贪婪匹配会
#:     跨过 ``|`` 把两段拼成一个名字（实测 ``| op (1) | htype (1) |``
#:     只抽出 ``op`` 与 ``hlen``，中间的 ``htype``/``hops``/``flags`` 全丢）。
#: ★ **单元格级**匹配：先按 ``|`` 切分，再逐格匹配
#:   （初版直接对整行做非贪婪匹配 ⇒ 会**跨过 ``|``** 把两段拼成一个名字，
#:     实测 ``| op (1) | htype (1) | hlen (1) |`` 只抽出 ``op``/``hlen``，
#:     中间的 ``htype``/``hops``/``flags`` 全丢）。
RE_BITFIELD_CELL = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 _-]*?)\s*\((\d+)(?:\s*(?:octet|byte)s?)?\)\s*$",
    re.IGNORECASE)

#: 位域图的**框线**（`+---+` / `+-+-+`）
RE_BITFIELD_RULE = re.compile(r"^\s*\+[-+]+\+\s*$")


@dataclass
class BitfieldField:
    """位域图里的一个字段。"""

    name: str
    length: int          # 字节数
    order: int           # 出现顺序（⇒ 推 offset）
    line_no: int = 0


@dataclass
class BitfieldBlock:
    """一段位域图（连续的多行）。"""

    fields: list[BitfieldField] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0
    text: str = ""


def extract_bitfield_blocks(lines: list[str]) -> list[BitfieldBlock]:
    """从 RFC 文本里抽**位域图**块。

    ★ 判据（协议无关）：
      ① 块内含**框线行**（``+---+``）—— 这是 ASCII 图的强特征；
      ② 块内含**至少 1 行位域字段**（``| name (N) |``）。

    Returns:
        位域图块列表（按出现序）。
    """
    out: list[BitfieldBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        if not RE_BITFIELD_RULE.match(lines[i]):
            i += 1
            continue
        # 从这条框线往下扫，直到离开图区
        lo = i
        hi = i
        fields: list[BitfieldField] = []
        j = i
        order = 0
        while j < n:
            ln = lines[j]
            if RE_BITFIELD_RULE.match(ln):
                hi = j
                j += 1
                continue
            if not ln.strip():
                break
            # ★ 一行**可能有多字段** ⇒ 按 ``|`` 切分成**单元格**再逐格匹配
            #   （直接对整行做非贪婪匹配会跨过 ``|`` 拼名 ⇒ 漏字段）
            _any = False
            if ln.strip().startswith("|"):
                for _cell in ln.split("|")[1:-1]:
                    m = RE_BITFIELD_CELL.match(_cell)
                    if not m:
                        continue
                    name = " ".join(m.group(1).split())
                    if not name:
                        continue
                    fields.append(BitfieldField(name=name,
                                                length=int(m.group(2)),
                                                order=order, line_no=j + 1))
                    order += 1
                    _any = True
            if _any:
                hi = j
            elif ln.strip().startswith("|"):
                hi = j          # 图内的续行（如 xid 跨 4 字节的说明）
            j += 1
        if fields:
            out.append(BitfieldBlock(fields=fields, line_start=lo + 1,
                                     line_end=hi + 1,
                                     text="\n".join(lines[lo:hi + 1])))
        i = max(j, i + 1)
    return out


# ===========================================================================
# ② 定长字段表
# ===========================================================================

#: 「字段名 + N octets/bytes」的行（**行首缩进**，避免命中散文）
RE_FIXED_FIELD = re.compile(
    r"^\s{0,8}([A-Za-z][A-Za-z0-9_.-]{1,30})\s+(\d+)\s+(octets?|bytes?)\b",
    re.IGNORECASE)


#: 定长字段的**停用词**（实测「length 312 octets」这类散文会被误抽）
_GENERIC_FIELD_WORDS = frozenset({
    "length", "total", "size", "field", "fields", "value", "values",
    "data", "byte", "bytes", "octet", "octets", "bit", "bits", "header",
    "message", "option", "options", "packet", "minimum", "maximum",
    "at", "least", "most", "the", "a", "an", "of", "and", "or", "is",
    "are", "in", "on", "to", "for", "with", "by", "as", "it",
})


@dataclass
class FixedField:
    """定长字段。"""

    name: str
    length: int
    line_no: int = 0


def extract_fixed_fields(lines: list[str]) -> list[FixedField]:
    """抽「``<字段名>  N octets``」形态的定长字段。

    ★ 判据（协议无关）：行首缩进 ≤8 空格 + 字段名 + 数字 + 字节单位。
    ⇒ 散文里的「the length of the field is 4 octets」不会命中
      （因为字段名位置必须有**紧跟**的数字）。
    """
    out: list[FixedField] = []
    seen: set[tuple[str, int]] = set()
    for i, ln in enumerate(lines):
        m = RE_FIXED_FIELD.match(ln)
        if not m:
            continue
        name = m.group(1).strip()
        # ★ 排除**通用词/散文词**（实测把 "length 312 octets" 当成字段名）
        #   ⇒ 只收「像字段名」的：不含常见散文词，且不是纯通用名词。
        if not name or name.lower() in _GENERIC_FIELD_WORDS:
            continue
        key = (name.lower(), int(m.group(2)))
        if key in seen:
            continue
        seen.add(key)
        out.append(FixedField(name=name, length=int(m.group(2)), line_no=i + 1))
    return out


# ===========================================================================
# ③ 选项表
# ===========================================================================

#: 选项表**表头**（Code / Name / Length 三个词同行）
RE_OPTION_HEADER = re.compile(
    r"\bCode\b.*\bName\b.*\bLen(?:gth)?\b", re.IGNORECASE)

#: 选项表的数据行：``|  1 | Subnet Mask | 4 |`` 或 ``1  Subnet Mask  4``
RE_OPTION_ROW = re.compile(
    r"^\s*\|?\s*(\d{1,3})\s*\|?\s+([A-Za-z][A-Za-z0-9 /()-]{1,40}?)\s*\|?\s*"
    r"(\d+)?\s*\|?\s*$")

#: ★ **独立小节**形态（RFC 2132 的实际形态！）：
#:   每个选项是独立小节，正文里写「The code for this option is 12」，
#:   标题形如 ``3.14. Host Name Option``。
#:   ⇒ 实测 RFC 2132 **没有汇总表** ⇒ 只靠表头判据会抽出 0 个。
RE_OPTION_CODE_SENTENCE = re.compile(
    r"code\s+for\s+this\s+option\s+is\s+(\d{1,3})", re.IGNORECASE)

#: 小节标题里的**选项名**（``3.14. Host Name Option`` ⇒ ``Host Name``）
RE_OPTION_SECTION = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9 /()-]{2,50}?)\s+Option\s*$",
    re.IGNORECASE)


@dataclass
class OptionDef:
    """一个选项定义（code / 名称 / 长度）。"""

    code: int
    name: str
    length: Optional[int] = None
    line_no: int = 0


def extract_option_tables(lines: list[str]) -> list[OptionDef]:
    """抽「选项定义」⇒ ``[{code, name, length}]``。

    ★ **两种形态**（都要支持，协议无关）：

    **形态 A：汇总表**（有些 RFC 有）
        表头行含 ``Code`` + ``Name``（+ ``Length``），数据行形如
        ``| 1 | Subnet Mask | 4 |``。

    **形态 B：独立小节**（★ RFC 2132 的实际形态）
        每个选项是**独立小节**：标题形如 ``3.14. Host Name Option``，
        正文里写「The code for this option is 12」。
        ⇒ **实测 RFC 2132 没有汇总表** ⇒ 只靠形态 A 会抽出 **0** 个。

    Returns:
        选项定义列表（按 code 出现序、去重）。
    """
    out: list[OptionDef] = []
    seen: set[int] = set()

    # ---- 形态 A：汇总表 ----
    in_table = False
    for i, ln in enumerate(lines):
        if RE_OPTION_HEADER.search(ln):
            in_table = True
            continue
        if not in_table:
            continue
        if not ln.strip():
            in_table = False
            continue
        m = RE_OPTION_ROW.match(ln)
        if not m:
            if ln.strip().startswith("|"):
                continue
            in_table = False
            continue
        code = int(m.group(1))
        name = " ".join(m.group(2).split())
        length = int(m.group(3)) if m.group(3) else None
        if not name or code in seen:
            continue
        seen.add(code)
        out.append(OptionDef(code=code, name=name, length=length, line_no=i + 1))

    # ---- 形态 B：独立小节（标题 + 「code for this option is N」）----
    for i, ln in enumerate(lines):
        m_sec = RE_OPTION_SECTION.match(ln)
        if not m_sec:
            continue
        name = " ".join(m_sec.group(2).split())
        # 在该小节内（到下一个标题前）找 code 句
        for j in range(i + 1, min(len(lines), i + 60)):
            if RE_OPTION_SECTION.match(lines[j]):
                break
            m_code = RE_OPTION_CODE_SENTENCE.search(lines[j])
            if not m_code:
                continue
            code = int(m_code.group(1))
            if code in seen:
                break
            # 长度：同段落里的「minimum length is N」/「length is N」
            _len = None
            for k in range(j, min(len(lines), j + 8)):
                m_len = re.search(r"length\s+(?:is|of)\s+(\d+)", lines[k],
                                  re.IGNORECASE)
                if m_len:
                    _len = int(m_len.group(1))
                    break
            seen.add(code)
            out.append(OptionDef(code=code, name=name, length=_len,
                                 line_no=i + 1))
            break
    return out


__all__ = [
    "BitfieldField", "BitfieldBlock", "FixedField", "OptionDef",
    "extract_bitfield_blocks", "extract_fixed_fields", "extract_option_tables",
    "RE_BITFIELD_CELL", "RE_BITFIELD_RULE", "RE_FIXED_FIELD",
    "RE_OPTION_HEADER", "RE_OPTION_ROW",
]
