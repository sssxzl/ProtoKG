# -*- coding: utf-8 -*-
"""tests/test_required_headers_global_channel.py —— P2-1：消息级必填头的活通道。

★ 背景（`打通缺口清单-20261106.md` §P2-1）：
  RFC 源会抽出 ``aspect=required_header_global`` 的事实（实测 rtsp 1 条 CSeq、
  sip 6 条 To/From/CSeq/Call-ID/Max-Forwards/Via），但 ``_BUCKET_BY_KIND``
  **没有这一项** ⇒ 事实被直接丢弃。于是：

    · ``required_headers`` 桶 **100% 由 profile 骨架提供**（rtsp 8 / sip 14）；
    · RFC 抽到的「消息级必填头」是条**死通道**（抽了等于没抽）。

  修复：映射到 ``required_headers`` 桶，用 ``"*"`` 键表示「**所有方法**都要带」，
  消费端统一用 :func:`required_headers_for` 读（全局 + 方法级合并）。
"""
from __future__ import annotations

from core.fused.downstream.rag_seedgen import (
    _GLOBAL_REQUIRED_KEY,
    assemble_bundle,
    load_fact_views,
    required_headers_for,
)
from core.models import SeedCorpus, SeedMessage


def _bundle(protocol: str) -> dict:
    views = load_fact_views(protocol)
    return assemble_bundle(views, protocol, source_set=["rfc"],
                           apply_allowed_methods=False,
                           include_skeleton_methods=False)


# ===========================================================================
# ① 桶内容：全局必填头真的进来了
# ===========================================================================

def test_global_key_present_for_rtsp_and_sip():
    """rtsp → CSeq；sip → 六个核心头（都来自 RFC 原文）。"""
    rtsp = _bundle("rtsp")["required_headers"]
    assert rtsp.get(_GLOBAL_REQUIRED_KEY) == ["CSeq"], rtsp.get(_GLOBAL_REQUIRED_KEY)

    sip = _bundle("sip")["required_headers"]
    glob = set(sip.get(_GLOBAL_REQUIRED_KEY) or [])
    assert {"To", "From", "CSeq", "Call-ID", "Max-Forwards", "Via"} <= glob, glob


def test_global_fact_does_not_touch_other_buckets():
    """★ 只进 ``required_headers`` —— methods / transitions 必须逐条不变。

    否则就是「修一个洞开另一个洞」：给 methods 桶加条目会让 prompt 渲染变化
    ⇒ 种子漂移。
    """
    b = _bundle("rtsp")
    assert len(b["methods"]) == 11
    assert len(b["transitions"]) == 14
    # 全局必填头的头名**不得**出现在 methods 桶里（它是 header，不是 verb）
    assert "CSEQ" not in {str(m).upper() for m in b["methods"]}


def test_provenance_records_rfc_authority():
    """溯源要能说明「这些全局头来自 rfc 源」。"""
    b = _bundle("rtsp")
    src = (b.get("by_source") or {}).get("required_headers") or {}
    assert src.get("rfc", 0) >= 1, src


# ===========================================================================
# ② required_headers_for：全局 + 方法级合并
# ===========================================================================

def test_helper_unions_global_and_method_level():
    m = {"*": ["CSeq"], "SETUP": ["Transport", "Session"]}
    assert required_headers_for(m, "SETUP") == ["CSeq", "Transport", "Session"]


def test_helper_dedupes_and_is_case_insensitive():
    m = {"*": ["CSeq"], "setup": ["CSeq", "Transport"]}
    assert required_headers_for(m, "SETUP") == ["CSeq", "Transport"]


def test_helper_returns_global_for_unknown_method():
    """★ 核心价值：没有方法级清单的方法，也拿得到全局必填头。"""
    m = {"*": ["CSeq"], "SETUP": ["Transport"]}
    assert required_headers_for(m, "ANNOUNCE") == ["CSeq"]


def test_helper_empty_inputs():
    assert required_headers_for({}, "SETUP") == []
    assert required_headers_for(None, "SETUP") == []


def test_helper_ignores_blank_names():
    assert required_headers_for({"*": ["CSeq", "", None]}, "SETUP") == ["CSeq"]


# ===========================================================================
# ③ 端到端：删「全局必填头」必须被拒（P2-2 守卫）
# ===========================================================================

def test_removing_global_required_header_is_rejected():
    """rtsp 的 ANNOUNCE **没有方法级**必填头，但全局有 CSeq。

    ⇒ 修复前 `_reject_reason` 的 ``reqs`` 是空集 ⇒ 「删 CSeq」被放行；
      修复后必须拒（服务端必拒收该报文 ⇒ 零价值动作）。

    ★ 为什么用 `_reject_reason` 而不是 R1（补头）：R1 在「取不到非空兜底值」
      时会**不产出动作**（R-2 的 fail-closed），因而无法稳定观察全局通道；
      拒绝守卫是纯判定，确定性更好。
    """
    from core.fused.downstream.action_seq import (
        Action, OP_REMOVE, REJECT_HEADER_IS_REQUIRED, _reject_reason,
    )

    rh = _bundle("rtsp")["required_headers"]
    assert _GLOBAL_REQUIRED_KEY in rh
    # ANNOUNCE 只在全局清单里（方法级没有）
    assert "ANNOUNCE" not in rh, "前提变了：ANNOUNCE 现在有方法级清单"

    msg = SeedMessage(method="ANNOUNCE", headers={"CSeq": "1"}, body="",
                      url="rtsp://127.0.0.1:8554/stream", argument="")
    act = Action(OP_REMOVE, 0, "headers.CSeq", None)
    assert _reject_reason(act, msg, required_headers=rh) == \
        REJECT_HEADER_IS_REQUIRED


def test_removing_non_required_header_still_allowed():
    """对照：删一个**非**必填头不应被这条守卫拦（避免守卫变成"全都拒"）。"""
    from core.fused.downstream.action_seq import (
        Action, OP_REMOVE, REJECT_HEADER_IS_REQUIRED, _reject_reason,
    )

    rh = _bundle("rtsp")["required_headers"]
    msg = SeedMessage(method="ANNOUNCE", headers={"X-Opt": "1"}, body="",
                      url="rtsp://127.0.0.1:8554/stream", argument="")
    act = Action(OP_REMOVE, 0, "headers.X-Opt", None)
    assert _reject_reason(act, msg, required_headers=rh) != \
        REJECT_HEADER_IS_REQUIRED
