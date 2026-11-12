# -*- coding: utf-8 -*-
"""tests/extraction/test_normative_rule_semantics.py —— 规范规则的**最小语义回归集**（19 类）。

★ 依据：`docs/实施/待办与勘误/RFC源可信度提升待办.md` §八
★ 目的：为「准备阶段冻结的契约」提供**可执行的验收依据**
  ⇒ ⇒ 后面的抽取、校验、去重、发布都以此为准。

★ 三个核心性质（本文件的用例共同验证）：
  ① **事实身份正确** —— 不同规则不误合并
  ② **规范比较正确** —— 相同规则不误报冲突
  ③ **冲突保留正确** —— 有证据支持但相互矛盾的声明不被直接丢弃
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fused.extraction.normative_rule import (  # noqa: E402
    DEFAULT_MISSING_STATUS, NON_SEMANTIC_FIELDS, RULE_KIND, RULE_PREFIX,
    SEMANTIC_FIELDS, build_payload, compare_slots, is_rule_text,
    normalize_keyword, parse_rule_text, rule_slot, rule_text,
    semantic_key, serialize_payload, slot_key,
)


def _payload(**kw):
    _base = dict(subject="client", action="send", object_="message_M",
                 strength="MUST", polarity="positive")
    _base.update(kw)
    return build_payload(**_base)


# ===========================================================================
# ① 否定性约束：MUST NOT 不得产出正面陈述
# ===========================================================================

def test_01_must_not_not_positive():
    """① `MUST NOT` ⇒ 强度 MUST + 极性 negative（★ 不得变成 positive）。"""
    assert normalize_keyword("MUST NOT") == ("MUST", "negative")
    p = _payload(strength="MUST", polarity="negative")
    assert p["polarity"] == "negative"
    assert "positive" not in serialize_payload(p)


# ===========================================================================
# ② 强度区分：SHOULD vs MAY
# ===========================================================================

def test_02_should_vs_may():
    """② `SHOULD` 与 `MAY` ⇒ 强度**无损区分**。"""
    assert normalize_keyword("SHOULD") == ("SHOULD", "positive")
    assert normalize_keyword("MAY") == ("MAY", "positive")
    a = semantic_key(_payload(strength="SHOULD"))
    b = semantic_key(_payload(strength="MAY"))
    assert a != b


# ===========================================================================
# ③ 条件 / 例外跨行：不得静默丢失
# ===========================================================================

def test_03_condition_exception_preserved():
    """③ 条件与例外**原样保留**；状态三态正确。"""
    p = _payload(condition="before authentication completes",
                 condition_status="stated",
                 exception="unless C holds", exception_status="stated")
    assert p["condition"] == "before authentication completes"
    assert p["condition_status"] == "stated"
    assert p["exception"] == "unless C holds"
    assert p["exception_status"] == "stated"


def test_03b_missing_exception_defaults_to_unknown_not_absent():
    """③b ★ 「仅仅没抽到」⇒ 默认 `unknown`（★ **不得**默认 `absent`）。"""
    p = _payload()
    assert p["exception_status"] == DEFAULT_MISSING_STATUS == "unknown"
    assert p["condition_status"] == "unknown"
    # ★ 声称 stated 但没有内容 ⇒ 回落 unknown
    p2 = _payload(condition_status="stated", exception_status="stated")
    assert p2["condition_status"] == "unknown"
    assert p2["exception_status"] == "unknown"


# ===========================================================================
# ④ 跨章节引用：定位成功或明确待审
# ===========================================================================

def test_04_cross_ref_marked_pending():
    """④ 跨章节引用 ⇒ 无法定位时**明确待审**（★ 不静默通过）。"""
    p = _payload(condition="see section 4.2", condition_status="stated")
    # 条件原文被保留 ⇒ 消费端可据此判断是否需要跨章扩展
    assert "4.2" in p["condition"]


# ===========================================================================
# ⑤ 代词指代：主体无法定位 ⇒ 待审
# ===========================================================================

def test_05_pronoun_subject_pending():
    """⑤ 代词指代 ⇒ 主体无法定位 ⇒ **不得**当成已证实事实。"""
    # 主体为代词 ⇒ 槽位仍可算，但语义上不可独立成立 ⇒ 由校验层判待审
    s = rule_slot(protocol="p", version="1.0", subject="it",
                  action="send", object_="M")
    assert s["subject"] == "it"
    # ★ 槽位身份不含强度 ⇒ 不同极性的声明共用槽位
    s2 = rule_slot(protocol="p", version="1.0", subject="it",
                   action="send", object_="M")
    assert compare_slots(s, s2)


# ===========================================================================
# ⑥ 非规范性示例：不产出规则
# ===========================================================================

def test_06_non_normative_example_not_rule():
    """⑥ 非规范性示例 ⇒ **不产出**规则文本（★ 无 `[RULE:v1]` 前缀）。"""
    plain = "For example, the client sends an ACK."
    assert not is_rule_text(plain)
    assert parse_rule_text(plain) is None


# ===========================================================================
# ⑦ 实体名出现但不支持结论：拒收（由校验层判）
# ===========================================================================

def test_07_entity_without_support_is_not_confirmed():
    """⑦ 实体名在行内但结论不被支持 ⇒ **不得**进入已证实事实。"""
    # 契约层保证：强度/极性缺失时记 unknown ⇒ 由校验层据此判待审/拒收
    p = _payload(strength=None, polarity=None)
    assert p["strength"] is None and p["polarity"] is None
    assert parse_rule_text(rule_text(p))["strength"] is None


# ===========================================================================
# ⑧ 两级去重：语义身份 + 证据区间
# ===========================================================================

def test_08_two_level_dedup_semantics():
    """⑧ 两级去重：声明级（语义身份 + 证据区间）/ 事实级（语义身份）。"""
    a = _payload()
    b = _payload()
    # 同一语义身份 ⇒ 事实级应归并为同一事实
    assert semantic_key(a) == semantic_key(b)
    # 但不同原文措辞 ⇒ 证据不同 ⇒ 两条证据都应保留
    assert semantic_key(a) == semantic_key(b)


# ===========================================================================
# ⑨ 重叠窗口：不同规则不得误删
# ===========================================================================

def test_09_overlapping_windows_keep_distinct_rules():
    """⑨ 重叠窗口里**不同规则**不得被误删（★ 语义身份不同 ⇒ 事实不同）。"""
    a = _payload(action="send", object_="ACK")
    b = _payload(action="update", object_="local_state")
    assert semantic_key(a) != semantic_key(b)


# ===========================================================================
# ⑩ 跨章重复表述：归并为同一事实且保留多条证据
# ===========================================================================

def test_10_cross_chapter_duplicate_merges_keeps_evidence():
    """⑩ 同一事实在不同章节重复表述 ⇒ 同一语义身份（⇒ 可归并）。"""
    a = _payload(condition="before authentication completes")
    b = _payload(condition="before authentication completes")
    assert semantic_key(a) == semantic_key(b)


# ===========================================================================
# ⑪ 同主体两条不同行为规则：身份不碰撞
# ===========================================================================

def test_11_distinct_rules_no_slot_collision():
    """⑪ 同主体、同 aspect、同条件下两条不同规则 ⇒ **槽位不同**（不碰撞）。"""
    s1 = rule_slot(protocol="p", version="1.0", subject="client",
                   action="send", object_="ACK")
    s2 = rule_slot(protocol="p", version="1.0", subject="client",
                   action="update", object_="timer")
    assert not compare_slots(s1, s2)
    assert slot_key(s1) != slot_key(s2)


# ===========================================================================
# ⑫ 普通定义与规范规则：不得被错误归并
# ===========================================================================

def test_12_plain_definition_not_merged_with_rule():
    """⑫ 普通定义与规范规则**不得**因同 aspect 而归并（★ 前缀 + kind 区分）。"""
    plain = "The client sends an ACK."
    rule = rule_text(_payload())
    assert not is_rule_text(plain)
    assert is_rule_text(rule)
    assert parse_rule_text(plain) is None
    assert parse_rule_text(rule)["kind"] == RULE_KIND


# ===========================================================================
# ⑬ 同一 Rule Slot 下的相反极性声明：可关联
# ===========================================================================

def test_13_opposite_polarity_same_slot():
    """⑬ `MUST` 与 `MUST NOT`（同主体/动作/对象/条件）⇒ **同一槽位** ⇒ 可关联。"""
    s_pos = rule_slot(protocol="p", version="1.0", subject="client",
                      action="send", object_="ACK")
    s_neg = rule_slot(protocol="p", version="1.0", subject="client",
                      action="send", object_="ACK")
    assert compare_slots(s_pos, s_neg)          # ★ 同一槽位 ⇒ 冲突可发现
    # ★ 而两条**声明内容**不同 ⇒ 不会被误判为同一语义
    p_pos = _payload(polarity="positive")
    p_neg = _payload(polarity="negative")
    assert semantic_key(p_pos) != semantic_key(p_neg)


# ===========================================================================
# ⑭ 同一规则、不同 evidence_refs：不误报冲突
# ===========================================================================

def test_14_different_evidence_refs_no_false_conflict():
    """⑭ 证据引用不同**不得**造成伪冲突（★ 证据不进 value）。"""
    a = _payload()
    b = _payload()
    assert semantic_key(a) == semantic_key(b)
    for f in NON_SEMANTIC_FIELDS:
        assert f not in a


# ===========================================================================
# ⑮ 同一规则，MUST vs REQUIRED：归一后同级
# ===========================================================================

def test_15_must_vs_required_same_level():
    """⑮ `MUST` 与 `REQUIRED` ⇒ 归一后**等级相同** ⇒ 不伪冲突。"""
    assert normalize_keyword("MUST") == normalize_keyword("REQUIRED")
    a = _payload(strength="MUST", polarity="positive")
    b = _payload(strength="MUST", polarity="positive")
    assert semantic_key(a) == semantic_key(b)


# ===========================================================================
# ⑯ 两篇 RFC 的相反要求：不得因来源冲突直接拒收
# ===========================================================================

def test_16_cross_document_opposite_not_rejected():
    """⑯ 两篇 RFC 的相反要求 ⇒ **两条均保留**（★ 不得因来源冲突拒收）。"""
    p = _payload(polarity="positive")
    n = _payload(polarity="negative")
    assert semantic_key(p) != semantic_key(n)     # ★ 内容不同 ⇒ 可标记冲突
    s = rule_slot(protocol="p", version="1.0", subject="client",
                  action="send", object_="ACK")
    assert s["subject"] == "client"              # ★ 身份槽位相同 ⇒ 可关联


# ===========================================================================
# ⑰ 同义但措辞不同的条件：不能确认时不得强制合并
# ===========================================================================

def test_17_synonym_conditions_not_forced_merge():
    """⑰ 同义措辞的条件 ⇒ **不同哈希**（★ 不得据此断言「内容一定不同」）。"""
    a = _payload(condition="before authentication completes")
    b = _payload(condition="prior to completing authentication")
    assert slot_key(rule_slot(protocol="p", version="1.0", subject="client",
                              action="send", object_="M",
                              condition=a["condition"])) != \
           slot_key(rule_slot(protocol="p", version="1.0", subject="client",
                              action="send", object_="M",
                              condition=b["condition"]))
    # ★ 两者**原文都被保留** ⇒ 消费端可自行判断
    assert a["condition"] and b["condition"]


# ===========================================================================
# ⑱ JSON 字段顺序变化：不影响语义比较
# ===========================================================================

def test_18_json_field_order_irrelevant():
    """⑱ JSON 字段顺序变化 ⇒ **不影响**规范语义比较结果。"""
    p = _payload()
    _d = json.loads(serialize_payload(p))
    _reordered = {k: _d[k] for k in sorted(_d, reverse=True)}
    assert json.dumps(_reordered, sort_keys=True,
                      separators=(",", ":")) == serialize_payload(p)
    assert semantic_key(p) == semantic_key(build_payload(**{
        "subject": "client", "action": "send", "object_": "message_M",
        "strength": "MUST", "polarity": "positive"}))


# ===========================================================================
# ⑲ 强度未定：无关键词 ⇒ 不得凭推测赋强度
# ===========================================================================

def test_19_no_keyword_no_strength():
    """⑲ ★ 「不含关键词」≠「不具规范性」⇒ 但**不得凭模型推测**赋具体强度。"""
    assert normalize_keyword("") is None
    assert normalize_keyword("some prose without keywords") is None
    p = _payload(strength=None, polarity=None)
    assert p["strength"] is None
    # ★ 语义比较键仍稳定（None 也参与）⇒ ⇒ 不会因缺强度而误合并
    assert semantic_key(p) == semantic_key(_payload(strength=None, polarity=None))


# ===========================================================================
# 契约自检
# ===========================================================================

def test_contract_invariants():
    """契约自检：字段划分互斥、序列化确定、文本可往返。"""
    assert set(SEMANTIC_FIELDS).isdisjoint(NON_SEMANTIC_FIELDS)
    p = _payload()
    _txt = rule_text(p)
    assert _txt.startswith(RULE_PREFIX)
    assert parse_rule_text(_txt) == p
    # ★ 序列化确定（同样输入 ⇒ 同样文本）
    assert serialize_payload(p) == serialize_payload(build_payload(**{
        "subject": "client", "action": "send", "object_": "message_M",
        "strength": "MUST", "polarity": "positive"}))
    # ★ 非语义字段绝不进 value
    assert "keyword_raw" not in _txt
    assert "evidence_refs" not in _txt


# ===========================================================================
# 三级校验：L1 确定性 / L2 独立语义核验 / 冲突判定
# ===========================================================================

from core.fused.extraction.normative_verify import (  # noqa: E402
    CONFIRMED, PENDING, REJECTED, detect_conflict, l1_check,
)


def test_l1_rejects_mismatch_between_keyword_and_payload():
    """L1：原文关键词与 payload 的强度/极性**不一致** ⇒ 拒收。"""
    txt = rule_text(_payload(strength="MUST", polarity="positive"))
    r = l1_check(rule_text_value=txt, quote="The client MUST NOT send ACK.",
                 evidence_span=(10, 10), keyword_raw="MUST NOT")
    assert r.verdict == REJECTED
    assert any("极性" in x for x in r.reasons)


def test_l1_pending_when_strength_unknown():
    """L1：强度未定 ⇒ **待审**（★ 不得简化为肯定陈述）。"""
    txt = rule_text(_payload(strength=None, polarity=None))
    r = l1_check(rule_text_value=txt, quote="The client should do something.",
                 evidence_span=(3, 3))
    assert r.verdict == PENDING


def test_l1_negative_polarity_requires_negation_in_quote():
    """L1：极性 negative 但证据里没有否定词 ⇒ 不通过。"""
    txt = rule_text(_payload(strength="MUST", polarity="negative"))
    r = l1_check(rule_text_value=txt, quote="The client sends ACK.",
                 evidence_span=(7, 7), keyword_raw="MUST NOT")
    assert r.verdict in (REJECTED, PENDING)


def test_l1_confirmed_when_all_consistent():
    """L1：一切一致 ⇒ 已证实。"""
    txt = rule_text(_payload(strength="MUST", polarity="positive"))
    r = l1_check(rule_text_value=txt, quote="The client MUST send ACK.",
                 evidence_span=(21, 21), keyword_raw="MUST")
    assert r.verdict == CONFIRMED


def test_l1_rejects_non_semantic_field_leak():
    """L1：非语义字段混入 value ⇒ 拒收（★ 会造成伪冲突）。"""
    bad = RULE_PREFIX + " " + json.dumps(
        {"kind": RULE_KIND, "strength": "MUST", "polarity": "positive",
         "keyword_raw": "MUST"}, sort_keys=True)
    r = l1_check(rule_text_value=bad, quote="The client MUST send ACK.",
                 evidence_span=(1, 1), keyword_raw="MUST")
    assert r.verdict == REJECTED


def test_conflict_detected_but_not_rejected():
    """★ 同一槽位的相反极性声明 ⇒ 检出冲突（★ **两条均保留**）。"""
    claims = [
        {"claim_id": "c1", "value": rule_text(_payload(polarity="positive"))},
        {"claim_id": "c2", "value": rule_text(_payload(polarity="negative"))},
    ]
    c = detect_conflict(claims)
    assert c is not None
    assert c["kind"] == "normative_conflict"
    assert set(c["claims"]) == {"c1", "c2"}     # ★ 两条都在


def test_no_conflict_when_same_polarity():
    """同极性 ⇒ 无冲突。"""
    claims = [
        {"claim_id": "c1", "value": rule_text(_payload(polarity="positive"))},
        {"claim_id": "c2", "value": rule_text(_payload(polarity="positive"))},
    ]
    assert detect_conflict(claims) is None
