# -*- coding: utf-8 -*-
"""tests/fused/test_semantic_try_convert.py —— B-2（转换判定：证据层 → 可执行层）。

对应 docs/rfc_source_bcd_roadmap.md §3.8 任务表 **B-2** 行（:670）的验收标准：

  ① `try_convert` 实现 C1~C7 七步，**顺序为「先验证区间（C2）后判显式
     性（C3）」**；
  ② **每个 reject_reason 至少 1 个用例**（7 个 + `optional_modality` = 8 个）；
  ③ 单测：给一条 `evidence_kind="normative"` + 可验证 span + **MAY 动词**的
     规则 → 产出 `KnowledgeCandidate(reject_reason="optional_modality")`，
     **不得**产出 `ExecutableConstraint`；
  ④ 单测：区间故意改错 → `reject_reason="span_unverified"`（而非 explicit）。

另加两条**结构性/顺序**断言：

  ⑤ **顺序的显式证明**：造一个「span 不存在 **且** evidence_kind 是 prose
     （同时触发 C2 与 C3）」的用例 ⇒ 必须返回 **`span_unverified`**
     （C2 先命中）—— 这直接锁住问题⑧ 的顺序；
  ⑥ **MAY 不得产出 ExecutableConstraint**：在 ③ 的用例上额外断言
     `constraint is None`，且**不得**因为 MAY 就降级 evidence_kind
     （`evidence_kind` 仍是 `normative`）。

★ 本文件只测 `core/fused/semantic.py` 的 B-2 增量，不触碰任何既有生产链路。
"""
from __future__ import annotations

import dataclasses

import pytest

from core.fused.semantic import (
    EVIDENCE_KINDS,
    MODALITY_MANDATORY,
    MODALITY_NONE,
    MODALITY_OPTIONAL,
    MODALITY_RECOMMENDED,
    NORMATIVE_EVIDENCE_KINDS,
    OPERATORS,
    REJECT_REASONS,
    EvidenceAnchor,
    ExecutableConstraint,
    KnowledgeCandidate,
    compute_explicitness,
    convert_or_reject,
    detect_modality,
    load_source_text,
    parse_source_anchor,
    try_convert,
    try_convert_with_source,
)

#: 一个「合法」的规范性句子 + 它的逐字源文本。
_NORMATIVE_TEXT = "A client MUST send the Content-Length header."
_MAY_TEXT = "A client MAY send the Content-Length header."
_PROSE_TEXT = "The Content-Length header describes the size of the message."


# ---------------------------------------------------------------- 夹具


def _evidence(
    *,
    span_text: str = _NORMATIVE_TEXT,
    source_text: str = _NORMATIVE_TEXT,
    span_start: int = 0,
    span_end: int | None = None,
    evidence_kind: str = "normative",
    source_anchor: str = "file:rfc3261.txt#@1",
    explicitness: str = "explicit",
) -> EvidenceAnchor:
    """构造一条证据锚点（默认区间与源文本逐字一致 ⇒ C2 可通过）。"""
    end = len(source_text) if span_end is None else span_end
    return EvidenceAnchor(
        evidence_id="e0123456789ab",
        spec_version="RFC3261",
        section_path=("21", "1.1"),
        source_anchor=source_anchor,
        span_text=span_text,
        span_start=span_start,
        span_end=end,
        evidence_kind=evidence_kind,
        explicitness=explicitness,
        source_class="normative_spec",
    )


def _resolver(**overrides):
    """构造一个「合规」的 resolver（返回 C4~C7 都够用的完整解析结果）。"""
    result = {
        "operator": "le",
        "operand": ("70",),
        "operand_source": "constant",
        "operand_ref": None,
        "target_field": "Content-Length",
        "expected_behavior": "protocol_error",
    }
    result.update(overrides)
    return lambda span_text: dict(result)


#: 已知字段集 / 期望词表（与 `fused_hub/targets/*/rfc_config.json` 同形）
_KNOWN_FIELDS = ("Content-Length", "Max-Forwards", "Contact")
_EXPECTED_VOCAB = ("success", "protocol_error", "application_error", "silence")


# ============================================ ① 判定顺序：C2 先于 C3


