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
    publish_gate,
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
    """03 条件与例外**跨行**也完整保留（★ 真过**跨行抽取器**，不是手工填 payload）。

    ★ 人工核对：原断言「条件/例外是手工填入 payload 的，没验证真实跨行抽取」
    ★ 补强：★ 用 :func:`extract_condition` / :func:`extract_exception`
      从**跨行原文**真抽 ⇒ ⇒ 断言抽出的结果进了 payload
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.extraction.normative_extract import (
        extract_condition, extract_exception,
    )
    _quote = ("The client MUST NOT send message M before authentication\n"
              "   completes, unless the session is in state S\n"
              "   for which an exception has been negotiated.")
    # ★ **真抽取**（跨行 ⇒ 先合并空白再切句）
    _cond, _cs = extract_condition(_quote)
    _exc, _es = extract_exception(_quote)
    assert _cs == "stated" and _es == "stated"
    assert _cond and "before authentication completes" in _cond
    assert _exc and "unless the session is in state S" in _exc
    # ★ 抽出的结果 ⇒ 进 payload（不再是手工构造）
    p = _payload(condition=_cond, condition_status=_cs,
                 exception=_exc, exception_status=_es, polarity="negative")
    assert p["condition"] and p["exception"]
    # ★ 证据跨度可回溯，且 L1 认可（否定词在证据里）
    r = l1_check(rule_text_value=rule_text(p), quote=_quote,
                 evidence_span=(10, 12), keyword_raw="MUST NOT", subject="client")
    assert r.verdict == CONFIRMED
    assert r.evidence_spans == [(10, 12)]


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
    """04 跨节引用**独立于条件**；**真定位**目标章节；定位不到 ⇒ 待审。

    ★ 人工核对：原断言「``cross_ref_status="resolved"`` 是测试手工指定的，
      没有真正调用章节定位器；而且证据只有 see section 4.2，却要求 L1 返回 CONFIRMED」
    ★ 补强：★ 用 :func:`extract_cross_ref` + :func:`locate_section_ref` **真定位**
      ⇒ ⇒ 证据只有引用句时 L1 **不得 CONFIRMED**
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.extraction.normative_extract import (
        extract_cross_ref, locate_section_ref,
    )
    _doc = ("4.1 Overview\nsome text\n"
            "4.2 Message Formats\n"
            "The client MUST send the request here.\n"
            "9.9 Missing Chapter\n")
    # ① 抽引用 + **真定位**
    _ref, _rs = extract_cross_ref("see section 4.2 for details")
    assert _rs == "stated" and _ref == "section 4.2"
    _num, _st = locate_section_ref(_doc, _ref)
    assert _st == "resolved" and _num == "4.2"

    # ② 定位得到 ⇒ 引用与条件**互不污染**
    p = _payload(cross_ref=_ref, cross_ref_status=_st)
    assert "4.2" not in (p["condition"] or "")
    # ★ 证据**含对行为的陈述** ⇒ L1 可确认
    r = l1_check(rule_text_value=rule_text(p),
                 quote="The client MUST send the request here.",
                 evidence_span=(4, 4), keyword_raw="MUST", subject="client")
    assert r.verdict == CONFIRMED
    assert r.field_verdicts.get("cross_ref") == "resolved"

    # ③ **定位不到** ⇒ unresolved ⇒ 待审（不得当合法事实）
    _ref2, _rs2 = extract_cross_ref("see section 7.7 for details")
    _num2, _st2 = locate_section_ref(_doc, _ref2)
    assert _st2 == "unresolved"
    p2 = _payload(cross_ref=_ref2, cross_ref_status=_st2)
    r2 = l1_check(rule_text_value=rule_text(p2),
                  quote="The client MUST send the request here.",
                  evidence_span=(4, 4), keyword_raw="MUST", subject="client")
    assert r2.verdict == PENDING
    assert r2.field_verdicts.get("cross_ref") == "unresolved"

    # ④ ★ 证据**只有引用句** ⇒ L1 **不得 CONFIRMED**（★ 意见指出的缺口）
    r3 = l1_check(rule_text_value=rule_text(p),
                  quote="see section 4.2 for details",
                  evidence_span=(1, 1), keyword_raw="MUST", subject="client")
    assert r3.verdict != CONFIRMED
    assert r3.field_verdicts.get("evidence") == "insufficient"


