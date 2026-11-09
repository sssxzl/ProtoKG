# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_metrics.py —— 指标计算与统计检验的行为契约。

固化 RQ3 指标层的关键不变式：
  · **manifest 与语料 MD5 不一致 → 报错中止**（不允许静默按文件名匹配）
  · 崩溃数为 0 → MHR_C 记 **N/A**（禁止记 0）
  · 数值缺失写 `NA`（不写 0、不写空）
  · MHR_A 池化比率 = Σ|命中| / Σ|derived|
  · 统计检验：Mann-Whitney 精确检验 + Holm 校正 + Cliff's δ + bootstrap CI
  · 未达显著时结论文字**不得**写「无差异」
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

import rq3_common as C  # noqa: E402
from scripts.rq3_stats import (  # noqa: E402
    mann_whitney_exact, kruskal_wallis, cliffs_delta, hodges_lehmann,
    bootstrap_ci, holm_correction, paired_win_rate, significance_claim,
)

#: 参考语料（RQ1.2 protorag）
REFERENCE = ROOT / "derived" / "model" / "seeds" / "rtsp" / "live555_20261024_110155"


# ===========================================================================
# 统计检验
# ===========================================================================

def test_mann_whitney_exact_identical_samples():
    """两组完全相同 → p = 1.0。"""
    p, _u = mann_whitney_exact([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert p == pytest.approx(1.0)


def test_mann_whitney_exact_min_reachable_p():
    """★ n=5 vs 5 完全分离时，最小可达双侧 p = 0.0079（组合数学下界）。"""
    p, _u = mann_whitney_exact([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert p == pytest.approx(0.0079, abs=1e-4)


def test_mann_whitney_exact_insufficient():
    """样本不足 → p 为 None（不是 0）。"""
    p, _u = mann_whitney_exact([1], [2, 3])
    assert p is None


def test_cliffs_delta_sign_and_bounds():
    """Cliff's δ：符号反映方向，值域 [-1, 1]。"""
    assert cliffs_delta([5, 6, 7], [1, 2, 3]) == pytest.approx(1.0)
    assert cliffs_delta([1, 2, 3], [5, 6, 7]) == pytest.approx(-1.0)
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)
    assert cliffs_delta([], [1]) is None


def test_hodges_lehmann_median_difference():
    """HL 中位数差 = 全部两两差的中心。

    [3,4,5] vs [1,2,3] 的两两差：2,1,0,3,2,1,4,3,2 → 排序 0,1,1,2,2,2,3,3,4
    → 中位数 = 2
    """
    assert hodges_lehmann([3, 4, 5], [1, 2, 3]) == pytest.approx(2.0)
    assert hodges_lehmann([5, 6], [1, 2]) == pytest.approx(4.0)
    assert hodges_lehmann([], [1]) is None


def test_kruskal_wallis_detects_difference():
    """KW 检验能检出组间差异。"""
    h, p = kruskal_wallis([[1, 2, 3, 4, 5], [10, 11, 12, 13, 14]])
    assert h is not None and h > 0
    assert p is not None and p < 0.05


def test_kruskal_wallis_insufficient():
    """组数不足 → (None, None)。"""
    assert kruskal_wallis([[1]]) == (None, None)


def test_bootstrap_ci_contains_point_estimate():
    """bootstrap 95% CI 包含点估计。"""
    a = [10.1, 10.2, 10.3, 10.4, 10.5]
    b = [9.1, 9.2, 9.3, 9.4, 9.5]
    lo, hi, point = bootstrap_ci(a, b, iters=2000)
    assert lo <= point <= hi
    assert point == pytest.approx(1.0)


def test_holm_correction_monotone():
    """Holm 校正：校正后 p 单调不减，且不小于原始 p。"""
    raw = {"a": 0.01, "b": 0.02, "c": 0.04}
    adj = holm_correction(raw)
    vals = [adj[k] for k in ("a", "b", "c")]
    assert vals == sorted(vals)
    for k in raw:
        assert adj[k] >= raw[k]
    assert all(v <= 1.0 for v in vals)


def test_holm_correction_keeps_none():
    """None 的 p 值保持 None（不是 0）。"""
    adj = holm_correction({"a": 0.01, "b": None})
    assert adj["b"] is None


# ===========================================================================
# 配对胜率（v2 §5.3.6 —— 主判定口径）
# ===========================================================================

def test_paired_win_rate_all_positive():
    """5/5 一致为正 → win_rate = 1.0，consistent_sign = True。"""
    wr = paired_win_rate([0.37, 0.69, 0.44, 0.69, 0.68])
    assert wr["n_pairs"] == 5
    assert wr["wins"] == 5
    assert wr["ties"] == 0
    assert wr["losses"] == 0
    assert wr["win_rate"] == 1.0
    assert wr["consistent_sign"] is True
    assert wr["all_diffs"] == [0.37, 0.69, 0.44, 0.69, 0.68]
    assert wr["mean_diff"] == pytest.approx(0.574)
    assert wr["std_diff"] == pytest.approx(0.1563, abs=1e-3)


def test_paired_win_rate_outlier_dominates_mean():
    """★ 单个离群 rep 会主导均值 → 必须看胜率而非只看均值。

    合成示例（非实测终态）：n_edges 差 +4/−2/−1/−1/+28，均值 +5.6 被 r5 的 +28 拉高
    → 胜率仅 2/5 → **不得**声称「稳定探索到更多边」。
    """
    wr = paired_win_rate([4, -2, -1, -1, 28])
    assert wr["mean_diff"] == pytest.approx(5.6)
    assert wr["wins"] == 2               # 只有 4 与 28 为正
    assert wr["win_rate"] == pytest.approx(0.4)   # 2/5
    assert wr["consistent_sign"] is False
    # 去掉最大 |d| 后重算
    assert wr["without_outlier"] is not None
    assert wr["without_outlier"]["n_pairs"] == 4


def test_paired_win_rate_ties():
    """平局计入 ties，不计胜。"""
    wr = paired_win_rate([1.0, 0.0, -1.0, 0.0, 2.0])
    assert wr["wins"] == 2
    assert wr["ties"] == 2
    assert wr["losses"] == 1
    assert wr["win_rate"] == pytest.approx(0.4)


def test_paired_win_rate_empty():
    """空输入 → None（不是 0）。"""
    wr = paired_win_rate([])
    assert wr["n_pairs"] == 0
    assert wr["win_rate"] is None
    assert wr["mean_diff"] is None


def test_significance_claim_discipline():
    """★ 表述纪律：win rate < 5/5 禁止写「稳定/一致」；未达显著禁止写「无差异」。"""
    min_p = 0.0079
    # 5/5 一致 → 可以写「一致占优」
    c5 = significance_claim(paired_win_rate([1, 2, 3, 4, 5]), min_p)
    assert "一致占优" in c5
    # 4/5 → 必须写「未达统计显著」，且不得出现「稳定」
    c4 = significance_claim(paired_win_rate([1, 2, 3, -1, 5]), min_p)
    assert "未达统计显著" in c4
    assert "稳定" not in c4
    assert "无差异" not in c4
    # 0/5 → 方向为负
    c0 = significance_claim(paired_win_rate([-1, -2, -3, -4, -5]), min_p)
    assert "未达统计显著" in c0
    assert "无差异" not in c0


# ===========================================================================
# manifest 一致性断言
# ===========================================================================

def test_metrics_aborts_on_md5_mismatch(tmp_path, monkeypatch):
    """★ manifest 与语料 MD5 不一致 → 报错中止（不静默按文件名匹配）。"""
    # ★ 产物根重定向到 tmp ⇒ 本用例**绝不写**真实的 derived/experiments/rq3/C/manifest.json
    #   （旧写法会「写进去再写回来」⇒ 内容虽复原，**mtime 却变** ⇒
    #     pytest 一跑就把「语料已被重建」护栏信号点亮，且污染已发表语料的 mtime）。
    monkeypatch.setattr(C, "RQ3_ROOT", tmp_path)
    # 构造一个 manifest 指向不存在的语料
    fake = tmp_path / "C"
    fake.mkdir()
    mpath = C.group_manifest_path("C")
    orig = mpath.read_text(encoding="utf-8") if mpath.exists() else None
    try:
        mpath.write_text(json.dumps({
            "schema_version": "1.0", "protocol": "rtsp", "group": "C",
            "seed_count": 1,
            "seeds": [{"index": 1, "rank": 1, "filename": "01_X.raw",
                       "md5": "deadbeef" * 4, "bytes": 1, "layer": "L1",
                       "layer_name": "edge_cover", "generated_by": "x",
                       "score": 1, "description": "", "legal_illegal": "n/a",
                       "pattern_tags": [], "stream": "", "methods": [],
                       "group": "C"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(C, "group_seed_dir", lambda g, create=False: fake)
        from scripts import rq3_metrics
        with pytest.raises(SystemExit) as exc:
            rq3_metrics._load_manifest_checked("C")
        assert "MD5 不一致" in str(exc.value)
    finally:
        if orig is not None:
            mpath.write_text(orig, encoding="utf-8")
        else:
            mpath.unlink(missing_ok=True)


def test_metrics_missing_dryrun_yields_na(tmp_path, monkeypatch):
    """未采集 dryrun.tsv / 采集产物 → M2/M3 记 N/A（不是 0）。"""
    from scripts import rq3_metrics
    # 在临时目录里造一份最小可用的 manifest + 语料（MD5 自洽）
    seed_dir = tmp_path / "C" / "seeds"
    seed_dir.mkdir(parents=True)
    raw = b"DESCRIBE rtsp://127.0.0.1:8554/s RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    (seed_dir / "01_DESCRIBE.raw").write_bytes(raw)
    md5 = hashlib.md5(raw).hexdigest()
    (tmp_path / "C" / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "protocol": "rtsp", "group": "C",
        "seed_count": 1,
        "seeds": [{"index": 1, "rank": 1, "filename": "01_DESCRIBE.raw",
                   "md5": md5, "bytes": len(raw), "layer": "L1",
                   "layer_name": "edge_cover", "generated_by": "rule-based:edge-cover",
                   "score": 20, "description": "edge", "legal_illegal": "n/a",
                   "pattern_tags": [], "stream": "", "methods": ["DESCRIBE"],
                   "group": "C"}],
    }, ensure_ascii=False), encoding="utf-8")
    # 把 RQ3_ROOT 指向临时目录 → 该组既无 dryrun.tsv 也无采集产物
    monkeypatch.setattr(rq3_metrics.C, "RQ3_ROOT", tmp_path)
    m = rq3_metrics._group_metrics("C", tmp_path, "chatafl", [1, 2, 3, 4, 5])
    assert "note" in m["M2_dryrun"]
    assert m["M3_coverage"].get("note")


def test_metrics_zero_crashes_is_na(tmp_path):
    """★ 崩溃数为 0 → MHR_C 记 N/A（禁止记 0）。"""
    from scripts import rq3_metrics
    m = rq3_metrics._group_metrics("C", tmp_path, "chatafl", [1])
    assert m["M5_mhr"]["C_crash"]["value"] is None
    assert "N/A" in m["M5_mhr"]["C_crash"]["note"]


# ===========================================================================
# 表 18 草稿格式
# ===========================================================================

def test_table18_draft_format():
    """表 18 草稿：列头固定 + 缺失写 NA。"""
    from scripts.rq3_metrics import _table18_draft
    cfg = C.load_config()
    draft = _table18_draft({}, cfg)
    assert "| 聚焦组 | 种子数 | dry-run 通过率% | 分支覆盖% | 崩溃数 | 变异命中率 |" \
        in draft
    assert "NA" in draft


def test_table18_draft_values():
    """表 18 草稿：有指标时按「均值 ± 标准差」紧凑形式输出。"""
    from scripts.rq3_metrics import _table18_draft
    cfg = C.load_config()
    m = {
        "M1_seed_count_design": 50,
        "M2_dryrun": {"rv": 84.0},
        "M3_coverage": {"mean": 10.37, "std": 0.09},
        "M4_crashes": {"p1_total": 0.0, "p2_total": 0.0},
        "M5_mhr": {"A_targeted": {"pooled": 3.10}},
    }
    draft = _table18_draft({"A": m, "B": m, "C": m}, cfg)
    assert "10.37 ± 0.09" in draft
    assert "3.10" in draft
    assert "84.0" in draft
    assert "0 (P2=0)" in draft
    assert "不具区分度" in draft
