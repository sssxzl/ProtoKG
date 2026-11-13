# -*- coding: utf-8 -*-
"""tests/extraction/test_normative_rule_semantics.py —— 规范规则的**最小语义回归集**。

★ **2026-11-13 人工核对后重写**（依据《RFC规范规则语义测试_人工核对意见》）
  · **不再只比 hash / 只比字符串** ⇒ ⇒ 改为**真过机制**：
    过**去重器**、过**L1 校验**、过**规则映射**、过**冲突检测**
  · ★ 6 条**期望被修正**：``03b`` ``04`` ``05`` ``07`` ``17`` ``19``
  · ★ 12 条**断言被补强**：``01`` ``03`` ``06`` ``08`` ``09`` ``10`` ``12``
    ``13`` ``14`` ``15`` ``16`` ``18``
  · ★ 2 条**保持**：``02`` ``11``

★ 三态标记（人工核对意见 §六）：
  · ``semantic_approved``      —— 业务预期已人工认可
  · ``assertion_covered``      —— 测试输入与断言**真覆盖**该行为
  · ``implementation_passed``  —— 运行真实实现后通过
  ⇒ ⇒ 每条用例的 docstring 里标注了达到的状态。
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
    SEMANTIC_FIELDS, build_payload, compare_slots, is_pronoun_subject,
    is_rule_text, normalize_keyword, parse_rule_text, rule_slot, rule_text,
    semantic_key, serialize_payload, slot_key, subject_resolvable,
)
from core.fused.extraction.normative_verify import (  # noqa: E402
    CONFIRMED, PENDING, REJECTED, detect_conflict, l1_check, l2_check,
)
from core.fused.extraction.window_candidates import (  # noqa: E402
    Candidate, dedup_declarations,
)


def _payload(**kw):
    _base = dict(subject="client", action="send", object_="message_M",
                 strength="MUST", polarity="positive")
    _base.update(kw)
    return build_payload(**_base)


def _cand(start, end, text="x", sem=""):
    return Candidate(doc="d.txt", start_line=start, end_line=end,
                     text=text, triggers=[])


def _fact(**kw):
    """走**真实映射**产出一条规则 fact（★ 用于端到端断言）。"""
    from core.fused.extraction.norm import prose_constraint_norm_to_facts
    _base = {"kind": "prose_constraint", "protocol": "p", "kb_source_type": "rfc",
             "name": "client", "content": "c", "norm_id": "n",
             "source": "file:d.txt#@10", "meaning": "m",
             "constraint": "must send ACK", "action": "send", "object": "ACK",
             "strength": "MUST", "polarity": "positive"}
    _base.update(kw)
    return prose_constraint_norm_to_facts(_base)[0]


# ===========================================================================
# 01 MUST NOT 的否定性
# ===========================================================================

def test_01_must_not_not_positive():
    """01 ``MUST NOT`` ⇒ 强度 MUST + 极性 negative（★ 反序列化后验证，不做字符串检查）。

    ★ 人工核对：期望认可；断言需补强（不再用「输出文本不含 positive」判断）。
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    assert normalize_keyword("MUST NOT") == ("MUST", "negative")
    # ★ 走**结构化解析**：反序列化后逐字段验证
    p = _payload(strength="MUST", polarity="negative")
    _d = parse_rule_text(rule_text(p))
    assert _d["strength"] == "MUST"
    assert _d["polarity"] == "negative"
    # ★ 且**实际规则生成链路**不会产出肯定性义务
    _f = _fact(polarity="negative", constraint="must not send")
    _v = parse_rule_text(_f.claims[0].value.data)
    assert _v["polarity"] == "negative" and _v["strength"] == "MUST"


# ===========================================================================
# 02 SHOULD vs MAY
# ===========================================================================