def test_05_pronoun_subject_not_merged_formally():
    """05 **未成功消解指代**的代词主体不得进入正式归并；**成功解析主体后可以进入**。

    ★ 人工核对：原表述「代词主体不进正式归并」**过于绝对** ⇒ 改为「未成功消解的」
      ⇒ 且原断言只测到 L1 待审，**没测正式发布流程是否确实隔离**
    ★ 补强：★ 过**发布闸**（真实发布路径的隔离判定）
    ★ 状态：语义已认可（措辞已修）/ 断言覆盖 ✔ / 实现待验收
    """
    assert is_pronoun_subject("it") and is_pronoun_subject("they")
    assert not subject_resolvable("it")
    assert subject_resolvable("client")

    # ① 未消解的代词主体 ⇒ **被发布闸隔离**
    p = _payload(subject="it")
    r = l1_check(rule_text_value=rule_text(p), quote="It MUST send ACK.",
                 evidence_span=(2, 2), keyword_raw="MUST", subject="it")
    assert r.verdict == PENDING
    assert r.field_verdicts.get("subject") == "pronoun"
    _ok, _why = publish_gate(payload=parse_rule_text(rule_text(p)),
                              subject="it", verdict=r.verdict)
    assert _ok is False and "主体" in _why

    # ② ★ **成功解析主体后可以进入**（不是绝对禁止）
    _ok2, _why2 = publish_gate(payload=parse_rule_text(rule_text(p)),
                               subject="client", verdict=CONFIRMED)
    assert _ok2 is True, _why2
    assert subject_resolvable("client")


def test_06_non_normative_example_produces_no_rule():
    """06 非规范性示例 ⇒ **不产生**规则，且**不因出现动作词就当成 MUST 类义务**。

    ★ 人工核对：原断言只证明「普通文字没有前缀」，**没走真实抽取入口**
    ★ 补强：★ 让示例文本**真的进抽取判据**（候选信号 + 确定性语义支持）
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.extraction.normative_extract import semantic_support
    from core.fused.extraction.window_candidates import detect_triggers
    _example = ("For example, the client might send an ACK here.\n"
                "   This is not a requirement.")
    # ★ 普通文字 ⇒ 不是规则
    assert not is_rule_text(_example)
    assert parse_rule_text(_example) is None
    # ★ **进抽取判据**：示例可能**触发**候选（出现 send 等动作词）
    _trig = detect_triggers(_example)
    _p = _payload(subject="client", action="send", object_="ACK",
                  strength="MUST", polarity="positive")
    # ★ 但**确定性语义支持**判定原文**不支持**该义务 ⇒ ⇒ 不得发布
    _v, _r = semantic_support(_example, "send", "ACK", strength="MUST")
    assert _v == "不支持", _r
    # ★ 发布闸 ⇒ 隔离（进待审）
    _ok, _why = publish_gate(payload=parse_rule_text(rule_text(_p)),
                             subject="client", verdict=PENDING)
    assert _ok is False


def test_07_entity_present_but_evidence_unsupported():
    """07 实体名出现，但原文**不支持**所声称的行为 ⇒ **不得**进正式事实。

    ★ 人工核对：原断言用 Stub LLM **预先返回「不支持」** ⇒ 只证明 L2 能处理拒收，
      **未证明验证器能识别不受支持的结论**
    ★ 补强：★ 用**确定性语义支持检查**（不依赖 LLM）识别出「原文不支持发送 ACK」
      ⇒ ⇒ 并验证 L2 的**通路**（LLM 路径仍被覆盖）
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.extraction.normative_verify import l2_deterministic_check
    # ★ 真反例：原文里**没有**「发送 ACK」这个行为要求（只有字段格式描述）
    _quote = "The ACK field is a 32-bit value used to acknowledge delivery."
    p = _payload(subject="ACK", action="send", object_="message_M",
                 strength="MUST", polarity="positive")
    # ★ **确定性检查**（不依赖 LLM）⇒ 必须自己识别出「不受支持」
    _v, _r = l2_deterministic_check(
        payload=parse_rule_text(rule_text(p)), quote=_quote)
    assert _v == "不支持", _r
    # ★ L2 **真调用**（确定性前置命中 ⇒ 直接拒收，不调 LLM）
    class _BoomLLM:
        def chat_json(self, **kw):
            raise AssertionError("★ 确定性前置应已拦下 ⇒ 不应调 LLM")
    r2 = l2_check(payload=parse_rule_text(rule_text(p)), quote=_quote,
                  llm=_BoomLLM())
    assert r2.verdict == REJECTED
    assert r2.rejected
    # ★ 发布闸 ⇒ 不得进入正式事实
    _ok, _why = publish_gate(payload=parse_rule_text(rule_text(p)),
                             subject="ACK", verdict=r2.verdict)
    assert _ok is False


