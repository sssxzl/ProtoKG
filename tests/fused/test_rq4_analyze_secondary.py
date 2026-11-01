# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_analyze_secondary.py —— 次要指标表「同向」列的回归测试。

背景
----
``rq4_analyze.render_secondary`` 的「同向」列原先有一行**死代码**把上一行的
计算无条件覆盖::

    same = "是" if (diff > 0) == (c2 - c1 < 0) or diff == 0 else "否"
    same = "—" if diff == 0 else ("是" if diff > 0 else "否")   # ← 无条件覆盖上一行

结果：真正的「方向相反」与「方向相同」都被显示成同一个值，列语义与表头不符。

QA 实测：
* bitmap_cvg 差 +5.00 / l_per 差 −8.00（真·方向相反）→ 显示「否」
* bitmap_cvg 差 −5.00 / l_per 差 −8.00（真·方向相同）→ **仍显示「否」**（错）

本文件要求：该列必须真正表达「bitmap_cvg 与 l_per 两个口径的方向是否一致」，
且与下方独立的「口径一致性检查 / ⚠口径分歧」段落**判定一致**。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.rq4_analyze import (  # noqa: E402
    _direction_conflict,
    render_secondary,
)

PROTO = "rtsp"


def _row(group: str, bitmap_cvg: float, l_per: float,
         b_per: float = 0.0) -> dict:
    """构造一行 summary 记录。"""
    return {
        "protocol": PROTO, "group": group, "rep": 1,
        "bitmap_cvg": bitmap_cvg, "l_per": l_per, "b_per": b_per,
    }


def _same_column(text: str) -> list[str]:
    """抽出次要指标表的「同向」列（最后一列）。"""
    vals: list[str] = []
    in_table = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("| 协议 | 指标 |"):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            break
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 6 and cells[0] != "---":
                vals.append(cells[5])
    return vals


def test_opposite_directions_show_no():
    """真·方向相反（bitmap_cvg +5.00 / l_per −8.00）→ 「同向」列必须是「否」。"""
    rows = [_row("protorag", 15.0, 2.0), _row("baseline", 10.0, 10.0)]
    text = render_secondary(rows)
    vals = _same_column(text)
    assert vals, "未解析到「同向」列"
    assert all(v == "否" for v in vals), f"方向相反时必须全是「否」，实际 {vals}"


def test_same_directions_show_yes():
    """真·方向相同（bitmap_cvg −5.00 / l_per −8.00）→ 「同向」列必须是「是」。

    这是 QA 构造出被误判为「否」的那个反例。
    """
    rows = [_row("protorag", 5.0, 2.0), _row("baseline", 10.0, 10.0)]
    text = render_secondary(rows)
    vals = _same_column(text)
    assert vals, "未解析到「同向」列"
    assert all(v == "是" for v in vals), f"方向相同时必须全是「是」，实际 {vals}"


def test_same_direction_positive_shows_yes():
    """两者同为正（+5.00 / +8.00）→ 「是」。"""
    rows = [_row("protorag", 15.0, 18.0), _row("baseline", 10.0, 10.0)]
    text = render_secondary(rows)
    vals = _same_column(text)
    assert all(v == "是" for v in vals), f"同为正时必须全是「是」，实际 {vals}"


def test_column_agrees_with_conflict_section():
    """表格「同向」列必须与下方「口径分歧」段落判定**一致**。"""
    # 方向相反 → 表格说「否」，且下方段落必须列出 ⚠ 口径分歧
    rows = [_row("protorag", 15.0, 2.0), _row("baseline", 10.0, 10.0)]
    text = render_secondary(rows)
    assert "⚠ 口径分歧" in text, "方向相反时下方必须列出口径分歧"
    assert all(v == "否" for v in _same_column(text))

    # 方向相同 → 表格说「是」，且下方不得列出口径分歧
    rows = [_row("protorag", 5.0, 2.0), _row("baseline", 10.0, 10.0)]
    text = render_secondary(rows)
    assert "⚠ 口径分歧" not in text, "方向相同时不得列出口径分歧"
    assert all(v == "是" for v in _same_column(text))


def test_missing_l_per_shows_dash():
    """l_per 缺失 → 「同向」无法判定 → 显示「—」。"""
    rows = [_row("protorag", 15.0, None), _row("baseline", 10.0, None)]
    text = render_secondary(rows)
    vals = _same_column(text)
    assert vals, "未解析到「同向」列"
    assert all(v == "—" for v in vals), f"缺 l_per 时必须全是「—」，实际 {vals}"
    assert "无法做口径一致性判定" in text, "缺 l_per 时必须如实说明无法判定"


# ---------------------------------------------------------------------------
# 判定函数本身
# ---------------------------------------------------------------------------
def test_direction_conflict_semantics():
    """_direction_conflict：方向相反=True / 相同=False / 缺数据=None。"""
    assert _direction_conflict(5.0, -8.0) is True, "方向相反必须是 True"
    assert _direction_conflict(-5.0, -8.0) is False, "方向相同必须是 False"
    assert _direction_conflict(5.0, 8.0) is False, "方向相同必须是 False"
    assert _direction_conflict(None, -8.0) is None, "缺数据必须是 None"
    assert _direction_conflict(5.0, None) is None, "缺数据必须是 None"
    # 某一侧恰为 0 → 不构成方向冲突（与历史口径一致性判定保持一致）
    assert _direction_conflict(0.0, -8.0) is False
    assert _direction_conflict(5.0, 0.0) is False


def test_column_is_protocol_level_not_per_metric():
    """「同向」是**协议级**判定：同一协议的三行指标显示同一个值。"""
    rows = [_row("protorag", 15.0, 2.0, b_per=1.0),
            _row("baseline", 10.0, 10.0, b_per=2.0)]
    vals = _same_column(render_secondary(rows))
    assert len(vals) >= 3, "次要指标表应有 l_per / b_per / bitmap_cvg 三行"
    assert len(set(vals)) == 1, f"同一协议内「同向」列应一致，实际 {vals}"
