# -*- coding: utf-8 -*-
"""★ V2-E1：★ **章节类型映射**（★ 冻结的**结构规则**，★ 不依赖人工真值）。

★ 五类（★ 用户 §八 建议）：
  ① 协议操作与行为规范   operations_and_behavior
  ② 消息格式与 ABNF     message_format_and_abnf
  ③ 状态、响应与错误处理 states_responses_errors
  ④ 定义、注册与参数说明 definitions_registry_parameters
  ⑤ 附录、元数据及其他   appendix_metadata_other

★ ★ 映射只依赖：★ RFC 标题文本 + 标题编号 + 该节内的行特征（★ 结构信息）
★ ★ **不依赖人工真值、不依赖 V2 预测**
"""
from __future__ import annotations

import re

KIND_OPS = "① 协议操作与行为规范"
KIND_FORMAT = "② 消息格式与 ABNF"
KIND_STATE = "③ 状态、响应与错误处理"
KIND_DEF = "④ 定义、注册与参数说明"
KIND_META = "⑤ 附录、元数据及其他"

ALL_KINDS = [KIND_OPS, KIND_FORMAT, KIND_STATE, KIND_DEF, KIND_META]

# ★ 标题关键字 → 章节类型（★ 顺序即优先级）
_TITLE_RULES = [
    (KIND_META, re.compile(
        r"\b(copyright|notice|disclaimer|trademark|acknowledg|authors?'|"
        r"contributors?|index|iana|full copyright|intellectual property|"
        r"change log|errata|references?)\b", re.I)),
    (KIND_FORMAT, re.compile(
        r"\b(abnf|grammar|syntax|message format|header field|message header|"
        r"body format|production|rule\s+\d+\s*[:=]|notation)\b", re.I)),
    (KIND_STATE, re.compile(
        r"\b(status codes?|responses?|error codes?|status lines?|methods?|"
        r"transactions?|state machines?|requests?|replies|redirects?)\b", re.I)),
    (KIND_DEF, re.compile(
        r"\b(definition|definitions|terminology|registry|registration|"
        r"assignment|option|parameter|number(ing|s)?|identifier|"
        r"abbreviation|glossary)\b", re.I)),
]

# ★ 行特征（★ 优先于标题：★ 标题归类可能不准）
_RE_ABNF_ASSIGN = re.compile(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*")
_RE_ABNF_CONT = re.compile(r"^\s*[|;]")
_RE_TABLE_ROW = re.compile(r"^\s*\|\s*\S")
_RE_COPYRIGHT = re.compile(r"\b(copyright|all rights reserved|trademark)\b", re.I)


def _title_of(line: str):
    """★ 判断一行是否为 RFC 章节标题（★ 返回 (编号, 标题文本) 或 None）。"""
    _t = str(line or "").strip()
    if not _t:
        return None
    _m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(\S.*)$", _t)
    if not _m:
        return None
    _num, _txt = _m.group(1), _m.group(2)
    # ★ 排除表格行/ABNF 行/正文行
    if _RE_TABLE_ROW.match(_t) or _RE_ABNF_ASSIGN.match(_t) \
            or _RE_ABNF_CONT.match(_t):
        return None
    # ★ 标题通常较短且不以句号结尾
    if len(_t) > 120:
        return None
    return (_num, _txt)


def build_section_index(lines):
    """★ 建立「行 → 所属章节类型」索引（★ 标题规则 + 行特征优先）。"""
    _kinds = [None] * (len(lines) + 1)
    _cur = KIND_OPS
    _prev_is_abnf = False          # ★ 上一行是否为 ABNF 产生式赋值（★ 续行判定）
    for _i in range(1, len(lines) + 1):
        _t = lines[_i - 1]
        _h = _title_of(_t)
        if _h:
            _num, _txt = _h
            _cur = KIND_OPS
            for _k, _rx in _TITLE_RULES:
                if _rx.search(_txt):
                    _cur = _k
                    break
            _kinds[_i] = _cur
            continue
        # ★ 行特征优先（★ ★ ABNF **续行**：★ 上一行是产生式赋值）
        _k = None
        if _RE_COPYRIGHT.search(str(_t or "")):
            _k = KIND_META
        elif _RE_ABNF_ASSIGN.match(str(_t or "")):
            _k = KIND_FORMAT
        elif _prev_is_abnf and (_RE_ABNF_CONT.match(str(_t or ""))
                                or re.match(r'^\s*("|<)', str(_t or ""))):
            _k = KIND_FORMAT
        elif _RE_TABLE_ROW.match(str(_t or "")):
            _k = KIND_DEF
        _kinds[_i] = _k or _cur
        _prev_is_abnf = bool(_RE_ABNF_ASSIGN.match(str(_t or "")))
    return _kinds


def kind_of_line(lines, kinds, line_no):
    if 1 <= line_no <= len(kinds):
        return kinds[line_no]
    return KIND_OPS
