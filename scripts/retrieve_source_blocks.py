# -*- coding: utf-8 -*-
"""scripts/retrieve_source_blocks.py —— AutoSeeder 检索层离线构建缓存。

用装有 sentence-transformers 的解释器运行（本机 /e/python/python.exe），
把 kb/协议实现源码 切片 + 7 条通用 query 语义检索 + 后处理，
产出 derived/source_blocks/<protocol>.json，供主流程 build_hub 读取。

用法:
    /e/python/python.exe scripts/retrieve_source_blocks.py --protocol rtsp
    /e/python/python.exe scripts/retrieve_source_blocks.py --protocol rtsp \
        --model microsoft/unixcoder-base-nine
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fused.extraction.source_retrieval import build_cache  # noqa: E402
from core import paths                                          # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="AutoSeeder 检索层离线构建缓存")
    ap.add_argument("--protocol", default="rtsp")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--model", default="all-MiniLM-L6-v2",
                    help="embedding 模型（默认 all-MiniLM-L6-v2，AutoSeeder 原用 "
                         "microsoft/unixcoder-base-nine）")
    args = ap.parse_args()

    src_dir = paths.kb_source_dir(args.protocol, "source")
    if not src_dir.is_dir():
        print(f"!! 源码目录不存在: {src_dir}")
        return 1

    print(f"源码目录: {src_dir}")
    print(f"embedding 模型: {args.model}")
    print("正在切片 + 向量化 + 7 query 检索 ...")
    blocks = build_cache(src_dir, args.protocol, top_k=args.top_k,
                         model_name=args.model)
    print(f"完成：{len(blocks)} 个相关代码块 → "
          f"derived/source_blocks/{args.protocol}.json")
    for i, b in enumerate(blocks, 1):
        files = ", ".join(b.get("files", []))
        print(f"  [{i}] {len(b['text'])} 字符  来源: {files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