def test_c2_precedes_c3_when_both_would_fail():
    """⑤ **顺序的显式证明**：span 不存在 **且** evidence_kind=prose
    （同时触发 C2 与 C3）⇒ 必须返回 `span_unverified`（C2 先命中）。

    ★ 这直接锁住问题⑧ 的顺序：先确认「这段原文确实是规范里那一句」，
      再判断「它算不算规范性证据」。反过来会把模型推断的规则错误提升为
      规范性强制要求。
    """
    ev = _evidence(
        span_text=_PROSE_TEXT,
        source_text=_NORMATIVE_TEXT,  # 区间对不上 ⇒ C2 失败
        evidence_kind="prose",  # 同时 C3 也会失败
    )
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "span_unverified"
    assert reason != "non_normative_kind"


def test_c3_hit_when_span_is_valid_but_kind_is_prose():
    """对照：C2 通过时，C3 才生效（evidence_kind=prose ⇒ non_normative_kind）。"""
    ev = _evidence(span_text=_PROSE_TEXT, source_text=_PROSE_TEXT,
                   evidence_kind="prose")
    constraint, reason = try_convert(
        ev,
        source_text=_PROSE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "non_normative_kind"


# ============================================ ② 8 个 reject_reason 各至少 1 例


def test_reject_reason_no_span():
    """② `no_span`：C1 —— 区间缺失（span_start/span_end/span_text 任一为空）。"""
    ev = _evidence()
    for broken in (
        dataclasses.replace(ev, span_start=None),
        dataclasses.replace(ev, span_end=None),
        dataclasses.replace(ev, span_text=""),
    ):
        constraint, reason = try_convert(
            broken,
            source_text=_NORMATIVE_TEXT,
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=_resolver(),
        )
        assert constraint is None
        assert reason == "no_span"


def test_reject_reason_span_unverified():
    """② `span_unverified`：C2 —— 区间在源文件中**逐字**对不上。"""
    ev = _evidence(span_text=_NORMATIVE_TEXT, source_text=_NORMATIVE_TEXT,
                   span_end=len(_NORMATIVE_TEXT))
    # 把 span_end 改小 ⇒ 取到的区间与 span_text 不一致
    broken = dataclasses.replace(ev, span_end=10)
    constraint, reason = try_convert(
        broken,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "span_unverified"


def test_reject_reason_span_unverified_when_source_text_missing():
    """② `span_unverified`：C2 —— `source_text` 缺省 ⇒ **无法核对即不通过**。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=None,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "span_unverified"


def test_reject_reason_non_normative_kind():
    """② `non_normative_kind`：C3 —— 证据类型不是 normative/abnf。"""
    for kind in ("table", "prose"):
        ev = _evidence(evidence_kind=kind)
        constraint, reason = try_convert(
            ev,
            source_text=_NORMATIVE_TEXT,
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=_resolver(),
        )
        assert constraint is None
        assert reason == "non_normative_kind"


def test_reject_reason_optional_modality():
    """② + ③ + ⑥ `optional_modality`：MAY/OPTIONAL 句不得产出可执行约束。

    ★ 位置在 C3 之后、C4 之前：先确认「它是规范性证据」，再看「动词强度
      是否只是 MAY/OPTIONAL」。
    ★ ⑥ 额外断言：**不得**因为 MAY 就降级 evidence_kind（仍是 `normative`）。
    """
    ev = _evidence(span_text=_MAY_TEXT, source_text=_MAY_TEXT)
    assert ev.evidence_kind == "normative"  # ⑥：evidence_kind 未被降级

    constraint, reason = try_convert(
        ev,
        source_text=_MAY_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None  # ⑥：不得产出 ExecutableConstraint
    assert reason == "optional_modality"


def test_reject_reason_operator_unresolved():
    """② `operator_unresolved`：C4 —— 无 resolver / 解析不出算子 / 算子词表外。"""
    ev = _evidence()
    # (a) 未注入 resolver
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
    )
    assert constraint is None
    assert reason == "operator_unresolved"

    # (b) resolver 返回 None
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=lambda t: None,
    )
    assert constraint is None
    assert reason == "operator_unresolved"

    # (c) resolver 返回词表外的算子 ⇒ 拒绝（**不默默接受**）
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(operator="matches_regex"),
    )
    assert constraint is None
    assert reason == "operator_unresolved"

    # (d) resolver 返回非 dict ⇒ 拒绝（不崩）
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=lambda t: ["not", "a", "dict"],
    )
    assert constraint is None
    assert reason == "operator_unresolved"


def test_reject_reason_operand_unresolved():
    """② `operand_unresolved`：C5 —— 解析不出 operand / operand_ref 不合法。"""
    ev = _evidence()
    for resolver in (
        _resolver(operand=()),  # 有参算子缺 operand
        _resolver(operand=None),
        _resolver(operand_source="field_ref", operand_ref=None),  # 缺 operand_ref
        _resolver(operand_source="constant", operand_ref="X"),  # constant 不得带 ref
        _resolver(operand_source="weird"),  # 非法 operand_source
        _resolver(operator="present", operand=("x",)),  # present 不得带 operand
    ):
        constraint, reason = try_convert(
            ev,
            source_text=_NORMATIVE_TEXT,
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=resolver,
        )
        assert constraint is None, resolver
        assert reason == "operand_unresolved", resolver


def test_reject_reason_field_unbound():
    """② `field_unbound`：C6 —— 字段绑定不上（**不做模糊匹配**）。"""
    ev = _evidence()
    # 规范化后**可以**绑上（下划线 vs 连字符 + 大小写差异）
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(target_field="Content_Length"),
    )
    assert reason is None
    assert constraint is not None

    # 相似但不同 ⇒ **绑不上**（模糊匹配是幻觉的主要来源）
    for unbound in ("Content-Length-Trailer", "X-Content-Length", "Length"):
        constraint, reason = try_convert(
            ev,
            source_text=_NORMATIVE_TEXT,
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=_resolver(target_field=unbound),
        )
        assert constraint is None, unbound
        assert reason == "field_unbound", unbound


def test_reject_reason_expectation_not_in_vocab():
    """② `expectation_not_in_vocab`：C7 —— 处理期望不在词表内。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(expected_behavior="teapot_error"),
    )
    assert constraint is None
    assert reason == "expectation_not_in_vocab"


def test_all_reject_reasons_are_covered_and_declared():
    """② 汇总：实现的 reject_reason 与 `REJECT_REASONS` 声明**精确一致**。

    ★ **B-5 扩展**：按 §3.5 层次2（单位归一）新增了第 9 个
      `non_length_operand` —— 秒级/未知计量单位**不可换算成字节**
      ⇒ 明确拒转换，不猜（B-5 的 `core/fused/semantic_rules.py` 触发）。
    ★ 断言仍是**精确集合**（新增必须同步登记），不是「包含即可」。
    """
    assert set(REJECT_REASONS) == {
        "no_span",
        "span_unverified",
        "non_normative_kind",
        "optional_modality",
        "operator_unresolved",
        "operand_unresolved",
        "non_length_operand",
        "field_unbound",
        "expectation_not_in_vocab",
    }
    assert len(REJECT_REASONS) == 9


# ============================================ ③ 全通过 ⇒ 产出 ExecutableConstraint


def test_all_checks_pass_produces_executable_constraint():
    """① C1~C7 全通过 ⇒ (constraint, None)，且字段与解析结果一致。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert reason is None
    assert isinstance(constraint, ExecutableConstraint)
    assert constraint.target_field == "Content-Length"
    assert constraint.operator == "le"
    assert constraint.operand == ("70",)
    assert constraint.operand_source == "constant"
    assert constraint.operand_ref is None
    assert constraint.expected_behavior == "protocol_error"
    assert constraint.sender_role == "client"
    assert constraint.receiver_role == "server"


def test_field_name_normalized_match_is_accepted():
    """C6：下划线/连字符、大小写差异应视为同一字段（规范化精确匹配）。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=("content-length", "max_forwards"),
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(target_field="Content_Length"),
    )
    assert reason is None
    assert constraint.target_field == "Content_Length"


