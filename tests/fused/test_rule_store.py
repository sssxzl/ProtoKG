"""tests/fused/test_rule_store.py —— B-7 四库分离 + `reflow_rules`。

对应 docs/rfc_source_bcd_roadmap.md §3.8 任务表 B-7（文档任务号 B5）与
§3.3 强制机制 3（落盘隔离），以及 docs/rfc_source_reform_plan.md §3.5
的 `reflow_rules()` 伪代码。

验收：
  ① **四库文件独立落盘** —— rules / candidates / revoked / feedback 各一份，
     候选**进不了**规则文件；`semantic/` 目录**不在** `*/facts/*.jsonl` 之下
     ⇒ 自动生成链路（`load_fact_views`）**读不到**；
  ② `reflow_rules()`：输入规则 + 反馈表 → 输出**仅顺序变化**，
     `rule` 对象**逐字段相等**（用 `==` 断言**整个 dataclass 相等**，
     而非只断言 id 集合）；
  ③ 反馈写入后 `rule_id` 与规则内容**均不变**（评审 T9/R23）；
  ④ `boundary_probe` 的探测回写**改道 feedback 库** ⇒ 原 `legal_boundary`
     fact **未被修改**。
"""
from __future__ import annotations

import json

import pytest


from core import paths
from core.fused.downstream import rule_store
from core.fused.downstream.boundary_probe import (
    emit_boundary_fact,
    emit_boundary_feedback,
)
from core.fused.semantic import (
    EvidenceAnchor,
    ExecutableConstraint,
    KnowledgeCandidate,
    SemanticRule,
)

PROTOCOL = "rtsp"


# ===========================================================================
# 构造夹具
# ===========================================================================

def _rule(rule_id: str, *, subject: str = "QNAME", operand: str = "63",
          rule_state: str = "authoritative") -> SemanticRule:
    """构造一条 SemanticRule（可执行层齐全）。"""
    ev = EvidenceAnchor(
        evidence_id=f"ev-{rule_id}",
        spec_version="RFC 2326",
        section_path=("1", "1.2"),
        source_anchor="file:rfc2326.txt#@320",
        span_text="The length of the label MUST NOT exceed 63 octets.",
        span_start=17254,
        span_end=17313,
        evidence_kind="normative",
        explicitness="explicit",
        source_class="rfc",
    )
    constraint = ExecutableConstraint(
        target_field=subject,
        operator="le",
        operand=(operand,),
        operand_source="constant",
        operand_ref=None,
        applies_to_state=(),
        applies_to_method=(),
        expected_behavior="protocol_error",
        sender_role="client",
        receiver_role="server",
        precondition=None,
    )
    return SemanticRule(
        rule_id=rule_id,
        evidence=ev,
        constraint=constraint,
        subject_type="header",
        subject_name=subject,
        rule_state=rule_state,
        supersedes=(),
        model_confidence=0.9,
        validated=True,
    )


def _candidate(candidate_id: str) -> KnowledgeCandidate:
    ev = EvidenceAnchor(
        evidence_id=f"ev-{candidate_id}",
        spec_version="RFC 2326",
        section_path=("1",),
        source_anchor="file:rfc2326.txt#@321",
        span_text="A MAY mention the value.",
        span_start=17314,
        span_end=17344,
        evidence_kind="prose",
        explicitness="paraphrased",
        source_class="rfc",
    )
    return KnowledgeCandidate(
        candidate_id=candidate_id,
        evidence=ev,
        subject_type="header",
        subject_name="QNAME",
        raw_text="A MAY mention the value.",
        convertible=False,
        reject_reason="optional_modality",
    )


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """把四库根指向 tmp_path（不改真实 derived/）。"""
    monkeypatch.setattr(paths, "per_source_root",
                        lambda p: tmp_path / p.lower())
    return tmp_path


# ===========================================================================
# ① 四库文件独立落盘（§3.3 强制机制 3）
# ===========================================================================

