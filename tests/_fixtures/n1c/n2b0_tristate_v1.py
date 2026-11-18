# -*- coding: utf-8 -*-
"""★ N2-B0-R：★ **V1 保守反证判据**（★ 与 V0 并行，★ 不覆盖 V0）。

★ ★ 核心修正：★ **规范强度不一致 ≠ 规范命题相互矛盾**
★ ⇒ ★ MUST 与 SHOULD 同段/同句/同窗口出现，★ **不得**判 contradicted

★ V1 的 `contradicted` 必须在**同一规范命题**上同时满足：
  ① 反证句与候选**指向同一命题**（主体 + 动作 + 对象 三者均可定位且对应）
  ② **极性相反**（★ 肯定 vs 否定）
★ ⇒ ★ 其余一切情况（★ 强度范围不一致 / 证据缺失 / 跨句归属不清 / 存在多个义务 /
★   候选字段自相矛盾 / 主体缺失）⇒ ★ **一律 uncertain**

★ ★ 绝不因取消错误反证就升级为 confirmed（★ 本模块**没有** confirmed 出口）
★ ★ 绝不按候选 ID 特例（★ 判据只看原文与字段）
"""
from __future__ import annotations

import re

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
UNCERTAIN = "uncertain"

# ★ BCP14 强度词（含否定形式）
_STR_WORDS = ("MUST NOT", "SHALL NOT", "SHOULD NOT", "MAY NOT",
              "MUST", "SHALL", "SHOULD", "REQUIRED", "RECOMMENDED", "MAY")
_NEG_BCP = ("MUST NOT", "SHALL NOT", "SHOULD NOT", "MAY NOT",
            "NOT RECOMMENDED", "NOT REQUIRED")
# ★ 强度同义词（★ 与 V0 一致，便于对照）
_SYN = {
    "MUST": ("must", "shall", "required", "is required", "has to"),
    "SHOULD": ("should", "recommended", "is recommended", "ought to"),
    "MAY": ("may", "optional", "can", "is able to"),
}
_RE_WORD = re.compile(r"[a-z0-9_]+")
_RE_BCP = re.compile(r"\b(MUST NOT|SHALL NOT|SHOULD NOT|MUST|SHALL|SHOULD|"
                     r"REQUIRED|RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")


def _norm(s):
    return " ".join(str(s or "").lower().replace("_", " ").split())


def _words(s):
    return _RE_WORD.findall(str(s or "").lower())


def _morph(word: str, other: str) -> bool:
    """★ 词形等价（★ 与 V0 一致）。"""
    if word == other:
        return True
    if word.endswith("e") and other == word[:-1]:
        return True
    if other.endswith("e") and word == other[:-1]:
        return True
    for _sfx in ("es", "s", "ed", "ing", "d"):
        if other.endswith(_sfx) and other[:-len(_sfx)] == word:
            return True
        if word.endswith(_sfx) and word[:-len(_sfx)] == other:
            return True
    if word.endswith("y") and other == word[:-1] + "ies":
        return True
    if other.endswith("y") and word == other[:-1] + "ies":
        return True
    return False


def _seq_hit(quote_words, term_words):
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


def _neg_in(text: str) -> bool:
    """★ 文本中是否存在**否定结构**（★ 强度否定或 not 动词/副词）。"""
    _f = str(text or "").lower()
    if any(_n in _f for _n in _NEG_BCP):
        return True
    return bool(re.search(r"\b(not|never|prohibit\w*|forbid\w*|shall not)\b", _f))


# ★ ★ 子句切分（★ **作用域**判定：★ 否定必须作用于候选所在的那个子句）
_RE_CLAUSE = re.compile(
    r"\b(if|when|unless|while|provided that|that|which|who|where|"
    r"in case|because|so that|and|but|or|then|otherwise)\b|[;,]")


def _clauses(sentence: str) -> list[tuple[str, int]]:
    """★ 把句子切成子句（★ 返回 ``(子句文本, 起始偏移)``）。"""
    _out = []
    _start = 0
    for _m in _RE_CLAUSE.finditer(str(sentence or "")):
        _seg = str(sentence[_start:_m.start()]).strip()
        if _seg:
            _out.append((_seg, _start))
        _start = _m.end()
    _tail = str(sentence[_start:]).strip()
    if _tail:
        _out.append((_tail, _start))
    return _out


def _clause_of_term(sentence: str, term: str) -> str:
    """★ 找到包含该术语的**子句**（★ 找不到 ⇒ 返回空串）。"""
    if not str(term or "").strip():
        return ""
    _tw = _words(term)
    for _seg, _off in _clauses(sentence):
        if _seq_hit(_words(_seg), _tw) is not None:
            return _seg
    return ""


# ★ 否定词（★ 用于「紧邻」判定）
_NEG_WORDS = ("not", "never", "nor", "neither", "without", "no")
# ★ ★ 否定到候选动作的最大允许词距（★ 超过 ⇒ 否定作用于别的谓词）
_NEG_MAX_DIST = 2


