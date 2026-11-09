# -*- coding: utf-8 -*-
"""tests/fused/test_semantic_rules.py —— B-5（operator/operand 模式表 + 字段绑定）。

对应 docs/实施/路线与里程碑/RFC源里程碑路线图.md §3.8 任务表 **B-5** 行（:673）的验收标准：

  ① **≥12 条有序模式**，每条配 **≥1 个最小可执行样例**单测；
     模式表是**可回归资产**。
  ② **动词 → evidence_kind / expected_behavior 可断言性**的映射正确，
     **MAY 必须落到候选**（`try_convert` 判 `optional_modality`）。
  ③ **单位归一**：`octets`/`bytes` → 字节；`bits` → 位；
     **`seconds` → 拒绝转换**（不可换算成字节）。
  ④ **字段绑定**：命中候选集 → 精确绑定；未命中 → `field_unbound`，
     **无模糊匹配**（相似但不同的字段名**必须绑不上**）。

另加：与 **B-2 resolver 契约**的接口一致性、模式表**有序性**、
**不发明处理期望**、**指数形式不猜**、真实候选上的**行为良好性**。

★ 本文件只测 `core/fused/semantic_rules.py`（+ B-2 的 `try_convert` 串联），
  不触碰任何既有生产链路。
"""
from __future__ import annotations

import pytest

from core.fused.semantic import (
    OPERATORS,
    REJECT_REASONS,
    EvidenceAnchor,
    ExecutableConstraint,
    normalize_field_name,
    try_convert,
)
from core.fused.semantic_rules import (
    LENGTH_UNITS,
    NON_LENGTH_UNITS,
    PATTERNS,
    bind_field,
    expectation_assertable,
    extract_field_clue,
    make_resolver,
    match_pattern,
    normalize_unit,
    resolve_evidence_kind,
)

#: 已知字段集（与 `fused_hub/targets/*/rfc_config.json` 同形）
_KNOWN_FIELDS = (
    "Content-Length",
    "Max-Forwards",
    "Contact",
    "CSeq",
    "Via",
    "Expires",
    "User-Agent",
    "Accept",
)

#: 期望响应词表
_EXPECTED_VOCAB = ("success", "protocol_error", "application_error", "silence")

#: **每条模式的最小可执行样例** —— 验收① 的核心资产。
#: 结构：模式名 → (样例句, 期望 operator, 期望 operand)
PATTERN_SAMPLES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # ── A 组：否定式 ⇒ 反向边界 ──
    "must_not_ge": ("MUST NOT be greater than or equal to 70", "lt", ("70",)),
    "must_not_le": ("MUST NOT be less than or equal to 70", "gt", ("70",)),
    "must_not_at_least": ("MUST NOT be at least 8", "lt", ("8",)),
    "must_not_at_most": ("MUST NOT be at most 8", "gt", ("8",)),
    "must_not_gt": ("MUST NOT be greater than 70", "le", ("70",)),
    "must_not_lt": ("MUST NOT be less than 70", "ge", ("70",)),
    "must_not_exceed": ("MUST NOT exceed 70", "le", ("70",)),
    "must_not_equal": ("MUST NOT be 70", "ne", ("70",)),
    # ── B 组：肯定式 ──
    "must_ge": ("MUST be at least 8", "ge", ("8",)),
    "must_le": ("MUST be no greater than 998", "le", ("998",)),
    "must_gt": ("MUST be greater than 70", "gt", ("70",)),
    "must_lt": ("MUST be less than 70", "lt", ("70",)),
    "must_eq": ("MUST be exactly 70", "eq", ("70",)),
    "must_range": ("MUST be between 1 and 31", "range", ("1", "31")),
    # ── C 组：无动词比较 ──
    "at_least": ("at least 8 octets", "ge", ("8",)),
    "at_most": ("at most 8 octets", "le", ("8",)),
    "no_more_than": ("no more than 8 octets", "le", ("8",)),
    "fewer_than": ("fewer than 8 octets", "lt", ("8",)),
    "more_than": ("more than 8 octets", "gt", ("8",)),
    "limited_to": ("limited to 8 octets", "le", ("8",)),
    "maximum_of": ("a maximum of 8 octets", "le", ("8",)),
    "minimum_of": ("a minimum of 8 octets", "ge", ("8",)),
    # ── D 组：集合 ──
    "one_of_braces": ("MUST be equal to {a, b, c}", "in", ("a", "b", "c")),
    "one_of_list": ("MUST be one of a, b, or c", "in", ("a", "b", "c")),
    # ── E 组：存在性 ──
    "must_not_be_present": ("MUST NOT be present", "absent", ()),
    "must_not_contain": ("MUST NOT include a Contact header", "absent", ()),
    "must_be_absent": ("MUST be absent", "absent", ()),
    "must_be_present": ("MUST be present", "present", ()),
    "must_contain": ("MUST contain a Contact header", "present", ()),
    # ── F 组：字段引用 ──
    "size_of": ("the size of the message body", "eq", ("message body",)),
    # ── G 组：ABNF ──
    "abnf_rule": ("Content-Length = 1*DIGIT", "present", ()),
}


