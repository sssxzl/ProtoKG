"""tests/fused/test_semantic_rules_switch.py —— D-6：语义规则参与生成的可关闭开关位。

对应 docs/rfc_source_bcd_roadmap.md §5.2 任务表 **D-6**（文档任务号 D6）：
"**投票保持可关闭** | 同上 + `scripts/build_hub.py` | 默认关闭；关闭时 bundle 的
`semantic_rules` **不参与**任何生成 | 单测：关闭开关 → `semantic_rules` 消费路径
0 次调用；`rules_only` 模式产物与 B-8 之前逐字节一致"。

★ D-6 的核心语义（「关闭」到底关掉了什么）：

  · 「开关关闭」= **不自动引入语义规则** —— `assemble_bundle` 不主动去读规则库，
    消费路径（`load_semantic_rules` + `project_semantic_rules`）**0 次调用**，
    产物**不含** `semantic_rules` / `bundle_schema_version` 两个新键
    ⇒ **与 B-8 之前的 bundle 逐字节一致**（默认路径不得被 B-8 悄悄改变）。
  · 「显式传入 `semantic_rules=`」= **调用方的显式授权**（程序化 API 层面的直接
    输入），**优先于开关** —— 照常装载 + 投影，**不得**静默丢弃（B-8 契约）。

本文件只测 `core/fused/llm_ensemble.py`（开关位）+ `rag_seedgen.assemble_bundle`
（行为矩阵）+ `scripts/build_hub.py`（CLI 暴露）。

★ 本文件**不改动** B-8 的契约文件 `tests/fused/test_bundle_projection.py`（只读）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.fused.downstream import rag_seedgen
from core.fused.downstream.rag_seedgen import assemble_bundle
from core.fused.llm_ensemble import (
    ENV_KEY,
    VOTING_ENV_KEY,
    reset_semantic_rules_enabled,
    reset_voting_enabled,
    semantic_rules_enabled,
    set_semantic_rules_enabled,
    voting_enabled,
)
from core.fused.semantic import (
    EvidenceAnchor,
    ExecutableConstraint,
    SemanticRule,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 合成协议名（kb/ 下不存在 ⇒ profile 兜底为空 ⇒ 产物只由本文件的 views 决定）。
PROTO = "d6proto"


# ===========================================================================
# 夹具：开关状态隔离（进程内覆盖是**全局**的 ⇒ 必须每个用例后复位）
# ===========================================================================

@pytest.fixture(autouse=True)
def _isolate_switch(monkeypatch):
    """每个用例前后都清掉进程内覆盖与环境变量 ⇒ 用例之间零污染。"""
    monkeypatch.delenv(ENV_KEY, raising=False)
    monkeypatch.delenv(VOTING_ENV_KEY, raising=False)
    reset_semantic_rules_enabled()
    reset_voting_enabled()
    yield
    reset_semantic_rules_enabled()
    reset_voting_enabled()


@pytest.fixture()
def isolated_library(tmp_path, monkeypatch):
    """把权威规则库（`derived/per_source/<proto>/rfc/semantic/`）指向 tmp_path。"""
    from core import paths

    monkeypatch.setattr(
        paths, "per_source_root",
        lambda protocol: tmp_path / "per_source" / str(protocol).lower(),
    )
    return tmp_path


# ===========================================================================
# 合成件：fact view（形状与 core.fused.export.get_fact_view 一致）
# ===========================================================================

def _view(aspect: str, subject_type: str, subject_name: str, data,
          *, protocol: str = PROTO) -> dict:
    """构造一个最小 fact view。"""
    return {
        "fact_key": {
            "protocol": protocol,
            "version": "1.0",
            "subject": {"type": subject_type, "name": subject_name,
                        "qualifiers": {}, "path": []},
            "aspect": aspect,
            "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": "c-1",
            "fact_id": f"f-{subject_name}",
            "value": {"type": "dict", "data": data},
            "epistemic_type": "normative",
            "authority": "rfc",
            "evidence": [],
            "confidence": 1.0,
        }],
    }


def _views() -> list[dict]:
    """本文件统一使用的 facts 视图（一个方法 + 一个字段约束）。"""
    return [
        _view("definition", "method", "SETUP", {"text": "SETUP 的合成定义"}),
        _view("legal_boundary", "header", "Content-Length",
              {"legal": "0..65535", "illegal": ">65535"}),
    ]


def _rule(rule_id: str = "r-qname-63") -> SemanticRule:
    """构造一条 authoritative 且可执行的语义规则（QNAME 长度 ≤ 63）。"""
    return SemanticRule(
        rule_id=rule_id,
        evidence=EvidenceAnchor(
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
        ),
        constraint=ExecutableConstraint(
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
        ),
        subject_type="header",
        subject_name="QNAME",
        rule_state="authoritative",
        supersedes=(),
        model_confidence=0.93,
        validated=True,
    )


def _dump(obj) -> str:
    """逐字节比对用的规范化 JSON。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


