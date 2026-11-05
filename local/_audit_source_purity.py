# -*- coding: utf-8 -*-
"""RFC 单源纯净度自证（只读、零 LLM、零写入）。

★ 回答的问题：「消费端实际采用的，是 RFC 源的知识吗？」
  逐桶报告**实际采用**的知识及其来源（authority），并与「全源口径」对照。

★ 口径说明（与 `scripts/seedgen.py` 完全一致）：
  · 中枢声明 `source_set`（`derived/per_source/<协议>/sources.json`）= ["rfc"]
  · ⇒ `_apply_allowed = (not _src_set_l) or ("source" in _src_set_l)` = **False**
  · ⇒ `assemble_bundle(..., source_set=["rfc"], apply_allowed_methods=False)`
    ⇒ **字段实例不迁移**（纯净度优先）、方法白名单不裁剪。

★ 注意：中枢**存着**骨架（profile 源）的 facts（它被「恒允许」物化进中枢），
  但消费端是否采用要逐桶看 —— 本脚本就是把这个差异量化出来。

用法：E:/app/Anaconda3/python.exe local/_audit_source_purity.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fused.downstream import rag_seedgen as RS        # noqa: E402


def hub_source_set(protocol: str) -> list[str]:
    p = Path("derived/per_source") / protocol / "sources.json"
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("source_set") or []
    except (json.JSONDecodeError, OSError):
        return []


def audit(protocol: str, *, single: bool) -> dict:
    views = RS.load_fact_views(protocol)
    if not views:
        return {}
    src_set = hub_source_set(protocol) if single else None
    apply_allowed = (not src_set) or ("source" in {s.lower() for s in src_set})
    b = RS.assemble_bundle(
        views, protocol, source_set=src_set,
        apply_allowed_methods=apply_allowed)

    # adopted transitions 的来源
    by_src = b.get("transitions_by_source") or {}
    adopted = set(tuple(t) for t in b.get("transitions") or [])
    adopted_origin = sorted(
        src for src, rows in by_src.items()
        if adopted & {tuple(r) for r in rows})

    mi = b.get("message_instances") or {}
    ledger = b.get("knowledge_ledger") or {}
    return {
        "source_set": src_set,
        "apply_allowed_methods": apply_allowed,
        "transitions_total": len(adopted),
        "transitions_by_source": {k: len(v) for k, v in by_src.items()},
        "adopted_transitions_origin": adopted_origin,
        "adopted_state_names": sorted({s for f, m, t in adopted for s in (f, t)}),
        "message_instances": len(mi),
        "message_instance_sample": [list(k) for k in list(mi)[:3]],
        "ledger_buckets": len(ledger.get("buckets") or {}),
        "ledger_violations": len(ledger.get("violations") or []),
        "ledger_violation_detail": (ledger.get("violations") or [])[:5],
        "available_sources": sorted(b.get("available_sources") or []),
    }


def main() -> None:
    print("=" * 80)
    print("RFC 单源纯净度自证 —— 消费端实际采用的源")
    print("=" * 80)
    report: dict = {}
    for protocol in ("rtsp", "sip", "smtp"):
        print(f"\n{'=' * 80}\n协议：{protocol}\n{'=' * 80}")
        for tag, single in (("① 单源口径（seedgen 默认路径）", True),
                            ("② 全源口径（对照）", False)):
            r = audit(protocol, single=single)
            if not r:
                print(f"  {tag}: 中枢为空 ⇒ 跳过")
                continue
            print(f"\n  ── {tag}")
            print(f"     source_set={r['source_set']}  "
                  f"apply_allowed_methods={r['apply_allowed_methods']}")
            print(f"     transitions 采用 {r['transitions_total']} 条，来源 = "
                  f"{r['adopted_transitions_origin']}")
            print(f"     各源存量: {r['transitions_by_source']}")
            print(f"     采用的状态名: {r['adopted_state_names']}")
            print(f"     message_instances 桶: {r['message_instances']} 条"
                  + (f"  样例 {r['message_instance_sample']}"
                     if r["message_instance_sample"] else ""))
            print(f"     知识台账: {r['ledger_buckets']} 桶 / "
                  f"违规 {r['ledger_violations']} 条")
            if r["ledger_violation_detail"]:
                for v in r["ledger_violation_detail"]:
                    print(f"        · {v}")
            report.setdefault(protocol, {})[tag] = r
    p = Path(__file__).resolve().parent / "_audit_source_purity.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
