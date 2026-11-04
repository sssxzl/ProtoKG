# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_manifest.py —— 种子 manifest 的完整性与正确性契约。

manifest 是 RQ3「变异命中率归因」与「论文可溯源」的数据基础，
必须保证：
  · 字段齐全（每条种子 15 个必需字段）
  · MD5 与磁盘文件**逐条**一致（归因主键正确）
  · 层归属判定正确（L1/L2/L3/L4）
  · `legal_illegal` **先判 illegal**（"illegal(同 track)" 含子串 legal）
  · 文件名与落盘文件名**零漂移**
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.downstream.selector import seed_layer  # noqa: E402
from core.fused.downstream.seed_manifest import (  # noqa: E402
    classify_legal_illegal, classify_pattern_tags, build_manifest,
    write_manifest, read_manifest, SCHEMA_VERSION,
)
from core.models import SeedCorpus, SeedMessage  # noqa: E402

#: manifest 的必需字段
REQUIRED_FIELDS = (
    "index", "rank", "filename", "md5", "bytes", "layer", "layer_name",
    "generated_by", "score", "description", "legal_illegal", "pattern_tags",
    "stream", "methods", "group",
)


def _seedgen(*args: str) -> subprocess.CompletedProcess:
    """调用 scripts/seedgen.py。"""
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seedgen.py"), *args],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace")


def _msg(method: str, url: str = "rtsp://127.0.0.1:8554/s") -> SeedMessage:
    """构造一条消息。"""
    return SeedMessage(method=method, url=url, headers={"CSeq": "1"})


def _seed(gb: str, desc: str, methods=None) -> SeedCorpus:
    """构造一条种子。"""
    ms = methods or ["DESCRIBE", "SETUP"]
    return SeedCorpus(protocol="rtsp", description=desc,
                      target_methods=ms, generated_by=gb,
                      messages=[_msg(m) for m in ms])


# ===========================================================================
# legal_illegal 判定
# ===========================================================================

def test_legal_illegal_checks_illegal_first():
    """★ 必须先判 illegal："illegal(同 track)" 含子串 legal，顺序反了会全判成 legal。"""
    assert classify_legal_illegal("boundary-candidate double_setup illegal(同 track)") \
        == "illegal"
    assert classify_legal_illegal("boundary-candidate double_setup legal(不同 track)") \
        == "legal"
    assert classify_legal_illegal("generic danger self-loop") == "n/a"
    assert classify_legal_illegal("") == "n/a"


def test_legal_illegal_illegal_substring_precedence():
    """描述里同时含 legal 与 illegal 时必须判 illegal。"""
    assert classify_legal_illegal("illegal legal mix") == "illegal"


# ===========================================================================
# pattern_tags 判定
# ===========================================================================

def test_pattern_tags_action_keywords():
    """action 关键词 → 模式标签。"""
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe",
              "boundary-candidate double_setup legal(不同 track)")) == ["P1"]
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe",
              "boundary-candidate interleave_seq legal(不切换)")) == ["P3"]
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe",
              "boundary-candidate lifecycle_seq illegal(重建)")) == ["P4"]
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe",
              "boundary-candidate uaf_seq illegal(重建)")) == ["P4"]


def test_pattern_tags_trigger_field_case_insensitive():
    """字段型漏洞的触发字段名判定必须大小写不敏感。"""
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe-vuln-field",
              "vuln-field empty_edge Transport illegal(边界值)")) == ["P3"]
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe-vuln-field",
              "vuln-field long_value track illegal(边界值)")) == ["P1"]
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe-vuln-field",
              "vuln-field long_value Session illegal(边界值)")) == ["P2"]


def test_pattern_tags_unknown_field_is_empty():
    """未映射的触发字段 → 空标签列表（不臆造标签）。"""
    assert classify_pattern_tags(
        _seed("rule-based:boundary-probe-vuln-field",
              "vuln-field long_value Digest illegal(边界值)")) == []


def test_pattern_tags_non_vuln_seed_empty():
    """非漏洞层的种子无模式标签。"""
    assert classify_pattern_tags(
        _seed("rule-based:edge-cover", "edge cover seed")) == []
    assert classify_pattern_tags(
        _seed("rule-based:generic-danger", "generic danger self-loop")) == []