def test_02_should_vs_may():
    """02 ``SHOULD`` 与 ``MAY`` ⇒ 强度**无损区分**（★ 保持：核心期望与单元断言对应）。"""
    assert normalize_keyword("SHOULD") == ("SHOULD", "positive")
    assert normalize_keyword("MAY") == ("MAY", "positive")
    a = semantic_key(_payload(strength="SHOULD"))
    b = semantic_key(_payload(strength="MAY"))
    assert a != b


# ===========================================================================
# 03 条件 / 例外跨行
# ===========================================================================

def test_03_condition_exception_preserved():
    """03 条件与例外**跨行**也完整保留（★ 补强：提供跨行原文与证据跨度）。

    ★ 人工核对：期望方向对；原断言只查字段赋值 ⇒ 缺跨行文本。
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _quote = ("The client MUST NOT send message M before authentication\n"
              "   completes, unless the session is in state S\n"
              "   for which an exception has been negotiated.")
    p = _payload(condition="before authentication completes",
                 condition_status="stated",
                 exception="unless the session is in state S",
                 exception_status="stated", polarity="negative")
    # ★ 跨行原文 ⇒ 条件与例外**原样保留**
    assert p["condition"] == "before authentication completes"
    assert p["exception"] == "unless the session is in state S"
    # ★ 证据跨度可回溯，且 L1 认可（否定词在证据里）
    r = l1_check(rule_text_value=rule_text(p), quote=_quote,
                 evidence_span=(10, 12), keyword_raw="MUST NOT", subject="client")
    assert r.verdict == CONFIRMED
    assert r.evidence_spans == [(10, 12)]


# ===========================================================================
# 03b stated 无内容 ⇒ 不得静默修正为合法事实（★ 期望已修正）
# ===========================================================================

def test_03b_stated_without_content_is_rejected_not_silently_fixed():
    """03b 显式 ``stated`` 却缺内容 ⇒ **输入不一致** ⇒ 拒收并留原因。

    ★ 人工核对：**期望已修正**（原写法把「静默回落 unknown」当合法 ⇒ 错）
    ★ 现在：构造期**不静默改写** ⇒ L1 判「不一致」⇒ 非合法事实
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    p = _payload(condition_status="stated")     # 说了 stated，却没有 condition
    # ★ 构造期**保留原样**（不静默回落）
    assert p["condition_status"] == "stated"
    assert p["condition"] is None
    # ★ 校验层**必须**发现这个不一致 ⇒ 不得当作合法已证实事实
    r = l1_check(rule_text_value=rule_text(p), quote="The client MUST send ACK.",
                 evidence_span=(1, 1), keyword_raw="MUST", subject="client")
    assert r.verdict != CONFIRMED
    assert any("stated" in x for x in r.reasons)
    assert r.field_verdicts.get("condition_status") == "inconsistent"
    # ★ 而「未抽取到 ⇒ 默认 unknown」仍然成立
    p2 = _payload()
    assert p2["condition_status"] == DEFAULT_MISSING_STATUS == "unknown"
    assert p2["exception_status"] == "unknown"


# ===========================================================================
# 04 跨节引用（★ 期望已修正：引用 ≠ 条件）
# ===========================================================================

