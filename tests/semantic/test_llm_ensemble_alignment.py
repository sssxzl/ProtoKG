# -*- coding: utf-8 -*-
"""tests/test_llm_ensemble_alignment.py —— D-1 / D-4 / D-7 的行为契约。

本文件把「跨模型对齐的口径」固化成可执行断言。覆盖：

  · **D-1** `Candidate` 包装层 —— 模型身份**不得污染**规范规则
  · **D-4** 对齐**主判据 = 结构化字段全等**；span 重叠**永远不能单独造成对齐**
  · **D-7** `theta` 的确切语义 = 「证据 span 重叠的**辅助阈值**」，
    且 θ 的作用范围被钉死（内容全等时它才有发言权）

★ **不测投票本体**（D-2/D-3/D-5）：按 `docs/实施/路线与里程碑/RFC源里程碑路线图.md` §6，
  投票推迟到 B-10 实验判定「收益成立」之后。
"""
from __future__ import annotations

import dataclasses

import pytest

from core.fused.semantic.llm_ensemble import (
    DEFAULT_THETA,
    Alignment,
    Candidate,
    align_by_structural_equality,
    evidence_overlap,
    rule_content_identity,
)
from core.fused.semantic.semantic import (
    EvidenceAnchor,
    ExecutableConstraint,
    SemanticRule,
)


# ---------------------------------------------------------------- 构造助手
def _constraint(**overrides) -> ExecutableConstraint:
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
    return ExecutableConstraint(**kwargs)


def _evidence(**overrides) -> EvidenceAnchor:
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


def _rule(*, evidence=None, constraint=None, **overrides) -> SemanticRule:
    kwargs = dict(
        rule_id="r0123456789abcdef",
        evidence=evidence if evidence is not None else _evidence(),
        constraint=constraint if constraint is not None else _constraint(),
        subject_type="header",
        subject_name="Max-Forwards",
        rule_state="authoritative",
        supersedes=(),
        model_confidence=0.91,
        validated=True,
    )
    kwargs.update(overrides)
    return SemanticRule(**kwargs)


def _ev(start: int, end: int, **overrides) -> EvidenceAnchor:
    """同源文件、不同字符区间的证据（便于构造可控的重叠率）。"""
    return _evidence(span_start=start, span_end=end, **overrides)


# =========================================================== D-1 Candidate
class TestCandidateWrapper:
    """D-1：`Candidate` = 规则 + 运行时身份。"""

    def test_candidate_is_frozen_dataclass_with_three_fields(self):
        assert dataclasses.is_dataclass(Candidate)
        params = dataclasses.fields(Candidate)
        assert [f.name for f in params] == ["rule", "model_id", "run_id"]
        with pytest.raises(dataclasses.FrozenInstanceError):
            Candidate(rule=_rule(), model_id="m1", run_id="r1").model_id = "m2"

    def test_model_identity_does_not_pollute_the_rule(self):
        """★ 模型身份**未污染规范规则** —— `SemanticRule` 上没有 `model_id`。"""
        rule = _rule()
        assert hasattr(rule, "model_id") is False
        assert hasattr(rule, "run_id") is False
        # 包装成 Candidate 后，规则本体依旧不含运行时身份
        c = Candidate(rule=rule, model_id="gpt-5.2", run_id="run-7")
        assert c.model_id == "gpt-5.2"
        assert hasattr(c.rule, "model_id") is False

    def test_candidate_carries_rule_unchanged(self):
        rule = _rule()
        assert Candidate(rule=rule, model_id="m", run_id="r").rule is rule


