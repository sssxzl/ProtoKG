# -*- coding: utf-8 -*-
"""★ N1-B 第 4 步：★ **揭盲** —— 混淆矩阵与模型质量指标（★ 严格分母定义）。

★ ★ 用户指定的分母规则：
  · confirmed precision 的**分母是模型 confirmed 样本**，★ **不是**全部 50 条
  · 错误确认**分两种口径**：★ 「规范义务不存在」与★ 「义务存在但关键字段错误」
  · rejected 与 pending **分别统计**
  · ★ pending **不是**自动意义上的错误拒收
  · ★ **不允许**用 24/50 表示模型 confirmed precision
  · 小样本比例给**置信区间**并明确不确定性
★ ★ **跨批次不稳定的候选单列，★ 不计入单批次指标**
★ ★ **无模型状态者 ⇒ 该类指标 N/A**
"""
import collections
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")

frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
fieldrows = {json.loads(l)["sample_id"]: json.loads(l) for l in
             (OUTD / "N1-B_字段级明细.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()}
model = {json.loads(l)["candidate_id"]: json.loads(l) for l in
         (OUTD / "N1-B_模型状态关联明细.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}


def _wilson(k, n, z=1.96):
    """★ Wilson 区间（★ 小样本比例的合理置信区间）。"""
    if not n:
        return None
    _p = k / n
    _d = 1 + z * z / n
    _c = _p + z * z / (2 * n)
    _m = z * math.sqrt(_p * (1 - _p) / n + z * z / (4 * n * n))
    return [round((_c - _m) / _d, 4), round((_c + _m) / _d, 4)]


def _rate(k, n):
    return {"k": k, "n": n, "rate": (round(k / n, 4) if n else "N/A"),
            "★ CI95(Wilson)": _wilson(k, n)}


rows = []
for sid, fr in sorted(frozen.items()):
    _m = model.get(sid)
    _L2 = _m["★ L2 状态"] if _m else None
    _unstable = bool(_m and _m.get("★ ★ 跨批次不稳定"))
    _truth = fr["★ ★ 冻结规范真值"]
    _sec = fieldrows.get(sid, {}).get("★ 第二层 候选字段完整性", "")
    _has_state = _L2 is not None
    _stable = _has_state and not _unstable
    rows.append({
        "sample_id": sid, "分组": fr["分组"],
        "★ 模型 L2 状态": _L2 if _has_state else "★ N/A（★ 无模型状态记录）",
        "★ 确定性短路": _m.get("★ 确定性短路") if _m else None,
        "★ 跨批次不稳定": _unstable,
        "★ 计入单批次指标": _stable,
        "★ 主口径 batch": _m.get("★ 主口径 batch") if _m else None,
        "★ 主口径 run_id": _m.get("★ 主口径 run_id") if _m else None,
        "prompt_hash": (_m.get("prompt_hash") or "")[:16] if _m else None,
        "model": _m.get("model") if _m else None,
        "★ 第一层 规范义务存在性": _truth,
        "★ 第二层 候选字段完整性": _sec,
        "★ 人工 evidence_support": fr["★ 冻结 evidence_support"],
    })

# ══ 混淆矩阵（★ 仅稳定且有模型状态者）══
_stable = [r for r in rows if r["★ 计入单批次指标"]]
_cm = collections.Counter((r["★ 模型 L2 状态"], r["★ 第一层 规范义务存在性"])
                          for r in _stable)
# ══ 全量（★ 含不稳定者，仅供对照）══
_allm = [r for r in rows if r["★ 模型 L2 状态"] not in (None, "★ N/A（★ 无模型状态记录）")]
_cm_all = collections.Counter((r["★ 模型 L2 状态"], r["★ 第一层 规范义务存在性"])
                              for r in _allm)

# ══ confirmed precision（★ 分母 = 模型 confirmed）══
_conf = [r for r in _stable if r["★ 模型 L2 状态"] == "confirmed"]
_conf_ok = [r for r in _conf if r["★ 第一层 规范义务存在性"] == "valid_confirmed"]
_conf_bad_none = [r for r in _conf
                  if r["★ 第一层 规范义务存在性"] == "valid_rejection"]
_conf_bad_field = [r for r in _conf
                   if r["★ 第二层 候选字段完整性"].startswith(("②", "③"))]
# ══ rejected / pending 分别统计 ══
_rej = [r for r in _stable if r["★ 模型 L2 状态"] == "rejected"]
_rej_miss = [r for r in _rej if r["★ 第一层 规范义务存在性"] == "valid_confirmed"]
_pend = [r for r in _stable if r["★ 模型 L2 状态"] == "pending"]
_pend_valid = [r for r in _pend if r["★ 第一层 规范义务存在性"] == "valid_confirmed"]
_pend_isolated = [r for r in _pend if r["★ 第一层 规范义务存在性"] != "valid_confirmed"]

summary = {
    "★ 口径": {
        "★ 单批次指标分母": "★ 仅「有模型状态 **且** 跨批次判定一致」的样本",
        "★ 有模型状态": sum(1 for r in rows if r["★ 模型 L2 状态"] != "★ N/A（★ 无模型状态记录）"),
        "★ 无模型状态（⇒ 相关指标 N/A）": sum(
            1 for r in rows if r["★ 模型 L2 状态"] == "★ N/A（★ 无模型状态记录）"),
        "★ 跨批次不稳定（★ 单列）": sum(1 for r in rows if r["★ 跨批次不稳定"]),
        "★ 计入单批次指标": len(_stable),
    },
    "★ 混淆矩阵（★ 单批次口径，★ 行=模型 L2，★ 列=人工规范真值）": {
        f"model={k[0]}|truth={k[1]}": v for k, v in sorted(_cm.items())},
    "★ 混淆矩阵（★ 全量对照，★ 含不稳定者）": {
        f"model={k[0]}|truth={k[1]}": v for k, v in sorted(_cm_all.items())},
    "★ 1 confirmed precision": {
        "★ 定义": "★ valid_confirmed / (模型 confirmed)，★ **分母 = 模型 confirmed 样本**",
        **_rate(len(_conf_ok), len(_conf)),
        "★ 错误确认（★ 口径①：规范义务不存在）": _rate(len(_conf_bad_none), len(_conf)),
        "★ 错误确认（★ 口径②：义务存在但关键字段缺失/错误）": _rate(len(_conf_bad_field), len(_conf)),
        "★ 错误确认样本": [{"sample_id": r["sample_id"], "分组": r["分组"],
                       "真值": r["★ 第一层 规范义务存在性"],
                       "第二层": r["★ 第二层 候选字段完整性"],
                       "evidence_support": r["★ 人工 evidence_support"]}
                      for r in _conf_bad_none + _conf_bad_field],
    },
    "★ 2 rejected 统计（★ 与 pending 分开）": {
        "★ 定义": "★ 模型 rejected 中，★ 人工判为 valid_confirmed ⇒ ★ **错误拒收（疑似误拒）**",
        **_rate(len(_rej_miss), len(_rej)),
        "★ 错误拒收样本": [{"sample_id": r["sample_id"], "分组": r["分组"],
                       "第二层": r["★ 第二层 候选字段完整性"]} for r in _rej_miss],
        "★ ★ 注意": "★ rejected 的其余部分**不是**错误（★ 人工也判不成立）",
    },
    "★ 3 pending 统计（★ ★ pending 不是自动意义上的错误拒收）": {
        "★ 定义": "★ 模型 pending 中，★ 人工判为 valid_confirmed ⇒ ★ **有效知识被隔离**",
        **_rate(len(_pend_valid), len(_pend)),
        "★ 被隔离的有效知识样本": [{"sample_id": r["sample_id"], "分组": r["分组"],
                           "第二层": r["★ 第二层 候选字段完整性"]} for r in _pend_valid],
        "★ 被正确保留 pending 的样本数": len(_pend_isolated),
        "★ ★ 说明": "★ pending 把 26 条人工判不成立的候选**留待复核**（★ 非错误）",
    },
    "★ 4 稳定性与人工真值交叉": {
        "★ 不稳定候选中人工判 valid_confirmed 的数量": sum(
            1 for r in rows if r["★ 跨批次不稳定"]
            and r["★ 第一层 规范义务存在性"] == "valid_confirmed"),
        "★ 不稳定候选中人工判 valid_rejection 的数量": sum(
            1 for r in rows if r["★ 跨批次不稳定"]
            and r["★ 第一层 规范义务存在性"] == "valid_rejection"),
        "★ ★ 含义": "★ 跨批次不稳定 ⇒ ★ **即使人工判成立，★ 单次 confirmed 也不足以作为发布依据**",
    },
}

(OUTD / "N1-B_模型质量指标.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "N1-B_逐样本对照.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

print("  ★ 口径：", json.dumps(summary["★ 口径"], ensure_ascii=False))
print()
print("  ★ 混淆矩阵（单批次）：")
for k, v in sorted(_cm.items()):
    print(f"      model={k[0]:9s} truth={str(k[1]):34s} {v}")
print()
print("  ★ confirmed precision：", json.dumps(
    {k: v for k, v in summary["★ 1 confirmed precision"].items()
     if k not in ("★ 错误确认样本",)}, ensure_ascii=False))
print("  ★ rejected：", json.dumps(
    {k: v for k, v in summary["★ 2 rejected 统计（★ 与 pending 分开）"].items()
     if k not in ("★ 错误拒收样本",)}, ensure_ascii=False))
print("  ★ pending：", json.dumps(
    {k: v for k, v in summary["★ 3 pending 统计（★ ★ pending 不是自动意义上的错误拒收）"].items()
     if k not in ("★ 被隔离的有效知识样本",)}, ensure_ascii=False))
print(f"\n  ⇒ {OUTD/'N1-B_模型质量指标.json'}")
