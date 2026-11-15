# -*- coding: utf-8 -*-
"""★ N1-R2：★ 生成**总体清单**（★ 供汇总脚本的总体口径段使用）。

★ 每条冻结候选一行，★ 含 `★ 类别`：
  audited                 本次盲审样本（50）
  unlocatable             绝对/相对均未命中或越界（23）
  insufficient_evidence   命中但锚点空/证据句缺失（33）
  not_sampled_in_frame    证据充分但未被抽中（50）
★ ⇒ **156 条全部在册** ⇒ ★ **不得在总体质量统计中无声消失**
"""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "guard/_out/n1r2"

led = {json.loads(l)["sample_id"]: json.loads(l) for l in
       (OUT / "n1r2_span_ledger.jsonl").read_text(encoding="utf-8").splitlines()
       if l.strip()}
packs = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (OUT / "n1r2_packs.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}
freeze = json.loads((OUT / "n1r2_sampling_freeze.json").read_text(encoding="utf-8"))
_risk_cat = {r["candidate_id"]: r["★ 风险类别"]
             for r in freeze["★ ★ 风险台账（★ 不进本次样本，★ 但计入总体分母）"]["明细"]}

rows = []
for cid, r in sorted(led.items()):
    if cid in packs:
        _cat = "audited"
        _grp = packs[cid]["分组"]
    else:
        _cat = _risk_cat.get(cid, "unspecified")
        _grp = None
    rows.append({
        "sample_id": cid, "★ 类别": _cat, "分组": _grp,
        "protocol": r["★ protocol"], "document": r["★ document"],
        "raw_span": r["raw_span"], "resolved_span": r["resolved_span"],
        "span_mode": r["span_mode"], "within_chunk": r["within_chunk"],
        "evidence_supported": r["evidence_supported"],
    })

(OUT / "n1r2_population.jsonl").write_text(
    "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
    encoding="utf-8")
_c = collections.Counter(x["★ 类别"] for x in rows)
print(f"  ★ 总体清单 = {len(rows)} 条")
for k, v in sorted(_c.items()):
    print(f"      {k:26s} {v:4d}")
assert len(rows) == 156
assert sum(v for k, v in _c.items() if k != "audited") == 106
print(f"  ★ 对账：audited {_c['audited']} + 未纳入 {sum(v for k,v in _c.items() if k!='audited')}"
      f" = {len(rows)}")
print(f"\n  ⇒ {OUT/'n1r2_population.jsonl'}")
