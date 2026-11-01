"""core.fused.exceptions — Fused Hub 异常类层次.

第一部分契约: fused_hub/docs/fused_knowledge_hub_design.md（v2 设计真源；异常类层次以本模块定义为准）。

异常类层次规定:
    FusedError                基类
    FusedSchemaError          Schema 或数据类结构校验失败. 携带 code 与 context
    FusedRegistryError        Registry 与 Schema artifact 加载失败 (含 JSON syntax error,
                              duplicate JSON object key, non-finite JSON number constant,
                              以及版本一致性失败). 携带 code 与 context
    FusedValidationError      Invariant 校验失败. 携带 violations 列表
    FusedIOError              读写盘失败

分类原则: "不进一步细分异常子类。错误原因通过 code 与 context 区分。"

因此本模块**不定义任何额外子类**。本模块是唯一的 Fused Hub 异常树，各子类的 code
常量由调用方在抛出点定义。
"""
from __future__ import annotations

from typing import Any


__all__ = [
    "FusedError",
    "FusedSchemaError",
    "FusedRegistryError",
    "FusedValidationError",
    "FusedIOError",
]


class FusedError(Exception):
    """Fused Hub 异常基类.

    所有 Fused Hub 派生的异常都继承本类, 调用方可以统一 `except FusedError`.
    """


class FusedSchemaError(FusedError):
    """Schema 或数据类结构校验失败.

    异常语义 — 覆盖:
        required field missing
        unknown extra field
        model structure invalid
        controlled field invalid

    Attributes:
        code: str | None — 机器可读错误码, 便于调用方分支处理
        context: dict — 错误上下文 (field / path / value 等)

    分类原则: 错误原因通过 code 与 context 区分, 不细分异常子类.
    """

    def __init__(self, message: str, code: str | None = None,
                 context: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context) if context else {}


class FusedRegistryError(FusedError):
    """Registry 与 Schema artifact 加载失败.

    异常语义 — 覆盖:
        JSON syntax error
        duplicate JSON object key
        non-finite JSON number constant
        版本一致性失败 (artifact 无法合法加载时直接抛本异常,
        不伪装成 fingerprint mismatch)

    Attributes:
        code: str | None
        context: dict
    """

    def __init__(self, message: str, code: str | None = None,
                 context: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context) if context else {}


class FusedValidationError(FusedError):
    """Invariant 校验失败.

    异常语义 — Invariant 1 到 24 任一违反.

    Attributes:
        violations: list — Violation 对象列表 (或 dict, 取决于 validation 层实现)

    注: violations 的元素类型由调用方传入, 本模块不做类型约束。
    """

    def __init__(self, message: str, violations: list | None = None):
        super().__init__(message)
        self.violations: list = list(violations) if violations else []


class FusedIOError(FusedError):
    """读写盘失败.

    读写盘失败语义; 错误 code 由调用方在抛出点自定义 (无集中常量表,
    本模块也不定义 I/O code 常量).

    Attributes:
        code: str | None — 由调用方在抛出点自定义, 无集中常量表
        context: dict — 尽量包含 path / line / column
    """

    def __init__(self, message: str, code: str | None = None,
                 context: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context) if context else {}
