# -*- coding: utf-8 -*-
"""RFC 内容形态普查（协议无关、零 LLM、只读）。

★ 动因：方案设计滑向了「按章节位置/按某个协议」思考（例：只关心 RTSP 附录）。
  正确的通用定位是：**按 RFC 文本的客观形态分类**，与协议无关、与章节位置无关。
  ⇒ 先用数据回答「RFC 里到底有哪些形态、各占多少」，再据此设计分类器。

★ 分类判据（全部基于 RFC 的**排版/语法客观特征**，不含任何协议特定规则）：
  ┌ boilerplate  RFC 抬头/页眉页脚/分页符/作者地址
  ├ toc          目录行（大量连续点号 + 页码）
  ├ table        连续多行的**列式**块（列间 2+ 空格或 tab 分隔）
  ├ diagram      含图形字符（+ - | < > / \\ 等组合）的图示区
  ├ figure_cap   "Figure N." / "图 N" 形式的图题
  ├ abnf         ABNF 规则定义（`::=` 或 `name = ...`）
  ├ example      示例报文块（缩进 + 以协议方法名开头的请求行）
  ├ normative    含 MUST/SHALL/SHOULD/REQUIRED/MAY 的**规范性**句
  └ descriptive  其余散文

★ 输出：每个协议的**行级**形态分布 + **块级**候选规模（块 = 连续同类行），
  并列出各类别的**代表性样例**（供人工核对判据是否合理）。

用法：E:/app/Anaconda3/python.exe local/_census_rfc_forms.py [协议...]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402

# ── 形态判据（协议无关）──────────────────────────────────────────────
RE_RFC_HEADER = re.compile(r"^\s*Request for Comments:\s*\d+", re.I)
RE_PAGE_BREAK = re.compile(r"\[Page\s+\d+\]|^\s*RFC\s+\d+\s+\S.*\s+\w+\s+\d{4}\s*$")
RE_AUTHOR_ADDR = re.compile(r"Author'?s? Address", re.I)
RE_TOC = re.compile(r"\.{4,}\s*\d+\s*$")
RE_FIGURE_CAP = re.compile(r"^\s*(Figure|Fig\.?|图)\s*\d+", re.I)
RE_ABNF = re.compile(r"::=|^\s*[A-Za-z][A-Za-z0-9\-]{1,30}\s*=\s*\S")
RE_NORMATIVE = re.compile(r"\b(MUST|MUST NOT|SHALL|SHALL NOT|SHOULD|SHOULD NOT|REQUIRED|MAY|OPTIONAL)\b")
#: 图示字符（ASCII art）：★ 收紧 —— 去掉正文常见的 `/ = # * { } v`
#:   （否则 "HTTP/1.1 [2]" 这类正文会被误判为图）
DIAGRAM_CHARS = set("+-|<>^[]")
#: 示例报文行：★ 放宽 —— 「缩进≥2 且 首 token 为全大写单词 + 后跟参数」
#:   （RFC 的示例常不带协议头，只写 "PLAY rtsp://..." 或 "MAIL FROM:<x>"）
RE_EXAMPLE = re.compile(r"^\s{2,}([A-Z][A-Z_]{1,15})\s+\S")
#: 列式行：至少两处 2+ 空格或 tab 的分隔
RE_COLUMNS = re.compile(r"\S[ \t]{2,}\S")


def classify_line(line: str) -> str:
    if RE_TOC.search(line):
        return "toc"
    if RE_RFC_HEADER.search(line) or RE_PAGE_BREAK.search(line) \
            or RE_AUTHOR_ADDR.search(line):
        return "boilerplate"
    if RE_FIGURE_CAP.match(line):
        return "figure_cap"
    if RE_ABNF.search(line):
        return "abnf"
    if RE_EXAMPLE.match(line):
        return "example"
    if RE_NORMATIVE.search(line):
        return "normative"
    # 列式：>=2 处 2+ 空格分隔
    if len(RE_COLUMNS.findall(line.rstrip())) >= 2:
        return "table"
    # 图示：图形字符 >= 3 种
    dg = DIAGRAM_CHARS & set(line)
    if len(dg) >= 3:
        return "diagram"
    return "descriptive"



def split_blocks(lines: list[str]) -> list[list[str]]:
    """切块：连续非空行 = 一个块（paragraph block）。"""
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if ln.strip():
            cur.append(ln)
        else:
            if cur:
                blocks.append(cur)
                cur = []
    if cur:
        blocks.append(cur)
    return blocks


def classify_block(block: list[str]) -> str:
    """块级形态判定（**位置无关、协议无关**）。

    ★ 关键：**形态必须在块级判** —— 行级会互相污染
      （表格块里每行都可能含 MUST；正文行可能含图形字符）。
      判据顺序：boilerplate/toc → 图 → 表 → ABNF → 示例 → 规范性 → 散文。
    """
    if len(block) < 2:
        return "single"
    rows = [ln.rstrip() for ln in block]
    votes: Counter = Counter(classify_line(ln) for ln in rows)
    # ① 图：块内多数行含图形字符，且块长 ≥3
    if len(block) >= 3:
        dg_rows = sum(1 for ln in rows if len(DIAGRAM_CHARS & set(ln)) >= 3)
        if dg_rows / len(rows) >= 0.6:
            return "diagram"
        # ② 表：块内多数行是列式（≥2 处 2+ 空格分隔）
        col_rows = sum(1 for ln in rows if len(RE_COLUMNS.findall(ln)) >= 2)
        if col_rows / len(rows) >= 0.6:
            return "table"
    if votes.most_common(1)[0][0] in ("boilerplate", "toc"):
        return votes.most_common(1)[0][0]
    if votes["abnf"] / len(rows) >= 0.5:
        return "abnf"
    if votes["example"] / len(rows) >= 0.5:
        return "example"
    if votes["normative"] / len(rows) >= 0.3:
        return "normative"
    if votes["table"] / len(rows) >= 0.5:
        return "table"
    return "descriptive"


def census(protocol: str) -> dict:
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    line_counts: Counter = Counter()
    blocks: Counter = Counter()
    samples: dict[str, list[str]] = {}
    total_lines = 0
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines += len(lines)
        prev = None
        run = 0
        for ln in lines:
            k = classify_line(ln)
            line_counts[k] += 1
            if k == prev:
                run += 1
            else:
                if prev in ("table", "diagram", "abnf", "example") and run >= 3:
                    blocks[prev] += 1
                prev, run = k, 1
            s = samples.setdefault(k, [])
            if len(s) < 3 and ln.strip():
                s.append(ln.strip()[:88])
        if prev in ("table", "diagram", "abnf", "example") and run >= 3:
            blocks[prev] += 1
    return {"file": f.name, "total_lines": total_lines,
            "lines": dict(line_counts.most_common()),
            "blocks_ge3": dict(blocks.most_common()),
            "samples": samples}


def main() -> None:
    protocols = sys.argv[1:] or ["rtsp", "sip", "smtp"]
    report: dict = {}
    for protocol in protocols:
        rows = []
        for f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            c: Counter = Counter()
            for ln in lines:
                c[classify_line(ln)] += 1
            rows.append((f.name, len(lines), c))
        report[protocol] = {}
        print("=" * 84)
        print(f"协议 {protocol} —— RFC 内容形态普查（行级）")
        print("=" * 84)
        agg: Counter = Counter()
        tot = 0
        for name, n, c in rows:
            agg.update(c)
            tot += n
            print(f"  {name:<18} {n:>6} 行  " +
                  "  ".join(f"{k}={v}" for k, v in c.most_common(6)))
        print(f"\n  合计 {tot} 行：")
        for k, v in agg.most_common():
            print(f"     {k:<14} {v:>6} 行  {v / tot:>6.1%}")
        report[protocol] = {"total": tot, "lines": dict(agg)}
        print()

    # 块级 + 样例（取 rtsp 作样例核对）
    print("=" * 84)
    print("形态样例核对（判据是否合理）")
    print("=" * 84)
    for protocol in protocols[:1]:
        d = census(protocol)
        print(f"\n── {protocol}（首个 RFC 文件） 块级（连续≥3 行）：{d['blocks_ge3']}")
        for k in ("table", "diagram", "abnf", "example", "normative", "figure_cap"):
            print(f"\n  【{k}】")
            for s in (d["samples"].get(k) or ["(无样例)"]):
                print(f"     {s}")
    # ── 块级普查：形态必须在**块级**判定（行级会互相污染）──────────────
    print("=" * 84)
    print("块级普查（块 = 连续非空行段；形态 = 段内形态投票 + 块级特判）")
    print("=" * 84)
    block_report: dict = {}
    for protocol in protocols:
        agg: Counter = Counter()
        sizes: dict[str, list[int]] = {}
        for f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            for blk in split_blocks(lines):
                kind = classify_block(blk)
                agg[kind] += 1
                sizes.setdefault(kind, []).append(len(blk))
        tot = sum(agg.values())
        print(f"\n── {protocol}：共 {tot} 块")
        for k, v in agg.most_common():
            sz = sizes[k]
            print(f"     {k:<14} {v:>5} 块 ({v / tot:>5.1%})  "
                  f"中位 {sorted(sz)[len(sz) // 2]:>3} 行  最大 {max(sz):>4} 行")
        block_report[protocol] = {"total_blocks": tot,
                                  "blocks": dict(agg.most_common())}
    print()
    p = Path(__file__).resolve().parent / "_census_rfc_forms.json"
    p.write_text(json.dumps({"line_level": report, "block_level": block_report},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