# ===========================================================================
# ① 默认关闭（无环境变量、无进程内覆盖 ⇒ False）
# ===========================================================================

def test_default_is_disabled():
    """★ 验收①：默认**关闭** —— 没有任何配置时开关为 False。"""
    assert semantic_rules_enabled() is False


def test_voting_default_is_disabled():
    """投票开关同样默认关闭（§6：在 B-10 判定「收益成立」之前不应投入）。"""
    assert voting_enabled() is False


# ===========================================================================
# ② 环境变量判定（1/true/yes/on ⇒ True；其它一切 ⇒ False）
# ===========================================================================

@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "True", "yes", "YES",
                                 "on", "ON", " 1 "])
def test_env_truthy_values(monkeypatch, raw):
    """★ 验收②：``1/true/yes/on``（大小写不敏感）⇒ True。"""
    monkeypatch.setenv(ENV_KEY, raw)
    assert semantic_rules_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "NO", "off",
                                 "OFF", "", "2", "enabled", "乱填"])
def test_env_falsy_values(monkeypatch, raw):
    """★ 验收②：**其它一切**（含未设置）⇒ False。"""
    monkeypatch.setenv(ENV_KEY, raw)
    assert semantic_rules_enabled() is False


def test_env_is_read_on_every_call(monkeypatch):
    """环境变量**每次调用时**判定（不在 import 时缓存成常量）。"""
    assert semantic_rules_enabled() is False
    monkeypatch.setenv(ENV_KEY, "1")
    assert semantic_rules_enabled() is True
    monkeypatch.delenv(ENV_KEY)
    assert semantic_rules_enabled() is False


def test_voting_env_var(monkeypatch):
    """投票开关走同机制（环境变量 `PROTORAG_VOTING`）。"""
    monkeypatch.setenv(VOTING_ENV_KEY, "on")
    assert voting_enabled() is True
    monkeypatch.setenv(VOTING_ENV_KEY, "off")
    assert voting_enabled() is False


# ===========================================================================
# ③ 进程内覆盖：set / reset 语义
# ===========================================================================

def test_process_override_wins_over_env(monkeypatch):
    """★ 验收③：进程内覆盖优先级**高于**环境变量。"""
    monkeypatch.setenv(ENV_KEY, "1")
    set_semantic_rules_enabled(False)
    assert semantic_rules_enabled() is False
    set_semantic_rules_enabled(True)
    assert semantic_rules_enabled() is True


def test_set_none_clears_override_back_to_env(monkeypatch):
    """★ 验收③：`set_semantic_rules_enabled(None)` ⇒ 清除覆盖，回到环境变量判定。"""
    monkeypatch.setenv(ENV_KEY, "1")
    set_semantic_rules_enabled(False)
    assert semantic_rules_enabled() is False
    set_semantic_rules_enabled(None)
    assert semantic_rules_enabled() is True


