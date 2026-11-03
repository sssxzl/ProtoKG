# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_common.py —— RQ3 共享常量与工具的契约。

固化「命名函数单一来源」「配置单一来源」「数值缺失写 NA」三条跨文件硬约定，
防止各脚本各自硬编码容器名 / CSV 表头 / 期望条数。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

import rq3_common as C  # noqa: E402


# ===========================================================================
# 命名（约定 C2）
# ===========================================================================

def test_container_name():
    """容器名规范：rq3_{group}_{fuzzer}_r{rep}。"""
    assert C.container_name("C", "chatafl", 3) == "rq3_C_chatafl_r3"
    assert C.container_name("A", "aflnet", 1) == "rq3_A_aflnet_r1"
    assert C.container_name("D", "chatafl", 5) == "rq3_D_chatafl_r5"


def test_out_dir_name():
    """输出目录名：{group}_{fuzzer}。"""
    assert C.out_dir_name("C", "chatafl") == "C_chatafl"


def test_group_label():
    """组标签与论文表 18 行名一致。"""
    assert C.group_label("A") == "A 守正"
    assert C.group_label("B") == "B 漏洞导向"
    assert C.group_label("C") == "C 完整聚焦"
    assert C.group_label("D").startswith("D")


def test_container_name_matches_orchestrator_template():
    """容器名与编排脚本的命名模板一致（防两处漂移）。"""
    cfg = C.load_config()
    tmpl = cfg["container_template"]
    assert tmpl.format(group="C", fuzzer="chatafl", rep=2) == \
        C.container_name("C", "chatafl", 2)


# ===========================================================================
# 配置（约定 C1）
# ===========================================================================

def test_config_loads_and_has_required_sections():
    """配置可读且含全部必需小节。"""
    cfg = C.load_config()
    for key in ("protocol", "image", "groups", "fuzzers", "reps", "ports",
                "container", "vm", "preflight", "docx", "stats",
                "dict_kinds"):
        assert key in cfg, f"配置缺 {key}"


def test_config_group_expectations_match_spec():
    """四组的期望条数 / 字典 token 数符合技术方案定稿。

    ★ 2026-11-03（批次 2.0 / P0）**按实测重新标定**：RFC 源补齐字段取值
      ⇒ 知识中枢 headers 取值池变化 ⇒ 种子内容与字典 token 数变化
      ⇒ 原值（38/50/123）与实测脱节 ⇒ 重新标定为 52/58/226。
    ★ 2026-11-03 批次 2.4（⑤ 层 action_seq 开启）后再次重标定为
      55/85/61/61（字典 token 24/24/226/24 不变）。
      详见 `local/RQ3_技术方案_20261024.md` 的「重新标定」小节。
    """
    cfg = C.load_config()
    assert cfg["groups"]["A"]["expect_seeds"] == 55
    assert cfg["groups"]["B"]["expect_seeds"] == 85
    assert cfg["groups"]["C"]["expect_seeds"] == 61
    assert cfg["groups"]["D"]["expect_seeds"] == 61
    for g in ("A", "B", "D"):
        assert cfg["groups"][g]["expect_dict_tokens"] == 24
    assert cfg["groups"]["C"]["expect_dict_tokens"] == 217


def test_config_base_dict_md5():
    """基础字典 MD5 与镜像内实测值一致。"""
    cfg = C.load_config()
    assert cfg["base_dict_md5"] == "464351f88db6c3f0bdac0de01859316b"


def test_config_docx_table_index_and_header():
    """docx 表 18 的 index 与表头签名（运行时三重定位用）。"""
    cfg = C.load_config()
    assert cfg["docx"]["table_index"] == 18
    assert cfg["docx"]["table_header"] == [
        "聚焦组", "种子数", "dry-run 通过率%", "分支覆盖%", "崩溃数", "变异命中率"]
    assert cfg["docx"]["preceding_paragraph"] == "Live555（RTSP，text）"
    assert cfg["docx"]["table_rows"] == 4
    assert cfg["docx"]["table_cols"] == 6


def test_config_container_network_is_none():
    """★ 容器网络必须是 none（关闭 ChatAFL LLM 增强的唯一机制性手段）。"""
    cfg = C.load_config()
    assert cfg["container"]["network"] == "none"


def test_config_ports_are_isolated():
    """容器 SUT 端口 8560 与 oracle 端口基址 8571 分离。"""
    cfg = C.load_config()
    assert cfg["ports"]["container_sut"] == 8560
    assert cfg["ports"]["oracle_base"] == 8571
    assert cfg["ports"]["oracle_base"] > cfg["ports"]["container_sut"]


# ===========================================================================
# CSV 表头（约定 §11.4「固定，不得改动」）
# ===========================================================================

def test_csv_headers_are_fixed():
    """各 CSV 的表头固定（跨脚本共享，防列序漂移）。"""
    assert C.P1_HEADER == ("group", "rep", "fuzzer", "n_states", "n_edges",
                           "paths_total_at_p1", "init_queue_count")
    assert C.P2_HEADER == ("group", "rep", "fuzzer", "n_states", "n_edges",
                           "bitmap_cvg", "unique_crashes", "unique_hangs",
                           "paths_total", "execs_done", "chat_times_max")
    assert C.SUMMARY_HEADER == ("group", "fuzzer", "metric", "n_reps", "mean",
                                "std", "raw_values")
    assert C.QUEUE_INDEX_HEADER == (
        "container", "group", "fuzzer", "rep", "snapshot_tag", "entry_name",
        "entry_md5", "root_seed", "kind", "hit_P1", "hit_P2", "hit_P3",
        "hit_P4", "layer")
    assert C.DRYRUN_HEADER == ("filename", "layer", "score",
                               "legal_illegal_expected", "verdict",
                               "retries_used", "note")


