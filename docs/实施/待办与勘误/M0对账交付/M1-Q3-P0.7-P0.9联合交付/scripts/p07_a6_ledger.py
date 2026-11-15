# -*- coding: utf-8 -*-
"""★ P0.7 第 6 步：★ 156 条候选的**最终复判台账**（★ 联合验收用）。

★ 互斥状态（★ 对账到 156）：
  · completed_paired_reviewed   已完成有效配对复判（★ 两侧都有真实 API 判定）
  · completed_single_side       仅完成单侧判定
  · deterministic_only          仅有确定性短路记录（★ 无 LLM 输出）
  · not_applicable              不适用 L2
  · upstream_invalid            上游证据/映射不成立
  · insufficient_evidence       证据不足
  · pending_manual_review       待独立人工复核
  · incomplete（★ 原因）        未完成
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import LEDGER_B1, OUTROOT, load_jsonl, save_json, save_jsonl

led = {x["candidate_id"]: x for x in load_jsonl(LEDGER_B1)}

# ★ 全部真实 API 判定记录（★ 按 (候选, quote 侧) 汇总）
_recs = []
for _p in (OUTROOT / "p07_a2_p3e_records.jsonl",
           OUTROOT / "p07_a4_p0_rows.jsonl",
           OUTROOT / "p07_a5_p1_rows.jsonl",
           OUTROOT.parent / "p07b5/p3s_records.jsonl",
           OUTROOT.parent / "p07b/b4_records.jsonl"):
    for r in load_jsonl(_p):
        if r.get("verdict") and not r.get("error"):
            _recs.append(r)
_api = [r for r in _recs if r.get("api_attempts", 0) > 0]
_byc = collections.defaultdict(lambda: collections.defaultdict(list))
for r in _api:
    _side = r.get("side") or r.get("which") or "new"
    if _side not in ("old", "new"):
        _side = "new"
    _byc[r["candidate_id"]][_side].append(r)
_det = collections.defaultdict(list)
for r in _recs:
    if r.get("api_attempts", 0) == 0:
        _det[r["candidate_id"]].append(r)

# ★ 稳定性分组（★ 同 ph）
_byph = collections.defaultdict(list)
for r in _api:
    if r.get("prompt_hash"):
        _byph[(r["candidate_id"], r["prompt_hash"])].append(r)
_incons_cids = {cid for (cid, ph), rs in _byph.items()
                if len(rs) >= 2 and len({x["verdict"] for x in rs}) > 1}
_conf_incons = set()
for (cid, ph), rs in _byph.items():
    if len(rs) >= 2 and len({x["verdict"] for x in rs}) > 1 \
            and "confirmed" in {x["verdict"] for x in rs}:
        _conf_incons.add(cid)

ledger = []
for cid, x in sorted(led.items()):
    _cls = x["★ 一级分类"]
    _sides = _byc.get(cid, {})
    _n_old = len(_sides.get("old", []))
    _n_new = len(_sides.get("new", []))
    _vs = [r["verdict"] for r in _sides.get("old", []) + _sides.get("new", [])]
    _manual = []
    if cid in _conf_incons:
        _manual.append("★ 同输入下 confirmed 相关分歧")
    if x.get("attribution", {}).get("status") in ("coreference_ambiguous",
                                                  "coreference_unresolved"):
        _manual.append("★ 主体归属歧义/未解析")
    if "strength_polarity_anomaly" in x["★ 风险标签"]:
        _manual.append("★ 强度/极性风险")
    if "subject_ne_entity" in x["★ 风险标签"]:
        _manual.append("★ subject≠entity")
    if _cls == "paired_reviewed" and _n_old >= 1 and _n_new >= 1:
        _state = "completed_paired_reviewed"
    elif _cls == "paired_reviewed" and (_n_old or _n_new):
        _state = "completed_single_side"
    elif _cls == "not_applicable":
        _state = "not_applicable"
    elif _cls == "upstream_invalid":
        _state = "upstream_invalid"
    elif _cls == "eligible_unreviewed" and (_n_old or _n_new):
        _state = "completed_single_side" if not (_n_old and _n_new) \
            else "completed_paired_reviewed"
    elif _cls == "eligible_unreviewed":
        _state = "incomplete"
    else:
        _state = "incomplete"
    if _manual and _state.startswith("completed"):
        _state = "pending_manual_review"
    ledger.append({
        "candidate_id": cid, "protocol": x["protocol"], "document": x["document"],
        "一级分类": _cls, "★ 最终状态": _state,
        "★ 真实 API 判定数": _n_old + _n_new,
        "old 侧真实 API 数": _n_old, "new 侧真实 API 数": _n_new,
        "★ 确定性短路记录数": len(_det.get(cid, [])),
        "判定序列": _vs,
        "★ 风险标签": x["★ 风险标签"],
        "★ 待人工原因": _manual,
        "★ 归属状态": (x.get("attribution") or {}).get("status"),
    })

_c = collections.Counter(r["★ 最终状态"] for r in ledger)
print("  ★ 156 条最终状态：")
for k, v in sorted(_c.items(), key=lambda y: -y[1]):
    print(f"      {k:32s} {v:4d}")
print(f"      {'★ 合计':32s} {sum(_c.values()):4d}")
assert sum(_c.values()) == 156

_api_by = {cid: len(v) for cid, v in _byc.items()}
summary = {
    "★ 最终状态分布": dict(_c), "★ 合计": sum(_c.values()),
    "★ 统计": {
        "唯一候选数": len(ledger),
        "实际 API 调用数（★ 本轮 B5-P0+P1）": len(
            load_jsonl(OUTROOT / "p07_a4_p0_rows.jsonl")) + len(
            load_jsonl(OUTROOT / "p07_a5_p1_rows.jsonl")),
        "★ 累计真实 API 判定记录（含历史）": len(_api),
        "★ 稳定性重复调用数": sum(
            max(0, len(rs) - 1) for rs in _byph.values()),
        "★ 复判状态变化": len(_incons_cids),
        "★ 涉及 confirmed 的分歧候选": len(_conf_incons),
        "★ false confirmation 风险": sorted(_conf_incons),
        "★ false rejection 风险": sorted(
            cid for cid in _incons_cids if cid not in _conf_incons),
        "★ unresolved 风险": sorted(
            cid for cid in ledger
            if (cid.get("attribution") or {}).get("status")
            in ("coreference_ambiguous", "coreference_unresolved")),
    },
    "★ 通过条件说明": "★ **不以 confirmed 增加作为通过条件**",
}
save_jsonl(OUTROOT / "p07_candidate_ledger.jsonl", ledger)
save_json(OUTROOT / "p07_a6_ledger_summary.json", summary)
print()
print(json.dumps(summary["★ 统计"], ensure_ascii=False, indent=2))
print(f"\n  ⇒ {OUTROOT/'p07_candidate_ledger.jsonl'}")