def test_reset_returns_to_env_judgement(monkeypatch):
    """★ 验收③：`reset_semantic_rules_enabled()` ⇒ 回到环境变量判定。"""
    set_semantic_rules_enabled(True)
    assert semantic_rules_enabled() is True
    reset_semantic_rules_enabled()
    assert semantic_rules_enabled() is False


def test_set_does_not_touch_environment(monkeypatch):
    """进程内覆盖**不写全局环境变量**（避免污染其它进程/用例）。"""
    monkeypatch.delenv(ENV_KEY, raising=False)
    set_semantic_rules_enabled(True)
    assert ENV_KEY not in os.environ


# ===========================================================================
# 规格冲突留痕：B-8 只读契约的默认路径断言 vs D-6 的「默认关闭」
# ===========================================================================

def test_b8_contract_semantics_hold_when_switch_is_on(isolated_library):
    """★ B-8 契约所验证的**能力**在开关 ON 下**完好**（D-6 未削弱 B-8）。

    B-8 的只读契约文件 `tests/fused/test_bundle_projection.py` 有两条用例
    断言的是**默认路径**的旧行为（未显式传参 ⇒ 产物带两个新键 + 自动装载
    权威库 + 投影两桶）。D-6 把「默认」改成**关闭**（路线图 D-6：
    "默认关闭；关闭时 bundle 的 `semantic_rules` 不参与任何生成"），
    ⇒ 那两条断言与 D-6 语义**正面冲突**（本文件 §④/⑤ 已锁定 D-6 侧语义）。

    本用例在**开关 ON**（= B-8 契约所描述的「能力路径」）下复现那两条
    断言的全部内容 ⇒ 证明 D-6 只改了**默认**，**没有削弱 B-8 的能力**。
    """
    from core.fused.downstream import rule_store

    rule_store.save_rules(PROTO, [_rule("r-auth")])
    set_semantic_rules_enabled(True)

    bundle = assemble_bundle(_views(), PROTO)

    # ① 契约形态：`semantic_rules` 键存在且是 list，`bundle_schema_version`
    #    == "2.0"（B-8 用例 1 的全部断言）。
    assert "semantic_rules" in bundle
    assert isinstance(bundle["semantic_rules"], list)
    assert bundle["bundle_schema_version"] == "2.0"

    # ② 自动装载权威库 + 投影两桶（B-8 用例 2 的全部断言）。
    assert len(bundle["semantic_rules"]) == 1
    assert bundle["semantic_rules"][0]["rule_id"] == "r-auth"
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"
    assert bundle["response_expectation"]["QNAME"][0]["expected_code"] == "4xx"


# ===========================================================================
# ④ 开关 OFF + 未显式传参 ⇒ 产物不含两个新键
# ===========================================================================

def test_off_without_explicit_rules_omits_new_keys():
    """★ 验收④：开关 OFF + 未显式传参 ⇒ **没有** `semantic_rules` /
    **没有** `bundle_schema_version` 两个键。"""
    bundle = assemble_bundle(_views(), PROTO)
    assert "semantic_rules" not in bundle
    assert "bundle_schema_version" not in bundle


# ===========================================================================
# ⑤ 开关 OFF ⇒ 消费路径 0 次调用
# ===========================================================================

def test_off_consumption_path_is_never_called(monkeypatch):
    """★ 验收⑤：开关 OFF ⇒ `load_semantic_rules` 与 `project_semantic_rules`
    **各 0 次调用**（消费路径完全不被触发）。"""
    calls = {"load": 0, "project": 0}

    def _fake_load(protocol="rtsp"):
        calls["load"] += 1
        return []

    def _fake_project(bundle):
        calls["project"] += 1
        return bundle

    monkeypatch.setattr(rag_seedgen, "load_semantic_rules", _fake_load)
    monkeypatch.setattr(rag_seedgen, "project_semantic_rules", _fake_project)

    bundle = assemble_bundle(_views(), PROTO)

    assert calls == {"load": 0, "project": 0}
    assert "semantic_rules" not in bundle


