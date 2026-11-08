# -*- coding: utf-8 -*-
"""local/_patch.py —— **CRLF 安全的补丁工具**（2026-11-08 新增）。

★ 为什么要它（实测踩过的坑）：
  项目里大量文件是 **CRLF 行尾** ⇒ 用 ``\\n`` 做多行匹配会**静默失配**
  （assert count==0 ⇒ 补丁不生效 ⇒ 改了什么自己都不知道）。
  ⇒ 本工具按**行**处理（``splitlines(keepends=True)``），
  **保留每行原有行尾** ⇒ CRLF / LF 混用都不受影响。

用法：
    from local_patch import patch_lines, replace_once
    replace_once(path, "旧的一行", "新的一行")
    patch_lines(path, "锚点行", ["插入行1", "插入行2"], before=True)
"""
from __future__ import annotations

import io
from pathlib import Path


def _read_lines(path) -> list[str]:
    """读文件为「保留行尾的行列表」。"""
    p = Path(path)
    return io.open(p, encoding="utf-8", newline="").read().splitlines(keepends=True)


def _write_lines(path, lines: list[str]) -> None:
    """写回「保留行尾的行列表」。"""
    p = Path(path)
    io.open(p, "w", encoding="utf-8", newline="").write("".join(lines))


def _eol(line: str) -> str:
    """取一行的行尾（``\\r\\n`` / ``\\n`` / ``""``）。"""
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _body(line: str) -> str:
    """取一行的内容（去掉行尾）。"""
    return line[: len(line) - len(_eol(line))]


def replace_once(path, old: str, new: str, *, required: bool = True) -> int:
    """替换**唯一一行**（内容完全匹配，忽略行尾差异）。

    Returns:
        替换的行数（0 或 1）。
    """
    lines = _read_lines(path)
    hits = [i for i, ln in enumerate(lines) if _body(ln) == old]
    if len(hits) != 1:
        if required:
            raise AssertionError(
                f"{path}: 期望恰好 1 行匹配，实际 {len(hits)} 行 —— {old!r}")
        return 0
    i = hits[0]
    eol = _eol(lines[i]) or "\n"
    # ★ new 可含 ``\n`` ⇒ 拆成多行（每行沿用原行尾）
    parts = new.split("\n")
    lines[i:i + 1] = [t + eol for t in parts]
    _write_lines(path, lines)
    return len(parts)


def replace_in_file(path, old: str, new: str, *, count: int = 1) -> int:
    """在文件里替换**子串**（``count`` 次；``-1`` = 全部）。

    ★ 用**纯字符串**替换（不按行）⇒ 适合跨行片段。
    """
    p = Path(path)
    raw = io.open(p, encoding="utf-8", newline="").read()
    n = raw.count(old)
    if n < count if count > 0 else False:
        raise AssertionError(f"{path}: 期望 {count} 处匹配，实际 {n}")
    if count == -1:
        raw = raw.replace(old, new)
    else:
        raw = raw.replace(old, new, count)
    io.open(p, "w", encoding="utf-8", newline="").write(raw)
    return n


def patch_lines(path, anchor: str, new_lines: list[str], *,
                before: bool = True, required: bool = True) -> int:
    """在**锚点行**前/后插入若干行（保留行尾风格）。

    Args:
        anchor: 锚点行内容（精确匹配，去行尾后比较）。
        new_lines: 要插入的行（**不含**行尾 ⇒ 自动用锚点的行尾）。
        before: True = 插在锚点前；False = 插在锚点后。

    Returns:
        插入的行数。
    """
    lines = _read_lines(path)
    hits = [i for i, ln in enumerate(lines) if _body(ln) == anchor]
    if len(hits) != 1:
        if required:
            raise AssertionError(
                f"{path}: 锚点期望 1 行，实际 {len(hits)} 行 —— {anchor!r}")
        return 0
    i = hits[0]
    eol = _eol(lines[i]) or "\n"
    block = [t + eol for t in new_lines]
    lines[i:i] = block if before else (lines[i:i + 1] and block)
    _write_lines(path, lines)
    return len(block)


def insert_at(path, line_no: int, new_lines: list[str]) -> int:
    """在**第 line_no 行（1-based）之前**插入若干行。"""
    lines = _read_lines(path)
    eol = _eol(lines[line_no - 1]) if line_no - 1 < len(lines) else "\n"
    block = [t + eol for t in new_lines]
    lines[line_no - 1:line_no - 1] = block
    _write_lines(path, lines)
    return len(block)
