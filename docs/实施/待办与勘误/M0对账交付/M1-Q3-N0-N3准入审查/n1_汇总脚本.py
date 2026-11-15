# -*- coding: utf-8 -*-
"""★ N1.3：★ 人工标签回填后的统计（★ **随机样本与风险样本分开**）。"""
import collections
import csv
import json
import pathlib
import sys

FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception", "evidence_support", "final_label"]
LABEL_MAP = {
    "valid_confirmed": "confirmed", "valid_rejection": "rejected",
    "false_rejection": "rejected", "false_confirmation": "confirmed",
    "pending_insufficient_evidence": "pending",
    "uncertain_requires_human": "pending",
}


def main(csv_path):
    rows = list(csv.DictReader(pathlib.Path(csv_path).open(encoding="utf-8-sig")))
    out = {}
    for grp in ("R", "K"):
        _rs = [r for r in rows if r["sample_id"].startswith(grp + "-")]
        if not _rs:
            continue
        _lab = [r["★待标注:final_label"].strip() for r in _rs]
        _done = [x for x in _lab if x]
        _c = collections.Counter(_done)
        _ev = collections.Counter(r["★待标注:evidence_support"].strip()
                                  for r in _rs if r["★待标注:evidence_support"].strip())
        _field_sup = {}
        for f in FIELDS[:7]:
            _vals = [r["★待标注:" + f].strip() for r in _rs
                     if r["★待标注:" + f].strip()]
            _field_sup[f] = {
                "filled": len(_vals),
                "★ 非 null/无 的比例": round(
                    sum(1 for v in _vals if v.lower() not in ("null", "none", "无", "-"))
                    / max(1, len(_vals)), 3) if _vals else None,
            }
        # ★ 双审一致性
        _pairs = [r for r in _rs if r["审核者"].strip() and r["审核者2"].strip()]
        _agree = sum(1 for r in _pairs
                     if r["★待标注:final_label"].strip()
                     == r.get("★待标注:final_label_2", "").strip())
        out[grp] = {
            "样本数": len(_rs), "已标注": len(_done),
            "★ 标签分布": dict(_c),
            "★ evidence_support 分布": dict(_ev),
            "★ 正确确认比例（valid_confirmed / 已标注）": round(
                _c.get("valid_confirmed", 0) / max(1, len(_done)), 3),
            "★ false confirmation 比例": round(
                _c.get("false_confirmation", 0) / max(1, len(_done)), 3),
            "★ false rejection 比例": round(
                _c.get("false_rejection", 0) / max(1, len(_done)), 3),
            "★ 证据不足比例": round(
                _c.get("pending_insufficient_evidence", 0) / max(1, len(_done)), 3),
            "★ 六字段支持率": _field_sup,
            "★ 双审样本数": len(_pairs),
            "★ 双审一致率": round(_agree / max(1, len(_pairs)), 3) if _pairs else None,
            "★ 双审分歧样本": [r["sample_id"] for r in _pairs
                          if r["★待标注:final_label"].strip()
                          != r.get("★待标注:final_label_2", "").strip()],
        }
    out["★ 说明"] = ("★ R（随机分层）可用于估计总体；★ K（风险富集）**不可**用于估计总体"
                     "★ ⇒ 两者分开统计")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "N1_人工标注表.csv")
