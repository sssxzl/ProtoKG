# -*- coding: utf-8 -*-
"""★ N2-B0：★ 确定性语义检查的**三态影子实现**（★ 不进生产路径）。

★ 核心原则：
    **没有找到支持证据，不等于已经找到反对证据。**

★ 三态：
  · `supported`    具备所需的确定性原文支持
  · `contradicted` 存在**明确、可复核的反证**
  · `uncertain`    证据不足、词面不匹配或上下文未解决

★ ★ **只作用于「纯语义支持检查」层**（★ `semantic_support`）
★ ⇒ ★ **不涉及** L1 身份契约 / 解析失败 / 无效来源 ⇒ ⇒ **这些情况一律不转换**
★ ★ **contradicted 判定极保守**：★ 只在存在**明确的相反强度/否定结构**时才判
★ ★ **uncertain ⇒ pending**（★ 绝不自动 confirmed，★ 绝不自动 rejected）
"""
from __future__ import annotations

import re

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
UNCERTAIN = "uncertain"

# ★ 强度同义词集（★ 与生产 `semantic_support` 保持一致的词典，★ 但判定更细）
_SYN = {
    "MUST": ("must", "shall", "required", "is required", "has to"),
    "SHOULD": ("should", "recommended", "is recommended", "ought to"),
    "MAY": ("may", "optional", "can", "is able to"),
}
# ★ 明确反证：★ 候选强度词与原文的**相反强度/否定结构**同时出现
_CONTRA = {
    "MUST": ("must not", "shall not", "should not", "may not",
             "is not required", "is not mandatory", "not required"),
    "SHOULD": ("must not", "shall not", "must", "is required", "shall",
               "is mandatory"),
    "MAY": ("must", "shall", "must not", "shall not", "is required"),
}
_RE_WORD = re.compile(r"[a-z0-9_]+")


def _norm(s):
    return " ".join(str(s or "").lower().replace("_", " ").split())


def _words(s):
    return _RE_WORD.findall(str(s or "").lower())


def _morph(word: str, other: str) -> bool:
    """★ 词形等价（★ 允许尾部 'e' 与常见屈折后缀）。

    ★ 例：include↔includes、ignore↔ignores、discard↔discards、carry↔carries
    ★ ★ **不做无差别子串匹配**（★ 否则「silently ignore」会被
    ★   「silently ignores」的子串误判为命中）
    """
    if word == other:
        return True
    # ★ 尾部 'e'（★ 与生产 `semantic_support` 一致）
    if word.endswith("e") and other == word[:-1]:
        return True
    if other.endswith("e") and word == other[:-1]:
        return True
    # ★ 屈折后缀（★ 去后缀后相等）
    for _sfx in ("es", "s", "ed", "ing", "d"):
        if other.endswith(_sfx) and other[:-len(_sfx)] == word:
            return True
        if word.endswith(_sfx) and word[:-len(_sfx)] == other:
            return True
    # ★ 双写辅音（★ carry→carries）
    if word.endswith("y") and other == word[:-1] + "ies":
        return True
    if other.endswith("y") and word == other[:-1] + "ies":
        return True
    return False


def _word_hit(quote_words, term_words):
    """★ 词序列命中（★ 允许**词形等价**变体）。"""
    if not term_words:
        return None
    _n = len(term_words)
    for i in range(len(quote_words) - _n + 1):
        _seg = quote_words[i:i + _n]
        if _seg == term_words:
            return i
        if all(_morph(_t, _w) for _t, _w in zip(term_words, _seg)):
            return i
    return None


def _substring_hit(quote_flat, term):
    """★ ★ **已停用**：★ 无差别子串匹配过宽（★ 「silently ignore」会被
    ★ 「silently ignores」的子串误判为命中）⇒ ★ 改由  词形等价承担。"""
    return False


def field_state(quote: str, term: str, kind: str) -> tuple[str, str]:
    """★ 单个字段的三态判定。

    Returns ``(state, detail)``
    """
    _q = str(quote or "")
    if not _q.strip():
        return UNCERTAIN, "★ 证据为空"
    if not str(term or "").strip():
        return UNCERTAIN, "★ 该字段无值（★ 合法缺省）"
    _qw = _words(_q)
    _qf = _norm(_q)
    if kind == "strength":
        _s = str(term).strip().upper()
        # ★ ★ **contradicted 优先**（★ 相反强度必须先于 supported 判定）
        _contra = _CONTRA.get(_s, ())
        _hit = [w for w in _contra if w in _qf]
        if _hit:
            return CONTRADICTED, (f"★ 原文出现**相反强度/否定结构**「{_hit[0]}」"
                                  f"⇒ 明确反证")
        if any(w in _qf for w in _SYN.get(_s, (_s.lower(),))):
            return SUPPORTED, f"★ 强度「{term}」的同义词集命中"
        return UNCERTAIN, f"★ 强度「{term}」的同义词集{_SYN.get(_s, ())}均未出现"
    # ★ action / object
    _tw = _words(term)
    _i = _word_hit(_qw, _tw)
    if _i is not None:
        return SUPPORTED, f"★ 词序列命中（★ 位置 {_i}）"
    if _substring_hit(_qf, term):
        return SUPPORTED, "★ 子串命中（★ 形态/词序不同）"
    return UNCERTAIN, f"★ 原文未出现（★ 词序列与子串均未命中）"


def semantic_support_tristate(text: str, action: str = "", object_: str = "",
                              *, strength: str = "") -> tuple[str, str, dict]:
    """★ 三态语义支持检查（★ 影子）。

    Returns:
        ``(verdict, reason, field_states)``
        verdict ∈ supported / contradicted / uncertain
        ★ **uncertain ⇒ 应转 pending**（★ 不自动 rejected，★ 绝不 confirmed）
    """
    _states = {}
    _reasons = []
    for _name, _val, _kind in (("action", action, "action"),
                              ("object", object_, "object"),
                              ("strength", strength, "strength")):
        _st, _dt = field_state(text, _val, _kind)
        _states[_name] = {"state": _st, "detail": _dt, "value": _val}
        if _st == CONTRADICTED:
            _reasons.append(f"{_name}：{_dt}")
    _any_contra = any(v["state"] == CONTRADICTED for v in _states.values())
    # ★ ★ **合法缺省不构成阻塞**（★ 该字段本就无值 ⇒ ★ 不应拉低整体判定）
    _blocking = [k for k, v in _states.items()
                 if v["state"] == UNCERTAIN and str(v["value"] or "").strip()]
    if _any_contra:
        return CONTRADICTED, "；".join(_reasons), _states
    if not _blocking:
        return SUPPORTED, "★ 有值的字段均在证据中出现（★ 合法缺省不构成阻塞）", _states
    _uncertain = [f"{k}：{_states[k]['detail']}" for k in _blocking]
    return UNCERTAIN, "；".join(_uncertain), _states


__all__ = ["SUPPORTED", "CONTRADICTED", "UNCERTAIN",
           "semantic_support_tristate", "field_state"]
