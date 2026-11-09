"""tests/fused/test_vuln.py —— vuln 源（kb/历史漏洞）→ Fact 原生映射。"""
from __future__ import annotations

from core.fused.vuln import vuln_to_facts, vuln_entry_to_facts
from core.fused.registry import load_registry
from core.fused.validation import validate_fact


def test_vuln_to_facts_non_empty():
    facts = vuln_to_facts(protocol="rtsp")
    sec = [f for f in facts if f.fact_key.aspect == "security_property"]
    assert len(sec) == 53   # 49 个漏洞文件（含 12 个新增 LIVE555 CVE）


def test_vuln_pattern_facts_produced():
    """vuln 源额外产结构化漏洞模式（vuln_pattern，借鉴 GLMFuzz）。"""
    facts = vuln_to_facts(protocol="rtsp")
    pats = [f for f in facts if f.fact_key.aspect == "vuln_pattern"]
    assert len(pats) == 23
    for f in pats:
        assert f.fact_key.subject.type in ("method", "header")
        assert f.claims[0].value.type == "struct"
        data = f.claims[0].value.data
        assert "action" in data and "trigger_sequence" in data
        assert data["action"] != ""
        assert f.claims[0].authority == "vuln"


def test_only_seedgen_scope_produces_facts():
    """scope=seedgen 才产 fact；not_rtsp_protocol 等不产。"""
    facts = vuln_to_facts(protocol="rtsp")
    cases = {c.evidence[0].locator for f in facts for c in f.claims}
    assert len(cases) == 23
    # 所有产出的 case_id 都是 RTSP-xxx（seedgen 的），无空
    assert all(c and c.startswith("RTSP-") for c in cases)


def test_method_subjects_map_security_property():
    facts = vuln_to_facts(protocol="rtsp")
    method_facts = [f for f in facts
                    if f.fact_key.subject.type == "method"
                    and f.fact_key.aspect == "security_property"]
    assert len(method_facts) == 27
    names = {f.fact_key.subject.name for f in method_facts}
    assert names == {"SETUP", "PLAY", "DESCRIBE", "TEARDOWN"}
    for f in method_facts:
        assert f.fact_key.aspect == "security_property"
        assert f.claims[0].value.type == "text"
        assert f.claims[0].epistemic_type == "descriptive"
        assert f.claims[0].authority == "vuln"


def test_header_subjects_map_security_property():
    facts = vuln_to_facts(protocol="rtsp")
    header_facts = [f for f in facts
                    if f.fact_key.subject.type == "header"
                    and f.fact_key.aspect == "security_property"]
    assert len(header_facts) == 26
    names = {f.fact_key.subject.name for f in header_facts}
    assert "Transport header" in names and "Authorization" in names
    for f in header_facts:
        assert f.fact_key.aspect == "security_property"
        assert f.claims[0].value.type == "text"


def test_non_seedgen_scope_skipped():
    """not_rtsp_protocol / insufficient_source 等 scope 产 0 fact。"""
    for scope in ("not_rtsp_protocol", "insufficient_source",
                  "not_rtsp_client_side", "not_trigger_vulnerability"):
        assert vuln_entry_to_facts({"scope": scope, "description_raw": "x"}) == []


def test_all_vuln_facts_pass_fail_closed():
    facts = vuln_to_facts(protocol="rtsp")
    registry = load_registry()
    for f in facts:
        validate_fact(f, registry)   # 不抛 = 通过


def test_protocol_parameterized():
    """protocol 参数化：换协议 fact 的 protocol 正确（不再硬编码 rtsp）。"""
    # rtsp 是 vuln.py 里的默认协议，只测 rtsp 无法暴露「硬编码 rtsp」回归；
    # 因此同时用非默认的存活协议（smtp）做判别性校验。
    for protocol in ("rtsp", "smtp"):
        facts = vuln_to_facts(protocol=protocol)
        assert facts, f"{protocol} 应有漏洞库"
        assert all(f.fact_key.protocol == protocol for f in facts)