def test_four_libraries_are_separate_files(store):
    """四库各一份文件；内容互不串库。"""
    rules = [_rule("r1"), _rule("r2")]
    cands = [_candidate("c1")]
    revoked = [_rule("r9", rule_state="revoked")]

    p_rules = rule_store.save_rules(PROTOCOL, rules)
    p_cands = rule_store.save_candidates(PROTOCOL, cands)
    p_rev = rule_store.save_revoked(PROTOCOL, revoked)
    p_fb = rule_store.save_feedback(PROTOCOL, {"r1": {"priority_score": 1.0}})

    paths_ = {p_rules, p_cands, p_rev, p_fb}
    assert len(paths_) == 4, "四库必须落在**四个不同文件**"
    for p in paths_:
        assert p.is_file()
    assert p_rules.name == "rules.jsonl"
    assert p_cands.name == "candidates.jsonl"
    assert p_rev.name == "revoked.jsonl"
    assert p_fb.name == "feedback.jsonl"
    assert p_rules.parent == p_cands.parent == p_rev.parent == p_fb.parent

    # 内容互不串库：rules.jsonl 里没有候选、candidates.jsonl 里没有规则
    kinds_rules = {json.loads(ln)["kind"]
                   for ln in p_rules.read_text(encoding="utf-8").splitlines() if ln}
    kinds_cands = {json.loads(ln)["kind"]
                   for ln in p_cands.read_text(encoding="utf-8").splitlines() if ln}
    assert kinds_rules == {"semantic_rule"}
    assert kinds_cands == {"knowledge_candidate"}


def test_candidates_cannot_be_loaded_as_rules(store):
    """强制机制 3 ②：逐条 isinstance 断言 ⇒ 候选进不了规则库。"""
    rule_store.save_candidates(PROTOCOL, [_candidate("c1")])
    cand_path = rule_store.library_path(PROTOCOL, "candidate")
    # 候选文件里没有 kind=semantic_rule 的条目 ⇒ load_rules 读不到任何规则
    assert rule_store.load_rules(cand_path) == []
    # 规则文件里混进候选 ⇒ 直接报错（不是静默跳过）
    rules_path = rule_store.library_path(PROTOCOL, "authoritative")
    with rules_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "semantic_rule",
                             "rule": {"rule_id": "r1"}}, ensure_ascii=False) + "\n")
    with pytest.raises((TypeError, ValueError)):
        rule_store.load_rules(rules_path)


def test_rules_with_none_constraint_are_rejected(store):
    """强制机制 3 ③：`constraint is None` 的规则**直接拒绝**（不静默跳过）。"""
    bad = SemanticRule(
        rule_id="r_bad", evidence=_rule("r1").evidence, constraint=None,
        subject_type="header", subject_name="QNAME", rule_state="authoritative",
        supersedes=(), model_confidence=None, validated=False)
    p = rule_store.save_rules(PROTOCOL, [bad])
    with pytest.raises(ValueError):
        rule_store.load_rules(p)


def test_semantic_dir_is_outside_the_facts_glob(store):
    """★ 落盘隔离：`semantic/` **不在** `*/facts/*.jsonl` 之下
    ⇒ `load_fact_views()`（glob `*/facts/*.jsonl`）读不到四库。"""
    rule_store.save_rules(PROTOCOL, [_rule("r1")])
    rule_store.save_candidates(PROTOCOL, [_candidate("c1")])
    rule_store.save_revoked(PROTOCOL, [_rule("r9", rule_state="revoked")])
    rule_store.save_feedback(PROTOCOL, {"r1": {"priority_score": 1.0}})
    root = paths.per_source_root(PROTOCOL)
    globbed = {p.resolve() for p in root.glob("*/facts/*.jsonl")}
    for lib in rule_store.LIBRARY_FILES:
        p = rule_store.library_path(PROTOCOL, lib)
        assert p.exists(), f"{lib} 库未落盘"
        assert p.resolve() not in globbed, f"{lib} 落在事实 glob 内 ⇒ 会混进知识中枢"


def test_roundtrip_preserves_dataclass_equality(store):
    """往返落盘后规则对象**逐字段相等**（tuple 不能退化成 list）。"""
    rules = [_rule("r1"), _rule("r2", subject="QTYPE")]
    p = rule_store.save_rules(PROTOCOL, rules)
    loaded = rule_store.load_rules(p)
    assert loaded == rules, "落盘往返必须保持整个 dataclass 相等"
    assert loaded[0].evidence.section_path == ("1", "1.2")
    assert loaded[0].constraint.operand == ("63",)


