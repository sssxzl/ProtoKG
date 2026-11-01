# -*- coding: utf-8 -*-
"""分析 ChatAFL 12h 对比实验（对照组 out-rtsp vs 实验组 out-rtsp-my，-t 一致=1000）。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE = r"D:\虚拟机\ubuntu-22.04.5\share\实验测试数据\chatafl\2026年10月11日12h"


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = [x.strip() for x in line.split(",")]
        if len(p) < 14:
            continue
        try:
            rows.append(dict(t=int(p[0]), paths=int(p[3]),
                             map=float(p[6].replace("%", "")),
                             crashes=int(p[7]), depth=int(p[9]),
                             eps=float(p[10]), nodes=int(p[11]),
                             edges=int(p[12]), chat=int(p[13])))
        except ValueError:
            continue
    return rows


def hx(rows):
    t0 = rows[0]["t"]
    return [(r["t"] - t0) / 3600.0 for r in rows]


ctl = load(BASE + r"\out-rtsp\plot_data")
my = load(BASE + r"\out-rtsp-my\plot_data")
hc, hm = hx(ctl), hx(my)

C1, C2 = "#3A6EA5", "#AA5555"

fig, axes = plt.subplots(2, 2, figsize=(14, 9))
axes[0, 0].plot(hc, [r["map"] for r in ctl], color=C1, lw=2, label="对照组(自带种子)")
axes[0, 0].plot(hm, [r["map"] for r in my], color=C2, lw=2, label="实验组(ProtoRAG)")
axes[0, 0].set_title("代码覆盖率 map_size（%），实验组全程领先")
axes[0, 0].set_xlabel("运行时间 (h)"); axes[0, 0].set_ylabel("覆盖率 %")
axes[0, 0].legend(); axes[0, 0].grid(alpha=0.3)

axes[0, 1].plot(hc, [r["depth"] for r in ctl], color=C1, lw=2, label="对照组")
axes[0, 1].plot(hm, [r["depth"] for r in my], color=C2, lw=2, label="实验组")
axes[0, 1].set_title("最大状态深度 max_depth（实验组 23 vs 14）")
axes[0, 1].set_xlabel("运行时间 (h)"); axes[0, 1].set_ylabel("深度")
axes[0, 1].legend(); axes[0, 1].grid(alpha=0.3)

axes[1, 0].plot(hc, [r["nodes"] for r in ctl], color=C1, lw=2, label="对照组")
axes[1, 0].plot(hm, [r["nodes"] for r in my], color=C2, lw=2, label="实验组")
axes[1, 0].set_title("IP 状态机节点数 n_nodes（追平）")
axes[1, 0].set_xlabel("运行时间 (h)"); axes[1, 0].set_ylabel("状态数")
axes[1, 0].legend(); axes[1, 0].grid(alpha=0.3)

axes[1, 1].plot(hc, [r["edges"] for r in ctl], color=C1, lw=2, label="对照组")
axes[1, 1].plot(hm, [r["edges"] for r in my], color=C2, lw=2, label="实验组")
axes[1, 1].set_title("IP 状态机边数 n_edges（追平）")
axes[1, 1].set_xlabel("运行时间 (h)"); axes[1, 1].set_ylabel("转移数")
axes[1, 1].legend(); axes[1, 1].grid(alpha=0.3)

fig.suptitle("ChatAFL 12h 对比（testOnDemandRTSPServer，-t 1000 一致）", fontsize=14, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
out = BASE + r"\对比分析图.png"
fig.savefig(out, dpi=150, facecolor="white")
print("已生成对比图:", out)
