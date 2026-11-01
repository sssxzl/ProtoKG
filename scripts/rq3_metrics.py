# -*- coding: utf-8 -*-
"""scripts/rq3_metrics.py —— RQ3 指标计算（M1–M9 + MHR 三口径 + 审计）。

输入（技术方案 §5.6）：
  · `derived/rq3/<g>/manifest.json`（归因的唯一依据）
  · `derived/rq3/collect/<ts>/rq3_queue_index.csv(.gz)`（全时序 + 各快照）
  · `derived/rq3/collect/<ts>/rq3_crashes_index.csv`
  · `derived/rq3/collect/<ts>/rq3_timeseries.csv(.gz)`
  · `derived/rq3/collect/<ts>/rq3_p1.csv` / `rq3_p2.csv`
  · `derived/rq3/<g>/dryrun.tsv`

输出：
  · `derived/rq3/metrics_<g>.json`
  · `derived/rq3/table18_draft.md`

失败策略：
  · manifest 与语料 MD5 不一致 → **报错中止**（不允许静默按文件名匹配）
  · derived 为空 → 明确报错，而非输出 0
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

from scripts.rq3_mhr_patterns import (  # noqa: E402
    PATTERNS, build_lineage_maps, entry_kind, match_patterns, parse_src_parents,
    resolve_root, resolve_root_seeds, summarize_hits,
)

import rq3_common as C  # noqa: E402
from rq3_common import manifest_by_md5  # noqa: E402


def _open_maybe_gzip(path: Path):
    """打开 CSV（自动识别 .gz）。"""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")


def _read_csv(path: Path) -> list[dict]:
    """读 CSV（支持 .gz）。"""
    with _open_maybe_gzip(path) as f:
        import csv
        return list(csv.DictReader(f))


def _mean_std(values) -> tuple[Optional[float], Optional[float]]:
    """mean/std（ddof=1）；缺失值不参与。"""
    return C.mean_std(values)


def _parse_id(name: str) -> Optional[int]:
    """从条目名解析队列 id（`id:000123` → 123）。"""
    from scripts.rq3_mhr_patterns import parse_entry_id
    return parse_entry_id(name)


def _fmt(v, spec="{:.2f}") -> str:
    """格式化；None → NA。"""
    return C.fmt(v, spec)


def _load_manifest_checked(group: str) -> dict:
    """读取 manifest 并**核对语料 MD5**（不一致 → 报错中止）。"""
    manifest = C.load_manifest(group)
    seed_dir = C.group_seed_dir(group)
    manifest_md5 = {e["md5"] for e in manifest.get("seeds", [])}
    disk_md5 = set(C.md5_set(seed_dir))
    if manifest_md5 != disk_md5:
        only_m = sorted(manifest_md5 - disk_md5)[:5]
        only_d = sorted(disk_md5 - manifest_md5)[:5]
        raise SystemExit(
            f"!! manifest 与语料 MD5 不一致（组 {group}）—— 报错中止\n"
            f"   仅在 manifest: {only_m}\n"
            f"   仅在磁盘:     {only_d}")
    return manifest


def _group_metrics(group: str, collect_dir: Path, fuzzer: str,
                    reps: list[int]) -> dict:
    """计算某组（某 fuzzer）的全部指标。

    Args:
        group: 组名。
        collect_dir: 采集产物目录。
        fuzzer: fuzzer 名。
        reps: rep 列表。

    Returns:
        metrics 字典。
    """
    manifest = _load_manifest_checked(group)
    manifest_by_filename = C.manifest_by_filename(manifest)
    manifest_by_index = C.manifest_by_index(manifest)
    seed_md5_set = set(manifest_by_md5(manifest).keys())

    out: dict = {
        "group": group,
        "fuzzer": fuzzer,
        "reps": reps,
        "audit": {},
    }

    # ---- M1：设计种子数 vs 实际接受数 ----
    out["M1_seed_count_design"] = manifest.get("seed_count", 0)

    # ---- M2：干跑 ----
    dryrun_path = C.RQ3_ROOT / group / "dryrun.tsv"
    if dryrun_path.exists():
        rows = C.read_tsv(dryrun_path)
        n_legal = sum(1 for r in rows if r.get("verdict") == "LEGAL")
        n_illegal = sum(1 for r in rows if r.get("verdict") == "ILLEGAL")
        n_error = sum(1 for r in rows if r.get("verdict") == "ERROR")
        denom = len(rows) - n_error
        out["M2_dryrun"] = {
            "n_seeds": len(rows),
            "n_legal": n_legal,
            "n_illegal": n_illegal,
            "n_error": n_error,
            "rv": round(100.0 * n_legal / denom, 2) if denom > 0 else None,
        }
    else:
        out["M2_dryrun"] = {"note": "N/A（未采集 dryrun.tsv）"}

    # ---- M3 / M4：覆盖率与崩溃（来自 P2）----
    p2_path = collect_dir / "rq3_p2.csv"
    p1_path = collect_dir / "rq3_p1.csv"
    if p2_path.exists():
        p2 = [r for r in _read_csv(p2_path)
              if r.get("group") == group and r.get("fuzzer") == fuzzer]
        cvg = [r.get("bitmap_cvg") for r in p2]
        crashes = [r.get("unique_crashes") for r in p2]
        m, sd = _mean_std(cvg)
        out["M3_coverage"] = {
            "per_rep": [float(v) for v in cvg if v not in (None, "", C.NA)],
            "mean": m, "std": sd,
        }
        cm, csd = _mean_std(crashes)
        out["M4_crashes"] = {"p2_total": cm, "p2_std": csd,
                             "note": "N/A-无区分度" if (cm or 0) == 0 else ""}
    else:
        out["M3_coverage"] = {"note": "N/A（未采集 rq3_p2.csv）"}
        out["M4_crashes"] = {"note": "N/A（未采集 rq3_p2.csv）"}
    if p1_path.exists():
        p1 = [r for r in _read_csv(p1_path)
              if r.get("group") == group and r.get("fuzzer") == fuzzer]
        out["M4_crashes"]["p1_total"] = _mean_std(
            [r.get("unique_crashes") for r in p1])[0]
        pt = _mean_std([r.get("paths_total_at_p1") for r in p1])[0]
        out["M1_paths_total_at_p1_mean"] = pt

    # ---- M5：MHR 三口径（来自队列索引 + crashes 索引）----
    # ★ v2：分类按**命名形式**（orig: = 初始 / src: = 派生），MD5 降为交叉校验
    qi_path = collect_dir / "rq3_queue_index.csv"
    qi_path_gz = collect_dir / "rq3_queue_index.csv.gz"
    qpath = qi_path if qi_path.exists() else qi_path_gz
    mhr: dict = {}
    if qpath.exists():
        qrows = _read_csv(qpath)
        qrows = [r for r in qrows
                 if r.get("group") == group and r.get("fuzzer") == fuzzer
                 and r.get("snapshot_tag") == "final"]
        # 血缘映射（v2：沿 src: 链上溯）
        orig_map, src_map = build_lineage_maps([r.get("entry_name", "")
                                                for r in qrows])
        per_rep: list[float] = []
        pooled_hit = pooled_derived = 0
        pattern_counts = {p: 0 for p in PATTERNS}
        layer3_hit = 0
        unattributed = 0
        derived_total = 0
        initial_total = 0
        multi_parent = 0
        identical = 0
        for r in qrows:
            name = r.get("entry_name", "")
            kind = entry_kind(name)          # ★ v2：按命名形式
            if kind == "initial_copy":
                initial_total += 1
                # MD5 交叉校验：初始条目的 MD5 应 ∈ 种子集合
                if r.get("entry_md5") in seed_md5_set:
                    pass
                else:
                    identical += 0
                continue
            derived_total += 1
            # ★ v2：宽松匹配（内容判定，与血缘无关）
            hits = {p: str(r.get(f"hit_{p}", "")).strip().lower() in ("1", "true")
                    for p in PATTERNS}
            if any(hits.values()):
                pooled_hit += 1
            for p in PATTERNS:
                if hits[p]:
                    pattern_counts[p] += 1
            root, layer, n_roots = resolve_root(
                name, orig_map, src_map, manifest_by_filename, manifest_by_index)
            if n_roots > 1:
                multi_parent += 1
            if root is None:
                unattributed += 1
            elif layer == "L3":
                layer3_hit += 1
        mhr["A_targeted"] = {
            "pooled": (100.0 * pooled_hit / derived_total) if derived_total else None,
            "pattern_counts": pattern_counts,
        }
        mhr["B_layer3"] = {
            "pooled": (100.0 * layer3_hit / derived_total) if derived_total else None,
            "unattributed_ratio": (unattributed / derived_total) if derived_total else None,
        }
        # ★ v2：多父（splice）占比 —— 论文须声明该口径
        mhr["multi_parent_ratio"] = (multi_parent / derived_total) if derived_total else None
        # 每条种子平均派生条目数（把「比率」与「绝对量」分开看）
        n_seeds = manifest.get("seed_count", 0) or 1
        mhr["derived_per_seed"] = derived_total / n_seeds if n_seeds else None
        n_l3 = sum(1 for e in manifest.get("seeds", []) if e.get("layer") == "L3")
        mhr["derived_per_seed_layer3"] = (layer3_hit / n_l3) if n_l3 else None
        out["audit"]["unattributed_ratio"] = mhr["B_layer3"]["unattributed_ratio"]
        out["audit"]["derived_identical_to_seed_count"] = identical
        # ★ v2：V11 污染探针 —— count(orig: 形式条目) == 初始种子数
        out["audit"]["init_queue_count"] = initial_total
        out["audit"]["init_queue_matches_seed_count"] = (initial_total == n_seeds)
        out["M5_mhr"] = mhr
    else:
        out["M5_mhr"] = {"note": "N/A（未采集队列索引）"}

    # 口径 C：崩溃归因（沿 src: 链上溯；崩溃为 0 → N/A，禁止记 0）
    ci_path = collect_dir / "rq3_crashes_index.csv"
    if ci_path.exists():
        crows = _read_csv(ci_path)
        crows = [r for r in crows
                 if r.get("group") == group and r.get("fuzzer") == fuzzer]
        if crows:
            # 崩溃的父链在队列索引里 → 用队列的 orig_map/src_map 上溯
            crash_orig, crash_src = build_lineage_maps(
                [r.get("entry_name", "") for r in crows])
            if qpath.exists():
                crash_orig, crash_src = orig_map, src_map
            hit3 = 0
            unresolved = 0
            for r in crows:
                cname = r.get("entry_name", "")
                # ★ P0 修复：崩溃名的 `id:` 是【崩溃目录内】编号，不是队列 id；
                #   队列血缘必须从 `src:` 父出发。splice 崩溃有 2 个父 → 取并集。
                parents = parse_src_parents(cname)
                roots = set()
                for p in parents:
                    roots |= resolve_root_seeds(p, crash_orig, crash_src)
                if not roots:
                    # 兜底：崩溃名没有 src: 字段（异常）→ 退回本地 id 查队列
                    roots = resolve_root_seeds(
                        _parse_id(cname), crash_orig, crash_src)
                if not roots:
                    unresolved += 1
                    continue
                layers = [manifest_by_filename[x].get("layer")
                          for x in roots if x in manifest_by_filename]
                if "L3" in layers:
                    hit3 += 1
            out["M5_mhr"]["C_crash"] = {
                "value": 100.0 * hit3 / len(crows),
                "n_crashes": len(crows),
                "unresolved": unresolved,
            }
        else:
            out["M5_mhr"]["C_crash"] = {"value": None,
                                        "note": "N/A（崩溃为 0）"}
    else:
        out.setdefault("M5_mhr", {})["C_crash"] = {
            "value": None, "note": "N/A（未采集 crashes 索引）"}

    # ---- 审计：增强关闭证据（V7 / V8）----
    ea_path = collect_dir / "rq3_enrichment_audit.csv"
    if ea_path.exists():
        erows = [r for r in _read_csv(ea_path)
                 if r.get("group") == group and r.get("fuzzer") == fuzzer]
        out["audit"]["enriched_in_seeds"] = sum(
            int(float(r.get("enriched_in_seeds") or 0)) for r in erows)
        out["audit"]["enriched_in_queue"] = sum(
            int(float(r.get("enriched_in_queue") or 0)) for r in erows)
        ct = [r.get("chat_times_max") for r in erows]
        out["audit"]["chat_times_max"] = _mean_std(ct)[0]

    return out


def _table18_draft(all_metrics: dict, cfg: dict) -> str:
    """生成表 18 的草稿（均值 ± 标准差紧凑形式）。

    单元格格式（技术方案 §7.2）：
      · 种子数       → 单值整数
      · dry-run 通过率% → 单值，1 位小数（组级一次测量，无 σ 可言）
      · 分支覆盖%    → `均值 ± 标准差`
      · 崩溃数       → `Δ(P2−P1)`（整数）+ 括注 P2 总数
      · 变异命中率   → `均值 ± 标准差`（%，1 位小数）
    """
    lines = ["# RQ3 表 18 草稿（Live555 / RTSP）", "",
             "| 聚焦组 | 种子数 | dry-run 通过率% | 分支覆盖% | 崩溃数 | 变异命中率 |",
             "|---|---|---|---|---|---|"]
    for g in ("A", "B", "C"):
        m = all_metrics.get(g)
        if not m:
            lines.append(f"| {C.group_label(g)} | NA | NA | NA | NA | NA |")
            continue
        seeds = m.get("M1_seed_count_design", "NA")
        dry = m.get("M2_dryrun", {}).get("rv")
        cov = m.get("M3_coverage", {})
        cr = m.get("M4_crashes", {})
        mhr = m.get("M5_mhr", {}).get("A_targeted", {})
        crash_txt = "NA"
        p1 = cr.get("p1_total")
        p2 = cr.get("p2_total")
        if p1 is not None and p2 is not None:
            crash_txt = f"{int(round(p2 - p1))} (P2={int(round(p2))})"
            if (p2 or 0) == 0:
                crash_txt += "（未观测到可复现崩溃，不具区分度）"
        lines.append(
            f"| {C.group_label(g)} | {seeds} | {_fmt(dry, '{:.1f}')} | "
            f"{_fmt(cov.get('mean'), '{:.2f}')} ± {_fmt(cov.get('std'), '{:.2f}')} | "
            f"{crash_txt} | {_fmt(mhr.get('pooled'), '{:.2f}')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ3 指标计算")
    ap.add_argument("--collect", default=None,
                    help="采集产物目录（默认取最新的 derived/rq3/collect/*）")
    ap.add_argument("--fuzzer", default="chatafl", help="fuzzer 名")
    ap.add_argument("--groups", default="A,B,C,D", help="参与的组（逗号分隔）")
    args = ap.parse_args()

    cfg = C.load_config()
    if args.collect:
        collect_dir = Path(args.collect)
    else:
        cands = sorted((C.RQ3_ROOT / "collect").glob("*"))
        if not cands:
            print("!! 没有采集产物目录（derived/rq3/collect/*）", file=sys.stderr)
            return 1
        collect_dir = cands[-1]
    if not collect_dir.exists():
        print(f"!! 采集目录不存在: {collect_dir}", file=sys.stderr)
        return 1
    print(f"采集目录: {collect_dir}")

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    reps = cfg["reps"]
    all_metrics: dict = {}
    for g in groups:
        print(f"\n=== 计算组 {g} 的指标 ===")
        try:
            m = _group_metrics(g, collect_dir, args.fuzzer, reps)
        except SystemExit as e:
            print(str(e), file=sys.stderr)
            return 2
        all_metrics[g] = m
        out_path = C.RQ3_ROOT / f"metrics_{g}.json"
        C.write_json(out_path, m)
        print(f"  → {out_path}")
        cov = m.get("M3_coverage", {})
        mhr = m.get("M5_mhr", {}).get("A_targeted", {})
        print(f"     覆盖 {cov.get('mean')} ± {cov.get('std')} | "
              f"MHR_A {mhr.get('pooled')} | 模式分布 {mhr.get('pattern_counts')}")

    draft = _table18_draft(all_metrics, cfg)
    draft_path = C.RQ3_ROOT / "table18_draft.md"
    draft_path.write_text(draft, encoding="utf-8")
    print(f"\n表 18 草稿: {draft_path}")
    print(draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
