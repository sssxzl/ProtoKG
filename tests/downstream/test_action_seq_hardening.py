# -*- coding: utf-8 -*-
"""tests/test_action_seq_hardening.py —— action_seq 的**安全与端点**硬化回归。

覆盖 QA 独立验证（批次 1 首轮实现）查出的两个安全相关缺陷：

  · **P0-1 纵深防御**：变异写入的端点必须在**合法端点集合**内
    （与 **合法端点闸**的 G1 **共用同一份实现**）
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
    OP_ADD,
    OP_REMOVE,
    OP_UPDATE,
    Action,
    ActionLedger,
    ActionSequence,
    apply_actions,
    plan_actions,
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
    p = ROOT / "profiles" / proto / "profile.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ===========================================================================
# P0-1 纵深防御：端点白名单
# ===========================================================================
class TestEndpointAllowlist:
    """★ P0-1：变异写入的端点必须在**合法端点集合**内。"""

    def test_whitelist_is_shared_with_target_env(self):
        """★ 白名单判据**必须与 target_env 共用同一份实现**（口径不得漂移）。"""
        from core.fused.downstream import action_seq, target_env
        assert action_seq._allowed_endpoints is target_env.allowed_endpoints

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


# ===========================================================================
# R-1（P0）：⑤ 种子漏跑 ``_rewrite_client_headers`` ⇒ 源侧端点留在 .raw 字节里
# ===========================================================================
class TestActionSeqPostProcessing:
    """★ R-1（P0）：⑤ 层种子必须跑**与基准层完全同款**的后处理链。

    根因：``scripts/seedgen.py`` 把⑤种子在流程**末尾**追加 ⇒ 它**绕过**了基准层的
    ``_rewrite_client_headers`` ⇒ 真实抓包底料里的源侧地址
    （实测 SIP 的 ``Via: SIP/2.0/UDP 192.168.1.2:5060``）原样留在 ``.raw`` 字节里
    ⇒ `corpus_gate` 的 G1 判违规（**退出码 1 ⇒ 语料无法发布**）；
    语义后果更重：服务端把响应回传到**错地址** ⇒ AFLNet **收不到响应**
    ⇒ 该种子零价值。
    """

    def test_action_seq_seeds_are_rewritten_by_seedgen(self):
        """★ 端到端：⑤ 层种子的 Via/Contact 必须被改写到客户端监听地址。

        判据用 **合法端点闸** 的**同一份** G1 判据（``extract_endpoints`` +
        ``allowed_endpoints``）⇒ 不用另写一套「看起来一样」的判据。
        """
        import scripts.seedgen as seedgen_mod
        from scripts.corpus_gate import (allowed_endpoints, extract_endpoints,
                                        request_url_index)

        profile = _profile("sip")
        env_cfg = ((profile.get("seedgen") or {}).get("environments")
                   or {}).get("rq2-kamailio") or {}
        allowed, _sources = allowed_endpoints(profile, env_cfg)
        url_index = request_url_index(profile)

        # 一条带**源侧真实地址**的 Via（真实抓包里就是这个形态）
        seed = SeedCorpus(
            protocol="sip", description="base",
            messages=[SeedMessage(
                method="UPDATE", url="sip:127.0.0.1:5060",
                headers={"Via": "SIP/2.0/UDP 192.168.1.2:5060;branch=z9hG4bK-x"},
                body="", argument="")])

        out = seedgen_mod._rewrite_client_headers([seed], profile, "sip")

        endpoints = [ep for ep, _pos in
                     extract_endpoints("\n".join(
                         f"{k}: {v}" for k, v in out[0].messages[0].headers.items()),
                         profile, url_index)]
        assert endpoints, "Via 里应当仍能抽出端点（否则本用例是空断言）"
        assert all(ep in allowed for ep in endpoints), (
            f"⑤ 后处理后仍残留越界端点: {endpoints}（合法集合 {sorted(allowed)}）")

    def test_rewrite_is_noop_for_protocol_without_client_side(self):
        """★ 无 ``client_side`` 声明的协议（RTSP）⇒ 原样返回（协议无关）。"""
        import scripts.seedgen as seedgen_mod
        profile = _profile("rtsp")
        seed = SeedCorpus(
            protocol="rtsp", description="base",
            messages=[SeedMessage(method="OPTIONS",
                                  url="rtsp://127.0.0.1:8554/x",
                                  headers={"User-Agent": "ua/1.0"},
                                  body="", argument="")])
        out = seedgen_mod._rewrite_client_headers([seed], profile, "rtsp")
        assert out[0].messages[0].headers["User-Agent"] == "ua/1.0"


# ===========================================================================
# R-2（P1）：``missing-required-header`` 补出**空值**必填头 ⇒ 零价值种子
# ===========================================================================
class TestEmptyValueRejected:
    """★ R-2（P1）：空串不是合法的新值 ⇒ 拒绝并记账。

    实测（QA 第二段复验）：补齐必填头时 **18/29（62%）是空串**
    ⇒ 落盘成 ``CSeq: `` ⇒ 服务端**必然拒收** ⇒ 该⑤种子**零价值**
    却**占掉契约名额**（对 SemFuzz「36%→87%」是**负贡献**）。
    ⇒ 真要清空某字段请用 ``remove``。
    """

    def test_empty_value_is_rejected(self):
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_ADD, msg_index=0, field_path="headers.CSeq", value=""),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger)
        assert "CSeq" not in out.messages[0].headers or \
            out.messages[0].headers["CSeq"] != ""
        assert ledger.reason_counts().get("empty_value") == 1

    def test_whitespace_only_value_is_rejected(self):
        """★ 纯空白等价于空值（落盘也是 ``CSeq: ``）⇒ 同样拒绝。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_UPDATE, msg_index=0, field_path="headers.Accept",
                   value="   "),
        ))
        apply_actions(_seed(), seq, ledger=ledger)
        assert ledger.reason_counts().get("empty_value") == 1

    def test_rule_does_not_produce_empty_required_header(self):
        """★ 规则层：取不到**非空**兜底值 ⇒ **不产出该动作**，且**记台账**。

        判据：知识中枢里该必填头只有空取值 ⇒ 补出来就是 ``CSeq: ``。
        """
        from core.fused.downstream.action_seq import REJECT_EMPTY_VALUE

        seed = SeedCorpus(
            protocol="sip", description="base",
            messages=[SeedMessage(method="UPDATE", url="sip:127.0.0.1:5060",
                                  headers={}, body="", argument="")])
        bundle = {
            "required_headers": {"UPDATE": ["CSeq"]},
            "session_header": {}, "headers": {"CSeq": {"values": [""]}},
            "statuses": {},
        }
        ledger = ActionLedger()
        seq = plan_actions(seed, bundle, protocol="sip", ledger=ledger)
        assert not any(a.field_path.lower() == "headers.cseq" for a in seq.actions), \
            "不得产出空值的 CSeq 动作"
        assert ledger.reason_counts().get(REJECT_EMPTY_VALUE) == 1, \
            "跳过必须**记台账**（可观测），不能静默"

    def test_default_header_value_skips_empty_pool_entries(self):
        """★ 取值池首值为空 ⇒ 必须**继续找下一个非空值**（而不是直接用空串）。"""
        from core.fused.downstream.action_seq import _default_header_value
        bucket = {"X-H": {"values": ["", "  ", "real-value"]}}
        assert _default_header_value(bucket, "X-H") == "real-value"

    def test_default_header_value_empty_when_pool_all_empty(self):
        from core.fused.downstream.action_seq import _default_header_value
        assert _default_header_value({"X-H": {"values": ["", " "]}}, "X-H") == ""
        assert _default_header_value({}, "X-H") == ""


