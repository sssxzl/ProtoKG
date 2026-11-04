# -*- coding: utf-8 -*-
"""local/rq1_2_analyze.py —— RQ1.2 Live555 最终结果统计分析与一致性校验。

输入（只读）：
  · derived/analysis/data/rq1_2/*.csv            最终态（24 h，2026-10-25 11:09 停止）
  · derived/analysis/data/rq1_2_interim_20261024/*.csv   10-24 20:00 中间态
  · derived/analysis/qa_rq1_2/raw/*.{plot_data,fuzzer_stats}   VM 原始数据（可选，独立复算）

产出：
  · derived/analysis/data/rq1_2/rq1_2_analysis.json   机器可读统计结果
  · stdout                                            人读摘要

★★ 表述纪律（硬约束，来自主理人 10-24 指示）：
  1. **aflnet 半侧为 RQ1.2 主证据**（0 LLM 增强、唯一变量成立）；
     chatafl 半侧被启动期 LLM 增强污染 → **降级为辅证**。
  2. **n_edges 不稳健** → 不得声称「稳定探索到更多状态机边」。
  3. 崩溃全在基线组是**结构性事实**（真实流量种子天然携带 matroska UAF
     CVE-2021-38382 / CVE-2021-38381），**不得**解读为「ProtoRAG 不会发现崩溃」。
  4. 覆盖率反超必须给 **win rate + 配对差值 mean±sd + 全部原始差值**，
     并做 Mann–Whitney 精确检验（n=5 vs 5 双侧最小可达 p=0.0079）。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path

REPS = (1, 2, 3, 4, 5)
FUZZERS = ("aflnet", "chatafl")
GROUPS = ("seed_reuse", "protorag")

#: 时序统计的**权威口径**（与采集脚本 rq1_collect_live555.sh 完全一致）：
#:   · 桶中心时刻列表（小时）
#:   · 每个桶取 rel_hours 落在 |rel_hours - h| < 0.2 的**全部**采样点
#:   · 跨 rep 池化后取均值
#: 改用其它口径（如取桶内首个/最后一个采样点）会显著改变 0.5 h 桶的结论，
#: 故 §6 必须使用本口径，并在正文中写明口径敏感性（见 make_record 的 §6.1）。
TS_POINT_BUCKETS = (0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 18.0, 24.0)
TS_BUCKET_TOL = 0.2

#: ★ v7 新增：**区间池化**时序口径（§6 表格改用此口径）。
#:   · 桶为**连续区间** [lo, hi)，边界取自 ``BUCKET_EDGES``
#:   · 每个区间内取跨 rep 的**全部**采样点混池求均值（不是"先分 rep 再平均"）
#:   · 舍入路径：单元格均值 round(·,4) → 差值 round(a-b,4) → 显示 round3
#: 该口径下 aflnet 半侧的反超差值序列为
#:   -0.355 / +0.279 / +0.420 / +0.533 / +0.555 / +0.573 / +0.568 / +0.581 / +0.549
#: （已用 rq1_2_timeseries.csv 独立复算，与主理人给出的清单逐格一致）。
#: 注意：本口径与上面的**点时刻**口径（TS_POINT_BUCKETS + ±0.2h 窗口）**并存**，
#: 两者用途不同：点时刻口径用于"反超时点"判读，区间池化口径用于 §6 表格本身。
BUCKET_EDGES = (0.0, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 18.0, 24.0)


# --------------------------------------------------------------------------
# 基础 IO
# --------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict]:
    """读 CSV（容忍 utf-8-sig / 尾逗号 / 空值）。"""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v) -> float | None:
    """解析数值；'' / 'NA' / None → None；剥离 '%' 与前后空白。"""
    if v is None:
        return None
    s = str(v).strip().replace("%", "").strip()
    if s == "" or s.upper() == "NA":
        return None
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 统计工具
# --------------------------------------------------------------------------
def mw_exact_p(a: list[float], b: list[float]) -> float | None:
    """Mann–Whitney U 双侧精确检验（枚举所有分配，n=5 时共 C(10,5)=252 种）。

    纯 Python 实现，避免引入 scipy 依赖；n=5 时枚举量极小。
    零假设：两样本来自同一分布（所有 C(n+m, n) 种标签分配等可能）。

    双侧 p 值定义：``p = 2 * min(P(U <= u_obs), P(U >= u_obs))``，上限截断到 1.0。
    （注意：**不可**写成 ``P(U <= u_obs or U >= nm - u_obs)`` —— 当两组完全分离
    （u_obs = nm）时该式退化为 P(U >= 0) = 1，恒返回 p = 1，属经典陷阱。）

    Returns:
        双侧 p 值；样本量过大（组合数 > 200000）时返回 None（改用正态近似）。
    """
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return None
    total = n + m
    n_comb = math.comb(total, n)
    if n_comb > 200_000:
        return None

    # 零假设下 U 的分布（枚举『哪些位置被指派为样本 a』的 C(total, n) 种分配）
    # ★ 关键：组合选中的位置**即**被指派为 a 组，其余位置为 b 组；
    #   不能按原始标签过滤，否则枚举的是原始分组而非置换分组（会得到错误分布）。
    pool = list(a) + list(b)
    u_dist: dict[float, int] = defaultdict(int)
    for combo in combinations(range(total), n):
        sel = set(combo)
        g_a = [pool[i] for i in range(total) if i in sel]
        g_b = [pool[i] for i in range(total) if i not in sel]
        u_dist[_u_from_groups(g_a, g_b)] += 1

    u_obs = _u_from_groups(a, b)
    # P(U <= u_obs) 与 P(U >= u_obs)
    p_le = sum(c for u, c in u_dist.items() if u <= u_obs + 1e-9) / n_comb
    p_ge = sum(c for u, c in u_dist.items() if u >= u_obs - 1e-9) / n_comb
    return min(1.0, 2.0 * min(p_le, p_ge))


def _u_from_groups(a: list[float], b: list[float]) -> float:
    """由两组样本算 U1（a 组胜出次数，含 0.5 平局）。"""
    u = 0.0
    for x in a:
        for y in b:
            if x > y:
                u += 1.0
            elif x == y:
                u += 0.5
    return u


def wilcoxon_signed_rank_exact_p(diffs: list[float]) -> float | None:
    """Wilcoxon 符号秩检验（配对样本）双侧**精确** p 值。

    零假设：差值分布关于 0 对称。
    做法：去掉零差值，对 |d| 排序（并列取平均秩），求 W+ ，再枚举 2^k 种
    符号分配统计 W+ 的分布，得到精确 p。

    ★ 重要：n=5 配对时最小可达双侧 p = 2/2^5 = **0.0625** > 0.05，
      即 **配对检验在 n=5 下永远达不到 0.05 显著性**。这一点必须写入记录，
      否则会被误读为「未达显著 = 无差异」。

    Returns:
        双侧 p 值；有效配对数 n_eff = 0 时返回 None。
    """
    d = [x for x in diffs if x != 0]
    k = len(d)
    if k == 0:
        return None

    # 平均秩（并列）
    order = sorted(range(k), key=lambda i: abs(d[i]))
    ranks = [0.0] * k
    i = 0
    while i < k:
        j = i
        while j + 1 < k and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[order[t]] = avg
        i = j + 1

    total = sum(ranks)
    w_plus = sum(r for r, v in zip(ranks, d) if v > 0)
    w_minus = total - w_plus

    # 枚举所有 2^k 符号分配（k ≤ 20 时 2^20 = 1M 尚可；本项目 k ≤ 5）
    if k > 20:
        return None
    dist: dict[float, int] = defaultdict(int)
    for mask in range(1 << k):
        s = 0.0
        for i in range(k):
            if mask >> i & 1:
                s += ranks[i]
        dist[s] += 1
    total_assign = 1 << k
    obs = min(w_plus, w_minus)
    p = sum(c for s, c in dist.items() if s <= obs + 1e-9) / total_assign
    return min(1.0, 2.0 * p)


def sign_test_exact_p(diffs: list[float]) -> float | None:
    """符号检验（配对样本）双侧精确 p 值。

    零假设：正负差值各占一半。n_eff = 5 时最小可达双侧 p = 2/2^5 = 0.0625。
    """
    pos = sum(1 for x in diffs if x > 0)
    neg = sum(1 for x in diffs if x < 0)
    k = pos + neg
    if k == 0:
        return None
    p = sum(math.comb(k, i) for i in range(0, min(pos, neg) + 1)) / (2 ** k)
    return min(1.0, 2.0 * p)


def parse_prose_report(path: Path) -> dict:
    """解析散文核查报告（rq1_2_extra_prose.txt）→ 结构化结果。

    报告含两段：
      · 【C5a】崩溃样本散文核查 —— 每容器一行，格式
        ``rq2_<group>_<fuzzer>_r<rep>: 崩溃样本 N 个，含散文 M 个，含强散文 K 个；标记: ...``
        无崩溃的容器为 ``rq2_...: 无崩溃样本``
      · 【C5b】种子语料溯源 —— 每容器一行，格式
        ``rq2_<group>_<fuzzer>_r<rep>  <entries>  <with_prose>  <pct>  <marker>``

    Returns:
        {"crash_samples": {container: {...}}, "seed_corpus": {container: {...}}}
    """
    out: dict = {"crash_samples": {}, "seed_corpus": {}}
    if not path.exists():
        return out

    text = path.read_text(encoding="utf-8", errors="replace")
    # 切分 C5a / C5b 两段
    section = "crash_samples"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("【C5b】"):
            section = "seed_corpus"
            continue
        if line.startswith("【C5a】"):
            section = "crash_samples"
            continue

        if section == "crash_samples" and line.startswith("rq2_"):
            # 形如：rq2_x: 崩溃样本 15 个，含散文 15 个，含强散文 14 个；标记: a×15, b×3
            head, _, tail = line.partition(":")
            container = head.strip()
            if "无崩溃样本" in tail:
                out["crash_samples"][container] = {
                    "samples": 0, "with_prose": 0, "with_strong_prose": 0,
                    "markers": [],
                }
                continue
            # 三个计数分别独立匹配（不能用 and 串联 —— 那只保留最后一个 match）
            m1 = re.search(r"崩溃样本\s*(\d+)\s*个", tail)
            m2 = re.search(r"含散文\s*(\d+)\s*个", tail)
            m3 = re.search(r"含强散文\s*(\d+)\s*个", tail)
            if not (m1 and m2 and m3):
                continue
            samples, prose, strong = int(m1.group(1)), int(m2.group(1)), int(m3.group(1))
            markers: list[str] = []
            mk = re.search(r"标记:\s*(.*)$", tail)
            if mk and "(无命中)" not in mk.group(1):
                markers = [x.strip() for x in mk.group(1).split(",")
                           if x.strip()]
            out["crash_samples"][container] = {
                "samples": samples, "with_prose": prose,
                "with_strong_prose": strong, "markers": markers,
            }

        elif section == "seed_corpus" and line.startswith("rq2_"):
            # 形如：rq2_x  168  160  95.2%  proper location
            parts = line.split()
            if len(parts) < 4:
                continue
            container = parts[0]
            try:
                entries = int(parts[1])
                with_prose = int(parts[2])
            except ValueError:
                continue
            out["seed_corpus"][container] = {
                "entries": entries, "with_prose": with_prose,
                "pct": parts[3],
                "marker": " ".join(parts[4:]) if len(parts) > 4 else "",
            }
    return out


def paired_stats(diffs: list[float], label: str, unit: str = "") -> dict:
    """配对差值（实验组 − 对照组）的完整统计量。

    Args:
        diffs: 同 rep 配对差值序列。
        label: 指标显示名。
        unit: 单位后缀（''=无；'pp'=百分点）。
    """
    n = len(diffs)
    if n == 0:
        return {"label": label, "unit": unit, "n": 0, "diffs": [],
                "mean": None, "sd": None, "sem": None,
                "wins": 0, "losses": 0, "ties": 0, "win_rate": None,
                "min": None, "max": None, "consistent_sign": None,
                "median": None, "drop_max_abs": None}
    w = sum(1 for d in diffs if d > 0)
    t = sum(1 for d in diffs if d == 0)
    l = sum(1 for d in diffs if d < 0)
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    sem = sd / math.sqrt(n) if n > 1 else 0.0
    out = {
        "label": label, "unit": unit, "n": n,
        "diffs": diffs,
        "mean": m, "sd": sd, "sem": sem,
        "wins": w, "losses": l, "ties": t,
        "win_rate": w / n,
        "min": min(diffs), "max": max(diffs),
        "median": statistics.median(diffs),
        "consistent_sign": (w == n) or (l == n),
    }
    # 去掉最大 |d| 的稳健性复算（离群点敏感性）
    if n > 1:
        idx = max(range(n), key=lambda i: abs(diffs[i]))
        rest = [d for i, d in enumerate(diffs) if i != idx]
        if rest:
            out["drop_max_abs"] = {
                "removed": diffs[idx],
                "mean": statistics.mean(rest),
                "sd": statistics.stdev(rest) if len(rest) > 1 else 0.0,
                "win_rate": sum(1 for d in rest if d > 0) / len(rest),
            }
    return out


def fmt_ps(v: dict) -> str:
    """把 paired_stats 结果渲染成一行 markdown 摘要。"""
    if not v or not v.get("n"):
        return "数据不足（NA）"
    u = f" {v['unit']}" if v.get("unit") else ""
    return (f"win {v['wins']}/{v['n']}={v['win_rate']:.2f}"
            f"（平{v['ties']}/负{v['losses']}）"
            f"，mean±sd = {v['mean']:+.2f}±{v['sd']:.2f}{u}"
            f"，原始差值 [{', '.join(f'{d:+.2f}' for d in v['diffs'])}]"
            f"，一致为正={v['consistent_sign']}")


# --------------------------------------------------------------------------
# 主分析
# --------------------------------------------------------------------------
def build(data_dir: Path, interim_dir: Path | None) -> dict:
    """汇总全部统计结果。"""
    p1 = read_csv(data_dir / "rq1_2_p1.csv")
    p2 = read_csv(data_dir / "rq1_2_p2.csv")
    summ = read_csv(data_dir / "rq1_2_summary.csv")
    ts = read_csv(data_dir / "rq1_2_timeseries.csv")
    crashdist = read_csv(data_dir / "rq1_2_extra_crashdist.csv")
    hangs = read_csv(data_dir / "rq1_2_extra_hangs.csv")
    lineage = read_csv(data_dir / "rq1_2_extra_lineage.csv")
    seedprov = read_csv(data_dir / "rq1_2_extra_seedprovenance.csv")

    idx1 = {(r["group"], r["fuzzer"], r["rep"].strip()): r for r in p1}
    idx2 = {(r["group"], r["fuzzer"], r["rep"].strip()): r for r in p2}

    res: dict = {"source": {"data_dir": str(data_dir),
                             "interim_dir": str(interim_dir) if interim_dir else None}}

    # ---------- 1. 逐容器最终态 ----------
    containers = []
    for g in GROUPS:
        for fz in FUZZERS:
            for rep in REPS:
                r2 = idx2.get((g, fz, str(rep)))
                r1 = idx1.get((g, fz, str(rep)))
                if not r2:
                    continue
                containers.append({
                    "container": f"rq2_{g}_{fz}_r{rep}",
                    "group": g, "fuzzer": fz, "rep": rep,
                    "n_states_P1": num(r1.get("n_states")) if r1 else None,
                    "n_edges_P1": num(r1.get("n_edges")) if r1 else None,
                    "n_states_P2": num(r2.get("n_states")),
                    "n_edges_P2": num(r2.get("n_edges")),
                    "bitmap_cvg_P2": num(r2.get("bitmap_cvg")),
                    "unique_crashes_P2": num(r2.get("unique_crashes")),
                    "unique_hangs_P2": num(r2.get("unique_hangs")),
                    "paths_total_P2": num(r2.get("paths_total")),
                    "execs_done_P2": num(r2.get("execs_done")),
                })
    res["containers"] = containers

    # ---------- 2. docx 表 4 的 4 行（来自 summary.csv） ----------
    res["summary_rows"] = sorted(
        summ, key=lambda r: int(r.get("docx_row") or 0))

    # ---------- 3. 配对统计（protorag − seed_reuse，同 fuzzer 同 rep） ----------
    METRICS = (
        ("bitmap_cvg", "分支覆盖率(P2)", "pp"),
        ("n_edges", "n_edges(P2)", ""),
        ("n_states", "n_states(P2)", ""),
        ("paths_total", "路径数(P2)", ""),
        ("unique_crashes", "唯一崩溃数(P2)", ""),
        ("unique_hangs", "唯一挂起数(P2)", ""),
        ("execs_done", "执行次数(P2)", ""),
    )
    paired: dict = {}
    for fz in FUZZERS:
        sub: dict = {}
        for metric, label, unit in METRICS:
            diffs = []
            for rep in REPS:
                a = idx2.get(("protorag", fz, str(rep)))
                b = idx2.get(("seed_reuse", fz, str(rep)))
                if not a or not b:
                    continue
                va, vb = num(a.get(metric)), num(b.get(metric))
                if va is None or vb is None:
                    continue
                diffs.append(va - vb)
            v = paired_stats(diffs, label, unit)
            # 检验：
            #  · Mann–Whitney 精确检验（**独立样本**口径，n=5 vs 5 双侧最小 p=0.0079）
            #  · Wilcoxon 符号秩 + 符号检验（**配对样本**口径，n=5 最小双侧 p=0.0625）
            if diffs:
                a_vals = [num(idx2[("protorag", fz, str(rep))].get(metric))
                          for rep in REPS]
                b_vals = [num(idx2[("seed_reuse", fz, str(rep))].get(metric))
                          for rep in REPS]
                a_ok = [x for x in a_vals if x is not None]
                b_ok = [y for y in b_vals if y is not None]
                v["mw_exact_p"] = mw_exact_p(a_ok, b_ok)
                v["wilcoxon_exact_p"] = wilcoxon_signed_rank_exact_p(diffs)
                v["sign_test_exact_p"] = sign_test_exact_p(diffs)
            else:
                v["mw_exact_p"] = None
                v["wilcoxon_exact_p"] = None
                v["sign_test_exact_p"] = None
            sub[metric] = v
        paired[fz] = sub
    res["paired"] = paired

    # P1 配对（n_states / n_edges 的 P1 值）
    paired_p1: dict = {}
    for fz in FUZZERS:
        sub = {}
        for metric, label in (("n_states", "n_states(P1)"),
                              ("n_edges", "n_edges(P1)")):
            diffs = []
            for rep in REPS:
                a = idx1.get(("protorag", fz, str(rep)))
                b = idx1.get(("seed_reuse", fz, str(rep)))
                if not a or not b:
                    continue
                va, vb = num(a.get(metric)), num(b.get(metric))
                if va is None or vb is None:
                    continue
                diffs.append(va - vb)
            sub[metric] = paired_stats(diffs, label, "")
        paired_p1[fz] = sub
    res["paired_P1"] = paired_p1

    # ---------- 4. 崩溃数分布 + 首次出现时刻 ----------
    crash_rows = []
    for r in crashdist:
        first = num(r.get("first_crash_rel_hours"))
        crash_rows.append({
            "container": r.get("container"),
            "group": r.get("group"), "fuzzer": r.get("fuzzer"),
            "rep": num(r.get("rep")),
            "first_crash_rel_h": first,
            "final_unique_crashes": num(r.get("final_unique_crashes")),
            "final_unique_hangs": num(r.get("final_unique_hangs")),
            "paths_total": num(r.get("paths_total")),
        })
    res["crash_distribution"] = crash_rows
    res["crash_first_appearance"] = {
        "with_crash": [c for c in crash_rows
                       if (c["first_crash_rel_h"] is not None)],
        "never_crashed": [c for c in crash_rows
                          if c["first_crash_rel_h"] is None],
    }

    # ---------- 5. unique_hangs 统计 ----------
    hang_rows = []
    for r in hangs:
        hang_rows.append({
            "container": r.get("container"),
            "group": r.get("group"), "fuzzer": r.get("fuzzer"),
            "rep": num(r.get("rep")),
            "unique_hangs": num(r.get("unique_hangs")),
        })
    hang_by_cell: dict = defaultdict(list)
    for h in hang_rows:
        hang_by_cell[(h["group"], h["fuzzer"])].append(h["unique_hangs"] or 0.0)
    res["hangs"] = {
        "rows": hang_rows,
        "by_cell": {f"{g}/{fz}": {
            "vals": vals,
            "mean": statistics.mean(vals),
            "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "total": sum(vals),
            "max": max(vals),
            "nonzero_reps": sum(1 for v in vals if v > 0),
        } for (g, fz), vals in sorted(hang_by_cell.items())},
    }

    # ---------- 6. 时序覆盖率分桶均值（权威口径：跨 rep 池化，|rel-h|<0.2） ----------
    # 按 (group, fuzzer, rep) 保留原始采样点，便于派生逐 rep 统计与替代口径。
    ts_points: dict = defaultdict(list)
    for r in ts:
        rel = num(r.get("rel_hours"))
        cvg = num(r.get("bitmap_cvg"))
        if rel is None or cvg is None:
            continue
        key = (r.get("group"), r.get("fuzzer"), str(r.get("rep", "")).strip())
        ts_points[key].append((rel, cvg, num(r.get("paths_total"))))

    def bucket_samples(points: list[tuple], h: float, idx: int,
                       tol: float = TS_BUCKET_TOL) -> list[float]:
        """取 rel_hours 落在 [h-tol, h+tol) 的全部采样点的指定字段。"""
        return [p[idx] for p in points
                if abs(p[0] - h) < tol and p[idx] is not None]

    def bucket_pick(points: list[tuple], h: float, mode: str,
                    tol: float = TS_BUCKET_TOL) -> float | None:
        """取单个采样点：mode='first' 桶内最早，mode='last' 桶内最晚。"""
        sel = [p for p in points if abs(p[0] - h) < tol and p[1] is not None]
        if not sel:
            return None
        return (min if mode == "first" else max)(sel, key=lambda x: x[0])[1]

    ts_buckets = []
    for h in TS_POINT_BUCKETS:
        row = {"bucket": f"{h:g}h", "h": h, "cells": {}}
        for g in GROUPS:
            for fz in FUZZERS:
                vals: list[float] = []
                paths: list[float] = []
                per_rep: dict[str, float] = {}
                for rep in REPS:
                    pts = ts_points.get((g, fz, str(rep)), [])
                    s = bucket_samples(pts, h, 1)
                    if s:
                        vals.extend(s)
                        per_rep[str(rep)] = round(statistics.mean(s), 4)
                    paths.extend(bucket_samples(pts, h, 2))
                if not vals:
                    continue
                row["cells"][f"{g}/{fz}"] = {
                    "n": len(vals),
                    "mean": round(statistics.mean(vals), 4),
                    "sd": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
                    "max": max(vals), "min": min(vals),
                    "per_rep": per_rep,
                    "paths_mean": (round(statistics.mean(paths), 2)
                                   if paths else None),
                    "paths_n": len(paths),
                }
        ts_buckets.append(row)
    res["timeseries_buckets"] = ts_buckets

    # 分桶反超判定：各桶内 protorag 均值 − seed_reuse 均值（权威口径）
    ts_delta = []
    for row in ts_buckets:
        cells = row["cells"]
        for fz in FUZZERS:
            a = cells.get(f"protorag/{fz}")
            b = cells.get(f"seed_reuse/{fz}")
            if not a or not b:
                continue
            # 逐 rep 配对差值（各 rep 先在桶内池化，再跨 rep 求均值/胜率）
            per_rep_diff = []
            for rep in REPS:
                pa = a["per_rep"].get(str(rep))
                sb = b["per_rep"].get(str(rep))
                if pa is None or sb is None:
                    continue
                per_rep_diff.append(round(pa - sb, 4))
            ts_delta.append({
                "bucket": row["bucket"], "h": row["h"], "fuzzer": fz,
                "delta_pp": round(a["mean"] - b["mean"], 4),
                "protorag_mean": a["mean"], "seed_reuse_mean": b["mean"],
                "per_rep_diff": per_rep_diff,
                "per_rep_mean": (round(statistics.mean(per_rep_diff), 4)
                                 if per_rep_diff else None),
                "win_rate": (sum(1 for d in per_rep_diff if d > 0)
                             if per_rep_diff else None),
                "nonneg_rate": (sum(1 for d in per_rep_diff if d >= -1e-9)
                                if per_rep_diff else None),
                # 按两位小数显示口径统计「非负」：差值四舍五入到 0.01pp 后 >= 0
                # 即视为持平（避免把 -0.0012pp 这类实质持平的样本误判为落后）
                "nonneg_rate_2dp": (sum(1 for d in per_rep_diff
                                        if round(d, 2) >= 0)
                                    if per_rep_diff else None),
            })
    res["timeseries_delta"] = ts_delta

    # 口径敏感性：同一批数据在两种替代口径下（桶内首个 / 桶内最后采样点）的差值。
    # 用于正文说明「0.5 h 的结论对口径敏感，1 h 以后各口径一致」。
    ts_alt = []
    for h in TS_POINT_BUCKETS:
        for mode in ("first", "last"):
            for fz in FUZZERS:
                diffs = []
                for rep in REPS:
                    pa = bucket_pick(ts_points.get(("protorag", fz, str(rep)), []), h, mode)
                    sb = bucket_pick(ts_points.get(("seed_reuse", fz, str(rep)), []), h, mode)
                    if pa is None or sb is None:
                        continue
                    diffs.append(round(pa - sb, 4))
                if not diffs:
                    continue
                ts_alt.append({
                    "bucket": f"{h:g}h", "h": h, "fuzzer": fz, "mode": mode,
                    "mean": round(statistics.mean(diffs), 4),
                    "win_rate": sum(1 for d in diffs if d > 0),
                    "per_rep_diff": diffs,
                })
    res["timeseries_alt_calibers"] = ts_alt

    # ---------- 6b. ★ v7：区间池化时序口径（§6 表格口径） ----------
    # 桶为连续区间 [lo, hi)；区间内跨 rep 的**全部**采样点混池求均值。
    # 与点时刻口径（ts_buckets）并存，互不覆盖。
    ts_iv_buckets = []
    for i in range(len(BUCKET_EDGES) - 1):
        lo, hi = BUCKET_EDGES[i], BUCKET_EDGES[i + 1]
        row = {"bucket": f"{lo:g}-{hi:g}h", "lo": lo, "hi": hi, "cells": {}}
        for g in GROUPS:
            for fz in FUZZERS:
                vals: list[float] = []
                paths: list[float] = []
                per_rep: dict[str, float] = {}
                for rep in REPS:
                    pts = ts_points.get((g, fz, str(rep)), [])
                    s = [p[1] for p in pts if lo <= p[0] < hi and p[1] is not None]
                    pv = [p[2] for p in pts if lo <= p[0] < hi and p[2] is not None]
                    if s:
                        vals.extend(s)
                        per_rep[str(rep)] = round(statistics.mean(s), 4)
                    paths.extend(pv)
                if not vals:
                    continue
                row["cells"][f"{g}/{fz}"] = {
                    "n": len(vals),
                    "mean": round(statistics.mean(vals), 4),
                    "sd": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
                    "max": max(vals), "min": min(vals),
                    "per_rep": per_rep,
                    "paths_mean": (round(statistics.mean(paths), 2)
                                   if paths else None),
                    "paths_n": len(paths),
                }
        ts_iv_buckets.append(row)
    res["timeseries_interval_buckets"] = ts_iv_buckets

    # 区间池化口径下的反超差值（protorag − seed_reuse）
    ts_iv_delta = []
    for row in ts_iv_buckets:
        cells = row["cells"]
        for fz in FUZZERS:
            a = cells.get(f"protorag/{fz}")
            b = cells.get(f"seed_reuse/{fz}")
            if not a or not b:
                continue
            per_rep_diff = []
            for rep in REPS:
                pa = a["per_rep"].get(str(rep))
                sb = b["per_rep"].get(str(rep))
                if pa is None or sb is None:
                    continue
                per_rep_diff.append(round(pa - sb, 4))
            ts_iv_delta.append({
                "bucket": row["bucket"], "lo": row["lo"], "hi": row["hi"],
                "fuzzer": fz,
                "delta_pp": round(a["mean"] - b["mean"], 4),
                "protorag_mean": a["mean"], "seed_reuse_mean": b["mean"],
                "per_rep_diff": per_rep_diff,
                "per_rep_mean": (round(statistics.mean(per_rep_diff), 4)
                                 if per_rep_diff else None),
                "win_rate": (sum(1 for d in per_rep_diff if d > 0)
                             if per_rep_diff else None),
            })
    res["timeseries_interval_delta"] = ts_iv_delta

    # 区间池化口径的**口径敏感性**：桶内首个 / 最后一个采样点。
    # 用于正文说明早期区间对取点方式敏感、1 h 以后各口径一致。
    ts_iv_alt = []
    for i in range(len(BUCKET_EDGES) - 1):
        lo, hi = BUCKET_EDGES[i], BUCKET_EDGES[i + 1]
        for mode in ("first", "last"):
            for fz in FUZZERS:
                diffs = []
                for rep in REPS:
                    sel_a = [p for p in ts_points.get(("protorag", fz, str(rep)), [])
                             if lo <= p[0] < hi]
                    sel_b = [p for p in ts_points.get(("seed_reuse", fz, str(rep)), [])
                             if lo <= p[0] < hi]
                    if not sel_a or not sel_b:
                        continue
                    pa = (min if mode == "first" else max)(sel_a, key=lambda x: x[0])[1]
                    pb = (min if mode == "first" else max)(sel_b, key=lambda x: x[0])[1]
                    diffs.append(round(pa - pb, 4))
                if not diffs:
                    continue
                ts_iv_alt.append({
                    "bucket": f"{lo:g}-{hi:g}h", "lo": lo, "hi": hi,
                    "fuzzer": fz, "mode": mode,
                    "mean": round(statistics.mean(diffs), 4),
                    "win_rate": sum(1 for d in diffs if d > 0),
                    "per_rep_diff": diffs,
                })
    res["timeseries_interval_alt_calibers"] = ts_iv_alt

    # ---------- 7. 中间态 vs 最终态差异 ----------
    if interim_dir and interim_dir.exists():
        i_p2 = read_csv(interim_dir / "rq1_2_p2.csv")
        i_ts = read_csv(interim_dir / "rq1_2_timeseries.csv")
        i_idx = {(r["group"], r["fuzzer"], r["rep"].strip()): r for r in i_p2}
        cmp_rows = []
        for g in GROUPS:
            for fz in FUZZERS:
                for rep in REPS:
                    fin = idx2.get((g, fz, str(rep)))
                    itm = i_idx.get((g, fz, str(rep)))
                    if not fin or not itm:
                        continue
                    cmp_rows.append({
                        "container": f"rq2_{g}_{fz}_r{rep}",
                        "group": g, "fuzzer": fz, "rep": rep,
                        "bitmap_cvg_interim": num(itm.get("bitmap_cvg")),
                        "bitmap_cvg_final": num(fin.get("bitmap_cvg")),
                        "paths_interim": num(itm.get("paths_total")),
                        "paths_final": num(fin.get("paths_total")),
                        "crashes_interim": num(itm.get("unique_crashes")),
                        "crashes_final": num(fin.get("unique_crashes")),
                        "hangs_interim": num(itm.get("unique_hangs")),
                        "hangs_final": num(fin.get("unique_hangs")),
                        "n_edges_interim": num(itm.get("n_edges")),
                        "n_edges_final": num(fin.get("n_edges")),
                    })
        res["interim_vs_final"] = {
            "rows": cmp_rows,
            "interim_max_rel_hours": max(
                (num(r.get("rel_hours")) or 0.0) for r in i_ts) if i_ts else None,
            "interim_ts_rows": len(i_ts),
            "final_ts_rows": len(ts),
            "crash_free_at_interim": all(
                (num(r.get("unique_crashes")) or 0) == 0 for r in i_p2),
        }
        # 中间态快照的覆盖率均值 vs 最终
        im = defaultdict(list)
        for r in i_p2:
            v = num(r.get("bitmap_cvg"))
            if v is not None:
                im[(r["group"], r["fuzzer"])].append(v)
        fm = defaultdict(list)
        for r in p2:
            v = num(r.get("bitmap_cvg"))
            if v is not None:
                fm[(r["group"], r["fuzzer"])].append(v)
        res["interim_vs_final"]["cell_means"] = {
            f"{k[0]}/{k[1]}": {
                "interim_mean": round(statistics.mean(im[k]), 4),
                "final_mean": round(statistics.mean(fm[k]), 4),
                "delta_pp": round(statistics.mean(fm[k]) - statistics.mean(im[k]), 4),
            } for k in sorted(im) if k in fm}

    # ---------- 8. 污染证据链（lineage / seedprovenance） ----------
    res["pollution_evidence"] = {
        "lineage": lineage,
        "seedprovenance": seedprov,
    }

    # ---------- 9. 崩溃/挂起的组×fuzzer 汇总 ----------
    crash_by_cell: dict = defaultdict(lambda: {"crashes": 0.0, "hangs": 0.0,
                                               "containers": 0})
    for c in containers:
        cell = crash_by_cell[(c["group"], c["fuzzer"])]
        cell["crashes"] += c["unique_crashes_P2"] or 0.0
        cell["hangs"] += c["unique_hangs_P2"] or 0.0
        cell["containers"] += 1
    res["crash_hang_by_cell"] = {
        f"{g}/{fz}": {**v,
                      "crashes_mean": v["crashes"] / v["containers"],
                      "hangs_mean": v["hangs"] / v["containers"]}
        for (g, fz), v in sorted(crash_by_cell.items())}

    # ---------- 10. execs_done 混淆因子（覆盖率 vs 执行量） ----------
    # 覆盖率是「执行量」的结果量；若两组执行量相差数倍，覆盖率对比需交代此混淆。
    execs_by_cell: dict = defaultdict(list)
    for c in containers:
        execs_by_cell[(c["group"], c["fuzzer"])].append(c["execs_done_P2"] or 0.0)
    res["execs_by_cell"] = {
        f"{g}/{fz}": {
            "mean": statistics.mean(v),
            "sd": statistics.stdev(v) if len(v) > 1 else 0.0,
            "min": min(v), "max": max(v),
        } for (g, fz), v in sorted(execs_by_cell.items())}

    # ---------- 11. 覆盖率 pooled 口径（跨两个 fuzzer 合并 10 个配对） ----------
    # ★ 注意：pooled 把「干净的 aflnet 半侧」与「受污染的 chatafl 半侧」混在一起，
    #   因此**只能作为总体参考**，不能替代分半侧的主/辅证表述。
    pooled_diffs: list[float] = []
    for fz in FUZZERS:
        for rep in REPS:
            a = idx2.get(("protorag", fz, str(rep)))
            b = idx2.get(("seed_reuse", fz, str(rep)))
            if not a or not b:
                continue
            va, vb = num(a.get("bitmap_cvg")), num(b.get("bitmap_cvg"))
            if va is None or vb is None:
                continue
            pooled_diffs.append(va - vb)
    pooled = paired_stats(pooled_diffs, "分支覆盖率(P2) · pooled(10)", "pp")
    pooled["mw_exact_p"] = mw_exact_p(
        [num(idx2[("protorag", fz, str(rep))].get("bitmap_cvg"))
         for fz in FUZZERS for rep in REPS],
        [num(idx2[("seed_reuse", fz, str(rep))].get("bitmap_cvg"))
         for fz in FUZZERS for rep in REPS])
    pooled["wilcoxon_exact_p"] = wilcoxon_signed_rank_exact_p(pooled_diffs)
    pooled["sign_test_exact_p"] = sign_test_exact_p(pooled_diffs)
    pooled["caveat"] = ("pooled 混合了干净半侧(aflnet)与受污染半侧(chatafl)，"
                        "仅作总体参考；分半侧结论以 §3 为准")
    res["paired_pooled_coverage"] = pooled

    # ---------- 12. P1 状态边差异的归因（合法种子质量效应 vs 污染） ----------
    # P1 = 初始种子/dry-run 刚结束时的状态图规模，取决于**基础种子集**大小
    # （protorag 50 vs seed_reuse 7），与 LLM 增强无关 → 属合法种子质量效应。
    p1_edges: dict = {}
    for fz in FUZZERS:
        a_vals = [num(idx1[("protorag", fz, str(rep))].get("n_edges"))
                  for rep in REPS]
        b_vals = [num(idx1[("seed_reuse", fz, str(rep))].get("n_edges"))
                  for rep in REPS]
        a_ok = [x for x in a_vals if x is not None]
        b_ok = [y for y in b_vals if y is not None]
        diffs = [x - y for x, y in zip(a_ok, b_ok)]
        p1_edges[fz] = {
            "protorag_mean": statistics.mean(a_ok) if a_ok else None,
            "seed_reuse_mean": statistics.mean(b_ok) if b_ok else None,
            "delta": statistics.mean(diffs) if diffs else None,
            "win_rate": (sum(1 for d in diffs if d > 0) / len(diffs)
                         if diffs else None),
            "diffs": diffs,
            "attribution": ("基础种子集规模差异（50 vs 7）导致的合法种子质量效应，"
                            "与 LLM 增强污染无关"),
        }
    res["p1_edges_attribution"] = p1_edges

    # ---------- 13. 等执行预算覆盖率（关键混淆因子控制） ----------
    # ★ v7 修正：原用「每百万次执行的覆盖率」(cvg/execs) 做归一化，**该指标构造有偏** ——
    #   覆盖率是饱和型累积量，同一容器内 cvg/execs 随执行量单调下降（实测首末比 ~18–35×），
    #   故该比值天然偏好"执行量少"的一方，与覆盖率的绝对水平无关 → 不能用于方法比较。
    #   正确做法是**等执行预算比较**：把两组截断到同一累计执行预算，再比覆盖率。
    #   累计执行量由 plot_data 的 execs_per_sec 梯形积分得到，并锚定到 fuzzer_stats 的 execs_done。
    #   数据源：qa_rq1_2/raw/*.plot_data（20 容器原始采样点）。
    raw_dir = data_dir.parent.parent / "qa_rq1_2" / "raw"
    if not raw_dir.exists():  # 兜底：向上查找
        for cand in (data_dir.parent, data_dir.parent.parent, data_dir.parent.parent.parent):
            p = cand / "qa_rq1_2" / "raw"
            if p.exists():
                raw_dir = p
                break

    def _load_series(group: str, fz: str, rep: int) -> dict | None:
        path = raw_dir / f"{group}_{fz}_r{rep}.plot_data"
        if not path.exists():
            return None
        ts: list[int] = []
        cvg: list[float] = []
        eps: list[float] = []
        for line in path.read_text(errors="replace", encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 13:
                continue
            try:
                ts.append(int(parts[0]))
                cvg.append(float(parts[6].replace("%", "")))
                eps.append(float(parts[10]))
            except ValueError:
                continue
        if len(ts) < 2:
            return None
        return {"t": ts, "cvg": cvg, "eps": eps}

    def _cum_execs(series: dict, total_execs: float) -> list[float]:
        """由 execs_per_sec 梯形积分得累计执行量，再线性锚定到 fuzzer_stats 的 execs_done。"""
        cum = [0.0]
        for i in range(1, len(series["t"])):
            dt = series["t"][i] - series["t"][i - 1]
            cum.append(cum[-1] + (series["eps"][i - 1] + series["eps"][i]) / 2.0 * dt)
        if cum[-1] > 0:
            scale = total_execs / cum[-1]
            cum = [x * scale for x in cum]
        return cum

    def _cov_at_budget(series: dict, cum: list[float], budget: float) -> float:
        for i, x in enumerate(cum):
            if x >= budget:
                return series["cvg"][i]
        return series["cvg"][-1]

    def _time_to_reach(series: dict, target: float) -> float | None:
        """达到目标覆盖率所需时间（相对容器启动的小时数）。"""
        if not series:
            return None
        t0 = series["t"][0]
        for tt, cv in zip(series["t"], series["cvg"]):
            if cv >= target:
                return (tt - t0) / 3600.0
        return None

    eqb: dict = {}
    t2t: dict = {}
    for fz in FUZZERS:
        rows = []
        t_rows = []
        for rep in REPS:
            a = idx2.get(("protorag", fz, str(rep)))
            b = idx2.get(("seed_reuse", fz, str(rep)))
            if not a or not b:
                continue
            ea, eb = num(a.get("execs_done")), num(b.get("execs_done"))
            ca, cb = num(a.get("bitmap_cvg")), num(b.get("bitmap_cvg"))
            if None in (ea, eb, ca, cb) or ea <= 0 or eb <= 0:
                continue
            sa = _load_series("protorag", fz, rep)
            sb = _load_series("seed_reuse", fz, rep)
            if not sa or not sb:
                continue
            cum_a = _cum_execs(sa, ea)
            cum_b = _cum_execs(sb, eb)
            budget = min(ea, eb)
            eq_a = _cov_at_budget(sa, cum_a, budget)
            eq_b = _cov_at_budget(sb, cum_b, budget)
            rows.append({
                "rep": rep,
                "execs_protorag": ea, "execs_seed_reuse": eb,
                "execs_ratio": ea / eb,
                "budget": budget,
                "cvg_protorag": ca, "cvg_seed_reuse": cb,
                "raw_diff": ca - cb,
                "eq_cvg_protorag": eq_a, "eq_cvg_seed_reuse": eq_b,
                "eq_diff": eq_a - eq_b,
            })
            # 时间-阈值：protorag 达到「基线自身最终覆盖」所需时间
            tgt = cb
            t_p = _time_to_reach(sa, tgt)
            t_s = _time_to_reach(sb, cb)
            t_rows.append({
                "rep": rep,
                "target_cvg_seed_reuse": tgt,
                "t_protorag_h": t_p,
                "t_seed_reuse_h": t_s,
                "speedup": (t_s / t_p) if (t_p and t_s and t_p > 0) else None,
            })
        diffs = [r["eq_diff"] for r in rows]
        v = paired_stats(diffs, "等执行预算覆盖率差(P2) = pp", "")
        v["wilcoxon_exact_p"] = wilcoxon_signed_rank_exact_p(diffs)
        v["sign_test_exact_p"] = sign_test_exact_p(diffs)
        v["rows"] = rows
        v["execs_ratio_mean"] = (statistics.mean(r["execs_ratio"] for r in rows)
                                 if rows else None)
        v["raw_win"] = sum(1 for r in rows if r["raw_diff"] > 0)
        eqb[fz] = v
        tv = [r["t_protorag_h"] for r in t_rows if r["t_protorag_h"] is not None]
        sv = [r["t_seed_reuse_h"] for r in t_rows if r["t_seed_reuse_h"] is not None]
        sp = [r["speedup"] for r in t_rows if r["speedup"] is not None]
        t2t[fz] = {
            "rows": t_rows,
            "t_protorag_mean": statistics.mean(tv) if tv else None,
            "t_protorag_median": statistics.median(tv) if tv else None,
            "t_seed_reuse_mean": statistics.mean(sv) if sv else None,
            "speedup_mean": statistics.mean(sp) if sp else None,
            "speedup_median": statistics.median(sp) if sp else None,
            "n_reached": len(tv),
        }
    res["coverage_equal_budget"] = eqb
    res["time_to_threshold"] = t2t

    # ---------- 13b. 启动错位（startup offset）----------
    # plot_data 首行 unix_time 与 fuzzer_stats.start_time 的差 = 「采样起点相对 fuzzer 启动」的错位。
    # ChatAFL 启动期要做 LLM 增强 → chatafl 的错位显著大于 aflnet（原生 AFLNet 无此逻辑）。
    # 这意味着：按「容器启动时刻」对齐时，chatafl 半侧的真实 fuzzing 起始被系统性延后。
    startup: dict = {}
    for fz in FUZZERS:
        for grp in GROUPS:
            vals = []
            for rep in REPS:
                fs_path = raw_dir / f"{grp}_{fz}_r{rep}.fuzzer_stats"
                pd_path = raw_dir / f"{grp}_{fz}_r{rep}.plot_data"
                if not (fs_path.exists() and pd_path.exists()):
                    continue
                st = {}
                for line in fs_path.read_text(errors="replace", encoding="utf-8").splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        st[parts[0]] = parts[2]
                first = None
                for line in pd_path.read_text(errors="replace", encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        first = line
                        break
                if not first or "start_time" not in st:
                    continue
                try:
                    t0 = int(first.split(",")[0].strip())
                    offs = t0 - int(st["start_time"])
                except ValueError:
                    continue
                vals.append(offs)
            if vals:
                startup[f"{grp}/{fz}"] = {
                    "offsets_s": vals,
                    "mean_s": statistics.mean(vals),
                    "median_s": statistics.median(vals),
                }
    res["startup_offset"] = startup

    # ---------- 13b. ★ v7：每百万次执行的覆盖率（cvg/execs 归一化） ----------
    # ⚠ 该指标**构造有偏**（覆盖率是累积饱和量，同容器内 cvg/execs 随执行量单调下降），
    #   **不能单独用于方法比较**；§3.4 的主口径是**等执行预算**（见上）。
    #   本段保留该口径，供正文按 (D) 要求**并列披露**：
    #   · aflnet 半侧：归一化后仍 5/5 占优，且分母干净（挂起近乎恒 0 → 非污染驱动）
    #   · chatafl 半侧：0/5 落后，但**分母本身是污染驱动的中介量**
    #     （挂起 445 + 416 次阻塞按 exec_timeout: 1000 消耗 execs）
    #   → 故 chatafl 侧的该结果**不足以单独作为"污染导致"的因果证据**。
    norm_mexec: dict = {}
    for fz in FUZZERS:
        rows = []
        for rep in REPS:
            a = idx2.get(("protorag", fz, str(rep)))
            b = idx2.get(("seed_reuse", fz, str(rep)))
            if not a or not b:
                continue
            ea, eb = num(a.get("execs_done")), num(b.get("execs_done"))
            ca, cb = num(a.get("bitmap_cvg")), num(b.get("bitmap_cvg"))
            if None in (ea, eb, ca, cb) or ea <= 0 or eb <= 0:
                continue
            na, nb = ca / ea * 1e6, cb / eb * 1e6
            rows.append({
                "rep": rep,
                "execs_protorag": ea, "execs_seed_reuse": eb,
                "execs_ratio": ea / eb,
                "cvg_per_Mexec_protorag": na,
                "cvg_per_Mexec_seed_reuse": nb,
                "ratio": na / nb,
                "diff": na - nb,
            })
        diffs = [r["diff"] for r in rows]
        v = paired_stats(diffs, "归一化覆盖率(P2) = pp/百万次执行", "")
        v["wilcoxon_exact_p"] = wilcoxon_signed_rank_exact_p(diffs)
        v["sign_test_exact_p"] = sign_test_exact_p(diffs)
        v["rows"] = rows
        v["execs_ratio_mean"] = (statistics.mean(r["execs_ratio"] for r in rows)
                                 if rows else None)
        v["ratio_min"] = min((r["ratio"] for r in rows), default=None)
        v["ratio_max"] = max((r["ratio"] for r in rows), default=None)
        norm_mexec[fz] = v
    res["coverage_per_Mexec"] = norm_mexec

    # ---------- 14. 崩溃样本散文核查（污染对崩溃证据的污染） ----------
    prose = parse_prose_report(data_dir / "rq1_2_extra_prose.txt")
    crash_prose = prose.get("crash_samples", {})
    corpus_prose = prose.get("seed_corpus", {})

    prose_by_cell: dict = defaultdict(lambda: {
        "samples": 0, "with_prose": 0, "with_strong_prose": 0, "containers": 0})
    for c in containers:
        key = c["container"]
        rec = crash_prose.get(key)
        if rec is None:
            continue
        cell = prose_by_cell[(c["group"], c["fuzzer"])]
        cell["samples"] += rec["samples"]
        cell["with_prose"] += rec["with_prose"]
        cell["with_strong_prose"] += rec["with_strong_prose"]
        cell["containers"] += 1
    res["crash_sample_prose"] = {
        "per_container": crash_prose,
        "seed_corpus": corpus_prose,
        "by_cell": {f"{g}/{fz}": {**v,
                                  "prose_rate": (v["with_prose"] / v["samples"]
                                                 if v["samples"] else None)}
                    for (g, fz), v in sorted(prose_by_cell.items())},
        "total_samples": sum(v["samples"] for v in prose_by_cell.values()),
        "total_with_prose": sum(v["with_prose"] for v in prose_by_cell.values()),
        "total_with_strong_prose": sum(v["with_strong_prose"]
                                       for v in prose_by_cell.values()),
    }

    return res


# --------------------------------------------------------------------------
# 打印
# --------------------------------------------------------------------------
def print_report(res: dict) -> None:
    print("=" * 78)
    print("RQ1.2 Live555 —— 最终结果统计分析")
    print("=" * 78)

    print("\n[1] docx 表 4 的 4 行（已回填值）")
    for r in res["summary_rows"]:
        print(f"    row{r.get('docx_row')}: {r.get('seed_source')} / {r.get('fuzzer')}"
              f" | states {r.get('n_states_P1')}→{r.get('n_states_P2')}"
              f" | edges {r.get('n_edges_P1')}→{r.get('n_edges_P2')}"
              f" | cvg {r.get('bitmap_cvg_P2')}"
              f" | crash {r.get('unique_crashes_P2')}"
              f" | paths {r.get('paths_total_P2')}")

    print("\n[2] 配对统计（protorag − seed_reuse，同 fuzzer 同 rep 配对，n=5）")
    print("    [检验口径] MW=独立样本双侧精确检验(n=5vs5 最小 p=0.0079)")
    print("             WSR=Wilcoxon 符号秩双侧精确检验(配对口径 n=5 最小 p=0.0625)")
    print("             SIGN=符号检验双侧精确检验(配对口径 n=5 最小 p=0.0625)")
    for fz in ("aflnet", "chatafl"):
        print(f"  --- {fz} ---")
        for metric, v in res["paired"][fz].items():
            pmw = v.get("mw_exact_p")
            pwsr = v.get("wilcoxon_exact_p")
            psgn = v.get("sign_test_exact_p")
            ps = ""
            if pmw is not None:
                ps += f"，MW p={pmw:.4f}"
            if pwsr is not None:
                ps += f"，WSR p={pwsr:.4f}"
            if psgn is not None:
                ps += f"，SIGN p={psgn:.4f}"
            print(f"    {v['label']}: {fmt_ps(v)}{ps}")

    print("\n[3] 崩溃数分布 + 首次出现时刻")
    for c in res["crash_distribution"]:
        fc = c["first_crash_rel_h"]
        fcs = f"{fc:.4f} h" if fc is not None else "—（全程未崩溃）"
        print(f"    {c['container']:<28} crashes={c['final_unique_crashes']:>5.0f}"
              f"  hangs={c['final_unique_hangs']:>5.0f}  首次崩溃={fcs}")

    print("\n[4] unique_hangs 统计")
    for cell, v in res["hangs"]["by_cell"].items():
        print(f"    {cell:<22} 各rep={v['vals']}  mean={v['mean']:.2f}"
              f"  sd={v['sd']:.2f}  total={v['total']:.0f}"
              f"  非零rep={v['nonzero_reps']}/5")

    print("\n[5] 时序覆盖率分桶均值（%）")
    hdr = "    " + "时间桶".ljust(10) + "".join(
        f"{g}/{f}".ljust(22) for g in GROUPS for f in FUZZERS)
    print(hdr)
    for row in res["timeseries_buckets"]:
        line = "    " + row["bucket"].ljust(10)
        for g in GROUPS:
            for f in FUZZERS:
                c = row["cells"].get(f"{g}/{f}")
                line += (f"{c['mean']:.3f}(n={c['n']})".ljust(22)
                         if c else "NA".ljust(22))
        print(line)

    print("\n[6] 各时间桶的反超差值（protorag − seed_reuse，pp）")
    for fz in ("aflnet", "chatafl"):
        line = f"    {fz}: "
        for d in res["timeseries_delta"]:
            if d["fuzzer"] == fz:
                line += f"{d['bucket']}={d['delta_pp']:+.3f}  "
        print(line)

    if "interim_vs_final" in res:
        iv = res["interim_vs_final"]
        print("\n[7] 与 10-24 20:00 中间态的差异")
        print(f"    中间态时序最大 rel_hours = {iv['interim_max_rel_hours']:.4f} h"
              f"（行数 {iv['interim_ts_rows']}），最终态行数 {iv['final_ts_rows']}")
        print(f"    中间态崩溃数全为 0：{iv['crash_free_at_interim']}")
        for cell, v in iv["cell_means"].items():
            print(f"    {cell:<22} 覆盖率 中间态 {v['interim_mean']:.3f}% → "
                  f"最终 {v['final_mean']:.3f}%（{v['delta_pp']:+.3f} pp）")


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ1.2 Live555 统计分析与一致性校验")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--interim-dir", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    interim = Path(args.interim_dir) if args.interim_dir else None
    res = build(data_dir, interim)
    print_report(res)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"\n[输出] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
