# -*- coding: utf-8 -*-
"""★ N2-B0-V2：★ **知识类型与来源作用域闸门**（★ 离线影子，★ 不接入生产）。

★ ★ 核心原则（★ 用户指定）：
  · V2 **不取代** V1；★ 只判断「候选属于哪一类知识、该交给哪条路径」
  · ★ **不得**把「不是规范规则」等同于「无价值知识」
  · ★ ABNF / 状态码 / 字段定义 / 状态转换 / IANA 注册 ⇒ **优先复用既有结构化通道**
  · ★ **不得**新建平行 FactID 或修改既有 21 aspects

★ ★ 禁止的两种朴素判据（★ 本模块**不采用**）：
  · 「包含 must ⇒ 规范规则」★ ★ **不成立**（★ 版权声明也含 must）
  · 「包含 copyright ⇒ 整块全部删除」★ ★ **不成立**（★ 只按**证据跨度**判定，★ 保留原始证据）

★ 六个知识类别（★ 最小分类体系）：
  · non_protocol_metadata
  · protocol_syntax
  · protocol_registry_or_enumeration
  · protocol_descriptive_semantics
  · normative_rule_candidate
  · mixed_or_uncertain
"""
from __future__ import annotations

import re

# ══ 六个知识类别 ══
NON_PROTOCOL_METADATA = "non_protocol_metadata"
PROTOCOL_SYNTAX = "protocol_syntax"
PROTOCOL_REGISTRY = "protocol_registry_or_enumeration"
PROTOCOL_DESCRIPTIVE = "protocol_descriptive_semantics"
NORMATIVE_RULE_CANDIDATE = "normative_rule_candidate"
MIXED_OR_UNCERTAIN = "mixed_or_uncertain"

# ══ 路由（★ 复用既有 aspect 通道，★ 不新建）══
ROUTE_RULE = "rule_channel"                  # ★ 进 V1 三态判断
ROUTE_STRUCTURED = "structured_channel"      # ★ 既有 aspect 通道（syntax/enum/definition/transition）
ROUTE_METADATA = "metadata_channel"         # ★ 非协议元数据（★ 保留记录，★ 不进规则通道）
ROUTE_DESCRIPTIVE = "descriptive_channel"   # ★ 描述性语义（★ 保留记录）
ROUTE_REVIEW = "pending_review"             # ★ 不确定 ⇒ 人工

# ══ 既有 aspect 通道（★ 复用，★ 不新增）══
STRUCTURED_ASPECT = {
    PROTOCOL_SYNTAX: ("syntax", "A_structure/headers"),
    PROTOCOL_REGISTRY: ("value_enum_spec", "D_construction/case_rules"),
    PROTOCOL_DESCRIPTIVE: ("definition", "A_structure/by_entity_type"),
}

# ══ 判据表 ══
# ★ ① 文档级（非协议参与方）对象词表（★ 版权/文档许可作用域）
_DOC_LEVEL_OBJ = re.compile(
    r"\b(copyrights?|notice|trademarks?|document|translations?|copies|"
    r"derivative works?|standards process|internet society|"
    r"all rights reserved|disclaimers?)\b", re.I)
# ★ ② 版权许可的固定表述
_COPYRIGHT_LICENSE = re.compile(
    r"(all rights reserved|copyright notice|this document and translations|"
    r"may be copied|derivative works|permission to (copy|use)|"
    r"infringement|shall be identified|without restriction)", re.I)
# ★ ③ 协议参与方主体词表（★ 命中 ⇒ 义务主体更像协议实体）
_PROTOCOL_ACTOR = re.compile(
    r"\b(server|client|uas|uas|uas|proxy|proxy|relay|peer|gateway|"
    r"sender|receiver|requester|responder|endpoint|host|user agent|"
    r"user agent server|registrar|presentity|back-to-back ua|"
    r"dhcp server|dhcp client|bootp client|smtp client|smtp server)\b", re.I)
