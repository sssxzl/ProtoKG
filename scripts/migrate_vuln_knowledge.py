# -*- coding: utf-8 -*-
"""scripts/migrate_vuln_knowledge.py —— 跨协议漏洞知识迁移入口（Phase 3 接线，GLMFuzz 式）。

多协议低成本迁移护城河：新协议（无漏洞库）不必从零积累漏洞知识，而是用自然语言描述
目标协议的危险点（如「重复建立会话」「超长字段」「认证缺失」），从**其他有漏洞库的协议**
检索相似漏洞模式，得到可迁移的边界建议（action + boundary 维度 + 来源协议）。

用法::

    python scripts/migrate_vuln_knowledge.py --query "重复建立会话 / 同 track 双 SETUP"
    python scripts/migrate_vuln_knowledge.py --query "超长字段溢出" --protocols rtsp smtp --top-k 3

注意：迁移的是「漏洞模式结构」（action / boundary 维度），不搬具体协议字段值；
目标协议用自己的 profile（方法名/字段）实例化边界种子。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fused.vuln_vector import (  # noqa: E402
    migrate_vuln_patterns, protocols_with_vuln_kb, build_vuln_pattern_vectors,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="跨协议漏洞知识迁移（GLMFuzz 式漏洞模式向量库检索）")
    ap.add_argument("--query", required=True,
                    help="目标协议危险点的自然语言描述（如「重复建立会话」「超长字段」）")
    ap.add_argument("--protocols", nargs="*", default=None,
                    help="迁移来源协议（默认所有有漏洞库的协议）")
    ap.add_argument("--top-k", type=int, default=5, help="返回 top-k 相似漏洞模式")
    args = ap.parse_args()

    sources = args.protocols or protocols_with_vuln_kb()
    if not sources:
        print("!! 无可用迁移来源协议（kb/ 下无任何「历史漏洞」目录）")
        return 1
    print(f"迁移来源协议: {sources}")
    print(f"查询: {args.query}\n")

    results = migrate_vuln_patterns(args.query, sources, top_k_per=args.top_k)
    if not results:
        print("（未检索到相似漏洞模式）")
        return 0

    print(f"检索到 {len(results)} 条可迁移漏洞模式：\n")
    for i, (score, p) in enumerate(results, 1):
        boundary = p.get("boundary") or {}
        illegal = boundary.get("illegal", "") if isinstance(boundary, dict) else ""
        print(f"[{i}] score={score:.3f}  来源协议={p.get('_protocol')}")
        print(f"    action={p.get('action')}  触发序列={p.get('trigger_sequence')}")
        print(f"    触发字段={p.get('trigger_field') or '(无)'}")
        if illegal:
            print(f"    非法域(触发点)={illegal}")
        print(f"    变异提示={p.get('mutation_hint', '')[:120]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