# ============================================================ ① 模式表


def test_pattern_table_has_at_least_twelve_patterns():
    """① ≥12 条模式。"""
    assert len(PATTERNS) >= 12


def test_pattern_names_unique_and_metadata_valid():
    """① 模式名唯一；operator ∈ OPERATORS；kind ∈ 三档。"""
    names = [p.name for p in PATTERNS]
    assert len(names) == len(set(names))
    for p in PATTERNS:
        assert p.operator in OPERATORS, p.name
        assert p.kind in ("normative", "abnf", "prose"), p.name


def test_every_pattern_has_a_minimal_executable_sample():
    """① **每条**模式都有 ≥1 个最小可执行样例，且样例**命中的是它自己**。

    ★ 断言「命中的模式名 == 期望的模式名」⇒ 同时锁住了**有序性**：
      若前面的模式抢命中，这条用例立刻失败。
    """
    assert set(PATTERN_SAMPLES) == {p.name for p in PATTERNS}
    for name, (sentence, operator, operand) in PATTERN_SAMPLES.items():
        m = match_pattern(sentence)
        assert m is not None, name
        assert m.pattern.name == name, f"{name} 被 {m.pattern.name} 抢先命中"
        assert m.operator == operator, name
        assert m.operand == operand, name


@pytest.mark.parametrize("name", sorted(PATTERN_SAMPLES))
def test_each_pattern_sample_is_individually_executable(name):
    """① 逐条模式的最小可执行样例（单测粒度，便于回归定位）。"""
    sentence, operator, operand = PATTERN_SAMPLES[name]
    m = match_pattern(sentence)
    assert m is not None
    assert m.operator == operator
    assert m.operand == operand
    # 样例句必须能构造出合法的 ExecutableConstraint（B-1 的 6 条构造校验）
    if operator in ("present", "absent"):
        field = m.target_field or "Contact"
    else:
        field = m.target_field or "Content-Length"
    constraint = ExecutableConstraint(
        target_field=field,
        operator=m.operator,
        operand=m.operand,
        operand_source=m.operand_source,
        operand_ref=m.operand_ref,
        applies_to_state=(),
        applies_to_method=(),
        expected_behavior="",
        sender_role="client",
        receiver_role="server",
        precondition=None,
    )
    assert constraint.operator == operator


def test_patterns_are_ordered_must_not_beats_must():
    """① **有序**：否定式模式必须排在肯定式之前（MUST NOT 不能被 MUST 截胡）。"""
    names = [p.name for p in PATTERNS]
    assert names.index("must_not_exceed") < names.index("must_ge")
    assert names.index("must_not_contain") < names.index("must_contain")
    assert names.index("must_not_be_present") < names.index("must_be_present")


