# -*- coding: utf-8 -*-
"""scripts/rq4_state_coverage.py —— RQ4 状态覆盖（AFLNet state coverage）分析。

为什么需要这个脚本
------------------
ProtoRAG 的设计目标是**协议状态空间**探索，而 AFLNet 主指标 ``bitmap_cvg`` 度量的是
**边覆盖**（``count_non_255_bytes(virgin_bits)``），不含消息级状态覆盖——单看它会
低估 ProtoRAG 的作用。

但状态覆盖**无需新增指标、也无需重跑实验**：
AFLNet 的 ``region_t`` 就是它的状态抽象（``state_sequence`` 为状态反馈序列，见
``aflnet.h``），``regions/`` 目录下每个文件对应一个已发现状态，且**文件数与
``paths_found`` 逐一相等**。故 ``paths_found`` 即终态状态覆盖数。

用法
----
    python scripts/rq4_state_coverage.py --summary <rq4_summary.csv> [--out-root <dir>]

``--out-root`` 指向宿主上的采集产物根目录（含 ``<proto>/<group>/r1/``）；若该目录
下没有 ``regions/``，脚本会退回用 ``tar.gz`` 内的 ``regions/`` 条目数（等价，且
不依赖容器存在）。

输出
----
1. 每组的 ``paths_found``（= 状态数）与 ``regions/`` 文件数对照（验证二者相等）
2. 状态覆盖与边覆盖两口径下的组间差值，及两口径结论是否一致
3. 一句话判定：ProtoRAG 是否在**状态覆盖**口径上取得一致优势
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tarfile
from pathlib import Path

PROTOCOLS = ("rtsp", "sip", "smtp")
GROUPS = ("protorag", "baseline")


def _regions_count_from_tar(tar_path: Path) -> int | None:
    """统计 tar 内 ``regions/id:`` 条目数（不依赖容器）。"""
    if not tar_path.is_file():
        return None
    try:
        with tarfile.open(tar_path, "r:gz") as tf:
            return sum(1 for m in tf.getmembers()
                       if "/regions/id:" in m.name)
    except (tarfile.TarError, OSError):
        return None


def _regions_count_from_dir(out_root: Path, proto: str, group: str) -> int | None:
    """统计宿主 ``regions/`` 目录下的文件数（若采集时拷出）。"""
    d = out_root / proto / group / "r1" / "regions"
    if not d.is_dir():
        return None
    return sum(1 for _ in d.iterdir() if _.is_file())


def collect(summary_csv: Path, out_root: Path | None) -> list[dict]:
    """读 summary，逐组取 paths_found / regions 数 / 边覆盖 / 行覆盖。"""
    with summary_csv.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: list[dict] = []
    for r in rows:
        proto, group = r.get("protocol", ""), r.get("group", "")
        if proto not in PROTOCOLS or group not in GROUPS:
            continue
        rec = {
            "protocol": proto,
            "group": group,
            "paths_found": int(r["paths_found"]),
            "paths_total": int(r["paths_total"]),
            "bitmap_cvg": float(r["bitmap_cvg"].rstrip("%")),
            "l_per": float(r["l_per"]) if r.get("l_per") else None,
            "b_per": float(r["b_per"]) if r.get("b_per") else None,
            "execs_done": int(r["execs_done"]),
        }
        regions = None
        if out_root is not None:
            regions = _regions_count_from_dir(out_root, proto, group)
            if regions is None:
                regions = _regions_count_from_tar(
                    out_root / proto / group / "r1" / "out.tar.gz")
        rec["regions"] = regions
        out.append(rec)
    return out


def _delta(a: dict, b: dict, key: str) -> int | None:
    return a[key] - b[key]


def render(recs: list[dict]) -> str:
    """渲染状态覆盖对比报告。"""
    by = {(r["protocol"], r["group"]): r for r in recs}
    lines: list[str] = []
    lines.append("# RQ4 状态覆盖分析（paths_found = AFLNet 状态数）")
    lines.append("")
    lines.append("> 依据：AFLNet 的 `region_t` 即状态抽象（`state_sequence` 为状态反馈序列），")
    lines.append("> `regions/` 每个文件对应一个已发现状态，其文件数与 `paths_found` 逐一相等。")
    lines.append("> 故 `paths_found` = 终态状态覆盖数，无需新增指标或重跑实验。")
    lines.append("")
    lines.append("## 1. paths_found 与 regions 文件数对照")
    lines.append("")
    lines.append("| 协议 | 组 | paths_found | regions 文件数 | 相等？ |")
    lines.append("|---|---|---|---|---|")
    consistent = True
    for p in PROTOCOLS:
        for g in GROUPS:
            r = by.get((p, g))
            if not r:
                continue
            reg = r["regions"]
            ok = reg is not None and reg == r["paths_found"]
            if reg is not None and not ok:
                consistent = False
            lines.append(
                f"| {p} | {g} | {r['paths_found']} | "
                f"{reg if reg is not None else '（未取到）'} | "
                f"{'✓' if ok else ('✗' if reg is not None else '—')} |")
    lines.append("")
    lines.append(f"> 判定：{'全部相等，paths_found 可作状态覆盖指标' if consistent else '存在不一致，需复查'}。")
    lines.append("")
    lines.append("## 2. 两口径下的组间差值（protorag − baseline）")
    lines.append("")
    lines.append("| 协议 | Δ状态数 | 相对差 | Δ边覆盖(pp) | Δ行覆盖 | 两口径结论是否一致 |")
    lines.append("|---|---|---|---|---|---|")
    verdicts: dict[str, str] = {}
    for p in PROTOCOLS:
        pr, bl = by.get((p, "protorag")), by.get((p, "baseline"))
        if not pr or not bl:
            continue
        ds = _delta(pr, bl, "paths_found")
        rel = ds / bl["paths_found"] * 100 if bl["paths_found"] else 0.0
        dc = pr["bitmap_cvg"] - bl["bitmap_cvg"]
        dl = (pr["l_per"] - bl["l_per"]) if (pr["l_per"] is not None and bl["l_per"] is not None) else None
        same = (ds > 0) == (dc > 0)
        verdicts[p] = "protorag 优" if ds > 0 else "protorag 劣"
        lines.append(
            f"| {p} | {ds:+d} | {rel:+.1f}% | {dc:+.2f} | "
            f"{('%+.1f' % dl) if dl is not None else '—'} | "
            f"{'一致' if same else '不一致'} |")
    lines.append("")
    wins = [p for p, v in verdicts.items() if v == "protorag 优"]
    if len(wins) == len(verdicts):
        lines.append("> **判定：ProtoRAG 在状态覆盖口径上于全部协议取得优势。**")
    elif not wins:
        lines.append("> **判定：ProtoRAG 在状态覆盖口径上于全部协议落后。**")
    else:
        lines.append(
            f"> **判定：状态覆盖口径下 ProtoRAG 仅在 {', '.join(wins)} 占优，"
            f"协议族内未取得一致优势。**")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RQ4 状态覆盖分析")
    ap.add_argument("--summary", required=True, type=Path,
                    help="rq4_summary.csv 路径")
    ap.add_argument("--out-root", type=Path, default=None,
                    help="采集产物根目录（含 <proto>/<group>/r1/），用于取 regions 数")
    ap.add_argument("--json-out", type=Path, default=None, help="JSON 输出路径")
    ap.add_argument("--md-out", type=Path, default=None, help="Markdown 输出路径")
    args = ap.parse_args(argv)

    if not args.summary.is_file():
        print(f"[qa] 找不到 summary: {args.summary}", file=sys.stderr)
        return 1
    recs = collect(args.summary, args.out_root)
    if not recs:
        print("[qa] summary 中没有可用的协议/组记录", file=sys.stderr)
        return 1
    md = render(recs)
    print(md)
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(md + "\n", encoding="utf-8", newline="\n")
        print(f"[qa] Markdown 写出: {args.md_out}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"rows": recs}, ensure_ascii=False, indent=1),
            encoding="utf-8", newline="\n")
        print(f"[qa] JSON 写出: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
