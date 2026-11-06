# -*- coding: utf-8 -*-
"""tests/fused/test_single_source_purity.py —— P0-1：严格单源下的方法集纯净度。

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
    views = load_fact_views(protocol)
    src_set = _hub_source_set(protocol) or None
    # 与 scripts/seedgen.py 同源判定：source ∉ source_set ⇒ 严格单源
    apply_allowed = (not src_set) or ("source" in {s.lower() for s in src_set})
    assert not apply_allowed, f"{protocol} 的中枢应是单源态（实测 source_set={src_set}）"
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


def test_default_flag_keeps_skeleton_methods_unchanged():
    """默认（不传新参数）必须与历史行为逐字节一致 ⇒ 骨架方法仍被并入。

    ★ 这条是「默认路径不得被悄悄改变」的守卫：显式 True 与不传必须等价。
    """
    for p in PROTOCOLS:
        views = load_fact_views(p)
        src_set = _hub_source_set(p) or None
        base = assemble_bundle(views, p, source_set=src_set,
                               apply_allowed_methods=False)
        explicit = assemble_bundle(views, p, source_set=src_set,
                                   apply_allowed_methods=False,
                                   include_skeleton_methods=True)
        assert set(base["methods"]) == set(explicit["methods"]), p


def test_skeleton_only_methods_are_actually_dropped():
    """严格单源**确实**减少了条目（证明修复有效，而不是空转）。

    实测：sip −2（INFO/SUBSCRIBE）、rtsp ±0（骨架是 RFC 子集）、
    smtp ±0 —— ⚠ smtp 的 ``AUTH`` 原本也是骨架独有的，但它在 **RFC 4954 §8**
    里有定义（``auth-command = "AUTH" SP ...``），已由「ABNF 命令规则字面量」
    通道补成 rfc 事实 ⇒ 严格单源下**不再消失**（这才是正确形态：
    该由 RFC 提供的方法，不能靠关掉骨架来"纯净"，要先把抽取补上）。

    用「差集」而不是硬编码条数 ⇒ 数据更新时测试不脆。
    """
    expected = {"rtsp": 0, "sip": 2, "smtp": 0}
    for p, n in expected.items():
        loose = set(_assemble(p, strict=False)["methods"])
        strict = set(_assemble(p, strict=True)["methods"])
        assert strict <= loose, p
        assert len(loose) - len(strict) == n, (
            f"[{p}] 期望严格单源减少 {n} 个骨架方法，实测减少 "
            f"{len(loose) - len(strict)} 个：{sorted(loose - strict)}")


def test_smtp_auth_comes_from_rfc_not_skeleton():
    """★ smtp 的 ``AUTH`` 必须由 **RFC 事实**提供（RFC 4954 §8 的 ABNF 规则）。

    修复前它只存在于骨架（authority=profile）里 ⇒ 「RFC 单源」实际上是
    「RFC + 骨架」；把它从骨架里挡掉又会**丢方法**。正解是先补抽取。
    """
    views = load_fact_views("smtp")
    rfc_methods = _rfc_defined_methods(views)
    assert "AUTH" in rfc_methods, (
        "AUTH 应由 rfc4954 的 auth-command ABNF 规则抽到；"
        f"当前 RFC 定义集 = {sorted(rfc_methods)}")
    # 且严格单源下仍在 methods 桶里（说明它不是靠骨架补的）
    assert "AUTH" in _assemble("smtp", strict=True)["methods"]


def test_strict_single_source_does_not_touch_transitions():
    """★ 修复只动 ``methods`` 桶 —— 状态机（transitions）必须逐条不变。

    否则就是「修一个洞开另一个洞」：P0-1 只负责方法集纯净度，
    状态机的换源是另一条已收口的线（rtsp rfc 优先、sip/smtp 骨架兜底）。
    """
    for p in PROTOCOLS:
        loose = [tuple(t) for t in _assemble(p, strict=False)["transitions"]]
        strict = [tuple(t) for t in _assemble(p, strict=True)["transitions"]]
        assert loose == strict, f"[{p}] 严格单源不应改变状态机"


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


def test_skeleton_existence_still_enriches_rfc_defined_method():
    """既有 RFC 条目的方法：骨架的 ``existence`` 仍要能补 ``observed_by``（不丢溯源）。

    ★ 这是「只挡新建、不挡补证」的边界 —— 挡过头会把已有的溯源信息一并丢掉。
    """
    views = (
        _view("method", "definition", "rfc", "SETUP", "f_rfc_def"),
        _view("method", "existence", "profile", "SETUP", "f_prof_exist",
              epistemic="observed"),
    )
    b = _synthetic(*views, strict=True)
    assert "SETUP" in b["methods"], "RFC 定义过的 SETUP 不应被删"
    assert "profile" in (b["methods"]["SETUP"].get("observed_by") or set())


def test_skeleton_only_method_is_dropped_only_in_strict_mode():
    """只有骨架 ``existence``、没有 RFC ``definition`` 的方法 ⇒ 严格单源下被丢弃。"""
    views = (_view("method", "existence", "profile", "SUBSCRIBE", "f_prof_only",
                   epistemic="observed"),)
    assert "SUBSCRIBE" in _synthetic(*views, strict=False)["methods"]
    b = _synthetic(*views, strict=True)
    assert "SUBSCRIBE" not in b["methods"], "骨架独有的方法在严格单源下必须被丢弃"


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
