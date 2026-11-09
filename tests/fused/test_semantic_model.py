# -*- coding: utf-8 -*-
"""tests/fused/test_semantic_model.py —— B-1（两层语义模型 + `rule_id` 派生）。

对应 docs/实施/路线与里程碑/RFC源里程碑路线图.md §3.8 任务表 **B-1** 行（:669）的验收标准：

  ① 四个 dataclass 定义齐全，字段与 §3.1 **逐项一致**；
  ② `ExecutableConstraint.__post_init__` 的 **6 条校验各有 1 个正例 + 1 个反例**
     单测（共 12 个用例）；
  ③ `compute_rule_id` 对**同一结构化身份**重复调用 100 次得**同一 id**；
     对 `operator` / `operand` / `section_path` **任一变更**得**不同 id**；
  ④ `compute_rule_id` 的输入**不含** `span_text` / `span_start` / LLM 输出顺序
     —— 单测断言「仅改 span_text → id 不变」。

另加两条**结构性**断言（B 阶段地基的前置证明）：

  ⑤ `SemanticRule` 上**没有** `model_id` 属性（D 阶段「模型身份不污染规范规则」）；
  ⑥ `KnowledgeCandidate` 上**没有** `constraint` 属性（「不可转换者不进生成链路」）。

★ 本文件**只测新模块** `core.fused.semantic`，不触碰任何既有生产链路。
"""
from __future__ import annotations

import dataclasses
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.fused.semantic import (
    EVIDENCE_KINDS,
    EXPLICITNESS,
    OPERATORS,
    RULE_STATES,
    SOURCE_CLASSES,
    EvidenceAnchor,
    ExecutableConstraint,
    KnowledgeCandidate,
    SemanticRule,
    compute_evidence_id,
    compute_rule_id,
)

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- 通用夹具


def _constraint_kwargs(**overrides):
    """构造一个**合法**的 `ExecutableConstraint` kwargs 基线。

    基线本身满足全部 6 条校验 ⇒ 任何单条校验的反例只需改动它对应的那一个维度。
    """
    kwargs = dict(
        target_field="Max-Forwards",
        operator="le",
        operand=("70",),
        operand_source="constant",
        operand_ref=None,
        applies_to_state=(),
        applies_to_method=(),
        expected_behavior="protocol_error",
        sender_role="client",
        receiver_role="server",
        precondition=None,
    )
    kwargs.update(overrides)
    return kwargs


def _evidence(**overrides):
    """构造一个合法的 `EvidenceAnchor`。"""
    kwargs = dict(
        evidence_id="e0123456789ab",
        spec_version="RFC3261",
        section_path=("21", "1.1"),
        source_anchor="file:rfc3261.txt#@10560",
        span_text="A proxy MUST NOT forward a request more than 70 times.",
        span_start=10560,
        span_end=10609,
        evidence_kind="normative",
        explicitness="explicit",
        source_class="normative_spec",
    )
    kwargs.update(overrides)
    return EvidenceAnchor(**kwargs)


def _rule(**overrides):
    """构造一个合法的 `SemanticRule`。"""
    kwargs = dict(
        rule_id="r0123456789abcdef",
        evidence=_evidence(),
        constraint=ExecutableConstraint(**_constraint_kwargs()),
        subject_type="header",
        subject_name="Max-Forwards",
        rule_state="authoritative",
        supersedes=(),
        model_confidence=0.91,
        validated=True,
    )
    kwargs.update(overrides)
    return SemanticRule(**kwargs)


# ---------------------------------------------- ① 四个 dataclass 字段逐项一致


def test_dataclasses_defined_and_frozen():
    """① 四个 dataclass 齐全，且都是 frozen（两层之间不共享可变状态）。"""
    for cls in (EvidenceAnchor, ExecutableConstraint, SemanticRule, KnowledgeCandidate):
        assert dataclasses.is_dataclass(cls), f"{cls.__name__} 不是 dataclass"
        assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} 未 frozen"


def test_evidence_anchor_fields_match_design():
    """① `EvidenceAnchor` 字段与 §3.1 逐项一致（顺序 + 名称）。

    ★ §3.1 明确：**不含 rule_id**（审计 I-1：规则身份挂在证据层会导致
      「一条规则多条证据时 id 漂移」）。
    """
    assert tuple(f.name for f in dataclasses.fields(EvidenceAnchor)) == (
        "evidence_id",
        "spec_version",
        "section_path",
        "source_anchor",
        "span_text",
        "span_start",
        "span_end",
        "evidence_kind",
        "explicitness",
        "source_class",
    )
    assert "rule_id" not in {f.name for f in dataclasses.fields(EvidenceAnchor)}


