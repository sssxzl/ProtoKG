# -*- coding: utf-8 -*-
"""core/fused/source_autoseeder.py —— AutoSeeder 方法：LLM 驱动的状态转移分析。

替代 ProtocolGPT 思路的正则提取（source_fsm.py）。对齐 AutoSeeder
(IEEE INFOCOM 2026) Section III-B：从协议实现源码的「相关代码块」出发，用 LLM
多阶段分析提取 状态(SS) + 方法(SM) + 状态转移(SST，含字段级实例)，并在跨代码块
之间维护「统一命名空间」（语义等价但命名不同的状态/方法归并到同一名字）。

与 ProtocolGPT 思路的本质区别：
  - ProtocolGPT：正则 pattern(method_handler/state_vars/fsm_marker) 精确匹配
    → 抓方法名/状态变量 → LLM 推断 3 元组转移（协议特定正则，换协议要改 pattern）
  - AutoSeeder：协议无关的通用 query 检索相关代码块 → LLM 逐块提取
    SS/SM/SST + 字段级实例（换协议零 pattern 改动）

映射到六元组知识中枢（可溯源，AutoSeeder 原方法没有这一层）：
  SS  → Subject(type=state)                          aspect=definition
  SM  → Subject(type=method)                         aspect=definition
  SST → Subject(type=relation, name=transitions_to)  aspect=target_state
  实例 → Subject(type=relation, name=transitions_to) aspect=message_instance (struct)

设计依据: AutoSeeder (IEEE INFOCOM 2026) Fig.2/Fig.3 + Algorithm 1。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from core import paths
from core.fused.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.canonical import (
    compute_fact_id, compute_claim_id, compute_evidence_id,
)

#: source 源的知识权威 / 认识论类型（源码实现是描述性陈述）
_EPISTEMIC = "descriptive"
_AUTHORITY = "source"
_SOURCE_DOC = "协议实现源码"


# ===========================================================================
# 通用 fact 构造（支持 protocol 参数，替代 source.py 里硬编码 rtsp 的 _make_fact）
# ===========================================================================

def _make_evidence(doc: str, source_id: str, quote: str, locator: Optional[str],
                   claim_id: str) -> Evidence:
    ev = Evidence(
        evidence_id="placeholder", claim_id=claim_id,
        source_type="source", source_id=source_id,
        document=doc, locator=locator, quote=quote,
        content_fingerprint="", extraction_fingerprint="",
    )
    eid = compute_evidence_id(ev)
    return Evidence(
        evidence_id=eid, claim_id=claim_id,
        source_type=ev.source_type, source_id=ev.source_id,
        document=ev.document, locator=ev.locator, quote=ev.quote,
        content_fingerprint=ev.content_fingerprint,
        extraction_fingerprint=ev.extraction_fingerprint,
    )


def _make_fact(subject: Subject, value: Value, protocol: str,
               norm: dict[str, Any], locator: Optional[str],
               aspect: str = "definition") -> Fact:
    """构造一条六元组 fact（epistemic=descriptive / authority=source）。"""
    fact_key = FactKey(protocol=protocol, version="1.0",
                       subject=subject, aspect=aspect,
                       condition=ConditionAlways())
    fact_id = compute_fact_id(fact_key)
    tmp = Claim(claim_id="placeholder", fact_id=fact_id, value=value,
                epistemic_type=_EPISTEMIC, authority=_AUTHORITY,
                scope=Scope(), evidence=())
    cid = compute_claim_id(tmp)
    ev = _make_evidence(norm.get("source", ""), norm.get("norm_id", ""),
                        norm.get("content", ""), locator, cid)
    claim = Claim(claim_id=cid, fact_id=fact_id, value=value,
                  epistemic_type=_EPISTEMIC, authority=_AUTHORITY,
                  scope=Scope(), evidence=(ev,), confidence=None)
    return Fact(fact_id=fact_id, fact_key=fact_key, claims=(claim,),
                resolution=None, alignments=(),
                metadata=FactMetadata(created_at="2026-10-19",
                                      profile_version=f"{protocol}-v1"))


# ===========================================================================
# Prompt 模板（对齐 AutoSeeder Fig.3，五阶段合并为三次 LLM 调用）
# ===========================================================================

_PROMPT_INITIALIZATION = """你是 {protocol} 协议逆向专家。请枚举 {protocol} 协议服务端常见的状态和请求消息方法，每个附一句功能描述。

