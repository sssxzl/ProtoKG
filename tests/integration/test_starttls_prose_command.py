# -*- coding: utf-8 -*-
"""tests/fused/test_starttls_prose_command.py —— 形态 E：散文里的「命令格式声明」。

★ 背景（2026-11-07 实测缺口）
  RFC 3207 用**散文**声明 STARTTLS 的命令格式：

      4. The STARTTLS Command

         The format for the STARTTLS command is:

         STARTTLS

  它**既没有** ABNF 规则（形态 D 不命中），也不是 "描述名 (缩写)" 形态
  （形态 A′ 不命中），也不是章节标题形态（形态 A 不命中）⇒ 前四种形态全不命中
  ⇒ smtp 的方法集漏掉 STARTTLS，只能靠 profile 骨架"补" —— 在「RFC 单源」
  口径下这就是污染（与 2026-11-06 修 AUTH 时同一类缺陷）。

★ 本文件锁住形态 E 的四条性质：
  ① **判据是句式**（协议无关）：换协议 / 换命令名一律照样命中；
  ② **不臆造**：抽出的名字逐字来自原文，且必须全大写；
  ③ **不误伤**：普通散文（"the format of the local part"）不得被当成命令；
  ④ **只多一个**：rtsp / sip 的方法集逐条不变，smtp 只多出 STARTTLS。
"""
from __future__ import annotations

import re

import pytest

from core.fused.extraction import rfc_extractor as RX


def _has_spec(protocol: str) -> bool:
    from core import paths
    return paths.kb_source_dir(protocol, "rfc").is_dir()


def _fake_kb(tmp_path, monkeypatch, text: str):
    """把 `kb_source_dir` 指到临时目录（放一份合成 RFC 文本）。"""
    d = tmp_path / "spec"
    d.mkdir(exist_ok=True)
    (d / "rfc.txt").write_text(text, encoding="utf-8")
    monkeypatch.setattr(RX.paths, "kb_source_dir", lambda _p, _s: d)
    return d


def _fake_cfg(monkeypatch, sections=("2",)):
    """给假协议一份最小 rfc_config（避免"缺配置"告警，且给章节号）。"""
    monkeypatch.setattr(
        RX, "_load_rfc_config",
        lambda _p: {"method_sections": list(sections), "method_excludes": []},
    )


# ===========================================================================
# ① 判据是「句式」，协议无关（**核心证据**）
# ===========================================================================

#: 一份**假协议**的 RFC 文本：命令名/协议名/章节号都与 smtp 完全不同，
#: 只有**句式**与 RFC 3207 相同 ⇒ 若判据写死了 "STARTTLS"/"smtp" 必然抽不到。
_FAKE_RFC = """1. Introduction

   Some introductory text about the ZQRP protocol.

2. The ZQRP Command

   The format for the ZQRP command is:

   ZQRP

   with no parameters.
"""


def test_prose_form_is_protocol_agnostic(tmp_path, monkeypatch):
    """★ 假协议 + 假命令名 ⇒ 照样命中 ⇒ 判据认的是**句式**不是具体名字。"""
    _fake_kb(tmp_path, monkeypatch, _FAKE_RFC)
    _fake_cfg(monkeypatch)
    ms = RX._rfc_source_methods("fake", {"method_sections": ["2"]})
    assert "ZQRP" in ms, f"句式判据未命中，实得 {sorted(ms)}"


def test_prose_form_norms_side_also_protocol_agnostic(tmp_path, monkeypatch):
    """★ 同一句式在 **norms 侧**（fact 抽取通道）同样命中 ⇒ 两个消费者口径一致。"""
    _fake_kb(tmp_path, monkeypatch, _FAKE_RFC)
    _fake_cfg(monkeypatch)
    names = {n["name"] for n in RX.extract_rfc_norms("fake")
             if n["kind"] == "method"}
    assert "ZQRP" in names, f"norms 侧未命中，实得 {sorted(names)}"


def test_prose_form_command_name_variants_all_match(tmp_path, monkeypatch):
    """★ 命令名换成别的全大写词（VERB / X-CMD / A1）⇒ 一律命中。"""
    _fake_cfg(monkeypatch)
    for cmd in ("VERB", "X-CMD", "A1"):
        text = (f"2. The {cmd} Command\n\n"
                f"   The format for the {cmd} command is:\n\n"
                f"   {cmd}\n")
        _fake_kb(tmp_path, monkeypatch, text)
        ms = RX._rfc_source_methods("fake", {"method_sections": ["2"]})
        assert cmd in ms, f"{cmd} 未命中，实得 {sorted(ms)}"


