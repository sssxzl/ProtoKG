# -*- coding: utf-8 -*-
"""★ N1-C 阶段：★ 为 **N1-C 全部 50 条**计算 V0 / V1 三态与路由（★ 冻结代码，★ 不改判据）。

★ ★ 与 N2-B0-R 开发集（32 条）的脚本**同一套判据**（★ `n2b0_tristate` / `n2b0_tristate_v1`）
★ ★ **不调用 LLM**；★ **不修改任何判据或指标定义**
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c"))
from core.fused.extraction import normative_verify as nv
from n2b0_tristate import (CONTRADICTED as V0_C, SUPPORTED as V0_S,
                           UNCERTAIN as V0_U, semantic_support_tristate)
from n2b0_tristate_v1 import (CONTRADICTED as V1_C, SUPPORTED as V1_S,
                              UNCERTAIN as V1_U, semantic_support_tristate_v1)

OUTD = ROOT / "guard/_out/_n1c"
FIXED = OUTD / "work_n1c_fixed"
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"

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
        _docs[_k] = _p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")
    return _docs[_k]


_ROUTE = {V0_C: "★ rejected", V0_U: "★ pending", V0_S: "★ routed_to_LLM"}
_ROUTE1 = {V1_C: "★ rejected", V1_U: "★ pending", V1_S: "★ routed_to_LLM"}

_A = {r["sample_id"]: r for r in
      csv.DictReader((FIXED / "N1-C_盲审标注表_A.csv")
                     .read_text(encoding="utf-8").splitlines())}

rows = []
for _sid, _ar in sorted(_A.items()):
    _sp = spans.get(_sid)
    _o = FR.get(_sid, {})
    if _sp:
        _L = _lines(_sp["★ protocol"], _sp["★ document"])
        _rs = _sp["resolved_span"]
        _quote = "\n".join(_L[_rs - 1:_rs + 2])
    else:
        _L, _rs, _quote = None, None, ""
    _payload = {"action": _o.get("action") or "",
                "object": _o.get("object") or "",
                "strength": _o.get("strength") or ""}
    _v0, _r0, _s0 = semantic_support_tristate(
        _quote, _payload["action"], _payload["object"],
        strength=_payload["strength"])
    _v1, _r1, _d1 = semantic_support_tristate_v1(
        quote=_quote, action=_payload["action"], object_=_payload["object"],
        strength=_payload["strength"],
        subject=_o.get("normative_subject") or "",
        constraint=_o.get("constraint") or "",
        lines=_L, anchor=_rs)
    rows.append({
        "candidate_id": _sid, "protocol": _ar.get("protocol", ""),
        "document": _ar.get("document", ""), "chunk_id": _ar.get("chunk_id", ""),
        "★ 人工 A truth_label": (_ar.get("★ A:truth_label") or "").strip(),
        "★ 人工 B truth_label": "",
        "★ 人工 A evidence_support": (_ar.get("★ A:evidence_support") or "").strip(),
        "★ V0 三态": _v0, "★ V0 路由": _ROUTE[_v0], "★ V0 reason": _r0,
        "★ V0 逐字段三态": json.dumps({k: v["state"] for k, v in _s0.items()},
                                     ensure_ascii=False),
        "★ V1 三态": _v1, "★ V1 路由": _ROUTE1[_v1], "★ V1 reason": _r1,
        "★ V1 命题对应": json.dumps(_d1.get("★ 命题对应"), ensure_ascii=False),
        "★ V1 反证句": _d1.get("★ 反证句"),
        "★ V1 反证行": _d1.get("★ 反证行"),
        "★ V1 证据跨度": json.dumps(_d1.get("★ 证据跨度"), ensure_ascii=False),
        "★ V1 字段自相矛盾": _d1.get("★ 候选字段自相矛盾"),
        "★ 原始 evidence（锚点行原文）": (_L[_rs - 1] if (_L and _rs) else ""),
    })

# ★ 补 B 列与仲裁
_B = {r["sample_id"]: r for r in
      csv.DictReader((FIXED / "N1-C_盲审标注表_B.csv")
                     .read_text(encoding="utf-8").splitlines())}
_AR = {r["sample_id"]: r for r in
       csv.DictReader((FIXED / "N1-C_仲裁表.csv")
                      .read_text(encoding="utf-8").splitlines())}
for _r in rows:
    _sid = _r["candidate_id"]
    _r["★ 人工 B truth_label"] = (_B[_sid].get("★ B:truth_label") or "").strip()
    _r["★ 人工 B evidence_support"] = (_B[_sid].get("★ B:evidence_support") or "").strip()
    _r["★ 仲裁 truth_label"] = (_AR[_sid].get("★ 仲裁后 truth_label") or "").strip()
    _r["★ 仲裁者 ID"] = (_AR[_sid].get("★ 仲裁者 ID（★ 匿名编号）") or "").strip()
    _r["★ 仲裁日期"] = (_AR[_sid].get("★ 审核日期") or "").strip()
    _r["★ 是否仍需 LLM"] = ("是" if _r["★ V1 路由"] == "★ routed_to_LLM" else "否")
    _r["★ 是否待人工审核"] = ("是" if _r["★ V1 路由"] == "★ pending" else "否")
    _r["★ 是否具备正式发布资格"] = "★ False（★ 本轮全部保持 false）"

with (DELIV / "N1-C_V0_V1逐候选对照.csv").open("w", newline="",
                                            encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
(OUTD / "n1c_v0v1.json").write_text(
    json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

_c0 = collections.Counter(r["★ V0 路由"] for r in rows)
_c1 = collections.Counter(r["★ V1 路由"] for r in rows)
print(f"  ★ N1-C 50 条 V0 路由：{dict(_c0)}")
print(f"  ★ N1-C 50 条 V1 路由：{dict(_c1)}")
print(f"  ⇒ {DELIV/'N1-C_V0_V1逐候选对照.csv'}")
