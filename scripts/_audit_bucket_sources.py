# -*- coding: utf-8 -*-
"""逐桶 × 逐 aspect 的来源审计（只读、零 LLM、零写入）。

★ 回答的问题：**RFC 单源实验里，到底哪些知识不是 RFC 源的？**
  逐 (aspect → authority) 统计中枢 facts ⇒ 不靠推断，直接看数据。

★ 背景：中枢声明 `source_set=["rfc"]`，但**协议骨架**（authority=profile）被
  「恒允许」物化进中枢（`rag_seedgen.py:968`），而骨架的 origin 是：
    {"source":  ["message_instance", "target_state"],
     "traffic": ["existence", "method_sequence", "occurrence", "value_enum"]}
  ⇒ 骨架里**含 traffic 源派生的维度** ⇒ 这些也会进 RFC 单源实验。

用法：E:/app/Anaconda3/python.exe scripts/_audit_bucket_sources.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fused.downstream import rag_seedgen as RS        # noqa: E402

#: aspect → 中枢桶名（与 rag_seedgen._BUCKET_BY_KIND 同源，见 _KIND_BY_ASPECT）
_KIND_BY_ASPECT = {
    "state_changing": "methods", "definition": "methods",
    "existence": "methods", "relation_to_other": "required_headers",
    "required_headers": "required_headers", "security_property": "security",
    "precondition": "precondition", "session_header": "session_header",
    "url_template": "url_template", "legal_boundary": "legal_boundary",
    "value_enum": "headers/values", "target_state": "transitions",
    "message_instance": "message_instances",
    "method_sequence": "method_sequences", "occurrence": "occurrence",
}


def main() -> None:
    report: dict = {}
    for protocol in ("rtsp", "sip", "smtp"):
        views = RS.load_fact_views(protocol)
        if not views:
            continue
        cnt: collections.Counter = collections.Counter()
        for v in views:
            asp = (v.get("fact_key") or {}).get("aspect", "")
            bucket = _KIND_BY_ASPECT.get(asp, asp)
            for c in (v.get("all_claims") or []):
                cnt[(bucket, asp, str(c.get("authority") or ""))] += 1
        buckets: dict[str, collections.Counter] = collections.defaultdict(
            collections.Counter)
        for (bucket, asp, auth), n in cnt.items():
            buckets[bucket][auth] += n

        print("=" * 82)
        print(f"协议 {protocol} —— 中枢 facts 的 (桶 ← aspect ← authority) 分布")
        print("=" * 82)
        print(f"  {'桶':<22} {'rfc':>6} {'profile':>8} {'其它':>6}   非RFC占比")
        rows = {}
        for bucket in sorted(buckets):
            c = buckets[bucket]
            rfc_n = c.get("rfc", 0)
            prof_n = c.get("profile", 0)
            other_n = sum(n for a, n in c.items() if a not in ("rfc", "profile"))
            total = sum(c.values())
            nonrfc = (prof_n + other_n) / total if total else 0.0
            flag = " ⚠" if nonrfc > 0 else ""
            print(f"  {bucket:<22} {rfc_n:>6} {prof_n:>8} {other_n:>6}   "
                  f"{nonrfc:>6.1%}{flag}")
            rows[bucket] = {"rfc": rfc_n, "profile": prof_n, "other": other_n,
                            "total": total, "non_rfc_rate": round(nonrfc, 4)}
        report[protocol] = rows
        print()
    p = Path(__file__).resolve().parent / "_audit_bucket_sources.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入 {p}")


if __name__ == "__main__":
    main()