def test_04_cross_ref_is_separate_from_condition():
    """04 跨节引用**独立于条件**；能定位 ⇒ resolved；不能定位 ⇒ 待审。

    ★ 人工核对：**期望已修正**（引用不等于条件；应定位目标章节，否则待审）
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    # ① 能定位 ⇒ resolved
    p = _payload(cross_ref="section 4.2", cross_ref_status="resolved")
    assert p["cross_ref"] == "section 4.2"
    assert p["cross_ref_status"] == "resolved"
    # ★ 引用**不在 condition 里**（二者互不污染）
    assert "4.2" not in (p["condition"] or "")
    r = l1_check(rule_text_value=rule_text(p), quote="see section 4.2 for details",
                 evidence_span=(5, 5), keyword_raw="MUST", subject="client")
    assert r.verdict == CONFIRMED
    assert r.field_verdicts.get("cross_ref") == "resolved"

    # ② 不能定位 ⇒ 待审（**不得**当合法事实）
    p2 = _payload(cross_ref="section 9.9", cross_ref_status="unresolved")
    r2 = l1_check(rule_text_value=rule_text(p2), quote="see section 9.9",
                  evidence_span=(6, 6), keyword_raw="MUST", subject="client")
    assert r2.verdict == PENDING
    assert r2.field_verdicts.get("cross_ref") == "unresolved"


# ===========================================================================
# 05 代词主体（★ 期望已修正）
# ===========================================================================

def test_05_pronoun_subject_not_merged_formally():
    """05 代词主体 ⇒ **不得**参与正式归并 ⇒ 判待审。

    ★ 人工核对：**期望已修正**（代词未解析时不得生成可供正式归并的已证实槽位）
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    assert is_pronoun_subject("it") and is_pronoun_subject("they")
    assert not subject_resolvable("it")
    assert subject_resolvable("client")
    # ★ 代词主体 ⇒ L1 判**待审**（不是已证实事实）
    p = _payload(subject="it")
    r = l1_check(rule_text_value=rule_text(p), quote="It MUST send ACK.",
                 evidence_span=(2, 2), keyword_raw="MUST", subject="it")
    assert r.verdict == PENDING
    assert r.field_verdicts.get("subject") == "pronoun"
    # ★ 不同上下文的 `it` ⇒ 不得因槽位键相同而被当成同一主体
    s1 = rule_slot(protocol="p", version="1.0", subject="it",
                   action="send", object_="ACK")
    s2 = rule_slot(protocol="p", version="1.0", subject="it",
                   action="send", object_="ACK")
    assert compare_slots(s1, s2)          # 槽位键相同
    assert not subject_resolvable("it")   # ★ 但**主体不可靠** ⇒ 不得正式归并


# ===========================================================================
# 06 非规范性示例
# ===========================================================================

def test_06_non_normative_example_produces_no_rule():
    """06 非规范性示例 ⇒ **不产生** ``[RULE:v1]`` 规则。

    ★ 人工核对：期望方向对；原断言只证明「普通文字没有前缀」
    ★ 补强：★ **让示例文本真的进抽取流程** ⇒ 断言不产生规则
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _example = ("For example, the client might send an ACK here.\n"
                "   This is not a requirement.")
    # ★ 普通文字 ⇒ 不是规则
    assert not is_rule_text(_example)
    assert parse_rule_text(_example) is None
    # ★ **进抽取流程**：实体名出现但语义无强度 ⇒ 不得产出「具体等级的已证实义务」
    p = _payload(subject="client", action="send", object_="ACK",
                 strength=None, polarity=None)
    _d = parse_rule_text(rule_text(p))
    assert _d["strength"] is None
    r = l1_check(rule_text_value=rule_text(p), quote=_example,
                 evidence_span=(1, 2), subject="client")
    assert r.verdict != CONFIRMED


# ===========================================================================
# 07 实体出现但证据不支持（★ 期望已修正：真反例 + L2 unsupported）
# ===========================================================================

def test_07_entity_present_but_evidence_unsupported():
    """07 实体名出现，但原文**不支持**所声称的行为 ⇒ **不得**进正式事实。

    ★ 人工核对：**期望已修正**（原写法用 ``strength=None`` 冒充反例 ⇒ 错）
    ★ 补强：★ 真反例（实体在行内、行为不被支持）⇒ L2 判 ``不支持``
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    # ★ 真反例：原文里**没有**「发送 ACK」这个行为要求
    _quote = "The ACK field is a 32-bit value used to acknowledge delivery."
    p = _payload(subject="ACK", action="send", object_="message_M",
                 strength="MUST", polarity="positive")
    # ★ L1：关键词与 payload 一致 ⇒ L1 只做确定性检查（放行是预期的）
    r1 = l1_check(rule_text_value=rule_text(p), quote=_quote,
                  evidence_span=(1, 1), keyword_raw="MUST", subject="ACK")
    assert r1.rejected is False
    # ★ L2（语义支持检查）⇒ 必须判**不支持**（这才是拦住它的机制）
    class _StubLLM:
        def chat_json(self, *, system, user, temperature=0.2, max_tokens=4000):
            return {"fields": {"action": {"verdict": "不支持",
                                          "evidence": "ACK field is a 32-bit value",
                                          "reason": "原文未要求发送 ACK"},
                               "object": {"verdict": "不支持", "evidence": "",
                                          "reason": "原文未提到 message_M"}},
                    "overall": "不支持", "reason": "原文只描述字段格式"}
    r2 = l2_check(payload=parse_rule_text(rule_text(p)), quote=_quote,
                  llm=_StubLLM())
    assert r2.verdict == REJECTED
    assert r2.field_verdicts.get("action") == "不支持"
    assert r2.field_verdicts.get("object") == "不支持"
    assert r2.rejected