def test_08_two_level_dedup_real_behaviour():
    """08 两级去重：★ 声明级（去重器）**与** 事实级（**真实归并**后证据完整保留）。

    ★ 人工核对：原断言只测声明级去重，**没测事实级归并后证据是否完整保留**
    ★ 补强：★ 过 **:func:`resolve_claims`**（中枢真实消解）⇒ 断言证据都在
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.downstream.resolver import resolve_claims
    # ① 声明级：同语义 + 同证据区间 ⇒ 去重成一条
    cands = [_cand(10, 12, "same", "S1"), _cand(10, 12, "same", "S1")]
    assert len(dedup_declarations(cands, semantic_keys={0: "S1", 1: "S1"})) == 1
    # ② 声明级：同语义 + **不同证据区间** ⇒ 两条都保留
    cands2 = [_cand(10, 12, "a", "S1"), _cand(40, 42, "b", "S1")]
    assert len(dedup_declarations(cands2, semantic_keys={0: "S1", 1: "S1"})) == 2
    # ③ 声明级：不同语义 + 同证据区间 ⇒ **不得**误删不同规则
    cands3 = [_cand(10, 12, "a", "S1"), _cand(10, 12, "b", "S2")]
    assert len(dedup_declarations(cands3, semantic_keys={0: "S1", 1: "S2"})) == 2

    # ④ ★ **事实级**：两条同语义、不同证据 ⇒ 归并后**两条证据都在**
    _f1 = _fact(norm_id="n1", source="file:a.txt#@10")
    _f2 = _fact(norm_id="n2", source="file:b.txt#@20")
    _claims = [{"claim_id": c.claim_id, "value": c.value.data,
                "epistemic_type": c.epistemic_type, "authority": c.authority}
               for c in (_f1.claims[0], _f2.claims[0])]
    _res = resolve_claims(_claims, "definition")
    # ★ 两条 claim **都在**（采纳的 ∪ 被覆盖但保留的）
    _all = set(_res.get("basis_claim_ids") or []) | set(_res.get("superseded") or [])
    assert {c.claim_id for c in (_f1.claims[0], _f2.claims[0])} <= _all


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
    """10 同一事实在**不同章节**表述 ⇒ **真实归并**后语义事实只有一个、证据有两条。

    ★ 人工核对：原断言「创建了两个独立 Fact，检查 ID 相同，**没有真正执行多证据归并**」
    ★ 补强：★ 过 **:func:`resolve_claims`** ⇒ 断言两条 claim 归并、证据都保留
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.downstream.resolver import resolve_claims
    _f1 = _fact(norm_id="n1", source="file:rfc1.txt#@100")
    _f2 = _fact(norm_id="n2", source="file:rfc2.txt#@250")
    # ★ 同一语义事实（身份相同）
    assert _f1.fact_id == _f2.fact_id
    # ★ **真正执行归并**
    _claims = [{"claim_id": c.claim_id, "value": c.value.data,
                "epistemic_type": c.epistemic_type, "authority": c.authority}
               for c in (_f1.claims[0], _f2.claims[0])]
    _res = resolve_claims(_claims, "definition")
    # ★ 两条 claim **都被保留**
    _all = set(_res.get("basis_claim_ids") or []) | set(_res.get("superseded") or [])
    assert {c.claim_id for c in (_f1.claims[0], _f2.claims[0])} <= _all
    # ★ 两条**证据**都在（不同文档不同行）
    _ev_docs = {_f1.claims[0].evidence[0].document,
                _f2.claims[0].evidence[0].document}
    assert len(_ev_docs) == 2


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
    """12 普通 definition 与 ``[RULE:v1]`` 规则 ⇒ **过真实归并流程**也不误合并。

    ★ 人工核对：原断言「检查了两个 FactID 不同，**尚未真正调用事实归并流程**」
    ★ 补强：★ 把两者放进同一 fact 的 claims 里 ⇒ 过 **:func:`resolve_claims`**
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.downstream.resolver import resolve_claims
    from core.fused.extraction.norm import prose_semantics_norm_to_facts
    _plain_text = "The client sends an ACK to acknowledge delivery."
    _rule_fact = _fact()
    # ★ 普通定义走**散文语义**映射（kind=prose_semantics ⇒ value 是自然语言）
    _plain_fact = prose_semantics_norm_to_facts({
        "kind": "prose_semantics", "protocol": "p", "kb_source_type": "rfc",
        "name": "client", "content": _plain_text, "norm_id": "np",
        "source": "file:d.txt#@3", "meaning": "plain",
    })[0]
    # ★ 同主体、同 aspect
    assert _rule_fact.fact_key.aspect == "definition"
    assert _plain_fact.fact_key.subject.name == _rule_fact.fact_key.subject.name
    # ★ 但**身份不同**（普通定义无 qualifiers/kind）
    assert _rule_fact.fact_id != _plain_fact.fact_id
    # ★ **过真实归并**：语义不同 ⇒ 判**冲突**而非误合并（两条都保留）
    _claims = [{"claim_id": c.claim_id, "value": c.value.data,
                "epistemic_type": c.epistemic_type, "authority": c.authority}
               for c in (_rule_fact.claims[0], _plain_fact.claims[0])]
    _res = resolve_claims(_claims, "definition")
    assert _res.get("method") in ("conflict", "consensus")
    _all = set(_res.get("basis_claim_ids") or []) | set(_res.get("superseded") or [])
    assert {c.claim_id for c in (_rule_fact.claims[0], _plain_fact.claims[0])} <= _all


def test_13_opposite_polarity_same_slot():
    """13 相反极性声明进入**同一 Rule Slot**，**均被保留**，并进入**潜在冲突检查**。

    ★ 人工核对：措辞「可检出冲突」易被理解成**必然存在真实冲突**
      ⇒ 改为「进入**潜在**冲突检查；**是否真冲突需看适用条件和来源效力**」
      ⇒ 且原断言**未验证真实中枢归并后两条 claim 都被保留**
    ★ 补强：★ 过 **:func:`resolve_claims`** ⇒ 断言两条 claim 都在
    ★ 状态：语义已认可（措辞已修）/ 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.downstream.resolver import resolve_claims
    _pos = _fact(norm_id="n1", source="file:a.txt#@10", polarity="positive")
    _neg = _fact(norm_id="n2", source="file:b.txt#@20", polarity="negative")
    # ★ **同一身份** ⇒ 同一 Rule Slot ⇒ 会落进同一事实槽位
    assert _pos.fact_id == _neg.fact_id
    # ★ 两条 Assertion 内容**不同**
    assert semantic_key(parse_rule_text(_pos.claims[0].value.data)) != \
           semantic_key(parse_rule_text(_neg.claims[0].value.data))
    # ★ **真实中枢归并** ⇒ 两条 claim **都被保留**
    _claims = [{"claim_id": c.claim_id, "value": c.value.data,
                "epistemic_type": c.epistemic_type, "authority": c.authority}
               for c in (_pos.claims[0], _neg.claims[0])]
    _res = resolve_claims(_claims, "definition")
    _all = set(_res.get("basis_claim_ids") or []) | set(_res.get("superseded") or [])
    assert {c.claim_id for c in (_pos.claims[0], _neg.claims[0])} <= _all
    # ★ 进入**潜在**冲突检查（★ 不等于已认定真冲突 ⇒ 需看条件/版本/来源效力）
    _c = detect_conflict([
        {"claim_id": _pos.claims[0].claim_id, "value": _pos.claims[0].value.data},
        {"claim_id": _neg.claims[0].claim_id, "value": _neg.claims[0].value.data},
    ])
    assert _c is not None
    assert set(_c["claims"]) == {_pos.claims[0].claim_id, _neg.claims[0].claim_id}
    assert _c["kind"] == "normative_conflict"


