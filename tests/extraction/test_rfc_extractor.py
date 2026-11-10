"""tests/test_rfc_extractor.py —— rfc 源（RFC 规范文本 → rfc norm）。"""
from __future__ import annotations

from core.fused.extraction.rfc_extractor import (
    extract_rfc_norms, _clean_body, _first_sentence,
    extract_constraint_candidates, infer_constraints,
    extract_constraint_norms,
)
from core.fused.extraction.norm import (map_norm_to_facts, constraint_norm_to_facts,
                              parse_constraint_content)
from core.llm import StubLLMClient


def test_clean_body_removes_page_marks():
    lines = [
        "   The DESCRIBE method retrieves the description.",
        "   Example:",
        "",
        "Schulzrinne, et. al.        Standards Track                    [Page 31]",
        "",
        "RFC 2326              Real Time Streaming Protocol            April 1998",
    ]
    out = _clean_body(lines)
    assert "DESCRIBE" in out
    assert "[Page" not in out
    assert "April 1998" not in out


def test_first_sentence_truncates():
    assert _first_sentence("This is a sentence. And more.") == "This is a sentence."
    assert _first_sentence("") == ""


def test_extract_methods_all_eleven():
    norms = extract_rfc_norms("rtsp")
    methods = [n["name"] for n in norms if n["kind"] == "method"]
    assert set(methods) == {
        "OPTIONS", "DESCRIBE", "ANNOUNCE", "SETUP", "PLAY", "PAUSE",
        "TEARDOWN", "GET_PARAMETER", "SET_PARAMETER", "REDIRECT", "RECORD",
    }


def test_extract_fields_and_outcome():
    norms = extract_rfc_norms("rtsp")
    fields = {n["name"] for n in norms if n["kind"] == "field"}
    outcomes = {n["name"] for n in norms if n["kind"] == "outcome"}
    # 字段应含核心头（Accept/Transport 类，RTSP 特有 CSeq/Session）
    assert {"Accept", "CSeq", "Session", "Range", "Transport"} <= fields
    assert outcomes, "应至少抽到若干状态码（§11 有正文定义的状态码）"
    assert "405" in outcomes or "250" in outcomes


def test_methods_map_to_definition_facts():
    norms = extract_rfc_norms("rtsp")
    method_norms = [n for n in norms if n["kind"] == "method"]
    facts = []
    for n in method_norms:
        facts.extend(map_norm_to_facts(n))
    # 每个 method norm 产 1 个 definition fact
    assert len(facts) == len(method_norms)
    assert all(f.fact_key.subject.type == "method" for f in facts)
    assert all(f.fact_key.aspect == "definition" for f in facts)
    # rfc 源的认识论是 normative
    assert all(f.claims[0].authority == "rfc" for f in facts)


def test_all_rfc_facts_pass_fail_closed():
    from core.fused.hub.registry import load_registry
    from core.fused.hub.validation import validate_fact
    norms = extract_rfc_norms("rtsp")
    registry = load_registry()
    for n in norms:
        for f in map_norm_to_facts(n):
            validate_fact(f, registry)  # 不抛 = 通过


# ===== 语义约束抽取（借鉴 SemFuzz）=====

def test_extract_constraint_candidates_non_empty():
    """rule 粗筛：能从 RFC 抽到含规范性措辞（MUST/长度等）的约束候选句子。"""
    cands = extract_constraint_candidates("rtsp")
    assert len(cands) > 0
    assert all(c["text"] and c["source"].startswith("file:") for c in cands)