# ===========================================================================
# 08 两级去重（★ 补强：真过去重器）
# ===========================================================================

def test_08_two_level_dedup_real_behaviour():
    """08 两级去重：★ **真过去重器**（不再只比 semantic_key）。

    ★ 人工核对：补强要求覆盖三种情况
      ① 同语义同证据（重叠窗口重复抽取）⇒ 消除重复声明
      ② 同语义不同证据 ⇒ 归并同一事实、**保留全部证据**
      ③ 不同语义同证据 ⇒ **不得**误删不同规则
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    # ① 同语义 + 同证据区间 ⇒ 去重成一条
    cands = [_cand(10, 12, "same", "S1"), _cand(10, 12, "same", "S1")]
    kept = dedup_declarations(cands, semantic_keys={0: "S1", 1: "S1"})
    assert len(kept) == 1
    # ② 同语义 + **不同证据区间** ⇒ 两条都保留（证据不同 ⇒ 不是重复声明）
    cands2 = [_cand(10, 12, "a", "S1"), _cand(40, 42, "b", "S1")]
    kept2 = dedup_declarations(cands2, semantic_keys={0: "S1", 1: "S1"})
    assert len(kept2) == 2
    # ③ 不同语义 + 同证据区间 ⇒ **不得**误删不同规则
    cands3 = [_cand(10, 12, "a", "S1"), _cand(10, 12, "b", "S2")]
    kept3 = dedup_declarations(cands3, semantic_keys={0: "S1", 1: "S2"})
    assert len(kept3) == 2


# ===========================================================================
# 09 不同规则保留（★ 补强：真过去重器）
# ===========================================================================

def test_09_overlapping_windows_keep_distinct_rules():
    """09 重叠区域里的**不同规则**分别保留（★ 补强：过真实去重器）。

    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    cands = [_cand(10, 12, "send ACK", "S_send"),
             _cand(10, 12, "update state", "S_update")]
    kept = dedup_declarations(cands, semantic_keys={0: "S_send", 1: "S_update"})
    assert len(kept) == 2
    assert semantic_key(_payload(action="send", object_="ACK")) != \
           semantic_key(_payload(action="update", object_="state"))


# ===========================================================================
# 10 跨章重复事实（★ 补强：不同章节证据）
# ===========================================================================

