# -*- coding: utf-8 -*-
"""ChatAFL 24h ×5 次重复对比（对照组 vs 实验组）箱线图汇总。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE = r"D:\虚拟机\ubuntu-22.04.5\share\实验测试数据\chatafl\2026年10月12日24h"

ctl_cvg = [1.85, 1.80, 1.85, 1.82, 1.81]
my_cvg = [2.25, 2.17, 2.17, 1.98, 2.24]
ctl_crash = [0, 0, 0, 0, 0]
my_crash = [6, 8, 6, 8, 8]
ctl_depth = [25, 21, 22, 23, 22]
my_depth = [18, 14, 19, 21, 17]
ctl_nodes = [10, 9, 10, 12, 9]
my_nodes = [10, 10, 8, 8, 12]
ctl_edges = [64, 70, 68, 86, 70]
my_edges = [69, 60, 45, 45, 73]

C1, C2 = "#3A6EA5", "#AA5555"

fig, axes = plt.subplots(2, 2, figsize=(13, 9))

def bp(ax, data, labels, title, ylabel):
    bp = ax.boxplot(data, labels=labels, patch_artist=True, widths=0.5,
                    showmeans=True)
    for patch, color in zip(bp["boxes"], [C1, C2]):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
    for median in bp["medians"]:
        median.set_color("#333333")
    for mean in bp["means"]:
        mean.set_markerfacecolor("#CC0000")
        mean.set_markeredgecolor("#CC0000")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)
    # 散点叠加
    for xi, d in enumerate(data, start=1):
        ax.scatter([xi] * len(d), d, color="#333333", s=30, zorder=3, alpha=0.7)

bp(axes[0, 0], [ctl_cvg, my_cvg], ["对照组", "实验组"],
   "代码覆盖率 bitmap_cvg（%），+19.2%，p=0.006", "覆盖率 %")
bp(axes[0, 1], [ctl_crash, my_crash], ["对照组", "实验组"],
   "唯一崩溃数 unique_crashes，p=0.003", "崩溃数")
bp(axes[1, 0], [ctl_edges, my_edges], ["对照组", "实验组"],
   "状态机转移数 n_edges", "转移数")
bp(axes[1, 1], [ctl_depth, my_depth], ["对照组", "实验组"],
   "最大深度 max_depth（对照组更深）", "深度")

fig.suptitle("ChatAFL 24h ×5 次重复对比（testOnDemandRTSPServer）", fontsize=14, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
out = BASE + r"\对比分析图.png"
fig.savefig(out, dpi=150, facecolor="white")
print("已生成:", out)