def _neg_adjacent_to_action(clause: str, action: str) -> bool:
    """★ 否定是否**紧邻**候选动作词（★ 同子句内且词距 ≤ 2）。

    ★ ★ 目的：★ 区分「对候选动作的否定」与「对别的谓词的否定」
    ★ 例：「that is **not** configured to support …」的 not 修饰 configured，
    ★   ★ 与候选动作 discards 无紧邻关系 ⇒ **不构成反证**
    """
    _cw = _words(clause)
    _aw = _words(action)
    if not _aw or not _cw:
        return False
    _neg_idx = [i for i, w in enumerate(_cw) if w in _NEG_WORDS]
    if not _neg_idx:
        return False
    for i in range(len(_cw) - len(_aw) + 1):
        _seg = _cw[i:i + len(_aw)]
        if _seg == _aw or all(_morph(t, w) for t, w in zip(_aw, _seg)):
            for _ni in _neg_idx:
                if abs(_ni - i) <= _NEG_MAX_DIST:
                    return True
    return False


def _strength_level(strength: str) -> str:
    """★ 强度等级（★ **不含**否定信息）。"""
    _s = str(strength or "").strip().upper()
    for _k in ("MUST", "SHALL", "SHOULD", "REQUIRED", "RECOMMENDED", "MAY"):
        if _s.startswith(_k):
            return _k
    return _s


def _sentences_from_lines(lines, anchor, window=3):
    """★ 复用生产句界逻辑：★ 取锚点所在逻辑行并切句（★ 返回带行号的句列表）。"""
    from core.fused.extraction.normative_extract import (
        _logical_line, _sentences_in)
    _lo, _hi, _logical, _offs = _logical_line(lines, anchor)
    _out = []
    for _s, _e in _sentences_in(_logical):
        _txt = _logical[_s:_e].strip()
        if not _txt:
            continue
        # ★ 行号定位
        _ln = _lo
        _acc = 0
        for _i in range(_lo, _hi + 1):
            _t = str(lines[_i - 1]).rstrip()
            if not _t:
                continue
            if _acc + len(_t) >= _s:
                _ln = _i
                break
            _acc += len(_t) + 1
        _out.append({"line": _ln, "text": _txt})
    return _out


def _field_state_v1(sentence: str, term: str, kind: str) -> str:
    """★ 单字段在**某句**内的判定（★ 无 confirmed 出口）。"""
    if not str(term or "").strip():
        return "★ 合法缺省"
    _qw = _words(sentence)
    if kind == "strength":
        _s = _strength_level(term)
        if any(w in sentence.lower() for w in _SYN.get(_s, (_s.lower(),))):
            return SUPPORTED
        return UNCERTAIN
    _i = _seq_hit(_qw, _words(term))
    return SUPPORTED if _i is not None else UNCERTAIN


