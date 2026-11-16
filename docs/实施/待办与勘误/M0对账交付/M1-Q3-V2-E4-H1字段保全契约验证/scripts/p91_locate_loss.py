# -*- coding: utf-8 -*-
"""★ H1 §三/§四/§六：★ **沿真实源码定位字段丢失点**（★ 只读，★ 不改生产）。

★ 核心：★ Norm 层【实际携带】9 个结构化字段；★ 丢失发生在
★ `prose_constraint_norm_to_facts` 的**两个降级分支**（★ 不进入 Rule Slot / Assertion 路径）
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/h0"))
OUTD = ROOT / "guard/_out/_n1c_v2/h1"
OUTD.mkdir(parents=True, exist_ok=True)

H3 = [json.loads(l) for l in
      (ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl")
      .read_text(encoding="utf-8").splitlines() if l.strip()]
RAW = [json.loads(l) for l in
       (ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3原始LLM输出.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()]

# ★ ★ Norm 层【实际】的键（★ 自生产 prose_semantics.py:1189 的 norms.append）
NORM_ACTUAL = ["kind", "protocol", "kb_source_type", "name", "content",
               "norm_id", "source", "entity", "meaning", "constraint",
               "span_line", "span_matched_line", "span_mode",
               "evidence_quote", "evidence_quote_span",
               "evidence_boundary_reason", "evidence_aux",
               "evidence_cross_chunk", "evidence_degraded",
               "action", "object", "strength", "polarity", "keyword_raw",
               "condition", "exception", "cross_ref", "cross_ref_status",
               "mentioned_entity", "normative_subject", "subject_span",
               "subject_status"]
# ★ canonical build_payload 需要的字段（★ SEMANTIC_FIELDS + 主体）
PAYLOAD_FIELDS = ["strength", "polarity", "condition", "condition_status",
                   "exception", "exception_status", "scope", "action", "object",
                   "cross_ref", "cross_ref_status"]
# ★ 语义字段（三态）
SEMANTIC = ["strength", "polarity", "condition", "condition_status",
             "exception", "exception_status", "scope", "action", "object",
             "cross_ref", "cross_ref_status"]

_rows = []
_branch = collections.Counter()
for _c in H3:
    _n = _c["★ norm（★ 派生层输出）"]
    _doc = _c["★ document_id"]
    _sl = int(_n.get("span_line") or 0)
    _raw = {}
    for _r in RAW:
        _ri = _r["★ ★ 原始 LLM 输出（★ 全字段）"]
        if _ri.get("doc") == _doc and int(_ri.get("span") or 0) <= _sl:
            _raw = _ri
    # ★ ★ 判定走哪条分支（★ 复刻生产 `prose_constraint_norm_to_facts` 的判定顺序）
    _ss = str(_n.get("subject_status") or "")
    _name = str(_n.get("name") or "")
    _act = str(_n.get("action") or "").strip()
    _obj = str(_n.get("object") or "").strip()
    if _ss and _ss != "resolved":
        _b = "★ 分支1：主体未解析 ⇒ normative_unspecified（★ 丢 action/object/strength/polarity/condition…）"
    elif (not _act or not _obj
          or (_act.lower() == _name.lower() and _obj.lower() == _name.lower())):
        _b = "★ 分支2：动作/对象缺失或为主体名占位 ⇒ 普通 definition（★ 丢全部结构化字段）"
    else:
        _b = "★ 正常路径：★ Rule Slot + Assertion（★ 结构化字段全部进入 canonical）"
    _branch[_b.split("：")[0]] += 1
    # ★ 逐字段状态（★ 真实）
    for _f in SEMANTIC:
        _llm = str((_raw or {}).get(_f) or "").strip()
        _nrm = str(_n.get(_f) or "").strip()
        if _f in ("condition_status", "exception_status", "scope"):
            _nrm_present = _f in _n
            _carrier = ("★ build_payload 默认 unknown（★ status）/ None（★ scope）"
                        if _nrm_present or True else "")
        else:
            _nrm_present = _f in _n
            _carrier = ""
        # ★ canonical 承载
        if _b.startswith("★ 正常路径"):
            _canon = ("★ Assertion（★ [RULE:v1] JSON）" if _f in
                      ("strength", "polarity", "condition", "exception",
                       "scope", "cross_ref", "cross_ref_status",
                       "condition_status", "exception_status")
                      else "★ Rule Slot qualifiers")
            _loss = "★ 无丢失"
        else:
            _canon = ("★ 仅 constraint 文本（★ 声明的值）"
                      if _f in ("strength", "polarity", "condition", "exception",
                               "scope", "cross_ref", "cross_ref_status")
                      else "★ 未承载")
            _loss = ("★ E（★ 派生已使用，★ 但 Norm 路径【未保留必要语义】）"
                     if _nrm_present else
                     "★ D（★ LLM 未产出）" if not _llm else
                     "★ E（★ LLM 已产出，★ 但 Norm 未保留）")
        _rows.append({
            "candidate_id": _c["★ candidate_id"],
            "knowledge_kind": _c["★ proposed_knowledge_kind"],
            "source_span": _c["★ source_span"],
            "field": _f,
            "original_value": str((_raw or {}).get(_f) or "")[:120],
            "source_stage": ("★ 阶段1 LLM" if _llm else "★ （未产出）"),
            "destination_stage": "★ 阶段2 Norm",
            "destination_field": _f if _nrm_present else "★ （无）",
            "transformation_type": "★ 直通" if _nrm_present else "★ 未保留",
            "semantic_equivalence": ("★ 等价" if _nrm_present else "★ 不可重建"),
            "loss_classification": _loss,
            "evidence": (f'★ 分支：{_b[:70]}｜LLM值={str((_raw or {}).get(_f) or "")[:40]}'),
            "recommended_fix": ("★ 无需修复" if not _loss.startswith("★ D")
                              else "★ 需在 Norm 路径保留该字段"),
            "★ canonical 承载": _canon,
            "★ 走哪条分支": _b,
        })

# ★ 完整链（★ 含无丢失项）另存
with (OUTD / "h1_field_trace_full.jsonl").open("w", encoding="utf-8") as f:
    for _r in _rows:
        f.write(json.dumps(_r, ensure_ascii=False) + "\n")
# ★ ★ 异常归因（★ 用户交付项「97 条异常逐项归因」⇒ ★ 只含 E 类真异常）
_anomaly = [r for r in _rows if r["loss_classification"].startswith("★ E")]
with (OUTD / "h1_97_anomaly_attribution.jsonl").open("w", encoding="utf-8") as f:
    for _r in _anomaly:
        f.write(json.dumps(_r, ensure_ascii=False) + "\n")

print("  ★ 分支分布：")
for _k, _v in _branch.items():
    print(f"      {_k}: {_v}")
_lost = [r for r in _rows if r["loss_classification"].startswith("★ E")]
_d = [r for r in _rows if r["loss_classification"].startswith("★ D")]
print(f"  ★ 字段记录总数 = {len(_rows)}｜E（Norm 未保留语义）= {len(_lost)}"
      f"｜D（LLM 未产出）= {len(_d)}")
print(f"  ★ E 类按字段：{dict(collections.Counter(r['field'] for r in _lost))}")
print(f"  ★ E 类涉及的候选数 = {len({r['candidate_id'] for r in _lost})}")
print(f"  ★ E 类按知识类型：{dict(collections.Counter(r['knowledge_kind'] for r in _lost))}")

(OUTD / "h1_loss_summary.json").write_text(json.dumps({
    "★ 分支分布": dict(_branch),
    "★ 字段记录总数": len(_rows),
    "★ E 类数": len(_lost),
    "★ D 类数": len(_d),
    "★ E 类按字段": dict(collections.Counter(r["field"] for r in _lost)),
    "★ E 类候选数": len({r["candidate_id"] for r in _lost}),
    "★ Norm 层实际键（★ 自源码）": NORM_ACTUAL,
    "★ canonical payload 需要字段": PAYLOAD_FIELDS,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'h1_field_loss_attribution.jsonl'}")
