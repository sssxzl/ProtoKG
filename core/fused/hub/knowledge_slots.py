# -*- coding: utf-8 -*-
"""core/fused/knowledge_slots.py —— 知识分类 / 槽位契约（2026-11-08 新增）。

★ 中枢重设计的**存放位置表**：
  ``aspect_registry.json``（已有）= 「一个实体有哪些属性」
  ``knowledge_slots.json``（新）  = 「这些属性归到哪个**知识分类**」

★ 本模块提供：
  · 加载与**自洽校验**（每个 aspect 都有落位；每个槽位的 entity_types 合法）；
  · **落位判定**（给定 aspect + subject.type ⇒ (category, slot)）—— 数据重排的依据；
  · 分类枚举（供落盘、聚合、台账使用）。

★ 不变式：
  I1 分类是第一维、源是第二维 ⇒ 本模块**只管位置**，不管来源；
  I2 同一槽位可有多源 claim ⇒ 落位与 owner 无关。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

#: 槽位契约文件名（与 aspect_registry.json 同级）
SLOTS_FILENAME = "knowledge_slots.json"


def slots_path() -> Path:
    """``core/fused/hub/knowledge_slots.json`` 的绝对路径。"""
    from core import paths
    # ★ 包内绝对路径（不依赖 cwd）
    return Path(__file__).resolve().parent / SLOTS_FILENAME


@lru_cache(maxsize=1)
def load_slots() -> dict[str, Any]:
    """读槽位契约（带缓存）；缺失时返回**空契约**（⇒ 校验器会报问题）。"""
    p = slots_path()
    if not p.is_file():
        return {"version": "0.0-missing", "categories": [], "aspect_map": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": "0.0-error", "categories": [], "aspect_map": {}}


def categories() -> list[dict[str, Any]]:
    """全部知识分类（按声明顺序）。"""
    return list(load_slots().get("categories") or [])


def category_ids() -> list[str]:
    """分类 id 列表。"""
    return [str(c.get("id")) for c in categories() if c.get("id")]


def category_file(category: str) -> str:
    """某分类的**落盘文件**（相对中枢根目录）。"""
    for c in categories():
        if str(c.get("id")) == str(category):
            return str(c.get("file") or f"{category}/{category}.jsonl")
    return f"{category}/{category}.jsonl"


def slots_of(category: str) -> list[dict[str, Any]]:
    """某分类下的槽位定义。"""
    for c in categories():
        if str(c.get("id")) == str(category):
            return list(c.get("slots") or [])
    return []


def all_slots() -> list[tuple[str, str, dict[str, Any]]]:
    """全部 ``(category, slot, 定义)`` 三元组。"""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for c in categories():
        for s in (c.get("slots") or []):
            out.append((str(c.get("id")), str(s.get("name")), s))
    return out


def aspect_map() -> dict[str, dict[str, str]]:
    """``aspect -> {category, slot}`` 映射（**迁移的钥匙**）。"""
    return dict(load_slots().get("aspect_map") or {})


def locate(aspect: str, subject_type: str = "") -> Optional[tuple[str, str]]:
    """落位判定：给定 aspect（+ 实体类型）⇒ ``(category, slot)``。

    ★ ``by_entity_type`` 是**动态槽位**（待决 3）：
      同一个 aspect 按 ``subject.type`` 再分到具体槽位
      （definition@method ⇒ A.methods；definition@header ⇒ A.headers；…）。
    """
    am = aspect_map()
    ent = aspect_map_entry(aspect)
    if not ent:
        return None
    cat, slot = str(ent.get("category")), str(ent.get("slot"))
    if slot == "by_entity_type" and subject_type:
        for c in categories():
            if str(c.get("id")) != cat:
                continue
            for s in (c.get("slots") or []):
                st = {str(x).lower() for x in (s.get("entity_types") or [])}
                if subject_type.lower() in st:
                    return cat, str(s.get("name"))
        # 找不到匹配的实体类型 ⇒ 退回该分类的**第一个**槽位
        for s in (c.get("slots") or []):
            return cat, str(s.get("name"))
    return cat, slot


def aspect_map_entry(aspect: str) -> Optional[dict[str, str]]:
    """某个 aspect 的落位定义。"""
    return (load_slots().get("aspect_map") or {}).get(str(aspect))


def validate_slots() -> list[str]:
    """校验槽位契约自洽 ⇒ 返回**问题列表**（空 = 通过）。

    ★ 检查项：
      ① 每个已注册的 aspect 都有落位；
      ② 每个 aspect_map 指向的 (category, slot) 都存在；
      ③ 每个槽位的 entity_types 合法（属于已知实体类型集合）；
      ④ 每个分类都声明了落盘文件。
    """
    problems: list[str] = []
    slots = load_slots()
    if not slots.get("categories"):
        problems.append("槽位契约缺失或为空（knowledge_slots.json）")
        return problems

    # 已知 aspect（从 aspect_registry 读）
    known_aspects: set[str] = set()
    try:
        from core import paths
        reg = Path(__file__).resolve().parent / "registry" / "aspect_registry.json"
        if reg.is_file():
            data = json.loads(reg.read_text(encoding="utf-8"))
            for a in (data.get("registered_aspects") or []):
                if a.get("name"):
                    known_aspects.add(str(a["name"]))
    except (OSError, json.JSONDecodeError):
        problems.append("aspect_registry.json 不可读（无法校验 aspect 覆盖）")

    am = aspect_map()
    slot_index = {(c, s) for (c, s, _d) in all_slots()}

    # ① 每个已注册 aspect 都有落位
    for a in sorted(known_aspects):
        if a not in am:
            problems.append(f"aspect「{a}」未登记落位（aspect_map 缺）")
    # ② aspect_map 指向的槽位存在
    for a, ent in sorted(am.items()):
        cat, slot = str(ent.get("category")), str(ent.get("slot"))
        if cat not in category_ids():
            problems.append(f"aspect「{a}」指向不存在的分类 {cat}")
        elif slot != "by_entity_type" and (cat, slot) not in slot_index:
            problems.append(f"aspect「{a}」指向不存在的槽位 {cat}/{slot}")
    # ③ 槽位的 entity_types 合法
    known_types = {"method", "header", "status", "state", "relation", "timer",
                   "param", "role", "actor", "option", "protocol"}
    for (cat, slot, d) in all_slots():
        for t in (d.get("entity_types") or []):
            if str(t).lower() not in known_types:
                problems.append(
                    f"槽位 {cat}/{slot} 的 entity_type「{t}」不在已知集合")
    # ④ 每个分类都声明了落盘文件
    for c in categories():
        if not c.get("file"):
            problems.append(f"分类「{c.get('id')}」未声明落盘文件")
    return problems


__all__ = [
    "SLOTS_FILENAME", "slots_path", "load_slots", "categories",
    "category_ids", "category_file", "slots_of", "all_slots", "aspect_map",
    "locate", "aspect_map_entry", "validate_slots",
]
