# -*- coding: utf-8 -*-
"""tests/fused/test_response_oracle.py —— 三轴结果模型 + 判定顺序 + 期望响应词表防漂移。

覆盖 C 阶段的四个修正点：

  · **C-1 三轴结果模型** —— ``ProtocolOutcome`` / ``TransportOutcome`` /
    ``ProcessHealth`` 的取值集合必须与 ``docs/实施/路线与里程碑/RFC源知识抽取改造方案.md`` §3.5
    （:646-666）**逐项相等**。本文件把文档取值**硬编码**在测试里（而不是运行时
    去解析文档），一旦有人改了枚举、或改了文档而没改枚举，单测立刻红 ——
    这正是「防漂移」的目的。

  · **C-2 判定顺序：UNKNOWN+TIMEOUT 最先** —— ``health=UNKNOWN`` + ``trans=TIMEOUT``
    且协议结果与期望不符时，必须返回 ``inconclusive``，**不能**返回
    ``semantic_deviation``（改进v2 问题⑦的核心误判）。

  · **C-3 EXITED 需判别** —— 退出码 0 + 正常收尾 ⇒ ``target_exited_normally``；
    退出码非 0 / 有 sanitizer 报告 ⇒ ``crash``。

  · **C-4 reset/close 不进 crash** —— ``trans=RESET/CLOSE`` 且进程健康 ⇒
    ``connection_aborted``，**不是** ``crash``。

  · **C-5 timeout/crash 不作协议响应期望** —— ``profiles/<协议>/rfc_config.json``
    的 ``expected_response_classes`` 必须**恰好**是 4 类协议语义结果，
    **不得**混入 ``timeout`` / ``crash``（它们分别属于传输层与进程层，不是协议响应期望）。
    断言**真的读取三个协议的真实配置**并逐项比对，不 mock、不读 ``derived/`` 下的
    实验产物（那些会随实验重生成而变）。

★ 本文件**只读**：不改任何生产代码、不改 ```` 下的配置。
"""
from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fused.downstream.response_oracle import (  # noqa: E402
    FEEDBACK_KINDS,
    PROCESS_HEALTH_VALUES,
    PROTOCOL_OUTCOME_VALUES,
    TRANSPORT_OUTCOME_VALUES,
    ExecResult,
    Feedback,
    ProcessHealth,
    ProtocolOutcome,
    TransportOutcome,
    classify_protocol_outcome,
    classify_transport_outcome,
    close_loop,
    probe_process_health,
)

# ===========================================================================
# 常量：文档 §3.5（:646-666）的权威取值（硬编码 = 防漂移锚点）
# ===========================================================================

#: 协议层结果：文档 §3.5 的 4 项 —— **只有协议语义结果**。
EXPECTED_PROTOCOL_OUTCOMES = {
    "success",
    "protocol_error",
    "application_error",
    "silence",
}

#: 传输层结果：文档 §3.5 的 4 项。
EXPECTED_TRANSPORT_OUTCOMES = {
    "response",
    "reset",
    "close",
    "timeout",
}

#: 进程健康：文档 §3.5 的 5 项。
EXPECTED_PROCESS_HEALTH = {
    "alive",
    "exited",
    "restarted",
    "sanitizer_failure",
    "unknown",
}

#: 枚举成员名 → 取值（文档 §3.5 逐项抄录，含成员名本身）。
EXPECTED_PROTOCOL_MEMBERS = {
    "SUCCESS": "success",
    "PROTOCOL_ERROR": "protocol_error",
    "APPLICATION_ERROR": "application_error",
    "SILENCE": "silence",
}

EXPECTED_TRANSPORT_MEMBERS = {
    "RESPONSE": "response",
    "RESET": "reset",
    "CLOSE": "close",
    "TIMEOUT": "timeout",
}

EXPECTED_PROCESS_HEALTH_MEMBERS = {
    "ALIVE": "alive",
    "EXITED": "exited",
    "RESTARTED": "restarted",
    "SANITIZER_FAILURE": "sanitizer_failure",
    "UNKNOWN": "unknown",
}