def test_14_different_evidence_refs_no_false_conflict():
    """14 同一语义 + **不同证据** ⇒ 语义一致、不伪冲突，**合并后两条证据仍存在**。

    ★ 人工核对：原断言「检查了不同来源、相同 value、无冲突，**未测试合并后两条证据仍存在**」
    ★ 补强：★ 过 **:func:`resolve_claims`** ⇒ 断言归并后两条 claim 与证据都在
    ★ 状态：语义已认可 / 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.downstream.resolver import resolve_claims
    _f1 = _fact(norm_id="n1", source="file:a.txt#@10")
    _f2 = _fact(norm_id="n2", source="file:b.txt#@20")
    # ★ 语义一致 ⇒ value 文本相同（★ 证据不进 value ⇒ 不伪冲突）
    assert _f1.claims[0].value.data == _f2.claims[0].value.data
    assert detect_conflict([
        {"claim_id": "c1", "value": _f1.claims[0].value.data},
        {"claim_id": "c2", "value": _f2.claims[0].value.data},
    ]) is None
    # ★ **真实归并** ⇒ 两条 claim 都在
    _claims = [{"claim_id": c.claim_id, "value": c.value.data,
                "epistemic_type": c.epistemic_type, "authority": c.authority}
               for c in (_f1.claims[0], _f2.claims[0])]
    _res = resolve_claims(_claims, "definition")
    _all = set(_res.get("basis_claim_ids") or []) | set(_res.get("superseded") or [])
    assert {c.claim_id for c in (_f1.claims[0], _f2.claims[0])} <= _all
    # ★ 两条**证据**分别挂在各自的 claim 上（合并后仍在）
    _docs = {_f1.claims[0].evidence[0].document,
             _f2.claims[0].evidence[0].document}
    assert len(_docs) == 2


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
    """16 两篇 RFC 的相反要求 ⇒ 各自有证据时**均被保留**；★ 是否**真冲突**另行判断。

    ★ 人工核对：原断言「构造了两个 RFC 来源，也调用了 L1 和冲突检测，
      **但没有验证真实发布时两条 claim 都保留**」
    ★ 补强：★ 过 **:func:`resolve_claims`**（真实归并）⇒ 断言两条 claim 都在
    ★ 状态：语义已认可（措辞已修）/ 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.downstream.resolver import resolve_claims
    _a = _fact(norm_id="n1", source="file:rfcA.txt#@10", polarity="positive")
    _b = _fact(norm_id="n2", source="file:rfcB.txt#@10", polarity="negative")
    # ★ 两个不同 RFC 来源
    assert "rfcA" in _a.claims[0].evidence[0].document
    assert "rfcB" in _b.claims[0].evidence[0].document
    # ★ 各自**有证据支持** ⇒ 均**不拒收**（各自证据与各自极性一致）
    for _f, _quote, _kw in (
        (_a, "The client MUST send ACK.", "MUST"),
        (_b, "The client MUST NOT send ACK.", "MUST NOT"),
    ):
        _r = l1_check(rule_text_value=_f.claims[0].value.data,
                      quote=_quote, evidence_span=(10, 10), keyword_raw=_kw,
                      subject="client")
        assert _r.rejected is False, _r.reasons
    # ★ 同槽位 ⇒ 可关联
    assert _a.fact_id == _b.fact_id
    # ★ **真实发布/归并** ⇒ 两条 claim **都保留**
    _claims = [{"claim_id": c.claim_id, "value": c.value.data,
                "epistemic_type": c.epistemic_type, "authority": c.authority}
               for c in (_a.claims[0], _b.claims[0])]
    _res = resolve_claims(_claims, "definition")
    _all = set(_res.get("basis_claim_ids") or []) | set(_res.get("superseded") or [])
    assert {c.claim_id for c in (_a.claims[0], _b.claims[0])} <= _all
    # ★ **是否真冲突另行判断**（★ 需看适用条件 / 版本 / 来源效力）
    _c = detect_conflict([
        {"claim_id": "ca", "value": _a.claims[0].value.data},
        {"claim_id": "cb", "value": _b.claims[0].value.data},
    ])
    assert _c is not None and set(_c["claims"]) == {"ca", "cb"}


