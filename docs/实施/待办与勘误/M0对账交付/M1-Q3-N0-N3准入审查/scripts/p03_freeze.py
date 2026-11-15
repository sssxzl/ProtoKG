# -*- coding: utf-8 -*-
"""★ N1-R2 发放前检查③：★ 冻结 R 组**抽样总体**、各层候选数量与抽样概率。

★ 核心原则（★ 用户要求）：
  · ★ **总体 = 全部 156 条冻结候选**（★ 质量统计的分母必须含全部）
  · ★ **抽样框（frame）= evidence_supported 的候选**（★ 本次可审核样本的来源）
  · ★ **不可定位（23 条）与证据不足（其余）** ⇒ ★ 列入**独立风险台账**
    ⇒ ⇒ ★ **不得在总体质量统计中无声消失**
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "guard/_out/n1r2"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"

led = {json.loads(l)["sample_id"]: json.loads(l) for l in
       (OUT / "n1r2_span_ledger.jsonl").read_text(encoding="utf-8").splitlines()
       if l.strip()}
p079 = {x["candidate_id"]: x for x in
        [json.loads(l) for l in
         (ROOT / "guard/_out/m1_q3/p079/p07_candidate_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]}
packs = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (OUT / "n1r2_packs.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = it


def _kind(cid):
    """★ 知识类型分层键（★ prose_constraint / prose_semantics）。"""
    _o = FR.get(cid, {})
    return "prose_constraint" if (_o.get("constraint") or "").strip() else "prose_semantics"


# ★ 总体分层（★ 全部 156）
_pop = collections.Counter((led[c]["★ protocol"], _kind(c)) for c in led)
# ★ 抽样框（★ evidence_supported）
_frame = [c for c, r in led.items() if r["evidence_supported"]]
_frame_layers = collections.Counter((led[c]["★ protocol"], _kind(c)) for c in _frame)
# ★ R 组实际抽中（★ 从 packs 取）
_R = [c for c, p in packs.items() if p["分组"] == "R"]
_K = [c for c, p in packs.items() if p["分组"] == "K"]
_R_layers = collections.Counter((led[c]["★ protocol"], _kind(c)) for c in _R)
_K_layers = collections.Counter((led[c]["★ protocol"], _kind(c)) for c in _K)

# ★ 风险台账（★ 不进本次样本 ⇒ 但必须留痕）
_sel_ids = set(_R) | set(_K)
_risk = []
for cid, r in sorted(led.items()):
    if cid in _sel_ids:
        continue                       # ★ 本次已抽中 ⇒ 不进风险台账
    if r["span_mode"] in ("not_found", "out_of_range"):
        _cat = "unlocatable"          # ★ 23 条：绝对/相对均未命中或越界
    elif not r["evidence_supported"]:
        _cat = "insufficient_evidence"   # ★ 33 条：命中但锚点空/证据句缺失
    else:
        # ★ ★ 50 条：★ **证据充分但未被抽中**（★ 抽样框内剩余）
        _cat = "not_sampled_in_frame"
        r = dict(r)
        r["★ 可否恢复"] = "★ 证据充分；★ 可在后续批次按同一抽样规则补抽"
        _risk.append({
            "candidate_id": cid, "protocol": r["★ protocol"],
            "document": r["★ document"], "raw_span": r["raw_span"],
            "resolved_span": r["resolved_span"], "span_mode": r["span_mode"],
            "within_chunk": r["within_chunk"],
            "★ 风险类别": _cat, "reason": r["reason"],
            "★ 一级分类": p079.get(cid, {}).get("一级分类"),
            "★ 最终状态": p079.get(cid, {}).get("★ 最终状态"),
            "★ 处置": "★ **不进入本次可审核样本**；★ 但**计入总体分母**（★ 不无声消失）",
            "★ 可否恢复": r["★ 可否恢复"],
        })
        continue
    _risk.append({
        "candidate_id": cid, "protocol": r["★ protocol"],
        "document": r["★ document"], "raw_span": r["raw_span"],
        "resolved_span": r["resolved_span"], "span_mode": r["span_mode"],
        "within_chunk": r["within_chunk"],
        "★ 风险类别": _cat, "reason": r["reason"],
        "★ 一级分类": p079.get(cid, {}).get("一级分类"),
        "★ 最终状态": p079.get(cid, {}).get("★ 最终状态"),
        "★ 处置": "★ **不进入本次可审核样本**；★ 但**计入总体分母**（★ 不无声消失）",
        "★ 可否恢复": "★ 需人工判定是否可人工定位（★ 不由模型臆造）",
    })

# ★ 抽样概率（★ R 组各层：抽中数 / 抽样框该层数）
_prob = {}
for _k in sorted(_frame_layers):
    _n_frame = _frame_layers[_k]
    _n_sel = _R_layers.get(_k, 0)
    _prob[f"{_k[0]}/{_k[1]}"] = {
        "★ 总体该层候选数": _pop.get(_k, 0),
        "★ 抽样框该层候选数": _n_frame,
        "★ R 组抽中数": _n_sel,
        "★ 层内抽样概率": round(_n_sel / _n_frame, 4) if _n_frame else None,
        "★ 层内未抽中数": _n_frame - _n_sel,
    }

freeze = {
    "★ 总体（population）": {
        "定义": "★ **全部 156 条冻结候选**（★ 质量统计的分母必须含全部）",
        "总数": len(led),
        "★ 分层候选数（protocol × kind）": {f"{k[0]}/{k[1]}": v
                                     for k, v in sorted(_pop.items())},
    },
    "★ 抽样框（frame）": {
        "定义": "★ evidence_supported 的候选（★ 本次可审核样本的来源）",
        "总数": len(_frame),
        "★ 分层候选数": {f"{k[0]}/{k[1]}": v
                    for k, v in sorted(_frame_layers.items())},
    },
    "★ 本次可审核样本": {
        "R（分层随机）": {"条数": len(_R), "分层": {f"{k[0]}/{k[1]}": v
                                for k, v in sorted(_R_layers.items())}},
        "K（风险富集）": {"条数": len(_K), "分层": {f"{k[0]}/{k[1]}": v
                                for k, v in sorted(_K_layers.items())}},
        "★ 合计": len(_R) + len(_K),
    },
    "★ R 组抽样概率（层内）": _prob,
    "★ ★ 风险台账（★ 不进本次样本，★ 但计入总体分母）": {
        "总数": len(_risk),
        "★ 分类": dict(collections.Counter(r["★ 风险类别"] for r in _risk)),
        "明细": _risk,
    },
    "★ ★ 总体口径核对": {
        "总体总数": len(led),
        "可审核样本": len(_R) + len(_K),
        "风险台账": len(_risk),
        "★ 对账": len(_R) + len(_K) + len(_risk) == len(led),
    },
}
(OUT / "n1r2_sampling_freeze.json").write_text(
    json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
# ★ 风险台账（★ 独立文件，★ 供人工查阅）
(DELIV / "N1_风险台账_未纳入本次审核.csv").write_text(
    "sample_id,protocol,document,raw_span,resolved_span,span_mode,"
    "within_chunk,★ 风险类别,reason,★ 处置\n" + "\n".join(
        ",".join([r["candidate_id"], r["protocol"], r["document"],
                  str(r["raw_span"]), str(r["resolved_span"]),
                  str(r["span_mode"]), str(r["within_chunk"]),
                  f'"{r["★ 风险类别"]}"', f'"{r["reason"]}"',
                  f'"{r["★ 处置"]}"'])
        for r in _risk) + "\n", encoding="utf-8")

print(f"  ★ 总体 = {len(led)}（★ 全部冻结候选）")
print(f"  ★ 抽样框 = {len(_frame)}（★ evidence_supported）")
print(f"  ★ 本次样本 = R {len(_R)} + K {len(_K)} = {len(_R)+len(_K)}")
print(f"  ★ 风险台账 = {len(_risk)}"
      f"（{dict(collections.Counter(r['★ 风险类别'] for r in _risk))}）")
print(f"  ★ ★ 对账：{len(_R)+len(_K)+len(_risk)} == {len(led)} ⇒ "
      f"{len(_R)+len(_K)+len(_risk) == len(led)}")
print()
print("  ★ R 组分层抽样概率：")
for _k, _v in _prob.items():
    print(f"      {_k:28s} 总体 {_v['★ 总体该层候选数']:3d}｜"
          f"抽样框 {_v['★ 抽样框该层候选数']:3d}｜抽中 {_v['★ R 组抽中数']:3d}"
          f"｜概率 {_v['★ 层内抽样概率']}")
print(f"\n  ⇒ {OUT/'n1r2_sampling_freeze.json'}")
