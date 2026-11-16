# -*- coding: utf-8 -*-
"""★ N1-C 阶段：★ 生成**混淆矩阵与分层统计** 与 **字段级未解决分歧清单**（★ 冻结口径）。"""
import collections
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
FIXED = ROOT / "guard/_out/_n1c/work_n1c_fixed"

rows = list(csv.DictReader((DELIV / "N1-C_V0_V1逐候选对照.csv").open(encoding="utf-8")))
A = {r["sample_id"]: r for r in
     csv.DictReader((FIXED / "N1-C_盲审标注表_A.csv")
                    .read_text(encoding="utf-8").splitlines())}
B = {r["sample_id"]: r for r in
     csv.DictReader((FIXED / "N1-C_盲审标注表_B.csv")
                    .read_text(encoding="utf-8").splitlines())}
AR = {r["sample_id"]: r for r in
      csv.DictReader((FIXED / "N1-C_仲裁表.csv")
                     .read_text(encoding="utf-8").splitlines())}
MS = {json.loads(l)["sample_id"]: json.loads(l) for l in
      (ROOT / "guard/_out/_n1c/n1c_model_state.jsonl")
      .read_text(encoding="utf-8").splitlines() if l.strip()}

# ══ ① 混淆矩阵与分层统计 ══
with (DELIV / "N1-C_混淆矩阵与分层统计.csv").open("w", newline="",
                                          encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["★ 口径", "★ 分层维度", "★ 分层取值", "★ 模型/影子状态",
                "★ 人工真值", "★ 条数", "★ 占比(该层内)", "★ 说明"])
    for _route, _lab in (("★ V0 路由", "V0"), ("★ V1 路由", "V1")):
        _c = collections.Counter((r[_route], r["★ 人工 A truth_label"]) for r in rows)
        _tot = collections.Counter(r[_route] for r in rows)
        for (rt, tv), n in sorted(_c.items()):
            w.writerow([f"★ 影子确定性层（{_lab}）", "★ 全体", "★ 全体", rt, tv, n,
                        round(n / max(1, _tot[rt]), 4),
                        "★ 行=影子路由，★ 列=人工冻结真值"])
    # ★ 按协议分层
    for _route, _lab in (("★ V0 路由", "V0"), ("★ V1 路由", "V1")):
        for _proto in sorted({r["protocol"] for r in rows}):
            _sub = [r for r in rows if r["protocol"] == _proto]
            _c = collections.Counter((r[_route], r["★ 人工 A truth_label"]) for r in _sub)
            _tot = collections.Counter(r[_route] for r in _sub)
            for (rt, tv), n in sorted(_c.items()):
                w.writerow([f"★ 影子确定性层（{_lab}）", "★ protocol", _proto, rt, tv,
                            n, round(n / max(1, _tot[rt]), 4), "★ 协议分层"])
    # ★ 按候选质量分层（★ evidence_support，★ 用 A 值；★ 4 条分歧单列）
    for _route, _lab in (("★ V0 路由", "V0"), ("★ V1 路由", "V1")):
        for _q in ("supported", "partially_supported", "contradicted",
                   "evidence_insufficient"):
            _sub = [r for r in rows
                    if (r["★ 人工 A evidence_support"] or "") == _q]
            if not _sub:
                continue
            _c = collections.Counter((r[_route], r["★ 人工 A truth_label"]) for r in _sub)
            _tot = collections.Counter(r[_route] for r in _sub)
            for (rt, tv), n in sorted(_c.items()):
                w.writerow([f"★ 影子确定性层（{_lab}）", "★ 候选质量(evidence_support)",
                            _q, rt, tv, n, round(n / max(1, _tot[rt]), 4),
                            "★ ★ 4 条 ABNF 的 evidence_support 存在 A/B 分类分歧（★ 方向一致）"])
    # ★ 模型相对层（★ 仅 27 条有冻结状态）
    _c = collections.Counter((MS[r["candidate_id"]]["★ 模型状态（★ 盲审阶段不可见）"],
                             r["★ 人工 A truth_label"])
                            for r in rows if r["candidate_id"] in MS
                            and MS[r["candidate_id"]]["★ 模型状态（★ 盲审阶段不可见）"])
    for (ms, tv), n in sorted(_c.items()):
        w.writerow(["★ 模型相对层", "★ 全体", "★ 全体", ms, tv, n, "",
                    "★ **仅 27 条有冻结模型状态**；★ 其余 23 条 N/A"])

# ══ ② 字段级未解决分歧清单 ══
FIELDS = ["subject", "action", "object", "strength", "polarity", "condition",
          "exception", "evidence_support"]
with (DELIV / "N1-C_字段级未解决分歧清单.csv").open("w", newline="",
                                            encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["sample_id", "字段", "★ A 值", "★ B 值",
                "★ 归一化后是否等价", "★ 是否已仲裁", "★ 仲裁结论",
                "★ 仲裁者 ID", "★ 仲裁日期", "★ 处置", "★ A review_note",
                "★ B review_note"])
    _n = 0
    for sid in sorted(A):
        for fl in FIELDS:
            _a = (A[sid].get(f"★ A:{fl}") or "").strip()
            _b = (B[sid].get(f"★ B:{fl}") or "").strip()
            if _a == _b:
                continue
            _na = " ".join(_a.lower().replace("_", " ").split())
            _nb = " ".join(_b.lower().replace("_", " ").split())
            _eq = (_na == _nb)
            _arb = (AR[sid].get("★ 仲裁后 truth_label") or "").strip()
            w.writerow([sid, fl, _a[:90], _b[:90], "是" if _eq else "否",
                        "★ 是（★ 仅 truth_label 层）" if _arb else "★ 否",
                        _arb, AR[sid].get("★ 仲裁者 ID（★ 匿名编号）", ""),
                        AR[sid].get("★ 审核日期", ""),
                        "★ **字段级未解决 ⇒ 该字段指标 N/A，★ 列入字段级仲裁待办**",
                        (A[sid].get("★ A:review_note") or "")[:200],
                        (B[sid].get("★ B:review_note") or "")[:200]])
            _n += 1
    print(f"  ★ 字段级未解决分歧：{_n} 处")
print(f"  ⇒ {DELIV/'N1-C_混淆矩阵与分层统计.csv'}")
print(f"  ⇒ {DELIV/'N1-C_字段级未解决分歧清单.csv'}")
