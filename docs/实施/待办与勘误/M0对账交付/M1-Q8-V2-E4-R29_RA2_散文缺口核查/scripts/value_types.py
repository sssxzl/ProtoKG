# -*- coding: utf-8 -*-
"""Value.type 合法性门禁（隔离实现，未合并）。

- 12 种为 models.py 声明的正式类型；
- `str` 为历史遗留（74 条 expert_note），保留但标记 legacy；
- 空串 / 未知 / 拼写错误一律抛错，不降级为 text。
"""
from __future__ import annotations

DECLARED = ("scalar", "enum", "set", "sequence", "range", "pattern",
            "struct", "ref", "observation", "binary", "union", "text")
LEGACY = ("str",)                      # 历史数据实测存在，未在声明表中
KNOWN_VALUE_TYPES = frozenset(DECLARED + LEGACY)


class ValueTypeError(ValueError):
    pass


def validate_value_type(t) -> str:
    if not isinstance(t, str) or not t.strip():
        raise ValueTypeError(f"Value.type 不能为空（收到 {t!r}）")
    if t not in KNOWN_VALUE_TYPES:
        raise ValueTypeError(f"未注册的 Value.type：{t!r}")
    return t
