# -*- coding: utf-8 -*-
"""★ P0.7：★ **按 prompt_hash 严格分组**重算同输入稳定性（★ 0 次 API）。

★ ★ 关键修正：`@1842#2` 的 6 次判定跨 3 个 prompt_hash ⇒ ⇒ **跨批次不可直接合并**
⇒ ⇒ ★ **只有同一 prompt_hash 内的多次判定才构成「同输入」样本**
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import OUTROOT, classify_pair, load_jsonl, save_json, save_jsonl

P07B = OUTROOT.parent / "p07b"
P3S = OUTROOT.parent / "p07b5"

srcs = [("P3-E", load_jsonl(OUTROOT / "p07_a2_p3e_records.jsonl")),
        ("P3-S", load_jsonl(P3S / "p3s_records.jsonl")),
        ("B4", load_jsonl(P07B / "b4_records.jsonl"))]

recs = []
for _src, _rs in srcs:
    for r in _rs:
        if not r.get("verdict") or r.get("error"):
            continue
        if r.get("api_attempts", 0) <= 0:
            continue            # ★ 确定性短路 ⇒ 无 LLM 输出 ⇒ 不计入
        recs.append({
            "source": _src, "candidate_id": r.get("candidate_id"),
            "prompt_hash": r.get("prompt_hash"), "verdict": r.get("verdict"),
            "reason": r.get("reason"), "field_verdicts": r.get("field_verdicts"),
            "tokens": (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0),
            "resp_sha": r.get("raw_response_sha256"),
            "stratum": r.get("stratum"),
        })

# ★ 按 (candidate_id, prompt_hash) 分组 ⇒ ★ 这才是「同输入」
groups = collections.defaultdict(list)
for r in recs:
    groups[(r["candidate_id"], r["prompt_hash"])].append(r)

rows = []
for (cid, ph), rs in sorted(groups.items()):
    _v = [r["verdict"] for r in rs]
    _cat = classify_pair(rs[0], rs[1]) if len(rs) >= 2 else "★ 不可比较"
    rows.append({
        "candidate_id": cid, "prompt_hash": ph, "n": len(rs),
        "sources": [r["source"] for r in rs],
        "verdicts": _v,
        "★ 状态一致": (len(set(_v)) == 1) if len(_v) >= 2 else None,
        "★ 理由一致": (len({r["reason"] for r in rs}) == 1) if len(rs) >= 2 else None,
        "★ 分类": _cat,
        "★ 涉及 confirmed": ("confirmed" in _v),
        "★ tokens": [r["tokens"] for r in rs],
        "★ 响应哈希相同": (len({r["resp_sha"] for r in rs}) == 1) if rs else None,
        "reasons": [r["reason"] for r in rs],
    })

_comparable = [r for r in rows if r["★ 状态一致"] is not None]
_incons = [r for r in _comparable if r["★ 状态一致"] is False]
_ci = [r for r in _incons if r["★ 涉及 confirmed"]]
_reason_diff = [r for r in _comparable if r["★ 状态一致"] and not r["★ 理由一致"]]

print(f"  ★ 真实 API 判定记录 = {len(recs)}")
print(f"  ★ (候选, prompt_hash) 分组 = {len(rows)}｜★ 可比较（同 ph ≥2 次）= {len(_comparable)}")
print(f"  ★ 状态不一致 = {len(_incons)}｜★ 涉及 confirmed = {len(_ci)}"
      f"｜★ 状态同但理由不同 = {len(_reason_diff)}")
print()
for r in _incons:
    print(f"  ★★ {r['candidate_id']:24s} ph={r['prompt_hash'][:12]} "
          f"{r['verdicts']} ⇒ {r['★ 分类']}")
print()
print("  ★ 同输入（同一 ph）内的全部组：")
for r in _comparable:
    print(f"     {r['candidate_id']:24s} ph={r['prompt_hash'][:10]} n={r['n']} "
          f"{r['verdicts']} ⇒ {r['★ 分类']}")

summary = {
    "★ 口径": {
        "真实 API 判定记录": len(recs),
        "(候选,prompt_hash) 分组": len(rows),
        "★ 同输入可比较对数": len(_comparable),
        "★ 判定顺序": "★ **只有同一 prompt_hash 内的多次判定才计「同输入」**",
    },
    "★ 结果": {
        "状态完全一致": len([r for r in _comparable if r["★ 状态一致"]
                          and r["★ 理由一致"]]),
        "状态一致、理由不同": len(_reason_diff),
        "pending↔rejected": len([r for r in _incons if r["★ 分类"].startswith("C")]),
        "confirmed↔pending": len([r for r in _incons if r["★ 分类"].startswith("D")]),
        "confirmed↔rejected": len([r for r in _incons if r["★ 分类"].startswith("E")]),
        "★ 状态不一致合计": len(_incons),
        "★ 涉及 confirmed 的不一致": len(_ci),
        "★ 不一致明细": [{"candidate_id": r["candidate_id"],
                    "prompt_hash": r["prompt_hash"], "verdicts": r["verdicts"],
                    "reasons": r["reasons"], "sources": r["sources"]}
                   for r in _incons],
    },
    "★ 限制": [
        "★ **不得据此给出总体错误率**（★ 分层抽样，★ 非随机）",
        "★ 判定样本含跨批次记录 ⇒ ★ 已在 ph 内分组",
    ],
}
save_jsonl(OUTROOT / "p07_l2_stability_pairs.jsonl", rows)
save_json(OUTROOT / "p07_a2c_stability_summary.json", summary)
print(f"\n  ⇒ {OUTROOT/'p07_l2_stability_pairs.jsonl'}")
