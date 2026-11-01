# -*- coding: utf-8 -*-
"""compare/interface.py —— 三路知识表示的抽象接口。

B 路（浅层知识库）与 C 路（向量 RAG）实现本接口。
A 路（ProtoRAG 可溯源）沿用 scripts/run_seedgen_e2e.py，不实现本接口。

统一出口 run_ablation.py 只依赖本接口 + core.llm + core.raw_writers，
从而保证三路「唯一变量 = 知识表示」。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class KnowledgeRepresentation(ABC):
    """知识表示抽象：prepare 构建表示，render_prompt 渲染成 (system, user)。"""

    name: str = ""  # 子类覆盖：shallow_kb / vector_rag

    @abstractmethod
    def prepare(self) -> None:
        """构建知识表示（B: 抽取+分桶、剥 provenance；C: chunk + embedding + 建索引）。"""

    @abstractmethod
    def render_prompt(self, task: dict[str, Any]) -> tuple[str, str]:
        """按生成任务渲染 (system, user) prompt。

        task 约定字段：
            protocol: str
            n_seeds: int
            resources: list[dict] | None      # 目标资源清单（流名等实例知识）
            request_templates: dict | None    # 真实请求模板
        """
