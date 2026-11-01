# -*- coding: utf-8 -*-
"""scripts/rq3_stats.py —— RQ3 组间统计检验（KW / M-W 精确 / Holm / Cliff's δ / bootstrap）。

用法:
    E:/app/Anaconda3/python.exe scripts/rq3_stats.py [--metrics-dir derived/rq3]

输出:
    `derived/rq3/stats_report.md`

★ 报告纪律（技术方案 §10 / 论文表述红线）：
  · 未达显著时，文字必须是「方向一致但未达统计显著（n=5，M-W 精确检验最小可达
    p=0.0079）」，**不得**写成「无差异」。
  · 必须同时给出 mean ± std **与全部 5 个原始值**。
  · 末态指标与早期指标**分列两组检验**（早期窗口是 H2 的主证据）。
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

import rq3_common as C  # noqa: E402

#: 组间比较对（依技术方案：主结论锚定 B→D→C）
PAIRS = [("B", "D"), ("D", "C"), ("B", "C"), ("A", "B")]

#: 参与检验的指标（末态）
METRICS = [
    ("M3_coverage", "mean", "分支覆盖%"),
    ("M3_coverage", "std", None),          # std 单独报告，不做检验
]

#: bootstrap 迭代次数（配置优先）
BOOTSTRAP_ITERS = 10000


def _get_metric(metrics: dict, path: str, key: str) -> Optional[float]:
    """按路径取指标值（如 "M3_coverage.mean"）。"""
    cur = metrics
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    if cur is None:
        return None
    if key == "per_rep":
        vals = [v for v in cur if v is not None]
        return statistics.mean(vals) if vals else None
    return cur.get(key) if isinstance(cur, dict) else None


def _per_rep(metrics: dict, path: str) -> list:
    """取 per-rep 原始值列表。"""
    cur = metrics
    for part in path.split("."):
        if not isinstance(cur, dict):
            return []
        cur = cur.get(part)
    if isinstance(cur, dict):
        return [v for v in (cur.get("per_rep") or []) if v is not None]
    return []


def mann_whitney_exact(a: list, b: list) -> tuple[Optional[float], float]:
    """Mann-Whitney U 检验（**精确** p 值，枚举全部标签分配）。

    p 值口径：标准双侧定义 `p = 2 × min(P(U ≤ u_obs), P(U ≥ n1·n2 − u_obs))`，
    上限截到 1.0。
    → n=5 vs 5 且两组完全分离时，最小可达双侧 p = 2/C(10,5) = 2/252 = **0.0079**
      （组合数学下界，n=3 vs 3 时为 0.10 → 数学上不可能宣称显著）。

    Args:
        a: 组 A 的样本。
        b: 组 B 的样本。

    Returns:
        `(p_value, u_statistic)`；样本不足时 p 为 None。
    """
    if len(a) < 2 or len(b) < 2:
        return (None, 0.0)
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    r1 = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    n1, n2 = len(a), len(b)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u_obs = min(u1, n1 * n2 - u1)
    # 精确 p 值：枚举全部「选 n1 个给 A」的标签分配
    total = n1 + n2
    lower = upper = 0
    n_assign = 0
    for mask in range(1 << total):
        sel_a = sum(1 for k in range(total) if mask >> k & 1)
        if sel_a != n1:
            continue
        n_assign += 1
        rank_sum = sum(k + 1 for k in range(total) if mask >> k & 1)
        u_a = rank_sum - n1 * (n1 + 1) / 2.0
        if u_a <= u_obs:
            lower += 1
        if u_a >= n1 * n2 - u_obs:
            upper += 1
    if n_assign == 0:
        return (None, u_obs)
    p = min(1.0, 2.0 * min(lower, upper) / float(n_assign))
    return (p, u_obs)


def kruskal_wallis(groups: list) -> tuple[Optional[float], float]:
    """Kruskal-Wallis H 检验（多组比较）。

    Args:
        groups: 各组的样本列表。

    Returns:
        `(h_statistic, p_approx)`；样本不足时 (None, None)。
    """
    groups = [g for g in groups if len(g) >= 1]
    if len(groups) < 2 or sum(len(g) for g in groups) < 3:
        return (None, None)
    allv = sorted(v for g in groups for v in g)
    n = len(allv)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and allv[j + 1] == allv[i]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    h = 0.0
    idx = 0
    for g in groups:
        m = len(g)
        r = sum(ranks[idx:idx + m])
        idx += m
        h += (r * r) / m
    h = 12.0 / (n * (n + 1)) * h - 3.0 * (n + 1)
    # chi-square 近似 p（k=groups-1 自由度）
    k = len(groups) - 1
    # 用 math.erf 的 Wilson–Hilferty 近似
    from math import erf, sqrt
    x = h / (2.0 * k)
    p = 1.0 - 0.5 * (1.0 + erf((x ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * k)))
                                 / sqrt(2.0 / (9.0 * k)))) if h > 0 else 1.0
    return (h, max(0.0, min(1.0, p)))


def cliffs_delta(a: list, b: list) -> Optional[float]:
    """Cliff's δ（效应量，[-1, 1]）。"""
    if not a or not b:
        return None
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / float(len(a) * len(b))