#: 受 C-5 约束的三个协议。
PROTOCOLS = ("rtsp", "sip", "smtp")

#: ``rfc_config.json`` 相对项目根的路径模板。
RFC_CONFIG_TEMPLATE = "profiles/{protocol}/rfc_config.json"

#: 绝不允许出现在 ``expected_response_classes`` 里的词（传输层/进程层，不是协议响应）。
FORBIDDEN_RESPONSE_CLASSES = {"timeout", "crash"}


def _load_rfc_config(protocol: str) -> dict:
    """读取某协议的真实 ``rfc_config.json``。

    配置文件缺失时**直接断言失败**（不 skip）：C-5 的保证依赖真实配置存在，
    悄悄跳过等于把保证丢掉。

    Args:
        protocol: 协议名（``rtsp`` / ``sip`` / ``smtp``）。

    Returns:
        解析后的配置字典。
    """
    path = ROOT / RFC_CONFIG_TEMPLATE.format(protocol=protocol)
    assert path.is_file(), f"缺少 {path} —— C-5 断言需要真实协议配置"
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_response_classes(protocol: str) -> list:
    """取某协议 ``rfc_config.json`` 里的 ``expected_response_classes``。"""
    config = _load_rfc_config(protocol)
    classes = config.get("expected_response_classes")
    assert classes is not None, \
        f"{protocol}: rfc_config.json 缺少 expected_response_classes"
    assert isinstance(classes, list), \
        f"{protocol}: expected_response_classes 必须是列表，实为 {type(classes).__name__}"
    return classes


# ===========================================================================
# C-1：三轴枚举的取值集合必须与文档 §3.5 逐项相等
# ===========================================================================


def test_protocol_outcome_values_match_doc() -> None:
    """协议层取值集合与文档 §3.5 逐项相等。"""
    assert {m.value for m in ProtocolOutcome} == EXPECTED_PROTOCOL_OUTCOMES


def test_transport_outcome_values_match_doc() -> None:
    """传输层取值集合与文档 §3.5 逐项相等。"""
    assert {m.value for m in TransportOutcome} == EXPECTED_TRANSPORT_OUTCOMES


def test_process_health_values_match_doc() -> None:
    """进程健康取值集合与文档 §3.5 逐项相等。"""
    assert {m.value for m in ProcessHealth} == EXPECTED_PROCESS_HEALTH


def test_enum_member_names_match_doc() -> None:
    """成员名与取值同时逐项相等（防止只改名字不改语义或反之）。"""
    assert {m.name: m.value for m in ProtocolOutcome} == EXPECTED_PROTOCOL_MEMBERS
    assert {m.name: m.value for m in TransportOutcome} == EXPECTED_TRANSPORT_MEMBERS
    assert {m.name: m.value for m in ProcessHealth} == EXPECTED_PROCESS_HEALTH_MEMBERS


def test_enums_are_str_mixin() -> None:
    """三个枚举都是 ``str, Enum``（可直接与裸字符串比较、可 JSON 序列化）。"""
    assert ProtocolOutcome.SUCCESS == "success"
    assert TransportOutcome.RESET == "reset"
    assert ProcessHealth.UNKNOWN == "unknown"
    for enum_cls in (ProtocolOutcome, TransportOutcome, ProcessHealth):
        assert issubclass(enum_cls, str)
        assert issubclass(enum_cls, Enum)


def test_derived_value_sets_match_enums() -> None:
    """派生的取值集合常量与枚举本身一致（常量由枚举派生，本测试防手工改坏）。"""
    assert PROTOCOL_OUTCOME_VALUES == {m.value for m in ProtocolOutcome}
    assert TRANSPORT_OUTCOME_VALUES == {m.value for m in TransportOutcome}
    assert PROCESS_HEALTH_VALUES == {m.value for m in ProcessHealth}


