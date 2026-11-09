# -*- coding: utf-8 -*-
"""core/fused/vuln_vector.py —— 漏洞模式向量库（Phase 3，借鉴 GLMFuzz）。

复用 core.fused.extraction.source_retrieval 的 embedding 基础设施（sentence-transformers 优先、
n-gram 降级 + cosine），把结构化漏洞模式（vuln_pattern）向量化，支撑两个检索场景：

  1. 同协议新 CVE：新漏洞描述 → 检索相似历史漏洞模式 → 复用其 boundary/action；
  2. 跨协议迁移：新协议无漏洞库 → 检索其他协议的相似漏洞模式（如 RTSP「同 track 双
     SETUP UAF」→ 检索出「重复建立会话」类模式）→ 迁移生成边界种子（护城河）。

语义文本 = action + boundary.illegal + mutation_hint + cwe（这几项最能刻画「漏洞靠
什么触发」）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core import paths
from core.fused.extraction.source_retrieval import _build_embedder, _cosine


def pattern_semantic_text(pat: dict) -> str:
    """漏洞模式 → 语义文本（用于 embedding）。"""
    boundary = pat.get("boundary") or {}
    illegal = boundary.get("illegal", "") if isinstance(boundary, dict) else ""
    parts = [
        str(pat.get("action", "")),
        illegal,
        str(pat.get("mutation_hint", "")),
        str(pat.get("cwe", "")),
    ]
    return " ".join(x for x in parts if x)


def _load_patterns(protocol: str) -> list[dict]:
    """读 per_source/<protocol>/vuln/facts/vuln.jsonl 的 vuln_pattern fact。"""
    facts_file = paths.per_source_root(protocol) / "vuln" / "facts" / "vuln.jsonl"
    if not facts_file.exists():
        return []
    patterns: list[dict] = []
    for line in facts_file.read_text(encoding="utf-8").splitlines():
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        fk = v.get("fact_key") or {}
        if fk.get("aspect") != "vuln_pattern":
            continue
        claims = v.get("all_claims") or []
        if not claims:
            continue
        data = (claims[0].get("value") or {}).get("data")
        if isinstance(data, dict):
            d = dict(data)
            d["_subject"] = (fk.get("subject") or {}).get("name", "")
            d["_protocol"] = protocol
            patterns.append(d)
    return patterns


def _cache_path(protocol: str) -> Path:
    return paths.model_root() / "vuln_pattern_vectors" / f"{protocol}.json"


def build_vuln_pattern_vectors(protocol: str, use_cache: bool = True):
    """建漏洞模式向量库：读 vuln_pattern fact → embedding → 缓存。

    Returns:
        (patterns: list[dict], vectors: list[list[float]], embedder_name: str)
        无漏洞模式时返回 ([], [], "empty")。
    """
    cache = _cache_path(protocol)
    if use_cache and cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            return data["patterns"], data["vectors"], data.get("embedder", "")
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    patterns = _load_patterns(protocol)
    if not patterns:
        return [], [], "empty"
    embed, name = _build_embedder()
    texts = [pattern_semantic_text(p) for p in patterns]
    vectors = embed(texts)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(
        {"patterns": patterns, "vectors": vectors, "embedder": name},
        ensure_ascii=False), encoding="utf-8")
    return patterns, vectors, name


def retrieve_similar_patterns(query_text: str, patterns: list[dict],
                              vectors: list, embed, top_k: int = 5) -> list[tuple]:
    """核心检索：query 文本 → top-k 相似漏洞模式（cosine 降序）。

    Returns:
        [(score: float, pattern: dict), ...]
    """
    if not patterns or not vectors:
        return []
    qv = embed([query_text])[0]
    scored = sorted(
        ((_cosine(qv, v), p) for v, p in zip(vectors, patterns)),
        key=lambda x: -x[0],
    )[:top_k]
    return scored


def retrieve_for_protocol(query_text: str, protocol: str, top_k: int = 5) -> list[tuple]:
    """高层封装：在 <protocol> 的漏洞模式库里检索相似模式（建库 + embed + 检索）。"""
    patterns, vectors, name = build_vuln_pattern_vectors(protocol)
    if not patterns:
        return []
    embed, _ = _build_embedder()
    return retrieve_similar_patterns(query_text, patterns, vectors, embed, top_k)


def retrieve_cross_protocol(query_text: str, protocols: list[str],
                            top_k_per: int = 3) -> list[tuple]:
    """跨协议迁移：在多个协议的漏洞模式库里检索相似模式，合并取 top_k。

    用于「新协议无漏洞库，从其他协议迁移漏洞知识」（多协议低成本迁移护城河）。
    Returns:
        [(score, pattern), ...] 跨协议按相似度降序，pattern 带 _protocol 标记来源协议。
    """
    merged: list[tuple] = []
    for proto in protocols:
        merged.extend(retrieve_for_protocol(query_text, proto, top_k=top_k_per))
    merged.sort(key=lambda x: -x[0])
    return merged


def protocols_with_vuln_kb() -> list[str]:
    """扫描 kb/ 下哪些协议有「历史漏洞」目录（即有漏洞库，可作迁移来源）。"""
    kb = paths.kb_root()
    if not kb.is_dir():
        return []
    protos = []
    for p in sorted(kb.iterdir()):
        if p.is_dir() and (p / paths.SOURCE_DIRS["vuln"]).is_dir():
            protos.append(p.name)
    return protos


def migrate_vuln_patterns(query_text: str, source_protocols: Optional[list] = None,
                          top_k_per: int = 3) -> list[tuple]:
    """跨协议迁移入口：检索相似漏洞模式（默认在所有有漏洞库的协议里）。

    query_text 描述目标协议的方法/字段/疑似危险点（如「重复建立会话」「超长字段」），
    返回可迁移的漏洞模式建议（action + boundary 结构 + 来源协议）。
    迁移的是「漏洞模式结构」（action/boundary 维度），具体协议字段值由目标协议 profile
    实例化。
    """
    if source_protocols is None:
        source_protocols = protocols_with_vuln_kb()
    return retrieve_cross_protocol(query_text, source_protocols, top_k_per=top_k_per)


__all__ = [
    "pattern_semantic_text",
    "build_vuln_pattern_vectors",
    "retrieve_similar_patterns",
    "retrieve_for_protocol",
    "retrieve_cross_protocol",
    "protocols_with_vuln_kb",
    "migrate_vuln_patterns",
]
