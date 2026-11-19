# -*- coding: utf-8 -*-
"""R29 RA-2：45 条散文缺口的通道/缓存可用性核查（只读）。"""
from __future__ import annotations

import hashlib
import json
import pathlib
from collections import Counter, defaultdict

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parents[6]
M0 = ROOT / "docs/实施/待办与勘误/M0对账交付"
R28C = M0 / "M1-Q8-V2-E4-R28_Gold复用与质量对账/R28-C_抽取机会与阶段覆盖对账.xlsx"
OUT = M0 / "M1-Q8-V2-E4-R29_RA2_散文缺口核查"
NORMS = ROOT / "guard/_out/_release/norms_machine.json"
CFG = {"DHCPv4": True, "smtp": False, "rtsp": False}
PROTO = {"smtp": "smtp", "rtsp": "rtsp", "DHCPv4": "DHCPv4"}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    wb = openpyxl.load_workbook(R28C, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    data = [dict(zip(hdr, r)) for r in rows[1:]]
    sel = [r for r in data if str(r["C4归因"])[:2] in ("3 ", "4 ") and r["R28B标签"] == "missing_extraction"]
    assert len(sel) == 45, len(sel)

    norms = json.loads(NORMS.read_text(encoding="utf-8"))
    doc_n = Counter()
    for p, items in norms.items():
        for n in items:
            src = n.get("source") or ""
            if "#@" in src:
                doc_n[(p, src.split("#@")[0].replace("file:", ""))] += 1

    cache = json.loads((ROOT / "derived/cache/source_blocks/DHCPv4.prose.json").read_text(encoding="utf-8"))
    c_docs = Counter(i.get("doc") for i in cache.get("items") or [])
    c_complete = cache.get("complete")

    out = []
    for r in sel:
        proto = PROTO.get(r["协议"], r["协议"])
        doc = r["文档"]
        n_doc = doc_n.get((proto, doc), 0)
        in_cache = c_docs.get(doc, 0) > 0
        cfg_on = CFG.get(r["协议"], False)
        if not cfg_on:
            cls = "1 通道未启用（profile 配置关闭）"
        elif n_doc > 0:
            cls = "2 适用块未被选择（通道只处理零产出文档）"
        elif not in_cache:
            cls = "3 冻结缓存不存在"
        elif c_complete is False:
            cls = "4 缓存存在但不完整（complete=false）"
        else:
            cls = "9 证据不足"
        out.append({
            "Gold ID": r["gold_id"], "协议": r["协议"], "文档": doc, "跨度": r["跨度"],
            "R28C 原分类": r["C4归因"], "知识类型": r.get("通道适用", ""),
            "配置开启": "是" if cfg_on else "否（缺省 False）",
            "文档 Norm 数": n_doc, "是否零产出": "是" if n_doc == 0 else "否",
            "缓存条目数": c_docs.get(doc, 0),
            "缓存 complete": str(c_complete),
            "本轮分类": cls,
            "源码依据": ("rfc_extractor.py:4159 开关" if not cfg_on else
                     ("rfc_extractor.py:4162 仅 _unmatched_files" if n_doc else
                      ("prose_semantics.py:619 complete=false 拒收" if in_cache else
                       "未发现该文档的缓存条目"))),
            "核验状态": "已核（源码+缓存）",
        })

    def dump(path, items, title):
        wb2 = openpyxl.Workbook(); s = wb2.active; s.title = title
        s.append(list(items[0]))
        for it in items: s.append(list(it.values()))
        for c in s[1]: c.font = Font(bold=True)
        for i, w in enumerate([42, 9, 16, 10, 30, 10, 14, 10, 10, 10, 12, 40, 40, 16], 1):
            s.column_dimensions[get_column_letter(i)].width = w
        for row in s.iter_rows(min_row=2):
            for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
        wb2.save(path)

    dump(OUT / "R29_RA2_45条散文知识缺口逐条核查.xlsx", out, "RA2_45条")
    sub31 = [x for x in out if x["R28C 原分类"].startswith("3 ")]
    sub14 = [x for x in out if x["R28C 原分类"].startswith("4 ")]
    dump(OUT / "R29_RA2_31条关闭通道归因.xlsx", sub31, "RA2_31条")
    dump(OUT / "R29_RA2_14条缓存拒收归因.xlsx", sub14, "RA2_14条")

    print("总", len(out))
    print("分类", dict(Counter(x["本轮分类"] for x in out)))
    print("31 组", dict(Counter(x["本轮分类"] for x in sub31)))
    print("14 组", dict(Counter(x["本轮分类"] for x in sub14)))
    print("协议", dict(Counter(x["协议"] for x in out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
