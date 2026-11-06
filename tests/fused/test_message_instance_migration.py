# -*- coding: utf-8 -*-
"""tests/fused/test_message_instance_migration.py —— 字段实例迁移与来源标注（P1-1c）。

★ 修的是什么（实测 bug）：
  `_align_message_instances` 原来写的是 ``allow_migrate=apply_allowed_methods``
  —— 把「**是否裁剪方法**」和「**是否搬迁字段实例**」两个**正交**语义绑在
  同一个旗标上。后果是**信息最多的模式拿到的字段知识最少**：

  | 协议 | 默认（全源，不裁剪） | 严格单源（裁剪） |
  |---|---|---|
  | rtsp | 转移 14 / 实例 **0**   | 转移 12 / 实例 12 |
  | sip  | 51 / 51               | 51 / 51 |
  | smtp | 64 / 64               | 64 / 64 |

  只有 rtsp 坏、且只在默认路径坏：骨架实例键是 ``Idle--SETUP-->Ready``，
  而采用的转移是 ``Init--SETUP-->Ready`` ⇒ 精确命中 0 条、又不许迁移 ⇒ 实例桶空。
  更糟的是严格单源那 12 条是**按方法迁移**来的骨架值，**没有任何来源标注**
  ⇒ 外面看不出它不是 RFC 原生知识（论文里就是「骨架值冒充 RFC」）。

★ 本文件锁四件事：
  ① 默认路径 rtsp 必须有实例，且严格单源数量不被这条改动带偏；
  ② sip/smtp 行为逐字节不变（全部 exact 命中，不产生迁移）；
  ③ 迁移出来的实例**必须**标 ``authority=profile`` / ``origin=migrated``，
     且 ``migrated_from`` 的方法与被填键**相同**；
  ④ `allow_instance_migrate=False` 能退回旧行为（纯净度极限模式仍可复现）。
"""
from __future__ import annotations

import pytest

from core.fused.downstream.rag_seedgen import (
    _align_message_instances,
    assemble_bundle,
    load_fact_views,
)

PROTOCOLS = ("rtsp", "sip", "smtp")


@pytest.fixture(scope="module")
def bundles():
    """三协议 × 两模式各组装一次（只读 derived 产物，无 LLM）。"""
    out = {}
    for proto in PROTOCOLS:
        views = load_fact_views(proto)
        # 「默认路径」= 全源（不裁剪方法）⇒ 必须显式传 False，
        # 因为 assemble_bundle 的形参默认值是 True（裁剪）。
        out[(proto, "default")] = assemble_bundle(
            views, proto, apply_allowed_methods=False)
        out[(proto, "strict")] = assemble_bundle(
            views, proto, apply_allowed_methods=True,
            include_skeleton_methods=False)
    return out


# ===========================================================================
# ① 默认路径必须有实例（这就是修的那个 bug）
# ===========================================================================

def test_rtsp_default_path_now_has_instances(bundles):
    """★ 修复前恒为 0；修复后应有 12 条按方法迁移来的模板。"""
    b = bundles[("rtsp", "default")]
    assert len(b["transitions"]) == 14
    assert len(b["message_instances"]) == 12


def test_rtsp_strict_single_source_unchanged(bundles):
    """严格单源原本就有 12 条 ⇒ 解耦不得改变它。"""
    assert len(bundles[("rtsp", "strict")]["message_instances"]) == 12


def test_sip_and_smtp_unchanged(bundles):
    """sip/smtp 的实例键本来就命中⇒ 两模式都必须与改动前一致。"""
    for proto, expect in (("sip", 51), ("smtp", 64)):
        for mode in ("default", "strict"):
            b = bundles[(proto, mode)]
            assert len(b["message_instances"]) == expect, (proto, mode)
            # 全量 exact，一条迁移都不该出现
            origins = {v["origin"] for v in
                       b["message_instance_provenance"].values()}
            assert origins == {"exact"}, (proto, mode, origins)


def test_instances_are_subset_of_transitions(bundles):
    """不变量：实例键 ⊆ 采用的转移键（迁移不得凭空造边）。"""
    for proto in PROTOCOLS:
        for mode in ("default", "strict"):
            b = bundles[(proto, mode)]
            trans = {(str(s), str(m).upper(), str(d))
                     for s, m, d in b["transitions"]}
            assert set(b["message_instances"]) <= trans, (proto, mode)


# ===========================================================================
# ② 来源标注（核心：不许冒充 RFC）
# ===========================================================================

def test_every_instance_has_provenance(bundles):
    for proto in PROTOCOLS:
        for mode in ("default", "strict"):
            b = bundles[(proto, mode)]
            assert set(b["message_instance_provenance"]) == set(
                b["message_instances"]), (proto, mode)


def test_migrated_instances_are_labelled_profile(bundles):
    """★ 迁移来的字段模板必须标 profile —— 它就是骨架值，不是 RFC 原生值。"""
    b = bundles[("rtsp", "default")]
    pv = b["message_instance_provenance"]
    assert len(pv) == 12
    for key, info in pv.items():
        assert info["origin"] == "migrated", key
        assert info["authority"] == "profile", key
        assert info["migrated_from"] is not None, key