def test_ordering_or_equal_to_variant_comes_before_bare_than():
    """① 「or equal to」变体必须排在裸「than」变体之前（否则语义反了）。"""
    names = [p.name for p in PATTERNS]
    assert names.index("must_not_ge") < names.index("must_not_gt")
    assert names.index("must_ge") < names.index("must_gt")
    # 语义断言：greater than or equal to 70 ≠ greater than 70
    m = match_pattern("MUST NOT be greater than or equal to 70")
    assert m.operator == "lt"  # 不是 le


def test_no_greater_than_is_le_not_gt():
    """①「no greater than」⇒ `le`（不是 `gt`）—— 「no」不能被吞掉。"""
    m = match_pattern("MUST be no greater than 998")
    assert m.operator == "le"
    assert m.operand == ("998",)


def test_verb_free_patterns_come_after_verb_patterns():
    """① 无动词比较模式必须排在带动词模式之后（更具体的先命中）。"""
    names = [p.name for p in PATTERNS]
    assert names.index("must_ge") < names.index("at_least")
    assert names.index("must_le") < names.index("at_most")


# ================================================== ② 动词 → 可断言性 / kind


@pytest.mark.parametrize(
    "sentence,assertable",
    [
        ("Content-Length MUST be at least 8", True),
        ("Content-Length SHALL be at least 8", True),
        ("Content-Length REQUIRED to be at least 8", True),
        ("Content-Length SHOULD be at least 8", False),
        ("Content-Length RECOMMENDED to be at least 8", False),
        ("Content-Length MAY be at least 8", False),
        ("Content-Length OPTIONAL to be at least 8", False),
        ("Content-Length is at least 8", False),
    ],
)
def test_verb_to_expectation_assertability(sentence, assertable):
    """② 动词 → `expected_behavior` **可断言性**。"""
    assert expectation_assertable(sentence) is assertable


@pytest.mark.parametrize(
    "sentence,kind",
    [
        ("Content-Length MUST be at least 8", "normative"),
        ("Content-Length SHOULD be at least 8", "normative"),
        ("Content-Length MAY be at least 8", "normative"),
        ("Content-Length is at least 8", "prose"),
    ],
)
def test_verb_to_evidence_kind(sentence, kind):
    """② 动词 → `evidence_kind`（MUST/SHOULD/MAY → normative；无动词 → prose）。"""
    assert resolve_evidence_kind(sentence) == kind


def test_abnf_pattern_yields_abnf_kind():
    """② ABNF 语法行 ⇒ `evidence_kind="abnf"`。"""
    m = match_pattern("Content-Length = 1*DIGIT")
    assert m is not None
    assert m.kind == "abnf"


def test_may_lands_in_candidate_not_executable_constraint():
    """② **MAY 必须落到候选** —— `try_convert` 判 `optional_modality`，
    **不得**产出 `ExecutableConstraint`。"""
    sentence = "Content-Length MAY be at least 8"
    m = match_pattern(sentence)
    assert m is not None
    assert m.kind == "normative"  # ②：MAY 的 evidence_kind 仍是 normative
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=make_resolver(known_fields=_KNOWN_FIELDS),
    )
    assert constraint is None
    assert reason == "optional_modality"


def test_should_expectation_is_not_assertable_through_try_convert():
    """② SHOULD ⇒ 期望**不可断言**（`expected_behavior=""`）。"""
    sentence = "Content-Length SHOULD be at least 8"
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=make_resolver(known_fields=_KNOWN_FIELDS),
    )
    assert reason is None
    assert constraint is not None
    assert constraint.expected_behavior == ""


def test_must_expectation_is_assertable_through_try_convert():
    """② MUST ⇒ 期望**可断言**（调用方给的期望被保留）。"""
    sentence = "Content-Length MUST be at least 8"
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)

    def _with_expectation(text: str):
        out = dict(resolver(text) or {})
        out["expected_behavior"] = "protocol_error"
        return out

    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=_with_expectation,
    )
    assert reason is None
    assert constraint.expected_behavior == "protocol_error"


