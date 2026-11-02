# -*- coding: utf-8 -*-
"""tests/fused/test_action_seq_hardening.py —— action_seq 的**安全与端点**硬化回归。

覆盖 QA 独立验证（批次 1 首轮实现）查出的两个安全相关缺陷：

  · **P0-1 纵深防御**：变异写入的端点必须在**合法端点集合**内
    （与 ``scripts/corpus_gate.py`` 的 G1 **共用同一份实现**）
  · **P1-1（安全）**：``value`` 含 CR/LF/NUL 等控制字符 ⇒ 拒绝
    （否则头值里会凭空多出一个头 ⇒ **协议/头注入**）
  · **P0-1 根因**：端点归一化必须覆盖**头部里嵌的 URI**
    （原先只归一化消息级 url ⇒ 外网端点原样留在 ``.raw`` 字节里）

★ 这些用例都是**负向**的（断言"坏事没发生"），不是"功能存在"的断言。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.fused.downstream.action_seq import (
    OP_UPDATE,
    Action,
    ActionLedger,
    ActionSequence,
    apply_actions,
)
from core.models import SeedCorpus, SeedMessage

ROOT = Path(__file__).resolve().parents[2]

#: 外网主机（某 IP 摄像机的真实地址，来自 `kb/*/数据流量/` 的真实抓包）
FOREIGN = "10.11.26.98:554"
#: 目标环境的合法端点
LOCAL = "127.0.0.1:8554"


def _seed() -> SeedCorpus:
    """一颗最小但完整的种子（2 条消息）。"""
    return SeedCorpus(
        seed_id="base-1",
        protocol="rtsp",
        description="base seed",
        target_state_path=["Init", "Ready"],
        target_methods=["OPTIONS", "PLAY"],
        messages=[
            SeedMessage(method="OPTIONS",
                        headers={"CSeq": "1", "Accept": "application/sdp"},
                        body="", url="rtsp://127.0.0.1:8554/stream",
                        argument=""),
            SeedMessage(method="PLAY",
                        headers={"CSeq": "2"},
                        body="payload-body", url="rtsp://127.0.0.1:8554/stream/",
                        argument="PLAY-ARG"),
        ],
    )


def _profile(proto: str = "rtsp") -> dict:
    p = ROOT / "fused_hub" / "targets" / proto / "profile.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ===========================================================================
# P0-1 纵深防御：端点白名单
# ===========================================================================
class TestEndpointAllowlist:
    """★ P0-1：变异写入的端点必须在**合法端点集合**内。"""

    def test_whitelist_is_shared_with_corpus_gate(self):
        """★ 白名单判据**必须与 corpus_gate 的 G1 共用同一份实现**（口径不得漂移）。"""
        from core.fused.downstream import action_seq, target_env
        assert action_seq._allowed_endpoints is target_env.allowed_endpoints

    def test_corpus_gate_reexports_the_same_function(self):
        """★ `scripts/corpus_gate.py` 必须**转出同一份**（既有调用方不改）。"""
        from scripts.corpus_gate import allowed_endpoints as cg_fn
        from core.fused.downstream.target_env import allowed_endpoints as te_fn
        assert cg_fn is te_fn

    def test_foreign_endpoint_is_rejected(self):
        """外网端点 ⇒ 拒绝，并记 `endpoint_not_allowed`。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_UPDATE, msg_index=0, field_path="url",
                   value="rtsp://10.11.26.98:554/isapi/streaming/channels/101"),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger, profile=_profile())
        assert out.messages[0].url == "rtsp://127.0.0.1:8554/stream"   # 未被改写
        assert ledger.reason_counts().get("endpoint_not_allowed") == 1

    def test_legal_endpoint_is_allowed(self):
        """合法端点 ⇒ 放行（不误杀）。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_UPDATE, msg_index=0, field_path="url",
                   value="rtsp://127.0.0.1:8554/mutated"),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger, profile=_profile())
        assert out.messages[0].url == "rtsp://127.0.0.1:8554/mutated"
        assert not ledger.reason_counts()

    def test_without_profile_whitelist_is_not_enforced(self):
        """★ 无 profile ⇒ 白名单为 ``None`` ⇒ **不启用**端点校验（不误杀合法动作）。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_UPDATE, msg_index=0, field_path="url",
                   value="rtsp://10.11.26.98:554/x"),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert out.messages[0].url == "rtsp://10.11.26.98:554/x"
        assert not ledger.reason_counts()