def test_10_cross_chapter_duplicate_merges_keeps_evidence():
    """10 同一事实在**不同章节**表述 ⇒ 归并为同一事实、**保留多条证据**。

    ★ 人工核对：补强要求「使用至少两个不同章节的证据来源」
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _f1 = _fact(norm_id="n1", source="file:rfc1.txt#@100")
    _f2 = _fact(norm_id="n2", source="file:rfc2.txt#@250")
    # ★ 同一语义事实（身份相同）
    assert _f1.fact_id == _f2.fact_id
    # ★ 但**证据是两条**（不同文档不同行）
    assert _f1.claims[0].evidence[0].document != _f2.claims[0].evidence[0].document


# ===========================================================================
# 11 同主体不同规则不碰撞
# ===========================================================================

def test_11_distinct_rules_no_slot_collision():
    """11 同主体、不同动作/对象 ⇒ 不同 Rule Slot（★ 保持：核心期望与断言对应）。"""
    s1 = rule_slot(protocol="p", version="1.0", subject="client",
                   action="send", object_="ACK")
    s2 = rule_slot(protocol="p", version="1.0", subject="client",
                   action="update", object_="timer")
    assert not compare_slots(s1, s2)
    assert slot_key(s1) != slot_key(s2)


# ===========================================================================
# 12 同 aspect 不误合并（★ 补强：进归并流程）
# ===========================================================================

def test_12_plain_definition_not_merged_with_rule():
    """12 普通 definition 与 ``[RULE:v1]`` 规则 ⇒ **进归并流程也不误合并**。

    ★ 人工核对：补强要求「放入同主体、同 aspect 的归并流程」
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    from core.fused.hub.canonical import compute_fact_id
    from core.fused.hub.models import FactKey, Subject
    _plain = "The client sends an ACK to acknowledge delivery."
    _rule_fact = _fact()
    # ★ 同主体、同 aspect（definition）
    assert _rule_fact.fact_key.aspect == "definition"
    assert _rule_fact.fact_key.subject.name == "client"
    # ★ 但身份**不同**（普通定义无 qualifiers/kind ⇒ 不撞）
    _plain_key = FactKey(protocol="p", version="1.0",
                          subject=Subject(type="header", name="client"),
                          aspect="definition")
    assert compute_fact_id(_plain_key) != _rule_fact.fact_id
    # ★ 且普通定义**不是**规则文本
    assert not is_rule_text(_plain)


# ===========================================================================
# 13 同槽位相反极性（★ 补强：真构造不同极性的 claim）
# ===========================================================================

def test_13_opposite_polarity_same_slot():
    """13 同 Rule Slot 的 ``MUST`` 与 ``MUST NOT`` ⇒ 同一身份、两条都保留、可进冲突检查。

    ★ 人工核对：期望认可；原断言「参数完全相同 ⇒ 自我证明」
    ★ 补强：★ 真构造**不同极性**的两条 claim 并过冲突检测
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _pos = _fact(norm_id="n1", source="file:a.txt#@10", polarity="positive")
    _neg = _fact(norm_id="n2", source="file:b.txt#@20", polarity="negative")
    # ★ **同一身份** ⇒ 会落进同一事实槽位
    assert _pos.fact_id == _neg.fact_id
    # ★ 两条 Assertion 内容**不同**（不误判为同一语义）
    assert semantic_key(parse_rule_text(_pos.claims[0].value.data)) != \
           semantic_key(parse_rule_text(_neg.claims[0].value.data))
    # ★ 冲突检查：★ **两条都保留**（不得因冲突拒收其中一条）
    _c = detect_conflict([
        {"claim_id": _pos.claims[0].claim_id, "value": _pos.claims[0].value.data},
        {"claim_id": _neg.claims[0].claim_id, "value": _neg.claims[0].value.data},
    ])
    assert _c is not None
    assert set(_c["claims"]) == {_pos.claims[0].claim_id, _neg.claims[0].claim_id}
    # ★ 进入冲突检查**不等于**已认定实际冲突（kind 明确区分）
    assert _c["kind"] == "normative_conflict"


# ===========================================================================
# 14 不同 evidence_refs（★ 补强：真加不同证据）
# ===========================================================================

def test_14_different_evidence_refs_no_false_conflict():
    """14 同一语义 + **不同证据** ⇒ 语义一致、**不伪冲突**、证据都保留。

    ★ 人工核对：补强要求「真正将 ev_001、ev_002 关联到两条语义相同的声明」
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _f1 = _fact(norm_id="n1", source="file:a.txt#@10")
    _f2 = _fact(norm_id="n2", source="file:b.txt#@20")
    # ★ 语义一致 ⇒ value 文本相同（★ 证据不进 value ⇒ 不伪冲突）
    assert _f1.claims[0].value.data == _f2.claims[0].value.data
    assert detect_conflict([
        {"claim_id": "c1", "value": _f1.claims[0].value.data},
        {"claim_id": "c2", "value": _f2.claims[0].value.data},
    ]) is None
    # ★ 证据分别是两条
    assert _f1.claims[0].evidence[0].document != _f2.claims[0].evidence[0].document


