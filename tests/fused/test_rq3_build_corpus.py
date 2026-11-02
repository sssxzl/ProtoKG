# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_build_corpus.py —— 语料组装与一致性断言的契约。

固化 RQ3 语料层的硬不变式（A1–A10）：
  · 四组条数 38/50/50/50
  · B/C/D 的 MD5 集合相等；C 集合 == RQ1.2 protorag 语料
  · A 的 38 条 == B 的前 38 条（自然序限定）
  · 定向字典是基础字典的**严格超集**（D→C 单变量的前提）
  · 组内 MD5 唯一（不复制种子）

★ **pytest 隔离（重要）**：本模块**绝不允许**写真实的 ``derived/rq3/``。
  ``derived/rq3/`` 是**已发表语料**（论文引用）：pytest 若直接写它
  ⇒ 一跑就重建真实语料（内容 + mtime 全变）⇒ 既污染数据，又让
  「语料已被重建」护栏信号永远为真（无法区分本次构建与历史产物）。
  ⇒ 构建器的 ``--root`` 指向 pytest 的 ``tmp_path``（见 :func:`_build`）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

import rq3_common as C  # noqa: E402

#: 历史参考语料（RQ1.2 protorag）
REFERENCE = ROOT / "derived" / "seeds" / "rtsp" / "live555_20261024_110155"


def _md5s(directory: Path) -> set:
    """目录下 .raw 的 MD5 集合。"""
    return {hashlib.md5(f.read_bytes()).hexdigest()
            for f in sorted(directory.glob("*.raw"))}


def _md5_map(directory: Path) -> dict:
    """目录下 .raw 的 `{文件名: MD5}`。"""
    return {f.name: hashlib.md5(f.read_bytes()).hexdigest()
            for f in sorted(directory.glob("*.raw"))}


def _build(root: Path) -> subprocess.CompletedProcess:
    """运行语料构建器，**``--root`` 指向 ``root``**。

    ★ ``--root`` = 构建根重定向 ⇒ 全部产物落在 ``root`` 下，
      **不碰真实的 ``derived/rq3/``**（pytest 隔离）。
    """
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rq3_build_corpus.py"),
         "--root", str(root)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace")


@pytest.fixture(scope="module")
def rq3_root(tmp_path_factory):
    """构建根目录（**pytest 隔离** ⇒ 绝不触碰 ``derived/rq3/``）。"""
    return tmp_path_factory.mktemp("rq3")


@pytest.fixture(scope="module")
def built(rq3_root):
    """构建四组语料（模块级，只跑一次；产物落在 ``rq3_root``）。"""
    r = _build(rq3_root)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


# ===========================================================================
# 构建产物
# ===========================================================================

def test_build_succeeds(built):
    """构建器退出码 0（全部断言通过）。"""
    assert built.returncode == 0


def test_layout_created(built, rq3_root):
    """目录骨架符合技术方案 §11.1。"""
    for g in ("A", "B", "C", "D"):
        assert (rq3_root / g / "seeds").is_dir()
        assert (rq3_root / g / "manifest.json").is_file()
    assert (rq3_root / "dict").is_dir()
    assert (rq3_root / "groups.json").is_file()
    assert (rq3_root / "dict" / "DICT_FROZEN.json").is_file()


def test_groups_json_content(built, rq3_root):
    """groups.json 含编排所需的全部字段（编排脚本的唯一输入）。"""
    data = C.read_json(rq3_root / "groups.json")
    assert set(data["groups"]) == {"A", "B", "C", "D"}
    for g, gi in data["groups"].items():
        for k in ("group", "label", "layers", "order", "dict_kind",
                  "dict_file", "dict_tokens", "expect_seeds", "seed_count",
                  "seed_md5_set", "seed_files", "manifest"):
            assert k in gi, f"组 {g} 缺字段 {k}"
        assert gi["seed_count"] == gi["expect_seeds"]
        assert len(gi["seed_md5_set"]) == gi["expect_seeds"]
        assert len(gi["seed_files"]) == gi["expect_seeds"]


def test_dict_frozen_record(built, rq3_root):
    """DICT_FROZEN.json 记录 token 数 + MD5（防字典内容漂移）。"""
    data = C.read_json(rq3_root / "dict" / "DICT_FROZEN.json")
    kinds = {r["kind"]: r for r in data["dictionaries"]}
    assert kinds["base"]["token_count"] == 24
    assert kinds["base"]["md5"] == "464351f88db6c3f0bdac0de01859316b"
    assert kinds["targeted"]["token_count"] == 123
    assert kinds["targeted-compact"]["token_count"] == 32
    assert data["base_md5"] == "464351f88db6c3f0bdac0de01859316b"


def test_assertion_report_all_pass(built, rq3_root):
    """断言报告里没有 FAIL。"""
    text = (rq3_root / "assertions_report.md").read_text(encoding="utf-8")
    assert "| FAIL |" not in text
    assert "失败: 0" in text


# ===========================================================================
# A1–A10 断言（逐条复核）
# ===========================================================================