# ===========================================================================
# P1-1：value 含控制字符 ⇒ 拒绝（协议/头注入）
# ===========================================================================
class TestControlCharInjection:
    """★ P1-1（安全）：``value`` 含 CR/LF/NUL ⇒ 头值里会凭空多出个头。"""

    def _apply(self, value: str):
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_UPDATE, msg_index=0, field_path="headers.Accept",
                   value=value),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger)
        return out, ledger

    def test_crlf_is_rejected(self):
        _out, ledger = self._apply("application/sdp\r\nX-Evil: pwned")
        assert ledger.reason_counts().get("value_has_control_chars") == 1

    def test_bare_lf_is_rejected(self):
        _out, ledger = self._apply("application/sdp\nX-Evil: pwned")
        assert ledger.reason_counts().get("value_has_control_chars") == 1

    def test_nul_is_rejected(self):
        _out, ledger = self._apply("application/sdp\x00")
        assert ledger.reason_counts().get("value_has_control_chars") == 1

    def test_tab_is_allowed(self):
        """``\\t`` 放行（协议里常见的分隔符，不是注入手段）。"""
        _out, ledger = self._apply("application/sdp;charset=utf-8\t")
        assert not ledger.reason_counts()

    def test_injected_header_never_reaches_the_message(self):
        """★ 端到端：被拒后**消息头里不得**出现注入的头。"""
        out, _ledger = self._apply("application/sdp\r\nX-Evil: pwned")
        blob = json.dumps(out.messages[0].headers, ensure_ascii=False)
        assert "X-Evil" not in blob
        assert out.messages[0].headers["Accept"] == "application/sdp"


# ===========================================================================
# P0-1 根因修复：端点归一化必须覆盖**头部里嵌的 URI**
# ===========================================================================
class TestHeaderUriNormalization:
    """★ P0-1 根因：原先只归一化消息级 url ⇒ 头部里的外网端点原样留在字节里。"""

    def test_foreign_endpoint_in_header_is_normalized(self):
        from core.fused.downstream.target_env import normalize_target_endpoint_in_text
        raw = ('Digest username="<user>", uri="rtsp://10.11.26.98:554/isapi/x", '
               'response="<r>"')
        out = normalize_target_endpoint_in_text(raw, _profile())
        assert FOREIGN not in out
        assert LOCAL in out

    def test_legal_endpoint_is_untouched(self):
        from core.fused.downstream.target_env import normalize_target_endpoint_in_text
        raw = "rtsp://127.0.0.1:8554/mp3AudioTest"
        assert normalize_target_endpoint_in_text(raw, _profile()) == raw

    def test_text_without_url_is_untouched(self):
        from core.fused.downstream.target_env import normalize_target_endpoint_in_text
        raw = "text/html, application/xhtml+xml"
        assert normalize_target_endpoint_in_text(raw, _profile()) == raw

    def test_idempotent(self):
        from core.fused.downstream.target_env import normalize_target_endpoint_in_text
        raw = 'uri="rtsp://10.11.26.98:554/isapi/x"'
        once = normalize_target_endpoint_in_text(raw, _profile())
        assert normalize_target_endpoint_in_text(once, _profile()) == once

    def test_protocol_with_switch_off_is_byte_identical(self):
        """★ SIP（开关关闭）的 URI domain 是逻辑实体标识 ⇒ 必须**逐字节不变**。"""
        from core.fused.downstream.target_env import normalize_target_endpoint_in_text
        raw = "sip:bob@example.com;transport=tcp"
        assert normalize_target_endpoint_in_text(raw, _profile("sip")) == raw

    def test_rtp_info_style_header_is_normalized(self):
        """Rtp-Info 这种「URL + 其它参数」的头也要能处理。"""
        from core.fused.downstream.target_env import normalize_target_endpoint_in_text
        raw = ("url=rtsp://10.11.26.98:554/isapi/streaming/channels/101/"
               "trackID=1;seq=4276;rtptime=3627500126")
        out = normalize_target_endpoint_in_text(raw, _profile())
        assert FOREIGN not in out
        assert "seq=4276" in out          # 其它参数**不得**被丢掉