# ===========================================================================
# seed_layer
# ===========================================================================

@pytest.mark.parametrize("gb,layer,name", [
    ("rule-based:edge-cover", "L1", "edge_cover"),
    ("rule-based:generic-danger", "L2", "generic_danger"),
    ("rule-based:canonical-session", "L4", "canonical"),
    ("rule-based:boundary-probe", "L3", "vuln_boundary"),
    ("rule-based:boundary-probe-vuln-field", "L3", "vuln_boundary"),
    ("rule-based:boundary-probe-semantic", "L3", "vuln_boundary"),
    ("rule-based:boundary-probe-constraint", "L3", "vuln_boundary"),
    ("rule-based:field-probe", "L0", "unknown"),
    ("llm-deepseek", "L0", "unknown"),
    ("", "L0", "unknown"),
])
def test_seed_layer_mapping(gb, layer, name):
    """层归属映射（与 manifest 的 layer / layer_name 一致）。"""
    assert seed_layer(_seed(gb, "d")) == (layer, name)


# ===========================================================================
# build_manifest / write_manifest
# ===========================================================================

def test_build_manifest_fields_and_md5(tmp_path):
    """manifest 的字段齐全 + MD5 与磁盘文件一致。"""
    seeds = [_seed("rule-based:edge-cover", "edge 1"),
             _seed("rule-based:boundary-probe",
                   "boundary-candidate double_setup illegal(同 track)")]
    from core.fused.downstream.rag_seedgen import write_seeds
    write_seeds(seeds, tmp_path)
    manifest = build_manifest(seeds, tmp_path, protocol="rtsp", group="C")
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["group"] == "C"
    assert manifest["seed_count"] == 2
    for i, entry in enumerate(manifest["seeds"], start=1):
        for f in REQUIRED_FIELDS:
            assert f in entry, f"缺字段 {f}"
        assert entry["index"] == i
        assert entry["rank"] == i
        p = tmp_path / entry["filename"]
        assert p.exists()
        assert entry["md5"] == hashlib.md5(p.read_bytes()).hexdigest()
        assert entry["bytes"] == p.stat().st_size
        assert entry["group"] == "C"


def test_manifest_filename_matches_disk(tmp_path):
    """★ manifest 的 filename 与磁盘文件名零漂移。"""
    from core.fused.downstream.rag_seedgen import write_seeds
    seeds = [_seed("rule-based:edge-cover", f"edge {i}") for i in range(5)]
    written = write_seeds(seeds, tmp_path)
    manifest = build_manifest(seeds, tmp_path, protocol="rtsp")
    assert [e["filename"] for e in manifest["seeds"]] == written


def test_manifest_roundtrip(tmp_path):
    """manifest 落盘 → 读回，内容一致。"""
    from core.fused.downstream.rag_seedgen import write_seeds
    seeds = [_seed("rule-based:generic-danger", "danger 1")]
    write_seeds(seeds, tmp_path)
    manifest = build_manifest(seeds, tmp_path, protocol="rtsp", group="B")
    p = write_manifest(manifest, tmp_path / "manifest.json")
    back = read_manifest(p)
    assert back == manifest


# ===========================================================================
# 端到端：CLI 产出的 manifest
# ===========================================================================

@pytest.mark.parametrize("group,expect", [("A", 38), ("B", 50), ("C", 50),
                                           ("D", 50)])
def test_cli_manifest_complete(tmp_path, group, expect):
    """CLI 产出的 manifest 字段齐全且条数正确。"""
    out = tmp_path / group
    r = _seedgen("--protocol", "rtsp", "--focus-group", group,
                 "--out", str(out), "--manifest")
    assert r.returncode == 0, r.stderr
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed_count"] == expect
    assert manifest["group"] == group
    assert manifest["seedgen"]["focus_group"] == group
    assert manifest["seedgen"]["danger_minimal"] is False
    assert manifest["seedgen"]["max_seeds"] is None
    for entry in manifest["seeds"]:
        for f in REQUIRED_FIELDS:
            assert f in entry, f"缺字段 {f}"
        assert (out / entry["filename"]).exists()
        assert entry["md5"] == hashlib.md5(
            (out / entry["filename"]).read_bytes()).hexdigest()


