"""tests/fused/test_strategy.py —— 多导向自适应种子生成（漏洞导向 P0）。"""
from __future__ import annotations

from core.fused.downstream.strategy import (
    VulnRecord, VulnSeedReq, load_vuln_kb, classify_vuln, classify_all,
    dedupe_reqs, determine_strategies, render_attack_prompt, generate_attack_seeds,
)
from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle
from core.llm import StubLLMClient


def _bundle():
    return assemble_bundle(load_fact_views())


# ===========================================================================
# 加载 kb/历史漏洞
# ===========================================================================

def test_load_vuln_kb_has_49():
    vulns = load_vuln_kb(protocol="rtsp")
    assert len(vulns) == 49
    assert vulns[0].case_id == "RTSP-001"


def test_load_vuln_kb_structure():
    v = load_vuln_kb(protocol="rtsp")[0]
    assert v.case_id == "RTSP-001"
    assert isinstance(v.methods, list) and "SETUP" in v.methods
    assert isinstance(v.cwe, str) and "CWE-" in v.cwe


def test_load_vuln_kb_empty_on_missing_dir(tmp_path):
    assert load_vuln_kb(tmp_path) == []


# ===========================================================================
# classify_vuln：漏洞 → 合法边界动作
# ===========================================================================

def test_classify_cwe_null_deref():
    v = VulnRecord(case_id="X", avd_id="", cwe="CWE-476 (空指针解引用)",
                   risk="", methods=["SETUP"], fields=["Transport"], condition="为空")
    r = classify_vuln(v)
    assert r.action == "empty_edge"
    assert "最小合法值" in r.guidance


def test_classify_cwe_stack_overflow():
    v = VulnRecord(case_id="X", avd_id="", cwe="CWE-121 (栈缓冲区溢出)",
                   risk="", methods=["SETUP"], fields=["Authorization"], condition="超长")
    r = classify_vuln(v)
    assert r.action == "long_value"
    assert "超长" in r.guidance or "长但" in r.guidance


def test_classify_condition_overrides_cwe():
    # CWE-416 默认 uaf_seq，但条件「连续两次 SETUP」更具体 → double_setup
    v = VulnRecord(case_id="RTSP-039", avd_id="", cwe="CWE-416 (释放后使用)",
                   risk="", methods=["SETUP"], fields=["track"],
                   condition="对同一 track 连续两次 SETUP")
    r = classify_vuln(v)
    assert r.action == "double_setup"


def test_classify_interleaved_uaf():
    v = VulnRecord(case_id="RTSP-049", avd_id="", cwe="CWE-416 (释放后使用)",
                   risk="", methods=["SETUP", "TEARDOWN"], fields=["Transport"],
                   condition="RTP/RTCP-over-RTSP(interleaved)setup 后终止流")
    r = classify_vuln(v)
    assert r.action == "interleave_seq"


def test_classify_extracts_trigger_streams():
    """漏洞 condition 里的「触发流」（Matroska/Ogg）必须被提取到 streams。"""
    v = VulnRecord(case_id="RTSP-039", avd_id="", cwe="CWE-416",
                   risk="", methods=["SETUP"], fields=["track"],
                   condition="对 Matroska/Ogg 同一 track 连续两次 SETUP")
    r = classify_vuln(v)
    assert r.action == "double_setup"
    assert "matroskaFileTest" in r.streams
    assert "oggFileTest" in r.streams


def test_classify_filters_crash_streams():
    """漏洞文本提到 ADTS（→aacAudioTest，崩溃流）时，只保留安全流 Matroska。"""
    v = VulnRecord(case_id="RTSP-046", avd_id="", cwe="CWE-416",
                   risk="", methods=["SETUP"], fields=[],
                   condition="Matroska 流 SETUP 触发 ADTS demuxer 释放后使用")
    r = classify_vuln(v)
    assert "matroskaFileTest" in r.streams
    assert "aacAudioTest" not in r.streams  # 崩溃流被过滤


def test_dedupe_distinguishes_streams():
    """不同触发流的同 action（double_setup）不能被合并。"""
    a = VulnSeedReq(case_id="A", cwe="", methods=["SETUP"], fields=["track"],
                    action="double_setup", guidance="x",
                    streams=["matroskaFileTest"])
    b = VulnSeedReq(case_id="B", cwe="", methods=["SETUP"], fields=["track"],
                    action="double_setup", guidance="x",
                    streams=["mpeg1or2ESVideoTest"])
    deduped = dedupe_reqs([a, b])
    assert len(deduped) == 2  # 流不同 → 不合并


