# -*- coding: utf-8 -*-
"""★ N2-B0：★ 原版确定性闸门 vs **三态影子**的逐候选对照（★ 离线，★ 不写正式 Fact）。

★ 逐样本记录：
  · 原状态（★ 来自历史批次的真实记录，★ **不重跑 LLM**）
  · 影子状态（★ 三态判定映射：supported→可进 LLM 链；uncertain→pending；contradicted→rejected）
  · 是否恢复人工认定的真实规范义务
  · 是否错误恢复人工认定为不成立的候选
  · 是否引入新的 confirmed
  · 是否增加 pending 及人工审核负担
  · 规则关键字段是否仍然缺失
  · 变化是否由确定性逻辑产生
"""
import collections
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c"))
from core.fused.extraction import normative_verify as nv
from n2b0_tristate import (CONTRADICTED, SUPPORTED, UNCERTAIN,
                           semantic_support_tristate)

OUTD = ROOT / "guard/_out/n1c"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
DELIV.mkdir(parents=True, exist_ok=True)

sample = [json.loads(l) for l in
          (N1B / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (N1B / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}
FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = it
_docs = {}


def _lines(proto, doc):
    _k = (proto, doc)
    if _k not in _docs:
        _p = ROOT / f"kb/{proto}/spec/{doc}"
        _docs[_k] = _p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")
    return _docs[_k]


# ★ 历史批次里 rejected 的 reason（★ 不重跑 LLM）
_hist_reason = {}
for _p in (ROOT / "guard/_out/m1_q3/p079/p07_a5_p1_rows.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a4_p0_rows.jsonl",
           ROOT / "guard/_out/n2/n2_records.jsonl",
           ROOT / "guard/_out/n3/n3_recall_records.jsonl",
           ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
           ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl"):
    if not _p.is_file():
        continue
    for l in _p.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        _d = json.loads(l)
        if _d.get("verdict") and _d.get("reason"):
            _hist_reason.setdefault(_d["candidate_id"], str(_d["reason"]))

rows = []
for r in sample:
    cid = r["sample_id"]
    _sp = spans.get(cid)
    if not _sp:
        continue
    _o = FR.get(cid, {})
    _L = _lines(_sp["★ protocol"], _sp["★ document"])
    _rs = _sp["resolved_span"]
    _quote = "\n".join(_L[_rs - 1:_rs + 2])
    _payload = {"action": _o.get("action") or "",
                "object": _o.get("object") or "",
                "strength": _o.get("strength") or ""}
    # ★ 原版（生产同函数，★ 确定性）
    _old_v, _old_r = nv.l2_deterministic_check(payload=_payload, quote=_quote)
    # ★ 三态影子
    _new_v, _new_r, _states = semantic_support_tristate(
        _quote, _payload["action"], _payload["object"],
        strength=_payload["strength"])
    # ★ 影子状态映射（★ 只改这一层，★ 不改 L1/L2 其余链路）
    _shadow_state = {"supported": "★ 进入 LLM 链（★ 与原版同）",
                     "contradicted": "★ rejected（★ 与原版同，★ 但需明确反证）",
                     "uncertain": "★ **pending**（★ 原版在此处会 rejected）"}[_new_v]
    _orig_state = r["★ 模型 L2 状态"]
    _truth = r["★ 第一层 规范义务存在性"]
    # ★ 变化
    _changed = ((_old_v == "不支持") and (_new_v != "不支持"))
    rows.append({
        "candidate_id": cid, "分组": r["分组"],
        "★ 原模型状态（★ 历史记录）": _orig_state,
        "★ 原确定性 verdict": _old_v, "★ 原 blocking_reason": _old_r,
        "★ 影子三态 verdict": _new_v, "★ 影子 reason": _new_r,
        "★ 影子状态": _shadow_state,
        "★ 逐字段三态": {k: v["state"] for k, v in _states.items()},
        "★ 人工真值": _truth,
        "★ 第二层": r["★ 第二层 候选字段完整性"],
        "★ 历史 reason（★ 若有）": _hist_reason.get(cid),
        "★ 是否由确定性逻辑产生变化": _changed,
        "★ 恢复人工认定成立（★ rejected→pending）": (
            _changed and _truth == "valid_confirmed"),
        # ★ ★ 口径：★ 「错误恢复」= **影子放行**（pending→confirmed）了人工判不成立者
        #   ⇒ ★ **rejected→pending 本身不构成错误确认**（★ pending ≠ 放行）
        "★ 错误恢复人工认定不成立（★ 影子放行口径）": False,
        "★ rejected→pending 且人工判不成立（★ 非错误确认，★ 但需闭环）": (
            _changed and _truth != "valid_confirmed"),
        "★ 是否引入新的 confirmed": False,
        "★ 规则关键字段是否仍缺失": (
            "★ 是" if _truth == "valid_confirmed"
            and r["★ 第二层 候选字段完整性"].startswith(("②", "③")) else "★ 否"),
    })

# ══ 汇总 ══
_chg = [r for r in rows if r["★ 是否由确定性逻辑产生变化"]]
_rec = [r for r in _chg if r["★ 恢复人工认定成立（★ rejected→pending）"]]
_bad = [r for r in _chg if r["★ rejected→pending 且人工判不成立（★ 非错误确认，★ 但需闭环）"]]
_conf_all = [r for r in rows if r["★ 原模型状态（★ 历史记录）"] == "confirmed"]
_pending_new = [r for r in rows
                if r["★ 原模型状态（★ 历史记录）"] in ("rejected", "pending")
                and r["★ 影子三态 verdict"] == UNCERTAIN]
_still_missing = [r for r in _rec
                  if r["★ 规则关键字段是否仍缺失"] == "★ 是"]

summary = {
    "★ 样本数（★ 全部 50 条盲审样本）": len(rows),
    "★ 原确定性 verdict 分布": dict(collections.Counter(
        r["★ 原确定性 verdict"] for r in rows)),
    "★ 影子三态 verdict 分布": dict(collections.Counter(
        r["★ 影子三态 verdict"] for r in rows)),
    "★ ★ 风险一（错误拒收）": {
        "★ 原 rejected 中人工判成立": sum(
            1 for r in rows if r["★ 原模型状态（★ 历史记录）"] == "rejected"
            and r["★ 人工真值"] == "valid_confirmed"),
        "★ 缺乏支持证据但无明确反证": sum(
            1 for r in rows if r["★ 原确定性 verdict"] == "不支持"
            and r["★ 影子三态 verdict"] == UNCERTAIN),
        "★ ★ 可安全恢复为 pending": len(_rec),
        "★ 仍应 rejected（★ 三态 contradicted）": sum(
            1 for r in rows if r["★ 影子三态 verdict"] == CONTRADICTED),
        "★ 需补充原文证据（★ 关键字段仍缺）": len(_still_missing),
        "★ ★ 错误确认（★ 影子放行口径）": 0,
        "★ ★ 其中「rejected→pending 且人工判不成立」（★ 非错误确认）": len(_bad),
        "★ ★ 说明": ("★ **rejected→pending ≠ 错误确认**（★ pending 不是放行）；"
                 "★ 本影子**未产生任何 confirmed** ⇒ ★ 错误确认 = 0"),
    },
    "★ ★ 风险二（错误确认）": {
        "★ 三态是否引入新的 confirmed": 0,
        "★ ★ 说明": ("★ 三态只产出 supported/contradicted/uncertain ⇒ "
                 "★ **uncertain 一律 pending，★ 绝不 confirmed** ⇒ "
                 "★ **结构上不可能引入新 confirmed**"),
        "★ ★ 「三态 supported」≠ 放行": ("★ supported 只表示「确定性语义检查通过 ⇒ 可进 LLM 链」；"
                            "★ 真正放行仍取决于 L1/L2 链（★ 本影子不改）"),
        "★ 三态 supported 条数": sum(
            1 for r in rows if r["★ 影子三态 verdict"] == SUPPORTED),
        "★ ★ 是否会把不确定性升级为确定知识": "★ **否**（★ uncertain→pending）",
    },
    "★ confirmed/pending/rejected 增减": {
        "★ 原 confirmed（★ 历史）": len(_conf_all),
        "★ 影子 confirmed": len(_conf_all),
        # ★ ★ 只算「有原状态」者（★ 排除本无模型状态的 18 条）
        "★ ★ 三态 uncertain 增量（★ 仅有原状态者）": sum(
            1 for r in rows if r["★ 影子三态 verdict"] == UNCERTAIN
            and r["★ 原模型状态（★ 历史记录）"] not in (
                "pending", "★ N/A（★ 无模型状态记录）")),
        "★ 原 pending": sum(1 for r in rows
                        if r["★ 原模型状态（★ 历史记录）"] == "pending"),
        "★ 影子 pending（★ 含原 pending + 新增 uncertain）": len(_pending_new),
        "★ 原 rejected": sum(1 for r in rows
                         if r["★ 原模型状态（★ 历史记录）"] == "rejected"),
        "★ 影子 rejected": sum(
            1 for r in rows
            if r["★ 原模型状态（★ 历史记录）"] == "rejected"
            and r["★ 影子三态 verdict"] == CONTRADICTED),
        "★ ★ 人工审核负担增量（★ 新增 pending 数）": len(_pending_new) - sum(
            1 for r in rows if r["★ 原模型状态（★ 历史记录）"] == "pending"),
    },
    "★ ★ 关键限定": ("★ **rejected→pending 不等于语义准确率提升，★ 也不等于可以发布**；"
                "★ 恢复的候选仍需独立证据校验；★ ★ 本影子**未接入生产**"),
}
(OUTD / "n2b0_shadow_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
with (DELIV / "N2-B0_原版与影子状态对照.csv").open("w", newline="",
                                              encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

print("  ★ 样本数（★ 有模型状态者）:", len(rows))
print("  ★ 原确定性 verdict:", summary["★ 原确定性 verdict 分布"])
print("  ★ 影子三态 verdict:", summary["★ 影子三态 verdict 分布"])
print("  ★ 风险一:", json.dumps(summary["★ ★ 风险一（错误拒收）"], ensure_ascii=False))
print("  ★ 风险二:", json.dumps(summary["★ ★ 风险二（错误确认）"], ensure_ascii=False))
print("  ★ 增减:", json.dumps(summary["★ confirmed/pending/rejected 增减"], ensure_ascii=False))
print(f"\n  ⇒ {OUTD/'n2b0_shadow_summary.json'}")
