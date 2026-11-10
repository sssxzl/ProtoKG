# -*- coding: utf-8 -*-
"""guard/verify_consumer_wiring.py —— 批次 1.6 **步 5** 的**分布校验**。

判据（方案 §3.1.10.6 步 5）：
  ① 不带参数**产物逐字节不变**（单源态下过滤是 no-op）；
  ② 单源时**只消费该源**（bundle 的 available_sources ⊆ 声明的源 ∪ 骨架）；
  ③ 消费端**只认中枢**：清单与事实都来自中枢，不碰知识源目录；
  ④ 报告里能打印「本次知识来源清单」。

用法::

    E:/app/Anaconda3/python.exe guard/verify_consumer_wiring.py \
        --protocol rtsp --protocol sip --protocol smtp
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fused.downstream.rag_seedgen import (             # noqa: E402
    SKELETON_AUTHORITY, assemble_bundle, load_fact_views,
    load_source_manifest,
)

#: 消费端**不得**直读知识源目录（D-6：源与消费端互不接触）
CONSUMER_FILES = ("scripts/seedgen.py",
                  "core/fused/downstream/rag_seedgen.py")


def _normalize(obj):
    """稳定化（set → sorted list；tuple key → 字符串 key）。"""
    if isinstance(obj, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)):
                _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_normalize(v) for v in obj)
    return obj


def _dump(obj) -> str:
    return json.dumps(_normalize(obj), ensure_ascii=False, default=str,
                      sort_keys=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 1.6 步 5 分布校验")
    ap.add_argument("--protocol", action="append", default=None)
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True

    # ③ 静态检查：消费端不碰知识源目录
    print("=== ③ 消费端只认中枢（静态检查）===")
    for rel in CONSUMER_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        hits = [n for n in ("kb_root", "kb_source_dir",
                            "kb/" + chr(34), "kb/" + chr(39))
                if n in text]
        ok = not hits
        print(f"  {rel}: {'✅ 不含知识源路径引用' if ok else '❌ 命中 ' + str(hits)}")
        if not ok:
            overall_ok = False

    for protocol in protocols:
        print(f"\n=== {protocol} ===")
        manifest = load_source_manifest(protocol)
        declared = list(manifest.get("source_set") or [])
        views = load_fact_views(protocol)
        if not views:
            print("  中枢为空 —— 跳过")
            continue

        # ① 单源态下过滤是 no-op（产物不变的前提）
        no_filter = assemble_bundle(list(views), protocol)
        with_filter = assemble_bundle(list(views), protocol,
                                      source_set=declared or None)
        noop_ok = _dump(no_filter) == _dump(with_filter)
        print(f"  ① 声明源 {declared}；过滤前后一致（单源态 no-op）"
              f" {'✅' if noop_ok else '❌'}")
        if not noop_ok:
            overall_ok = False

        # ② 只消费该源（+ 骨架）
        avail = set(with_filter.get("available_sources") or [])
        allowed = set(declared) | {SKELETON_AUTHORITY}
        leak = avail - allowed
        print(f"  ② available_sources={sorted(avail)}；"
              f"越界来源={sorted(leak) or '无'} {'✅' if not leak else '❌'}")
        if leak:
            overall_ok = False

        # ④ 清单可打印（含 build_id / built_at ⇒ 可审计）
        print(f"  ④ 本次知识来源清单: {declared}  ← 中枢 sources.json 声明")
        print(f"     build_ids={manifest.get('build_ids')} "
              f"built_at={manifest.get('built_at')}")
        if not declared:
            print("     ⚠ 中枢未声明源集合 ⇒ 消费端按「不过滤」处理")
        # ④' 中枢布局信息（可审计）
        layout = manifest.get("hub_layout") or {}
        if layout:
            print(f"     hub_layout={layout.get('scheme')} "
                  f"aspect_counts={layout.get('aspect_counts')}")

    print("\n结论：" + ("✅ 可采信（步 5 分布校验通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