# ====================================================== D-4 对齐主判据
class TestAlignMainCriterion:
    """D-4：主判据 = 结构化字段全等；span 重叠仅辅助。"""

    def test_span_overlap_09_but_operator_differs_is_not_aligned(self):
        """★ 评审 T1 第三点的直接反例：span 重叠 0.9 但算子不同 ⇒ **不对齐**。"""
        a = _rule(evidence=_ev(100, 200))
        b = _rule(evidence=_ev(110, 210), constraint=_constraint(operator="ge"))
        ov = evidence_overlap(a.evidence, b.evidence)
        assert ov == pytest.approx(0.9, abs=1e-6)   # 重叠确实很高
        res = align_by_structural_equality(a, b)
        assert res.aligned is False
        assert res.reason == "content_mismatch"

    def test_identical_rule_is_aligned(self):
        a = _rule()
        b = _rule()
        res = align_by_structural_equality(a, b)
        assert res.aligned is True
        assert res.overlap == pytest.approx(1.0, abs=1e-6)
        assert res.reason == "aligned"

    def test_each_content_field_participates(self):
        """内容身份里的**每一项**不同 ⇒ 都不对齐（逐项比对，不是抽样）。"""
        base = _rule()
        variants = [
            _rule(subject_type="method"),
            _rule(subject_name="Content-Length"),
            _rule(constraint=_constraint(target_field="Content-Length")),
            _rule(constraint=_constraint(operator="ge")),
            _rule(constraint=_constraint(operand=("71",))),
            _rule(constraint=_constraint(operand_source="field_ref", operand_ref="X")),
            _rule(constraint=_constraint(expected_behavior="success")),
            _rule(constraint=_constraint(applies_to_state=("connected",))),
            _rule(constraint=_constraint(applies_to_method=("INVITE",))),
        ]
        for other in variants:
            res = align_by_structural_equality(base, other)
            assert res.aligned is False, f"应判不对齐：{rule_content_identity(other)}"

    def test_evidence_position_is_not_part_of_content_identity(self):
        """★ 证据位置**不在**内容身份里 —— 它由重叠率单独比（不同模型摘录不同片段）。"""
        a = _rule(evidence=_ev(100, 200))
        b = _rule(evidence=_ev(120, 200))
        assert rule_content_identity(a) == rule_content_identity(b)


# ==================================================== D-7 theta 的语义
class TestThetaSemantics:
    """D-7：θ = 证据 span 重叠的**辅助阈值**，主判据始终是结构化全等。"""

    def test_default_theta_is_075(self):
        """★ 默认 θ = 0.75 —— 与 SpecGPT 的实测阈值**数值一致**
        （arXiv 2510.14348：一条转移判为正确需「状态精确匹配 + condition/action
        span 重叠 ≥ 75%」）⇒ θ 有外部实证，不是拍脑袋的数。"""
        assert DEFAULT_THETA == 0.75

    def test_overlap_below_theta_blocks_alignment(self):
        """内容全等，但证据重叠 < θ ⇒ 不对齐（θ 真的有发言权）。"""
        a = _rule(evidence=_ev(0, 100))
        b = _rule(evidence=_ev(80, 200))     # overlap = 20/100 = 0.2 < 0.75
        res = align_by_structural_equality(a, b)
        assert res.aligned is False
        assert "below_theta" in res.reason
        assert res.overlap == pytest.approx(0.2, abs=1e-6)

    def test_overlap_at_or_above_theta_aligns(self):
        """重叠 ≥ θ ⇒ 对齐（弱对齐：内容一致、证据高度重合）。"""
        a = _rule(evidence=_ev(0, 100))
        b = _rule(evidence=_ev(10, 200))     # overlap = 90/100 = 0.9 ≥ 0.75
        res = align_by_structural_equality(a, b)
        assert res.aligned is True
        assert res.overlap == pytest.approx(0.9, abs=1e-6)

    def test_theta_zero_removes_evidence_from_judgement(self):
        """★ θ = 0 ⇒ 证据位置**完全不参与**判定（只比内容）。"""
        a = _rule(evidence=_ev(0, 100))
        b = _rule(evidence=_ev(1000, 1100))  # 完全不同位置
        assert align_by_structural_equality(a, b).aligned is False      # θ 默认仍拦
        res = align_by_structural_equality(a, b, theta=0.0)
        assert res.aligned is True
        assert res.overlap == pytest.approx(0.0, abs=1e-6)

    def test_theta_one_demands_near_identical_evidence(self):
        """θ = 1 ⇒ 要求证据几乎完全重合。"""
        a = _rule(evidence=_ev(0, 100))
        b = _rule(evidence=_ev(10, 200))     # 0.9 < 1.0
        assert align_by_structural_equality(a, b, theta=1.0).aligned is False
        assert align_by_structural_equality(a, _rule(evidence=_ev(0, 100)),
                                             theta=1.0).aligned is True

    def test_theta_never_overrides_content_mismatch(self):
        """★ θ 无论多低，**内容不同就永远不对齐**（辅助不能越权）。"""
        a = _rule(evidence=_ev(0, 100))
        b = _rule(evidence=_ev(0, 100), constraint=_constraint(operator="ge"))
        for theta in (0.0, 0.5, 0.75, 1.0):
            assert align_by_structural_equality(a, b, theta=theta).aligned is False


