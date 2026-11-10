"""tests/test_seedgen.py —— seedgen.py 入口的漏洞边界候选接入（回归测试）。

固化「seedgen.py 必须包含漏洞导向层（序列型漏洞边界候选）」这一契约，防止再次出现
「seedgen.py 漏接漏洞导向层、导致历史漏洞知识不参与生成」的盲区。
"""
from __future__ import annotations

from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle
from scripts.seedgen import _load_profile, _derive_vuln_boundary_candidates


def _bundle():
    return assemble_bundle(load_fact_views())


def test_seedgen_includes_vuln_boundary_candidates():
    """seedgen.py 的漏洞边界候选层必须产出来自 vuln_pattern 桶的边界种子。"""
    b = _bundle()
    profile = _load_profile("rtsp")
    cands = _derive_vuln_boundary_candidates(b, profile, "rtsp")
    assert cands, "seedgen.py 应产出漏洞边界候选（非空）"
    tags = {s.generated_by for s in cands}
    assert "rule-based:boundary-probe" in tags, "边界候选应带 boundary-probe 标签"
    # 序列型漏洞模式（同 track 双 SETUP）的候选应出现
    seqs = [tuple(m.method for m in s.messages) for s in cands]
    assert any(seq.count("SETUP") >= 2 for seq in seqs), \
        "边界候选应包含双 SETUP 序列"


def test_seedgen_vuln_candidates_filter_non_whitelisted_methods():
    """漏洞边界候选必须过滤掉白名单外的方法（避免漏洞数据里的垃圾方法混入）。"""
    b = _bundle()
    profile = _load_profile("rtsp")
    cands = _derive_vuln_boundary_candidates(b, profile, "rtsp")
    valid = set(b["methods"].keys())
    for s in cands:
        for m in s.messages:
            assert m.method in valid, f"候选方法 {m.method!r} 不在白名单内"


def test_seedgen_focused_prioritizes_boundary_candidates():
    """聚焦模式（--focused）契约：漏洞边界候选按漏洞接近度排在结构覆盖之前。

    固化「实验教训：种子过多摊薄变异预算、稀释漏洞导向层」——排序后 fuzzer 优先
    变异离漏洞触发点最近的种子（边界候选 legal 端），而非结构覆盖的合法种子。
    """
    from core.fused.downstream.selector import prioritize_seeds
    from core.fused.downstream.edge_cover import edge_cover
    b = _bundle()
    profile = _load_profile("rtsp")
    vuln_cands = _derive_vuln_boundary_candidates(b, profile, "rtsp")
    valid = set(b["methods"].keys())
    trans = [t for t in b["transitions"] if t[1] in valid]
    struct = edge_cover(trans, b.get("required_headers"), b.get("headers"),
                        b.get("message_instances"), protocol="rtsp",
                        method_order=b.get("method_order"))
    ranked = prioritize_seeds(vuln_cands + struct)
    assert ranked, "聚焦排序后应非空"
    assert ranked[0].generated_by == "rule-based:boundary-probe", \
        "排序后第一条应是漏洞边界候选（boundary-probe）"
    # 所有边界候选都应排在任意结构覆盖种子之前
    last_boundary = max(i for i, s in enumerate(ranked)
                        if s.generated_by == "rule-based:boundary-probe")
    first_struct = min(i for i, s in enumerate(ranked)
                       if s.generated_by == "rule-based:edge-cover")
    assert last_boundary < first_struct, "漏洞边界候选应整体排在结构覆盖之前"
