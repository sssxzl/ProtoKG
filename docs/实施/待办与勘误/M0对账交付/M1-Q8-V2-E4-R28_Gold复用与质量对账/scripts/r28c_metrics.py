# -*- coding: utf-8 -*-
"""R28-C：在 R28-B 对齐结果上补证据、分层归因、算可计算指标。

只读：norms_machine.json（R28-B 产物）、B2 对齐 CSV、R25 输入清单、散文缓存。
输出：覆盖率复核 CSV、抽取机会对账 XLSX、110 条归因 XLSX。
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
from collections import Counter, defaultdict

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parents[6]
D = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q8-V2-E4-R28_Gold复用与质量对账"
R25 = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q8-V2-E4-R25_RFC单源知识抽取链路验证/R25_RFC文档输入与版本清单.csv"
NORMS = ROOT / "guard/_out/_release/norms_machine.json"
B2 = D / "R28_B2_九类匹配状态与理由.csv"

PROTO = {"SMTP": "smtp", "RTSP": "rtsp", "DHCPv4": "DHCPv4", "sip": "sip"}
DET_KINDS = {"protocol_syntax", "protocol_registry_or_enumeration"}
PROSE_KINDS = {"normative_rule_candidate", "protocol_descriptive_semantics"}


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_r25() -> dict:
    out = {}
    with R25.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            path = (row.get("本地文件路径") or "").strip()
            if path:
                out[path.split("/")[-1]] = row.get("SHA256", "").strip()
    return out


def main() -> int:
    raw = json.loads(NORMS.read_text(encoding="utf-8"))
    norms = {}
    for proto, items in raw.items():
        norms[proto] = []
        for n in items:
            src = n.get("source") or ""
            doc, loc = "", ""
            if "#@" in src:
                doc = src.split("#@")[0].replace("file:", "")
                loc = src.split("#@", 1)[1]
            norms[proto].append({**n, "doc": doc,
                                 "line": int(loc) if str(loc).isdigit() else None})
    r25 = load_r25()
    b2 = list(csv.DictReader(B2.open(encoding="utf-8")))
    golds = [r for r in b2 if r["组"] == "G-B1"]

    prose = json.loads((ROOT / "derived/cache/source_blocks/DHCPv4.prose.json").read_text(encoding="utf-8"))
    prose_docs = {i.get("doc") for i in prose.get("items", [])}

    lines_cache = {}
    def lines_of(proto, doc):
        key = (proto, doc)
        if key not in lines_cache:
            p = ROOT / "kb" / proto / "spec" / doc
            lines_cache[key] = (p.read_text(encoding="utf-8", errors="replace").split("\n")
                                if p.is_file() else [])
        return lines_cache[key]

    b1 = [json.loads(l) for l in (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    kmap = {x["gold_knowledge_id"]: x.get("knowledge_kind", "") for x in b1}

    rows = []
    for g in golds:
        proto = PROTO.get(g["协议"], g["协议"])
        doc, span = g["文档"], g["跨度"]
        kind = kmap.get(g["gold_id"], "")
        start = int(span.split("-")[0]) if span.split("-")[0].isdigit() else None
        lines = lines_of(proto, doc)
        kb_path = ROOT / "kb" / proto / "spec" / doc
        doc_norms = [n for n in norms.get(proto, []) if n["doc"].lower() == doc.lower()]
        span_norms = [n for n in doc_norms if n["line"] and start and abs(n["line"] - start) <= 3]
        # 文档范围候选：用 Gold 命题里的英文实词做弱匹配（仅给候选，不判等价）
        q = re.sub(r"\s+", " ", g.get("Gold命题") or "")
        # 只认「协议标识符级」token：全大写缩写或含连字符/驼峰的名称；不认普通英文词
        raw_toks = re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", q)
        stop = {"must", "should", "shall", "this", "that", "with", "from", "when",
                "which", "value", "client", "server", "dhcp", "smtp", "rtsp", "sip",
                "field", "option", "header", "message", "packet", "protocol", "using",
                "required", "include", "address", "request", "response", "server's"}
        toks = [w for w in raw_toks
                if w.lower() not in stop and (w.isupper() or "-" in w or any(c.isupper() for c in w[1:]))]
        cand = []
        for n in doc_norms:
            name = (n.get("name") or "").lower()
            content = (n.get("content") or "").lower()
            if any(t.lower() in name for t in toks) or \
               any(t.lower() in content and len(t) >= 6 for t in toks):
                cand.append(n["norm_id"])
        rows.append({
            "gold_id": g["gold_id"], "协议": g["协议"], "文档": doc, "跨度": span,
            "Gold命题": q[:110],
            "文件存在": "是" if kb_path.is_file() else "否",
            "SHA与R25一致": ("一致" if kb_path.is_file() and r25.get(doc) == sha(kb_path)
                          else ("不一致" if r25.get(doc) else "R25无记录")),
            "跨度可重建": "是" if lines and start and 1 <= start <= len(lines) else "否",
            "文档Norm数": len(doc_norms),
            "同跨度Norm": ";".join(n["norm_id"] for n in span_norms),
            "文档范围候选": ";".join(cand[:3]),
            "候选数": len(cand),
            "在散文缓存文档内": "是" if doc in prose_docs else "否",
            "散文缓存complete": str(prose.get("complete")),
            "R28B标签": g["标签"],
            "证据强度": ("已确认" if span_norms else ("候选待判" if cand else "无候选")),
            # ---- C1.1 十项核查（无日志者一律 unavailable） ----
            "通道适用": ("确定性" if kind in DET_KINDS else
                     ("散文" if kind in PROSE_KINDS else "未知")),
            "通道实际执行": ("是（文档有 Norm）" if doc_norms else "否（零产出）"),
            "Parser处理": "unavailable（无分块级日志）",
            "Chunk覆盖": "unavailable（无分块级日志）",
            "Raw候选": "是" if (span_norms or cand) else "否",
            "进入门禁": "unavailable（无门禁日志）",
            "产生Norm": "是" if span_norms else "否",
            "产生Canonical": "是" if span_norms and span_norms[0].get("facts") else "否",
            "产生Evidence": "是" if span_norms else "否",
        })

    # ---- 覆盖率复核 CSV ----
    with (D / "R28-C_历史Gold覆盖率复核.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader(); w.writerows(rows)

    # ---- C4 归因 ----
    def bucket(r):
        """按任务书九类归因（1–9）给主类别。"""
        kind = kmap.get(r["gold_id"], "")
        if r["文档Norm数"] == 0:
            return "8 文档零产出（阶段未归因）"
        if r["候选数"] and not r["同跨度Norm"]:
            return "7 有 Raw 候选但未进入 Norm"
        if kind in DET_KINDS:
            return "1 确定性通道应覆盖但无候选"
        if kind in PROSE_KINDS:
            if r["在散文缓存文档内"] == "是":
                return "4 有冻结缓存但未被接受"
            return "3 散文通道配置关闭且无缓存"
        return "9 证据不足，无法判断"

    for r in rows:
        r["C4归因"] = bucket(r)
    cnt = Counter(r["C4归因"] for r in rows)
    print("C4 归因:", dict(cnt))
    print("证据强度:", dict(Counter(r["证据强度"] for r in rows)))
    print("SHA 一致性:", dict(Counter(r["SHA与R25一致"] for r in rows)))

    # ---- XLSX: 抽取机会对账 ----
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "C1_抽取机会对账"
    ws.append(list(rows[0]))
    for r in rows: ws.append(list(r.values()))
    for c in ws[1]: c.font = Font(bold=True)
    for i, wd in enumerate([44, 10, 16, 10, 50, 8, 12, 8, 10, 34, 34, 8, 12, 12, 16, 10,
                            10, 18, 24, 24, 8, 20, 8, 12, 10], 1):
        ws.column_dimensions[get_column_letter(i)].width = wd
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(D / "R28-C_抽取机会与阶段覆盖对账.xlsx")

    # ---- XLSX: 110 条归因（不含 partial/其他） ----
    miss = [r for r in rows if r["R28B标签"] == "missing_extraction"]
    wb2 = openpyxl.Workbook(); s2 = wb2.active; s2.title = "C4_未匹配归因"
    cols = ["gold_id", "协议", "文档", "跨度", "Gold命题", "文档Norm数", "同跨度Norm",
            "文档范围候选", "候选数", "在散文缓存文档内", "散文缓存complete",
            "通道适用", "通道实际执行", "C4归因"]
    s2.append(cols)
    for r in miss: s2.append([r[c] for c in cols])
    for c in s2[1]: c.font = Font(bold=True)
    for i, wd in enumerate([44, 10, 16, 10, 50, 10, 20, 30, 8, 14, 14, 12, 18, 38], 1):
        s2.column_dimensions[get_column_letter(i)].width = wd
    wb2.save(D / "R28-C_110条未匹配记录归因.xlsx")

    print("未匹配", len(miss))
    print("C4 分布:", dict(Counter(bucket(r) for r in miss)))
    # 分 kind 需要原始 B1
    by_kind = Counter((kmap.get(r["gold_id"], ""), r["C4归因"]) for r in miss)
    print("未匹配分 kind:", dict(sorted(by_kind.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
