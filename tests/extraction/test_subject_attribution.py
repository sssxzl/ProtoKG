# -*- coding: utf-8 -*-
"""tests/extraction/test_subject_attribution.py —— **主体归属 + 条件/例外角色**回归。

★ 依据：任务书 P0-1 / P0-3 + 独立复核意见的**已知错误样本**
  · 主体：S11(SIP/B2BUA) S21(SMTP/多主体) S23(SMTP/clients and servers)
           S26(SMTP/client) S33(DHCPv4/DHCP server)
  · 条件/例外：S16(even if) S17(主体修饰) S27(in order to) S28(or contain)

★ **测试必须经过真实被测机制**（走 norm 映射 / L1 / 角色判定），
  **不**只比较 hash、**不**预填正确结果。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fused.extraction.norm import prose_constraint_norm_to_facts  # noqa: E402
from core.fused.extraction.normative_extract import (               # noqa: E402
    classify_clause_role, extract_condition, extract_exception,
)
from core.fused.extraction.normative_rule import (                   # noqa: E402
    build_payload, parse_rule_text, rule_text,
)
from core.fused.extraction.normative_verify import (                # noqa: E402
    CONFIRMED, PENDING, REJECTED, l1_check,
)


def _norm(**kw):
    _b = {
        "kind": "prose_constraint", "protocol": "p", "kb_source_type": "rfc",
        "name": "entity-name", "content": "c", "norm_id": "n",
        "source": "file:rfc.txt#@100", "meaning": "m",
        "constraint": "must do X", "action": "send", "object": "ACK",
        "strength": "MUST", "polarity": "positive",
        # ★ 主体字段（★ 新增中间字段）
        "mentioned_entity": "entity-name",
        "normative_subject": "entity-name",
        "subject_status": "resolved",
    }
    _b.update(kw)
    return _b


# ===========================================================================
# P0-1 · 主体归属
# ===========================================================================

def test_subject_is_obligation_bearer_not_entity():
    """★ 主体取**义务承担者**，而非原文提及的实体。

    ★ S11：原文主体是 B2BUA，``entity`` 是 dialogs ⇒ Rule Slot 主体必须是 B2BUA。
    """
    _f = prose_constraint_norm_to_facts(_norm(
        name="dialogs", mentioned_entity="dialogs",
        normative_subject="B2BUA", subject_status="resolved"))[0]
    assert _f.fact_key.subject.name == "B2BUA"
    assert _f.fact_key.subject.name != "dialogs"


def test_subject_multi_party_is_preserved():
    """★ S21/S23：多主体并列 ⇒ **不得静默丢失其中一方**。

    ★ 原文「Both the client and the server MUST know…」⇒ 主体应保留双方。
    """
    _f = prose_constraint_norm_to_facts(_norm(
        name="client and server", mentioned_entity="client and server",
        normative_subject="client and server",
        subject_status="resolved"))[0]
    assert "client" in _f.fact_key.subject.name
    assert "server" in _f.fact_key.subject.name


def test_subject_response_code_is_not_bearer():
    """★ S26：响应码 454 出现在原文，但**不是**义务承担者。

    ★ 原文「If the client receives 454 …」⇒ 主体必须是 client。
    """
    _f = prose_constraint_norm_to_facts(_norm(
        name="454", mentioned_entity="454", normative_subject="client",
        subject_status="resolved"))[0]
    assert _f.fact_key.subject.name == "client"
    assert _f.fact_key.subject.name != "454"


def test_subject_message_name_is_not_bearer():
    """★ S33：BOOTP BOOTREPLY message 不是义务承担者 ⇒ 主体是 DHCP server。"""
    _f = prose_constraint_norm_to_facts(_norm(
        name="BOOTP BOOTREPLY message",
        mentioned_entity="BOOTP BOOTREPLY message",
        normative_subject="DHCP server", subject_status="resolved"))[0]
    assert _f.fact_key.subject.name == "DHCP server"


def test_subject_unresolved_yields_no_rule_slot():
    """★ 主体**未解析** ⇒ **不生成**可进入正式归并的 Rule Slot。

    ★ 「不得为了获得稳定 FactID 而猜测主体」⇒ ⇒ 落回普通 definition。
    """
    _f = prose_constraint_norm_to_facts(_norm(
        name="dialogs", mentioned_entity="dialogs",
        normative_subject="", subject_status="unresolved"))[0]
    # ★ 没有 Rule Slot 的 qualifiers ⇒ ⇒ 不是规范规则
    assert not _f.fact_key.subject.qualifiers.get("action")
    assert not _f.fact_key.subject.qualifiers.get("kind")


def test_subject_pronoun_is_pending():
    """★ 代词主体 ⇒ L1 判**待审**（不进 confirmed）。"""
    _p = build_payload(subject="it", action="send", object_="ACK",
                       strength="MUST", polarity="positive")
    _r = l1_check(rule_text_value=rule_text(_p), quote="It MUST send ACK.",
                  evidence_span=(10, 10), keyword_raw="MUST", subject="it")
    assert _r.verdict == PENDING
    assert _r.field_verdicts.get("subject") == "pronoun"


# ===========================================================================
# P0-3 · 条件 / 例外的**语义角色**
# ===========================================================================

def test_even_if_is_concession_not_condition():
    """★ S16：``even if`` ⇒ **让步**，不是生效条件。"""
    _txt = "The empty line MUST be present, even if message-body is not."
    assert classify_clause_role(_txt) == "concession"
    _cond, _st = extract_condition(_txt)
    assert _cond is None or "even if" not in _cond.lower()


def test_purpose_is_not_condition():
    """★ S27：``in order to`` ⇒ **目的**，不是触发条件。"""
    _txt = ("MUST NOT require STARTTLS in order to deliver mail locally.")
    assert classify_clause_role(_txt) == "purpose"
    _cond, _st = extract_condition(_txt)
    assert _cond is None or "in order to" not in _cond.lower()


def test_alternative_is_not_exception():
    """★ S28：``or contain "="`` ⇒ **替代方案**，不是例外。"""
    _txt = 'The parameter MUST be a string, or contain "=" .'
    assert classify_clause_role(_txt) == "alternative"
    _exc, _st = extract_exception(_txt)
    assert _exc is None or "or contain" not in _exc.lower()


def test_subject_modifier_is_qualifier_not_condition():
    """★ S17：主体修饰语 ⇒ **限定**，不是生效条件。"""
    _txt = "documented in standards track RFCs may be used by SIP extensions"
    _role = classify_clause_role(_txt)
    assert _role in ("explanatory", "qualifier")
    _cond, _st = extract_condition(_txt)
    assert _cond is None or "standards track" not in _cond.lower()


def test_real_condition_still_detected():
    """★ 排除规则**不得**误伤真条件。"""
    _txt = "The client MUST send ACK if the session is in state S."
    assert classify_clause_role(_txt) == "condition"
    _cond, _st = extract_condition(_txt)
    assert _cond is not None and "if the session" in _cond.lower()


def test_real_exception_still_detected():
    """★ 排除规则**不得**误伤真例外。"""
    _txt = "The client MUST NOT send ACK unless the session is in state S."
    _exc, _st = extract_exception(_txt)
    assert _exc is not None and "unless" in _exc.lower()


# ===========================================================================
# 集成：走真实映射链（LLM 原始项 → norm → fact）
# ===========================================================================

def test_integration_entity_only_does_not_become_rule():
    """★ 集成：只有 entity（无 normative_subject）⇒ **不成规则**。

    ★ 覆盖「entity 不得无条件写入 Rule Slot 的 subject」。
    """
    _f = prose_constraint_norm_to_facts(_norm(
        name="RTSP", mentioned_entity="RTSP", normative_subject="",
        subject_status="unresolved"))[0]
    assert not _f.fact_key.subject.qualifiers.get("kind")
    assert _f.fact_key.aspect == "definition"


def test_integration_slot_carries_subject_semantics():
    """★ 集成：Rule Slot 的 qualifiers 带 action/object/kind ⇒ 身份可区分。"""
    _f = prose_constraint_norm_to_facts(_norm(
        name="client", normative_subject="client",
        action="send", object="ACK"))[0]
    _q = _f.fact_key.subject.qualifiers
    assert _q.get("action") == "send"
    assert _q.get("object") == "ACK"
    assert _q.get("kind") == "normative_rule"
    # ★ 值是规范化规则文本
    _v = parse_rule_text(_f.claims[0].value.data)
    assert _v is not None and _v["strength"] == "MUST"