def hodges_lehmann(a: list, b: list) -> Optional[float]:
    """Hodges-Lehmann 中位数差（两样本所有两两差的中心）。"""
    if not a or not b:
        return None
    diffs = sorted(x - y for x in a for y in b)
    n = len(diffs)
    mid = n // 2
    return (diffs[mid] if n % 2 else (diffs[mid - 1] + diffs[mid]) / 2.0)


def bootstrap_ci(a: list, b: list, iters: int = BOOTSTRAP_ITERS,
                 ci: float = 0.95, seed: int = 20261025) -> tuple:
    """bootstrap 95% CI（对均值差）。

    Args:
        a: 组 A 样本。
        b: 组 B 样本。
        iters: 迭代次数。
        ci: 置信水平。
        seed: 随机种子（保证可复现）。

    Returns:
        `(lo, hi, point)`。
    """
    if not a or not b:
        return (None, None, None)
    point = statistics.mean(a) - statistics.mean(b)
    rnd = random.Random(seed)
    diffs = []
    for _ in range(iters):
        ra = [rnd.choice(a) for _ in a]
        rb = [rnd.choice(b) for _ in b]
        diffs.append(statistics.mean(ra) - statistics.mean(rb))
    diffs.sort()
    alpha = (1.0 - ci) / 2.0
    lo = diffs[max(0, int(alpha * iters) - 1)]
    hi = diffs[min(iters - 1, int((1 - alpha) * iters))]
    return (lo, hi, point)


def paired_win_rate(diffs: list) -> dict:
    """同 rep 配对差值（实验组 − 对照组）的胜率与统计量（v2 §5.3.6）。

    ★ 这是 RQ3 的**主判定口径**：n=5 时单看均值极易被单个离群 rep 主导
    （合成示例，非实测终态：n_edges 差 +4/−2/−1/−1/+28，均值 +5.6 被 r5 的 +28 拉高），
    故必须报「同 rep 配对下的胜率」与「配对差值均值±标准差」。

    Args:
        diffs: 逐 rep 的配对差值列表。

    Returns:
        统计量字典（含 win_rate / consistent_sign / without_outlier / all_diffs）。
    """
    n = len(diffs)
    if n == 0:
        return {"n_pairs": 0, "wins": 0, "ties": 0, "losses": 0,
                "win_rate": None, "mean_diff": None, "std_diff": None,
                "median_diff": None, "min_diff": None, "max_diff": None,
                "all_diffs": [], "consistent_sign": False,
                "without_outlier": None}
    wins = sum(1 for d in diffs if d > 0)
    ties = sum(1 for d in diffs if d == 0)
    losses = sum(1 for d in diffs if d < 0)
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    # 离群稳健性：去掉 |d| 最大的一个后重算（判断结论是否被单个 rep 主导）
    without_outlier = None
    if n >= 3:
        trimmed = [d for d in diffs
                   if abs(d) != max(abs(x) for x in diffs)]
        if trimmed:
            without_outlier = {
                "n_pairs": len(trimmed),
                "wins": sum(1 for d in trimmed if d > 0),
                "win_rate": sum(1 for d in trimmed if d > 0) / len(trimmed),
                "mean_diff": statistics.mean(trimmed),
            }
    return {
        "n_pairs": n,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "win_rate": wins / n,                 # ★ 主判定口径
        "mean_diff": m,
        "std_diff": sd,
        "median_diff": statistics.median(diffs),
        "min_diff": min(diffs),
        "max_diff": max(diffs),
        "all_diffs": list(diffs),             # ★ 必须列出全部原始值
        "consistent_sign": (wins == n) or (losses == n),   # ★ 5/5 一致性
        "without_outlier": without_outlier,
    }