# ===========================================================================
# ② reflow_rules：仅顺序变化，整个 dataclass 相等
# ===========================================================================

def test_reflow_rules_only_changes_order():
    """★ ② 反馈只改**调度顺序**，规则对象**逐字段相等**。"""
    rules = [_rule("r1"), _rule("r2"), _rule("r3")]
    feedback = {"r2": {"priority_score": 5.0, "selection_count": 3,
                        "coverage_signal": 0.2}}
    out = rule_store.reflow_rules(rules, feedback)

    # 顺序确实变了：高优先级规则排到最前
    assert [r.rule_id for r in out] == ["r2", "r1", "r3"]
    # 集合不变（没有增删）
    assert {r.rule_id for r in out} == {r.rule_id for r in rules}
    # ★ 用 `==` 断言**整个 dataclass 相等**（不是只断言 id 集合）
    by_id_before = {r.rule_id: r for r in rules}
    for r in out:
        assert r == by_id_before[r.rule_id], (
            f"规则 {r.rule_id} 的内容被反馈改了（违反「反馈不改规则内容」）")


def test_reflow_rules_is_deterministic_and_order_independent():
    """同优先级按 rule_id 兜底 ⇒ 与输入顺序无关（确定性）。"""
    rules = [_rule("r3"), _rule("r1"), _rule("r2")]
    a = rule_store.reflow_rules(rules, {})
    b = rule_store.reflow_rules(list(reversed(rules)), {})
    assert [r.rule_id for r in a] == [r.rule_id for r in b] == ["r1", "r2", "r3"]
    # 无反馈 ⇒ 全部优先级 0
    assert [r.rule_id for r in a] == ["r1", "r2", "r3"]


def test_reflow_rules_ignores_non_rule_feedback_keys():
    """探测反馈（`probe:` 前缀键）不影响规则排序（取不到 ⇒ 默认分）。"""
    rules = [_rule("r1"), _rule("r2")]
    feedback = {rule_store.probe_feedback_key(PROTOCOL, "SETUP", "track"): {
        "priority_score": 99.0, "selection_count": 1, "coverage_signal": 1.0}}
    out = rule_store.reflow_rules(rules, feedback)
    assert [r.rule_id for r in out] == ["r1", "r2"]


# ===========================================================================
# ③ 反馈写入后 rule_id 与规则内容均不变
# ===========================================================================

def test_feedback_write_does_not_change_rules(store):
    """★ ③ 反馈写入后，`rule_id` 与规则内容**均不变**（评审 T9/R23）。"""
    rules = [_rule("r1"), _rule("r2")]
    p = rule_store.save_rules(PROTOCOL, rules)
    before = rule_store.load_rules(p)
    before_ids = [r.rule_id for r in before]

    rule_store.record_feedback(PROTOCOL, "r2", {
        "priority_score": 9.0, "selection_count": 7, "coverage_signal": 0.1})
    rule_store.record_feedback(PROTOCOL, "r3", {
        "priority_score": 1.0, "selection_count": 2, "coverage_signal": 0.5})

    after = rule_store.load_rules(p)
    assert [r.rule_id for r in after] == before_ids
    # ★ 整个 dataclass 逐字段相等（内容一字未改）
    for r_before, r_after in zip(before, after):
        assert r_after == r_before
    # 反馈表本身落盘了
    fb = rule_store.load_feedback(rule_store.library_path(PROTOCOL, "feedback"))
    assert fb["r2"]["priority_score"] == 9.0
    assert fb["r3"]["selection_count"] == 2


def test_feedback_merge_keeps_other_fields(store):
    """同键反馈按**字段合并**更新（不丢已有字段）。"""
    rule_store.record_feedback(PROTOCOL, "r1", {"priority_score": 2.0})
    rule_store.record_feedback(PROTOCOL, "r1", {"selection_count": 5})
    fb = rule_store.load_feedback(rule_store.library_path(PROTOCOL, "feedback"))
    assert fb["r1"]["priority_score"] == 2.0
    assert fb["r1"]["selection_count"] == 5


