# -*- coding: utf-8 -*-
"""确定性结构抽取（影子）：ABNF 规则 / 位域保留位 / 字段表行。

只做形态识别，不推断原文未写的 MUST；输出带行号，供 Evidence 追溯。
"""
from __future__ import annotations
import re

RE_RULE = re.compile(r"^[ \t]{1,6}([A-Za-z][A-Za-z0-9-]*)[ \t]*=[ \t]*(.+)$")
RE_CONT = re.compile(r"^[ \t]{6,}(.+)$")
RE_MBZ = re.compile(r"\b(MBZ|MUST be (?:set to )?zero|reserved[^.]{0,40}(?:zero|ignored))", re.I)
RE_TABLE = re.compile(r"^[ \t]{2,}([a-z][a-z0-9_-]{1,15})[ \t]{2,}(\d{1,3})[ \t]{2,}([A-Za-z][^\n]{5,})$")


def abnf_rules(lines: list[str]) -> list[dict]:
    out, i = [], 0
    while i < len(lines):
        m = RE_RULE.match(lines[i])
        if not m:
            i += 1
            continue
        name, expr = m.group(1), m.group(2).strip()
        start, j = i, i + 1
        while j < len(lines):
            c = RE_CONT.match(lines[j])
            if not c:
                break
            expr += " " + c.group(1).strip()
            j += 1
        if name.lower() not in ("example",) and len(expr) > 3:
            out.append({"kind": "abnf", "name": name, "expr": expr,
                        "line": start + 1, "end_line": j,
                        "quote": "\n".join(lines[start:j])})
        i = j
    return out


def mbz_bits(lines: list[str]) -> list[dict]:
    out = []
    for i, ln in enumerate(lines):
        m = RE_MBZ.search(ln)
        if m:
            out.append({"kind": "bitfield", "name": m.group(1), "line": i + 1,
                        "end_line": i + 1, "quote": ln.strip()})
    return out


def table_rows(lines: list[str]) -> list[dict]:
    out = []
    for i, ln in enumerate(lines):
        m = RE_TABLE.match(ln)
        if m:
            out.append({"kind": "table", "name": m.group(1), "size": m.group(2),
                        "desc": m.group(3).strip(), "line": i + 1, "end_line": i + 1,
                        "quote": ln.strip()})
    return out


def extract(text: str) -> dict:
    lines = text.split("\n")
    return {"abnf": abnf_rules(lines), "bitfield": mbz_bits(lines),
            "table": table_rows(lines)}
