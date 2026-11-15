# -*- coding: utf-8 -*-
"""★ N2.2：★ L2 同输入稳定性扩展（★ ≤36 次 API，★ 硬上限执行前设定）。

★ 规模：★ **16 个不同候选各 2 次** + ★ `@1842#2` **额外 4 次** = **36 次**（★ 恰好用满）
★ ★ 修复了 P3-E 的记录落盘 bug（★ `records` 从未 append ⇒ 22 次结果丢失）
★ ★ 本轮**补回**那批丢失的判定
★ 每次保存：完整输入 hash / 响应 hash / 状态 / 字段级结论 / 理由 / token
"""
import collections
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_p079"))
from _lib import (AUDIT06, LEDGER_B1, ROOT as _R, Budget, classify_pair,
                  judge, l2_payload, l2_prompt, load_frozen_orig, load_jsonl,
                  save_json, save_jsonl)
from core.fused.extraction import normative_verify as nv

MAX_ATTEMPTS = 36
MAX_TOKENS = 70_000
PROTO = "sip"

# ★ 用 P0.7 的**最终台账**（★ 含「★ 最终状态」与风险标签）
led = {x["candidate_id"]: x for x in
       load_jsonl(ROOT / "guard/_out/m1_q3/p079/p07_candidate_ledger.jsonl")}
aud = {x["candidate_id"]: x for x in load_jsonl(AUDIT06)}
orig = load_frozen_orig()
_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, cwd=str(ROOT)).stdout.strip()

