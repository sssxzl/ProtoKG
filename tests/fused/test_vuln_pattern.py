"""tests/fused/test_vuln_pattern.py —— 漏洞模式（vuln_pattern）识别与抽取（GLMFuzz 借鉴，rule 部分）。"""
from __future__ import annotations

import json
from pathlib import Path

from core.fused.vuln_pattern import (
    classify_action, boundary_for_action, extract_vuln_pattern,
    normalize_field, extract_stream_hints, complete_vuln_pattern,
)
from core.fused.vuln import vuln_entry_to_pattern_facts
from core.llm import StubLLMClient
from core.fused.downstream.boundary_probe import (
    derive_vuln_pattern_candidates, vuln_pattern_dict_tokens,
)

KB_VULN = Path(__file__).resolve().parents[2] / "kb" / "rtsp" / "历史漏洞"


def _entry(case_id: str) -> dict:
    return json.loads((KB_VULN / f"{case_id}.json").read_text(encoding="utf-8"))


# ============ action 分类 ============

def test_classify_action_cwe_only():
    assert classify_action("CWE-416 (释放后使用)", "", "") == "uaf_seq"
    assert classify_action("CWE-617 (可达断言)", "", "") == "assert_seq"
    assert classify_action("CWE-121 (栈缓冲区溢出)", "", "") == "long_value"


def test_classify_action_condition_overrides_cwe():
    # 条件关键词「同一 track 连续两次 SETUP」更具体，压过 CWE-416
    assert classify_action("CWE-416", "对同一 track 连续两次 SETUP", "") == "double_setup"
    # interleaved 关键词 → interleave_seq
    assert classify_action("CWE-416", "interleaved setup 后终止流", "") == "interleave_seq"


def test_classify_action_default():
    assert classify_action("CWE-999 (未知)", "无关键词", "") == "default"


# ============ 边界参数 ============

def test_boundary_for_action_mapped():
    b = boundary_for_action("double_setup")
    assert b is not None and b.dim == "track_number"
    assert boundary_for_action("long_value") is None  # 字段型 action 无边界参数
    assert boundary_for_action("no_such_action") is None


# ============ 漏洞模式抽取 ============

def test_extract_vuln_pattern_assert_seq():
    pat = extract_vuln_pattern(_entry("RTSP-001"))
    assert pat["action"] == "assert_seq"
    assert pat["trigger_sequence"] == ["SETUP", "PLAY"]
    assert pat["boundary"]["dim"] == "repeated_setup_play"
    assert pat["cwe"].startswith("CWE-617")
    assert pat["mutation_hint"] == "多个 SETUP 和 PLAY 命令"


def test_extract_vuln_pattern_field_anchor():
    """field 锚点（无 method）→ trigger_field 归一化，boundary 依 action 而定。"""
    # 构造一个只有 field 锚点、scope=seedgen 的条目
    entry = {
        "scope": "seedgen", "case_id": "X", "cwe_avd": "CWE-121",
        "description_raw": "认证头超长溢出", "trigger": {
            "method": {"value": None},
            "field": {"value": ["Authorization header"]},
            "condition": {"value": "超长"},
        },
    }
    pat = extract_vuln_pattern(entry)
    assert pat["trigger_sequence"] == []
    assert pat["trigger_field"] == "Authorization"  # 归一化
    assert pat["action"] == "long_value"
    assert pat["boundary"] is None  # long_value 无边界参数


def test_extract_vuln_pattern_returns_none():
    assert extract_vuln_pattern({"scope": "not_rtsp_protocol",
                                 "trigger": {"method": {"value": ["SETUP"]}}}) is None
    # 无 method/field 锚点
    assert extract_vuln_pattern({"scope": "seedgen",
                                 "trigger": {"method": {"value": None},
                                             "field": {"value": None}}}) is None


def test_extract_vuln_pattern_streams():
    pat = extract_vuln_pattern({
        "scope": "seedgen", "case_id": "X", "cwe_avd": "CWE-416",
        "description_raw": "Matroska 流 SETUP 触发释放后使用",
        "trigger": {"method": {"value": ["SETUP"]},
                    "field": {"value": None},
                    "condition": {"value": "Matroska 同一 track 连续两次 SETUP"}},
    })
    assert pat["action"] == "double_setup"
    assert "matroskaFileTest" in pat["streams"]


# ============ fact 映射 ============

def test_vuln_entry_to_pattern_facts_method_subject():
    facts = vuln_entry_to_pattern_facts(_entry("RTSP-001"))
    assert len(facts) == 1
    f = facts[0]
    assert f.fact_key.subject.type == "method"
    assert f.fact_key.subject.name == "SETUP"  # 触发序列首个方法
    assert f.fact_key.aspect == "vuln_pattern"
    assert f.claims[0].value.type == "struct"


def test_vuln_entry_to_pattern_facts_header_subject():
    entry = {
        "scope": "seedgen", "case_id": "X", "cwe_avd": "CWE-121",
        "description_raw": "认证头超长溢出", "trigger": {
            "method": {"value": None},
            "field": {"value": ["Authorization header"]},
            "condition": {"value": "超长"},
        },
    }
    facts = vuln_entry_to_pattern_facts(entry)
    assert len(facts) == 1
    assert facts[0].fact_key.subject.type == "header"
    assert facts[0].fact_key.subject.name == "Authorization"


# ============ 归一化 ============

def test_normalize_field_alias():
    assert normalize_field("Transport header") == "Transport"
    assert normalize_field("授权头") == "Authorization"
    assert normalize_field("序列号") == "CSeq"
    assert normalize_field("track") == "track"


