"""core/fused/traffic.py —— traffic 源（pcap/raw 观测 norm）→ Fact 映射。

traffic 源现走确定性抽取（core/fused/traffic_extractor.py 从数据流量目录读 client.log / csv / packets.ndjson）, 不再依赖 norms.jsonl。
同一 norm_id 被大量抓包 capture 重复展开（按 norm_id 去重, 每 distinct norm 产 observed fact），evidence quote 记录
「该观测出现于 N 个 capture」的统计（用户 2026-10-09 裁定「去重+统计」，R3）。

kind → 映射（epistemic 一律 observed）:
  message      method=DESCRIBE occurrences=1       → method  + existence（bool）
  field        CSeq header occurrences=10          → header  + value_enum_observed（set）
  field        unique URLs=2 samples=[...]         → header  + value_enum_observed（set）
  state_machine observed transitions: A → B → C    → relation + method_sequence（相邻对）
  outcome      status code distribution: {...}     → status  + （不产出 fact：实测频次无意义）
  protocol     transport distribution / methods    → protocol + value_enum_observed（set）
  actor        RTSP server observed on ports [...] → actor   + value_enum_observed（set）

设计依据: docs/设计/抽取层/抽取层方法借鉴.md §三 traffic 行（LLM-Boofuzz 借鉴，
           rule 做统计/边界，LLM 增强字段语义 —— 本模块只做 rule 部分）。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from core.fused.hub.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.hub.canonical import (
    compute_fact_id, compute_claim_id, compute_evidence_id,
)


# ===========================================================================
# 公共构造
# ===========================================================================

def _make_evidence(norm: dict[str, Any], quote: str, claim_id: str) -> Evidence:
    ev = Evidence(
        evidence_id="placeholder", claim_id=claim_id,
        source_type=norm.get("kb_source_type", "traffic"),
        source_id=norm.get("norm_id", ""),
        document=norm.get("source", ""),
        locator=None, quote=quote,
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


def _make_fact(subject: Subject, aspect: str, value: Value,
               norm: dict[str, Any], quote: str) -> Fact:
    fact_key = FactKey(protocol=norm.get("protocol", "rtsp"), version="1.0",
                       subject=subject, aspect=aspect, condition=ConditionAlways())
    fact_id = compute_fact_id(fact_key)
    # authority 从 norm 派生：packets.ndjson 字段用 traffic_packet，client.log 用
    # traffic 默认值。让下游能区分「完整包真实字段」与「日志摘要字段」（P4-b）。
    authority = norm.get("authority", "traffic")
    tmp = Claim(claim_id="placeholder", fact_id=fact_id, value=value,
                epistemic_type="observed", authority=authority,
                scope=Scope(), evidence=())
    cid = compute_claim_id(tmp)
    ev = _make_evidence(norm, quote, cid)
    claim = Claim(claim_id=cid, fact_id=fact_id, value=value,
                  epistemic_type="observed", authority=authority,
                  scope=Scope(), evidence=(ev,), confidence=None)
    return Fact(fact_id=fact_id, fact_key=fact_key, claims=(claim,),
                resolution=None, alignments=(),
                metadata=FactMetadata(created_at="2026-10-09", profile_version="rtsp-v1"))


def _quote(content: str, capture_count: int) -> str:
    return f"{content}（observed in {capture_count} captures）"


# ===========================================================================
# 解析器
# ===========================================================================

def parse_message(content: str) -> Optional[str]:
    """'method=DESCRIBE occurrences=1' → 'DESCRIBE'。"""
    m = re.search(r"method=(\S+)", content)
    return m.group(1).upper() if m else None


def parse_field_samples(content: str) -> Optional[list[str]]:
    """'unique URLs=2 samples=[...]' → 解析 samples 列表。

    samples 由 repr(value) 逗号拼接（可能含逗号/方括号），故用 ast.literal_eval
    解析到末尾，避免逗号误拆；失败时退化为简单逗号分割。
    """
    m = re.search(r"samples=\[(.*)\]\s*$", content)
    if not m:
        return None
    inner = m.group(1).strip()
    if not inner:
        return []
    try:
        import ast
        vals = ast.literal_eval("[" + inner + "]")
        return [str(v) for v in vals]
    except (ValueError, SyntaxError):
        # 兜底：逗号分割（strip 引号）
        return [s.strip().strip("'\"") for s in inner.split(",") if s.strip()]


def parse_field_definition(content: str) -> Optional[tuple[str, str]]:
    """'CSeq definition=序列号，用于匹配请求响应' → ('CSeq', '...')。

    这是 LLM 兜底（infer_traffic_fields）产出的字段语义，对齐 LLM-Boofuzz 的
    「LLM 解析真实流量提取协议信息」——rule 只做 occurrence/samples 统计，
    LLM 补字段含义（definition）。
    """
    m = re.search(r"(\S+)\s+definition=(.+)$", content)
    if m:
        return m.group(1), m.group(2).strip()
    return None


def parse_state_machine(content: str) -> list[str]:
    """'observed transitions: A → B → C' → ['A', 'B', 'C']。"""
    m = re.search(r"observed\s+(?:transitions|methods):\s*(.+)$", content)
    if not m:
        return []
    seq = m.group(1)
    parts = re.split(r"\s*(?:→|->)\s*", seq)
    return [p.strip() for p in parts if p.strip()]


def parse_outcome(content: str) -> list[tuple[str, int]]:
    """'status code distribution: {'200': 5, ...}' → [('200', 5), ...]。"""
    m = re.search(r"\{([^{}]*)\}", content)
    if not m:
        return []
    out = []
    for pair in m.group(1).split(","):
        if ":" not in pair:
            continue
        k, _, v = pair.partition(":")
        k = k.strip().strip("'\"")
        v = v.strip().strip("'\"")
        if k and v.isdigit():
            out.append((k, int(v)))
    return out


def parse_distribution_keys(content: str) -> list[str]:
    """'transport distribution: {'TCP': 20, 'UDP': 35}' → ['TCP', 'UDP']。"""
    m = re.search(r"\{([^{}]*)\}", content)
    if not m:
        return []
    return [p.partition(":")[0].strip().strip("'\"")
            for p in m.group(1).split(",") if ":" in p]


def parse_bracketed_list(content: str) -> list[str]:
    """'server-advertised methods (8): ['A', 'B']' → ['A', 'B']；'ports [8554]' → ['8554']。"""
    m = re.search(r"\[([^\]]*)\]", content)
    if not m:
        return []
    return [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]


# ===========================================================================
# kind → 映射
# ===========================================================================

def _message_facts(norm: dict[str, Any], quote: str) -> list[Fact]:
    method = parse_message(norm.get("content", ""))
    if not method:
        return []
    return [_make_fact(Subject(type="method", name=method), "existence",
                       Value(type="scalar", data=True), norm, quote)]


def _field_facts(norm: dict[str, Any], quote: str) -> list[Fact]:
    content = norm.get("content", "")
    # ★ 2026-11-11：删除「实测频次」（occurrence）⇒ 字段的 ``occurrences=N`` **不再产出 fact**
    #   （理由：知识抽取层**面向知识源**⇒ 源码/RFC/注记里得不到「实测频次」
    #   ⇒ 只有抓包才有 ⇒ 属于**投放期观测**，不是协议知识 ⇒ 不该占知识维度）
    samples = parse_field_samples(content)
    if samples:
        name = norm.get("name", "") or "field"
        return [_make_fact(Subject(type="header", name=name), "value_enum_observed",
                           Value(type="set", data=samples), norm, quote)]
    definition = parse_field_definition(content)
    if definition:
        name, sem = definition
        return [_make_fact(Subject(type="header", name=name), "definition",
                           Value(type="text", data=sem), norm, quote)]
    return []


def _state_machine_facts(norm: dict[str, Any], quote: str) -> list[Fact]:
    """方法序列相邻对 → method_sequence 关系 fact（语义与状态机边显式区分）。

    注意：traffic 的「state_machine」norm 实际是「观测到的方法调用顺序」（method→
    method 相邻对），不是「状态机边」（state --method--> state）。故用独立 aspect
    `method_sequence` + subject.name `method_sequence`，与 rfc/source 的
    `target_state`（状态机边）显式区分，避免靠 qualifiers.source.type 隐式分流。
    """
    seq = parse_state_machine(norm.get("content", ""))
    facts = []
    for a, b in zip(seq, seq[1:]):
        subject = Subject(type="relation", name="method_sequence",
                          qualifiers={
                              "source": Subject(type="method", name=a),
                              "target": Subject(type="method", name=b),
                          })
        facts.append(_make_fact(subject, "method_sequence",
                                Value(type="text", data=b), norm, quote))
    return facts


def _outcome_facts(norm: dict[str, Any], quote: str) -> list[Fact]:
    # ★ 2026-11-11：删除「实测频次」（occurrence）⇒ 状态码分布**不产出 fact**
    #   （同上：实测频次是投放期观测，不是协议知识）
    return []


def _protocol_facts(norm: dict[str, Any], quote: str) -> list[Fact]:
    content = norm.get("content", "")
    keys = parse_distribution_keys(content) or parse_bracketed_list(content)
    if not keys:
        return []
    name = norm.get("name", "") or "protocol"
    return [_make_fact(Subject(type="protocol", name=name), "value_enum_observed",
                       Value(type="set", data=keys), norm, quote)]


def _actor_facts(norm: dict[str, Any], quote: str) -> list[Fact]:
    ports = parse_bracketed_list(norm.get("content", ""))
    if not ports:
        return []
    name = norm.get("name", "") or "actor"
    return [_make_fact(Subject(type="actor", name=name), "value_enum_observed",
                       Value(type="set", data=ports), norm, quote)]


_KIND_MAP = {
    "message": _message_facts,
    "field": _field_facts,
    "state_machine": _state_machine_facts,
    "outcome": _outcome_facts,
    "protocol": _protocol_facts,
    "actor": _actor_facts,
}


def traffic_norm_to_facts(norm: dict[str, Any], capture_count: int = 1) -> list[Fact]:
    """单个 distinct traffic norm → 0 或多个 observed Fact。"""
    kind = norm.get("kind", "")
    fn = _KIND_MAP.get(kind)
    if fn is None:
        return []
    return fn(norm, _quote(norm.get("content", ""), capture_count))


def traffic_norms_to_facts(norms: list[dict]) -> tuple[list[Fact], int]:
    """全部 traffic norms → 去重 + 映射，返回 (facts, 跳过数)。

    按 norm_id 去重（跨 pcap+raw），capture_count = 该 norm_id 出现的行数。
    """
    distinct: dict[str, list] = {}
    for n in norms:
        nid = n.get("norm_id", "")
        if nid not in distinct:
            distinct[nid] = [n, 0]
        distinct[nid][1] += 1
    facts: list[Fact] = []
    skipped = 0
    for norm, cnt in distinct.values():
        mapped = traffic_norm_to_facts(norm, cnt)
        if not mapped:
            skipped += 1
        else:
            facts.extend(mapped)
    return facts, skipped
