# -*- coding: utf-8 -*-
"""compare/vector_rag.py —— C 路：向量 RAG（MultiFuzz 式）。

完全绕过 A 路的结构化抽取（build_hub / assemble_bundle），直接对五源原始文档
切 chunk + embedding + 语义检索，把检索到的原文片段喂给 LLM。

⚠️ 骨架阶段：
  - chunk 策略 = 简单按字符数切分（TODO：按语义/段落切分）
  - embedding = dummy（字符 n-gram hash），仅让流程跑通（TODO：替换为真实语义
    embedding，如 sentence-transformers / bge 系列，安装到隔离环境）
  - 检索 = 简单关键词 overlap 打分（TODO：替换为真实向量相似度检索）
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

from compare.config import MODE_VECTOR_RAG, KB_ROOT, PROTOCOL
from compare.interface import KnowledgeRepresentation

# 五源目录（与 scripts/build_hub.py 的 KB_SOURCE_DIRS 对齐，同一份数据）
_SOURCE_DIRS = ("spec", "expert_note", "数据流量", "历史漏洞", "协议实现源码")

# 可当文本读取的扩展名（跳过 pcap/二进制等）
_TEXT_SUFFIXES = (".txt", ".md", ".json", ".jsonl", ".c", ".cpp", ".h", ".hpp",
                  ".py", ".cc", ".xml", ".yaml", ".yml", ".cfg", ".ini")

_CHUNK_SIZE = 800      # TODO: 调优 chunk 大小
_CHUNK_OVERLAP = 100


def _iter_text_files(kb_root: Path):
    """遍历五源目录，产出可读文本文件路径。"""
    for sub in _SOURCE_DIRS:
        d = kb_root / sub
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix.lower() in _TEXT_SUFFIXES:
                yield f


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def chunk_sources(kb_root: Path, size: int = _CHUNK_SIZE,
                  overlap: int = _CHUNK_OVERLAP) -> list[dict]:
    """把五源文档切成 chunk，返回 [{file, idx, text}]。"""
    chunks: list[dict] = []
    for f in _iter_text_files(kb_root):
        text = _read_text(f)
        if not text.strip():
            continue
        step = size - overlap
        for i, start in enumerate(range(0, len(text), step)):
            piece = text[start:start + size]
            if not piece.strip():
                continue
            chunks.append({"file": str(f), "idx": i, "text": piece})
            if start + size >= len(text):
                break
    return chunks


# ---------------------------------------------------------------------------
# dummy embedding / 检索（TODO：替换为真实语义 embedding + 向量检索）
# ---------------------------------------------------------------------------

def _dummy_embed(text: str, dim: int = 256) -> list[float]:
    """字符 3-gram 哈希 → 稀疏向量（仅让流程跑通，无语义）。"""
    vec = [0.0] * dim
    s = re.sub(r"\s+", "", text.lower())
    for i in range(len(s) - 2):
        h = int(hashlib.md5(s[i:i + 3].encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorRAG(KnowledgeRepresentation):
    """C 路：向量 RAG（原文 chunk 检索）。"""

    name = MODE_VECTOR_RAG

    def __init__(self, protocol: str, kb_root: Any = KB_ROOT,
                 resources: Optional[list] = None,
                 request_templates: Optional[dict] = None,
                 top_k: int = 6):
        self.protocol = protocol
        self.kb_root = Path(kb_root)
        self.resources = resources
        self.request_templates = request_templates
        self.top_k = top_k
        self.chunks: list[dict] = []
        self.embeddings: list[list[float]] = []

    def prepare(self) -> None:
        self.chunks = chunk_sources(self.kb_root)
        # TODO: 替换为真实 embedding（sentence-transformers/bge），并持久化向量索引
        self.embeddings = [_dummy_embed(c["text"]) for c in self.chunks]

    def retrieve(self, query: str) -> list[dict]:
        """按 query 取 top-k chunk（TODO：替换为真实向量检索）。"""
        if not self.chunks:
            return []
        q = _dummy_embed(query)
        scored = sorted(
            enumerate(self.embeddings),
            key=lambda iv: _dot(q, iv[1]),
            reverse=True,
        )[:self.top_k]
        return [self.chunks[i] for i, _ in scored]

    def render_prompt(self, task: dict[str, Any]) -> tuple[str, str]:
        protocol = task.get("protocol", self.protocol)
        n_seeds = task.get("n_seeds", 20)
        # TODO: query 由 task 构造（协议 + 待生成消息类型），当前用协议名 + 通用目标
        query = f"{protocol} 消息格式 字段 状态机 请求序列 种子生成"
        retrieved = self.retrieve(query)

        context = "\n\n".join(
            f"[片段 {i + 1}（来源 {c['file']}）]\n{c['text']}"
            for i, c in enumerate(retrieved)
        ) or "（无检索结果）"

        system = f"你是 {protocol} 协议 fuzz 测试专家，基于提供的协议资料生成合法测试用例。"
        user = f"""[协议资料（检索自知识库，供参考）]
{context}

[生成目标]
- 协议: {protocol}
- 生成 {n_seeds} 个会话种子，每个是完整有序 message 列表

[输出要求]
返回 JSON 对象（不要用 markdown 代码块包裹），格式：
{{"seeds": [
  {{"description": "...", "url": "rtsp://127.0.0.1:8554/<流名>", "state_path": ["Init", ...], "messages": [
    {{"method": "DESCRIBE", "url": "rtsp://127.0.0.1:8554/<流名>", "headers": {{"CSeq": "1", "Accept": "application/sdp"}}, "body": ""}}
  ]}}
]}}
要求 method/字段/状态迁移参照上方协议资料。"""
        return system, user