def test_message_level_constraint_present_allowed():
    """C6：消息级约束（target_field=""）仅允许 present。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(operator="present", operand=(), target_field=""),
    )
    assert reason is None
    assert constraint.target_field == ""
    assert constraint.operator == "present"


def test_message_level_constraint_non_present_rejected():
    """C6：消息级约束（target_field=""）配非 present 算子 ⇒ 拒绝。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(target_field=""),
    )
    assert constraint is None
    assert reason == "field_unbound"


# ============================================ C7 的重要特例


def test_c7_missing_expectation_does_not_block_and_becomes_empty_string():
    """C7 特例：`expected_behavior` 缺失**不阻断**转换，且置为 `""`。

    ★ §3.4 行 528：缺 P（处理期望）时该规则**只能用于「构造违规种子」，
      不能用于「判定 oracle 预期」**。
    ★ 与 C 阶段 `close_loop(seed, result, expected=None)` 的
      「`expected=None` ⇒ 跳过语义偏离判定」**语义对齐**。
    """
    ev = _evidence()
    for missing in (None, ""):
        constraint, reason = try_convert(
            ev,
            source_text=_NORMATIVE_TEXT,
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=_resolver(expected_behavior=missing),
        )
        assert reason is None, missing
        assert constraint is not None
        assert constraint.expected_behavior == ""  # 不是 None、不是猜一个