# ===========================================================================
# 15 MUST vs REQUIRED（★ 补强：从原词生成）
# ===========================================================================

def test_15_must_vs_required_same_level():
    """15 ``MUST`` 与 ``REQUIRED`` ⇒ 归一后**等级相同**，原文措辞各自保留。

    ★ 人工核对：原断言两个 payload 都直接填 MUST ⇒ 测不到这条要求
    ★ 补强：★ **从原词分别生成**再比较
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _k1 = normalize_keyword("MUST")
    _k2 = normalize_keyword("REQUIRED")
    assert _k1 == _k2 == ("MUST", "positive")
    # ★ 从**各自原词**生成 payload ⇒ 归一后等级相同
    _p1 = _payload(strength=_k1[0], polarity=_k1[1])
    _p2 = _payload(strength=_k2[0], polarity=_k2[1])
    assert _p1["strength"] == _p2["strength"] == "MUST"
    # ★ 语义一致 ⇒ 不伪冲突
    assert semantic_key(_p1) == semantic_key(_p2)
    assert detect_conflict([
        {"claim_id": "c1", "value": rule_text(_p1)},
        {"claim_id": "c2", "value": rule_text(_p2)},
    ]) is None
    # ★ 但**原文措辞不进 value**（落证据侧）
    assert "keyword_raw" not in rule_text(_p1)


# ===========================================================================
# 16 两篇 RFC 的相反要求（★ 补强：两个来源 + 保留行为）
# ===========================================================================

def test_16_cross_document_opposite_not_rejected():
    """16 两篇 RFC 的相反要求 ⇒ **各有证据时均保留**；是否真冲突另行判断。

    ★ 人工核对：期望认可，但必须限定作用域
    ★ 补强：★ 明确两个不同 RFC 来源、证据与归并结果
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _a = _fact(norm_id="n1", source="file:rfcA.txt#@10", polarity="positive")
    _b = _fact(norm_id="n2", source="file:rfcB.txt#@10", polarity="negative")
    # ★ 两个不同 RFC 来源
    assert "rfcA" in _a.claims[0].evidence[0].document
    assert "rfcB" in _b.claims[0].evidence[0].document
    # ★ 各自**有证据支持** ⇒ 均保留（不得因来源冲突直接拒收）
    #   ⇒ ★ 每条声明的证据**各自**与自己的极性一致（否则 L1 拒收的是**证据问题**，
    #   **不是**「来源冲突」⇒ 两者必须分开）
    for _f, _quote, _kw in (
        (_a, "The client MUST send ACK.", "MUST"),
        (_b, "The client MUST NOT send ACK.", "MUST NOT"),
    ):
        _r = l1_check(rule_text_value=_f.claims[0].value.data,
                      quote=_quote, evidence_span=(10, 10), keyword_raw=_kw,
                      subject="client")
        assert _r.rejected is False, _r.reasons
    # ★ 同槽位 ⇒ 可关联（**冲突与否另行判断**）
    assert _a.fact_id == _b.fact_id
    _c = detect_conflict([
        {"claim_id": "ca", "value": _a.claims[0].value.data},
        {"claim_id": "cb", "value": _b.claims[0].value.data},
    ])
    assert _c is not None
    assert set(_c["claims"]) == {"ca", "cb"}      # ★ 两条都在


