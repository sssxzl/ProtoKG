# -*- coding: utf-8 -*-
"""★ H0 §五/§六 P1：★ **字段级知识保全对账**（★ 影子层，★ 不改生产）。

★ 沿真实链路追踪：``RFC 原文 → LLM 原始 JSON → _extract_blocks 派生 → Norm → Fact 映射 → 中枢消费视图``
★ ★ **不假定每层字段名相同**；★ 逐字段判定状态

★ 七种状态：
  · not_applicable        当前知识类型不需要
  · not_requested        当前 Schema 未要求
  · generated            当前阶段生成
  · derived              由后续结构化逻辑得到
  · transformed          按既有契约转换
  · intentionally_omitted 契约明确不要求保留
  · unexpectedly_lost    **应保留却意外丢失**
  · unresolved           无法确认
"""
from __future__ import annotations

FIELDS = ["entity", "meaning", "normative_subject", "action", "object",
          "strength", "polarity", "condition", "exception", "constraint",
          "cross_ref_status", "evidence_span"]

NOT_APPLICABLE = "not_applicable"
NOT_REQUESTED = "not_requested"
GENERATED = "generated"
DERIVED = "derived"
TRANSFORMED = "transformed"
INTENTIONALLY_OMITTED = "intentionally_omitted"
UNEXPECTEDLY_LOST = "unexpectedly_lost"
UNRESOLVED = "unresolved"

# ★ LLM 原始 Schema 的字段（★ 自生产 `_PROMPT` 的输出约定）
LLM_SCHEMA_FIELDS = ["entity", "meaning", "constraint", "action", "object",
                      "strength", "polarity", "condition", "exception",
                      "normative_subject", "subject_span", "cross_ref",
                      "cross_ref_status", "keyword_raw"]
# ★ Norm 层保留的字段（★ 自生产 `prose_semantics.py` 的 norms.append）
NORM_FIELDS = ["kind", "name", "content", "norm_id", "source", "entity",
               "meaning", "constraint", "span_line", "span_matched_line"]
# ★ Norm 层**没有**、但 LLM 层**有**的字段（★ 结构性丢失点）
LLM_ONLY = ["normative_subject", "action", "object", "strength", "polarity",
             "condition", "exception", "subject_span", "cross_ref",
             "cross_ref_status", "keyword_raw"]

# ★ canonical 身份契约（★ 不改；★ 仅记录映射去向）
CANONICAL_SLOTS = {
    "entity": "A_structure/by_entity_type（★ 经 entity 归一）",
    "meaning": "A_structure（★ 经 content 合并 meaning + constraint）",
    "constraint": "C_constraints（★ 经 content 合并）",
    "normative_subject": "★ **无直接槽位**（★ 派生层未保留 ⇒ 只能经 content 间接体现）",
    "action": "★ **无直接槽位**",
    "object": "★ **无直接槽位**",
    "strength": "★ **无直接槽位**（★ 只能经 constraint 文本间接体现）",
    "polarity": "★ **无直接槽位**（★ 只能经 constraint 文本间接体现）",
    "condition": "★ **无直接槽位**（★ normative_extract.extract_condition 可从文本派生）",
    "exception": "★ **无直接槽位**（★ normative_extract.extract_exception 可从文本派生）",
    "cross_ref_status": "★ **无直接槽位**（★ 仅用于跨句引用判断）",
    "evidence_span": "B_interaction / C_constraints（★ 经 span_line / source 落位）",
}


def _nonempty(v):
    return bool(str(v or "").strip())


