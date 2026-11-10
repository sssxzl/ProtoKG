"""tests/test_vuln_vector.py —— 漏洞模式向量库（Phase 3，GLMFuzz 借鉴）。"""
from __future__ import annotations

from core.fused.extraction.vuln_vector import (
    pattern_semantic_text, retrieve_similar_patterns, _load_patterns,
    migrate_vuln_patterns, protocols_with_vuln_kb,
)


def test_pattern_semantic_text_joins_fields():
    pat = {
        "action": "double_setup",
        "boundary": {"illegal": "同 track 双 SETUP"},
        "mutation_hint": "连续两次",
        "cwe": "CWE-416",
    }
    text = pattern_semantic_text(pat)
    assert "double_setup" in text
    assert "同 track 双 SETUP" in text
    assert "CWE-416" in text


def test_pattern_semantic_text_boundary_none():
    pat = {"action": "long_value", "boundary": None,
           "mutation_hint": "超长", "cwe": "CWE-121"}
    text = pattern_semantic_text(pat)
    assert "long_value" in text and "超长" in text


def test_retrieve_similar_patterns_scores_desc():
    patterns = [{"action": "a"}, {"action": "b"}]
    vectors = [[1.0, 0.0], [0.0, 1.0]]

    def embed(ts):
        # query 含 "a" → [1,0]（更接近 a），否则 [0,1]
        return [[1.0, 0.0] if "a" in t else [0.0, 1.0] for t in ts]

    res = retrieve_similar_patterns("query a", patterns, vectors, embed, top_k=1)
    assert len(res) == 1
    assert res[0][1]["action"] == "a"
    assert res[0][0] >= 0  # 分数是余弦相似度


def test_retrieve_similar_patterns_empty():
    assert retrieve_similar_patterns("x", [], [], lambda ts: [[]], 5) == []
    assert retrieve_similar_patterns("x", [{"action": "a"}], [],
                                     lambda ts: [[1.0]], 5) == []


def test_load_patterns_returns_vuln_pattern_facts():
    """读真实 vuln facts 的 vuln_pattern（rtsp 数据已落盘）。"""
    patterns = _load_patterns("rtsp")
    assert len(patterns) == 23
    for p in patterns:
        assert "action" in p and "_subject" in p and p["_protocol"] == "rtsp"


# ============ 接线2：跨协议迁移 ============

def test_protocols_with_vuln_kb():
    protos = protocols_with_vuln_kb()
    assert "rtsp" in protos  # rtsp 有历史漏洞
    assert "smtp" in protos  # smtp 有历史漏洞


def test_migrate_vuln_patterns_returns_source_protocol():
    """跨协议迁移：检索结果带来源协议标记，且按相似度降序。"""
    results = migrate_vuln_patterns("重复建立会话触发释放后使用",
                                    source_protocols=["rtsp"], top_k_per=3)
    assert results
    assert all(p.get("_protocol") == "rtsp" for _score, p in results)
    scores = [s for s, _ in results]
    assert scores == sorted(scores, reverse=True)  # 降序


def test_migrate_vuln_patterns_defaults_to_all_sources():
    """未指定来源协议 → 默认所有有漏洞库的协议。"""
    results = migrate_vuln_patterns("超长字段溢出", top_k_per=2)
    assert results
    protos = {p.get("_protocol") for _s, p in results}
    assert protos  # 来源协议非空
