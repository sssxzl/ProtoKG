# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_build_corpus_continue.py —— `--continue-on-error` 的控制流契约。

背景（QA 复扫实测）
------------------
`scripts/rq3_build_corpus.py` 原本「首组生成失败即 `return 4` 中止」⇒
**B/C/D 组永远不会被重新生成**，磁盘上留着旧污染产物
（QA 实测：`derived/rq3/A/seeds` 的 mtime 最新，而 B/C/D 仍是 10-31 03:24 的旧产物）。

本文件把修复后的不变式固化成可执行断言：

  · **默认路径**（不加开关）：某组失败 ⇒ **立即中止**（退出码 4），
    其余组**不重建**（历史行为逐字节保持：既有调用方与既有测试不受影响）。
  · **`--continue-on-error`**：某组失败 ⇒ 记录并**继续**构建其余组；
    全部组跑完后若有失败组 ⇒ 退出码非 0 + **列出失败组清单**，
    且**不发布** groups.json（语料不完整，禁止用于实验）。

另有护栏：构建前后比对各组 `seeds` 目录的 mtime 快照 ⇒ 快照变了即说明本次
构建改动了产物目录（提示后续流程「语料已被重建」）。

★ 全程走 **tmp 目录 + mock 的 `_run_seedgen`**：**绝不触碰 `derived/rq3/`**
  （硬约束：不得改动 `derived/rq3/` 下的任何产物）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "local") not in sys.path:
    sys.path.insert(0, str(ROOT / "local"))

import rq3_common as C  # noqa: E402

from scripts import rq3_build_corpus as B  # noqa: E402

#: 四个聚焦组（与被测脚本一致）
GROUPS = ("A", "B", "C", "D")

#: 「语料已被重建」护栏信号的关键字
SIGNAL = "语料已被重建"


# ===========================================================================
# 夹具与桩
# ===========================================================================

@pytest.fixture()
def rq3_root(tmp_path, monkeypatch):
    """把 rq3 产物根重定向到 tmp 目录（**绝不触碰 derived/rq3/**）。"""
    root = tmp_path / "rq3"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(C, "RQ3_ROOT", root)
    return root