def test_prose_evidence_is_rejected_by_c3():
    """② 无规范动词 ⇒ kind="prose" ⇒ C3 判 `non_normative_kind`。"""
    sentence = "Content-Length is at least 8"
    m = match_pattern(sentence)
    assert m is not None and m.kind == "prose"
    constraint, reason = try_convert(
        _evidence(sentence, evidence_kind=m.kind),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=make_resolver(known_fields=_KNOWN_FIELDS),
    )
    assert constraint is None
    assert reason == "non_normative_kind"


# ============================================================ ③ 单位归一


@pytest.mark.parametrize(
    "word,expected",
    [
        ("octets", "byte"),
        ("octet", "byte"),
        ("bytes", "byte"),
        ("byte", "byte"),
        ("bits", "bit"),
        ("bit", "bit"),
        ("characters", "char"),
        ("chars", "char"),
    ],
)
def test_length_units_normalized(word, expected):
    """③ `octets`/`bytes` → 字节；`bits` → 位（**不与字节混算**）。"""
    assert normalize_unit(word) == expected


def test_octets_and_bytes_normalize_to_the_same_unit():
    """③ `octets` 与 `bytes` 归一到**同一**单位（字节）。"""
    assert normalize_unit("octets") == normalize_unit("bytes") == "byte"
    assert normalize_unit("bits") != normalize_unit("bytes")


def test_seconds_is_rejected_not_converted():
    """③ **`seconds` → 拒绝转换**（不可换算成字节）。"""
    assert "seconds" in NON_LENGTH_UNITS
    assert normalize_unit("seconds") == "__reject__"


def test_seconds_constraint_is_rejected_end_to_end():
    """③ 秒级约束端到端 ⇒ `reject_reason="non_length_operand"`，**不产出约束**。"""
    sentence = "The timeout MUST be less than 30 seconds"
    m = match_pattern(sentence)
    assert m is not None
    assert m.reject_reason == "non_length_operand"
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=make_resolver(known_fields=_KNOWN_FIELDS),
    )
    assert constraint is None
    assert reason == "non_length_operand"
    assert "non_length_operand" in REJECT_REASONS


def test_unknown_measure_unit_is_rejected_not_guessed():
    """③ **单位不认识 → 拒绝转换，不猜**（"70 hops" 不是字节长度）。"""
    assert normalize_unit("hops") == "__reject__"
    sentence = "A client MUST NOT exceed 70 hops"
    m = match_pattern(sentence)
    assert m is not None
    assert m.reject_reason == "non_length_operand"


def test_non_plural_trailing_word_is_not_treated_as_unit():
    """③ 非计量词（如 "Not"）**不当单位** —— 纯数值比较。"""
    assert normalize_unit("Not") is None
    assert normalize_unit(None) is None


def test_unit_captured_in_match_result():
    """③ 匹配结果携带归一后的单位。"""
    m = match_pattern("MUST be at least 8 octets")
    assert m is not None
    assert m.unit == "byte"
    m = match_pattern("MUST be at least 8 bits")
    assert m is not None
    assert m.unit == "bit"


def test_word_numbers_are_normalized_to_digits():
    """③ 英文数字归一（"at least eight octets" → 8）。"""
    m = match_pattern("randomly and MUST be at least eight octets long")
    assert m is not None
    assert m.operand == ("8",)
    assert m.unit == "byte"


def test_exponent_form_is_not_matched_rather_than_wrong_operand():
    """③ 指数形式（"less than 2**31"）**不匹配** —— 宁可不匹配，也不产出错值。"""
    m = match_pattern("the value MUST be less than 2**31")
    assert m is None


# ============================================================ ④ 字段绑定


def test_bind_field_exact_match():
    """④ 精确绑定。"""
    assert bind_field("Content-Length", _KNOWN_FIELDS) == "Content-Length"
    assert bind_field("Contact", _KNOWN_FIELDS) == "Contact"


