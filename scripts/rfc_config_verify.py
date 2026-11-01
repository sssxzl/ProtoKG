# -*- coding: utf-8 -*-
"""scripts/rfc_config_verify.py —— 校验 rfc_config.json 的章节号是否真实存在于 RFC 原文。

不是格式校验，是**内容校验**：把 rfc_config.json 里声明的每个章节号，
回到 kb/<protocol>/spec/*.txt 里找对应标题行，报告「命中/未命中」。

只读脚本，不写任何产物。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths                                   # noqa: E402

#: 宽松标题正则：N.N(...) 任意标题
_RE_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+(.+?)\s*$")
#: 一级标题：两种形态都算
#:   ① `N.  Title`（带点，如 `10.  Protocol`）
#:   ② `N Title`（无点，如 RTSP 的 `5 General Header Fields`）
_RE_TOP_HEADING = re.compile(r"^(\d{1,2})\.?\s+(\S.*?)\s*$")


def load_headings(protocol: str) -> dict[str, list[str]]:
    """收集该协议所有 RFC 里出现的章节号 → [标题, ...]（含一级标题）。"""
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    found: dict[str, list[str]] = {}
    if not spec_dir.is_dir():
        return found
    for f in sorted(spec_dir.glob("*.txt")):
        for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = ln.strip()
            if not s or re.search(r"\.{3,}", s):
                continue          # TOC 行不算
            m = _RE_HEADING.match(s)
            if m:
                found.setdefault(m.group(1), []).append(m.group(2))
                continue
            m = _RE_TOP_HEADING.match(s)
            if m:
                found.setdefault(m.group(1), []).append(m.group(2))
    return found


def _match_section(section: str, headings: dict[str, list[str]]) -> list[str]:
    """按**前缀语义**匹配章节号。

    RFC 的一级章节（如 `10.`、`19.`）通常**没有独立标题行**——其下直接是
    `10.1 OPTIONS` / `19.1 ...`。所以配置里写 `10` 表示「§10 及其所有子节」，
    必须按前缀匹配，不能要求 `10` 本身作为一个标题行存在。

    匹配规则：`sec` 命中 `h` 当且仅当 `h == sec` 或 `h.startswith(sec + ".")`。
    （用 `sec + "."` 而非裸 startswith，避免 `1` 误配 `10`/`11`/`12`。）
    """
    if section in headings:
        return [section]
    prefix = section + "."
    return sorted(h for h in headings if h.startswith(prefix))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="校验 rfc_config.json 章节号真实性（**单协议 × 单源**）")
    # ★★ 架构约束（2026-10-31）：本模型一次只处理一个协议 × 一个知识源。
    #    默认**必须指定单个 --protocol**；批量校验需显式 --all-protocols。
    ap.add_argument("--protocol", default=None,
                    help="目标协议（**单个**，如 sip）。不传则需加 --all-protocols")
    ap.add_argument("--all-protocols", action="store_true",
                    help="校验 kb/ 下所有有 spec 的协议（**显式批量**，"
                         "仅用于跨协议一致性回归）")
    args = ap.parse_args(argv)

    if args.all_protocols:
        protos = sorted(
            p.name for p in paths.kb_root().iterdir()
            if p.is_dir() and (p / "spec").is_dir())
        print(f"[批量模式] 校验 {len(protos)} 个协议: {', '.join(protos)}")
    elif args.protocol:
        protos = [args.protocol]
    else:
        ap.error("必须指定 --protocol <单个协议>，或显式使用 --all-protocols "
                 "（本模型一次只处理一个协议 × 一个知识源）")

    total_ok = total_bad = 0
    for proto in protos:
        cfg_path = paths.target_rfc_config(proto)
        if not cfg_path.exists():
            print(f"\n=== {proto} === 无 rfc_config.json")
            continue
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        headings = load_headings(proto)
        print(f"\n=== {proto} === (RFC 中共 {len(headings)} 个章节号)")
        for key in ("method_sections", "field_sections", "status_sections"):
            secs = cfg.get(key) or []
            ok, bad = [], []
            for sec in secs:
                hits = _match_section(sec, headings)
                if hits:
                    ok.append(sec)
                else:
                    bad.append(sec)
            total_ok += len(ok)
            total_bad += len(bad)
            flag = "OK " if not bad else "!! "
            print(f"  {flag}{key}: {len(ok)}/{len(secs)} 命中")
            if ok:
                print(f"       命中: {ok}")
            if bad:
                print(f"       未命中: {bad}")
                # 给出最接近的候选，辅助判断是笔误还是确实不存在
                for b in bad:
                    cands = [h for h in headings
                             if h.startswith(b) or b.startswith(h)][:6]
                    if cands:
                        print(f"         {b} 近似候选: {cands}")

    print(f"\n=== 总计: 命中 {total_ok} / 未命中 {total_bad} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
