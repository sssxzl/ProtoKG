# -*- coding: utf-8 -*-
"""★ N1-B 第 6 步：★ **重点错误案例分析**（★ 逐条列原文证据/人工判断/模型判断/失效环节/修复点）。"""
import collections
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")
WORK = OUTD / "work_utf8"

frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
fields = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_字段级明细.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
model = {json.loads(l)["candidate_id"]: json.loads(l) for l in
         (OUTD / "N1-B_模型状态关联明细.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}
sens = {json.loads(l)["sample_id"]: json.loads(l) for l in
        (OUTD / "N1-B_口径敏感性逐样本.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()}
A = {r["sample_id"]: r for r in
     csv.DictReader((WORK / "N1_盲审标注表_A.csv").read_text(encoding="utf-8").splitlines())}
B = {r["sample_id"]: r for r in
     csv.DictReader((WORK / "N1_盲审标注表_B.csv").read_text(encoding="utf-8").splitlines())}

# ★ 案例分类（★ 用户指定的 A~G）
CASES = collections.defaultdict(list)
for sid, fr in sorted(frozen.items()):
    _m = model.get(sid)
    _l2 = _m.get("★ L2 状态") if _m else None
    _truth = fr["★ ★ 冻结规范真值"]
    _sec = fields.get(sid, {}).get("★ 第二层 候选字段完整性", "")
    _ev = fr["★ 冻结 evidence_support"]
    _s = sens.get(sid, {})
    _cat = None
    if _truth == "valid_rejection" and _l2 == "confirmed":
        _cat = "B 非规范文本被错误确认"
    elif _truth == "valid_confirmed" and _l2 == "rejected":
        _cat = "A 真实规范义务被错误拒收"
    elif _truth == "valid_confirmed" and _sec.startswith("③"):
        _cat = "C 义务存在但主体/动作/对象错误"
    elif _truth == "valid_confirmed" and _sec.startswith("②"):
        _cat = "G 原文证据存在但候选语义不完整"
    elif _s.get("★ 跨批不一致"):
        _cat = "F L2 相同输入出现状态分歧"
    elif _truth == "valid_confirmed" and (_ev == "contradicted"
                                        or "strength" in str(fields.get(sid, {}))):
        _cat = "D 强度/极性识别错误"
    elif _truth == "valid_confirmed":
        _cat = "E 条件/例外/指代信息遗漏"
    if _cat:
        CASES[_cat].append(sid)

print("  ★ 案例分类（★ 一个样本可能命中多类 ⇒ ★ 按优先级归一）：")
for k in sorted(CASES):
    print(f"      {k:32s} {len(CASES[k]):3d}")

# ★ ★ 重点复查 @1#4
FOCUS = "rfc1534.txt@1#4"
_f = fields[FOCUS]
_m = model.get(FOCUS)
_s = sens.get(FOCUS)
_a = A[FOCUS]
print()
print(f"  ★★ 重点复查 {FOCUS}")
print(f"      分组：{frozen[FOCUS]['分组']}｜协议：{frozen[FOCUS]['protocol']}")
print(f"      ★ 人工 A：truth={_a.get('★ A:truth_label')}｜support={_a.get('★ A:evidence_support')}")
print(f"      ★ 人工 B：truth={B[FOCUS].get('★ B:truth_label')}｜support={B[FOCUS].get('★ B:evidence_support')}")
print(f"      ★ 仲裁：{_a.get('★ 仲裁后 truth_label')}｜仲裁者={_a.get('★ 仲裁者')}")
print(f"      ★ 冻结真值：{frozen[FOCUS]['★ ★ 冻结规范真值']}｜第二层：{_f.get('★ 第二层 候选字段完整性')}")
print(f"      ★ 模型 L2：{_m.get('★ L2 状态') if _m else 'N/A'}"
      f"｜批次判定：{_m.get('★ 各批次判定') if _m else '—'}")
print(f"      ★ 锚点行原文：{_a.get('★ 锚点行原文（★ 合法可为空）')}")
print(f"      ★ 证据句：{_a.get('★ 证据句（含 entity 的非空行）')}")
print(f"      ★ 上下文：{_a.get('★ RFC 原文上下文（锚点 ±6 行）')}")
print(f"      ★ 候选字段：entity={_a.get('★ entity（LLM 候选）')}"
      f"｜subject={_a.get('★ normative_subject（LLM 候选）')}"
      f"｜action={_a.get('★ action（LLM 候选）')}"
      f"｜object={_a.get('★ object（LLM 候选）')}"
      f"｜strength={_a.get('★ strength（LLM 候选）')}")
print(f"      ★ A review_note：{_a.get('★ A:review_note')}")
print(f"      ★ B review_note：{B[FOCUS].get('★ B:review_note')}")
print(f"      ★ 字段待仲裁：{_f.get('★ 字段级待仲裁字段')}")

# ★ 逐案例明细
cases = []
for cat, ids in sorted(CASES.items()):
    for sid in ids:
        _m = model.get(sid)
        _a = A[sid]
        cases.append({
            "★ 案例类别": cat, "sample_id": sid,
            "分组": frozen[sid]["分组"],
            "★ 原文证据（锚点行）": _a.get("★ 锚点行原文（★ 合法可为空）"),
            "★ 证据句": _a.get("★ 证据句（含 entity 的非空行）"),
            "★ 原文上下文": _a.get("★ RFC 原文上下文（锚点 ±6 行）"),
            "★ LLM 候选字段": {
                "entity": _a.get("★ entity（LLM 候选）"),
                "subject": _a.get("★ normative_subject（LLM 候选）"),
                "action": _a.get("★ action（LLM 候选）"),
                "object": _a.get("★ object（LLM 候选）"),
                "strength": _a.get("★ strength（LLM 候选）"),
                "polarity": _a.get("★ 推导 polarity（★ 供核对）"),
                "condition": _a.get("★ condition（LLM 候选，★ 原始无此字段）"),
                "exception": _a.get("★ exception（LLM 候选，★ 原始无此字段）"),
            },
            "★ 人工 A 真值": _a.get("★ A:truth_label"),
            "★ 人工 B 真值": B[sid].get("★ B:truth_label"),
            "★ 仲裁结论": _a.get("★ 仲裁后 truth_label"),
            "★ 冻结真值": frozen[sid]["★ ★ 冻结规范真值"],
            "★ 第二层分类": fields.get(sid, {}).get("★ 第二层 候选字段完整性"),
            "★ 人工 evidence_support": frozen[sid]["★ 冻结 evidence_support"],
            "★ 模型 L2 状态": _m.get("★ L2 状态") if _m else "N/A",
            "★ 模型各批次判定": _m.get("★ 各批次判定") if _m else "—",
            "★ 跨批不一致": sens.get(sid, {}).get("★ 跨批不一致", False),
            "★ A review_note": _a.get("★ A:review_note"),
            "★ B review_note": B[sid].get("★ B:review_note"),
        })

with (OUTD / "N1-B_错误案例明细.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(cases[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(cases)
(OUTD / "N1-B_案例分类统计.json").write_text(json.dumps(
    {k: len(v) for k, v in CASES.items()}, ensure_ascii=False, indent=2),
    encoding="utf-8")
print(f"\n  ★ 案例明细 {len(cases)} 条 ⇒ {OUTD/'N1-B_错误案例明细.csv'}")