def test_executable_constraint_fields_match_design():
    """① `ExecutableConstraint` 字段与 §3.1 逐项一致。"""
    assert tuple(f.name for f in dataclasses.fields(ExecutableConstraint)) == (
        "target_field",
        "operator",
        "operand",
        "operand_source",
        "operand_ref",
        "applies_to_state",
        "applies_to_method",
        "expected_behavior",
        "sender_role",
        "receiver_role",
        "precondition",
    )


def test_semantic_rule_fields_match_design():
    """① `SemanticRule` 字段与 §3.1 逐项一致（`rule_id` 在**顶层**）。"""
    assert tuple(f.name for f in dataclasses.fields(SemanticRule)) == (
        "rule_id",
        "evidence",
        "constraint",
        "subject_type",
        "subject_name",
        "rule_state",
        "supersedes",
        "model_confidence",
        "validated",
    )


def test_knowledge_candidate_fields_match_design():
    """① `KnowledgeCandidate` 字段与 §3.1 逐项一致。

    ★ §3.1 明确：它**没有** `constraint` 字段 —— 结构上就装不下 operator/operand。
    """
    assert tuple(f.name for f in dataclasses.fields(KnowledgeCandidate)) == (
        "candidate_id",
        "evidence",
        "subject_type",
        "subject_name",
        "raw_text",
        "convertible",
        "reject_reason",
    )


def test_constants_are_frozensets_with_expected_members():
    """5 个常量 frozenset 齐全，成员与 §3.1 一致。"""
    assert isinstance(SOURCE_CLASSES, frozenset)
    assert SOURCE_CLASSES == frozenset(
        {"normative_spec", "observation", "model_inference", "human"}
    )
    assert isinstance(EVIDENCE_KINDS, frozenset)
    assert EVIDENCE_KINDS == frozenset({"normative", "abnf", "table", "prose"})
    assert isinstance(EXPLICITNESS, frozenset)
    assert EXPLICITNESS == frozenset({"explicit", "quoted", "paraphrased"})
    assert isinstance(OPERATORS, frozenset)
    assert OPERATORS == frozenset(
        {"eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent", "range"}
    )
    assert isinstance(RULE_STATES, frozenset)
    assert RULE_STATES == frozenset(
        {"authoritative", "candidate", "revoked", "feedback"}
    )


# ------------------------- ② 6 条构造校验：每条各 1 正例 + 1 反例（共 12 例）


def test_check1_operator_in_vocab_positive():
    """② 校验① 正例：operator ∈ OPERATORS → 构造成功。"""
    c = ExecutableConstraint(**_constraint_kwargs(operator="le"))
    assert c.operator == "le"


def test_check1_operator_in_vocab_negative():
    """② 校验① 反例：operator ∉ OPERATORS → ValueError。"""
    with pytest.raises(ValueError, match="非法 operator"):
        ExecutableConstraint(**_constraint_kwargs(operator="BAD"))


def test_check2_no_arg_operator_rejects_operand_positive():
    """② 校验② 正例：无参算子 present + 空 operand → 构造成功。"""
    c = ExecutableConstraint(
        **_constraint_kwargs(operator="present", operand=())
    )
    assert c.operator == "present"
    assert c.operand == ()


def test_check2_no_arg_operator_rejects_operand_negative():
    """② 校验② 反例：present 不得带 operand → ValueError。"""
    with pytest.raises(ValueError, match="不得带 operand"):
        ExecutableConstraint(
            **_constraint_kwargs(operator="present", operand=("x",))
        )


def test_check3_arg_operator_requires_operand_positive():
    """② 校验③ 正例：有参算子 eq + 非空 operand → 构造成功。"""
    c = ExecutableConstraint(**_constraint_kwargs(operator="eq", operand=("x",)))
    assert c.operand == ("x",)


def test_check3_arg_operator_requires_operand_negative():
    """② 校验③ 反例：有参算子 eq 缺 operand → ValueError。"""
    with pytest.raises(ValueError, match="必须带 operand"):
        ExecutableConstraint(**_constraint_kwargs(operator="eq", operand=()))


