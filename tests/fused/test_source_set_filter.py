# -*- coding: utf-8 -*-
"""tests/fused/test_source_set_filter.py —— 批次 1.6 **步 2**（组装期源过滤）。

★ 覆盖四条：
  ① 组装期按 ``authority ∈ source_set`` 过滤 —— **其它源的条目根本不进桶**
     （不是「进去再标记」）；
  ② claim 级裁剪：跨源合并的 fact 里，非本次源的 claim 被剔除；
  ③ **协议骨架恒允许**（authority=profile）—— 它是跨实验复用的协议结构，
     不是源派生知识 ⇒ 单源调试时链路不断；
  ④ **不传 source_set ⇒ 不过滤 ⇒ 与引入前逐字节一致**（默认路径不变）。
"""
from __future__ import annotations

import importlib
import json

rag_seedgen = importlib.import_module("core.fused.downstream.rag_seedgen")
assemble_bundle = rag_seedgen.assemble_bundle

PROTOCOL = "rtsp"


def _transition_view(authority: str, src: str, method: str, dst: str,
                     fid: str = "f1", claim_id: str = "c1") -> dict:
    """构造一条「状态机边」事实（aspect=target_state, subject=relation）。"""
    view = _fact_view(authority, "target_state", subject_type="relation",
                      subject_name="transitions_to", fid=fid, claim_id=claim_id)
    view["fact_key"]["subject"]["qualifiers"] = {
        "source": {"type": "state", "name": src, "qualifiers": {}, "path": []},
        "target": {"type": "state", "name": dst, "qualifiers": {}, "path": []},
        "method": {"type": "method", "name": method, "qualifiers": {}, "path": []},
    }
    return view


