# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_analyze_aligned.py —— RQ4 对齐表（execs_done 对齐）的回归测试。

背景
----
``rq4_analyze.render_aligned`` 原先把**多个 rep 的快照合并成一条序列**再插值::

    for rep in reps:
        pts.extend(load_snapshots(out_root, proto, group, rep))
    series[group] = sorted(pts)

不同 rep 的 (execs, cov) 点混在同一个有序序列里，插值会**跨越 rep 边界**取值，
产生统计上无效的差值。

QA 用合成数据实测：REPS=2，rep1 恒优 +4.0、rep2 恒劣 -4.0，**真实均值差 = 0.00**，
旧实现却给出 ``+2.00 / -2.00 / +4.00`` 的**虚假信号**。

正确口径：**每个 rep 各自**在公共窗口内插值 → rep 内求差 → 再跨 rep 求均值。

本文件覆盖：

* 多 rep 场景下对齐表差值必须 ≈ 0（不得出现 ±2/±4 的虚假信号）；
* REPS=1 时输出必须与旧实现**完全等价**（向后兼容）；
* 公共窗口的语义（两组 execs_done 的公共重叠区间）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.rq4_analyze import (  # noqa: E402
    aligned_coverage,
    load_snapshots,
    render_aligned,
)

PROTO = "rtsp"


# ---------------------------------------------------------------------------
# 合成数据构造
# ---------------------------------------------------------------------------
def _write_snapshots(out_root: Path, group: str, rep: int,
                     points: list[tuple[int, float]]) -> None:
    """把 (execs_done, bitmap_cvg) 序列写成 fuzzer_stats 快照文件。"""
    d = out_root / PROTO / group / f"r{rep}"
    d.mkdir(parents=True, exist_ok=True)
    for i, (execs, cov) in enumerate(points):
        (d / f"stats_{1700000000 + i * 60}.txt").write_text(
            f"execs_done : {execs}\n"
            f"bitmap_cvg : {cov}%\n",
            encoding="utf-8")


def _row(group: str, rep: int) -> dict:
    """构造一行 summary 记录（render_aligned 只用到 protocol/group/rep）。"""
    return {"protocol": PROTO, "group": group, "rep": rep}


