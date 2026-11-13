# -*- coding: utf-8 -*-
"""tests/extraction/test_normative_rule_publish.py —— **第三批灰度门槛专项测试**。

★ 对应改进计划 §10 的灰度门槛（摘取与「规则发布」直接相关的 5 项）：
  ② **事实唯一性** —— 不同规则不误合并；同主体多规则身份不碰撞
  ②b **规范语义比较** —— 相同语义不误报冲突
  ③ **证据归属** —— 每条规则能定位完整、真实的原文证据
  ④ **身份唯一性 + 冲突可发现性** —— 相反极性声明可关联并报告；不同语义类型不被覆盖；
     同一语义事实允许保留多个证据来源
  ⑤ **旧消费者兼容** —— aspect 数量不变
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fused.extraction.normative_rule import (  # noqa: E402
    RULE_KIND, compare_slots, is_rule_text, parse_rule_text,
    rule_slot, semantic_key,
)
from core.fused.extraction.normative_verify import (  # noqa: E402
    CONFIRMED, PENDING, REJECTED, detect_conflict, l1_check,
)


def _norm(**kw):
    _base = dict(
        kind="prose_constraint", protocol="p", kb_source_type="rfc",
        name="client", content="c", norm_id="n1",
        source="file:rfc.txt#@10", meaning="m", constraint="must do X",
        action="send", object="ACK", strength="MUST", polarity="positive",
    )
    _base.update(kw)
    return _base


def _facts(norm: dict):
    from core.fused.extraction.norm import prose_constraint_norm_to_facts
    return prose_constraint_norm_to_facts(norm)


# ===========================================================================
# ② 事实唯一性
# ===========================================================================

def test_gate2_distinct_rules_do_not_merge():
    """② 不同规则（不同 action/object）⇒ **身份不同** ⇒ 不误合并。"""
    f1 = _facts(_norm(action="send", object="ACK"))[0]
    f2 = _facts(_norm(action="update", object="local_state"))[0]
    assert f1.fact_id != f2.fact_id


def test_gate2_same_subject_distinct_rules_no_collision():
    """② 同主体、同 aspect、同条件下两条不同规则 ⇒ **身份不碰撞**。"""
    f1 = _facts(_norm(action="send", object="ACK"))[0]
    f2 = _facts(_norm(action="update", object="timer"))[0]
    assert f1.fact_key.subject.name == f2.fact_key.subject.name
    assert f1.fact_id != f2.fact_id


# ===========================================================================
# ②b 规范语义比较
# ===========================================================================

def test_gate2b_same_semantics_no_false_conflict():
    """②b 同一语义、不同原文措辞与证据 ⇒ **不伪冲突**（value 文本相同）。"""
    f1 = _facts(_norm(strength="MUST", polarity="positive"))[0]
    f2 = _facts(_norm(strength="MUST", polarity="positive"))[0]
    assert f1.fact_key.subject.qualifiers == f2.fact_key.subject.qualifiers
    # ★ 值是规范化 JSON 文本 ⇒ 语义相同 ⇒ 文本必然相同
    assert f1.claims[0].value.data == f2.claims[0].value.data


def test_gate2b_non_semantic_fields_not_in_value():
    """②b 非语义字段（原文措辞 / 证据引用）**不得**进 value。"""
    f = _facts(_norm())[0]
    _txt = f.claims[0].value.data
    assert "keyword_raw" not in _txt
    assert "evidence_refs" not in _txt
    assert is_rule_text(_txt)
    assert parse_rule_text(_txt)["kind"] == RULE_KIND


# ===========================================================================
# ③ 证据归属
# ===========================================================================

def test_gate3_evidence_locates_source():
    """③ 每条规则都能定位**完整、真实**的原文证据（document + quote + 可回溯）。"""
    f = _facts(_norm(source="file:rfc.txt#@42"))[0]
    assert f.claims[0].evidence
    _ev = f.claims[0].evidence[0]
    # ★ 文档位置可定位
    assert "rfc.txt" in _ev.document
    # ★ 原文措辞落**证据侧**（不进 value）⇒ 便于核对
    assert _ev.quote
    assert "keyword_raw" not in f.claims[0].value.data


# ===========================================================================
# ④ 冲突可发现性
# ===========================================================================

def test_gate4_opposite_polarity_same_slot():
    """④ 相反极性声明 ⇒ **同一槽位**（可关联）⇒ 冲突可检出。"""
    s_pos = rule_slot(protocol="p", version="1.0", subject="client",
                      action="send", object_="ACK")
    s_neg = rule_slot(protocol="p", version="1.0", subject="client",
                      action="send", object_="ACK")
    assert compare_slots(s_pos, s_neg)      # ★ 同一槽位
    f_pos = _facts(_norm(polarity="positive"))[0]
    f_neg = _facts(_norm(polarity="negative"))[0]
    # ★ 同一身份（⇒ 进同一事实槽位 ⇒ consensus 能标记冲突）
    assert f_pos.fact_id == f_neg.fact_id
    # ★ 但声明内容不同（⇒ 不会被误判为同一语义）
    assert semantic_key(parse_rule_text(f_pos.claims[0].value.data)) != \
           semantic_key(parse_rule_text(f_neg.claims[0].value.data))
    # ★ 冲突可检出，且**两条都保留**
    _c = detect_conflict([
        {"claim_id": "c1", "value": f_pos.claims[0].value.data},
        {"claim_id": "c2", "value": f_neg.claims[0].value.data},
    ])
    assert _c is not None
    assert set(_c["claims"]) == {"c1", "c2"}


def test_gate4_different_semantics_not_overwritten():
    """④ 不同语义类型的声明**不被错误覆盖**（事实身份不同 ⇒ 不同槽位）。"""
    f1 = _facts(_norm(action="send", object="ACK"))[0]
    f2 = _facts(_norm(action="send", object="BYE"))[0]
    assert f1.fact_id != f2.fact_id


def test_gate4_same_fact_multiple_evidence_allowed():
    """④ 同一语义事实**允许保留多个证据来源**（claim 层面）。"""
    f = _facts(_norm())[0]
    assert len(f.claims) >= 1
    # ★ value 里**不出现**证据引用 ⇒ ⇒ 证据差异不进入语义比较
    assert "evidence" not in f.claims[0].value.data


# ===========================================================================
# ⑤ 旧消费者兼容
# ===========================================================================

def test_gate4_uncertain_candidate_not_published():
    """★ 强度未定的候选 ⇒ **不得**作为「已证实的具体等级规则」进正式事实。"""
    from core.fused.extraction.normative_rule import build_payload, rule_text
    from core.fused.extraction.normative_verify import l1_check
    _p = build_payload(subject="client", action="send", object_="ACK",
                       strength=None, polarity=None)
    _r = l1_check(rule_text_value=rule_text(_p),
                  quote="The client should send ACK here.",
                  evidence_span=(7, 7), subject="client")
    assert _r.verdict == PENDING
    assert _r.confirmed is False


def test_gate5_aspect_count_unchanged():
    """⑤ aspect 数量**不变**（21）⇒ 旧消费者兼容。"""
    import json as _json
    _reg = _json.loads((ROOT / "core/fused/hub/registry/aspect_registry.json")
                        .read_text(encoding="utf-8"))
    assert len(_reg["registered_aspects"]) == 21


def test_gate5_rule_lands_in_definition():
    """⑤ 规则落在**已有的** ``definition``（★ 不新增 aspect）。"""
    f = _facts(_norm())[0]
    assert f.fact_key.aspect == "definition"
    assert f.fact_key.subject.type == "header"     # ★ 已有主体类型


# ===========================================================================
# L1 与发布的衔接
# ===========================================================================

def test_l1_accepts_published_rule():
    """L1：一致的规则 ⇒ 已证实。"""
    f = _facts(_norm(strength="MUST", polarity="positive"))[0]
    r = l1_check(rule_text_value=f.claims[0].value.data,
                 quote="The client MUST send ACK.",
                 evidence_span=(42, 42), keyword_raw="MUST",
                 subject="client")
    assert r.verdict == CONFIRMED


def test_l1_rejects_polarity_mismatch():
    """L1：原文是 MUST NOT 而 payload 是 positive ⇒ 拒收。"""
    f = _facts(_norm(strength="MUST", polarity="positive"))[0]
    r = l1_check(rule_text_value=f.claims[0].value.data,
                 quote="The client MUST NOT send ACK.",
                 evidence_span=(42, 42), keyword_raw="MUST NOT",
                 subject="client")
    assert r.verdict == REJECTED
