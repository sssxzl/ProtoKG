# -*- coding: utf-8 -*-
"""core/fused/extraction/prose_semantics.py —— **通道 I：LLM 语义切片**。

★ 为什么需要（2026-11-12 跨协议实测）
  rfc 源的 10 个结构化通道（A0/A0b/A0c/A0d/A/B/C/D/E/F）覆盖的是
  **结构化形态**（ABNF / 表格 / 命令列表 / 状态转移表 / 消息清单表）
  ⇒ ⇒ 对「**纯散文**的扩展 RFC」**完全无能为力**
  （实测 DHCPv4 的 36 个 spec 文档 ⇒ 结构化通道只触及 5 个 ⇒ 31 个丢失）。

★ 结构：**切块 + 共享内核**（★ 2026-11-12 第二批重构）
  · `_extract_blocks(protocol, blocks, ...)` —— 共享内核（缓存 / 批量化 /
    LLM 调用 / 运行保护 / 过滤 / 产 norm 全在这里）
  · `extract_prose_norms(protocol, files, ...)` —— **按文档**切块
  · `extract_window_norms(protocol, files, ...)` —— **按段落**切块
  ⇒ ⇒ 两个入口**只在切块粒度上不同** ⇒ ⇒ 缓存 / 批处理 / 运行保护完全同源。

★ 四条硬约束
  ① **只喂未充分覆盖的文档 / 段落** ⇒ 不重复劳动
  ② **只产已有 aspect** ⇒ 契约面不变（aspect 数量仍是 21）
  ③ **证据必须可核对**：span 必填 **且** 该行原文必须出现所声称的实体名
  ④ **磁盘缓存**（版本化缓存键）⇒ 命中缓存 ⇒ 不调 LLM ⇒ 逐字节可复现
"""
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

#: ★ prompt 版本（改动 ⇒ 缓存键变 ⇒ 自动失效）
PROSE_SEMANTICS_PROMPT_VERSION = "prose-semantics-v2"

#: 每块的最大字符数（喂给 LLM 的上限 ⇒ 控制 token）
_MAX_BLOCK_CHARS = 3500

#: 每文档最多取几块（按文档入口）
_MAX_BLOCKS_PER_DOC = 1

#: 一次调用最多合并几个块（★ 批量化 ⇒ 控制调用次数）
_BATCH_BLOCKS = 5

#: 每块最多几条
_MAX_ITEMS = 6

#: LLM 的输出预算（★ 推理模型会把 reasoning 计入此预算 ⇒ 须留足）
_MAX_TOKENS = 16000

#: LLM prompt（要求结构化 JSON + 强制 span + 强制 doc）
_PROMPT = """你是协议规范分析员。下面给出若干份 RFC 文档的**片段**。
请只抽取**片段中明确写出的**协议语义事实（不要推测、不要补充文档外知识）。

★ 每段片段前有 `[文档 <文件名>]` 标记 ⇒ 你输出时**必须**带上该文件名（`doc` 字段）。
★ `span` 是**该文档内**的行号（1 起始）⇒ 无法给出确切行号的条目**不要输出**。
★ `entity` 必须是**该行原文里真实出现**的名字（否则会被判为幻觉而丢弃）。
★ `meaning` 用一句话说明它是什么。
★ 若该段是**规范性要求**，额外给出：`action`（动作）/ `object`（对象）/
  `strength`（MUST|SHOULD|MAY，★ **只取原文出现的等级词，不要推测**）/
  `polarity`（positive|negative）/ `keyword_raw`（原文等级措辞）/
  `condition`（生效条件原文）/ `exception`（例外原文）/
  `cross_ref`（**跨节引用**，如 `section 4.2`；★ **与条件分开** ⇒ 引用不是条件）/
  `cross_ref_status`（`resolved` 该章节能在本文档内定位 / `unresolved` 定位不到 /
  `unknown` 无引用）。
★ 若**不是**规范性要求，上述字段**全部留空**。
★ 只输出 JSON，不要解释文字。

格式：
{"items": [{"doc": "<文件名>", "entity": "<实体名>", "meaning": "<一句话含义>",
   "constraint": "<强制约束或空串>", "span": <行号>,
   "action": "<动作或空串>", "object": "<对象或空串>",
   "strength": "<MUST|SHOULD|MAY 或空串>", "polarity": "<positive|negative 或空串>",
   "keyword_raw": "<原文等级措辞或空串>",
   "condition": "<生效条件原文片段或空串>", "exception": "<例外原文片段或空串>",
   "cross_ref": "<跨节引用或空串>", "cross_ref_status": "<resolved|unresolved|unknown>"}]}"""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _split_blocks(text: str, max_blocks: int) -> list[tuple[int, str]]:
    """把文档切成若干块 ⇒ ``[(起始行号, 块文本), ...]``（行号可追溯 ⇒ span 的基础）。"""
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
    """读缓存（★ **只认「已完成」的缓存**）。

    ★ 2026-11-13：曾出现「LLM 调用失败 ⇒ 仍把空/部分结果写进缓存」⇒
      ⇒ 后续命中**空缓存** ⇒ **永不重跑** ⇒ 缺口被永久掩盖。
      ⇒ ⇒ 现在缓存带 ``complete`` 标志；**未跑完的不算命中** ⇒ ⇒ 会重跑。
    """
    p = _cache_path(protocol)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("block_hash") != block_hash:
        return None
    # ★ 旧缓存没有 complete 标志 ⇒ 视为「已完成」（向后兼容）
    if d.get("complete") is False:
        return None
    return d