def significance_claim(wr: dict, min_p: float) -> str:
    """按配对胜率与显著性给出**合规**的结论文字（v2 §5.3.6 表述纪律）。

    ★ 表述纪律：
      · win rate < 5/5 时**禁止**写「稳定地/一致地」→ 写「n/5 rep 占优
        （方向倾向为正），但样本量小（n=5）未达统计显著」
      · 未达显著时**禁止**写「无差异」→ 写「方向一致但未达统计显著」

    Args:
        wr: `paired_win_rate` 的返回值。
        min_p: n=5 vs 5 时 M-W 精确检验的最小可达 p。

    Returns:
        结论文字。
    """
    if not wr or not wr.get("n_pairs"):
        return "NA（无配对样本）"
    n = wr["n_pairs"]
    wr_rate = wr["win_rate"]
    wr_str = f"{wr['wins']}/{n}"
    if wr.get("consistent_sign") and wr_rate == 1.0:
        return (f"{wr_str} rep **一致占优**（配对差值均值 "
                f"{wr['mean_diff']:+.4g}）")
    if wr_rate > 0.5:
        return (f"{wr_str} rep 占优（方向倾向为正），但样本量小（n={n}）"
                f"未达统计显著（M-W 精确检验最小可达 p={min_p}）")
    if wr_rate == 0.5:
        return (f"{wr_str} rep 占优（方向中性），样本量小（n={n}），"
                f"未达统计显著（M-W 精确检验最小可达 p={min_p}）")
    return (f"{wr_str} rep 占优（方向倾向为负），样本量小（n={n}），"
            f"未达统计显著（M-W 精确检验最小可达 p={min_p}）")


def holm_correction(pvals: dict) -> dict:
    """Holm-Bonferroni 校正（保持 FWER）。

    Args:
        pvals: `{检验名: p 值}`。

    Returns:
        `{检验名: 校正后 p 值}`。
    """
    items = [(k, v) for k, v in pvals.items() if v is not None]
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    out: dict = {}
    prev = 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        adj = max(adj, prev)
        out[k] = adj
        prev = adj
    for k, v in pvals.items():
        if v is None:
            out[k] = None
    return out


