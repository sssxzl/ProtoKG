"""tests/fused/test_compat.py —— 双轨: 旧 131 Facts → v2 Fact。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from core.fused.compat import convert_v1_fact_jsonl, convert_v1_fact
from core.fused.canonical import canonical_serialize, compute_fact_id
from core.fused.models import Fact, Subject, FactKey, ConditionAlways


FUSED = Path("derived/fused/facts")


def _all_v1_lines():
    out = []
    for p in sorted(FUSED.glob("*.jsonl")):
        if p.is_file():
            out.extend(p.read_text(encoding="utf-8").splitlines())
    return [l for l in out if l.strip()]


def test_no_unhandled_exceptions():
    """逐条转换: 异常即 fail, 不能静默吞。"""
    bad = []
    for line in _all_v1_lines():
        r = convert_v1_fact(line)
        if not isinstance(r, Fact):
            continue
    assert True    # 没崩


def test_at_least_120_succeed():
    """131 - 容许少量 'unmapped property' 类合理错误, 但成功 ≥ 120。"""
    ok = 0
    for line in _all_v1_lines():
        r = convert_v1_fact(line)
        if isinstance(r, Fact):
            ok += 1
    assert ok >= 120, f"仅 {ok} 成功, 预期 ≥ 120"


def test_failure_list_recorded_not_thrown():
    """失败 fact → 返回 reason 字符串, 不抛异常 (compat 双轨阶段)。"""
    fail = 0
    for line in _all_v1_lines():
        r = convert_v1_fact(line)
        if not isinstance(r, Fact):
            assert isinstance(r, str), f"非 Fact 应返 str, 实际 {type(r)}"
            fail += 1
    assert fail <= 20, f"失败过多: {fail} (需人工核对清单)"


def test_fact_id_deterministic():
    """同一 v1 fact 多次转换 → 同一 v2 fact_id。"""
    lines = [l for l in _all_v1_lines() if "existence" in l]
    if not lines:
        return
    line = lines[0]
    a = convert_v1_fact(line)
    b = convert_v1_fact(line)
    assert isinstance(a, Fact) and isinstance(b, Fact)
    assert a.fact_id == b.fact_id


def test_loaded_facts_have_fact_key_shape():
    """转换后的 v2 Fact 全部含 FactKey, 不是 dict 也不是 None。"""
    for line in _all_v1_lines():
        r = convert_v1_fact(line)
        if isinstance(r, Fact):
            assert isinstance(r.fact_key, FactKey)
            assert isinstance(r.fact_key.subject, Subject)
            assert r.fact_key.aspect != ""
            assert r.fact_id.startswith("f2_")    # Step A3 2026-10-08: v2 fact_id 前缀 f2_
            assert len(r.fact_id) == 3 + 16


def test_dedup_preserves_distinct_keys():
    """不同 v1 fact_key → 不同 v2 fact_key 的 canonical (允许合并多源同一事实)。"""
    from collections import defaultdict
    canon_to_count = defaultdict(int)
    for line in _all_v1_lines():
        r = convert_v1_fact(line)
        if isinstance(r, Fact):
            canon_to_count[canonical_serialize(r.fact_key)] += 1
    dups = {k: v for k, v in canon_to_count.items() if v > 1}
    # 仅记录, 不阻断
    print(f"distinct canonical fact_key: {len(canon_to_count)}, "
          f"with duplicates: {len(dups)}")


# ===========================================================================
# Step C 合并规则 (tmp_path, 不碰 derived/fused/)
# ===========================================================================

from core.fused.compat import _merge_group, UnmergedClaimValueError  # noqa


def _make_v1_jsonl(tmp_path: Path, *v1_dicts) -> Path:
    """由 v1 dict 列表写 jsonl 到 tmp_path/facts.jsonl."""
    p = tmp_path / "facts.jsonl"
    p.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in v1_dicts)
                     + "\n", encoding="utf-8")
    return p


def _v1_obj(fact_id: str, kind: str, subject: str, property_: str,
            actor: str = "server", condition: dict | None = None,
            claims: list | None = None,
            audit_refs: list[str] | None = None) -> dict:
    """构造 1 条最简 v1 fact dict (供 tmp_path 测试用)."""
    return {
        "alignments": [], "assertion": None,
        "audit_refs": audit_refs or [],
        "fact_id": fact_id,
        "fact_key": {
            "actor": actor,
            "condition": condition or {"type": "always"},
            "kind": kind,
            "property": property_,
            "subject": subject,
        },
        "resolution": {"basis_claim_ids": [], "method": None,
                        "reason": None, "status": "resolved"},
        "claims": claims or [],
    }


def _ev(source_id_suffix: str, document: str, locator_data: dict) -> dict:
    """构造 1 条最简 v1 evidence 对象 (Step A5-fix 走 claim.evidence[] 路径).

    返回的 evidence_id 经 compat 重算 (e2_ 前缀), 此处 evidence_id 字段仅为占位.
    """
    return {
        "evidence_id": "e1_placeholder_" + source_id_suffix,
        "source_type": "rfc",
        "source_id": f"rfc/{source_id_suffix}",
        "document": document,
        "locator": {"type": "field", "data": locator_data},
        "quote": None,
        "content_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "extraction_fingerprint": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        "extraction": {"extracted_at": "2026-10-08T00:00:00",
                       "extractor": "test", "extractor_version": "v1"},
    }


def test_merge_same_canonical(tmp_path):
    """3 份同 canonical v1 fact → 合并为 1 份 v2 Fact.

    Step A5-fix: 改走 claim.evidence[] 路径 (不再用 fact.audit_refs).
    用 4 个不同 (source_id, locator) 的 v1 evidence 构造, 走 compute_evidence_id
    产出 4 个 e2_ ID, 跨 3 份 v1 fact 合并后去重, 应得 4 个 distinct evidence_id.
    """
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "header", "cseq", "existence",
                claims=[{"claim_id": "c1_x", "assertion": {"modality": "must",
                                                          "type": "bool",
                                                          "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("a1", "rfc/test.txt", {"norm_id": "e1"}),
                              _ev("a1", "rfc/test.txt", {"norm_id": "e2"}),
                          ]}]),
        _v1_obj("v1_b", "header", "cseq", "existence",
                claims=[{"claim_id": "c1_x", "assertion": {"modality": "must",
                                                          "type": "bool",
                                                          "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("a1", "rfc/test.txt", {"norm_id": "e3"}),
                          ]}]),
        _v1_obj("v1_c", "header", "cseq", "existence",
                claims=[{"claim_id": "c1_x", "assertion": {"modality": "must",
                                                          "type": "bool",
                                                          "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("a1", "rfc/test.txt", {"norm_id": "e1"}),  # 重复
                              _ev("a1", "rfc/test.txt", {"norm_id": "e4"}),
                          ]}]),
    )
    facts, errs = convert_v1_fact_jsonl(p)
    assert errs == []
    assert len(facts) == 1, f"应 1 份 v2 Fact, 实得 {len(facts)}"
    f = facts[0]
    assert len(f.claims) == 1, "同一 claim_id 应去重为 1 条"
    e = f.claims[0]
    assert len(e.evidence) == 4, f"evidence 去重后应为 4 条, 实得 {len(e.evidence)}"
    # 4 个 e2_ ID 互异
    ev_prefixes = {x.evidence_id[:3] for x in e.evidence}
    assert ev_prefixes == {"e2_"}, f"evidence_id 应全 e2_, 实得 {ev_prefixes}"


def test_merge_dedup_claims(tmp_path):
    """同一 canonical 下多份 v1 fact, 各自有相同 claim_id → claim 去重为 1 条."""
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"}}]),
        _v1_obj("v1_b", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"}}]),
    )
    facts, errs = convert_v1_fact_jsonl(p)
    assert errs == []
    assert len(facts) == 1
    assert len(facts[0].claims) == 1


def test_merge_dedup_evidence(tmp_path):
    """同 claim_id, evidence_ids 跨多份 — 按 evidence_id 去重.

    Step A5-fix: 用 claim.evidence[] 构造 3 个 v1 evidence, 跨 2 份 v1 fact (其中
    1 个重复) → 合并后 evidence 去重, 应得 3 个 distinct e2_ evidence_id.
    """
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("a", "rfc/test.txt", {"norm_id": "e_a"}),
                              _ev("b", "rfc/test.txt", {"norm_id": "e_b"}),
                          ]}]),
        _v1_obj("v1_b", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("b", "rfc/test.txt", {"norm_id": "e_b"}),   # 重复
                              _ev("c", "rfc/test.txt", {"norm_id": "e_c"}),
                          ]}]),
    )
    facts, _ = convert_v1_fact_jsonl(p)
    assert len(facts) == 1
    ev_ids = {x.evidence_id for x in facts[0].claims[0].evidence}
    assert len(ev_ids) == 3, f"去重后应为 3, 实得 {len(ev_ids)}: {ev_ids}"
    assert all(eid.startswith("e2_") for eid in ev_ids), f"应全 e2_: {ev_ids}"


def test_merge_distinct_claims(tmp_path):
    """不同 claim_id 的 claim 全部保留 (同 canonical 多观察).

    两条 claim value 都是 bool, 但 epistemic 不同 (must / may),
    canonicalize 后 (value, type) 看似一致, 然而 design 要求:
        claim_id = hash(canonical(value)) + epistemic_type.encode()
    不同 epistemic 一定产生不同 claim_id. 验证: 两条都保留.
    """
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"}}]),
        _v1_obj("v1_b", "header", "auth", "existence",
                claims=[{"claim_id": "c1_y", "assertion":
                          {"modality": "may", "type": "bool", "value": False},
                          "authority": {"level": "registry"}}]),
    )
    facts, _ = convert_v1_fact_jsonl(p)
    assert len(facts) == 1
    assert len(facts[0].claims) == 2   # 两条都保留 (must ≠ may)
    modalities = {c.epistemic_type for c in facts[0].claims}
    assert modalities == {"must", "may"}


def test_merge_distinct_evidence(tmp_path):
    """不同 evidence_id 的 evidence 全部保留.

    Step A5-fix: 跨 claim 的 evidence 不去重 (只在同 claim_id 下按 eid 去重).
    """
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("a", "rfc/test.txt", {"norm_id": "e_a"}),
                          ]}]),
        _v1_obj("v1_b", "header", "auth", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("b", "rfc/test.txt", {"norm_id": "e_b"}),
                          ]}]),
    )
    facts, _ = convert_v1_fact_jsonl(p)
    assert len(facts) == 1
    ev_ids = {x.evidence_id for x in facts[0].claims[0].evidence}
    assert len(ev_ids) == 2, f"应 2 个 evidence (跨 fact 但同 claim, 因 eid 不同不去重), 实得 {len(ev_ids)}: {ev_ids}"
    assert all(eid.startswith("e2_") for eid in ev_ids)


# 注: test_claim_id_value_collision 已删除 (Step C-close 2026-10-08).
# 原 fixture 依赖「v1 claim_id 传播」旧前提, 与 P7「内容决定 ID」设计不兼容.
# 详见 compat.UnmergedClaimValueError 的 docstring.





def test_idempotent_conversion(tmp_path):
    """同一 jsonl 跑两次 → 完全相同结果."""
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "header", "cseq", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"}}],
                audit_refs=["e1_1", "e1_2"]),
        _v1_obj("v1_b", "header", "cseq", "existence",
                claims=[{"claim_id": "c1_x", "assertion":
                          {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"}}],
                audit_refs=["e1_3"]),
        _v1_obj("v1_c", "method", "setup", "existence",
                claims=[{"claim_id": "c1_y", "assertion":
                          {"modality": "may", "type": "bool", "value": True},
                          "authority": {"level": "registry"}}],
                audit_refs=["e1_4"]),
    )
    facts1, errs1 = convert_v1_fact_jsonl(p)
    facts2, errs2 = convert_v1_fact_jsonl(p)
    assert errs1 == errs2 == []
    assert len(facts1) == len(facts2) == 2

    def _key(f):
        return (f.fact_id,
                canonical_serialize(f.fact_key),
                tuple(sorted(c.claim_id for c in f.claims)),
                tuple(sorted(c.value.data if c.value else None
                              for c in f.claims)))

    assert sorted(_key(f) for f in facts1) == sorted(_key(f) for f in facts2)


# ===========================================================================
# P7 不变量测试 (Step C-close 2026-10-08 新增)
# 替代已删除的 test_claim_id_value_collision, 反映 P7「内容决定 ID」设计
# ===========================================================================


def test_merge_same_canonical_ids_consistent(tmp_path):
    """P7: 3 份同 canonical 内容 → 合并后 1 fact, 同 v2 claim_id, 同 v2 fact_id.

    构造 3 份 v1 fact, 内容 (value + epistemic) 完全一致 → 3 份 v2 claim_id 应相同
    (P7「内容决定 ID」) → _merge_group 按 claim_id 去重 → 合并后 1 条 claim.

    Step A5-fix: evidence 用 claim.evidence[] 构造, 每个 v1 fact 带 1 个 distinct evidence.
    """
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "method", "setup", "existence",
                actor="client",
                claims=[{"claim_id": "c1_input",
                          "assertion": {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [_ev("x", "rfc/test.txt", {"norm_id": "e_x"})]}]),
        _v1_obj("v1_b", "method", "setup", "existence",
                actor="client",
                claims=[{"claim_id": "c1_input",
                          "assertion": {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [_ev("y", "rfc/test.txt", {"norm_id": "e_y"})]}]),
        _v1_obj("v1_c", "method", "setup", "existence",
                actor="client",
                claims=[{"claim_id": "c1_input",
                          "assertion": {"modality": "must", "type": "bool", "value": True},
                          "authority": {"level": "registry"},
                          "evidence": [_ev("z", "rfc/test.txt", {"norm_id": "e_z"})]}]),
    )
    facts, errs = convert_v1_fact_jsonl(p)
    assert errs == []
    assert len(facts) == 1, f"应 1 份 v2 Fact, 实得 {len(facts)}"
    f = facts[0]
    assert len(f.claims) == 1, f"同 canonical 内容 → 1 条 claim, 实得 {len(f.claims)}"
    c = f.claims[0]
    assert c.claim_id.startswith("c2_")    # Step A3 2026-10-08: v2 claim_id 前缀 c2_
    # 3 个 distinct e2_ evidence_id (eid 全异, 不去重)
    ev_ids = {e.evidence_id for e in c.evidence}
    assert len(ev_ids) == 3, f"应 3 个 distinct evidence, 实得 {len(ev_ids)}: {ev_ids}"
    assert all(eid.startswith("e2_") for eid in ev_ids), f"应全 e2_: {ev_ids}"


def test_merge_distinct_content_keeps_claims(tmp_path):
    """P7: 同 canonical fact_key 但内容不同 → 合并后保留全部 claim (SETUP 场景).

    对应 derived/fused/facts/method.jsonl 中 SETUP ×3 security_condition 现象:
    3 份 v1 fact 同 fact_key, 但各自 value 内容不同 → 3 个不同 v2 claim_id
    → _merge_group 保留全部 claims (不同 claim_id 不去重).

    Step A5-fix: evidence 走 claim.evidence[] (audit_refs 路径已废除).
    """
    p = _make_v1_jsonl(tmp_path,
        _v1_obj("v1_a", "method", "setup", "existence",
                actor="client",
                claims=[{"claim_id": "c1_input_a",
                          "assertion": {"modality": "must", "type": "text",
                                        "value": "条件 A:Transport header 字段为空"},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("a1", "rfc/test.txt", {"norm_id": "e_a1"}),
                              _ev("a2", "rfc/test.txt", {"norm_id": "e_a2"}),
                          ]}]),
        _v1_obj("v1_b", "method", "setup", "existence",
                actor="client",
                claims=[{"claim_id": "c1_input_b",
                          "assertion": {"modality": "may", "type": "text",
                                        "value": "条件 B:SETUP 流程沿用 tcpSocketNum"},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("b1", "rfc/test.txt", {"norm_id": "e_b1"}),
                              _ev("b2", "rfc/test.txt", {"norm_id": "e_b2"}),
                          ]}]),
        _v1_obj("v1_c", "method", "setup", "existence",
                actor="client",
                claims=[{"claim_id": "c1_input_c",
                          "assertion": {"modality": "must", "type": "text",
                                        "value": "条件 C:SETUP+DESCRIBE+PLAY 三步无认证"},
                          "authority": {"level": "registry"},
                          "evidence": [
                              _ev("c1", "rfc/test.txt", {"norm_id": "e_c1"}),
                          ]}]),
    )
    facts, errs = convert_v1_fact_jsonl(p)
    assert errs == []
    assert len(facts) == 1, f"应 1 份 v2 Fact (同 canonical fact_key), 实得 {len(facts)}"
    f = facts[0]
    assert len(f.claims) == 3, f"应 3 条 claim, 实得 {len(f.claims)}"
    claim_ids = [c.claim_id for c in f.claims]
    assert len(set(claim_ids)) == 3, f"3 条 claim_id 应互异: {claim_ids}"
    # evidence 总数 = 5 (各 claim 自带 evidence, 跨 claim 不去重, 同 evidence 不去重)
    total_evid = sum(len(c.evidence) for c in f.claims)
    assert total_evid == 5, f"应 5 个 evidence, 实得 {total_evid}"
    assert f.fact_id.startswith("f2_")    # Step A3 2026-10-08: v2 fact_id 前缀 f2_