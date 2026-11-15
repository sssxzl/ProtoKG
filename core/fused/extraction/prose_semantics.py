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
import collections
import hashlib
import json
import os
import os
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
★ ★ `normative_subject`：**真正承担义务的主体**（★ **不是** `entity`！
  `entity` 只是原文**提及**的实体；义务主体可能是它，也可能是别的（如 client / server /
  B2BUA / DHCP server）。★ 若主体是代词或**无法确定** ⇒ **留空**（★ **不要猜**）。
★ ★ `subject_span`：`normative_subject` 在原文中的行号（★ 用于核对；不确定就留 0）。
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
   "cross_ref": "<跨节引用或空串>", "cross_ref_status": "<resolved|unresolved|unknown>",
   "normative_subject": "<义务承担主体或空串>", "subject_span": <主体行号或 0>}]}"""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def _rule_text_of(item: dict) -> str:
    """由 LLM 原始项构造**规则文本**（★ 与 norm 映射同源 ⇒ 字段一致）。"""
    from core.fused.extraction.normative_rule import (
        build_payload, normalize_keyword, rule_text,
    )
    _kw = str(item.get("keyword_raw") or "").strip()
    _st = _pol = None
    if _kw:
        _n = normalize_keyword(_kw)          # ★ 只认全大写（RFC 8174）
        if _n:
            _st, _pol = _n
    if not _st:
        _st = str(item.get("strength") or "").strip() or None
    if not _pol:
        _pol = str(item.get("polarity") or "").strip() or None
    _ent = str(item.get("entity") or "").strip()
    _con = str(item.get("condition") or "").strip() or None
    _exc = str(item.get("exception") or "").strip() or None
    _payload = build_payload(
        subject=str(item.get("normative_subject") or "").strip() or _ent,
        action=str(item.get("action") or "").strip() or _ent,
        object_=str(item.get("object") or "").strip() or _ent,
        strength=_st, polarity=_pol,
        condition=_con, condition_status=("stated" if _con else "unknown"),
        exception=_exc, exception_status=("stated" if _exc else "unknown"),
        scope=None,
        cross_ref=str(item.get("cross_ref") or "").strip() or None,
        cross_ref_status=str(item.get("cross_ref_status") or "").strip() or None,
    )
    return rule_text(_payload)



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
    """读缓存（★ M1-①：**四类状态 + 旧格式兼容**）。

    ★ 2026-11-13：曾出现「LLM 调用失败 ⇒ 仍把空/部分结果写进缓存」⇒
      ⇒ 后续命中**空缓存** ⇒ **永不重跑** ⇒ 缺口被永久掩盖。
      ⇒ ⇒ 现在缓存带 ``complete`` 标志；**未跑完的不算命中** ⇒ ⇒ 会重跑。

    ★ **M1-① 的状态语义**（★ 四类 + 旧格式）：
      · ``success_nonempty`` ⇒ 正常命中
      · ``success_empty``    ⇒ 正常命中（★ 合法空结果，不是失败）
      · ``filtered_zero``    ⇒ 正常命中（★ 映射阶段全拒收 ⇒ **不自动重试**，
        但**必须**带拒收原因 ⇒ 进入质量观察）
      · ``failed_incomplete`` ⇒ **不命中**（★ 失败不得复用）
      · ``legacy_unknown``   ⇒ 正常命中（★ 旧缓存无状态字段 ⇒ **不得假装成功**，
        但也**不得无差别删除** ⇒ 标记为未知）
    """
    from core.fused.extraction.cache_key import (
        CACHE_STATUS_FAILED_INCOMPLETE, CACHE_STATUS_LEGACY_UNKNOWN,
    )
    p = _cache_path(protocol)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # ★ 缓存文件损坏 / 写入中断 ⇒ **不命中**（★ 不得误认为成功）
        return None
    if not isinstance(d, dict) or d.get("block_hash") != block_hash:
        return None
    # ★ 旧缓存没有 complete 标志 ⇒ 视为「已完成」（向后兼容）
    if d.get("complete") is False:
        return None
    # ★ M1-①：**状态缺失 ⇒ 标记 legacy_unknown**（★ 不假装成功，也不删除）
    _st = d.get("status")
    if not _st:
        d["status"] = CACHE_STATUS_LEGACY_UNKNOWN
        d["legacy_unknown"] = True
    elif _st == CACHE_STATUS_FAILED_INCOMPLETE:
        # ★ 明确标记为失败不完整 ⇒ **不命中**（★ 双保险：complete 标志之外）
        return None
    return d


def _save_cache(protocol: str, block_hash: str, items: list[dict],
                complete: bool = True, *,
                status: Optional[str] = None,
                drop_reasons: Optional[dict] = None,
                mapped_count: Optional[int] = None,
                llm_calls: Optional[int] = None) -> None:
    """写缓存（★ M1-①：**显式状态 + 拒收原因 + 诊断计数**）。

    ★ ``complete=False`` ⇒ 未跑完 ⇒ **下次会重跑**（★ 失败不固化）
    ★ ``status`` 缺省时按「complete + items 是否为空」推导：
      · complete=False ⇒ ``failed_incomplete``
      · complete=True 且 items 为空 ⇒ ``success_empty``
      · complete=True 且 items 非空 ⇒ ``success_nonempty``
    ★ ``filtered_zero`` 只能由**映射后**的调用方显式传入（★ 因为要等拒收原因）
    """
    from core.fused.extraction.cache_key import (
        CACHE_STATUS_FAILED_INCOMPLETE, CACHE_STATUS_SUCCESS_EMPTY,
        CACHE_STATUS_SUCCESS_NONEMPTY, key_manifest,
    )
    if not status:
        if not complete:
            status = CACHE_STATUS_FAILED_INCOMPLETE
        elif not items:
            status = CACHE_STATUS_SUCCESS_EMPTY
        else:
            status = CACHE_STATUS_SUCCESS_NONEMPTY
    p = _cache_path(protocol)
    p.parent.mkdir(parents=True, exist_ok=True)
    _payload = {"block_hash": block_hash, "items": items,
                "complete": bool(complete),
                "status": status,
                "key_manifest": key_manifest(block_hash)}
    # ★ M1-③ 的诊断计数（★ 只增 ⇒ 不影响既有解析）
    if drop_reasons is not None:
        _payload["drop_reasons"] = dict(drop_reasons)
    if mapped_count is not None:
        _payload["mapped_count"] = int(mapped_count)
    if llm_calls is not None:
        _payload["llm_calls"] = int(llm_calls)
    p.write_text(json.dumps(_payload, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _blocks_per_doc() -> int:
    """★ M1-Q3：**每文档块数**（★ 默认 1 ⇒ ★ 行为与改前一致 ⇒ 不触发历史重抽）。"""
    try:
        return max(1, int(os.environ.get("PROSE_BLOCKS_PER_DOC",
                                        _MAX_BLOCKS_PER_DOC)))
    except (TypeError, ValueError):
        return _MAX_BLOCKS_PER_DOC


def _batch_blocks() -> int:
    """★ M1-Q3：**每批块数**（★ 默认 5 ⇒ ★ 单块调用须显式启用）。"""
    try:
        return max(1, int(os.environ.get("PROSE_BATCH_BLOCKS", _BATCH_BLOCKS)))
    except (TypeError, ValueError):
        return _BATCH_BLOCKS


def _collect_blocks(files: list[Path], max_blocks: Optional[int] = None,
                    budget=None, block_starts: Optional[list] = None) -> list[dict]:
    """按**文档**切块 ⇒ ``[{"doc":…, "start":…, "text":…}, …]``。

    ★ M1-Q3：``max_blocks`` 可按文档覆盖；``budget`` 为块预算（★ 记录未处理块与原因）。
    ★ ★ ``block_starts``：**可选的**块起始行白名单（★ 供测试/实验**指定非首块**）。
      · ★ **不硬编码任何行号** ⇒ 由调用方传入
      · ★ 默认 ``None`` ⇒ ⇒ **行为与改前完全一致**（★ 可回滚）
      · ★ 仅取**该文档**内的块；★ 不在白名单的块一律不产出
    """
    out: list[dict] = []
    _mpd = max_blocks if max_blocks is not None else _blocks_per_doc()
    # ★ 白名单模式下需切出**全文**再过滤（★ 顺序切块 ⇒ 起始行由切分决定
    #   ⇒ ⇒ 只切前 N 块会漏掉靠后的目标块 ⇒ ⇒ 必须切足量）
    if block_starts:
        _mpd = 10 ** 6
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _bl = _split_blocks(text, _mpd)
        if block_starts is not None:
            _want = set(int(x) for x in block_starts)
            _bl = [(s, t) for (s, t) in _bl if s in _want]
        if budget is not None and not budget.allow(f.name, len(_bl)):
            for _st, _tx in _bl:
                budget.skip(f.name, _st, "budget_exhausted")
            continue
        for start, block in _bl:
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


def _chunk_start_of(item: dict, blocks: list[dict], doc: str) -> Optional[int]:
    """★ M1-Q2：取 item 所属 chunk 的**真实起始行**（★ 相对换算的基准）。

    ★ 只有当**本批只有一个块**时才可确定基准 ⇒ ⇒ 多块混批时返回 ``None``
      （★ 不猜测 ⇒ ⇒ 相对换算不做 ⇒ ⇒ 行为与改前一致）。
    """
    if not blocks or len(blocks) != 1:
        return None
    _b = blocks[0]
    if str(_b.get("doc") or "") != str(doc or ""):
        return None
    try:
        return int(_b.get("start") or 0) or None
    except (TypeError, ValueError):
        return None


def _chunk_end_of(item: dict, blocks: list[dict], doc: str,
                  n_lines: int) -> Optional[int]:
    """★ M1-Q2：chunk 的行范围上界（★ 相对换算不得越界）。"""
    _s = _chunk_start_of(item, blocks, doc)
    if _s is None:
        return None
    _b = blocks[0]
    _n = str(_b.get("text") or "").count("\n") + 1
    return min(n_lines, _s + _n - 1)


def _chunk_id(blocks: list[dict]) -> Optional[str]:
    """★ M1-③：批次的稳定标识（★ 文档名 + 起始行）。"""
    if not blocks:
        return None
    _b = blocks[0]
    return f"{_b.get('doc', '')}@{_b.get('start', '')}"


def _chunk_span(blocks: list[dict]) -> Optional[str]:
    """★ M1-③：批次的原始证据跨度（★ 起始行 ~ 结束行）。"""
    if not blocks:
        return None
    _starts = [int(b.get("start") or 0) for b in blocks]
    _ends = [int(b.get("start") or 0) + len(str(b.get("text") or "")) for b in blocks]
    return f"L{min(_starts)}-L{max(_ends)}"


def _model_of(llm) -> Optional[str]:
    """★ M1-③：模型标识（★ 取不到 ⇒ None，不编造）。"""
    return str(getattr(llm, "model", None) or "") or None


def _cache_key_str(block_hash: str) -> Optional[str]:
    """★ M1-③：缓存键（★ 与 :func:`cache_key` 同源计算）。"""
    return f"prose-semantics-v2:{block_hash}"


def _extract_blocks(protocol: str, blocks: list[dict], *,
                    entities: Optional[list] = None,
                    llm=None,
                    max_items: int = _MAX_ITEMS,
                    guard=None,
                    doc_lines: Optional[dict] = None,
                    diagnostics=None) -> tuple[list[dict], dict]:
    """**共享内核**：对一批已切好的块做 LLM 抽取 ⇒ ``(norms, stats)``。

    ★ 两个入口（按文档 / 按段落）都委托到这里 ⇒ ⇒ 缓存 / 批量化 / 运行保护**同源**。
    """
    from core.fused.extraction.cache_key import cache_key as _cache_key
    from core.fused.extraction.normative_extract import (
        entity_in_span, resolve_span_evidence as _resolve_span_evidence,
        span_quote_window as _span_quote_window,
        build_evidence as _build_evidence,
    )

    stats = {"protocol": protocol, "blocks": len(blocks or []),
             "calls": 0, "retries": 0, "failures": 0, "raw_items": 0,
             "norms": 0, "rejected": 0, "triggers": {},
             # ★ M1-Q3：★ token 累计（★ 成本闸用；★ 无单价 ⇒ 费用记 null）
             "input_tokens": 0, "output_tokens": 0, "raw_items_total": 0}
    _diag = diagnostics      # ★ M1-③：诊断收集器（★ None ⇒ 完全不记录）
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
        # ★ M1-③：缓存命中也留痕（★ 区分「缓存命中」与「真实调用」）
        if _diag is not None:
            _rec = _diag.new_record(
                document=(blocks[0].get("doc") if blocks else None),
                chunk_id=_chunk_id(blocks), source_span=_chunk_span(blocks),
                chunk_hash=block_hash, cache_hit=True,
                cache_key=_cache_key_str(block_hash),
                outcome="success", error_stage=None,
            )
            _rec.blocks_without_candidate = 0
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
                if _diag is not None:
                    _diag.new_record(
                        document=(blocks[0].get("doc") if blocks else None),
                        chunk_id=_chunk_id(blocks), source_span=_chunk_span(blocks),
                        chunk_hash=block_hash, cache_hit=False,
                        cache_key=_cache_key_str(block_hash),
                        error_stage="request", error_type=type(exc).__name__,
                        error_message=str(exc), outcome="abandoned",
                    )
                return [], stats
        raw_items = []
        _batch_n = _batch_blocks()
        for i in range(0, len(blocks), _batch_n):
            batch = blocks[i:i + _batch_n]
            body_parts = []
            for b in batch:
                body_parts.append(
                    f"\n\n===== [文档 {b.get('doc', '')}]"
                    f"（起始行号 {b.get('start')}）=====\n{b.get('text', '')}")
            user = _PROMPT + "".join(body_parts)
            _dedup_key = _hash_text("".join(body_parts))
            # ★ M1-①：**模型身份一致性检查**（★ 只统计，不改行为、不占诊断记录）
            #   缓存键里的 model 取自 env（`model_identity()`）⇒ 若**实际 client**
            #   用了别的模型 ⇒ 键与实际模型不一致 ⇒ ⇒ 记进 stats（不静默）
            #   ★ 生产场景下 `DeepSeekClient` 读的也是同一 env ⇒ ⇒ 二者同源；
            #   ★ 仅当调用方传入**显式指定模型**的 client 时才会不一致。
            _client_model = str(getattr(llm, "model", "") or "")
            if _client_model:
                from core.fused.extraction.cache_key import model_identity
                _env_model = model_identity()
                if _client_model != _env_model:
                    stats.setdefault("model_identity_mismatch", []).append({
                        "client_model": _client_model, "env_model": _env_model})
            _reject = guard.before_call(_dedup_key)
            if _reject:
                stats.setdefault("blocked", []).append(_reject)
                if _diag is not None:
                    _diag.new_record(
                        document=(batch[0].get("doc") if batch else None),
                        chunk_id=_chunk_id(batch), source_span=_chunk_span(batch),
                        chunk_hash=block_hash, cache_hit=False,
                        cache_key=_cache_key_str(block_hash),
                        error_stage="request", error_type="GuardRejected",
                        error_message=str(_reject), outcome="abandoned",
                    )
                break
            ok = False
            _batch_failed = False
            for _attempt in (1, 2):
                stats["calls"] += 1
                # ★ M1-③：每次调用一条结构化记录（★ 阶段可区分）
                _rec = None
                if _diag is not None:
                    _rec = _diag.new_record(
                        document=(batch[0].get("doc") if batch else None),
                        chunk_id=_chunk_id(batch), source_span=_chunk_span(batch),
                        chunk_hash=block_hash, cache_hit=False,
                        cache_key=_cache_key_str(block_hash),
                        model=_model_of(llm),
                        prompt_digest=_hash_text(_PROMPT),
                        parser_version=PROSE_SEMANTICS_PROMPT_VERSION,
                        attempt=_attempt,
                    )
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
                    # ★ 区分失败阶段：JSONDecodeError ⇒ 解析阶段；其余 ⇒ 请求阶段
                    _stage = ("json_parse"
                              if type(exc).__name__ == "JSONDecodeError"
                              else "request")
                    _batch_failed = True
                    if _rec is not None:
                        _rec.error_stage = _stage
                        _rec.error_type = type(exc).__name__
                        _rec.error_message = str(exc)
                        _rec.outcome = "failed"
                        _meta = getattr(llm, "last_call_meta", None) or {}
                        _rec.input_tokens = _meta.get("input_tokens")
                        _rec.output_tokens = _meta.get("output_tokens")
                        _rec.finish_reason = _meta.get("finish_reason")
                        _rec.raw_response_sha256 = _meta.get("raw_response_sha256")
                        _rec.elapsed_s = _meta.get("elapsed_s")
                    continue
                # ★ 解析成功 ⇒ 把调用侧元数据（usage / finish_reason）补进记录
                _meta = getattr(llm, "last_call_meta", None) or {}
                # ★ M1-Q3：★ token 累计（★ 供预算与成本统计）
                stats["input_tokens"] = int(stats.get("input_tokens") or 0) + \
                    int(_meta.get("input_tokens") or 0)
                stats["output_tokens"] = int(stats.get("output_tokens") or 0) + \
                    int(_meta.get("output_tokens") or 0)
                if _rec is not None:
                    _rec.input_tokens = _meta.get("input_tokens")
                    _rec.output_tokens = _meta.get("output_tokens")
                    _rec.finish_reason = _meta.get("finish_reason")
                    _rec.raw_response_sha256 = _meta.get("raw_response_sha256")
                    _rec.elapsed_s = _meta.get("elapsed_s")
                if isinstance(out, str):
                    try:
                        out = json.loads(out)
                    except (ValueError, TypeError) as exc:
                        guard.on_failure()
                        _batch_failed = True
                        if _rec is not None:
                            _rec.error_stage = "json_parse"
                            _rec.error_type = type(exc).__name__
                            _rec.error_message = str(exc)
                            _rec.outcome = "failed"
                        continue
                if not isinstance(out, dict):
                    guard.on_failure()
                    _batch_failed = True
                    if _rec is not None:
                        _rec.error_stage = "schema_validation"
                        _rec.error_type = "NotDictPayload"
                        _rec.error_message = f"payload type={type(out).__name__}"
                        _rec.outcome = "failed"
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
                if _rec is not None:
                    _rec.outcome = "success"
                    _rec.blocks_without_candidate = got
                break
            if ok:
                # ★ 分批增量落缓存（成功的批不重跑）；★ **未跑完 ⇒ complete=False**
                _save_cache(protocol, block_hash, raw_items, complete=False)
            elif _batch_failed and _diag is not None:
                # ★ 重试后仍失败 ⇒ 标记「放弃」（★ 与「重试恢复」区分）
                _last = _diag.records[-1] if _diag.records else None
                if _last is not None and _last.outcome == "failed":
                    _last.outcome = "abandoned"
        # ★ 全部批次跑完 ⇒ complete=True（★ 失败留下的缓存会被忽略）
        _save_cache(protocol, block_hash, raw_items,
                    complete=(not stats.get("failures")))

    stats["raw_items"] = len(raw_items)
    stats["raw_items_total"] = len(raw_items)   # ★ M1-Q3：★ 与「解析成功调用数」区分

    # ---- ② 过滤 + 产 norm ----
    norms: list[dict] = []
    seen: set = set()
    # ★ M1-③：**产物映射阶段的丢弃也要留痕**（★ 此前完全静默）
    _drop = {"missing_entity": 0, "missing_meaning": 0, "missing_doc": 0,
             "duplicate": 0, "missing_span": 0, "span_out_of_range": 0,
             "entity_not_in_span": 0, "subject_unresolved": 0,
             "kind_not_mapped": 0}
    # ★ M1-Q2：解释模式分布 + 逐条留痕
    _drop_by_mode: dict = {}
    _span_trace: list = []
    _sp_matched = None
    _sp_mode = None
    _sp_evidence = None
    for it in raw_items:
        ent = str(it.get("entity") or "").strip()
        meaning = str(it.get("meaning") or "").strip()
        doc = str(it.get("doc") or "").strip()
        if not ent or not meaning or not doc:
            if not ent:
                _drop["missing_entity"] += 1
            if not meaning:
                _drop["missing_meaning"] += 1
            if not doc:
                _drop["missing_doc"] += 1
            continue
        try:
            span_line = int(it.get("span"))
        except (TypeError, ValueError):
            _drop["missing_span"] += 1       # ★ M1-③：静默拒收留痕
            continue                         # ★ span 必填 ⇒ 无 span 直接拒收
        if span_line <= 0:
            _drop["missing_span"] += 1       # ★ M1-③
            continue
        lines = (doc_lines or {}).get(doc)
        if lines is not None:
            idx = span_line - 1
            if not (0 <= idx < len(lines)):
                _drop["span_out_of_range"] += 1   # ★ M1-③
                continue                     # span 越界 ⇒ 拒收
            # ★ 可核对：实体名须在**证据跨度内**（含前后若干行）出现
            #   ★ 2026-11-13（独立复核意见 P0-2）：旧逻辑只看 **span 单行**
            #     ⇒ 实体名在**相邻行**时被**误拒**（如 S09/S19/S29/S39）
            # ★ ★ M1-Q2：**双口径证据定位**（★ 绝对优先；相对须有据）
            #   · 绝对行号命中 ⇒ 行为与改前**完全一致**（★ 不影响既有 127 条）
            #   · 绝对未命中 ⇒ 才尝试相对换算（★ chunk_start + (raw_span - 1)）
            #   · 换算越界 / 歧义 / 缺基准 ⇒ 一律**不放行**
            _sp_ev = _resolve_span_evidence(
                lines, span_line, ent,
                chunk_start=_chunk_start_of(it, blocks, doc),
                chunk_end=_chunk_end_of(it, blocks, doc, len(lines)))
            _span_trace.append(_sp_ev)
            _sp_matched = _sp_ev.get("matched_evidence_lines")
            _sp_mode = _sp_ev.get("span_mode")
            # ★ M1-Q3-P0.6：★ 构造**句界证据**（★ 锚点所在完整规范句）
            _sp_evidence = _build_evidence(lines, _sp_ev, entity=ent)
            if _sp_ev["span_mode"] in ("absolute", "relative"):
                span_line = _sp_ev["resolved_span"]     # ★ 采用解析后的**锚点行**
            else:
                stats["rejected"] += 1
                _drop["entity_not_in_span"] += 1   # ★ M1-③
                _drop_by_mode[_sp_ev["span_mode"]] = \
                    _drop_by_mode.get(_sp_ev["span_mode"], 0) + 1
                continue
        con = str(it.get("constraint") or "").strip()
        # ★ ★ **主体归属核验**（★ P0-1）：★ `entity` 只是**原文提及的实体**
        #   ⇒ 义务主体可能是别的 ⇒ ⇒ 用 `normative_subject`（来自原文主语）
        #   ⇒ ★ 且它**必须在证据跨度内可核对** ⇒ 否则 `unresolved`
        #   ⇒ ★ **未解析 ⇒ 不产 Rule Slot**（⇒ 归描述通道 + 标待审）
        _nsub = str(it.get("normative_subject") or "").strip()
        _subject_status = "unresolved"
        if _nsub:
            # ★ M1-Q2：主体核对**沿用解析后的 span_line**（★ 与证据同一坐标系）
            if entity_in_span(lines or [], span_line, _nsub) is not None:
                _subject_status = "resolved"
            elif _nsub.lower() == ent.lower():
                _subject_status = "resolved"   # ★ 主体就是 entity ⇒ 可核对
        # ★ 主体可解析 ⇒ 用它；否则保留 entity 仅为**提及实体**（不成规则）
        _subject_for_slot = _nsub if _subject_status == "resolved" else ""
        # ★ ④ **描述 / 规范分流**（★ 独立复核意见 P0-4）
        #   ⇒ 若「动作/对象」缺失或**就是主体名本身**（占位）⇒ ⇒ 该条**不是**
        #     行为性规范义务 ⇒ ⇒ 归**描述性知识**（prose_semantics）
        #     ⇒ ⇒ 杜绝 `RTSP/RTSP/RTSP`、`220/220/220` 这类**虚假 Rule Slot**
        _act = str(it.get("action") or "").strip()
        _obj = str(it.get("object") or "").strip()
        _is_placeholder = (not _act or not _obj
                           or (_act.lower() == ent.lower()
                               and _obj.lower() == ent.lower()))
        # ★ ★ 主体未解析 ⇒ **不成规则**（★ P0-1：不得为稳定 FactID 而猜主体）
        if _subject_status != "resolved":
            _is_placeholder = True
        kind = ("prose_semantics" if _is_placeholder
                else ("prose_constraint" if con else "prose_semantics"))
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
            # ★ M1-Q3：★ 锚点 / 匹配行（★ 供 L1/L2 取完整证据窗口）
            "span_matched_line": _sp_matched,
            "span_mode": _sp_mode,
            # ★ M1-Q3-P0.6：★ 句界证据（★ 主要 quote + 单独标记的辅助证据）
            "evidence_quote": _sp_evidence.get("quote") if _sp_evidence else None,
            "evidence_quote_span": _sp_evidence.get("quote_span") if _sp_evidence else None,
            "evidence_boundary_reason": (_sp_evidence.get("boundary_reason")
                                          if _sp_evidence else None),
            "evidence_aux": _sp_evidence.get("aux_evidence") if _sp_evidence else None,
            "evidence_cross_chunk": _sp_evidence.get("cross_chunk") if _sp_evidence else None,
            "evidence_degraded": _sp_evidence.get("degraded") if _sp_evidence else None,
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
            # ★ ★ **主体归属**（P0-1）：`entity` = 提及实体；`normative_subject` = 义务主体
            "mentioned_entity": ent,
            "normative_subject": _nsub or None,
            "subject_span": int(it.get("subject_span") or 0) or None,
            "subject_status": _subject_status,
            # ★ L1/L2 需要：规则文本 + 原文行（★ 仅作影子期校验用）
            # ★ 规则文本（★ L1/L2 用）—— 由**同一份**语义字段构造
            #   ⇒ 保证「value 里的字段」与「校验的字段」一致
            "rule_text": _rule_text_of(it),
            "_doc_lines": lines,
        })
    # ---- ★★ **真实接入 L1 / L2**（★ P0-2）--------------------------------
    #   ⇒ ★ 此前 L1/L2 **只在测试里**被调用 ⇒ 真实抽取**从不校验**
    #   ⇒ ⇒ 现在：**L1（确定性）→ L2（真实独立调用）→ 最终状态** ⇒ 写入影子产物
    #   ⇒ ★ 成本控制：L2 **只对 L1 通过且关键字段齐备**的候选跑（其余直接 pending）
    #   ⇒ ★ 影子模式下状态**只作记录**，不进正式 fact
    try:
        from core.fused.extraction.normative_rule import (
            is_pronoun_subject, parse_rule_text,
        )
        from core.fused.extraction.normative_verify import (
            CONFIRMED as _CONF, PENDING as _PEND, REJECTED as _REJ,
            l1_check as _l1_check, l2_check as _l2_check,
        )
        _l2_calls = 0
        # ★ L2 用**独立预算**（★ 否则与抽取调用互相挤占 ⇒ 抽取用完额度后 L2 无机会）
        from core.fused.extraction.window_candidates import RunGuard as _RG
        _l2_guard = _RG(max_calls=30, circuit_breaker_threshold=5)
        for _n in norms:
            _l1 = None
            if _n.get("kind") == "prose_constraint" and _n.get("span_line"):
                _doc_n = _n.get("_doc_lines")
                _ln = _n.get("span_line")
                _quote = ""
                if isinstance(_doc_n, list) and _ln and 0 < _ln <= len(_doc_n):
                    # ★ ★ M1-Q3-P0.6：★ quote = **锚点所在的完整规范句**
                    #   ⇒ ★ 句界由确定性算法恢复（★ 排除章节标题/图注/ABNF/表格）
                    #   ⇒ ★ 前一句（条件/指代/例外）作为**单独标记的辅助证据**
                    #   ⇒ ⇒ ★ **entity 校验窗口本身未变（仍是 ±3）**
                    _ev_q = _n.get("evidence_quote")
                    if isinstance(_ev_q, str) and _ev_q.strip():
                        _quote = _ev_q
                    else:
                        # ★ 兜底：句界不可用 ⇒ 退回「锚点↔匹配行」窗口
                        _mk = _n.get("span_matched_line")
                        if isinstance(_mk, int) and _mk and 0 < _mk <= len(_doc_n):
                            _lo_q = max(1, min(_ln, _mk))
                            _hi_q = min(len(_doc_n), max(_ln, _mk))
                            _quote = " ".join(str(x).strip()
                                              for x in _doc_n[_lo_q - 1:_hi_q]
                                              if str(x).strip())
                        else:
                            _quote = _doc_n[_ln - 1]
                # ★ M1-Q3：★ quote 存入 norm（★ 供回归测试与追溯）
                _n["_l1_quote"] = _quote
                _n["_quote_span"] = (
                    list(_span_quote_window({
                        "resolved_span": _ln,
                        "matched_evidence_lines": _n.get("span_matched_line"),
                    })) if _n.get("span_matched_line") else [_ln, _ln])
                try:
                    _l1 = _l1_check(
                        rule_text_value=_n.get("rule_text") or "",
                        quote=_quote, evidence_span=(_ln, _ln),
                        keyword_raw=str(_n.get("keyword_raw") or ""),
                        subject=str(_n.get("normative_subject") or
                                    _n.get("name") or ""))
                except Exception as _e:
                    _n["l1_error"] = f"{type(_e).__name__}: {_e}"
            _n["l1"] = ({"verdict": _l1.verdict, "reasons": _l1.reasons,
                         "field_verdicts": _l1.field_verdicts,
                         "verifier": _l1.verifier_version} if _l1 else None)
            # ---- L2：只对 L1 通过的候选跑（成本控制）----
            if _l1 is not None and _l1.verdict == _CONF:
                _payload = parse_rule_text(_n.get("rule_text") or "")
                if _payload:
                    _reject = _l2_guard.before_call(_hash_text(
                        _n.get("rule_text") or "") + str(_n.get("span_line")))
                    if not _reject:
                        try:
                            _l2 = _l2_check(payload=_payload, quote=_quote,
                                             llm=llm)
                            _l2_calls += 1
                            _n["l2"] = {
                                "verdict": _l2.verdict, "reasons": _l2.reasons,
                                "field_verdicts": _l2.field_verdicts,
                                "verifier": _l2.verifier_version}
                        except Exception as _e:
                            _l2_guard.on_failure()
                            _n["l2"] = {"verdict": _PEND,
                                        "reasons": [f"{type(_e).__name__}: {_e}"],
                                        "verifier": "l2-error"}
            # ---- 最终状态 ----
            _l1v = (_n.get("l1") or {}).get("verdict")
            _l2v = (_n.get("l2") or {}).get("verdict")
            if _l1v == _REJ or _l2v == "rejected":
                _n["final_state"] = "rejected"
            elif _l1v == _CONF and (_l2v in ("支持", "confirmed", _CONF)):
                _n["final_state"] = "confirmed"
            else:
                _n["final_state"] = "pending"
            # ★ ★ M1-Q3-P0.7-A：★ **确认前的指代主体归属核验**
            #   ⇒ ★ **不修改 L1/L2 判定标准**（★ 只在状态落定后加一道确认前检查）
            #   ⇒ ★ 归属歧义 / 未解析 ⇒ ★ **不得自动确认** ⇒ 保守保持 pending
            #   ⇒ ★ **不重写 canonical 身份**（★ 只改 final_state 并留痕）
            try:
                _att = _resolve_subject_attribution(
                    lines=lines,
                    quote_span=_n.get("evidence_quote_span"),
                    quote=str(_n.get("evidence_quote") or ""),
                    aux_evidence=_n.get("evidence_aux"),
                    entity=str(_n.get("mentioned_entity") or ""),
                    subject=str(_n.get("normative_subject") or ""),
                )
            except Exception as _exc:
                _att = {"status": "coreference_unresolved",
                        "antecedents": [], "evidence_lines": [],
                        "reason": f"归属核验异常：{type(_exc).__name__}: {_exc}",
                        "coref_phrase": None}
            _n["subject_attribution"] = _att
            if _n.get("final_state") == "confirmed" and \
                    _att.get("status") in ("coreference_ambiguous",
                                           "coreference_unresolved"):
                _n["final_state"] = "pending"
                _n["attribution_downgraded"] = True
                stats["attribution_downgraded"] = \
                    int(stats.get("attribution_downgraded") or 0) + 1
        stats["l2_calls"] = _l2_calls
        stats["l2_guard"] = _l2_guard.to_dict()
        stats["final_states"] = dict(collections.Counter(
            n.get("final_state") for n in norms))
        # ★ **影子产物落盘**（★ 任务书：L1/L2 结果可追溯 ⇒ 不只留在内存）
        #   ⇒ 写 derived/per_source/<协议>/<源>/verify.jsonl ⇒ **不进 fact 空间**
        try:
            from core import paths as _paths
            _vp = (_paths.per_source_facts_dir(protocol, "rfc").parent
                   / "verify.jsonl")
            _vp.parent.mkdir(parents=True, exist_ok=True)
            with _vp.open("w", encoding="utf-8") as _vf:
                for _n in norms:
                    _vf.write(json.dumps({
                        "kind": _n.get("kind"),
                        "mentioned_entity": _n.get("mentioned_entity"),
                        "normative_subject": _n.get("normative_subject"),
                        "subject_status": _n.get("subject_status"),
                        "strength": _n.get("strength"),
                        "polarity": _n.get("polarity"),
                        "condition": _n.get("condition"),
                        "exception": _n.get("exception"),
                        "cross_ref": _n.get("cross_ref"),
                        "cross_ref_status": _n.get("cross_ref_status"),
                        "source": _n.get("source"),
                        "l1": _n.get("l1"), "l2": _n.get("l2"),
                        "final_state": _n.get("final_state"),
                        "rule_text": _n.get("rule_text"),
                    }, ensure_ascii=False) + "\n")
            stats["verify_file"] = str(_vp)
        except Exception as _vex:
            print(f"[通道I] 影子产物写入跳过：{_vex}", file=sys.stderr)
    except Exception as _exc:
        import traceback
        print(f"[通道I] L1/L2 接入失败：{_exc}", file=sys.stderr)
        traceback.print_exc()
        stats["verify_error"] = f"{type(_exc).__name__}: {_exc}"


    stats["norms"] = len(norms)
    # ★ M1-③：**产物映射阶段的丢弃统计**（★ 此前完全静默 ⇒ 无法解释产出量差异）
    stats["raw_items_dropped"] = sum(_drop.values())
    stats["drop_reasons"] = dict(_drop)
    # ★ M1-Q2：span 解释模式统计（★ 可观测）
    stats["span_mode_counts"] = dict(_drop_by_mode)
    stats["span_trace"] = list(_span_trace[-64:])
    stats["input_blocks"] = len(blocks or [])
    # ★ M1-①：**回写缓存状态**（★ 区分「合法空」/「全被拒收」/「失败不完整」）
    from core.fused.extraction.cache_key import (
        CACHE_STATUS_FILTERED_ZERO, CACHE_STATUS_SUCCESS_EMPTY,
        CACHE_STATUS_SUCCESS_NONEMPTY,
    )
    if stats.get("failures"):
        _cache_status = None            # ★ 失败 ⇒ 保持 complete=False（不固化）
    elif not raw_items:
        _cache_status = CACHE_STATUS_SUCCESS_EMPTY
    elif not norms:
        # ★ LLM 返回了候选，但**全部被映射校验拒收** ⇒ ⇒
        #   保留缓存 + 记录全部拒收原因 ⇒ **不自动重试**（★ 用户规则三）
        _cache_status = CACHE_STATUS_FILTERED_ZERO
    else:
        _cache_status = CACHE_STATUS_SUCCESS_NONEMPTY
    # ★ **命中时也回写**（★ 只更新状态与诊断元数据 ⇒ 旧缓存命中后即获得真实状态；
    #   ★ items 与 block_hash 原样保留 ⇒ **不无差别删除历史缓存**）
    _save_cache(protocol, block_hash, raw_items,
                complete=(not stats.get("failures")),
                status=_cache_status, drop_reasons=dict(_drop),
                mapped_count=len(norms), llm_calls=stats.get("calls"))
    stats["cache_status"] = _cache_status
    if _diag is not None:
        _diag.input_blocks = len(blocks or [])
        _mrec = _diag.new_record(
            document=(blocks[0].get("doc") if blocks else None),
            chunk_id=_chunk_id(blocks), source_span=_chunk_span(blocks),
            chunk_hash=block_hash, cache_hit=bool(stats.get("cache_hit")),
            cache_key=_cache_key_str(block_hash),
            outcome="success", error_stage="mapping",
            blocks_without_candidate=sum(_drop.values()),
        )
        _mrec.error_message = (
            f"raw_items={len(raw_items)} → norms={len(norms)}；"
            f"丢弃 {json.dumps(_drop, ensure_ascii=False)}")
        # ★ M1-Q2：★ 逐条记录「原始跨度 / 换算跨度 / 解释模式 / 定位结果」
        _mrec.span_trace = list(_span_trace[-64:])
        _mrec.span_mode_counts = dict(_drop_by_mode)
    try:
        stats["guard"] = guard.to_dict()
    except Exception:                        # noqa: BLE001
        pass
    return norms, stats


def extract_prose_norms(protocol: str, files: list[Path], *,
                         entities: Optional[list] = None,
                         llm=None,
                         max_items: int = _MAX_ITEMS,
                         diagnostics=None) -> list[dict]:
    """对**一批未命中文档**抽散文语义 ⇒ 返回 norm 列表（★ 按文档切块）。

    ★ M1-③：``diagnostics`` 传入 :class:`LLMDiagnostics` ⇒ 记录每次调用与失败
      （★ 不传 ⇒ 完全不记录 ⇒ **行为与改前逐字节一致**）。
    """
    _blocks = _collect_blocks(list(files or []))
    if not _blocks:
        return []
    _norms, _stats = _extract_blocks(protocol, _blocks, entities=entities,
                                    llm=llm, max_items=max_items,
                                    doc_lines=_doc_lines_map(list(files or [])),
                                    diagnostics=diagnostics)
    return _norms


def extract_window_norms(protocol: str, files: list, *,
                         entities: Optional[list] = None,
                         llm=None,
                         max_items: int = 5,
                         guard=None,
                         shadow: bool = True,
                         diagnostics=None) -> dict:
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
                                         doc_lines=_doc_lines_map(list(files or [])),
                                         diagnostics=diagnostics)
        _stats["norms"] = len(_norms)
        _stats["inner"] = _istats
        # ★ L1/L2 的结果提到**外层**（★ 便于观测；★ 内层在 _istats 里）
        for _k in ("l2_calls", "l2_guard", "final_states", "verify_error",
                   "verify_file"):
            if _k in _istats:
                _stats[_k] = _istats[_k]
    try:
        _stats["guard"] = _guard.to_dict()
    except Exception:                        # noqa: BLE001
        pass
    return {"norms": _norms, "stats": _stats}