def test_bind_field_normalized_match():
    """④ 规范化匹配（大小写 + 下划线/连字符）。"""
    assert bind_field("content-length", _KNOWN_FIELDS) == "Content-Length"
    assert bind_field("CONTENT_LENGTH", _KNOWN_FIELDS) == "Content-Length"
    assert bind_field("Content_Length", _KNOWN_FIELDS) == "Content-Length"


@pytest.mark.parametrize(
    "clue",
    [
        "Content-Lenght",  # 拼写错误
        "Content-Length-Trailer",  # 相似但更长
        "X-Content-Length",
        "Content",
        "Length",
        "contentlength",
        "Contact2",
    ],
)
def test_similar_but_different_field_must_not_bind(clue):
    """④ **相似但不同的字段名必须绑不上**（无模糊匹配）。"""
    assert bind_field(clue, _KNOWN_FIELDS) is None


def test_similar_but_different_field_yields_field_unbound_end_to_end():
    """④ 端到端：绑不上 ⇒ `field_unbound`（不是别的原因）。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    sentence = "Content-Lenght MUST be at least 8"
    # 线索抽到 "Content-Lenght" ⇒ 绑不上 ⇒ target_field 置空
    out = resolver(sentence)
    assert out is not None
    assert out["target_field"] == ""
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=resolver,
    )
    assert constraint is None
    assert reason == "field_unbound"


def test_known_field_binds_end_to_end():
    """④ 端到端：已知字段 ⇒ 绑定成功 ⇒ 产出可执行约束。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    sentence = "Content-Length MUST be at least 8"
    out = resolver(sentence)
    assert out is not None
    assert out["target_field"] == "Content-Length"
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=resolver,
    )
    assert reason is None
    assert isinstance(constraint, ExecutableConstraint)
    assert constraint.target_field == "Content-Length"
    assert constraint.operator == "ge"
    assert constraint.operand == ("8",)


def test_extract_field_clue_prefers_header_noun():
    """④ 字段线索优先取 `<Token> header|field` 形式。"""
    assert extract_field_clue("a Contact header field MUST be present") == "Contact"
    assert extract_field_clue("the Content-Length header MUST be present") == (
        "Content-Length"
    )


def test_extract_field_clue_uses_subject_position():
    """④ 字段线索取动词主语位（排除句首常见词）。"""
    assert extract_field_clue("Content-Length MUST be at least 8") == "Content-Length"
    # "The client MUST ..." 的 "The" 不是字段
    assert extract_field_clue("The client MUST send the request") is None


def test_normalize_field_name_is_shared_with_c6():
    """④ 字段绑定与 C6 **同口径**（复用同一个公共函数）。"""
    assert normalize_field_name("Content_Length") == "content-length"
    assert bind_field("Content_Length", ["content-length"]) == "content-length"


# ============================================ 与 B-2 resolver 契约的一致性


def test_resolver_returns_exactly_the_contract_keys():
    """resolver 契约：返回的 dict 键必须是 B-2 文档里列的那几个。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    out = resolver("Content-Length MUST be at least 8")
    assert out is not None
    allowed = {
        "operator",
        "operand",
        "operand_source",
        "operand_ref",
        "target_field",
        "expected_behavior",
        "applies_to_state",
        "applies_to_method",
        "sender_role",
        "receiver_role",
        "precondition",
        "reject_reason",
    }
    assert set(out) <= allowed


def test_resolver_never_invents_expected_behavior():
    """★ 模式表**不发明处理期望**（C/P 分离）—— 一律返回 `""`。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    for sentence, _, _ in PATTERN_SAMPLES.values():
        out = resolver(sentence)
        if out is not None:
            assert out["expected_behavior"] == ""


