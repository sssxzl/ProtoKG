# -*- coding: utf-8 -*-
"""★ N1-R2 第 2 步：★ 重建 50 条盲审标注包（★ 契约修复版）。

★ 关键修复：
  ① ★ **跨度定位改用 M1-Q2 的 `resolve_span_evidence` 契约**（★ 绝对优先 / 相对换算 / 歧义不放行）
  ② ★ **抽样池只取 `evidence_supported=True` 的候选**（★ 证据不足 ⇒ 不进标注包）
  ③ ★ **锚点行空白是合法情况**（★ entity 可在 ±3 窗口内命中）⇒ ★ 另行给出**证据句**
  ④ ★ **盲审标签契约**：★ 只填「原文支持程度 + 六个语义字段 + 独立审核理由」
     ⇒ ★ **不要求**盲审者判断 `false_confirmation` / `false_rejection`
     ⇒ ★ 这些**模型相对标签由汇总阶段结合隐藏模型状态自动生成**
"""
import csv
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction.normative_extract import entity_in_span

OUT = ROOT / "guard/_out/n1r2"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
DELIV.mkdir(parents=True, exist_ok=True)
P079 = ROOT / "guard/_out/m1_q3/p079"

spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (OUT / "n1r2_span_ledger.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}
led = {x["candidate_id"]: x for x in
       [json.loads(l) for l in
        (P079 / "p07_candidate_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]}
_docs = {}


def _lines(proto, doc):
    _k = (proto, doc)
    if _k not in _docs:
        _p = ROOT / f"kb/{proto}/spec/{doc}"
        _docs[_k] = _p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")
    return _docs[_k]


# ★ ★ 抽样池：★ **只取 evidence_supported 的候选**
_pool = [cid for cid, r in spans.items()
         if r["evidence_supported"] and cid in led]
print(f"  ★ 证据充分的可标注候选池 = {len(_pool)}（★ 共 {len(spans)} 条）")

_rng = random.Random(20261116)
_MIG = {"rfc3261.txt@1842#2", "rfc3261.txt@12767#1"}
_RISK = ("coreference_subject", "strength_polarity_anomaly", "subject_ne_entity",
         "cross_sentence_object_or_condition")
_risk = []
for cid in _pool:
    _t = set(led[cid].get("★ 风险标签") or [])
    _w = 0
    if cid in _MIG:
        _w += 5
    if "coreference_subject" in _t:
        _w += 4
    if "strength_polarity_anomaly" in _t:
        _w += 3
    if "subject_ne_entity" in _t:
        _w += 3
    if "cross_chunk_evidence" in _t:
        _w += 2
    if "l2_state_migrated" in _t:
        _w += 2
    if led[cid].get("★ 最终状态") == "pending_manual_review":
        _w += 3
    if _w:
        _risk.append((_w, cid))
_risk.sort(key=lambda z: (-z[0], z[1]))
_risk_ids = [c for _, c in _risk[:20]]

_strata = {}
for cid in _pool:
    if cid in _risk_ids:
        continue
    _sp = spans[cid]
    _kind = "constraint" if (led[cid].get("★ 最终状态") != "not_applicable") else "semantics"
    _strata.setdefault((_sp["★ protocol"], _kind), []).append(cid)
_random, _keys, _i = [], sorted(_strata), 0
while len(_random) < 30 and _i < 800:
    _k = _keys[_i % len(_keys)]
    _lst = _strata[_k]
    if _lst:
        _cid = _lst.pop(_rng.randrange(len(_lst)))
        if _cid not in _random:
            _random.append(_cid)
    _i += 1
_ids = _risk_ids + _random
print(f"  ★ 抽样：K 风险 {len(_risk_ids)} + R 随机 {len(_random)} = {len(_ids)}")
if len(_ids) < 50:
    print(f"  ★ ★ 证据充分候选不足 50（★ 实际 {len(_ids)}）⇒ ★ 按冻结规则补充")
    for cid in _pool:
        if len(_ids) >= 50:
            break
        if cid not in _ids:
            _ids.append(cid)

_NEG = ("MUST NOT", "SHALL NOT", "SHOULD NOT", "MAY NOT", "NOT RECOMMENDED")


def _polarity(strength):
    _s = str(strength or "").strip().upper()
    if not _s:
        return "", "★ 原始候选无 strength ⇒ 无法推导"
    if _s in _NEG:
        return "negative", f"★ **推导值**：strength={_s} ⇒ 含否定形式"
    return "positive", f"★ **推导值**：strength={_s}"


def _build(cid, group):
    _sp = spans[cid]
    _L = _lines(_sp["★ protocol"], _sp["★ document"])
    _rs = _sp["resolved_span"]
    _ent = _sp["★ entity"]
    _ctx = [{"line": i, "text": _L[i - 1]}
            for i in range(max(1, _rs - 6), min(len(_L), _rs + 6) + 1)]
    # ★ 证据句（★ 锚点 ±3 内**含 entity 的非空行**；★ 锚点行本身可为空）
    _ev_line = None
    for i in range(max(1, _rs - 3), min(len(_L), _rs + 3) + 1):
        if _ent and _ent.lower() in _L[i - 1].lower() and _L[i - 1].strip():
            _ev_line = {"line": i, "text": _L[i - 1]}
            break
    _pol, _pol_src = _polarity(led[cid].get("★ 风险标签") and
                                _sp.get("★ entity") and "" or "")
    # ★ strength 从冻结件取
    from pathlib import Path
    _fz = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl"
    return {"_sp": _sp, "_L": _L, "_rs": _rs, "_ent": _ent, "_ctx": _ctx,
            "_ev_line": _ev_line, "_group": group}


# ★ 冻结件的原始字段（含 strength 等）
FR = {}
for b in [json.loads(l) for l in
          (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl")
          .read_text(encoding="utf-8").splitlines() if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = it

packs = []
for cid in _ids:
    _sp = spans[cid]
    _L = _lines(_sp["★ protocol"], _sp["★ document"])
    _rs = _sp["resolved_span"]
    _ent = _sp["★ entity"]
    _o = FR.get(cid, {})
    _ctx = [{"line": i, "text": _L[i - 1]}
            for i in range(max(1, _rs - 6), min(len(_L), _rs + 6) + 1)]
    _ev_line = None
    for i in range(max(1, _rs - 3), min(len(_L), _rs + 3) + 1):
        if _ent and _ent.lower() in _L[i - 1].lower() and _L[i - 1].strip():
            _ev_line = {"line": i, "text": _L[i - 1]}
            break
    _pol, _pol_src = _polarity(_o.get("strength"))
    packs.append({
        "sample_id": cid, "分组": "K" if cid in _risk_ids else "R",
        "protocol": _sp["★ protocol"], "document": _sp["★ document"],
        "rfc_sha256": _sp["★ rfc_sha256"],
        "chunk_id": f"{_sp['★ document']}@{_sp['chunk_start']}",
        "chunk_start": _sp["chunk_start"], "chunk_end": _sp["chunk_end"],
        "★ raw_span": _sp["raw_span"], "★ resolved_span": _rs,
        "★ span_mode": _sp["span_mode"], "★ within_chunk": _sp["within_chunk"],
        "★ matched_evidence_lines": _sp["★ matched_evidence_lines"],
        "★ 锚点行原文（★ 可为空）": _L[_rs - 1],
        "★ 锚点行是否空白": (not _L[_rs - 1].strip()),
        "★ 证据句（含 entity 的非空行）": _ev_line,
        "★ RFC 原文上下文（锚点 ±6 行）": _ctx,
        "★ LLM 原始候选字段": {
            "entity": _o.get("entity"), "normative_subject": _o.get("normative_subject"),
            "action": _o.get("action"), "object": _o.get("object"),
            "strength": _o.get("strength"), "polarity": _o.get("polarity"),
            "condition": _o.get("condition"), "exception": _o.get("exception")},
        "★ LLM meaning（生成文本，★ 非原文）": _o.get("meaning"),
        "★ LLM constraint（生成文本，★ 非原文）": _o.get("constraint"),
        "★ 推导 polarity（供核对）": _pol, "★ polarity 来源": _pol_src,
    })

# ★ ★ 盲审标签契约（★ **不含** false_* ★）
BLIND_FIELDS = [
    ("subject", "义务承担者（★ 指代须写出解析后的实际承担者）"),
    ("action", "行为动词"),
    ("object", "行为对象（★ 跨行须完整）"),
    ("strength", "MUST/MUST NOT/SHOULD/SHOULD NOT/MAY/…"),
    ("polarity", "positive / negative"),
    ("condition", "★ 原文中的条件；★ 无则 null；★ **不得**填整条 constraint"),
    ("exception", "★ 原文中的例外；★ 无则 null"),
    ("evidence_support", "supported / partially_supported / contradicted / evidence_insufficient"),
    ("truth_label", "★ **独立语义真值**：valid_confirmed / valid_rejection / "
              "pending_insufficient_evidence / uncertain_requires_human"),
    ("review_note", "★ 独立审核理由（★ 必填或说明依据）"),
]

HEAD_BASE = [
    "sample_id", "分组", "protocol", "document", "rfc_sha256", "chunk_id",
    "chunk_start", "chunk_end", "★ raw_span", "★ resolved_span", "★ span_mode",
    "★ within_chunk", "★ matched_evidence_lines",
    "★ entity（LLM 候选）", "★ normative_subject（LLM 候选）",
    "★ action（LLM 候选）", "★ object（LLM 候选）", "★ strength（LLM 候选）",
    "★ polarity（LLM 候选，★ 原始无此字段）",
    "★ condition（LLM 候选，★ 原始无此字段）",
    "★ exception（LLM 候选，★ 原始无此字段）",
    "★ LLM meaning（★ 生成文本，★ 非 RFC 原文）",
    "★ LLM constraint（★ 生成文本，★ 非 RFC 原文）",
    "★ 推导 polarity（★ 供核对）",
    "★ 锚点行原文（★ 合法可为空）", "★ 锚点行是否空白",
    "★ 证据句（含 entity 的非空行）",
    "★ RFC 原文上下文（锚点 ±6 行）",
]


def _g(p, *keys):
    for k in keys:
        if k in p:
            return p[k]
    for k in p:
        if any(x in k for x in keys):
            return p[k]
    return ""


def _norm(s):
    return str(s or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ⏎ ")


def _row(p, tag):
    _f = p["★ LLM 原始候选字段"]
    _ctx = " ⏎ ".join(f"{c['line']}: {_norm(c['text'])}"
                      for c in p["★ RFC 原文上下文（锚点 ±6 行）"])
    _ev = p["★ 证据句（含 entity 的非空行）"]
    _ev_s = (f"{_ev['line']}: {_norm(_ev['text'])}" if _ev else "")
    _base = [
        p["sample_id"], p["分组"], p["protocol"], p["document"], p["rfc_sha256"],
        p["chunk_id"], p["chunk_start"], p["chunk_end"],
        p["★ raw_span"], p["★ resolved_span"], p["★ span_mode"],
        p["★ within_chunk"], p["★ matched_evidence_lines"],
        _f["entity"], _f["normative_subject"], _f["action"], _f["object"],
        _f["strength"], _f["polarity"] or "", _f["condition"] or "",
        _f["exception"] or "",
        _g(p, "LLM meaning"),
        _g(p, "LLM constraint"),
        _g(p, "推导 polarity"),
        _g(p, "锚点行原文"), p.get("★ 锚点行是否空白"), _ev_s, _ctx,
    ]
    _base = [_norm(_v) if isinstance(_v, str) else _v for _v in _base]
    return _base + [""] * len(BLIND_FIELDS) + [""]


HEAD_A = HEAD_BASE + [f"★ A:{c}" for c, _ in BLIND_FIELDS] + ["★ A:审核者"]
HEAD_B = HEAD_BASE + [f"★ B:{c}" for c, _ in BLIND_FIELDS] + ["★ B:审核者"]

for _tag, _head, _name in (("A", HEAD_A, "N1_盲审标注表_A.csv"),
                           ("B", HEAD_B, "N1_盲审标注表_B.csv")):
    with (DELIV / _name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(_head)
        for p in packs:
            w.writerow(_row(p, _tag))
    print(f"  ★ {_name}：{len(packs)} 行 × {len(_head)} 列")

with (DELIV / "N1_仲裁表.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["sample_id", "分组", "★ A:truth_label", "★ B:truth_label",
                "★ 是否分歧", "★ 仲裁后 truth_label", "★ 仲裁者", "★ 仲裁理由"])
    for p in packs:
        w.writerow([p["sample_id"], p["分组"], "", "", "", "", "", ""])

# ★ 模型状态（★ 单独存放）
_state = []
for cid in _ids:
    _st = None
    for _p in (ROOT / "guard/_out/n1r/n1r_model_state.jsonl",):
        if _p.is_file():
            for l in _p.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    _d = json.loads(l)
                    if _d["sample_id"] == cid:
                        _st = _d.get("★ 模型状态（★ 盲审阶段不可见）")
    _state.append({"sample_id": cid, "分组": "K" if cid in _risk_ids else "R",
                   "★ 模型状态（★ 盲审阶段不可见）": _st})
(OUT / "n1r2_model_state.jsonl").write_text(
    "\n".join(json.dumps(s, ensure_ascii=False) for s in _state) + "\n",
    encoding="utf-8")

(OUT / "n1r2_packs.jsonl").write_text(
    "\n".join(json.dumps(p, ensure_ascii=False) for p in packs) + "\n",
    encoding="utf-8")
print(f"  ★ 模型状态单独存放：{OUT/'n1r2_model_state.jsonl'}")
print(f"  ★ ★ 盲审标签契约（★ **不含** false_*）：{[c for c, _ in BLIND_FIELDS]}")
