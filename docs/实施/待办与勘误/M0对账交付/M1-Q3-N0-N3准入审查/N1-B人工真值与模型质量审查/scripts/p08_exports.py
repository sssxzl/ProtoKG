# -*- coding: utf-8 -*-
"""★ N1-B：★ 导出混淆矩阵 CSV 与七字段一致性与错误归因 CSV。"""
import collections
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")

rows = [json.loads(l) for l in
        (OUTD / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]
fields = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_字段级明细.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
metrics = json.loads((OUTD / "N1-B_模型质量指标.json").read_text(encoding="utf-8"))

NA = "★ N/A（★ 无模型状态记录）"
_stable = [r for r in rows if r["★ 计入单批次指标"]]
_allm = [r for r in rows if r["★ 模型 L2 状态"] != NA]

# ══ ① 混淆矩阵 CSV ══
with (OUTD / "N1-B_模型与人工混淆矩阵.csv").open("w", newline="",
                                                encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["★ 口径", "★ 模型 L2 状态", "★ 人工规范义务存在性",
                "★ 样本数", "★ 占比(分母=该口径总样本)", "★ 说明"])
    for _label, _rs in (("单批次口径（★ 跨批一致者）", _stable),
                         ("全量对照（★ 含跨批不一致与无状态）", _allm)):
        _c = collections.Counter((r["★ 模型 L2 状态"],
                                  r["★ 第一层 规范义务存在性"]) for r in _rs)
        for (m, t), n in sorted(_c.items()):
            w.writerow([_label, m, t, n,
                        round(n / max(1, len(_rs)), 4),
                        "★ 行=模型 L2，★ 列=人工规范真值（★ 第一层）"])
    w.writerow([])
    w.writerow(["★ 指标", "★ 分子", "★ 分母", "★ 值", "★ CI95(Wilson)", "★ 定义"])
    _m1 = metrics["★ 1 confirmed precision"]
    w.writerow(["confirmed precision", _m1["k"], _m1["n"], _m1["rate"],
                str(_m1["★ CI95(Wilson)"]),
                "★ valid_confirmed / (模型 confirmed)；★ **分母=模型 confirmed 样本**"])
    w.writerow(["错误确认（口径①义务不存在）",
                _m1["★ 错误确认（★ 口径①：规范义务不存在）"]["k"],
                _m1["★ 错误确认（★ 口径①：规范义务不存在）"]["n"],
                _m1["★ 错误确认（★ 口径①：规范义务不存在）"]["rate"],
                str(_m1["★ 错误确认（★ 口径①：规范义务不存在）"]["★ CI95(Wilson)"]),
                "★ 人工判 valid_rejection 但模型 confirmed"])
    w.writerow(["错误确认（口径②字段错误）",
                _m1["★ 错误确认（★ 口径②：义务存在但关键字段缺失/错误）"]["k"],
                _m1["★ 错误确认（★ 口径②：义务存在但关键字段缺失/错误）"]["n"],
                _m1["★ 错误确认（★ 口径②：义务存在但关键字段缺失/错误）"]["rate"],
                str(_m1["★ 错误确认（★ 口径②：义务存在但关键字段缺失/错误）"]["★ CI95(Wilson)"]),
                "★ 人工判 valid_confirmed 但第二层为②/③"])
    _m2 = metrics["★ 2 rejected 统计（★ 与 pending 分开）"]
    w.writerow(["错误拒收（rejected）", _m2["k"], _m2["n"], _m2["rate"],
                str(_m2["★ CI95(Wilson)"]),
                "★ 人工判 valid_confirmed 但模型 rejected；★ **pending 不计入**"])
    _m3 = metrics["★ 3 pending 统计（★ ★ pending 不是自动意义上的错误拒收）"]
    w.writerow(["有效知识被 pending 隔离", _m3["k"], _m3["n"], _m3["rate"],
                str(_m3["★ CI95(Wilson)"]),
                "★ 人工判 valid_confirmed 但模型 pending；★ **pending ≠ 错误拒收**"])

# ══ ② 七字段一致性与错误归因 CSV ══
with (OUTD / "N1-B_七字段一致性与错误归因.csv").open("w", newline="",
                                                  encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["sample_id", "分组", "★ 第一层 规范义务存在性",
                "★ 第二层 候选字段完整性", "★ evidence_support",
                "字段", "★ A 填写", "★ B 填写", "★ 归一化A", "★ 归一化B",
                "★ 归一化后状态", "★ LLM 候选字段", "★ 候选是否匹配",
                "★ 模型 L2 状态", "★ 跨批不一致", "★ 失效环节",
                "★ 推荐修复点"])
    _fix = {
        "subject": "★ 主体归属：★ 区分规范要求主体 vs 语法主语；★ 指代须解析",
        "action": "★ 动作抽取：★ 跨行动作须完整；★ 勿把条件写成动作",
        "object": "★ 对象抽取：★ 跨行对象须完整；★ ★ 本字段 A/B 表达差异最大 ⇒ 需字段级仲裁",
        "strength": "★ 强度：★ MUST/SHOULD/MAY 与否定形式须有原文依据（★ 无 2119 关键词时须留空）",
        "polarity": "★ 极性：★ MUST+negative ≡ MUST NOT；★ 义务不成立时不应填极性",
        "condition": "★ 条件：★ 跨句继承的条件须显式补全；★ 无则 null",
        "exception": "★ 例外：★ 无则 null；★ 勿遗漏",
    }
    for r in rows:
        _sid = r["sample_id"]
        _fd = fields.get(_sid, {}).get("★ 字段明细") or []
        _eff = []
        if r["★ 模型 L2 状态"] == "rejected" and r["★ 第一层 规范义务存在性"] == "valid_confirmed":
            _eff.append("★ 拒收闸门过严")
        if r["★ 跨批次不稳定"]:
            _eff.append("★ L2 非确定")
        if r["★ 第二层 候选字段完整性"].startswith(("②", "③")):
            _eff.append("★ 字段抽取不完整")
        for d in _fd:
            w.writerow([
                _sid, r["分组"], r["★ 第一层 规范义务存在性"],
                r["★ 第二层 候选字段完整性"], r["★ 人工 evidence_support"],
                d["field"], d["A"], d["B"], d["norm_A"], d["norm_B"],
                d["★ 归一化后状态"], d["★ LLM 候选"],
                d["★ 候选是否匹配"], r["★ 模型 L2 状态"],
                r["★ 跨批次不稳定"], "；".join(_eff) or "★ 无",
                _fix.get(d["field"], "")])
print("  ★ 已导出：N1-B_模型与人工混淆矩阵.csv、N1-B_七字段一致性与错误归因.csv")
