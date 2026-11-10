"""tests/test_selector.py —— 三层编排 + 降级。"""
from __future__ import annotations

from core.fused.downstream.selector import select_seeds
from core.fused.downstream.strategy import load_vuln_kb
from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle
from core.llm import StubLLMClient


def _bundle():
    return assemble_bundle(load_fact_views())


def _legal_attack_seed():
    """一条合法且方法序列唯一（6 条消息、多次回到 Ready，非简单路径）的攻击种子。"""
    return {
        "description": "漏洞导向合法边界种子",
        "state_path": ["Init", "Ready", "Playing", "Init"],
        "messages": [
            {"method": "DESCRIBE",
             "headers": {"Accept": "application/sdp", "CSeq": "1"}, "body": ""},
            {"method": "OPTIONS", "headers": {"CSeq": "2"}, "body": ""},
            {"method": "SETUP",
             "headers": {"CSeq": "3", "Transport": "RTP/AVP;unicast;client_port=0-0"},
             "body": ""},
            {"method": "PLAY",
             "headers": {"CSeq": "4", "Session": "{{session_id}}",
                         "Range": "npt=0.000-"}, "body": ""},
            {"method": "PAUSE",
             "headers": {"CSeq": "5", "Session": "{{session_id}}"}, "body": ""},
            {"method": "TEARDOWN",
             "headers": {"CSeq": "6", "Session": "{{session_id}}"}, "body": ""},
        ],
    }


def test_select_seeds_no_vulns_degrades_gracefully():
    b = _bundle()
    seeds = select_seeds(b)  # vulns=None, llm=None
    assert seeds, "无漏洞时也应返回 ①+② 的种子（降级不失效）"
    tags = {s.generated_by for s in seeds}
    assert "rule-based:edge-cover" in tags
    assert "rule-based:generic-danger" in tags


def test_select_seeds_includes_vuln_pattern_boundary_candidates():
    """接线1：select_seeds 无漏洞库/LLM 也叠加 vuln_pattern 桶的序列型边界候选。"""
    b = _bundle()
    seeds = select_seeds(b)  # vulns=None, llm=None
    tags = {s.generated_by for s in seeds}
    assert "rule-based:boundary-probe" in tags  # vuln_pattern 边界候选已叠加
    # 序列型漏洞模式（同 track 双 SETUP）的候选应出现（≥2 个 SETUP）
    seqs = [tuple(m.method for m in s.messages) for s in seeds]
    assert any(seq.count("SETUP") >= 2 for seq in seqs)


def test_select_seeds_with_vulns_returns_more():
    b = _bundle()
    vulns = load_vuln_kb(protocol="rtsp")
    assert vulns, "需读到真实漏洞库"
    llm = StubLLMClient(response=[_legal_attack_seed()])
    without = select_seeds(b)
    with_vulns = select_seeds(b, vulns=vulns, llm=llm)
    assert len(with_vulns) > len(without), "有漏洞时应叠加 ③ 产出更多种子"


def test_select_seeds_preserves_boundary_diversity():
    """去重签名必须含头部取值，否则同方法序列、不同字段取值会被压扁。

    直接测 dedupe_seeds 的签名行为（不再依赖层②产合成边界值——2.3 边界取值已移除）。
    """
    from core.fused.downstream.selector import dedupe_seeds
    from core.models import SeedCorpus, SeedMessage
    mk = lambda cseq: SeedCorpus(  # noqa: E731
        protocol="rtsp",
        messages=[SeedMessage("SETUP", {"CSeq": cseq, "Transport": "RTP/AVP"}, "")])
    s0 = mk("0")
    s1 = mk("-1")
    smax = mk("2147483647")
    sempty = mk("")
    # 同方法序列 + 不同 CSeq 取值 → 不去重（4 条边界取值全部保留）
    assert len(dedupe_seeds([s0, s1, smax, sempty])) == 4
    # 完全相同 → 去重为 1
    assert len(dedupe_seeds([s0, mk("0")])) == 1


def test_select_seeds_respects_max_seeds():
    """max_seeds 上限截断（设计 §六-4 种子总数可控）。"""
    b = _bundle()
    assert len(select_seeds(b)) > 10
    capped = select_seeds(b, max_seeds=10)
    assert len(capped) == 10


def test_vuln_proximity_score_orders_layers():
    """漏洞接近度打分：边界候选 legal > 边界候选 illegal > 序列型危险 > 其他危险
    > 结构覆盖 > 黄金路径（协议无关，只依赖 generated_by 标记）。"""
    from core.fused.downstream.selector import vuln_proximity_score
    from core.models import SeedCorpus, SeedMessage
    mk = lambda gb, desc="": SeedCorpus(  # noqa: E731
        protocol="rtsp", generated_by=gb, description=desc,
        messages=[SeedMessage("SETUP", {}, "")])
    ordered = [
        mk("rule-based:boundary-probe", "boundary-candidate double_setup legal(不同 track)"),
        mk("rule-based:boundary-probe", "boundary-candidate double_setup illegal(同 track)"),
        mk("rule-based:boundary-probe-vuln-field", "vuln-field long_value x legal"),
        mk("rule-based:generic-danger", "generic-danger self-loop repeat SETUP"),
        mk("rule-based:generic-danger", "generic-danger other"),
        mk("rule-based:edge-cover", "edge-cover path"),
        mk("rule-based:canonical-session", "canonical session"),
    ]
    scores = [vuln_proximity_score(s) for s in ordered]
    assert scores == sorted(scores, reverse=True), f"打分应严格递减，实际 {scores}"
    assert vuln_proximity_score(ordered[0]) == 100
    assert vuln_proximity_score(ordered[1]) == 95  # illegal 端略降（可能 dry-run 崩）


def test_prioritize_seeds_sorts_descending_and_truncates():
    """聚焦排序：漏洞边界候选排最前；max_seeds 截断时丢弃低分（结构覆盖/黄金路径）。"""
    from core.fused.downstream.selector import prioritize_seeds
    from core.models import SeedCorpus, SeedMessage
    mk = lambda gb, desc="": SeedCorpus(  # noqa: E731
        protocol="rtsp", generated_by=gb, description=desc,
        messages=[SeedMessage("SETUP", {}, "")])
    edge = mk("rule-based:edge-cover", "edge-cover path")
    canon = mk("rule-based:canonical-session", "canonical")
    boundary = mk("rule-based:boundary-probe", "boundary legal")
    danger = mk("rule-based:generic-danger", "self-loop SETUP")
    # 故意乱序输入，排序后边界候选应排最前
    ranked = prioritize_seeds([canon, edge, danger, boundary])
    assert ranked[0].generated_by == "rule-based:boundary-probe"
    # 截断前 2 条 → 只保留边界候选 + 序列型危险
    capped = prioritize_seeds([canon, edge, danger, boundary], max_seeds=2)
    assert len(capped) == 2
    assert {s.generated_by for s in capped} == {
        "rule-based:boundary-probe", "rule-based:generic-danger"}
