# -*- coding: utf-8 -*-
"""tools/qa/verify_source_filter.py —— 批次 1.6 **步 2** 的**分布校验**。

判据（方案 §3.1.10.6 步 2）：
  ① 单源 bundle 的 ``available_sources`` **只含该源**（``profile`` 骨架单独标注）；
  ② 桶内容**逐条可追到源**（每条事实都能指回 fact_id / authority）；
  ③ 过滤**恰好**隔离掉被排除源的贡献 —— 用「只用允许源的事实组装」的结果
     与「过滤后」的结果**逐字节比对**（相等 ⇒ 过滤不多不少；不可解释差异 = 0）。

用法::

    E:/app/Anaconda3/python.exe tools/qa/verify_source_filter.py \
        --protocol rtsp --protocol sip --protocol smtp

本脚本**只读**真实中枢；「多源场景」通过**给真实事实重新贴 authority 标签**
在内存里合成（不落盘、不污染中枢）⇒ 可重复跑。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths                                      # noqa: E402
from core.fused.downstream.rag_seedgen import (             # noqa: E402
    SKELETON_AUTHORITY, assemble_bundle, load_fact_views,
)

#: 合成的「外来源」标签（用来在内存里造一个多源场景）
FOREIGN_AUTHORITIES = ("vuln", "traffic", "expert_note")


def _relabel(views: list[dict], authority: str) -> list[dict]:
    """把一批事实的 authority 改标成另一个源（内存里，不落盘）。"""
    out = []
    for v in views:
        v2 = json.loads(json.dumps(v, ensure_ascii=False))
        for c in v2.get("all_claims") or []:
            c["authority"] = authority
        out.append(v2)
    return out


def _normalize(obj):
    if isinstance(obj, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)):
                _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_normalize(v) for v in obj)
    return obj


def _dump(obj) -> str:
    """序列化（**保留 dict 插入序**）⇒ 可逐字节比较。"""
    return json.dumps(_normalize(obj), ensure_ascii=False, default=str)


def _kept_views(views: list[dict], source_set: list[str]) -> list[dict]:
    """按「claim 的 authority ∈ 允许集」筛出应保留的事实（= 过滤的语义定义）。"""
    allowed = {str(s).strip().lower() for s in source_set if str(s).strip()}
    allowed.add(SKELETON_AUTHORITY)
    kept = []
    for v in views:
        claims = v.get("all_claims") or []
        if any(str(c.get("authority") or "").strip().lower() in allowed
               for c in claims):
            kept.append(v)
    return kept


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 1.6 步 2 分布校验")
    ap.add_argument("--protocol", action="append", default=None)
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True
    for protocol in protocols:
        manifest = paths.per_source_root(protocol) / "sources.json"
        if not manifest.is_file():
            print(f"[{protocol}] 无 sources.json —— 跳过")
            overall_ok = False
            continue
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        source_set = list(doc.get("source_set") or [])
        views = load_fact_views(protocol)
        if not views:
            print(f"[{protocol}] 中枢为空 —— 跳过")
            overall_ok = False
            continue

        print(f"\n=== {protocol} ===")
        print(f"  本次源集合（sources.json.source_set）: {source_set}")
        print(f"  中枢事实数: {len(views)}")

        # ---- 场景 A：**真实中枢**（已清空 ⇒ 过滤应当是 no-op）-----------------
        unfiltered = assemble_bundle(list(views), protocol)
        filtered = assemble_bundle(list(views), protocol, source_set=source_set)
        noop_ok = _dump(unfiltered) == _dump(filtered)
        print(f"  A 真实中枢：过滤前后一致（清空已保证单源 ⇒ 过滤是 no-op）"
              f" {'✅' if noop_ok else '❌'}")
        if not noop_ok:
            overall_ok = False

        # ---- 场景 B：**合成多源**（重新贴标签）⇒ 验证过滤真的有效 -------------
        foreign_views: list[dict] = []
        for i, auth in enumerate(FOREIGN_AUTHORITIES):
            foreign_views.extend(
                _relabel(views[i::len(FOREIGN_AUTHORITIES)], auth))
        multi_views = list(views) + foreign_views
        multi_unfiltered = assemble_bundle(list(multi_views), protocol)
        multi_filtered = assemble_bundle(list(multi_views), protocol,
                                         source_set=source_set)
        has_effect = _dump(multi_unfiltered) != _dump(multi_filtered)
        avail = sorted(multi_filtered.get("available_sources") or [])
        leaked = [a for a in avail if a in FOREIGN_AUTHORITIES]
        print(f"  B 合成多源：过滤前后有差异 {'✅' if has_effect else '❌'}"
              f"（多源事实 {len(foreign_views)} 条被隔离）")
        print(f"    过滤后 available_sources = {avail}")
        print(f"    外来源泄漏 = {leaked or '无'} "
              f"{'✅' if not leaked else '❌'}")
        if not has_effect or leaked:
            overall_ok = False

        # ---- 判据 ③：过滤**恰好**隔离掉被排除源（逐字节等价证明）--------------
        kept = _kept_views(multi_views, source_set)
        expected = assemble_bundle(list(kept), protocol)
        exact_ok = _dump(expected) == _dump(multi_filtered)
        print(f"  ③ 过滤精确性：与「只用允许源组装」逐字节一致 "
              f"{'✅' if exact_ok else '❌'}"
              f"（保留 {len(kept)} / {len(multi_views)} 条事实）")
        if not exact_ok:
            overall_ok = False

        # ---- 判据 ②：桶内容逐条可追到源 --------------------------------------
        trace_ok = True
        for v in kept:
            for c in v.get("all_claims") or []:
                if not c.get("fact_id") or not c.get("authority"):
                    trace_ok = False
        print(f"  ② 桶内容可追源（fact_id + authority 齐备）"
              f" {'✅' if trace_ok else '❌'}")
        if not trace_ok:
            overall_ok = False

    print("\n结论：" + ("✅ 可采信（步 2 分布校验通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