# ============================================ 刻意保留的非传递性（D-7）
class TestKnownNonTransitivity:
    """★ 对齐是**成对判定**，不是传递闭包 —— 这是被测试钉住的**已知行为**。"""

    def test_alignment_is_not_transitive(self):
        """A≈B、B≈C，但 A≉C（内容全等、证据两两重叠阈值满足而 A∩C 不足）。"""
        a = _rule(evidence=_ev(0, 100))
        b = _rule(evidence=_ev(0, 150))
        c = _rule(evidence=_ev(50, 150))
        assert align_by_structural_equality(a, b).aligned is True    # overlap 1.0
        assert align_by_structural_equality(b, c).aligned is True    # overlap 1.0
        res_ac = align_by_structural_equality(a, c)
        assert res_ac.aligned is False                                # overlap 0.5
        assert res_ac.overlap == pytest.approx(0.5, abs=1e-6)

    def test_known_non_transitivity_is_documented_in_source(self):
        """★ 该性质必须**写在代码里**（否则后来者会误以为对齐是等价关系）。"""
        import inspect

        from core.fused.semantic import llm_ensemble
        doc = inspect.getdoc(llm_ensemble.align_by_structural_equality) or ""
        assert "传递" in doc
        assert "成对判定" in doc


# ================================================== evidence_overlap 口径
class TestEvidenceOverlap:
    def test_same_file_uses_char_interval_containment(self):
        a = _ev(100, 200)
        b = _ev(150, 250)
        assert evidence_overlap(a, b) == pytest.approx(0.5, abs=1e-6)
        # b 完全落在 a 内 ⇒ 包含率 1.0（这是**包含率**而非 Jaccard 的关键差别）
        assert evidence_overlap(a, _ev(150, 200)) == pytest.approx(1.0, abs=1e-6)

    def test_disjoint_intervals_give_zero(self):
        assert evidence_overlap(_ev(0, 50), _ev(100, 150)) == 0.0

    def test_cross_file_falls_back_to_text_overlap(self):
        """跨源文件时没有可比坐标系 ⇒ 退回文本最长公共子串。"""
        a = _evidence(source_anchor="file:a.txt#@1", span_text="MUST forward 70")
        b = _evidence(source_anchor="file:b.txt#@1", span_text="MUST forward 70")
        assert evidence_overlap(a, b) == pytest.approx(1.0, abs=1e-6)
        c = _evidence(source_anchor="file:b.txt#@1", span_text="completely different")
        # 只共享零散字符 ⇒ 极低但**不为 0**（最长公共子串口径）
        assert evidence_overlap(a, c) < 0.2
        d = _evidence(source_anchor="file:b.txt#@1", span_text="xyz")
        assert evidence_overlap(a, d) == 0.0

    def test_missing_spans_fall_back_to_text(self):
        a = _evidence(span_start=None, span_end=None)
        b = _evidence(span_start=None, span_end=None)
        assert evidence_overlap(a, b) == pytest.approx(1.0, abs=1e-6)


# ============================================================ 结果类型
def test_alignment_is_frozen_dataclass():
    assert dataclasses.is_dataclass(Alignment)
    with pytest.raises(dataclasses.FrozenInstanceError):
        Alignment(True, 1.0, "x").aligned = False
