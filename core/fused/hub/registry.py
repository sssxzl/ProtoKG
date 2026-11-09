"""core/fused/registry.py —— 从 fused_hub/schema/ 加载 3 个注册表。

fail-closed: 未注册引用 → UnregisteredReferenceError。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.fused.hub.exceptions import FusedSchemaError  # 同包异常基类


SCHEMA_DIR = Path("fused_hub") / "schema"


class UnregisteredReferenceError(FusedSchemaError):
    code = "unregistered_reference"


class Registry:
    """加载三个注册表的容器。

    设计: 每个注册表 JSON 含 core_version 与一个列表。
    三个注册表已由 Layer 1 Profile 填充（aspect 19 项 / epistemic 4 项 / subject 7 项），core_version 均为 "1.0"。
    """

    def __init__(self, base_dir: Path = SCHEMA_DIR):
        self.subject_types = self._load(base_dir / "subject_type_registry.json",
                                         "registered_types")
        self.aspects = self._load(base_dir / "aspect_registry.json",
                                   "registered_aspects")
        self.epistemic_types = self._load(
            base_dir / "epistemic_type_registry.json", "registered_types")

    @staticmethod
    def _load(path: Path, list_key: str) -> list:
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise FusedSchemaError(
                f"注册表 {path.name} 解析失败: {exc}",
                code="registry_parse_error",
                context={"path": str(path)}) from exc
        items = data.get(list_key, [])
        if not isinstance(items, list):
            raise FusedSchemaError(
                f"注册表 {path.name} 的 {list_key!r} 不是列表",
                code="registry_shape",
                context={"path": str(path), "got_type": type(items).__name__})
        return items


def load_registry(base_dir: Path = SCHEMA_DIR) -> Registry:
    return Registry(base_dir)