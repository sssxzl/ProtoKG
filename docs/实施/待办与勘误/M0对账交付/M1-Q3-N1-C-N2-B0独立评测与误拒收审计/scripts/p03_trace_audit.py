# -*- coding: utf-8 -*-
"""★ N2-B0：★ 确定性拒收闸门的**逐条执行轨迹**（★ 只读诊断，★ 不跑 LLM）。

★ 对 N1-B 中「人工判成立但模型 rejected」的样本，★ 重建真实执行路径：
  candidate_id → truth_label → evidence → **first_blocking_stage** →
  blocking_reason → rejection_rule → deterministic_or_LLM → proposed_action
★ ★ **只重跑确定性部分**（★ 廉价且确定）⇒ ★ **不重跑 LLM 来填补历史状态**
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction import normative_extract as ne
from core.fused.extraction import normative_verify as nv

OUTD = ROOT / "guard/_out/n1c"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

sample = [json.loads(l) for l in
          (N1B / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (N1B / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}
FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = it
_docs = {}


def _lines(proto, doc):
    _k = (proto, doc)
    if _k not in _docs:
        _p = ROOT / f"kb/{proto}/spec/{doc}"
        _docs[_k] = _p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")
    return _docs[_k]


# ★ ★ 目标样本：★ 人工判 valid_confirmed 且模型 rejected
_targets = [r for r in sample
            if r["★ 模型 L2 状态"] == "rejected"
            and r["★ 第一层 规范义务存在性"] == "valid_confirmed"]
print(f"  ★ 误拒收样本 = {len(_targets)}")

trace = []
for r in _targets:
    cid = r["sample_id"]
    _sp = spans[cid]
    _o = FR.get(cid, {})
    _L = _lines(_sp["★ protocol"], _sp["★ document"])
    _rs = _sp["resolved_span"]
    _quote = "\n".join(_L[_rs - 1:_rs + 2])       # ★ 证据窗口（锚点行）
    _quote_full = "\n".join(_L[max(0, _rs - 4):min(len(_L), _rs + 4)])
    _action = str(_o.get("action") or "")
    _object = str(_o.get("object") or "")
    _strength = str(_o.get("strength") or "")
    _subject = str(_o.get("normative_subject") or _o.get("entity") or "")
    # ── 阶段 1：跨度定位 ──
    _ev = ne.resolve_span_evidence(_L, _sp["raw_span"], _sp["★ entity"],
                                   chunk_start=_sp["chunk_start"],
                                   chunk_end=_sp["chunk_end"])
    _span_ok = (_ev.get("resolved_span") == _rs)
    # ── 阶段 2：主体归属（entity_in_span ±3）──
    _subj_hit = ne.entity_in_span(_L, _rs, _sp["★ entity"], window=3)
    # ── 阶段 3：★ 确定性语义支持（★ 真正的第一阻塞点）──
    _det_v, _det_r = nv.l2_deterministic_check(payload={
        "action": _action, "object": _object, "strength": _strength},
        quote=_quote)
    _det_v_full, _det_r_full = nv.l2_deterministic_check(payload={
        "action": _action, "object": _object, "strength": _strength},
        quote=_quote_full)
    # ── 逐条拆解 semantic_support 的三条判据 ──
    _flat = " ".join(_quote.lower().split())
    _flat_n = " ".join(_flat.replace("_", " ").split())
    _why = []
    if _action:
        _a = " ".join(_action.lower().replace("_", " ").split())
        if _a and _a not in _flat_n:
            _stem = _a[:-1] if _a.endswith("e") else _a
            if _stem not in _flat_n:
                _why.append(f"★ 动作「{_action}」未按**精确/去尾e**匹配命中")
    if _object:
        _o_n = " ".join(_object.lower().replace("_", " ").split())
        if _o_n and _o_n not in _flat_n:
            _why.append(f"★ 对象「{_object}」未按**精确**匹配命中")
    if _strength:
        _s = _strength.strip().upper()
        _syn = {"MUST": ("must", "shall", "required"),
                "SHOULD": ("should", "recommended"),
                "MAY": ("may", "optional")}
        if not any(w in _flat for w in _syn.get(_s, (_s.lower(),))):
            _why.append(f"★ 强度「{_strength}」的同义词集"
                        f"{_syn.get(_s, (_s.lower(),))} 未在证据中出现")
    # ── 拒收原因分类（A~G）──
    _reasons = _det_r.split("；") if _det_r else []
    if _det_v != "不支持":
        _cat = "★ 非确定性前置拒收（★ 需另行定位）"
        _stage = "★ L2/LLM 阶段"
    else:
        _stage = "★ semantic_support（★ 确定性前置）"
        if any("强度" in x for x in _reasons) and \
                not any("动作" in x or "对象" in x for x in _reasons):
            _cat = "★ D 强度识别错误（★ 无明确反证，★ 仅词面缺失）"
        elif any("动作" in x or "对象" in x for x in _reasons) and \
                not any("强度" in x for x in _reasons):
            _cat = "★ B 仅词面/同义词不匹配（★ 无明确反证）"
        else:
            _cat = "★ B 仅词面/同义词不匹配（★ 含强度词面）"
    # ── 是否存在**明确反证**（★ 原文里出现相反的强度/否定）──
    _neg = [w for w in ("must not", "shall not", "should not", "may not")
            if w in _flat]
    _explicit = bool(_neg)
    trace.append({
        "candidate_id": cid, "分组": r["分组"],
        "truth_label": r["★ 第一层 规范义务存在性"],
        "second_layer": r["★ 第二层 候选字段完整性"],
        "evidence_support": r["★ 人工 evidence_support"],
        "★ evidence（锚点行原文）": _L[_rs - 1],
        "★ 证据窗口（锚点行）": _quote[:300],
        "★ 候选字段": {"subject": _subject, "action": _action,
                    "object": _object, "strength": _strength},
        "★ 阶段1 跨度定位": {"resolved_span": _ev.get("resolved_span"),
                       "span_mode": _ev.get("span_mode"),
                       "★ 与台账一致": _span_ok},
        "★ 阶段2 主体归属（entity_in_span ±3）": {
            "hit": _subj_hit, "★ 主体有独立证据": bool(_subj_hit)},
        "★ 阶段3 semantic_support": {
            "verdict": _det_v, "reason": _det_r,
            "★ 逐条拆解": _why,
            "★ 加宽证据窗口后的 verdict": _det_v_full},
        "★ 明确反证（★ 原文含相反强度/否定）": _explicit,
        "first_blocking_stage": _stage,
        "blocking_reason": _det_r,
        "rejection_rule": _cat,
        "deterministic_or_LLM": "★ **确定性**（★ 未进入 LLM）"
                          if _det_v == "不支持" else "★ LLM",
        "★ 模型实际 api_attempts": None,
        "proposed_action": (
            "★ **A 保留 rejected**" if _explicit else
            "★ **B 改判 uncertain → pending**（★ 无明确反证，★ 仅词面不匹配）"
            "⇒ ★ 需补充原文证据后由人工/受控路径核验"),
    })

# ★ 汇总
_cat = collections.Counter(t["rejection_rule"] for t in trace)
_stage = collections.Counter(t["first_blocking_stage"] for t in trace)
_expl = sum(1 for t in trace if t["★ 明确反证（★ 原文含相反强度/否定）"])
print("  ★ first_blocking_stage：", dict(_stage))
print("  ★ rejection_rule：", dict(_cat))
print(f"  ★ ★ 有明确反证（⇒ 应保留 rejected）= {_expl}"
      f"｜无明确反证（⇒ 应改 pending）= {len(trace) - _expl}")
print("  ★ 加宽证据窗口后 verdict 变化：",
      dict(collections.Counter(t["★ 阶段3 semantic_support"]["★ 加宽证据窗口后的 verdict"]
                            for t in trace)))
for t in trace:
    print(f"      {t['candidate_id'][:26]:28s} {t['rejection_rule'][:36]:38s}"
          f"｜{t['blocking_reason'][:70]}")

(OUTD / "n2b0_blocking_trace.jsonl").write_text(
    "\n".join(json.dumps(t, ensure_ascii=False) for t in trace) + "\n",
    encoding="utf-8")
(OUTD / "n2b0_blocking_summary.json").write_text(json.dumps({
    "★ 目标": "★ N1-B 中人工判成立但模型 rejected 的样本",
    "★ 条数": len(trace),
    "★ first_blocking_stage 分布": dict(_stage),
    "★ rejection_rule 分布": dict(_cat),
    "★ 有明确反证（保留 rejected）": _expl,
    "★ 无明确反证（改 pending）": len(trace) - _expl,
    "★ 加宽证据窗口后 semantic_support verdict": dict(collections.Counter(
        t["★ 阶段3 semantic_support"]["★ 加宽证据窗口后的 verdict"] for t in trace)),
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n2b0_blocking_trace.jsonl'}")
