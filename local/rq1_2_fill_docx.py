# -*- coding: utf-8 -*-
"""local/rq1_2_fill_docx.py —— RQ1.2 实验记录表（docx 表 4）回填。

★★ 关键约束：`table_id` **跨会话不稳定**（QA 实测：同一文件先后出现
   `kfdkkqaa` → `d3r7wldb`）→ **严禁硬编码**，必须运行时**三重定位**：

     ① `doc_list_tables` 的 **index**（表 4 = index 4）
     ② **表头文本校验**（表 4 表头含 `n_states(P1)` / `分支覆盖%(P2)`）
     ③ **python-docx body 遍历**：目标表之前最近的非空段落必须含
        `Live555`（区分同文档中其他协议的同名表）

写入范围：**仅 col3..col9**（row 2..5，共 4 行数据行）。
col1（种子来源）/ col2（Fuzzer选择）**不动**。

row/col 均为 **1-based**（与 edsdk 的 doc_set_table_cells 一致）。
填完必须 `save_file`；**不要** `close_file`。

用法:
    E:/app/Anaconda3/python.exe local/rq1_2_fill_docx.py \
        --docx "<abs path>" --summary "<abs path to rq1_2_summary.csv>"
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDSDK = Path(r"D:\app\WorkBuddy\resources\app.asar.unpacked\resources\plugins"
             r"\workbuddy-builtin\skills\workbuddy-local-office-edit\edsdk.py")

#: 表 4 的预期表头签名（任一命中即可）
HEADER_SIGS = ("n_states(P1)", "n_edges(P2)", "分支覆盖%(P2)")
#: 表 4 的数据行数（含表头）
EXPECT_ROWS = 5
#: 表 4 的列数
EXPECT_COLS = 9
#: 目标表之前最近非空段落必须包含的签名
PRECEDING_SIG = "Live555"


def _edsdk_call(tool: str, args: dict) -> str:
    """调用 edsdk.py call <tool> --json '<args>'，返回 stdout+stderr 文本。"""
    cmd = [sys.executable, str(EDSDK), "call", tool,
           "--json", json.dumps(args, ensure_ascii=False)]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def _parse_tables(raw: str) -> list[dict]:
    """从 doc_list_tables 输出里解析出 tables 列表。

    ★ edsdk 的 stdout 可能包含**多个 JSON 对象**（如失败时的
      `{"ok": false, "error": ...}` + 后续输出）→ 不能用
      `find('{')/rfind('}')` 粗暴截取。
      正确做法：逐个候选 `{` 位置用 `raw_decode()` 精确解码，
      取**第一个含 "tables" 数组**的 JSON 对象。
    """
    dec = json.JSONDecoder()
    pos = 0
    last_err = ""
    while True:
        i = raw.find("{", pos)
        if i < 0:
            break
        try:
            data, end = dec.raw_decode(raw[i:])
        except json.JSONDecodeError as e:
            last_err = str(e)
            pos = i + 1
            continue
        tables = data.get("tables") if isinstance(data, dict) else None
        if isinstance(tables, list):
            return tables
        # 记录失败原因，继续找下一个 JSON 对象
        if isinstance(data, dict) and data.get("ok") is False:
            last_err = str(data.get("error"))[:300]
        pos = i + 1
    raise RuntimeError(
        f"doc_list_tables 输出中找不到含 tables 数组的 JSON 对象"
        f"（last_err={last_err}）:\n{raw[:500]}")


def _read_body_tables(docx_path: Path) -> list[list[list[str]]]:
    """用 python-docx 读出 body 中所有表的单元格文本（按 body 顺序）。"""
    try:
        import docx as docx_mod  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(f"需要 python-docx: {e}") from e
    d = docx_mod.Document(str(docx_path))
    out: list[list[list[str]]] = []
    for t in d.tables:
        out.append([[c.text.strip() for c in row.cells] for row in t.rows])
    return out


def _preceding_paragraph(docx_path: Path, table_index: int) -> str:
    """取 body 中第 table_index 张表之前最近的非空段落文本。"""
    try:
        import docx as docx_mod  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(f"需要 python-docx: {e}") from e
    d = docx_mod.Document(str(docx_path))
    tbl_i = 0
    last_text = ""
    for el in d.element.body.iterchildren():
        tag = el.tag.split("}")[-1]
        if tag == "p":
            txt = "".join(el.itertext()).strip()
            if txt:
                last_text = txt
        elif tag == "tbl":
            if tbl_i == table_index:
                return last_text
            tbl_i += 1
    return last_text


def locate_table(tables: list[dict], table_index: int) -> str:
    """三重定位的第 ①② 重：index + 表头签名 → 返回 table_id。

    Raises:
        RuntimeError: 定位失败或命中多个候选（歧义 → 拒绝写，避免写错表）。
    """
    cands = [t for t in tables if int(t.get("index", -1)) == table_index]
    if not cands:
        raise RuntimeError(f"doc_list_tables 中找不到 index={table_index} 的表")
    cands = [t for t in cands
             if all(s in " ".join(t.get("first_row_texts") or [])
                    for s in HEADER_SIGS)]
    if not cands:
        raise RuntimeError(
            f"index={table_index} 的表表头不匹配（需同时含 {HEADER_SIGS}）")
    if len(cands) > 1:
        raise RuntimeError(
            f"定位歧义：index={table_index} 命中 {len(cands)} 个同表头候选 → 拒绝写入")
    t = cands[0]
    if int(t.get("row_count", 0)) != EXPECT_ROWS or \
       int(t.get("col_count", 0)) != EXPECT_COLS:
        raise RuntimeError(
            f"表结构不符：{t.get('row_count')} 行 × {t.get('col_count')} 列"
            f"（期望 {EXPECT_ROWS} × {EXPECT_COLS}）")
    print(f"[定位] index={table_index} + 表头签名命中 → "
          f"table_id={t['table_id']}（运行时取得，非硬编码）")
    return t["table_id"]


def load_summary(path: Path) -> list[list[str]]:
    """读 summary.csv → 4 行数据（按 docx_row 升序）。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"{path} 为空")
    rows.sort(key=lambda r: int(r.get("docx_row") or 0))
    if len(rows) != 4:
        raise RuntimeError(f"{path} 应有 4 行数据，实测 {len(rows)} 行")
    # 表 4 的列顺序：种子来源 | Fuzzer选择 | n_states_P1 | n_states_P2 |
    #               n_edges_P1 | n_edges_P2 | bitmap_cvg_P2 |
    #               unique_crashes_P2 | paths_total_P2
    # → col3..col9 共 7 列
    cols = ("n_states_P1", "n_states_P2", "n_edges_P1", "n_edges_P2",
            "bitmap_cvg_P2", "unique_crashes_P2", "paths_total_P2")
    out: list[list[str]] = []
    for r in rows:
        vals = [str(r.get(c, "") or "").strip() for c in cols]
        if any(v == "" for v in vals):
            raise RuntimeError(f"summary.csv 行 {r.get('docx_row')} 有空值：{vals}")
        out.append(vals)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="RQ1.2 表 4 回填（运行时三重定位，幂等覆写 col3..col9）")
    ap.add_argument("--docx", required=True, help="目标 docx 绝对路径")
    ap.add_argument("--summary", required=True, help="rq1_2_summary.csv 绝对路径")
    ap.add_argument("--table-index", type=int, default=4)
    ap.add_argument("--header-sig", default="n_states(P1)")
    ap.add_argument("--dry-run", action="store_true", help="只打印将写的内容")
    args = ap.parse_args()

    docx_path = Path(args.docx)
    summary_path = Path(args.summary)
    if not docx_path.exists():
        print(f"!! docx 不存在: {docx_path}", file=sys.stderr)
        return 2

    # ---------- 备份（QA 实测：编辑器 SDK 的 open 会话生命周期可能改动/移除
    #            被打开的文件 → 回填前必须留一份可回滚副本）----------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = docx_path.with_suffix(docx_path.suffix + f".bak_{ts}")
    shutil.copyfile(docx_path, backup)
    print(f"[备份] {backup.name}（{backup.stat().st_size} bytes）")

    # ---------- 读回填前的表内容（幂等基线 + 前后对比）----------
    before = _read_body_tables(docx_path)[args.table_index]
    print(f"[回读-前] 表 index={args.table_index} 共 {len(before)} 行")
    for i, row in enumerate(before, 1):
        print(f"    row{i}: {row}")

    # ---------- 运行时三重定位 ----------
    # ★ 必须先 open_file —— 否则 doc_list_tables 报
    #   "ListTables failed: document is not opened."
    #   （实测：不 open 直接 list → JSON-RPC -32603）
    #
    # ★★ 必须带 wait=true —— open_file 默认是**异步**的：
    #   「returns as soon as the load has been kicked off, BEFORE the model is usable」。
    #   不带 wait 时 open 立刻返回，随即调 doc_list_tables 会因文档尚未载入而报
    #   "ListTables failed: document is not opened."（JSON-RPC -32603）。
    #   带 wait=true 会阻塞到 open 真正完成，返回即代表模型可读可改。
    #   若该文件已在编辑器池中（重复打开），open 会自动复用既有会话。
    out_open = _edsdk_call("open_file",
                           {"file_path": str(docx_path), "wait": True})
    print(f"[打开] open_file(wait=true) → {out_open.strip()[:200]}")
    # 兜底重试：极端情况下（并发/会话池抖动）第一次 list 可能仍未就绪
    raw = ""
    for attempt in range(5):
        raw = _edsdk_call("doc_list_tables", {"file_path": str(docx_path)})
        if '"tables"' in raw:
            break
        if attempt < 4:
            print(f"[重试] doc_list_tables 未就绪（{attempt + 1}/5），2 s 后重试")
            time.sleep(2)
    tables = _parse_tables(raw)
    table_id = locate_table(tables, args.table_index)

    # ③ 前置段落校验
    para = _preceding_paragraph(docx_path, args.table_index)
    print(f"[定位] 前置段落: {para[:80]!r}")
    if PRECEDING_SIG.lower() not in para.lower():
        print(f"!! 前置段落不含 {PRECEDING_SIG} —— 拒绝写入（防写错表）",
              file=sys.stderr)
        return 3

    # ---------- 组装 cells（只写 col3..col9）----------
    data = load_summary(summary_path)
    cells: list[dict] = []
    for i, vals in enumerate(data):
        row = 2 + i          # 1-based：row2..row5
        for j, v in enumerate(vals):
            cells.append({"row": row, "col": 3 + j, "text": v})
    print(f"[待写] {len(cells)} 个单元格（row2..row5 × col3..col9）")
    for c in cells:
        print(f"    r{c['row']}c{c['col']} = {c['text']!r}")

    if args.dry_run:
        print("[dry-run] 未写入")
        return 0

    # ---------- 写入 → 保存 ----------
    out = _edsdk_call("doc_set_table_cells",
                      {"file_path": str(docx_path), "table_id": table_id,
                       "cells": cells})
    print(f"[写入] doc_set_table_cells → {out.strip()[:300]}")
    if "error" in out.lower() and "ok" not in out.lower():
        print("!! 写入失败", file=sys.stderr)
        return 4

    out = _edsdk_call("save_file", {"file_id": str(docx_path)})
    print(f"[保存] save_file → {out.strip()[:200]}")

    # ---------- 保存后存在性自检（QA 实测：编辑器会话可能导致文件消失）----------
    if not docx_path.exists():
        print(f"!! 保存后目标文件不存在（可能被编辑器会话移除）→ 从备份恢复",
              file=sys.stderr)
        shutil.copyfile(backup, docx_path)
        print(f"[恢复] 已从 {backup.name} 恢复 → {docx_path}", file=sys.stderr)
        if not docx_path.exists():
            print("!! 恢复失败 —— 目标文件仍不存在，请手动处理", file=sys.stderr)
            return 9
        print("!! 已恢复为回填前内容（本次回填未生效），请重跑", file=sys.stderr)
        return 9

    # ---------- 回读校验 ----------
    after = _read_body_tables(docx_path)[args.table_index]
    print(f"[回读-后] 表 index={args.table_index} 共 {len(after)} 行")
    for i, row in enumerate(after, 1):
        print(f"    row{i}: {row}")

    if len(after) != EXPECT_ROWS:
        print(f"!! 回读行数 {len(after)} != {EXPECT_ROWS}", file=sys.stderr)
        return 5
    # 表头未破坏
    if after[0][:2] != before[0][:2]:
        print(f"!! 表头 col1/col2 被改动：{after[0][:2]} != {before[0][:2]}",
              file=sys.stderr)
        return 6
    # 前两列（种子来源/Fuzzer）未破坏
    for i in range(1, EXPECT_ROWS):
        if after[i][:2] != before[i][:2]:
            print(f"!! row{i+1} 的 col1/col2 被改动："
                  f"{after[i][:2]} != {before[i][:2]}", file=sys.stderr)
            return 7
    # col3..col9 与 summary 一致
    for i, vals in enumerate(data):
        got = after[1 + i][2:9]
        if got != vals:
            print(f"!! row{2+i} 的 col3..col9 回读不一致："
                  f"期望 {vals} 实测 {got}", file=sys.stderr)
            return 8
    print("[校验] ✓ 4 行数据已更新；表头与前两列未破坏；col3..col9 与 summary 一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
