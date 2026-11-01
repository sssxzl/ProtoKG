# -*- coding: utf-8 -*-
"""scripts/rq4_analyze.py —— RQ4 实验结果分析与对比出图。

输入：VM 采集出的 ``rq4_summary.csv``（每容器一行）+ 可选的 ``stats_*.txt`` 快照序列
（覆盖率时序）。

指标口径（裁决）
----------------
1. **主指标** = ``bitmap_cvg`` 的终值（AFLNet 自报的边覆盖百分比，跨协议可比）。
2. **主指标（时间对齐口径）** = 在**相同 execs_done** 处比较 ``bitmap_cvg``
   （线性插值到最近点）—— 两组 exec 速率不同，直接比终值不公平。
3. **次要指标** = 官方 ``cov_over_time.csv`` 末行的 ``l_per``（行覆盖 %）与
   ``b_per``（分支覆盖 %）。这是 cov_script 的官方口径，**与 bitmap_cvg 不是同一个量**
   （行覆盖 vs 边覆盖）。二者不一致时**如实同时报告，不做取舍、不做换算**。
4. **辅助指标** = ``unique_crashes`` / ``unique_hangs`` / ``paths_total`` /
   ``max_depth`` / ``stability``。
5. **自证列** = ``seed_files`` / ``seed_regions`` / ``dict_tokens``：
   证明两组之间**只有种子不同**（字典 token 数必须相同 → 字典不是变量）。

输出：
  1. **对比表**（终端 + Markdown）：protorag vs baseline 的逐协议逐指标对比。
  2. **execs_done 对齐的覆盖率**：按 ``execs_done`` 插值取**相同 exec 数**下的
     ``bitmap_cvg``（主指标口径，见设计文档 §7.2）。
  3. **次要指标表**：``l_per`` / ``b_per`` 与 ``bitmap_cvg`` 并列，
     并标注二者是否同向。
  4. **覆盖率时序曲线**（``--plot`` 时出 PNG）：``bitmap_cvg`` 随 execs_done 的变化。
  5. **参数自检汇总**：``param_check`` 列（``command_line`` 逐字比对结果）。

用法:
    python scripts/rq4_analyze.py --summary /home/zxy/rq4/rq4_summary.csv
    python scripts/rq4_analyze.py --summary rq4_summary.csv --out-dir derived/rq4
    python scripts/rq4_analyze.py --summary rq4_summary.csv --plot
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# 参数自检的判定逻辑在 rq4_param_check.py（唯一真源，rq4_collect.sh 也调用它）。
# 两种导入方式都要支持：作为脚本直接跑（scripts/ 在 sys.path 里）
# 与作为包导入（tests/ 里 `from scripts.rq4_analyze import ...`）。
try:  # pragma: no cover - 仅取决于调用方式
    from rq4_param_check import (  # type: ignore[import-not-found]
        OK as PARAM_OK,
        check_command_lines_consistent,
        options_tail,
    )
except ImportError:  # pragma: no cover
    from scripts.rq4_param_check import (  # type: ignore[import-not-found]
        OK as PARAM_OK,
        check_command_lines_consistent,
        options_tail,
    )

#: rq4_collect.sh 写出的列顺序
SUMMARY_COLUMNS = [
    "protocol", "group", "rep", "container", "image",
    "start_time", "last_update", "fuzz_sec",
    "cycles_done", "execs_done", "execs_per_sec",
    "paths_total", "paths_found", "max_depth", "cur_path",
    "stability", "bitmap_cvg", "unique_crashes", "unique_hangs",
    "peak_rss_mb", "param_check", "exit_code", "command_line",
    # 自证列：只有种子不同
    "seed_files", "seed_regions", "dict_tokens",
    # 次要指标：官方 cov_over_time.csv 末行
    "l_per", "b_per",
]

#: 数值型字段
NUMERIC_FIELDS = [
    "start_time", "last_update", "fuzz_sec", "cycles_done", "execs_done",
    "execs_per_sec", "paths_total", "paths_found", "max_depth",
    "stability", "bitmap_cvg", "unique_crashes", "unique_hangs", "peak_rss_mb",
    "seed_files", "seed_regions", "dict_tokens", "l_per", "b_per",
]

#: 对比表展示的主指标（按重要性排序）
COMPARE_FIELDS = [
    ("bitmap_cvg", "bitmap_cvg(%) [主]"),
    ("execs_done", "execs_done"),
    ("execs_per_sec", "execs_per_sec"),
    ("paths_total", "paths_total"),
    ("paths_found", "paths_found"),
    ("max_depth", "max_depth"),
    ("stability", "stability(%)"),
    ("unique_crashes", "unique_crashes"),
    ("unique_hangs", "unique_hangs"),
    ("fuzz_sec", "fuzz_sec"),
    ("peak_rss_mb", "peak_rss_mb"),
]

#: 自证列（证明"两组只有种子不同"）
SELF_CERTIFY_FIELDS = [
    ("seed_files", "seed_files(种子文件数)"),
    ("seed_regions", "seed_regions(AFLNet 分区数)"),
    ("dict_tokens", "dict_tokens(官方字典条目)"),
]

#: 次要指标（官方 cov_over_time.csv 口径）
SECONDARY_FIELDS = [
    ("l_per", "l_per(%) [次要·行覆盖]"),
    ("b_per", "b_per(%) [次要·分支覆盖]"),
]


def _to_int(value: str) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_float(value: str) -> Optional[float]:
    """把 fuzzer_stats 的字段转成 float。

    ★ 必须剥离展示性后缀：
      · ``bitmap_cvg`` = ``"8.75%"``、``stability`` = ``"27.64%"``（百分比字符串）
      · ``execs_per_sec`` 等大数可能写成 ``"1,234"``（千分位逗号）
      直接 ``float()`` 会失败 → 字段变成 None → **主指标 bitmap_cvg 整列丢失**
      （实测踩过：修复前对比表里 bitmap_cvg 全是 "—"）。
      剥离后得到的是**百分数数值本身**（8.75 表示 8.75%），不做除以 100 的换算。
    """
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def load_summary(path: Path) -> list[dict]:
    """读 rq4_summary.csv → list[dict]（数值字段已转型）。"""
    if not path.exists():
        raise SystemExit(f"!! 汇总表不存在: {path}")
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row = {k: (raw.get(k) or "").strip() for k in SUMMARY_COLUMNS}
            for f in NUMERIC_FIELDS:
                row[f] = _to_float(row[f])
            row["rep"] = _to_int(row["rep"]) or 0
            rows.append(row)
    return rows


def load_snapshots(out_root: Path, protocol: str, group: str,
                   rep: int) -> list[tuple[int, float]]:
    """读该容器的 fuzzer_stats 快照序列 → [(execs_done, bitmap_cvg), ...]。

    快照文件名形如 ``stats_<unix_ts>.txt``，按时间戳排序。
    """
    d = out_root / protocol / group / f"r{rep}"
    if not d.is_dir():
        return []
    series: list[tuple[int, float]] = []
    for snap in sorted(d.glob("stats_*.txt"),
                       key=lambda p: _to_int(p.stem.split("_")[-1]) or 0):
        try:
            text = snap.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        execs = _to_int(_extract(text, "execs_done"))
        cov = _to_float(_extract(text, "bitmap_cvg"))
        if execs is not None and cov is not None:
            series.append((execs, cov))
    return series


def _extract(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}\s*:\s*(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def aligned_coverage(series: list[tuple[int, float]],
                     target_execs: int) -> Optional[float]:
    """取 target_execs 处的 bitmap_cvg（线性插值；超界则取端点）。"""
    if not series:
        return None
    pts = sorted(series)
    if target_execs <= pts[0][0]:
        return pts[0][1]
    if target_execs >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= target_execs <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (target_execs - x0) / (x1 - x0)
    return pts[-1][1]


def aggregate(rows: list[dict], protocol: str, group: str) -> dict:
    """按 (protocol, group) 聚合多重复：均值 + 样本数。"""
    sel = [r for r in rows if r["protocol"] == protocol and r["group"] == group]
    agg: dict = {"n": len(sel)}
    for f, _ in COMPARE_FIELDS + SELF_CERTIFY_FIELDS + SECONDARY_FIELDS:
        vals = [r[f] for r in sel if r[f] is not None]
        agg[f] = statistics.fmean(vals) if vals else None
    # 参数自检：任一容器不 OK 则整体不 OK
    checks = {r.get("param_check", "") for r in sel}
    agg["param_check"] = "OK" if checks == {"OK"} else ("|".join(sorted(checks)) or "N/A")
    return agg


def render_secondary(rows: list[dict]) -> str:
    """次要指标表：官方 cov_over_time.csv 的 l_per / b_per 与主指标 bitmap_cvg 并列。

    ★ 为什么要并列而不是二选一：
      ``bitmap_cvg`` 是 AFLNet 自报的**边覆盖**百分比（跨协议可比口径）；
      ``l_per`` 是 cov_script 从 gcov 数据算出的**行覆盖**百分比（官方口径）。
      两者测的不是同一个量，数值不可互相换算，也可能出现**方向相反**
      （例如某组行覆盖更高但边覆盖更低）。
      因此本表**如实同时给出**，并显式标注是否同向 —— 不做取舍、不做加权。

    ★ 「同向」列的语义（**协议级**，不是逐指标行）：
      该协议的 ``bitmap_cvg`` 差值与 ``l_per`` 差值是否**方向一致**。
      · 方向相反 → "否"（同时在下方「口径分歧」段落里列出，必须人工判读）
      · 方向一致（含某一侧差值恰为 0）→ "是"
      · 任一指标缺失 → "—"（无法判定）
      判定与下方「口径一致性检查」段落**共用** ``_direction_conflict``，
      保证两处结论永远一致（历史上表格列有一行死代码把判定无条件覆盖，
      导致"真·同向"也被显示成"否"）。
    """
    lines = ["## 次要指标：官方 l_per / b_per 与主指标 bitmap_cvg 并列", ""]
    lines.append("> `bitmap_cvg` = AFLNet 自报边覆盖；`l_per`/`b_per` = cov_script 行/分支覆盖。")
    lines.append("> 二者不是同一个量，**不换算、不取舍**；方向不一致时如实标注。")
    lines.append("> 「同向」= 该协议的 `bitmap_cvg` 与 `l_per` **差值方向是否一致**（协议级判定）。")
    lines.append("")
    lines.append("| 协议 | 指标 | protorag | baseline | 差值 | 同向 |")
    lines.append("|---|---|---|---|---|---|")
    for proto in sorted({r["protocol"] for r in rows}):
        # ---- 协议级「同向」判定（bitmap_cvg vs l_per）----
        d_bc = _delta(_group_mean(rows, proto, "protorag", "bitmap_cvg"),
                      _group_mean(rows, proto, "baseline", "bitmap_cvg"))
        d_lp = _delta(_group_mean(rows, proto, "protorag", "l_per"),
                      _group_mean(rows, proto, "baseline", "l_per"))
        conflict = _direction_conflict(d_bc, d_lp)
        same = "—" if conflict is None else ("否" if conflict else "是")

        for field, label in SECONDARY_FIELDS + [("bitmap_cvg", "bitmap_cvg(%) [主]")]:
            c1 = _group_mean(rows, proto, "protorag", field)
            c2 = _group_mean(rows, proto, "baseline", field)
            if c1 is None or c2 is None:
                lines.append(f"| {proto} | {label} | "
                             f"{'—' if c1 is None else f'{c1:.2f}'} | "
                             f"{'—' if c2 is None else f'{c2:.2f}'} | — | — |")
                continue
            diff = c1 - c2
            lines.append(f"| {proto} | {label} | {c1:.2f} | {c2:.2f} | "
                         f"{diff:+.2f} | {same} |")
    lines.append("")

    # —— 明确标注 bitmap_cvg 与 l_per 不一致的协议 ——
    conflicts: list[str] = []
    missing: list[str] = []
    for proto in sorted({r["protocol"] for r in rows}):
        d_bc = _delta(_group_mean(rows, proto, "protorag", "bitmap_cvg"),
                      _group_mean(rows, proto, "baseline", "bitmap_cvg"))
        d_lp = _delta(_group_mean(rows, proto, "protorag", "l_per"),
                      _group_mean(rows, proto, "baseline", "l_per"))
        if d_bc is None or d_lp is None:
            missing.append(proto)
            continue
        if _direction_conflict(d_bc, d_lp):
            conflicts.append(
                f"{proto}: bitmap_cvg 差值 {d_bc:+.2f} 与 l_per 差值 {d_lp:+.2f} "
                f"**方向相反** → 两个口径给出不同结论，需人工判读")
    if conflicts:
        lines.append("### ⚠ 口径分歧（必须人工判读）")
        lines.append("")
        for c in conflicts:
            lines.append(f"- {c}")
    elif missing:
        # ★ 诚实处理：次要指标缺失时**不能**说"无分歧"（那是"没数据"不是"一致"）
        lines.append("### 口径一致性检查")
        lines.append("")
        all_missing = len(missing) == len({r["protocol"] for r in rows})
        if all_missing:
            lines.append(
                f"- **全部协议**（{', '.join(missing)}）都缺 l_per/b_per"
                f"（`cov_over_time.csv` 尚未生成 —— 它由 fuzz 结束后的 cov_script 产出）"
                f"→ **本次无法做口径一致性判定**。")
        else:
            lines.append(f"- 以下协议缺 l_per/b_per（`cov_over_time.csv` 尚未生成 —— "
                         f"它由 fuzz 结束后的 cov_script 产出），**无法判定口径是否一致**："
                         f"{', '.join(missing)}")
            lines.append(f"- 其余协议的 `bitmap_cvg` 与 `l_per` 差值方向一致。")
    else:
        lines.append("### 口径一致性检查")
        lines.append("")
        lines.append("- 所有协议的 `bitmap_cvg` 与 `l_per` 差值方向一致（无分歧）。")
    lines.append("")
    return "\n".join(lines)


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """两组均值之差（任一缺失则返回 None）。"""
    if a is None or b is None:
        return None
    return a - b


def _group_mean(rows: list[dict], protocol: str, group: str,
                field: str) -> Optional[float]:
    """某协议某组某字段的均值（该组无有效样本则返回 None）。"""
    sel = [r[field] for r in rows
           if r["protocol"] == protocol and r["group"] == group
           and r.get(field) is not None]
    return statistics.fmean(sel) if sel else None


def _direction_conflict(d_bc: Optional[float],
                         d_lp: Optional[float]) -> Optional[bool]:
    """``bitmap_cvg`` 与 ``l_per`` 两个口径的差值方向是否冲突。

    Returns:
        ``True``  = 方向相反（口径分歧，必须人工判读）
        ``False`` = 方向一致（含某一侧差值恰为 0 的情形）
        ``None``  = 数据缺失，无法判定

    ★ **表格「同向」列与「口径一致性检查」段落共用本函数** ——
      两处判定永不打架（历史上表格列有一行死代码把判定无条件覆盖，
      导致"真·同向"也被显示成"否"）。
    """
    if d_bc is None or d_lp is None:
        return None
    if d_bc == 0 or d_lp == 0:
        # 有一侧差值为 0 → 不构成方向冲突（与历史口径一致性判定保持一致）
        return False
    return (d_bc > 0) != (d_lp > 0)


def audit_param_consistency(rows: list[dict]) -> list[str]:
    """跨容器参数自检审计：同协议所有容器的 command_line 必须逐字一致。

    ★ 为什么需要这一层
    ------------------
    ``param_check`` 列（规则 1）只比对 **OPTIONS 段**，能挡住
    "OPTIONS 抄错/漂移"。但**服务端命令之后**多出的杂选项
    （例如 ``... ./testOnDemandRTSPServer 8554 -X extra``）不在 OPTIONS 窗口里，
    规则 1 看不见 —— 而服务端自己的参数（``-f``/``-L``/``-Y``/``-n``/``-D``/``-E``）
    长得就像选项，**不能**靠"数 -开头的 token"来判断。

    同协议、同一次编排下，afl-fuzz 的调用形态只随**协议**变化（官方 run 脚本固定），
    唯一随容器变化的是 ``-o <outdir>``。故把 ``-o`` 的值遮蔽后，
    同协议所有容器（两组 × 全部 rep）的 command_line 必须**逐字相同** ——
    这条不依赖任何镜像内部知识（不硬编码服务端命令），却能挡住**任何位置**
    的命令行漂移。

    Returns:
        问题描述列表（空列表 = 全部一致）。
    """
    problems: list[str] = []
    for proto in sorted({r["protocol"] for r in rows}):
        sel = [r for r in rows
               if r["protocol"] == proto and (r.get("command_line") or "").strip()]
        if len(sel) < 2:
            continue
        consistent, reason = check_command_lines_consistent(
            [r["command_line"] for r in sel])
        if not consistent:
            names = ", ".join(sorted(r["container"] for r in sel))
            problems.append(f"{proto}: {reason}（涉及容器: {names}）")
            continue
        # 逐字一致还不够：再确认各容器的**服务端命令尾巴**也一致
        # （遮蔽 outdir 的整行比对已覆盖，这里做二次显式校验，便于定位）
        tails = {options_tail(r["command_line"], "", "") for r in sel}
        tails.discard(None)
        if len(tails) > 1:
            names = ", ".join(sorted(r["container"] for r in sel))
            problems.append(f"{proto}: 各容器的服务端命令尾巴不一致（涉及容器: {names}）")
    return problems


def render_self_certify(rows: list[dict]) -> str:
    """自证表：证明两组之间**只有种子不同**。

    - ``seed_files`` / ``seed_regions``：允许不同（这正是实验变量）。
    - ``dict_tokens``：**必须相同** —— 字典是两组共用的官方字典，
      若不同则说明实验引入了字典这一额外变量。
    """
    lines = ["## 自证：两组之间只有种子不同", ""]
    lines.append("| 协议 | 组 | seed_files | seed_regions | dict_tokens | 字典一致 |")
    lines.append("|---|---|---|---|---|---|")
    for proto in sorted({r["protocol"] for r in rows}):
        for group in sorted({r["group"] for r in rows
                             if r["protocol"] == proto}):
            sel = [r for r in rows
                   if r["protocol"] == proto and r["group"] == group]
            sf = statistics.fmean([r["seed_files"] for r in sel
                                   if r.get("seed_files") is not None]) \
                if any(r.get("seed_files") is not None for r in sel) else None
            sr = statistics.fmean([r["seed_regions"] for r in sel
                                   if r.get("seed_regions") is not None]) \
                if any(r.get("seed_regions") is not None for r in sel) else None
            dt = statistics.fmean([r["dict_tokens"] for r in sel
                                   if r.get("dict_tokens") is not None]) \
                if any(r.get("dict_tokens") is not None for r in sel) else None
            lines.append(
                f"| {proto} | {group} | "
                f"{'—' if sf is None else f'{sf:.0f}'} | "
                f"{'—' if sr is None else f'{sr:.1f}'} | "
                f"{'—' if dt is None else f'{dt:.0f}'} | |")
        # 字典一致性
        dts = {r.get("dict_tokens") for r in rows if r["protocol"] == proto
               and r.get("dict_tokens") is not None}
        if len(dts) > 1:
            lines.append(f"| {proto} | **字典一致性** | | | | "
                         f"**✗ 不一致 {sorted(dts)}** |")
        elif dts:
            lines.append(f"| {proto} | **字典一致性** | | | | ✓ 相同（{dts.pop()}） |")
        else:
            lines.append(f"| {proto} | **字典一致性** | | | | — 未知 |")
    lines.append("")
    return "\n".join(lines)


def render_table(rows: list[dict]) -> str:
    """渲染对比表（Markdown）。"""
    protocols = sorted({r["protocol"] for r in rows})
    groups = sorted({r["group"] for r in rows})
    lines: list[str] = []
    lines.append("## RQ4 结果对比（protorag vs baseline）")
    lines.append("")
    for proto in protocols:
        lines.append(f"### {proto}")
        lines.append("")
        header = ["指标"] + [f"{g} (n={aggregate(rows, proto, g)['n']})" for g in groups]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for f, label in COMPARE_FIELDS:
            cells = []
            for g in groups:
                agg = aggregate(rows, proto, g)
                v = agg.get(f)
                cells.append("—" if v is None else f"{v:.2f}")
            lines.append("| " + " | ".join([label] + cells) + " |")
        # 自证列（种子 / 字典）
        for f, label in SELF_CERTIFY_FIELDS:
            cells = []
            for g in groups:
                agg = aggregate(rows, proto, g)
                v = agg.get(f)
                cells.append("—" if v is None else f"{v:.2f}")
            lines.append("| " + " | ".join([label] + cells) + " |")
        # 次要指标（官方 cov_over_time 口径）
        for f, label in SECONDARY_FIELDS:
            cells = []
            for g in groups:
                agg = aggregate(rows, proto, g)
                v = agg.get(f)
                cells.append("—" if v is None else f"{v:.2f}")
            lines.append("| " + " | ".join([label] + cells) + " |")
        # 参数自检
        cells = [aggregate(rows, proto, g)["param_check"] for g in groups]
        lines.append("| " + " | ".join(["参数自检(command_line)"] + cells) + " |")
        lines.append("")
    return "\n".join(lines)


def render_aligned(rows: list[dict], out_root: Path) -> str:
    """execs_done 对齐的覆盖率对比（主指标口径）。

    ★ 多重复（REPS>1）的正确做法
    ----------------------------
    绝不能把**多个 rep 的快照合并成一条序列**再插值 —— 合并后序列在 execs_done
    上是交错的，插值会**跨越 rep 边界**取值，产生统计上无效的差值
    （QA 实测：两个 rep 反向偏移、真实均值差 = 0.00 的构造，合并插值会给出
     +2.00 / -2.00 / +4.00 的**虚假信号**）。

    正确口径：
      1. **公共 execs 窗口** = 两组各自 execs_done 序列的公共重叠区间
         [max(起点), min(终点)]（语义与单 rep 时一致）。
      2. **每个 rep 各自插值**：在 rep 自己的快照序列上做线性插值。
      3. **先在 rep 内求差**（protorag - baseline），**再跨 rep 求均值**
         （并报告参与统计的 rep 数 n）。

    ★ 向后兼容：REPS=1 时只有一个 rep，窗口与插值结果与合并写法**完全等价**
      （QA 已对过 12 个点的数值，改动后必须保持不变）。
      为此，多 rep 的"参与统计的 rep 数 n"以**脚注**形式追加在表后，
      仅当存在 n>1 的协议时才输出 —— REPS=1 时本函数输出与改动前**逐字节相同**。
    """
    lines = ["## execs_done 对齐的 bitmap_cvg（主指标口径）", ""]
    lines.append("| 协议 | 对齐 execs_done | protorag bitmap_cvg | baseline bitmap_cvg | 差值 |")
    lines.append("|---|---|---|---|---|")
    multi_rep_notes: list[str] = []
    for proto in sorted({r["protocol"] for r in rows}):
        # 每个 rep 各自持有一条快照序列（**绝不合并**）
        per_rep: dict[int, dict[str, list[tuple[int, float]]]] = {}
        reps = sorted({r["rep"] for r in rows if r["protocol"] == proto})
        for rep in reps:
            entry: dict[str, list[tuple[int, float]]] = {}
            for group in ("protorag", "baseline"):
                series = load_snapshots(out_root, proto, group, rep)
                if series:
                    entry[group] = sorted(series)
            # 只有两组都有数据的 rep 才参与统计（避免 n 与实际参与数不符）
            if len(entry) == 2:
                per_rep[rep] = entry
        if not per_rep:
            continue

        # 公共 execs 窗口：所有参与 rep 的两组序列的交集
        lo = max(max(e["protorag"][0][0], e["baseline"][0][0])
                 for e in per_rep.values())
        hi = min(min(e["protorag"][-1][0], e["baseline"][-1][0])
                 for e in per_rep.values())
        if hi <= lo:
            continue

        n_rep = len(per_rep)
        for frac in (0.25, 0.5, 0.75, 1.0):
            target = int(lo + (hi - lo) * frac)
            # 每个 rep 各自插值 → rep 内求差 → 跨 rep 求均值
            diffs: list[float] = []
            c1_sum = 0.0
            c2_sum = 0.0
            for _rep in sorted(per_rep):
                e = per_rep[_rep]
                c1 = aligned_coverage(e["protorag"], target)
                c2 = aligned_coverage(e["baseline"], target)
                if c1 is None or c2 is None:
                    continue
                diffs.append(c1 - c2)
                c1_sum += c1
                c2_sum += c2
            if not diffs:
                continue
            n = len(diffs)
            c1_mean = c1_sum / n
            c2_mean = c2_sum / n
            diff = statistics.fmean(diffs)
            lines.append(f"| {proto} | {target} | {c1_mean:.2f} | {c2_mean:.2f} | "
                         f"{diff:+.2f} |")
        if n_rep > 1:
            multi_rep_notes.append(
                f"- `{proto}`：n = {n_rep} 个 rep（差值为各 rep 差值的均值）")
    lines.append("")
    if multi_rep_notes:
        lines.append("> 多重复口径：每个 rep **各自**插值后先在 rep 内求差，再跨 rep 求均值。")
        lines.extend(multi_rep_notes)
        lines.append("")
    return "\n".join(lines)


def plot_curves(rows: list[dict], out_root: Path, out_dir: Path) -> list[str]:
    """出覆盖率时序曲线 PNG（无 matplotlib 时跳过）。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ["（未安装 matplotlib，跳过绘图）"]

    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    for proto in sorted({r["protocol"] for r in rows}):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        drew = False
        for group in ("protorag", "baseline"):
            reps = sorted({r["rep"] for r in rows
                           if r["protocol"] == proto and r["group"] == group})
            for rep in reps:
                series = load_snapshots(out_root, proto, group, rep)
                if not series:
                    continue
                xs = [p[0] for p in sorted(series)]
                ys = [p[1] for p in sorted(series)]
                ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.2,
                        label=f"{group} r{rep}")
                drew = True
        if not drew:
            plt.close(fig)
            continue
        ax.set_xlabel("execs_done")
        ax.set_ylabel("bitmap_cvg (%)")
        ax.set_title(f"RQ4 {proto}: coverage vs executions")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = out_dir / f"rq4_{proto}_coverage.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        made.append(str(path))
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ4 结果分析与对比")
    ap.add_argument("--summary", required=True, help="rq4_summary.csv 路径")
    ap.add_argument("--out-root", default="/home/zxy/rq4/out",
                    help="结果根目录（用于读 stats_*.txt 快照）")
    ap.add_argument("--out-dir", default="derived/rq4",
                    help="本地产出目录（Markdown / PNG）")
    ap.add_argument("--plot", action="store_true", help="出覆盖率时序曲线 PNG")
    args = ap.parse_args()

    summary = Path(args.summary)
    rows = load_summary(summary)
    if not rows:
        print("!! 汇总表为空", file=sys.stderr)
        return 1

    out_root = Path(args.out_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 参数自检汇总（防抄写漂移）
    bad = [r["container"] for r in rows if r.get("param_check") != "OK"]
    if bad:
        print("!! 参数自检未通过（command_line 与预期不符）：", file=sys.stderr)
        for r in rows:
            if r.get("param_check") != "OK":
                print(f"   {r['container']}: {r.get('param_check')}", file=sys.stderr)
                print(f"     {r.get('command_line', '')[:300]}", file=sys.stderr)

    # 跨容器参数自检审计（同协议各容器的 command_line 必须逐字一致）
    consistency_problems = audit_param_consistency(rows)
    if consistency_problems:
        print("!! 跨容器参数自检未通过（同协议 command_line 不一致）：", file=sys.stderr)
        for p in consistency_problems:
            print(f"   {p}", file=sys.stderr)

    table = render_table(rows)
    print(table)

    self_cert = render_self_certify(rows)
    print(self_cert)

    secondary = render_secondary(rows)
    print(secondary)

    aligned = render_aligned(rows, out_root)
    print(aligned)

    md = out_dir / "rq4_report.md"
    md.write_text(
        f"# RQ4 实验结果\n\n{table}\n{self_cert}\n{secondary}\n{aligned}\n",
        encoding="utf-8")
    print(f"报告: {md}")

    if args.plot:
        made = plot_curves(rows, out_root, out_dir)
        for p in made:
            print(f"图: {p}")
        if not made:
            print("（无快照数据，跳过绘图）")

    (out_dir / "rq4_summary_copy.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if (bad or consistency_problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
