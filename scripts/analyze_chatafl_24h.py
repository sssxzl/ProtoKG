# -*- coding: utf-8 -*-
"""分析 ChatAFL 24h 对比实验（对照组 out-chatafl vs 实验组 out-chatafl-my）。

提取 plot_data 的时序指标，画对比曲线，输出关键时间点数据。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE = r"D:\虚拟机\ubuntu-22.04.5\share\实验测试数据\chatafl\24h"


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 14:
                continue
            try:
                rows.append({
                    "t": int(parts[0]),
                    "paths": int(parts[3]),
                    "map": float(parts[6].replace("%", "")),
                    "crashes": int(parts[7]),
                    "depth": int(parts[9]),
                    "eps": float(parts[10]),
                    "nodes": int(parts[11]),
                    "edges": int(parts[12]),
                    "chat": int(parts[13]),
                })
            except ValueError:
                continue
    return rows


def rel_hours(rows):
    t0 = rows[0]["t"]
    return [(r["t"] - t0) / 3600.0 for r in rows]


ctl = load(BASE + r"\out-chatafl\plot_data")
my = load(BASE + r"\out-chatafl-my\plot_data")

hx_c = rel_hours(ctl)
hx_m = rel_hours(my)

# 打印关键时间点对比
def at(rows, hx, target_h):
    """返回最接近 target_h 的采样点。"""
    best = min(range(len(hx)), key=lambda i: abs(hx[i] - target_h))
    return rows[best]


print("=" * 72)
print("ChatAFL 24h 对比：对照组(自带种子) vs 实验组(ProtoRAG 种子)")
print("=" * 72)
print(f"{'指标':<14}{'对照组':>12}{'实验组':>12}")
for h in [0.0, 0.5, 1.0, 2.0, 4.0, 6.0, 12.0, 24.0]:
    c = at(ctl, hx_c, h)
    m = at(my, hx_m, h)
    if h == 0.0:
        print(f"\n--- 冷启动起点 ---")
    else:
        print(f"\n--- {h:.1f}h ---")
    print(f"{'n_nodes(状态)':<14}{c['nodes']:>12}{m['nodes']:>12}")
    print(f"{'n_edges(转移)':<14}{c['edges']:>12}{m['edges']:>12}")
    print(f"{'map_size%':<14}{c['map']:>12.2f}{m['map']:>12.2f}")
    print(f"{'paths_total':<14}{c['paths']:>12}{m['paths']:>12}")
    print(f"{'crashes':<14}{c['crashes']:>12}{m['crashes']:>12}")

print("\n" + "=" * 72)
print("最终态 (fuzzer_stats):")
print(f"  对照组: nodes={ctl[-1]['nodes']} edges={ctl[-1]['edges']} map={ctl[-1]['map']}% "
      f"paths={ctl[-1]['paths']} crashes={ctl[-1]['crashes']} eps={ctl[-1]['eps']:.2f}")
print(f"  实验组: nodes={my[-1]['nodes']} edges={my[-1]['edges']} map={my[-1]['map']}% "
      f"paths={my[-1]['paths']} crashes={my[-1]['crashes']} eps={my[-1]['eps']:.2f}")
print(f"  对照组 chat_times={ctl[-1]['chat']}, 实验组 chat_times={my[-1]['chat']}")

# 画图
fig, axes = plt.subplots(2, 2, figsize=(14, 9))
C1, C2 = "#3A6EA5", "#AA5555"

axes[0, 0].plot(hx_c, [r["nodes"] for r in ctl], color=C1, lw=2, label="对照组(自带种子)")
axes[0, 0].plot(hx_m, [r["nodes"] for r in my], color=C2, lw=2, label="实验组(ProtoRAG)")
axes[0, 0].set_title("IP 状态机节点数 n_nodes（state coverage）")
axes[0, 0].set_xlabel("运行时间 (h)"); axes[0, 0].set_ylabel("状态数")
axes[0, 0].legend(); axes[0, 0].grid(alpha=0.3)

axes[0, 1].plot(hx_c, [r["edges"] for r in ctl], color=C1, lw=2, label="对照组")
axes[0, 1].plot(hx_m, [r["edges"] for r in my], color=C2, lw=2, label="实验组")
axes[0, 1].set_title("IP 状态机边数 n_edges（state transition coverage）")
axes[0, 1].set_xlabel("运行时间 (h)"); axes[0, 1].set_ylabel("转移数")
axes[0, 1].legend(); axes[0, 1].grid(alpha=0.3)

axes[1, 0].plot(hx_c, [r["map"] for r in ctl], color=C1, lw=2, label="对照组")
axes[1, 0].plot(hx_m, [r["map"] for r in my], color=C2, lw=2, label="实验组")
axes[1, 0].set_title("代码覆盖率 map_size (%)")
axes[1, 0].set_xlabel("运行时间 (h)"); axes[1, 0].set_ylabel("覆盖率 %")
axes[1, 0].legend(); axes[1, 0].grid(alpha=0.3)

axes[1, 1].plot(hx_c, [r["paths"] for r in ctl], color=C1, lw=2, label="对照组")
axes[1, 1].plot(hx_m, [r["paths"] for r in my], color=C2, lw=2, label="实验组")
axes[1, 1].set_title("paths_total（队列条目数）")
axes[1, 1].set_xlabel("运行时间 (h)"); axes[1, 1].set_ylabel("路径数")
axes[1, 1].legend(); axes[1, 1].grid(alpha=0.3)

fig.suptitle("ChatAFL 24h 对比实验（testOnDemandRTSPServer / Live555）", fontsize=14, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
out = BASE + r"\对比分析图.png"
fig.savefig(out, dpi=150, facecolor="white")
print("\n已生成对比图:", out)
