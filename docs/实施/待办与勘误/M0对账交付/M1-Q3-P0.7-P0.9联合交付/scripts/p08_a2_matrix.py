# -*- coding: utf-8 -*-
"""★ P0.8 第 2 步：★ 候选级稳定性指标 + kind 分类翻转矩阵（★ 纯离线）。

★ 分别统计（★ 不混成单一不稳定率）：
  ① 候选生成波动（★ 候选身份集合交集/并集）
  ② 类型分类波动（★ kind 翻转矩阵）
  ③ 证据定位波动（★ span/锚点/匹配行）
  ④ L1/L2 结果波动（★ final_state）
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import OUTROOT, load_jsonl, save_json, save_jsonl

runs = load_jsonl(OUTROOT / "p08_candidate_stability.jsonl")
_byblk = collections.defaultdict(list)
for r in runs:
    _byblk[(r["document"], r["chunk_start"])].append(r)


def ident(it):
    """★ 归一化候选身份（★ 语义字段 + 证据位置）。"""
    return (it.get("kind"), it.get("entity"), it.get("subject"),
            it.get("action"), it.get("object"), it.get("strength"),
            it.get("polarity"), it.get("span_line"))


def sem_ident(it):
    """★ 仅语义字段（★ 不含 span ⇒ 用于区分「语义波动」与「位置波动」）。"""
    return (it.get("entity"), it.get("subject"), it.get("action"),
            it.get("object"), it.get("strength"), it.get("polarity"))


blocks = []
flip_matrix = collections.Counter()
for (doc, start), rs in sorted(_byblk.items()):
    _sets = [{ident(i) for i in r["★ items"]} for r in rs]
    _sem = [{sem_ident(i) for i in r["★ items"]} for r in rs]
    _inter = set.intersection(*_sets) if _sets else set()
    _union = set.union(*_sets) if _sets else set()
    _sem_inter = set.intersection(*_sem) if _sem else set()
    _sem_union = set.union(*_sem) if _sem else set()
    # ★ kind 翻转矩阵（★ 按位置对齐：★ 用 entity 对齐）
    for r1 in rs:
        for r2 in rs:
            for i1 in r1["★ items"]:
                for i2 in r2["★ items"]:
                    if i1.get("entity") == i2.get("entity") and \
                            i1.get("kind") != i2.get("kind"):
                        flip_matrix[f"{i1.get('kind')} → {i2.get('kind')}"] += 1
    # ★ 字段级变化（★ 稳定候选里字段变了多少）
    _field_changed = 0
    _stable = list(_inter)
    for k in _stable:
        _vals = set()
        for r in rs:
            for i in r["★ items"]:
                if ident(i) == k:
                    _vals.add((i.get("action"), i.get("object"),
                               i.get("strength"), i.get("polarity")))
        if len(_vals) > 1:
            _field_changed += 1
    _finals = [tuple(sorted(collections.Counter(
        i["final_state"] for i in r["★ items"]).items())) for r in rs]
    blocks.append({
        "document": doc, "chunk_start": start,
        "stratum": rs[0]["stratum"], "repeats": len(rs),
        "raw_items_per_run": [r["raw_items"] for r in rs],
        "norms_per_run": [r["norms"] for r in rs],
        "kind_counts_per_run": [r["kind_counts"] for r in rs],
        "★ 身份交集": len(_inter), "★ 身份并集": len(_union),
        "★ 身份稳定性": round(len(_inter) / max(1, len(_union)), 3),
        "★ 语义交集": len(_sem_inter), "★ 语义并集": len(_sem_union),
        "★ 语义稳定性": round(len(_sem_inter) / max(1, len(_sem_union)), 3),
        "★ 候选消失数": len(_sem_union) - len(_sem_inter),
        "★ 候选新增数": len(_sem_union) - len(_sem_inter),
        "★ 字段级变化数": _field_changed,
        "★ 证据位置波动": sorted({(i.get("span_line"), i.get("span_mode"))
                             for r in rs for i in r["★ items"]}),
        "★ L1L2 结果波动": _finals,
        "★ L1L2 稳定": len(set(_finals)) == 1,
    })

# ★ 汇总
_all_ids = []
for (doc, start), rs in sorted(_byblk.items()):
    _s = set()
    for r in rs:
        for i in r["★ items"]:
            _s.add(sem_ident(i))
    _all_ids.append(_s)
_tot_inter = len(set.intersection(*_all_ids)) if _all_ids else 0
_tot_union = len(set.union(*_all_ids)) if _all_ids else 0

# ★ 进入 L1/L2 的比例（★ kind=prose_constraint 才进）
_l12 = []
for r in runs:
    _pc = [i for i in r["★ items"] if i.get("kind") == "prose_constraint"]
    _l12.append({"chunk_start": r["chunk_start"], "repeat": r["repeat_index"],
                 "total": len(r["★ items"]), "into_l12": len(_pc),
                 "rate": round(len(_pc) / max(1, len(r["★ items"])), 3)})

summary = {
    "★ ① 候选生成波动": {
        "全局身份交集": _tot_inter, "全局身份并集": _tot_union,
        "★ 全局稳定性": round(_tot_inter / max(1, _tot_union), 3),
        "★ 候选消失+新增（全局）": _tot_union - _tot_inter,
        "★ 分块明细": blocks},
    "★ ② 类型分类波动": {
        "★ kind 翻转矩阵": dict(flip_matrix),
        "★ 翻转次数合计": sum(flip_matrix.values()),
        "★ prose_constraint→prose_semantics 次数": flip_matrix.get(
            "prose_constraint → prose_semantics", 0),
    },
    "★ ③ 证据定位波动": {
        "★ 各块 span/模式集合": {f"{b['document']}@{b['chunk_start']}":
                              b["★ 证据位置波动"] for b in blocks}},
    "★ ④ L1/L2 结果波动": {
        "★ 各块 final_state 序列": {f"{b['document']}@{b['chunk_start']}":
                               b["★ L1L2 结果波动"] for b in blocks},
        "★ 稳定的块数": sum(1 for b in blocks if b["★ L1L2 稳定"]),
        "★ 总块数": len(blocks)},
    "★ 进入 L1/L2 的比例": _l12,
    "★ 映射拒收原因": "★ 见 p08_candidate_stability.jsonl 的 items（★ 每条带 span_mode 与 final_state）",
}
save_json(OUTROOT / "p08_kind_flip_matrix.json", summary)
save_jsonl(OUTROOT / "p08_kind_flip_blocks.jsonl", blocks)
print(f"  ★ 块数 = {len(blocks)}｜runs = {len(runs)}")
print(f"  ★ 全局候选身份稳定性 = {_tot_inter}/{_tot_union} = "
      f"{summary['★ ① 候选生成波动']['★ 全局稳定性']}")
print(f"  ★ kind 翻转矩阵 = {dict(flip_matrix)}")
print(f"  ★ L1/L2 稳定块 = {summary['★ ④ L1/L2 结果波动']['★ 稳定的块数']}/{len(blocks)}")
print(f"\n  ⇒ {OUTROOT/'p08_kind_flip_matrix.json'}")
