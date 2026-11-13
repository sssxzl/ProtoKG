# -*- coding: utf-8 -*-
"""tests/test_rfc_extractor_abnf.py —— SIP 的 ABNF 方法枚举抽取（L1/L2/L3）。

背景
----
SIP RFC 3261 的方法**不是章节标题**，而是 §25 ABNF 里的 hex 伴生规则：
    INVITEm   =  %x49.4E.56.49.54.45 ; INVITE in caps
    ACKm      =  %x41.43.4B ; ACK in caps
    Method    =  INVITEm / ACKm / OPTIONSm / BYEm / CANCELm / REGISTERm
                / extension-method
    extension-method  =  token

改造前 SIP 只抽到 1 个 method（`OK`，一个状态码 reason phrase 被误抽），
6 个真实方法一个都没抽到 —— SIP 的方法知识近乎为零。

本文件锁住三个修复（对应 `core/fused/rfc_extractor.py`）：
  L1 —— ABNF hex 伴生规则抽取（hex 反解 + 注释 + 规则名三者交叉验证）
  L2 —— 英语停用词过滤（become/not/or 等正文虚词被缩进条目识别误抽为 field）
  L3 —— method 名不再重复当 field（SMTP 的 MAIL/RCPT/DATA 等）
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.extraction import rfc_extractor as rx  # noqa: E402


# ===========================================================================
# L1：SIP ABNF 方法枚举抽取
# ===========================================================================

SIP_METHODS = {"INVITE", "ACK", "OPTIONS", "BYE", "CANCEL", "REGISTER"}


def test_sip_methods_extracted_from_abnf():
    """SIP 的 6 个 ABNF 方法必须全部抽到。"""
    methods = {n["name"] for n in rx.extract_rfc_norms("sip")
               if n["kind"] == "method"}
    assert SIP_METHODS <= methods, f"SIP 方法缺失: {SIP_METHODS - methods}"


def test_sip_method_ok_not_misclassified():
    """`OK` 是 200 状态码的 reason phrase，不是方法，不得抽为 method。"""
    methods = {n["name"] for n in rx.extract_rfc_norms("sip")
               if n["kind"] == "method"}
    assert "OK" not in methods


def test_abnf_rule_names_not_methods():
    """`extension-method` / `token` 是 ABNF 规则名，不是方法。"""
    methods = {n["name"] for n in rx.extract_rfc_norms("sip")
               if n["kind"] == "method"}
    assert "extension-method" not in methods
    assert "token" not in methods
    assert "extension" not in methods


def test_extract_abnf_methods_cross_validation():
    """hex 伴生规则三处来源（规则名/hex 反解/注释）一致才采信。"""
    sample = (
        "INVITEm           =  %x49.4E.56.49.54.45 ; INVITE in caps\n"
        "ACKm              =  %x41.43.4B ; ACK in caps\n"
    )
    assert rx._extract_abnf_methods(sample) == ["INVITE", "ACK"]


def test_extract_abnf_methods_rejects_mismatch():
    """hex 反解与注释不一致时不得采信（防御畸形输入）。"""
    # 注释写 INVITE，但 hex 反解出来是 OTHER → 三者不一致 → 拒绝
    sample = "INVITEm = %x4F.54.48.45.52 ; INVITE in caps\n"
    assert rx._extract_abnf_methods(sample) == []


def test_abnf_method_has_no_m_suffix():
    """ABNF 终结符 `m` 后缀不得残留（INVITEm → INVITE，不是 INVITEm）。"""
    methods = {n["name"] for n in rx.extract_rfc_norms("sip")
               if n["kind"] == "method"}
    assert not any(name.endswith("m") for name in methods)


# ===========================================================================
# L2：垃圾 field 过滤（停用词）
# ===========================================================================

def test_sip_no_stopword_fields():
    """become/not/or 等英语虚词不得被抽为 field。"""
    fields = {n["name"] for n in rx.extract_rfc_norms("sip")
              if n["kind"] == "field"}
    assert not {"become", "not", "or"} & fields


def test_sip_real_header_fields_preserved():
    """From/To/Via 是 SIP 强制头字段，停用词过滤不得误删它们。"""
    fields = {n["name"] for n in rx.extract_rfc_norms("sip")
              if n["kind"] == "field"}
    assert {"From", "To", "Via", "Contact", "CSeq"} <= fields


# ===========================================================================
# L3：method 名不再重复当 field
# ===========================================================================

def test_smtp_methods_not_duplicated_as_fields():
    """SMTP 命令（MAIL/RCPT/DATA 等）抽为 method 后不得再当 field。"""
    norms = rx.extract_rfc_norms("smtp")
    methods = {n["name"] for n in norms if n["kind"] == "method"}
    fields = {n["name"] for n in norms if n["kind"] == "field"}
    assert not (methods & fields), \
        f"method/field 重复: {methods & fields}"


def test_smtp_methods_complete():
    """SMTP 的命令完整：10 个 RFC 5321 命令 + **AUTH**（RFC 4954 §8）
    + **STARTTLS**（RFC 3207 §4）。

    ★ 2026-11-06：AUTH 由「ABNF 命令规则字面量」通道补出
      （``auth-command = "AUTH" SP sasl-mech [SP initial-response]``）。
      修复前它只能靠 profile 骨架"补"，在 RFC 单源口径下就是污染。
    ★ 2026-11-07：STARTTLS 由**形态 E**（散文命令格式声明）补出 ——
      RFC 3207 **没有** ABNF 规则，正文只写散文
      "The format for the STARTTLS command is: / STARTTLS"
      ⇒ 前四种形态全不命中 ⇒ 需「散文命令格式」通道（本次新增）。
      补出后 STARTTLS 是 **RFC 事实**（authority=rfc），不再是骨架补丁。
    """
    methods = {n["name"] for n in rx.extract_rfc_norms("smtp")
               if n["kind"] == "method"}
    assert methods == {"DATA", "EHLO", "EXPN", "HELP", "MAIL",
                       "NOOP", "QUIT", "RCPT", "RSET", "VRFY",
                       "AUTH", "STARTTLS"}


# ===========================================================================
# 无回归：RTSP 完全不变
# ===========================================================================

def test_rtsp_methods_unchanged():
    """RTSP 的 11 个方法不受 ABNF 通道影响。"""
    methods = {n["name"] for n in rx.extract_rfc_norms("rtsp")
               if n["kind"] == "method"}
    assert methods == {"OPTIONS", "DESCRIBE", "ANNOUNCE", "SETUP", "PLAY",
                       "PAUSE", "TEARDOWN", "GET_PARAMETER", "SET_PARAMETER",
                       "REDIRECT", "RECORD"}


def test_quality_gate_still_passes():
    """三协议质量闸仍通过（dup_fact_ids=0、无 TOC 污染）。"""
    for p in ("sip", "rtsp", "smtp"):
        r = rx.rfc_quality_report(p)
        assert r.passed, f"{p} 质量闸未通过: {r.blocking_issues}"
        assert r.dup_fact_ids == 0
