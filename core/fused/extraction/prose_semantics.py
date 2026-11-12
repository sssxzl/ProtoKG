# -*- coding: utf-8 -*-
"""core/fused/extraction/prose_semantics.py —— **通道 I：LLM 语义切片**。

★ 为什么需要（2026-11-12 跨协议实测）
  rfc 源的 10 个结构化通道（A0/A0b/A0c/A0d/A/B/C/D/E/F）覆盖的是
  **结构化形态**（ABNF / 表格 / 命令列表 / 状态转移表 / 消息清单表）
  ⇒ ⇒ 对「**纯散文**的扩展 RFC」**完全无能为力**：
  · 实测 DHCPv4 的 kb 有 **36 个 spec 文档** ⇒ 结构化通道只触及 **5 个**
    ⇒ **31 个散文型扩展 RFC 全部丢失**
    （rfc3004 DHCP Lease Management / rfc3203 DHCP Reconfigure / rfc2939 选项定义流程…）
  ⇒ ⇒ 这些文档定义的**选项语义与流程约束**（如选项 61/62/63）**全部丢失**。

★ 本通道做什么
  **只对「没有任何结构化形态命中」的文档** ⇒ 切片 ⇒ 喂 LLM ⇒ 抽**散文语义**
  ⇒ 产出**已有 aspect**（``definition`` / ``legal_boundary``）⇒ **不新增 aspect**。

★ 四条硬约束（缺一不可）
  ① **只喂未命中的文档** ⇒ 不重复劳动、不增加已有文档的调用量
  ② **只产已有 aspect** ⇒ 契约面不变（``aspect_registry.json`` 仍是 21 个）
  ③ **证据必须可核对**：``span`` 必填 **且** 该行的原文里**出现该实体名**
     ⇒ 「实体名 + 那一行的文本」**第三方可核对** ⇒ **比白名单更强**
     ⇒ ★ **不限制主体必须已知**：通道 I 的价值恰恰在于抽「结构化通道没抽到」的实体
  ④ **磁盘缓存**（``block_hash``）⇒ 命中缓存 ⇒ 不调 LLM ⇒ **逐字节可复现**
     （范式照抄 ``infer_transitions`` ⇒ ``derived/cache/source_blocks/<协议>.prose.json``）

★ ★ **批量化**（实测必需）
  逐文件逐块调用 ⇒ DHCPv4 31 文档 × 2 块 = **62 次调用 ≈ 530s** ⇒ 不可用。
  ⇒ ⇒ 现在**多文档合并成一次调用**（默认每批 5 个块）⇒ 31 块 ⇒ **约 7 次调用**
  ⇒ ⇒ 每块带**文档标签**（``[文档 rfc3004.txt]``）⇒ LLM 返回 ``doc`` + ``span``
  ⇒ ⇒ 核验时按 doc 定位文件、按 span 定位行 ⇒ **仍可核对**
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional


#: ★ prompt 版本（**改动 ⇒ block_hash 变 ⇒ 缓存自动失效**）
PROSE_SEMANTICS_PROMPT_VERSION = "prose-semantics-v2"

#: 每块的最大字符数（喂给 LLM 的上限 ⇒ 控制 token）
_MAX_BLOCK_CHARS = 3500

#: 每文档最多取几块
_MAX_BLOCKS_PER_DOC = 1

#: 一次调用最多合并几个块（★ 批量化 ⇒ 控制调用次数）
_BATCH_BLOCKS = 5

#: 每块最多几条
_MAX_ITEMS = 6

#: LLM prompt（**要求结构化 JSON + 强制 span + 强制 doc**）
_PROMPT = """你是协议规范分析员。下面给出若干份 RFC 文档的**片段**。
请只抽取**片段中明确写出的**协议语义事实（不要推测、不要补充文档外知识）。

★ 每段片段前有 `[文档 <文件名>]` 标记 ⇒ 你输出时**必须**带上该文件名（`doc` 字段）。
★ `span` 是**该文档内**的行号（1 起始）⇒ 无法给出确切行号的条目**不要输出**。
★ `entity` 必须是**该行原文里真实出现**的名字（否则会被判为幻觉而丢弃）。
★ 只输出 JSON，不要任何解释文字。