def test_timeout_and_crash_are_not_protocol_outcomes() -> None:
    """timeout/crash 不在协议层取值里（它们分属传输层与进程层）。"""
    assert "timeout" not in PROTOCOL_OUTCOME_VALUES
    assert "crash" not in PROTOCOL_OUTCOME_VALUES
    # timeout 在传输层；崩溃证据在进程层（RESTARTED / SANITIZER_FAILURE / EXITED）。
    assert "timeout" in TRANSPORT_OUTCOME_VALUES
    assert {"restarted", "sanitizer_failure", "exited"} <= PROCESS_HEALTH_VALUES


# ===========================================================================
# C-5：timeout/crash 不作协议响应期望（读三协议真实配置逐项比对）
# ===========================================================================


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_expected_response_classes_exclude_timeout_and_crash(protocol: str) -> None:
    """三协议的期望响应词表恰好是 4 类协议语义结果，且不含 timeout/crash。"""
    classes = _expected_response_classes(protocol)
    assert set(classes) == EXPECTED_PROTOCOL_OUTCOMES, (
        f"{protocol}: expected_response_classes 应恰好为 {sorted(EXPECTED_PROTOCOL_OUTCOMES)}，"
        f"实为 {sorted(classes)}"
    )
    forbidden = FORBIDDEN_RESPONSE_CLASSES & set(classes)
    assert not forbidden, (
        f"{protocol}: expected_response_classes 不得含传输层/进程层词 {sorted(forbidden)}"
    )


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_expected_response_classes_are_protocol_outcome_subset(protocol: str) -> None:
    """词表里的每一项都必须是合法的 ``ProtocolOutcome``（双向防漂移）。"""
    classes = _expected_response_classes(protocol)
    unknown = set(classes) - PROTOCOL_OUTCOME_VALUES
    assert not unknown, (
        f"{protocol}: expected_response_classes 含非法协议结果 {sorted(unknown)}"
    )


def test_three_protocols_share_the_same_vocabulary() -> None:
    """三协议词表一致（避免某协议单方面漂移）。"""
    per_protocol = {p: set(_expected_response_classes(p)) for p in PROTOCOLS}
    distinct = {frozenset(v) for v in per_protocol.values()}
    assert len(distinct) == 1, f"三协议词表不一致: {per_protocol}"
    assert distinct.pop() == frozenset(EXPECTED_PROTOCOL_OUTCOMES)


def test_no_rfc_config_contains_timeout_or_crash_in_response_classes() -> None:
    """全仓扫一遍 ``profiles/*/rfc_config.json``，防止将来新增协议时引入。"""
    targets_dir = ROOT / "profiles"
    assert targets_dir.is_dir(), f"缺少 {targets_dir}"
    checked = 0
    for config_path in sorted(targets_dir.glob("*/rfc_config.json")):
        classes = set(
            json.loads(config_path.read_text(encoding="utf-8")).get(
                "expected_response_classes") or []
        )
        forbidden = FORBIDDEN_RESPONSE_CLASSES & classes
        assert not forbidden, (
            f"{config_path.relative_to(ROOT)}: expected_response_classes 含 "
            f"{sorted(forbidden)}"
        )
        checked += 1
    assert checked >= len(PROTOCOLS), \
        f"实际只扫到 {checked} 份 rfc_config.json，少于 {len(PROTOCOLS)} 个协议"


# ===========================================================================
# C-2 / C-3 / C-4：判定顺序（改进v2 问题⑦）
# ===========================================================================


def _seed(violation_of: str = "r-test-001", **extra: object) -> SimpleNamespace:
    """构造一个最小种子对象（duck typed）。"""
    return SimpleNamespace(violation_of=violation_of, **extra)


def _unknown_timeout_result() -> ExecResult:
    """health=UNKNOWN + trans=TIMEOUT（无任何响应）。"""
    return ExecResult(health_probe="unknown", transport_event="timeout")


def test_unknown_health_with_timeout_yields_inconclusive_not_deviation() -> None:
    """C-2 核心用例：UNKNOWN+TIMEOUT 且协议结果与期望不符 ⇒ inconclusive。"""
    result = _unknown_timeout_result()
    feedback = close_loop(_seed(), result, expected="success")
    assert feedback is not None
    assert feedback.kind == "inconclusive"
    assert feedback.kind != "semantic_deviation"


