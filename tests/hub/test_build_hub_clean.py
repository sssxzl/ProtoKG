"""tests/test_build_hub_clean.py —— build_hub._clean_per_source 只清五源、保留运行时回写。
# ★ 中枢**共用一套** ⇒ 隔离中枢根（不污染仓库 derived/）
monkeypatch.setattr(paths, "hub_root",
                    lambda *a: tmp_path / "hub")

背景：边界探针（run_boundary_probe.py）会把 oracle 验证的 legal_boundary fact 回写到
per_source/<protocol>/boundary_probe/facts/。build_hub 重抽取时若 rmtree 整个
per_source/<protocol>/ 会误清这份运行时富化知识。修复后 _clean_per_source 只删五源子目录。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_hub  # noqa: E402
from core import paths  # noqa: E402


def test_clean_per_source_only_removes_five_sources(tmp_path, monkeypatch):
    proto_root = tmp_path / "rtsp"
    # 五源 facts
    for src in paths.SOURCES:
        (proto_root / src / "facts").mkdir(parents=True)
        (proto_root / src / "facts" / f"{src}.jsonl").write_text("{}\n", encoding="utf-8")
    # 运行时回写（非五源）
    bf_facts = proto_root / "boundary_probe" / "facts"
    bf_facts.mkdir(parents=True)
    (bf_facts / "boundary_probe.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(paths, "per_source_root", lambda p: tmp_path / p.lower())
    build_hub._clean_per_source("rtsp")

    # 五源全清空
    for src in paths.SOURCES:
        assert not (proto_root / src).exists(), f"五源 {src} 应被清空"
    # 运行时回写保留
    assert (bf_facts / "boundary_probe.jsonl").exists(), \
        "boundary_probe 回写（非五源）应被保留"


def test_clean_per_source_missing_root_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "per_source_root", lambda p: tmp_path / p.lower())
    # 目录不存在 → 不抛异常
    build_hub._clean_per_source("rtsp")
    assert not (tmp_path / "rtsp").exists()