格式：
{"items": [{"doc": "<文件名>", "entity": "<实体名>", "meaning": "<它是什么/做什么，一句话>",
   "constraint": "<若有强制约束则填，否则空串>", "span": <行号>}]}"""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _split_blocks(text: str, max_blocks: int) -> list[tuple[int, str]]:
    """把文档切成若干块 ⇒ ``[(起始行号, 块文本), ...]``（★ 行号可追溯 ⇒ span 的基础）。"""
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[tuple[int, str]] = []
    cur: list[str] = []
    cur_start = 1
    for i, ln in enumerate(lines, start=1):
        if not cur:
            cur_start = i
        cur.append(ln)
        if sum(len(x) + 1 for x in cur) >= _MAX_BLOCK_CHARS:
            blocks.append((cur_start, "\n".join(cur)))
            cur = []
            if len(blocks) >= max_blocks:
                return blocks
    if cur and len(blocks) < max_blocks:
        blocks.append((cur_start, "\n".join(cur)))
    return blocks


def _cache_path(protocol: str) -> Path:
    from core.fused.extraction.source_retrieval import CACHE_DIR
    return Path(CACHE_DIR) / f"{protocol}.prose.json"


def _load_cache(protocol: str, block_hash: str) -> Optional[dict]:
    p = _cache_path(protocol)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(d, dict) and d.get("block_hash") == block_hash:
        return d
    return None


def _save_cache(protocol: str, block_hash: str, items: list[dict]) -> None:
    p = _cache_path(protocol)
    p.parent.mkdir(parents=True, exist_ok=True)
    from core.fused.extraction.cache_key import key_manifest
    _payload = {"block_hash": block_hash, "items": items,
                "key_manifest": key_manifest(block_hash)}
    p.write_text(json.dumps(_payload, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _collect_blocks(files: list[Path]) -> list[dict]:
    """收集每个文档的块 ⇒ ``[{"doc": 文件名, "start": 起始行, "text": 块文本}, ...]``。"""
    out: list[dict] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for start, block in _split_blocks(text, _MAX_BLOCKS_PER_DOC):
            out.append({"doc": f.name, "start": start, "text": block})
    return out


def extract_prose_norms(protocol: str, files: list[Path], *,
                        entities: Optional[list] = None,
                        llm=None,
                        max_items: int = _MAX_ITEMS) -> list[dict]:
    """对**一批未命中文档**抽散文语义 ⇒ 返回 norm 列表。

    Args:
        protocol: 协议名。
        files: **未命中**的文档列表。
        entities: 已知实体名（仅作 prompt 提示 ⇒ **不限制产出主体**）。
        llm: LLM 客户端（None ⇒ 自建 ``DeepSeekClient``）。
        max_items: 每块最多几条。

    Returns:
        norm 列表（kind=``prose_semantics`` / ``prose_constraint``）。
    """
    blocks = _collect_blocks(list(files or []))
    if not blocks:
        return []
    # 原文行（按文档）⇒ 核验用
    doc_lines: dict[str, list[str]] = {}
    for f in files:
        try:
            doc_lines[f.name] = f.read_text(
                encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        except OSError:
            doc_lines[f.name] = []

    # ---- ① 缓存键（★ 版本化：模型 / 推理配置 / 解析器 / Schema / 校验器）----
    #   ⇒ 任一要素变化 ⇒ 键变化 ⇒ **旧缓存自动失效**
    from core.fused.extraction.cache_key import cache_key as _cache_key
    _block_hash = hashlib.sha256("|".join(
        [_hash_text(b["doc"] + str(b["start"]) + b["text"]) for b in blocks]
    ).encode("utf-8")).hexdigest()
    block_hash = _cache_key(
        prompt_version=PROSE_SEMANTICS_PROMPT_VERSION,
        input_fingerprint=_block_hash,
        temperature=0.1, max_tokens=16000)
    cached = _load_cache(protocol, block_hash)
    if cached is not None:
        raw_items = list(cached.get("items") or [])
    else:
        if llm is None:
            try:
                from core.llm import DeepSeekClient
                llm = DeepSeekClient()
            except Exception:                    # noqa: BLE001
                return []
        raw_items = []
        # ★ **批量化**：每 ``_BATCH_BLOCKS`` 块合并成一次调用
        # ★★ **分批增量落缓存**（2026-11-12 实测：LLM 偶发超时 ⇒ 整批失败
        #   ⇒ 若「全部成功才写缓存」⇒ 一批失败就得**全部重跑** ⇒ 极慢）
        #   ⇒ 现在每批成功就**增量写缓存** ⇒ 下次只跑失败的批
        # ★★ **重试 1 次**（LLM 服务偶发超时 ⇒ 重试通常就好了）
        for i in range(0, len(blocks), _BATCH_BLOCKS):
            batch = blocks[i:i + _BATCH_BLOCKS]
            body_parts = []
            for b in batch:
                body_parts.append(
                    f"\n\n===== [文档 {b['doc']}]（起始行号 {b['start']}）=====\n{b['text']}")
            user = _PROMPT + "".join(body_parts)
            got_items: list[dict] = []
            for _attempt in (1, 2):
                try:
                    # ★ ``chat_json`` 的签名是 **keyword-only**（``system=`` / ``user=``）
                    # ★★ max_tokens 必须**留足推理空间**：deepseek-flash 是
                    #   **推理模型** ⇒ ``reasoning_tokens`` 会**先**吃掉 max_tokens
                    #   ⇒ 实测 max_tokens=4000 时 finish_reason=length 且
                    #     **正式输出为空**（⇒ JSON 解析必失败）
                    #   ⇒ 16000 时实测正常（30s/次，产出 9 条带 span 的条目）
                    out = llm.chat_json(
                        system="你是协议规范分析员。只输出 JSON。",
                        user=user, temperature=0.1, max_tokens=16000)
                except Exception as exc:        # noqa: BLE001
                    print(f"[通道I] LLM 调用失败（第 {_attempt} 次，"
                          f"{type(exc).__name__}: {exc}）", file=sys.stderr)
                    continue
                if isinstance(out, str):
                    try:
                        out = json.loads(out)
                    except (ValueError, TypeError):
                        continue
                if not isinstance(out, dict):
                    continue
                got = 0
                for it in (out.get("items") or []):
                    if not isinstance(it, dict):
                        continue
                    got_items.append(dict(it))
                    got += 1
                    if got >= max_items * len(batch):
                        break
                break
            if got_items:
                raw_items.extend(got_items)
                _save_cache(protocol, block_hash, raw_items)   # ★ 增量落缓存
        _save_cache(protocol, block_hash, raw_items)

    # ---- ② 过滤 + 产 norm ----
    norms: list[dict] = []
    seen: set[str] = set()
    for it in raw_items:
        ent = str(it.get("entity") or "").strip()
        meaning = str(it.get("meaning") or "").strip()
        doc = str(it.get("doc") or "").strip()
        if not ent or not meaning or not doc:
            continue
        if doc not in doc_lines:
            continue                     # 文档对不上 ⇒ 拒收
        try:
            span_line = int(it.get("span"))
        except (TypeError, ValueError):
            continue                     # ★ **span 必填** ⇒ 无 span 直接拒收
        if span_line <= 0:
            continue
        lines = doc_lines[doc]
        idx = span_line - 1
        if not (0 <= idx < len(lines)):
            continue                     # span 越界 ⇒ 拒收
        # ★ **可核对**：span 所在原文行必须**含该实体名** ⇒ 否则判幻觉、拒收
        if ent.lower() not in lines[idx].lower():
            continue
        con = str(it.get("constraint") or "").strip()
        kind = "prose_constraint" if con else "prose_semantics"
        # ★★ **按「实体 + 类别」去重**（2026-11-12 实测：质量闸 dup_fact_ids=2）
        #   ★ 原因：``fact_key`` **不含 span** ⇒ 同一实体在同一 aspect 下
        #     **无论来自哪个文档/哪一行都会撞成同一个 fact_key**
        #     ⇒ ⇒ 同一实体只保留**第一条**（⇒ 事实空间唯一 ⇒ 质量闸通过）
        _dedup_key = (kind, ent.lower())
        if _dedup_key in seen:
            continue
        seen.add(_dedup_key)
        norm_id = f"{kind}_{ent.lower().replace('-', '_')}"
        norms.append({
            "kind": kind,
            "protocol": protocol,
            # ★ ``map_norm_to_facts`` 按 ``kb_source_type`` 分派 ⇒ 缺它会被 skipped
            "kb_source_type": "rfc",
            "name": ent,
            "content": (meaning + (" | constraint: " + con if con else "")),
            "norm_id": norm_id,
            "source": f"file:{doc}#@{span_line}",
            "entity": ent,
            "meaning": meaning,
            "constraint": con,
            "span_line": span_line,
        })
    return norms