def test_unknown_health_with_timeout_not_deviation_even_with_mismatched_proto() -> None:
    """C-2：协议结果确实与期望不符，也**不能**先判成语义偏离。"""
    result = ExecResult(
        health_probe="unknown",
        transport_event="timeout",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected="success")
    assert feedback is not None
    assert feedback.kind == "inconclusive"
    assert feedback.actual == "protocol_error"   # 实际值仍如实记录
    assert feedback.expected == "success"


def test_unknown_timeout_without_expected_is_inconclusive() -> None:
    """C-2：``expected=None`` 时 UNKNOWN+TIMEOUT 仍走 inconclusive 分支。"""
    feedback = close_loop(_seed(), _unknown_timeout_result())
    assert feedback is not None
    assert feedback.kind == "inconclusive"


def test_known_health_timeout_falls_through_to_semantic_deviation() -> None:
    """对照：health 已知时，timeout 不再走 inconclusive（证明分支由 health 触发）。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="timeout",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected="success")
    assert feedback is not None
    assert feedback.kind == "semantic_deviation"


def test_exited_zero_exit_code_with_request_termination_is_normal() -> None:
    """C-3：退出码 0 + 正常收尾 ⇒ target_exited_normally（不是 crash）。"""
    result = ExecResult(
        health_probe="exited",
        exit_code=0,
        terminated_by_request=True,
    )
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "target_exited_normally"
    assert feedback.kind != "crash"


def test_exited_nonzero_exit_code_is_crash() -> None:
    """C-3：退出码非 0 ⇒ crash。"""
    result = ExecResult(health_probe="exited", exit_code=1)
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "crash"


def test_exited_with_sanitizer_report_is_crash() -> None:
    """C-3：有 sanitizer 报告 ⇒ crash（即使退出码为 0）。"""
    result = ExecResult(
        health_probe="exited",
        exit_code=0,
        sanitizer_report="ERROR: AddressSanitizer: heap-buffer-overflow",
        terminated_by_request=True,
    )
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "crash"


def test_exited_zero_exit_code_without_request_termination_is_crash() -> None:
    """C-3：退出码 0 但**无请求收尾证据** ⇒ 按「非请求收尾导致」判异常 ⇒ crash。"""
    result = ExecResult(health_probe="exited", exit_code=0, terminated_by_request=False)
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "crash"


def test_exited_normal_precedes_reset() -> None:
    """顺序：②（EXITED 判别）先于 ③（reset/close）。"""
    result = ExecResult(
        health_probe="exited",
        exit_code=0,
        terminated_by_request=True,
        transport_event="reset",
    )
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "target_exited_normally"


def test_reset_with_alive_health_is_connection_aborted_not_crash() -> None:
    """C-4：trans=RESET, health=ALIVE ⇒ connection_aborted（**不是** crash）。"""
    result = ExecResult(health_probe="alive", transport_event="reset")
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "connection_aborted"
    assert feedback.kind != "crash"


def test_close_with_alive_health_is_connection_aborted() -> None:
    """C-4：trans=CLOSE 同样 ⇒ connection_aborted。"""
    result = ExecResult(health_probe="alive", transport_event="close")
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "connection_aborted"


def test_reset_precedes_semantic_deviation() -> None:
    """顺序：③（reset/close）先于 ④（语义偏离）。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="reset",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected="success")
    assert feedback is not None
    assert feedback.kind == "connection_aborted"


def test_restarted_is_crash() -> None:
    """C-3：异常重启 ⇒ crash。"""
    result = ExecResult(health_probe="restarted")
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "crash"


def test_sanitizer_failure_is_crash() -> None:
    """C-3：sanitizer 报告 ⇒ crash。"""
    result = ExecResult(health_probe="sanitizer_failure")
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "crash"


def test_crash_evidence_precedes_reset() -> None:
    """顺序：②（crash 独立证据）先于 ③（reset/close）。"""
    result = ExecResult(health_probe="restarted", transport_event="reset")
    feedback = close_loop(_seed(), result)
    assert feedback is not None
    assert feedback.kind == "crash"


