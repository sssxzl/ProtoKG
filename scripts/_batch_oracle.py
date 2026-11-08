#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量 dry-run 重放 oracle：对一个目录下所有 .raw 逐一判定合法/非法。

用法:
    python3 batch_oracle.py <dir> <port> [retries] [--manifest M] [--out TSV]
                            [--summary JSON] [--watchdog SEC]

输出:
    每行 "文件名\\tLEGAL/ILLEGAL/ERROR"（兼容旧版纯文本格式），
    指定 --out 时额外写 TSV（含分层/分数/预期/重试次数/备注）。

机制（对齐技术方案 §4.2）:
  · **串行**执行 —— 并发会让多个 ASAN 服务器互相污染（端口 + 媒体文件 fd + ASAN 全局状态）
  · 每条种子用**独立端口**（port 递增），与 fuzzing 容器的 8560 天然隔离
  · 3 次重试，LEGAL 早退（排除概率性 UAF 抖动）
  · 整批墙钟**看门狗**（默认 30 min/组），超时未跑的条目标为 ERROR
    （note=watchdog_timeout），**不静默跳过**
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# 复用 oracle 模块（同目录优先，其次 VM 上的 /tmp）
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/tmp")
try:
    import oracle as O  # noqa: E402
except ImportError:  # pragma: no cover - 仅在 oracle.py 缺失时触发
    print("!! 找不到 oracle 模块（需与本文件同目录或 /tmp/oracle.py）",
          file=sys.stderr)
    sys.exit(2)

#: 单组墙钟看门狗（秒）；超时未跑的条目记 ERROR
DEFAULT_WATCHDOG = 1800


def _load_manifest(path):
    """读 manifest.json → {文件名: 条目}；文件不存在返回空字典。"""
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {s.get("filename", ""): s for s in data.get("seeds", [])}


def main():
    ap = argparse.ArgumentParser(description="批量 dry-run 重放 oracle")
    ap.add_argument("dir", help="种子目录")
    ap.add_argument("port", type=int, help="起始端口（每条种子递增）")
    ap.add_argument("retries", type=int, nargs="?", default=3,
                    help="每条种子的重试次数（默认 3）")
    ap.add_argument("--manifest", default=None, help="manifest.json 路径")
    ap.add_argument("--out", default=None, help="TSV 输出路径")
    ap.add_argument("--summary", default=None, help="JSON 汇总输出路径")
    ap.add_argument("--watchdog", type=int, default=DEFAULT_WATCHDOG,
                    help=f"整批墙钟看门狗秒数（默认 {DEFAULT_WATCHDOG}）")
    ap.add_argument("--group", default="", help="组名（写进 summary）")
    args = ap.parse_args()

    seed_dir = Path(args.dir)
    if not seed_dir.is_dir():
        print(f"!! 目录不存在: {seed_dir}", file=sys.stderr)
        sys.exit(2)

    manifest = _load_manifest(args.manifest)
    files = sorted(p for p in seed_dir.iterdir()
                   if p.is_file() and p.suffix == ".raw")

    rows = []
    n_legal = n_illegal = n_error = 0
    port = args.port
    t0 = time.time()
    watchdog_hit = False

    for f in files:
        # 看门狗：超时后剩余条目一律记 ERROR（不静默跳过）
        if time.time() - t0 > args.watchdog:
            watchdog_hit = True
            entry = manifest.get(f.name, {})
            rows.append({
                "filename": f.name,
                "layer": entry.get("layer", "NA"),
                "score": entry.get("score", "NA"),
                "legal_illegal_expected": entry.get("legal_illegal", "NA"),
                "verdict": "ERROR",
                "retries_used": 0,
                "note": "watchdog_timeout",
            })
            n_error += 1
            continue
        # 每个种子用一个独立端口，避免服务器残留冲突
        v = O.oracle(str(f), port, args.retries)
        used_port = port
        port += 1
        entry = manifest.get(f.name, {})
        note = ""
        if v == "ERROR":
            note = "server_not_ready"
        rows.append({
            "filename": f.name,
            "layer": entry.get("layer", "NA"),
            "score": entry.get("score", "NA"),
            "legal_illegal_expected": entry.get("legal_illegal", "NA"),
            "verdict": v,
            "retries_used": args.retries if v == "ILLEGAL" else 1,
            "note": note,
        })
        if v == "LEGAL":
            n_legal += 1
        elif v == "ILLEGAL":
            n_illegal += 1
        else:
            n_error += 1
        # 兼容旧版：纯文本行
        print(f"{f.name}\t{v}", flush=True)

    # ---- TSV 输出（固定表头） ----
    if args.out:
        header = ["filename", "layer", "score", "legal_illegal_expected",
                  "verdict", "retries_used", "note"]
        lines = ["\t".join(header)]
        for r in rows:
            lines.append("\t".join(str(r.get(h, "NA")) for h in header))
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_p.with_suffix(out_p.suffix + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(out_p)

    # ---- JSON 汇总 ----
    n_seeds = len(files)
    denom = n_seeds - n_error
    rv = (100.0 * n_legal / denom) if denom > 0 else None
    if args.summary:
        summary = {
            "group": args.group,
            "n_seeds": n_seeds,
            "n_legal": n_legal,
            "n_illegal": n_illegal,
            "n_error": n_error,
            "rv_primary": round(rv, 2) if rv is not None else None,
            "rv_formula": "100 * n_legal / (n_seeds - n_error)",
            "wall_clock_sec": round(time.time() - t0, 1),
            "port_range": f"{args.port}-{port - 1}",
            "watchdog_sec": args.watchdog,
            "watchdog_hit": watchdog_hit,
            "oracle_version": "_oracle.py",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        sp = Path(args.summary)
        sp.parent.mkdir(parents=True, exist_ok=True)
        tmp = sp.with_suffix(sp.suffix + ".tmp")
        tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(sp)

    print(f"== 组 {args.group or '-'}：{n_seeds} 条，"
          f"LEGAL={n_legal} ILLEGAL={n_illegal} ERROR={n_error}，"
          f"Rv={rv if rv is not None else 'NA'}%", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
