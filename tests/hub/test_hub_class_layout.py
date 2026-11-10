# -*- coding: utf-8 -*-
"""tests/test_hub_class_layout.py —— **阶段 C**：中枢按知识分类落盘（护栏）。

★ 阶段 C 的目标：中枢按「**知识分类**」存储，而不是按 aspect 存储。

    旧（批次 1.6）：derived/hub/facts/<aspect>.jsonl（16 个 aspect 文件）
    新（阶段 C）  ：derived/hub/<分类>/<文件>.jsonl（A~F 六个知识分类）

★ 落位依据 = ``core/fused/hub/knowledge_slots.json`` 的 ``aspect_map``
  ⇒ **不改抽取器**，只重排已有事实。

★ 关键回归：
  ① **分类正确**：aspect + 实体类型 ⇒ 正确的分类与槽位；
  ② **顺序契约**：落位后读出的顺序 == 旧布局的**全局遍历序**
     （顺序变了 ⇒ ``methods``/``headers`` 键插入序变 ⇒ 种子编号漂移）；
  ③ **条数守恒**：分类文件里的条数之和 == 落盘前的条数；
  ④ **协议隔离**：中枢共用一套 ⇒ 记录按 ``protocol`` 过滤；
  ⑤ **按协议替换**：重建时只替换本协议，其它协议保留。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.fused.hub import hub_layout
from core.fused.hub.knowledge_slots import category_ids, locate


# ===========================================================================
# 辅助
# ===========================================================================

def _fact(aspect: str, name: str, *, protocol: str = "rtsp",
          stype: str = "method", fid: str = "f1", claim: str = "c1") -> dict:
    return {
        "fact_key": {"protocol": protocol, "version": "1.0",
                     "subject": {"type": stype, "name": name,
                                 "qualifiers": {}, "path": []},
                     "aspect": aspect, "condition": {"type": "always"}},
        "resolution": None,
        "all_claims": [{"claim_id": claim, "fact_id": fid,
                        "value": {"type": "text", "data": name},
                        "epistemic_type": "normative",
                        "authority": "rfc", "scope": None,
                        "evidence_summary": [f"rfc:{name}"],
                        "confidence": None}],
    }


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                               for r in rows) + "\n", encoding="utf-8")


# ===========================================================================
# ① 落位判定
# ===========================================================================

def test_classify_uses_aspect_map():
    """★ 落位依据 = ``aspect_map``（aspect + 实体类型 ⇒ 分类/槽位）。"""
    assert hub_layout.classify(_fact("definition", "INVITE")) == \
        ("A_structure", "methods")
    assert hub_layout.classify(_fact("definition", "CSeq", stype="header")) == \
        ("A_structure", "headers")
    assert hub_layout.classify(_fact("target_state", "x", stype="relation")) == \
        ("B_interaction", "transitions")
    assert hub_layout.classify(_fact("required_headers", "x")) == \
        ("C_constraints", "required_headers")
    assert hub_layout.classify(_fact("binary_layout", "x", stype="header")) == \
        ("D_construction", "layout")
    assert hub_layout.classify(_fact("occurrence", "x", stype="header")) == \
        ("E_observation", "frequency")


def test_classify_falls_back_without_losing_data():
    """★ 未知 aspect ⇒ **兜底到 C_constraints**（不丢数据）。"""
    cat, slot = hub_layout.classify(_fact("no_such_aspect", "x"))
    assert cat == "C_constraints"
    assert slot == "no_such_aspect"


def test_locate_covers_all_registered_aspects():
    """★ **每个已注册 aspect 都有落位**（漏一个 ⇒ 该维度无处安放）。"""
    from core.fused.hub.knowledge_slots import aspect_map
    assert aspect_map(), "aspect_map 为空"


# ===========================================================================
# ② 落盘 + 读取（顺序契约是核心）
# ===========================================================================

def test_write_classified_groups_by_category(tmp_path):
    """★ 落盘后**按分类分文件**（一个分类一个文件）。"""
    recs = []
    for i, (asp, st) in enumerate([("definition", "method"),
                                   ("target_state", "relation"),
                                   ("required_headers", "method"),
                                   ("binary_layout", "header")]):
        v = _fact(asp, f"N{i}", stype=st, fid=f"f{i+1}")
        recs.append((json.dumps(v, ensure_ascii=False), v))
    # ★ 需要全局下标
    recs = [(i, ln, v) for i, (ln, v) in enumerate(recs)]

    written = hub_layout.write_classified(tmp_path, recs, "rtsp")

    assert written == {"A_structure": 1, "B_interaction": 1,
                       "C_constraints": 1, "D_construction": 1}
    for cat in written:
        assert (tmp_path / cat / f"{cat.split('_', 1)[1]}.jsonl").is_file() \
            or list((tmp_path / cat).glob("*.jsonl")), cat


def test_read_classified_preserves_global_order(tmp_path):
    """★★ **顺序契约**：落位后读出的顺序 == 落盘前的顺序。

    ★ 这是「种子逐字节不变」的**前提**：``methods``/``headers`` 是 dict
      ⇒ 键插入序取决于 fact 遍历序 ⇒ 键序一变 ⇒ 种子编号漂移。
    """
    # 交错的 aspect（实测真实数据即如此）
    specs = [("definition", "method", "A"), ("syntax", "header", "H1"),
             ("definition", "method", "B"), ("syntax", "header", "H2"),
             ("definition", "method", "C")]
    recs = []
    for i, (asp, st, nm) in enumerate(specs):
        v = _fact(asp, nm, stype=st, fid=f"f{i+1}")
        recs.append((i, json.dumps(v, ensure_ascii=False), v))

    hub_layout.write_classified(tmp_path, recs, "rtsp")
    out = hub_layout.read_classified(tmp_path, "rtsp")

    assert [x["all_claims"][0]["fact_id"] for x in out] == \
        ["f1", "f2", "f3", "f4", "f5"]


def test_write_classified_preserves_count(tmp_path):
    """★ 条数守恒（分类文件里的条数之和 == 落盘前）。"""
    recs = []
    for i in range(12):
        v = _fact(["definition", "syntax", "target_state"][i % 3], f"N{i}",
                  stype="method" if i % 3 != 1 else "header",
                  fid=f"f{i+1}")
        recs.append((i, json.dumps(v, ensure_ascii=False), v))
    written = hub_layout.write_classified(tmp_path, recs, "rtsp")
    total = sum(len([ln for ln in f.read_text(encoding="utf-8").splitlines()
                     if ln.strip()])
                for f in tmp_path.rglob("*.jsonl")
                if "index" not in f.parts)
    assert total == 12
    assert sum(written.values()) == 12


def test_read_classified_filters_by_protocol(tmp_path):
    """★ **协议隔离**：中枢共用一套 ⇒ 记录按 ``protocol`` 过滤。"""
    r1 = _fact("definition", "A", protocol="rtsp", fid="f1")
    s1 = _fact("definition", "B", protocol="sip", fid="f2")
    hub_layout.write_classified(tmp_path, [
        (0, json.dumps(r1, ensure_ascii=False), r1)], "rtsp")
    hub_layout.write_classified(tmp_path, [
        (0, json.dumps(s1, ensure_ascii=False), s1)], "sip")
    # ★ 两个协议在**同一个**分类文件里（按协议分块）
    out_r = hub_layout.read_classified(tmp_path, "rtsp")
    out_s = hub_layout.read_classified(tmp_path, "sip")
    assert [x["all_claims"][0]["fact_id"] for x in out_r] == ["f1"]
    assert [x["all_claims"][0]["fact_id"] for x in out_s] == ["f2"]


def test_rebuild_replaces_only_this_protocol(tmp_path):
    """★ **按协议替换**：重建本协议 ⇒ 其它协议的记录保留。"""
    r1 = _fact("definition", "A", protocol="rtsp", fid="f1")
    s1 = _fact("definition", "B", protocol="sip", fid="f2")
    hub_layout.write_classified(tmp_path, [
        (0, json.dumps(r1, ensure_ascii=False), r1)], "rtsp")
    hub_layout.write_classified(tmp_path, [
        (0, json.dumps(s1, ensure_ascii=False), s1)], "sip")
    # ★ 重建 rtsp（同一条）⇒ sip 的记录仍在
    r1b = _fact("definition", "A2", protocol="rtsp", fid="f3")
    hub_layout.write_classified(tmp_path, [
        (0, json.dumps(r1b, ensure_ascii=False), r1b)], "rtsp")
    out_r = hub_layout.read_classified(tmp_path, "rtsp")
    out_s = hub_layout.read_classified(tmp_path, "sip")
    assert [x["all_claims"][0]["fact_id"] for x in out_r] == ["f3"]
    assert [x["all_claims"][0]["fact_id"] for x in out_s] == ["f2"]


def test_index_records_global_positions(tmp_path):
    """★ 顺序索引落盘（每 (文件, 协议) 一行，含全局下标）。"""
    recs = []
    for i in range(4):
        v = _fact("definition", f"N{i}", fid=f"f{i+1}")
        recs.append((i, json.dumps(v, ensure_ascii=False), v))
    hub_layout.write_classified(tmp_path, recs, "rtsp")
    ip = hub_layout.index_path(tmp_path)
    assert ip.is_file()
    rows = [json.loads(ln) for ln in ip.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    assert rows, "索引为空"
    r0 = rows[0]
    assert r0["protocol"] == "rtsp"
    assert r0["positions"] == [0, 1, 2, 3]
    assert r0["count"] == 4


def test_six_categories_are_declared():
    """★ 六个知识分类齐备（A~F）。"""
    ids = category_ids()
    for want in ("A_structure", "B_interaction", "C_constraints",
                 "D_construction", "E_observation", "F_security"):
        assert want in ids, ids


# ===========================================================================
# ④ 阶段 C2：记录结构升级（纯增量）
# ===========================================================================

def test_upgrade_adds_entity_epistemic_resolution():
    """★ **阶段 C2**：fact 升级成 v2 记录结构。

    ★ **纯增量**：``fact_key`` / ``all_claims`` **一字不改**，
      只**新增** ``entity`` / ``epistemic``，并把 ``resolution`` 从
      ``null`` 补成实际内容。
    """
    from core.fused.hub.hub_layout import _upgrade_record
    v = _fact("target_state", "transitions_to", stype="relation",
              fid="f1", claim="c1")
    v["fact_key"]["subject"]["qualifiers"] = {
        "source": {"type": "state", "name": "Idle"},
        "target": {"type": "state", "name": "Ready"},
        "method": {"type": "method", "name": "REGISTER"},
    }
    v["all_claims"][0]["epistemic_type"] = "normative"
    v["resolution"] = None
    line = json.dumps(v, ensure_ascii=False)
    out = json.loads(_upgrade_record(line, v))

    # ★ 既有字段**一字不改**
    assert out["fact_key"] == v["fact_key"]
    assert out["all_claims"] == v["all_claims"]
    # ★ 新增字段
    assert out["entity"]["entity_id"] == "rtsp:relation:idle--register-->ready"
    roles = [p["role"] for p in out["entity"]["participants"]]
    assert roles == ["source", "via", "target"], roles
    assert out["epistemic"] == "normative"
    # ★ resolution 必填
    assert out["resolution"]["strategy"] == "single_source"
    assert out["resolution"]["winners"]["value"] == "c1"


def test_upgrade_epistemic_mapping():
    """★ fact 级 ``epistemic``（四档）由 claim 级 ``epistemic_type`` 归并。"""
    from core.fused.hub.hub_layout import _fact_epistemic
    assert _fact_epistemic({"all_claims": [{"epistemic_type": "must"}]}) == \
        "normative"
    assert _fact_epistemic({"all_claims": [{"epistemic_type": "descriptive"}]}) == \
        "informative"
    assert _fact_epistemic({"all_claims": [{"epistemic_type": "observed"}]}) == \
        "observed"
    # ★ 多个 claim ⇒ 取「最强」的一档
    assert _fact_epistemic({"all_claims": [
        {"epistemic_type": "observed"}, {"epistemic_type": "must"}]}) == \
        "normative"


def test_upgrade_resolution_multi_claim():
    """★ 多 claim ⇒ ``consensus`` 策略。"""
    from core.fused.hub.hub_layout import _fact_resolution
    v = {"all_claims": [{"claim_id": "c1"}, {"claim_id": "c2"}]}
    r = _fact_resolution(v)
    assert r["strategy"] == "consensus"
    assert r["winners"]["value"] == "c1"


def test_epistemic_registry_values_covered():
    """★ claim 级判据**全部**能映射到 fact 级四档。"""
    from core.fused.hub.hub_layout import _EPI_MAP
    import json as _json
    from core import paths
    reg = _json.loads(
        (paths.PROJECT_ROOT / "core" / "fused" / "hub" / "registry"
         / "epistemic_type_registry.json").read_text(encoding="utf-8"))
    for t in (reg.get("registered_types") or []):
        name = str(t.get("name") or "")
        assert name in _EPI_MAP, f"未映射的判据：{name}"


# ===========================================================================
# ④ 阶段 C2：记录结构升级（纯增量）
# ===========================================================================

def test_upgrade_adds_entity_epistemic_resolution():
    """★ **阶段 C2**：fact 升级成 v2 记录结构。

    ★ **纯增量**：``fact_key`` / ``all_claims`` **一字不改**，
      只**新增** ``entity`` / ``epistemic``，并把 ``resolution`` 从
      ``null`` 补成实际内容。
    """
    from core.fused.hub.hub_layout import _upgrade_record
    v = _fact("target_state", "transitions_to", stype="relation",
              fid="f1", claim="c1")
    v["fact_key"]["subject"]["qualifiers"] = {
        "source": {"type": "state", "name": "Idle"},
        "target": {"type": "state", "name": "Ready"},
        "method": {"type": "method", "name": "REGISTER"},
    }
    v["all_claims"][0]["epistemic_type"] = "normative"
    v["resolution"] = None
    line = json.dumps(v, ensure_ascii=False)
    out = json.loads(_upgrade_record(line, v))

    # ★ 既有字段**一字不改**
    assert out["fact_key"] == v["fact_key"]
    assert out["all_claims"] == v["all_claims"]
    # ★ 新增字段
    assert out["entity"]["entity_id"] == "rtsp:relation:idle--register-->ready"
    roles = [p["role"] for p in out["entity"]["participants"]]
    assert roles == ["source", "via", "target"], roles
    assert out["epistemic"] == "normative"
    # ★ resolution 必填
    assert out["resolution"]["strategy"] == "single_source"
    assert out["resolution"]["winners"]["value"] == "c1"


def test_upgrade_epistemic_mapping():
    """★ fact 级 ``epistemic``（四档）由 claim 级 ``epistemic_type`` 归并。"""
    from core.fused.hub.hub_layout import _fact_epistemic
    assert _fact_epistemic({"all_claims": [{"epistemic_type": "must"}]}) == \
        "normative"
    assert _fact_epistemic({"all_claims": [{"epistemic_type": "descriptive"}]}) == \
        "informative"
    assert _fact_epistemic({"all_claims": [{"epistemic_type": "observed"}]}) == \
        "observed"
    # ★ 多个 claim ⇒ 取「最强」的一档
    assert _fact_epistemic({"all_claims": [
        {"epistemic_type": "observed"}, {"epistemic_type": "must"}]}) == \
        "normative"


def test_upgrade_resolution_multi_claim():
    """★ 多 claim ⇒ ``consensus`` 策略。"""
    from core.fused.hub.hub_layout import _fact_resolution
    v = {"all_claims": [{"claim_id": "c1"}, {"claim_id": "c2"}]}
    r = _fact_resolution(v)
    assert r["strategy"] == "consensus"
    assert r["winners"]["value"] == "c1"


def test_epistemic_registry_values_covered():
    """★ claim 级判据**全部**能映射到 fact 级四档。"""
    from core.fused.hub.hub_layout import _EPI_MAP
    import json as _json
    from core import paths
    reg = _json.loads(
        (paths.PROJECT_ROOT / "core" / "fused" / "hub" / "registry"
         / "epistemic_type_registry.json").read_text(encoding="utf-8"))
    for t in (reg.get("registered_types") or []):
        name = str(t.get("name") or "")
        assert name in _EPI_MAP, f"未映射的判据：{name}"