{anchor}

只输出 JSON（不要解释），格式：
{{"states": [{{"name": "状态名", "desc": "功能描述"}}, ...],
  "methods": [{{"name": "方法名", "desc": "功能描述"}}, ...]}}"""


_PROMPT_BLOCK_ANALYSIS = """你是 {protocol} 协议逆向专家。给定协议实现源码的一个代码片段，请提取：
① 该片段涉及的协议状态（state）；
② 该片段涉及的请求消息方法（method）；
③ 状态转移（from_state --method--> to_state），并为每条转移生成「能触发它的消息实例」（字段级模板，字段名+取值）。

{message_hint}

已知统一命名空间（供语义归并，若新提取的状态/方法语义与已知项一致则复用其名字，否则保留原名并标 is_new=true）：
- 已知状态: {states}
- 已知方法: {methods}

代码片段：
<<<
{code_block}
>>>

只输出 JSON（不要解释），格式：
{{"states": [{{"name": "状态名", "desc": "描述", "is_new": true}}],
  "methods": [{{"name": "方法名", "desc": "描述", "is_new": true}}],
  "transitions": [{{"from": "状态A", "method": "方法", "to": "状态B",
                    "instance": {{"fields": [{{"name": "字段名", "value": "字段值"}}]}}}}]}}"""


# 协议无关默认提示：不预设任何消息结构（url / argument 等），由 LLM 从源码自行归纳。
_MESSAGE_HINT_DEFAULT = "请根据源码自行归纳该协议消息的字段结构，如实生成字段级实例。"


def _load_profile_data(protocol: str) -> Optional[dict]:
    """读 fused_hub/targets/<protocol>/profile.json（协议维度配置）。"""
    if not protocol:
        return None
    path = paths.target_profile(protocol)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_message_hint(protocol: str) -> str:
    """从 profile.json 读 message_schema.hint。

    换协议只换 profile.json 数据（消息结构提示），不改代码。缺 hint 时返回通用默认，
    不预设 url/argument 等协议特定字段（避免 RTSP 污染 SMTP 等行命令协议）。
    """
    data = _load_profile_data(protocol)
    if not data:
        return _MESSAGE_HINT_DEFAULT
    hint = (data.get("message_schema") or {}).get("hint", "").strip()
    return hint or _MESSAGE_HINT_DEFAULT


def _load_allowed_methods(protocol: str) -> Optional[set[str]]:
    """从 profile.json 读 allowed_methods（命令白名单，来自源码命令分发表）。

    用于过滤 LLM 先验污染的命令超集（如 SMTP 过时命令 SAML/SEND/SOML/TURN）。
    换协议只换 profile 数据，不改代码；无该字段则不过滤（返回 None）。
    """
    data = _load_profile_data(protocol)
    if not data:
        return None
    allowed = data.get("allowed_methods")
    if isinstance(allowed, list) and allowed:
        return {str(m).strip().upper() for m in allowed if str(m).strip()}
    return None


def _normalize_method(name: str) -> str:
    """方法名规范化：大写 + 带空格时取首词（行命令协议的命令动词）。

    LLM 先验常把 SMTP 的「MAIL FROM」「RCPT TO」写成带空格的方法名，而源码命令表
    里命令是单 token（MAIL/RCPT），参数 FROM:/TO: 应放 argument。取首词修正。
    """
    n = (name or "").strip().upper()
    return n.split()[0] if n else ""


def _load_state_anchor(protocol: str) -> str:
    """从 profile 读 canonical_flow + allowed_methods，生成状态枚举的确定性锚点。

    引导 LLM 围绕协议真实方法/会话流程枚举「语义化状态」（Idle/Registered/Invited/
    Confirmed），而非响应码（200/401/404）或认证中间态（Trying/Unauthorized），
    消除阶段1「纯 LLM 先验」导致的状态机语义随机性（会话状态机 vs 认证状态机）。
    无 profile 或无 canonical_flow/allowed_methods 时返回空串（纯先验兜底）。
    """
    data = _load_profile_data(protocol)
    if not data:
        return ""
    seedgen = data.get("seedgen") or {}
    flow = seedgen.get("canonical_flow") or []
    allowed = data.get("allowed_methods") or []
    if not flow and not allowed:
        return ""
    parts = []
    if allowed:
        parts.append("已知约束（来自协议实现）：请求方法白名单 = "
                     + ", ".join(str(m).upper() for m in allowed))
    if flow:
        parts.append("会话黄金流程 = " + " → ".join(str(m).upper() for m in flow))
    parts.append(
        "请围绕上述方法枚举「语义化」状态（如空闲/已注册/通话建立/通话中/通话结束），"
        "状态名用语义化命名（如 Idle/Registered/Invited/Confirmed），"
        "不要用响应码（200/401/404）或认证中间态（Trying/Unauthorized）作为状态名。")
    return "\n".join(parts)


_PROMPT_COMPLETION = """你是 {protocol} 协议逆向专家。已知协议状态机如下：
- 状态: {states}
- 方法: {methods}
- 已有转移: {transitions}