def _fake_seedgen(failing, calls):
    """构造 mock 的 `_run_seedgen`：失败组返回 1，其余组写出 1 条种子 + manifest。

    Args:
        failing: 生成失败的组名集合。
        calls: 记录被调用的组名与顺序（调用后即可断言「哪些组被构建过」）。

    Returns:
        可直接 monkeypatch 到 `B._run_seedgen` 的函数。
    """

    def _run(group: str, out_dir: Path, manifest: bool = True) -> int:
        calls.append(group)
        if group in failing:
            return 1
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"{group}_seed_01.raw"
        payload = f"SEED {group}\n".encode("utf-8")
        (out_dir / name).write_bytes(payload)
        if manifest:
            (out_dir / "manifest.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "group": group,
                    "seed_count": 1,
                    "seeds": [{
                        "index": 1, "rank": 1, "filename": name,
                        "md5": hashlib.md5(payload).hexdigest(),
                        "bytes": len(payload),
                    }],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8")
        return 0

    return _run


def _stub_dict_and_assertions(tmp_path, monkeypatch):
    """把字典生成 / 字典冻结 / 一致性断言替换为轻量桩。

    目的：成功路径只测**控制流**，不触碰真实字典与真实语料断言。

    Returns:
        桩字典文件映射 `{种类: 路径}`。
    """
    d = tmp_path / "stubs"
    d.mkdir(parents=True, exist_ok=True)
    base = d / "rtsp_base.dict"
    tgt = d / "c_targeted.dict"
    base.write_text("a\nb\nc\n", encoding="utf-8")
    tgt.write_text("a\nb\nc\nd\n", encoding="utf-8")
    monkeypatch.setattr(B, "_generate_dicts",
                        lambda cfg: {"base": base, "targeted": tgt})
    monkeypatch.setattr(B, "_freeze_dicts",
                        lambda cfg, dict_files: {"dictionaries": []})
    monkeypatch.setattr(B, "_assert_corpus",
                        lambda cfg, groups, dict_files: B.Assertions())
    return {"base": base, "targeted": tgt}


def _seed_files(root: Path, group: str) -> list:
    """某组语料目录下的 `.raw` 文件列表。"""
    return sorted((root / group / "seeds").glob("*.raw"))


def _write_manifests(root: Path, groups=GROUPS) -> None:
    """在 tmp 产物根里预置最小 manifest（模拟「上一次构建已发布」的产物）。

    `--check-only` 不生成任何东西，但后续 groups.json 阶段要读 manifest ⇒
    测试必须先摆好「上一轮产物」。
    """
    for g in groups:
        d = root / g
        d.mkdir(parents=True, exist_ok=True)
        name = f"{g}_seed_01.raw"
        payload = f"SEED {g}\n".encode("utf-8")
        (d / "manifest.json").write_text(
            json.dumps({
                "schema_version": "1.0",
                "group": g,
                "seed_count": 1,
                "seeds": [{
                    "index": 1, "rank": 1, "filename": name,
                    "md5": hashlib.md5(payload).hexdigest(),
                    "bytes": len(payload),
                }],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8")


# ===========================================================================
# 默认路径（不加开关）：首组失败即中止
# ===========================================================================

def test_default_path_returns_4_on_first_failure(rq3_root, monkeypatch):
    """默认路径：A 组失败 ⇒ 退出码 4（历史行为不变）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    assert B.build() == 4


def test_default_path_stops_at_first_failure(rq3_root, monkeypatch):
    """默认路径：A 组失败 ⇒ 立即中止，B/C/D **从未被调用**。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build()
    assert calls == ["A"], f"B/C/D 不该被构建，实际调用序列: {calls}"


def test_default_path_leaves_remaining_groups_unbuilt(rq3_root, monkeypatch):
    """默认路径：B/C/D 的语料目录保持为空（未被重建）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build()
    for g in ("B", "C", "D"):
        assert _seed_files(rq3_root, g) == [], f"{g} 组不该被重建"


def test_default_path_does_not_publish_groups_json(rq3_root, monkeypatch):
    """默认路径：中止时**不发布** groups.json。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build()
    assert not (rq3_root / "groups.json").exists()


def test_default_path_stdout_has_no_rebuild_signal(rq3_root, monkeypatch,
                                                   capsys):
    """默认路径：护栏信号只走 stderr ⇒ stdout 逐字节不变（可做黄金比对）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build()
    captured = capsys.readouterr()
    assert SIGNAL not in captured.out
    assert SIGNAL not in captured.err  # A 组失败 ⇒ 未改动产物 ⇒ 无重建信号


# ===========================================================================
# --continue-on-error：失败不中止，其余组照常构建
# ===========================================================================

def test_continue_on_error_builds_remaining_groups(rq3_root, monkeypatch):
    """★ 核心验收：A 组失败时，B/C/D **仍被构建**。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build(continue_on_error=True)
    assert calls == ["A", "B", "C", "D"], f"实际调用序列: {calls}"


def test_continue_on_error_writes_remaining_group_seeds(rq3_root, monkeypatch):
    """★ 核心验收：A 组失败时，B/C/D 的种子文件**真的落盘**了。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build(continue_on_error=True)
    for g in ("B", "C", "D"):
        files = _seed_files(rq3_root, g)
        assert len(files) == 1, f"{g} 组语料未落盘: {files}"


def test_continue_on_error_returns_nonzero(rq3_root, monkeypatch):
    """★ 核心验收：存在失败组 ⇒ 最终退出码非 0。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    rc = B.build(continue_on_error=True)
    assert rc != 0
    assert rc == 6


def test_continue_on_error_lists_failed_groups(rq3_root, monkeypatch, capsys):
    """★ 核心验收：失败组清单被打印出来（stderr）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build(continue_on_error=True)
    err = capsys.readouterr().err
    assert "生成失败" in err
    assert "A" in err
    assert "1 组生成失败" in err


def test_continue_on_error_lists_every_failed_group(rq3_root, monkeypatch,
                                                    capsys):
    """多个组失败 ⇒ 失败组清单**一个不漏**。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A", "C"}, calls))
    rc = B.build(continue_on_error=True)
    err = capsys.readouterr().err
    assert rc == 6
    assert "2 组生成失败" in err
    assert "A, C" in err


def test_continue_on_error_does_not_publish_groups_json(rq3_root, monkeypatch):
    """语料不完整 ⇒ **不发布** groups.json（禁止用于实验）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    B.build(continue_on_error=True)
    assert not (rq3_root / "groups.json").exists()


def test_continue_on_error_success_path_publishes(rq3_root, tmp_path,
                                                 monkeypatch):
    """开关打开但**全部组成功** ⇒ 走完整流程，退出码 0 且发布 groups.json。"""
    _stub_dict_and_assertions(tmp_path, monkeypatch)
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen(set(), calls))
    rc = B.build(continue_on_error=True)
    assert rc == 0
    assert calls == list(GROUPS)
    assert (rq3_root / "groups.json").is_file()


# ===========================================================================
# CLI 接线
# ===========================================================================

def test_cli_flag_is_wired(rq3_root, monkeypatch):
    """`--continue-on-error` 必须真的接到 build() 上（CLI 冒烟）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    monkeypatch.setattr(sys, "argv",
                        ["rq3_build_corpus.py", "--continue-on-error"])
    rc = B.main()
    assert rc != 0
    assert calls == ["A", "B", "C", "D"]


def test_cli_without_flag_keeps_legacy_behaviour(rq3_root, monkeypatch):
    """不加开关 ⇒ CLI 走历史路径（A 组失败即中止，返回 4）。"""
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen({"A"}, calls))
    monkeypatch.setattr(sys, "argv", ["rq3_build_corpus.py"])
    assert B.main() == 4
    assert calls == ["A"]


# ===========================================================================
# 护栏：构建前后的 mtime 快照比对
# ===========================================================================

def test_rebuild_signal_emitted_when_corpus_changed(rq3_root, tmp_path,
                                                    monkeypatch, capsys):
    """构建改动了产物目录 ⇒ 打印「语料已被重建」信号（stderr）。"""
    _stub_dict_and_assertions(tmp_path, monkeypatch)
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen(set(), calls))
    B.build(continue_on_error=True)
    err = capsys.readouterr().err
    assert SIGNAL in err
    for g in GROUPS:
        assert g in err


def test_rebuild_signal_not_on_stdout(rq3_root, tmp_path, monkeypatch,
                                       capsys):
    """护栏信号只走 stderr ⇒ stdout 逐字节不变。"""
    _stub_dict_and_assertions(tmp_path, monkeypatch)
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen(set(), calls))
    B.build(continue_on_error=True)
    captured = capsys.readouterr()
    assert SIGNAL not in captured.out
    assert SIGNAL in captured.err


def test_check_only_neither_rebuilds_nor_signals(rq3_root, tmp_path,
                                                  monkeypatch, capsys):
    """--check-only：既不重建语料，也不触发重建信号。"""
    _stub_dict_and_assertions(tmp_path, monkeypatch)
    _write_manifests(rq3_root)
    calls: list = []
    monkeypatch.setattr(B, "_run_seedgen", _fake_seedgen(set(), calls))
    rc = B.build(check_only=True)
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [], "--check-only 不该调用 seedgen"
    assert SIGNAL not in captured.err
    for g in GROUPS:
        assert _seed_files(rq3_root, g) == []


def test_snapshot_helpers_detect_change(tmp_path):
    """快照helper 自身的行为：目录 mtime 变 / 文件变 ⇒ 都能检出。"""
    d = tmp_path / "seeds"
    d.mkdir(parents=True)
    groups = {"A": d}
    before = B._snapshot_seed_dirs(groups)
    assert B._changed_seed_groups(before, before) == []

    (d / "x.raw").write_bytes(b"x")
    after = B._snapshot_seed_dirs(groups)
    assert B._changed_seed_groups(before, after) == ["A"]


def test_snapshot_helpers_ignore_untouched_groups(tmp_path):
    """未改动的组不进变更清单。"""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    before = B._snapshot_seed_dirs({"A": a, "B": b})
    (b / "x.raw").write_bytes(b"x")
    after = B._snapshot_seed_dirs({"A": a, "B": b})
    assert B._changed_seed_groups(before, after) == ["B"]
