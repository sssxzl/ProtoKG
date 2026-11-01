# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_logical_sentences.py —— B-13（约束候选按**逻辑句**切句）。

背景
----
RFC 正文是**折行排版**（一个逻辑句跨多行）。B-3 引入的
``core/fused/rfc_extractor.py::_split_sentences_with_offsets`` 原本按**物理行**
切句 ⇒ 抽出的约束候选经常是**半句**（实测 430 条里 76.6% 的散文类候选
以「句中」状态结尾）。

半句会让 B-10 的 C0/E1/E2 三组对照建立在**半句候选池**上 ⇒ 测的是抽取
粒度，而不是表达层升级的收益。

本文件锁住 B-13 的**行为契约**：

  ① **切句规则**（协议无关、确定性、**无 LLM**）：
     段落边界（源行号不连续）/ 行内句界 / 跨行合并三档；
  ② **边界情况**：列举项、表格行、ASCII 图示、ABNF 语法行、跨行引用块、
     章节标题 —— 各自的处理方式；
  ③ **不用缩进判边界**（RFC 缩进是排版对齐，不是语义边界）；
  ④ **C2 逐字核对不受影响**（``raw[span_start:span_end] == text`` 恒成立）；
  ⑤ **B-5 的模式命中率不下降**（改动的目的是**提高**它）；
  ⑥ **B-5 的 ``abnf_rule`` 依赖不被破坏**（ABNF 行仍自成一句）。

⚠ 本文件**不**断言候选条数（条数会随语料与规则演化）⇒ 用**比率**与
  **不变量**表达契约。
