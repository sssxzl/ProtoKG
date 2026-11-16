# -*- coding: utf-8 -*-
"""★ N2-B0-R 第 0 步：★ **由脚本重算** V0 当前 32 条影子统计（★ 不写死期望值）。

★ 同时核实：★ `contradicted → rejected` 的**完整清单**（★ 此前报告漏列第三条）
"""
import collections
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
OUTD = ROOT / "guard/_out/n1c"

rows = list(csv.DictReader((DELIV / "N2-B0_影子状态32条对账.csv")
                            .read_text(encoding="utf-8").splitlines()))
print(f"  ★ 对账全集 = {len(rows)}")

_by_route = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    _by_route[r["★ 路由去向"]][r["★ 人工真值"]] += 1

print("  ★ ★ V0 当前影子统计（★ 由脚本重算）：")
for _route in ("★ routed_to_LLM", "★ pending", "★ rejected"):
    _c = _by_route[_route]
    _ok = _c.get("valid_confirmed", 0)
    _no = sum(v for k, v in _c.items() if k != "valid_confirmed")
    print(f"      {_route:20s} 合计 {sum(_c.values()):2d}｜"
          f"★ 人工成立 {_ok:2d}｜不成立 {_no:2d}")
_total_ok = sum(v for c in _by_route.values() for k, v in c.items()
                 if k == "valid_confirmed")
print(f"      ★ 合计 {sum(sum(c.values()) for c in _by_route.values())}"
      f"｜★ 人工成立合计 {_total_ok}")

# ★ ★ contradicted → rejected 的完整清单
_con = [r for r in rows if r["★ 影子三态 verdict"] == "contradicted"]
print()
print(f"  ★ ★ contradicted → rejected 完整清单（{len(_con)} 条）：")
for r in _con:
    print(f"      {r['candidate_id'][:28]:30s} 真值={r['★ 人工真值']:16s}"
          f"｜逐字段={r['★ 影子逐字段三态']}")
    print(f"          reason={r['★ 影子 reason'][:110]}")

# ★ 三条误拒案例的原始字段（★ 供 §五 核查）
FR = {}
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = {**it,
                                                     "protocol": b["protocol"],
                                                     "document": b["document"],
                                                     "chunk_start": b["chunk_start"]}
print()
print("  ★ 三条案例的原始候选字段：")
for _cid in ("rfc2326.txt@2030#5", "rfc5321.txt@5226#1", "rfc5321.txt@5226#2"):
    _o = FR.get(_cid, {})
    print(f"      {_cid}")
    for _k in ("entity", "normative_subject", "action", "object", "strength",
               "meaning", "constraint"):
        print(f"          {_k:18s} = {str(_o.get(_k))[:100]!r}")

summary = {
    "★ V0 当前影子统计（★ 脚本重算）": {
        _route: {"合计": sum(_by_route[_route].values()),
               "★ 人工成立": _by_route[_route].get("valid_confirmed", 0),
               "★ 人工不成立": sum(v for k, v in _by_route[_route].items()
                              if k != "valid_confirmed")}
        for _route in _by_route},
    "★ 合计": sum(sum(c.values()) for c in _by_route.values()),
    "★ 人工成立合计": _total_ok,
    "★ contradicted → rejected 完整清单": [
        {"candidate_id": r["candidate_id"], "人工真值": r["★ 人工真值"],
         "逐字段三态": r["★ 影子逐字段三态"], "reason": r["★ 影子 reason"]}
        for r in _con],
}
(OUTD / "n2b0r_v0_recompute.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n2b0r_v0_recompute.json'}")
