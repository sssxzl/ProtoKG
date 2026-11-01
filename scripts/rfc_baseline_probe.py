# -*- coding: utf-8 -*-
"""scripts/rfc_baseline_probe.py —— rfc 抽取器基线测量（A 阶段验收参照）。

用途：在改造前/后测量同一组指标，用同一套口径对比。
只读：不写任何产物，只打印。

用法：
    python scripts/rfc_baseline_probe.py
    python scripts/rfc_baseline_probe.py --protocol sip --protocol rtsp
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths                                     # noqa: E402
from core.fused import rfc_extractor as rx                 # noqa: E402


#: 真实章节标题判定（用于「标题召回率」口径）：
#: 标题形如 `N.N(...) Title`（标题可含多词/空格/括号），且**不是** TOC 行。
def _is_real_heading(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if rx._is_toc_line(s):
        return False
    return bool(rx._RE_ANY_HEADING.match(s))


def probe_protocol(protocol: str) -> dict:
    """测量单协议的 rfc 抽取基线。"""
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    out: dict = {"protocol": protocol, "spec_dir": str(spec_dir)}
    if not spec_dir.is_dir():
        out["error"] = "spec dir missing"
        return out

    files = sorted(spec_dir.glob("*.txt"))
    out["file_count"] = len(files)

    total_lines = 0
    toc_lines = 0
    real_headings = 0
    matched_by_any_section = 0      # _RE_ANY_SECTION（单词正则）命中
    matched_by_status_any = 0
    matched_by_any_heading = 0

    for f in files:
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines += len(lines)
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if rx._is_toc_line(s):
                toc_lines += 1
                continue
            if rx._RE_ANY_HEADING.match(s):
                matched_by_any_heading += 1
                if not _is_real_heading(s):
                    continue
                real_headings += 1
                if rx._RE_ANY_SECTION.match(s):
                    matched_by_any_section += 1
                if rx._RE_STATUS_ANY.match(s):
                    matched_by_status_any += 1

    out["total_lines"] = total_lines
    out["toc_lines"] = toc_lines
    out["real_headings"] = real_headings
    out["matched_any_heading"] = matched_by_any_heading
    out["matched_any_section"] = matched_by_any_section
    out["matched_status_any"] = matched_by_status_any
    out["heading_recall_any_section"] = (
        round(matched_by_any_section / real_headings, 4) if real_headings else None)

    # ---- norm 抽取结果 ----
    norms = rx.extract_rfc_norms(protocol)
    out["norm_count"] = len(norms)
    kinds = Counter(n.get("kind") for n in norms)
    out["norm_kinds"] = dict(kinds)

    # ---- norm_id 重复（同 norm_id 多次出现）----
    id_counter = Counter(n.get("norm_id") for n in norms)
    out["dup_norm_ids"] = {k: v for k, v in id_counter.items() if v > 1}

    # ---- 重复抽取对 fact_id 的影响 ----
    from core.fused.norm import map_norm_to_facts
    from core.fused.canonical import compute_fact_id
    fact_ids = []
    for n in norms:
        for f in map_norm_to_facts(n):
            fact_ids.append(f.fact_id)
    fc = Counter(fact_ids)
    dups = {k: v for k, v in fc.items() if v > 1}
    out["fact_count"] = len(fact_ids)
    out["unique_fact_ids"] = len(fc)
    out["dup_fact_ids"] = len(dups)
    out["dup_fact_id_detail"] = dict(list(dups.items())[:10])

    # ---- TOC 污染检测：outcome norm 的正文是否来自 TOC 行 ----
    #  口径说明（2026-11-01 P1-3 修复后）：norm 的 source 是
    #  `file:<名>#@<行号>`，其中行号**已是 RFC 原文的真实行号**（1-based），
    #  可直接回查原文定位该标题。
    #  但本检查仍用「内容溯源」而非行号回查：行号只能定位**标题所在行**，
    #  而污染的判据是「reason 文本只出现在目录行」——需要比对**全文出现位置**，
    #  内容溯源更直接、且对 ABNF 通道（source 标记为 `@abnf`、无行号）也适用。
    toc_outcome = 0
    body_outcome = 0
    for n in norms:
        if n.get("kind") != "outcome":
            continue
        content = n.get("content", "")
        reason = content.split("|", 1)[0].strip()
        if not reason:
            continue
        found_toc = False
        found_body = False
        for f in files:
            for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = ln.strip()
                if reason not in s:
                    continue
                if rx._is_toc_line(s):
                    found_toc = True
                else:
                    found_body = True
            if found_toc or found_body:
                break
        if found_toc and not found_body:
            toc_outcome += 1
        elif found_body:
            body_outcome += 1
    out["toc_sourced_outcomes"] = toc_outcome
    out["body_sourced_outcomes"] = body_outcome

    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="rfc 抽取器基线测量（**单协议 × 单源**）")
    # ★★ 架构约束（2026-10-31）：本模型一次只处理一个协议 × 一个知识源。
    #    故本脚本默认**必须指定单个 --protocol**；批量测量需显式 --all-protocols。
    ap.add_argument("--protocol", default=None,
                    help="目标协议（**单个**，如 sip）。不传则需加 --all-protocols")
    ap.add_argument("--all-protocols", action="store_true",
                    help="测量 kb/ 下所有有 spec 的协议（**显式批量**，"
                         "仅用于跨协议回归对比）")
    args = ap.parse_args(argv)

    if args.all_protocols:
        protos = sorted(
            p.name for p in paths.kb_root().iterdir()
            if p.is_dir() and (p / "spec").is_dir())
        print(f"[批量模式] 测量 {len(protos)} 个协议: {', '.join(protos)}")
    elif args.protocol:
        protos = [args.protocol]
    else:
        ap.error("必须指定 --protocol <单个协议>，或显式使用 --all-protocols "
                 "（本模型一次只处理一个协议 × 一个知识源）")

    results = []
    for p in protos:
        r = probe_protocol(p)
        results.append(r)
        print(f"\n=== {p} ===")
        for k, v in r.items():
            if k == "protocol":
                continue
            if isinstance(v, dict) and len(v) > 6:
                print(f"  {k}: ({len(v)} 项) {list(v.items())[:6]}")
            else:
                print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
