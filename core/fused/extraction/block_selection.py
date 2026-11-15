# -*- coding: utf-8 -*-
"""★ M1-Q3-P0.9：★ 块级价值评分与预算选择（★ **实验性，默认关闭**）。

★ 启用方式：环境变量 ``PROSE_BLOCK_SELECTION=block_density``
★ ⇒ **默认（未设置）⇒ 既有生产行为完全不变**（★ 每文档取前 N 块）
★ ★ 不修改缓存键算法；★ 实验配置通过独立缓存目录防止误命中

★ 评分（★ 可解释的组成部分 + 固定版本 + 确定性排序）：
  ① BCP14 规范关键词及其上下文　② 方法/Header/状态码/响应关系
  ③ 状态转换与事务生命周期　　　④ ABNF/字段格式/参数与取值约束
  ⑤ 定义、条件、异常及跨节引用　⑥ 章节多样性与历史未覆盖程度
★ 低价值识别：版权页 / 目录 / 重复样板 / 纯参考文献
★ ★ **不得仅因某块没有 BCP14 就永久排除**（★ 保留非 BCP14 配额）
"""
from __future__ import annotations

import re
from typing import Optional

SCORER_VERSION = "block-score-v1"

_BCP = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|"
                  r"REQUIRED|RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")
_RE_SEC = re.compile(r"^\s{0,3}(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9 /\-()]{3,70})\s*$")
_RE_CAP = re.compile(r"^(Figure|Table|Note|Listing)\s+\d+", re.I)
_RE_ABNF = re.compile(r"^[=;]")
_RE_PAGE = re.compile(r"^\[Page \d+\]")
_RE_FRONT = re.compile(r"^(Abstract|Index|Table of Contents|References|"
                       r"Acknowledg|Authors' Addresses|Contributors|"
                       r"Copyright Notice|Status of this Memo)", re.I)
_RE_COPY = re.compile(r"Copyright \(C\)|All Rights Reserved|"
                       r"Distribution of this memo is unlimited|"
                       r"Internet Society|Standards Track", re.I)
_RE_METHOD = re.compile(
    r"\b(SETUP|PLAY|PAUSE|TEARDOWN|OPTIONS|DESCRIBE|ANNOUNCE|RECORD|"
    r"INVITE|ACK|BYE|CANCEL|REGISTER|SUBSCRIBE|PUBLISH|MESSAGE)\b")
_RE_HEADER = re.compile(r"\b[A-Z][A-Za-z-]{2,}\s+(header|field)\b")
_RE_STATE = re.compile(r"\b(state|mode|transaction|dialog)\b", re.I)
_RE_COND = re.compile(r"\b(if|unless|except|only when|in response to)\b", re.I)
_RE_XREF = re.compile(r"\bSection\s+\d")
_RE_DEF = re.compile(r"\b(is defined as|means|refers to|is called|"
                     r"consists of|is an?\s+\w+\s+protocol|"
                     r"can be used to|allows)\b", re.I)

_W = {"bcp14": 3.0, "method": 1.2, "header": 1.0, "state": 1.5,
      "condition": 0.8, "xref": 0.6, "format": 1.0, "definition": 0.9}


def score_block(text: str) -> tuple:
    """★ 块级评分（★ 返回 ``(总分, 组成字典)``；★ 确定性）。"""
    _up = text.upper()
    _n_bcp = len(_BCP.findall(text))
    _n_xref = len(_RE_XREF.findall(text))
    _n_hdr = len(_RE_HEADER.findall(text))
    _n_meth = len(_RE_METHOD.findall(text))
    _n_state = len(_RE_STATE.findall(text))
    _n_cond = len(_RE_COND.findall(text))
    _n_def = len(_RE_DEF.findall(text))
    _n_abnf = sum(1 for ln in text.split("\n") if _RE_ABNF.match(ln.strip()))
    _low = []
    if _RE_COPY.search(text):
        _low.append("copyright_boilerplate")
    if _RE_CAP.match(text.strip()):
        _low.append("caption")
    if _RE_FRONT.match(text.strip()):
        _low.append("front_matter")
    if _RE_PAGE.match(text.strip()):
        _low.append("page_footer")
    _pen = len(_low) * 1.6
    _parts = {
        "bcp14_hits": _n_bcp,
        "bcp14_score": round(min(_n_bcp, 8) * _W["bcp14"], 3),
        "xref_score": round(min(_n_xref, 5) * _W["xref"], 3),
        "header_score": round(min(_n_hdr, 6) * _W["header"], 3),
        "method_score": round(min(_n_meth, 8) * _W["method"], 3),
        "state_score": round(min(_n_state, 6) * _W["state"], 3),
        "condition_score": round(min(_n_cond, 5) * _W["condition"], 3),
        "definition_score": round(min(_n_def, 4) * _W["definition"], 3),
        "format_score": round(min(_n_abnf, 4) * _W["format"], 3),
        "low_value_signals": _low,
        "low_value_penalty": round(_pen, 3),
    }
    _total = round(sum(v for k, v in _parts.items() if k.endswith("_score")) - _pen, 3)
    return _total, _parts


def has_normative_hint(text: str) -> bool:
    """★ 块是否含**规范性线索**（★ 只是发现线索，★ 不是义务成立的证明）。"""
    return bool(_BCP.search(text) or _RE_METHOD.search(text)
                or _RE_HEADER.search(text))


def select_block_density(chunks: list, budget: int,
                         non_bcp_quota: float = 0.20) -> list:
    """★ S4 选择：块级密度 + 文档保底 + 章节多样性 + 非 BCP14 保留配额。

    Args:
        chunks: ``[{"doc","start","text",...}]``
        budget: 块预算（★ 严格上限）
    Returns:
        选中的 chunk 列表（★ 顺序确定）
    """
    _out, _left = [], int(budget)
    if _left <= 0:
        return _out
    _bydoc = {}
    for c in chunks:
        _bydoc.setdefault(c.get("doc"), []).append(c)
    # ① 文档保底（★ 受预算约束 ⇒ ≤ 50%）
    _cap = max(1, int(budget * 0.5))
    for _doc in sorted(_bydoc):
        if _left <= 0 or len(_out) >= _cap:
            break
        _c = _bydoc[_doc]
        _best = max(_c, key=lambda r: (score_block(r.get("text") or "")[0],
                                       -int(r.get("start") or 0)))
        _out.append(_best)
        _left -= 1
    # ② ★ **非 BCP14 区域保留配额**（★ **提前执行** ⇒ 防止被密度选择吃光额度）
    _scored = []
    for c in chunks:
        _s, _p = score_block(c.get("text") or "")
        _scored.append((_s, c))
    _scored.sort(key=lambda x: (-x[0], x[1].get("doc") or "",
                                int(x[1].get("start") or 0)))
    _used = {id(c) for c in _out}
    _quota = max(1, int(round(budget * non_bcp_quota)))
    _added = 0
    for _s, c in _scored:
        if _added >= _quota or _left <= 0:
            break
        if id(c) in _used:
            continue
        _t = c.get("text") or ""
        if _BCP.search(_t):
            continue                      # ★ 已是 BCP14 区
        _out.append(c)
        _used.add(id(c))
        _added += 1
        _left -= 1
    # ③ 块级密度 + 章节多样性（★ 用剩余额度）
    for _s, c in _scored:
        if _left <= 0:
            break
        if id(c) in _used:
            continue
        _out.append(c)
        _used.add(id(c))
        _left -= 1
    return _out[:budget]


__all__ = ["SCORER_VERSION", "score_block", "has_normative_hint",
           "select_block_density"]
