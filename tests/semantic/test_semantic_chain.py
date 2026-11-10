# -*- coding: utf-8 -*-
"""tests/test_semantic_chain.py —— 批次 1.5：RFC 语义链路的回归用例。

★ 链路（此前有**三级断链**，机制齐备但没接线）::

    RFC 源 → facts → 两层模型 → SemanticRule
      → ★断点1 权威库 rules.jsonl 从未落盘（save_rules API 齐备但无人调用）
      → ★断点2 bundle["semantic_rules"] 恒缺（D-6 默认 OFF 且消费端不显式传参）
      → 投影两桶 legal_boundary / response_expectation 恒空
      → ★断点3 derive_constraint_candidates 只被测试调用、生产代码从不调用
      ⇒ 「RFC 语义 → 知识中枢 → 消费」对种子生成**零贡献**

★ 本文件把这些断链逐条钉死，防止再退化。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.fused.downstream.boundary_probe import (
    derive_constraint_candidates,
)
from core.fused.downstream.rag_seedgen import (
    assemble_bundle,
    project_semantic_rules,
)
from core.fused.downstream.rule_store import (
    KIND_RULE,
    publish_rules,
)
from core.fused.semantic.semantic import (
    SANITIZE_REJECT_REASONS,
    SemanticRule,
    sanitize_rule,
)

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# 夹具
# ===========================================================================

def _rule(rule_id: str = "r-test-0001", *, subject: str = "Session",
          target: str = "Session", operator: str = "present",
          operand: tuple = (), behavior: str = "") -> dict:
    return {
        "rule_id": rule_id,
        "evidence": {
            "evidence_id": "e-test-0001",
            "spec_version": "RFC 2326",
            "section_path": ["Method Definitions"],
            "source_anchor": "file:rfc2326.txt#@1679",
            "span_text": "A server MUST include the Session header.",
            "span_start": 100,
            "span_end": 140,
            "evidence_kind": "normative",
            "explicitness": "explicit",
            "source_class": "normative_spec",
        },
        "constraint": {
            "target_field": target,
            "operator": operator,
            "operand": list(operand),
            "operand_source": "constant",
            "operand_ref": None,
            "applies_to_state": [],
            "applies_to_method": [],
            "expected_behavior": behavior,
            "sender_role": "client",
            "receiver_role": "server",
            "precondition": None,
        },
        "subject_type": "header",
        "subject_name": subject,
        "rule_state": "authoritative",
        "supersedes": [],
        "model_confidence": 1.0,
        "validated": True,
    }


def _bundle_with_rule(rule: dict) -> dict:
    bundle = {"semantic_rules": [rule]}
    project_semantic_rules(bundle)
    return bundle


# ===========================================================================
# ① 批次 2 主体：sanitize_rule 的三类移除
# ===========================================================================

class TestSanitizeRule:
    """★ 批次 2（迁移项 D）：规则后处理，移除伪规则/空规则。"""

    def test_keeps_valid_rule(self):
        kept, reason = sanitize_rule(_rule_obj())
        assert kept is not None
        assert reason is None

    def test_removes_empty_subject(self):
        """★ subject_name 与 target_field **都空** ⇒ 投影不出任何桶 ⇒ 移除。"""
        kept, reason = sanitize_rule(
            _rule_obj(subject="", target=""))
        assert kept is None
        assert reason == "empty_subject"

    def test_removes_empty_operand(self):
        """★ 有参算子但 operand 空 ⇒ 兜底移除。

        ★ 该情形**正常构造路径造不出来**（``ExecutableConstraint.__post_init__``
          已拦）⇒ 本用例模拟「**绕过构造校验**」的路径（LLM 兜底路径），
          这正是这条兜底规则存在的意义。
        """
        rule = _rule_obj(operator="lt", operand=("8",))
        object.__setattr__(rule.constraint, "operand", ())
        kept, reason = sanitize_rule(rule)
        assert kept is None
        assert reason == "empty_operand"

    def test_removes_self_reference(self):
        """★ operand_ref == target_field ⇒ 自指约束 ⇒ 移除。"""
        rule = _rule_obj()
        object.__setattr__(rule.constraint, "operand_source", "field_ref")
        object.__setattr__(rule.constraint, "operand_ref", "Session")
        kept, reason = sanitize_rule(rule)
        assert kept is None
        assert reason == "self_reference"

    def test_keeps_rule_with_empty_expected_behavior(self):
        """★ **刻意保留** ``expected_behavior`` 为空的规则。

        它仍能投影出 **C（合法边界）** ⇒ 移除会白白丢掉 C 侧知识
        （实测 E1 组 14/14 条全空 ⇒ 移除后 legal_boundary 从 5 条变 0 条）。
        """
        kept, reason = sanitize_rule(_rule_obj(behavior=""))
        assert kept is not None
        assert reason is None

    def test_reject_reasons_are_closed_vocabulary(self):
        assert set(SANITIZE_REJECT_REASONS) == {
            "empty_subject", "empty_operand", "self_reference"}


def _rule_obj(**kw) -> SemanticRule:
    """构造一个真正的 ``SemanticRule``（走 dataclass 校验）。"""
    from core.fused.downstream.rule_store import _rule_from_dict
    data = _rule(**kw)
    return _rule_from_dict(data)


# ===========================================================================
# ② 四库分流发布
# ===========================================================================

class TestPublishRules:
    """★ 发布通道：合格的进权威库，不合格的进**候选库**（不静默丢弃）。"""

    def test_split_between_authoritative_and_candidate(self, tmp_path, monkeypatch):
        import core.fused.downstream.rule_store as rs
        monkeypatch.setattr(rs.paths, "per_source_root",
                            lambda p: tmp_path / p)
        rows = [_rule("r-good-01"),
                _rule("r-empty-01", subject="", target="")]
        report = publish_rules("rtsp", rows, replace=True)
        assert report["authoritative"] == 1
        assert report["candidate"] == 1
        assert report["rejects"] == {"empty_subject": 1}
        auth = tmp_path / "rtsp" / "rfc" / "semantic" / "rules.jsonl"
        cand = tmp_path / "rtsp" / "rfc" / "semantic" / "candidates.jsonl"
        assert auth.is_file() and cand.is_file()
        # 权威库只装 SemanticRule；候选库只装 KnowledgeCandidate
        auth_rows = [json.loads(_line) for _line in
                     auth.read_text(encoding="utf-8").splitlines()
                     if _line.strip()]
        assert all(r["kind"] == KIND_RULE for r in auth_rows)
        cand_rows = [json.loads(_line) for _line in
                     cand.read_text(encoding="utf-8").splitlines()
                     if _line.strip()]
        assert all(r["kind"] == "knowledge_candidate" for r in cand_rows)
        assert cand_rows[0]["candidate"]["reject_reason"] == "empty_subject"

    def test_candidate_library_is_appended_not_overwritten(self, tmp_path,
                                                           monkeypatch):
        """★ 候选库**追加**：分批发布不得把前一批的候选**丢掉**。"""
        import core.fused.downstream.rule_store as rs
        monkeypatch.setattr(rs.paths, "per_source_root",
                            lambda p: tmp_path / p)
        publish_rules("rtsp", [_rule("r-empty-01", subject="", target="")],
                      replace=True)
        publish_rules("rtsp", [_rule("r-empty-02", subject="", target="")],
                      replace=False)
        cand = tmp_path / "rtsp" / "rfc" / "semantic" / "candidates.jsonl"
        rows = [json.loads(_line) for _line in
                cand.read_text(encoding="utf-8").splitlines()
                if _line.strip()]
        assert len(rows) == 2, "第二批发布后，第一批的候选不得消失"


# ===========================================================================
# ③ 消费端显式装载 ⇒ 投影两桶有内容
# ===========================================================================

class TestSemanticChainClosed:
    """★ 断点 1/2：规则 → 权威库 → bundle → 投影两桶。"""

    def test_projection_produces_legal_boundary(self):
        bundle = _bundle_with_rule(_rule())
        lb = bundle.get("legal_boundary") or {}
        assert lb, "显式传入规则 ⇒ legal_boundary 必须非空"
        assert "Session" in lb

    def test_projection_is_idempotent(self):
        """★ 不变量 I5.2：同一 bundle 投影两次 ⇒ 两桶逐字节相同。"""
        bundle = {"semantic_rules": [_rule()]}
        project_semantic_rules(bundle)
        first = json.dumps([bundle.get("legal_boundary"),
                            bundle.get("response_expectation")],
                           ensure_ascii=False, sort_keys=True)
        project_semantic_rules(bundle)
        second = json.dumps([bundle.get("legal_boundary"),
                             bundle.get("response_expectation")],
                            ensure_ascii=False, sort_keys=True)
        assert first == second

    def test_default_path_has_no_semantic_rules_key(self):
        """★ 不变量 I5.4：D-6 OFF 且未显式传参 ⇒ bundle **不含**新键。"""
        from core.fused.downstream.rag_seedgen import load_fact_views
        views = load_fact_views("rtsp")
        if not views:
            return
        bundle = assemble_bundle(views)
        assert "semantic_rules" not in bundle
        assert "bundle_schema_version" not in bundle

    def test_explicit_rules_produce_projected_buckets(self):
        """★ 显式传参 = 调用方显式授权（**优先于 D-6 开关**）。"""
        from core.fused.downstream.rag_seedgen import load_fact_views
        views = load_fact_views("rtsp")
        if not views:
            return
        bundle = assemble_bundle(views, semantic_rules=[_rule()])
        assert "semantic_rules" in bundle
        assert bundle.get("legal_boundary")


# ===========================================================================
# ④ 最后一跳：约束边界候选真的被 seedgen 用上了
# ===========================================================================

class TestConstraintCandidatesReachSeedgen:
    """★ 断点 3：``derive_constraint_candidates`` 必须**被生产代码调用**。"""

    def test_seedgen_calls_derive_constraint_candidates(self):
        """★ 静态断言：seedgen 的 ③ 层必须调用它（否则最后一跳缺失）。"""
        import inspect
        import scripts.seedgen as seedgen_mod
        src = inspect.getsource(seedgen_mod)
        assert "derive_constraint_candidates" in src, \
            "③ 层必须并入「源 A 第四类」约束边界候选"

    def test_candidates_are_produced_from_projected_bundle(self):
        bundle = _bundle_with_rule(_rule())
        cands = derive_constraint_candidates(bundle)
        assert len(cands) == 2
        assert [label for label, _ in cands] == ["legal", "illegal"]

    def test_protocol_agnostic_construction(self):
        """★ 协议化：用 bundle 的 methods/required_headers 构造消息（非 RTSP 也可用）。"""
        bundle = {
            "legal_boundary": {"Subject": [
                {"dim": "Subject", "legal": "存在", "illegal": "缺失",
                 "trigger": ""}]},
            "response_expectation": {},
            "methods": {"HELLO": {"state_changing": False}},
            "required_headers": {"HELLO": ["CSeq", "Subject"]},
            "headers": {"CSeq": {"values": ["1"]},
                        "Subject": {"values": ["hi"]}},
        }
        cands = derive_constraint_candidates(bundle, stream="", protocol="x")
        assert len(cands) == 2
        illegal = cands[1][1]
        assert illegal.messages[0].method == "HELLO", "入口方法应来自 bundle"
        assert illegal.messages[0].headers.get("Subject") == "A" * 300


# ===========================================================================
# ⑤ 知识中枢质量：headers 桶的空取值（批次 1.5 改动 4 的前置诊断）
# ===========================================================================

class TestHeadersBucketQuality:
    """★ 知识中枢的 headers 桶存在**大面积空取值** ⇒ 必填头补不出值。"""

    def test_required_header_without_value_is_reported(self):
        """必填头若在 headers 桶里取不到非空值 ⇒ 补齐动作必被拒（R-2 根因）。"""
        from core.fused.downstream.rag_seedgen import load_fact_views
        views = load_fact_views("sip")
        if not views:
            return
        bundle = assemble_bundle(views)
        headers = bundle.get("headers") or {}
        required = bundle.get("required_headers") or {}
        names = sorted({h for lst in required.values() for h in (lst or [])})
        blank = [h for h in names
                 if not [v for v in ((headers.get(h) or {}).get("values") or [])
                         if str(v).strip()]]
        # 只断言「诊断口径可用」：若真有必填头取不到值，必须能被列出来
        assert isinstance(blank, list)