"""
from __future__ import annotations

import pathlib
import re

import pytest

from core.fused import rfc_extractor as R
from core.fused.semantic_rules import PATTERNS, match_pattern

PROTOCOLS = ("rtsp", "sip", "smtp")
ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 候选 `source` 的唯一形态：file:<name>#@<真实行号>
_RE_SOURCE = re.compile(r"^file:(?P<name>[^#]+)#@(?P<line>\d+)$")


# ===========================================================================
# 测试夹具
# ===========================================================================

@pytest.fixture(scope="module")
def candidates() -> dict:
    """三协议的约束候选（模块级缓存 —— 抽取要读全文，重复调用很慢）。"""
    return {p: R.extract_constraint_candidates(p) for p in PROTOCOLS}


@pytest.fixture(scope="module")
def spec_texts() -> dict:
    """{protocol: {文件名: 原文}}"""
    return {p: {f.name: f.read_text(encoding="utf-8", errors="ignore")
                for f in sorted((ROOT / "kb" / p / "spec").glob("*.txt"))}
            for p in PROTOCOLS}


def _split(text: str, refs: list[tuple[int, str]]):
    """切句（逻辑句口径）。"""
    return R._split_sentences_with_offsets(text, refs)


def _mk(lines: list[str], first_lineno: int = 100,
        gap: int = 1) -> tuple[str, list[tuple[int, str]]]:
    """由物理行构造 (窗口文本, 行引用)。

    Args:
        lines: 物理行（不含换行）。
        first_lineno: 首行的**源文件行号**。
        gap: 相邻行的行号步长（``gap=2`` ⇒ 制造**段落边界**）。
    """
    refs = [(first_lineno + i * gap, ln) for i, ln in enumerate(lines)]
    return "\n".join(lines), refs


# ===========================================================================
# ① 切句规则
# ===========================================================================

def test_wrapped_lines_merge_into_one_logical_sentence():
    """**折行合并**：一个逻辑句跨 3 个物理行 ⇒ 切成 **1** 句（跨 3 行）。"""
    lines = [
        "   The client MUST send a request to the server and the server MUST",
        "   reply with a 200 (OK) response before the session is torn down by",
        "   the client.",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 1, out
    sent, s, e = out[0]
    assert sent == text
    assert (s, e) == (0, len(text))


def test_sentence_terminator_breaks_the_sentence():
    """**句末标点断句**：上一行以 ``.`` 结尾 ⇒ 不与下一行合并。"""
    lines = [
        "   The server MUST reply with an error. The client MUST wait for",
        "   the reply before it sends the next request.",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 2, out
    assert out[0][0].endswith("error.")
    assert out[1][0].startswith("The client MUST wait for")


def test_paragraph_break_prevents_merging():
    """**段落边界** = 源文件**行号不连续** ⇒ 绝不跨段落合并。

    ★ 这正是 RFC 里「空行分段」在清洗后的体现：`_doc_content_lines` 会丢掉
      空行 ⇒ 段落内相邻行号连续、段落间行号有缺口。
    """
    lines = [
        "   The client MUST send a request",
        "   to the server.",
    ]
    text, refs = _mk(lines, gap=2)          # ← 行号不连续 ⇒ 段落边界
    out = _split(text, refs)
    assert len(out) == 2, out


def test_indentation_is_not_a_boundary_signal():
    """★ **不用缩进判边界**：RFC 的缩进是排版对齐，不是语义边界。

    同一段里三行缩进不同（RFC 的缩进定义条目就是这个样子）⇒ **合并成 1 句**。
    若用缩进判边界，这块定义会被切成 3 个半句。
    """
    lines = [
        "   Aggregate control:",
        "          The control of the multiple streams using a single timeline",
        "          by the server.",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 1, out
    assert "The control of the multiple streams" in out[0][0]
    assert out[0][0].endswith("by the server.")


def test_split_is_deterministic():
    """★ **确定性**：同一输入两次 ⇒ 完全相同（无随机、无 LLM）。"""
    lines = [
        "   The server MUST respond with 400 (Bad Request) if the request is",
        "   malformed, and it MUST log the error.",
    ]
    text, refs = _mk(lines)
    assert _split(text, refs) == _split(text, refs)


def test_legacy_fallback_without_refs():
    """``refs=None`` ⇒ 退化为**历史口径**（按物理行 / 行内句末标点切分）。"""
    text = "   The server MUST reply.\n   The client MUST wait."
    out = R._split_sentences_with_offsets(text)
    assert [s.strip() for s, _a, _b in out] == [
        "The server MUST reply.", "The client MUST wait."]


# ===========================================================================
# ② 边界情况
# ===========================================================================

@pytest.mark.parametrize("marker", ["1. ", "a) ", "- ", "* ", "+ "])
def test_list_item_is_not_absorbed_by_preceding_prose(marker: str):
    """**列举项**：不被前一行散文吞掉（它自成一句）。"""
    lines = [
        "   The client MUST send the following headers:",
        f"   {marker}The CSeq header",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    # 前一行散文与列举项**必须落在不同的句子里**
    assert len(out) >= 2, out
    assert not out[0][0].endswith("headers:" + marker.strip() + "The CSeq header")
    assert any(marker.strip() in s for s, _a, _b in out)


def test_list_item_may_absorb_its_own_continuation():
    """**列举项**可以续写**自己的**下一行（缩进的续行）。

    ★ 列举项与表格/ABNF 不同：它是**散文**，只是带了个编号标记 ⇒
      它的续行仍属同一句（否则又变半句）。
    """
    lines = [
        "   1. The registrar returns a 200 (OK) response and the client MUST",
        "      wait for the reply before it sends the next request.",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 2, out
    tail = out[-1][0]
    assert "wait for the reply before it sends the next request." in tail
    assert "\n" in tail, "列举项的续行应当被合并进同一句"


def test_table_row_is_not_merged():
    """**表格行**：列对齐的表格行**不与散文合并**（合并会得到无意义串）。"""
    lines = [
        "   The methods are listed below:",
        "      DESCRIBE          C->S             P,S        recommended",
        "      ANNOUNCE          C->S, S->C       P,S        optional",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 3, out
    assert out[1][0].lstrip().startswith("DESCRIBE")


def test_pipe_table_row_is_not_merged():
    """**表格行**（``|`` 开头）同样不合并。"""
    lines = [
        "   The response codes are:",
        '   |     "411"      ; Length Required',
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 2, out


def test_ascii_art_and_rule_lines_are_not_merged():
    """**ASCII 图示 / 分隔线**不与散文合并。"""
    lines = [
        "   The message format is:",
        "   +---------+",
        "   | header  |",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 3, out


def test_abnf_line_is_its_own_sentence():
    """★ **ABNF 产生式自成一句**（前后都不合并）。

    ★ 这是 B-5 ``abnf_rule`` 模式不被破坏的前提：该模式的正则以 ``^``
      锚定句首 ⇒ 一旦 ABNF 行被并进散文句，``^`` 锚点失效 ⇒ B-5 再也
      抽不出 ABNF 约束。
    """
    lines = [
        "   The CSeq header is defined as follows:",
        "   CSeq = 1*DIGIT",
        "          *( SEMI ( \"[\" token \"]\" / [ branch-id ] ) )",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 3, out
    assert out[1][0].strip() == "CSeq = 1*DIGIT"


def test_prose_starting_with_a_quote_is_still_prose():
    """★ 以 `"` 开头但**引号已闭合**的行**仍是散文**（可合并）。

    ⚠ RFC 里有大量这样的行（RFC 2119 关键词说明行等）—— 若把它们当成
      「引用块」⇒ 该行不与下一行合并 ⇒ 又变回半句。
    """
    lines = [
        '   The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",',
        '   "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this',
        "   document are to be interpreted as described in RFC 2119 [4].",
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 1, out
    assert out[0][0].endswith("RFC 2119 [4].")


def test_unclosed_quote_block_stays_together_and_isolated():
    """**跨行引用块**（`"..."` 跨行）自成一句，且**不与散文合并**。"""
    lines = [
        "   The quoted example is",
        '   "an unterminated quote',
        '   continued here."',
    ]
    text, refs = _mk(lines)
    out = _split(text, refs)
    assert len(out) == 2, out
    assert out[1][0].lstrip().startswith('"an unterminated quote')
    assert out[1][0].rstrip().endswith('continued here."')


def test_section_heading_never_enters_the_body():
    """★ **章节标题绝不能并入正文句子**（结构保证，不是靠形态判据）。

    `_split_heads_bodies` 在构造章节正文时就把标题行摘走了 ⇒ 标题行
    **不可能**出现在 `body_refs` 里 ⇒ 正文句子永不包含标题。
    """
    raw = (ROOT / "kb" / "rtsp" / "spec" / "rfc2326.txt").read_text(
        encoding="utf-8", errors="ignore")
    content = R._doc_content_lines(raw.splitlines())
    heads, bodies, nos = R._split_heads_bodies(content)
    assert heads
    head_lines = {h.line for h in heads}
    for body, nums in zip(bodies, nos):
        for lineno in nums:
            assert lineno not in head_lines, (
                f"标题行 {lineno} 混进了正文")


# ===========================================================================
# ③ 集成：候选层不变量
# ===========================================================================

def test_span_is_verbatim_in_source(candidates, spec_texts):
    """★ **C2 逐字核对不受影响**：`raw[span_start:span_end] == text` 恒成立。

    ★ 这是 B-2「先验证证据再判显式」的物理前提 —— 切句粒度改了之后，
      span 可能**跨行**，但**逐字相等**这条不变量必须保持 100%。
    """
    total = 0
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m, f"{p}: source 格式不合法：{c['source']!r}"
            raw = spec_texts[p][m.group("name")]
            assert raw[c["span_start"]:c["span_end"]] == c["text"], (
                f"{p}: span 与原文不一致：{c['source']}")
            total += 1
    assert total > 0


def test_span_start_is_inside_the_anchor_line(candidates, spec_texts):
    """★ span **起点**必须落在锚点行内（splitlines 口径）。

    ★ 这正是 B-2 的 C2 第③条（行锚点包含性）—— 切句粒度改成跨行之后，
      「起点在锚点行内」仍是硬契约（`span_end` 可以跨行）。
    """
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            raw = spec_texts[p][m.group("name")]
            offsets = R._line_offsets(raw)
            lineno = int(m.group("line"))
            start_off = offsets.get(lineno)
            assert start_off is not None, f"{p}: 行号 {lineno} 不存在"
            end_off = offsets.get(lineno + 1, len(raw))
            assert start_off <= c["span_start"] < end_off, (
                f"{p}: span 起点不在锚点行 {lineno} 内：{c['source']}")


def test_prose_candidates_are_no_longer_truncated_mid_sentence(
        candidates, spec_texts):
    """★ **半句率大幅下降**：散文类候选里「不以句末标点结束」的比例 ≤ 20%。

    ★ 改前实测 **76.6%**（305/398）—— 那正是「候选被切成半句」的量化。
    """
    prose = 0
    truncated = 0
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            raw = spec_texts[p][m.group("name")]
            line = raw.splitlines()[int(m.group("line")) - 1]
            if not R._line_structure(line) == "prose":
                continue
            prose += 1
            if not re.search(r"[.!?][\"'\u2019)\]]*$", c["text"]):
                truncated += 1
    assert prose > 0
    ratio = truncated / prose
    assert ratio <= 0.20, (
        f"散文类候选的折行截断率仍达 {ratio:.1%}（改前 76.6%）")


def test_b5_pattern_hit_rate_did_not_drop(candidates):
    """★ **B-5 的模式命中率不下降**（改动的目的恰恰是**提高**它）。

    ★ 改前实测 34/430 = 7.9%；按**比率**表达契约 ⇒ 语料演化不会假失败。
    """
    hits = 0
    total = 0
    for p in PROTOCOLS:
        for c in candidates[p]:
            total += 1
            if match_pattern(c["text"]) is not None:
                hits += 1
    assert total > 0
    ratio = hits / total
    assert ratio >= 0.079, (
        f"B-5 模式命中率 {ratio:.2%} 低于改前基线 7.9%")


def test_abnf_candidates_are_still_matched_by_b5(candidates):
    """★ **B-5 的 ``abnf_rule`` 依赖不被破坏**：ABNF 候选仍能被命中。

    ★ 若 ABNF 行被并进散文句，`abnf_rule` 的 `^` 锚点失效 ⇒ 这条就红。
    """
    abnf = [p for p in PATTERNS if p.name == "abnf_rule"]
    assert len(abnf) == 1, "B-5 模式表里应恰有一条 abnf_rule"
    found = 0
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = match_pattern(c["text"])
            if m is not None and m.pattern.name == "abnf_rule":
                found += 1
                assert m.target_field, (
                    f"ABNF 候选丢了产生式名：{c['text'][:60]!r}")
    assert found > 0, "没有任何候选命中 abnf_rule"


def test_abnf_line_regex_matches_b5_pattern():
    """★ 抽取器的 ABNF 判据与 B-5 的 ``abnf_rule`` 正则**同形**。

    ★ 两者必须一致，否则「抽取器认为是 ABNF」与「B-5 认为是 ABNF」会分叉
      ⇒ 抽取器把 ABNF 行并进散文句，B-5 却仍想按 ABNF 抽 ⇒ 静默失配。
    """
    from core.fused.semantic_rules import PATTERNS as _P
    b5 = next(p for p in _P if p.name == "abnf_rule")
    assert R._RE_ABNF_RULE.pattern == b5.regex.pattern, (
        "抽取器的 ABNF 判据与 B-5 的 abnf_rule 正则不同形")


def test_toc_contamination_stays_zero(candidates, spec_texts):
    """★ **TOC 污染仍为 0**（用**独立**判据回查来源行）。"""
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            raw = spec_texts[p][m.group("name")]
            line = raw.splitlines()[int(m.group("line")) - 1]
            assert not R._independent_toc_lines([line]), (
                f"{p}: TOC 污染候选：{c['source']}")


def test_section_no_path_and_provenance_are_preserved(candidates):
    """★ **B-4 / B-3 的下游契约不变**：`section_no_path` / `spec_version` /
    `source` 形态在切句粒度改动后**保持原样**。"""
    _re_no = re.compile(r"^\d+(\.\d+)*$")
    for p in PROTOCOLS:
        for c in candidates[p]:
            assert _RE_SOURCE.match(c["source"]), c["source"]
            assert c["spec_version"].startswith("RFC ")
            assert c["section_path"], c["source"]
            assert c["section_no_path"], c["source"]
            for no in c["section_no_path"]:
                assert _re_no.match(no), f"非章节号成分：{no!r}"


def test_extractor_version_was_bumped():
    """★ 抽取结果变了 ⇒ ``_EXTRACTOR_VERSION`` 必须变（否则 build_id 不变，
    「代码已改但产物未重建」会被误判为一致）。"""
    assert R._EXTRACTOR_VERSION != "a1-p1-2026-11-01"
    assert "b13" in R._EXTRACTOR_VERSION
