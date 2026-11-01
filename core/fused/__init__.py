"""core/fused — v2 结构化知识中枢 (Structured Knowledge Hub).

2026-10-09 清理：v1 的 reader/writer/runtime/pipeline 等已退役，
本包仅保留 exceptions（v2 的 validation / registry 依赖）与 v2 模块。
"""
from __future__ import annotations

from .exceptions import (
    FusedError,
    FusedIOError,
    FusedRegistryError,
    FusedSchemaError,
    FusedValidationError,
)

__all__ = [
    "FusedError",
    "FusedSchemaError",
    "FusedRegistryError",
    "FusedValidationError",
    "FusedIOError",
]
