# -*- coding: utf-8 -*-
"""★ M1-Q3-P0.7-A：指代主体的**归属核验**（★ 确认前的最小检查）。

★ 目标：防止「主要证据里的规范句成立，**但义务承担者未确定归属**」被直接 confirmed。
★ 例：主要证据 ``This field MUST be present in all requests and responses.``
      ★ 句子本身有义务，但 ``This field`` 指向哪个字段**未证明**。

★ 状态（★ 四类）：
  · ``explicit_subject``      主体在主要证据中**明确出现**
  · ``coreference_resolved``  通过上下文**唯一**确认先行词
  · ``coreference_ambiguous`` 存在**多个**可能先行词
  · ``coreference_unresolved`` 缺乏足够证据

★ 约束：
  · ★ **不修改 L1/L2 判定标准**（★ 本模块只做「确认前」的额外检查）
  · ★ **不得仅按「距离最近」推断** ⇒ ★ 必须「类型一致 + 唯一 + 原文支持」
  · ★ 保留原始候选主体与证据，**不重写 canonical 身份**
  · ★ 歧义/未解析 ⇒ **不得自动确认**（保持 pending / 人工复核）
"""
from __future__ import annotations

import re
from typing import Optional

# ★ 指代表达（★ 主体位置的指代）
# ★ 组①：指示词 + 名词（This field / Such responses …）
_RE_COREF_N = re.compile(
    r"\b(this|these|those|such)\s+"
    r"(field|fields|header|headers|message|messages|request|requests|"
    r"response|responses|session|sessions|method|methods|entity|entities|"
    r"value|values|parameter|parameters|option|options|extension|extensions|"
    r"body|bodies|packet|packets|element|elements|transaction|transactions|"
    r"state|states|dialog|dialogs)\b",
    re.I)
# ★ 组②：人称代词（It / They …）★ **可单独成指代**
_RE_COREF_P = re.compile(r"\b(it|they|he|she)\b(?![A-Za-z])", re.I)

# ★ 先行词（★ 名词性修饰结构：「the <X> field」）
_RE_ANTECEDENT = re.compile(
    r"\b(?:the|a|an|each|every|any)\s+"
    r"([A-Za-z][A-Za-z0-9-]{0,30}?)\s+"
    r"(field|fields|header|headers|message|messages|request|requests|"
    r"response|responses|session|sessions|method|methods|entity|entities|"
    r"value|values|parameter|parameters|option|options|extension|extensions|"
    r"body|bodies|packet|packets|element|elements|transaction|transactions|"
    r"state|states|dialog|dialogs)\b",
    re.I)

# ★ 实体类型词（★ 用于「先行词类型与指代类型一致」的核验）
_NOUN_KINDS = {
    "field", "fields", "header", "headers", "message", "messages",
    "request", "requests", "response", "responses", "session", "sessions",
    "method", "methods", "entity", "entities", "value", "values",
    "parameter", "parameters", "option", "options", "extension", "extensions",
    "body", "bodies", "packet", "packets", "element", "elements",
    "transaction", "transactions", "state", "states", "dialog", "dialogs",
}


# ★ 组③：**句首/主语位置**的指代（★ 宾语代词「it supports」**不算**）
_RE_COREF_SUBJ = re.compile(
    r"(?:^|(?<=[.;:!?])\s+|(?<=\n)\s*)"
    r"(?P<c1>(this|these|those|such)\s+"
    r"(field|fields|header|headers|message|messages|request|requests|"
    r"response|responses|session|sessions|method|methods|entity|entities|"
    r"value|values|parameter|parameters|option|options|extension|extensions|"
    r"body|bodies|packet|packets|element|elements|transaction|transactions|"
    r"state|states|dialog|dialogs)"
    r"|(?P<c2>it|they|he|she)\b(?![A-Za-z]))",
    re.I)


def detect_coreference(text: str) -> Optional[str]:
    """★ 主要证据里是否出现**主体位置的指代表达**（★ 返回命中的短语，★ 无 ⇒ None）。

    ★ **只检测句首/主语位置**：★ 宾语代词（如 "list the methods it supports"）
      **不是**义务主体的指代 ⇒ ⇒ 不触发归属核验
    ★ 两组：① 指示词 + 名词（This field / Such responses）② 人称代词（It / They）
    """
    if not text:
        return None
    m = _RE_COREF_SUBJ.search(str(text))
    return m.group(0).strip() if m else None


