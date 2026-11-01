"""tests/fused/test_norm.py —— norm → v2 Fact 原生映射 (Layer 2 第一源 rfc)。"""
from __future__ import annotations

from core.fused.norm import (
    parse_transition_content, transition_norm_to_fact,
    parse_field_content, field_norm_to_facts,
    parse_outcome_content, outcome_norm_to_facts, method_norm_to_facts,
    map_norm_to_facts,
)
from core.fused.registry import load_registry
from core.fused.validation import validate_fact


TRANSITION_NORM = {
    "norm_id": "rtsp.transition.Init.setup.200",
    "protocol": "rtsp",
    "kind": "transition",
    "name": "Init→Ready via SETUP",
    "content": "from=Init method=SETUP code=200 to=Ready",
    "source": "file:rfc2326.txt#10.1",
    "kb_source_type": "rfc",
}

FIELD_NORM = {
    "norm_id": "rtsp.field.require",
    "protocol": "rtsp",
    "kind": "field",
    "name": "Require",
    "content": "Require: <tag> | required: 当客户端在方法扩展不被支持时需要否定确认时，可添加对应扩展的 tag",
    "source": "file:rfc2326.txt#10.1",
    "kb_source_type": "rfc",
}


# ===== transition =====

def test_parse_transition_content():
    d = parse_transition_content("from=Init method=SETUP code=200 to=Ready")
    assert d == {"from": "Init", "method": "SETUP", "code": "200", "to": "Ready"}


def test_transition_norm_to_fact_structure():
    fact = transition_norm_to_fact(TRANSITION_NORM)
    subj = fact.fact_key.subject
    assert subj.type == "relation"
    assert subj.name == "transitions_to"
    assert subj.qualifiers["source"].name == "Init"
    assert subj.qualifiers["target"].name == "Ready"
    assert subj.qualifiers["method"].name == "SETUP"
    assert fact.fact_key.aspect == "target_state"
    assert fact.claims[0].value.type == "text"
    assert fact.claims[0].value.data == "Ready"
    assert fact.claims[0].epistemic_type == "normative_unspecified"


# ===== field =====

def test_parse_field_content_simple():
    syntax, modality, semantic = parse_field_content(FIELD_NORM["content"])
    assert syntax == "Require: <tag>"
    assert modality == "required"
    assert semantic.startswith("当客户端")


def test_parse_field_content_abnf_multiple_pipes():
    c = 'smpte-type = "smpte" | "smpte-30-drop" | "smpte-25" | required: 指定 SMPTE'
    syntax, modality, semantic = parse_field_content(c)
    assert syntax == 'smpte-type = "smpte" | "smpte-30-drop" | "smpte-25"'
    assert modality == "required"
    assert semantic == "指定 SMPTE"


def test_parse_field_content_enum_value():
    c = "unicast | multicast | required: 互斥地指示尝试单播还是组播传输"
    syntax, modality, semantic = parse_field_content(c)
    assert syntax == "unicast | multicast"
    assert modality == "required"


def test_field_norm_to_facts_two_facts():
    facts = field_norm_to_facts(FIELD_NORM)
    assert len(facts) == 2
    aspects = {f.fact_key.aspect for f in facts}
    assert aspects == {"syntax", "definition"}
    by_aspect = {f.fact_key.aspect: f for f in facts}
    assert by_aspect["syntax"].claims[0].value.type == "pattern"
    assert by_aspect["definition"].claims[0].value.type == "text"
    assert by_aspect["syntax"].claims[0].epistemic_type == "must"
    assert by_aspect["syntax"].fact_key.subject.name == "Require"


def test_field_fact_passes_fail_closed():
    registry = load_registry()
    for f in field_norm_to_facts(FIELD_NORM):
        validate_fact(f, registry)   # 不抛 = 通过


# ===== outcome =====

OUTCOME_NORM = {
    "norm_id": "rtsp.outcome.501",
    "protocol": "rtsp",
    "kind": "outcome",
    "name": "501",
    "content": "Not implemented | when: 消息接收方不理解请求时",
    "source": "file:rfc2326.txt#10.1",
    "kb_source_type": "rfc",
}


def test_parse_outcome_content():
    meaning, condition = parse_outcome_content(OUTCOME_NORM["content"])
    assert meaning == "Not implemented"
    assert condition == "消息接收方不理解请求时"


def test_parse_outcome_content_empty_when():
    meaning, condition = parse_outcome_content("OK | when: ")
    assert meaning == "OK"
    assert condition == ""


def test_outcome_norm_to_facts():
    facts = outcome_norm_to_facts(OUTCOME_NORM)
    assert len(facts) == 1
    f = facts[0]
    assert f.fact_key.subject.type == "status"
    assert f.fact_key.subject.name == "501"
    assert f.fact_key.aspect == "definition"
    assert f.claims[0].value.type == "text"
    assert f.claims[0].value.data == "Not implemented"


def test_outcome_fact_passes_fail_closed():
    registry = load_registry()
    for f in outcome_norm_to_facts(OUTCOME_NORM):
        validate_fact(f, registry)


# ===== method =====

METHOD_NORM = {
    "norm_id": "rtsp.method.setup",
    "protocol": "rtsp",
    "kind": "method",
    "name": "SETUP",
    "content": "The SETUP request for a URI specifies the transport mechanism to be used for the streamed media.",
    "source": "file:rfc2326.txt#10.1",
    "kb_source_type": "rfc",
}


def test_method_norm_to_facts():
    facts = method_norm_to_facts(METHOD_NORM)
    assert len(facts) == 1
    f = facts[0]
    assert f.fact_key.subject.type == "method"
    assert f.fact_key.subject.name == "SETUP"
    assert f.fact_key.aspect == "definition"
    assert f.claims[0].value.type == "text"


def test_method_fact_passes_fail_closed():
    registry = load_registry()
    for f in method_norm_to_facts(METHOD_NORM):
        validate_fact(f, registry)


# ===== 分派 =====

def test_map_norm_to_facts_dispatches():
    assert len(map_norm_to_facts(TRANSITION_NORM)) == 1
    assert len(map_norm_to_facts(FIELD_NORM)) == 2
    assert len(map_norm_to_facts(OUTCOME_NORM)) == 1
    assert len(map_norm_to_facts(METHOD_NORM)) == 1
    src_norm = dict(FIELD_NORM, kb_source_type="vuln")
    assert map_norm_to_facts(src_norm) == []       # 第一版只 rfc
