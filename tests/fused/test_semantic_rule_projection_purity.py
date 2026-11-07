# -*- coding: utf-8 -*-
"""tests/fused/test_semantic_rule_projection_purity.py —— 语义规则投影的纯净与来源标注。

★ 背景（2026-11-07，P2-2 预检发现的两类问题）：

  ① **`absent` 语义错位**（知识污染，必须拦）：权威规则库里 `absent` 只有 3 条，
     **3/3 全部抽错**——
       · `Accept`（RFC 3261）：原文是「**若**远端要求不带 multipart 的 Accept，
         则必须发非 multipart 的 session description」⇒ 条件约束，被抽成
         「Accept 不得出现」；
       · `From`（RFC 5322）：原文是「From **不应包含**不属于作者的邮箱」
         ⇒ 内容约束，被抽成「From 不得出现」（From 还是必填头）；
       · `Reply-To`（RFC 5322）：原文是「**没有** Reply-To 时回复默认发给 From」
         ⇒ 缺省行为描述，被抽成「Reply-To 不得出现」。
     这三条会经 `_render_constraints()` 进 prompt，等于教 LLM「报文别带 From」。

  ② **处理期望（P）全是推断、且 1 条判错**：已有值的 9 条里，没有一条的证据
     原文规定了「违反后返回什么」；`SIP-Version` 那条更把「违反大小写要求」
     填成 `success`（违反约束却期望 2xx，语义矛盾）。

  ⇒ 本文件锁四件事：
     · `absent` 一律拒收，且可整体回退（`_REJECT_ABSENT_OPERATOR`）；
     · 空处理期望按**确定性规则**推断并标 `rule_inferred`；
     · 语义矛盾的 `success` 改判 `protocol_error` 并标 `rule_corrected`；
     · 三档来源在条目里**逐条**可见 ⇒ 指标不再把推断算成抽取。
"""
from __future__ import annotations

import pytest

from core.fused.downstream import rag_seedgen as RS


def mk_rule(field: str, operator: str, expected_behavior: str = "",
            operand=(), *, rule_state: str = "authoritative") -> dict:
    """构造一条最小可用规则（结构同 `dataclasses.asdict(SemanticRule)`）。"""
    return {
        "rule_id": f"r_{field}_{operator}_{expected_behavior or 'none'}",
        "rule_state": rule_state,
        "subject_type": "field",
        "subject_name": field,
        "constraint": {
            "target_field": field,
            "operator": operator,
            "operand": list(operand),
            "operand_source": "constant",
            "operand_ref": None,
            "applies_to_state": [],
            "applies_to_method": [],
            "expected_behavior": expected_behavior,
            "sender_role": "client",
            "receiver_role": "server",
            "precondition": None,
        },
        "evidence": {
            "evidence_id": "e_test",
            "spec_version": "RFC X",
            "section_path": [],
            "source_anchor": "",
            "span_text": "",
            "span_start": 0,
            "span_end": 0,
            "evidence_kind": "normative",
            "explicitness": "explicit",
            "source_class": "normative_spec",
        },
        "model_confidence": 1.0,
        "validated": True,
        "supersedes": None,
    }


# ===========================================================================
# ① absent 一律拒收（知识污染拦截）
# ===========================================================================

def test_absent_is_rejected():
    assert RS._project_rule(mk_rule("From", "absent")) is None


@pytest.mark.parametrize("field", ["Accept", "From", "Reply-To", "Any-Field"])
def test_absent_rejected_generically(field):
    """★ 判据必须**协议无关且不含字段特例**：换任何字段名都一样拒收。"""
    assert RS._project_rule(mk_rule(field, "absent")) is None


def test_absent_rejection_can_be_switched_off(monkeypatch):
    """回退开关有效：关掉后 `absent` 会照旧投影（供将来抽取器修好后放开）。"""
    monkeypatch.setattr(RS, "_REJECT_ABSENT_OPERATOR", False)
    out = RS._project_rule(mk_rule("X-Test", "absent"))
    assert out is not None
    key, lb, _re = out
    assert key == "X-Test"
    assert "出现即非法" in lb["illegal"]


# ===========================================================================
# ② 空处理期望 ⇒ 确定性推断（rule_inferred）
# ===========================================================================

@pytest.mark.parametrize("op", sorted(RS._INFERABLE_OPERATORS))
def test_empty_expected_behavior_inferred_for_inferable_operators(op):
    out = RS._project_rule(mk_rule("X", op, "", (1,) if op not in ("present",) else ()))
    assert out is not None, op
    _key, lb, re_entry = out
    assert lb["trigger"] == "protocol_error"
    assert lb["expected_behavior_source"] == "rule_inferred"
    assert re_entry is not None
    assert re_entry["expected_code"] == "4xx"


