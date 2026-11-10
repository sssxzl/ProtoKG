# -*- coding: utf-8 -*-
"""tests/test_example_form_tightened.py —— `example` 判据收紧（P1-1a）。

★ 背景（证伪记录，见 `core/fused/rfc_forms.py` 模块 docstring）：
  旧判据 = 「缩进 + 短全大写词 + 任意 token」，把**散文**判成示例报文。
  实测按 `kind == "example"` 取块人工核对：rtsp 14 块里真报文 **0**。
  ⇒ 「从 RFC 示例报文取字段值」这条 P1-1 前提被证伪，故先把判据收紧，
    再谈是否值得建解析器。

★ 本文件锁四件事：
  ① 三种**协议无关**报文语法形态被接受（请求行 / 状态行 / `C:`·`S:` 对话前缀）；
  ② 旧判据误判的具体散文串、状态表数据行，**必须**不再判 example；
  ③ 真实语料上的块数锚点（rtsp 1 / sip 13 / smtp 22）—— 判据再放宽或收紧都会红；
  ④ `example` 标签在 core 内部**没有消费方** ⇒ 收紧不改任何抽取产物（可安全推进）。
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from core.fused.extraction import rfc_forms as RF

REPO = Path(__file__).resolve().parents[2]

#: 判据收紧前的旧正则（仅作对照，**不进产品代码**）。
RE_EXAMPLE_OLD = re.compile(
    r"^\s{2,}([A-Z][A-Z_]{1,15})\s+(?!\s*[A-Z][A-Z0-9_]*\s*$)(\S+)")


# ===========================================================================
# ① 三种报文语法形态被接受
# ===========================================================================

@pytest.mark.parametrize("line", [
    "  PLAY xxx://foo.com/movie PROTO/1.0",       # 请求行
    "     INVITE sip:a@b PROTO/2.0",              # 请求行（缩进更深）
    "        PROTO/2.0 200 OK",                   # 状态行
    "  PROTO/1.0 200  OK",                        # 状态行（reason 双空格）
    "   C: MAIL FROM:<a@b>",                      # 行命令协议对话前缀
    "   S: 250 OK",
])
def test_message_syntax_lines_are_example(line):
    assert RF.classify_line(line) == "example"


def test_request_line_requires_version_tail():
    """★ 请求行必须是「方法 + uri + 版本」三段；缺版本尾的不是报文。"""
    assert RF.classify_line("  PLAY xxx://foo.com/movie") != "example"
    assert RF.classify_line("  OPTIONS *") != "example"


def test_example_judgement_is_protocol_agnostic():
    """★ G2 行为守卫：换任何协议名/版本号，判定不得变化。"""
    for proto, ver in (("AAA", "0.9"), ("ZZZ", "12.34"), ("HTTP", "1.1")):
        assert RF.classify_line(f"  OPTIONS * {proto}/{ver}") == "example", proto
        assert RF.classify_line(f"  {proto}/{ver} 200 OK") == "example", proto


# ===========================================================================
# ② 旧判据的误判必须被消灭
# ===========================================================================

@pytest.mark.parametrize("line", [
    "     IP address hosts several document trees.",
    "  TEARDOWN         Init",
    "  NOTE this is prose",
])
def test_prose_no_longer_classified_as_example(line):
    """★ 旧判据会把这些判成 example（缩进 + 全大写词 + token）。"""
    assert RE_EXAMPLE_OLD.match(line), "对照前提失效：旧正则本应命中这条"
    assert RF.classify_line(line) != "example"


def test_state_table_data_row_is_not_example():
    """状态表数据行 `TEARDOWN   Init` 曾是 rtsp 那 14 块假示例的主要来源。"""
    assert RF.classify_line("  TEARDOWN         Init") == "descriptive"
    assert RF.classify_line("      Init            SETUP             Ready") == "table"


def test_example_block_requires_a_message_line():
    """块内**没有**任何报文语法行 ⇒ 整块不得判 example。"""
    prose = ["      This makes \"virtual hosting\" easier",
             "     IP address hosts several document trees.",
             "     The server MAY reject such a request."]
    assert RF.classify_form(prose) != "example"


def test_example_block_label_is_unreliable_for_message_extraction():
    """★ 实测记录：**块级** `example` 标签不足以定位一个完整报文。

    RFC 里的示例报文常是「请求行/状态行 + 若干 header 行」，而 header 行
    （`Contact: …` / `Route: <…>`）本身既不是请求行也不是状态行 ⇒ 判成
    `descriptive` / `diagram`，把块内 example 票稀释到 0.5 以下，整块掉回
    `descriptive`；原文又常把报文用正文/空行切碎，于是一个完整报文被拆成
    多块、每块只剩 1-2 行。

    ⇒ **P1-1b（示例报文 → message_instance）不得依赖 `kind == "example"` 块**，
      必须自己在全文中按「请求行/状态行 + 紧邻 header 行」扫行。
      若哪天块级判据改强到本用例变 example，本测试会红 —— 届时可同步简化 P1-1b。
    """
    message = ["        PROTO/2.0 200 OK",
               "        Via: PROTO/2.0 site",
               "        Content-Length: 0"]
    assert RF.classify_line(message[0]) == "example"
    assert RF.classify_form(message) == "descriptive"


# ===========================================================================
# ③ 真实语料锚点
# ===========================================================================

def _count_kinds(proto: str) -> dict[str, int]:
    files = sorted((REPO / "kb" / proto / "spec").glob("*.txt"))
    assert files, f"kb/{proto}/spec 下没有语料"
    out: dict[str, int] = {}
    for f in files:
        lines = io.open(f, encoding="utf-8", errors="replace").read().splitlines()
        for b in RF.split_form_blocks(lines):
            out[b.kind] = out.get(b.kind, 0) + 1
    return out


@pytest.mark.parametrize("proto,expected", [
    ("rtsp", 1),    # 收紧前 14（真报文 0）
    ("sip", 13),    # 收紧前 45（真报文 12）
    ("smtp", 22),   # 收紧前 39（多为散文）
])
def test_real_corpus_example_block_counts(proto, expected):
    """★ 锚点：块数变了说明判据被改动，必须重新人工核对真报文数。"""
    got = _count_kinds(proto)["example"]
    assert got == expected, (
        f"{proto} 的 example 块数 {got} != 锚点 {expected}；"
        "改判据后请重新人工核对真报文数并更新本锚点")


def test_rtsp_has_almost_no_real_example():
    """★ P1-1 前提证伪的机械化记录：rtsp 的 example 块几乎不存在。"""
    assert _count_kinds("rtsp")["example"] <= 1


# ===========================================================================
# ④ `example` 无消费方 ⇒ 收紧不改产物
# ===========================================================================

def test_example_kind_has_no_consumer_in_core():
    """★ 守卫：`example` 目前**只能**出现在形态层内部。

    若有人在别处给它接了消费方，收紧判据就会改变抽取产物 ——
    此时必须同步补产物回归，故这里强制红。
    """
    hits: list[str] = []
    for p in sorted((REPO / "core").rglob("*.py")):
        if p.name == "rfc_forms.py":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, ln in enumerate(text.splitlines(), 1):
            if re.search(r"""["']example["']""", ln):
                hits.append(f"{p.relative_to(REPO)}:{i}: {ln.strip()}")
    assert not hits, "`example` 出现了新消费方，判据变动会改产物：\n" + "\n".join(hits)


def test_example_is_a_structured_kind():
    """形态层仍需把 example 当结构化块合并（否则真报文会被空行切碎）。"""
    assert "example" in RF.STRUCTURED_KINDS
    assert "example" in RF.FORM_KINDS
