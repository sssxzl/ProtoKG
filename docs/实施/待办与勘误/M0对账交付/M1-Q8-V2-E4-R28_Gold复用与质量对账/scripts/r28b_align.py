# -*- coding: utf-8 -*-
"""R28-B：历史 Gold 与当前 RFC 知识的逐条对齐（可复算）。

输入：
  guard/_out/_release/norms_machine.json   当前 main 的 Norm 索引（含 kind/name/source/content）
  R19_原子Gold_v5冻结基线.jsonl             6 条
  B1_人工真值冻结清单.jsonl                 130 条（121 有效 + 9 无目标）

输出：
  R28_B0_...xlsx  R28_B1_...xlsx  R28_B2_...xlsx  R28_B2_九类匹配状态与理由.csv
  R28_B3_G-B1片段覆盖与漏抽归因.xlsx

判定规则见各函数 docstring；不做人工裁定，无法可靠判定的一律 unresolved。
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parents[6]
M0 = ROOT / "docs/实施/待办与勘误/M0对账交付"
OUT = M0 / "M1-Q8-V2-E4-R28_Gold复用与质量对账"
R19 = M0 / "M1-Q3-V2-E4-R19_原子Goldv5冻结与独立验证门禁准备/R19_原子Gold_v5冻结基线.jsonl"
B1 = M0 / "M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl"
NORMS = ROOT / "guard/_out/_release/norms_machine.json"

PROTO_MAP = {"SMTP": "smtp", "RTSP": "rtsp", "DHCPv4": "DHCPv4", "sip": "sip"}


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_norms() -> dict:
    raw = json.loads(NORMS.read_text(encoding="utf-8"))
    idx = {}
    for proto, items in raw.items():
        idx[proto] = []
        for n in items:
            src = n.get("source") or ""
            doc, loc = "", ""
            if "#@" in src:
                doc = src.split("#@")[0].replace("file:", "")
                loc = src.split("#@", 1)[1]
            line = int(loc) if str(loc).isdigit() else None
            idx[proto].append({**n, "doc": doc, "line": line})
    return idx


def parse_b1(g: dict) -> dict:
    gid = g.get("gold_knowledge_id", "")
    m = re.match(r"GK-B-([A-Za-z0-9]+)-(.+?)-(\d+)-(\d+)$", gid)
    proto = m.group(1) if m else "?"
    doc = m.group(2) if m else "?"
    span = g.get("evidence_span") or (f"{m.group(3)}-{m.group(4)}" if m else "")
    start = int(span.split("-")[0]) if span and span.split("-")[0].isdigit() else None
    end = int(span.split("-")[1]) if "-" in str(span) and str(span).split("-")[1].isdigit() else start
    quote = ""
    txt = g.get("★ 原文支持说明") or ""
    mm = re.search(r"[\"'“]([^\"'”]{20,})[\"'”]", txt)
    if mm:
        quote = mm.group(1)
    fields = g.get("★ 适用的结构化字段") or {}
    return {"gold_id": gid, "protocol": proto, "doc": doc, "span": span,
            "start": start, "end": end, "quote": quote,
            "kind": g.get("knowledge_kind", ""),
            "subject": fields.get("subject", ""), "action": fields.get("action", ""),
            "object": fields.get("object", ""), "strength": fields.get("strength", ""),
            "polarity": fields.get("polarity", ""), "condition": fields.get("condition", ""),
            "exception": fields.get("exception", ""), "support": fields.get("evidence_support", ""),
            "raw_status": g.get("★ status") or g.get("status") or "",
            "gold_status": g.get("★ status") or g.get("status") or "",
            "arbitration": g.get("★ 仲裁状态") or "", "dispute": g.get("★ 分歧字段") or ""}


def label_for(rec: dict, norms: dict) -> tuple[str, str, str]:
    """返回 (九类标签, 判定理由, 阻断阶段)。"""
    proto = rec["protocol"]
    if proto.lower() == "sip":
        return ("outside_current_scope", "SIP 不在当前三协议 RFC-only 基线内", "")
    pkey = PROTO_MAP.get(proto, proto)
    items = norms.get(pkey, [])
    doc_items = [n for n in items if n["doc"].lower() == rec["doc"].lower()]
    if rec["start"] is None:
        return ("unresolved", "Gold 无可用行号跨度，无法定位", "")
    if not doc_items:
        return ("missing_extraction", "该文档在当前构建中零 Norm", "文档零产出（解析/分块/通道未产出）")
    lo, hi = rec["start"] - 3, (rec["end"] or rec["start"]) + 3
    near = [n for n in doc_items if n["line"] and lo <= n["line"] <= hi]
    # 命题文本匹配：仅当 Norm content 含足够长的原文片段才算命中
    q = re.sub(r"\s+", " ", rec["quote"]).strip().lower()
    hit = None
    for n in doc_items:
        c = re.sub(r"\s+", " ", (n.get("content") or "")).lower()
        if q and len(q) >= 40 and q[:40] in c:
            hit = n
            break
    if hit:
        return ("exact_match", f"Norm {hit['norm_id']} 的 content 含原文命题片段", "")
    if near:
        n = min(near, key=lambda x: abs(x["line"] - rec["start"]))
        return ("partial_match", f"同跨度有 Norm（{n['norm_id']}，{n['kind']}），但未承载该命题全文", "")
    return ("missing_extraction", "该跨度内无任何 Norm 候选", "抽取后无候选（确定性通道不覆盖散文命题）")


def main() -> int:
    norms = load_norms()
    r19 = [json.loads(l) for l in R19.read_text(encoding="utf-8").splitlines() if l.strip()]
    b1 = [json.loads(l) for l in B1.read_text(encoding="utf-8").splitlines() if l.strip()]

    # ---- B0：8 项资产元数据 ----
    b0 = [
        ["G-N1B", "N1-B 50 条人工真值", "M1-Q3-N0-N3准入审查/N1-B人工真值与模型质量审查",
         "verified_partial", "unresolved", "verified_complete",
         "未见审核者 A/B 独立标注表；仲裁记录缺失", "人工真值与逐样本对照分离", "无独立双审，独立性受限", "曾用于开发"],
        ["G-N1C", "N1-C 50 条独立评测", "M1-Q3-N1-C-N2-B0独立评测与误拒收审计",
         "verified_complete", "verified_complete", "verified_complete",
         "盲审标注表 A/B（82KB/87KB）+ 仲裁表 + 未解决分歧清单齐备", "盲审表与机器预填分离", "当时独立，现已揭盲", "曾用于一次性评估"],
        ["G-B1", "V2-E4 队列 B 121+9", "M1-Q3-V2-E4-B1队列B人工真值验收",
         "verified_complete", "verified_complete", "verified_complete",
         "回收表 A 129 行 / B 124 行 / 仲裁 98 行；双人一致性与未决项齐备", "冻结清单与机器对齐台账分离", "已揭盲", "曾用于片段级评估"],
        ["G-H3", "H3 23 条候选", "M1-Q3-V2-E4-R1_H3候选人工盲审",
         "verified_complete", "verified_complete", "verified_complete",
         "A/B 工作簿含 24 行人工审核表与 47 行补充知识表；第三方仲裁模板在位", "机器身份与人工审核分 sheet", "盲审后已揭盲", "曾用于 H3 评测"],
        ["G-H3S", "H3 5 条补充知识", "M1-Q3-V2-E4-R6_H3Gold冻结复核与评测准备",
         "verified_partial", "unresolved", "verified_complete",
         "补充知识在评估分母表与结构化复核表中，未见独立仲裁文件", "分母表与复核表分离", "随 H3 同批，非独立", "曾用于 H3 评测"],
        ["G-R13", "R13 57 条候选级 Gold", "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核",
         "verified_complete", "verified_complete", "verified_complete",
         "57 条冻结报告 + 待确认状态表（未裁定字段已登记）+ 必要补充复核表", "冻结基线与复核表分离", "一次性评估已使用", "曾用于分类评估"],
        ["G-R14", "R14 一次性事后分类评估", "M1-Q3-V2-E4-R14_候选级分类一次性评估",
         "verified_complete", "not_applicable", "verified_complete",
         "评估结果与限制说明齐备；无独立仲裁（本就是事后评估）", "结果表与混淆矩阵分离", "事后评估，非独立", "评估结论已使用"],
        ["G-R19", "R19 原子 Gold v5（6 条）", "M1-Q3-V2-E4-R19_原子Goldv5冻结与独立验证门禁准备",
         "verified_complete", "verified_complete", "verified_partial",
         "人工回填与冻结验收报告 + 冻结基线；但 document/source_sha256 字段为空", "机器原文与人工命题分离", "冻结，未参与调优", "未用于开发"],
    ]
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "B0_Gold元数据补核"
    head = ["编号", "资产", "目录", "A/B原始记录", "第三方仲裁", "最终Gold身份与版本",
            "证据与缺口说明", "机器候选与人工结论分离", "独立性限制", "历史使用情况"]
    ws.append(head)
    for r in b0: ws.append(r)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, w in enumerate([10, 26, 46, 18, 18, 20, 46, 26, 22, 18], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.cell(1, 1).font = Font(bold=True)
    wb.save(OUT / "R28_B0_Gold人工审核与仲裁元数据补核.xlsx")

    # ---- B1：身份清单 + B2 对齐 ----
    rows = []
    for g in r19:
        gid = g.get("gold_id", "")
        rows.append({"组": "G-R19", "gold_id": gid, "协议": g.get("protocol", ""),
                     "文档": "", "跨度": g.get("source_span", ""),
                     "命题": (g.get("★ human_gold_proposition") or "")[:120],
                     "kind": g.get("knowledge_kind", ""), "strength": g.get("strength", ""),
                     "polarity": g.get("polarity", ""), "仲裁者": g.get("★ 仲裁者", ""),
                     "来源": g.get("★ 人工来源", "")})
    parsed = []
    for g in b1:
        rec = parse_b1(g); parsed.append(rec)
        rows.append({"组": "G-B1", "gold_id": rec["gold_id"], "协议": rec["protocol"],
                     "文档": rec["doc"], "跨度": rec["span"], "命题": rec["quote"][:120],
                     "kind": rec["kind"], "strength": rec["strength"], "polarity": rec["polarity"],
                     "仲裁者": rec["arbitration"], "来源": g.get("★ 来源 RFC", "")})

    wb1 = openpyxl.Workbook(); s1 = wb1.active; s1.title = "B1_Gold身份清单"
    s1.append(list(rows[0]))
    for r in rows: s1.append(list(r.values()))
    for i, w in enumerate([10, 44, 10, 18, 10, 60, 26, 10, 10, 14, 18], 1):
        s1.column_dimensions[get_column_letter(i)].width = w
    for c in s1[1]: c.font = Font(bold=True)
    wb1.save(OUT / "R28_B1_两组Gold身份与来源清单.xlsx")

    # 对齐：R19 全部落在当前输入之外（rfc7826/rfc3461/rfc6531/rfc8098 不在 kb）
    align = []
    kb_docs = {p.name for p in (ROOT / "kb").glob("*/spec/*.txt")}
    for g in r19:
        gid = g.get("gold_id", "")
        m = re.search(r"rfc(\d+)", gid)
        doc = f"rfc{m.group(1)}.txt" if m else ""
        ins = doc in kb_docs
        label = "outside_current_scope" if not ins else "unresolved"
        why = (f"Gold 引用 {doc or '未注明文件'}，不在当前 kb 输入" if not ins
               else "文档在输入内，但 Gold 缺 document/sha，无法定位")
        align.append({"组": "G-R19", "gold_id": gid, "协议": g.get("protocol", ""),
                      "文档": doc, "跨度": g.get("source_span", ""),
                      "命中的Norm": "", "标签": label, "理由": why, "阻断阶段": "",
                      "Gold命题": (g.get("★ human_gold_proposition") or "")[:100]})
    for rec in parsed:
        if rec["gold_status"] == "no_target_knowledge":
            pkey = PROTO_MAP.get(rec["protocol"], rec["protocol"])
            items = [n for n in norms.get(pkey, [])
                     if n["doc"].lower() == rec["doc"].lower()]
            near = [n for n in items if n["line"] and rec["start"] and
                    abs(n["line"] - rec["start"]) <= 3]
            if rec["protocol"].lower() == "sip":
                lab, why, stage = "outside_current_scope", "SIP 不在当前基线", ""
            elif near:
                lab, why, stage = "no_target_record", (
                    f"无目标片段但机器在同跨度有 {len(near)} 条 Norm（疑似误抽，需人工判）"), ""
            else:
                lab, why, stage = "no_target_record", "无目标片段且机器同跨度无候选（符合预期）", ""
            align.append({"组": "G-B1(无目标)", "gold_id": rec["gold_id"],
                          "协议": rec["protocol"], "文档": rec["doc"], "跨度": rec["span"],
                          "命中的Norm": "" if not near else near[0]["norm_id"],
                          "标签": lab, "理由": why, "阻断阶段": stage, "Gold命题": rec["quote"][:100]})
            continue
        lab, why, stage = label_for(rec, norms)
        hit = ""
        if lab in ("exact_match", "partial_match"):
            hit = "见理由"
        align.append({"组": "G-B1", "gold_id": rec["gold_id"], "协议": rec["protocol"],
                      "文档": rec["doc"], "跨度": rec["span"], "命中的Norm": hit,
                      "标签": lab, "理由": why, "阻断阶段": stage,
                      "Gold命题": rec["quote"][:100]})

    wb2 = openpyxl.Workbook(); s2 = wb2.active; s2.title = "B2_逐条对齐"
    s2.append(list(align[0]))
    for r in align: s2.append(list(r.values()))
    for i, w in enumerate([10, 44, 10, 16, 10, 14, 24, 56, 34, 60], 1):
        s2.column_dimensions[get_column_letter(i)].width = w
    for c in s2[1]: c.font = Font(bold=True)
    wb2.save(OUT / "R28_B2_Gold到Raw_Norm_Canonical_Evidence逐条对齐.xlsx")

    with (OUT / "R28_B2_九类匹配状态与理由.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=list(align[0]), lineterminator="\n")
        w.writeheader(); w.writerows(align)

    # ---- 统计 ----
    stat = Counter((r["组"], r["标签"]) for r in align)
    print("对齐条数", len(align))
    for k, v in sorted(stat.items()): print(" ", k, v)

    # 分协议 + 文档维度
    by_kind = Counter()
    for rec in parsed:
        if rec["gold_status"] != "valid_gold":
            continue
        lab, _, _ = label_for(rec, norms)
        by_kind[(rec["kind"], lab)] += 1
    print("按 kind:", dict(sorted(by_kind.items())))

    per_doc = defaultdict(lambda: [0, 0, 0, 0])
    for r in align:
        if r["组"] != "G-B1": continue
        key = (r["协议"], r["文档"])
        per_doc[key][0] += 1
        if r["标签"] == "exact_match": per_doc[key][1] += 1
        elif r["标签"] == "partial_match": per_doc[key][2] += 1
        elif r["标签"] == "missing_extraction": per_doc[key][3] += 1
    doc_norm = Counter()
    for p, items in norms.items():
        for n in items:
            if n["doc"]: doc_norm[(p, n["doc"])] += 1

    wb3 = openpyxl.Workbook(); s3 = wb3.active; s3.title = "B3_片段覆盖与漏抽"
    s3.append(["协议", "文档", "Gold条数", "exact", "partial", "missing", "当前Norm数", "文档是否零产出"])
    for (p, d), v in sorted(per_doc.items()):
        s3.append([p, d, v[0], v[1], v[2], v[3], doc_norm.get((p, d), 0),
                   "是" if doc_norm.get((p, d), 0) == 0 else "否"])
    for i, w in enumerate([12, 18, 10, 8, 8, 8, 12, 14], 1):
        s3.column_dimensions[get_column_letter(i)].width = w
    for c in s3[1]: c.font = Font(bold=True)
    wb3.save(OUT / "R28_B3_G-B1片段覆盖与漏抽归因.xlsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
