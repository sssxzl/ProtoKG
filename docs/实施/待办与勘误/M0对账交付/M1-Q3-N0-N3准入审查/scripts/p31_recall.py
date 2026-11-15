# -*- coding: utf-8 -*-
"""★ N3 第二类补齐：★ 对 18 条 `recoverable_by_recall` 候选追加 L2 复判。

★ 预算：**API ≤ 64**｜token ≤ 120,000（★ 执行前设定，★ 达限即停）
★ 原则：★ **只对第二类（可重新调用补齐）追加**；★ 不可恢复与待人工的不调用
★ ★ **不把无法恢复历史对照的数据伪装成完整配对复判**
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
from _lib import (AUDIT06, ROOT as _R, Budget, judge, l2_payload, l2_prompt,
                  load_frozen_orig, load_jsonl, save_json, save_jsonl)
from core.fused.extraction import normative_verify as nv

MAX_ATTEMPTS = 64
MAX_TOKENS = 120_000

OUT = ROOT / "guard/_out/n3"
attrib = [json.loads(l) for l in
          (OUT / "n3_incomplete_attribution.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
_recall = [a["candidate_id"] for a in attrib
           if a["★ 处置类别"] == "recoverable_by_recall"]
aud = {x["candidate_id"]: x for x in load_jsonl(AUDIT06)}
orig = load_frozen_orig()
_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, cwd=str(ROOT)).stdout.strip()

print(f"  ★ 允许追加调用的候选 = {len(_recall)}")
print(f"  ★ 预算：API ≤ {MAX_ATTEMPTS}｜token ≤ {MAX_TOKENS:,}")

b = Budget("N3-补齐复判", MAX_ATTEMPTS, MAX_TOKENS, None)
records = []
for cid in _recall:
    o = orig.get(cid)
    a = aud.get(cid)
    if not o or not a:
        continue
    p = l2_payload(o)
    for side in ("old", "new"):
        q = (a.get("old_quote") if side == "old" else a.get("new_quote")) or ""
        if not q.strip():
            continue
        if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
            break
        full = l2_prompt(p, q, nv)
        _r = judge(b, p, q, nv)
        _rec = {"candidate_id": cid, "side": side,
                "prompt_hash": hashlib.sha256(full.encode()).hexdigest(),
                "model": os.environ.get("LLM_MODEL"), "code_commit": _commit,
                "stage": "N3", **_r}
        b.record(**{k: v for k, v in _rec.items() if k != "stage"})
        records.append(_rec)
        print(f"  · {cid:26s} {side:4s} ⇒ {str(_r['verdict']):10s} "
              f"(att={_r['api_attempts']} tok={(_r['input_tokens'] or 0) + (_r['output_tokens'] or 0)})")
    if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
        break

# ★ 汇总
_c = collections.Counter(r["verdict"] for r in records)
_by = collections.defaultdict(dict)
for r in records:
    _by[r["candidate_id"]][r["side"]] = r
_paired = [c for c, d in _by.items() if len(d) == 2]
_incons = [c for c, d in _by.items()
           if len(d) == 2 and d["old"]["verdict"] != d["new"]["verdict"]]
summary = b.summary()
summary.update({
    "★ 补齐候选": len(_recall),
    "★ 判定分布": dict(_c),
    "★ 两侧都完成（可配对）": len(_paired),
    "★ 仅单侧": len(_by) - len(_paired),
    "★ old/new 判定不同的候选": _incons,
    "★ 说明": "★ 本批**只**对第二类（可重新调用补齐）追加；★ 不可恢复与待人工的未调用",
})
save_jsonl(OUT / "n3_recall_records.jsonl", records)
save_json(OUT / "n3_recall_summary.json", summary)
print()
print(f"  ★ API {b.attempts}/{MAX_ATTEMPTS}｜token {b.in_tok + b.out_tok:,}")
print(f"  ★ 判定分布: {dict(_c)}｜可配对 {len(_paired)}｜old≠new {len(_incons)}")
print(f"\n  ⇒ {OUT/'n3_recall_summary.json'}")