def test_resolver_returns_none_for_unmatched_text():
    """未命中 ⇒ `None` ⇒ B-2 的 C4 判 `operator_unresolved`。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    sentence = "The server responds with an error."
    assert resolver(sentence) is None
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=resolver,
    )
    assert constraint is None
    assert reason == "operator_unresolved"


def test_unmatched_may_sentence_hits_optional_modality_before_c4():
    """★ 顺序的又一处体现：含 "may" 但**模式未命中**的句子 ⇒ C4 之前
    先被 `optional_modality` 拦下（optional_modality 位于 C3 之后、C4 之前）。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    sentence = "The server may respond with an error."
    assert resolver(sentence) is None
    constraint, reason = try_convert(
        _evidence(sentence),
        source_text=sentence,
        known_fields=_KNOWN_FIELDS,
        expected_vocab=_EXPECTED_VOCAB,
        resolver=resolver,
    )
    assert constraint is None
    assert reason == "optional_modality"


def test_every_matched_pattern_yields_a_valid_constraint_or_a_clean_reject():
    """★ 端到端不变量：每条样例经 `try_convert` 后，要么产出**合法**约束、
    要么判一个**已登记**的 reject_reason —— 绝不抛异常、绝不产出非法约束。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    for name, (sentence, _, _) in PATTERN_SAMPLES.items():
        constraint, reason = try_convert(
            _evidence(sentence),
            source_text=sentence,
            known_fields=_KNOWN_FIELDS,
            expected_vocab=_EXPECTED_VOCAB,
            resolver=resolver,
        )
        if constraint is not None:
            assert reason is None, name
            assert isinstance(constraint, ExecutableConstraint)
        else:
            assert reason in REJECT_REASONS, name


def test_pattern_table_is_deterministic():
    """★ 模式表是**可回归资产** —— 同输入必得同输出。"""
    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    for sentence, _, _ in PATTERN_SAMPLES.values():
        results = {repr(resolver(sentence)) for _ in range(10)}
        assert len(results) == 1, sentence


# ============================================================ 结构性护栏


def test_pattern_table_lives_in_semantic_rules_not_semantic():
    """★ 模式表是**独立资产**（§3.7）：`semantic.py` 里不得有 operator 正则。"""
    import core.fused.semantic as semantic_mod

    # 模式表（类型 + 入口 + 匹配函数）**只在** semantic_rules.py 里
    for name in ("PATTERNS", "RulePattern", "PatternMatch", "match_pattern"):
        assert not hasattr(semantic_mod, name), name


def test_length_units_and_non_length_units_are_disjoint():
    """单位表本身不得自相矛盾。"""
    assert not (set(LENGTH_UNITS) & NON_LENGTH_UNITS)


def test_real_candidates_produce_wellformed_results():
    """★ 真实候选上的**行为良好性**：命中必产出合法形状，绝不抛异常。

    （B-3 的真实候选（数量随 engineer-13 的粒度修正变动，实测 430 → 421）
    是模式表的真实输入面 —— 这里保证「不崩、
    不产出畸形结果」，不断言召回率。）
    """
    from core.fused.rfc_extractor import extract_constraint_candidates

    resolver = make_resolver(known_fields=_KNOWN_FIELDS)
    checked = 0
    for proto in ("rtsp", "sip", "smtp"):
        for cand in extract_constraint_candidates(proto):
            out = resolver(cand["text"])
            if out is None:
                continue
            checked += 1
            assert out["operator"] in OPERATORS
            assert isinstance(out["operand"], list)
            assert out["expected_behavior"] == ""
            if out["operator"] in ("present", "absent"):
                assert out["operand"] == []
    assert checked > 0


# ---------------------------------------------------------------- 夹具


def _evidence(sentence: str, evidence_kind: str = "normative") -> EvidenceAnchor:
    """构造一条与 `sentence` 逐字一致的证据锚点（C2 可通过）。"""
    return EvidenceAnchor(
        evidence_id="e0123456789ab",
        spec_version="RFC3261",
        section_path=("21", "1.1"),
        source_anchor="file:rfc3261.txt#@1",
        span_text=sentence,
        span_start=0,
        span_end=len(sentence),
        evidence_kind=evidence_kind,
        explicitness="explicit",
        source_class="normative_spec",
    )
