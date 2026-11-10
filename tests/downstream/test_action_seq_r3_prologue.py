# -*- coding: utf-8 -*-
"""tests/fused/test_action_seq_r3_prologue.py —— R-3（P0）回归用例。

★ R-3（P0，QA 第二轮新查出）：⑤（action-seq 变异层）种子**从未**被
  ``_prepend_session_prologue`` 补 prologue。

  成因：``scripts/seedgen.py`` 里 ``_prepend_session_prologue`` 只对**基准层**跑，
  而 ⑤ 在流程**最后**才追加 ⇒ ⑤ 从不经过这一步。
  实测（QA）：sip/C 组 ⑤ 层 48 条种子里 **46 条（96%）**首消息不是 REGISTER
  ⇒ 非 REGISTER 不进 kamailio 的 registrar 路由 ⇒ **被静默丢弃**
  ⇒ AFLNet 收不到响应（「No server states have been detected」）
  ⇒ 正是 ``seedgen.py`` 自己注释里点名的 SIP 覆盖率低根因。

★ 结构性修复：⑤ 的后处理链**收敛成一个函数**
  ``_postprocess_action_seq_seeds()``（prologue → {seq} → 端点/资源归一化
  → 响应回传地址重写）⇒ R-1（漏 ``_rewrite_client_headers``）与
  R-3（漏 ``_prepend_session_prologue``）**连续两次同根因**不再复发。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.fused.downstream.action_seq import (
    ACTION_SEQ_GENERATED_BY,
    Action,
    ActionLedger,
    ActionSequence,
    apply_actions,
)
from core.models import SeedCorpus, SeedMessage

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# 夹具
# ===========================================================================

def _sip_profile() -> dict:
    return json.loads((ROOT / "profiles" / "sip" / "profile.json")
                      .read_text(encoding="utf-8"))


def _bundle() -> dict:
    """最小知识中枢：SIP 的必填头 + 一个 REGISTER 自环（prologue 的入口边）。"""
    return {
        "required_headers": {
            "REGISTER": ["Via", "From", "To", "Call-ID", "CSeq", "Max-Forwards"],
            "INVITE": ["Via", "From", "To", "Call-ID", "CSeq", "Max-Forwards"],
        },
        "session_header": {},
        "headers": {
            "Via": {"values": ["SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK1"]},
            "From": {"values": ["<sip:alice@127.0.0.1>;tag=a"]},
            "To": {"values": ["<sip:bob@127.0.0.1>;tag=b"]},
            "Call-ID": {"values": ["cid@127.0.0.1"]},
            "Max-Forwards": {"values": ["70"]},
            "CSeq": {"values": [""]},
        },
        "statuses": {"200": "OK"},
        "transitions": [("Idle", "REGISTER", "Idle"),
                        ("Idle", "INVITE", "Ready")],
        "message_instances": {},
    }


def _invite_seed() -> SeedCorpus:
    """一颗**首消息不是 REGISTER** 的 SIP 种子（正是被 kamailio 静默丢弃的形态）。"""
    return SeedCorpus(
        seed_id="base-1",
        protocol="sip",
        description="base",
        target_state_path=["Idle"],
        target_methods=["INVITE"],
        messages=[
            SeedMessage(method="INVITE",
                        headers={"Via": "SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK2",
                                 "From": "<sip:alice@127.0.0.1>;tag=a",
                                 "To": "<sip:bob@127.0.0.1>;tag=b",
                                 "Call-ID": "cid@127.0.0.1",
                                 "CSeq": "2 INVITE",
                                 "Max-Forwards": "70"},
                        body="", url="sip:127.0.0.1:5060", argument=""),
        ],
        generated_by=ACTION_SEQ_GENERATED_BY,
    )


# ===========================================================================
# R-3：⑤ 种子必须补 prologue
# ===========================================================================

class TestR3PrologueForActionSeqSeeds:
    """★ R-3（P0）：⑤ 种子必须与基准层**同样**补 prologue。"""

    def test_postprocess_entry_point_exists(self):
        """★ 结构性修复：⑤ 的后处理链必须收敛在**一个**函数里。"""
        import scripts.seedgen as seedgen_mod
        assert hasattr(seedgen_mod, "_postprocess_action_seq_seeds"), \
            "⑤ 的后处理链必须收敛在 _postprocess_action_seq_seeds（防第三次漏步骤）"

    def test_action_seq_seed_gets_register_prologue(self):
        """⑤ 种子插完 prologue ⇒ **首消息是 REGISTER**（否则被 kamailio 丢弃）。"""
        import scripts.seedgen as seedgen_mod
        seed = _invite_seed()
        out = seedgen_mod._postprocess_action_seq_seeds(
            [seed], _bundle(), _sip_profile(), "sip")
        assert out[0].messages[0].method.upper() == "REGISTER", \
            "⑤ 种子必须以协议入口方法（REGISTER）开头"

    def test_prologue_message_has_cseq_one(self):
        """新插入的入口消息拿 ``CSeq: 1``。"""
        import scripts.seedgen as seedgen_mod
        out = seedgen_mod._postprocess_action_seq_seeds(
            [_invite_seed()], _bundle(), _sip_profile(), "sip")
        first = out[0].messages[0]
        assert str(first.headers.get("CSeq", "")).startswith("1"), \
            f"入口消息的 CSeq 应为 1，实际 {first.headers.get('CSeq')!r}"

    def test_existing_cseq_is_shifted_not_renumbered(self):
        """★ 原有消息的 CSeq 必须**平移 +1**（让位），**不能**重排。

        重排会把 ``cseq-replay`` 的变异（本条序号 == 下一条序号）**静默抹掉**
        （P0-3：实测 96% 的 CSeq 变异被抹）⇒ 平移只改绝对值、相对关系不变。
        """
        import scripts.seedgen as seedgen_mod
        # 构造「cseq-replay 变异形态」：两条消息的 CSeq 相同（都是 2）
        seed = _invite_seed()
        seed.messages.append(SeedMessage(
            method="INVITE",
            headers={"Via": "SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK3",
                     "From": "<sip:alice@127.0.0.1>;tag=a",
                     "To": "<sip:bob@127.0.0.1>;tag=b",
                     "Call-ID": "cid@127.0.0.1",
                     "CSeq": "2 INVITE",          # ← 与上一条相同（重放形态）
                     "Max-Forwards": "70"},
            body="", url="sip:127.0.0.1:5060", argument=""))
        out = seedgen_mod._postprocess_action_seq_seeds(
            [seed], _bundle(), _sip_profile(), "sip")
        seqs = [str(m.headers.get("CSeq", "")).split()[0]
                for m in out[0].messages]
        assert seqs[0] == "1", f"入口消息应拿 1，实际 {seqs}"
        assert seqs[1] == seqs[2] == "3", \
            f"重放形态必须保留（平移后两条同为 3），实际 {seqs}"

    def test_cseq_numbers_are_unique_after_prologue(self):
        """插完 prologue 后 CSeq 序号**不得重复**（否则服务端拒收）。"""
        import scripts.seedgen as seedgen_mod
        seed = _invite_seed()
        seed.messages.append(SeedMessage(
            method="INVITE",
            headers={"Via": "SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK3",
                     "From": "<sip:alice@127.0.0.1>;tag=a",
                     "To": "<sip:bob@127.0.0.1>;tag=b",
                     "Call-ID": "cid@127.0.0.1",
                     "CSeq": "3 INVITE",
                     "Max-Forwards": "70"},
            body="", url="sip:127.0.0.1:5060", argument=""))
        out = seedgen_mod._postprocess_action_seq_seeds(
            [seed], _bundle(), _sip_profile(), "sip")
        seqs = [str(m.headers.get("CSeq", "")).split()[0]
                for m in out[0].messages]
        assert len(seqs) == len(set(seqs)), f"CSeq 序号重复：{seqs}"

    def test_generated_by_is_preserved(self):
        """★ 补 prologue **不得**改写 ``generated_by``（否则 ⑤ 层会落成 L0）。"""
        import scripts.seedgen as seedgen_mod
        out = seedgen_mod._postprocess_action_seq_seeds(
            [_invite_seed()], _bundle(), _sip_profile(), "sip")
        assert out[0].generated_by == ACTION_SEQ_GENERATED_BY

    def test_base_layer_seed_is_unaffected_by_action_seq_path(self):
        """★ 基准层（``generated_by`` 不是 ⑤）走**基准层**的重排路径，不受平移影响。"""
        import scripts.seedgen as seedgen_mod
        seed = _invite_seed()
        seed.generated_by = "rule-based:edge-cover"
        out = seedgen_mod._prepend_session_prologue(
            [seed], _bundle(), _sip_profile())
        seqs = [str(m.headers.get("CSeq", "")).split()[0]
                for m in out[0].messages]
        assert seqs == ["1", "2"], f"基准层应被重排为 1..N，实际 {seqs}"

    def test_shift_is_idempotent_for_plain_numbers(self):
        """``_shift_cseq_by_one`` 只改序号、保留「序号 + 方法」形态。"""
        import scripts.seedgen as seedgen_mod
        seed = SeedCorpus(protocol="sip", description="x", messages=[
            SeedMessage(method="INVITE", headers={"CSeq": "7 INVITE"},
                        body="", url="", argument="")])
        seedgen_mod._shift_cseq_by_one(seed)
        assert seed.messages[0].headers["CSeq"] == "8 INVITE"

    def test_shift_leaves_non_numeric_cseq_untouched(self):
        import scripts.seedgen as seedgen_mod
        seed = SeedCorpus(protocol="sip", description="x", messages=[
            SeedMessage(method="INVITE", headers={"CSeq": "abc"},
                        body="", url="", argument="")])
        seedgen_mod._shift_cseq_by_one(seed)
        assert seed.messages[0].headers["CSeq"] == "abc"


# ===========================================================================
# P2-6：零变异丢弃必须**区分成因**
# ===========================================================================

class TestP26ZeroMutationCauseSplit:
    """★ P2-6：零变异不是一个笼统数字（无法区分改进方向）。"""

    def test_info_reports_split_causes(self):
        import scripts.seedgen as seedgen_mod
        import inspect
        src = inspect.getsource(seedgen_mod._build_action_seq_seeds)
        assert "zero_no_rule" in src and "zero_all_rejected" in src, \
            "零变异必须拆成「无规则命中」与「规则全被拒」两个计数"
