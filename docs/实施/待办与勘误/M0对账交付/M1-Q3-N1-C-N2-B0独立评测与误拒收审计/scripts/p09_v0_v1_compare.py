# -*- coding: utf-8 -*-
"""★ N2-B0-R：★ **V0 / V1 并行逐候选对账**（★ 32 条开发样本，★ 不调 LLM）。

★ ★ V0（已冻结）与 V1（修正版）**并行运行**，★ **不覆盖 V0**。
★ 输出：每条候选的 V0/V1 三态、原文明证、变更前后原因、反证是否指向同一命题、
★       是否仍需 LLM、是否待人工审核、是否具备正式发布资格（★ 默认 false）
"""
import collections
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
                              UNCERTAIN as V1_U,
                              semantic_support_tristate_v1)

OUTD = ROOT / "guard/_out/n1c"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

rows0 = list(csv.DictReader((DELIV / "N2-B0_影子状态32条对账.csv")
                             .read_text(encoding="utf-8").splitlines()))
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}
FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = {**it,
                                                     "protocol": b["protocol"],
                                                     "document": b["document"]}
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

rows = []
for r0 in rows0:
    cid = r0["candidate_id"]
    _sp = spans.get(cid)
    _o = FR.get(cid, {})
    if _sp:
        _L = _lines(_sp["★ protocol"], _sp["★ document"])
        _rs = _sp["resolved_span"]
        _quote = "\n".join(_L[_rs - 1:_rs + 2])
    else:
        _L, _rs, _quote = None, None, ""
    _payload = {"action": _o.get("action") or "",
                "object": _o.get("object") or "",
                "strength": _o.get("strength") or ""}
    # ★ V0（★ 冻结版，★ 逐条重跑以保证可复算）
    _v0, _r0, _s0 = semantic_support_tristate(
        _quote, _payload["action"], _payload["object"],
        strength=_payload["strength"])
    # ★ V1（★ 修正版）
    _v1, _r1, _d1 = semantic_support_tristate_v1(
        quote=_quote, action=_payload["action"], object_=_payload["object"],
        strength=_payload["strength"],
        subject=_o.get("normative_subject") or "",
        constraint=_o.get("constraint") or "",
        lines=_L, anchor=_rs)
    _route0 = _ROUTE[_v0]
    _route1 = _ROUTE1[_v1]
    rows.append({
        "candidate_id": cid, "分组": r0["分组"],
        "★ 原版状态（历史）": r0["★ 原版状态"],
        "★ V0 三态": _v0, "★ V0 路由": _route0, "★ V0 reason": _r0,
        "★ V0 逐字段三态": {k: v["state"] for k, v in _s0.items()},
        "★ V1 三态": _v1, "★ V1 路由": _route1, "★ V1 reason": _r1,
        "★ V1 命题对应": json.dumps(_d1.get("★ 命题对应"), ensure_ascii=False),
        "★ V1 反证句": _d1.get("★ 反证句"),
        "★ V1 反证行": _d1.get("★ 反证行"),
        "★ V1 证据跨度": json.dumps(_d1.get("★ 证据跨度"), ensure_ascii=False),
        "★ V1 候选字段自相矛盾": _d1.get("★ 候选字段自相矛盾"),
        "★ 是否由 contradicted 改为 uncertain/supported": (
            _v0 == V0_C and _v1 != V1_C),
        "★ 是否仍需 LLM": ("是" if _route1 == "★ routed_to_LLM" else "否"),
        "★ 是否待人工审核": ("是" if _route1 == "★ pending" else "否"),
        "★ 是否具备正式发布资格": "★ False（★ 本轮全部保持 false）",
        "★ 人工真值": r0["★ 人工真值"],
        "★ 第二层": r0["★ 第二层"],
        "★ 原始 evidence（锚点行原文）": (r0.get("★ 原文证据（锚点行原文）")
                                  or (_L[_rs - 1] if (_L and _rs) else "")),
    })


def _stat(key_route, key_truth="★ 人工真值"):
    _c = collections.defaultdict(collections.Counter)
    for r in rows:
        _c[r[key_route]][r[key_truth]] += 1
    _out = {}
    for _route, _cnt in _c.items():
        _ok = _cnt.get("valid_confirmed", 0)
        _no = sum(v for k, v in _cnt.items() if k != "valid_confirmed")
        _out[_route] = {"合计": sum(_cnt.values()), "★ 人工成立": _ok,
                        "★ 人工不成立": _no}
    return _out


_s0, _s1 = _stat("★ V0 路由"), _stat("★ V1 路由")
print("  ★ V0 统计：", json.dumps(_s0, ensure_ascii=False))
print("  ★ V1 统计：", json.dumps(_s1, ensure_ascii=False))

# ★ 变化明细
_chg = [r for r in rows if r["★ V0 路由"] != r["★ V1 路由"]]
print(f"  ★ 路由变化 {len(_chg)} 条：")
for r in _chg:
    print(f"      {r['candidate_id'][:26]:28s} {r['★ 原版状态（历史）']:10s}"
          f" V0 {r['★ V0 三态']:13s} → V1 {r['★ V1 三态']:13s}"
          f"｜真值={r['★ 人工真值']}")

# ★ 三条案例的 V1 结果
print()
print("  ★ ★ 三条误拒案例的 V1 结果：")
for _cid in ("rfc2326.txt@2030#5", "rfc5321.txt@5226#1", "rfc5321.txt@5226#2"):
    for r in rows:
        if r["candidate_id"] == _cid:
            print(f"      {_cid}")
            print(f"          V0={r['★ V0 三态']}（{r['★ V0 路由']}）｜"
                  f"V1={r['★ V1 三态']}（{r['★ V1 路由']}）")
            print(f"          V1 reason={r['★ V1 reason'][:120]}")
            print(f"          V1 命题对应={r['★ V1 命题对应']}")
            print(f"          V1 反证行={r['★ V1 反证行']}｜反证句={str(r['★ V1 反证句'])[:90]}")
            print(f"          ★ 字段自相矛盾={r['★ V1 候选字段自相矛盾']}")

with (DELIV / "N2-B0-R_V0_V1逐候选对照.csv").open("w", newline="",
                                             encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

summary = {
    "★ V0 统计（★ 冻结版）": _s0,
    "★ V1 统计（★ 修正版）": _s1,
    "★ 路由变化条数": len(_chg),
    "★ 路由变化明细": [{"candidate_id": r["candidate_id"],
                   "原版": r["★ 原版状态（历史）"],
                   "V0": r["★ V0 三态"], "V1": r["★ V1 三态"],
                   "★ 人工真值": r["★ 人工真值"],
                   "V1 reason": r["★ V1 reason"][:160]} for r in _chg],
    "★ 三条误拒案例 V1 结果": [
        {"candidate_id": r["candidate_id"], "V0": r["★ V0 三态"],
         "V1": r["★ V1 三态"], "V1 路由": r["★ V1 路由"],
         "V1 reason": r["★ V1 reason"],
         "V1 命题对应": r["★ V1 命题对应"],
         "V1 反证行": r["★ V1 反证行"],
         "V1 反证句": r["★ V1 反证句"],
         "★ 字段自相矛盾": r["★ V1 候选字段自相矛盾"],
         "★ 人工真值": r["★ 人工真值"]}
        for r in rows if r["candidate_id"] in
        ("rfc2326.txt@2030#5", "rfc5321.txt@5226#1", "rfc5321.txt@5226#2")],
}
(OUTD / "n2b0r_v0_v1.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n2b0r_v0_v1.json'}")
print(f"  ⇒ {DELIV/'N2-B0-R_V0_V1逐候选对照.csv'}")
