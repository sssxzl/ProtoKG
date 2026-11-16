# -*- coding: utf-8 -*-
"""★ N1-B：★ 字段级**归因**补充（★ 区分「候选抽取缺失」与「候选判错」）。

★ ★ 关键区分（★ 本轮新发现）：
  · 候选字段**为空**但人工参考真值**有值** ⇒ ★ **候选抽取缺失**（★ 不是模型判错）
  · 候选字段**有值**但与人工参考真值**不同** ⇒ ★ **候选判错**
★ ★ condition / exception 的候选字段**原本就为空**（★ 原始候选无此字段）
  ⇒ ⇒ ★ 人工标签里**有**条件 ⇒ ⇒ ★ **这是「抽取缺失」的集中体现**
"""
import collections
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")

rows = [json.loads(l) for l in
        (OUTD / "N1-B_字段级明细.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]
FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception"]

_att = {f: collections.Counter() for f in FIELDS}
_rows = []
for r in rows:
    for d in r["★ 字段明细"]:
        f = d["field"]
        _state = d["★ 归一化后状态"]
        _cand_empty = d["★ LLM 候选"].strip().lower() in ("", "null", "none", "无")
        _human_filled = not d["B"].strip().lower() in ("", "null", "none", "无")
        if _state != "resolved":
            _att[f]["字段待仲裁（★ 不计准确率）"] += 1
            _cls = "字段待仲裁"
        elif _cand_empty and _human_filled:
            _att[f]["★ 候选抽取缺失（★ 人工有值）"] += 1
            _cls = "候选抽取缺失"
        elif _cand_empty and not _human_filled:
            _att[f]["★ 双方均缺省（★ 一致）"] += 1
            _cls = "双方均缺省"
        elif d["★ 候选是否匹配"] is True:
            _att[f]["★ 候选匹配"] += 1
            _cls = "候选匹配"
        elif d["★ 候选是否匹配"] is False:
            _att[f]["★ 候选判错"] += 1
            _cls = "候选判错"
        else:
            _att[f]["★ 不可判"] += 1
            _cls = "不可判"
        _rows.append({
            "sample_id": r["sample_id"], "分组": r["分组"],
            "★ 第一层": r["★ 第一层 规范义务存在性"],
            "★ 第二层": r["★ 第二层 候选字段完整性"],
            "field": f, "★ 归因": _cls,
            "★ A": d["A"], "★ B": d["B"], "★ LLM 候选": d["★ LLM 候选"],
            "★ 归一化后状态": _state, "★ 候选是否匹配": d["★ 候选是否匹配"],
        })

summary = {"★ 逐字段归因": {f: dict(_att[f]) for f in FIELDS}}
(OUTD / "N1-B_字段归因.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
with (OUTD / "N1-B_字段归因明细.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(_rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(_rows)

print("  ★ 逐字段归因：")
for f in FIELDS:
    print(f"      {f:11s} {dict(_att[f])}")
print(f"\n  ⇒ {OUTD/'N1-B_字段归因.json'}")