# ★ 历史已有真实 API 判定的候选（★ 优先纳入以获得更多可比组）
_hist = {json.loads(l)["candidate_id"] for l in
         (ROOT / "guard/_out/n2/n2_history_rows.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}

_MIGRATED = {"rfc3261.txt@1842#2", "rfc3261.txt@12767#1"}
_RISK = ("coreference_subject", "strength_polarity_anomaly", "subject_ne_entity",
         "cross_sentence_object_or_condition")

_cand = [x for x in led.values()
         if x["candidate_id"] in orig
         and x["candidate_id"] in aud
         and (aud[x["candidate_id"]].get("new_quote") or "").strip()]


def _prio(cid):
    x = led[cid]
    _t = set(x.get("★ 风险标签", []))
    _w = 0
    if cid in _MIGRATED:
        _w += 10
    if cid in _hist:
        _w += 4
    if _t & set(_RISK):
        _w += 3
    if x["★ 最终状态"] == "pending_manual_review":
        _w += 2
    if "quote_changed" in _t:
        _w += 1
    return (-_w, cid)


_picks = [x["candidate_id"] for x in sorted(_cand, key=lambda z: _prio(z["candidate_id"]))]
# ★ 16 个不同候选（★ @1842#2 必含）
_16 = []
for c in _picks:
    if c not in _16:
        _16.append(c)
    if len(_16) >= 16:
        break
if "rfc3261.txt@1842#2" not in _16:
    _16[0] = "rfc3261.txt@1842#2"
print(f"  ★ 候选 {len(_16)} 个 × 2 次 + @1842#2 额外 4 次 = "
      f"{len(_16) * 2 + 4} 次（★ 上限 {MAX_ATTEMPTS}）")

# ★ 冻结输入（★ 完整渲染 Prompt 的 sha256）
frozen = []
for cid in _16:
    o = orig[cid]
    a = aud[cid]
    p = l2_payload(o)
    q = a.get("new_quote") or ""
    full = l2_prompt(p, q, nv)
    frozen.append({
        "candidate_id": cid, "stratum": led[cid].get("★ 风险标签", []),
        "payload": p, "quote": q,
        "★ prompt_hash": hashlib.sha256(full.encode("utf-8")).hexdigest(),
        "model": os.environ.get("LLM_MODEL"), "temperature": 0.0,
        "max_tokens": 16000, "code_commit": _commit,
        "★ 原始字段": {k: o.get(k) for k in ("entity", "normative_subject",
                                     "action", "object", "strength",
                                     "polarity", "constraint", "raw_span")},
    })

# ══ 执行 ══
b = Budget("N2.2-稳定性扩展", MAX_ATTEMPTS, MAX_TOKENS, None)
records = []


def _run(f, idx, purpose):
    _r = judge(b, f["payload"], f["quote"], nv)
    _rec = {"candidate_id": f["candidate_id"], "purpose": purpose,
            "repeat_index": idx, "prompt_hash": f["★ prompt_hash"],
            "model": f["model"], "code_commit": _commit,
            "stage": "N2.2", **_r}
    b.record(**{k: v for k, v in _rec.items() if k not in ("stage",)})
    records.append(_rec)          # ★ ★ 修复落盘 bug
    return _rec


for f in frozen:
    for _i in (1, 2):
        if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
            break
        _r = _run(f, _i, "同输入配对")
        print(f"  · {f['candidate_id']:26s} #{_i} ⇒ {str(_r['verdict']):10s} "
              f"(att={_r['api_attempts']} tok={(_r['input_tokens'] or 0) + (_r['output_tokens'] or 0)})")
    if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
        break

# ★ @1842#2 额外 4 次
_h = [f for f in frozen if f["candidate_id"] == "rfc3261.txt@1842#2"]
if _h and not b.stop_reason:
    for _i in (3, 4, 5, 6):
        if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
            break
        _r = _run(_h[0], _i, "★ 历史异常候选额外重复")
        print(f"  ★ @1842#2 #{_i} ⇒ {str(_r['verdict']):10s} "
              f"(att={_r['api_attempts']})")

# ══ 分组比较 ══
_byc = collections.defaultdict(list)
for r in records:
    _byc[r["candidate_id"]].append(r)
pairs = []
for cid, rs in _byc.items():
    _ph = {r["prompt_hash"] for r in rs}
    _v = [r["verdict"] for r in rs]
    _cat = classify_pair(rs[0], rs[1]) if len(rs) >= 2 else "★ 不可比较"
    pairs.append({
        "candidate_id": cid, "n": len(rs), "prompt_hash": sorted(_ph),
        "★ 同输入": len(_ph) == 1, "verdicts": _v,
        "★ 状态一致": (len(set(_v)) == 1) if len(_v) >= 2 else None,
        "★ 理由一致": (len({r.get('reason') for r in rs}) == 1) if len(rs) >= 2 else None,
        "★ 字段级结论": [r.get("field_verdicts") for r in rs],
        "★ 分类": _cat,
        "★ 涉及 confirmed": ("confirmed" in _v),
        "★ tokens": [(r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
                   for r in rs],
        "★ 响应哈希": [r.get("raw_response_sha256") for r in rs],
        "reasons": [r.get("reason") for r in rs],
    })

_incons = [p for p in pairs if p["★ 状态一致"] is False]
_ci = [p for p in _incons if p["★ 涉及 confirmed"]]
_rd = [p for p in pairs if p["★ 状态一致"] and not p["★ 理由一致"]]
print()
print(f"  ★ 可比组 {len(pairs)}｜状态不一致 {len(_incons)}｜涉及 confirmed {len(_ci)}"
      f"｜状态同理由不同 {len(_rd)}")
for p in _incons:
    print(f"     ★★ {p['candidate_id']:26s} {p['verdicts']} ⇒ {p['★ 分类']}")

summary = b.summary()
summary.update({
    "★ 结果": {
        "可比组数": len(pairs),
        "状态完全一致": len([p for p in pairs if p["★ 状态一致"] and p["★ 理由一致"]]),
        "状态一致、理由不同": len(_rd),
        "pending↔rejected": len([p for p in pairs if p["★ 分类"].startswith("C")]),
        "confirmed↔pending": len([p for p in pairs if p["★ 分类"].startswith("D")]),
        "confirmed↔rejected": len([p for p in pairs if p["★ 分类"].startswith("E")]),
        "★ 状态不一致合计": len(_incons),
        "★ 涉及 confirmed 的不一致": len(_ci),
        "★ 不一致明细": [{"candidate_id": p["candidate_id"], "verdicts": p["verdicts"],
                    "reasons": p["reasons"]} for p in _incons],
    },
    "★ 限制": ["★ **16 对仅用于风险诊断**；★ **不得据此证明真实错误率 < 5%**",
             "★ 本轮补回了 P3-E 丢失的逐条记录（★ 该批 22 次结果已重新采集）"],
})
save_jsonl(ROOT / "guard/_out/n2/n2_records.jsonl", records)
save_jsonl(ROOT / "guard/_out/n2/n2_pairs.jsonl", pairs)
save_json(ROOT / "guard/_out/n2/n2_summary.json", summary)
save_json(ROOT / "guard/_out/n2/n2_frozen.json", frozen)
print(f"\n  ★ API {b.attempts}/{MAX_ATTEMPTS}｜token {b.in_tok + b.out_tok:,}")
print(f"  ⇒ {ROOT/'guard/_out/n2/n2_summary.json'}")