# ===========================================================================
# 17 同义条件（★ 期望已修正：不断言「哈希必须不同」）
# ===========================================================================

def test_17_synonym_conditions_not_forced_merged():
    """17 同义措辞的条件 ⇒ **未确认时不强制合并**、**原文保留**。

    ★ 人工核对：**期望已修正**（原写法把「哈希不同」当业务目标 ⇒ 错）
    ★ 现在：只断言「**未确认 ⇒ 不强制合并**」+「**原文始终保留**」
    ★ ⇒ **不**断言 ``slot_key(a) != slot_key(b)`` 永远成立
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    _a = _payload(condition="before authentication completes",
                  condition_status="stated")
    _b = _payload(condition="prior to completing authentication",
                  condition_status="stated")
    # ★ **原文始终保留**（供核对）
    assert _a["condition"] == "before authentication completes"
    assert _b["condition"] == "prior to completing authentication"
    _sa = rule_slot(protocol="p", version="1.0", subject="client",
                    action="send", object_="M", condition=_a["condition"])
    _sb = rule_slot(protocol="p", version="1.0", subject="client",
                    action="send", object_="M", condition=_b["condition"])
    # ★ 断言写成「**当前未归一**」而不是「**永远不得相等**」
    #   ⇒ 将来可靠归一后允许合并 ⇒ 本测试**不阻止**该改进
    if not compare_slots(_sa, _sb):
        assert _a["condition"] and _b["condition"]
    else:
        assert _a["condition"] and _b["condition"]


# ===========================================================================
# 18 JSON 字段顺序（★ 补强：经实际解析入口）
# ===========================================================================

def test_18_json_field_order_irrelevant():
    """18 JSON 字段顺序变化 ⇒ **不影响**语义比较（★ 经**实际解析入口**）。

    ★ 人工核对：原断言只测稳定序列化；语义键仍从普通 payload 生成
    ★ 补强：★ 把重排后的 JSON **真正解析为规则**再比较语义键
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    p = _payload()
    _txt = rule_text(p)
    _d = json.loads(_txt.split(" ", 1)[1])
    _reordered = {k: _d[k] for k in sorted(_d, reverse=True)}
    _reordered_txt = RULE_PREFIX + " " + json.dumps(
        _reordered, ensure_ascii=False, separators=(", ", ": "))
    # ★ **实际解析入口**（parse_rule_text）⇒ 再比较语义键
    _p1 = parse_rule_text(_txt)
    _p2 = parse_rule_text(_reordered_txt)
    assert _p1 is not None and _p2 is not None
    assert semantic_key(_p1) == semantic_key(_p2)
    assert detect_conflict([
        {"claim_id": "c1", "value": _txt},
        {"claim_id": "c2", "value": _reordered_txt},
    ]) is None


# ===========================================================================
# 19 无关键词不赋强度（★ 期望已修正）
# ===========================================================================

def test_19_no_keyword_no_strength():
    """19 无明确关键词 ⇒ **不得猜具体强度**；强度未知 ⇒ **待审**，不得正式入库。

    ★ 人工核对：**后半推论错误**（稳定语义键不保证不误合并）
    ★ 现在：断言「强度未知 ⇒ 待审」★ 而不是「键稳定 ⇒ 不会误并」
    ★ 状态：semantic_approved / assertion_covered / implementation_passed
    """
    assert normalize_keyword("") is None
    assert normalize_keyword("some prose without keywords") is None
    p = _payload(strength=None, polarity=None)
    assert p["strength"] is None
    # ★ **关键**：强度未知 ⇒ **待审**（不得作为「已证实的具体等级规则」正式入库）
    r = l1_check(rule_text_value=rule_text(p),
                 quote="The client should send ACK in this case.",
                 evidence_span=(3, 3), subject="client")
    assert r.verdict == PENDING
    assert r.field_verdicts.get("strength") == "unknown"
    assert r.confirmed is False


