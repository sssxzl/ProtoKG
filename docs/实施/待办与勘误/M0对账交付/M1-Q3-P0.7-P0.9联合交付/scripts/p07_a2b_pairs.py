# -*- coding: utf-8 -*-
"""★ P0.7：★ 从 P3-E/P3-S/B4 的**已有记录**重算稳定性配对（★ 0 次 API）。

★ 修正：P3-E 脚本的 `★ 分类` 为空（★ record 字段名不匹配）⇒ ⇒ 此处按正确口径重算。
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

p3e = load_jsonl(OUTROOT / "p07_a2_p3e_records.jsonl")
p3s = load_jsonl(P3S / "p3s_records.jsonl")
b4 = load_jsonl(P07B / "b4_records.jsonl")

# ★ 统一：把三批记录归一（★ 字段名一致化）
def norm(r, src):
    return {
        "source": src,
        "candidate_id": r.get("candidate_id"),
        "stratum": r.get("stratum"),
        "prompt_hash": r.get("prompt_hash"),
        "verdict": r.get("verdict"),
        "reason": r.get("reason"),
        "field_verdicts": r.get("field_verdicts"),
        "api_attempts": r.get("api_attempts", 0),
        "tokens": (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0),
        "resp_sha": r.get("raw_response_sha256"),
        "error": r.get("error"),
    }


allrecs = ([norm(r, "P3-E") for r in p3e]
            + [norm(r, "P3-S") for r in p3s]
            + [norm(r, "B4") for r in b4])

_byc = collections.defaultdict(list)
for r in allrecs:
    _byc[r["candidate_id"]].append(r)

pairs = []
for cid, rs in sorted(_byc.items()):
    _valid = [r for r in rs if r.get("verdict") and not r.get("error")
              and r.get("api_attempts", 0) > 0]
    _phs = {r["prompt_hash"] for r in _valid}
    _v = [r["verdict"] for r in _valid]
    # ★ 同输入判定：★ 仅当 prompt_hash 唯一时可比
    if len(_phs) == 1 and len(_valid) >= 2:
        _cat = classify_pair(_valid[0], _valid[1])
    elif len(_valid) >= 2:
        _cat = "★ 输入不同（★ prompt_hash 不唯一）"
    else:
        _cat = "★ 不可比较"
    _status_same = (len(set(_v)) == 1) if len(_v) >= 2 else None
    pairs.append({
        "candidate_id": cid,
        "★ prompt_hash 集合": sorted(_phs),
        "★ 同输入": (len(_phs) == 1),
        "n_valid_real_api": len(_valid),
        "来源": [r["source"] for r in _valid],
        "verdicts": _v,
        "★ 状态一致": _status_same,
        "★ 状态分布": dict(collections.Counter(_v)),
        "★ 分类": _cat,
        "★ 涉及 confirmed": ("confirmed" in _v),
        "★ tokens": [r["tokens"] for r in _valid],
        "★ 响应哈希": [r["resp_sha"] for r in _valid],
        "reasons": [r["reason"] for r in _valid],
    })

_c = collections.Counter(p["★ 分类"] for p in pairs)
_incons = [p for p in pairs if p["★ 状态一致"] is False]
_ci = [p for p in _incons if p["★ 涉及 confirmed"]]
_same_in = [p for p in pairs if p["★ 同输入"] and p["★ 状态一致"] is not None]
_same_in_incons = [p for p in _same_in if p["★ 状态一致"] is False]

print(f"  ★ 涉及候选 = {len(pairs)}｜分类分布 = {dict(_c)}")
print(f"  ★ 状态不一致 = {len(_incons)}｜★ 涉及 confirmed = {len(_ci)}")
print(f"  ★ 同输入可比 = {len(_same_in)}｜★ 同输入内不一致 = {len(_same_in_incons)}")
for p in _incons:
    print(f"    · {p['candidate_id']:24s} {p['verdicts']} "
          f"★同输入={p['★ 同输入']} ph={[x[:10] for x in p['★ prompt_hash 集合']]}")

summary = {
    "★ 汇总": {
        "候选数": len(pairs),
        "分类分布": dict(_c),
        "状态不一致": len(_incons),
        "涉及 confirmed 的不一致": len(_ci),
        "同输入可比对数": len(_same_in),
        "同输入内状态不一致": len(_same_in_incons),
        "★ 不一致明细": [{"candidate_id": p["candidate_id"],
                    "verdicts": p["verdicts"], "sources": p["来源"],
                    "same_input": p["★ 同输入"]} for p in _incons],
    },
    "★ 重要限制": [
        "★ 本汇总含 B4/P3-S/P3-E 三批（★ **同一 prompt_hash 跨批次**才计「同输入」）",
        "★ **不得据此给出总体错误率**（★ 样本为分层抽样，★ 非随机）",
        "★ 分类为空的历史问题已在本脚本按正确口径重算",
    ],
}
save_jsonl(OUTROOT / "p07_l2_stability_pairs.jsonl", pairs)
save_json(OUTROOT / "p07_a2b_stability_summary.json", summary)
print(f"\n  ⇒ {OUTROOT/'p07_l2_stability_pairs.jsonl'}")
