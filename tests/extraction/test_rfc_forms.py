# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_forms.py —— RFC 内容形态分类层（协议无关 / 位置无关）。

★ 覆盖：
  ① 行级与块级判据（表格 / ASCII 图 / ABNF / 示例 / 规范性 / 抬头页眉 / 目录）；
  ② 形态感知合并（M1 同类合并、M2 图形窗口合并、M3 噪声丢弃）；
  ③ ★ **机械化守卫**：模块源码**不得**含协议名 / 章节号特例（G2 + G1）；
  ④ ★ **位置无关守卫**：同一段表格，放在「附录」位置与放在正文中，**形态判定必须相同**。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.fused.extraction import rfc_forms as RF


# ===========================================================================
# ① 行级判据
# ===========================================================================

def test_classify_line_forms():
    assert RF.classify_line("Request for Comments: 2326") == "boilerplate"
    assert RF.classify_line("Schulzrinne, et. al.  [Page 77]") == "boilerplate"
    assert RF.classify_line("Author's Address") == "boilerplate"
    assert RF.classify_line("12.1.  Connection ...... 45") == "toc"
    assert RF.classify_line("port      =   *DIGIT") == "abnf"
    assert RF.classify_line("  PLAY rtsp://foo.com/movie RTSP/1.0") == "example"
    assert RF.classify_line("The client MUST send a Transport header.") == "normative"
    assert RF.classify_line("state       message sent     next state") == "table"
    assert RF.classify_line("   Init        SETUP            Ready") == "table"
    assert RF.classify_line("   |     Connection        ; Section 12.10") == "table"
    assert RF.classify_line("ordinary prose line without structure") == "descriptive"


def test_graphic_chars_tightened():
    """★ 图形字符集必须收紧 —— 正文 `HTTP/1.1 [2]` 不得被误判为图。"""
    assert RF.classify_line("HTTP/1.1 [2] so that extension mechanisms work") \
        != "diagram"
    assert RF.classify_line("   +-----+     +-----+") == "diagram"


# ===========================================================================
# ② 块级判据
# ===========================================================================

def test_classify_form_table_block():
    lines = ["      state           message received  next state",
             "      Init            SETUP             Ready",
             "                      TEARDOWN          Init",
             "      Ready           PLAY              Playing"]
    assert RF.classify_form(lines) == "table"


def test_classify_form_diagram_block():
    lines = ["   +-------+        +-------+",
             "   | Init  |  ---> | Ready |",
             "   +-------+        +-------+",
             "                      |",
             "                      v",
             "                  +-------+",
             "                  | Play  |",
             "                  +-------+"]
    assert RF.classify_form(lines) == "diagram"


def test_classify_form_normative_block():
    lines = ["   The client MUST include a Transport header in every SETUP",
             "   request, and the server SHOULD reject the request otherwise.",
             "   A client that receives a 4xx response MUST NOT retry."]
    assert RF.classify_form(lines) == "normative"


def test_classify_form_descriptive_block():
    lines = ["   This section describes the general structure of the protocol.",
             "   Protocols of this family are used to transfer media data.",
             "   The following paragraphs give historical background."]
    assert RF.classify_form(lines) == "descriptive"


# ===========================================================================
# ③ 形态感知合并
# ===========================================================================

def test_m2_diagram_merged_across_blank_lines():
    """★ M2：ASCII 图内部有空行 ⇒ 不得被切成多块。"""
    lines = [
        "   +-------+        +-------+",
        "   | Init  |  ---> | Ready |",
        "",
        "   |       |        |       |",
        "   +-------+        +-------+",
        "",
        "   prose line that is clearly not part of the figure at all",
    ]
    blocks = RF.split_form_blocks(lines)
    dgs = [b for b in blocks if b.kind == "diagram"]
    assert len(dgs) == 1, f"图形块应合并为 1 块，实得 {len(dgs)}"
    assert "Init" in dgs[0].text and "Ready" in dgs[0].text


def test_m1_same_kind_merged():
    """★ M1：同类（table）相邻块合并。"""
    lines = ["      state      message      next state",
             "      Init       SETUP         Ready",
             "",
             "      Ready      PLAY          Playing",
             "      Playing    PAUSE         Ready"]
    blocks = RF.split_form_blocks(lines)
    tbls = [b for b in blocks if b.kind == "table"]
    assert len(tbls) == 1, f"表格块应合并为 1 块，实得 {len(tbls)}"
    assert "Init" in tbls[0].text and "Playing" in tbls[0].text


