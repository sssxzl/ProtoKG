# -*- coding: utf-8 -*-
"""ChatAFL 对比实验分析：覆盖率时序曲线 + 崩溃曲线（对照组 vs 实验组，5 次重复）。

用法: python scripts/analyze_compare_12h.py [--hours 24]
"""
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=float, default=24.0,
                help="实验总时长（小时），图表横轴与关键时间点据此生成，默认 24")
_args = ap.parse_args()
HOURS = _args.hours

DATA = "derived/analysis/data"
OUT = "derived/analysis"
os.makedirs(OUT, exist_ok=True)


def load(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 13:
                continue
            try:
                rows.append({
                    "t": int(parts[0]),
                    "paths": int(parts[3]),
                    "map": float(parts[6].replace("%", "")),
                    "crashes": int(parts[7]),
                    "nodes": int(parts[11]),
                    "edges": int(parts[12]),
                })
            except (ValueError, IndexError):
                continue
    return rows


def series(rows, key):
    """返回 (相对小时列表, 指标列表)。"""
    if not rows:
        return [], []
    t0 = rows[0]["t"]
    return [(r["t"] - t0) / 3600.0 for r in rows], [r[key] for r in rows]


def load_group(prefix):
    """加载 5 次重复，返回 {key: [(hours, values), ...]}。"""
    groups = {}
    for i in range(1, 6):
        rows = load(f"{DATA}/{prefix}_{i}_plot_data")
        for key in ("map", "crashes", "nodes", "edges", "paths"):
            h, v = series(rows, key)
            groups.setdefault(key, []).append((h, v))
    return groups


def mean_band(groups, key, hmax=None, step=0.25):
    """对 5 次重复做时间对齐重采样，返回 (hour_axis, mean, std)。"""
    if hmax is None:
        hmax = HOURS
    hours = np.arange(0, hmax + 1e-6, step)
    curves = []
    for h, v in groups[key]:
        interp = np.interp(hours, h, v) if len(v) > 1 else np.full_like(hours, np.nan)
        curves.append(interp)
    curves = np.array(curves)
    mean = np.nanmean(curves, axis=0)
    std = np.nanstd(curves, axis=0)
    return hours, mean, std


def pick_index(hours, h_target):
    """在**时间轴** ``hours`` 上取最接近 ``h_target`` 的下标。

    ★ 为什么不用 ``int(h_target / step)`` 这种算术
    ---------------------------------------------
    1) 时间轴是 ``np.arange(0, hmax + 1e-6, step)`` 生成的，其长度与末元素
       取决于 ``hmax`` 与 ``step``；用算术反推下标一旦 ``step`` 变化就会错位。
    2) ``hmax`` **不一定是 step 的整数倍**（如 ``HOURS=10.3`` 时末元素只有 10.25），
       算术算出的下标会越界。
    本函数直接**在轴上找最近点**并夹紧到合法范围，两种情况都正确。

    Returns:
        最接近 ``h_target`` 的下标（int）。
    """
    if len(hours) == 0:
        return 0
    return int(np.argmin(np.abs(np.asarray(hours) - h_target)))


ctl = load_group("out-rtsp")
my = load_group("out-rtsp-my")

# ============ 图 1：覆盖率 + 崩溃（2x2） ============
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
C1, C2 = "#3A6EA5", "#AA5555"

for ax, key, title, ylabel in [
    (axes[0, 0], "map", "代码覆盖率 map_size (%)", "覆盖率 %"),
    (axes[0, 1], "crashes", "唯一崩溃数 unique_crashes", "崩溃数"),
    (axes[1, 0], "nodes", "IP 状态机节点数 n_nodes", "状态数"),
    (axes[1, 1], "edges", "IP 状态机边数 n_edges", "转移数"),
]:
    hc, mc, sc = mean_band(ctl, key)
    hm, mm, sm = mean_band(my, key)
    ax.plot(hc, mc, color=C1, lw=2, label="对照组(原始种子)")
    ax.fill_between(hc, mc - sc, mc + sc, color=C1, alpha=0.15)
    ax.plot(hm, mm, color=C2, lw=2, label="实验组(漏洞导向种子)")
    ax.fill_between(hm, mm - sm, mm + sm, color=C2, alpha=0.15)
    ax.set_title(title, fontsize=12)
    ax.set_xlabel("运行时间 (h)"); ax.set_ylabel(ylabel)
    ax.legend(); ax.grid(alpha=0.3)
    ax.set_xlim(0, HOURS)

fig.suptitle(f"ChatAFL {HOURS:.0f}h 对比实验（testOnDemandRTSPServer / Live555，5 次重复均值±标准差）",
             fontsize=14, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
out1 = "derived/analysis/对比分析图.png"
fig.savefig(out1, dpi=150, facecolor="white")
print("已生成:", out1)

# ============ 图 2：5 次重复的原始曲线（覆盖率） ============
fig2, axes2 = plt.subplots(1, 2, figsize=(14, 5))
for ax, groups, title in [(axes2[0], ctl, "对照组（原始种子）"),
                          (axes2[1], my, "实验组（漏洞导向种子）")]:
    for i, (h, v) in enumerate(groups["map"], start=1):
        ax.plot(h, v, lw=1.2, alpha=0.8, label=f"重复 {i}")
    ax.set_title(f"{title} — 覆盖率", fontsize=12)
    ax.set_xlabel("运行时间 (h)"); ax.set_ylabel("覆盖率 %")
    ax.legend(); ax.grid(alpha=0.3); ax.set_xlim(0, HOURS)

fig2.suptitle("覆盖率时序（5 次重复原始曲线）", fontsize=13, fontweight="bold")
fig2.tight_layout(rect=[0, 0, 1, 0.95])
out2 = "derived/analysis/覆盖率原始曲线.png"
fig2.savefig(out2, dpi=150, facecolor="white")
print("已生成:", out2)

# ============ 关键时间点对比打印 ============
print("\n" + "=" * 70)
print("关键时间点对比（5 次重复均值）")
print("=" * 70)
print(f"{'指标':<14}{'对照组':>10}{'实验组':>10}{'差异':>10}")
_targets = sorted({2.0, 4.0, 8.0, 12.0, HOURS})
for h_target in _targets:
    print(f"\n--- {h_target:.0f}h ---")
    for key, name in [("map", "覆盖率%"), ("crashes", "崩溃数"), ("nodes", "状态节点"), ("edges", "状态边")]:
        hc, mc, _ = mean_band(ctl, key)
        hm, mm, _ = mean_band(my, key)
        # ★ 两组必须落在**同一条时间轴**上，差值 m - c 才是"同一时刻相减"。
        if len(hc) != len(hm) or not np.allclose(hc, hm):
            raise ValueError(
                f"对照组与实验组的时间轴不一致（{len(hc)} vs {len(hm)} 点）——"
                "跨组差值将失去意义，请检查 mean_band 的 hmax/step"
            )
        # ★ 在**时间轴**上取与 h_target 最近的下标。
        #   历史实现是 `int(h_target / 0.25) - 1` → 少减了 1，
        #   导致「--- 2.0h ---」实际取的是 1.75h 的数据（标签与实际时刻差一个 step）。
        #   （跨组差值 m - c 不受影响：两组用的是同一个 idx，即同一时刻相减。）
        idx = pick_index(hc, h_target)
        c, m = mc[idx], mm[idx]
        print(f"{name:<14}{c:>10.2f}{m:>10.2f}{m - c:>+10.2f}")
