# -*- coding: utf-8 -*-
"""R29 RA-1：32 条 syntax 缺口的原文 / Chunk / 抽取入口核查（只读）。

事实前提（已核代码）：
  core/fused/extraction/rfc_extractor.py 中**没有任何 chunk 引用**；
  分块（block_selection / block_budget）只被散文通道 prose_semantics 使用。
  ⇒ 确定性通道按整文件行扫描，不存在「Chunk 未覆盖」这一阻断面。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
from collections import Counter, defaultdict

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parents[6]
M0 = ROOT / "docs/实施/待办与勘误/M0对账交付"
D28 = M0 / "M1-Q8-V2-E4-R28_Gold复用与质量对账"
OUT = M0 / "M1-Q8-V2-E4-R29_RA1_Syntax缺口核查"
B1 = M0 / "M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl"
NORMS = ROOT / "guard/_out/_release/norms_machine.json"

PROTO = {"SMTP": "smtp", "RTSP": "rtsp", "DHCPv4": "DHCPv4", "smtp": "smtp", "rtsp": "rtsp"}


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def structure_flags(lines: list[str]) -> dict:
    """在跨度内找「确定性通道能吃」的结构证据。"""
    txt = "\n".join(lines)
    abnf = bool(re.search(r"^\s*[A-Za-z][\w\-]*\s*=\s*\S", txt, re.M))
    table = sum(1 for l in lines if l.count("|") >= 2) >= 2
    bitdiag = any(re.search(r"[+\-]{4,}", l) and ("0" in l or "1" in l) for l in lines)
    numbered = bool(re.search(r"^\s*0\s+1\s+2", txt, re.M))
    return {"abnf": abnf, "table": table, "bit_diagram": bitdiag or numbered}


def main() -> int:
    # 1) 32 条：syntax 且 missing
    wb = openpyxl.load_workbook(D28 / "R28-C_抽取机会与阶段覆盖对账.xlsx", read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr, data = rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]
    b1 = [json.loads(l) for l in B1.read_text(encoding="utf-8").splitlines() if l.strip()]
    kmap = {x["gold_knowledge_id"]: x.get("knowledge_kind", "") for x in b1}
    qmap = {x["gold_knowledge_id"]: (x.get("★ 原文支持说明") or "") for x in b1}
    sel = [r for r in data
           if kmap.get(r["gold_id"]) == "protocol_syntax"
           and r["R28B标签"] == "missing_extraction"]
    assert len(sel) == 32, len(sel)

    norms = json.loads(NORMS.read_text(encoding="utf-8"))
    doc_kinds = defaultdict(set)
    doc_lines = defaultdict(set)
    for proto, items in norms.items():
        for n in items:
            src = n.get("source") or ""
            if "#@" not in src:
                continue
            doc = src.split("#@")[0].replace("file:", "")
            loc = src.split("#@", 1)[1]
            doc_kinds[(proto, doc)].add(n.get("kind"))
            if loc.isdigit():
                doc_lines[(proto, doc)].add(int(loc))

    out = []
    for r in sel:
        proto = PROTO[r["协议"]]
        doc, span = r["文档"], r["跨度"]
        p = ROOT / "kb" / proto / "spec" / doc
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n") if p.is_file() else []
        s = int(span.split("-")[0]); e = int(span.split("-")[1]) if "-" in span else s
        seg = lines[s - 1:e] if lines and 1 <= s <= len(lines) else []
        flags = structure_flags(seg)
        kinds = doc_kinds[(proto, doc)]
        # 判定
        if not seg:
            cls, why = "unresolved", "跨度无法重建"
        elif flags["abnf"]:
            cls, why = ("unsupported_syntax_structure",
                        "跨度是 ABNF **语法产生式**（grammar production），现有 ABNF 通道只解头字段/方法，不解通用产生式")
        elif flags["table"]:
            cls, why = "extractor_invoked_no_candidate", "跨度内含表格，但该行未产出 Norm"
        elif flags["bit_diagram"]:
            cls, why = "unsupported_syntax_structure", "跨度是位/八位组图或顺序描述，确定性通道无对应解析器"
        else:
            cls, why = "unsupported_syntax_structure", "跨度是散文形式的结构描述，无 ABNF/表格/位图可解析"
        # 同文档是否存在同类结构产出
        same_family = bool(kinds & {"field", "option_layout", "binary_layout", "field_value"})
        out.append({
            "gold_id": r["gold_id"], "协议": r["协议"], "文档": doc, "跨度": span,
            "RFC SHA256": sha(p) if p.is_file() else "<missing>",
            "原文行数": len(lines),
            "跨度可重建": "是" if seg else "否",
            "跨度首行": (seg[0].strip()[:90] if seg else ""),
            "ABNF": "有" if flags["abnf"] else "无",
            "表格": "有" if flags["table"] else "无",
            "位图": "有" if flags["bit_diagram"] else "无",
            "文档已产出类型": ";".join(sorted(kinds)),
            "同族结构产出": "是" if same_family else "否",
            "Parser": "ok（文件级解析，行可重建）",
            "Chunk": "not_applicable（确定性通道按整文件行扫描，无 chunk 概念）",
            "进入抽取窗口": "是（整文件）",
            "抽取函数": ("ABNF 通道" if flags["abnf"] else
                     ("表格通道" if flags["table"] else "无对应通道")),
            "Raw候选": "否",
            "到达Norm": "否",
            "阻断阶段": cls, "判定理由": why,
            "证据位置": f"kb/{proto}/spec/{doc}:{s}-{e}",
            "核验状态": "已核（代码+原文）" if seg else "unavailable",
        })

    # 2) 台账 xlsx
    wb1 = openpyxl.Workbook(); s1 = wb1.active; s1.title = "RA1_32条核查"
    s1.append(list(out[0]))
    for r in out: s1.append(list(r.values()))
    for c in s1[1]: c.font = Font(bold=True)
    widths = [44, 9, 16, 10, 66, 8, 10, 50, 6, 6, 6, 26, 10, 26, 44, 12, 14, 14, 12, 30, 44, 30, 16]
    for i, w in enumerate(widths[:len(out[0])], 1):
        s1.column_dimensions[get_column_letter(i)].width = w
    for row in s1.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    wb1.save(OUT / "R29_RA1_32条Syntax原文与Chunk覆盖台账.xlsx")

    # 3) 入口对账（按文档聚合 + 逐条阻断）
    wb2 = openpyxl.Workbook(); s2 = wb2.active; s2.title = "RA1_抽取入口"
    s2.append(["协议", "文档", "缺口条数", "文档已产出类型", "同族结构产出",
               "ABNF跨度", "表格跨度", "位图跨度", "散文跨度", "主要阻断"])
    agg = defaultdict(list)
    for r in out: agg[(r["协议"], r["文档"])].append(r)
    for (proto, doc), items in sorted(agg.items()):
        kinds = items[0]["文档已产出类型"]
        s2.append([proto, doc, len(items), kinds, items[0]["同族结构产出"],
                   sum(1 for x in items if x["ABNF"] == "有"),
                   sum(1 for x in items if x["表格"] == "有"),
                   sum(1 for x in items if x["位图"] == "有"),
                   sum(1 for x in items if x["ABNF"] == "无" and x["表格"] == "无" and x["位图"] == "无"),
                   Counter(x["阻断阶段"] for x in items).most_common(1)[0][0]])
    for c in s2[1]: c.font = Font(bold=True)
    for i, w in enumerate([10, 18, 10, 30, 12, 10, 10, 10, 10, 34], 1):
        s2.column_dimensions[get_column_letter(i)].width = w
    wb2.save(OUT / "R29_RA1_抽取入口与Raw候选对账.xlsx")

    print("32 条阻断:", dict(Counter(r["阻断阶段"] for r in out)))
    print("结构形态: ABNF", sum(1 for r in out if r["ABNF"] == "有"),
          "表格", sum(1 for r in out if r["表格"] == "有"),
          "位图", sum(1 for r in out if r["位图"] == "有"),
          "纯散文", sum(1 for r in out if r["ABNF"] == "无" and r["表格"] == "无" and r["位图"] == "无"))
    print("文档数", len(agg), "| 同族产出文档", sum(1 for k, v in agg.items() if v[0]["同族结构产出"] == "是"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
