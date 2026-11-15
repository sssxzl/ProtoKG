# -*- coding: utf-8 -*-
"""★ P0.7 第 1 步：账本核实与冻结（2.1）。

★ 复核最新已修正口径；★ **按 candidate_id 去重**；★ 核对 P0/P1/P2/P3 批次交集。
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lib import (AUDIT06, LEDGER_B1, P07B, P3S, DELIV, OUTROOT,
                  load_jsonl, save_json)

led = load_jsonl(LEDGER_B1)
b4 = load_jsonl(P07B / "b4_records.jsonl")
p3s = load_jsonl(P3S / "p3s_records.jsonl")
p3s_frozen = json.loads((P3S / "p3s_frozen.json").read_text(encoding="utf-8")) \
    if (P3S / "p3s_frozen.json").is_file() else []

_cls = collections.Counter(x["★ 一级分类"] for x in led)
_elig = {x["candidate_id"] for x in led if x["★ 一级分类"] == "eligible_unreviewed"}
_paired_all = {x["candidate_id"] for x in led
               if x["★ 一级分类"] == "paired_reviewed"}
_b4_api = [r for r in b4 if r["api_attempts"] > 0]
_b4_pairs = collections.defaultdict(dict)
for r in b4:
    if r["which"] in ("old", "new"):
        _b4_pairs[r["candidate_id"]][r["which"]] = r
_b4_real = {cid for cid, v in _b4_pairs.items()
            if v["old"]["api_attempts"] or v["new"]["api_attempts"]}
_elig_paired = _elig & set(_b4_pairs)
_elig_real = _elig & _b4_real
_mig = {x["candidate_id"] for x in led if "l2_state_migrated" in x["★ 风险标签"]}

# ★ B5 批次候选 ID 交集（★ 按 candidate_id 去重）
B5 = {
    "P0_状态迁移": _mig,
    "P1_quote变化且证据完整": {
        x["candidate_id"] for x in led
        if x["★ 一级分类"] == "eligible_unreviewed"
        and "quote_changed" in x["★ 风险标签"]
        and not (set(x["★ 风险标签"]) & {"coreference_subject",
                                          "strength_polarity_anomaly",
                                          "subject_ne_entity",
                                          "cross_sentence_object_or_condition"})},
    "P2_高风险": {
        x["candidate_id"] for x in led
        if set(x["★ 风险标签"]) & {"coreference_subject",
                                    "strength_polarity_anomaly",
                                    "subject_ne_entity",
                                    "cross_sentence_object_or_condition"}},
    "P3_对照": {
        x["candidate_id"] for x in led
        if x["★ 一级分类"] == "eligible_unreviewed"
        and "quote_changed" not in x["★ 风险标签"]},
}
_allB5 = set().union(*B5.values())
_overlaps = []
_ks = list(B5)
for i in range(len(_ks)):
    for j in range(i + 1, len(_ks)):
        _ov = B5[_ks[i]] & B5[_ks[j]]
        if _ov:
            _overlaps.append({"a": _ks[i], "b": _ks[j], "n": len(_ov),
                              "ids": sorted(_ov)[:10]})

# ★ 已做真实 API 复判的候选全集（含 P3-S）
_p3s_ids = {r["candidate_id"] for r in p3s if r["api_attempts"] > 0}
_real_api_anywhere = _b4_real | _p3s_ids
_real_api_in_elig = _elig & _real_api_anywhere
_no_api = _elig - _real_api_anywhere

print("  ★ 一级分类（★ 复核）：", dict(_cls), "⇒ 合计", sum(_cls.values()))
print(f"  ★ B4：真实 API {len(_b4_api)} 次｜逻辑判定 {len(b4)} 条｜"
      f"确定性短路 {len(b4) - len(_b4_api)} 条")
print(f"  ★ 7 条配对记录中：真调过 API 的候选 = {len(_b4_real)}")
print(f"  ★ eligible={len(_elig)}｜其中做过配对记录 {len(_elig_paired)}｜"
      f"真调过 API {len(_elig_real)}")
print(f"  ★ ★ 真正未做任何真实 API 复判的 eligible = {len(_no_api)}")
print(f"  ★ P3-S 已做真实 API 的候选 = {len(_p3s_ids)}")
print()
print("  ★ B5 批次交集（★ 按 candidate_id）：")
for _o in _overlaps:
    print(f"      {_o['a']} ∩ {_o['b']} = {_o['n']} 条")
print(f"      B5 各批次并集（去重后）= {len(_allB5)}")

report = {
    "★ 一级分类": dict(_cls), "★ 合计": sum(_cls.values()),
    "★ B4": {"real_api": len(_b4_api), "logical_verdicts": len(b4),
           "deterministic_shortcuts": len(b4) - len(_b4_api),
           "unique_candidates": len({r["candidate_id"] for r in b4})},
    "★ 7 条配对记录": {"candidates": len(_b4_pairs),
                  "real_api_candidates": len(_b4_real),
                  "both_sides_real": sum(
                      1 for v in _b4_pairs.values()
                      if v["old"]["api_attempts"] and v["new"]["api_attempts"])},
    "★ eligible": {"total": len(_elig), "paired_recorded": len(_elig_paired),
                "real_api": len(_elig_real),
                "★ never_real_api": len(_no_api)},
    "★ B5 批次": {k: len(v) for k, v in B5.items()},
    "★ B5 并集（去重）": len(_allB5),
    "★ B5 交集": _overlaps,
    "★ P3-S": {"records": len(p3s), "real_api_candidates": len(_p3s_ids)},
    "★ 冻结": {"git_commit": __import__("subprocess").run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[3])).stdout.strip()},
}
save_json(OUTROOT / "p07_a1_accounting.json", report)
print(f"\n  ⇒ {OUTROOT/'p07_a1_accounting.json'}")