def test_render_reqs_includes_stream_hint():
    """渲染时流名约束要写进 prompt。"""
    b = _bundle()
    reqs = [VulnSeedReq(case_id="RTSP-039", cwe="", methods=["SETUP"],
                        fields=["track"], action="double_setup",
                        guidance="双 SETUP", streams=["matroskaFileTest"])]
    system, user = render_attack_prompt(b, reqs, protocol="RTSP")
    assert "流名必须用 matroskaFileTest" in user


def test_classify_all_49():
    reqs = classify_all(load_vuln_kb(protocol="rtsp"))
    assert len(reqs) == 49
    # 每条都有动作 + 非空指引
    assert all(r.action for r in reqs)
    assert all(r.guidance for r in reqs)
    # 动作分布至少覆盖序列型与字段型
    actions = {r.action for r in reqs}
    assert "double_setup" in actions
    assert "interleave_seq" in actions
    assert "long_value" in actions
    assert "empty_edge" in actions


def test_dedupe_reqs_merges_same_pattern():
    reqs = classify_all(load_vuln_kb(protocol="rtsp"))
    deduped = dedupe_reqs(reqs)
    # 49 条 CVE → 去重后显著减少（漏洞模式少于 CVE 数）
    assert len(deduped) < 49
    # 同模式合并 case_id（分号连接）
    assert all(";" not in r.case_id or r.case_id for r in deduped)
    # 动作仍覆盖序列型 + 字段型
    actions = {r.action for r in deduped}
    assert "double_setup" in actions
    assert "interleave_seq" in actions
    assert "long_value" in actions


# ===========================================================================
# determine_strategies：自适应导向判定
# ===========================================================================

def test_determine_strategies_all_sources():
    b = _bundle()
    vulns = load_vuln_kb(protocol="rtsp")
    st = determine_strategies(b, resources=[{"name": "x"}],
                              request_templates={"methods": {}}, vulns=vulns)
    assert "instance_guided" in st["normal"]
    assert "structure_guided" in st["normal"]
    assert "state_machine_guided" in st["normal"]
    assert "vulnerability_guided" in st["attack"]
    assert "traffic_guided" in st["constraints"]


def test_determine_strategies_no_vuln_no_attack():
    b = _bundle()
    st = determine_strategies(b, resources=[{"name": "x"}],
                              request_templates=None, vulns=[])
    assert st["attack"] == []
    assert "instance_guided" in st["normal"]
    assert st["constraints"] == []


# ===========================================================================
# render_attack_prompt
# ===========================================================================

def test_render_attack_prompt_contains_reqs():
    b = _bundle()
    reqs = classify_all(load_vuln_kb(protocol="rtsp"))[:5]
    system, user = render_attack_prompt(b, reqs, protocol="RTSP")
    assert "RTSP" in system
    assert "[漏洞导向生成要求]" in user
    assert reqs[0].case_id in user
    assert "绝对合法" in user
    assert "[状态机转移]" in user


# ===========================================================================
# generate_attack_seeds：生成 → 校验（StubLLM）
# ===========================================================================

def _legal_seed_resp():
    return [{
        "description": "SETUP→PLAY 合法边界会话",
        "state_path": ["Init", "Ready", "Playing"],
        "messages": [
            {"method": "SETUP",
             "headers": {"CSeq": "1", "Transport": "RTP/AVP;unicast;client_port=0-0"},
             "body": ""},
            {"method": "PLAY",
             "headers": {"CSeq": "2", "Session": "{{session_id}}",
                         "Range": "npt=0.000-"}, "body": ""},
        ],
    }]


def test_generate_attack_seeds_marks_generated_by():
    b = _bundle()
    reqs = classify_all(load_vuln_kb(protocol="rtsp"))[:3]
    llm = StubLLMClient(response=_legal_seed_resp())
    seeds = generate_attack_seeds(b, llm, reqs, protocol="RTSP")
    assert len(seeds) == 1
    assert seeds[0].generated_by == "hub-rag-v2:attack"
    assert seeds[0].target_vuln_class


def test_generate_attack_seeds_empty_reqs_returns_empty():
    b = _bundle()
    llm = StubLLMClient(response=_legal_seed_resp())
    assert generate_attack_seeds(b, llm, [], protocol="RTSP") == []


def test_generate_attack_seeds_filters_invalid():
    b = _bundle()
    reqs = classify_all(load_vuln_kb(protocol="rtsp"))[:3]
    # 非法种子（Init 直接 PLAY）→ 被 validate_seed 过滤，返回空
    llm = StubLLMClient(response=[{
        "description": "bad",
        "state_path": ["Init"],
        "messages": [{"method": "PLAY",
                      "headers": {"CSeq": "1", "Session": "x"}, "body": ""}],
    }])
    seeds = generate_attack_seeds(b, llm, reqs, protocol="RTSP")
    assert seeds == []