def test_off_does_not_touch_authoritative_library(isolated_library):
    """★ 验收⑤（加强）：开关 OFF ⇒ 连规则库文件都不该被创建/读取。"""
    from core.fused.downstream import rule_store

    rule_store.save_rules(PROTO, [_rule("r-auth")])
    lib = rule_store.library_path(PROTO, "authoritative")
    assert lib.is_file()

    bundle = assemble_bundle(_views(), PROTO)

    assert "semantic_rules" not in bundle
    # 规则没被引入 ⇒ 两桶里也不该出现投影出来的 QNAME
    assert "QNAME" not in bundle["legal_boundary"]
    assert "QNAME" not in bundle["response_expectation"]


# ===========================================================================
# ⑥ 与 B-8 之前逐字节一致
# ===========================================================================

def test_off_bundle_is_byte_identical_to_pre_b8(monkeypatch, isolated_library):
    """★ 验收⑥：开关 OFF ⇒ 产物与「B-8 之前形态」**逐字节一致**。

    判据（与任务规格一致）：
      ① 产物里**确实不含** `semantic_rules` / `bundle_schema_version` 两个键；
      ② 剔除这两个键后，剩下的部分必须与「同 views 但**不调**
         `project_semantic_rules`」的产物**逐字节相同**。
    """
    from core.fused.downstream import rule_store

    rule_store.save_rules(PROTO, [_rule("r-auth")])

    # ① 开关 OFF 的产物：不含两个新键。
    off_bundle = assemble_bundle(_views(), PROTO)
    assert "semantic_rules" not in off_bundle
    assert "bundle_schema_version" not in off_bundle

    # ② 参考形态：同 views、同一份规则，但**不调** project_semantic_rules
    #    （= B-8 之前的投影行为）⇒ 剔除两个新键后应与 OFF 产物逐字节相同。
    def _no_project(bundle):
        return bundle

    monkeypatch.setattr(rag_seedgen, "project_semantic_rules", _no_project)
    set_semantic_rules_enabled(True)
    ref_bundle = assemble_bundle(_views(), PROTO)
    assert "semantic_rules" in ref_bundle          # 参考形态确实带了新键
    assert "bundle_schema_version" in ref_bundle
    stripped = {k: v for k, v in ref_bundle.items()
                if k not in ("semantic_rules", "bundle_schema_version")}

    assert _dump(stripped) == _dump(off_bundle)


def test_on_bundle_actually_projects(isolated_library):
    """对照：开关 ON ⇒ 投影**真的发生**（否则上一条的「逐字节一致」是空转）。"""
    from core.fused.downstream import rule_store

    rule_store.save_rules(PROTO, [_rule("r-auth")])
    set_semantic_rules_enabled(True)

    bundle = assemble_bundle(_views(), PROTO)

    assert "QNAME" in bundle["legal_boundary"]
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"
    assert "QNAME" in bundle["response_expectation"]


# ===========================================================================
# ⑦ 开关 ON ⇒ 自动装载 + 两桶投影 + 契约版本 2.0
# ===========================================================================

def test_on_loads_and_projects(isolated_library):
    """★ 验收⑦：开关 ON + 未显式传参 ⇒ `semantic_rules` 键存在、
    `bundle_schema_version == "2.0"`、两桶被投影。"""
    from core.fused.downstream import rule_store

    rule_store.save_rules(PROTO, [_rule("r-auth")])
    set_semantic_rules_enabled(True)

    bundle = assemble_bundle(_views(), PROTO)

    assert len(bundle["semantic_rules"]) == 1
    assert bundle["semantic_rules"][0]["rule_id"] == "r-auth"
    assert bundle["bundle_schema_version"] == "2.0"
    # 两桶被投影（QNAME 是规则的目标字段）
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"
    assert bundle["legal_boundary"]["QNAME"][0]["illegal"] == "> 63"
    assert bundle["response_expectation"]["QNAME"][0]["expected_code"] == "4xx"


