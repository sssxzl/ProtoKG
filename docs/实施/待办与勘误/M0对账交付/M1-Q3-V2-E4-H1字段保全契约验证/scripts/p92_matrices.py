# -*- coding: utf-8 -*-
"""★ H1：★ 生成**LLM↔Norm 字段契约矩阵**与**知识类型字段适用性矩阵**（★ 只读）。"""
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/h1"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E4-H1字段保全契约验证"
DELIV.mkdir(parents=True, exist_ok=True)

# ══ §三 前提一：逐字段契约（★ 指向实际源码）══
CONTRACT = [
    # field, Schema定义, 必填性, 首次产生阶段, LLM直出, 确定性派生,
    # 缺失时契约是否允许, 显式转换规则, 源码指向
    ("entity", "✔ 定义（_PROMPT items）", "必填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（空则无候选）", "★ 归一为 norm.entity",
     "prose_semantics.py:1204 norms.append"),
    ("meaning", "✔ 定义", "必填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许", "★ 与 constraint 合并进 norm.content",
     "prose_semantics.py:1204"),
    ("constraint", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许", "★ 进 norm.constraint；★ 分支1/2 时进 norm.content",
     "prose_semantics.py:1204"),
    ("normative_subject", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（★ 主体未解析时走分支1）",
     "★ 进 norm.normative_subject；★ **分支1 时未进 Rule Slot**",
     "prose_semantics.py:1204 / norm.py:548-560"),
    ("action", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（★ 缺失或占位时走分支2）",
     "★ 进 norm.action；★ **分支1/2 时未进 Rule Slot**",
     "prose_semantics.py:1204 / norm.py:577-586"),
    ("object", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（★ 同 action）",
     "★ 进 norm.object；★ **分支1/2 时未进 Rule Slot**",
     "prose_semantics.py:1204 / norm.py:577-586"),
    ("strength", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（★ None ⇒ 记 unknown ⇒ 待审）",
     "★ 进 norm.strength → Assertion；★ **分支1/2 时未进 Assertion**",
     "prose_semantics.py:1204 / normative_rule.py:126-143"),
    ("polarity", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（★ 非法值 ⇒ None）",
     "★ 进 norm.polarity → Assertion；★ **分支1/2 时未进 Assertion**",
     "prose_semantics.py:1204 / normative_rule.py:143-144"),
    ("condition", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✔ 可派生",
     "✔ 允许（★ status 缺省 ⇒ unknown，★ 不默认 absent）",
     "★ 进 norm.condition → Assertion；★ **分支1/2 时未进 Assertion**",
     "prose_semantics.py:1204 / normative_rule.py:145-146"),
    ("exception", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✔ 可派生",
     "✔ 允许（同上）",
     "★ 进 norm.exception → Assertion；★ **分支1/2 时未进 Assertion**",
     "prose_semantics.py:1204 / normative_rule.py:147-148"),
    ("cross_ref_status", "✔ 定义", "选填", "★ 阶段1 LLM", "✔ 是", "✖",
     "✔ 允许（★ 缺省 ⇒ unknown）",
     "★ 进 norm.cross_ref_status → Assertion；★ **分支1/2 时未进 Assertion**",
     "prose_semantics.py:1204 / normative_rule.py:147"),
    ("evidence_span", "✖ 非 LLM 字段", "—", "★ 阶段2 派生", "✖", "✔",
     "✖ 不允许缺（★ 缺则证据不可定位）",
     "★ norm.source + norm.span_line + evidence_quote/span",
     "prose_semantics.py:1204 / norm.py:594-600"),
]
with (DELIV / "H1_LLM与Norm字段契约矩阵.csv").open("w", newline="",
                                          encoding="utf-8") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["字段", "① Schema 是否定义", "② 必填/选填/不适用",
                "③ 哪个阶段首次产生", "④ 是否 LLM 直出", "⑤ 是否确定性派生",
                "⑥ 缺失时契约是否允许", "⑦ 显式转换规则", "★ 源码指向"])
    for _r in CONTRACT:
        w.writerow(list(_r))

# ══ §四 前提二：知识类型字段适用性 ══
TYPES = ["prose_constraint", "prose_semantics", "protocol_syntax",
         "protocol_registry_or_enumeration", "protocol_descriptive_semantics",
         "normative_rule_candidate"]
FIELDS = ["entity", "meaning", "normative_subject", "action", "object",
          "strength", "polarity", "condition", "exception", "constraint",
          "cross_ref_status", "evidence_span"]