# ===========================================================================
# ② 不臆造：名字逐字来自原文
# ===========================================================================

def test_prose_form_requires_uppercase_token(tmp_path, monkeypatch):
    """★ 小写词**不得**被当成命令名（RFC 里命令名一律大写）。"""
    text = ("2. The widget command\n\n"
            "   The format for the widget command is:\n\n"
            "   widget\n")
    _fake_kb(tmp_path, monkeypatch, text)
    ms = RX._rfc_source_methods("fake", {"method_sections": ["2"]})
    assert "widget" not in ms and "WIDGET" not in ms, (
        f"小写词被当成命令，实得 {sorted(ms)}")


def test_prose_form_never_invents_names(tmp_path, monkeypatch):
    """★ 抽出的每个名字都必须**逐字出现在原文里**（不臆造）。"""
    _fake_kb(tmp_path, monkeypatch, _FAKE_RFC)
    text = (tmp_path / "spec" / "rfc.txt").read_text(encoding="utf-8")
    for name in RX._rfc_source_methods("zqrp", {"method_sections": ["2"]}):
        assert name in text, f"{name} 不在原文里 ⇒ 臆造"


def test_prose_form_excludes_protocol_own_name(tmp_path, monkeypatch):
    """★ 「the <协议名> command is」里的协议名**不是**命令 ⇒ 排除。"""
    text = ("2. The HELLO Command\n\n"
            "   The format for the HELLO command is:\n\n"
            "   HELLO\n")
    _fake_kb(tmp_path, monkeypatch, text)
    ms = RX._rfc_source_methods("hello", {"method_sections": ["2"]})
    assert "HELLO" not in ms, f"协议自身名被当成命令，实得 {sorted(ms)}"


# ===========================================================================
# ③ 不误伤：普通散文不得被当成命令声明
# ===========================================================================

@pytest.mark.parametrize("sentence", [
    "   The format of the local part is not specified.",     # 无 "command"
    "   The format for the mailbox is undefined.",           # 词形非全大写
    "   The syntax of the argument clauses of the above commands (using the",
    "   The format of the RFC is defined elsewhere.",        # 关键字原子
])
def test_prose_form_ignores_ordinary_prose(tmp_path, monkeypatch, sentence):
    """★ 普通散文句**不得**产出方法名。"""
    text = f"2. Some Section\n\n{sentence}\n"
    _fake_kb(tmp_path, monkeypatch, text)
    ms = RX._rfc_source_methods("fake", {"method_sections": ["2"]})
    assert not ms, f"普通散文被当成命令声明，实得 {sorted(ms)}"


def test_prose_form_ignores_toc_lines(tmp_path, monkeypatch):
    """★ 目录行里的同样句式**不得**产出方法名（目录不是规范证据）。"""
    text = ("Table of Contents\n\n"
            "   2. The ZQRP Command ................. 2\n\n"
            "2. The ZQRP Command\n\n"
            "   The format for the ZQRP command is:\n\n"
            "   ZQRP\n")
    _fake_kb(tmp_path, monkeypatch, text)
    ms = RX._rfc_source_methods("fake", {"method_sections": ["2"]})
    # 只允许正文那一次命中（去重后 1 个），且不能出现多个变体
    assert len(ms) == 1, f"目录行污染了方法集，实得 {sorted(ms)}"


# ===========================================================================
# ④ 真实语料：只有 smtp 多出 STARTTLS
# ===========================================================================

def test_real_smtp_gains_starttls():
    """★ 真实语料：smtp 的方法集**多出** STARTTLS（RFC 3207 §4）。"""
    if not _has_spec("smtp"):
        pytest.skip("无 smtp RFC 底料")
    ms = RX._rfc_source_methods("smtp", RX._load_rfc_config("smtp"))
    assert "STARTTLS" in ms, f"STARTTLS 缺失，实得 {sorted(ms)}"


