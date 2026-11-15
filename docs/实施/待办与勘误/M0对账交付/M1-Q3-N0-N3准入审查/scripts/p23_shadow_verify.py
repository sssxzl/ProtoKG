# -*- coding: utf-8 -*-
"""★ N2.4：★ 确认防护的**影子验证**（★ 不改正式发布策略，★ 只算「若启用会怎样」）。"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_n2"))
from p22_confirm_guard_design import confirm_guard, deterministic_field_evidence

OUT = ROOT / "guard/_out/n2"
P079 = ROOT / "guard/_out/m1_q3/p079"
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

pairs = [json.loads(l) for l in (OUT / "n2_pairs.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
led = {x["candidate_id"]: x for x in
       [json.loads(l) for l in
        (P079 / "p07_candidate_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]}
aud = {json.loads(l)["candidate_id"]: json.loads(l) for l in
       (ROOT / "guard/_out/m1_q3/p06/p06_audit.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()}
orig = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        orig[f"{b['document']}@{b['chunk_start']}#{i}"] = it

# ★ ① 有 confirmed 分歧的候选（★ 防护的隔离集合）
_instable = {p["candidate_id"] for p in pairs
             if p["★ 状态一致"] is False and p["★ 涉及 confirmed"]}
print(f"  ★ confirmed 分歧候选集合（{len(_instable)}）：{sorted(_instable)}")

# ★ ② 逐候选影子判定（★ 以其 observed verdict 为 L2 输入）
rows = []
for p in pairs:
    cid = p["candidate_id"]
    o = orig.get(cid, {})
    payload = {"subject": o.get("normative_subject") or o.get("entity") or "",
               "action": o.get("action") or "", "object": o.get("object") or "",
               "strength": o.get("strength") or "", "polarity": o.get("polarity") or "",
               "condition": o.get("constraint") or ""}
    q = aud.get(cid, {}).get("new_quote") or ""
    _att = (led.get(cid, {}).get("★ 归属状态") or "explicit_subject")
    _l2 = p["verdicts"][0] if p["verdicts"] else None
    _g = confirm_guard(payload, q, _l2, attribution_status=_att,
                       instability_candidates=_instable,
                       human_labeled=None)      # ★ 本轮尚无人工标签
    rows.append({
        "candidate_id": cid, "observed_l2": _l2, "verdicts": p["verdicts"],
        "attribution": _att,
        "★ 有 confirmed 分歧": cid in _instable,
        "★ 防护 allow_confirm": _g["allow_confirm"],
        "★ 防护理由": _g["reason"],
        "★ 确定性字段证据": _g["evidence"],
    })

# ★ ③ 统计
_conf = [r for r in rows if r["observed_l2"] == "confirmed"]
_blocked = [r for r in _conf if not r["★ 防护 allow_confirm"]]
_by_reason = collections.Counter(r["★ 防护理由"].split("（")[0][:40]
                                 for r in _blocked)
print()
print(f"  ★ observed confirmed 的候选 = {len(_conf)}")
print(f"  ★ 防护会**阻止**的 = {len(_blocked)}")
print(f"  ★ 阻止原因分布：")
for k, v in _by_reason.most_common():
    print(f"      {k:44s} {v}")
print()
print("  ★ 逐条：")
for r in rows:
    if r["observed_l2"] == "confirmed":
        print(f"      {r['candidate_id']:26s} L2={r['observed_l2']:9s} "
              f"分歧={r['★ 有 confirmed 分歧']!s:5s} ⇒ 允许确认={r['★ 防护 allow_confirm']}")
        print(f"          {r['★ 防护理由'][:110]}")

# ★ ④ 影子运行对正式产物的影响 = 0（★ 未接入生产路径）
(OUT / "n2_confirm_guard_shadow.json").write_text(json.dumps({
    "★ confirmed 分歧候选": sorted(_instable),
    "★ 逐候选影子判定": rows,
    "★ 统计": {
        "observed_confirmed": len(_conf),
        "★ 防护阻止数": len(_blocked),
        "★ 阻止原因分布": dict(_by_reason),
        "★ 对正式产物的影响": 0,
        "★ 说明": "★ 本模块**未接入生产路径**（★ 只影子运行）⇒ ★ 正式中枢/种子不变",
    },
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUT/'n2_confirm_guard_shadow.json'}")