def test_extract_stream_hints_filters_crash_streams():
    # aacAudioTest 是崩溃流，被过滤
    assert "aacAudioTest" not in extract_stream_hints("ADTS demuxer 释放后使用")


# ============ Phase 2：LLM 补全 ============

def test_complete_vuln_pattern_without_llm_is_rule_anchor():
    pat = complete_vuln_pattern(_entry("RTSP-001"))  # llm=None → rule 锚点
    assert pat["trigger_sequence"] == ["SETUP", "PLAY"]
    assert pat["mutation_hint"] == "多个 SETUP 和 PLAY 命令"


def test_complete_vuln_pattern_llm_completes_sequence():
    llm = StubLLMClient(response={"sequence": ["DESCRIBE", "SETUP", "SETUP"]})
    pat = complete_vuln_pattern(_entry("RTSP-001"), llm=llm)
    assert pat["trigger_sequence"] == ["DESCRIBE", "SETUP", "SETUP"]


def test_complete_vuln_pattern_llm_completes_hint():
    llm = StubLLMClient(response={"hint": "重复 SETUP 触发断言"})
    pat = complete_vuln_pattern(_entry("RTSP-001"), llm=llm)
    assert pat["mutation_hint"] == "重复 SETUP 触发断言"


def test_complete_vuln_pattern_llm_degrade_on_exception():
    """LLM 抛异常 → 降级保留 rule 锚点（不丢失）。"""

    class _Boom:
        def chat_json(self, **kw):
            raise RuntimeError("boom")

    pat = complete_vuln_pattern(_entry("RTSP-001"), llm=_Boom())
    assert pat["trigger_sequence"] == ["SETUP", "PLAY"]


# ============ Phase 4：漏洞模式 → 边界候选 + 定向字典 ============

def test_derive_vuln_pattern_candidates_double_setup():
    bundle = {"vuln_pattern": {
        "SETUP": [{"action": "double_setup", "trigger_sequence": ["SETUP"]}],
    }}
    cands = derive_vuln_pattern_candidates(bundle)
    assert len(cands) == 2  # legal + illegal
    labels = [l for l, _ in cands]
    assert labels == ["legal", "illegal"]


def test_derive_vuln_pattern_candidates_dedupes_action():
    """同 action 的多条 CVE 只产一份候选（去重）。"""
    bundle = {"vuln_pattern": {
        "SETUP": [
            {"action": "double_setup", "trigger_sequence": ["SETUP"]},
            {"action": "double_setup", "trigger_sequence": ["SETUP"]},
        ],
    }}
    cands = derive_vuln_pattern_candidates(bundle)
    assert len(cands) == 2  # 去重后仍只有 legal+illegal


def test_derive_vuln_pattern_candidates_field_action_no_field_no_llm_returns_empty():
    """字段型 action 无 trigger_field 且无 llm → 不产候选（规则版覆盖不了）。"""
    bundle = {"vuln_pattern": {
        "Authorization": [{"action": "long_value", "trigger_sequence": []}],
    }}
    assert derive_vuln_pattern_candidates(bundle) == []


def test_derive_vuln_pattern_candidates_field_action_produces_edge():
    """字段型 action（long_value）+ trigger_field → 产「正常 vs 超长」候选对。"""
    bundle = {"vuln_pattern": {
        "Authorization": [{
            "action": "long_value", "trigger_sequence": [], "trigger_field": "Authorization",
        }],
    }}
    cands = derive_vuln_pattern_candidates(bundle)
    assert len(cands) == 2  # legal + illegal
    labels = [l for l, _ in cands]
    assert labels == ["legal", "illegal"]
    # illegal 候选带超长字段值
    illegal = cands[1][1]
    assert any(len(v) == 128 for m in illegal.messages for v in m.headers.values())


def test_field_action_candidates_edge_values():
    """规则版字段型边界值：long_value→超长 / empty_edge→空 / int_edge→MAX。"""
    from core.fused.downstream.boundary_probe import _field_action_candidates
    # long_value → 128 字符
    cands = _field_action_candidates(
        {"action": "long_value", "trigger_field": "Authorization"}, "s")
    assert cands[1][1].messages[0].headers["Authorization"] == "A" * 128
    # empty_edge → 空值
    cands = _field_action_candidates(
        {"action": "empty_edge", "trigger_field": "Authorization"}, "s")
    assert cands[1][1].messages[0].headers["Authorization"] == ""
    # 未映射字段型 action（abs_time_seek 等）→ 规则版返回空（走 LLM）
    assert _field_action_candidates(
        {"action": "abs_time_seek", "trigger_field": "Range"}, "s") == []


def test_vuln_pattern_dict_tokens():
    bundle = {"vuln_pattern": {
        "SETUP": [{
            "action": "double_setup",
            "trigger_sequence": ["SETUP"],
            "trigger_field": "track",
            "streams": ["matroskaFileTest"],
        }],
    }}
    tokens = vuln_pattern_dict_tokens(bundle)
    assert "SETUP" in tokens
    assert "track" in tokens
    assert "matroskaFileTest" in tokens


def test_boundary_and_stream_from_profile():
    """流名/边界从 profile 的 vuln 段读（协议特定知识归位，不再硬编码通用层）。"""
    from core.fused.vuln_pattern import boundary_for_action, extract_stream_hints
    assert boundary_for_action("double_setup", "rtsp").dim == "track_number"
    assert extract_stream_hints("matroska", "rtsp") == ["matroskaFileTest"]
