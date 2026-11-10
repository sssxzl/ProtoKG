# -*- coding: utf-8 -*-
"""tests/test_hub_aspect_layout.py —— 批次 1.6 **步 1**（中枢布局改 aspect）。

★ 覆盖六条新行为：
  ① 中枢**按 aspect 统一存放**（``facts/<aspect>.jsonl``）——不再按源分目录；
  ② 「源」退化为**事实内部的字段**（``all_claims[].authority``）；
  ③ 读取端**新布局优先**；
  ④ 读取端**旧布局降级**（不破坏既有产物）；
  ⑤ ★ **新旧两种布局产出的 bundle 逐字节一致**（默认路径不变）；
  ⑥ 清空中枢时**新布局一并清空**（不残留上一批次的知识）。

★ 为什么 ⑤ 是硬要求：方案 §3.1.10.6 的「四条保证」第 1 条要求
  「步 1~5 全是加参数/加字段 ⇒ **默认路径逐字节不变**」⇒ 本用例是那条
  保证的**机器可判定形式**。
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

build_hub = importlib.import_module("scripts.build_hub")
paths_mod = importlib.import_module("core.paths")
rag_seedgen = importlib.import_module("core.fused.downstream.rag_seedgen")

PROTOCOL = "rtsp"


# ===========================================================================
# 夹具
# ===========================================================================

def _fact_view(authority: str, aspect: str, subject_type: str = "method",
               subject_name: str = "SETUP", value=None, fid: str = "f1",
               claim_id: str = "c1") -> dict:
    """构造一条最小 fact view（结构与 ``get_fact_view`` 产出兼容）。"""
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
        "all_claims": [{
            "claim_id": claim_id,
            "fact_id": fid,
            "value": {"type": "bool" if value is None else "struct",
                      "data": True if value is None else value},
            "epistemic_type": "normative",
            "authority": authority,
            "scope": None,
            "evidence_summary": [f"{authority}:{subject_name}"],
            "confidence": None,
        }],
    }


def _write_facts(path: Path, views: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in views),
        encoding="utf-8")


def _norm(obj):
    """稳定化（set → sorted list；tuple key → 字符串 key）。"""
    if isinstance(obj, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): _norm(v)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_norm(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_norm(v) for v in obj)
    return obj


def _dump(obj) -> str:
    return json.dumps(_norm(obj), ensure_ascii=False, sort_keys=True,
                      default=str)


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    """把中枢根指向 tmp_path（**不污染仓库的 derived/**）。"""
    root = tmp_path / "per_source" / PROTOCOL
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod, "per_source_root",
                        lambda p: tmp_path / "per_source" / p.lower())
    monkeypatch.setattr(paths_mod, "hub_root",
                        lambda *a: tmp_path / "per_source" / PROTOCOL)
    return root


# ===========================================================================
# ① 中枢按 aspect 统一存放
# ===========================================================================

def test_class_layout_writes_one_file_per_category(hub):
    """★ **阶段 C**：中枢按**知识分类**存放（一个分类一个文件）。"""
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", fid="f1", claim_id="c1"),
        _fact_view("rfc", "syntax", subject_type="header",
                   subject_name="CSeq", fid="f2", claim_id="c2"),
    ])
    _write_facts(hub / "profile" / "facts" / "profile.jsonl", [
        _fact_view("profile", "definition", subject_name="PLAY",
                   fid="f3", claim_id="c3"),
    ])

    counts = build_hub._write_aspect_layout(PROTOCOL)

    # ★ definition@method/header ⇒ A_structure；syntax@header ⇒ A_structure
    assert set(counts) == {"A_structure"}, counts
    assert counts["A_structure"] == 3
    f = paths_mod.hub_root() / "A_structure" / "structure.jsonl"
    assert f.is_file(), f
    # ★ 不再按源分目录：分类文件里**没有**源目录层
    assert not (f.parent / "rfc").exists()
    assert not (f.parent / "profile").exists()
    # 条数守恒
    total = sum(1 for ln in f.read_text(encoding="utf-8").splitlines()
                if ln.strip())
    assert total == 3
def test_class_layout_keeps_source_as_fact_field(hub):
    """★ 「源」退化为事实内部的字段（``all_claims[].authority``）。"""
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", fid="f1", claim_id="c1"),
    ])
    _write_facts(hub / "traffic" / "facts" / "traffic.jsonl", [
        _fact_view("traffic", "value_enum", subject_type="header",
                   subject_name="CSeq", fid="f2", claim_id="c2"),
    ])
    build_hub._write_aspect_layout(PROTOCOL)

    from core.fused.hub.knowledge_slots import category_ids
    authorities = []
    for cat in category_ids():
        cd = paths_mod.hub_root() / cat
        if not cd.is_dir():
            continue
        for jf in cd.glob("*.jsonl"):
            for line in jf.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    authorities.append(
                        json.loads(line)["all_claims"][0]["authority"])
    assert sorted(authorities) == ["rfc", "traffic"]
# ===========================================================================
# ③ 读取端：新布局优先 / ④ 旧布局降级
# ===========================================================================

def test_load_fact_views_prefers_aspect_layout(hub):
    """★ 新布局存在 ⇒ 读新布局（**不**再读旧的按源目录）。"""
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", fid="f1", claim_id="c1"),
    ])
    build_hub._write_aspect_layout(PROTOCOL)
    # 旧布局里塞一条**不该**被读到的残留
    _write_facts(hub / "vuln" / "facts" / "vuln.jsonl", [
        _fact_view("vuln", "security_property", fid="f2", claim_id="c2"),
    ])

    views = rag_seedgen.load_fact_views(PROTOCOL)
    authorities = {c["authority"] for v in views for c in v["all_claims"]}
    assert authorities == {"rfc"}


def test_load_fact_views_falls_back_to_legacy_layout(hub):
    """★ 新布局缺失 ⇒ 自动降级读旧布局（不破坏既有产物）。"""
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", fid="f1", claim_id="c1"),
    ])
    _write_facts(hub / "traffic" / "facts" / "traffic.jsonl", [
        _fact_view("traffic", "value_enum", subject_type="header",
                   subject_name="CSeq", fid="f2", claim_id="c2"),
    ])
    assert not paths_mod.per_source_aspect_facts_dir(PROTOCOL).exists()

    views = rag_seedgen.load_fact_views(PROTOCOL)
    authorities = {c["authority"] for v in views for c in v["all_claims"]}
    assert authorities == {"rfc", "traffic"}


def test_load_fact_views_does_not_double_read_both_layouts(hub):
    """★ 新旧布局同时存在 ⇒ **不重复读**（同一 fact 只出现一次）。"""
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", fid="f1", claim_id="c1"),
    ])
    build_hub._write_aspect_layout(PROTOCOL)

    views = rag_seedgen.load_fact_views(PROTOCOL)
    assert len(views) == 1


# ===========================================================================
# ⑤ ★ 新旧布局产出逐字节一致（默认路径不变）
# ===========================================================================

def test_legacy_and_aspect_layout_produce_identical_bundle(hub):
    """★ **bundle 逐字节一致** ⇒ 下游（种子生成）必然逐字节不变。"""
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _fact_view("rfc", "syntax", subject_type="header",
                   subject_name="CSeq", fid="f2", claim_id="c2"),
    ])
    _write_facts(hub / "profile" / "facts" / "profile.jsonl", [
        _fact_view("profile", "definition", subject_name="PLAY",
                   fid="f3", claim_id="c3"),
    ])
    _write_facts(hub / "traffic" / "facts" / "traffic.jsonl", [
        _fact_view("traffic", "value_enum", subject_type="header",
                   subject_name="CSeq", value=["1", "2"],
                   fid="f4", claim_id="c4"),
    ])

    # 旧布局读法（逐字节复刻改动前的实现）
    legacy_views = []
    for jsonl in sorted(hub.glob("*/facts/*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                legacy_views.append(json.loads(line))

    build_hub._write_aspect_layout(PROTOCOL)
    new_views = rag_seedgen.load_fact_views(PROTOCOL)

    legacy_bundle = rag_seedgen.assemble_bundle(list(legacy_views), PROTOCOL)
    new_bundle = rag_seedgen.assemble_bundle(list(new_views), PROTOCOL)
    # ★ 阶段 C2/D1 给 fact / bundle **新增**了字段（纯增量）
    #   ⇒ 比对前剥离（被比对的仍是**旧契约**的全部内容）。
    from tests.extraction._compat import strip_bundle
    assert _dump(strip_bundle(new_bundle)) == _dump(strip_bundle(legacy_bundle))


# ===========================================================================
# ⑤-b ★ **顺序索引**：还原旧全局遍历序（否则键序漂移 ⇒ 种子编号漂移）
# ===========================================================================

def test_load_fact_views_restores_legacy_global_order(hub):
    """★ 新布局读出的视图序 == 旧布局的**全局遍历序**。

    ★ 这是「默认路径逐字节不变」的**前提**：``assemble_bundle`` 的
      ``methods``/``headers`` 是 dict ⇒ 键的**插入序**取决于 fact 遍历序
      ⇒ 键序一变 ⇒ 下游种子顺序变 ⇒ 种子文件名（编号 + 资源后缀）全变。
    """
    # 交错布局：rfc 源里 definition / syntax 交替出现（实测真实数据即如此）
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", subject_name="A", fid="f1", claim_id="c1"),
        _fact_view("rfc", "syntax", subject_type="header",
                   subject_name="H1", fid="f2", claim_id="c2"),
        _fact_view("rfc", "definition", subject_name="B", fid="f3", claim_id="c3"),
        _fact_view("rfc", "syntax", subject_type="header",
                   subject_name="H2", fid="f4", claim_id="c4"),
    ])
    _write_facts(hub / "traffic" / "facts" / "traffic.jsonl", [
        _fact_view("traffic", "definition", subject_name="C", fid="f5", claim_id="c5"),
    ])

    legacy_views = []
    for jsonl in sorted(hub.glob("*/facts/*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                legacy_views.append(json.loads(line))

    build_hub._write_aspect_layout(PROTOCOL)
    new_views = rag_seedgen.load_fact_views(PROTOCOL)

    assert [v["all_claims"][0]["fact_id"] for v in new_views] == \
           [v["all_claims"][0]["fact_id"] for v in legacy_views]


def test_bundle_key_insertion_order_identical(hub):
    """★ bundle 的 **dict 键插入序**必须一致（内容一致但键序不同 ⇒ 种子漂移）。

    ★ 回归教训：用 ``sort_keys=True`` 比较 JSON 会**掩盖**键序差异 ⇒
      必须单独断言键序。
    """
    _write_facts(hub / "rfc" / "facts" / "rfc.jsonl", [
        _fact_view("rfc", "definition", subject_name="SETUP",
                   fid="f1", claim_id="c1"),
        _fact_view("rfc", "syntax", subject_type="header",
                   subject_name="CSeq", fid="f2", claim_id="c2"),
        _fact_view("rfc", "definition", subject_name="PLAY",
                   fid="f3", claim_id="c3"),
    ])
    legacy_views = []
    for jsonl in sorted(hub.glob("*/facts/*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                legacy_views.append(json.loads(line))

    build_hub._write_aspect_layout(PROTOCOL)
    new_views = rag_seedgen.load_fact_views(PROTOCOL)

    legacy_bundle = rag_seedgen.assemble_bundle(list(legacy_views), PROTOCOL)
    new_bundle = rag_seedgen.assemble_bundle(list(new_views), PROTOCOL)
    # ★ 阶段 D1：视图层新增 ``by_category`` / ``entities``（**追加在末尾**
    #   ⇒ 不影响旧键的插入序）⇒ 本断言只关心**旧契约**。
    for _k in ("by_category", "entities", "entity_by_name"):
        legacy_bundle.pop(_k, None)
        new_bundle.pop(_k, None)
    for key in legacy_bundle:
        if isinstance(legacy_bundle[key], dict):
            assert list(legacy_bundle[key].keys()) == list(new_bundle[key].keys()), \
                f"桶 `{key}` 的键插入序不一致"


# ===========================================================================
# ⑥ 清空中枢 ⇒ 新布局一并清空
# ===========================================================================

def test_purge_clears_aspect_layout(hub, monkeypatch):
    """★ 清空中枢时**新布局一并清空**（不残留上一批次的知识）。"""
    aspect_dir = paths_mod.per_source_aspect_facts_dir(PROTOCOL)
    aspect_dir.mkdir(parents=True, exist_ok=True)
    (aspect_dir / "definition.jsonl").write_text("{}\n", encoding="utf-8")
    (aspect_dir / "value_enum.jsonl").write_text("{}\n", encoding="utf-8")

    build_hub._purge_hub_for_batch(PROTOCOL, purge_semantic=True)

    assert not (aspect_dir / "definition.jsonl").exists()
    assert not (aspect_dir / "value_enum.jsonl").exists()


# ===========================================================================
# ⑦ sources.json 记录中枢布局
# ===========================================================================

def test_source_manifest_records_hub_layout(hub):
    """★ ``sources.json`` 记录 aspect 分布（中枢布局可审计）。"""
    path = build_hub._write_source_manifest(
        PROTOCOL, ["rfc"], {"rfc": "rb_x"},
        required_headers_count=9,
        aspect_counts={"definition": 71, "syntax": 45})
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["hub_layout"]["scheme"] == "aspect-v1"
    assert doc["hub_layout"]["aspect_counts"] == {"definition": 71,
                                                  "syntax": 45}


# ===========================================================================
# 批次 2.3：骨架来源维度消融开关（--exclude-skeleton-dims）
# ===========================================================================
