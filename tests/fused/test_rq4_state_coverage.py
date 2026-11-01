# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_state_coverage.py —— 状态覆盖分析脚本的回归测试。

为什么需要这个测试
------------------
``scripts/rq4_state_coverage.py`` 承载一个**论文级论断**：

    AFLNet 的 ``region_t`` 即状态抽象（``state_sequence`` 为状态反馈序列，见
    ``aflnet.h``），``regions/`` 每个文件对应一个已发现状态，其文件数与
    ``paths_found`` **逐一相等** → 故 ``paths_found`` = 终态状态覆盖数。

这条论断支撑了论文中「状态覆盖口径」的结论（并据此修正了「主指标测不到
ProtoRAG 卖点」这一原先的判断）。若脚本的判定逻辑或数据解析出错，会直接污染
论文结论，故必须有测试锁住。

覆盖三件事
----------
1. **判定逻辑**：``paths_found`` 与 ``regions/`` 文件数必须被判为相等；
   不相等时必须被判为不一致（不能默认通过）。
2. **数据解析**：能从真实格式的 summary CSV 正确取出各组字段。
3. **结论判定**：三协议的胜负汇总必须由数据决定（构造数据 → 期望判定）。
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rq4_state_coverage.py"

SUMMARY_HEADER = [
    "protocol", "group", "rep", "container", "image", "start_time",
    "last_update", "fuzz_sec", "cycles_done", "execs_done", "execs_per_sec",
    "paths_total", "paths_found", "max_depth", "cur_path", "stability",
    "bitmap_cvg", "unique_crashes", "unique_hangs", "peak_rss_mb",
    "param_check", "exit_code", "command_line", "seed_files", "seed_regions",
    "dict_tokens", "l_per", "b_per",
]


def _load_module():
    spec = importlib.util.spec_from_file_location("rq4_state_coverage", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rq4_state_coverage"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_summary(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SUMMARY_HEADER})


def _row(proto: str, group: str, paths_found: int, paths_total: int,
         cvg: str, l_per: str, b_per: str) -> dict:
    return {
        "protocol": proto, "group": group, "rep": "1", "container": "c",
        "image": "i", "start_time": "1", "last_update": "2", "fuzz_sec": "3",
        "cycles_done": "1", "execs_done": "100", "execs_per_sec": "1.0",
        "paths_total": str(paths_total), "paths_found": str(paths_found),
        "max_depth": "3", "cur_path": "1", "stability": "1.0%",
        "bitmap_cvg": cvg, "unique_crashes": "0", "unique_hangs": "0",
        "peak_rss_mb": "1", "param_check": "OK", "exit_code": "0",
        "command_line": "x", "seed_files": "1", "seed_regions": "1",
        "dict_tokens": "0", "l_per": l_per, "b_per": b_per,
    }


def test_script_exists() -> None:
    assert SCRIPT.is_file(), f"缺少状态覆盖分析脚本: {SCRIPT}"


def test_collect_parses_summary_fields(tmp_path: Path) -> None:
    """能从真实格式的 summary CSV 正确取字段（按列名，不靠位置）。"""
    mod = _load_module()
    s = tmp_path / "rq4_summary.csv"
    _write_summary(s, [
        _row("rtsp", "protorag", 935, 974, "9.94%", "24.7", "15.7"),
        _row("rtsp", "baseline", 1098, 1105, "9.72%", "24.2", "15.4"),
    ])
    recs = mod.collect(s, None)
    assert len(recs) == 2
    by = {(r["protocol"], r["group"]): r for r in recs}
    pr = by[("rtsp", "protorag")]
    assert pr["paths_found"] == 935
    assert pr["paths_total"] == 974
    assert pr["bitmap_cvg"] == 9.94
    assert pr["l_per"] == 24.7
    assert pr["b_per"] == 15.7


def test_regions_count_matches_paths_found(tmp_path: Path) -> None:
    """★ 核心论断：``regions/`` 文件数必须与 ``paths_found`` 相等（6/6 组）。"""
    mod = _load_module()
    s = tmp_path / "rq4_summary.csv"
    _write_summary(s, [
        _row("rtsp", "protorag", 3, 4, "9.94%", "24.7", "15.7"),
        _row("rtsp", "baseline", 5, 6, "9.72%", "24.2", "15.4"),
        _row("sip", "protorag", 7, 8, "22.06%", "6.6", "1.6"),
        _row("sip", "baseline", 9, 10, "22.11%", "6.4", "1.5"),
        _row("smtp", "protorag", 11, 12, "10.00%", "5.9", "4.0"),
        _row("smtp", "baseline", 13, 14, "11.66%", "14.1", "9.2"),
    ])
    # 造 out_root：<proto>/<group>/r1/regions/ 下放对应数量的文件
    out_root = tmp_path / "out"
    for proto, group, n in [("rtsp", "protorag", 3), ("rtsp", "baseline", 5),
                            ("sip", "protorag", 7), ("sip", "baseline", 9),
                            ("smtp", "protorag", 11), ("smtp", "baseline", 13)]:
        rd = out_root / proto / group / "r1" / "regions"
        rd.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            # ★ 文件名不能含 ":"（Windows 非法）—— AFLNet 真实文件名形如
            #   "id:000151,src:000000,op:havoc,rep:64,+cov"，此处用等价的
            #   合法名（脚本只数文件个数，不解析名字）
            (rd / f"id-{i:06d}-src-000000-op-havoc-rep-1").write_text("x")
    recs = mod.collect(s, out_root)
    assert len(recs) == 6
    for r in recs:
        assert r["regions"] == r["paths_found"], (
            f"{r['protocol']}/{r['group']}: regions={r['regions']} "
            f"!= paths_found={r['paths_found']}")
    md = mod.render(recs)
    assert "全部相等" in md, "判定应给出「全部相等」"


def test_mismatched_regions_is_reported(tmp_path: Path) -> None:
    """★ 反向：regions 数与 paths_found **不一致**时必须报不一致（不能默认通过）。"""
    mod = _load_module()
    s = tmp_path / "rq4_summary.csv"
    _write_summary(s, [
        _row("rtsp", "protorag", 999, 1000, "9.94%", "24.7", "15.7"),
    ])
    out_root = tmp_path / "out"
    rd = out_root / "rtsp" / "protorag" / "r1" / "regions"
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "id:000000").write_text("x")          # 只有 1 个，与 999 不符
    recs = mod.collect(s, out_root)
    md = mod.render(recs)
    assert "存在不一致" in md, "不一致时必须显式报出，不能默认通过"
    assert "全部相等" not in md


