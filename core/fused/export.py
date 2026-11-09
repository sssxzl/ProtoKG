"""core/fused/export.py —— LLM 安全接口 (P10)。

导出格式严格按 fused_knowledge_hub_design.md 第五部分。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.fused.models import (
    Fact, Claim, Evidence, Resolution, Support, Generalization,
)
# ★ 2026-11-08：v1 兼容层（core/fused/compat.py）已删 ⇒ v1 产物
#   （derived/fused/）不再存在 ⇒ 下面只接受 v2 shape。


# ===========================================================================
# 单层视图
# ===========================================================================

def get_evidence_view(evidence: Evidence) -> dict:
    loc = evidence.locator
    if loc is None:
        loc_d = None
    elif hasattr(loc, "type"):
        # 联合类型 → 按字段 dict
        loc_d = {"type": getattr(loc, "type", "")}
        for k in ("file", "line", "col", "offset", "length",
                  "timestamp", "path", "start", "end"):
            if hasattr(loc, k):
                v = getattr(loc, k, None)
                if v is not None and v != () and v != "":
                    loc_d[k] = list(v) if isinstance(v, tuple) else v
    else:
        loc_d = None
    return {
        "evidence_id": evidence.evidence_id,
        "claim_id": evidence.claim_id,
        "source_type": evidence.source_type,
        "source_id": evidence.source_id,
        "document": evidence.document,
        "locator": loc_d,
        "quote": evidence.quote,
        "content_fingerprint": evidence.content_fingerprint,
        "extraction_fingerprint": evidence.extraction_fingerprint,
    }


def _evidence_summary_item(evidence) -> str:
    """一条 evidence 的摘要串：**协议级锚点 + 文件锚点**（多 RFC 协议可溯源）。

    ★ 2026-11-07：旧形态只有 ``{source_type}:{source_id}``，而 source_id 是
      **协议级**的（norm_id = ``{protocol}.{kind}.{name}``）⇒ 一个协议有多份 RFC
      时，中枢里**分不清某条知识来自哪份 RFC**（实测 smtp 的 4 份 RFC 全混在一起）。

    ★ 新形态：``{source_type}:{source_id}@{document}``
      —— ``document`` 形如 ``file:rfc5321.txt#@1814``（**文件名 + 行号锚点**）。

    ★ 三条兼容约束：
      ① **前缀不变**（``{source_type}:{source_id}`` 原样保留）⇒ 现有按
         ``split(":")[1]`` / ``startswith`` 解析的代码不受影响；
      ② ``document`` 为空 ⇒ 输出与旧形态**完全一致**（不引入 ``@``）；
      ③ ``document`` 与 ``source_id`` **重复**时（如 source_id 本身就是文件名）
         ⇒ 不重复附加，避免 ``rfc:rfc2326.txt@rfc2326.txt`` 这种冗余。
    """
    base = f"{evidence.source_type}:{evidence.source_id}"
    doc = str(getattr(evidence, "document", "") or "")
    if not doc:
        return base
    # ③ document 与 source_id 重复 ⇒ 只在「含文件名部分」时才附加
    if doc == evidence.source_id:
        return base
    return f"{base}@{doc}"


def get_claim_view(claim: Claim) -> dict:
    v = claim.value
    return {
        "claim_id": claim.claim_id,
        "fact_id": claim.fact_id,
        "value": {"type": v.type, "data": v.data} if v else None,
        "epistemic_type": claim.epistemic_type,
        "authority": claim.authority,
        # 注：原 scope 字段用 claim.scope.in_scope，但 Scope dataclass 无 in_scope
        # 属性（恒 None），属死字段，已移除。Scope 细节不进 LLM 安全视图。
        # ★ 2026-11-07：evidence_summary **带文件锚点**（多 RFC 协议可溯源）。
        #   旧形态只拼 ``{source_type}:{source_id}`` ⇒ source_id 是**协议级**的
        #   （norm_id = ``{protocol}.{kind}.{name}``）⇒ 一个协议有多份 RFC 时，
        #   中枢里**分不清某条知识来自哪份 RFC**（实测 smtp 4 份 RFC 全部混在一起）。
        #   新形态：``{source_type}:{source_id}@{document}``，其中 document 形如
        #   ``file:rfc5321.txt#@1814``（**文件名 + 行号锚点**）。
        #   ★ 向后兼容：``@`` 之后的部分是**附加**信息，原前缀不变
        #     ⇒ 现有按 ``split(":")[1]`` 或 ``startswith`` 解析的代码不受影响。
        "evidence_summary": [
            _evidence_summary_item(e) for e in claim.evidence
        ],
        "confidence": claim.confidence,
    }


def _subject_view(subj) -> dict:
    """递归序列化 Subject (qualifiers 里可能嵌套 Subject, 如 relation 的 source/target)。"""
    qualifiers = {}
    for k, v in (subj.qualifiers or {}).items():
        if hasattr(v, "type") and hasattr(v, "name") and hasattr(v, "qualifiers"):
            qualifiers[k] = _subject_view(v)
        else:
            qualifiers[k] = v
    return {
        "type": subj.type,
        "name": subj.name,
        "qualifiers": qualifiers,
        "path": list(subj.path or []),
    }


def get_fact_view(fact: Fact) -> dict:
    fk = fact.fact_key
    fk_view = {
        "protocol": fk.protocol,
        "version": fk.version,
        "subject": _subject_view(fk.subject),
        "aspect": fk.aspect,
        "condition": {"type": fk.condition.type},
    }

    if fact.resolution:
        r = fact.resolution
        sup = (r.support.__dict__ if r.support else None)
        gen = (r.generalization.__dict__ if r.generalization else None)
        # 解析后的 value: 优先取 basis_claim_ids 第一条对应的 claim.value
        val = None
        if r.basis_claim_ids:
            for c in fact.claims:
                if c.claim_id in r.basis_claim_ids:
                    val = {"type": c.value.type, "data": c.value.data}
                    break
        # 单源 fallback (method=single 且只有一条 claim)
        if val is None and r.method == "single" and len(fact.claims) == 1:
            val = {"type": fact.claims[0].value.type,
                   "data": fact.claims[0].value.data}
        res_view = {
            "status": r.status,
            "method": r.method,
            "value": val,
            "epistemic": (r.method if r.method in
                           ("single", "consensus", "precedence",
                            "conflict", "insufficient") else None),
            "basis_claim_ids": list(r.basis_claim_ids),
            "reason": r.reason,
            "reason_code": r.reason_code,
            "policy_version": r.policy_version,
            "support": sup,
            "generalization": gen,
        }
        # 冲突显式呈现（P9）
        if r.status == "unresolved" and r.method == "conflict":
            res_view["conflicting_claims"] = [
                get_claim_view(c) for c in fact.claims
            ]
    else:
        res_view = None

    return {
        "fact_key": fk_view,
        "resolution": res_view,
        "all_claims": [get_claim_view(c) for c in fact.claims],
    }


# ===========================================================================
# 整库导出
# ===========================================================================

def export_facts_for_llm(protocol: str, version: str,
                         facts_source: Path,
                         profile_version: str = "v2") -> dict:
    """从 Fact 列表或 JSONL 读, 产出 LLM 安全导出。

    支持两种输入:
      - list[Fact]: 直接给出
      - Path: 指向 JSONL, 每行一个 Fact 的 JSON 表示
    """
    if isinstance(facts_source, list):
        facts = facts_source
    else:
        facts = []
        with Path(facts_source).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    item = json.loads(line)
                    # 兼容: list 元素可能是 Fact 对象或 view dict
                    if isinstance(item, dict):
                        facts.append(_deserialize(item)
                                     if "fact_key" in item
                                     else _fact_from_json(line))
                    else:
                        facts.append(item)
    # view dict 列表: 直接 wrap 成 view 输出, 不再过 get_fact_view
    if facts and isinstance(facts[0], dict) and "fact_key" in facts[0]:
        return {
            "protocol": protocol,
            "profile_version": profile_version,
            "facts": list(facts),
        }

    return {
        "protocol": protocol,
        "profile_version": profile_version,
        "facts": [get_fact_view(f) for f in facts],
    }


def _fact_from_json(line: str) -> Fact:
    """把 JSON 行还原为 Fact 对象 (用于 export_facts_for_llm 读 JSONL)。

    ⚠ 双轨阶段: 读进来的可能是 v1 shape (kind/subject/property) 或 v2 shape
    (subject.type/name/aspect)。先按 v2 试, 失败按 v1 试, 再失败抛。
    """
    obj = json.loads(line)
    if isinstance(obj, dict) and "subject" in obj and "aspect" in obj:
        return _deserialize(obj)
    # ★ v1 shape 已下线（v1 产物与兼容层都已移除）⇒ 明确报错而非静默降级
    raise ValueError("fact 行不是 v2 shape（缺 subject/aspect）")


def _deserialize(obj: dict) -> Fact:
    """从 v2 shape dict 还原 Fact 对象 (双轨阶段, 简化版)。"""
    from core.fused.models import (
        Subject, FactKey, Value, Claim, Evidence, Scope,
        ConditionAlways, FactMetadata,
    )
    fk_d = obj["fact_key"]
    subj = Subject(
        type=fk_d["subject"]["type"],
        name=fk_d["subject"]["name"],
        qualifiers=fk_d["subject"].get("qualifiers", {}),
        path=fk_d["subject"].get("path", []))
    fid = obj.get("fact_id")
    if not fid:
        from core.fused.canonical import compute_fact_id
        fid = compute_fact_id(FactKey(protocol=fk_d["protocol"],
                                       version=fk_d["version"],
                                       subject=subj, aspect=fk_d["aspect"],
                                       condition=ConditionAlways()))
    new_claims = []
    for c_d in obj.get("all_claims", []):
        v_d = c_d.get("value") or {}
        ev_d = Evidence(
            evidence_id=f"e_{len(new_claims)}", claim_id=c_d["claim_id"],
            source_type="legacy", source_id="shape",
            document="v2 jsonl", locator=None,
            content_fingerprint="", extraction_fingerprint="")
        new_claims.append(Claim(
            claim_id=c_d["claim_id"], fact_id=fid,
            value=Value(type=v_d.get("type", "scalar"), data=v_d.get("data")),
            epistemic_type=c_d.get("epistemic_type", "descriptive"),
            authority=c_d.get("authority", "registry"),
            scope=Scope(), evidence=(ev_d,)))
    # resolution 可能是 dict, 也可能是 None, 也可能是来自 view 的字符串
    raw_res = obj.get("resolution")
    res = None
    if isinstance(raw_res, dict):
        # 已是 view 形态(扁平 dict), 反序列化简化为 None —— 双轨阶段不重建
        res = None
    return Fact(
        fact_id=fid,
        fact_key=FactKey(protocol=fk_d["protocol"], version=fk_d["version"],
                         subject=subj, aspect=fk_d["aspect"],
                         condition=ConditionAlways()),
        claims=tuple(new_claims), resolution=res, alignments=(),
        metadata=FactMetadata(profile_version="v2"))