@pytest.mark.parametrize("group,expect", [("A", 38), ("B", 50), ("C", 50),
                                           ("D", 50)])
def test_a1_seed_counts(built, rq3_root, group, expect):
    """A1：语料条数正确。"""
    n = len(list((rq3_root / group / "seeds").glob("*.raw")))
    assert n == expect


def test_a4_a_is_prefix_of_b(built, rq3_root):
    """A4/A5：A 的 38 条与 B 的前 38 条逐字节相同（自然序）。"""
    ma = _md5_map(rq3_root / "A" / "seeds")
    mb = _md5_map(rq3_root / "B" / "seeds")
    assert list(ma) == list(mb)[:38]
    assert [ma[n] for n in ma] == [mb[n] for n in list(mb)[:38]]


def test_a6_bcd_same_set(built, rq3_root):
    """A6：B/C/D 的 MD5 集合相等。"""
    s = [_md5s(rq3_root / g / "seeds") for g in ("B", "C", "D")]
    assert s[0] == s[1] == s[2]
    assert len(s[0]) == 50


def test_a7_c_matches_rq12(built, rq3_root):
    """A7：C 的 MD5 集合 == RQ1.2 protorag 语料。"""
    if not REFERENCE.exists():
        pytest.skip("历史参考语料不存在")
    assert _md5s(rq3_root / "C" / "seeds") == _md5s(REFERENCE)


def test_a9_superset(built, rq3_root):
    """A9：定向字典是基础字典的严格超集。"""
    base = C.dict_tokens(rq3_root / "dict" / "rtsp_base.dict")
    tgt = C.dict_tokens(rq3_root / "dict" / "c_targeted.dict")
    assert base < tgt
    assert len(base) == 24
    assert len(tgt) == 123


def test_a10_md5_unique(built, rq3_root):
    """A10：组内 MD5 唯一（不复制种子）。"""
    for g in ("A", "B", "C", "D"):
        m = _md5_map(rq3_root / g / "seeds")
        assert len(set(m.values())) == len(m)


# ===========================================================================
# manifest 与语料的一致性
# ===========================================================================

@pytest.mark.parametrize("group", ["A", "B", "C", "D"])
def test_manifest_matches_corpus(built, rq3_root, group):
    """manifest 的 MD5/filename 与磁盘文件逐条一致。"""
    manifest = C.read_json(rq3_root / group / "manifest.json")
    seed_dir = rq3_root / group / "seeds"
    disk = _md5_map(seed_dir)
    assert len(manifest["seeds"]) == len(disk)
    for entry in manifest["seeds"]:
        p = seed_dir / entry["filename"]
        assert p.exists()
        assert entry["md5"] == hashlib.md5(p.read_bytes()).hexdigest()
        assert entry["md5"] == disk[entry["filename"]]


def test_manifest_cross_group_md5_consistency(built, rq3_root):
    """★ 跨组归因以 MD5 为主键：B/C/D 的文件名**不同**（顺序不同），
    但同一粒种子在各组的 MD5 相同 → 归因必须走 MD5，不能走文件名。"""
    manifests = {g: C.read_json(rq3_root / g / "manifest.json")
                 for g in ("B", "C", "D")}
    md5_by_file = {g: {e["filename"]: e["md5"] for e in m["seeds"]}
                   for g, m in manifests.items()}
    md5_sets = {g: set(d.values()) for g, d in md5_by_file.items()}
    assert md5_sets["B"] == md5_sets["C"] == md5_sets["D"]

    # B（自然序）与 C/D（漏洞接近度序）的**文件名集合不同** → 证明文件名不可作跨组主键
    assert set(md5_by_file["B"]) != set(md5_by_file["C"])
    # C 与 D 顺序相同（仅字典不同）→ 文件名集合相同，但内容 MD5 各自唯一
    assert set(md5_by_file["C"]) == set(md5_by_file["D"])

    # 每个 MD5 在**每组内**恰好出现一次（组内不复制）
    for g in ("B", "C", "D"):
        vals = list(md5_by_file[g].values())
        assert len(set(vals)) == len(vals) == 50

    # 同一粒种子在 B（自然序）与 C（排序后）指向**不同文件名**但**相同 MD5**
    for md5 in list(md5_sets["B"])[:5]:
        nb = next(n for n, m in md5_by_file["B"].items() if m == md5)
        nc = next(n for n, m in md5_by_file["C"].items() if m == md5)
        assert md5_by_file["B"][nb] == md5_by_file["C"][nc] == md5


# ===========================================================================
# 幂等
# ===========================================================================

def test_check_only_is_idempotent(built, rq3_root):
    """--check-only 重复执行结果一致（幂等）。"""
    cmd = [sys.executable, str(ROOT / "scripts" / "rq3_build_corpus.py"),
           "--check-only", "--root", str(rq3_root)]
    r1 = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                        encoding="utf-8")
    r2 = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                        encoding="utf-8")
    assert r1.returncode == 0 and r2.returncode == 0
    assert r1.stdout == r2.stdout
