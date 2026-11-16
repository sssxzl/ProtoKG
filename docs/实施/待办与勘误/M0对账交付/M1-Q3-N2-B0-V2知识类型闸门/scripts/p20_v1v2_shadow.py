# -*- coding: utf-8 -*-
"""★ N2-B0-V2：★ **V1 / V2 联合影子逐候选对照**（★ 开发性与诊断性比较）。

★ ★ **重要**：★ N1-B（32 条）与 N1-C（50 条）**均已用于 V2 设计** ⇒ ★ **不属于 V2 的独立验证**
★ ★ V0 / V1 **不修改**；★ **0 次 LLM**
"""
import collections
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c"))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2"))
from core.fused.extraction import normative_verify as nv
from n2b0_tristate import (CONTRADICTED as V0_C, SUPPORTED as V0_S,
                           UNCERTAIN as V0_U, semantic_support_tristate)
from n2b0_tristate_v1 import (CONTRADICTED as V1_C, SUPPORTED as V1_S,
                              UNCERTAIN as V1_U, semantic_support_tristate_v1)
import v2_knowledge_gate as V2

OUTD = ROOT / "guard/_out/_n1c_v2"
OUTD.mkdir(parents=True, exist_ok=True)
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N2-B0-V2知识类型闸门"
DELIV.mkdir(parents=True, exist_ok=True)
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
N1C = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计")

FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = {**it,
                                                     "protocol": b["protocol"],
                                                     "document": b["document"]}
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}
_docs = {}


def _lines(proto, doc):
    _k = (proto, doc)
    if _k not in _docs:
        _p = ROOT / f"kb/{proto}/spec/{doc}"
        _docs[_k] = {"lines": _p.read_text(encoding="utf-8", errors="replace")
                     .replace("\r\n", "\n").split("\n"),
                     "sha": hashlib.sha256(_p.read_bytes()).hexdigest()}
    return _docs[_k]


