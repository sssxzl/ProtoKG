# -*- coding: utf-8 -*-
"""★ N0：★ 防止再次出现「重复定义导致补丁静默失效」。

★ 背景：★ `prose_semantics.py` 曾含 5 个 `_collect_blocks` 定义（★ 历史 CRLF 补丁遗留），
★ ★ Python 以最后一个定义为准 ⇒ ★ 补丁若插入非最后定义 ⇒ ★ **静默不生效**。
★ 本测试用 AST 扫描全部受保护模块，★ 保证**顶层函数/类名唯一**。
"""
from __future__ import annotations

import ast
import collections
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
# ★ 历史上出现过重复定义的模块（★ 重点防护对象）
PROTECTED = [
    "core/fused/extraction/prose_semantics.py",
    "core/fused/extraction/normative_extract.py",
    "core/fused/extraction/normative_verify.py",
    "core/fused/extraction/normative_rule.py",
    "core/fused/extraction/coreference.py",
    "core/fused/extraction/block_selection.py",
]


def _dups(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = collections.Counter()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names[node.name] += 1
    return {k: v for k, v in names.items() if v > 1}


@pytest.mark.parametrize("rel", PROTECTED)
def test_no_duplicate_top_level_definitions(rel):
    """★ 顶层函数/类名必须唯一（★ 否则补丁可能落到失效定义上）。"""
    _p = ROOT / rel
    assert _p.is_file(), rel
    _d = _dups(_p)
    assert not _d, f"★ {rel} 存在重复定义：{_d}"


def test_prose_semantics_has_single_collect_blocks():
    """★ 显式锁定 P0.9 的教训。"""
    _p = ROOT / "core/fused/extraction/prose_semantics.py"
    _tree = ast.parse(_p.read_text(encoding="utf-8"))
    _n = sum(1 for n in _tree.body
             if isinstance(n, ast.FunctionDef) and n.name == "_collect_blocks")
    assert _n == 1, f"★ `_collect_blocks` 定义 { _n } 次（★ 应为 1）"


def test_runtime_object_is_the_last_definition():
    """★ 运行时生效的函数**必须**是源码里唯一的那个（★ 防止再次静默分叉）。"""
    import importlib
    _mod = importlib.import_module("core.fused.extraction.prose_semantics")
    _p = ROOT / "core/fused/extraction/prose_semantics.py"
    _tree = ast.parse(_p.read_text(encoding="utf-8"))
    for _n in _tree.body:
        if isinstance(_n, ast.FunctionDef) and _n.name == "_collect_blocks":
            assert _mod._collect_blocks.__code__.co_firstlineno == _n.lineno, (
                "★ 运行时对象与源码定义不一致 ⇒ ★ 存在同名覆盖")
