# -*- coding: utf-8 -*-
"""guard/verify_provenance.py —— 批次 1.6 **步 3** 的**分布校验**。

判据（方案 §3.1.10.6 步 3）：
  ① 旧字段**逐字节等价** —— 剔除步 3 新增的 4 个顶层键后，bundle 与
     「只含旧键的视图」**逐字节一致**（⇒ prompt 不变 ⇒ 种子不变）；
  ② 每桶能**逐条回指**事实 —— ``bucket_fact_ids`` 里每条都能在
     ``fact_index`` 里找到，且能指回 authority；
  ③ 桶级统计自洽 —— ``by_source`` 的计数与实际事实数一致。

用法::

    E:/app/Anaconda3/python.exe guard/verify_provenance.py \
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
    assemble_bundle, load_fact_views, render_seed_prompt,
)

#: 步 3 新增的顶层键
NEW_KEYS = ("by_source", "bucket_fact_ids", "fact_index", "bucket_origin")


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 1.6 步 3 分布校验")
    ap.add_argument("--protocol", action="append", default=None)
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True
    for protocol in protocols:
        views = load_fact_views(protocol)
        if not views:
            print(f"[{protocol}] 中枢为空 —— 跳过")
            overall_ok = False
            continue
        bundle = assemble_bundle(list(views), protocol)

        print(f"\n=== {protocol} ===")
        print(f"  中枢事实数: {len(views)}")

        # ① 新键存在 + 旧字段逐字节等价（剔除新键后 prompt 不变）--------------
        keys_ok = all(k in bundle for k in NEW_KEYS)
        stripped = {k: v for k, v in bundle.items() if k not in NEW_KEYS}
        p_full = render_seed_prompt(bundle, protocol=protocol)
        p_strip = render_seed_prompt(stripped, protocol=protocol)
        prompt_ok = (p_full == p_strip)
        print(f"  ① 新键齐备: {'✅' if keys_ok else '❌'}   "
              f"prompt 逐字节不变（剔除新键后）: {'✅' if prompt_ok else '❌'}")
        if not (keys_ok and prompt_ok):
            overall_ok = False

        # ② 每桶能逐条回指 ---------------------------------------------------
        by_source = bundle.get("by_source") or {}
        bucket_ids = bundle.get("bucket_fact_ids") or {}
        fact_index = bundle.get("fact_index") or {}
        trace_ok = True
        for bucket, ids in bucket_ids.items():
            for fid in ids:
                if fid not in fact_index:
                    trace_ok = False
                    print(f"     ✗ {bucket} 里的 {fid} 无法回指")
                elif not fact_index[fid].get("authority"):
                    trace_ok = False
                    print(f"     ✗ {fid} 缺 authority")
        print(f"  ② 每桶逐条可回指（{sum(len(v) for v in bucket_ids.values())} 条）"
              f" {'✅' if trace_ok else '❌'}")
        if not trace_ok:
            overall_ok = False

        # ③ 桶级统计自洽 ------------------------------------------------------
        count_ok = True
        for bucket, srcs in by_source.items():
            total = sum(srcs.values())
            if total <= 0:
                count_ok = False
                print(f"     ✗ 桶 `{bucket}` 的计数为 0")
            # 桶内事实数 ≤ 该桶在 fact_index 里的条目数
            if len(bucket_ids.get(bucket) or []) > total:
                count_ok = False
                print(f"     ✗ 桶 `{bucket}`：回指条数 > 计数")
        # 计数总和 ≤ 中枢事实总数
        grand = sum(sum(s.values()) for s in by_source.values())
        if grand > len(views):
            count_ok = False
            print(f"     ✗ 计数总和 {grand} > 事实总数 {len(views)}")
        print(f"  ③ 桶级统计自洽（{len(by_source)} 个桶 / 计数总和 {grand}）"
              f" {'✅' if count_ok else '❌'}")
        if not count_ok:
            overall_ok = False

        # 明细：各桶的来源分布
        print("     桶来源分布：")
        for bucket in sorted(by_source):
            print(f"       {bucket:24s} {by_source[bucket]}")

    print("\n结论：" + ("✅ 可采信（步 3 分布校验通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