def resolve_subject_attribution(*, lines: list, quote_span, quote: str,
                                aux_evidence: Optional[list] = None,
                                entity: str = "", subject: str = "") -> dict:
    """★ 主体归属核验。

    Args:
        lines: 文档**全文**的行列表（★ 同一版本 RFC 真实原文）
        quote_span: 主要 quote 的行范围（★ 1 起始闭区间）
        quote: 主要 quote 文本
        aux_evidence: 辅助证据（★ 前一句等，★ 仅用于**归属**核验，★ 不并入 quote）
        entity: 候选的**提及实体**
        subject: 候选的**义务主体**

    Returns:
        ``{"status", "antecedents", "evidence_lines", "reason", "coref_phrase"}``
    """
    _out = {"status": "explicit_subject", "antecedents": [],
            "evidence_lines": [], "reason": "", "coref_phrase": None}
    _ent = str(entity or "").strip()
    _subj = str(subject or "").strip()
    _ph = detect_coreference(quote)
    _out["coref_phrase"] = _ph
    if not _ph:
        _out["reason"] = "主要证据中无指代表达 ⇒ 主体明确"
        return _out

    # ★ 收集可作归属依据的上下文（★ **同一段落内** ⇒ ★ 不跨段）
    _ctx = []
    if quote_span:
        _s, _e = int(quote_span[0]), int(quote_span[1])
        _lo = max(1, _s - 12)
        for _i in range(_lo, _e + 1):
            if 1 <= _i <= len(lines):
                _ctx.append((_i, str(lines[_i - 1])))
    for _a in (aux_evidence or []):
        _sp = _a.get("span")
        if _sp:
            for _i in range(max(1, int(_sp[0]) - 6), int(_sp[1]) + 1):
                if 1 <= _i <= len(lines):
                    _ctx.append((_i, str(lines[_i - 1])))
    # ★ 去重 + 按行序
    _seen = set()
    _ctx2 = []
    for _i, _t in sorted(_ctx):
        if _i not in _seen:
            _seen.add(_i)
            _ctx2.append((_i, _t))

    # ★ 找先行词（★ 类型与指代类型一致 ⇒ ★ **不按距离最近**）
    _kind = None
    _m = re.match(r"\b\w+\s+(\w+)\b", _ph)
    if _m:
        _kind = _m.group(1).lower()
    _cands = []
    for _i, _t in _ctx2:
        for _mm in _RE_ANTECEDENT.finditer(_t):
            _mod = _mm.group(1)
            _k = _mm.group(2).lower()
            if _kind and _k != _kind:
                continue                      # ★ 类型不一致 ⇒ 排除
            _cands.append({"line": _i, "modifier": _mod, "kind": _k,
                           "text": _mm.group(0).strip()})
    _out["antecedents"] = _cands
    _out["evidence_lines"] = sorted({c["line"] for c in _cands})

    if not _cands:
        _out["status"] = "coreference_unresolved"
        _out["reason"] = (f"主要证据含指代「{_ph}」⇒ 但同一段落内无"
                           f"类型一致的明确先行词 ⇒ 归属未解析")
        return _out

    # ★ 唯一性（★ 同类型多个不同修饰名 ⇒ 歧义）
    _mods = {c["modifier"] for c in _cands}
    # ★ 候选实体本身若与先行词一致 ⇒ 强证据（★ 可消歧）
    _hit = [c for c in _cands
            if _ent and (c["modifier"].lower() == _ent.lower()
                         or _ent.lower() in c["modifier"].lower()
                         or c["modifier"].lower() in _ent.lower())]
    if len(_hit) == 1 and len(_cands) == 1:
        _out["status"] = "coreference_resolved"
        _out["reason"] = (f"指代「{_ph}」⇒ 先行词「{_hit[0]['modifier']}」"
                          f"（行 {_hit[0]['line']}）与候选实体「{_ent}」一致且唯一")
        return _out
    if len(_hit) == 1 and len(_cands) > 1:
        # ★ ★ **不得仅按「距离最近」推断** ⇒ ★ 同类型另有先行词 ⇒ 归属不唯一
        _out["status"] = "coreference_ambiguous"
        _out["reason"] = (f"指代「{_ph}」⇒ 虽有一个先行词与实体「{_ent}」一致，"
                          f"但同类型先行词共 {len(_cands)} 个 ⇒ 归属不唯一")
        return _out
    if len(_hit) > 1:
        _out["status"] = "coreference_ambiguous"
        _out["reason"] = (f"指代「{_ph}」⇒ 有 {len(_hit)} 个同类型先行词，"
                          f"无法唯一归属")
        return _out
    if len(_mods) > 1:
        _out["status"] = "coreference_ambiguous"
        _out["reason"] = (f"指代「{_ph}」⇒ 同一段落内有 {len(_mods)} 个不同先行词"
                          f"（{sorted(_mods)}）⇒ 无法唯一归属")
        return _out
    # ★ 只有一个修饰名，但与候选实体不一致 ⇒ 归属存疑（★ 不得自动确认）
    _only = _cands[0]
    _out["status"] = "coreference_unresolved"
    _out["reason"] = (f"指代「{_ph}」⇒ 唯一先行词「{_only['modifier']}」"
                      f"（行 {_only['line']}）与候选主体/实体「{_subj or _ent}」不一致"
                      f" ⇒ 归属未获支持")
    return _out


__all__ = ["detect_coreference", "resolve_subject_attribution",
           "RE_COREF", "RE_ANTECEDENT"]
