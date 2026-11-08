# -*- coding: utf-8 -*-
"""tests/fused/test_consumer_wiring.py —— 批次 1.6 **步 5**（消费端接线）。

★ 覆盖六条：
  ① 消费端能读中枢的 ``sources.json``（本次源集合 = 唯一权威）；
  ② 清单缺失 ⇒ 返回空（兼容期：不过滤，保持旧行为）；
  ③ 缺省用**中枢声明**的源集合；
  ④ ``--sources`` 显式传参 ⇒ **覆盖**中枢声明（双保险）；
  ⑤ ★ 消费端**不碰 kb/**（源与消费端互不接触，D-6）；
  ⑥ 消费端**只读中枢**：知识入口只有 ``sources.json`` + ``facts/*.jsonl``。
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

seedgen = importlib.import_module("scripts.seedgen")
paths_mod = importlib.import_module("core.paths")
rag_seedgen = importlib.import_module("core.fused.downstream.rag_seedgen")

PROTOCOL = "rtsp"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    root = tmp_path / "per_source" / PROTOCOL
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod, "per_source_root",
                        lambda p: tmp_path / "per_source" / p.lower())
    monkeypatch.setattr(paths_mod, "hub_root",
                        lambda *a: tmp_path / "per_source" / PROTOCOL)
    return root


def _write_manifest(root: Path, source_set: list[str]) -> None:
    (root / "sources.json").write_text(json.dumps({
        "protocol": PROTOCOL,
        "source_set": source_set,
        "build_ids": {s: f"rb_{s}" for s in source_set},
        "built_at": "2026-11-02T00:00:00+08:00",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


# ===========================================================================
# ① 读中枢清单
# ===========================================================================

def test_load_source_manifest_reads_manifest(hub):
    """★ 消费端能读中枢的 sources.json。"""
    _write_manifest(hub, ["rfc", "vuln"])
    doc = rag_seedgen.load_source_manifest(PROTOCOL)
    assert doc["source_set"] == ["rfc", "vuln"]
    assert doc["build_ids"] == {"rfc": "rb_rfc", "vuln": "rb_vuln"}


def test_load_source_manifest_missing_returns_empty(hub):
    """★ 清单缺失 ⇒ 返回空（兼容期：不过滤）。"""
    assert rag_seedgen.load_source_manifest(PROTOCOL) == {}


def test_load_source_manifest_invalid_json_returns_empty(hub):
    """★ 清单损坏 ⇒ 返回空（不崩）。"""
    (hub / "sources.json").write_text("{not json", encoding="utf-8")
    assert rag_seedgen.load_source_manifest(PROTOCOL) == {}


# ===========================================================================
# ③④ 源集合解析（缺省 = 中枢声明；--sources = 显式覆盖）
# ===========================================================================

def test_resolve_source_set_defaults_to_manifest(hub):
    """★ 缺省 ⇒ 用中枢声明的源集合。"""
    _write_manifest(hub, ["rfc"])
    picked, origin = seedgen.resolve_source_set(PROTOCOL, None)
    assert picked == ["rfc"]
    assert "sources.json" in origin


def test_resolve_source_set_cli_overrides_manifest(hub):
    """★ `--sources` ⇒ **覆盖**中枢声明（调用方显式授权 = 双保险）。"""
    _write_manifest(hub, ["rfc", "vuln"])
    picked, origin = seedgen.resolve_source_set(PROTOCOL, ["rfc"])
    assert picked == ["rfc"]
    assert "--sources" in origin


def test_resolve_source_set_empty_when_no_manifest(hub):
    """★ 中枢没声明 ⇒ 空列表 ⇒ 调用方按「不过滤」处理。"""
    picked, origin = seedgen.resolve_source_set(PROTOCOL, None)
    assert picked == []
    assert "sources.json" in origin


# ===========================================================================
# ⑤ 消费端不碰 kb/（源与消费端互不接触）
# ===========================================================================

def test_consumer_never_reads_kb_directory():
    """★ 消费端**不读 kb/** —— 知识源只经中枢进入消费端（D-6）。

    判据：``scripts/seedgen.py`` 与 ``core/fused/downstream/rag_seedgen.py``
    的源码里**不得**出现 kb 路径引用（``kb_root`` / ``kb_source_dir`` /
    ``"kb/"``）。
    """
    for rel in ("scripts/seedgen.py",
                "core/fused/downstream/rag_seedgen.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in ("kb_root", "kb_source_dir", "kb/" + chr(34), "kb/" + chr(39)):
            assert needle not in text, f"{rel} 出现了知识源直读：{needle}"


# ===========================================================================
# ⑥ 消费端只读中枢
# ===========================================================================

def test_consumer_reads_only_hub_entries(hub):
    """★ 中枢的知识入口只有两处：``sources.json`` + ``facts/*.jsonl``。"""
    _write_manifest(hub, ["rfc"])
    (hub / "facts").mkdir(parents=True, exist_ok=True)
    (hub / "facts" / "definition.jsonl").write_text("{}\n", encoding="utf-8")
    # 消费端能同时读到清单与事实
    assert rag_seedgen.load_source_manifest(PROTOCOL)["source_set"] == ["rfc"]
    # 新布局里只有一个空事实
    assert rag_seedgen.load_fact_views(PROTOCOL) == [{}]
    # 消费端**不**去读别的目录（per-source 的旧布局存在时也不额外读路径）
    (hub / "rfc" / "facts").mkdir(parents=True, exist_ok=True)
    (hub / "rfc" / "facts" / "rfc.jsonl").write_text(
        json.dumps({
            "fact_key": {"protocol": PROTOCOL, "version": "1.0",
                         "subject": {"type": "method", "name": "SETUP",
                                     "qualifiers": {}, "path": []},
                         "aspect": "definition",
                         "condition": {"type": "always"}},
            "resolution": None,
            "all_claims": [{"claim_id": "c", "fact_id": "f",
                            "value": {"type": "bool", "data": True},
                            "epistemic_type": "normative",
                            "authority": "rfc", "scope": None,
                            "evidence_summary": ["rfc:SETUP"],
                            "confidence": None}],
        }, ensure_ascii=False) + "\n", encoding="utf-8")
    views = rag_seedgen.load_fact_views(PROTOCOL)
    # ★ 新布局存在 ⇒ 只读新布局（旧布局里的这条**不**被读到）
    assert views == [{}]
