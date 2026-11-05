# -*- coding: utf-8 -*-
"""「语义规则 present 算子 → required_headers 桶」投影可行性（零 LLM、只读）。

★ 动机（来自桶级来源审计）：
  `required_headers` 桶 **100% 来自骨架**（rtsp 8 条 / sip 14 条）⇒ RFC 单源实验里
  这一维不是 RFC 源的。而 RFC 源的**语义规则里已经有 `present` 算子**，且带
  `evidence.section_path`（能定位到方法章节，如 ["Method Definitions","SETUP"]）
  ⇒ 可能是「**已有答案没接线**」，而不是能力缺口。

★ 本脚本：
  ① 把语义规则里 `operator=="present"` 且 `target_field` 是已知头的规则挑出来；
  ② 按 `section_path` 里出现的**方法名**绑定到方法 ⇒ 投影出「方法 → 必填头」；
  ③ 与骨架版 `profile.json:seedgen.required_headers` 逐方法对照覆盖率。

★ 注意：`present` 规则有的是**消息级**而非方法级（如 "所有请求 MUST 含 Via"）
  ⇒ 这类只能进「全局必填头」，本脚本单独统计。

用法：E:/app/Anaconda3/python.exe local/_probe_present_to_required.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402


def known_headers(protocol: str) -> set[str]:
    views = RS.load_fact_views(protocol)
    if not views:
        return set()
    b = RS.assemble_bundle(views, protocol)
    return {h.upper() for h in (b.get("headers") or {})}


def main() -> None:
    for protocol in ("rtsp", "sip"):
        print("=" * 78)
        print(f"协议 {protocol}")
        print("=" * 78)
        rf = Path("derived/per_source") / protocol / "rfc" / "semantic" / "rules.jsonl"
        if not rf.is_file():
            print("  无语义规则库 ⇒ 跳过")
            continue
        known = known_headers(protocol)
        profile = json.loads(
            paths.target_profile(protocol).read_text(encoding="utf-8"))
        skel = ((profile.get("seedgen") or {}).get("required_headers") or {})

        # 协议方法集
        views = RS.load_fact_views(protocol)
        b = RS.assemble_bundle(views, protocol)
        methods = set(b.get("methods") or {})

        per_method: dict[str, set[str]] = {}
        global_h: set[str] = set()
        unmatched: list[str] = []
        for ln in rf.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            r = r.get("rule") or r
            c = r.get("constraint") or {}
            if c.get("operator") != "present":
                continue
            field = str(c.get("target_field") or "").strip()
            if not field or field.upper() not in known:
                continue
            sp = (r.get("evidence") or {}).get("section_path") or []
            hit = [m for m in methods if m.upper() in {str(x).upper() for x in sp}]
            if hit:
                for m in hit:
                    per_method.setdefault(m, set()).add(field)
            else:
                unmatched.append(field)
                global_h.add(field)

        print(f"  骨架版 required_headers（100% 非 RFC 源）:")
        for m, hs in sorted(skel.items()):
            print(f"     {m:<16} {sorted(hs)}")
        print(f"\n  RFC 语义规则 present 投影（按 section_path 绑方法）:")
        for m, hs in sorted(per_method.items()):
            print(f"     {m:<16} {sorted(hs)}")
        print(f"\n  消息级（无法绑方法）: {sorted(global_h)}")
        print(f"  丢弃（target_field 不在已知头集）: {sorted(set(unmatched) - global_h)}")

        # 覆盖率对照
        skel_pairs = {(m, h) for m, hs in skel.items() for h in hs}
        proj_pairs = {(m, h) for m, hs in per_method.items() for h in hs}
        print(f"\n  ▸ 骨架「方法-必填头」对: {len(skel_pairs)}")
        print(f"  ▸ RFC 投影「方法-必填头」对: {len(proj_pairs)}")
        print(f"  ▸ 两者交集: {len(skel_pairs & proj_pairs)}")
        print(f"  ▸ 投影覆盖骨架的比例: "
              f"{len(skel_pairs & proj_pairs) / len(skel_pairs):.1%}" if skel_pairs else "  n/a")
        print()


if __name__ == "__main__":
    main()