def _parse_aligned_diffs(text: str) -> list[float]:
    """从对齐表里抽出「差值」列（最后一列，格式形如 ``+1.23``）。"""
    diffs: list[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 5 or cells[0] == "协议":
            continue
        if not cells[1].lstrip("+-").isdigit():
            continue  # 分隔行 `|---|---|...`
        diffs.append(float(cells[4]))
    return diffs


# ---------------------------------------------------------------------------
# 核心回归：两 rep 反向偏移 → 均值差必须 ≈ 0
# ---------------------------------------------------------------------------
def test_two_reps_opposite_offsets_give_zero_mean_diff(tmp_path):
    """QA 的构造：rep1 恒优 +4.0、rep2 恒劣 -4.0 → 每个 target 的均值差必须 ≈ 0。

    旧实现（合并 rep 后插值）会给出 +2.00 / -2.00 / +4.00 的虚假信号。
    """
    out_root = tmp_path / "out"
    # 公共窗口：execs 0..1000，10 个采样点
    base = [(i * 100, 10.0 + i) for i in range(11)]
    # rep1：protorag 比 baseline 高 4.0（恒优）
    _write_snapshots(out_root, "baseline", 1, base)
    _write_snapshots(out_root, "protorag", 1,
                     [(e, c + 4.0) for e, c in base])
    # rep2：protorag 比 baseline 低 4.0（恒劣）
    _write_snapshots(out_root, "baseline", 2, base)
    _write_snapshots(out_root, "protorag", 2,
                     [(e, c - 4.0) for e, c in base])

    rows = [_row("protorag", 1), _row("baseline", 1),
            _row("protorag", 2), _row("baseline", 2)]

    diffs = _parse_aligned_diffs(render_aligned(rows, out_root))
    assert diffs, "对齐表没有产出任何数据行"
    for d in diffs:
        assert abs(d) < 1e-6, (
            f"两 rep 反向偏移的均值差必须为 0，实际 {d:+.2f}（虚假信号）")


def test_two_reps_report_n_and_note(tmp_path):
    """多 rep 时必须报告 n（rep 数），并在表后给出脚注说明口径。"""
    out_root = tmp_path / "out"
    base = [(i * 100, 10.0 + i) for i in range(11)]
    for rep in (1, 2):
        _write_snapshots(out_root, "baseline", rep, base)
        _write_snapshots(out_root, "protorag", rep,
                         [(e, c + (4.0 if rep == 1 else -4.0)) for e, c in base])
    rows = [_row("protorag", 1), _row("baseline", 1),
            _row("protorag", 2), _row("baseline", 2)]

    text = render_aligned(rows, out_root)
    assert "n = 2" in text, "多 rep 时必须报告 n = rep 数"
    assert "跨 rep 求均值" in text, "必须说明多重复的聚合口径"


def test_single_rep_output_has_no_multi_rep_note(tmp_path):
    """REPS=1 时不输出多重复脚注（保持与旧实现逐字节等价）。"""
    out_root = tmp_path / "out"
    base = [(i * 100, 10.0 + i) for i in range(11)]
    _write_snapshots(out_root, "baseline", 1, base)
    _write_snapshots(out_root, "protorag", 1, [(e, c + 1.5) for e, c in base])
    rows = [_row("protorag", 1), _row("baseline", 1)]

    text = render_aligned(rows, out_root)
    assert "n = " not in text, "单 rep 时不应出现多重复脚注"
    assert "跨 rep 求均值" not in text


# ---------------------------------------------------------------------------
# 向后兼容：REPS=1 的数值必须与旧（合并插值）实现完全一致
# ---------------------------------------------------------------------------
def test_single_rep_matches_legacy_merged_interpolation(tmp_path):
    """REPS=1 时，新实现必须与旧"合并插值"实现给出**完全相同**的数值。

    旧实现（单 rep 时合并与否等价）::

        series[group] = sorted(pts)          # 单 rep → 就是该 rep 的序列
        lo = max(series["protorag"][0][0], series["baseline"][0][0])
        hi = min(series["protorag"][-1][0], series["baseline"][-1][0])
        for frac in (0.25, 0.5, 0.75, 1.0):
            target = int(lo + (hi - lo) * frac)
            c1 = aligned_coverage(series["protorag"], target)
            c2 = aligned_coverage(series["baseline"], target)

    新实现（逐 rep 插值）在 REPS=1 时必须与之**逐点相等**。
    """
    out_root = tmp_path / "out"
    base = [(i * 137, 3.5 + i * 1.25) for i in range(12)]
    _write_snapshots(out_root, "baseline", 1, base)
    _write_snapshots(out_root, "protorag", 1,
                     [(e, c + 2.25) for e, c in base])
    rows = [_row("protorag", 1), _row("baseline", 1)]

    # ---- 旧实现的参考算法（单 rep 情形）----
    series = {
        "protorag": sorted(load_snapshots(out_root, PROTO, "protorag", 1)),
        "baseline": sorted(load_snapshots(out_root, PROTO, "baseline", 1)),
    }
    lo = max(series["protorag"][0][0], series["baseline"][0][0])
    hi = min(series["protorag"][-1][0], series["baseline"][-1][0])
    legacy: list[tuple[int, float, float, float]] = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        target = int(lo + (hi - lo) * frac)
        c1 = aligned_coverage(series["protorag"], target)
        c2 = aligned_coverage(series["baseline"], target)
        legacy.append((target, c1, c2, c1 - c2))

    # ---- 新实现的输出 ----
    cells: list[tuple[int, float, float, float]] = []
    for line in render_aligned(rows, out_root).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [c.strip() for c in line.strip("|").split("|")]
        if len(parts) != 5 or parts[0] == "协议":
            continue
        if not parts[1].lstrip("+-").isdigit():
            continue  # 分隔行
        cells.append((int(parts[1]), float(parts[2]), float(parts[3]),
                      float(parts[4])))

    assert len(cells) == len(legacy), "行数与旧实现不一致"
    for (t1, a1, b1, d1), (t2, a2, b2, d2) in zip(cells, legacy):
        assert t1 == t2
        # 对齐表按 2 位小数展示，故比较**格式化后的字符串**（与展示口径一致）
        assert f"{a1:.2f}" == f"{a2:.2f}", \
            f"target={t1} protorag 值变化: {a1:.2f} vs {a2:.2f}"
        assert f"{b1:.2f}" == f"{b2:.2f}", \
            f"target={t1} baseline 值变化: {b1:.2f} vs {b2:.2f}"
        assert f"{d1:+.2f}" == f"{d2:+.2f}", \
            f"target={t1} 差值变化: {d1:+.2f} vs {d2:+.2f}"


def test_single_rep_aligned_table_is_byte_identical_to_legacy(tmp_path):
    """REPS=1 时整个对齐表（含表头/分隔行）必须与旧实现逐字节一致。

    旧实现输出（单 rep）::

        | rtsp | 250 | 11.50 | 10.50 | +1.00 |
    """
    out_root = tmp_path / "out"
    base = [(i * 100, 10.0 + i) for i in range(11)]
    _write_snapshots(out_root, "baseline", 1, base)
    _write_snapshots(out_root, "protorag", 1, [(e, c + 1.0) for e, c in base])
    rows = [_row("protorag", 1), _row("baseline", 1)]

    series = {
        "protorag": sorted(load_snapshots(out_root, PROTO, "protorag", 1)),
        "baseline": sorted(load_snapshots(out_root, PROTO, "baseline", 1)),
    }
    lo = max(series["protorag"][0][0], series["baseline"][0][0])
    hi = min(series["protorag"][-1][0], series["baseline"][-1][0])
    legacy_lines = [
        "## execs_done 对齐的 bitmap_cvg（主指标口径）",
        "",
        "| 协议 | 对齐 execs_done | protorag bitmap_cvg | baseline bitmap_cvg | 差值 |",
        "|---|---|---|---|---|",
    ]
    for frac in (0.25, 0.5, 0.75, 1.0):
        target = int(lo + (hi - lo) * frac)
        c1 = aligned_coverage(series["protorag"], target)
        c2 = aligned_coverage(series["baseline"], target)
        legacy_lines.append(
            f"| {PROTO} | {target} | {c1:.2f} | {c2:.2f} | {c1 - c2:+.2f} |")
    legacy_lines.append("")
    legacy = "\n".join(legacy_lines)

    assert render_aligned(rows, out_root) == legacy, (
        "REPS=1 的对齐表必须与旧实现逐字节一致（QA 已对过 12 个点的数值）")


# ---------------------------------------------------------------------------
# 公共窗口语义
# ---------------------------------------------------------------------------
def test_common_window_uses_overlap_of_both_groups(tmp_path):
    """公共窗口 = 两组 execs_done 的公共重叠区间 [max(起点), min(终点)]。"""
    out_root = tmp_path / "out"
    # protorag 覆盖 execs 0..1000；baseline 只覆盖 400..800 → 公共窗口 400..800
    _write_snapshots(out_root, "protorag", 1,
                     [(i * 100, 10.0 + i) for i in range(11)])
    _write_snapshots(out_root, "baseline", 1,
                     [(i * 100, 10.0 + i) for i in range(4, 9)])
    rows = [_row("protorag", 1), _row("baseline", 1)]

    targets = []
    for line in render_aligned(rows, out_root).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [c.strip() for c in line.strip("|").split("|")]
        if len(parts) != 5 or parts[0] == "协议":
            continue
        if not parts[1].lstrip("+-").isdigit():
            continue  # 分隔行
        targets.append(int(parts[1]))

    assert targets, "对齐表没有产出数据行"
    assert min(targets) >= 400, f"target 不应早于公共窗口起点 400: {targets}"
    assert max(targets) <= 800, f"target 不应晚于公共窗口终点 800: {targets}"


def test_missing_snapshots_produces_no_rows(tmp_path):
    """某组完全没有快照 → 该协议跳过（不产出误导性的行）。"""
    out_root = tmp_path / "out"
    _write_snapshots(out_root, "protorag", 1,
                     [(i * 100, 10.0 + i) for i in range(11)])
    rows = [_row("protorag", 1), _row("baseline", 1)]
    text = render_aligned(rows, out_root)
    assert _parse_aligned_diffs(text) == [], "缺 baseline 快照时不应产出数据行"


def test_reps_with_partial_data_only_use_complete_reps(tmp_path):
    """只有部分 rep 两组都有数据时，只用完整的 rep 参与统计（n 必须正确）。"""
    out_root = tmp_path / "out"
    base = [(i * 100, 10.0 + i) for i in range(11)]
    _write_snapshots(out_root, "baseline", 1, base)
    _write_snapshots(out_root, "protorag", 1, [(e, c + 1.0) for e, c in base])
    # rep2 只有 protorag 有快照 → 不参与统计
    _write_snapshots(out_root, "protorag", 2, [(e, c + 9.0) for e, c in base])
    rows = [_row("protorag", 1), _row("baseline", 1),
            _row("protorag", 2), _row("baseline", 2)]

    text = render_aligned(rows, out_root)
    diffs = _parse_aligned_diffs(text)
    assert diffs, "对齐表没有产出任何数据行"
    for d in diffs:
        assert abs(d - 1.0) < 1e-6, f"差值应只反映 rep1 的 +1.0，实际 {d:+.2f}"
    assert "n = 2" not in text, "只有 1 个完整 rep 时不应报告 n = 2"
