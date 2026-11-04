"""core/fused/norm.py —— Layer 2: 知识源 ProtocolNorm → v2 Fact 的原生映射。

rfc 源的 5 种 kind 映射已全部实现（transition / field / outcome / method / constraint，见 RFC_KIND_MAP）。

设计依据: fused_hub/docs/fused_knowledge_hub_design.md +
           fused_hub/docs/rtsp_profile_v1_draft.md +
           local/layer2_extraction_methods.md（LLM 增强部分留 -m llm 钩子）。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from core.fused.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.canonical import (
    compute_fact_id, compute_claim_id, compute_evidence_id,
)


# ===========================================================================
# 公共构造
# ===========================================================================

def _make_evidence(norm: dict[str, Any], claim_id: str) -> Evidence:
    """从 norm 构造 evidence（evidence_id 依赖 source_type+source_id+locator）。"""
    ev = Evidence(
        evidence_id="placeholder",
        claim_id=claim_id,
        source_type=norm.get("kb_source_type", "rfc"),
        source_id=norm.get("norm_id", ""),
        document=norm.get("source", ""),
        locator=None,
        quote=norm.get("content", ""),
        content_fingerprint="",
        extraction_fingerprint="",
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
               epistemic_type: str, norm: dict[str, Any]) -> Fact:
    """构造单个 v2 Fact（subject + aspect + value，单 claim）。"""
    fact_key = FactKey(
        protocol=norm.get("protocol", "rtsp"),
        version="1.0",
        subject=subject,
        aspect=aspect,
        condition=ConditionAlways())
    fact_id = compute_fact_id(fact_key)
    tmp = Claim(
        claim_id="placeholder", fact_id=fact_id,
        value=value, epistemic_type=epistemic_type,
        authority=norm.get("kb_source_type", "rfc"), scope=Scope(), evidence=(),
    )
    cid = compute_claim_id(tmp)
    ev = _make_evidence(norm, cid)
    claim = Claim(
        claim_id=cid, fact_id=fact_id,
        value=value, epistemic_type=epistemic_type,
        authority=norm.get("kb_source_type", "rfc"), scope=Scope(),
        evidence=(ev,), confidence=None,
    )
    return Fact(
        fact_id=fact_id, fact_key=fact_key, claims=(claim,),
        resolution=None, alignments=(),
        metadata=FactMetadata(created_at="2026-10-08", profile_version="rtsp-v1"),
    )


# ===========================================================================
# 解析器
# ===========================================================================

def parse_transition_content(content: str) -> dict:
    """解析 'from=Init method=SETUP code=200 to=Ready' → dict。"""
    out: dict[str, str] = {}
    for part in content.split():
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def parse_field_content(content: str) -> tuple[str, str, str]:
    """解析 '语法 | <modality>: 语义' → (syntax, modality, semantic)。

    以最后一个 '| <word>:' 作为分隔点（ABNF 的 '|' 后跟引号，不匹配本模式）。
    """
    matches = list(re.finditer(r"\|\s*([A-Za-z]+)\s*:", content))
    if not matches:
        return content.strip(), "", ""
    m = matches[-1]
    syntax = content[:m.start()].strip()
    modality = m.group(1)
    semantic = content[m.end():].strip()
    return syntax, modality, semantic


_MODALITY_TO_EPISTEMIC = {
    "required": "must",
    "optional": "normative_unspecified",
    "should": "normative_unspecified",
    "may": "normative_unspecified",
}


def parse_outcome_content(content: str) -> tuple[str, str]:
    """解析 '含义 | when: 条件' → (meaning, condition)。

    ★ P1-1 修复（2026-11-01）：原正则**缺 `re.DOTALL`** ⇒ `.` 不匹配换行 ⇒
      只要 `| when:` 之后有换行（RFC 正文必然多行），整条正则**匹配失败** ⇒
      走 else 分支：`condition` 为空，且 `meaning` 里混入了完整的 `| when: ...`
      文本。实测三协议 65 个 outcome 里 **52 个（80%）** condition 丢失
      （rtsp 13/15 = 87%、sip 39/50 = 78%）—— 语义层数据是错的。

    ★ `re.DOTALL` 是**承重**的：去掉它 ⇒ 回归 P1-1（`.` 不匹配换行 ⇒
      `| when:` 之后一旦有换行，整条正则匹配失败 ⇒ condition 恒空）。
    ★ 取**首个** `| when:` 作分隔点（`meaning` 在前、条件在后）；
      reason 短语里若含 `| when` 但后面不接冒号，不会被误匹配。
    """
    m = re.search(r"\|\s*when\s*:\s*(.*)$", content, re.DOTALL)
    if m:
        meaning = content[:m.start()].strip()
        condition = m.group(1).strip()
    else:
        meaning = content.strip()
        condition = ""
    return meaning, condition


# ===========================================================================
# 映射
# ===========================================================================

def transition_norm_to_fact(norm: dict[str, Any]) -> Fact:
    """rfc transition norm → v2 relation Fact (aspect=target_state)。

    qualifiers 保留 source/target state + method（触发转移的方法）——
    seedgen 需要「from_state --method--> to_state」完整三元组。

    ★注意（2026-10-21）：当前 rfc_extractor.extract_rfc_norms 不产 kind="transition"
    的 norm（RFC 状态机是自然语言场景描述，非确定性标题，见 rfc_extractor 注释），
    故本映射目前无数据源（死代码）。
    保留此映射作为「rfc LLM 补状态机」的未来接口；状态机当前由 source 源（AutoSeeder）提供。
    """
    d = parse_transition_content(norm.get("content", ""))
    src = d.get("from", "")
    tgt = d.get("to", "")
    method = d.get("method", "")
    subject = Subject(
        type="relation",
        name="transitions_to",
        qualifiers={
            "source": Subject(type="state", name=src),
            "target": Subject(type="state", name=tgt),
            "method": Subject(type="method", name=method),
        })
    return _make_fact(subject, "target_state", Value(type="text", data=tgt),
                      "normative_unspecified", norm)


def _qualified_subject(stype: str, name: str,
                        norm: dict[str, Any]) -> Subject:
    """构造 subject；带 `origin` 标记的 norm 追加**来源限定子**。

    ★ B-4 附带修复：fact_id 只由 fact_key 决定 ⇒ 同一 (subject, aspect) 的两个
      norm（确定性抽取 + LLM 结构兜底）会产出**同一个 fact_id**
      ⇒ `dup_fact_ids > 0` ⇒ `--constraints` 构建被质量闸阻断
      （实测 smtp 10 个方法全撞）。
      用 `origin` 限定子把两者区分为**不同事实**（实体仍是同一个方法/字段）。
    ⚠ `subject.name` **不变** ⇒ 下游 bundle（rag_seedgen）按 name 聚合的
      分桶行为**完全不变**。
    """
    subject = Subject(type=stype, name=name)
    origin = str(norm.get("origin") or "").strip()
    if origin:
        subject.qualifiers["origin"] = origin
    return subject


def field_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """rfc field norm → [syntax fact, definition fact]（缺失部分跳过）。"""
    syntax, modality, semantic = parse_field_content(norm.get("content", ""))
    name = norm.get("name", "")
    epistemic = _MODALITY_TO_EPISTEMIC.get(modality, "normative_unspecified")
    facts: list[Fact] = []
    subject = _qualified_subject("header", name, norm)
    if syntax:
        facts.append(_make_fact(
            subject, "syntax",
            Value(type="pattern", data=syntax), epistemic, norm))
    if semantic:
        facts.append(_make_fact(
            subject, "definition",
            Value(type="text", data=semantic), epistemic, norm))
    return facts


#: ★ 批次 2.0（P0）：取值样本在 norm content 里的分隔符（与 rfc_extractor 同源）
VALUE_SAMPLE_SEP = " |~| "


def parse_field_value_content(content: str) -> tuple[str, list[str]]:
    """解析 ``"<字段名> | values: v1 |~| v2"`` → ``(字段名, [v1, v2])``。

    ★ 批次 2.0（P0）：RFC 源补齐「字段取值」的专用载体。
      此前 RFC 源只贡献 syntax + definition ⇒ 知识中枢 ``headers`` 桶
      **取值池大面积为空**（rtsp 48% / sip 41%，含 sip 的**必填头**）
      ⇒ 直接压制 ⑤ 层 ``value-pool-boundary`` 规则（没有另一个取值可换）。
    """
    body = content or ""
    if "| values:" not in body:
        name = body.split("|", 1)[0].strip()
        return name, []
    head, tail = body.split("| values:", 1)
    name = head.split("|", 1)[0].strip()
    values = [v.strip() for v in tail.split(VALUE_SAMPLE_SEP) if v.strip()]
    return name, values


def field_value_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """rfc field_value norm → [value_enum fact]（字段的取值样本集合）。

    ★ 批次 2.0（P0）：aspect 契约见 ``fused_hub/schema/aspect_registry.json`` ——
      ``value_enum`` 的 ``value_type = "set"``、适用主体 = header/protocol/actor
      ⇒ 这里用 ``header`` + ``Value(type="set", data=[...])``。
    """
    name, values = parse_field_value_content(norm.get("content", ""))
    if not name or not values:
        return []
    subject = _qualified_subject("header", name, norm)
    return [_make_fact(
        subject, "value_enum",
        Value(type="set", data=sorted(set(values))),
        "normative_unspecified", norm)]


def outcome_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """rfc outcome norm → [definition fact]（when 条件暂存 evidence.quote）。"""
    meaning, condition = parse_outcome_content(norm.get("content", ""))
    name = norm.get("name", "")
    if not meaning:
        return []
    return [_make_fact(
        _qualified_subject("status", name, norm), "definition",
        Value(type="text", data=meaning), "normative_unspecified", norm)]


def method_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """rfc method norm → [definition fact]（方法语义定义）。"""
    name = norm.get("name", "")
    content = (norm.get("content", "") or "").strip()
    if not content:
        return []
    return [_make_fact(
        _qualified_subject("method", name, norm), "definition",
        Value(type="text", data=content), "normative_unspecified", norm)]


#: 约束 content 的已知 key（按 key= 边界切分，值可含空格）
#: ★ ``operator`` / ``operand`` 是**结构化算子**通道：
#:   LLM 直接给出的受控算子与取值 ⇒ norm → fact 链路不再从中文自由文本反推算子。
#:   ★ ``operand`` 用逗号分隔承载（列表语义，见 ``parse_constraint_operand``）。
_RE_CONSTRAINT_SPLIT = re.compile(
    r"\b(field|constraint|violation|code|behavior|operator|operand)=")


def parse_constraint_content(content: str) -> dict[str, str]:
    """解析 'field=X constraint=Y violation=Z code=W behavior=V' → dict。

    值可能含空格（LLM 输出如「单 label 长度 <= 63」），不能按空白 split；
    改为按已知 key= 边界切分，避免把多词值打散。返回 dict（缺 key 则无该键）。
    """
    out: dict[str, str] = {}
    parts = _RE_CONSTRAINT_SPLIT.split(content or "")
    # parts = ['', 'field', 'X ', 'constraint', 'Y ', ...]（捕获组使 key 与值交替出现）
    for i in range(1, len(parts), 2):
        key = parts[i]
        val = parts[i + 1].strip() if i + 1 < len(parts) else ""
        out[key] = val
    return out


def parse_constraint_operand(content: str) -> list[str]:
    """从 content 串取 ``operand`` 列表（逗号分隔 → 字符串数组）。

    ★ 与 :func:`parse_constraint_content` 同口径（同一套切分正则）。
    ★ 空串 ⇒ 空列表（无参算子 present/absent 的正常形态）。
    """
    raw = parse_constraint_content(content or "").get("operand") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


#: 约束身份的**结构化字段**（判别位只用这些，**不含**自由措辞字段）。
#: - `expected_behavior` 是 LLM 的自由文本（"返回 FORMERR 错误"）⇒ 不可做判别位。
#: - `constraint` / `violation` 是约束的**语义内容**（"单 label ≤ 63 字节"）⇒ 可做判别位。
_CONSTRAINT_IDENTITY_FIELDS = ("field", "constraint", "violation", "code")


def normalize_constraint_identity_part(value: Any) -> str:
    """归一化约束身份的一个字段：NFKC + 空白折叠 + 去首尾空白 + 大小写折叠。

    ★ 归一化的目的：让**排版差异**（大小写、多余空白、全/半角）不改变 id，
      而**语义差异**（约束内容不同）一定改变 id。
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip().casefold()


