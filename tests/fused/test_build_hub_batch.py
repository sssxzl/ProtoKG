# -*- coding: utf-8 -*-
"""tests/fused/test_build_hub_batch.py —— 批次 1.6 步 0/0.5 的回归用例。

★ 覆盖四条新行为：
  ① 批次级「**清空整个中枢**」（只清五源抽取产物；**保留**运行时富化目录）
  ② 「**协议骨架**」物化进中枢（⇒ 单源调试时状态机不为 0 ⇒ 链路不断）
  ③ ``sources.json``（本次源集合 = 唯一权威）
  ④ 护栏6 的「窄化数据态」**条件性**豁免（窄化时生效、全源时**不生效**）
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

build_hub = importlib.import_module("scripts.build_hub")
paths_mod = importlib.import_module("core.paths")
ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# ① 批次级清空
# ===========================================================================

def test_purge_clears_all_five_sources_but_keeps_runtime_enrich(tmp_path,
                                                              monkeypatch):
    """★ 清空整个中枢：五源 facts 全清，**保留** boundary_probe 等运行时富化。"""
    root = tmp_path / "per_source" / "rtsp"
    for source in ("rfc", "traffic", "vuln", "source", "expert_note"):
        d = root / source / "facts"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{source}.jsonl").write_text("{}\n", encoding="utf-8")
    # 运行时富化：oracle 探测回写的富化知识 ⇒ **必须保留**
    bp = root / "boundary_probe" / "facts"
    bp.mkdir(parents=True, exist_ok=True)
    (bp / "boundary_probe.jsonl").write_text('{"x":1}\n', encoding="utf-8")
    # 语义四库 ⇒ 清空（D-7 选项 A）
    sem = root / "rfc" / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    (sem / "rules.jsonl").write_text("{}\n", encoding="utf-8")
    # 快照 ⇒ 保留
    snap = root / "rfc" / "facts" / "snapshots" / "b1"
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "rfc.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(paths_mod, "per_source_root",
                        lambda p: tmp_path / "per_source" / p.lower())
    monkeypatch.setattr(build_hub, "SEMANTIC_BACKUP_ROOT", tmp_path / "bak")

    purged = build_hub._purge_hub_for_batch("rtsp", purge_semantic=True)

    assert set(purged) >= {"rfc", "traffic", "vuln", "source", "expert_note"}
    # 五源的 facts 清空（**有快照的那个源**的快照保留）
    for source in ("rfc", "traffic", "vuln", "source", "expert_note"):
        d = root / source / "facts"
        assert not (d / f"{source}.jsonl").exists(), f"{source} 未清空"
    assert (root / "rfc" / "facts" / "snapshots").is_dir(), "历史快照被误删"
    # 运行时富化保留
    assert (bp / "boundary_probe.jsonl").is_file(), "运行时富化被误清"
    # 语义四库清空
    assert not (sem / "rules.jsonl").exists(), "语义四库未清空（D-7 选项 A）"
    # 备份落在仓库外
    assert (tmp_path / "bak" / "rtsp").is_dir()


def test_purge_keeps_semantic_when_disabled(tmp_path, monkeypatch):
    """``purge_semantic=False`` ⇒ 语义四库保留（--no-purge 语义）。"""
    root = tmp_path / "per_source" / "rtsp"
    sem = root / "rfc" / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    (sem / "rules.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(paths_mod, "per_source_root",
                        lambda p: tmp_path / "per_source" / p.lower())
    monkeypatch.setattr(build_hub, "SEMANTIC_BACKUP_ROOT", tmp_path / "bak")
    build_hub._purge_hub_for_batch("rtsp", purge_semantic=False)
    assert (sem / "rules.jsonl").is_file(), "purge_semantic=False 时不该清规则库"


# ===========================================================================
# ② 骨架物化
# ===========================================================================

def test_materialize_skeleton_writes_profile_facts(tmp_path, monkeypatch):
    """★ 骨架物化：写进中枢的 ``profile/`` 源，authority 改标 profile。"""
    skel = tmp_path / "fused_hub" / "targets" / "rtsp" / "skeleton.json"
    skel.parent.mkdir(parents=True, exist_ok=True)
    skel.write_text(json.dumps({
        "protocol": "rtsp",
        "facts": [{
            "fact_key": {"protocol": "rtsp", "version": "1.0",
                         "subject": {"type": "method", "name": "SETUP"},
                         "aspect": "target_state", "condition": {"type": "always"}},
            "all_claims": [{"claim_id": "c1", "fact_id": "f1",
                            "authority": "source", "value": {}}],
            "resolution": {},
        }],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(build_hub, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(paths_mod, "per_source_facts_dir",
                        lambda p, s: tmp_path / "derived" / "per_source" / p / s
                        / "facts")

    n = build_hub._materialize_skeleton("rtsp")
    assert n == 1
    dest = tmp_path / "derived" / "per_source" / "rtsp" / "profile" / "facts" \
        / "profile.jsonl"
    assert dest.is_file()
    fact = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
    assert fact["all_claims"][0]["authority"] == "profile", \
        "骨架的 authority 必须改标 profile（与本次抽取的源分得开）"


def test_missing_skeleton_is_reported_not_silent(tmp_path, monkeypatch, capsys):
    """★ 骨架缺失必须**显式提示**（否则单源构建会因无状态机而悄悄失败）。"""
    monkeypatch.setattr(build_hub, "REPO_ROOT", tmp_path)
    assert build_hub._materialize_skeleton("rtsp") == 0
    assert "skeleton.json" in capsys.readouterr().out


# ===========================================================================
# ③ sources.json = 本次源集合的唯一权威
# ===========================================================================

def test_source_manifest_records_source_set_and_skeleton(tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "per_source_root",
                        lambda p: tmp_path / "per_source" / p.lower())
    path = build_hub._write_source_manifest(
        "rtsp", ["rfc"], {"rfc": "rb_1"}, skeleton_count=145)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["source_set"] == ["rfc"]
    assert doc["build_ids"] == {"rfc": "rb_1"}
    assert doc["skeleton"]["fact_count"] == 145
    assert doc["skeleton"]["source"] == "profile"


# ===========================================================================
# ④ 护栏6：窄化数据态的**条件性**豁免
# ===========================================================================

def test_narrow_hub_state_detects_narrowed_hub(tmp_path, monkeypatch):
    """★ 中枢 source_set 非五源 ⇒ 判为窄化态。"""
    import tools.qa.run_guarded_pytest as guard
    root = tmp_path / "derived" / "per_source"
    (root / "rtsp").mkdir(parents=True)
    (root / "rtsp" / "sources.json").write_text(
        json.dumps({"source_set": ["rfc"]}), encoding="utf-8")
    state = guard._detect_narrow_hub_state(root)
    assert state["narrowed"] is True
    assert state["source_sets"] == {"rtsp": ["rfc"]}


def test_narrow_hub_state_full_hub_is_not_narrowed(tmp_path, monkeypatch):
    """★ 五源齐备 ⇒ **不**判为窄化 ⇒ 窄化豁免**不生效**（常态护栏不被削弱）。"""
    import tools.qa.run_guarded_pytest as guard
    root = tmp_path / "derived" / "per_source"
    (root / "rtsp").mkdir(parents=True)
    (root / "rtsp" / "sources.json").write_text(
        json.dumps({"source_set": ["rfc", "expert_note", "traffic", "vuln",
                                  "source"]}), encoding="utf-8")
    state = guard._detect_narrow_hub_state(root)
    assert state["narrowed"] is False