# ★ required 须来自真实 Schema 或明确语义要求（★ 不人为要求所有类型都有主体/强度/条件）
APPLICABILITY = {
    "prose_constraint": {
        "entity": "required", "meaning": "required",
        "normative_subject": "optional", "action": "optional",
        "object": "optional", "strength": "optional", "polarity": "optional",
        "condition": "optional", "exception": "optional",
        "constraint": "required", "cross_ref_status": "optional",
        "evidence_span": "required"},
    "prose_semantics": {
        "entity": "required", "meaning": "required",
        "normative_subject": "not_applicable", "action": "not_applicable",
        "object": "not_applicable", "strength": "not_applicable",
        "polarity": "not_applicable", "condition": "not_applicable",
        "exception": "not_applicable", "constraint": "optional",
        "cross_ref_status": "not_applicable", "evidence_span": "required"},
    "protocol_syntax": {
        "entity": "required", "meaning": "optional",
        "normative_subject": "not_applicable", "action": "not_applicable",
        "object": "not_applicable", "strength": "not_applicable",
        "polarity": "not_applicable", "condition": "not_applicable",
        "exception": "not_applicable", "constraint": "not_applicable",
        "cross_ref_status": "not_applicable", "evidence_span": "required"},
    "protocol_registry_or_enumeration": {
        "entity": "required", "meaning": "optional",
        "normative_subject": "not_applicable", "action": "not_applicable",
        "object": "not_applicable", "strength": "not_applicable",
        "polarity": "not_applicable", "condition": "not_applicable",
        "exception": "not_applicable", "constraint": "not_applicable",
        "cross_ref_status": "not_applicable", "evidence_span": "required"},
    "protocol_descriptive_semantics": {
        "entity": "required", "meaning": "required",
        "normative_subject": "not_applicable", "action": "not_applicable",
        "object": "not_applicable", "strength": "not_applicable",
        "polarity": "not_applicable", "condition": "not_applicable",
        "exception": "not_applicable", "constraint": "optional",
        "cross_ref_status": "not_applicable", "evidence_span": "required"},
    "normative_rule_candidate": {
        "entity": "required", "meaning": "required",
        "normative_subject": "required", "action": "required",
        "object": "required", "strength": "required", "polarity": "required",
        "condition": "optional", "exception": "optional",
        "constraint": "required", "cross_ref_status": "optional",
        "evidence_span": "required"},
}
with (DELIV / "H1_知识类型字段适用性矩阵.csv").open("w", newline="",
                                            encoding="utf-8") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["knowledge_kind"] + FIELDS + ["★ 依据"])
    for _t in TYPES:
        w.writerow([_t] + [APPLICABILITY[_t][_f] for _f in FIELDS] + [
            "★ required 来自真实 Schema 或明确语义要求；★ prose_semantics 的规范字段"
            "★ **不适用**（★ 它是描述性知识）；★ normative_rule_candidate 为"
            "★ 规范义务的完整语义要求"])

# ★ 修正后的统计（★ 分母 = 适用字段）
import collections as _c
_rows = [json.loads(l) for l in
         (OUTD / "h1_field_loss_attribution.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()]
_applic = {(r["knowledge_kind"], r["field"]): v
           for r in _rows for v in [APPLICABILITY.get(r["knowledge_kind"], {})
                                   .get(r["field"], "unknown")]}
_stats = {}
for _t in TYPES:
    _sub = [r for r in _rows if r["knowledge_kind"] == _t]
    if not _sub:
        continue
    _app = [r for r in _sub
            if APPLICABILITY.get(_t, {}).get(r["field"]) != "not_applicable"]
    _e = [r for r in _app if r["loss_classification"].startswith("★ E")]
    _d = [r for r in _app if r["loss_classification"].startswith("★ D")]
    _stats[_t] = {
        "★ 候选数": len({r["candidate_id"] for r in _sub}),
        "★ 适用字段记录数（★ 分母）": len(_app),
        "★ 不适用字段记录数": len(_sub) - len(_app),
        "★ 适用率": round(len(_app) / len(_sub), 4) if _sub else "N/A",
        "★ E（Norm 未保留语义）": len(_e),
        "★ D（LLM 未产出）": len(_d),
        "★ ★ 阶段保全率（★ 分子 = 未丢失）": round(
            (len(_app) - len(_e)) / len(_app), 4) if _app else "N/A",
    }
(OUTD / "h1_applicability_stats.json").write_text(
    json.dumps(_stats, ensure_ascii=False, indent=2), encoding="utf-8")
print("  ★ 契约矩阵与适用性矩阵已生成")
for _k, _v in _stats.items():
    print(f"      {_k}: {_v}")
print(f"\n  ⇒ {DELIV/'H1_LLM与Norm字段契约矩阵.csv'}")
print(f"  ⇒ {DELIV/'H1_知识类型字段适用性矩阵.csv'}")
