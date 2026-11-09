"""core.fused.downstream — 中枢的下游消费方。

2026-10-09 清理：v1 的 seedgen_bridge（读 v1 Fused Dataset）已退役，
现仅保留 v2 的 rag_seedgen（知识中枢 → RAG → LLM → 种子）。
"""
from __future__ import annotations

from .rag_seedgen import (
    load_fact_views,
    assemble_bundle,
    render_seed_prompt,
    generate_seeds,
    generate_seeds_react,
    retrieve_subgraph,
    validate_seed,
    write_seeds,
    plan_seed_filenames,
)

__all__ = [
    "load_fact_views",
    "assemble_bundle",
    "render_seed_prompt",
    "generate_seeds",
    "generate_seeds_react",
    "retrieve_subgraph",
    "validate_seed",
    "write_seeds",
    "plan_seed_filenames",
]