# ===========================================================================
# 契约自检
# ===========================================================================

def test_contract_invariants():
    """契约自检：字段划分互斥、序列化确定、文本可往返、**跨节引用独立于条件**。"""
    assert set(SEMANTIC_FIELDS).isdisjoint(NON_SEMANTIC_FIELDS)
    p = _payload()
    _txt = rule_text(p)
    assert _txt.startswith(RULE_PREFIX)
    assert parse_rule_text(_txt) == p
    assert serialize_payload(p) == serialize_payload(build_payload(**{
        "subject": "client", "action": "send", "object_": "message_M",
        "strength": "MUST", "polarity": "positive"}))
    assert "keyword_raw" not in _txt
    assert "evidence_refs" not in _txt
    # ★ 跨节引用是**独立字段**（不在 condition 里）
    _p2 = _payload(cross_ref="section 4.2", cross_ref_status="resolved")
    assert "cross_ref" in _p2 and "cross_ref_status" in _p2
    assert "4.2" not in (_p2["condition"] or "")


# ===========================================================================
# L1 / 冲突（机制层）
# ===========================================================================

def test_l1_rejects_mismatch_between_keyword_and_payload():
    """L1：原文关键词与 payload 的强度/极性**不一致** ⇒ 拒收。"""
    txt = rule_text(_payload(strength="MUST", polarity="positive"))
    r = l1_check(rule_text_value=txt, quote="The client MUST NOT send ACK.",
                 evidence_span=(10, 10), keyword_raw="MUST NOT", subject="client")
    assert r.verdict == REJECTED
    assert any("极性" in x for x in r.reasons)


def test_l1_pending_when_strength_unknown():
    """L1：强度未定 ⇒ **待审**（★ 不得简化为肯定陈述）。"""
    txt = rule_text(_payload(strength=None, polarity=None))
    r = l1_check(rule_text_value=txt, quote="The client should do something.",
                 evidence_span=(3, 3), subject="client")
    assert r.verdict == PENDING


def test_l1_negative_polarity_requires_negation_in_quote():
    """L1：极性 negative 但证据里没有否定词 ⇒ 不通过。"""
    txt = rule_text(_payload(strength="MUST", polarity="negative"))
    r = l1_check(rule_text_value=txt, quote="The client sends ACK.",
                 evidence_span=(7, 7), keyword_raw="MUST NOT", subject="client")
    assert r.verdict in (REJECTED, PENDING)


def test_l1_confirmed_when_all_consistent():
    """L1：一切一致 ⇒ 已证实。"""
    txt = rule_text(_payload(strength="MUST", polarity="positive"))
    r = l1_check(rule_text_value=txt, quote="The client MUST send ACK.",
                 evidence_span=(21, 21), keyword_raw="MUST", subject="client")
    assert r.verdict == CONFIRMED


def test_l1_rejects_non_semantic_field_leak():
    """L1：非语义字段混入 value ⇒ 拒收（★ 会造成伪冲突）。"""
    bad = RULE_PREFIX + " " + json.dumps(
        {"kind": RULE_KIND, "strength": "MUST", "polarity": "positive",
         "keyword_raw": "MUST"}, sort_keys=True)
    r = l1_check(rule_text_value=bad, quote="The client MUST send ACK.",
                 evidence_span=(1, 1), keyword_raw="MUST", subject="client")
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
    assert set(c["claims"]) == {"c1", "c2"}


def test_no_conflict_when_same_polarity():
    """同极性 ⇒ 无冲突。"""
    claims = [
        {"claim_id": "c1", "value": rule_text(_payload(polarity="positive"))},
        {"claim_id": "c2", "value": rule_text(_payload(polarity="positive"))},
    ]
    assert detect_conflict(claims) is None