# ===========================================================================
# ④ boundary_probe 探测回写改道 feedback 库
# ===========================================================================

def test_probe_feedback_does_not_touch_authoritative_facts(store, tmp_path):
    """★ ④ 探测回写改道 ⇒ 原 `legal_boundary` fact **未被修改**。"""
    # 造一个「权威事实」文件（模拟 rfc 源产出的 legal_boundary fact）
    facts_dir = paths.per_source_root(PROTOCOL) / "rfc" / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    authoritative = facts_dir / "rfc.jsonl"
    original = json.dumps({
        "fact_key": {"protocol": PROTOCOL, "version": "1.0",
                     "subject": {"type": "header", "name": "QNAME",
                                 "qualifiers": {}, "path": []},
                     "aspect": "legal_boundary",
                     "condition": {"type": "always"}},
        "resolution": None,
        "all_claims": [{"claim_id": "c2_x", "fact_id": "f2_x",
                        "value": {"type": "struct", "data": {
                            "dim": "QNAME", "legal": "≤ 63", "illegal": "> 63",
                            "trigger": "FORMERR"}},
                        "epistemic_type": "normative", "authority": "rfc",
                        "scope": None, "evidence_summary": ["rfc:QNAME"],
                        "confidence": None}],
    }, ensure_ascii=False) + "\n"
    authoritative.write_text(original, encoding="utf-8")
    before_bytes = authoritative.read_bytes()

    # 改道后的规范入口：只写 feedback 库
    sink = tmp_path / "feedback.jsonl"
    rec = emit_boundary_feedback("SETUP", "track_number", "不同track", "同track",
                                  "Session=000022B8", protocol=PROTOCOL, sink=sink)

    # ★ 原 legal_boundary fact **未被修改**（逐字节）
    assert authoritative.read_bytes() == before_bytes
    # 探测结果落在 feedback 库
    assert sink.is_file()
    fb = rule_store.load_feedback(sink)
    key = rec["key"]
    assert key in fb
    assert fb[key]["method"] == "SETUP"
    assert fb[key]["dim"] == "track_number"
    # feedback 库**不在**事实 glob 下 ⇒ 知识中枢读不到
    globbed = {p.resolve() for p in paths.per_source_root(PROTOCOL).glob(
        "*/facts/*.jsonl")}
    assert sink.resolve() not in globbed


def test_emit_boundary_fact_records_feedback_and_keeps_legacy_shape(store, tmp_path):
    """`emit_boundary_fact` 保持**签名/返回结构**；给定 sink 时**只**落 feedback 库。"""
    facts_dir = paths.per_source_root(PROTOCOL) / "rfc" / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    authoritative = facts_dir / "rfc.jsonl"
    authoritative.write_text('{"fact_key": {}}\n', encoding="utf-8")
    before_bytes = authoritative.read_bytes()

    sink = tmp_path / "feedback.jsonl"
    fact = emit_boundary_fact("SETUP", "track_number", "不同track", "同track",
                              "Session=000022B8", protocol=PROTOCOL,
                              feedback_sink=sink)

    # 返回结构与改道前**一致**（既有测试依赖）
    assert fact["fact_key"]["subject"]["type"] == "method"
    assert fact["fact_key"]["subject"]["name"] == "SETUP"
    assert fact["fact_key"]["aspect"] == "legal_boundary"
    assert fact["all_claims"][0]["value"]["data"]["dim"] == "track_number"
    assert fact["all_claims"][0]["authority"] == "boundary_probe"

    # 探测结果进了 feedback 库；权威 facts **未被修改**
    assert sink.is_file()
    assert authoritative.read_bytes() == before_bytes
    fb = rule_store.load_feedback(sink)
    assert any(v.get("method") == "SETUP" for v in fb.values())


def test_probe_feedback_key_never_collides_with_rule_id():
    """探测反馈键带命名空间前缀 ⇒ 永远不与 rule_id 撞键。"""
    key = rule_store.probe_feedback_key(PROTOCOL, "SETUP", "track_number")
    assert key.startswith(rule_store.FEEDBACK_PROBE_PREFIX)
    assert "SETUP" in key and "track_number" in key


