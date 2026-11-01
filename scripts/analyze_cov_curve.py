# -*- coding: utf-8 -*-
"""ChatAFL 24h×5 覆盖率（bitmap_cvg/map_size）时序对比：平均曲线 + 误差带。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE = r"D:\虚拟机\ubuntu-22.04.5\share\实验测试数据\chatafl\2026年10月12日24h"


def load_map(path):
    """返回 (hours_list, map_list)。"""
    hs, maps = [], []
    t0 = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = [x.strip() for x in line.split(",")]
        if len(p) < 14:
            continue
        try:
            t = int(p[0])
            m = float(p[6].replace("%", ""))
        except ValueError:
            continue
        if t0 is None:
            t0 = t
        hs.append((t - t0) / 3600.0)
        maps.append(m)
    return hs, maps


def resample(hs, maps, grid):
    """把 (hs, maps) 重采样到 grid 小时点（取最近值）。"""
    out = []
    for g in grid:
        i = min(range(len(hs)), key=lambda j: abs(hs[j] - g))
        out.append(maps[i])
    return out


GRID = [0, 0.5, 1, 2, 4, 6, 8, 12, 16, 20, 24]

ctl_all, my_all = [], []
for i in range(1, 6):
    hc, mc = load_map(f"{BASE}\\out-rtsp\\{i}\\plot_data")
    hm, mm = load_map(f"{BASE}\\out-rtsp-my\\{i}\\plot_data")
    ctl_all.append(resample(hc, mc, GRID))
    my_all.append(resample(hm, mm, GRID))

ctl = np.array(ctl_all)
my = np.array(my_all)
ctl_m, ctl_s = ctl.mean(0), ctl.std(0)
my_m, my_s = my.mean(0), my.std(0)

C1, C2 = "#3A6EA5", "#AA5555"
fig, ax = plt.subplots(figsize=(11, 6))
ax.plot(GRID, ctl_m, color=C1, lw=2, label="对照组(自带种子) 平均")
ax.fill_between(GRID, ctl_m - ctl_s, ctl_m + ctl_s, color=C1, alpha=0.15)
ax.plot(GRID, my_m, color=C2, lw=2, label="实验组(ProtoRAG) 平均")
ax.fill_between(GRID, my_m - my_s, my_m + my_s, color=C2, alpha=0.15)
ax.set_xlabel("运行时间 (h)")
ax.set_ylabel("代码覆盖率 bitmap_cvg (%)")
ax.set_title("代码覆盖率增长曲线（5 次重复，均值 ± 1σ）")
ax.legend()
ax.grid(alpha=0.3)
ax.set_xlim(0, 24)

out = BASE + r"\覆盖率增长曲线.png"
fig.savefig(out, dpi=150, facecolor="white")
print("已生成:", out)

# 关键点数字
print("\n时间点 | 对照组均值±σ | 实验组均值±σ | 差值")
for k, g in enumerate(GRID):
    if g in (0, 1, 4, 12, 24):
        print(f"  {g:>4}h | {ctl_m[k]:.2f}±{ctl_s[k]:.2f} | "
              f"{my_m[k]:.2f}±{my_s[k]:.2f} | {my_m[k]-ctl_m[k]:+.2f}")