def test_on_with_empty_library_still_has_contract_keys(isolated_library):
    """开关 ON + 规则库为空 ⇒ 键仍在（契约形态不因库空而消失）。"""
    set_semantic_rules_enabled(True)
    bundle = assemble_bundle(_views(), PROTO)
    assert bundle["semantic_rules"] == []
    assert bundle["bundle_schema_version"] == "2.0"


# ===========================================================================
# ⑧ 显式传参（无论开关状态）⇒ 照常投影（B-8 契约不被破坏）
# ===========================================================================

def test_explicit_rules_are_authorized_even_when_switch_off():
    """★ 验收⑧：开关 OFF + **显式传参** ⇒ 键存在且两桶被投影。"""
    bundle = assemble_bundle(_views(), PROTO, semantic_rules=[_rule("r-auth")])
    assert len(bundle["semantic_rules"]) == 1
    assert bundle["bundle_schema_version"] == "2.0"
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"
    assert bundle["response_expectation"]["QNAME"][0]["expected_code"] == "4xx"


def test_explicit_rules_are_authorized_even_when_switch_on(isolated_library):
    """★ 验收⑧：开关 ON + 显式传参 ⇒ 用**传入值**（不去读规则库）。"""
    from core.fused.downstream import rule_store

    rule_store.save_rules(PROTO, [_rule("r-other")])
    set_semantic_rules_enabled(True)

    bundle = assemble_bundle(_views(), PROTO, semantic_rules=[_rule("r-auth")])

    assert [r["rule_id"] for r in bundle["semantic_rules"]] == ["r-auth"]
    assert bundle["legal_boundary"]["QNAME"][0]["legal"] == "<= 63"


def test_explicit_empty_list_is_authorization():
    """显式传空列表也是**显式授权** ⇒ 两键存在（内容为空）。"""
    bundle = assemble_bundle(_views(), PROTO, semantic_rules=[])
    assert "semantic_rules" in bundle
    assert bundle["semantic_rules"] == []
    assert bundle["bundle_schema_version"] == "2.0"


# ===========================================================================
# ⑨ CLI 暴露开关位
# ===========================================================================

def test_build_hub_help_exposes_switch():
    """★ 验收⑨：`scripts/build_hub.py --help` 里能看到 `--enable-semantic-rules`。"""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_hub.py"), "--help"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--enable-semantic-rules" in proc.stdout


def test_build_hub_switch_is_off_by_default():
    """★ 验收⑨：CLI 开关**默认关闭** ⇒ 不带该参数时开关仍为关闭。"""
    from scripts import build_hub

    # 用一个不存在的协议名提前退出（不跑构建、不写 derived/）
    rc = build_hub.main(["--protocol", "__no_such_protocol__"])
    assert rc == 2                      # 协议不存在 ⇒ 早退
    assert semantic_rules_enabled() is False


def test_build_hub_enable_flag_turns_switch_on(monkeypatch):
    """★ 验收⑨：带 `--enable-semantic-rules` ⇒ 开关被置为开启（进程内 + 环境变量）。"""
    from scripts import build_hub

    # ★ build_hub 会**直接写** os.environ ⇒ 先用 monkeypatch 记录原值，
    #   让 monkeypatch 在用例结束时把环境变量复原（避免污染其它用例）。
    monkeypatch.delenv(ENV_KEY, raising=False)

    # 用一个不存在的协议名提前退出（不跑构建、不写 derived/）
    rc = build_hub.main(["--protocol", "__no_such_protocol__",
                         "--enable-semantic-rules"])
    assert rc == 2                      # 协议不存在 ⇒ 早退
    assert semantic_rules_enabled() is True
    assert os.environ.get(ENV_KEY) == "1"