def semantic_support_tristate_v1(*, quote: str, action: str = "", object_: str = "",
                                strength: str = "", subject: str = "",
                                constraint: str = "", lines=None, anchor=None,
                                window: int = 3) -> tuple[str, str, dict]:
    """★ V1 三态判定（★ 保守反证）。

    Returns ``(verdict, reason, detail)``；★ verdict ∈ supported/contradicted/uncertain
    """
    _detail = {"★ 逐字段": {}, "★ 反证句": None, "★ 反证行": None,
               "★ 命题对应": None, "★ 证据跨度": None}
    if not str(quote or "").strip():
        return UNCERTAIN, "★ 证据为空", _detail
    # ★ ① 候选字段自相矛盾检查（★ strength 与 constraint 文本的否定不一致）
    _c_txt = str(constraint or "")
    if _c_txt and _neg_in(_c_txt) and not _neg_in(strength or ""):
        _detail["★ 候选字段自相矛盾"] = (
            f"★ constraint 文本含否定结构（{_c_txt[:60]!r}）而 strength 字段"
            f"（{strength!r}）不含 ⇒ ★ **字段自相矛盾 ⇒ uncertain**")
        return (UNCERTAIN,
                "★ 候选字段自相矛盾（★ constraint 含否定而 strength 不含）"
                "⇒ ★ 优先 uncertain，★ **不判 contradicted、★ 不升级 confirmed**",
                _detail)
    # ★ ② 命题定位：★ 逐句找「同命题句」
    _sents = []
    if lines is not None and anchor:
        _sents = _sentences_from_lines(lines, anchor, window)
    if not _sents:
        _sents = [{"line": None, "text": str(quote)}]
    _subj = str(subject or "").strip()
    for _s in _sents:
        _t = _s["text"]
        _fa = _field_state_v1(_t, action, "action")
        _fo = _field_state_v1(_t, object_, "object")
        _fs = _field_state_v1(_t, strength, "strength")
        _fu = _field_state_v1(_t, _subj, "subject") if _subj else "★ 主体缺失"
        _detail["★ 逐字段"][f"行{_s['line']}"] = {
            "action": _fa, "object": _fo, "strength": _fs, "subject": _fu}
        # ★ ③ 同命题判定：★ 主体 + 动作 + 对象 三者都对应
        _same = (_fa == SUPPORTED and _fo == SUPPORTED
                 and _fu in (SUPPORTED, "★ 主体缺失"))
        if not _same:
            continue
        # ★ ④ 极性相反 ⇒ contradicted（★ **强度不一致不构成矛盾**）
        # ★ ★ **作用域判定**：★ 否定必须作用于**候选动作所在的子句**，
        #   ★ 而不是句中任意位置的 not（★ 如「that is **not** configured to …」是条件限定）
        _cl = _clause_of_term(_t, action) or _clause_of_term(_t, object_) or _t
        # ★ ★ **否定必须紧邻候选动作**（★ 否则否定作用于别的谓词 ⇒ 不构成反证）
        _neg_adj = _neg_adjacent_to_action(_cl, action) or \
            _neg_adjacent_to_action(_cl, object_)
        # ★ 强度否定（must not / shall not …）★ 作用于动作时同样有效
        _neg_str = [w for w in _NEG_BCP if w in _cl.lower()]
        _neg_same_scope = _neg_adj or bool(_neg_str)
        _detail["★ 反证作用域子句"] = _cl[:160]
        _detail["★ 否定是否紧邻候选动作"] = _neg_adj
        _detail["★ 子句内强度否定词"] = _neg_str
        # ★ ★ **先查「候选强度极性 vs 原文强度极性」**：★ 不一致 ⇒ 字段不一致 ⇒ uncertain
        _sbcp = _RE_BCP.findall(_cl or _t)
        if _sbcp and _neg_same_scope:
            _sneg = any(_n in _b for _b in _sbcp for _n in _NEG_BCP)
            _cneg = _neg_in(strength or "")
            if _sneg != _cneg:
                _detail["★ 强度极性不一致"] = {
                    "★ 原文子句强度词": _sbcp, "★ 候选 strength": strength,
                    "★ 原文否定": _sneg, "★ 候选否定": _cneg}
                return (UNCERTAIN,
                        "★ **候选 strength 的极性与原文同子句的强度极性不一致**"
                        "（★ 字段不一致，★ **不是反证**）⇒ ★ 优先 uncertain",
                        _detail)
        if _neg_same_scope and not _neg_in(strength or ""):
            _detail["★ 反证句"] = _t
            _detail["★ 反证行"] = _s["line"]
            _detail["★ 命题对应"] = {
                "subject": _fu, "action": _fa, "object": _fo, "strength": _fs}
            _detail["★ 证据跨度"] = {"line": _s["line"],
                                 "char_len": len(_t),
                                 "★ 作用域子句": _cl[:160]}
            return (CONTRADICTED,
                    f"★ 同一命题（★ 主体/动作/对象对应）**且同一作用域子句**内出现"
                    f"**极性相反**的否定结构 ⇒ 明确冲突（★ 反证行 {_s['line']}）",
                    _detail)
        # ★ ⑤ 同命题且强度命中 ⇒ supported
        # ★ ★ **合法缺省不阻塞**（★ strength 无值 ⇒ ★ 不应阻止 supported 判定）
        if _fs == SUPPORTED or _fs == "★ 合法缺省":
            # ★ ★ **候选强度极性 vs 原文强度极性**（★ 在同一子句上）
            _sbcp = _RE_BCP.findall(_cl or _t)
            if _sbcp:
                _sneg = any(_n in _b for _b in _sbcp for _n in _NEG_BCP)
                _cneg = _neg_in(strength or "")
                if _sneg != _cneg:
                    _detail["★ 强度极性不一致"] = {
                        "★ 原文子句强度词": _sbcp, "★ 候选 strength": strength,
                        "★ 原文否定": _sneg, "★ 候选否定": _cneg}
                    return (UNCERTAIN,
                            "★ **候选 strength 的极性与原文同子句的强度极性不一致**"
                            "（★ 字段不一致，★ **不是反证**）⇒ ★ 优先 uncertain",
                            _detail)
            _detail["★ 命题对应"] = {
                "subject": _fu, "action": _fa, "object": _fo, "strength": _fs}
            _detail["★ 证据跨度"] = {"line": _s["line"], "char_len": len(_t)}
            return (SUPPORTED,
                    f"★ 同命题（★ 行 {_s['line']}）且强度命中 ⇒ supported"
                    "（★ **强度不一致不构成矛盾**）", _detail)
    # ★ ⑥ 未定位到同命题句 ⇒ uncertain
    return (UNCERTAIN,
            "★ 未能在**同一命题**（主体+动作+对象同时对应）上定位强度或明确反证"
            "⇒ ★ 证据缺失/跨句归属不清/存在多个义务 ⇒ ★ 优先 uncertain", _detail)


__all__ = ["SUPPORTED", "CONTRADICTED", "UNCERTAIN",
           "semantic_support_tristate_v1", "_sentences_from_lines",
           "_neg_in", "_strength_level"]
