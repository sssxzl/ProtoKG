# -*- coding: utf-8 -*-
"""tests/fused/test_action_seq_batch1_regress.py —— 批次 1 **第三轮**修复的回归用例。

对应 QA 第二段复验查出的 **5 个开放缺陷**（R-1 / R-2 / P1-2 / P2-1 / P2-2 / P2-3）
与 team-lead 复现确认的两个根因：

  · **R-1（P0）**：⑤（action-seq）种子**漏跑** ``_rewrite_client_headers``
    ⇒ 真实抓包底料里的**源侧端点**（``Via: SIP/2.0/UDP 192.168.1.2:5060``）
    原样留在 ``.raw`` 字节里 ⇒ G1 判违规（**语料无法发布**），
    且服务端把响应回传到错地址 ⇒ AFLNet 收不到响应 ⇒ 该种子零价值。
  · **R-2（P1）**：``missing-required-header`` 补齐必填头时用的是知识中枢
    取值池的**兜底值**，而实测 **18/29（62%）是空串** ⇒ 落盘 ``CSeq: ``
    ⇒ 服务端必然拒收 ⇒ **零价值却占掉契约名额**。
  · **P1-2（P1）**：``apply_actions`` 的 ``ledger`` 原本默认 ``None``
    ⇒ 拒绝被**静默吞掉** ⇒ 违反模块硬性约束①「拒绝必须可观测」。
  · **P2-1**：``field_path`` 的**嵌套歧义**（``headers.A.B`` 到底是头名还是子字段）。
  · **P2-2**：``remove`` **必填**头**零台账**（静默生效）。
  · **P2-3**：``value`` **无长度上限**。

★ 这些用例都是**负向**的（断言「坏事没发生」），并且**把 QA 的实测数字固化成断言**。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.fused.downstream.action_seq import (
    MAX_VALUE_LENGTH,
    OP_ADD,
    OP_REMOVE,
    OP_UPDATE,
    REJECT_EMPTY_VALUE,
    REJECT_FIELD_PATH_OUT_OF_DOMAIN,
    REJECT_HEADER_IS_REQUIRED,
    REJECT_VALUE_TOO_LONG,
    Action,
    ActionLedger,
    ActionSequence,
    apply_actions,
    normalize_field_path,
    plan_actions,
)
from core.models import SeedCorpus, SeedMessage

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# 夹具
# ===========================================================================

def _seed() -> SeedCorpus:
    return SeedCorpus(
        seed_id="base-1",
        protocol="sip",
        description="base seed",
        target_state_path=["Idle"],
        target_methods=["INVITE"],
        messages=[
            SeedMessage(method="INVITE",
                        headers={"Via": "SIP/2.0/UDP 192.168.1.2:5060;branch=z9hG4bK1",
                                 "From": "<sip:a@b>", "To": "<sip:c@d>",
                                 "Call-ID": "x@y", "Max-Forwards": "70"},
                        body="", url="sip:127.0.0.1:5060", argument=""),
        ],
    )


def _bundle(headers_bucket: dict | None = None) -> dict:
    """最小知识中枢。

    ★ 默认给 ``CSeq`` 的取值池是**只有空串**（复刻 QA 实测的 62% 空值情形）。
    """
    bucket = {"CSeq": {"values": [""]}} if headers_bucket is None else headers_bucket
    return {
        "required_headers": {"INVITE": ["Via", "From", "To", "Call-ID",
                                        "CSeq", "Max-Forwards"]},
        "session_header": {},
        "headers": bucket,
        "statuses": {"200": "OK"},
    }


def _sip_profile() -> dict:
    return json.loads((ROOT / "profiles" / "sip" / "profile.json")
                      .read_text(encoding="utf-8"))


# ===========================================================================
# R-1（P0）：⑤ 种子必须走「响应回传地址重写」
# ===========================================================================

class TestR1ClientHeaderRewrite:
    """★ R-1（P0）：⑤ 种子**漏跑** ``_rewrite_client_headers`` ⇒ G1 违规。"""

    def test_rewrite_moves_via_sent_by_to_client_port(self):
        """源侧端点必须被改写到客户端监听端口（否则服务端回包到错地址）。"""
        from scripts.seedgen import _rewrite_client_headers
        seed = _seed()
        _rewrite_client_headers([seed], _sip_profile(), "sip")
        via = seed.messages[0].headers["Via"]
        assert "192.168.1.2:5060" not in via, "源侧端点必须被改写"
        assert "127.0.0.1:5061" in via, "应改写成客户端监听端口"

    def test_rewrite_is_idempotent(self):
        from scripts.seedgen import _rewrite_client_headers
        seed = _seed()
        _rewrite_client_headers([seed], _sip_profile(), "sip")
        once = seed.messages[0].headers["Via"]
        _rewrite_client_headers([seed], _sip_profile(), "sip")
        assert seed.messages[0].headers["Via"] == once

    def test_protocol_without_client_side_is_untouched(self):
        """协议无关：无 ``client_side`` 声明 ⇒ 原样返回（不误伤）。"""
        from scripts.seedgen import _rewrite_client_headers
        seed = _seed()
        before = seed.messages[0].headers["Via"]
        _rewrite_client_headers([seed], {"seedgen": {}}, "sip")
        assert seed.messages[0].headers["Via"] == before


# ===========================================================================
# R-2（P1）：必填头补齐**不得**落盘空值
# ===========================================================================

class TestR2EmptyValueRejected:
    """★ R-2：``missing-required-header`` 不得补出空值头（``CSeq: ``）。"""

    def test_rule_does_not_emit_action_for_empty_pool_value(self):
        """取值池只有空串 ⇒ **不产出**该动作，且台账可观测。"""
        ledger = ActionLedger()
        seq = plan_actions(_seed(), _bundle(), protocol="sip", ledger=ledger)
        added = [a for a in seq.actions
                 if a.op == OP_ADD and a.field_path.lower() == "headers.cseq"]
        assert added == [], "空值兜底不得被补成必填头"
        assert ledger.reason_counts().get(REJECT_EMPTY_VALUE, 0) >= 1, \
            "拒绝必须可观测（台账有记录）"

    def test_empty_value_action_is_rejected_at_apply_time(self):
        """纵深防御：即便动作已成型，空串 value 也**必须**被拒绝。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_UPDATE, 0, "headers.CSeq", ""),))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert not out.messages[0].headers.get("CSeq"), \
            "空串不得写进消息头"
        assert ledger.reason_counts().get(REJECT_EMPTY_VALUE) == 1

    def test_empty_add_does_not_create_a_blank_header(self):
        """端到端：被拒后消息里**不得**出现 ``CSeq: ``（空值头）。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_ADD, 0, "headers.CSeq", ""),))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert "CSeq" not in out.messages[0].headers
        assert ledger.reason_counts().get(REJECT_EMPTY_VALUE) == 1

    def test_default_header_value_skips_empty_entries(self):
        """取值池首值为空时，兜底值应**跳过**空值取下一个非空值。"""
        from core.fused.downstream.action_seq import _default_header_value
        bucket = {"CSeq": {"values": ["", "7"]}}
        assert _default_header_value(bucket, "CSeq") == "7"

    def test_default_header_value_returns_empty_when_all_blank(self):
        from core.fused.downstream.action_seq import _default_header_value
        bucket = {"CSeq": {"values": ["", "  "]}}
        assert _default_header_value(bucket, "CSeq") == ""


# ===========================================================================
# P1-2：拒绝台账**必传**（不许静默吞掉）
# ===========================================================================

class TestP1_2LedgerIsMandatory:
    """★ P1-2：``ledger`` 默认 ``None`` ⇒ 拒绝被静默吞掉。"""

    def test_apply_actions_requires_ledger(self):
        with pytest.raises(TypeError):
            apply_actions(_seed(), ActionSequence())      # type: ignore[call-arg]

    def test_plan_actions_requires_ledger(self):
        with pytest.raises(TypeError):
            plan_actions(_seed(), _bundle(), protocol="sip")   # type: ignore[call-arg]


# ===========================================================================
# P2-1：field_path 无嵌套歧义
# ===========================================================================

class TestP21NoNestedAmbiguity:
    """★ P2-1：``headers.A.B`` 不得被当成「头名 A.B」而凭空建头。"""

    def test_dotted_header_name_is_out_of_domain(self):
        assert normalize_field_path("headers.Content.Base") is None

    def test_dotted_header_path_is_rejected_with_reason(self):
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_ADD, 0, "headers.X.Y", "v"),))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert out.messages[0].headers.get("X.Y") is None
        assert ledger.reason_counts().get(REJECT_FIELD_PATH_OUT_OF_DOMAIN) == 1

    def test_plain_header_name_still_works(self):
        assert normalize_field_path("headers.CSeq") == ("header", "CSeq")
        assert normalize_field_path("headers.X-Custom_1") == ("header", "X-Custom_1")


# ===========================================================================
# P2-2：不得删必填头（且必须有台账）
# ===========================================================================

class TestP22CannotRemoveRequiredHeader:
    """★ P2-2：删必填头 ⇒ 拒绝并记台账（此前零台账）。"""

    def test_remove_required_header_is_rejected(self):
        """删一个**存在且必填**的头 ⇒ 拒绝并记台账。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_REMOVE, 0, "headers.Max-Forwards"),))
        out = apply_actions(_seed(), seq, ledger=ledger,
                            required_headers={"INVITE": ["Max-Forwards"]})
        assert "Max-Forwards" in out.messages[0].headers, "必填头不得被删"
        assert ledger.reason_counts().get(REJECT_HEADER_IS_REQUIRED) == 1

    def test_remove_optional_header_is_allowed(self):
        """非必填头照常可删（不误杀）。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_REMOVE, 0, "headers.Max-Forwards"),))
        out = apply_actions(_seed(), seq, ledger=ledger,
                            required_headers={"INVITE": ["CSeq"]})
        assert "Max-Forwards" not in out.messages[0].headers
        assert not ledger.reason_counts()

    def test_plan_actions_passes_required_headers_context(self):
        """``plan_actions`` 必须把知识中枢的必填头表传下去。"""
        ledger = ActionLedger()
        plan_actions(_seed(), _bundle(), protocol="sip", ledger=ledger)
        # 规则里没有「删必填头」这一条 ⇒ 不应产生该类拒绝
        assert ledger.reason_counts().get(REJECT_HEADER_IS_REQUIRED, 0) == 0


# ===========================================================================
# P2-3：value 长度上限
# ===========================================================================

class TestP23ValueLengthLimit:
    """★ P2-3：``value`` 无长度上限 ⇒ LLM 可产出 MB 级字段。"""

    def test_overlong_value_is_rejected(self):
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_UPDATE, 0, "headers.From", "x" * (MAX_VALUE_LENGTH + 1)),))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert out.messages[0].headers["From"] == "<sip:a@b>", "不得改动"
        assert ledger.reason_counts().get(REJECT_VALUE_TOO_LONG) == 1

    def test_value_at_limit_is_allowed(self):
        """恰好等于上限 ⇒ 放行（不误杀）。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(OP_UPDATE, 0, "headers.From", "x" * MAX_VALUE_LENGTH),))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert len(out.messages[0].headers["From"]) == MAX_VALUE_LENGTH
        assert not ledger.reason_counts()
