# -*- coding: utf-8 -*-
"""scripts/_fill_rq3_docx.py —— 回填 RQ3 表 18（Live555/RTSP）+ 表注段落。

★ 关键约束：`table_id` **跨会话不稳定**（实测同一文件三次打开得到三个不同的
  table_id）→ **严禁硬编码**，必须在运行时做**三重定位**：
      ① index 校验（表 18 = docx 内部 table index = 18）
      ② 表头签名校验（聚焦组/种子数/dry-run 通过率%/分支覆盖%/崩溃数/变异命中率）
      ③ 前置段落校验（必须是 `Live555（RTSP，text）` —— index 19/20/21 三张表
         表头完全相同，分别对应 BFTPD/Exim/Kamailio）
  定位不到或命中 ≠ 1 个 → **报错退出，不写**。

幂等流程（技术方案 §7.3）：
  1. 备份（仅首次创建，不覆盖）
  2. 运行时定位表
  3. 读当前值
  4. 条件写入（仅当现有文本 ≠ 目标文本；目标为空则跳过）
  5. 保存
  6. 回读校验（python-docx 逐单元格断言）
  7. 表注段落（以 `【RQ3 表 18 注】` 开头，存在则替换，不存在则追加）

用法:
    E:/app/Anaconda3/python.exe scripts/_fill_rq3_docx.py --dry-run
    E:/app/Anaconda3/python.exe scripts/_fill_rq3_docx.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

import rq3_common as C  # noqa: E402

#: 目标 docx（相对项目根）
DOCX_REL = "local/实验方案_详细版.docx"

#: edsdk 路径（本地 Office 编辑 SDK）
EDSDK = Path(r"D:\app\WorkBuddy\resources\app.asar.unpacked\resources\plugins"
             r"\workbuddy-builtin\skills\workbuddy-local-office-edit\edsdk.py")

#: 调用 edsdk 用的 python（ed sdk 自带解释器）
EDSDK_PY = Path(r"E:\python\python.exe")

#: 表 18 的表头签名
TABLE_HEADER = ["聚焦组", "种子数", "dry-run 通过率%", "分支覆盖%", "崩溃数",
                "变异命中率"]

#: 表 18 的前置段落签名（区分 index 19/20/21 的同表头表）
PRECEDING_PARAGRAPH = "Live555（RTSP，text）"

#: 表注段落的固定标记（幂等替换用）
NOTE_MARKER = "【RQ3 表 18 注】"


def _edsdk_call(tool: str, payload: dict) -> str:
    """调用 edsdk 的一个工具，返回合并后的 stdout/stderr。

    Args:
        tool: 工具名（如 doc_list_tables / doc_set_table_cells）。
        payload: 参数字典。

    Returns:
        工具输出文本。
    """
    args = json.dumps(payload, ensure_ascii=False)
    proc = subprocess.run(
        [str(EDSDK_PY), str(EDSDK), "call", tool, "--json", args],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (proc.stdout or "") + (proc.stderr or "")


def locate_rq3_table(tables: list[dict], index_hint: int = 18,
                     protocol: str = "Live555") -> str:
    """定位 RQ3 的目标表（运行时三重定位），返回 table_id。

    Args:
        tables: `doc_list_tables` 的输出（每项含 index / table_id /
            first_row_texts / row_count / col_count）。
        index_hint: 目标表的 index。
        protocol: 目标协议名（用于日志）。

    Returns:
        table_id。

    Raises:
        RuntimeError: 命中候选 ≠ 1 个（**不写**，宁可失败也不误写）。
    """
    cands = []
    for t in tables:
        if int(t.get("index", -1)) != index_hint:
            continue
        hdr = [str(h).replace("\n", "").strip()
               for h in (t.get("first_row_texts") or [])]
        if hdr != TABLE_HEADER:
            continue
        if int(t.get("row_count", -1)) != 4 or int(t.get("col_count", -1)) != 6:
            continue
        cands.append(t)
    if len(cands) != 1:
        raise RuntimeError(
            f"定位失败：命中 {len(cands)} 个候选（index={index_hint}）"
            "—— 拒绝写入")
    print(f"[定位] {protocol} 表 index={index_hint} → "
          f"table_id={cands[0]['table_id']}（运行时取得，非硬编码）")
    return cands[0]["table_id"]


def verify_preceding_paragraph(docx_path: Path, table_index: int = 18) -> str:
    """用 python-docx 遍历 body，取目标表**之前最近的非空段落**文本。

    这是三重定位的第 ③ 重：index 18/19/20/21 四张表表头完全相同，
    必须靠前置段落区分 Live555 / BFTPD / Exim / Kamailio。

    Args:
        docx_path: docx 路径（参数名避开 `docx` 以免遮蔽同名模块）。
        table_index: 目标表在 body 中的顺序（0-based）。

    Returns:
        前置段落文本。

    Raises:
        RuntimeError: 前置段落与预期不符。
    """
    try:
        import docx  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(f"需要 python-docx: {e}")
    d = docx.Document(str(docx_path))
    body = d.element.body
    tbl_idx = 0
    last_text = ""
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = "".join(n.text or "" for n in child.iter()
                           if n.tag.endswith("}t")).strip()
            if text:
                last_text = text
        elif tag == "tbl":
            if tbl_idx == table_index:
                if last_text != PRECEDING_PARAGRAPH:
                    raise RuntimeError(
                        f"前置段落校验失败：期望 {PRECEDING_PARAGRAPH!r}，"
                        f"实际 {last_text!r} —— 拒绝写入")
                print(f"[定位] 前置段落校验通过: {last_text!r}")
                return last_text
            tbl_idx += 1
    raise RuntimeError(f"body 中找不到第 {table_index} 张表")


def _read_table_cells(docx_path: Path, table_index: int = 18) -> list[list[str]]:
    """用 python-docx 读出目标表的全部单元格文本（回读校验用）。"""
    import docx
    d = docx.Document(str(docx_path))
    tbl = d.tables[table_index]
    return [[cell.text for cell in row.cells] for row in tbl.rows]


def _format_cells(metrics: dict) -> list[dict]:
    """按技术方案 §7.2 的格式规范生成待写单元格。

    | 列 | 格式 | 例 |
    |---|---|---|
    | 种子数 | 单值整数 | `50` |
    | dry-run 通过率% | 单值，1 位小数 | `84.0` |
    | 分支覆盖% | `均值 ± 标准差` | `10.37 ± 0.09` |
    | 崩溃数 | `Δ(P2−P1)` + 括注 P2 总数 | `0 (P2=0)` |
    | 变异命中率 | `均值 ± 标准差`（%，1 位小数） | `3.10 ± 0.41` |

    ★ 崩溃列（v2 修正）：**不得把所有行都填 0**。RQ1.2 实测崩溃是
    **概率性、晚发**的（基线组 seed_reuse_aflnet_r1 = 7、r3 = 1，
    protorag 组 10 个容器全 0，首次出现约在启动后 9.2h / 9.9h）。
    → 崩溃为 0 的行写 `0 (P2=0)` 并加注「不具区分度」；
      非 0 的行写真实值。

    Args:
        metrics: `metrics_<g>.json` 的内容。

    Returns:
        `[{row, col, text}]` 列表（row/col 均 1-based）。
    """
    def f(v, spec="{:.2f}"):
        return C.fmt(v, spec)

    dry = metrics.get("M2_dryrun", {}).get("rv")
    cov = metrics.get("M3_coverage", {})
    cr = metrics.get("M4_crashes", {})
    mhr = metrics.get("M5_mhr", {}).get("A_targeted", {})
    seeds = metrics.get("M1_seed_count_design", "")

    crash_txt = ""
    p1 = cr.get("p1_total")
    p2 = cr.get("p2_total")
    if p1 is not None and p2 is not None:
        crash_txt = f"{int(round(p2 - p1))} (P2={int(round(p2))})"
        if (p2 or 0) == 0:
            crash_txt += "（未观测到可复现崩溃，不具区分度）"
    elif p2 is not None:
        # P1 缺失时至少报 P2 总数（不静默填 0）
        crash_txt = f"P2={int(round(p2))}"
        if (p2 or 0) == 0:
            crash_txt += "（未观测到可复现崩溃，不具区分度）"

    return [
        {"row": 2, "col": 2, "text": str(seeds)},
        {"row": 2, "col": 3, "text": f(dry, "{:.1f}")},
        {"row": 2, "col": 4, "text": f"{f(cov.get('mean'))} ± {f(cov.get('std'))}"},
        {"row": 2, "col": 5, "text": crash_txt},
        {"row": 2, "col": 6, "text": f(mhr.get("pooled"))},
    ]


def _note_paragraph(cfg: dict, metrics: dict) -> str:
    """生成表 18 下方的表注文本（技术方案 §7.2 的 10 条）。"""
    dry = metrics.get("M2_dryrun", {})
    cov = metrics.get("M3_coverage", {})
    mhr = metrics.get("M5_mhr", {})
    dict_md5 = cfg["base_dict_md5"]
    frozen = C.RQ3_ROOT / "dict" / "DICT_FROZEN.json"
    tgt_md5 = "（见附录 DICT_FROZEN.json）"
    if frozen.exists():
        for r in C.read_json(frozen).get("dictionaries", []):
            if r.get("kind") == "targeted":
                tgt_md5 = r.get("md5", tgt_md5)
    n = cfg["stats"]["min_reachable_p_n5v5"]
    return (
        f"{NOTE_MARKER}"
        "① 种子集合关系：A 的 38 条与 B 的前 38 条逐字节相同（均为自然序）；"
        "B ≡ C ≡ D 种子集合完全相同（仅顺序/字典不同）。"
        f"② 字典：A/B/D = 基础 24 token（MD5 {dict_md5}）；"
        f"C = 定向 123 token（MD5 {tgt_md5}）；C 字典严格包含 A/B/D 的 24 token。"
        "③ 崩溃列口径：Δ(P2−P1)，括号内为 P2 总数。"
        "④ 崩溃数：本次窗口未观测到可复现崩溃时，该列不具区分度，"
        "结论依据变异命中率/分支覆盖/路径增长等次级指标。"
        f"⑤ rep = {len(cfg['reps'])}；统计检验为 Mann-Whitney 精确检验 + Holm 校正；"
        f"附最小可达 p 下界（n=5 vs 5 → {n}）。"
        "⑥ 变异命中率主口径 = MHR_A（定向命中，池化比率），"
        "附录给 MHR_B / MHR_C 与「每条种子平均派生条目数」。"
        "⑦ A→B 非单变量声明：A→B 同时含「新增 ③ 层」与「种子数 38→50」两个因素；"
        "纯净单变量结论以 B→D→C 为准。"
        "⑧ ChatAFL LLM 增强关闭声明：RQ3 全部容器以 --network none 运行，"
        "ChatAFL 启动期 LLM 增强与运行时 stall-chat 均已关闭"
        "（enrichment_audit.csv 记录 orig:enriched* 恒为 0、chat_times 恒为 0）；"
        "故 RQ3 的 chatafl 行与 RQ1.2 的 chatafl 行不可直接横向比较。"
        "⑨ D 组说明：D 组为解耦对照（B 同集合 + 仅排序 + 基础字典），"
        "进附录表 R3-1，不占表 18 三行。"
        "⑩ 铁律声明：全程全量种子、不截断、不复制；聚焦 = 排序 + 定向字典重分配变异预算。"
    )


def _replace_note_paragraph(docx_path: Path, text: str) -> bool:
    """幂等写入表注段落（存在则替换，不存在则追加）。

    Args:
        docx_path: docx 路径。
        text: 表注完整文本。

    Returns:
        True = 发生了写入；False = 已是目标文本（未写入）。
    """
    import docx
    d = docx.Document(str(docx_path))
    for p in d.paragraphs:
        if p.text.strip().startswith(NOTE_MARKER):
            if p.text.strip() == text.strip():
                return False
            # 保留首段的 run 格式，只改文本
            for r in list(p.runs)[1:]:
                r._element.getparent().remove(r._element)
            if p.runs:
                p.runs[0].text = text
            else:
                p.add_run(text)
            d.save(str(docx_path))
            return True
    d.add_paragraph(text)
    d.save(str(docx_path))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="回填 RQ3 表 18（docx）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只计算目标文本并打印，不写文件")
    ap.add_argument("--docx", default=None, help="目标 docx 路径")
    ap.add_argument("--metrics-dir", default=None,
                    help="metrics_<g>.json 所在目录（默认 derived/rq3）")
    args = ap.parse_args()

    cfg = C.load_config()
    docx_path = Path(args.docx) if args.docx else (ROOT / DOCX_REL)
    if not docx_path.exists():
        print(f"!! docx 不存在: {docx_path}", file=sys.stderr)
        print("   （提示：Git Bash 的 /tmp/... 与 Windows Python 的路径解析不同，"
              "请传 Windows 绝对路径，如 C:\\Users\\...\\Temp\\x.docx）",
              file=sys.stderr)
        return 1
    metrics_dir = Path(args.metrics_dir) if args.metrics_dir else C.RQ3_ROOT

    # ---- 读指标 ----
    metrics = {}
    missing = []
    for g in ("A", "B", "C"):
        p = metrics_dir / f"metrics_{g}.json"
        if not p.exists():
            missing.append(g)
            continue
        metrics[g] = C.read_json(p)
    if missing:
        msg = (f"缺少指标文件: {', '.join(missing)}"
               "（实验未采集完？先跑 scripts/rq3_metrics.py）")
        if args.dry_run:
            # dry 模式：只报告缺哪些指标，不视为失败（实验数据尚未产生）
            print(f"!! {msg}")
            print("dry-run：目标单元格需要 metrics_<g>.json 才能计算；"
                  "本次实验数据未产生，跳过。")
            return 0
        print(f"!! {msg}", file=sys.stderr)
        return 1

    cells = []
    for g, row in (("A", 2), ("B", 3), ("C", 4)):
        for c in _format_cells(metrics[g]):
            cells.append({"row": row, "col": c["col"], "text": c["text"]})

    print("=== 待写单元格 ===")
    for c in cells:
        print(f"  row {c['row']} col {c['col']}: {c['text']!r}")

    if args.dry_run:
        print("\n(dry-run：未写入)")
        return 0

    # ---- 1. 备份（仅首次）----
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = docx_path.with_suffix(f".docx.bak_{ts}")
    if not list(docx_path.parent.glob(docx_path.name + ".bak_*")):
        shutil.copyfile(docx_path, backup)
        print(f"[备份] {backup.name}")

    # ---- 2. 运行时定位（index + 表头签名 + 前置段落）----
    if not EDSDK.exists():
        print(f"!! 找不到 edsdk: {EDSDK}", file=sys.stderr)
        return 1
    # 打开文档（edsdk 的表格工具要求文档处于已打开状态）
    out = _edsdk_call("open_file", {"file_path": str(docx_path)})
    if "error" in out.lower() and "ok" not in out.lower():
        print(f"!! open_file 失败:\n{out[:400]}", file=sys.stderr)
        return 1
    try:
        out = _edsdk_call("doc_list_tables", {"file_path": str(docx_path)})
        try:
            tables = json.loads(out)
        except json.JSONDecodeError:
            print(f"!! doc_list_tables 输出解析失败:\n{out[:500]}", file=sys.stderr)
            _edsdk_call("close_file", {"file_path": str(docx_path)})
            return 1
        if isinstance(tables, dict):
            tables = tables.get("tables", [])
        try:
            table_id = locate_rq3_table(tables,
                                       index_hint=cfg["docx"]["table_index"])
            verify_preceding_paragraph(docx_path,
                                       table_index=cfg["docx"]["table_index"])
        except RuntimeError as e:
            print(f"!! {e}", file=sys.stderr)
            _edsdk_call("close_file", {"file_path": str(docx_path)})
            return 3
    except Exception as e:  # noqa: BLE001
        print(f"!! 定位过程异常: {e}", file=sys.stderr)
        _edsdk_call("close_file", {"file_path": str(docx_path)})
        return 3

    # ---- 3. 读当前值 + 4. 条件写入 ----
    current = _read_table_cells(docx_path, cfg["docx"]["table_index"])
    to_write = []
    for c in cells:
        try:
            cur = current[c["row"] - 1][c["col"] - 1].strip()
        except IndexError:
            cur = ""
        if c["text"] == "":
            continue                      # 目标为空 → 跳过，不覆盖人工填写
        if cur != c["text"]:
            to_write.append(c)
    if not to_write:
        print("[写入] 目标单元格已是目标文本（幂等，无需写入）")
    else:
        print(f"[写入] {len(to_write)} 个单元格需要更新")
        _edsdk_call("doc_set_table_cells",
                    {"file_path": str(docx_path), "table_id": table_id,
                     "cells": to_write})
        _edsdk_call("save_file", {"file_path": str(docx_path)})
        _edsdk_call("close_file", {"file_path": str(docx_path)})

    # ---- 6. 回读校验 ----
    after = _read_table_cells(docx_path, cfg["docx"]["table_index"])
    bad = []
    for c in cells:
        if not c["text"]:
            continue
        got = after[c["row"] - 1][c["col"] - 1].strip()
        if got != c["text"]:
            bad.append((c["row"], c["col"], c["text"], got))
    if bad:
        print("!! 回读校验不一致:", file=sys.stderr)
        for r, c, want, got in bad:
            print(f"   row {r} col {c}: 期望 {want!r} 实际 {got!r}",
                  file=sys.stderr)
        return 4
    print("[校验] 逐单元格回读一致 ✓")

    # ---- 7. 表注段落（幂等）----
    note = _note_paragraph(cfg, metrics["C"])
    if _replace_note_paragraph(docx_path, note):
        print("[表注] 已写入/替换")
    else:
        print("[表注] 已是目标文本（幂等）")

    # ---- 8. 附录 md（默认不写 docx 表格）----
    appendix = C.RQ3_ROOT / "appendix_r3_1.md"
    lines = ["# 附录 R3-1：D 组（解耦对照）六项指标", ""]
    d_path = metrics_dir / "metrics_D.json"
    if d_path.exists():
        md = C.read_json(d_path)
        lines += ["| 指标 | 值 |", "|---|---|"]
        lines.append(f"| 分支覆盖% | {C.fmt(md.get('M3_coverage', {}).get('mean'))} "
                     f"± {C.fmt(md.get('M3_coverage', {}).get('std'))} |")
        lines.append(f"| dry-run 通过率% | {C.fmt(md.get('M2_dryrun', {}).get('rv'), '{:.1f}')} |")
        lines.append(f"| MHR_A（定向命中） | {C.fmt(md.get('M5_mhr', {}).get('A_targeted', {}).get('pooled'))} |")
        lines.append(f"| MHR_B（③层归因） | {C.fmt(md.get('M5_mhr', {}).get('B_layer3', {}).get('pooled'))} |")
        cc = md.get("M5_mhr", {}).get("C_crash", {})
        lines.append(f"| MHR_C（崩溃归因） | "
                     f"{C.fmt(cc.get('value')) if cc.get('value') is not None else 'N/A'} |")
        lines.append(f"| 每条种子平均派生条目数 | {C.fmt(md.get('M5_mhr', {}).get('derived_per_seed'))} |")
    lines += ["", "## 字典冻结摘要", ""]
    if (C.RQ3_ROOT / "dict" / "DICT_FROZEN.json").exists():
        for r in C.read_json(C.RQ3_ROOT / "dict" / "DICT_FROZEN.json").get("dictionaries", []):
            lines.append(f"- `{r.get('kind')}`：{r.get('token_count')} token，"
                         f"MD5 `{r.get('md5')}`")
    appendix.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[附录] {appendix}")

    print("\n回填完成 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