请推断「缺失但合法」的状态转移，并用已知方法构造。特别关注两类缺失：
① 状态之间的转移（某些状态之间应有、但尚未提取到的转移）；
② 状态改变方法在其目标状态上的自环（如 READY --SETUP--> READY 重复建立会话、
   PLAYING --PLAY--> PLAYING 重复播放、TEARDOWN 后再次 SETUP 的重建），
   这类「重复/自环」往往触发 UAF、资源泄漏或断言，是漏洞关键，务必补全。
若已完备则返回空列表。

只输出 JSON（不要解释），格式：
{{"new_transitions": [{{"from": "状态A", "method": "方法", "to": "状态B",
                        "instance": {{"fields": [{{"name": "字段名", "value": "字段值"}}]}}}}]}}"""


# ===========================================================================
# LLM 调用封装（失败降级：返回空/原值）
# ===========================================================================

def _chat_json(llm, system: str, user: str,
               temperature: float = 0.0, max_tokens: int = 4000) -> dict:
    try:
        r = llm.chat_json(system=system, user=user,
                          temperature=temperature, max_tokens=max_tokens)
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


def _as_list(x) -> list:
    return x if isinstance(x, list) else []


# ===========================================================================
# Algorithm 1：LLM 驱动的状态转移分析（统一命名空间 + 字段级实例）
# ===========================================================================

def analyze_state_transitions(code_blocks: list[dict], llm,
                              protocol: str = "rtsp") -> tuple[list, list, list]:
    """从相关代码块逐块提取 状态/方法/转移（含字段级实例），维护统一命名空间。

    Returns:
        (SS, SM, SST)
        SS  = [{"name", "desc"}]                     协议状态
        SM  = [{"name", "desc"}]                     请求方法
        SST = [{"from", "method", "to", "instance"}] 状态转移（instance 为字段级模板）
    """
    # 阶段 1：初始化统一命名空间（Fig.3a），注入 profile 锚点（canonical_flow +
    # allowed_methods）让状态枚举语义稳定，而非纯 LLM 先验随机。
    init = _chat_json(llm, "你输出 JSON。",
                      _PROMPT_INITIALIZATION.format(
                          protocol=protocol.upper(),
                          anchor=_load_state_anchor(protocol)))
    ss: list[dict] = []
    sm: list[dict] = []
    ss_names: set[str] = set()
    sm_names: set[str] = set()
    for s in _as_list(init.get("states")):
        n = (s.get("name") or "").strip()
        if n and n not in ss_names:
            ss.append({"name": n, "desc": (s.get("desc") or "").strip()})
            ss_names.add(n)
    for m in _as_list(init.get("methods")):
        n = _normalize_method(m.get("name"))
        if n and n not in sm_names:
            sm.append({"name": n, "desc": (m.get("desc") or "").strip()})
            sm_names.add(n)

    # 阶段 2：逐块提取 状态/方法/转移（Fig.3b/c/d 合并，减少 LLM 调用）
    sst: list[dict] = []
    for i, blk in enumerate(code_blocks):
        code = blk.get("text", "") if isinstance(blk, dict) else str(blk)
        if not code.strip():
            continue
        user = _PROMPT_BLOCK_ANALYSIS.format(
            protocol=protocol.upper(),
            message_hint=_load_message_hint(protocol),
            states=json.dumps([s["name"] for s in ss], ensure_ascii=False),
            methods=json.dumps([m["name"] for m in sm], ensure_ascii=False),
            code_block=code,
        )
        r = _chat_json(llm, "你输出 JSON。", user, max_tokens=8000)
        # 归并新状态
        for s in _as_list(r.get("states")):
            n = (s.get("name") or "").strip()
            if n and n not in ss_names:
                ss.append({"name": n, "desc": (s.get("desc") or "").strip()})
                ss_names.add(n)
        # 归并新方法
        for m in _as_list(r.get("methods")):
            n = _normalize_method(m.get("name"))
            if n and n not in sm_names:
                sm.append({"name": n, "desc": (m.get("desc") or "").strip()})
                sm_names.add(n)
        # 转移 + 字段级实例
        for t in _as_list(r.get("transitions")):
            fr = (t.get("from") or "").strip()
            mt = _normalize_method(t.get("method"))
            to = (t.get("to") or "").strip()
            inst = t.get("instance") or {}
            if fr and mt and to:
                sst.append({"from": fr, "method": mt, "to": to,
                            "instance": inst})

    # 阶段 3：补全缺失转移（Fig.3e）
    completion = _chat_json(
        llm, "你输出 JSON。",
        _PROMPT_COMPLETION.format(
            protocol=protocol.upper(),
            states=json.dumps([s["name"] for s in ss], ensure_ascii=False),
            methods=json.dumps([m["name"] for m in sm], ensure_ascii=False),
            transitions=json.dumps(
                [{"from": t["from"], "method": t["method"], "to": t["to"]}
                 for t in sst], ensure_ascii=False),
        ))
    for t in _as_list(completion.get("new_transitions")):
        fr = (t.get("from") or "").strip()
        mt = _normalize_method(t.get("method"))
        to = (t.get("to") or "").strip()
        if fr and mt and to:
            sst.append({"from": fr, "method": mt, "to": to,
                        "instance": t.get("instance") or {}})

    # 去重（按 from/method/to 签名）
    seen: set = set()
    dedup: list = []
    for t in sst:
        key = (t["from"], t["method"], t["to"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(t)
    sst = dedup

    # 命令白名单过滤（来自 profile 的源码命令表，过滤 LLM 先验超集）
    allowed = _load_allowed_methods(protocol)
    if allowed:
        sm = [m for m in sm if m["name"] in allowed]
        sst = [t for t in sst if t["method"] in allowed]
    return ss, sm, sst


# ===========================================================================
# 映射到六元组知识中枢
# ===========================================================================

def map_to_facts(ss: list[dict], sm: list[dict], sst: list[dict],
                 protocol: str = "rtsp") -> list[Fact]:
    """把 AutoSeeder 分析结果 (SS/SM/SST) 映射为六元组 fact。

    SS  → state fact (aspect=definition)
    SM  → method fact (aspect=definition)
    SST → relation fact (aspect=target_state) + message_instance fact (struct)
    """
    facts: list[Fact] = []

    def _norm(norm_id: str, content: str = "") -> dict:
        return {"protocol": protocol, "kb_source_type": "source",
                "source": f"file:{_SOURCE_DOC}", "norm_id": norm_id,
                "content": content}

    for s in ss:
        name = s["name"]
        facts.append(_make_fact(
            Subject(type="state", name=name),
            Value(type="text", data=s.get("desc") or name),
            protocol, _norm(f"source.autoseeder.state.{name}"), None,
            aspect="definition"))

    for m in sm:
        name = m["name"]
        facts.append(_make_fact(
            Subject(type="method", name=name),
            Value(type="text", data=m.get("desc") or name),
            protocol, _norm(f"source.autoseeder.method.{name}"), None,
            aspect="definition"))

    for t in sst:
        fr, mt, to = t["from"], t["method"], t["to"]
        subj = Subject(type="relation", name="transitions_to", qualifiers={
            "source": Subject(type="state", name=fr),
            "target": Subject(type="state", name=to),
            "method": Subject(type="method", name=mt),
        })
        facts.append(_make_fact(
            subj, Value(type="text", data=to),
            protocol, _norm(f"source.autoseeder.transition.{fr}.{mt}.{to}"),
            None, aspect="target_state"))
        # 字段级实例 → message_instance aspect（struct）
        inst = t.get("instance") or {}
        fields = _as_list(inst.get("fields"))
        if fields:
            facts.append(_make_fact(
                subj,
                Value(type="struct",
                      data={"fields": [{"name": f.get("name"),
                                        "value": f.get("value")}
                                       for f in fields if isinstance(f, dict)]}),
                protocol,
                _norm(f"source.autoseeder.instance.{fr}.{mt}.{to}"), None,
                aspect="message_instance"))
    return facts


# ===========================================================================
# 入口：检索相关代码块 → LLM 分析 → 映射 fact（build_hub 调用）
# ===========================================================================

def infer_source_facts(protocol: str = "rtsp", llm=None) -> list[Fact]:
    """AutoSeeder 方法完整入口：源码 → 检索 → LLM 分析 → 六元组 fact。

    依赖 core.fused.source_retrieval 检索相关代码块（协议无关通用 query）。

    稳定化（P4）：LLM 分析结果按 code_blocks 的 hash 缓存到
    ``derived/model/source_blocks/<protocol>.state.json``，后续 build 命中缓存则不再调 LLM，
    消除「每次 build 状态机都不同」的随机性（temperature=0 仍不稳定的兜底）。
    """
    from core.fused.source_retrieval import retrieve_state_relevant_code, CACHE_DIR
    if llm is None:
        from core.llm import DeepSeekClient
        llm = DeepSeekClient()
    src_dir = paths.kb_source_dir(protocol, "source")
    code_blocks = retrieve_state_relevant_code(src_dir, protocol)
    if not code_blocks:
        return []
    import hashlib
    block_hash = hashlib.md5(
        json.dumps(code_blocks, ensure_ascii=False, sort_keys=True)
        .encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{protocol}.state.json"
    cached = None
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached = None
    if isinstance(cached, dict) and cached.get("block_hash") == block_hash:
        ss, sm, sst = cached.get("ss", []), cached.get("sm", []), cached.get("sst", [])
    else:
        ss, sm, sst = analyze_state_transitions(code_blocks, llm, protocol)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"block_hash": block_hash, "ss": ss, "sm": sm,
                            "sst": sst}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return map_to_facts(ss, sm, sst, protocol)


__all__ = [
    "analyze_state_transitions",
    "map_to_facts",
    "infer_source_facts",
]
