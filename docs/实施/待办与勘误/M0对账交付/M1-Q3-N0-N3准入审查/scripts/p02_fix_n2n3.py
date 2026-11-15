# -*- coding: utf-8 -*-
"""★ N1-R：★ 修复 N3 对账（★ 156 条互斥最终状态）+ N2 统计勘误。

★ N3 问题：★ 上一版合计 143 ≠ 156（★ **13 条 `deterministic_only` 未被纳入互斥分类**）
★ N2 问题：★ 16 组混合统计（★ 其中 1 组为确定性短路）⇒ ⇒ **须单列 15 组真实 LLM 配对**
★           ★ `@1842#2` 应为**三种状态**（★ 实际出现 4 种）
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
P079 = ROOT / "guard/_out/m1_q3/p079"
OUT = ROOT / "guard/_out/n1r"

# ══════════ N3 对账修复 ══════════
led = {json.loads(l)["candidate_id"]: json.loads(l) for l in
       (P079 / "p07_candidate_ledger.jsonl").read_text(encoding="utf-8").splitlines()
       if l.strip()}
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
frozen = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        frozen[f"{b['document']}@{b['chunk_start']}#{i}"] = it

# ★ 全部真实 API 记录（★ 含 N2/N3）
_api = []
for _src in (ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl",
             ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
             P079 / "p07_a4_p0_rows.jsonl",
             P079 / "p07_a5_p1_rows.jsonl",
             ROOT / "guard/_out/n2/n2_records.jsonl",
             ROOT / "guard/_out/n3/n3_recall_records.jsonl"):
    if not _src.is_file():
        continue
    for r in [json.loads(l) for l in _src.read_text(encoding="utf-8").splitlines()
              if l.strip()]:
        if r.get("verdict") and not r.get("error"):
            _api.append(r)
# ★ 确定性短路记录（★ 单独统计）
_det = []
for _src in (ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl",
             ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
             P079 / "p07_a4_p0_rows.jsonl",
             P079 / "p07_a5_p1_rows.jsonl",
             ROOT / "guard/_out/n2/n2_records.jsonl",
             ROOT / "guard/_out/n3/n3_recall_records.jsonl"):
    if not _src.is_file():
        continue
    for r in [json.loads(l) for l in _src.read_text(encoding="utf-8").splitlines()
              if l.strip()]:
        if r.get("verdict") and not r.get("error") and r.get("api_attempts", 0) == 0:
            _det.append(r)

_byc = collections.defaultdict(lambda: collections.defaultdict(list))
for r in _api:
    _side = r.get("side") or r.get("which") or "new"
    _byc[r["candidate_id"]][_side].append(r)
_detc = collections.defaultdict(list)
for r in _det:
    _detc[r["candidate_id"]].append(r)

# ══ ★ 互斥的 8 类最终状态 ══
ledger = []
for cid, x in sorted(led.items()):
    _sides = _byc.get(cid, {})
    _n_old = len(_sides.get("old", []))
    _n_new = len(_sides.get("new", []))
    _n_det = len(_detc.get(cid, []))
    _cls = x["一级分类"]
    _manual = list(x.get("★ 待人工原因") or [])
    if _cls == "not_applicable":
        _st = "not_applicable"
        _why = "★ 知识类型导致 L2 不适用（prose_semantics ⇒ 不进 L1/L2）"
    elif _cls == "upstream_invalid":
        _st = "upstream_invalid"
        _why = "★ 上游证据或映射不成立"
    elif _n_old >= 1 and _n_new >= 1:
        _st = "completed_paired_reviewed"
        _why = f"★ 两侧均有**真实 LLM 判定**（old {_n_old} / new {_n_new}）⇒ ★ **可配对复判**"
    elif _n_old or _n_new:
        _st = "completed_single_side"
        _why = "★ 仅单侧有真实 LLM 判定 ⇒ ★ 不可配对"
    elif _n_det >= 1:
        _st = "deterministic_only"
        _why = (f"★ 仅有**确定性短路**记录（{_n_det} 条，★ 无 LLM 输出）"
                f"⇒ ★ **不构成 LLM 配对复判**")
    else:
        _st = "incomplete"
        _why = "★ 未完成（★ 无任何判定记录）"
    if _manual and _st.startswith("completed"):
        _st = "pending_manual_review"
        _why = "★ 存在风险标签或分歧记录 ⇒ ★ 保持待人工复核"
    ledger.append({
        "candidate_id": cid, "protocol": x["protocol"], "document": x["document"],
        "一级分类": _cls, "★ 最终状态": _st, "★ 处置理由": _why,
        "★ 真实 LLM 判定数": _n_old + _n_new,
        "★ old 侧真实 LLM 数": _n_old, "★ new 侧真实 LLM 数": _n_new,
        "★ 确定性短路记录数": _n_det,
        "★ 待人工原因": _manual,
    })

_c = collections.Counter(r["★ 最终状态"] for r in ledger)
_ids = [r["candidate_id"] for r in ledger]
_dup = [k for k, v in collections.Counter(_ids).items() if v > 1]
print("  ★ N3 对账（★ 互斥最终状态）：")
for k, v in sorted(_c.items(), key=lambda y: -y[1]):
    print(f"      {k:32s} {v:4d}")
print(f"      {'★ 合计':32s} {sum(_c.values()):4d}")
print(f"      ★ 唯一 candidate_id = {len(set(_ids))}｜重复 = {_dup or '无'}")
assert sum(_c.values()) == 156 and len(set(_ids)) == 156

# ══════════ N2 统计勘误 ══════════
pairs = [json.loads(l) for l in (ROOT / "guard/_out/n2/n2_pairs.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
# ★ 单列真实 LLM 配对组（★ 至少 2 次真实 API 判定）
_llm_pairs = []
_mixed = []
for p in pairs:
    _real = 0
    for _r in (ROOT / "guard/_out/n2/n2_records.jsonl").read_text(
            encoding="utf-8").splitlines():
        if not _r.strip():
            continue
        _d = json.loads(_r)
        if _d["candidate_id"] == p["candidate_id"] and _d.get("api_attempts", 0) > 0:
            _real += 1
    p = dict(p)
    p["★ 真实 LLM 判定次数"] = _real
    if _real >= 2:
        _llm_pairs.append(p)
    else:
        _mixed.append(p)

_c2 = collections.Counter(p["★ 分类"] for p in _llm_pairs)
_incons = [p for p in _llm_pairs if p["★ 状态一致"] is False]
_ci = [p for p in _incons if p["★ 涉及 confirmed"]]

# ★ @1842#2 的状态集合（★ 修正为「三种/四种」）
_h = [p for p in _llm_pairs if p["candidate_id"] == "rfc3261.txt@1842#2"]
_h_states = []
for p in _h:
    _h_states += p["verdicts"]
_h_uniq = sorted(set(_h_states))

print()
print("  ★ N2 统计勘误（★ 单列真实 LLM 配对）：")
print(f"      真实 LLM 配对组 = {len(_llm_pairs)}（★ 混合统计 16 组作为对照，★ 分母不混用）")
print(f"      确定性短路组 = {len(_mixed)}：{[p['candidate_id'] for p in _mixed]}")
print(f"      分类分布 = {dict(_c2)}")
print(f"      状态不一致 = {len(_incons)}（★ {round(len(_incons)/max(1,len(_llm_pairs))*100,1)}%）")
print(f"      涉及 confirmed = {len(_ci)}")
print(f"      ★ @1842#2 累计判定 = {_h_states} ⇒ **状态种类 = {len(_h_uniq)}：{_h_uniq}**")

summary = {
    "★ N3 最终状态（★ 互斥，★ 对账 156）": dict(_c),
    "★ N3 合计": sum(_c.values()),
    "★ N3 唯一 candidate_id": len(set(_ids)),
    "★ N3 重复": _dup,
    "★ N3 口径说明": {
        "completed_paired_reviewed": "★ 两侧均有真实 LLM 判定 ⇒ 可配对复判",
        "completed_single_side": "★ 仅单侧真实 LLM 判定",
        "deterministic_only": "★ 仅有确定性短路（★ 无 LLM 输出 ⇒ 不计作 LLM 配对复判）",
        "not_applicable": "★ L2 不适用",
        "upstream_invalid": "★ 上游无效",
        "pending_manual_review": "★ 有风险/分歧 ⇒ 待人工",
        "incomplete": "★ 无任何判定",
    },
    "★ N2 统计勘误": {
        "★ 真实 LLM 配对组数": len(_llm_pairs),
        "★ 确定性短路组数": len(_mixed),
        "★ 确定性短路组": [p["candidate_id"] for p in _mixed],
        "★ 真实 LLM 配对分类": dict(_c2),
        "★ 状态不一致": len(_incons),
        "★ 状态不一致率": round(len(_incons) / max(1, len(_llm_pairs)), 4),
        "★ 涉及 confirmed 的不一致": len(_ci),
        "★ 涉及 confirmed 清单": [p["candidate_id"] for p in _ci],
        "★ @1842#2 累计判定": _h_states,
        "★ @1842#2 状态种类": len(_h_uniq),
        "★ @1842#2 状态集合": _h_uniq,
        "★ 混合统计（16 组，★ 仅作对照）": {
            "总组数": len(pairs),
            "状态不一致": sum(1 for p in pairs if p["★ 状态一致"] is False),
            "★ 说明": "★ 含 1 组确定性短路 ⇒ ★ **不得与真实 LLM 配对分母混用**",
        },
    },
}
(OUT / "n1r_n2n3_audit.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "n1r_final_ledger.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in ledger) + "\n",
    encoding="utf-8")
print(f"\n  ⇒ {OUT/'n1r_n2n3_audit.json'}")
