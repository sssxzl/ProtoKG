# -*- coding: utf-8 -*-
"""纯净度修复方案 · 只读模拟（零 LLM 成本、零写入）。

★ 背景（三条实测结论汇合）：
  ① source_autoseeder 的状态锚点提示词硬塞 **SIP 式状态名范例**；
  ② 实测三版提示词（硬编码 / 宁缺勿滥 / 来源约束）在 RTSP 上的
     **RFC 原文命中率分别 20% / 0%（产出崩塌）/ 24%** ⇒ **改提示词无效**；
  ③ live555 RTSP 实现源码里**零个规范会话状态名** ⇒ 源码逆向本质产不出
     规范状态机。
  ⇒ 结论：**骨架的 `target_state` 维度本质是低质量知识**（origin 实为 source 源）
    ⇒ 在 **RFC 单源实验**里应当排除（纯净度修复，命中论文核心主张）。

★ 本脚本模拟：在「RFC 单源」口径下，把骨架的 `target_state` 事实排除后，
  各协议的确定性层种子数与质量会怎样。

★ 关键约束：**sip/smtp 目前没有 RFC 源状态机**
  （sip 的 `enable_transitions` 未开、smtp 的 RFC 无 state machine 表述）
  ⇒ 排除骨架 target_state 会让它们的 transitions **变空** ⇒ 必须先量化。

用法：E:/app/Anaconda3/python.exe local/_sim_purity_skeleton.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402
from core.fused.downstream.edge_cover import edge_cover    # noqa: E402
from core.fused.downstream.generic_danger import generic_danger  # noqa: E402
from core.fused.rfc_extractor import infer_transitions    # noqa: E402


def drop_skeleton_state(views: list[dict]) -> list[dict]:
    """剔除骨架（authority=profile）的 target_state 事实。"""
    out = []
    for v in views:
        fk = v.get("fact_key") or {}
        if fk.get("aspect") != "target_state":
            out.append(v)
            continue
        claims = [c for c in (v.get("all_claims") or [])
                  if str(c.get("authority") or "").strip().lower() != "profile"]
        if not claims:
            continue
        nv = dict(v)
        nv["all_claims"] = claims
        out.append(nv)
    return out


def layers(bundle: dict, protocol: str) -> dict:
    tr = bundle.get("transitions") or []
    mi = bundle.get("message_instances") or {}
    ec = edge_cover(tr, bundle.get("required_headers"), bundle.get("headers"),
                    mi, protocol=protocol)
    gd = generic_danger(tr, bundle.get("headers"), bundle.get("required_headers"),
                        precondition=bundle.get("precondition"),
                        session_header=bundle.get("session_header"),
                        message_instances=mi, protocol=protocol)
    return {"transitions": len(tr),
            "states": sorted({s for f, m, t in tr for s in (f, t)}),
            "edge_cover": len(ec), "generic_danger": len(gd),
            "total": len(ec) + len(gd)}


def main() -> None:
    print("=" * 78)
    print("纯净度修复模拟：RFC 单源口径下排除骨架 target_state")
    print("=" * 78)
    report: dict = {}
    for protocol in ("rtsp", "sip", "smtp"):
        views = RS.load_fact_views(protocol)
        if not views:
            print(f"\n★ {protocol}: 中枢为空 ⇒ 跳过")
            continue
        # 口径 A：现状（骨架恒允许）
        a = RS.assemble_bundle(views, protocol, source_set=["rfc"],
                               apply_allowed_methods=False)
        # 口径 B：排除骨架 target_state
        views_b = drop_skeleton_state(views)
        b = RS.assemble_bundle(views_b, protocol, source_set=["rfc"],
                               apply_allowed_methods=False)
        # RFC 源能不能补上？
        rfc_rows = infer_transitions(protocol)
        la, lb = layers(a, protocol), layers(b, protocol)
        print(f"\n── {protocol}")
        print(f"   A 现状      : transitions {la['transitions']:>3} 条  "
              f"状态 {la['states']}")
        print(f"                确定性层 {la['total']:>3} 条 "
              f"(edge_cover {la['edge_cover']} + generic_danger {la['generic_danger']})")
        print(f"   B 排除骨架后: transitions {lb['transitions']:>3} 条  "
              f"状态 {lb['states']}")
        print(f"                确定性层 {lb['total']:>3} 条 "
              f"(edge_cover {lb['edge_cover']} + generic_danger {lb['generic_danger']})")
        print(f"   ⇒ RFC 源可抽 {len(rfc_rows)} 条"
              + (f"  状态名 {sorted({x for r in rfc_rows for x in (r['from'], r['to'])})}"
                 if rfc_rows else "  （该协议无 RFC 状态机 ⇒ 排除后为空）"))
        report[protocol] = {"A": la, "B": lb, "rfc_rows": len(rfc_rows)}
    p = Path(__file__).resolve().parent / "_sim_purity_skeleton.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
