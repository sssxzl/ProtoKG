# -*- coding: utf-8 -*-
"""★ V2-E2 §五：★ **四类来源集合的预先隔离**（★ RFC 文档级优先）。

★ ① 已使用的 N1-B/N1-C/V2 开发来源
★ ② 本轮试点来源（★ ≤ 12 份）
★ ③ 未来独立评估保留来源
★ ④ 队列 B 原文片段审核来源
★ ★ 优先**文档级隔离**；★ 某协议只有一份 RFC 时 ⇒ ★ 改用 chunk / 证据跨度 / 近重复隔离
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
import sampler as SP

OUTD = ROOT / "guard/_out/_n1c_v2/e2"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
N1C = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计")
import csv as _csv

_dev_cands = {json.loads(l)["sample_id"] for l in
              (N1B / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
              if l.strip()}
_dev_cands |= {r["candidate_id"] for r in
               _csv.DictReader((N1C / "N1-C_V0_V1逐候选对照.csv").open(encoding="utf-8"))}
_fr, _meta = SP.load_candidates(ROOT)
_docs = SP.load_docs(ROOT)
_spans = SP.load_spans(ROOT)
_dev_chunks = {f"{_spans[c]['★ document']}@{_spans[c]['chunk_start']}"
               for c in _dev_cands if c in _spans}
_dev_docs = {(o["protocol"], o["document"]) for o in _fr.values()}

# ★ 零候选审计结果
_audit = [json.loads(l) for l in
          (OUTD / "v2e2_zero_candidate_audit.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
_zero = [(_r["protocol"], _r["rfc_id"]) for _r in _audit]

# ★ 队列 B 抽样结果（★ E2 配额求解产物）
_pick = json.loads((OUTD / "v2e2_quota_pick.json").read_text(encoding="utf-8"))
_qb_docs = {(p["proto"], p["doc"]) for p in _pick}
print(f"  ★ 队列 B 抽样涉及文档 = {len(_qb_docs)} 份")

# ★ 试点来源选择（★ ≤12 份）
# ★ 优先级：★ ① **不与队列 B 来源重叠**　② 归因 B（★ 覆盖不足，★ 有规范内容）
# 　　③ 按 BCP14 密度降序（★ 预期产出高）　④ 协议轮转
_qb_docnames = {f"{p}/{d}" for p, d in _qb_docs}
_cand_pilot = []
for _r in _audit:
    _dn = f"{_r['protocol']}/{_r['rfc_id']}"
    if _dn in _qb_docnames:
        continue
    if not _r["zero_candidate_reason"].startswith("B"):
        continue
    _cand_pilot.append((_r["★ 文档健康度"]["★ BCP14 密度"], _dn, _r))
_cand_pilot.sort(key=lambda z: (-z[0], z[1]))
# ★ 协议轮转取前 12
_pilot = []
_seen_p = collections.Counter()
for _d, _dn, _r in _cand_pilot:
    if len(_pilot) >= 12:
        break
    if _seen_p[_r["protocol"]] >= 4:
        continue
    _pilot.append(_r)
    _seen_p[_r["protocol"]] += 1
# ★ 不足 12 ⇒ 放宽「不与队列 B 重叠」（★ 记录该放宽）
_relax = False
if len(_pilot) < 12:
    _relax = True
    for _d, _dn, _r in _cand_pilot:
        if len(_pilot) >= 12:
            break
        if any(x["rfc_id"] == _r["rfc_id"] for x in _pilot):
            continue
        _pilot.append(_r)
        _seen_p[_r["protocol"]] += 1
_pilot_docs = {(x["protocol"], x["rfc_id"]) for x in _pilot}
_reserved = [(_r["protocol"], _r["rfc_id"]) for _r in _audit
             if (_r["protocol"], _r["rfc_id"]) not in _pilot_docs]
print(f"  ★ 试点来源 = {len(_pilot)} 份｜协议分布 {dict(_seen_p)}"
      f"｜★ 是否放宽队列B重叠：{_relax}")

# ★ 隔离清单（★ 逐条落盘）
_rows = []
for _r in _audit:
    _k = (_r["protocol"], _r["rfc_id"])
    if _k in _pilot_docs:
        _set, _note = "② 本轮试点来源", "★ 已用于限额 LLM 试点；★ 不得再作为独立评测来源"
    elif _k in _qb_docs:
        _set, _note = "④ 队列B 片段审核来源", "★ 已用于队列 B 的片段级人工审核"
    elif _k in _dev_docs:
        _set, _note = "① 开发来源", "★ 已有冻结候选，★ 已在开发集排除集中"
    else:
        _set, _note = "③ 未来独立评估保留", "★ 未参与试点与队列 B；★ 可作未来独立评测来源"
    _rows.append({
        "rfc_id": _r["rfc_id"], "protocol": _r["protocol"],
        "source_sha256": _r["source_sha256"],
        "★ 来源集合": _set, "★ 说明": _note,
        "zero_candidate_reason": _r["zero_candidate_reason"],
        "★ 文档健康度": _r["★ 文档健康度"],
    })
(OUTD / "v2e2_source_isolation.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in _rows) + "\n",
    encoding="utf-8")

_sum = {
    "★ 四类来源集合计数": dict(collections.Counter(r["★ 来源集合"] for r in _rows)),
    "★ 试点来源明细": [{"protocol": x["protocol"], "rfc_id": x["rfc_id"],
                  "★ BCP14 密度": x["★ 文档健康度"]["★ BCP14 密度"],
                  "★ 散文行": x["★ 文档健康度"]["散文行"]} for x in _pilot],
    "★ 未来独立评估保留来源数": len(_reserved),
    "★ 是否放宽队列B重叠（★ 记录）": _relax,
    "★ 队列B 涉及文档数": len(_qb_docs),
    "★ 文档级隔离是否可行": (not _relax),
    "★ ★ 单协议仅一份 RFC 的限制": {
        p: [d for (pp, d) in _docs if pp == p]
        for p in sorted({k[0] for k in _docs})
        if len([1 for (pp, _) in _docs if pp == p]) == 1},
}
(OUTD / "v2e2_isolation_summary.json").write_text(
    json.dumps(_sum, ensure_ascii=False, indent=2), encoding="utf-8")
print()
for _k, _v in _sum.items():
    if isinstance(_v, list) and len(_v) > 6:
        print(f"      {_k}: （{len(_v)} 项）")
    else:
        print(f"      {_k}: {json.dumps(_v, ensure_ascii=False)[:200]}")
print(f"\n  ⇒ {OUTD/'v2e2_source_isolation.jsonl'}")
