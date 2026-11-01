"""core/fused/compat.py —— v1 fact → v2 Fact 的双轨映射。

⚠ 只读 derived/fused/facts/（v1 遗留产物，131 条），本模块不写该目录。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.fused.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.canonical import (
    canonical_serialize, compute_fact_id, compute_claim_id, compute_evidence_id,
)


# ===========================================================================
# 映射表（与 fused_compatibility_mapping.md 严格一致）
# ===========================================================================

_ACTOR_TO_QUALIFIER = {"client": "client", "server": "server"}
_KIND_TO_TYPE = {
    "method": "method",
    "header": "header",
    "state": "state",
    "constraint": "status",   # 旧约束 status.NNN 归 status
    "transition": "relation",
    "packet_role_pair": "packet_role",
}
#: 注意（2026-10-21）：下面 header 侧映射出的 value_type/value_range/default_value/
#: case_sensitivity/observed_presence_rate/observed_co_occurrence/observed_occurrence_rate
#: 这些 aspect，在 assemble_bundle（下游消费端）的 header 分支【无对应处理】，会被
#: 静默丢弃。它们是 v1 双轨迁移的历史遗留；若确认 v2 种子生成不需要这些观测统计，
#: 应从此表删除，避免「映射了但没人消费」的误导。当前保留以维持 v1→v2 兼容性。
_PROPERTY_TO_ASPECT = {
    # method
    "existence": "existence",
    "security_condition": "security_property",
    "security_consequence": "security_property",    # Step A2 2026-10-08: 补映射 (vuln CVE 后果描述归 security_property 桶)
    "relation_to_other_field": "relation_to_other",
    "occurrence": "occurrence",
    # header
    "value_type": "value_type",
    "value_range": "value_range",
    "default_value": "default_value",
    "case_sensitivity": "case_sensitivity",
    "observed_presence_rate": "observed_presence_rate",
    "observed_co_occurrence": "observed_co_occurrence",
    "observed_occurrence_rate": "observed_occurrence_rate",
    # state
    "target_state": "target_state",
}

# v1→v2 迁移期（2026-10-08）：v1 assertion.type → v2 ValueType 命名映射
# v1 实测 5 值: bool/number/text/enum/relation; v2 ValueType 为 12 种
# (bool/number → scalar; relation → struct [用户裁定])
_VTYPE_MAP = {
    "bool": "scalar",
    "number": "scalar",
    "text": "text",
    "enum": "enum",
    "relation": "struct",
}


def _subject_from_kind(v1_kind: str, v1_subject: str, v1_property: str) -> Subject | None:
    """旧 (kind, subject, property) → 新 Subject. 失败返回 None。"""
    # transition 是关系型, 主体是 "transitions_to" + qualifiers
    if v1_kind == "transition":
        # 旧 transition 通常主体是 "from→to" 字符串或 state 组合
        # 极简化处理: 当 subject 是 "Init→Ready" 这类字符串时拆成 qualifiers
        sep = "→" if "→" in v1_subject else ("->" if "->" in v1_subject else None)
        if sep:
            src, tgt = v1_subject.split(sep, 1)
            return Subject(
                type="relation",
                name="transitions_to",
                qualifiers={
                    "source": Subject(type="state", name=src.strip()),
                    "target": Subject(type="state", name=tgt.strip()),
                })
        return Subject(type="state", name=v1_subject)

    if v1_kind == "constraint":
        # 旧 "status.413" 类格式: kind=constraint, subject=status.413
        name = v1_subject
        if name.startswith("status."):
            return Subject(type="status", name=name[len("status."):])
        return Subject(type="status", name=name)

    typ = _KIND_TO_TYPE.get(v1_kind)
    if typ is None:
        return None
    return Subject(type=typ, name=v1_subject)


def _aspect_from_property(v1_kind: str, v1_property: str) -> str | None:
    return _PROPERTY_TO_ASPECT.get(v1_property)


def _qualifiers_from_actor(v1_actor: str | None) -> dict:
    """client/server 进 qualifiers; both/not_applicable 丢弃。"""
    if v1_actor in _ACTOR_TO_QUALIFIER:
        return {"actor": _ACTOR_TO_QUALIFIER[v1_actor]}
    return {}


# ===========================================================================
# 转换入口
# ===========================================================================

def convert_v1_fact_jsonl(facts_jsonl_path: Path) -> tuple[list[Fact], list[dict]]:
    """从 derived/fused/facts/<kind>.jsonl 读 v1 facts, 转换到 v2 Fact 列表。

    返回: (转换成功的 v2 Fact 列表, 失败清单[dict])

    ★ 多源 claim 合并规则:
      - 同 canonical fact_key 的多份 v1 fact → 一份 v2 Fact
      - claims[] = 所有源 claim 合并后, 按 claim_id 去重 (同 value)
      - 每条 claim 的 evidence[] = 同 claim_id 下所有源 evidence 合并后,
        按 evidence_id 去重
      - 同 claim_id 但 value 不同 → 抛 UnmergedClaimValueError (不自行裁)
    """
    out: list[Fact] = []
    errs: list[dict] = []

    # 先逐行解析, 按 v2 canonical fact_key 聚合
    by_key: dict[str, list[dict]] = {}    # key -> [v1_obj, ...]
    for line in Path(facts_jsonl_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errs.append({"line": line[:200], "reason": f"json decode: {exc}"})
            continue
        f = convert_v1_fact(line)
        if not isinstance(f, Fact):
            errs.append({"line": line[:200], "reason": f})
            continue
        # 用 v2 canonical fact_key 做聚合键
        k = canonical_serialize(f.fact_key)
        by_key.setdefault(k, []).append(f)

    # 再按组合并
    for k, group in by_key.items():
        try:
            out.append(_merge_group(group))
        except Exception as exc:  # noqa: BLE001
            errs.append({
                "canonical_key": k,
                "reason": str(exc),
                "group_size": len(group),
            })
    return out, errs


class UnmergedClaimValueError(Exception):
    """同 claim_id 但 value 不同 → 不自行裁, 抛错让上层裁.

    防御性断言（v1→v2 迁移期标记, 2026-10-08）。
    按 P7「内容决定 ID」设计 (canonical_serialize(value) + epistemic 决定 claim_id),
    不同 value 必然产生不同 claim_id, 故此异常在正常 v2 路径下不可达.
    唯一可能触发: canonical_serialize 被破坏 (e.g. dict 序未排序, 浮点精度未归一).
    若此异常被触发, 应先查 canonical.py 的稳定性, 再看 _merge_group 的
    触发条件, 不应直接处理此异常.
    """


def _merge_group(group: list) -> Fact:
    """合并一组同 canonical fact_key 的 v2 Fact → 一份 v2 Fact.

    规则（v1→v2 迁移期用户裁定）:
        1. claims[]: concat(所有源 claim), 按 claim_id 去重.
           同 claim_id 但 value 不同 → 抛 UnmergedClaimValueError.
        2. 每条 claim 的 evidence[]: concat(同 claim_id 下所有源 evidence),
           按 evidence_id 去重.
    """
    if not group:
        raise ValueError("empty group")
    f0 = group[0]   # fact_key / metadata 来自首条 (所有同 canonical 的 fact_key 一致)

    # 1. 合并 claims
    claims_by_id: dict[str, list] = {}
    for f in group:
        for c in f.claims:
            claims_by_id.setdefault(c.claim_id, []).append(c)
    merged_claims = []
    for cid, cs in claims_by_id.items():
        # 同 claim_id 的 value 必须一致 (canonical)
        canon_values = {canonical_serialize(c.value) for c in cs}
        if len(canon_values) > 1:
            raise UnmergedClaimValueError(
                f"claim_id {cid!r} 有 {len(canon_values)} 个不同 value: "
                f"{canon_values}")
        # 合并 evidence: 按 evidence_id 去重
        seen_ev: dict[str, object] = {}
        for c in cs:
            for e in c.evidence:
                if e.evidence_id not in seen_ev:
                    seen_ev[e.evidence_id] = e
        base = cs[0]
        merged_claims.append(Claim(
            claim_id=base.claim_id,
            fact_id="placeholder",    # 再算 (fact_id 决定后回填)
            value=base.value,
            epistemic_type=base.epistemic_type,
            authority=base.authority,
            scope=base.scope,
            evidence=tuple(seen_ev.values()),
            confidence=base.confidence,
        ))

    # 2. 重算 claim_id (fact_id 确定后回填)
    fact_id = compute_fact_id(f0.fact_key)
    final_claims = tuple(
        Claim(
            claim_id=c.claim_id,
            fact_id=fact_id,
            value=c.value,
            epistemic_type=c.epistemic_type,
            authority=c.authority,
            scope=c.scope,
            evidence=c.evidence,
            confidence=c.confidence,
        )
        for c in merged_claims
    )

    # 3. 重组 Fact (复用首条的 fact_key / metadata)
    return Fact(
        fact_id=fact_id,
        fact_key=f0.fact_key,
        claims=final_claims,
        resolution=f0.resolution,
        alignments=f0.alignments,
        metadata=f0.metadata,
    )


def convert_v1_fact(v1_fact_json: str) -> Fact | str:
    """单条 v1 fact (JSON 字符串) → v2 Fact. 失败时返回错误描述字符串。"""
    obj = json.loads(v1_fact_json)
    fk = obj.get("fact_key", {})
    v1_kind = fk.get("kind", "")
    v1_subject = fk.get("subject", "")
    v1_property = fk.get("property", "")
    v1_actor = fk.get("actor")
    v1_protocol = fk.get("protocol", "unknown")
    v1_version = fk.get("version", "1.0")

    new_subject = _subject_from_kind(v1_kind, v1_subject, v1_property)
    if new_subject is None:
        return f"unmapped kind={v1_kind!r}"

    new_aspect = _aspect_from_property(v1_kind, v1_property)
    if new_aspect is None:
        return f"unmapped property={v1_property!r}"

    # 旧 fact_key 的 actor 进 qualifiers
    qualifiers = _qualifiers_from_actor(v1_actor)
    if new_subject.type == "relation" and qualifiers:
        # relation 不加 actor qualifier (rel 不属于某个 actor)
        qualifiers = {}

    if qualifiers and "actor" in qualifiers:
        new_subject = Subject(type=new_subject.type, name=new_subject.name,
                             qualifiers=qualifiers, path=new_subject.path)

    new_fk = FactKey(protocol=v1_protocol, version=v1_version,
                    subject=new_subject, aspect=new_aspect,
                    condition=ConditionAlways())

    # Claim 转换: 旧 claims[*].assertion.value/type/modality → Claim
    old_claims = obj.get("claims") or []
    new_claims = []
    for old in old_claims:
        old_a = old.get("assertion", {}) or {}
        old_v = old_a.get("value")
        old_t = old_a.get("type", "scalar")
        old_m = old_a.get("modality", "")
        # 旧 evidence 走 claim.evidence[] (A5-fix 2026-10-08):
        # 不再用 fact.audit_refs 透传 (稀疏, 85% 空, 丢弃 99.5% v1 evidence 数据).
        # 现在逐条 v1 evidence 构造 v2 Evidence, evidence_id 走 compute_evidence_id (e2_).
        new_evidences = []
        for old_ev in old.get("evidence", []) or []:
            ev_obj = Evidence(
                evidence_id="placeholder",    # 由 compute_evidence_id 覆盖
                claim_id="placeholder",
                source_type=old_ev.get("source_type", "unknown"),
                source_id=old_ev.get("source_id", v1_protocol),
                document=old_ev.get("document", ""),
                locator=old_ev.get("locator"),    # v1 dict, 由 canonical_serialize 处理
                quote=old_ev.get("quote"),
                content_fingerprint=old_ev.get("content_fingerprint", ""),
                extraction_fingerprint=old_ev.get("extraction_fingerprint", ""),
            )
            ev_obj = Evidence(
                evidence_id=compute_evidence_id(ev_obj),
                claim_id=ev_obj.claim_id,
                source_type=ev_obj.source_type,
                source_id=ev_obj.source_id,
                document=ev_obj.document,
                locator=ev_obj.locator,
                quote=ev_obj.quote,
                content_fingerprint=ev_obj.content_fingerprint,
                extraction_fingerprint=ev_obj.extraction_fingerprint,
            )
            new_evidences.append(ev_obj)
        new_claims.append(Claim(
            claim_id=compute_claim_id(Claim(
                claim_id="placeholder", fact_id="placeholder",
                value=Value(type=_VTYPE_MAP.get(old_t, old_t), data=old_v),
                epistemic_type=old_m or "descriptive",
                authority=((old.get("authority") or {}).get("level") or "registry"),
                scope=Scope(observation_population=None, measurement_unit=None,
                           independence="unknown", bounded=False, bounds={}),
                evidence=tuple(new_evidences))),
            fact_id="placeholder",
            value=Value(type=_VTYPE_MAP.get(old_t, old_t), data=old_v),
            epistemic_type=old_m or "descriptive",
            authority=((old.get("authority") or {}).get("level") or "registry"),
            scope=Scope(observation_population=None, measurement_unit=None,
                       independence="unknown", bounded=False, bounds={}),
            evidence=tuple(new_evidences)))

    # resolution
    old_res = obj.get("resolution") or {}
    new_resolution = None
    if old_res:
        new_resolution = None  # 双轨阶段, 旧 resolution 不映射, 由 v2 自己重算

    new_metadata = FactMetadata(
        created_at="2026-10-08",
        profile_version="compat",
    )

    new_fact_id = compute_fact_id(new_fk)
    new_fact = Fact(fact_id=new_fact_id, fact_key=new_fk, claims=tuple(new_claims),
                    resolution=new_resolution, alignments=(),
                    metadata=new_metadata)

    # 重填 claim_id（v2 设计: claim_id 包含 value + epistemic_type hash）
    new_fact = Fact(
        fact_id=new_fact.fact_id, fact_key=new_fact.fact_key,
        claims=tuple(
            Claim(claim_id=compute_claim_id(c), fact_id=new_fact.fact_id,
                  value=c.value, epistemic_type=c.epistemic_type,
                  authority=c.authority, scope=c.scope, evidence=c.evidence,
                  confidence=None)
            for c in new_claims
        ),
        resolution=new_fact.resolution, alignments=new_fact.alignments,
        metadata=new_fact.metadata)

    return new_fact