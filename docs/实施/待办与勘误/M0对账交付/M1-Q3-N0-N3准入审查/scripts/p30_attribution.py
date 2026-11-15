# -*- coding: utf-8 -*-
"""★ N3：★ 31 条 incomplete 候选的**逐条归因**（★ 先离线，★ 不直接重试）。

★ 归因类别：
  · old_response_missing      旧响应/旧 quote 缺失
  · not_comparable            新旧输入无法构成有效比较
  · historical_api_failure    历史 API 或解析失败
  · insufficient_evidence     证据不足
  · needs_human_judgement     需要独立人工判断
  · budget_not_covered        预算或批次未覆盖
  · other                     其他明确原因
★ 四类处置：
  ① recoverable_from_existing  能利用已有结果补齐
  ② recoverable_by_recall     重新调用 L2 可以补齐
  ③ unrecoverable_history     即使重新调用也无法恢复历史可比性
  ④ wait_for_human            必须等待人工判断
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_p079"))
from _lib import AUDIT06, LEDGER_B1, load_frozen_orig, load_jsonl, save_json, save_jsonl

OUT = ROOT / "guard/_out/n3"
OUT.mkdir(parents=True, exist_ok=True)

led = [json.loads(l) for l in
       (ROOT / "guard/_out/m1_q3/p079/p07_candidate_ledger.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()]
aud = {x["candidate_id"]: x for x in load_jsonl(AUDIT06)}
orig = load_frozen_orig()

# ★ 全部真实 API 记录（★ 含历史）
_api_rows = []
for _p in (ROOT / "guard/_out/n2/n2_history_rows.jsonl",
           ROOT / "guard/_out/n2/n2_records.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a4_p0_rows.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a5_p1_rows.jsonl"):
    if _p.is_file():
        for r in load_jsonl(_p):
            # ★ ★ **必须过滤确定性短路**（★ attempts=0 ⇒ 无 LLM 输出 ⇒ 不算真实判定）
            if r.get("verdict") and not r.get("error")                     and r.get("api_attempts", 0) > 0:
                _api_rows.append(r)
_byc = collections.defaultdict(list)
for r in _api_rows:
    _byc[r["candidate_id"]].append(r)
# ★ 失败记录
_fail = collections.defaultdict(list)
for _p in (ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl",
           ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a4_p0_rows.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a5_p1_rows.jsonl"):
    if _p.is_file():
        for r in load_jsonl(_p):
            if r.get("error"):
                _fail[r["candidate_id"]].append(r)

_inc = [x for x in led if x["★ 最终状态"] == "incomplete"]
print(f"  ★ incomplete 候选 = {len(_inc)}")

rows = []
for x in _inc:
    cid = x["candidate_id"]
    a = aud.get(cid, {})
    o = orig.get(cid)
    _has_old = bool((a.get("old_quote") or "").strip())
    _has_new = bool((a.get("new_quote") or "").strip())
    _rs = _byc.get(cid, [])
    _fs = _fail.get(cid, [])
    _det = len(_rs) == 0
    # ★ 归因判定（★ 先离线）
    if not o:
        _reason = "other"
        _detail = "★ 冻结件中无该候选的原始字段"
        _disp = "unrecoverable_history"
    elif _fs and not _rs:
        _reason = "historical_api_failure"
        _detail = f"★ 历史 API/解析失败 {len(_fs)} 次且无成功判定"
        _disp = "recoverable_by_recall"
    elif not _has_old:
        _reason = "old_response_missing"
        _detail = "★ 旧 quote 缺失 ⇒ 无法构造 old/new 对照"
        _disp = "unrecoverable_history"
    elif not _has_new:
        _reason = "insufficient_evidence"
        _detail = "★ 新 quote 缺失 ⇒ 无证据可判"
        _disp = "unrecoverable_history"
    elif not _rs:
        # ★ ★ 区分「从未调用」与「只有确定性短路记录」
        _det_sides = set()
        for _p in (ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl",
                   ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
                   ROOT / "guard/_out/m1_q3/p079/p07_a4_p0_rows.jsonl",
                   ROOT / "guard/_out/m1_q3/p079/p07_a5_p1_rows.jsonl"):
            if not _p.is_file():
                continue
            for _r in load_jsonl(_p):
                if _r["candidate_id"] == cid and _r.get("verdict") \
                        and _r.get("api_attempts", 0) == 0:
                    _det_sides.add(_r.get("side") or _r.get("which") or "new")
        if _det_sides:
            _reason = "deterministic_only"
            _detail = (f"★ 仅有**确定性短路**记录（侧 {sorted(_det_sides)}）"
                       f"⇒ ★ 无 LLM 输出 ⇒ ★ 无法构成 L2 配对")
            _disp = "unrecoverable_history"
        else:
            _reason = "budget_not_covered"
            _detail = "★ 输入完整但**从未调用** L2 ⇒ 可补齐"
            _disp = "recoverable_by_recall"
    elif len({r.get("side") or r.get("which") or "new" for r in _rs}) < 2:
        _reason = "not_comparable"
        _detail = "★ 只做了单侧判定 ⇒ 需补另一侧"
        _disp = "recoverable_by_recall"
    else:
        _reason = "other"
        _detail = "★ 其他"
        _disp = "recoverable_from_existing"
    _risk = set(x["★ 风险标签"])
    if _disp == "recoverable_by_recall" and ("coreference_subject" in _risk
                                            or "strength_polarity_anomaly" in _risk):
        _reason = "needs_human_judgement" if "coreference_subject" in _risk else _reason
        _detail += "；★ 且带高风险标签 ⇒ ★ 建议人工判读后再调用"
        if _reason == "needs_human_judgement":
            _disp = "wait_for_human"
    rows.append({
        "candidate_id": cid, "protocol": x["protocol"], "document": x["document"],
        "★ 未完成原因": _reason, "★ 说明": _detail, "★ 处置类别": _disp,
        "★ 风险标签": x["★ 风险标签"],
        "★ 已有真实 API 判定数": len(_rs),
        "★ 历史失败数": len(_fs),
        "★ old quote 存在": _has_old, "★ new quote 存在": _has_new,
        "★ 可复用的历史侧": sorted({r.get("side") or r.get("which") or "new"
                             for r in _rs}),
    })

_c1 = collections.Counter(r["★ 未完成原因"] for r in rows)
_c2 = collections.Counter(r["★ 处置类别"] for r in rows)
print("  ★ 未完成原因分布：")
for k, v in _c1.most_common():
    print(f"      {k:28s} {v:3d}")
print("  ★ 处置类别分布：")
for k, v in _c2.most_common():
    print(f"      {k:28s} {v:3d}")
_recall = [r["candidate_id"] for r in rows
           if r["★ 处置类别"] == "recoverable_by_recall"]
print(f"  ★ ⇒ **允许追加调用的候选 = {len(_recall)}**")

save_jsonl(OUT / "n3_incomplete_attribution.jsonl", rows)
save_json(OUT / "n3_attribution_summary.json", {
    "total": len(rows),
    "★ 未完成原因分布": dict(_c1),
    "★ 处置类别分布": dict(_c2),
    "★ 允许追加调用的候选": _recall,
    "★ 允许追加调用次数上限": 64,
})
print(f"\n  ⇒ {OUT/'n3_incomplete_attribution.jsonl'}")
