# -*- coding: utf-8 -*-
"""compare/config.py —— 三路消融共享配置。

⚠️ 三路（A=ProtoRAG / B=浅层知识库 / C=向量RAG）必须强制共用本配置，
   以保证可比性：唯一变量只能是「知识表示层」，不能是 LLM 参数、种子数或数据。

A 路沿用 scripts/run_seedgen_e2e.py —— 但它的 LLM 参数（temperature 等）也必须
与本文件对齐，否则 A/B/C 不可比（见 README「关键改造点」）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

# 项目根（compare/config.py -> compare -> <项目根>）
REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 三路 mode 标识
# ---------------------------------------------------------------------------
MODE_PROVENANCE = "provenance"     # A 路：现有框架，沿用 run_seedgen_e2e.py，不在此实现
MODE_SHALLOW = "shallow_kb"        # B 路：浅层知识库
MODE_VECTOR_RAG = "vector_rag"     # C 路：向量 RAG
MODES = (MODE_SHALLOW, MODE_VECTOR_RAG)  # compare/ 实际实现的两路

# ---------------------------------------------------------------------------
# LLM（三路强制共用，谁也不能单独改）
# ---------------------------------------------------------------------------
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 8000

# ---------------------------------------------------------------------------
# 协议与种子
# ---------------------------------------------------------------------------
PROTOCOL = "rtsp"
N_SEEDS = 20

# ---------------------------------------------------------------------------
# 知识源（三路同源：同一份五源原始知识）
# ---------------------------------------------------------------------------
KB_ROOT = REPO_ROOT / "kb"                          # 五源原始数据（RFC/流量/漏洞/源码/专家）
FACTS_ROOT = REPO_ROOT / "derived" / "per_source"   # A/B 路经 build_hub 抽取的 v2 Fact

# ---------------------------------------------------------------------------
# 输出（B/C 路种子，与 A 路框架的 derived/seeds/ 严格区分）
# ---------------------------------------------------------------------------
OUT_ROOT = REPO_ROOT / "compare" / "out"


def out_dir(mode: str, protocol: str = PROTOCOL) -> Path:
    """B/C 路种子输出目录：compare/out/<mode>/<protocol>/<时间戳>/"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUT_ROOT / mode / protocol / ts
