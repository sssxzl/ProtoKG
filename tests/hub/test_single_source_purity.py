# -*- coding: utf-8 -*-
"""tests/test_single_source_purity.py —— P0-1：严格单源下的方法集纯净度。

★ 守的是什么不变量（`docs` 见
  `rag-chatafl个人想法/方案改进问题/rfc源改进/打通缺口清单-20261106.md` §P0-1）：

  ``assemble_bundle`` 里 **裁剪**（`apply_allowed_methods`）与 **并入**
  （`include_skeleton_methods`）是**两个独立机制**：

    · 裁剪 —— 用 ``profile.allowed_methods``（源码侧白名单）**删掉** RFC 抽到的方法；
    · 并入 —— 骨架（authority=``profile``）的 ``existence`` 事实经
      ``_BUCKET_BY_KIND[("method","existence")]`` **新建** ``methods`` 桶条目。

  只关裁剪**挡不住**并入 ⇒ 实测 sip 被注入 ``INFO``/``SUBSCRIBE``（RFC 2976/3265，
  不在 RFC 3261 里）、smtp 被注入 ``AUTH``（RFC 4954，不在 RFC 5321 里）
  ⇒ 「RFC 单源纯净度」这一主张就站不住。

  ⇒ 严格单源必须同时关掉「并入」：``include_skeleton_methods=False``。
"""
from __future__ import annotations

from core.fused.downstream.rag_seedgen import (
    assemble_bundle,
    load_fact_views,
    load_source_manifest,
)

PROTOCOLS = ("rtsp", "sip", "smtp")


# ===========================================================================
# 真实数据：严格单源 ⇒ methods 键集合 ⊆ RFC 定义的方法集合
# ===========================================================================

def _hub_source_set(protocol: str) -> list[str]:
    doc = load_source_manifest(protocol) or {}
    return [str(s).strip().lower() for s in (doc.get("source_set") or [])]


def _rfc_defined_methods(views: list[dict]) -> set[str]:
    """RFC 侧 ``definition`` 事实声明的方法集合（**唯一的合法方法来源**）。"""
    out: set[str] = set()
    for v in views:
        fk = v.get("fact_key") or {}
        subj = fk.get("subject") or {}
        if fk.get("aspect") != "definition" or subj.get("type") != "method":
            continue
        if any(str(c.get("authority") or "").strip().lower() == "rfc"
               for c in (v.get("all_claims") or [])):
            out.add(str(subj.get("name") or "").strip().upper())
    return {m for m in out if m}


def _assemble(protocol: str, *, strict: bool) -> dict:
    """按**单源态**组装（自建 source_set，不依赖中枢当前的数据状态）。

    ★ 为什么自建：中枢可能刚被建成**多源**（五源全开）⇒ 此时
      「中枢应是单源态」这个前提不成立 ⇒ 断言会因**数据状态**而失败，
      而不是因被测逻辑失败。
      ⇒ 本用例要验的是「**单源态下的纯净度**」⇒ 显式构造单源态。
    ★ 阶段 E5：骨架已消解 ⇒ 「严格单源」不再靠关闭骨架并入实现，
      而是靠 ``source_set`` 只含 rfc ⇒ ``include_skeleton_methods`` 保留为
      兼容开关（其「并入骨架」分支现已无对象）。
    """
    views = load_fact_views(protocol)
    src_set = ["rfc"]
    apply_allowed = False          # source ∉ source_set ⇒ 严格单源
    return assemble_bundle(
        views, protocol, source_set=src_set,
        apply_allowed_methods=apply_allowed,
        include_skeleton_methods=False if strict else True)


def test_rfc_definition_facts_exist_for_all_protocols():
    """前置：三协议都有 RFC 侧方法定义事实（否则下面的子集断言会空转成空集）。"""
    for p in PROTOCOLS:
        assert _rfc_defined_methods(load_fact_views(p)), f"{p} 没有 RFC 方法定义事实"


def test_strict_single_source_methods_are_rfc_defined_only():
    """★ 核心断言：严格单源下，methods 桶里每个方法都必须有 RFC 定义事实。"""
    for p in PROTOCOLS:
        rfc_methods = _rfc_defined_methods(load_fact_views(p))
        got = set(_assemble(p, strict=True)["methods"])
        extra = got - rfc_methods
        assert not extra, (
            f"[{p}] 严格单源下 methods 桶仍含**非 RFC 定义**的方法：{sorted(extra)}"
            f"（RFC 定义集 = {sorted(rfc_methods)}）")


# ===========================================================================
# 合成数据：行为的精确边界
# ===========================================================================

def _view(stype: str, aspect: str, authority: str, name: str,
          fid: str, *, data=True, epistemic: str = "normative") -> dict:
    """构造一条能真正进桶的最小事实（形状与 `assemble_bundle` 的读法一致）。"""
    return {
        "fact_key": {
            "protocol": "rtsp", "version": "1.0",
            "subject": {"type": stype, "name": name,
                        "qualifiers": {}, "path": []},
            "aspect": aspect, "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": fid, "fact_id": fid,
            "value": {"type": "struct", "data": data},
            "epistemic_type": epistemic, "authority": authority,
            "scope": None, "evidence_summary": [f"{authority}:{name}"],
        }],
    }


def _synthetic(*views: dict, strict: bool) -> dict:
    return assemble_bundle(list(views), "rtsp", source_set=["rfc"],
                           apply_allowed_methods=False,
                           include_skeleton_methods=not strict)


def test_rfc_side_existence_is_never_dropped():
    """authority=rfc 的 ``existence`` 事实**不受**该开关影响（只挡骨架）。"""
    views = (_view("method", "existence", "rfc", "ANNOUNCE", "f_rfc_exist"),)
    assert "ANNOUNCE" in _synthetic(*views, strict=True)["methods"]


def test_dropped_fact_not_registered_in_provenance_ledger():
    """★ 溯源台账必须如实：被丢弃的事实**不得**记进 ``by_source`` / ``fact_index``。

    （否则「台账说这条进了桶、桶里却没有」⇒ 审计时会误判为已采用。）
    """
    views = (_view("method", "existence", "profile", "SUBSCRIBE", "f_drop_me",
                   epistemic="observed"),)
    b = _synthetic(*views, strict=True)
    assert "f_drop_me" not in (b.get("fact_index") or {}), \
        "被丢弃的事实不该出现在 fact_index"
    assert "SUBSCRIBE" not in (b.get("methods") or {})