def test_check4_field_ref_requires_operand_ref_positive():
    """② 校验④ 正例：operand_source=field_ref 且给了 operand_ref → 构造成功。"""
    c = ExecutableConstraint(
        **_constraint_kwargs(
            operand_source="field_ref", operand_ref="CSeq.number"
        )
    )
    assert c.operand_ref == "CSeq.number"


def test_check4_field_ref_requires_operand_ref_negative():
    """② 校验④ 反例：operand_source=field_ref 缺 operand_ref → ValueError。"""
    with pytest.raises(ValueError, match="field_ref 必须给 operand_ref"):
        ExecutableConstraint(
            **_constraint_kwargs(operand_source="field_ref", operand_ref=None)
        )


def test_check5_constant_forbids_operand_ref_positive():
    """② 校验⑤ 正例：operand_source=constant 且无 operand_ref → 构造成功。"""
    c = ExecutableConstraint(
        **_constraint_kwargs(operand_source="constant", operand_ref=None)
    )
    assert c.operand_ref is None


def test_check5_constant_forbids_operand_ref_negative():
    """② 校验⑤ 反例：operand_source=constant 却给了 operand_ref → ValueError。"""
    with pytest.raises(ValueError, match="constant 不得给 operand_ref"):
        ExecutableConstraint(
            **_constraint_kwargs(operand_source="constant", operand_ref="r")
        )


def test_check6_empty_target_field_only_present_positive():
    """② 校验⑥ 正例：target_field 为空 + present（消息级约束）→ 构造成功。"""
    c = ExecutableConstraint(
        **_constraint_kwargs(target_field="", operator="present", operand=())
    )
    assert c.target_field == ""
    assert c.operator == "present"


def test_check6_empty_target_field_only_present_negative():
    """② 校验⑥ 反例：target_field 为空 + 非 present → ValueError。"""
    with pytest.raises(ValueError, match="target_field 为空时仅允许 present"):
        ExecutableConstraint(
            **_constraint_kwargs(target_field="", operator="eq", operand=("x",))
        )


def test_all_six_validations_actually_raise():
    """② 汇总：6 条校验**真的会抛 ValueError**（不得被弱化成告警/静默降级）。

    每条独立构造一条「只违反这一条」的参数，与上面的 12 个用例互为备份。
    """
    cases = [
        ("非法 operator", dict(operator="BAD")),
        ("present 带 operand", dict(operator="present", operand=("x",))),
        ("有参算子缺 operand", dict(operator="eq", operand=())),
        ("field_ref 缺 operand_ref", dict(operand_source="field_ref", operand_ref=None)),
        ("constant 带 operand_ref", dict(operand_source="constant", operand_ref="r")),
        ("空 target_field 用非 present", dict(target_field="", operator="eq", operand=("x",))),
    ]
    assert len(cases) == 6
    for label, override in cases:
        with pytest.raises(ValueError):
            ExecutableConstraint(**_constraint_kwargs(**override)), label


# ------------------------------------------------ ③ compute_rule_id 的确定性


_BASE_IDENTITY = dict(
    protocol="sip",
    spec_version="RFC3261",
    section_path=("21", "1.1"),
    subject_type="header",
    subject_name="Max-Forwards",
    operator="le",
    operand=("70",),
    operand_ref=None,
    expected_behavior="protocol_error",
)


def test_compute_rule_id_is_stable_across_100_calls():
    """③ 同一结构化身份重复调用 100 次 → 同一个 id。"""
    ids = {compute_rule_id(**_BASE_IDENTITY) for _ in range(100)}
    assert len(ids) == 1
    assert next(iter(ids)).startswith("r")


@pytest.mark.parametrize(
    "field,changed_value",
    [
        ("operator", "gt"),
        ("operand", ("71",)),
        ("section_path", ("21", "1.2")),
    ],
)
def test_compute_rule_id_changes_with_structured_field(field, changed_value):
    """③ `operator` / `operand` / `section_path` 任一变更 → 不同 id。"""
    base = compute_rule_id(**_BASE_IDENTITY)
    mutated = dict(_BASE_IDENTITY)
    mutated[field] = changed_value
    assert compute_rule_id(**mutated) != base


def test_compute_rule_id_format():
    """③ rule_id 形如 "r" + sha256 前 16 位十六进制。"""
    rid = compute_rule_id(**_BASE_IDENTITY)
    assert len(rid) == 17
    assert rid[0] == "r"
    assert all(ch in "0123456789abcdef" for ch in rid[1:])


