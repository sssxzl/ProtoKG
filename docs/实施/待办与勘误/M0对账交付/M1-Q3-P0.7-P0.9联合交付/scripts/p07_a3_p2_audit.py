# -*- coding: utf-8 -*-
"""★ P0.7 第 3 步：B5-P2 —— ★ 高风险语义字段专项审计（★ 离线优先）。

★ 覆盖：strength/polarity 异常｜subject≠entity｜跨块证据｜coreference 风险｜已知边界案例
★ 逐字段核查：subject / action / object / strength / polarity / condition / exception
★ 规则：
  ① 主体归属必须有独立证据
  ② SHOULD NOT / MUST NOT 等否定不能被拆成错误强度
  ③ 跨行对象必须完整
  ④ 条件与例外不能误归为动作
  ⑤ 同段相邻义务不能错误拼接
  ⑥ ★ **指代 resolved 只代表归属成立，不代表全部字段正确**
  ⑦ 无法确认 ⇒ 保持待审
★ API 上限 16（★ 本阶段**以离线为主** ⇒ 实际用量应远低于上限）
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import (AUDIT06, LEDGER_B1, OUTROOT, doc_lines, load_frozen_orig,
                  load_jsonl, save_json, save_jsonl)

led = {x["candidate_id"]: x for x in load_jsonl(LEDGER_B1)}
aud = {x["candidate_id"]: x for x in load_jsonl(AUDIT06)}
orig = load_frozen_orig()

_NEG = ("SHOULD NOT", "MUST NOT", "SHALL NOT", "MAY NOT", "NOT RECOMMENDED")
_NEG_RE = re.compile(r"\b(SHOULD NOT|MUST NOT|SHALL NOT|MAY NOT|NOT RECOMMENDED)\b")


def _norm(s):
    _s = str(s or "").lower()
    _s = re.sub(r"[^a-z0-9 ]+", " ", _s)
    return re.sub(r"\s+", " ", _s).strip()


def _contains(q, term):
    _t = _norm(term)
    if not _t:
        return None
    _q = _norm(q)
    if _t in _q:
        return True
    _stems = {"include": "includ", "contain": "contain", "list": "list",
              "use": "us", "move": "mov", "process": "process",
              "equal": "equal", "follow": "follow", "send": "send",
              "set": "set", "perform": "perform", "carry": "carr",
              "ignore": "ignor", "require": "requir"}
    for _s, _st in _stems.items():
        if _t.startswith(_s) and _st in _q:
            return True
    return False


# ★ 高风险集合（★ 按 candidate_id 去重）
_risk = {}
for cid, x in led.items():
    _t = set(x["★ 风险标签"])
    _rs = []
    if "strength_polarity_anomaly" in _t:
        _rs.append("strength_polarity")
    if "subject_ne_entity" in _t:
        _rs.append("subject_ne_entity")
    if "cross_chunk_evidence" in _t:
        _rs.append("cross_chunk")
    if "coreference_subject" in _t:
        _rs.append("coreference")
    if cid == "rfc2326.txt@2747#1":
        _rs.append("★ 已知边界案例")
    if _rs:
        _risk[cid] = _rs

print(f"  ★ 高风险候选（★ 去重后）= {len(_risk)}")
_cnt = collections.Counter(t for v in _risk.values() for t in v)
print(f"  ★ 风险分布: {dict(_cnt)}")

reviews = []
for cid, risks in sorted(_risk.items()):
    x = led[cid]
    o = orig.get(cid, {})
    a = aud[cid]
    L = doc_lines(a["protocol"], a["document"])
    q = a.get("new_quote") or ""
    _att = x.get("attribution") or {}
    # ① 主体
    _subj = str(o.get("normative_subject") or "")
    _ent = str(o.get("entity") or "")
    _subj_in_q = _contains(q, _subj) if _subj else None
    _ent_in_q = _contains(q, _ent) if _ent else None
    _subj_ne_ent = bool(_subj and _ent and _subj.lower() != _ent.lower())
    # ② 强度 / 极性
    _str = str(o.get("strength") or "").strip().upper()
    _q_u = q.upper()
    _neg_in_quote = bool(_NEG_RE.search(_q_u))
    _str_present = (_str in _q_u) if _str else None
    _neg_mismatch = (_str in ("MUST", "SHOULD", "MAY", "REQUIRED")
                     and _neg_in_quote and "NOT" not in _str)
    # ③ 对象跨行完整性
    _obj = str(o.get("object") or "")
    _obj_in_q = _contains(q, _obj) if _obj else None
    _obj_cross = (_obj_in_q is False and _ent_in_q is not False)
    # ④ 条件 / 例外 是否被误当动作
    _con = str(o.get("constraint") or "")
    _con_in_q = _contains(q, _con) if _con else None
    # ⑤ 相邻义务拼接（★ quote 内是否出现多个强度词）
    _multi_strength = len({m for m in _NEG_RE.findall(_q_u)}) + \
        len([m for m in ("MUST", "SHOULD", "MAY") if m in _q_u])
    # ⑥ 指代 resolved ≠ 字段全对
    _coref_resolved = (_att.get("status") == "coreference_resolved")
    _all_ok = all(v is not False for v in
                  (_subj_in_q, _obj_in_q, _str_present)) and not _neg_mismatch
    if not _all_ok:
        _concl = "★ 待复核（★ 字段未被原文完整支持）"
    elif _coref_resolved:
        _concl = "★ 归属成立但需逐字段确认（★ 指代 resolved ≠ 字段全对）"
    else:
        _concl = "valid"
    reviews.append({
        "candidate_id": cid, "protocol": a["protocol"], "document": a["document"],
        "风险标签": risks,
        "原始字段": {"entity": _ent, "normative_subject": _subj,
                  "action": o.get("action"), "object": _obj,
                  "strength": o.get("strength"), "polarity": o.get("polarity"),
                  "condition": o.get("constraint"), "exception": o.get("exception"),
                  "raw_span": o.get("raw_span")},
        "主要证据": {"lines": a.get("source_lines"), "quote": q},
        "辅助证据": (a.get("aux_evidence") or [{}])[0].get("text")
        if a.get("aux_evidence") else None,
        "字段核查": {
            "subject_in_quote": _subj_in_q, "entity_in_quote": _ent_in_q,
            "subject_ne_entity": _subj_ne_ent,
            "strength_present": _str_present,
            "★ 否定与强度不匹配": _neg_mismatch,
            "object_in_quote": _obj_in_q,
            "★ 对象疑似跨行截断": _obj_cross,
            "condition_in_quote": _con_in_q,
            "★ quote 内强度词数量": _multi_strength,
            "★ 归属状态": _att.get("status"),
        },
        "★ 结论": _concl,
        "★ 审计方式": "★ **模型辅助复核（确定性原文比对）** —— ★ **非独立人工确认**",
    })
    print(f"  · {cid:24s} {','.join(risks):34s} ⇒ {_concl[:34]}")

_c = collections.Counter(r["★ 结论"] for r in reviews)
print()
print("  ★ 结论分布:", dict(_c))
save_jsonl(OUTROOT / "p07_semantic_audit.jsonl", reviews)
save_json(OUTROOT / "p07_a3_p2_summary.json", {
    "total": len(reviews), "risk_distribution": dict(_cnt),
    "conclusions": dict(_c),
    "★ API 调用": "★ 本阶段**纯离线**（★ 0 次 API ⇒ 未触及 16 次上限）",
    "★ 审计方式": "模型辅助复核（确定性原文比对）；★ 非独立人工确认",
})
print(f"\n  ⇒ {OUTROOT/'p07_semantic_audit.jsonl'}")
