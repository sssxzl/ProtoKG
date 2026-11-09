"""tests/fused/test_bundle_projection.py —— B-8 bundle 契约扩展 + 语义规则投影。

对应 docs/RFC源里程碑BCD路线图.md §3.8 任务表 B-8（文档任务号 B7）与
§3.6 选项 c（「影子实现升级为两层模型，`legal_boundary` 桶保留但由两层模型
投影填充」）。

验收（逐条对齐任务表）：
  ① bundle 新增 `semantic_rules` + `bundle_schema_version="2.0"`；
  ② `legal_boundary` / `response_expectation` 两桶**由 `semantic_rules` 投影填充**；
  ③ **投影幂等**：对同一 bundle 投影两次 ⇒ 两桶逐字节相同；
  ④ **旧 bundle 兼容**：无 `semantic_rules` 键 ⇒ 投影不抛异常且两桶不变；
  ⑤ `boundary_probe.py` / `strategy.py` **零改动**仍能工作（回归护栏）。

★ 本文件只测 `core/fused/downstream/rag_seedgen.py` 的投影契约 ——
  `boundary_probe.py` / `strategy.py` **一个字都不许改**（本文件只**消费**它们）。
"""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from core.fused.downstream.boundary_probe import derive_constraint_candidates
from core.fused.llm_ensemble import ENV_KEY as SEMANTIC_RULES_ENV_KEY
from core.fused.downstream.rag_seedgen import (
    BUNDLE_SCHEMA_VERSION,
    _render_domains,
    _resolve_expected_behavior,
    assemble_bundle,
    get_bundle_schema_version,
    load_semantic_rules,
    project_semantic_rules,
)
from core.fused.downstream.strategy import render_attack_prompt
from core.fused.semantic import (
    EvidenceAnchor,
    ExecutableConstraint,
    KnowledgeCandidate,
    SemanticRule,
)


# ===========================================================================
# 构造夹具
# ===========================================================================

def _evidence() -> EvidenceAnchor:
    """一条可核对的规范性证据（B-2 的两层模型形态）。"""
    return EvidenceAnchor(
        evidence_id="ev-qname-63",
        spec_version="RFC 2326",
        section_path=("12", "33"),
        source_anchor="file:rfc2326.txt#@320",
        span_text="The length of the label MUST NOT exceed 63 octets.",
        span_start=17254,
        span_end=17313,
        evidence_kind="normative",
        explicitness="explicit",
        source_class="normative_spec",
    )


def _constraint(**kw) -> ExecutableConstraint:
    """构造可执行层（默认：QNAME 长度 ≤ 63，处理期望 = protocol_error）。"""
    params = dict(
        target_field="QNAME",
        operator="le",
        operand=("63",),
        operand_source="constant",
        operand_ref=None,
        applies_to_state=(),
        applies_to_method=(),
        expected_behavior="protocol_error",
        sender_role="client",
        receiver_role="server",
        precondition=None,
    )
    params.update(kw)
    return ExecutableConstraint(**params)


def _rule(rule_id: str = "r-qname-63", *, rule_state: str = "authoritative",
          constraint: ExecutableConstraint | None = None,
          subject_name: str = "QNAME") -> SemanticRule:
    """构造一条 SemanticRule（`constraint=None` 时即「不可转换」规则）。"""
    return SemanticRule(
        rule_id=rule_id,
        evidence=_evidence(),
        constraint=_constraint() if constraint is None else constraint,
        subject_type="header",
        subject_name=subject_name,
        rule_state=rule_state,
        supersedes=(),
        model_confidence=0.93,
        validated=True,
    )


def _bundle_with(rules: list, *, lb: dict | None = None,
                 re_: dict | None = None) -> dict:
    """构造一个待投影的 bundle（`semantic_rules` 用 asdict 形态）。"""
    return {
        "semantic_rules": [asdict(r) for r in rules],
        "legal_boundary": dict(lb or {}),
        "response_expectation": dict(re_ or {}),
    }