def test_m3_noise_dropped():
    lines = ["Request for Comments: 2326",
             "1.  Introduction .................... 5",
             "2.  Basic Structure ................. 7"]
    assert RF.split_form_blocks(lines) == []
    kept = RF.split_form_blocks(lines, drop_noise=False)
    assert kept, "drop_noise=False 时应保留"


def test_blocks_carry_line_numbers():
    lines = ["", "prose one", "prose two", ""]
    blocks = RF.split_form_blocks(lines)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.line_start == 2 and b.line_end == 3
    assert b.refs[0][0] == 2
    assert b.text == "prose one\nprose two"


# ===========================================================================
# ④ 通用性守卫（G1 位置无关 / G2 协议无关）
# ===========================================================================

def test_module_has_no_protocol_specific_constants():
    """★ G2 机械化守卫：形态层源码**不得**出现协议名。"""
    src = Path(RF.__file__).read_text(encoding="utf-8")
    # 去掉文档字符串后再查，避免注释里的举例被误判
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    for name in ("rtsp", "sip", "smtp", "rfc2326", "rfc3261", "rfc5321"):
        assert not re.search(rf"\b{re.escape(name)}\b", code, re.I), (
            f"形态层出现了协议特例「{name}」⇒ 违反 G2（协议无关）")


def test_module_has_no_section_number_specialcases():
    """★ G1 机械化守卫：不得出现章节号特例（如 'A.1' / '10.4'）。"""
    src = Path(RF.__file__).read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    assert not re.search(r"[\"']\s*[A-Z]\.\d+[\"']", code), (
        "形态层出现了字母章节号特例 ⇒ 违反 G1（位置无关）")
    assert not re.search(r"[\"']\s*\d{1,2}\.\d{1,2}[\"']", code), (
        "形态层出现了数字章节号特例 ⇒ 违反 G1（位置无关）")


def test_form_judgement_is_position_independent():
    """★ G1 行为守卫：同一段内容放在不同位置，形态判定必须相同。"""
    table = ["      state      message      next state",
             "      Init       SETUP         Ready",
             "      Ready      PLAY          Playing"]
    as_appendix = ["Appendix A: Protocol State Machines",
                   "",
                   *table]
    as_body = ["12.  Some Section",
               "",
               *table]
    def kinds_of(lines):
        return [b.kind for b in RF.split_form_blocks(lines)]

    k1, k2 = kinds_of(as_appendix), kinds_of(as_body)
    assert "table" in k1 and "table" in k2, (
        f"同一段表格在两处都应判为 table，实得 {k1} vs {k2}")
    # ★ 且两处**同形态块的内容必须完全一致**（位置不影响内容切分）
    t1 = next(b.text for b in RF.split_form_blocks(as_appendix)
              if b.kind == "table")
    t2 = next(b.text for b in RF.split_form_blocks(as_body)
              if b.kind == "table")
    assert t1 == t2, "位置影响了表格块的内容切分"


# ===========================================================================
# ⑤ 真实 RFC 回归（验收标准：形态层须覆盖**附录里的表格**，不依赖章节树）
# ===========================================================================

def test_real_rfc_appendix_tables_are_detected():
    """★ 验收核心：RFC **附录**里的状态转移表必须被形态层识别为 `table`。

    ★ 该表位于「字母编号附录」内 ⇒ **现有章节树不认它**（`_parse_heading_shape`
      对 `A.1 …` 返回 None）⇒ 若形态层也认不出，就得靠"全文扫"侥幸命中。
    ★ 本测试锁住「形态层与章节树解耦」这一通用性前提。
    """
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        pytest.skip("无 RFC 底料（需先准备 kb）")
    f = d / "rfc2326.txt"
    if not f.is_file():
        pytest.skip("缺 rfc2326.txt")
    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
    blocks = RF.split_form_blocks(lines)
    tables = [b for b in blocks if b.kind == "table"]
    # 表头行含 "state" 且含 "message" ⇒ 即状态转移表
    hit = [b for b in tables
           if "state" in b.text.lower() and "message" in b.text.lower()]
    assert hit, "未识别出状态转移表（形态层失效）"
    assert all(b.line_start > 4000 for b in hit), (
        "状态转移表应在附录区（行 >4000），实测 "
        f"{[b.line_start for b in hit]}")