def test_migration_preserves_method(bundles):
    """迁移只许**同方法**搬模板（换方法就是编造）。"""
    b = bundles[("rtsp", "default")]
    for key, info in b["message_instance_provenance"].items():
        src = info["migrated_from"]
        assert src is not None
        assert str(src[1]).upper() == str(key[1]).upper(), (src, key)


def test_migrated_fields_match_source_template():
    """迁移后字段内容必须与源模板**逐项相同**（只换状态名，不换值）。

    ★ 只能单元级验证：返回的 ``message_instances`` 里只有**迁移后**的键，
      原始骨架键（``migrated_from`` 指向的那个）通常不在其中。
    """
    fields = [("url", "rtsp://a"), ("Transport", "RTP/AVP/TCP")]
    mi = {("Idle", "SETUP", "Ready"): list(fields)}
    pv: dict = {}
    out = _align_message_instances(TRANS, mi, allow_migrate=True, provenance=pv)
    k = ("Init", "SETUP", "Ready")
    assert out[k] == fields
    assert pv[k]["migrated_from"] == ("Idle", "SETUP", "Ready")


# ===========================================================================
# ③ 单元级：_align_message_instances 的四种情形
# ===========================================================================

TRANS = [("Init", "SETUP", "Ready"), ("Ready", "PLAY", "Playing")]


def test_align_exact_hit_kept():
    mi = {("Init", "SETUP", "Ready"): [("url", "rtsp://a")]}
    pv: dict = {}
    out = _align_message_instances(TRANS, mi, allow_migrate=False,
                                   provenance=pv,
                                   instance_authority={("Init", "SETUP", "Ready"): "rfc"})
    assert out == mi
    assert pv[("Init", "SETUP", "Ready")] == {
        "authority": "rfc", "origin": "exact", "migrated_from": None}


def test_align_migrates_same_method_only():
    """只有同方法的模板可迁移；没有同方法模板的转移保持空缺。"""
    mi = {("Idle", "SETUP", "Ready"): [("url", "rtsp://a")]}
    pv: dict = {}
    out = _align_message_instances(TRANS, mi, allow_migrate=True,
                                   provenance=pv,
                                   instance_authority={
                                       ("Idle", "SETUP", "Ready"): "profile"})
    # SETUP 迁移成功；PLAY 没有同方法模板 ⇒ 不凭空造
    assert set(out) == {("Init", "SETUP", "Ready")}
    info = pv[("Init", "SETUP", "Ready")]
    assert info["origin"] == "migrated"
    assert info["authority"] == "profile"
    assert info["migrated_from"] == ("Idle", "SETUP", "Ready")


def test_align_without_migrate_drops_unmatched():
    mi = {("Idle", "SETUP", "Ready"): [("url", "rtsp://a")]}
    assert _align_message_instances(TRANS, mi, allow_migrate=False) == {}


def test_align_provenance_is_optional():
    """不传出参时不得报错（旧调用方零改动）。"""
    mi = {("Idle", "SETUP", "Ready"): [("url", "x")]}
    assert _align_message_instances(TRANS, mi, allow_migrate=True) != {}


def test_align_empty_transitions_keeps_all():
    """没有状态机时原样保留（既有不变量，见 test_bundle_provenance）。"""
    mi = {("A", "SETUP", "B"): [("url", "x")]}
    pv: dict = {}
    assert _align_message_instances([], mi, allow_migrate=True,
                                    provenance=pv) == mi
    assert pv[("A", "SETUP", "B")]["origin"] == "exact"


# ===========================================================================
# ④ 可回退：纯净度极限模式
# ===========================================================================

def test_migration_can_be_disabled():
    """`allow_instance_migrate=False` ⇒ rtsp 退回 0（旧行为完全可复现）。"""
    views = load_fact_views("rtsp")
    b = assemble_bundle(views, "rtsp", allow_instance_migrate=False)
    assert b["message_instances"] == {}
    assert b["message_instance_provenance"] == {}


def test_downstream_message_fields_are_per_method(bundles):
    """★ 端到端：修复后字段组合**随方法变化**，不再全方法同值。"""
    from core.fused.downstream.edge_cover import build_seed_from_edges

    b = bundles[("rtsp", "default")]
    seed = build_seed_from_edges(
        [("Init", "SETUP", "Ready"), ("Ready", "PLAY", "Playing")],
        required_headers=b["required_headers"], headers=b["headers"],
        init="Init", description="t", generated_by="test",
        message_instances=b["message_instances"], protocol="rtsp")
    setup, play = seed.messages[0], seed.messages[1]
    # SETUP 的模板里有 Transport/Session；PLAY 的有 Range
    assert "Transport" in setup.headers
    assert "Range" in play.headers
    # CSeq 由 build_message 递增，不被模板里的旧值打乱
    assert setup.headers["CSeq"] == "1"
    assert play.headers["CSeq"] == "2"
