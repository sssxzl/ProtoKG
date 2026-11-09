# -*- coding: utf-8 -*-
"""core/fused/source_retrieval.py —— AutoSeeder Section III-A：基于检索的相关代码提取。

对齐 AutoSeeder (INFOCOM 2026) 的「retrieval-based relevant code extraction」：
  1. 切片 + 向量化：把协议实现源码切成 chunk，用 embedding 编码成向量；
  2. 向量检索：7 条协议无关的通用 query（描述「状态机/转移/事件处理/错误处理/生命周期」
     等通用概念，不含任何协议名）编码成向量，取余弦相似度 top-k；
  3. 后处理：跨 query 去重 → 按「文件名+位置」重排序恢复上下文 → 按 token 上限分块。

与 ProtocolGPT 思路的区别：这里【不写任何协议特定正则】，query 是协议无关的通用
自然语言，换协议零配置（正是 AutoSeeder 的「低成本迁移」卖点）。

embedding 可插拔 + 缓存：
  - 优先 sentence-transformers（真实语义，如 unixcoder / all-MiniLM，装在 /e/python）；
  - 无 sentence-transformers 时降级字符 n-gram（仅让流程跑通，无语义）；
  - 检索结果缓存到 derived/source_blocks/<protocol>.json，主流程读缓存避免重复检索。
"""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path
from typing import Any, Optional

from core import paths

#: AutoSeeder Fig.2 的 7 条通用 query（协议无关，描述状态处理的通用维度）
AUTOSEEDER_QUERIES: list[str] = [
    "Locate all code segments defining the protocol state machine, including "
    "state identifiers, initialization logic, and structures or variables used "
    "for tracking states.",
    "Identify conditions, events, or input messages that trigger state "
    "transitions in the protocol, along with the corresponding logic "
    "implementing these transitions.",
    "Retrieve mappings or logic connecting client messages to protocol state "
    "changes, focusing on how specific message types affect the server's state "
    "machine.",
    "Locate all event handlers, callback functions, or interrupt routines "
    "responsible for managing or triggering state transitions in the protocol "
    "server.",
    "Retrieve any code related to protocol state machine implementation, state "
    "transitions, client message handling, or state monitoring during operation.",
    "Identify error-handling logic, including mechanisms for transitioning to "
    "and recovering from error states, as well as their integration into the "
    "state machine.",
    "Retrieve code governing protocol state transitions during key lifecycle "
    "events, such as session setup, authentication, data exchange, and "
    "termination.",
]

#: 可当文本读的源码后缀（协议实现源码目录）
_SRC_EXTS = (".cpp", ".cc", ".cxx", ".c", ".hh", ".hpp", ".h")

#: 切片参数（字符级滑动窗口，替代 LangChain LanguageAwareSplitter 的轻量实现）
_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 200

#: 缓存目录（绝对路径，走统一 paths 解析）
CACHE_DIR = paths.model_root() / "source_blocks"


# ===========================================================================
# 切片
# ===========================================================================

def slice_code(src_dir: Path) -> list[dict]:
    """把协议实现源码切成 chunk，返回 [{file, idx, text}]（保留文件来源便于溯源）。

    递归遍历子目录（rglob）：多目标协议的源码常按子目录组织（如 ftp/bftpd/、
    sip/kamailio/），只扫顶层会漏掉全部源码。file 用相对 src_dir 的路径，保留
    子目录信息避免同名文件（不同子目录的 main.c）混淆。
    """
    chunks: list[dict] = []
    for f in sorted(p for p in src_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in _SRC_EXTS):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(src_dir)).replace("\\", "/")
        step = _CHUNK_SIZE - _CHUNK_OVERLAP
        for i, start in enumerate(range(0, len(text), step)):
            piece = text[start:start + _CHUNK_SIZE]
            if not piece.strip():
                continue
            chunks.append({"file": rel, "idx": i, "start": start, "text": piece})
            if start + _CHUNK_SIZE >= len(text):
                break
    return chunks


# ===========================================================================
# embedding（可插拔）
# ===========================================================================

def _get_sentence_transformer_embedder(model_name: str = "all-MiniLM-L6-v2"):
    """尝试用 sentence-transformers（真实语义 embedding）。装于 /e/python。

    优先走国内镜像 hf-mirror.com（HuggingFace 直连常 SSL 失败），可用环境变量
    HF_ENDPOINT 覆盖。
    """
    try:
        import os
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        return lambda texts: model.encode(
            texts, normalize_embeddings=True).tolist()
    except Exception:
        return None