def _save_cache(protocol: str, block_hash: str, items: list[dict],
                complete: bool = True) -> None:
    """写缓存（★ ``complete=False`` ⇒ 未跑完 ⇒ **下次会重跑**）。"""
    p = _cache_path(protocol)
    p.parent.mkdir(parents=True, exist_ok=True)
    from core.fused.extraction.cache_key import key_manifest
    _payload = {"block_hash": block_hash, "items": items,
                "complete": bool(complete),
                "key_manifest": key_manifest(block_hash)}
    p.write_text(json.dumps(_payload, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _collect_blocks(files: list[Path]) -> list[dict]:
    """按**文档**切块 ⇒ ``[{"doc":…, "start":…, "text":…}, …]``。"""
    out: list[dict] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for start, block in _split_blocks(text, _MAX_BLOCKS_PER_DOC):
            out.append({"doc": f.name, "start": start, "text": block})
    return out


def _doc_lines_map(files: list[Path]) -> dict:
    """``{文件名: [原文行, …]}`` ⇒ 核验「span 所在行必须出现实体名」。"""
    out: dict = {}
    for f in files:
        try:
            out[f.name] = f.read_text(
                encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        except OSError:
            out[f.name] = []
    return out


def _extract_blocks(protocol: str, blocks: list[dict], *,
                    entities: Optional[list] = None,
                    llm=None,
                    max_items: int = _MAX_ITEMS,
                    guard=None,
                    doc_lines: Optional[dict] = None) -> tuple[list[dict], dict]:
    """**共享内核**：对一批已切好的块做 LLM 抽取 ⇒ ``(norms, stats)``。

    ★ 两个入口（按文档 / 按段落）都委托到这里 ⇒ ⇒ 缓存 / 批量化 / 运行保护**同源**。
    """
    from core.fused.extraction.cache_key import cache_key as _cache_key

    stats = {"protocol": protocol, "blocks": len(blocks or []),
             "calls": 0, "retries": 0, "failures": 0, "raw_items": 0,
             "norms": 0, "rejected": 0, "triggers": {}}
    if not blocks:
        return [], stats

    if guard is None:
        from core.fused.extraction.window_candidates import RunGuard
        guard = RunGuard()

    # ---- ① 缓存键（★ 版本化）⇒ 命中缓存则不调 LLM ----
    _block_hash = hashlib.sha256("|".join(
        [_hash_text(b.get("doc", "") + str(b.get("start")) + b.get("text", ""))
         for b in blocks]).encode("utf-8")).hexdigest()
    block_hash = _cache_key(prompt_version=PROSE_SEMANTICS_PROMPT_VERSION,
                            input_fingerprint=_block_hash,
                            temperature=0.1, max_tokens=_MAX_TOKENS,
                            # ★ 2026-11-13（实现验收发现）：prompt **内容**指纹
                            #   ⇒ 改 prompt ⇒ 键变 ⇒ **旧缓存自动失效**
                            #   ⇒ 否则「改了 prompt 但没改版本号」⇒ 命中旧缓存
                            #   ⇒ ⇒ **用旧结果冒充新结果**
                            prompt_digest=_hash_text(_PROMPT))
    cached = _load_cache(protocol, block_hash)
    if cached is not None:
        raw_items = list(cached.get("items") or [])
        stats["cache_hit"] = True
    else:
        stats["cache_hit"] = False
        if llm is None:
            try:
                from core.llm import DeepSeekClient
                llm = DeepSeekClient()
            except Exception as exc:            # noqa: BLE001
                # ★ 2026-11-13：**不得静默返回空** ⇒ 记录原因（否则「无 key」
                #   会被误读成「该文档没有散文语义」⇒ 缺口被掩盖）
                stats["error"] = f"LLM 客户端不可用：{type(exc).__name__}: {exc}"
                print(f"[通道I] {stats['error']}", file=sys.stderr)
                return [], stats
        raw_items = []
        for i in range(0, len(blocks), _BATCH_BLOCKS):
            batch = blocks[i:i + _BATCH_BLOCKS]
            body_parts = []
            for b in batch:
                body_parts.append(
                    f"\n\n===== [文档 {b.get('doc', '')}]"
                    f"（起始行号 {b.get('start')}）=====\n{b.get('text', '')}")
            user = _PROMPT + "".join(body_parts)
            _dedup_key = _hash_text("".join(body_parts))
            _reject = guard.before_call(_dedup_key)
            if _reject:
                stats.setdefault("blocked", []).append(_reject)
                break
            ok = False
            for _attempt in (1, 2):
                stats["calls"] += 1
                try:
                    # ★ chat_json 的签名是 keyword-only（system= / user=）
                    # ★ max_tokens 须留足推理空间（推理模型先吃 reasoning 预算）
                    out = llm.chat_json(
                        system="你是协议规范分析员。只输出 JSON。",
                        user=user, temperature=0.1, max_tokens=_MAX_TOKENS)
                except Exception as exc:        # noqa: BLE001
                    stats["retries"] += 1
                    stats["failures"] += 1
                    guard.on_failure()
                    print(f"[通道I] LLM 调用失败（第 {_attempt} 次，"
                          f"{type(exc).__name__}: {exc}）", file=sys.stderr)
                    continue
                if isinstance(out, str):
                    try:
                        out = json.loads(out)
                    except (ValueError, TypeError):
                        guard.on_failure()
                        continue
                if not isinstance(out, dict):
                    guard.on_failure()
                    continue
                got = 0
                for it in (out.get("items") or []):
                    if not isinstance(it, dict):
                        continue
                    raw_items.append(dict(it))
                    got += 1
                    if got >= max_items * len(batch):
                        break
                guard.on_success()
                ok = True
                break
            if ok:
                # ★ 分批增量落缓存（成功的批不重跑）；★ **未跑完 ⇒ complete=False**
                _save_cache(protocol, block_hash, raw_items, complete=False)
        # ★ 全部批次跑完 ⇒ complete=True（★ 失败留下的缓存会被忽略）
        _save_cache(protocol, block_hash, raw_items,
                    complete=(not stats.get("failures")))

    stats["raw_items"] = len(raw_items)

    # ---- ② 过滤 + 产 norm ----
    norms: list[dict] = []
    seen: set = set()
    for it in raw_items:
        ent = str(it.get("entity") or "").strip()
        meaning = str(it.get("meaning") or "").strip()
        doc = str(it.get("doc") or "").strip()
        if not ent or not meaning or not doc:
            continue
        try:
            span_line = int(it.get("span"))
        except (TypeError, ValueError):
            continue                         # ★ span 必填 ⇒ 无 span 直接拒收
        if span_line <= 0:
            continue
        lines = (doc_lines or {}).get(doc)
        if lines is not None:
            idx = span_line - 1
            if not (0 <= idx < len(lines)):
                continue                     # span 越界 ⇒ 拒收
            # ★ 可核对：span 所在原文行必须出现该实体名 ⇒ 否则判幻觉、拒收
            if ent.lower() not in lines[idx].lower():
                stats["rejected"] += 1
                continue
        con = str(it.get("constraint") or "").strip()
        kind = "prose_constraint" if con else "prose_semantics"
        # ★ 按「实体 + 类别」去重（fact_key 不含 span ⇒ 同实体必撞）
        _dedup_key = (kind, ent.lower())
        if _dedup_key in seen:
            continue
        seen.add(_dedup_key)
        norms.append({
            "kind": kind,
            "protocol": protocol,
            # ★ map_norm_to_facts 按 kb_source_type 分派 ⇒ 缺它会被 skipped
            "kb_source_type": "rfc",
            "name": ent,
            "content": (meaning + (" | constraint: " + con if con else "")),
            "norm_id": f"{kind}_{ent.lower().replace('-', '_')}",
            "source": f"file:{doc}#@{span_line}",
            "entity": ent,
            "meaning": meaning,
            "constraint": con,
            "span_line": span_line,
            # ★ **规范声明内容**（Assertion）⇒ 供 Rule Slot / 规则 fact 构造
            "action": str(it.get("action") or "").strip(),
            "object": str(it.get("object") or "").strip(),
            "strength": str(it.get("strength") or "").strip() or None,
            "polarity": str(it.get("polarity") or "").strip() or None,
            "keyword_raw": str(it.get("keyword_raw") or "").strip(),
            "condition": str(it.get("condition") or "").strip() or None,
            "exception": str(it.get("exception") or "").strip() or None,
            # ★ 跨节引用（★ 独立于条件）
            "cross_ref": str(it.get("cross_ref") or "").strip() or None,
            "cross_ref_status": str(it.get("cross_ref_status") or "").strip() or None,
        })
    stats["norms"] = len(norms)
    try:
        stats["guard"] = guard.to_dict()
    except Exception:                        # noqa: BLE001
        pass
    return norms, stats


def extract_prose_norms(protocol: str, files: list[Path], *,
                         entities: Optional[list] = None,
                         llm=None,
                         max_items: int = _MAX_ITEMS) -> list[dict]:
    """对**一批未命中文档**抽散文语义 ⇒ 返回 norm 列表（★ 按文档切块）。"""
    _blocks = _collect_blocks(list(files or []))
    if not _blocks:
        return []
    _norms, _stats = _extract_blocks(protocol, _blocks, entities=entities,
                                    llm=llm, max_items=max_items,
                                    doc_lines=_doc_lines_map(list(files or [])))
    return _norms


def extract_window_norms(protocol: str, files: list, *,
                         entities: Optional[list] = None,
                         llm=None,
                         max_items: int = 5,
                         guard=None,
                         shadow: bool = True) -> dict:
    """**窗口级**散文语义抽取（★ 第二批）。

    ★ 与 :func:`extract_prose_norms` 的**唯一差异**是**切块粒度**：
      · 本入口按**段落**切 ⇒ ⇒ 混合结构文档里的散文义务
        **不再因为「同篇有表格命中」而整体跳过**
      · 去重 = **声明级**（语义身份 + 证据区间）⇒ ⇒ 不会误删同一行里的不同义务
      · 其余（缓存 / 批量化 / 运行保护）**与按文档入口同源**（共用内核）

    ★ **影子模式**（``shadow=True``）：★ 只产出候选与统计，**不进 fact 空间**
      ⇒ ⇒ 用实测数据决定是否灰度（第三批）。

    Returns:
        统计摘要（``{"norms": [...], "stats": {...}}``）。
    """
    from core.fused.extraction.window_candidates import (
        RunGuard, dedup_declarations, find_candidates,
    )
    _guard = guard or RunGuard()
    _blocks: list[dict] = []
    _stats = {
        "protocol": protocol,
        "shadow": bool(shadow),
        "documents": 0,
        "lines_scanned": 0,
        "candidates": 0,
        "after_dedup": 0,
        "triggers": {},
        "norms": 0,
    }
    for _f in (files or []):
        try:
            _raw = _f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _stats["documents"] += 1
        _lines = [(i, ln) for i, ln in
                  enumerate(_raw.replace("\r\n", "\n").split("\n"), 1)]
        _stats["lines_scanned"] += len(_lines)
        _cands = find_candidates(_lines)
        if not _cands:
            continue
        _cands = dedup_declarations(_cands)
        _stats["candidates"] += len(_cands)
        _stats["after_dedup"] += len(_cands)
        for _c in _cands:
            for _t in _c.triggers:
                _stats["triggers"][_t] = _stats["triggers"].get(_t, 0) + 1
            _blocks.append({"doc": getattr(_f, "name", ""),
                            "start": _c.start_line, "text": _c.text})
    _norms: list[dict] = []
    if _blocks:
        _norms, _istats = _extract_blocks(protocol, _blocks, entities=entities,
                                         llm=llm, max_items=max_items,
                                         guard=_guard,
                                         doc_lines=_doc_lines_map(list(files or [])))
        _stats["norms"] = len(_norms)
        _stats["inner"] = _istats
    try:
        _stats["guard"] = _guard.to_dict()
    except Exception:                        # noqa: BLE001
        pass
    return {"norms": _norms, "stats": _stats}