# ===========================================================================
# P2-2：``remove`` 必填头 ⇒ 拒绝并记账（此前**静默生效**）
# ===========================================================================
class TestRemoveRequiredHeaderRejected:
    """★ P2-2：删**必填**头 ⇒ 服务端必然拒收 ⇒ 零价值；此前**不被拒绝且零台账**。

    ★ 必填头清单来自**知识中枢** ``required_headers``（按方法分组）⇒
      **不硬编码任何头名**（协议无关）。
    """

    def test_remove_required_header_is_rejected(self):
        ledger = ActionLedger()
        required = {"OPTIONS": ["CSeq", "User-Agent"]}
        seq = ActionSequence(actions=(
            Action(op=OP_REMOVE, msg_index=0, field_path="headers.CSeq"),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger,
                            required_headers=required)
        assert out.messages[0].headers.get("CSeq") == "1", "必填头不得被删"
        assert ledger.reason_counts().get("header_is_required") == 1, \
            "拒绝必须**记台账**（此前零台账 ⇒ 静默）"

    def test_remove_optional_header_is_allowed(self):
        """★ 非必填头照常可删（不得**误杀**）。"""
        ledger = ActionLedger()
        required = {"OPTIONS": ["CSeq"]}
        seq = ActionSequence(actions=(
            Action(op=OP_REMOVE, msg_index=0, field_path="headers.Accept"),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger,
                            required_headers=required)
        assert "Accept" not in out.messages[0].headers
        assert not ledger.reason_counts()

    def test_required_header_list_comes_from_bundle_not_hardcoded(self):
        """★ 判据来自知识中枢 ⇒ 换个头名同样生效（证明没硬编码 ``CSeq``）。"""
        ledger = ActionLedger()
        required = {"OPTIONS": ["Accept"]}
        seq = ActionSequence(actions=(
            Action(op=OP_REMOVE, msg_index=0, field_path="headers.Accept"),
        ))
        out = apply_actions(_seed(), seq, ledger=ledger,
                            required_headers=required)
        assert "Accept" in out.messages[0].headers
        assert ledger.reason_counts().get("header_is_required") == 1


# ===========================================================================
# P1-2：``apply_actions`` 默认 ``ledger=None`` ⇒ 拒绝**静默**
# ===========================================================================
class TestLedgerIsMandatory:
    """★ P1-2：不给台账 ⇒ **调不动**（拒绝不得被静默吞掉）。

    本模块的硬性约束①是「域外路径 / 越界下标 / 缺值等**一律拒绝并登记
    reject_reason**（不抛异常、**不静默忽略**）」⇒ 台账必须**必传**。
    """

    def test_apply_actions_requires_ledger(self):
        """★ 缺台账 ⇒ TypeError（**不是**静默吞掉拒绝）。"""
        import inspect
        from core.fused.downstream.action_seq import apply_actions
        sig = inspect.signature(apply_actions)
        assert sig.parameters["ledger"].default is inspect.Parameter.empty, \
            "ledger 必须是**必传**参数"
        assert sig.parameters["ledger"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_plan_actions_requires_ledger(self):
        import inspect
        from core.fused.downstream.action_seq import plan_actions
        sig = inspect.signature(plan_actions)
        assert sig.parameters["ledger"].default is inspect.Parameter.empty

    def test_rejection_is_always_recorded(self):
        """★ 端到端：域外动作**一定**落一条台账（不静默）。"""
        ledger = ActionLedger()
        seq = ActionSequence(actions=(
            Action(op=OP_UPDATE, msg_index=0, field_path="raw_bytes", value="x"),
        ))
        apply_actions(_seed(), seq, ledger=ledger)
        assert ledger.reason_counts().get("field_path_out_of_domain") == 1
