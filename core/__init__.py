"""ProtoRAG 核心包 —— v2 结构化知识中枢。

2026-10-09 清理：v1 代码（抽取 / 知识图谱 / 生成 / 约束 / 变异 / 工作流等）已退役，
本包仅保留 v2 通路需要的薄层导出（数据模型 + LLM 客户端）。v2 核心在 core.fused 下。
"""
from .models import SeedMessage, SeedCorpus
from .llm import StubLLMClient, DeepSeekClient

__version__ = "0.5.0"

__all__ = [
    "SeedMessage", "SeedCorpus",
    "StubLLMClient", "DeepSeekClient",
]