# ★ ④ BCP14 强度词
_BCP14 = re.compile(
    r"\b(MUST NOT|SHALL NOT|SHOULD NOT|MAY NOT|MUST|SHALL|SHOULD|"
    r"REQUIRED|RECOMMENDED|MAY)\b")
_BCP14_NEG = re.compile(
    r"\b(MUST NOT|SHALL NOT|SHOULD NOT|MAY NOT)\b")
# ★ ⑤ 义务动词（★ 行为动词）
_OBLIGATION_VERB = re.compile(
    r"\b(must|shall|should|may|required to|has to|ought to)\b", re.I)
# ★ ⑥ ABNF 产生式
_ABNF_ASSIGN = re.compile(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*")
_ABNF_CONT = re.compile(r"^\s*[|;]")
# ★ ⑦ 登记/枚举表上下文
_REGISTRY_HINT = re.compile(
    r"(status code|error code|option name|header name|registry|"
    r"registered|iana|assignment|code\s*\|)", re.I)
# ★ ⑧ RFC 元数据章节标题
_META_SECTION = re.compile(
    r"^\s*(\d+\.?\s*)?(copyright|notice|disclaimer|trademark|"
    r"acknowledg(e)?ments?|authors'? addresses?|"
    r"contributors|full copyright statement|intellectual property)\b", re.I)
# ★ ⑨ ★ **陈述式规范句**判据（★ §五 要求：★ 无 BCP14 关键词也可能规定协议行为）
#   ★ 条件从句连词
_COND_CONJ = re.compile(r"\b(if|when|unless|provided that|in case|whenever)\b",
                        re.I)
#   ★ 协议行为动词（★ 协议参与方的可观测行为）
_PROTOCOL_ACTION = re.compile(
    r"\b(discard\w*|ignore\w*|return\w*|send\w*|receiv\w*|transmit\w*|"
    r"respond\w*|forward\w*|process\w*|handl\w*|accept\w*|reject\w*|"
    r"close\w*|open\w*|establish\w*|maintain\w*|support\w*|provid\w*|"
    r"implement\w*|allow\w*|requir\w*|generat\w*|set\b|add\w*|remov\w*|"
    r"keep\b|us\w*|include\w*|appear\w*|carried?\b|must\b|may\b)\b", re.I)


def is_declarative_normative(sentence: str) -> tuple[bool, str]:
    """★ **陈述式规范句**判定（★ 无 BCP14 强度词但仍规定协议行为）。

    ★ 条件：★ ① 含条件从句连词　② 含协议行为动词　③ 含协议参与方主体
    ★ ⇒ ★ **强度记为 unknown**（★ 不得擅自提升为 MUST）
    Returns ``(is_declarative, reason)``
    """
    _s = str(sentence or "")
    if _BCP14.search(_s):
        return False, "★ 含 BCP14 强度词（★ 走常规规范规则判据）"
    _c = bool(_COND_CONJ.search(_s))
    _a = bool(_PROTOCOL_ACTION.search(_s))
    _p = bool(_PROTOCOL_ACTOR.search(_s))
    if _c and _a and _p:
        return True, ("★ 陈述式规范句（★ 条件从句 + 协议行为动词 + 协议参与方主体，"
                      "★ **但无 BCP14 强度词**）⇒ ★ 适用规范规则通道，"
                      "★ **strength = unknown**（★ 不擅自提升为 MUST）")
    _miss = [n for n, ok in (("条件从句", _c), ("行为动词", _a),
                              ("协议主体", _p)) if not ok]
    return False, f"★ 非陈述式规范句（★ 缺：{'、'.join(_miss) or '—'}）"


def _sentences(lines, anchor, window=3):
    """★ 复用生产句界逻辑（★ 不造新体系）。"""
    from core.fused.extraction.normative_extract import (
        _logical_line, _sentences_in)
    _lo, _hi, _logical, _offs = _logical_line(lines, anchor)
    _out = []
    for _s, _e in _sentences_in(_logical):
        _txt = _logical[_s:_e].strip()
        if _txt:
            _out.append(_txt)
    return _out


def _is_abnf(line: str, prev_line: str = "") -> bool:
    """★ ABNF 产生式判定（★ **枚举项不算产生式**）。

    ★ ① 本行是产生式赋值（``X = ...`` / ``X ::= ...`` / ``X := ...``）
    ★ ② 本行是**续行**（★ 上一行是产生式赋值，★ 且本行以 | ; " < 等续行形态开头）
    ★ ★ **单纯的状态码枚举项（``"100" ; Continue``）不算产生式**
    """
    _t = str(line or "")
    if _ABNF_ASSIGN.match(_t):
        return True
    if _ABNF_CONT.match(_t) and _ABNF_ASSIGN.match(str(prev_line or "")):
        return True
    return bool(re.match(r'^\s*("|<)', _t)
                and _ABNF_ASSIGN.match(str(prev_line or "")))


def classify_sentence(sentence: str, context_lines=(), doc_meta_zone=False):
    """★ 对**单个证据句**做来源与知识类别判定。

    Returns ``(source_kind, knowledge_kind, rule_eligibility, reason, signals)``
    """
    _s = str(sentence or "")
    if not _s.strip():
        return (MIXED_OR_UNCERTAIN, MIXED_OR_UNCERTAIN, "uncertain",
                "★ 证据为空 ⇒ ★ 无法判定（★ 不猜测）", {})
    _sig = {
        "★ 含 BCP14 强度词": bool(_BCP14.search(_s)),
        "★ 含否定强度": bool(_BCP14_NEG.search(_s)),
        "★ 命中文档级对象": bool(_DOC_LEVEL_OBJ.search(_s)),
        "★ 命中协议参与方": bool(_PROTOCOL_ACTOR.search(_s)),
        "★ 命中版权许可表述": bool(_COPYRIGHT_LICENSE.search(_s)),
        "★ 落在元数据章节": bool(doc_meta_zone),
        "★ 行内含 ABNF 形态": any(
            _is_abnf(l, context_lines[i - 1] if i > 0 else "")
            for i, l in enumerate(context_lines)),
        "★ 上下文含登记/枚举提示": any(_REGISTRY_HINT.search(l)
                                for l in context_lines),
        "★ 义务动词": bool(_OBLIGATION_VERB.search(_s)),
    }
    # ══ ① 非协议元数据（★ 结构位置 + 语义对象双判据）══
    if _sig["★ 落在元数据章节"] or (
            _sig["★ 命中版权许可表述"]
            and _sig["★ 命中文档级对象"]
            and not _sig["★ 命中协议参与方"]):
        return (NON_PROTOCOL_METADATA, NON_PROTOCOL_METADATA, "ineligible",
                "★ 结构位置属元数据章节，或语义对象为文档/版权级"
                "（★ 非协议参与方行为）⇒ ★ 不适用规范规则通道", _sig)
    # ══ ② 协议语法（ABNF）══
    if _sig["★ 行内含 ABNF 形态"]:
        return (PROTOCOL_SYNTAX, PROTOCOL_SYNTAX, "ineligible",
                "★ 证据行呈 ABNF 产生式形态 ⇒ ★ 属协议语法知识"
                "（★ 走既有 syntax / layout 通道）", _sig)
    # ══ ③ 登记 / 枚举 ══
    if _sig["★ 上下文含登记/枚举提示"] and not _sig["★ 含 BCP14 强度词"]:
        return (PROTOCOL_REGISTRY, PROTOCOL_REGISTRY, "ineligible",
                "★ 处于登记/枚举表上下文且无强度词 ⇒ ★ 属登记类结构化知识"
                "（★ 走既有 value_enum_spec 通道）", _sig)
    # ══ ④ 规范规则候选（★ 强度 + 义务主体 + 行为 三者齐备）══
    if _sig["★ 含 BCP14 强度词"]:
        if _sig["★ 命中协议参与方"] and _sig["★ 义务动词"]:
            return (NORMATIVE_RULE_CANDIDATE, NORMATIVE_RULE_CANDIDATE,
                    "eligible",
                    "★ 含强度词且义务主体为协议参与方、★ 有行为动词"
                    "⇒ ★ 适用规范规则通道", _sig)
        if _sig["★ 命中文档级对象"] and not _sig["★ 命中协议参与方"]:
            return (NON_PROTOCOL_METADATA, MIXED_OR_UNCERTAIN, "uncertain",
                    "★ 含强度词但语义对象为文档/版权级而非协议参与方"
                    "⇒ ★ **不确定**，★ 不得据此判为规范义务", _sig)
        return (MIXED_OR_UNCERTAIN, MIXED_OR_UNCERTAIN, "uncertain",
                "★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定"
                "⇒ ★ 交人工复核", _sig)
    # ══ ④' 含义务动词但**无大写 BCP14 词** ⇒ ★ 不确定（★ 不得直接判描述性）
    if not _BCP14.search(_s) and _OBLIGATION_VERB.search(_s) \
            and not _PROTOCOL_ACTOR.search(_s):
        return (MIXED_OR_UNCERTAIN, MIXED_OR_UNCERTAIN, "uncertain",
                "★ 含义务动词但无大写 BCP14 强度词且缺协议主体 ⇒ ★ "
                "**不确定**（★ 不得直接归为描述性）", _sig)
    # ══ ⑤ 描述性语义（★ ★ 但先判「陈述式规范句」）══
    _decl, _dreason = is_declarative_normative(_s)
    _sig["★ 陈述式规范句"] = _decl
    if _decl:
        return (NORMATIVE_RULE_CANDIDATE, NORMATIVE_RULE_CANDIDATE, "eligible",
                _dreason, _sig)
    return (PROTOCOL_DESCRIPTIVE, PROTOCOL_DESCRIPTIVE, "ineligible",
            "★ 无 BCP14 强度词且非语法/登记 ⇒ ★ 描述性知识"
            "（★ 走既有 definition / existence 通道）；★ " + _dreason, _sig)


def route_of(knowledge_kind: str, rule_eligibility: str) -> str:
    """★ 知识类别 ⇒ 处理路径（★ 不删除任何知识）。"""
    if rule_eligibility == "eligible":
        return ROUTE_RULE
    if rule_eligibility == "uncertain":
        return ROUTE_REVIEW
    if knowledge_kind == PROTOCOL_SYNTAX:
        return ROUTE_STRUCTURED
    if knowledge_kind == PROTOCOL_REGISTRY:
        return ROUTE_STRUCTURED
    if knowledge_kind == PROTOCOL_DESCRIPTIVE:
        return ROUTE_DESCRIPTIVE
    if knowledge_kind == NON_PROTOCOL_METADATA:
        return ROUTE_METADATA
    return ROUTE_REVIEW


def classify_candidate(*, candidate_id: str, source_doc: str, source_sha256: str,
                       source_span: int, lines, anchor: int,
                       entity: str = "", action: str = "",
                       object_: str = "", strength: str = "",
                       subject: str = "", constraint: str = "",
                       window: int = 3) -> dict:
    """★ 对**一个候选**做 V2 判定（★ 输出 10 个规定字段）。"""
    _ctx = []
    for i in range(max(1, anchor - window), min(len(lines), anchor + window) + 1):
        _ctx.append(lines[i - 1])
    # ★ 元数据章节检测（★ 结构位置）：★ 向上找最近的章节标题
    _meta_zone = False
    for i in range(anchor, max(0, anchor - 60), -1):
        _t = str(lines[i - 1] or "").strip()
        if _META_SECTION.match(_t):
            _meta_zone = True
            break
        if re.match(r"^\s*\d+\.\s+\S", _t) and not _META_SECTION.match(_t):
            break
    _sents = _sentences(lines, anchor, window)
    # ★ ★ **完整逻辑行**（★ 条件从句与主体常跨句 ⇒ ★ 判定须在逻辑行上进行）
    _logical = " ".join(_sents)
    _cand_text = _logical or \
        str(lines[anchor - 1] if 1 <= anchor <= len(lines) else "")
    # ★ ★ **证据跨度选择（★ 第 4 轮调整）**：
    #   ★ 优先级 1：★ 同时含 **entity** 且含 **BCP14 强度词**的句
    #   ★ 优先级 2：★ 含 entity 的句
    #   ★ 优先级 3：★ 含强度词的句
    #   ★ 优先级 4：★ 锚点行
    # ⇒ ★ 避免「entity 首匹配选到章节标题/定义句」导致类型误判
    _pick = None
    if entity:
        for _s in _sents:
            if entity.lower() in _s.lower() and _BCP14.search(_s):
                _pick = _s
                break
        if _pick is None:
            for _s in _sents:
                if entity.lower() in _s.lower():
                    _pick = _s
                    break
    if _pick is None:
        for _s in _sents:
            if _BCP14.search(_s):
                _pick = _s
                break
    # ★ ★ **跨度合并（★ 第 5 轮调整）**：★ 「含 entity 的句」与「含强度词的句」
    #   ★ 若在同一逻辑行内且相邻（★ 索引差 ≤ 2）⇒ ★ **合并为一段证据**
    #   ★ （★ 例：「The CSeq field specifies … This field MUST be present in all requests …」）
    _merged = False
    _target = _pick or _cand_text
    if entity:
        _ei = next((i for i, s in enumerate(_sents)
                    if entity.lower() in s.lower()), None)
        _bi = next((i for i, s in enumerate(_sents)
                    if _BCP14.search(s)), None)
        if _ei is not None and _bi is not None and abs(_ei - _bi) <= 2:
            _lo, _hi = sorted((_ei, _bi))
            _target = " ".join(_sents[_lo:_hi + 1])
            _merged = True
    # ★ ★ **合并优先于单句**（★ 否则合并逻辑会被短路）
    if not _merged:
        _target = _pick or _target
    _sk, _kk, _elig, _reason, _sig = classify_sentence(
        _target, _ctx, _meta_zone)
    # ★ ★ **陈述式规范句的跨句复核**（★ 条件/主体常在相邻句 ⇒ ★ 在逻辑行上再判一次）
    if _kk != NORMATIVE_RULE_CANDIDATE and _logical:
        _decl2, _r2 = is_declarative_normative(_logical)
        if _decl2:
            _sk = _kk = NORMATIVE_RULE_CANDIDATE
            _elig = "eligible"
            _reason = ("★ 跨句复核（★ 完整逻辑行）：" + _r2)
            _sig["★ 陈述式规范句（跨句）"] = True
    _route = route_of(_kk, _elig)
    # ★ 证据跨度（★ 只覆盖被判定的那一句，★ 保留原始证据）
    _ev_line = anchor
    if _pick:
        for i in range(max(1, anchor - window), min(len(lines), anchor + window) + 1):
            if lines[i - 1].strip() == _pick.strip():
                _ev_line = i
                break
    return {
        "candidate_id": candidate_id,
        "source_doc": source_doc,
        "source_sha256": source_sha256,
        "source_span": source_span,
        "source_kind": _sk,
        "knowledge_kind": _kk,
        "rule_eligibility": _elig,
        "evidence_span": {"line": _ev_line, "text": _target[:400]},
        "reason": _reason,
        "route": _route,
        "★ 判据信号": _sig,
        "★ 复用既有 aspect 通道": STRUCTURED_ASPECT.get(_kk),
        "★ 是否进入 V1 三态判断": _route == ROUTE_RULE,
    }


__all__ = ["NON_PROTOCOL_METADATA", "PROTOCOL_SYNTAX", "PROTOCOL_REGISTRY",
           "PROTOCOL_DESCRIPTIVE", "NORMATIVE_RULE_CANDIDATE",
           "MIXED_OR_UNCERTAIN", "ROUTE_RULE", "ROUTE_STRUCTURED",
           "ROUTE_METADATA", "ROUTE_DESCRIPTIVE", "ROUTE_REVIEW",
           "STRUCTURED_ASPECT", "classify_sentence", "classify_candidate",
           "route_of"]
