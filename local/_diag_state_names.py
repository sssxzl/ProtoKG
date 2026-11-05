# -*- coding: utf-8 -*-
"""状态名正确性诊断（零成本、零 LLM、只读）。

★ 动因：「性能优先」原则下，重新评估 RFC 源状态机（通道 G）的真实价值。
  先前判断「RTSP 服务端状态机 A.2 是散文、表格抽不到 ⇒ 只有客户端那 12 条边」
  **已被证伪**（A.2 也是定宽表格，且边集与 A.1 **完全相同** ⇒ 抽了也无增量）。
  ⇒ 真正要问的是：**当前消费端采用的 38 条骨架状态机，其状态名对 RTSP 是否正确？**

本脚本回答：
  Q1 骨架状态名 / RFC 状态名，各自是否出现在该协议 RFC 原文中？
  Q2 渲染进 prompt 的状态机知识里，有多少条是「RFC 里查无此状态」的？
  Q3 若改用 RFC 源那套（RTSP 原生状态名），状态机覆盖与 prompt 差异如何？
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402


def rfc_text(protocol: str) -> str:
    d = paths.kb_source_dir(protocol, "rfc")
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted(d.glob("*.txt")))


def main() -> None:
    for protocol in ("rtsp", "sip", "smtp"):
        print("=" * 74)
        print(f"协议：{protocol}")
        print("=" * 74)
        views = RS.load_fact_views(protocol)
        if not views:
            print("  中枢为空 ⇒ 跳过")
            continue
        bundle = RS.assemble_bundle(views, protocol)
        by_src = bundle.get("transitions_by_source") or {}
        text = rfc_text(protocol)

        for src, rows in sorted(by_src.items()):
            states = sorted({r[0] for r in rows} | {r[2] for r in rows})
            hit = [s for s in states if s in text]
            miss = [s for s in states if s not in text]
            print(f"\n  ── 来源 {src}：{len(rows)} 条边 / {len(states)} 个状态名")
            print(f"     RFC 原文中出现 : {len(hit)}/{len(states)}  {hit}")
            print(f"     RFC 原文中查无 : {len(miss)}/{len(states)}  {miss}")

        # ---- Q2：prompt 里实际渲染了什么 ----
        prompt_src = RS._render_transitions(bundle["transitions"])
        n_line = len([ln for ln in prompt_src.splitlines() if ln.strip()])
        print(f"\n  ── prompt 渲染的状态机条目数 : {n_line}")
        # 渲染里的状态名有多少在 RFC 原文中查无
        rendered_states = sorted({s for s in states})
        miss_in_prompt = [s for s in rendered_states if s not in text]
        print(f"     其中 RFC 原文查无此状态 : {len(miss_in_prompt)}/{len(rendered_states)}"
              f"  {miss_in_prompt}")
        print()
    return


if __name__ == "__main__":
    main()
