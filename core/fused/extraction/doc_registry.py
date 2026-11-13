# -*- coding: utf-8 -*-
"""core/fused/extraction/doc_registry.py —— **文档级登记**（第四批）。

★ 对应改进计划 §7：

  | 项 | 内容 |
  |---|---|
  | 登记内容 | 从 RFC 头部抽：编号 / 标题 / **文档自述状态** / 日期 / `Updates` / `Obsoletes` / 规范性引用 |
  | ★ 标签语义限定 | ★ 只能标「**该文档自身声明的信息**」⇒ **单篇旧 RFC 的头部无法反映后来其他 RFC 对它的更新或废弃** ⇒ ⇒ **不得**标「当前生效」 |
  | 支持 `unknown` | 无法从头部判定的 ⇒ 记 `unknown`（**不猜**） |
  | 两级信息分开 | ① **文档类别**（Standards Track / Informational / …）<br>② **单条 claim 的规范强度**（MUST / SHOULD / …）⇒ 二者**不可混用** |
  | 不门禁 | ★ **不因状态是 Informational 或已被 Obsoletes 就拒抽** ⇒ 只**标记**，让下游自行过滤 |
  | 产物去向 | 文档登记 ⇒ 写 `derived/per_source/<协议>/<源>/documents.json`<br>⇒ ★ **不进 fact 空间** ⇒ **中枢零影响 / 契约零变化** |

★ ★ **「文档自述状态」≠「当前生效状态」**
  ⇒ 单篇文档只能声明它**自己**是什么 ⇒ 跨文档的效力核查（谁更新了我 / 谁废弃了我）
  ⇒ **本轮不做**（需外部依赖）⇒ ⇒ 标 `unknown` ⇒ ⇒ 时效性风险**仍未关闭**。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: RFC 头部的月份
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

#: **文档类别**（RFC 的 Category 字段）
CATEGORY_STANDARD = "Standards Track"
CATEGORY_INFORMATIONAL = "Informational"
CATEGORY_EXPERIMENTAL = "Experimental"
CATEGORY_BCP = "Best Current Practice"
CATEGORY_UNKNOWN = "unknown"

#: ★ 效力标签的取值（**只表示「该文档自身声明的信息」**）
SELF_DECLARED = "self_declared"
UNKNOWN = "unknown"


@dataclass
class DocumentRecord:
    """一份文档的登记记录。"""

    protocol: str = ""
    source: str = "rfc"
    filename: str = ""
    rfc_number: str = ""
    title: str = ""
    #: ★ **文档自述状态**（Category）⇒ ★ 只表示该文档自己的声明
    category: str = CATEGORY_UNKNOWN
    date: str = ""
    updates: list[str] = field(default_factory=list)
    obsoletes: list[str] = field(default_factory=list)
    also_see: list[str] = field(default_factory=list)
    #: **规范性引用**（正文/头部提到的其它 RFC 编号）
    normative_refs: list[str] = field(default_factory=list)
    #: ★ 效力标签（★ **不表示「当前有效」**）
    status_label: str = SELF_DECLARED
    #: 头部区块的原文（供核对）
    header_raw: str = ""

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "source": self.source,
            "filename": self.filename,
            "rfc_number": self.rfc_number,
            "title": self.title,
            # ★ 文档类别 = 该文档**自述**的类别
            "category": self.category,
            "date": self.date,
            "updates": list(self.updates),
            "obsoletes": list(self.obsoletes),
            "also_see": list(self.also_see),
            "normative_refs": list(self.normative_refs),
            # ★ 效力标签：**只表示「该文档自身声明的信息」**
            #   ⇒ ★ **不得**解读为「当前生效」
            "status_label": self.status_label,
            "note": ("★ 「文档自述状态」≠「当前生效状态」⇒ 跨文档效力核查"
                     "（Updates/Obsoletes 的实际影响）**本轮未做**⇒ "
                     "效力时效性风险**仍未关闭**"),
        }


def _rfc_list(text: str) -> list[str]:
    """从 ``2545, 2549`` 这类串里抽编号列表。"""
    return [str(x) for x in re.findall(r"\b\d{3,5}\b", text or "")]


def parse_header(text: str, *, protocol: str = "", source: str = "rfc",
                 filename: str = "") -> DocumentRecord:
    """从 RFC 文本**头部区块**抽登记信息。

    ★ 只解析**头部**（前 40 行）⇒ ⇒ 正文里的 ``RFC 1234`` 不会被当成
      「规范性引用」误收。

    Args:
        text: 文档全文（只取头部若干行）。
        protocol: 协议名。
        source: 源名。
        filename: 文件名。

    Returns:
        :class:`DocumentRecord`（抽不到的字段记 ``unknown`` / 空）。
    """
    _lines = (text or "").replace("\r\n", "\n").split("\n")
    _head = "\n".join(_lines[:40])

    _rec = DocumentRecord(protocol=protocol, source=source,
                          filename=filename, header_raw=_head[:2000])

    # ① 编号：``Request for Comments: 2326``
    _m = re.search(r"Request for Comments:[ 	]*(\d{3,5})", _head)
    if _m:
        _rec.rfc_number = _m.group(1)

    # ② 标题：★ RFC 的头部**右列是作者/机构**（不是标题！）⇒ ⇒ 标题在
    #   **版权块之后** ⇒ ⇒ 跳过右列行（左侧空白很宽）⇒ ⇒ 取第一条正文标题行
    _skip_prefix = ("Network Working Group", "Request for Comments:",
                    "Category:", "Updates:", "Obsoletes:", "Also see:")
    for _i in range(min(40, len(_lines))):
        _raw = _lines[_i]
        _stripped = _raw.strip()
        if not _stripped:
            continue
        if _stripped.startswith(_skip_prefix):
            continue
        # ★ 右列判据：前导空白很宽 ⇒ 是右列（作者/机构/日期）⇒ 跳过
        _lead = len(_raw) - len(_raw.lstrip())
        if _lead >= 20:
            continue
        _rec.title = _stripped[:200]
        break


    # ③ 类别（★ 文档自述）—— ★ **枚举匹配**（不依赖行尾 ⇒ 右侧有作者时也能匹配）
    _m = re.search(r"Category:[ \t]*(Standards Track|Informational|Experimental"
                   r"|Best Current Practice)", _head)
    if _m:
        _rec.category = _m.group(1).strip()
    else:
        _rec.category = CATEGORY_UNKNOWN


    # ④ 日期：``February 1998``
    _m = re.search(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{4})", _head)
    if _m:
        _rec.date = f"{_m.group(1)} {_m.group(2)}"

    # ⑤ Updates / Obsoletes / Also see
    _m = re.search(r"Updates:[ 	]*([\d,	 ]+)", _head)
    if _m:
        _rec.updates = _rfc_list(_m.group(1))
    _m = re.search(r"Obsoletes:[ 	]*([\d,	 ]+)", _head)
    if _m:
        _rec.obsoletes = _rfc_list(_m.group(1))
    _m = re.search(r"Also see:[ 	]*([\d,	 ]+)", _head)
    if _m:
        _rec.also_see = _rfc_list(_m.group(1))

    # ⑥ 头部提到的其它 RFC（★ 规范性引用的**候选**）
    _refs = []
    for _r in re.findall(r"\bRFC\s*(\d{3,5})\b", _head):
        if _r != _rec.rfc_number:
            _refs.append(_r)
    _rec.normative_refs = sorted(set(_refs))

    # ⑦ 效力标签：★ 只表示「该文档自身声明的信息」
    _rec.status_label = SELF_DECLARED if (_rec.category != CATEGORY_UNKNOWN
                                          or _rec.rfc_number) else UNKNOWN
    return _rec


def write_registry(records: list[DocumentRecord], path: Path) -> Path:
    """写文档登记表（★ 元数据 ⇒ **不进 fact 空间** ⇒ 中枢零影响）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    _payload = {
        "documents": [r.to_dict() for r in (records or [])],
        "note": ("★ 本表只登记**文档自述**信息（Category / Updates / Obsoletes）"
                 "⇒ ★ **不表示「当前生效」**⇒ 跨文档效力核查**未做**"),
    }
    path.write_text(json.dumps(_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


__all__ = [
    "CATEGORY_STANDARD", "CATEGORY_INFORMATIONAL", "CATEGORY_EXPERIMENTAL",
    "CATEGORY_BCP", "CATEGORY_UNKNOWN", "SELF_DECLARED", "UNKNOWN",
    "DocumentRecord", "parse_header", "write_registry",
]