def _dump(obj) -> str:
    """逐字节比对用的规范化 JSON。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


# ===========================================================================
# ① bundle 契约扩展：semantic_rules + bundle_schema_version="2.0"
# ===========================================================================

def test_bundle_contract_has_semantic_rules_and_version(monkeypatch):
    """assemble_bundle 的产物必须带 `semantic_rules` 与 `bundle_schema_version`。

    ★ D-6 起，语义规则参与生成是**默认关闭**的开关位
      （`core/fused/llm_ensemble.py`）。本用例测的是**开关开启**时的契约 ——
      ⇒ 显式打开开关，避免它随默认值变化而失去意义。
      「开关关闭 ⇒ 产物与 B-8 之前逐字节一致」由
      `tests/fused/test_semantic_rules_switch.py` 覆盖。
    """
    monkeypatch.setenv(SEMANTIC_RULES_ENV_KEY, "1")
    bundle = assemble_bundle([], protocol="rtsp")
    assert "semantic_rules" in bundle
    assert isinstance(bundle["semantic_rules"], list)
    assert bundle["bundle_schema_version"] == "2.0"
    assert BUNDLE_SCHEMA_VERSION == "2.0"


def test_bundle_accepts_explicit_semantic_rules():
    """显式传入语义规则 ⇒ bundle 的 `semantic_rules` 里有它，且**已被投影**。"""
    rule = _rule()
    bundle = assemble_bundle([], protocol="rtsp", semantic_rules=[rule])
    assert len(bundle["semantic_rules"]) == 1
    assert bundle["semantic_rules"][0]["rule_id"] == rule.rule_id
    # 两层嵌套：constraint 是**一层** dict
    assert isinstance(bundle["semantic_rules"][0]["constraint"], dict)
    # 已被投影进 legal_boundary
    assert "QNAME" in bundle["legal_boundary"]


def test_legacy_bundle_version_is_tolerated():
    """旧 bundle 没有 `bundle_schema_version` 键 ⇒ 读取方必须容忍（不得抛异常）。"""
    assert get_bundle_schema_version({}) == "1.0"
    assert get_bundle_schema_version({"bundle_schema_version": ""}) == "1.0"
    assert get_bundle_schema_version({"bundle_schema_version": "2.0"}) == "2.0"


# ===========================================================================
# ② 投影映射：SemanticRule → legal_boundary / response_expectation
# ===========================================================================

def test_project_maps_rule_into_both_buckets():
    """一条 authoritative 且可执行的规则 ⇒ 同时投到两桶。"""
    bundle = _bundle_with([_rule()])
    project_semantic_rules(bundle)

    lb = bundle["legal_boundary"]["QNAME"]
    assert len(lb) == 1
    entry = lb[0]
    assert entry["dim"] == "QNAME"
    assert entry["legal"] == "<= 63"          # le ⇒ 合法域 = 上界
    assert entry["illegal"] == "> 63"         # 非法域 = 越界
    assert entry["trigger"] == "protocol_error"

    re_list = bundle["response_expectation"]["QNAME"]
    assert len(re_list) == 1
    r_entry = re_list[0]
    assert r_entry["violation"] == "> 63"
    assert r_entry["expected_code"] == "4xx"  # protocol_error ⇒ 4xx 族
    assert r_entry["expected_behavior"] == "protocol_error"


@pytest.mark.parametrize(
    "operator, operand, legal, illegal",
    [
        ("le", ("63",), "<= 63", "> 63"),
        ("ge", ("1",), ">= 1", "< 1"),
        ("lt", ("10",), "< 10", ">= 10"),
        ("gt", ("0",), "> 0", "<= 0"),
        ("eq", ("7",), "= 7", "!= 7"),
        ("ne", ("7",), "!= 7", "= 7"),
        ("in", ("a", "b"), "属于 {a, b}", "不属于 {a, b}"),
        ("range", ("1", "63"), "介于 [1, 63] 之间", "超出 [1, 63] 区间"),
        ("present", (), "存在（必须出现）", "缺失（不得出现）"),
        # ★ 2026-11-07：`absent` 已移出本参数化用例 —— 投影层**拒收**该算子
        #   （语义不可靠，见 `_REJECT_ABSENT_OPERATOR`），故无法经
        #   `project_semantic_rules` 观察渲染结果。渲染映射本身仍作守卫，
        #   见下方 `test_absent_domain_mapping_preserved_but_not_projected`。
    ],
)
def test_operator_domain_mapping(operator, operand, legal, illegal):
    """operator/operand → 合法域/非法域 的反向渲染（协议无关）。"""
    constraint = _constraint(operator=operator, operand=tuple(operand))
    bundle = _bundle_with([_rule(constraint=constraint)])
    project_semantic_rules(bundle)
    entry = bundle["legal_boundary"]["QNAME"][0]
    assert entry["legal"] == legal
    assert entry["illegal"] == illegal


def test_absent_domain_mapping_preserved_but_not_projected():
    """★ 分离两件事：渲染映射**仍正确**，但投影层**拒收** `absent`。

    ★ 为什么拒收见 `rag_seedgen._REJECT_ABSENT_OPERATOR` 的实测依据：
      权威库 3 条 `absent` 全部语义错位（条件约束 / 内容约束 / 缺省描述被压成
      「字段不得出现」）⇒ 进 prompt 就是知识污染。
    ★ 保留映射是为了抽取器修好后可直接放开（届时补正例测试）。
    """
    legal, illegal = _render_domains("absent", (), "constant", None)
    assert legal == "缺失（不得出现）"
    assert illegal == "存在（出现即非法）"

    constraint = _constraint(operator="absent", operand=())
    bundle = _bundle_with([_rule(constraint=constraint)])
    project_semantic_rules(bundle)
    assert bundle["legal_boundary"] == {}
    assert bundle["response_expectation"] == {}


def test_grouping_prefers_target_field_over_subject_name():
    """归组键 = `target_field` 优先，缺省用 `subject_name`。"""
    rule = _rule(subject_name="QNAME")
    bundle = _bundle_with([rule])
    project_semantic_rules(bundle)
    assert list(bundle["legal_boundary"].keys()) == ["QNAME"]


def test_grouping_falls_back_to_subject_name():
    """`target_field` 为空 ⇒ 用 `subject_name` 归组。"""
    constraint = _constraint(target_field="", operator="present", operand=())
    bundle = _bundle_with([_rule(constraint=constraint, subject_name="Contact")])
    project_semantic_rules(bundle)
    assert list(bundle["legal_boundary"].keys()) == ["Contact"]
    assert bundle["legal_boundary"]["Contact"][0]["legal"] == "存在（必须出现）"


def test_projection_accepts_dataclass_form():
    """输入形态①：`SemanticRule` 本体（不必先 asdict）。"""
    bundle = {
        "semantic_rules": [_rule()],
        "legal_boundary": {},
        "response_expectation": {},
    }
    project_semantic_rules(bundle)
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"


def test_projection_accepts_asdict_form():
    """输入形态②：`dataclasses.asdict` 的两层嵌套 dict。"""
    bundle = _bundle_with([_rule()])
    project_semantic_rules(bundle)
    assert bundle["legal_boundary"]["QNAME"][0]["illegal"] == "> 63"


def test_knowledge_candidate_is_not_projected():
    """`KnowledgeCandidate` 没有可执行层 ⇒ **不投影**（结构上就投不了）。"""
    cand = KnowledgeCandidate(
        candidate_id="c-1",
        evidence=_evidence(),
        subject_type="header",
        subject_name="QNAME",
        raw_text="长度不应超过 63",
        convertible=False,
        reject_reason="field_unbound",
    )
    bundle = {
        "semantic_rules": [asdict(cand)],
        "legal_boundary": {},
        "response_expectation": {},
    }
    project_semantic_rules(bundle)
    assert bundle["legal_boundary"] == {}
    assert bundle["response_expectation"] == {}


def test_rule_without_expected_behavior_is_inferred():
    """★ 契约变更（2026-11-07）：缺 P 时按**确定性规则**推断，不再「只出 C」。

    旧契约是「缺 P ⇒ 留空、只出 C」（与 `norm.constraint_norm_to_facts` 同口径）。
    新契约：留空会让 prompt 里那条约束缺少「违反会被拒」的强度信息，而推断
    规则（客户端违反存在/取值约束 ⇒ 服务端应拒 ⇒ protocol_error）是协议无关、
    可审计的 ⇒ 填 `protocol_error` 并标 `rule_inferred`。
    ★ 指标引用必须按 `expected_behavior_source` 分档，不得把推断算成抽取。
    """
    constraint = _constraint(expected_behavior="")
    bundle = _bundle_with([_rule(constraint=constraint)])
    project_semantic_rules(bundle)
    lb = bundle["legal_boundary"]["QNAME"][0]
    assert lb["trigger"] == "protocol_error"
    assert lb["expected_behavior_source"] == "rule_inferred"
    re_entry = bundle["response_expectation"]["QNAME"][0]
    assert re_entry["expected_behavior"] == "protocol_error"
    assert re_entry["expected_code"] == "4xx"


def test_uninferable_operator_keeps_p_empty():
    """不可推断算子（`absent`）⇒ 解析函数返回空，不硬填。"""
    assert _resolve_expected_behavior({"expected_behavior": ""}, "absent") == ("", "")


# ===========================================================================
# ③ 幂等：投影两次 ⇒ 两桶逐字节相同
# ===========================================================================

def test_projection_is_idempotent():
    """★ 验收③：对同一 bundle 连续投影两次 ⇒ 两桶逐字节相同（json.dumps 比对）。"""
    bundle = _bundle_with([
        _rule("r-1"),
        _rule("r-2", constraint=_constraint(operator="ge", operand=("1",))),
        _rule("r-3", constraint=_constraint(operator="in",
                                            operand=("a", "b", "c"))),
    ])
    project_semantic_rules(bundle)
    lb_once = _dump(bundle["legal_boundary"])
    re_once = _dump(bundle["response_expectation"])

    project_semantic_rules(bundle)
    assert _dump(bundle["legal_boundary"]) == lb_once
    assert _dump(bundle["response_expectation"]) == re_once

    # 再投影一次仍然不变（不是「碰巧第二次相同」）
    project_semantic_rules(bundle)
    assert _dump(bundle["legal_boundary"]) == lb_once
    assert _dump(bundle["response_expectation"]) == re_once


def test_projection_is_idempotent_with_existing_facts_entries():
    """既有 facts 条目在场时，幂等同样成立（不重复追加）。"""
    lb = {"QNAME": [{"dim": "QNAME", "legal": "旧 facts 条目",
                     "illegal": "旧非法域", "trigger": "旧 trigger"}]}
    bundle = _bundle_with([_rule()], lb=lb)
    project_semantic_rules(bundle)
    lb_once = _dump(bundle["legal_boundary"])

    project_semantic_rules(bundle)
    assert _dump(bundle["legal_boundary"]) == lb_once
    # 既有 facts 条目仍在（投影是**新增**来源，不替换）
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "旧 facts 条目"
    assert len(bundle["legal_boundary"]["QNAME"]) == 2


# ===========================================================================
# ④ 旧 bundle 兼容：无 semantic_rules 键 ⇒ 空操作
# ===========================================================================

def test_legacy_bundle_without_semantic_rules_is_noop():
    """★ 验收④：无 `semantic_rules` 键 ⇒ 不抛异常且两桶**一个字节都不变**。"""
    legacy = {
        "legal_boundary": {"QNAME": [{"dim": "QNAME", "legal": "L1",
                                      "illegal": "I1", "trigger": "T1"}]},
        "response_expectation": {"QNAME": [{"violation": "V1",
                                            "expected_code": "400",
                                            "expected_behavior": "B1"}]},
    }
    before = _dump(legacy)
    out = project_semantic_rules(legacy)      # ★ 不得抛异常
    assert out is legacy
    assert _dump(legacy) == before


def test_legacy_bundle_without_semantic_rules_gains_no_keys():
    """旧 bundle 连 `legal_boundary` 键都没有时 ⇒ 投影不得凭空造出键。"""
    legacy = {"methods": {}}
    out = project_semantic_rules(legacy)
    assert out == {"methods": {}}
    assert "legal_boundary" not in legacy
    assert "response_expectation" not in legacy


def test_empty_semantic_rules_is_noop():
    """`semantic_rules` 为空列表 ⇒ 同样是空操作。"""
    legacy = {
        "semantic_rules": [],
        "legal_boundary": {"X": [{"dim": "X", "legal": "L", "illegal": "I"}]},
        "response_expectation": {},
    }
    before = _dump(legacy)
    project_semantic_rules(legacy)
    assert _dump(legacy) == before


# ===========================================================================
# 过滤：constraint is None / rule_state != authoritative ⇒ 不投影
# ===========================================================================

def test_rule_without_constraint_is_not_projected():
    """★ `constraint is None`（不可转换）⇒ **不进两桶**。"""
    rule = SemanticRule(
        rule_id="r-none",
        evidence=_evidence(),
        constraint=None,
        subject_type="header",
        subject_name="QNAME",
        rule_state="authoritative",
        supersedes=(),
        model_confidence=0.5,
        validated=True,
    )
    bundle = _bundle_with([rule])
    project_semantic_rules(bundle)
    assert bundle["legal_boundary"] == {}
    assert bundle["response_expectation"] == {}


@pytest.mark.parametrize("state", ["candidate", "revoked", "feedback"])
def test_non_authoritative_rule_states_are_not_projected(state):
    """★ `rule_state != "authoritative"` ⇒ **不进权威桶**（四库隔离同口径）。"""
    bundle = _bundle_with([_rule(rule_state=state)])
    project_semantic_rules(bundle)
    assert bundle["legal_boundary"] == {}
    assert bundle["response_expectation"] == {}


def test_only_authoritative_rules_survive_mixed_input():
    """混合输入 ⇒ 只有 authoritative 的那条被投影。"""
    bundle = _bundle_with([
        _rule("r-ok", rule_state="authoritative"),
        _rule("r-cand", rule_state="candidate"),
        _rule("r-revoked", rule_state="revoked"),
        _rule("r-fb", rule_state="feedback"),
    ])
    project_semantic_rules(bundle)
    assert list(bundle["legal_boundary"].keys()) == ["QNAME"]
    assert len(bundle["legal_boundary"]["QNAME"]) == 1


# ===========================================================================
# 合并语义：投影是**新增**来源，旧 facts 来源保留可用
# ===========================================================================

def test_projection_keeps_facts_source_entries():
    """投影条目**追加**在既有 facts 条目之后 ⇒ 旧来源保留可用。"""
    lb = {"QNAME": [{"dim": "QNAME", "legal": "旧", "illegal": "旧非法",
                     "trigger": "旧 trigger"}]}
    bundle = _bundle_with([_rule()], lb=lb)
    project_semantic_rules(bundle)
    entries = bundle["legal_boundary"]["QNAME"]
    assert len(entries) == 2
    assert entries[0]["legal"] == "旧"
    assert entries[1]["legal"] == "<= 63"


def test_projection_dedups_identical_entries():
    """完全相同的投影条目只保留一份（去重 ⇒ 幂等）。"""
    bundle = _bundle_with([_rule("r-1"), _rule("r-1")])
    project_semantic_rules(bundle)
    assert len(bundle["legal_boundary"]["QNAME"]) == 1


# ===========================================================================
# ⑤ 回归护栏：boundary_probe.py / strategy.py 零改动仍能工作
# ===========================================================================

def test_boundary_probe_still_consumes_projected_bundle():
    """★ 验收⑤：`boundary_probe.derive_constraint_candidates` 零改动仍消费投影桶。"""
    bundle = _bundle_with([_rule()])
    project_semantic_rules(bundle)
    cands = derive_constraint_candidates(bundle)
    assert len(cands) == 2
    assert [label for label, _ in cands] == ["legal", "illegal"]
    # 非法候选携带超长字段值（违反约束）
    illegal = cands[1][1]
    assert any("A" * 300 == m.headers.get("QNAME") for m in illegal.messages)


def test_strategy_still_renders_projected_constraints():
    """★ 验收⑤：`strategy.render_attack_prompt` 零改动仍渲染投影出来的约束。"""
    bundle = _bundle_with([_rule()])
    project_semantic_rules(bundle)
    # 补齐 strategy 渲染所需的其他桶（既有契约，不在 B-8 范围内）
    bundle.update({
        "methods": {"DESCRIBE": {"state_changing": False}},
        "transitions": [],
        "required_headers": {},
        "headers": {},
        "security": [],
        "precondition": {},
        "session_header": {},
        "url_template": {},
    })
    _system, user = render_attack_prompt(bundle, [], protocol="rtsp")
    assert "QNAME" in user
    assert "合法「<= 63」" in user
    assert "非法「> 63」" in user


def test_render_constraints_format_unchanged():
    """渲染格式不变（下游 strategy 侧行为不得变）。"""
    bundle = _bundle_with([_rule()])
    project_semantic_rules(bundle)
    from core.fused.downstream.rag_seedgen import _render_constraints
    text = _render_constraints(bundle)
    assert text == (
        "[字段约束（来自 RFC 规范：合法域/非法域，生成时字段取值须落在合法域、"
        "接近边界但不越界）]\n"
        "  QNAME: 合法「<= 63」 | 非法「> 63」 → protocol_error"
    )


def test_existing_derived_bundle_still_loads():
    """回归护栏：真实 facts 组装出的 bundle 两桶仍是 dict[str, list]。"""
    bundle = assemble_bundle([], protocol="rtsp")
    assert isinstance(bundle["legal_boundary"], dict)
    assert isinstance(bundle["response_expectation"], dict)
    assert all(isinstance(v, list) for v in bundle["legal_boundary"].values())
    assert all(isinstance(v, list)
               for v in bundle["response_expectation"].values())


# ===========================================================================
# 端到端：从 authoritative 规则库自动装载 → 投影
# ===========================================================================

def _isolate_per_source(tmp_path, monkeypatch):
    """把 `paths.per_source_root` 指到 tmp_path（**不污染仓库的 derived/**）。"""
    from core import paths
    monkeypatch.setattr(
        paths, "per_source_root",
        lambda protocol: tmp_path / "per_source" / protocol.lower(),
    )
    return tmp_path


def test_load_semantic_rules_reads_authoritative_library(tmp_path, monkeypatch):
    """自动装载只读 authoritative 库；候选/撤销/反馈三库**读不到**。"""
    from core.fused.downstream import rule_store
    _isolate_per_source(tmp_path, monkeypatch)

    rule_store.save_rules("rtsp", [_rule("r-auth")])
    rules = load_semantic_rules("rtsp")
    assert len(rules) == 1
    assert rules[0]["rule_id"] == "r-auth"
    # 两层嵌套：constraint 是一层 dict
    assert isinstance(rules[0]["constraint"], dict)
    assert isinstance(rules[0]["evidence"], dict)

    # 其它三库落盘 ⇒ 装载结果**不变**（四库隔离）
    rule_store.save_candidates("rtsp", [KnowledgeCandidate(
        candidate_id="c-1", evidence=_evidence(), subject_type="header",
        subject_name="QNAME", raw_text="x", convertible=False,
        reject_reason="field_unbound")])
    rule_store.save_revoked("rtsp", [_rule("r-revoked", rule_state="revoked")])
    rule_store.record_feedback("rtsp", "probe:x", {"priority_score": 1.0})
    assert len(load_semantic_rules("rtsp")) == 1


def test_assemble_bundle_auto_loads_and_projects(tmp_path, monkeypatch):
    """端到端：assemble_bundle 自动读权威库 ⇒ `semantic_rules` 有内容且**已投影**。

    ★ 自动装载属于「开关开启」路径（D-6：语义规则参与生成默认关闭）⇒ 显式打开。
    """
    from core.fused.downstream import rule_store
    _isolate_per_source(tmp_path, monkeypatch)
    monkeypatch.setenv(SEMANTIC_RULES_ENV_KEY, "1")

    rule_store.save_rules("rtsp", [_rule("r-auth")])
    bundle = assemble_bundle([], protocol="rtsp")
    assert len(bundle["semantic_rules"]) == 1
    assert bundle["bundle_schema_version"] == "2.0"
    # 已被投影进两桶
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"
    assert bundle["response_expectation"]["QNAME"][0]["expected_code"] == "4xx"


def test_load_semantic_rules_returns_empty_when_library_absent(tmp_path,
                                                                monkeypatch):
    """权威库不存在 ⇒ 返回空列表（B 阶段前语义库尚未落地，不是错误）。"""
    _isolate_per_source(tmp_path, monkeypatch)
    assert load_semantic_rules("rtsp") == []