def test_expected_none_skips_semantic_deviation() -> None:
    """``expected=None`` ⇒ 不返回 semantic_deviation，也不抛异常。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected=None)
    assert feedback is None


def test_expected_none_still_reports_connection_aborted() -> None:
    """``expected=None`` 只跳过**语义偏离**判定，传输层判定照常。"""
    result = ExecResult(health_probe="alive", transport_event="reset")
    feedback = close_loop(_seed(), result, expected=None)
    assert feedback is not None
    assert feedback.kind == "connection_aborted"


def test_expected_none_ignores_seed_expected_class() -> None:
    """``expected`` 是期望的**唯一来源**（不回退读 seed.expected_class）。"""
    seed = _seed(expected_class="success")
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(seed, result, expected=None)
    assert feedback is None


def test_expected_accepts_enum_member() -> None:
    """``expected`` 可以是枚举成员（归一后按裸字符串比对）。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected=ProtocolOutcome.SUCCESS)
    assert feedback is not None
    assert feedback.kind == "semantic_deviation"
    assert feedback.expected == "success"


@pytest.mark.parametrize("bad_expected",
                         ["timeout", "crash", "reset", "nonsense", "bogus"])
def test_expected_invalid_protocol_value_raises(bad_expected: str) -> None:
    """期望值只接受协议层取值；timeout/crash 属别的轴，必须显式报错。"""
    result = ExecResult(health_probe="alive", transport_event="response")
    with pytest.raises(ValueError, match="expected 非法取值"):
        close_loop(_seed(), result, expected=bad_expected)


def test_expected_empty_string_equals_none() -> None:
    """C 阶段 × B-2 对齐：``expected=""``（convert-C7 特例产出）与 ``expected=None`` 等价。

    ★ B-2 的 ``try_convert`` 在缺处理期望时产出 ``expected_behavior == ""``（**不是 None**），
      若 close_loop 只认 ``None``，B-8 消费 bundle 时必抛 ValueError。
    """
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="success",
    )
    assert close_loop(_seed(), result, expected="") is None
    assert close_loop(_seed(), result, expected=None) is None


def test_expected_empty_string_skips_deviation_even_on_mismatch() -> None:
    """★ 关键用例：``expected=""`` 且实际是 protocol_error ⇒ 仍返回 None（**不** semantic_deviation）。

    证明空期望被**跳过**，而不是被当成「有一个空期望」去比对（否则会出现假匹配/假通过）。
    """
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected="")
    assert feedback is None


def test_expected_empty_string_still_reports_transport_and_health() -> None:
    """``expected=""`` 只跳过**语义偏离**判定，传输层 / 进程健康判定照常。"""
    result = ExecResult(health_probe="alive", transport_event="reset")
    feedback = close_loop(_seed(), result, expected="")
    assert feedback is not None
    assert feedback.kind == "connection_aborted"


def test_expected_whitespace_only_treated_as_no_expectation() -> None:
    """纯空白也按「无期望」处理（不误判为非法取值，也不误判为语义偏离）。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="protocol_error",
    )
    assert close_loop(_seed(), result, expected="   ") is None


def test_matching_expectation_returns_none() -> None:
    """符合预期 ⇒ 无反馈（返回 None）。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="success",
    )
    assert close_loop(_seed(), result, expected="success") is None


