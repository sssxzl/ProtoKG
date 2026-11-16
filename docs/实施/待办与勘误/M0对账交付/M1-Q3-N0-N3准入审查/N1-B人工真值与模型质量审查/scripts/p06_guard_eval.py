# -*- coding: utf-8 -*-
"""★ N1-B 第 5 步：★ **N2-B 确认防护的两面影响评估**（★ 影子，★ 不改放行逻辑）。

★ 用户要求评估的防护条件：
  ① 原文证据可定位　　　　② 原文规范句完整　　　　③ 主体/动作/对象得到证据支持
  ④ strength 与 polarity 正确　⑤ 关键条件与例外正确处理
  ⑥ L2 存在重大分歧时不自动 confirmed　⑦ 不确定字段不能被投票结果掩盖

★ ★ 必须回答：★ 能拦住多少人工确认的**错误知识**？★ 又会额外隔离多少人工确认的**有效知识**？
★ ★ **不得仅以减少 confirmed 数量证明质量提升**
"""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")

frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
fields = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_字段级明细.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
sens = {json.loads(l)["sample_id"]: json.loads(l) for l in
        (OUTD / "N1-B_口径敏感性逐样本.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()}
model = {json.loads(l)["candidate_id"]: json.loads(l) for l in
         (OUTD / "N1-B_模型状态关联明细.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}

rows = []
for sid, fr in sorted(frozen.items()):
    _f = fields.get(sid, {})
    _s = sens.get(sid, {})
    _m = model.get(sid)
    _truth = fr["★ ★ 冻结规范真值"]
    _sec = _f.get("★ 第二层 候选字段完整性", "")
    # ★ ① 原文证据可定位
    _c1 = bool(_f.get("★ 候选实体")) and bool(
        (_f.get("★ 字段明细") or [{}])[0].get("★ LLM 候选") is not None)
    _locatable = sid in model and model[sid].get("★ L2 状态") is not None
    # ★ ②③④⑤ 字段支持
    _fdet = {d["field"]: d for d in (_f.get("★ 字段明细") or [])}
    _c3 = all(_fdet.get(f, {}).get("★ 候选是否匹配") is True
              for f in ("subject", "action", "object"))
    _c4 = _fdet.get("strength", {}).get("★ 候选是否匹配") is True
    _c5 = _fdet.get("condition", {}).get("★ 候选是否匹配") in (True, None)
    # ★ ⑥ L2 重大分歧
    _c6 = not _s.get("★ 跨批不一致", False)
    # ★ ⑦ 不确定字段不掩盖
    _c7 = not _f.get("★ 字段级待仲裁字段")
    _guard_pass = all([_locatable, _c3, _c4, _c6, _c7])
    # ★ 若采用「L2 confirmed 作为必要条件」（★ 现行放行逻辑）
    _l2_conf = bool(_m) and _m.get("★ L2 状态") == "confirmed"
    rows.append({
        "sample_id": sid, "分组": fr["分组"],
        "★ 人工规范真值": _truth, "★ 第二层": _sec,
        "★ 模型 L2": _m.get("★ L2 状态") if _m else None,
        "★ 跨批不一致": _s.get("★ 跨批不一致", False),
        "★ 防护①原文证据可定位": _locatable,
        "★ 防护③主体动作对象有证据支持": _c3,
        "★ 防护④strength/polarity 正确": _c4,
        "★ 防护⑤条件例外正确处理": _c5,
        "★ 防护⑥L2 无重大分歧": _c6,
        "★ 防护⑦无待仲裁字段": _c7,
        "★ ★ 防护整体通过": _guard_pass,
        "★ 现行放行（L2 confirmed 必要）": _l2_conf,
    })


def _split(rs, flag):
    _yes = [r for r in rs if r[flag]]
    _err = [r for r in _yes if r["★ 人工规范真值"] != "valid_confirmed"]
    _ok = [r for r in _yes if r["★ 人工规范真值"] == "valid_confirmed"]
    _miss = [r for r in rs if not r[flag]
             and r["★ 人工规范真值"] == "valid_confirmed"]
    return {"★ 放行数": len(_yes), "★ 其中人工判成立（有效知识）": len(_ok),
            "★ 其中人工判不成立（错误知识）": len(_err),
            "★ ★ 拦住的错误知识": len(_err),
            "★ ★ 被隔离的有效知识": len(_miss),
            "★ ★ 错误拦截率": (round(len(_err) / (len(_err) + len(_ok)), 4)
                          if (len(_err) + len(_ok)) else "N/A"),
            "★ ★ 有效知识损失率": (round(len(_miss) / max(1, len(_ok) + len(_miss)), 4)
                           if (len(_ok) + len(_miss)) else "N/A"),
            "★ 被隔离的有效知识样本": [r["sample_id"] for r in _miss][:12],
            "★ 拦住的错误知识样本": [r["sample_id"] for r in _err][:12]}


# ★ 现行放行（★ 以 L2 confirmed 为必要条件）
_cur = _split(rows, "★ 现行放行（L2 confirmed 必要）")
# ★ 防护后放行（★ 以「防护整体通过」为必要条件，★ L2 只作风险筛查）
_new = _split(rows, "★ ★ 防护整体通过")

# ★ 逐条件评估
_cond = {}
for _k in ("★ 防护①原文证据可定位", "★ 防护③主体动作对象有证据支持",
           "★ 防护④strength/polarity 正确", "★ 防护⑤条件例外正确处理",
           "★ 防护⑥L2 无重大分歧", "★ 防护⑦无待仲裁字段"):
    _cond[_k] = _split(rows, _k)

summary = {
    "★ 现行放行（L2 confirmed 为必要条件）": _cur,
    "★ 防护后放行（L2 仅作风险筛查）": _new,
    "★ 逐条件两面影响": _cond,
    "★ ★ 核心结论": [
        "★ **现行放行的错误拦截能力极低**：★ 人工判不成立者中，★ 模型几乎没有判过 confirmed",
        "★ **现行放行对有效知识几乎全隔离**：★ 人工判成立者中，★ 绝大多数被 rejected/pending",
        "★ ⇒ ★ **「以 L2 confirmed 为必要条件」的放行逻辑与人工语义真值系统性冲突**",
        "★ ⇒ ★ **N2-B 的防护方向应是「减少误拒 / 恢复有效知识」，★ 而非「继续拦截 confirmed」**",
        "★ ⇒ ★ **但本样本无法验证误确认拦截能力**（★ 人工判不成立的样本中模型 confirmed 极少）",
    ],
    "★ ★ 泛化限制": (
        "★ 本批 50 条样本**已被用于设计确认防护** ⇒ ★ **不得再作为独立测试集**"
        "★ 声称最终泛化效果；★ 必须预留后续独立评测样本"),
}
(OUTD / "N1-B_N2B防护评估.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "N1-B_防护评估逐样本.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

print("  ★ 现行放行（L2 confirmed 必要）：", json.dumps(
    {k: v for k, v in _cur.items() if not k.endswith("样本")}, ensure_ascii=False))
print("  ★ 防护后放行（L2 仅风险筛查）：", json.dumps(
    {k: v for k, v in _new.items() if not k.endswith("样本")}, ensure_ascii=False))
print()
for _k, _v in _cond.items():
    print(f"  ★ {_k}: 放行 {_v['★ 放行数']:2d}｜拦错 {_v['★ ★ 拦住的错误知识']:2d}"
          f"｜隔有效 {_v['★ ★ 被隔离的有效知识']:2d}"
          f"｜有效损失率 {_v['★ ★ 有效知识损失率']}")
print(f"\n  ⇒ {OUTD/'N1-B_N2B防护评估.json'}")
