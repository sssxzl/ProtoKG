# -*- coding: utf-8 -*-
"""tests/test_status_code_table.py —— P1-2：状态码的「表格形态」抽取。

★ 背景（`打通缺口清单-20261106.md` §P1-2）：smtp 的 `statuses` 抽成 **0** 条，
  两个缺陷叠加：

    ① `profiles/smtp/rfc_config.json` 的 `4.2` **同时**列在
       `method_sections` 与 `status_sections`，而 `_section_kind` 旧实现是
       **固定类别优先**（method 赢）⇒ 整章「SMTP Replies」被判成 method；
    ② 状态码通道只认**章节标题**（`^\\d{3}\\s+title`），
       而 RFC 5321 §4.2.3 是**缩进表格** ⇒ 判对类型也抽不出。

  本文件守三件事：
    · `_section_kind` 的「跨类别最长前缀 + 破平局」；
    · `_extract_status_code_entries` 的表格解析（真 RFC 5321 应恰好 24 个码）；
    · 通道 C **只在 status 窗口**生效（否则正文里的三位数会被误当状态码）。
"""
from __future__ import annotations

import pytest

from core.fused.extraction import rfc_extractor as rx


# ===========================================================================
# ① `_section_kind`：跨类别最长前缀 + 破平局
# ===========================================================================

def test_section_kind_status_wins_tie_with_method():
    """同一章节号同时是 method 与 status ⇒ **status 赢**（修 smtp §4.2 的直接判据）。"""
    cfg = {"method_sections": ["4.2"], "field_sections": [],
           "status_sections": ["4.2"], "transition_sections": []}
    assert rx._section_kind({"section_no": "4.2", "title": "X"}, cfg) == "status"
    assert rx._section_kind({"section_no": "4.2.3", "title": "X"}, cfg) == "status"


def test_section_kind_longer_field_beats_shorter_method():
    """长子节胜过短的跨类别前缀：`3.6`(field) 应压过 `3`(method)。"""
    cfg = {"method_sections": ["3"], "field_sections": ["3.6"],
           "status_sections": [], "transition_sections": []}
    assert rx._section_kind({"section_no": "3.6.1", "title": "X"}, cfg) == "field"
    # 同一个 "3" 自己的直接子节仍归 method
    assert rx._section_kind({"section_no": "3.9", "title": "X"}, cfg) == "method"


def test_section_kind_method_beats_field_on_equal_length():
    """等长并列时 **method > field** —— 沿用修正前的实际行为（有测试锁定）。"""
    cfg = {"method_sections": ["10"], "field_sections": ["10"],
           "status_sections": [], "transition_sections": []}
    assert rx._section_kind({"section_no": "10.1", "title": "X"}, cfg) == "method"


def test_section_kind_empty_config_returns_none():
    assert rx._section_kind({"section_no": "9.9", "title": "X"}, {}) is None


# ===========================================================================
# ② `_extract_status_code_entries`：表格解析
# ===========================================================================

_TABLE = """\
   211  System status, or system help reply

   214  Help message (Information on how to use the receiver or the
      meaning of a particular non-standard command; this reply is useful
      only to the human user)

   220  <domain> Service ready

   252  Cannot VRFY user, but will accept message and attempt delivery
      (See Section 3.5.3)
"""


def test_table_entries_basic():
    rows = rx._extract_status_code_entries(_TABLE)
    assert [c for c, _ in rows] == ["211", "214", "220", "252"]
    # 续行被拼进 reason（RFC 用一个空行分隔条目、续行缩进更深）
    assert "only to the human user" in dict(rows)["214"]
    assert dict(rows)["220"] == "<domain> Service ready"


def test_table_entries_skip_non_three_digit():
    text = (
        "   2yz  Positive Completion reply\n"     # 严重度通配（不是具体码）
        "   4.2.3.  Reply Codes in Numeric Order\n"  # 章节标题
        "   12   short\n"                          # 两位
        "   1234  four digits\n"                   # 四位
        "   500  OK\n"
    )
    assert [c for c, _ in rx._extract_status_code_entries(text)] == ["500"]


def test_table_entries_dedupe_keeps_first():
    """§4.2.2 与 §4.2.3 会重复列出同一批码 ⇒ 只取首次出现。"""
    text = "   500  Syntax error\n   500  Syntax error again\n"
    rows = rx._extract_status_code_entries(text)
    assert len(rows) == 1 and rows[0][1] == "Syntax error"


def test_table_entries_empty_text():
    assert rx._extract_status_code_entries("") == []


def test_real_rfc5321_yields_24_codes():
    """★ 真实语料：RFC 5321 §4.2.2–§4.2.3 应恰好 24 个唯一回复码。"""
    path = rx.paths.kb_source_dir("smtp", "rfc") / "rfc5321.txt"
    if not path.is_file():
        pytest.skip("无 smtp RFC 底料")
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("4.2.2."))
    end = next(i for i, ln in enumerate(lines) if ln.startswith("4.2.4."))
    rows = rx._extract_status_code_entries("\n".join(lines[start:end]))
    codes = {c for c, _ in rows}
    assert len(codes) == 24, f"应为 24 个唯一码，实测 {len(codes)}：{sorted(codes)}"
    # 三个典型码必须在（首/中/尾）
    assert {"211", "354", "555"} <= codes


# ===========================================================================
# ③ 通道 C 只在 status 窗口生效
# ===========================================================================

def test_smtp_outcomes_come_from_both_heading_and_table():
    """smtp 的状态码全部来自表格通道（它没有逐码标题）。"""
    outcomes = [n for n in rx.extract_rfc_norms("smtp") if n["kind"] == "outcome"]
    assert len(outcomes) == 24
    # 证据串带行号（可回溯到 rfc5321.txt）
    assert all("#@" in (n.get("source") or "") for n in outcomes)
    assert any("rfc5321" in (n.get("source") or "") for n in outcomes)


def test_non_status_section_does_not_yield_codes():
    """★ 边界：正文里的三位数（如超时秒数）不得被当成状态码。

    RFC 5321 的 §4.5.3.2 讨论超时（"5 Minutes"），不是码表章节 ⇒
    通道 C 在那些窗口（kind 不是 status）里根本不运行。
    """
    # 直接验证解析器本身是「无状态」的（它只认缩进表形态），
    # 而「只在 status 窗口调用」由调用点保证 —— 用一条反向断言锁定：
    norms = rx.extract_rfc_norms("smtp")
    codes = {n["name"] for n in norms if n["kind"] == "outcome"}
    # 超时章里的 "5 Minutes" / "2 Minutes" 之类不能变成 "005"/"002"
    assert not (codes & {"005", "002", "003", "010"})


def test_smtp_status_codes_reach_the_bundle():
    """端到端：中枢 → 消费端 bundle 的 ``statuses`` 桶必须非空。"""
    from core.fused.downstream.rag_seedgen import assemble_bundle, load_fact_views

    views = load_fact_views("smtp")
    if not views:
        pytest.skip("smtp 中枢为空（需先跑 build_hub）")
    bundle = assemble_bundle(views, "smtp", source_set=["rfc"],
                             apply_allowed_methods=False,
                             include_skeleton_methods=False)
    statuses = bundle.get("statuses") or {}
    assert len(statuses) >= 20, f"smtp statuses 桶只填了 {len(statuses)} 条"
    assert "220" in statuses and "250" in statuses
