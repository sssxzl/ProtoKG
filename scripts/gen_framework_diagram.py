# -*- coding: utf-8 -*-
"""生成 ProtoRAG 整体框架图 v6（横向宽扁构图，参考用户截图 2.5:1 比例）。

横向三段：左=五源+处理链路（离线）→ 中=结构化知识中枢三层（离线）→
右=RAG 检索展开 + LLM + 校验 + 种子（在线），两阶段用大背景框区分，含图例。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

C_SRC_F, C_SRC_E = "#F5F5F5", "#666666"
C_STP_F, C_STP_E = "#E8F0FA", "#3A6EA5"
C_L1_F, C_L1_E = "#E6F5E6", "#3A7A3A"
C_L0_F, C_L0_E = "#FFF4DD", "#AA8833"
C_RAG_F, C_RAG_E = "#FFE6CC", "#AA7733"
C_LLM_F, C_LLM_E = "#EDE4F7", "#6B4FA0"
C_CHK_F, C_CHK_E = "#E0F0F0", "#3A7A7A"
C_OUT_F, C_OUT_E = "#FFE5E5", "#AA5555"
C_P1_F, C_P1_E = "#F5F8FB", "#B7C2CE"
C_P2_F, C_P2_E = "#FBF7F0", "#CDBE9E"
TXT = "#333333"
SUB = "#666666"


def box(ax, x, y, w, h, fc, ec, lw=1.5, rounding=0.05, ls="-"):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.0,rounding_size={rounding}",
                       linewidth=lw, edgecolor=ec, facecolor=fc, linestyle=ls, zorder=1)
    ax.add_patch(p)
    return p


def txt(ax, x, y, s, size=11, color=TXT, weight="normal",
        ha="center", va="center", ls=1.3):
    ax.text(x, y, s, fontsize=size, color=color, fontweight=weight,
            ha=ha, va=va, linespacing=ls, family="Microsoft YaHei", zorder=3)


def arrow(ax, x1, y1, x2, y2, color="#555555", lw=1.4, scale=13, ls="-"):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                        mutation_scale=scale, color=color, lw=lw,
                        linestyle=ls, shrinkA=0, shrinkB=0, zorder=2)
    ax.add_patch(a)


def arc(ax, x1, y1, x2, y2, rad, color="#CC0000", lw=1.2, scale=13):
    a = FancyArrowPatch((x1, y1), (x2, y2), connectionstyle=f"arc3,rad={rad}",
                        arrowstyle="-|>", mutation_scale=scale,
                        color=color, lw=lw, linestyle="--", shrinkA=2, shrinkB=2, zorder=2)
    ax.add_patch(a)


fig, ax = plt.subplots(figsize=(26, 10.5), dpi=150)
ax.set_xlim(0, 26)
ax.set_ylim(0, 10.5)
ax.axis("off")
fig.patch.set_facecolor("white")

# ---- 标题 ----
txt(ax, 13, 10.05, "ProtoRAG 整体框架", size=16, weight="bold")
txt(ax, 13, 9.62, "结构化协议知识中枢（离线构建）  +  RAG 驱动种子生成（在线消费）",
    size=9.5, color=SUB)

# ================= 离线框（左+中） =================
box(ax, 0.3, 1.3, 17.2, 8.0, C_P1_F, C_P1_E, lw=1.5, rounding=0.04)
txt(ax, 0.7, 9.08, "① 结构化知识中枢构建（Offline）", size=11, weight="bold", ha="left")

# ---- 五源 + 处理链路 ----
cols = [
    ("RFC 规范", "597", "分节切片+正则抽取", "章节切片/规范抽取", "method/header/状态机"),
    ("专家标注", "122", "结构化 JSON 解析", "白名单/约束提取", "白名单/约束/转移"),
    ("历史漏洞", "29", "CVE 解析+条件抽取", "触发条件/异常路径", "漏洞模式/边界值"),
    ("真实流量", "25", "抓包解析+报文分帧", "行为统计/去重", "method序列/状态轨迹"),
    ("协议源码", "10", "静态分析+定义抽取", "API 文档解析", "字段类型/实现细节"),
]
CYS = [8.45, 6.75, 5.05, 3.35, 1.65]
CH = 0.7
for cy, (name, cnt, p1t, p1d, p2) in zip(CYS, cols):
    box(ax, 0.7, cy - CH / 2, 1.7, CH, C_SRC_F, C_SRC_E)
    txt(ax, 1.55, cy + 0.12, name, size=8, weight="bold")
    txt(ax, 1.55, cy - 0.14, cnt, size=6.5, color=SUB)
    box(ax, 2.8, cy - CH / 2, 1.8, CH, C_STP_F, C_STP_E)
    txt(ax, 3.7, cy + 0.12, p1t, size=7, weight="bold")
    txt(ax, 3.7, cy - 0.14, p1d, size=6, color=SUB)
    box(ax, 5.0, cy - CH / 2, 1.8, CH, C_STP_F, C_STP_E)
    txt(ax, 5.9, cy, "→ " + p2, size=7, weight="bold")
    arrow(ax, 2.4, cy, 2.8, cy)
    arrow(ax, 4.6, cy, 5.0, cy)
    arrow(ax, 6.8, cy, 9.3, cy)

# ---- 结构化知识中枢（三层，有内部结构） ----
box(ax, 9.3, 1.6, 7.9, 7.55, "#FFFFFF", "#8A94A0", lw=1.7, rounding=0.04)
txt(ax, 13.25, 8.82, "结构化知识中枢（三层架构）", size=10.5, weight="bold")

box(ax, 9.6, 7.15, 7.3, 0.85, C_STP_F, C_STP_E)
txt(ax, 13.25, 7.66, "Layer 2 · 逐源映射", size=9, weight="bold")
txt(ax, 13.25, 7.36, "五类源 → 统一知识原子（fail-closed）", size=6.8, color=SUB)

arrow(ax, 13.25, 7.15, 13.25, 6.72)

box(ax, 9.6, 5.7, 7.3, 0.95, C_L1_F, C_L1_E)
txt(ax, 13.25, 6.30, "Layer 1 · 每协议 Profile", size=9, weight="bold")
txt(ax, 13.25, 6.00, "subject_type / aspect / epistemic_type", size=6.6, color=SUB)
txt(ax, 13.25, 5.80, "未注册引用 → 硬错误", size=6.6, color=SUB)

arrow(ax, 13.25, 5.7, 13.25, 5.40)

box(ax, 9.6, 3.6, 7.3, 1.72, C_L0_F, C_L0_E)
txt(ax, 13.25, 5.00, "Layer 0 · 知识原子（六元组）", size=9, weight="bold")
tuples = ["Subject", "Aspect", "Condition", "Value", "Epistemic", "Evidence"]
tw = 1.05
tg = (7.3 - 6 * tw) / 5
for i, t in enumerate(tuples):
    tx = 9.6 + i * (tw + tg)
    box(ax, tx, 4.28, tw, 0.42, "#FFFFFF", C_L0_E, lw=0.9, rounding=0.04)
    txt(ax, tx + tw / 2, 4.49, t, size=5.5, weight="bold")
txt(ax, 13.25, 4.00, "12 ValueType · 4 Epistemic · 内容哈希", size=6.6, color=SUB)

# ================= 在线框（右） =================
box(ax, 17.8, 1.3, 7.9, 8.0, C_P2_F, C_P2_E, lw=1.5, rounding=0.04)
txt(ax, 18.1, 9.08, "② RAG 驱动种子生成（Online）", size=11, weight="bold", ha="left")

# 中枢 → RAG
arrow(ax, 17.2, 5.5, 18.3, 7.75)
txt(ax, 17.6, 6.9, "检索知识原子", size=7, color=SUB, ha="left")

RX, RW = 18.3, 7.1

# RAG 检索（展开）
box(ax, RX, 7.0, RW, 1.5, C_RAG_F, C_RAG_E)
txt(ax, RX + RW / 2, 8.12, "RAG 检索（结构化 · 无向量索引）", size=9, weight="bold")
txt(ax, RX + RW / 2, 7.66, "全量分桶 assemble_bundle（小协议）", size=6.8, color=SUB)
txt(ax, RX + RW / 2, 7.40, "k-hop 子图检索 retrieve_subgraph（大协议）", size=6.8, color=SUB)
txt(ax, RX + RW / 2, 7.14, "→ 相关知识原子集", size=7.2, weight="bold")

arrow(ax, RX + RW / 2, 7.0, RX + RW / 2, 6.60)

# Prompt 组装
box(ax, RX, 5.6, RW, 0.95, C_L0_F, C_L0_E)
txt(ax, RX + RW / 2, 6.22, "Prompt 组装", size=9, weight="bold")
txt(ax, RX + RW / 2, 5.90, "知识 + 指令 → seed prompt", size=6.8, color=SUB)

arrow(ax, RX + RW / 2, 5.6, RX + RW / 2, 5.20)

# LLM 生成
box(ax, RX, 4.1, RW, 1.05, C_LLM_F, C_LLM_E)
txt(ax, RX + RW / 2, 4.76, "LLM 生成（独立模块）", size=9, weight="bold")
txt(ax, RX + RW / 2, 4.40, "→ 生成候选种子", size=6.8, color=SUB)

arrow(ax, RX + RW / 2, 4.1, RX + RW / 2, 3.70)

# 轻量校验
box(ax, RX, 2.7, RW, 0.95, C_CHK_F, C_CHK_E)
txt(ax, RX + RW / 2, 3.32, "轻量校验", size=9, weight="bold")
txt(ax, RX + RW / 2, 3.00, "白名单 / 必填头 / 状态转移", size=6.8, color=SUB)

arrow(ax, RX + RW / 2, 2.7, RX + RW / 2, 2.30)

# 种子
box(ax, RX, 1.5, RW, 0.75, C_OUT_F, C_OUT_E)
txt(ax, RX + RW / 2, 1.98, "初始种子 .raw", size=9, weight="bold")
txt(ax, RX + RW / 2, 1.72, "ProFuzzBench → AFLNet / ChatAFL", size=6.6, color=SUB)

# ReAct 回环：校验 → LLM
arc(ax, RX, 3.17, RX, 4.62, rad=-0.22)
txt(ax, RX - 0.35, 3.9, "失败反馈重生成（ReAct）", size=7, color="#CC0000",
    weight="bold", ha="right")

# ================= 图例 =================
leg = [
    (C_SRC_F, C_SRC_E, "知识源"), (C_STP_F, C_STP_E, "处理/映射"),
    (C_L1_F, C_L1_E, "Profile"), (C_L0_F, C_L0_E, "知识原子"),
    (C_RAG_F, C_RAG_E, "RAG 检索"), (C_LLM_F, C_LLM_E, "LLM"),
    (C_CHK_F, C_CHK_E, "校验"), (C_OUT_F, C_OUT_E, "种子"),
]
lx = 4.6
for fc, ec, name in leg:
    box(ax, lx, 0.45, 0.45, 0.36, fc, ec, lw=1.1, rounding=0.06)
    txt(ax, lx + 0.78, 0.63, name, size=7.5, color=SUB, ha="left")
    lx += 2.15

out = r"E:\科研\想法idea\rag-chatafl思路\ProtoRAG-整体框架图.png"
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
print("已生成:", out)
