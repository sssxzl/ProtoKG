# -*- coding: utf-8 -*-
"""★ N1-B 统计复核（★ §二 六项口径逐一核实 + 术语修正）。

★ **原则**：★ 不改原始人工标签；★ 只修统计报告与复算脚本。
★ 复核对象：★ N1-B 的全部关键数字，★ 从冻结产物**重新计算**并与报告文本比对。
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")

frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
sample = [json.loads(l) for l in
          (OUTD / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
sens = {json.loads(l)["sample_id"]: json.loads(l) for l in
        (OUTD / "N1-B_口径敏感性逐样本.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()}
model = {json.loads(l)["candidate_id"]: json.loads(l) for l in
         (OUTD / "N1-B_模型状态关联明细.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}
NA = "★ N/A（★ 无模型状态记录）"

R = {}
# ══ ① 11/12 = 91.67% 的来源 ══
_stable = [r for r in sample if r["★ 计入单批次指标"]]
_rej = [r for r in _stable if r["★ 模型 L2 状态"] == "rejected"]
_rej_miss = [r for r in _rej if r["★ 第一层 规范义务存在性"] == "valid_confirmed"]
R["① 误拒收 11/12"] = {
    "★ 分子定义": "★ 模型 L2=rejected 且人工 truth_label=valid_confirmed",
    "★ 分母定义": "★ 模型 L2=rejected 的**单批次口径**样本",
    "★ k": len(_rej_miss), "★ n": len(_rej),
    "★ 率": round(len(_rej_miss) / len(_rej), 4) if _rej else "N/A",
    "★ 分母样本逐条": [{"sample_id": r["sample_id"], "分组": r["分组"],
                   "batch": r["★ 主口径 batch"], "run_id": r["★ 主口径 run_id"],
                   "model_L2": r["★ 模型 L2 状态"],
                   "人工真值": r["★ 第一层 规范义务存在性"],
                   "★ 是误拒": r in _rej_miss} for r in _rej],
    "★ ★ 术语修正": ("★ **不得**称「全系统误拒收率」或「系统性总体错误率」；"
                 "★ 应称**「在本批 50 条 R+K 样本、单批次口径、"
                 "模型 rejected 子集上的条件性误拒收结果」**"),
}

# ══ ② 跨批不一致 14 vs 9：单位核实 ══
_u14 = [r for r in sample if r["★ 跨批次不稳定"]]
_u9 = [sid for sid, v in sens.items() if v.get("★ 跨批不一致")]
R["② 跨批不一致 14 vs 9"] = {
    "★ 14 的单位": "★ **全部 50 条样本**内，★ 有模型状态且跨批判定不一致",
    "★ 14 的计数": len(_u14),
    "★ 9 的单位": "★ **有模型状态的 32 条**内（★ 口径敏感性脚本的统计范围）",
    "★ 9 的计数": len(_u9),
    "★ ★ 差异来源": ("★ **不是矛盾**（★ 单位不同）⇒ ★ 但 ★ **报告文本必须写清单位**，"
                 "★ 否则易被读成互相矛盾"),
    "★ 14 里有模型状态者": len([r for r in _u14
                          if r["★ 模型 L2 状态"] != NA]),
    "★ 修正建议": "★ 统一表述为：**50 条样本内 14 条；其中有模型状态的 32 条内 9 条**",
}

# ══ ③ 单批 confirmed=0 vs 现行放行 3 条 ══
_conf_stable = [r for r in _stable if r["★ 模型 L2 状态"] == "confirmed"]
_conf_all = [r for r in sample if r["★ 模型 L2 状态"] == "confirmed"]
R["③ confirmed=0 vs 现行放行 3 条"] = {
    "★ 单批次口径 confirmed": len(_conf_stable),
    "★ 全部有模型状态样本中的 confirmed": len(_conf_all),
    "★ ★ 差异来源": ("★ **是不同口径**：★ 单批次口径**先剔除了跨批不一致者**（14 条），"
                 "★ 而「现行放行 3 条」统计的是**全部 32 条有状态样本**里的 confirmed；"
                 "★ ⇒ ★ **3 条 confirmed 全部落在跨批不一致集合内**"),
    "★ 3 条 confirmed 逐条": [{"sample_id": r["sample_id"], "分组": r["分组"],
                       "主口径 batch": r["★ 主口径 batch"],
                       "主口径 L2": r["★ 模型 L2 状态"],
                       "跨批不一致": r["★ 跨批次不稳定"],
                       "全部批次判定": sens.get(r["sample_id"], {}).get(
                           "★ 全部批次判定"),
                       "人工真值": r["★ 第一层 规范义务存在性"]}
                      for r in _conf_all],
    "★ ★ 结论": "★ **两个数字都对，★ 但必须并列说明口径**；★ 单批次口径下 confirmed=0 ⇒ "
            "★ **confirmed precision 只能以多口径报告**",
}

# ══ ④ 24 条成立 vs 7 条 fully supported 的对应 ══
_vc = [r for r in sample if r["★ 第一层 规范义务存在性"] == "valid_confirmed"]
_es = collections.Counter(r["★ 人工 evidence_support"] for r in _vc)
R["④ 24 成立 vs 7 fully supported"] = {
    "★ 成立总数": len(_vc),
    "★ 其中 evidence_support 分布": dict(_es),
    "★ supported（= fully supported）": _es.get("supported", 0),
    "★ partially_supported": _es.get("partially_supported", 0),
    "★ contradicted": _es.get("contradicted", 0),
    "★ ★ 说明": "★ **7 条 fully supported ⊂ 24 条成立**；★ 其余 17 条「义务成立但字段仅部分支持」",
    "★ 第二层交叉": dict(collections.Counter(
        r["★ 第二层 候选字段完整性"] for r in _vc)),
}

# ══ ⑤ 七字段可判分母与仲裁缺口 ══
fields = [json.loads(l) for l in
          (OUTD / "N1-B_字段级明细.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception"]
_fstats = {}
for f in FIELDS:
    _rows = [d for r in fields for d in r["★ 字段明细"] if d["field"] == f]
    _m = sum(1 for d in _rows if d["★ 候选是否匹配"] is True)
    _x = sum(1 for d in _rows if d["★ 候选是否匹配"] is False)
    _arb = sum(1 for d in _rows if d["★ 归一化后状态"] != "resolved")
    _fstats[f] = {"★ 可判分母（匹配+判错）": _m + _x, "★ 匹配": _m, "★ 判错": _x,
             "★ 准确率": (round(_m / (_m + _x), 4) if (_m + _x) else "N/A"),
             "★ 字段级仲裁缺口（★ 待仲裁条数）": _arb,
             "★ 不可判定原因": (
                 "★ 该字段 A/B 归一化后仍实质分歧 ⇒ ★ 未形成一致参考真值"
                 if _arb else "★ 该字段已全部 resolve（★ 但部分为双方均缺省）")}
R["⑤ 七字段可判分母与仲裁缺口"] = _fstats

# ══ ⑥ 仲裁者身份/日期/独立性 ══
import csv
_AR = list(csv.DictReader((ROOT / "docs/实施/待办与勘误/M0对账交付"
                           / "M1-Q3-N0-N3准入审查/N1_仲裁表.csv")
                          .read_text(encoding="utf-8").splitlines()))
_ids = set()
for r in _AR:
    _w = (r.get("★ 仲裁者") or "").strip()
    if _w and _w not in ("无需仲裁（A/B 独立判定一致）", "第三方复核"):
        _ids.add(_w)
R["⑥ 仲裁者审计"] = {
    "★ 仲裁表行数": len(_AR),
    "★ 标「无需仲裁」": sum(1 for r in _AR
                       if (r.get("★ 仲裁者") or "").strip().startswith("无需仲裁")),
    "★ 标「第三方复核」": sum(1 for r in _AR
                       if (r.get("★ 仲裁者") or "").strip() == "第三方复核"),
    "★ 具名审核者 ID 数": len(_ids),
    "★ ★ 审核日期列存在？": bool(_AR and ("★ 仲裁日期" in _AR[0])),
    "★ ★ 日期非空条数": sum(1 for r in _AR if (r.get("★ 仲裁日期") or "").strip()),
    "★ ★ 独立性记录列存在？": bool(_AR and ("★ 独立性记录" in _AR[0])),
    "★ ★ 结论": ("★ **未补齐** ⇒ ★ 仲裁来源待核实（★ 不宣称审计完备）"),
}

# ══ 与报告文本比对 ══
_reports = {}
for _f in ("N1-B_模型语义质量评估报告.md", "N1-B_人工真值冻结与一致性报告.md",
           "N2-B_确认防护准入建议.md", "N1-B_典型错误案例.md",
           "N1-B_抽样总体与统计适用范围.md"):
    _p = OUTD / _f
    if _p.is_file():
        _reports[_f] = _p.read_text(encoding="utf-8")

_consistency = []
for _f, _t in _reports.items():
    _nums = set(re.findall(r"\b(?:0\.\d{2,4}|\d{1,3}/\d{1,3})\b", _t))
    _consistency.append({"file": _f, "★ 出现的比率数字": sorted(_nums)[:30]})

(ROOT / "guard/_out/_n1c/n1b_recheck.json").write_text(json.dumps({
    "★ 复核结果": R, "★ 报告数字清单": _consistency,
}, ensure_ascii=False, indent=2), encoding="utf-8")

print("  ★ ① 误拒收 11/12：k=%d n=%d rate=%s" % (
    len(_rej_miss), len(_rej), R["① 误拒收 11/12"]["★ 率"]))
print(f"      分母样本（★ 逐条）：")
for r in R["① 误拒收 11/12"]["★ 分母样本逐条"]:
    print(f"        {r['sample_id'][:24]:26s} {r['分组']} batch={str(r['batch'])[:22]:24s}"
          f" L2={r['model_L2']:9s} 真值={r['人工真值']:16s} 误拒={r['★ 是误拒']}")
print(f"  ★ ② 跨批不一致：14={R['② 跨批不一致 14 vs 9']['★ 14 的计数']}"
      f"（50 条内）｜9={R['② 跨批不一致 14 vs 9']['★ 9 的计数']}"
      f"（32 条有状态内）｜★ 单位不同，★ 非矛盾")
print(f"  ★ ③ 单批次 confirmed={len(_conf_stable)}｜"
      f"全部有状态 confirmed={len(_conf_all)}｜★ 口径不同")
for r in R["③ confirmed=0 vs 现行放行 3 条"]["★ 3 条 confirmed 逐条"]:
    print(f"        {r['sample_id'][:24]:26s} 跨批不一致={r['跨批不一致']} "
          f"真值={r['人工真值']}")
print(f"  ★ ④ 成立 {len(_vc)} 条：evidence_support {dict(_es)}"
      f"｜第二层 {R['④ 24 成立 vs 7 fully supported']['★ 第二层交叉']}")
print("  ★ ⑤ 七字段：")
for f, v in _fstats.items():
    print(f"        {f:11s} 可判分母 {v['★ 可判分母（匹配+判错）']:2d}｜"
          f"准确率 {v['★ 准确率']}｜仲裁缺口 {v['★ 字段级仲裁缺口（★ 待仲裁条数）']:2d}")
print(f"  ★ ⑥ 仲裁者：{R['⑥ 仲裁者审计']['★ 标「第三方复核」']} 条第三方复核"
      f"｜日期列存在={R['⑥ 仲裁者审计']['★ ★ 审核日期列存在？']}"
      f"｜日期非空={R['⑥ 仲裁者审计']['★ ★ 日期非空条数']}"
      f"｜独立性列存在={R['⑥ 仲裁者审计']['★ ★ 独立性记录列存在？']}")
print(f"\n  ⇒ {ROOT/'guard/_out/_n1c/n1b_recheck.json'}")