def test_compute_rule_id_differs_across_protocol_and_version():
    """③ 协议 / 规范版本不同 → 不同 id（M1 版本隔离）。"""
    base = compute_rule_id(**_BASE_IDENTITY)
    for key, value in (("protocol", "rtsp"), ("spec_version", "RFC2543")):
        mutated = dict(_BASE_IDENTITY)
        mutated[key] = value
        assert compute_rule_id(**mutated) != base


def test_compute_rule_id_is_stable_across_processes():
    """③ 跨进程（不同 PYTHONHASHSEED）稳定 —— 不用 Python `hash()`。"""
    code = (
        "import sys; sys.path.insert(0, %r);"
        "from core.fused.semantic import compute_rule_id;"
        "print(compute_rule_id(**%r))" % (str(ROOT), _BASE_IDENTITY)
    )
    outs = []
    for seed in ("0", "1", "12345"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(ROOT)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout.strip())
    assert len(set(outs)) == 1
    assert outs[0] == compute_rule_id(**_BASE_IDENTITY)


# ------------------------------- ④ rule_id 的输入不含 span / 自由文本 / 顺序


def test_compute_rule_id_signature_excludes_span_and_free_text():
    """④ `compute_rule_id` 的入参**只有** 9 个结构化字段。

    ★ `span_text` / `span_start` / `span_end` / 任何自由文本字段**不得出现**。
    """
    params = tuple(inspect.signature(compute_rule_id).parameters)
    assert params == (
        "protocol",
        "spec_version",
        "section_path",
        "subject_type",
        "subject_name",
        "operator",
        "operand",
        "operand_ref",
        "expected_behavior",
    )
    for forbidden in ("span_text", "span_start", "span_end", "raw_text"):
        assert forbidden not in params


def test_compute_rule_id_unchanged_when_only_span_text_changes():
    """④ 仅改 span_text → id 不变（措辞微调 / LLM 改写不产生新规则身份）。"""
    ev_a = _evidence(span_text="A proxy MUST NOT forward a request more than 70 times.")
    ev_b = _evidence(span_text="Proxies MUST NOT forward requests over 70 hops.")
    assert ev_a.span_text != ev_b.span_text

    def _rule_id_from(ev: EvidenceAnchor) -> str:
        return compute_rule_id(
            protocol="sip",
            spec_version=ev.spec_version,
            section_path=ev.section_path,
            subject_type="header",
            subject_name="Max-Forwards",
            operator="le",
            operand=("70",),
            operand_ref=None,
            expected_behavior="protocol_error",
        )

    assert _rule_id_from(ev_a) == _rule_id_from(ev_b)


def test_compute_rule_id_unchanged_when_only_span_offsets_change():
    """④ 仅改 span_start / span_end → id 不变（证据位置不参与规则身份）。"""
    ev_a = _evidence(span_start=10560, span_end=10609)
    ev_b = _evidence(span_start=999, span_end=1234)
    base = compute_rule_id(**_BASE_IDENTITY)
    for ev in (ev_a, ev_b):
        mutated = dict(_BASE_IDENTITY)
        mutated["spec_version"] = ev.spec_version
        mutated["section_path"] = ev.section_path
        assert compute_rule_id(**mutated) == base


def test_compute_rule_id_independent_of_llm_output_order():
    """④ LLM 输出顺序不影响 id —— 打乱候选顺序后 id 集合不变。"""
    cands = [
        ("header", "Max-Forwards", "le", ("70",)),
        ("header", "Contact", "present", ()),
        ("method", "REGISTER", "eq", ("REGISTER",)),
    ]
    forward = {
        compute_rule_id(
            protocol="sip",
            spec_version="RFC3261",
            section_path=("21", "1.1"),
            subject_type=st,
            subject_name=sn,
            operator=op,
            operand=od,
            operand_ref=None,
            expected_behavior="protocol_error",
        )
        for st, sn, op, od in cands
    }
    backward = {
        compute_rule_id(
            protocol="sip",
            spec_version="RFC3261",
            section_path=("21", "1.1"),
            subject_type=st,
            subject_name=sn,
            operator=op,
            operand=od,
            operand_ref=None,
            expected_behavior="protocol_error",
        )
        for st, sn, op, od in reversed(cands)
    }
    assert forward == backward
    assert len(forward) == 3


# ------------------------------------------------- compute_evidence_id 的行为