def test_load_fact_views_excludes_boundary_probe_after_redirect(store):
    """★ **机器可判定判据**：改道 + 清理旧残留后，
    ``load_fact_views()`` 读到的 fact 里**不含** boundary_probe 源。

    场景还原：旧版脚本把探测回写写进
    ``per_source/<p>/boundary_probe/facts/boundary_probe.jsonl`` ——
    那个目录**在** ``*/facts/*.jsonl`` glob 内 ⇒ 会被读走 ⇒
    探测反馈混进权威知识中枢（改进v2 问题⑤）。
    改道后：探测反馈落 ``semantic/feedback.jsonl``（不在 glob 内），
    且脚本会清理旧路径残留。
    """
    from core.fused.downstream.rag_seedgen import load_fact_views
    from scripts.run_boundary_probe import purge_legacy_boundary_facts

    # ① 权威侧：rfc 源的一份 legal_boundary fact（**应当**被读到）
    rfc_dir = paths.per_source_root(PROTOCOL) / "rfc" / "facts"
    rfc_dir.mkdir(parents=True, exist_ok=True)
    (rfc_dir / "rfc.jsonl").write_text(json.dumps({
        "fact_key": {"protocol": PROTOCOL, "version": "1.0",
                     "subject": {"type": "header", "name": "QNAME",
                                 "qualifiers": {}, "path": []},
                     "aspect": "legal_boundary",
                     "condition": {"type": "always"}},
        "resolution": None,
        "all_claims": [{"claim_id": "c2_rfc", "fact_id": "f2_rfc",
                        "value": {"type": "struct", "data": {"dim": "QNAME"}},
                        "epistemic_type": "normative", "authority": "rfc",
                        "scope": None, "evidence_summary": ["rfc:QNAME"],
                        "confidence": None}]}, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # ② 历史残留：旧路径的 boundary_probe 回写（**仍在 facts glob 内**）
    legacy_dir = paths.per_source_root(PROTOCOL) / "boundary_probe" / "facts"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy = legacy_dir / "boundary_probe.jsonl"
    legacy.write_text(json.dumps({
        "fact_key": {"protocol": PROTOCOL, "version": "1.0",
                     "subject": {"type": "method", "name": "SETUP",
                                 "qualifiers": {}, "path": []},
                     "aspect": "legal_boundary",
                     "condition": {"type": "always"}},
        "resolution": None,
        "all_claims": [{"claim_id": "c2_bp", "fact_id": "f2_bp",
                        "value": {"type": "struct", "data": {"dim": "track_number"}},
                        "epistemic_type": "observed",
                        "authority": "boundary_probe", "scope": None,
                        "evidence_summary": ["boundary_probe:SETUP.legal_boundary.track_number"],
                        "confidence": None}]}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    # 清理前：旧残留**确实**会被 glob 命中（即旧路径是污染源）
    globbed = {p.resolve() for p in paths.per_source_root(PROTOCOL).glob(
        "*/facts/*.jsonl")}
    assert legacy.resolve() in globbed

    # ③ 改道后的新落点：feedback 库
    emit_boundary_feedback("SETUP", "track_number", "不同track", "同track",
                           "Session=000022B8", protocol=PROTOCOL)

    # ④ 脚本里的清理逻辑（同一段代码）
    purged = purge_legacy_boundary_facts(PROTOCOL)
    assert purged is not None and not legacy.exists(), "旧路径残留未被清理"

    # ★ 判据：load_fact_views 读到的 fact 里**不含** boundary_probe
    views = load_fact_views(PROTOCOL)
    authorities = {c.get("authority") for v in views
                   for c in (v.get("all_claims") or [])}
    assert authorities == {"rfc"}, f"fact 视图里出现了非 rfc 来源：{authorities}"
    # 反馈库不在 glob 内 ⇒ 读不到
    fb = rule_store.library_path(PROTOCOL, "feedback")
    assert fb.is_file()
    globbed = {p.resolve() for p in paths.per_source_root(PROTOCOL).glob(
        "*/facts/*.jsonl")}
    assert fb.resolve() not in globbed
