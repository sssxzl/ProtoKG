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
    from core.fused.extraction.normative_extract import entity_in_span

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
            # ★ 可核对：实体名须在**证据跨度内**（含前后若干行）出现
            #   ★ 2026-11-13（独立复核意见 P0-2）：旧逻辑只看 **span 单行**
            #     ⇒ 实体名在**相邻行**时被**误拒**（如 S09/S19/S29/S39）
            if entity_in_span(lines, span_line, ent) is None:
                stats["rejected"] += 1
                continue
        con = str(it.get("constraint") or "").strip()
        # ★ ★ **主体归属核验**（★ P0-1）：★ `entity` 只是**原文提及的实体**
        #   ⇒ 义务主体可能是别的 ⇒ ⇒ 用 `normative_subject`（来自原文主语）
        #   ⇒ ★ 且它**必须在证据跨度内可核对** ⇒ 否则 `unresolved`
        #   ⇒ ★ **未解析 ⇒ 不产 Rule Slot**（⇒ 归描述通道 + 标待审）
        _nsub = str(it.get("normative_subject") or "").strip()
        _subject_status = "unresolved"
        if _nsub:
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
            "rule_text": rule_text(_payload_of(it)),
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
        for _n in norms:
            _l1 = None
            if _n.get("kind") == "prose_constraint" and _n.get("span_line"):
                _doc_n = _n.get("_doc_lines")
                _ln = _n.get("span_line")
                _quote = ""
                if isinstance(_doc_n, list) and 0 < _ln <= len(_doc_n):
                    _quote = _doc_n[_ln - 1]
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
                    _reject = guard.before_call(_hash_text(
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
                            guard.on_failure()
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
        stats["l2_calls"] = _l2_calls
        stats["final_states"] = dict(collections.Counter(
            n.get("final_state") for n in norms))
    except Exception as _exc:
        print(f"[通道I] L1/L2 接入跳过：{_exc}", file=sys.stderr)
        stats["verify_error"] = f"{type(_exc).__name__}: {_exc}"


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