def test_c7_empty_expected_behavior_ignores_vocab_membership():
    """C7 特例：`expected_behavior=""` ⇒ 不查词表（空值不在词表也算通过）。"""
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=(),  # 词表为空也不影响空期望
        resolver=_resolver(expected_behavior=""),
    )
    assert reason is None
    assert constraint.expected_behavior == ""


# ============================================ ④ 区间改错


def test_deliberately_wrong_span_yields_span_unverified_not_explicit():
    """④ 区间故意改错 ⇒ `span_unverified`（**而非** explicit/其它原因）。"""
    ev = _evidence()
    broken = dataclasses.replace(ev, span_start=5, span_end=20)
    constraint, reason = try_convert(
        broken,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "span_unverified"


def test_span_beyond_source_length_yields_span_unverified():
    """④ 区间越界（超出源文件长度）⇒ `span_unverified`。"""
    ev = _evidence()
    broken = dataclasses.replace(ev, span_start=9999, span_end=10050)
    constraint, reason = try_convert(
        broken,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "span_unverified"


def test_verbatim_comparison_is_byte_exact():
    """④ C2 的比对必须是**逐字**的：大小写/空白不同 ⇒ 不通过。"""
    ev = _evidence(span_text=_NORMATIVE_TEXT.upper())
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "span_unverified"


# ============================================ 规范性动词强度（§3.5 层次1 第3条）


def test_detect_modality_classification():
    """规范性动词 → 强度分类。"""
    assert detect_modality("A client MUST send X.") == MODALITY_MANDATORY
    assert detect_modality("A client SHALL send X.") == MODALITY_MANDATORY
    assert detect_modality("A client MUST NOT send X.") == MODALITY_MANDATORY
    assert detect_modality("A client REQUIRED to send X.") == MODALITY_MANDATORY
    assert detect_modality("A client SHOULD send X.") == MODALITY_RECOMMENDED
    assert detect_modality("A client RECOMMENDED to send X.") == MODALITY_RECOMMENDED
    assert detect_modality("A client MAY send X.") == MODALITY_OPTIONAL
    assert detect_modality("An OPTIONAL header may appear.") == MODALITY_OPTIONAL
    assert detect_modality("The server sends a reply.") == MODALITY_NONE


def test_detect_modality_takes_the_strongest_verb():
    """★ 强度取**最强命中**：句中同时有 MUST 与 MAY 时按 mandatory。

    理由（实测依据）：RFC 2119 术语声明句同时含 MUST/SHOULD/MAY/OPTIONAL
    全部关键字 —— 若按「先命中者」判定会被误判成 MAY 而错误丢弃。
    """
    boilerplate = (
        'The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", '
        '"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this '
        "document are to be interpreted as described in BCP 14."
    )
    assert detect_modality(boilerplate) == MODALITY_MANDATORY
    assert (
        detect_modality("Systems implementing RTSP MUST support TCP and MAY")
        == MODALITY_MANDATORY
    )


def test_detect_modality_respects_word_boundaries():
    """词边界：MAYBE / REQUIREDLY 之类不得误命中。"""
    assert detect_modality("The MAYBE clause is absent.") == MODALITY_NONE
    assert detect_modality("It is REQUIREDLY true.") == MODALITY_NONE


def test_optional_modality_rejects_even_when_everything_else_passes():
    """MAY 句即便其余判据全过，仍判 `optional_modality`。"""
    ev = _evidence(span_text=_MAY_TEXT, source_text=_MAY_TEXT)
    constraint, reason = try_convert(
        ev,
        source_text=_MAY_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert reason == "optional_modality"


# ============================================ 知识候选产物（强制机制 1）


def test_convert_or_reject_produces_knowledge_candidate_on_may():
    """③ 产物形态：MAY ⇒ `KnowledgeCandidate(reject_reason="optional_modality")`。

    ★ 该候选**没有** constraint 字段（强制机制 1）⇒ 结构上进不了生成链路。
    """
    cand = KnowledgeCandidate(
        candidate_id="c0001",
        evidence=_evidence(span_text=_MAY_TEXT, source_text=_MAY_TEXT),
        subject_type="header",
        subject_name="Content-Length",
        raw_text=_MAY_TEXT,
    )
    constraint, rejected = convert_or_reject(
        cand,
        source_text=_MAY_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert constraint is None
    assert isinstance(rejected, KnowledgeCandidate)
    assert rejected.reject_reason == "optional_modality"
    assert rejected.convertible is False
    assert hasattr(rejected, "constraint") is False


def test_convert_or_reject_returns_constraint_on_success():
    """产物形态：转换成功 ⇒ (constraint, None)。"""
    cand = KnowledgeCandidate(
        candidate_id="c0002",
        evidence=_evidence(),
        subject_type="header",
        subject_name="Content-Length",
        raw_text=_NORMATIVE_TEXT,
    )
    constraint, rejected = convert_or_reject(
        cand,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert isinstance(constraint, ExecutableConstraint)
    assert rejected is None


# ============================================ anchor 解析 / 源文件读取


def test_parse_source_anchor():
    """anchor 解析：文件名 + 1-based 行号；非数字行号 ⇒ None。"""
    assert parse_source_anchor("file:rfc3261.txt#@10560") == (
        "rfc3261.txt",
        10560,
    )
    assert parse_source_anchor("file:rfc3261.txt#@abnf") == ("rfc3261.txt", None)
    assert parse_source_anchor("file:rfc3261.txt") == ("rfc3261.txt", None)
    assert parse_source_anchor("") == (None, None)


def test_load_source_text_reads_kb_spec_file():
    """`load_source_text` 按 anchor 从 kb/<protocol>/spec/ 读源文件（只读）。"""
    text = load_source_text("sip", "file:rfc3261.txt#@1")
    assert text is not None
    assert "SIP" in text[:4000]
    # 不存在的文件 ⇒ None（⇒ C2 判 span_unverified）
    assert load_source_text("sip", "file:does_not_exist.txt#@1") is None
    assert load_source_text("sip", "") is None


def test_try_convert_with_source_auto_loads_source_text():
    """便捷封装：自动按 anchor 读源文件后再判定。

    ★ 用 **B-3 的真实候选**（真实 span + 真实 anchor）验证 C2 —— 这同时
      验证了「B-2 的逐字比对口径」与「B-3 的产出口径」**严丝合缝**。
    """
    from core.fused.rfc_extractor import extract_constraint_candidates

    candidates = extract_constraint_candidates("sip")
    assert candidates, "B-3 未产出候选"
    checked = 0
    for cand in candidates:
        ev = EvidenceAnchor(
            evidence_id="e0",
            spec_version=cand.get("spec_version") or "RFC3261",
            section_path=tuple(cand.get("section_path") or ()),
            source_anchor=cand["source"],
            span_text=cand["text"],
            span_start=cand["span_start"],
            span_end=cand["span_end"],
            evidence_kind="normative",
            explicitness="explicit",
            source_class="normative_spec",
        )
        constraint, reason = try_convert_with_source(
            ev,
            "sip",
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=_resolver(),
        )
        # 真实候选的 span 必定可在源文件中逐字核对 ⇒ C2 不得失败
        assert reason != "span_unverified", cand["source"]
        checked += 1
        if checked >= 40:
            break
    assert checked >= 40


def test_real_candidates_pass_c2_verbatim_check():
    """C2 的逐字判据对 **B-3 全部真实候选**成立（三协议实测 430/430）。"""
    from core.fused.rfc_extractor import extract_constraint_candidates

    from core import paths

    total = 0
    for proto in ("rtsp", "sip", "smtp"):
        spec = paths.kb_source_dir(proto, "rfc")
        for cand in extract_constraint_candidates(proto):
            fname = cand["source"].split("#@")[0].replace("file:", "")
            path = spec / fname
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            assert raw[cand["span_start"] : cand["span_end"]] == cand["text"]
            total += 1
    assert total == 430


# ============================================ explicitness 计算（§3.1 + §4 M4）


def test_compute_explicitness_respects_m4_purity():
    """M4（§4 行 955）：`explicit` 必须蕴含原文含 MUST/SHALL/REQUIRED。"""
    # 区间已校验 + 规范性证据 + 强制动词 ⇒ explicit
    assert (
        compute_explicitness(
            _NORMATIVE_TEXT, verified=True, evidence_kind="normative"
        )
        == "explicit"
    )
    # 区间不可核对 ⇒ 非 explicit
    assert (
        compute_explicitness(
            _NORMATIVE_TEXT, verified=False, evidence_kind="normative"
        )
        != "explicit"
    )
    # 非规范性证据 ⇒ 非 explicit
    assert (
        compute_explicitness(_NORMATIVE_TEXT, verified=True, evidence_kind="prose")
        != "explicit"
    )
    # SHOULD 句不含 MUST/SHALL/REQUIRED ⇒ 不得为 explicit（M4 纯净度）
    assert (
        compute_explicitness(
            "A client SHOULD send X.", verified=True, evidence_kind="normative"
        )
        != "explicit"
    )


def test_explicitness_values_are_within_declared_vocabulary():
    """explicitness 取值必须落在 `EXPLICITNESS` 词表内。"""
    from core.fused.semantic import EXPLICITNESS

    for text in (_NORMATIVE_TEXT, _MAY_TEXT, _PROSE_TEXT):
        for kind in ("normative", "abnf", "table", "prose"):
            for verified in (True, False):
                value = compute_explicitness(
                    text, verified=verified, evidence_kind=kind
                )
                assert value in EXPLICITNESS


# ============================================ 词表一致性


def test_normative_evidence_kinds_subset_of_evidence_kinds():
    """C3 的白名单必须是 `EVIDENCE_KINDS` 的子集。"""
    assert NORMATIVE_EVIDENCE_KINDS <= EVIDENCE_KINDS
    assert NORMATIVE_EVIDENCE_KINDS == frozenset({"normative", "abnf"})


def test_operators_wordlist_unchanged_by_b2():
    """B-2 增量**不得**改动 B-1 的算子词表。"""
    assert OPERATORS == frozenset(
        {"eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent", "range"}
    )


# ============================================ 纯函数性


def test_try_convert_is_pure_deterministic():
    """`try_convert` 是纯函数：同输入 → 同输出（可重复调用）。"""
    ev = _evidence()
    kwargs = dict(
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    results = [try_convert(ev, **kwargs) for _ in range(20)]
    assert len({repr(r) for r in results}) == 1
    assert results[0][1] is None


def test_try_convert_does_not_mutate_input():
    """`try_convert` **不修改**入参（frozen dataclass + 纯函数）。"""
    ev = _evidence()
    before = ev
    try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(),
    )
    assert ev == before


def test_try_convert_rejects_bad_candidate_type():
    """入参类型不对 ⇒ 明确 TypeError（不静默吞掉）。"""
    with pytest.raises(TypeError):
        try_convert("not an evidence anchor", source_text=_NORMATIVE_TEXT)


def test_set_operand_is_sorted_for_determinism():
    """集合型 operand 必须**排序**后使用 —— 否则顺序随 PYTHONHASHSEED 变化。

    ★ 这直接关系到「同输入同 rule_id」的确定性保证（operand 参与 rule_id 派生）。
    """
    ev = _evidence()
    constraint, reason = try_convert(
        ev,
        source_text=_NORMATIVE_TEXT,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_resolver(operator="in", operand={"b", "a", "c"}),
    )
    assert reason is None
    assert constraint.operand == ("a", "b", "c")