def test_infer_constraints_with_stub():
    """LLM 结构化：StubLLM 返回 (field/constraint/violation/expected) → 结构化约束。"""
    stub = StubLLMClient(response={"constraints": [
        {"field": "QNAME", "constraint": "单 label ≤ 63 字节",
         "violation": "label 长度字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
    ]})
    cons = infer_constraints("rtsp", llm=stub, max_candidates=8)
    assert len(cons) >= 1
    c = cons[0]
    assert c["field"] == "QNAME"
    assert c["constraint"]
    assert c["expected_behavior"] == "FORMERR"


def test_constraint_norm_to_facts_maps_boundary_and_expectation():
    """constraint → legal_boundary + response_expectation 两个 fact。"""
    norm = {
        "norm_id": "dns.constraint.qname", "kind": "constraint", "name": "QNAME",
        "kb_source_type": "rfc", "protocol": "dns", "source": "file:rfc1035.txt",
        "content": "field=QNAME constraint=单label<=63 violation=长度字段>实际 "
                   "code=1 behavior=FORMERR",
    }
    facts = constraint_norm_to_facts(norm)
    aspects = {f.fact_key.aspect for f in facts}
    assert "legal_boundary" in aspects
    assert "response_expectation" in aspects
    assert all(f.fact_key.subject.type == "header" for f in facts)
    assert all(f.fact_key.subject.name == "QNAME" for f in facts)
    assert all(f.claims[0].epistemic_type == "must" for f in facts)


def test_parse_constraint_content_keeps_spaces_in_values():
    """值含空格（真实 LLM 输出）时，按 key= 边界切分不丢词。"""
    content = ("field=QNAME constraint=单 label 长度 <= 63 violation=长度字段 > 实际内容 "
               "code=FORMERR behavior=返回 FORMERR 错误")
    d = parse_constraint_content(content)
    assert d["field"] == "QNAME"
    assert d["constraint"] == "单 label 长度 <= 63"
    assert d["violation"] == "长度字段 > 实际内容"
    assert d["code"] == "FORMERR"
    assert d["behavior"] == "返回 FORMERR 错误"


def test_constraint_facts_pass_fail_closed():
    """约束映射的 fact 全过 fail-closed（legal_boundary 扩展 header + response_expectation 新 aspect）。"""
    from core.fused.hub.registry import load_registry
    from core.fused.hub.validation import validate_fact
    norm = {
        "norm_id": "dns.constraint.qname", "kind": "constraint", "name": "QNAME",
        "kb_source_type": "rfc", "protocol": "dns", "source": "file:rfc1035.txt",
        "content": "field=QNAME constraint=单label<=63 violation=长度字段>实际 "
                   "code=1 behavior=FORMERR",
    }
    registry = load_registry()
    for f in constraint_norm_to_facts(norm):
        validate_fact(f, registry)  # 不抛 = 通过


def test_rfc_config_comes_from_profile_not_hardcoded():
    """rfc 配置必须来自 profile，通用层不内置协议默认（标题格式识别协议无关）。"""
    from core.fused.extraction.rfc_extractor import _load_rfc_config
    rtsp = _load_rfc_config("rtsp")
    assert rtsp["method_excludes"] == ["EMBEDDED"]
    # smtp 未配 rfc 段 → 全空
    smtp = _load_rfc_config("smtp")
    assert smtp["method_excludes"] == []
    assert smtp["numeric_bounds"] == []


def test_extract_is_section_number_agnostic():
    """标题格式识别不依赖章节号：方法/状态码靠「全大写 / NNN Reason」格式，
    而非「§10=方法」这类 RTSP 特定章节号映射（根治硬编码）。"""
    from core.fused.extraction.rfc_extractor import extract_rfc_norms
    norms = extract_rfc_norms("rtsp")
    methods = {n["name"] for n in norms if n["kind"] == "method"}
    outcomes = {n["name"] for n in norms if n["kind"] == "outcome"}
    assert len(methods) == 11
    assert "EMBEDDED" not in methods  # 多词标题自然排除，无需章节号过滤
    assert {"250", "454", "461"} <= outcomes  # 状态码靠「NNN Reason」识别


def test_infer_structures_llm_fallback():
    """LLM 兜底：正则识别不了的多词/带括号标题（如 SMTP「Extended HELLO (EHLO)」）
    交给 LLM 识别方法/字段，补齐正则标题格式识别的不足（SemFuzz 式 LLM 补语义）。"""
    from core.fused.extraction.rfc_extractor import infer_structures
    stub = StubLLMClient(response={
        "methods": [{"name": "EHLO", "definition": "Extended HELLO greeting"}],
        "fields": [{"name": "Reply-To", "definition": "回复地址"}],
        "outcomes": [],
    })
    norms = infer_structures("smtp", llm=stub, max_headings=30)
    # smtp 有多词标题（Extended HELLO (EHLO)），会交给 LLM；StubLLM 固定返回
    assert any(n["kind"] == "method" and n["name"] == "EHLO" for n in norms)
    assert any(n["kind"] == "field" and n["name"] == "Reply-To" for n in norms)
    # norm 结构对齐 norm.py 映射器（kb_source_type/protocol）
    assert all(n["kb_source_type"] == "rfc" for n in norms)
    assert all(n["protocol"] == "smtp" for n in norms)