def test_proto_mismatch_with_known_health_is_semantic_deviation() -> None:
    """④ 语义偏离分支：健康已知、非超时、协议结果与期望不符。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="response",
        protocol_outcome="application_error",
    )
    feedback = close_loop(_seed(), result, expected="success")
    assert feedback is not None
    assert feedback.kind == "semantic_deviation"
    assert feedback.expected == "success"
    assert feedback.actual == "application_error"


def test_feedback_carries_all_three_axes() -> None:
    """每条 Feedback 都带齐三轴（便于下游统一归因）。"""
    result = ExecResult(
        health_probe="alive",
        transport_event="reset",
        protocol_outcome="protocol_error",
    )
    feedback = close_loop(_seed(), result, expected="success")
    assert feedback is not None
    assert feedback.protocol == ProtocolOutcome.PROTOCOL_ERROR
    assert feedback.transport == TransportOutcome.RESET
    assert feedback.health == ProcessHealth.ALIVE


def test_feedback_kind_always_in_closed_vocabulary() -> None:
    """Feedback.kind 只能取闭合词表里的 5 种。"""
    assert FEEDBACK_KINDS == {
        "inconclusive",
        "crash",
        "target_exited_normally",
        "connection_aborted",
        "semantic_deviation",
    }
    cases = [
        ExecResult(health_probe="unknown", transport_event="timeout"),
        ExecResult(health_probe="restarted"),
        ExecResult(health_probe="exited", exit_code=0, terminated_by_request=True),
        ExecResult(health_probe="exited", exit_code=3),
        ExecResult(health_probe="alive", transport_event="reset"),
        ExecResult(health_probe="alive", transport_event="response",
                   protocol_outcome="protocol_error"),
    ]
    kinds = []
    for case in cases:
        feedback = close_loop(_seed(), case, expected="success")
        if feedback is not None:
            kinds.append(feedback.kind)
    assert kinds
    assert set(kinds) <= FEEDBACK_KINDS


def test_feedback_carries_violated_rule_id() -> None:
    """违规点标识（violation_of）从种子透传到 Feedback。"""
    result = ExecResult(health_probe="alive", transport_event="reset")
    feedback = close_loop(_seed(violation_of="r-abc123"), result)
    assert feedback is not None
    assert feedback.violated == "r-abc123"


def test_close_loop_accepts_dict_shaped_result() -> None:
    """三轴判定吃下裸 dict（回放器直接吐 JSON 的常见形态）。"""
    feedback = close_loop(
        _seed(),
        {"health_probe": "alive", "transport_event": "reset"},
    )
    assert feedback is not None
    assert feedback.kind == "connection_aborted"


def test_classifiers_default_to_conservative_values() -> None:
    """无任何证据时：协议层 silence / 传输层 timeout / 进程健康 unknown。"""
    empty = ExecResult()
    assert classify_protocol_outcome(empty) is ProtocolOutcome.SILENCE
    assert classify_transport_outcome(empty) is TransportOutcome.TIMEOUT
    assert probe_process_health(empty) is ProcessHealth.UNKNOWN


def test_explicit_protocol_outcome_overrides_status_code() -> None:
    """显式 ``protocol_outcome`` 优先于状态码推断。"""
    result = ExecResult(protocol_outcome="silence", status_code=200)
    assert classify_protocol_outcome(result) is ProtocolOutcome.SILENCE


def test_status_code_bands_map_to_protocol_outcomes() -> None:
    """状态码分档：2xx 成功 / 4xx 协议错误 / 5xx 应用错误。"""
    assert classify_protocol_outcome(ExecResult(status_code=200)) is ProtocolOutcome.SUCCESS
    assert classify_protocol_outcome(ExecResult(status_code=404)) is ProtocolOutcome.PROTOCOL_ERROR
    assert classify_protocol_outcome(ExecResult(status_code=500)) is ProtocolOutcome.APPLICATION_ERROR


def test_reproducible_is_none_without_reproducer() -> None:
    """没有复现器 ⇒ ``reproducible=None``（未知，不编造「不可复现」）。"""
    feedback = close_loop(_seed(), ExecResult(health_probe="restarted"))
    assert feedback is not None
    assert feedback.reproducible is None


def test_reproduce_injection_sets_reproducible() -> None:
    """注入复现器 ⇒ ``reproducible`` 取其 ``.ok``。"""
    feedback = close_loop(
        _seed(),
        ExecResult(health_probe="restarted"),
        reproduce=lambda seed: SimpleNamespace(ok=True),
    )
    assert feedback is not None
    assert feedback.reproducible is True


def test_feedback_dataclass_is_frozen() -> None:
    """Feedback 不可变（避免下游就地改写判定结果）。"""
    feedback = Feedback(kind="inconclusive")
    with pytest.raises(Exception):
        feedback.kind = "crash"  # type: ignore[misc]
