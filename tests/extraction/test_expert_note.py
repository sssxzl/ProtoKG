"""tests/test_expert_note.py —— expert_note v3（专家判断）→ Fact 原生映射。"""
from __future__ import annotations

from core.fused.extraction.expert_note import expert_note_to_facts
from core.fused.hub.registry import load_registry
from core.fused.hub.validation import validate_fact


def test_expert_note_to_facts_non_empty():
    facts = expert_note_to_facts(protocol="rtsp")
    assert len(facts) > 0  # v3 四维至少产若干 security_property fact


def test_hotspots_map_security_property_by_target_type():
    facts = expert_note_to_facts(protocol="rtsp")
    sec = [f for f in facts if f.fact_key.aspect == "security_property"]
    assert sec
    subjects = {(f.fact_key.subject.type, f.fact_key.subject.name) for f in sec}
    # target_type=field → header（Transport）；target_type=method → method（SETUP）
    assert ("header", "Transport") in subjects
    assert ("method", "SETUP") in subjects
    for f in sec:
        assert f.claims[0].value.type == "text"
        assert f.claims[0].authority == "expert_note"


def test_design_weaknesses_map_protocol_subject():
    facts = expert_note_to_facts(protocol="rtsp")
    proto = [f for f in facts if f.fact_key.subject.type == "protocol"]
    assert proto  # 设计弱点（会话状态机复杂）挂 protocol subject
    assert any("会话状态机" in f.fact_key.subject.name for f in proto)


def test_implicit_constraints_map_header_subject():
    facts = expert_note_to_facts(protocol="rtsp")
    headers = [f for f in facts if f.fact_key.subject.type == "header"]
    names = {f.fact_key.subject.name for f in headers}
    assert any("CSeq" in n or "Session" in n for n in names)  # 隐含约束挂 header


def test_all_protocols_pass_fail_closed():
    registry = load_registry()
    # 目标协议范围（2026-10-31 kb 裁剪后仅剩 rtsp/sip/smtp）
    for p in ["rtsp", "sip", "smtp"]:
        facts = expert_note_to_facts(protocol=p)
        assert facts, f"{p} 应有 v3 expert_note facts"
        for f in facts:
            validate_fact(f, registry)  # 不抛 = 通过
