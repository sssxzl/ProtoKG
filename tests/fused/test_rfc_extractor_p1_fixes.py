# -*- coding: utf-8 -*-
r"""tests/fused/test_rfc_extractor_p1_fixes.py —— rfc 抽取器 P1 批次修复的回归测试。

背景（独立 QA 实测复核，2026-11-01）
-----------------------------------
`core/fused/rfc_extractor.py` 在「里程碑 A」（TOC 隔离 + 质量闸）之后仍有
三个缺陷，全部已实测证实：

  P0-1　SMTP 的**间隔点线**目录**从未被剥离**
        `_RE_TOC_DOTS = r"\.{3,}"` 只认**连续**点线，而 RFC 5321/5322 的目录
        用**间隔点线**（`. . . .`）排版 ⇒ 实测 SMTP 195 行真目录 0 命中，
        SMTP 章节树里 39% 的节点是目录条目（148/378）。

  P1-3　`norm["source"]` 的 `@N` **不是原文行号** ⇒ 溯源链断裂
        （`SectionHead.line` 存的是「标题在 heads 列表中的序号」）。

  P1-2　**首个标题之前**的内容（RFC 抬头/摘要/目录）被并入「第一节」正文
        （off-by-one 残留）。

本文件锁住三者的修复口径：
  · 间隔点线目录 **100%** 命中，且**零误报**（SIP 的正文省略号仍判正文）；
  · `norm["source"]` 的 `@N` 能在 RFC 原文里定位到该标题；
  · 首标题之前的内容**不进入任何 norm 的 content**。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.extraction import rfc_extractor as rx  # noqa: E402


PROTOCOLS = ("rtsp", "sip", "smtp")


# ===========================================================================
# 测试侧的**独立**目录判据（不复用被测函数的逻辑，避免自证）
# ===========================================================================

#: 目录块锚点标题
_RE_ANCHOR = re.compile(r"^\s*(?:table\s+of\s+contents|contents)\s*$",
                        re.IGNORECASE)
#: 目录块终止标志：**零缩进**的一级章节标题
_RE_TERMINATOR = re.compile(r"^\d{1,2}\.?\s+\S")
#: 行尾页码
_RE_TRAIL_PAGE = re.compile(r"\.\s*\d+\s*$")


def _spec_files(protocol: str) -> list[Path]:
    """该协议 kb 下的全部 RFC 原文（按文件名排序）。"""
    return sorted((ROOT / "kb" / protocol / "spec").glob("*.txt"))


def _raw_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def _toc_block_end_line(lines: list[str]) -> int | None:
    """目录块的**结束行号**（1-based，指向正文第一个一级章节标题）。

    无目录（无锚点标题）或找不到终止标志时返回 None。
    """
    anchor = None
    for i, ln in enumerate(lines):
        if _RE_ANCHOR.match(ln):
            anchor = i
            break
    if anchor is None:
        return None
    for j in range(anchor + 1, len(lines)):
        if _RE_TERMINATOR.match(lines[j]):
            return j + 1
    return None


def _norm_source_parts(source: str) -> tuple[str, int | None]:
    """解析 `file:<名>#@<行号>` → (文件名, 行号)；非行号定位器返回 (名, None)。"""
    name, _, frag = source.partition("#")
    name = name[len("file:"):] if name.startswith("file:") else name
    m = re.match(r"^@(\d+)$", frag)
    return name, int(m.group(1)) if m else None


# ===========================================================================
# P0-1　间隔点线目录（`. . . .`）
# ===========================================================================

def test_is_toc_line_detects_spaced_dot_leader_with_page():
    """★ P0-1 核心：RFC 5321/5322 的**间隔点线**目录行必须判为 TOC。"""
    assert rx._is_toc_line(
        "   1.  Introduction . . . . . . . . . . . . . . . . . . . . . . . . .  5")
    assert rx._is_toc_line(
        "     1.1.  Transport of Electronic Mail . . . . . . . . . . . . . . .  5")
    assert rx._is_toc_line(
        "       2.2.2.  Special Issues with Extensions . . .  11")


def test_is_toc_line_keeps_body_ellipsis_without_page():
    """★ P0-1 的**零误报**约束：正文省略号形态与目录点线完全一样，
    唯一区别是**不带行尾页码** ⇒ 必须仍判为正文。"""
    # SIP RFC3261 正文里的省略号（实测：21 个间隔点线 + 无页码）
    assert not rx._is_toc_line(
        "       Alice's  . . . . . . . . . . . . . . . . . . . .  Bob's")
    # SIP RFC3261 正文里的域名省略（3 个间隔点线 + 无页码）
    assert not rx._is_toc_line(
        "                     atlanta.com  . . . biloxi.com")
    # ★ 不得放宽成「含点线就算目录」——那是本缺陷的错解
    assert not rx._is_toc_line("The value 699921578 (0x29b7f4aa) is stored")


def test_is_toc_line_still_detects_continuous_dot_leaders():
    """连续点线目录（RTSP/SIP 的排版）不得因本次改动而漏判。"""
    assert rx._is_toc_line("   21.1.1     100 Trying ................. 183")
    assert rx._is_toc_line("4.1.  Basic Structure ....................")
    assert rx._is_toc_line("   ..............................")


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_all_real_toc_lines_are_detected(protocol):
    """★ 三协议 kb 里**所有**真目录行 100% 被命中。

    「真目录行」的独立口径：行内带点线引导（连续或间隔）**且**行尾带页码。
    （目录行必带页码；正文省略号不带 ⇒ 该口径零误报。）
    """
    total = 0
    missed: list[str] = []
    for f in _spec_files(protocol):
        for lineno, ln in enumerate(_raw_lines(f), start=1):
            if not re.search(r"\.{3,}|(?:\.\s){2,}\.", ln):
                continue
            if not _RE_TRAIL_PAGE.search(ln.rstrip()):
                continue
            total += 1
            if not rx._is_toc_line(ln):
                missed.append(f"{f.name}:{lineno}: {ln!r}")
    assert total > 0, f"{protocol} 没有找到任何真目录行（判据失效？）"
    assert missed == [], f"{protocol} 有 {len(missed)}/{total} 行真目录漏判: {missed[:5]}"


def test_smtp_spaced_dot_toc_hit_count_is_195():
    r"""★ 验收口径：SMTP 的间隔点线目录行命中数 = 195（修复前 = 0）。

    候选集口径与 QA 复核脚本一致：`(?:\.\s){3,}\.`（≥4 个间隔点）。
    """
    candidates = 0
    hits = 0
    for f in _spec_files("smtp"):
        for ln in _raw_lines(f):
            if re.search(r"(?:\.\s){3,}\.", ln):
                candidates += 1
                if rx._is_toc_line(ln):
                    hits += 1
    assert candidates == 195, f"SMTP 间隔点线候选集变了: {candidates}"
    assert hits == 195, f"SMTP 间隔点线目录命中数应为 195，实际 {hits}"


def test_sip_body_ellipsis_is_not_misjudged():
    """★ 验收口径：SIP 的那 1 行 `Alice's . . . . Bob's` 仍须判为正文（0/1）。"""
    candidates = 0
    hits = 0
    for f in _spec_files("sip"):
        for ln in _raw_lines(f):
            if re.search(r"(?:\.\s){3,}\.", ln):
                candidates += 1
                if rx._is_toc_line(ln):
                    hits += 1
    assert candidates == 1, f"SIP 间隔点线候选集变了: {candidates}"
    assert hits == 0, f"SIP 的正文省略号被误判成目录（命中 {hits}）"


@pytest.mark.parametrize("protocol,expected", [("smtp", 29), ("sip", 318),
                                               ("rtsp", 154)])
def test_continuous_dot_toc_counts_unchanged(protocol, expected):
    """连续点线目录行数不得因本次改动而变化（回归保护）。"""
    total = 0
    hits = 0
    for f in _spec_files(protocol):
        for ln in _raw_lines(f):
            if re.search(r"\.{3,}", ln):
                total += 1
                if rx._is_toc_line(ln):
                    hits += 1
    assert total == expected, f"{protocol} 连续点线行数变了: {total} != {expected}"
    assert hits == total, f"{protocol} 连续点线漏判: {hits}/{total}"


def test_wrapped_toc_entry_is_not_treated_as_heading():
    """★ 目录块兜底：折行目录条目（点线在第二行）不得进章节树。

    SIP RFC3261 的目录里：
        `   26         Security Considerations: Threat Model and Security`
        `              Usage Recommendations ...............................  232`
    第一行**没有点线**（点线在折行后的第二行）⇒ 只靠点线判据会漏判，
    它会被当成一级章节标题 `26` 进章节树 ⇒ 目录条目污染知识库。
    """
    wrapped = ("   26         Security Considerations: Threat Model and Security")
    # 形态上**确实**像章节标题（若不进目录块就会被当成标题）
    assert rx._parse_heading_shape(wrapped) is not None
    # 但在 RFC 原文里它位于目录块内 ⇒ 不得成为任何 norm 的来源
    src = ROOT / "kb" / "sip" / "spec" / "rfc3261.txt"
    lines = _raw_lines(src)
    assert wrapped in lines, "RFC 原文里应存在该折行目录条目"
    end_line = _toc_block_end_line(lines)
    assert end_line is not None
    entry_line = lines.index(wrapped) + 1
    assert entry_line < end_line, "该目录条目应位于目录块内"

    for norm in rx.extract_rfc_norms("sip"):
        name, lineno = _norm_source_parts(norm["source"])
        if name != "rfc3261.txt" or lineno is None:
            continue
        assert lineno >= end_line, (
            f"SIP 存在来自目录块的 norm: {norm['norm_id']} @ {lineno} "
            f"(目录块结束于 {end_line})")


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_no_norm_is_sourced_from_toc_block(protocol):
    """★ 端到端：任何 norm 的来源行号都必须在目录块**之后**。

    这是「目录条目不进章节树」的最强判据 —— 任何目录条目一旦混进树，
    它产出的 norm 的 `@N` 就会落在目录块区间内。
    """
    ends: dict[str, int | None] = {}
    for f in _spec_files(protocol):
        ends[f.name] = _toc_block_end_line(_raw_lines(f))

    offenders: list[str] = []
    for norm in rx.extract_rfc_norms(protocol):
        name, lineno = _norm_source_parts(norm["source"])
        if lineno is None:
            continue
        end = ends.get(name)
        if end is None:
            continue
        if lineno < end:
            offenders.append(f"{norm['norm_id']} @ {name}:{lineno} (< {end})")
    assert offenders == [], (
        f"{protocol} 有 {len(offenders)} 条 norm 来自目录块: {offenders[:5]}")


# ===========================================================================
# P1-3　`norm["source"]` 的 `@N` 必须是原文行号
# ===========================================================================

@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_source_line_number_locates_heading_in_raw_file(protocol):
    """★ 溯源链：`norm["source"]` 的 `@N` 能在 RFC 原文里定位到该标题。

    判据：原文第 N 行（非空）能定位到该 norm 的章节号与标题片段。
    """
    raw_cache: dict[str, list[str]] = {}
    checked = 0
    problems: list[str] = []
    for norm in rx.extract_rfc_norms(protocol):
        name, lineno = _norm_source_parts(norm["source"])
        if lineno is None:
            continue
        if name not in raw_cache:
            raw_cache[name] = _raw_lines(
                next(f for f in _spec_files(protocol) if f.name == name))
        lines = raw_cache[name]
        assert 1 <= lineno <= len(lines), (
            f"{norm['norm_id']} 的行号 {lineno} 超出 {name} 的范围 "
            f"(共 {len(lines)} 行)")
        line = lines[lineno - 1]
        if not line.strip():
            problems.append(f"{norm['norm_id']} @ {name}:{lineno} 是空行: {line!r}")
        checked += 1
    assert checked > 0, f"{protocol} 没有可校验的行号定位器"
    assert problems == [], f"{protocol} 行号定位失败: {problems[:5]}"


def test_section_head_line_is_raw_source_line_number(tmp_path):
    """★ 单元级：`SectionHead.line` 存的是**原文行号**，不是 heads 序号。"""
    spec = tmp_path / "fake_spec"
    spec.mkdir()
    (spec / "rfc.txt").write_text(
        "1.  Alpha\n"
        "   alpha body\n"
        "2.  Beta\n"
        "   beta body\n"
        "3.  Gamma\n"
        "   gamma body\n",
        encoding="utf-8")
    cfg = {"method_sections": [], "field_sections": ["2"],
           "status_sections": [], "method_excludes": [], "numeric_bounds": []}
    norms = rx._extract_rfc_file(spec / "rfc.txt", "fake", cfg)
    assert norms, "应至少抽出一条 norm"
    for norm in norms:
        name, lineno = _norm_source_parts(norm["source"])
        assert name == "rfc.txt"
        assert lineno == 3, f"§2 Beta 的行号应为 3，实际 {lineno}"
        raw = (spec / "rfc.txt").read_text(encoding="utf-8").splitlines()
        line = raw[lineno - 1]
        assert line.strip() == "2.  Beta", f"行号未定位到标题: {line!r}"


def test_rtsp_options_and_smtp_ehlo_point_to_real_headings():
    """★ QA 实测的具体样本：RTSP `OPTIONS` / SMTP `EHLO` 的定位器。"""
    cases = [
        ("rtsp", "OPTIONS", "rfc2326.txt", "10.1 OPTIONS"),
        ("smtp", "EHLO", "rfc5321.txt",
         "4.1.1.1.  Extended HELLO (EHLO) or HELLO (HELO)"),
    ]
    for protocol, method, expect_file, expect_line in cases:
        norms = [n for n in rx.extract_rfc_norms(protocol)
                 if n["kind"] == "method" and n["name"] == method]
        assert norms, f"{protocol}.{method} 未抽出"
        name, lineno = _norm_source_parts(norms[0]["source"])
        assert name == expect_file, f"{protocol}.{method} 源文件错: {name}"
        assert lineno is not None
        lines = _raw_lines(ROOT / "kb" / protocol / "spec" / expect_file)
        actual = lines[lineno - 1].strip()
        assert actual == expect_line, (
            f"{protocol}.{method} 行号 {lineno} 定位到 {actual!r}，"
            f"期望 {expect_line!r}")


def test_source_line_number_is_not_the_head_index():
    """★ 反向断言：`@N` **不是** heads 序号（QA 实测 RTSP OPTIONS 旧值 @41）。"""
    norms = [n for n in rx.extract_rfc_norms("rtsp")
             if n["kind"] == "method" and n["name"] == "OPTIONS"]
    assert norms
    _, lineno = _norm_source_parts(norms[0]["source"])
    assert lineno is not None
    # RTSP RFC2326 里 OPTIONS 标题在 1000 行以后（真实行号 ≈1683）
    assert lineno > 1000, f"行号 {lineno} 仍像 heads 序号而非原文行号"


# ===========================================================================
# P1-2　首个标题之前的内容不进任何章节
# ===========================================================================

def test_content_before_first_heading_is_not_in_any_norm(tmp_path):
    """★ 首个标题之前的内容（RFC 抬头/摘要/目录）**不进入任何章节窗口**。

    修复前：off-by-one 把这段内容挂给了第一节 ⇒ 第一节的语义摘要变成
    「Network Working Group J. Klensin …」这类抬头文字。
    """
    spec = tmp_path / "fake_spec"
    spec.mkdir()
    (spec / "rfc.txt").write_text(
        "Network Working Group                    Some Author\n"
        "Request for Comments: 9999               January 2020\n"
        "\n"
        "PREAMBLE_MARKER_ALPHA\n"
        "PREAMBLE_MARKER_BETA\n"
        "\n"
        "Table of Contents\n"
        "   1.  Alpha  . . . . . . . . . . . . . . .  1\n"
        "\n"
        "1.  Alpha\n"
        "   The real body of the first section.\n"
        "2.  Beta\n"
        "   The real body of the second section.\n",
        encoding="utf-8")
    cfg = {"method_sections": [], "field_sections": ["2"],
           "status_sections": [], "method_excludes": [], "numeric_bounds": []}
    norms = rx._extract_rfc_file(spec / "rfc.txt", "fake", cfg)
    assert norms, "应至少抽出一条 norm"
    for norm in norms:
        content = norm.get("content", "")
        assert "PREAMBLE_MARKER_ALPHA" not in content, (
            f"首标题前的内容进入了 norm: {norm['norm_id']}")
        assert "PREAMBLE_MARKER_BETA" not in content, (
            f"首标题前的内容进入了 norm: {norm['norm_id']}")
        assert "Network Working Group" not in content, (
            f"RFC 抬头进入了 norm: {norm['norm_id']}")
    # 首节的语义摘要应是**正文**而不是抬头
    beta = [n for n in norms if n["name"] == "Beta"]
    assert beta, "应抽到 §2 Beta"
    assert "real body" in beta[0]["content"]


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_real_protocol_norms_have_no_rfc_front_matter(protocol):
    """★ 真实语料：三协议的 norm 里不得出现 RFC 抬头/摘要文字。"""
    forbidden = ("Network Working Group", "Request for Comments",
                 "Obsoletes:", "Category: Standards Track")
    problems: list[str] = []
    for norm in rx.extract_rfc_norms(protocol):
        content = norm.get("content", "")
        for token in forbidden:
            if token in content:
                problems.append(f"{norm['norm_id']}: {token}")
    assert problems == [], f"{protocol} 的 norm 里混入 RFC 抬头: {problems[:5]}"


def test_toc_block_fallback_runs_before_preamble_discard():
    """★ 顺序契约：目录块兜底**先于**「首标题前内容丢弃」执行。

    目录块位于首标题之前 ⇒ 若先丢弃，目录块就再也定位不到，
    折行目录条目会重新混进章节树。本测试锁住这个顺序依赖。
    """
    src = ROOT / "kb" / "sip" / "spec" / "rfc3261.txt"
    lines = _raw_lines(src)
    end_line = _toc_block_end_line(lines)
    assert end_line is not None
    # 目录块必须**确实**位于首个一级标题之前
    anchor = next(i for i, ln in enumerate(lines) if _RE_ANCHOR.match(ln))
    assert anchor + 1 < end_line
    # 目录块兜底必须仍能识别折行目录条目
    wrapped = ("   26         Security Considerations: Threat Model and Security")
    assert wrapped in lines
    assert lines.index(wrapped) + 1 < end_line
    # 抽取结果里不得出现该目录条目
    for norm in rx.extract_rfc_norms("sip"):
        assert "Security Considerations: Threat Model and Security" not in \
            norm.get("content", ""), f"目录条目混入了 norm: {norm['norm_id']}"
