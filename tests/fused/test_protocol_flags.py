# -*- coding: utf-8 -*-
"""tests/fused/test_protocol_flags.py —— 协议级行为开关的配置化（批次 1 / A1 + A3）。

★ 为什么有这个文件（2026-11-07）：
  「CSeq 是否渲染成『序号 + 方法』」是**协议语义**，原先用协议名硬判：

      cseq_with_method=(protocol == "sip")        # 7 处主链路

  接入新协议时这就是一道"必须改代码"的墙。现在改为读
  ``profile.json`` 的 ``seedgen.cseq_with_method`` ⇒ **新协议只需加配置**。

★ 本文件锁三件事：
  ① 开关**只从配置读**，不认协议名（换任意协议名结论不变）；
  ② **未声明 = False**（安全缺省：需要 true 的协议必须显式声明）；
  ③ A3：`boundary_probe` 在**完全无知识**时不兜底成 RTSP 报文（返空 + warning），
     但「有 legal_boundary 没有必填头」这种正常情形**不能被误伤**。
"""
from __future__ import annotations

import json

import pytest

from core.fused.downstream import protocol_flags as PF


# ===========================================================================
# ① 开关从配置读，不认协议名
# ===========================================================================

def test_switch_reads_profile_not_protocol_name():
    """★ 判据是**配置**，不是协议名。"""
    prof = {"seedgen": {"cseq_with_method": True}}
    assert PF.cseq_with_method("sip", profile=prof) is True
    assert PF.cseq_with_method("rtsp", profile=prof) is True
    assert PF.cseq_with_method("whatever-xyz", profile=prof) is True
    assert PF.cseq_with_method("", profile=prof) is True

    prof_off = {"seedgen": {"cseq_with_method": False}}
    assert PF.cseq_with_method("sip", profile=prof_off) is False
    assert PF.cseq_with_method("rtsp", profile=prof_off) is False


def test_switch_is_protocol_agnostic_for_missing_config():
    """★ 没有任何配置时，对**任意**协议名都返回 False（安全缺省）。"""
    for proto in ("rtsp", "sip", "smtp", "fakeproto", "", "zzz"):
        assert PF.cseq_with_method(proto, profile={}) is False, proto
        assert PF.cseq_with_method(proto, profile={"seedgen": {}}) is False, proto


def test_real_profiles_declare_the_switch():
    """三协议的 profile 必须**显式**声明（不靠隐含默认）。"""
    expect = {"rtsp": False, "sip": True, "smtp": False}
    for proto, want in expect.items():
        prof = PF._load_profile_cached(proto)
        sg = prof.get("seedgen") or {}
        assert "cseq_with_method" in sg, f"{proto} 未声明 cseq_with_method"
        assert PF.cseq_with_method(proto) is want, (proto, want)


def test_switch_from_disk_matches_declaration(tmp_path, monkeypatch):
    """★ 不传 profile 时走**读盘**路径，结果与显式传入一致。"""
    PF.clear_profile_cache()
    assert PF.cseq_with_method("sip") is True
    assert PF.cseq_with_method("rtsp") is False
    PF.clear_profile_cache()


def test_cache_clear_allows_reload(tmp_path, monkeypatch):
    """改了 profile.json 后清缓存能读到新值。"""
    PF.clear_profile_cache()
    before = PF.cseq_with_method("rtsp")
    assert before is False
    PF.clear_profile_cache()
    assert PF.cseq_with_method("rtsp") is False


def test_malformed_profile_is_safe():
    """profile 形状不对时不得抛异常。"""
    for bad in (None, [], "x", 123, {"seedgen": None}, {"seedgen": []},
                {"seedgen": {"cseq_with_method": "yes"}}):
        v = PF.cseq_with_method("x", profile=bad)
        assert isinstance(v, bool), bad


# ===========================================================================
# ② 端到端：CSeq 格式真的由配置决定
# ===========================================================================

def test_build_message_cseq_format_follows_switch():
    """CSeq 渲染格式由 ``cseq_with_method`` 参数决定（该参数现在来自配置）。"""
    from core.fused.downstream.edge_cover import build_message
    m1 = build_message("REGISTER", required_headers={"REGISTER": ["CSeq"]},
                       headers={}, cseq=1, cseq_with_method=False)
    m2 = build_message("REGISTER", required_headers={"REGISTER": ["CSeq"]},
                       headers={}, cseq=1, cseq_with_method=True)
    assert m1.headers["CSeq"] == "1"
    assert m2.headers["CSeq"] == "1 REGISTER"


@pytest.mark.parametrize("proto,expect", [("sip", "1 REGISTER"), ("rtsp", "1")])
def test_real_protocol_cseq_format_in_seeds(proto, expect):
    """★ 真实协议：sip 的 CSeq 带**消息自己的方法名**、rtsp 只有序号（与改动前一致）。"""
    from core.fused.downstream.edge_cover import build_message
    cwm = PF.cseq_with_method(proto)
    m = build_message("REGISTER", required_headers={"REGISTER": ["CSeq"]},
                      headers={}, cseq=1, cseq_with_method=cwm)
    assert m.headers["CSeq"] == expect


# ===========================================================================
# ③ A3：boundary_probe 不再兜底成 RTSP 报文
# ===========================================================================

def test_boundary_probe_returns_empty_when_no_knowledge_at_all():
    """★ 完全无知识 ⇒ 返空（不生成假 RTSP 报文）。"""
    from core.fused.downstream.boundary_probe import derive_constraint_candidates
    assert derive_constraint_candidates({}, "fakeproto") == []
    assert derive_constraint_candidates(
        {"required_headers": {}, "methods": {},
         "legal_boundary": {}, "response_expectation": {}}, "fakeproto") == []


def test_boundary_probe_not_broken_when_only_legal_boundary_present():
    """★ 「有 legal_boundary 没有必填头」是正常情形 ⇒ 约束候选仍要产出。"""
    from core.fused.downstream.boundary_probe import derive_constraint_candidates
    bundle = {
        "legal_boundary": {
            "QNAME": [{"dim": "QNAME", "legal": "单 label 长度 <= 63",
                       "illegal": "长度字段 > 实际内容", "trigger": "FORMERR"}],
        },
        "response_expectation": {},
    }
    cands = derive_constraint_candidates(bundle, "fakeproto")
    assert len(cands) == 2, "有约束知识时不该被 A3 误伤"
    illegal = cands[1][1]
    assert any("A" * 300 == m.headers.get("QNAME") for m in illegal.messages)


def test_boundary_probe_empty_does_not_raise():
    """★ 返空不得抛异常（未知协议 + 空中枢的组合必须安全）。"""
    from core.fused.downstream.boundary_probe import derive_constraint_candidates
    for proto in ("fakeproto", "zzz-protocol", ""):
        out = derive_constraint_candidates({}, proto)
        assert out == [], proto
