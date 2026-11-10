# -*- coding: utf-8 -*-
"""tests/test_rfc_forms_table.py —— 表格腿「按列角色」解析（协议无关）。

★ 补齐 S1 的测试缺口：`core/fused/rfc_forms.parse_state_table()` 已在生产路径
  （`rfc_extractor._extract_transition_tables_by_form`）但一度**零测试覆盖**。
  本文件锁住它的四条关键性质：
    ① 列角色由**表头列名**判定（不按固定列号）⇒ 换列名/换列序都能解析；
    ② **续行右对齐**（RFC 表格续行省略左侧列）；
    ③ **状态名继承** + 修饰后缀剥离；
    ④ 只在 `table` 块上工作、且**不含协议特例**（G2）。
"""
from __future__ import annotations

import re
from pathlib import Path

from core.fused.extraction import rfc_forms as RF


def _mk(lines: list[str]) -> RF.FormBlock:
    """由原始行构造一个 `table` 形态块（模拟 RFC 里的表格）。"""
    refs = [(i + 1, ln.rstrip()) for i, ln in enumerate(lines) if ln.strip()]
    text = "\n".join(t for _n, t in refs)
    return RF.FormBlock(kind="table", text=text, line_start=1,
                        line_end=len(lines), refs=refs)


# ===========================================================================
# ① 列角色由表头列名判定
# ===========================================================================

def test_three_column_table():
    b = _mk([
        "      state       message sent     next state after response",
        "      Init        SETUP            Ready",
        "                      TEARDOWN         Init",
        "      Ready       PLAY             Playing",
    ])
    rows = RF.parse_state_table(b)
    assert rows == [
        {"from": "Init", "method": "SETUP", "to": "Ready"},
        {"from": "Init", "method": "TEARDOWN", "to": "Init"},
        {"from": "Ready", "method": "PLAY", "to": "Playing"},
    ], f"实际 {rows}"


def test_column_role_variants():
    """★ 表头列名不同也应解析（trigger / event / command 等变体）。"""
    b = _mk([
        "  Current State | Trigger Event | New State",
        "  Idle          | START        | Active",
    ])
    rows = RF.parse_state_table(b)
    assert rows == [{"from": "Idle", "method": "START", "to": "Active"}], f"实际 {rows}"


def test_column_order_independent():
    """★ 列序不同（目标列在前）也应解析 —— 角色由列名决定，不由列号决定。"""
    b = _mk([
        "  next state     message sent      state",
        "  Ready          SETUP             Init",
    ])
    rows = RF.parse_state_table(b)
    assert rows == [{"from": "Init", "method": "SETUP", "to": "Ready"}], f"实际 {rows}"


# ===========================================================================
# ② 续行右对齐 + ③ 状态名继承 + 修饰后缀
# ===========================================================================

def test_continuation_row_right_aligned():
    """★ 续行省略左侧列 ⇒ 按**末尾对齐**映射到角色。"""
    b = _mk([
        "      state      message      next state",
        "      Init       SETUP         Ready",
        "                  TEARDOWN      Init",
    ])
    rows = RF.parse_state_table(b)
    assert rows[1] == {"from": "Init", "method": "TEARDOWN", "to": "Init"}, \
        f"实际 {rows}"


def test_state_name_inherited_and_suffix_stripped():
    """★ 状态名继承 + 修饰后缀剥离（`Playing (changed transport)` → `Playing`）。"""
    b = _mk([
        "      state       message sent     next state after response",
        "      Playing     PLAY             Playing (changed transport)",
    ])
    rows = RF.parse_state_table(b)
    assert rows == [{"from": "Playing", "method": "PLAY", "to": "Playing"}], \
        f"实际 {rows}"


def test_rows_missing_required_values_dropped():
    """★ 缺触发列或目标列的行必须被丢弃（不得产出半条转移）。"""
    b = _mk([
        "      state      message      next state",
        "      Init       SETUP",
        "      Init       SETUP         Ready",
    ])
    rows = RF.parse_state_table(b)
    assert rows == [{"from": "Init", "method": "SETUP", "to": "Ready"}], f"实际 {rows}"


# ===========================================================================
# ④ 只在 table 块上工作 + G2 守卫
# ===========================================================================

def test_non_table_block_returns_empty():
    b = _mk([
        "  The client MUST include a Transport header in every SETUP request.",
        "  The server SHOULD reject the request otherwise.",
    ])
    b.kind = "normative"
    assert RF.parse_state_table(b) == []


def test_prose_block_without_state_header_returns_empty():
    b = _mk([
        "  This section describes the general structure of the protocol.",
        "  Protocols of this family are used to transfer media data.",
    ])
    b.kind = "table"
    assert RF.parse_state_table(b) == []


def test_column_role_keywords_have_no_protocol_specialcases():
    """★ G2：列角色关键词不得含协议名或协议特定方法名。"""
    src = Path(RF.__file__).read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    for name in ("rtsp", "sip", "smtp", "SETUP", "PLAY", "INVITE", "MAIL"):
        assert not re.search(rf"\b{re.escape(name)}\b", code), (
            f"列角色关键词出现了协议/方法特例「{name}」⇒ 违反 G2")


# ===========================================================================
# 真实 RFC 回归
# ===========================================================================

def test_real_rfc_state_tables_parsed():
    """★ 真实回归：附录里的两张状态转移表各应抽出 14 条，且状态名与 RFC 原生一致。"""
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")
    f = d / "rfc2326.txt"
    if not f.is_file():
        import pytest
        pytest.skip("缺 rfc2326.txt")
    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
    got = []
    for b in RF.split_form_blocks(lines):
        if b.kind == "table":
            got.append((b.line_start, b.line_end, RF.parse_state_table(b)))
    tables = [g for g in got if g[2]]
    assert len(tables) == 2, f"应有两张状态转移表，实得 {len(tables)}"
    for lo, hi, rows in tables:
        assert len(rows) == 14, f"表 {lo}-{hi} 应 14 条，实得 {len(rows)}"
    states = {r["from"] for _lo, _hi, rows in tables for r in rows} \
        | {r["to"] for _lo, _hi, rows in tables for r in rows}
    assert states == {"Init", "Ready", "Playing", "Recording"}, f"状态名 {states}"