def _fact_view(authority: str, aspect: str, subject_type: str = "method",
               subject_name: str = "SETUP", value=None, fid: str = "f1",
               claim_id: str = "c1", extra_claims: list | None = None) -> dict:
    claims = [{
        "claim_id": claim_id,
        "fact_id": fid,
        "value": {"type": "bool" if value is None else "struct",
                  "data": True if value is None else value},
        "epistemic_type": "normative",
        "authority": authority,
        "scope": None,
        "evidence_summary": [f"{authority}:{subject_name}"],
        "confidence": None,
    }]
    for i, c in enumerate(extra_claims or []):
        claims.append({
            "claim_id": f"{claim_id}_x{i}",
            "fact_id": f"{fid}_x{i}",
            "value": {"type": "struct", "data": c},
            "epistemic_type": "observed",
            "authority": authority,
            "scope": None,
            "evidence_summary": [f"{authority}:{subject_name}"],
            "confidence": None,
        })
    return {
        "fact_key": {
            "protocol": PROTOCOL,
            "version": "1.0",
            "subject": {"type": subject_type, "name": subject_name,
                        "qualifiers": {}, "path": []},
            "aspect": aspect,
            "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": claims,
    }


# ===========================================================================
# ① 其它源的条目根本不进桶
# ===========================================================================

def test_source_set_excludes_other_sources_from_buckets():
    """★ 传入 source_set ⇒ 其它源的条目**不进桶**。"""
    views = [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _fact_view("vuln", "security_property", subject_name="SETUP",
                   fid="f2", claim_id="c2"),
        _fact_view("traffic", "existence", subject_name="PLAY",
                   fid="f3", claim_id="c3"),
    ]
    b = assemble_bundle(views, PROTOCOL, source_set=["rfc"])

    # vuln 的安全属性、traffic 的存在性都**不在**桶里
    assert b["security"] == []
    # ★ 只看**事实派生**的部分（profile.json 兜底仍会注入方法全集 ⇒ 不在此断言）
    assert "PLAY" not in (b["methods"].get("PLAY") or {})
    assert "PLAY" not in b["methods"].get("PLAY", {}).get("declared_by", [])
    # rfc 的定义仍在
    assert "SETUP" in b["methods"]
    assert "rfc" in b["methods"]["SETUP"].get("declared_by", [])


def test_source_set_reflected_in_available_sources():
    """★ `available_sources` 只反映**实际进桶**的来源。"""
    views = [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _fact_view("vuln", "security_property", subject_name="SETUP",
                   fid="f2", claim_id="c2"),
    ]
    b = assemble_bundle(views, PROTOCOL, source_set=["rfc"])
    assert "vuln" not in b["available_sources"]
    assert "rfc" in b["available_sources"]


def test_source_set_none_keeps_everything():
    """★ **不传 source_set ⇒ 不过滤**（默认路径不变）。"""
    views = [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _fact_view("vuln", "security_property", subject_name="SETUP",
                   fid="f2", claim_id="c2"),
    ]
    filtered = assemble_bundle(views, PROTOCOL, source_set=["rfc"])
    unfiltered = assemble_bundle(views, PROTOCOL)
    assert unfiltered["security"]          # 未过滤时 vuln 的安全属性在桶里
    assert not filtered["security"]
    assert "vuln" in unfiltered["available_sources"]


def test_empty_source_set_filters_everything_but_skeleton():
    """★ 空集合 ⇒ 只剩骨架（profile）与 profile.json 兜底。"""
    views = [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _transition_view("profile", "Init", "SETUP", "Ready",
                         fid="f2", claim_id="c2"),
    ]
    b = assemble_bundle(views, PROTOCOL, source_set=[])
    # rfc 的条目被过滤掉（只剩 profile.json 兜底注入的方法全集）
    assert "rfc" not in b["methods"]["SETUP"].get("declared_by", [])
    # ★ 骨架恒允许
    assert b["transitions"], "协议骨架被误过滤 ⇒ 单源时链路会断"


# ===========================================================================
# ② claim 级裁剪
# ===========================================================================

def test_claim_level_pruning_drops_foreign_claims():
    """★ 跨源合并的 fact 里，非本次源的 claim 被**剔除**（不是整条丢弃）。"""
    merged = _fact_view("rfc", "definition", subject_name="SETUP",
                         fid="f1", claim_id="c1")
    merged["all_claims"].append({
        "claim_id": "c1_vuln",
        "fact_id": "f1_vuln",
        "value": {"type": "struct", "data": {"x": 1}},
        "epistemic_type": "observed",
        "authority": "vuln",
        "scope": None,
        "evidence_summary": ["vuln:SETUP"],
        "confidence": None,
    })
    b = assemble_bundle([merged], PROTOCOL, source_set=["rfc"])
    assert "vuln" not in b["available_sources"]
    assert "rfc" in b["available_sources"]
    # 这条 fact 本身**保留**（rfc 的 claim 在集合内）⇒ 方法仍在
    assert "SETUP" in b["methods"]


# ===========================================================================
# ③ 协议骨架恒允许
# ===========================================================================

def test_skeleton_profile_always_allowed():
    """★ 协议骨架（authority=profile）**不在** source_set 里也恒允许。"""
    views = [
        _transition_view("profile", "Init", "SETUP", "Ready",
                         fid="f1", claim_id="c1"),
    ]
    b = assemble_bundle(views, PROTOCOL, source_set=["rfc"])
    assert b["transitions"], "协议骨架被误过滤 ⇒ 单源时链路会断"
    assert "profile" in b["available_sources"]


# ===========================================================================
# ④ 默认路径逐字节不变
# ===========================================================================

def test_default_call_is_byte_identical_to_unfiltered():
    """★ 不传 source_set ⇒ 与「显式传全量集合」逐字节一致（默认路径不变）。"""
    views = [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _fact_view("vuln", "security_property", subject_name="SETUP",
                   fid="f2", claim_id="c2"),
    ]
    default = json.dumps(assemble_bundle(views, PROTOCOL),
                         ensure_ascii=False, sort_keys=True, default=str)
    explicit = json.dumps(
        assemble_bundle(views, PROTOCOL, source_set=["rfc", "vuln"]),
        ensure_ascii=False, sort_keys=True, default=str)
    assert default == explicit
