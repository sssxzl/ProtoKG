# -*- coding: utf-8 -*-
"""tests/fused/test_kind_classifier.py —— 「从内容判定类别」独立通道的护栏。

★ 背景：GraphRAG 改造批次 2 / S1（独立通道）+ S2（E-1 对照实验）。
★ 旧通道 = 章节号配置（``_section_kind``）；新通道 = 内容判据（本模块）。
★ 本文件只测**新通道**；两通道的**对照**由 ``scripts/exp_kind_channel.py`` 做。

★ 关键回归护栏：
  · 新通道**不认协议名**（判据全部来自 RFC 内容）；
  · 新通道**覆盖旧通道的全部 6 类**（这是 S3「清除旧通道」的前置条件）；
  · 章节号配置**保留**（L-D 兜底 + 人工纠正入口）。
"""
from __future__ import annotations

import inspect

import pytest


# ===========================================================================
# ① 通道独立性
# ===========================================================================

def test_classifier_does_not_reference_section_numbers():
    """★ 新通道的**核心判据**不得依赖章节号（否则就退化成旧通道了）。

    ★ 只允许 L-D 兜底里调用旧通道（`_section_kind`）。
    """
    from core.fused import rfc_classifier as RC
    src = inspect.getsource(RC)
    # 主体判据函数里不得出现 section_no / method_sections 等
    for fn_name in ("_classify_by_form", "_classify_by_title",
                    "_classify_by_prose"):
        fn = getattr(RC, fn_name)
        fsrc = inspect.getsource(fn)
        assert "method_sections" not in fsrc, fn_name
        assert "field_sections" not in fsrc, fn_name
        assert "status_sections" not in fsrc, fn_name


def test_classifier_has_no_protocol_names():
    """★ 代码级守卫：新通道**判据里不得出现协议名**（协议无关）。

    ★ 守卫要**剥掉 docstring** —— docstring 里可以举例协议名（说明用法），
      但**代码**里出现协议名就意味着判据被写死了。
    """
    import ast
    from core.fused import rfc_classifier as RC
    src = inspect.getsource(RC)
    tree = ast.parse(src)
    doc_lines: set[int] = set()
    if ast.get_docstring(tree, clean=False):
        doc_lines.update(range(1, tree.body[0].end_lineno + 1))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                doc_lines.update(range(node.body[0].lineno,
                                       node.body[0].end_lineno + 1))
    code = "\n".join(
        ln.split("#", 1)[0] for i, ln in enumerate(src.splitlines(), 1)
        if i not in doc_lines).lower()
    for name in ("rtsp", "sip", "smtp", "dhcp"):
        assert name not in code, f"新通道的判据里出现了协议名 {name}"


def test_classifier_falls_back_to_config():
    """★ L-D 兜底：配置仍被调用（保留人工纠正入口）。"""
    from core.fused import rfc_classifier as RC
    src = inspect.getsource(RC.classify_window)
    assert "_section_kind" in src
    assert "sections_by_file" in src or "src_name" in src


# ===========================================================================
# ② 类别覆盖（S3 的前置条件）
# ===========================================================================

def test_kinds_cover_all_six():
    """★ 新通道覆盖旧通道的**全部 6 类**（否则不能清除旧通道）。"""
    from core.fused.rfc_classifier import KINDS
    assert set(KINDS) == {"method", "field", "status", "transition",
                          "outcome", "required_header"}


def test_coverage_table_reports_classes():
    """★ 覆盖统计能报出实际判出的类别。"""
    from core.fused.rfc_classifier import coverage_table
    windows = [
        {"section_no": "10.1", "title": "OPTIONS", "text": "OPTIONS * RTSP/1.0"},
        {"section_no": "12.1", "title": "CSeq", "text": "CSeq: 1"},
        {"section_no": "21.1", "title": "100 Trying", "text": "100 Trying"},
    ]
    cov = coverage_table(windows)
    assert cov["total"] == 3
    assert cov["counts"]["method"] >= 1
    assert cov["counts"]["field"] >= 1
    assert cov["counts"]["status"] >= 1