# ★ ★ 人工真值（★ N1-B 32 条 + N1-C 50 条；★ V2 设计已用过 ⇒ 非独立验证）
_truth = {}
for _l in (N1B / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines():
    if _l.strip():
        _d = json.loads(_l)
        _truth[_d["sample_id"]] = {"batch": "N1-B(开发集)",
                                  "truth": _d["★ 第一层 规范义务存在性"],
                                  "support": _d["★ 人工 evidence_support"]}
for _l in (N1C / "N1-C_V0_V1逐候选对照.csv").read_text(encoding="utf-8").splitlines()[1:]:
    _d = next(csv.DictReader([_l])) if False else None
for _r in csv.DictReader((N1C / "N1-C_V0_V1逐候选对照.csv").open(encoding="utf-8")):
    _truth[_r["candidate_id"]] = {"batch": "N1-C(独立集·已用于V2设计)",
                                  "truth": _r["★ 人工 A truth_label"],
                                  "support": _r["★ 人工 A evidence_support"]}

rows = []
for cid, tinfo in sorted(_truth.items()):
    _sp = spans.get(cid)
    _o = FR.get(cid, {})
    if not _sp:
        continue
    _d = _lines(_sp["★ protocol"], _sp["★ document"])
    _L = _d["lines"]
    _rs = _sp["resolved_span"]
    _quote = "\n".join(_L[_rs - 1:_rs + 2])
    _payload = {"action": _o.get("action") or "",
                "object": _o.get("object") or "",
                "strength": _o.get("strength") or ""}
    # ── V0（冻结）──
    _v0, _r0, _s0 = semantic_support_tristate(
        _quote, _payload["action"], _payload["object"],
        strength=_payload["strength"])
    # ── V1（冻结）──
    _v1, _r1, _d1 = semantic_support_tristate_v1(
        quote=_quote, action=_payload["action"], object_=_payload["object"],
        strength=_payload["strength"], subject=_o.get("normative_subject") or "",
        constraint=_o.get("constraint") or "", lines=_L, anchor=_rs)
    # ── V2（新增）──
    _g = V2.classify_candidate(
        candidate_id=cid, source_doc=_sp["★ document"],
        source_sha256=_d["sha"], source_span=_rs, lines=_L, anchor=_rs,
        entity=_sp["★ entity"], action=_payload["action"],
        object_=_payload["object"], strength=_payload["strength"],
        subject=_o.get("normative_subject") or "",
        constraint=_o.get("constraint") or "")
    _route0 = {V0_C: "rejected", V0_U: "pending", V0_S: "routed_to_LLM"}[_v0]
    _route1 = {V1_C: "rejected", V1_U: "pending", V1_S: "routed_to_LLM"}[_v1]
    # ── 联合路径 A：V1 单独 ──
    _A = _route1
    # ── 联合路径 B：V2 路由 + V1 三态 ──
    if _g["route"] == V2.ROUTE_RULE:
        _B = _route1
    elif _g["route"] == V2.ROUTE_REVIEW:
        _B = "pending"
    else:
        _B = "routed_to_structured"      # ★ 走既有结构化通道（★ 非规则通道）
    rows.append({
        "candidate_id": cid, "批次": tinfo["batch"],
        "protocol": _sp["★ protocol"], "document": _sp["★ document"],
        "chunk_id": f"{_sp['★ document']}@{_sp['chunk_start']}",
        "★ 人工真值": tinfo["truth"], "★ 人工 evidence_support": tinfo["support"],
        "★ V0 三态": _v0, "★ V0 路由": _route0,
        "★ V1 三态": _v1, "★ V1 路由": _route1, "★ V1 reason": _r1,
        "★ V2 source_kind": _g["source_kind"],
        "★ V2 knowledge_kind": _g["knowledge_kind"],
        "★ V2 rule_eligibility": _g["rule_eligibility"],
        "★ V2 route": _g["route"],
        "★ V2 reason": _g["reason"],
        "★ V2 证据跨度": json.dumps(_g["evidence_span"], ensure_ascii=False),
        "★ V2 复用既有 aspect": str(_g["★ 复用既有 aspect 通道"]),
        "★ 联合A（V1 单独）": _A,
        "★ 联合B（V2+V1）": _B,
        "★ B 是否改变 A": _A != _B,
    })

with (DELIV / "V2_V1联合影子逐候选对照.csv").open("w", newline="",
                                              encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
(OUTD / "v2_v1_joint.json").write_text(
    json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

# ══ 统计 ══
def _stats(key):
    _c = collections.Counter((r[key], r["★ 人工真值"] == "valid_confirmed")
                             for r in rows)
    _out = {}
    for (rt, v), n in _c.items():
        _out.setdefault(rt, {})["有效" if v else "无效"] = n
    for rt in _out:
        _out[rt]["合计"] = sum(_out[rt].values())
    return _out


_s = {"★ 联合A（V1 单独）": _stats("★ 联合A（V1 单独）"),
      "★ 联合B（V2+V1）": _stats("★ 联合B（V2+V1）"),
      "★ V2 route 分布": dict(collections.Counter(r["★ V2 route"] for r in rows)),
      "★ V2 knowledge_kind 分布": dict(collections.Counter(
          r["★ V2 knowledge_kind"] for r in rows)),
      "★ V2 rule_eligibility 分布": dict(collections.Counter(
          r["★ V2 rule_eligibility"] for r in rows))}
print("  ★ 联合A（V1 单独）：", json.dumps(_s["★ 联合A（V1 单独）"], ensure_ascii=False))
print("  ★ 联合B（V2+V1）：", json.dumps(_s["★ 联合B（V2+V1）"], ensure_ascii=False))
print("  ★ V2 route:", json.dumps(_s["★ V2 route 分布"], ensure_ascii=False))
print("  ★ V2 knowledge_kind:", json.dumps(_s["★ V2 knowledge_kind 分布"], ensure_ascii=False))
(OUTD / "v2_joint_stats.json").write_text(
    json.dumps(_s, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {DELIV/'V2_V1联合影子逐候选对照.csv'}")