def test_real_smtp_starttls_is_rfc_fact_not_skeleton():
    """★ STARTTLS 必须是 **RFC 源**的方法（authority=rfc），不是骨架补丁。"""
    if not _has_spec("smtp"):
        pytest.skip("无 smtp RFC 底料")
    norms = [n for n in RX.extract_rfc_norms("smtp")
             if n["kind"] == "method" and n["name"] == "STARTTLS"]
    assert norms, "smtp 的 RFC 源里没有 STARTTLS 方法"
    for n in norms:
        assert n["kb_source_type"] == "rfc"
        assert n["source"].startswith("file:rfc3207.txt#@"), (
            f"溯源应指向 RFC 3207 的真实行号，实得 {n['source']}")


def test_real_rtsp_and_sip_unchanged():
    """★ rtsp / sip 的方法集**逐条不变**（形态 E 不得误伤其它协议）。"""
    if not _has_spec("rtsp"):
        pytest.skip("无 rtsp RFC 底料")
    rtsp = RX._rfc_source_methods("rtsp", RX._load_rfc_config("rtsp"))
    assert rtsp == {"ANNOUNCE", "DESCRIBE", "GET_PARAMETER", "OPTIONS", "PAUSE",
                    "PLAY", "RECORD", "REDIRECT", "SETUP", "SET_PARAMETER",
                    "TEARDOWN"}, f"rtsp 方法集漂移：{sorted(rtsp)}"
    if not _has_spec("sip"):
        pytest.skip("无 sip RFC 底料")
    sip = RX._rfc_source_methods("sip", RX._load_rfc_config("sip"))
    assert sip == {"ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"}, (
        f"sip 方法集漂移：{sorted(sip)}")


def test_real_two_consumers_agree():
    """★ 两个消费者（方法集 / norms）口径**必须一致**（质量闸与 facts 互相矛盾）。"""
    for p in ("rtsp", "sip", "smtp"):
        if not _has_spec(p):
            continue
        ms = RX._rfc_source_methods(p, RX._load_rfc_config(p))
        nm = {n["name"] for n in RX.extract_rfc_norms(p) if n["kind"] == "method"}
        assert ms == nm, f"[{p}] 两处不一致：{sorted(ms)} vs {sorted(nm)}"


def test_real_quality_gate_still_passes():
    """★ 质量闸仍通过（无重复 fact_id / 无 TOC 污染）。"""
    for p in ("rtsp", "sip", "smtp"):
        if not _has_spec(p):
            continue
        rep = RX.rfc_quality_report(p)
        assert rep.passed, f"[{p}] 质量闸未通过：{rep.blocking_issues}"
        assert rep.dup_fact_ids == 0, f"[{p}] 出现重复 fact_id"
        assert not rep.toc_sourced_by_line, f"[{p}] TOC 溯源行污染"


# ===========================================================================
# ⑤ 协议无关性守卫（G2）：判据里不得写死协议名/命令名
# ===========================================================================

def test_criterion_has_no_protocol_or_command_hardcode():
    """★ G2：判据（正则 + 抽取函数）源码里不得出现任何协议名/命令名。

    ⇒ 证明「协议无关」不是靠注释承诺，而是**代码层面**可验证的事实。
    """
    import inspect
    src = inspect.getsource(RX._extract_prose_command_formats)
    pat = RX._RE_PROSE_COMMAND_FORMAT.pattern
    # 去掉注释与 docstring 里的说明性文字后再查（说明文字允许提协议名）
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    code_only = re.sub(r"#.*", "", code_only)
    for bad in ("STARTTLS", "AUTH", "MAIL", "RCPT", "DATA", "EHLO", "VRFY",
                "rtsp", "sip", "smtp", "zqrp"):
        assert not re.search(rf"\b{re.escape(bad)}\b", code_only), (
            f"判据代码里出现了协议/命令特例「{bad}」⇒ 违反协议无关")
        assert not re.search(rf"\b{re.escape(bad)}\b", pat), (
            f"判据正则里出现了协议/命令特例「{bad}」⇒ 违反协议无关")


def test_criterion_is_shared_by_both_consumers():
    """★ 两个消费者**共用**同一个抽取函数 ⇒ 口径不可能漂移。"""
    import inspect
    src_m = inspect.getsource(RX._rfc_source_methods)
    src_n = inspect.getsource(RX._extract_rfc_file)
    for src in (src_m, src_n):
        assert "_extract_prose_command_formats(" in src, (
            "某个消费者没有走形态 E 的共享抽取函数")