def constraint_identity_digest(field: Any, constraint: Any,
                               violation: Any, code: Any) -> str:
    """约束的**结构化身份摘要**（sha256 前 10 位十六进制）。

    ★ **不用 Python 的 `hash()`**：str 的 hash 按进程随机化（PYTHONHASHSEED）
      ⇒ 同一约束在不同进程/机器上得到不同的 id ⇒ 幂等键失效、build_id 漂移。
      必须用 hashlib（sha256）—— 跨机器、跨进程、跨版本**稳定可复现**。
    ★ **判别位只用结构化字段**（field/constraint/violation/code），**不含**
      `expected_behavior`（LLM 自由措辞）—— 同一语义不同措辞必须得到同一 id，
      否则同一约束会被当成多条重复入库（并撞 norm_id）。
    """
    values = {"field": field, "constraint": constraint,
              "violation": violation, "code": code}
    # ★ 字段顺序由 `_CONSTRAINT_IDENTITY_FIELDS` 固定 ⇒ 摘要可复现。
    parts = [normalize_constraint_identity_part(values[k])
             for k in _CONSTRAINT_IDENTITY_FIELDS]
    payload = "\x1f".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def constraint_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """rfc constraint norm → [legal_boundary fact, response_expectation fact]。

    对齐 SemFuzz 的「构造约束 C + 处理期望 P」配对：
      - 构造约束 C → legal_boundary（Subject=header, value={dim,legal,illegal,trigger}）
      - 处理期望 P → response_expectation（Subject=header, value={violation,expected_code,expected_behavior}）
    epistemic 用 "must"（RFC 2119 MUST 强制要求）。
    """
    d = parse_constraint_content(norm.get("content", ""))
    field = d.get("field") or norm.get("name", "")
    constraint = d.get("constraint", "")
    violation = d.get("violation", "")
    code = d.get("code", "")
    behavior = d.get("behavior", "")
    # ★ 结构化算子（LLM 直接给出）⇒ 随 fact 一起下沉到下游。
    operator = d.get("operator", "")
    operand = parse_constraint_operand(norm.get("content", ""))
    # ★ B-4：同一 field 的**多条**约束必须产出**不同的 fact_key** ——
    #   fact_id 只由 fact_key 决定（**不含 value**）⇒ 同字段多约束会产出
    #   **同一个 fact_id** ⇒ `dup_fact_ids > 0` ⇒ 质量闸阻断构建
    #   （实测同字段 3 条约束 → 4 个重复 fact_id）。
    #   用**结构化身份摘要**做 subject 限定子：它只依赖
    #   (field, constraint, violation, code)，**跨进程/跨机器稳定**
    #   （不用 LLM 自由措辞、不用随机化的 hash()）。
    #   ⚠ subject.name 仍是字段名 ⇒ 下游 bundle 的 legal_boundary /
    #     response_expectation 分桶（按 name 聚合）行为**完全不变**。
    digest = constraint_identity_digest(field, constraint, violation, code)
    subject = _qualified_subject("header", field, norm)
    subject.qualifiers["constraint_id"] = digest
    facts: list[Fact] = []
    if field and constraint:
        facts.append(_make_fact(
            subject, "legal_boundary",
            Value(type="struct", data={"dim": field, "legal": constraint,
                                       "illegal": violation, "trigger": behavior,
                                       "operator": operator,
                                       "operand": operand}),
            "must", norm))
    if field and (code or behavior):
        facts.append(_make_fact(
            subject, "response_expectation",
            Value(type="struct", data={"violation": violation,
                                       "expected_code": code,
                                       "expected_behavior": behavior}),
            "must", norm))
    return facts


#: rfc 源 kind → 映射函数（返回 list[Fact]）
RFC_KIND_MAP = {
    "transition": lambda n: [transition_norm_to_fact(n)],
    "field": field_norm_to_facts,
    # ★ 批次 2.0（P0）：字段取值样本 → value_enum fact
    "field_value": field_value_norm_to_facts,
    "outcome": outcome_norm_to_facts,
    "method": method_norm_to_facts,
    "constraint": constraint_norm_to_facts,
}


def map_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """按 norm 的 (kb_source_type, kind) 分派，返回 0 或多个 v2 Fact。"""
    source_type = norm.get("kb_source_type", "")
    kind = norm.get("kind", "")
    if source_type == "rfc":
        fn = RFC_KIND_MAP.get(kind)
        if fn is None:
            return []
        return fn(norm)
    return []