# ===========================================================================
# ③ 各层判据
# ===========================================================================

def test_l1_table_with_roles_is_transition():
    """★ L-A：表头有 from/trigger/to ⇒ 迁移表；否则是字段表。"""
    from core.fused.rfc_classifier import _classify_by_form
    tr = {"section_no": "3", "title": "Transitions",
          "text": "From State | Trigger | To State\n"
                  "Init | REQUEST | Ready\n"}
    assert _classify_by_form(tr) == "transition"
    # ★ 表头**不含** from/trigger/to ⇒ 是字段表
    #   （形态层要求**至少 3 列**才认成 table ⇒ 用真实 RFC 表格的列数）
    fld = {"section_no": "4", "title": "Fields",
           "text": "   Code   Len         Address 1               Address 2\n"
                   "   +-----+-----+-----+-----+-----+-----+-----+-----+--\n"
                   "   |  71  |  n  |  a1 |  a2 |  a3 |  a4 |  a1 |  a2 |  ...\n"}
    assert _classify_by_form(fld) == "field"


def test_l2_title_forms():
    """★ L-B：标题形态 ⇒ 类别。"""
    from core.fused.rfc_classifier import _classify_by_title
    assert _classify_by_title({"title": "OPTIONS"}) == "method"
    assert _classify_by_title({"title": "Content-Length"}) == "field"
    assert _classify_by_title({"title": "100 Trying"}) == "status"
    # ★ 多词 + 以 Option 结尾 ⇒ 选项定义章，不是方法
    assert _classify_by_title(
        {"title": "Post Office Protocol (POP3) Server Option"}) == "field"
    # ★ 单个全大写词 OPTIONS **不能**被「Option 结尾」规则误伤
    assert _classify_by_title({"title": "OPTIONS"}) == "method"


def test_l2_option_registry_form_is_field():
    """★ 选项**登记形态**（Code:/Name:/Defined in:）⇒ 字段，不是方法。"""
    from core.fused.rfc_classifier import _classify_by_form
    w = {"section_no": "3.2.3", "title": "URL",
         "text": "   Code:              114\n"
                 "   Name:              URL\n"
                 "   Defined in:        (none)\n"}
    assert _classify_by_form(w) == "field"


def test_l3_prose_forms():
    """★ L-C：正文句式。"""
    from core.fused.rfc_classifier import _classify_by_prose
    assert _classify_by_prose(
        {"text": "The format of the STARTTLS command is:"}) == "method"
    assert _classify_by_prose(
        {"text": "CSeq MUST be included in every request."}) == \
        "required_header"


def test_l4_fallback_uses_config():
    """★ L-D：三层都判不出时，用章节号配置兜底。"""
    from core.fused.rfc_classifier import classify_window
    cfg = {"method_sections": ["4.3"], "field_sections": [],
           "status_sections": [], "transition_sections": [],
           "sections_by_file": {}}
    w = {"section_no": "4.3.1", "title": "Some Prose Heading",
         "text": "   Just some prose with no distinctive shape."}
    assert classify_window(w, cfg, "x.txt") == "method"


# ===========================================================================
# ④ 端到端：两通道的对照结论（护栏）
# ===========================================================================

def test_e1_experiment_script_exists():
    """★ E-1 对照实验脚本在位（批次 2 / S2 的交付物）。"""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "scripts" / "exp_kind_channel.py"
    assert p.is_file(), p


def test_known_methods_cover_dhcp_server_messages():
    """★ 真值集必须包含 DHCP 的**服务器方向**消息（RFC 2131 §3.1 表 2）。

    ★ 踩过的坑：真值集只列了客户端 5 个 ⇒ 把 content 通道正确抽出的
      ``DHCPOFFER``/``DHCPACK``/``DHCPNAK`` 误判成「误抽」。
    """
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "scripts" / "exp_kind_channel.py"
    spec = importlib.util.spec_from_file_location("exp_kind_channel", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    km = mod.KNOWN_METHODS["dhcpv4"]
    for want in ("DHCPOFFER", "DHCPACK", "DHCPNAK"):
        assert want in km, (want, sorted(km))