def test_cli_manifest_records_dictionary(tmp_path):
    """manifest 记录字典元信息（token 数 + MD5）。"""
    out = tmp_path / "C"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "C",
                     "--out", str(out), "--manifest").returncode == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    d = manifest["dictionary"]
    assert d["token_count"] == 123
    assert len(d["md5"]) == 32


def test_cli_no_manifest_without_flag(tmp_path):
    """不加 --manifest 时不产出 manifest.json（向后兼容）。"""
    out = tmp_path / "x"
    assert _seedgen("--protocol", "rtsp", "--danger", "--out", str(out)).returncode == 0
    assert not (out / "manifest.json").exists()


def test_cli_manifest_md5_unique_per_group(tmp_path):
    """组内 MD5 唯一（不复制种子）—— **按层分流**。

    ★ 批次 2.5：⑤ 层（action_seq）是**在基准层去重之后追加**的
      （``scripts/seedgen.py::_append_action_seq_seeds``：⑤ 开启时**不得裁剪**
      任何既有层 ⇒ ⑤ 是「纯追加」）⇒ **跨层**可能出现字节相同的两个种子。
      实测：组 C 有 1 处跨层重复 —— L3 ``01_DESCRIBE.raw``（boundary-probe-constraint）
      与 L5 ``M89_DESCRIBE.raw``（action-seq: drop-optional-header）字节相同。
      ⚠ 同一现象**批次 2.4 的 rtsp/B 组就已存在**（同一 MD5）⇒ 非 2.5 引入。

    ⇒ 故「不复制种子」的不变式拆成三条**各自严格**的断言：
      ① **层内** MD5 唯一（基准层与 ⑤ 层各自都过了 ``dedupe_seeds``）；
      ② **基准层内**（①~④ 合并，整体过了 ``dedupe_seeds``）MD5 唯一；
      ③ 组级跨层重复**只允许**是「⑤ 层 ⇔ 基准层」撞车（同层重复已在 ① 被拦），
         且撞车条数被钉死为当前实测值（防止静默增长）。
    """
    out = tmp_path / "C"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "C",
                     "--out", str(out), "--manifest").returncode == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    seeds = manifest["seeds"]
    mds = [e["md5"] for e in seeds]

    # ① 层内 MD5 唯一
    by_layer: dict = {}
    for e in seeds:
        by_layer.setdefault(e["layer"], []).append(e["md5"])
    for layer, lst in by_layer.items():
        assert len(set(lst)) == len(lst), f"{layer} 层内出现重复种子（复制了同一条）"

    # ② 基准层（①~④，不含 ⑤）整体 MD5 唯一
    base_mds = [e["md5"] for e in seeds if e["layer"] != "L5"]
    assert len(set(base_mds)) == len(base_mds), "基准层内出现重复种子"

    # ③ 跨层撞车只允许 ⑤ ⇔ 基准层，且条数钉死
    cnt = Counter(mds)
    dups = {md: n for md, n in cnt.items() if n > 1}
    for md in dups:
        layers = {e["layer"] for e in seeds if e["md5"] == md}
        assert "L5" in layers, f"重复种子未涉及 ⑤ 层: {md[:12]} {layers}"
        assert len(layers) == 2, f"重复种子跨了多于两层: {md[:12]} {layers}"
    # ★ 批次 2.5 **F9（跨层去重）后为 0**（旧值 1 ⇒ 那是 ③层与⑤层
    #   字节完全相同的已知缺陷；F9 让 ⑤ 层丢弃"未产生新内容"的变异
    #   ⇒ 跨层撞车归零 ⇒ 本断言从"记录缺陷"升级为"**防复发**"）
    assert len(dups) == 0, \
        f"组 C 跨层撞车应为 0 处（F9 后 ⑤ 层不与基准层重复），实际 {len(dups)} 处"