def test_compute_evidence_id_is_stable_and_distinguishes_anchors():
    """evidence_id = f(rule_id, source_anchor, span_start) 的确定性派生。"""
    rid = "r0123456789abcdef"
    e1 = compute_evidence_id(rid, "file:rfc3261.txt#@10560", 10560)
    e2 = compute_evidence_id(rid, "file:rfc3261.txt#@10560", 10560)
    e3 = compute_evidence_id(rid, "file:rfc3261.txt#@10700", 10700)
    e4 = compute_evidence_id("rffffffffffffffff", "file:rfc3261.txt#@10560", 10560)
    assert e1 == e2  # 幂等
    assert e1 != e3  # 同规则不同证据 → 不同 id
    assert e1 != e4  # 不同规则 → 不同 id
    assert e1.startswith("e")
    assert len(e1) == 13  # "e" + sha256 前 12 位


def test_compute_evidence_id_accepts_none_span_start():
    """span_start 允许 None（无 offset 的证据也要有稳定 id）。"""
    e = compute_evidence_id("r0123456789abcdef", "file:rfc3261.txt#@10560", None)
    assert e.startswith("e") and len(e) == 13


# --------------------- ⑤⑥ 结构性保证：模型身份不污染规则 / 候选不装约束


def test_semantic_rule_has_no_model_id_attribute():
    """⑤ `SemanticRule` 上**没有** `model_id` 属性（D 阶段的前置证明）。

    ★ 模型置信度只经 `model_confidence` 记录，**不污染规范规则的身份字段**。
    """
    rule = _rule()
    assert hasattr(rule, "model_id") is False
    assert "model_id" not in {f.name for f in dataclasses.fields(SemanticRule)}
    # 模型身份确实只以「置信度」形式存在，且与 explicitness/validated 分开
    assert rule.model_confidence == 0.91
    assert rule.evidence.explicitness == "explicit"
    assert rule.validated is True


def test_knowledge_candidate_has_no_constraint_attribute():
    """⑥ `KnowledgeCandidate` 上**没有** `constraint` 属性（强制机制 1）。

    ★ 「不可转换者不进自动生成链路」的结构性保证：候选**物理上装不下**
      operator/operand，任何「把候选当规则用」的代码在属性访问时即失败。
    """
    cand = KnowledgeCandidate(
        candidate_id="c0001",
        evidence=_evidence(),
        subject_type="header",
        subject_name="Max-Forwards",
        raw_text="proxies should generally limit forwarding hops",
    )
    assert hasattr(cand, "constraint") is False
    assert "constraint" not in {f.name for f in dataclasses.fields(KnowledgeCandidate)}
    assert cand.convertible is False
    assert cand.reject_reason is None


def test_knowledge_candidate_convertible_defaults_false():
    """⑥ 候选的 `convertible` 恒为 False（默认），且显式传入 False 亦然。"""
    base = dict(
        candidate_id="c0002",
        evidence=_evidence(),
        subject_type="header",
        subject_name="Max-Forwards",
        raw_text="should probably limit hops",
    )
    assert KnowledgeCandidate(**base).convertible is False
    assert KnowledgeCandidate(**base, convertible=False).convertible is False


# ------------------------------------------------------------ 端到端小样例


def test_end_to_end_rule_construction_from_structured_identity():
    """端到端：由结构化身份派生 rule_id → 组装成 `SemanticRule`（含证据锚点）。"""
    ev = _evidence()
    constraint = ExecutableConstraint(**_constraint_kwargs())
    rid = compute_rule_id(
        protocol="sip",
        spec_version=ev.spec_version,
        section_path=ev.section_path,
        subject_type="header",
        subject_name="Max-Forwards",
        operator=constraint.operator,
        operand=constraint.operand,
        operand_ref=constraint.operand_ref,
        expected_behavior=constraint.expected_behavior,
    )
    eid = compute_evidence_id(rid, ev.source_anchor, ev.span_start)
    rule = SemanticRule(
        rule_id=rid,
        evidence=dataclasses.replace(ev, evidence_id=eid),
        constraint=constraint,
        subject_type="header",
        subject_name="Max-Forwards",
        rule_state="authoritative",
        supersedes=(),
        model_confidence=0.88,
        validated=True,
    )
    assert rule.rule_id == rid
    assert rule.evidence.evidence_id == eid
    assert rule.rule_state in RULE_STATES
    assert rule.constraint is not None