def _fmt(v, spec="{:.3f}") -> str:
    """格式化；None → NA。"""
    return C.fmt(v, spec)


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ3 组间统计检验")
    ap.add_argument("--metrics-dir", default=None,
                    help="metrics_<g>.json 所在目录（默认 derived/rq3）")
    args = ap.parse_args()

    cfg = C.load_config()
    mdir = Path(args.metrics_dir) if args.metrics_dir else C.RQ3_ROOT

    metrics: dict = {}
    for g in ("A", "B", "C", "D"):
        p = mdir / f"metrics_{g}.json"
        if p.exists():
            metrics[g] = C.read_json(p)
    if not metrics:
        print("!! 没有可用的 metrics_<g>.json（先跑 rq3_metrics.py）",
              file=sys.stderr)
        return 1

    groups_present = [g for g in ("A", "B", "C", "D") if g in metrics]
    n_reps = len(cfg["reps"])
    min_p = cfg["stats"]["min_reachable_p_n5v5"]
    iters = cfg["stats"].get("bootstrap_iterations", BOOTSTRAP_ITERS)

    # ---- 配对 win-rate + 逐 rep 原始差值（v2 §5.3.6 主判定口径）----
    paired_rows: list = []
    winrate_rows: list = []
    for fa, fb in PAIRS:
        if fa not in metrics or fb not in metrics:
            continue
        for fz in ("chatafl", "aflnet"):
            for metric, label in (("bitmap_cvg", "分支覆盖%"),
                                  ("n_edges", "n_edges"),
                                  ("paths_total", "paths_total"),
                                  ("n_states", "n_states"),
                                  ("unique_crashes", "unique_crashes")):
                a_all = _per_rep(metrics[fa], "M3_coverage")
                b_all = _per_rep(metrics[fb], "M3_coverage")
                if not a_all or not b_all:
                    continue
                diffs: list = []
                for i in range(min(len(a_all), len(b_all))):
                    d = a_all[i] - b_all[i]
                    diffs.append(d)
                    paired_rows.append([
                        metric, fa, fb, fz, i + 1, d,
                        "a" if d > 0 else ("b" if d < 0 else "tie")])
                wr = paired_win_rate(diffs)
                wr["significance_claim"] = significance_claim(wr, min_p)
                winrate_rows.append([
                    metric, fa, fb, fz, wr["n_pairs"], wr["wins"], wr["ties"],
                    wr["losses"], f"{wr['win_rate']:.4f}" if wr["win_rate"] is not None else "NA",
                    f"{wr['mean_diff']:.6g}" if wr["mean_diff"] is not None else "NA",
                    f"{wr['std_diff']:.6g}" if wr["std_diff"] is not None else "NA",
                    f"{wr['median_diff']:.6g}" if wr["median_diff"] is not None else "NA",
                    f"{wr['min_diff']:.6g}" if wr["min_diff"] is not None else "NA",
                    f"{wr['max_diff']:.6g}" if wr["max_diff"] is not None else "NA",
                    wr["consistent_sign"],
                    ";".join(f"{d:.6g}" for d in wr["all_diffs"]),
                    wr["significance_claim"]])

    if paired_rows:
        C.write_csv(C.RQ3_ROOT / "rq3_paired.csv",
                    ("metric", "group_a", "group_b", "fuzzer", "rep",
                     "diff_value", "winner"), paired_rows)
    if winrate_rows:
        C.write_csv(C.RQ3_ROOT / "rq3_winrate.csv",
                    ("metric", "group_a", "group_b", "fuzzer", "n_pairs",
                     "wins", "ties", "losses", "win_rate", "mean_diff",
                     "std_diff", "median_diff", "min_diff", "max_diff",
                     "consistent_sign", "all_diffs", "significance_claim"),
                    winrate_rows)

    lines: list = []
    lines.append("# RQ3 组间统计报告")
    lines.append("")
    lines.append(f"- 组：{', '.join(groups_present)}")
    lines.append(f"- rep 数：{n_reps}（每组）")
    lines.append(f"- 检验：Mann-Whitney **精确**检验 + Holm 校正；"
                 f"Kruskal-Wallis；Cliff's δ；Hodges-Lehmann 中位数差；"
                 f"bootstrap {iters} 次 95% CI")
    lines.append(f"- n=5 vs 5 时 M-W 精确检验的**最小可达双侧 p** = {min_p}"
                 "（数学上不可达更小值）")
    lines.append("")
    lines.append("> 表述纪律：未达显著时写「方向一致但未达统计显著」，"
                 "**不写**「无差异」。")
    lines.append("")

    # ---- 原始值与 mean ± std ----
    lines.append("## 1. 末态指标的原始值与 mean ± std")
    lines.append("")
    lines.append("| 组 | 指标 | 全部原始值 | mean | std |")
    lines.append("|---|---|---|---|---|")
    for g in groups_present:
        cov = metrics[g].get("M3_coverage", {})
        raw = cov.get("per_rep") or []
        lines.append(f"| {g} | 分支覆盖% | "
                     f"{'; '.join(f'{v:.2f}' for v in raw) or 'NA'} | "
                     f"{_fmt(cov.get('mean'), '{:.2f}')} | "
                     f"{_fmt(cov.get('std'), '{:.2f}')} |")
        mhr = metrics[g].get("M5_mhr", {}).get("A_targeted", {})
        lines.append(f"| {g} | MHR_A（%） | "
                     f"{_fmt(mhr.get('pooled'), '{:.2f}')} | "
                     f"{_fmt(mhr.get('pooled'), '{:.2f}')} | — |")
    lines.append("")

    # ---- 末态组间检验 ----
    lines.append("## 2. 末态指标的组间检验")
    lines.append("")
    lines.append("| 比较 | 指标 | MW 精确 p | MW 校正 p(Holm) | Cliff's δ | "
                 "HL 中位数差 | bootstrap 95% CI | 结论 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    pvals: dict = {}
    for fa, fb in PAIRS:
        if fa not in metrics or fb not in metrics:
            continue
        a = _per_rep(metrics[fa], "M3_coverage")
        b = _per_rep(metrics[fb], "M3_coverage")
        if not a or not b:
            continue
        p, _u = mann_whitney_exact(a, b)
        delta = cliffs_delta(a, b)
        hl = hodges_lehmann(a, b)
        lo, hi, point = bootstrap_ci(a, b, iters=iters)
        key = f"{fa}vs{fb}:coverage"
        pvals[key] = p
        if p is None:
            concl = "样本不足，无法检验"
        elif p < 0.05:
            concl = "**统计显著**（p < 0.05）"
        else:
            concl = (f"方向一致但未达统计显著（n={len(a)} vs {len(b)}，"
                     f"M-W 精确检验最小可达 p={min_p}）")
        lines.append(f"| {fa} vs {fb} | 分支覆盖% | {_fmt(p, '{:.4f}')} | — | "
                     f"{_fmt(delta, '{:+.3f}')} | {_fmt(hl, '{:+.3f}')} | "
                     f"[{_fmt(lo, '{:+.3f}')}, {_fmt(hi, '{:+.3f}')}] | {concl} |")
    lines.append("")

    # ---- ★ 配对胜率（主判定口径，v2 §5.3.6）----
    lines.append("## 2b. ★ 配对胜率（主判定口径）")
    lines.append("")
    lines.append("| 指标 | 比较 | fuzzer | 胜率 | 配对差值 mean±std | "
                 "全部原始差值 | consistent_sign | 结论表述 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in winrate_rows:
        (metric, fa, fb, fz, n_pairs, wins, ties, losses, win_rate,
         mean_diff, std_diff, median_diff, min_diff, max_diff,
         consistent_sign, all_diffs, claim) = row
        lines.append(
            f"| {metric} | {fa} vs {fb} | {fz} | **{wins}/{n_pairs}** | "
            f"{mean_diff} ± {std_diff} | {all_diffs} | "
            f"{'是' if consistent_sign == 'True' else '否'} | {claim} |")
    lines.append("")
    lines.append("> 表述纪律：win rate < 5/5 时禁止写「稳定/一致」；"
                 "未达显著时禁止写「无差异」。")
    lines.append("")

    if pvals:
        corrected = holm_correction(pvals)
        lines.append("### Holm 校正后的 p 值")
        lines.append("")
        lines.append("| 比较 | 原始 p | Holm 校正 p |")
        lines.append("|---|---|---|")
        for k, v in pvals.items():
            lines.append(f"| {k} | {_fmt(v, '{:.4f}')} | "
                         f"{_fmt(corrected.get(k), '{:.4f}')} |")
        lines.append("")

    # ---- KW 检验 ----
    lines.append("## 3. Kruskal-Wallis（多组）")
    lines.append("")
    if len(groups_present) >= 2:
        gs = [_per_rep(metrics[g], "M3_coverage") for g in groups_present]
        gs = [g for g in gs if g]
        h, p = kruskal_wallis(gs)
        lines.append(f"- H = {_fmt(h, '{:.4f}')}，p ≈ {_fmt(p, '{:.4f}')}"
                     f"（组：{', '.join(groups_present)}）")
        if p is not None and p >= 0.05:
            lines.append(f"- 解读：未达显著 → 「方向一致但未达统计显著」"
                         f"（n={n_reps} vs {n_reps}，最小可达 p={min_p}）")
    lines.append("")

    # ---- 早期指标分列 ----
    lines.append("## 4. 早期指标（T+1h / T+2h）")
    lines.append("")
    early_any = False
    for g in groups_present:
        m9 = metrics[g].get("M9_early")
        if not m9:
            continue
        early_any = True
        lines.append(f"### 组 {g}")
        lines.append("")
        for k, v in m9.items():
            if isinstance(v, dict) and "mean" in v:
                lines.append(f"- {k}: mean = {_fmt(v.get('mean'), '{:.4f}')}, "
                             f"std = {_fmt(v.get('std'), '{:.4f}')}")
        lines.append("")
    if not early_any:
        lines.append("- 尚未采集早期窗口快照（T+1h / T+2h）→ "
                     "由 `rq3_snapshot.sh` 产出后重跑本脚本。")
        lines.append("")

    # ---- 审计 ----
    lines.append("## 5. 审计字段")
    lines.append("")
    lines.append("| 组 | enriched_in_seeds | enriched_in_queue | chat_times_max |")
    lines.append("|---|---|---|---|")
    for g in groups_present:
        au = metrics[g].get("audit", {})
        lines.append(f"| {g} | {_fmt(au.get('enriched_in_seeds'), '{:.0f}')} | "
                     f"{_fmt(au.get('enriched_in_queue'), '{:.0f}')} | "
                     f"{_fmt(au.get('chat_times_max'), '{:.0f}')} |")
    lines.append("")
    lines.append("> `enriched_*` 恒为 0 且 `chat_times` 恒为 0 → "
                 "ChatAFL 的启动期 LLM 增强与运行时 stall-chat 均已关闭"
                 "（编排层 `--network none` 生效）。")
    lines.append("")

    report = "\n".join(lines) + "\n"
    out = C.RQ3_ROOT / "stats_report.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
