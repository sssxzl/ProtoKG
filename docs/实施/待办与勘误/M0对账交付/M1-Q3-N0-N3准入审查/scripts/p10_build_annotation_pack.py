# -*- coding: utf-8 -*-
"""★ N1.1：★ 生成 **50 条匿名化人工复核包**（★ Agent 只负责包，★ 标签须独立人工提供）。

★ 设计要点：
  ① 30 条**分层随机抽样**（★ 按知识类型 / 状态 / 协议分层）
  ② 20 条**风险富集**（★ confirmed 波动 / 疑似误确认 / 误拒 / 指代 / 极性 / 跨句）
  ③ ★ **隐藏 L2 结论与 Agent 推荐结论**（★ 只给原文 + 候选字段 + 证据位置）
  ④ 每个样本标注 9 个字段；★ 允许 `evidence_insufficient`
  ⑤ 随机分层样本与风险富集样本**分开统计**（★ 不混合估计总体错误率）
"""
import collections
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction import normative_rule as nr

OUT = ROOT / "guard/_out/n1"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
OUT.mkdir(parents=True, exist_ok=True)
DELIV.mkdir(parents=True, exist_ok=True)
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

ledger = [json.loads(l) for l in
          (ROOT / "guard/_out/m1_q3/p079/p07_candidate_ledger.jsonl")
          .read_text(encoding="utf-8").splitlines() if l.strip()]
orig = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        orig[f"{b['document']}@{b['chunk_start']}#{i}"] = {**it,
                                                          "chunk_start": b["chunk_start"]}

# ★ 只取「进入过 L2 / 有真实 API 判定」的候选（★ 否则人工无从判断语义）
_cand = [x for x in ledger
         if x["一级分类"] in ("paired_reviewed", "eligible_unreviewed")
         and x["candidate_id"] in orig]

_rng = random.Random(20261116)

# ══ ② 风险富集 20 条 ══
_risk_pool = []
for x in _cand:
    _t = set(x["★ 风险标签"])
    _w = 0
    if x["candidate_id"] in ("rfc3261.txt@1842#2", "rfc3261.txt@12767#1"):
        _w += 5                       # ★ confirmed 波动 / false rejection
    if "coreference_subject" in _t:
        _w += 4
    if "strength_polarity_anomaly" in _t:
        _w += 3
    if "subject_ne_entity" in _t:
        _w += 3
    if "cross_chunk_evidence" in _t:
        _w += 2
    if "l2_state_migrated" in _t:
        _w += 2
    if x["★ 最终状态"] == "pending_manual_review":
        _w += 3
    if _w:
        _risk_pool.append((_w, x["candidate_id"]))
_risk_pool.sort(key=lambda z: (-z[0], z[1]))
_risk_ids = [cid for _, cid in _risk_pool[:20]]

# ══ ① 分层随机 30 条（★ 按协议 × 知识类型分层）══
_strata = collections.defaultdict(list)
for x in _cand:
    _cid = x["candidate_id"]
    if _cid in _risk_ids:
        continue
    _kind = "constraint" if orig[_cid].get("constraint") else "semantics"
    _strata[(x["protocol"], _kind)].append(_cid)
_random_ids = []
_keys = sorted(_strata)
_i = 0
while len(_random_ids) < 30 and _i < 200:
    _k = _keys[_i % len(_keys)]
    _lst = _strata[_k]
    if _lst:
        _cid = _lst.pop(_rng.randrange(len(_lst)))
        if _cid not in _random_ids:
            _random_ids.append(_cid)
    _i += 1

print(f"  ★ 候选池 = {len(_cand)}｜分层随机 {len(_random_ids)} 条｜风险富集 {len(_risk_ids)} 条")


def _pack(cid, group):
    x = [y for y in ledger if y["candidate_id"] == cid][0]
    o = orig[cid]
    _doc = ROOT / f"kb/{x['protocol']}/spec/{x['document']}"
    L = _doc.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _sp = o.get("raw_span")
    _anchor = _sp if isinstance(_sp, int) else None
    _ctx = []
    if _anchor and 1 <= _anchor <= len(L):
        for _i in range(max(1, _anchor - 4), min(len(L), _anchor + 4) + 1):
            _ctx.append({"line": _i, "text": L[_i - 1]})
    return {
        "★ sample_id": f"{group}-{cid}",
        "★ 分组": group,
        "protocol": x["protocol"], "document": x["document"],
        "chunk_id": x.get("chunk_id"),
        "★ 原始位置": {"raw_span": _sp, "chunk_start": o.get("chunk_start")},
        "★ 原文上下文": _ctx,
        "★ 候选字段": {
            "entity": o.get("entity"),
            "normative_subject": o.get("normative_subject"),
            "action": o.get("action"),
            "object": o.get("object"),
            "strength": o.get("strength"),
            "polarity": o.get("polarity"),
            "condition": o.get("constraint"),
            "exception": o.get("exception"),
        },
        "★ 候选原始文本": {
            "meaning": o.get("meaning"), "constraint": o.get("constraint"),
        },
        "★ 待标注字段（★ 请填）": {
            "subject": None, "action": None, "object": None,
            "strength": None, "polarity": None, "condition": None,
            "exception": None,
            "evidence_support": None,      # supported / partially_supported / contradicted / evidence_insufficient
            "final_label": None,           # valid_confirmed / valid_rejection / false_rejection / false_confirmation / pending_insufficient_evidence / uncertain_requires_human
        },
        "★ 审核者": None, "★ 审核者2": None, "★ 仲裁": None,
        "★ 备注": None,
    }


packs = ([_pack(c, "R") for c in _random_ids]
          + [_pack(c, "K") for c in _risk_ids])

# ★ ★ 确认包内**不含** L2 结论 / Agent 推荐结论
_leak = []
for p in packs:
    _s = json.dumps(p, ensure_ascii=False)
    for _w in ("l2_verdict", "final_state", "l1_l2", "old_l1_l2", "new_l1_l2",
               "semantic_review", "★ 结论", "★ 分类"):
        if _w in _s:
            _leak.append((p["★ sample_id"], _w))
print(f"  ★ 包内**泄漏检查**：{_leak or '★ 无泄漏'}")

(OUT / "n1_annotation_pack.jsonl").write_text(
    "\n".join(json.dumps(p, ensure_ascii=False) for p in packs) + "\n",
    encoding="utf-8")
(OUT / "n1_pack_meta.json").write_text(json.dumps({
    "total": len(packs),
    "随机分层": len(_random_ids), "风险富集": len(_risk_ids),
    "★ 协议分布": dict(collections.Counter(p["protocol"] for p in packs)),
    "★ 分组分布": dict(collections.Counter(p["★ 分组"] for p in packs)),
    "★ 泄漏检查": _leak,
    "★ random_seed": 20261116,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  ★ 协议分布: {dict(collections.Counter(p['protocol'] for p in packs))}")
print(f"\n  ⇒ {OUT/'n1_annotation_pack.jsonl'}")