def trace_candidate(*, candidate_id: str, knowledge_kind: str,
                    raw_item: dict, norm: dict, source_ref: str,
                    source_resolution: dict,
                    canonical_view: dict = None) -> list[dict]:
    """★ 逐候选逐字段的流转记录。"""
    _rows = []
    _raw = raw_item or {}
    _nrm = norm or {}
    for _f in FIELDS:
        _in_llm = _f in LLM_SCHEMA_FIELDS
        _in_norm = _f in NORM_FIELDS
        _raw_has = _nonempty(_raw.get(_f)) if _in_llm else None
        _nrm_has = _nonempty(_nrm.get(_f)) if _in_norm else None
        if _f == "evidence_span":
            _stage_llm = "★ 不适用（★ 证据跨度非 LLM 产出）"
            # ★ Norm 层的载体是 span_line / source（★ 非同名键）⇒ ★ 单独判定
            _nrm_has = bool(_nrm.get("span_line")) or bool(_nrm.get("source"))
            _in_norm = True
            _stage_norm = GENERATED if _nrm_has else UNEXPECTEDLY_LOST
            _status = (GENERATED if _nrm_has else UNEXPECTEDLY_LOST)
            _note = ("★ 证据跨度由派生层从原文定位产生（★ span_line / source），"
                     "★ **未丢失**")
        elif _in_llm and _in_norm:
            _status = (GENERATED if _raw_has else NOT_REQUESTED)
            if _raw_has and not _nrm_has:
                _status = INTENTIONALLY_OMITTED if _f in ("normative_subject",) \
                    else UNEXPECTEDLY_LOST
            _note = "★ LLM 层有该字段"
        elif _in_llm and not _in_norm:
            if _raw_has:
                _status = UNEXPECTEDLY_LOST
                _note = ("★ ★ LLM 层【已产出】★ 但 Norm 层【无该字段】"
                         "⇒ ★ 结构性丢失（★ 见 §五）")
            else:
                _status = NOT_REQUESTED
                _note = "★ Schema 要求但本次未产出"
        else:
            _status = NOT_APPLICABLE
            _note = "★ 该层不涉及此字段"
        _rows.append({
            "candidate_id": candidate_id,
            "knowledge_kind": knowledge_kind,
            "field": _f,
            "★ LLM 层存在": _in_llm,
            "★ LLM 层非空": _raw_has,
            "★ Norm 层存在": _in_norm,
            "★ Norm 层非空": _nrm_has,
            "★ canonical 视图非空": _nonempty((canonical_view or {}).get(_f)),
            "★ 状态": _status,
            "★ 说明": _note,
            "★ canonical 映射去向": CANONICAL_SLOTS.get(_f, "★ 未映射"),
            "★ source_reference": source_ref,
            "★ normalized_document_id": source_resolution.get(
                "normalized_document_id"),
            "★ source_sha256": source_resolution.get("source_sha256"),
            "★ 来源解析状态": source_resolution.get("status"),
        })
    return _rows


def field_stats(rows):
    """★ §六 六项指标（★ **分别计算，★ 不合并**）。"""
    _by_kind = {}
    for _f in FIELDS:
        _sub = [r for r in rows if r["field"] == _f]
        _n = len(_sub)
        if not _n:
            continue
        _llm_ok = sum(1 for r in _sub if r["★ LLM 层非空"])
        _norm_ok = sum(1 for r in _sub if r["★ Norm 层非空"])
        _canon_ok = sum(1 for r in _sub if r["★ canonical 视图非空"])
        _states = {}
        for r in _sub:
            _states[r["★ 状态"]] = _states.get(r["★ 状态"], 0) + 1
        _by_kind[_f] = {
            "★ 分母（候选数）": _n,
            "① 字段适用率": round(sum(
                1 for r in _sub if r["★ 状态"] != NOT_APPLICABLE) / _n, 4),
            "② 模型输出覆盖率": round(_llm_ok / _n, 4),
            "③ 派生阶段保留率": round(_norm_ok / _n, 4),
            "④ 映射阶段保全率": round(_canon_ok / _n, 4),
            "⑤ 证据支持率": round(sum(
                1 for r in _sub if r.get("★ 来源解析状态") == "resolved") / _n, 4),
            "⑥ 字段语义准确率": "★ unavailable（★ 无可信人工真值）",
            "★ 状态分布": _states,
        }
    return _by_kind


def kind_split_stats(rows):
    """★ 按 knowledge_kind 分组（★ prose_semantics / prose_constraint 分别统计）。"""
    _out = {}
    for _k in sorted({r["knowledge_kind"] for r in rows if r["knowledge_kind"]}):
        _sub = [r for r in rows if r["knowledge_kind"] == _k]
        _out[_k] = {"★ 候选数": len({r["candidate_id"] for r in _sub}),
                     "★ 字段统计": field_stats(_sub)}
    return _out


__all__ = ["FIELDS", "LLM_SCHEMA_FIELDS", "NORM_FIELDS", "LLM_ONLY",
           "CANONICAL_SLOTS", "NOT_APPLICABLE", "NOT_REQUESTED", "GENERATED",
           "DERIVED", "TRANSFORMED", "INTENTIONALLY_OMITTED",
           "UNEXPECTEDLY_LOST", "UNRESOLVED",
           "trace_candidate", "field_stats", "kind_split_stats"]
