# -*- coding: utf-8 -*-
"""★ N2-B0-R：★ **反证边界回归测试**（★ V1 保守反证判据）。

★ 覆盖 §六 八个场景：
  ① MUST 与 SHOULD 同段但约束不同动作
  ② MUST 与 SHOULD 同句但约束不同主体
  ③ 同一命题存在不同强度表述
  ④ 同一命题出现明确肯定与否定冲突
  ⑤ 不同条件下的义务不得误判为矛盾
  ⑥ 跨句代词或条件未解析时保持 uncertain
  ⑦ 缺少强度字段时不得凭推测确认
  ⑧ 无明确反证的词形不匹配不得直接 rejected
★ ★ 测试验证**完整字段语义与证据定位**，★ 而非仅字符串命中。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/_fixtures/n1c"))
from n2b0_tristate_v1 import (CONTRADICTED, SUPPORTED, UNCERTAIN,
                              semantic_support_tristate_v1, _clauses,
                              _neg_adjacent_to_action)


def _v1(quote, action="", obj="", strength="", subject="", constraint="",
        lines=None, anchor=None):
    return semantic_support_tristate_v1(
        quote=quote, action=action, object_=obj, strength=strength,
        subject=subject, constraint=constraint, lines=lines, anchor=anchor)


# ══ ① MUST 与 SHOULD 同段但约束不同动作 ══
def test_same_paragraph_different_action_not_contradiction():
    """★ 同段出现 MUST 与 SHOULD，★ 但约束不同动作 ⇒ ★ **不是矛盾**。"""
    _q = ("A request SHOULD only contain a single parameter to allow the client. "
          "If several parameters are present, the server MUST only act on the "
          "request if all of the parameters can be set successfully.")
    _v, _r, _d = _v1(_q, action="contain", obj="a single parameter",
                      strength="SHOULD")
    assert _v != CONTRADICTED
    assert _v in (SUPPORTED, UNCERTAIN)


# ══ ② MUST 与 SHOULD 同句但约束不同主体 ══
def test_same_sentence_different_subject_not_contradiction():
    """★ 同句出现 MUST 与 SHOULD，★ 但主体不同 ⇒ ★ **不是矛盾**。"""
    _q = ("Clients SHOULD NOT provide SEND as services.  Servers MUST use the "
          "implementation model specified in RFC 821.")
    _v, _r, _d = _v1(_q, action="provide", obj="SEND as services",
                      strength="SHOULD", subject="Clients")
    assert _v != CONTRADICTED


# ══ ③ 同一命题存在不同强度表述 ══
def test_same_proposition_different_strength_is_uncertain():
    """★ 同一命题上 MUST 与 SHOULD 并存 ⇒ ★ **强度不一致 ≠ 矛盾** ⇒ uncertain。"""
    _q = "The server MUST include a list of extensions."
    _v, _r, _d = _v1(_q, action="include", obj="list of extensions",
                      strength="SHOULD")
    assert _v != CONTRADICTED
    assert _v == UNCERTAIN


# ══ ④ 同一命题出现明确肯定与否定冲突 ══
def test_same_proposition_explicit_polarity_conflict_is_contradicted():
    """★ ★ 同一命题（主体+动作+对象对应）上出现**极性相反** ⇒ contradicted。"""
    _q = "The server must not include a list of extensions."
    _v, _r, _d = _v1(_q, action="include", obj="list of extensions",
                      strength="MUST")
    assert _v == CONTRADICTED
    assert _d["★ 反证句"]
    assert _d["★ 反证行"] is not None or _d["★ 证据跨度"]


# ══ ⑤ 不同条件下的义务不得误判为矛盾 ══
def test_different_conditions_not_contradiction():
    """★ 条件从句中的 not 修饰**别的谓词** ⇒ ★ 不构成反证。"""
    _q = ("If a DHCP server that is not configured to support BOOTP clients "
          "receives a BOOTREQUEST message, that server silently discards the "
          "BOOTREQUEST message.")
    _v, _r, _d = _v1(_q, action="discards", obj="BOOTREQUEST message",
                      strength="MUST")
    assert _v != CONTRADICTED


def test_negation_must_be_adjacent_to_action():
    """★ ★ 「not configured」与候选动作「discards」词距 > 2 ⇒ 非反证。"""
    assert _neg_adjacent_to_action(
        "is not configured to support BOOTP clients receives a BOOTREQUEST "
        "message from a BOOTP client", "discards") is False
    assert _neg_adjacent_to_action(
        "must not include a list of extensions", "include") is True


# ══ ⑥ 跨句代词或条件未解析时保持 uncertain ══
def test_cross_sentence_pronoun_keeps_uncertain():
    """★ 对象是代词、★ 跨句未解析 ⇒ uncertain。"""
    _q = ("Clients SHOULD NOT provide SEND, SAML, or SOML as services.  "
          "Servers MAY implement them.")
    _v, _r, _d = _v1(_q, action="implement", obj="them (SEND, SAML, SOML)",
                      strength="MAY", subject="Servers")
    assert _v == UNCERTAIN


# ══ ⑦ 缺少强度字段时不得凭推测确认 ══
def test_missing_strength_not_upgraded():
    """★ ★ strength 缺省 ⇒ ★ **不因其他字段命中而升级为 confirmed**（★ 本模块无 confirmed 出口）。"""
    _v, _r, _d = _v1("The server includes a list of extensions.",
                      action="include", obj="list of extensions", strength="")
    assert _v in (SUPPORTED, UNCERTAIN)
    assert _v != "confirmed"


def test_candidate_field_self_contradiction_is_uncertain():
    """★ ★ constraint 含否定而 strength 不含 ⇒ uncertain（★ 不是 contradicted、★ 不升级）。"""
    _v, _r, _d = _v1("Clients SHOULD NOT provide SEND as services.",
                      action="provide", obj="SEND as services",
                      strength="SHOULD",
                      constraint="Clients SHOULD NOT provide SEND as services.")
    assert _v == UNCERTAIN
    assert _d["★ 候选字段自相矛盾"]


# ══ ⑧ 无明确反证的词形不匹配不得直接 rejected ══
def test_morph_mismatch_is_uncertain_not_rejected():
    """★ 词形差异（ignore vs ignores）⇒ supported；★ 完全缺失 ⇒ uncertain；★ 都不是 rejected。"""
    _v1r, _r1, _d1 = _v1("that server silently ignores the BOOTREQUEST message",
                          action="silently ignore", obj="BOOTREQUEST message")
    assert _v1r == SUPPORTED
    _v2, _r2, _d2 = _v1("that server silently discards the BOOTREQUEST message",
                          action="return", obj="BOOTREQUEST message")
    assert _v2 == UNCERTAIN
    assert _v2 != CONTRADICTED


# ══ 结构与可复算性 ══
def test_v1_has_no_confirmed_output():
    for _kw in ({"quote": "x", "action": "a"}, {"quote": "x", "strength": "MUST"}):
        _v, _r, _d = _v1(**_kw)
        assert _v in (SUPPORTED, CONTRADICTED, UNCERTAIN)


def test_clause_splitting_works():
    _cl = _clauses("If a server is not configured, it discards the message.")
    assert len(_cl) >= 2
    assert any("not configured" in c for c, _ in _cl)


def test_v0_still_present_and_unchanged():
    """★ ★ V0（冻结版）必须仍在且可独立运行（★ 不被 V1 覆盖）。"""
    import importlib
    _v0 = importlib.import_module("n2b0_tristate")
    assert hasattr(_v0, "semantic_support_tristate")
    _v, _r, _s = _v0.semantic_support_tristate(
        "that server silently ignores the BOOTREQUEST message",
        "silently ignore", "BOOTREQUEST message", strength="")
    assert _v in ("supported", "contradicted", "uncertain")


def test_no_llm_calls_in_v1():
    _t = (ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py").read_text(encoding="utf-8")
    assert "DeepSeekClient" not in _t
    assert "chat_json" not in _t
