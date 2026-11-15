# -*- coding: utf-8 -*-
"""★ P0.7 第 2 步：P3-E —— ★ 扩大同输入 L2 稳定性实验。

★ 预算：**API ≤ 36 次**（★ 严格上限，★ 重试计入）｜token ≤ 70,000（★ 执行前校验）
★ ★ **prompt_hash 统一为「完整渲染 Prompt 的 sha256」**（★ B4 与 P3-S 曾用不同算法）
★ ★ **仅当完整渲染 Prompt 一致才计入「同输入」比较**
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import (AUDIT06, LEDGER_B1, OUTROOT, ROOT, Budget, classify_pair, doc_lines,
                  git_commit, judge, l2_payload, l2_prompt, load_frozen_orig,
                  load_jsonl, save_json, save_jsonl)
from core.fused.extraction import normative_verify as nv

MAX_ATTEMPTS = 36
MAX_TOKENS = 70_000
COST_PER_1K = None

led = {x["candidate_id"]: x for x in load_jsonl(LEDGER_B1)}
aud = {x["candidate_id"]: x for x in load_jsonl(AUDIT06)}
orig = load_frozen_orig()
p3s_recs = load_jsonl(OUTROOT.parent / "p07b5/p3s_records.jsonl")
p3s_real = {r["candidate_id"] for r in p3s_recs if r["api_attempts"] > 0}

# ══ 候选选择（★ 分层覆盖；★ 不按结果挑选）══
def _tags(x):
    return set(x["★ 风险标签"])


elig = [x for x in led.values() if x["★ 一级分类"] == "eligible_unreviewed"]
_byid = {x["candidate_id"]: x for x in elig}
# ★ 已做真实 API 的 eligible ⇒ 排除（★ 增量）
_no_api = [x for x in elig if x["candidate_id"] not in p3s_real]

_picks = []
# ① 强度/极性风险
_picks += [("T1 强度/极性风险", x) for x in _no_api
           if "strength_polarity_anomaly" in _tags(x)][:2]
# ② subject≠entity
_picks += [("T2 subject≠entity", x) for x in _no_api
           if "subject_ne_entity" in _tags(x)][:2]
# ③ 指代风险
_picks += [("T3 指代主体", x) for x in _no_api
           if "coreference_subject" in _tags(x)][:2]
# ④ 跨块证据
_picks += [("T4 跨块证据", x) for x in _no_api
           if "cross_chunk_evidence" in _tags(x)][:1]
# ⑤ quote 变化 + 低风险（有效候选）
_picks += [("T5 quote变化·低风险", x) for x in _no_api
           if "quote_changed" in _tags(x)
           and not (_tags(x) & {"coreference_subject",
                                 "strength_polarity_anomaly",
                                 "subject_ne_entity",
                                 "cross_sentence_object_or_condition"})][:3]
# ⑥ quote 未变化对照
_picks += [("T6 quote未变对照", x) for x in _no_api
           if "quote_changed" not in _tags(x)][:3]
# ⑦ 状态迁移候选（★ 可能不在 eligible ⇒ 单独取）
_mig = [x for x in led.values() if "l2_state_migrated" in _tags(x)]
for x in _mig[:2]:
    if x["candidate_id"] not in {p["candidate_id"] for _, p in _picks}:
        _picks.append(("T7 已发生状态迁移", x))
# 去重
_seen = set()
_picks2 = []
for _t, _x in _picks:
    if _x["candidate_id"] in _seen:
        continue
    _seen.add(_x["candidate_id"])
    _picks2.append((_t, _x))
# ★ 补足到 14 对
_i = 0
while len(_picks2) < 14 and _i < len(_no_api):
    _x = _no_api[_i]
    _i += 1
    if _x["candidate_id"] in _seen:
        continue
    _seen.add(_x["candidate_id"])
    _picks2.append(("T8 补足", _x))

print(f"  ★ P3-E 候选对数 = {len(_picks2)}（★ 每对 2 次 ⇒ {len(_picks2)*2} 次）"
      f" + @1842#2 额外 2 次 ⇒ {len(_picks2)*2 + 2} 次（★ 上限 {MAX_ATTEMPTS}）")

# ══ 冻结输入 ══
_commit = git_commit()
frozen = []
for _t, _x in _picks2:
    _cid = _x["candidate_id"]
    _o = orig.get(_cid, {})
    _a = aud[_cid]
    _p = l2_payload(_o)
    _q = _a.get("new_quote") or ""
    _full = l2_prompt(_p, _q, nv)
    frozen.append({
        "stratum": _t, "candidate_id": _cid,
        "protocol": _a["protocol"], "document": _a["document"],
        "原始字段": {k: _o.get(k) for k in ("entity", "normative_subject",
                                       "action", "object", "strength",
                                       "polarity", "constraint", "raw_span")},
        "payload": _p, "quote": _q,
        "rfc_sha256": __import__("hashlib").sha256(
            (ROOT / f"kb/{_a['protocol']}/spec/{_a['document']}").read_bytes()
        ).hexdigest(),
        "★ 完整渲染 Prompt": _full,
        "★ prompt_hash": __import__("hashlib").sha256(
            _full.encode("utf-8")).hexdigest(),
        "model": os.environ.get("LLM_MODEL"), "temperature": 0.0,
        "max_tokens": 16000, "code_commit": _commit,
    })

# ══ 执行 ══
b = Budget("P0.7-P3-E", MAX_ATTEMPTS, MAX_TOKENS, COST_PER_1K)
records = []


def run_once(f, idx, purpose):
    _r = judge(b, f["payload"], f["quote"], nv)
    b.record(candidate_id=f["candidate_id"], stratum=f["stratum"],
              repeat_index=idx, purpose=purpose,
              prompt_hash=f["★ prompt_hash"], model=f["model"],
              **(_r | {"api_attempts": _r["api_attempts"]}))
    return _r


for f in frozen:
    for _i in (1, 2):
        if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
            break
        _r = run_once(f, _i, "new_candidate_pair")
        print(f"  · {f['candidate_id']:24s} {_i} ⇒ {str(_r['verdict']):10s} "
              f"(att={_r['api_attempts']} tok={( _r['input_tokens'] or 0)+(_r['output_tokens'] or 0)})")
    if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
        break

# ★ ★ 历史异常候选：**额外重复**（★ 单独分析，不计入独立候选数）
_hist = [f for f in frozen if f["candidate_id"] == "rfc3261.txt@1842#2"]
if not _hist:
    # 从 audit+冻结件重建
    _cid = "rfc3261.txt@1842#2"
    _o = orig[_cid]
    _a = aud[_cid]
    _p = l2_payload(_o)
    _q = _a.get("new_quote") or ""
    _full = l2_prompt(_p, _q, nv)
    _hist = [{"stratum": "T0 历史异常", "candidate_id": _cid,
              "protocol": _a["protocol"], "document": _a["document"],
              "原始字段": {k: _o.get(k) for k in ("entity", "normative_subject",
                                           "action", "object", "strength",
                                           "polarity", "constraint", "raw_span")},
              "payload": _p, "quote": _q,
              "rfc_sha256": __import__("hashlib").sha256(
                  (ROOT / f"kb/{_a['protocol']}/spec/{_a['document']}").read_bytes()
              ).hexdigest(),
              "★ 完整渲染 Prompt": _full,
              "★ prompt_hash": __import__("hashlib").sha256(
                  _full.encode("utf-8")).hexdigest(),
              "model": os.environ.get("LLM_MODEL"), "temperature": 0.0,
              "max_tokens": 16000, "code_commit": _commit}]
for f in _hist:
    for _i in (3, 4):        # ★ 第 3/4 次 ⇒ 与 P3-S 的 2 次合并分析
        if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
            break
        _r = run_once(f, _i, "★ 历史异常候选额外重复")
        print(f"  ★ {f['candidate_id']:24s} #{_i} ⇒ {str(_r['verdict']):10s} "
              f"(att={_r['api_attempts']})")

# ══ 比较 ══
_byc = collections.defaultdict(list)
for r in records:
    _byc[r["candidate_id"]].append(r)
pairs = []
for cid, rs in _byc.items():
    _valid = [r for r in rs if r.get("verdict") and not r.get("error")]
    _ph = {r["prompt_hash"] for r in rs}
    if len(_valid) >= 2:
        _a, _b = _valid[0], _valid[1]
        _cat = classify_pair(_a, _b)
        _same_ph = True
        _status_same = (_a["verdict"] == _b["verdict"])
        _reason_same = (_a.get("reason") == _b.get("reason"))
        _fd_changed = (_a.get("field_verdicts") != _b.get("field_verdicts"))
    else:
        _cat = classify_pair(None, None)
        _same_ph = len(_ph) == 1
        _status_same = None
        _reason_same = None
        _fd_changed = None
    pairs.append({
        "candidate_id": cid, "stratum": rs[0]["stratum"],
        "prompt_hash": sorted(_ph), "★ 同输入": _same_ph,
        "n_valid": len(_valid), "runs": len(rs),
        "verdicts": [r["verdict"] for r in _valid],
        "reasons": [r["reason"] for r in _valid],
        "★ 分类": _cat, "★ 状态一致": _status_same,
        "★ 理由一致": _reason_same, "★ 字段级变化": _fd_changed,
        "★ 响应哈希": [r["raw_response_sha256"] for r in _valid],
        "★ token": [(r["input_tokens"] or 0) + (r["output_tokens"] or 0)
                   for r in _valid],
        "★ 涉及 confirmed": any(r["verdict"] == "confirmed" for r in _valid),
    })

_c = collections.Counter(p["★ 分类"] for p in pairs)
_incons = [p for p in pairs if p["★ 状态一致"] is False]
_ci = [p for p in _incons if p["★ 涉及 confirmed"]]
print()
print("  ★ 分类分布:", dict(_c))
print(f"  ★ 状态不一致 = {len(_incons)}｜涉及 confirmed = {len(_ci)}")

# ★ 与历史记录的合并分析（★ @1842#2）
_hist_all = [r for r in load_jsonl(OUTROOT.parent / "p07b5/p3s_records.jsonl")
              if r["candidate_id"] == "rfc3261.txt@1842#2"]
_hist_all += [r for r in records if r["candidate_id"] == "rfc3261.txt@1842#2"]
_hist_b4 = [r for r in load_jsonl(OUTROOT.parent / "p07b/b4_records.jsonl")
            if r["candidate_id"] == "rfc3261.txt@1842#2"
            and r["stratum"] == "S4 同输入重复"]
print(f"  ★★ @1842#2 历史合并：B4 2 次 + P3-S 2 次 + P3-E 2 次 = "
      f"{len(_hist_b4) + len(_hist_all)} 次 ⇒ "
      f"verdicts={[r['verdict'] for r in _hist_b4 + _hist_all]}")

summary = b.summary()
summary.update({
    "★ 一致性": {"pairs": len(pairs), "comparable": len(_incons) + sum(
        1 for p in pairs if p["★ 状态一致"] is True),
        "★ 分类分布": dict(_c),
        "★ 状态不一致": len(_incons),
        "★ 涉及 confirmed 的不一致": len(_ci),
        "★ 不一致明细": [{"candidate_id": p["candidate_id"],
                     "verdicts": p["verdicts"], "reasons": p["reasons"]}
                    for p in _incons]},
    "★ 历史异常候选 @1842#2 合并": {
        "b4_prompt_hash": [r["prompt_hash"] for r in _hist_b4],
        "p3s_p3e_prompt_hash": sorted({r["prompt_hash"] for r in _hist_all}),
        "★ 两批 hash 相同": (
            {r["prompt_hash"] for r in _hist_b4} ==
            {r["prompt_hash"] for r in _hist_all}) if (_hist_b4 and _hist_all) else None,
        "verdicts": [r["verdict"] for r in _hist_b4 + _hist_all],
    },
})
save_json(OUTROOT / "p07_a2_p3e_summary.json", summary)
save_jsonl(OUTROOT / "p07_l2_stability_pairs.jsonl", pairs)
save_jsonl(OUTROOT / "p07_a2_p3e_records.jsonl", records)
save_json(OUTROOT / "p07_a2_p3e_frozen.json", frozen)
print(f"\n  ⇒ {OUTROOT/'p07_a2_p3e_summary.json'}")