def test_verdict_follows_data(tmp_path: Path) -> None:
    """★ 结论判定必须由数据决定：构造「状态口径下 protorag 全优」的数据。"""
    mod = _load_module()
    s = tmp_path / "rq4_summary.csv"
    _write_summary(s, [
        _row("rtsp", "protorag", 1200, 1201, "9.0%", "20.0", "10.0"),
        _row("rtsp", "baseline", 1000, 1001, "9.0%", "20.0", "10.0"),
        _row("sip", "protorag", 1800, 1801, "20.0%", "6.0", "1.0"),
        _row("sip", "baseline", 1700, 1701, "20.0%", "6.0", "1.0"),
        _row("smtp", "protorag", 600, 601, "10.0%", "6.0", "4.0"),
        _row("smtp", "baseline", 500, 501, "10.0%", "14.0", "9.0"),
    ])
    recs = mod.collect(s, None)
    md = mod.render(recs)
    assert "全部协议取得优势" in md, (
        "状态口径下 protorag 三协议全优时，判定应为「全部协议取得优势」\n" + md)


def test_verdict_detects_no_consistent_advantage(tmp_path: Path) -> None:
    """★ 反向：三协议方向不一致时，判定必须是「未取得一致优势」。"""
    mod = _load_module()
    s = tmp_path / "rq4_summary.csv"
    _write_summary(s, [
        _row("rtsp", "protorag", 900, 901, "9.9%", "25.0", "16.0"),
        _row("rtsp", "baseline", 1000, 1001, "9.7%", "24.0", "15.0"),
        _row("sip", "protorag", 1800, 1801, "22.0%", "6.6", "1.6"),
        _row("sip", "baseline", 1700, 1701, "22.1%", "6.4", "1.5"),
        _row("smtp", "protorag", 350, 351, "10.0%", "5.9", "4.0"),
        _row("smtp", "baseline", 520, 521, "11.6%", "14.1", "9.2"),
    ])
    recs = mod.collect(s, None)
    md = mod.render(recs)
    assert "未取得一致优势" in md, (
        "仅 sip 占优时，判定应为「未取得一致优势」\n" + md)
