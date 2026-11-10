"""tests/test_rfc_extractor_a1.py —— rfc 抽取器 A1 改造的单元测试。

覆盖 A1.1~A1.7 + A0.4/A0.5：
  - TOC 前置隔离（A1.2）
  - 宽松标题识别（A1.3）
  - 章节树 + 有预算合并（A1.4）
  - 缩进字段条目 / 缩进命令条目（A1.5）
  - 语义判定（rfc_config 驱动，A1.3）
  - 跨文件去重（A1.3）
  - 质量闸（A0.4）
  - 幂等键（A0.5）

这些测试用**内联样本**验证函数行为（不依赖 kb/ 真实数据），
另有一组「真实数据回归」用例锁定目标协议（rtsp/sip/smtp）的实测指标。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.fused.extraction import rfc_extractor as rx


# ===========================================================================
# A1.2　TOC 识别与隔离
# ===========================================================================

def test_is_toc_line_detects_dot_leaders():
    assert rx._is_toc_line("   21.1.1     100 Trying ................. 183")
    assert rx._is_toc_line("4.1.  Basic Structure ....................")
    assert rx._is_toc_line("   ..............................")


def test_is_toc_line_keeps_body_lines():
    """正文行（含数字/章节号/状态码）不能被误判为 TOC。"""
    assert not rx._is_toc_line("21.1.1 100 Trying")
    assert not rx._is_toc_line("4.1.  Basic Structure")
    assert not rx._is_toc_line("The value 699921578 (0x29b7f4aa) is stored")
    assert not rx._is_toc_line("   byte")


def test_toc_line_removed_before_section_tree(tmp_path):
    """★ 核心回归：TOC 行不得进入章节树，也不得产生 norm。

    改造前 TOC 版与正文版各抽一次 → SIP 68 个 fact_id 冲突、
    50 个 outcome 来自 TOC 行（知识污染）。
    """
    spec = tmp_path / "fake_spec"
    spec.mkdir()
    (spec / "rfc.txt").write_text(
        "1.  Overview\n"
        "   Some prose.\n"
        "\n"
        "2.  Responses\n"
        "2.1.1 100 Trying\n"
        "   The 100 response is provisional.\n"
        "\n"
        "   Table of Contents:\n"
        "2.1.1     100 Trying ........................  183\n",
        encoding="utf-8")
    cfg = {"method_sections": [], "field_sections": [],
           "status_sections": [], "method_excludes": [], "numeric_bounds": []}
    norms = rx._extract_rfc_file(spec / "rfc.txt", "fake", cfg)
    outcomes = [n for n in norms if n["kind"] == "outcome"]
    assert len(outcomes) == 1, f"TOC 版不应重复产生 outcome: {outcomes}"
    assert outcomes[0]["name"] == "100"
    assert "provisional" in outcomes[0]["content"]


# ===========================================================================
# A1.3　宽松标题识别
# ===========================================================================

@pytest.mark.parametrize("line,number,title", [
    ("4.1.  Basic Structure", "4.1", "Basic Structure"),
    ("10.1 The OPTIONS method", "10.1", "The OPTIONS method"),
    ("3.1.  DATA REPRESENTATION", "3.1", "DATA REPRESENTATION"),
    ("5 General Header Fields", "5", "General Header Fields"),
    ("21.1.1 100 Trying", "21.1.1", "100 Trying"),
    ("12.2.1.1 Example", "12.2.1.1", "Example"),
])
def test_parse_heading_accepts_multiword_titles(line, number, title):
    """★ A1.3 核心：旧正则只认单词标题（实测命中率 15.2%），现须识别多词标题。"""
    h = rx._parse_heading(line, 0)
    assert h is not None, f"未识别为标题: {line!r}"
    assert h.number == number
    assert h.title == title


def test_parse_heading_rejects_data_rows():
    """协议数据图示行（如 SSH 的 `0 00 00 00 00`）不得被当标题。"""
    assert rx._parse_heading("0 00 00 00 00", 0) is None
    assert rx._parse_heading("80 00 00 02 00 80", 0) is None


def test_parse_heading_rejects_toc():
    assert rx._parse_heading("21.1.1     100 Trying ....... 183", 0) is None


def test_normalize_method_name():
    assert rx._normalize_method_name("OPTIONS") == "OPTIONS"
    assert rx._normalize_method_name("MAIL (MAIL)") == "MAIL"
    assert rx._normalize_method_name("Extended HELLO (EHLO)") == "EHLO"
    assert rx._normalize_method_name("The OPTIONS method") == "OPTIONS"
    assert rx._normalize_method_name("Basic Structure") == ""


def test_normalize_field_name():
    assert rx._normalize_field_name("Content-Length") == "Content-Length"
    assert rx._normalize_field_name("CSeq") == "CSeq"
    # SSH/TLS 的小写数据类型形态
    assert rx._normalize_field_name("byte") == "byte"
    assert rx._normalize_field_name("uint32") == "uint32"
    assert rx._normalize_field_name("name-list") == "name-list"
    assert rx._normalize_field_name("Basic Structure") == ""


def test_normalize_command_name():
    """命令条目「全称（缩写）」→ 取括号内的缩写（线上实际传输的命令字）。"""
    assert rx._normalize_command_name("USER NAME (USER)") == "USER"
    assert rx._normalize_command_name("RETRIEVE (RETR)") == "RETR"
    assert rx._normalize_command_name("PASSWORD (PASS)") == "PASS"
    # 多个括号时取最后一个全大写缩写
    assert rx._normalize_command_name("APPEND (with create) (APPE)") == "APPE"


# ===========================================================================
# A1.4　章节树 + 有预算合并
# ===========================================================================

def _build_tree_from_lines(lines: list[str]):
    heads, bodies, cur, pending = [], [], [], None
    for s in lines:
        h = rx._parse_heading(s.strip(), len(heads))
        if h is not None:
            if pending is not None:
                bodies.append(cur)
                cur = []
            pending = h
            heads.append(h)
        else:
            cur.append(s)
    if pending is not None:
        bodies.append(cur)
    return rx._build_section_tree(heads, bodies)


def test_section_tree_parent_child():
    tree = _build_tree_from_lines([
        "1.  Top",
        "   top body",
        "1.1  Sub",
        "   sub body",
        "1.2  Sub2",
        "   sub2 body",
    ])
    assert len(tree) == 1
    root = tree[0]
    assert root.number == "1"
    assert len(root.children) == 2
    assert [c.number for c in root.children] == ["1.1", "1.2"]


def test_body_belongs_to_section_after_heading():
    """★ off-by-one 回归：body 必须是标题**之后**的内容。

    曾经的实现把标题**之前**的累积内容挂给该标题 →
    SSH §5 拿到 §4.5 的正文，字段全丢。
    """
    tree = _build_tree_from_lines([
        "1.  First",
        "   first body",
        "2.  Second",
        "   second body",
    ])
    by_num = {n.number: n for n in tree}
    strip1 = [x.strip() for x in by_num["1"].body_lines]
    strip2 = [x.strip() for x in by_num["2"].body_lines]
    assert "first body" in strip1
    assert "second body" in strip2
    assert "second body" not in strip1


def test_merge_windows_respects_budget():
    """合并窗口必须有预算（评审 F2：上下文膨胀防护）。"""
    tree = _build_tree_from_lines([
        "1.  Top",
        "   " + ("x" * 200),
        "1.1  Sub",
        "   " + ("y" * 200),
    ])
    budget = rx.MergeBudget(max_depth=1, max_chars=300)
    windows = rx._merge_leaf_windows(tree, budget)
    assert windows
    for w in windows:
        assert len(w["text"]) <= budget.max_chars + 3   # 截断标记 "..."


def test_merge_windows_includes_child_text():
    """父节窗口应包含子节正文（SpecGPT 自底向上合并）。"""
    tree = _build_tree_from_lines([
        "1.  Top",
        "   parent body",
        "1.1  Sub",
        "   child body",
    ])
    windows = rx._merge_leaf_windows(tree, rx.MergeBudget())
    top = [w for w in windows if w["section_no"] == "1"][0]
    assert "parent body" in top["text"]
    assert "child body" in top["text"]


# ===========================================================================
# A1.5　缩进条目
# ===========================================================================

def test_extract_indented_entries():
    text = ("   byte\n"
            "\n"
            "      A byte represents an arbitrary 8-bit value.\n"
            "   boolean\n"
            "      A boolean value is stored as a single byte.\n")
    entries = rx._extract_indented_entries(text)
    names = [e[0] for e in entries]
    assert "byte" in names
    assert "boolean" in names
    assert "8-bit value" in dict(entries)["byte"]


def test_extract_command_entries():
    """命令条目：全称（缩写）+ 深缩进正文。"""
    text = ("         USER NAME (USER)\n"
            "\n"
            "            The argument field is a Telnet string.\n"
            "         RETRIEVE (RETR)\n"
            "            The file is retrieved.\n")
    entries = rx._extract_command_entries(text)
    names = [e[0] for e in entries]
    assert "USER NAME (USER)" in names
    assert "RETRIEVE (RETR)" in names


def test_extract_command_entries_skips_section_headings():
    """分组名（章节标题）不是命令。"""
    text = ("      4.1.  ACCESS CONTROL COMMANDS\n"
            "         USER NAME (USER)\n"
            "            The argument field.\n")
    entries = rx._extract_command_entries(text)
    names = [e[0] for e in entries]
    assert "USER NAME (USER)" in names
    assert not any("ACCESS CONTROL" in n for n in names)


# ===========================================================================
# A1.3　语义判定（rfc_config 驱动）
# ===========================================================================

def test_section_kind_uses_rfc_config():
    cfg = {"method_sections": ["10"], "field_sections": ["12"],
           "status_sections": ["11"], "method_excludes": [], "numeric_bounds": []}
    assert rx._section_kind({"section_no": "10.1", "title": "OPTIONS"}, cfg) == "method"
    assert rx._section_kind({"section_no": "12.3", "title": "Accept"}, cfg) == "field"
    assert rx._section_kind({"section_no": "11.1", "title": "200 OK"}, cfg) == "status"
    assert rx._section_kind({"section_no": "3.2", "title": "RTSP URL"}, cfg) is None


def test_section_kind_prefers_longest_prefix():
    cfg = {"method_sections": ["10"], "field_sections": ["10", "12"],
           "status_sections": [], "method_excludes": [], "numeric_bounds": []}
    # "10.1" 同时命中 method_sections["10"] 与 field_sections["10"]，
    #  长度相同时 method 优先（与 _section_kind 实现顺序一致）
    assert rx._section_kind({"section_no": "10.1", "title": "X"}, cfg) == "method"
    # "12.1" 只命中 field
    assert rx._section_kind({"section_no": "12.1", "title": "Accept"}, cfg) == "field"


def test_infer_kind_does_not_treat_uppercase_phrases_as_method():
    """★ 「全大写词组」不是方法特征（评审 T7：语义判定替代形态猜测）。

    实测反例：RTSP `3.2 RTSP URL`、DNS `1. STATUS OF THIS MEMO`。
    """
    assert rx._infer_kind_from_content({"title": "RTSP URL", "level": 2,
                                        "text": "url = ..."}) is None
    assert rx._infer_kind_from_content({"title": "STATUS OF THIS MEMO", "level": 1,
                                        "text": ""}) is None
    # 带全大写缩写的命令仍然识别
    assert rx._infer_kind_from_content({"title": "MAIL (MAIL)", "level": 2,
                                        "text": ""}) == "method"


# ===========================================================================
# A0.4　质量闸
# ===========================================================================

def test_quality_report_passes_for_real_protocol():
    """真实协议必须通过构建质量闸（否则 build 会被阻断）。"""
    for proto in ("sip", "rtsp", "smtp"):
        rep = rx.rfc_quality_report(proto)
        assert rep.passed, f"{proto} 质量闸未通过: {rep.blocking_issues}"
        assert rep.dup_fact_ids == 0
        assert rep.toc_sourced_outcomes == 0


def test_quality_report_detects_dup_fact_ids():
    """质量闸必须能发现重复 fact_id（这是它存在的意义）。"""
    rep = rx.QualityReport(protocol="x")
    rep.dup_fact_ids = 3
    rep.blocking_issues.append("重复 fact_id 3 个")
    assert not rep.passed
    assert "重复 fact_id" in rep.to_dict()["blocking_issues"][0]


def test_quality_report_offline_metrics_skipped_without_truth():
    """无人工真值集时离线评测**跳过**，不是失败（改进v2 问题③）。"""
    rep = rx.rfc_quality_report("sip")
    assert rep.passed
    assert rep.offline_metrics == {}
    assert any("真值集" in w for w in rep.warnings)


def test_offline_metrics_precision_recall():
    truth = {"methods": ["OPTIONS", "PLAY"], "fields": [], "outcomes": []}
    norms = [{"kind": "method", "name": "OPTIONS"},
             {"kind": "method", "name": "EXTRA"}]
    m = rx._offline_metrics(norms, truth)
    assert m["method"]["tp"] == 1
    assert m["method"]["precision"] == 0.5
    assert m["method"]["recall"] == 0.5
    assert m["method"]["f1"] == 0.5
    assert "PLAY" in m["method"]["missing"]
    assert "EXTRA" in m["method"]["extra"]


# ===========================================================================
# A0.5　幂等键
# ===========================================================================

def test_build_id_is_deterministic():
    norms = [{"kind": "method", "name": "OPTIONS"}]
    cfg = {"method_sections": ["10"]}
    a = rx.compute_build_id("rtsp", norms, cfg)
    b = rx.compute_build_id("rtsp", norms, cfg)
    assert a == b
    assert a.startswith("rb_")


def test_build_id_changes_with_config_and_norms():
    norms = [{"kind": "method", "name": "OPTIONS"}]
    base = rx.compute_build_id("rtsp", norms, {"method_sections": ["10"]})
    assert base != rx.compute_build_id("rtsp", norms, {"method_sections": ["11"]})
    assert base != rx.compute_build_id(
        "rtsp", norms + [{"kind": "method", "name": "PLAY"}],
        {"method_sections": ["10"]})
    assert base != rx.compute_build_id("sip", norms, {"method_sections": ["10"]})


# ===========================================================================
# 真实数据回归（锁定目标协议 rtsp/sip/smtp 实测指标）
# ===========================================================================

@pytest.mark.parametrize("proto,min_methods", [
    ("rtsp", 11),      # RTSP §10 的 11 个方法
    ("smtp", 8),       # SMTP 的 8+ 个命令
])
def test_real_protocol_method_counts(proto, min_methods):
    methods = [n["name"] for n in rx.extract_rfc_norms(proto)
               if n["kind"] == "method"]
    assert len(methods) >= min_methods, f"{proto} 方法过少: {methods}"


def test_real_rtsp_methods_exact_set():
    """RTSP §10 的 11 个方法必须齐全，且不含 `EMBEDDED`（§10.12 非方法）。"""
    methods = {n["name"] for n in rx.extract_rfc_norms("rtsp")
               if n["kind"] == "method"}
    assert methods == {
        "OPTIONS", "DESCRIBE", "ANNOUNCE", "SETUP", "PLAY", "PAUSE",
        "TEARDOWN", "GET_PARAMETER", "SET_PARAMETER", "REDIRECT", "RECORD",
    }


def test_real_sip_has_no_dup_fact_ids():
    """★ SIP 是 TOC 污染最严重的协议（改造前 68 个 fact_id 冲突）。"""
    from core.fused.extraction.norm import map_norm_to_facts
    facts = []
    for n in rx.extract_rfc_norms("sip"):
        facts.extend(map_norm_to_facts(n))
    ids = [f.fact_id for f in facts]
    assert len(ids) == len(set(ids)), "SIP 仍有重复 fact_id"


# ssh 已于 2026-10-31 从目标协议范围移除（kb 裁剪），故删除本用例
# （原 test_real_ssh_has_data_type_fields 校验 SSH §5/§6 的 byte/boolean/uint32
#   数据类型字段，ssh 的 kb/spec 已不存在，该断言已无从校验）
