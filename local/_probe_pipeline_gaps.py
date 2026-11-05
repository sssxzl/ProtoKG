# -*- coding: utf-8 -*-
"""端到端缺口清点（只读、零 LLM、零写入派生文件）。

★ 回答的问题：从 RFC 源 → 结构化知识中枢 → 种子消费，**每个桶实际有多少条、
  每条来自哪个源**？

★ 口径：与 `scripts/seedgen.py` 默认路径完全一致
  · 中枢 `source_set`（`derived/per_source/<协议>/sources.json`）若为 ["rfc"]
    ⇒ `apply_allowed_methods=False`（不按 profile 白名单裁剪）
  · 语义规则**显式打开**（`set_semantic_rules_enabled(True)`）—— 因为 seedgen
    `scripts/seedgen.py:1019` 是无条件 `load_semantic_rules()`，若用模块默认值
    （False）会得到 legal_boundary=0 的**假缺口**。

用法：E:/app/Anaconda3/python.exe local/_probe_pipeline_gaps.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fused.downstream import rag_seedgen as RS   # noqa: E402
from core.fused import llm_ensemble as LE            # noqa: E402

PROTOCOLS = ("rtsp", "sip", "smtp")

# 需要报「条数」的桶（其余桶是 dict/list，统一按 len 报）
BUCKETS = (
    "methods", "headers", "required_headers", "statuses", "transitions",
    "method_sequences", "message_instances", "security", "actors",
    "precondition", "session_header", "url_template", "protocol",
    "legal_boundary", "response_expectation",
)


def hub_source_set(protocol: str) -> list[str]:
    p = Path("derived/per_source") / protocol / "sources.json"
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("source_set") or []
    except (json.JSONDecodeError, OSError):
        return []


def probe(protocol: str) -> dict:
    views = RS.load_fact_views(protocol)
    if not views:
        return {}
    src_set = hub_source_set(protocol) or None
    apply_allowed = (not src_set) or ("source" in {s.lower() for s in src_set})
    bundle = RS.assemble_bundle(
        views, protocol, source_set=src_set,
        apply_allowed_methods=apply_allowed,
        # ★ 与 scripts/seedgen.py 一致：严格单源下不并入骨架的方法存在性
        include_skeleton_methods=apply_allowed)
    by_source = bundle.get("by_source") or {}

    rows = {}
    for name in BUCKETS:
        val = bundle.get(name)
        if name == "legal_boundary" or name == "response_expectation":
            # 语义规则投影桶：值是 dict{bucket_name: [entries]} 或 list
            if isinstance(val, dict):
                n = sum(len(v) for v in val.values() if isinstance(v, list))
            elif isinstance(val, list):
                n = len(val)
            else:
                n = 0
        elif isinstance(val, dict):
            n = len(val)
        elif isinstance(val, (list, tuple, set)):
            n = len(val)
        else:
            n = 0
        rows[name] = {"count": n, "by_source": by_source.get(name) or {}}

    # 方法集差异：RFC 抽到的 vs bundle 里实际留下
    rfc_methods = sorted({
        v.get("subject") for v in views
        if (v.get("aspect") or "") == "methods"
        and (v.get("authority") or "") == "rfc" and v.get("subject")})
    bundle_methods = sorted({str(m) for m in (bundle.get("methods") or {})})
    return {
        "source_set": src_set,
        "apply_allowed_methods": apply_allowed,
        "buckets": rows,
        "bucket_origin": bundle.get("bucket_origin") or {},
        "rfc_methods_only": rfc_methods,
        "bundle_methods": bundle_methods,
        "dropped_by_allowed_methods": sorted(set(rfc_methods) - set(bundle_methods)),
        "transitions_by_source": {
            k: len(v) for k, v in (bundle.get("transitions_by_source") or {}).items()},
        "transitions_total": len(bundle.get("transitions") or []),
        "has_semantic_bucket": "semantic_rules" in bundle,
    }


def main() -> None:
    LE.set_semantic_rules_enabled(True)
    report = {}
    for p in PROTOCOLS:
        report[p] = probe(p)

    hdr = f"{'桶':<24}" + "".join(f"{p:>10}" for p in PROTOCOLS) + "   来源"
    print("=" * 96)
    print("端到端桶填充率（seedgen 默认口径 + 语义规则打开）")
    print("=" * 96)
    print(hdr)
    print("-" * 96)
    for name in BUCKETS:
        cells, srcs = "", set()
        for p in PROTOCOLS:
            r = (report.get(p) or {}).get("buckets", {}).get(name)
            cells += f"{r['count']:>10}" if r else f"{'-':>10}"
            if r:
                srcs |= {k for k, v in (r["by_source"] or {}).items() if v}
        print(f"{name:<24}{cells}   {','.join(sorted(srcs)) or '—'}")

    print()
    for p in PROTOCOLS:
        r = report.get(p) or {}
        print(f"[{p}] source_set={r.get('source_set')} "
              f"apply_allowed_methods={r.get('apply_allowed_methods')} "
              f"semantic_rules键={r.get('has_semantic_bucket')}")
        print(f"  RFC 方法集({len(r.get('rfc_methods_only') or [])}) = "
              f"{r.get('rfc_methods_only')}")
        print(f"  bundle 方法集({len(r.get('bundle_methods') or [])}) = "
              f"{r.get('bundle_methods')}")
        print(f"  被 allowed_methods 裁掉 = {r.get('dropped_by_allowed_methods')}")
        print(f"  transitions 采用 {r.get('transitions_total')} 条，"
              f"各源存量 {r.get('transitions_by_source')}")

    out = Path(__file__).resolve().parent / "_probe_pipeline_gaps.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {out}")


if __name__ == "__main__":
    main()