def test_p1_header_has_init_queue_count():
    """★ v2：P1 表头含 init_queue_count（V11 污染探针列）。"""
    assert "init_queue_count" in C.P1_HEADER


# ===========================================================================
# 统计工具
# ===========================================================================

def test_mean_std_ddof1():
    """标准差用样本标准差（ddof=1）。"""
    m, sd = C.mean_std([1, 2, 3, 4, 5])
    assert m == 3.0
    assert sd == pytest.approx(1.5811388, rel=1e-6)


def test_mean_std_skips_missing():
    """缺失值（None / NA / 空串 / 非数值）不参与计算。"""
    m, sd = C.mean_std([1, None, "NA", "", 3, "x"])
    assert m == 2.0
    assert sd == pytest.approx(1.4142135, rel=1e-6)


def test_mean_std_all_missing():
    """全缺失 → (None, None)（不是 0）。"""
    assert C.mean_std([None, "NA", ""]) == (None, None)


def test_fmt_missing_is_NA():
    """★ 约定 C5：数值缺失写 NA，不写 0、不写空。"""
    assert C.fmt(None) == "NA"
    assert C.fmt(3.14159, "{:.2f}") == "3.14"


def test_paired_win_rate():
    """配对胜率：> 0 计胜，== 0 计平不计胜。"""
    assert C.paired_win_rate([1.0, 2.0, -1.0]) == (2, 3)
    assert C.paired_win_rate([0.0, 0.0]) == (0, 2)
    assert C.paired_win_rate([]) == (0, 0)


# ===========================================================================
# 原子写 / 幂等（约定 C6）
# ===========================================================================

def test_write_csv_is_atomic_and_idempotent(tmp_path):
    """先写临时文件再 mv；重复写同一路径结果一致（幂等）。"""
    p = tmp_path / "a.csv"
    C.write_csv(p, C.P1_HEADER, [["A", 1, "chatafl", 1, 2, 3]])
    first = p.read_bytes()
    C.write_csv(p, C.P1_HEADER, [["A", 1, "chatafl", 1, 2, 3]])
    assert p.read_bytes() == first
    assert not list(tmp_path.glob("*.tmp"))


def test_write_csv_none_becomes_NA(tmp_path):
    """None → NA。"""
    p = tmp_path / "a.csv"
    C.write_csv(p, ("x", "y"), [[None, 1]])
    rows = C.read_csv(p)
    assert rows[0]["x"] == "NA"
    assert rows[0]["y"] == "1"


def test_tsv_roundtrip(tmp_path):
    """TSV 读写往返。"""
    p = tmp_path / "a.tsv"
    C.write_tsv(p, C.DRYRUN_HEADER, [["f.raw", "L3", 100, "legal", "LEGAL", 1, ""]])
    rows = C.read_tsv(p)
    assert rows[0]["filename"] == "f.raw"
    assert rows[0]["verdict"] == "LEGAL"


# ===========================================================================
# MD5 工具
# ===========================================================================

def test_md5_helpers(tmp_path):
    """MD5 工具：文件 / 目录 / 集合。"""
    (tmp_path / "a.raw").write_bytes(b"hello")
    (tmp_path / "b.raw").write_bytes(b"world")
    assert C.md5_file(tmp_path / "a.raw") == \
        "5d41402abc4b2a76b9719d911017c592"
    d = C.md5_dir(tmp_path)
    assert set(d) == {"a.raw", "b.raw"}
    assert len(C.md5_set(tmp_path)) == 2


def test_dict_token_count_and_tokens(tmp_path):
    """字典 token 计数与 token 集合。"""
    p = tmp_path / "x.dict"
    p.write_text('"a"\n"b"\n\n', encoding="utf-8")
    assert C.dict_token_count(p) == 2
    assert C.dict_tokens(p) == {"a", "b"}


# ===========================================================================
# manifest 读取辅助
# ===========================================================================

def test_manifest_indexes():
    """manifest 的三种索引（文件名 / MD5 / 序号）。"""
    manifest = {"seeds": [
        {"filename": "01_A.raw", "md5": "aa", "index": 1},
        {"filename": "02_B.raw", "md5": "bb", "index": 2},
    ]}
    assert set(C.manifest_by_filename(manifest)) == {"01_A.raw", "02_B.raw"}
    assert set(C.manifest_by_md5(manifest)) == {"aa", "bb"}
    assert set(C.manifest_by_index(manifest)) == {"01", "02"}


def test_required_seed_fields_cover_manifest_schema():
    """必需字段清单覆盖 manifest 的每条种子字段。"""
    for f in ("index", "rank", "filename", "md5", "bytes", "layer",
              "layer_name", "generated_by", "score", "description",
              "legal_illegal", "pattern_tags", "stream", "methods", "group"):
        assert f in C.REQUIRED_SEED_FIELDS
