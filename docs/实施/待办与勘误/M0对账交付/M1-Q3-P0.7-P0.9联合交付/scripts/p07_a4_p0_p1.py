# -*- coding: utf-8 -*-
"""★ P0.7 第 4/5 步：B5-P0（状态迁移复判）+ B5-P1（其余有效候选复判）。

★ B5-P0：≤24 次 API ｜ B5-P1：≤76 次 API
★ 原则：★ **不重复调用已具有可比有效记录的输入**（★ 按 (候选, quote 侧) 去重）
★ 所有结果写入实验审计数据，★ **不改变正式 confirmed 或 Fact**
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import (AUDIT06, LEDGER_B1, OUTROOT, ROOT, Budget, classify_pair,
                  judge, l2_payload, l2_prompt, load_frozen_orig, load_jsonl,
                  save_json, save_jsonl)
from core.fused.extraction import normative_verify as nv

MAX_P0 = 24
MAX_P1 = 76
MAX_TOK_P0 = 55_000
MAX_TOK_P1 = 140_000
COST = None

led = {x["candidate_id"]: x for x in load_jsonl(LEDGER_B1)}
aud = {x["candidate_id"]: x for x in load_jsonl(AUDIT06)}
orig = load_frozen_orig()
# ★ 已有的真实 API 记录（★ 按 (候选, quote 侧) 标记）
_have = collections.defaultdict(set)
for _p in (OUTROOT / "p07_a2_p3e_records.jsonl",
           OUTROOT.parent / "p07b5/p3s_records.jsonl",
           OUTROOT.parent / "p07b/b4_records.jsonl"):
    for r in load_jsonl(_p):
        if r.get("api_attempts", 0) > 0 and r.get("verdict"):
            _w = r.get("which")
            _side = _w if _w in ("old", "new") else "new"
            _have[r["candidate_id"]].add(_side)


def _mk(cid):
    _o = orig.get(cid, {})
    _a = aud[cid]
    _p = l2_payload(_o)
    _out = []
    for _side, _q in (("old", _a.get("old_quote") or ""),
                      ("new", _a.get("new_quote") or "")):
        if not _q.strip():
            continue
        _full = l2_prompt(_p, _q, nv)
        _out.append({"side": _side, "quote": _q, "payload": _p,
                     "prompt_hash": __import__("hashlib").sha256(
                         _full.encode("utf-8")).hexdigest()})
    return _out


# ══ B5-P0：状态迁移复判 ══
b0 = Budget("P0.7-B5-P0", MAX_P0, MAX_TOK_P0, COST)
_mig = [x["candidate_id"] for x in led.values()
        if "l2_state_migrated" in set(x["★ 风险标签"])]
_p0_rows = []
for cid in _mig:
    for s in _mk(cid):
        if s["side"] in _have.get(cid, ()):
            _p0_rows.append({"candidate_id": cid, "side": s["side"],
                             "skipped": "★ 已有可比真实 API 记录 ⇒ 不重复调用"})
            continue
        if b0.attempts >= MAX_P0 or b0.stop_reason:
            break
        _r = judge(b0, s["payload"], s["quote"], nv)
        b0.record(candidate_id=cid, side=s["side"], stratum="B5-P0 状态迁移复判",
                  prompt_hash=s["prompt_hash"], **(_r | {"api_attempts": _r["api_attempts"]}))
        _p0_rows.append({"candidate_id": cid, "side": s["side"],
                          "verdict": _r["verdict"], "reason": _r["reason"],
                          "prompt_hash": s["prompt_hash"],
                          "api_attempts": _r["api_attempts"],
                          "tokens": (_r["input_tokens"] or 0) + (_r["output_tokens"] or 0)})
    if b0.attempts >= MAX_P0 or b0.stop_reason:
        break
print(f"  ★ B5-P0：API {b0.attempts}/{MAX_P0}｜token {b0.in_tok + b0.out_tok:,}")

# ══ B5-P1：其余有效候选复判 ══
b1 = Budget("P0.7-B5-P1", MAX_P1, MAX_TOK_P1, COST)
_elig = [x["candidate_id"] for x in led.values()
         if x["★ 一级分类"] == "eligible_unreviewed"]
# ★ 优先：quote 变化 + 证据完整 + 上游有效
def _prio(cid):
    x = led[cid]
    _t = set(x["★ 风险标签"])
    _risk = 1 if (_t & {"coreference_subject", "strength_polarity_anomaly",
                        "subject_ne_entity",
                        "cross_sentence_object_or_condition"}) else 0
    _qc = 0 if "quote_changed" in _t else 1
    return (_risk, _qc, cid)


_p1_rows = []
for cid in sorted(_elig, key=_prio):
    for s in _mk(cid):
        if s["side"] in _have.get(cid, ()):
            _p1_rows.append({"candidate_id": cid, "side": s["side"],
                             "skipped": "★ 已有可比真实 API 记录 ⇒ 不重复调用"})
            continue
        if b1.attempts >= MAX_P1 or b1.stop_reason:
            break
        _r = judge(b1, s["payload"], s["quote"], nv)
        b1.record(candidate_id=cid, side=s["side"], stratum="B5-P1 有效候选复判",
                  prompt_hash=s["prompt_hash"], **(_r | {"api_attempts": _r["api_attempts"]}))
        _p1_rows.append({"candidate_id": cid, "side": s["side"],
                         "verdict": _r["verdict"], "reason": _r["reason"],
                         "prompt_hash": s["prompt_hash"],
                         "api_attempts": _r["api_attempts"],
                         "tokens": (_r["input_tokens"] or 0) + (_r["output_tokens"] or 0)})
    if b1.attempts >= MAX_P1 or b1.stop_reason:
        break
print(f"  ★ B5-P1：API {b1.attempts}/{MAX_P1}｜token {b1.in_tok + b1.out_tok:,}")

# ══ 汇总 ══
def _sum(b, rows, label):
    _c = collections.Counter(r.get("verdict") for r in rows if r.get("verdict"))
    return {label: b.summary(),
            "★ 判定分布": dict(_c),
            "★ 跳过（已有可比记录）": sum(1 for r in rows if r.get("skipped"))}


summary = {"★ B5-P0": _sum(b0, _p0_rows, "预算"),
           "★ B5-P1": _sum(b1, _p1_rows, "预算")}
save_json(OUTROOT / "p07_a4_p0_p1_summary.json", summary)
save_jsonl(OUTROOT / "p07_a4_p0_rows.jsonl", _p0_rows)
save_jsonl(OUTROOT / "p07_a5_p1_rows.jsonl", _p1_rows)
print()
print(json.dumps(summary, ensure_ascii=False, indent=2)[:1800])
print(f"\n  ⇒ {OUTROOT/'p07_a4_p0_p1_summary.json'}")