def test_17_synonym_conditions_not_forced_merged():
    """17 未确认时**不强制合并**；★ 可靠确认后**允许合并**（★ 不阻止将来改进）。

    ★ 人工核对：原断言「if/else 两个分支**执行相同断言**」⇒ **没检验**
      「未确认时不强制合并」；且「把『同义条件必须不同哈希』固定为业务期望」错
    ★ 补强：★ 用 :func:`normalize_condition`（**带开关**）⇒ 断言两条路径：
      未确认 ⇒ 不合并；★ 开关打开且命中同义表 ⇒ **允许合并**
    ★ 状态：语义已认可（期望已修）/ 断言覆盖 ✔ / 实现待验收
    """
    from core.fused.extraction import normative_extract as _nx
    _a_text = "before authentication completes"
    _b_text = "prior to completing authentication"
    # ★ 未确认（开关关闭）⇒ **不合并**，且原文保留
    _na, _ca = _nx.normalize_condition(_a_text)
    _nb, _cb = _nx.normalize_condition(_b_text)
    assert _ca is False and _cb is False
    _sa = rule_slot(protocol="p", version="1.0", subject="client",
                    action="send", object_="M", condition=_a_text)
    _sb = rule_slot(protocol="p", version="1.0", subject="client",
                    action="send", object_="M", condition=_b_text)
    assert not compare_slots(_sa, _sb)      # ★ 未确认 ⇒ 不合并
    # ★ 原文**始终保留**（供核对）
    p_a = _payload(condition=_a_text, condition_status="stated")
    p_b = _payload(condition=_b_text, condition_status="stated")
    assert p_a["condition"] == _a_text and p_b["condition"] == _b_text

    # ★ **可靠确认后允许合并**（★ 本测试**不阻止**该改进）
    _old = _nx.ENABLE_CONDITION_NORMALIZATION
    try:
        _nx.ENABLE_CONDITION_NORMALIZATION = True
        _na2, _ca2 = _nx.normalize_condition(_a_text)
        _nb2, _cb2 = _nx.normalize_condition(_b_text)
        assert _ca2 is True and _cb2 is True
        assert _na2 == _nb2                  # ★ 归一后 ⇒ 同一条件 ⇒ 允许合并
        _sa2 = rule_slot(protocol="p", version="1.0", subject="client",
                         action="send", object_="M", condition=_na2)
        _sb2 = rule_slot(protocol="p", version="1.0", subject="client",
                         action="send", object_="M", condition=_nb2)
        assert compare_slots(_sa2, _sb2)    # ★ 允许合并
    finally:
        _nx.ENABLE_CONDITION_NORMALIZATION = _old


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