def _ngram_embed(text: str, dim: int = 384) -> list[float]:
    """字符 3-gram 哈希 → 归一化向量（降级，无语义，仅让流程跑通）。

    ★ 用 zlib.crc32（确定性）而非内置 hash()：内置 hash 受 PYTHONHASHSEED 影响，
    跨进程随机，导致 code_blocks 检索结果跨进程不同 → LLM 结果缓存永远 miss。
    """
    vec = [0.0] * dim
    s = re.sub(r"\s+", "", text.lower())
    for i in range(len(s) - 2):
        h = zlib.crc32(s[i:i + 3].encode("utf-8")) & 0x7FFFFFFF
        vec[h % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _build_embedder():
    """返回 embed(texts)->list[vectors] 的可调用；优先真实 embedding，降级 n-gram。"""
    fn = _get_sentence_transformer_embedder()
    if fn is not None:
        return fn, "sentence-transformers"
    return (lambda texts: [_ngram_embed(t) for t in texts]), "ngram-fallback"


# ===========================================================================
# 检索 + 后处理
# ===========================================================================

def _retrieve_all(chunks: list[dict], embed, top_k: int) -> list[dict]:
    """7 条 query 各自取 top-k，合并（后处理前）。"""
    if not chunks:
        return []
    chunk_vecs = embed([c["text"] for c in chunks])
    hit_idx: set[int] = set()
    for q in AUTOSEEDER_QUERIES:
        qv = embed([q])[0]
        scored = sorted(
            ((_cosine(qv, v), i) for i, v in enumerate(chunk_vecs)),
            key=lambda x: -x[0],
        )[:top_k]
        for _, i in scored:
            hit_idx.add(i)
    return [chunks[i] for i in sorted(hit_idx)]


def _postprocess(blocks: list[dict], max_block_chars: int = 6000) -> list[dict]:
    """后处理：去重 → 按(文件名,位置)重排序 → 按 token 上限合并分块。"""
    # 去重（按 文件+起始位置）
    seen: set = set()
    uniq: list[dict] = []
    for b in blocks:
        key = (b["file"], b["start"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    # 按文件名 + 文件内位置重排序（恢复被相似度排序打乱的上下文）
    uniq.sort(key=lambda b: (b["file"], b["start"]))
    # 按字符上限合并成块（每个块带来源文件，便于溯源）
    out: list[dict] = []
    cur_parts: list[str] = []
    cur_files: list[str] = []
    cur_len = 0
    for b in uniq:
        if cur_len + len(b["text"]) > max_block_chars and cur_parts:
            out.append({"text": "\n\n".join(cur_parts), "files": sorted(set(cur_files))})
            cur_parts, cur_files, cur_len = [], [], 0
        cur_parts.append(b["text"])
        cur_files.append(b["file"])
        cur_len += len(b["text"])
    if cur_parts:
        out.append({"text": "\n\n".join(cur_parts), "files": sorted(set(cur_files))})
    return out


def retrieve_state_relevant_code(src_dir: Path, protocol: str,
                                 top_k: int = 8) -> list[dict]:
    """AutoSeeder III-A 完整流程：切片 → 7 query 检索 → 后处理 → 代码块列表。

    优先读缓存 derived/source_blocks/<protocol>.json；无缓存则实时检索（真实
    embedding 若不可用则降级 n-gram）。
    """
    cache = CACHE_DIR / f"{protocol}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    embed, _kind = _build_embedder()
    blocks = _postprocess(_retrieve_all(slice_code(src_dir), embed, top_k))
    return blocks


def build_cache(src_dir: Path, protocol: str, top_k: int = 8,
                model_name: str = "all-MiniLM-L6-v2") -> list[dict]:
    """离线构建检索缓存（在装有 sentence-transformers 的解释器下运行）。

    产出的缓存供主流程 retrieve_state_relevant_code 直接读取，避免跨解释器重复检索。
    """
    embed = _get_sentence_transformer_embedder(model_name)
    if embed is None:
        raise RuntimeError("sentence-transformers 不可用，无法构建语义检索缓存")
    blocks = _postprocess(_retrieve_all(slice_code(src_dir), embed, top_k))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{protocol}.json").write_text(
        json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    return blocks


__all__ = [
    "AUTOSEEDER_QUERIES",
    "slice_code",
    "retrieve_state_relevant_code",
    "build_cache",
]