def test_absent_is_not_inferable():
    """★ absent 不参与推断（先被拒收；即使放开也应保持不可推断）。"""
    assert "absent" not in RS._INFERABLE_OPERATORS


def test_unknown_operator_is_not_projected():
    assert RS._project_rule(mk_rule("X", "bogus_op")) is None


# ===========================================================================
# ③ 语义矛盾 ⇒ 改判（rule_corrected）
# ===========================================================================

def test_success_after_violation_is_corrected():
    """★ 违反「取值须为 SIP/2.0」却期望 success ⇒ 不可能，改判 protocol_error。"""
    out = RS._project_rule(mk_rule("SIP-Version", "eq", "success", ("SIP/2.0",)))
    assert out is not None
    _key, lb, re_entry = out
    assert lb["trigger"] == "protocol_error"
    assert lb["expected_behavior_source"] == "rule_corrected"
    assert re_entry["expected_behavior"] == "protocol_error"


def test_evidence_value_preserved():
    """证据原值的 other 取值（silence / application_error）**不得**被改写。"""
    for eb in ("protocol_error", "application_error", "silence"):
        out = RS._project_rule(mk_rule("X", "present", eb))
        assert out is not None, eb
        _key, lb, re_entry = out
        assert lb["trigger"] == eb
        assert lb["expected_behavior_source"] == "evidence"


def test_render_domains_not_affected():
    """守卫：本条只改 P 侧，C 侧（合法/非法域）逐字不变。"""
    out = RS._project_rule(mk_rule("Content-Length", "present"))
    _key, lb, _re = out
    assert lb["legal"] == "存在（必须出现）"
    assert lb["illegal"] == "缺失（不得出现）"


# ===========================================================================
# ④ 真实语料锚点（三类问题在真实库上都消失 / 都被标注）
# ===========================================================================

@pytest.fixture(scope="module")
def projected():
    out = {}
    for proto in ("rtsp", "sip", "smtp"):
        rules = RS.load_semantic_rules(proto)
        out[proto] = (rules, RS.project_semantic_rules({"semantic_rules": rules}))
    return out


@pytest.mark.parametrize("proto,expect_lb", [("rtsp", 4), ("sip", 10), ("smtp", 2)])
def test_real_corpus_legal_boundary_counts(projected, proto, expect_lb):
    """★ 锚点：sip 11→10（拒 `Accept`）、smtp 4→2（拒 `From`/`Reply-To`）、rtsp 5→4（去重）。"""
    _rules, b = projected[proto]
    n = sum(len(v) for v in (b.get("legal_boundary") or {}).values())
    assert n == expect_lb, f"{proto} legal_boundary={n}"


def test_no_absent_field_leaks_into_buckets(projected):
    """★ 错位三条（Accept / From / Reply-To）不得出现在任何投影桶里。"""
    for proto in ("rtsp", "sip", "smtp"):
        _rules, b = projected[proto]
        keys = set(b.get("legal_boundary") or {}) | set(
            b.get("response_expectation") or {})
        assert not ({"Accept", "From", "Reply-To"} & keys), (proto, keys)


def test_every_entry_has_source_label(projected):
    """★ 每个条目都必须带来源标签 —— 这是「不把推断算成抽取」的机械保证。"""
    allowed = {"evidence", "rule_corrected", "rule_inferred"}
    for proto in ("rtsp", "sip", "smtp"):
        _rules, b = projected[proto]
        for bucket in ("legal_boundary", "response_expectation"):
            for field, entries in (b.get(bucket) or {}).items():
                for e in entries:
                    assert e.get("expected_behavior_source") in allowed, (
                        proto, bucket, field, e)
                    assert str(e.get("expected_behavior") or e.get("trigger")).strip()


def test_sip_version_is_corrected_in_real_corpus(projected):
    _rules, b = projected["sip"]
    entries = b["legal_boundary"]["SIP-Version"]
    srcs = {e["expected_behavior_source"] for e in entries}
    assert "rule_corrected" in srcs
    assert all(e["trigger"] != "success" for e in entries), entries


def test_prompt_rendering_has_trigger_everywhere(projected):
    """★ prompt 里每条约束都应带处理期望（修复前 14 条是空白）。"""
    _rules, b = projected["sip"]
    text = RS._render_constraints(b)
    lines = [ln for ln in text.splitlines() if ln.startswith("  ") and "：" not in ln[:3]]
    assert lines, text
    for ln in lines:
        assert "→ protocol_error" in ln, ln


def test_projection_is_idempotent(projected):
    """连续投影两次结果一致（bucket 合并幂等）。"""
    rules, b = projected["sip"]
    once = {k: [dict(x) for x in v] for k, v in b["legal_boundary"].items()}
    RS.project_semantic_rules({"semantic_rules": rules,
                               "legal_boundary": b["legal_boundary"]})
    twice = b["legal_boundary"]
    for k in once:
        assert len(once[k]) == len(twice[k]), k
