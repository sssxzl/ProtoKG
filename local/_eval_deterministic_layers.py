# -*- coding: utf-8 -*-
"""状态机择一 · 种子质量的最终量化（纯确定性、零 LLM 成本）。

★ 为什么必须单独量化：`kept`（校验后种子数）是**自证循环**（校验器用的就是
  被测对象自己的状态机）⇒ 不可作为质量判据。
  而 ChataFL 里 **RTSP 无预定义状态机**（aflnet `extract_requests_rtsp` 的
  region 里 `state_sequence = NULL`）⇒ 种子的 `target_state_path` 不直接
  影响 fuzzing 行为 ⇒ 真正决定种子价值的是**方法序列是否合法**。

★ 判据（外部真值 = RFC 2326 A.1+A.2 共 14 条边）：
  方法序列合法 ⇔ 相邻方法对在真值里构成一条合法转移（状态推进合法）。
  例：SETUP→PLAY→PAUSE 合法；DESCRIBE→DESCRIBE→GET_PARAMETER→PAUSE 非法
      （RTSP 里 DESCRIBE 不改变会话状态 ⇒ 该序列在真实服务器上会被 405）。

★ 对比两组（只差 `bundle["transitions"]`）：
  组 A = 协议骨架那 38 条（SIP 式状态名，RFC 原文命中 0/6）
  组 B = RFC 原生那 14 条（状态名 4/4 命中）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fused.downstream import rag_seedgen as RS        # noqa: E402
from core.fused.downstream.edge_cover import edge_cover    # noqa: E402
from core.fused.downstream import generic_danger as GD     # noqa: E402

#: RFC 2326 A.1（客户端）+ A.2（服务端）状态转移真值（14 条，逐行核对原文）
TRUTH: set[tuple[str, str, str]] = {
    ("Init", "SETUP", "Ready"), ("Init", "TEARDOWN", "Init"),
    ("Ready", "PLAY", "Playing"), ("Ready", "RECORD", "Recording"),
    ("Ready", "TEARDOWN", "Init"), ("Ready", "SETUP", "Ready"),
    ("Playing", "PAUSE", "Ready"), ("Playing", "TEARDOWN", "Init"),
    ("Playing", "PLAY", "Playing"), ("Playing", "SETUP", "Playing"),
    ("Recording", "PAUSE", "Ready"), ("Recording", "TEARDOWN", "Init"),
    ("Recording", "RECORD", "Recording"), ("Recording", "SETUP", "Recording"),
}
#: 真值里**能改变状态**的方法（RTSP 里只有这 5 个）
STATE_CHANGING = {m for _, m, _ in TRUTH}
#: 真值里允许的「方法 → 方法」相邻对（由 from 态与该态的出边方法推导）
LEGAL_NEXT: dict[str, set[str]] = {}
for _f, _m, _t in TRUTH:
    LEGAL_NEXT.setdefault(_f, set()).add(_m)


def judge_method_seq(methods: list[str]) -> tuple[bool, str]:
    """方法序列是否在 RFC A.1/A.2 的「next state」规则下合法。

    判定（按 RFC 2326 A.1/A.2 的状态推进）：
      · 游标从 **Init** 出发；
      · **状态改变方法**（SETUP/PLAY/PAUSE/RECORD/TEARDOWN）⇒ 必须存在
        (cur, m, next) ∈ 真值 ⇒ 否则非法（例：未 SETUP 就 PLAY）；
      · **状态无关方法**（DESCRIBE/OPTIONS/GET_PARAMETER/SET_PARAMETER）
        ⇒ 不推进状态，**允许出现在会话未建立时**（RFC 允许 OPTIONS/DESCRIBE
        做会话探测）⇒ 不判非法。
    ★ 注意：这比「所有方法都得是状态改变方法」**更贴近真实 RTSP 语义** ——
      合法 RTSP 会话可以是 DESCRIBE → SETUP → PLAY → TEARDOWN。
    """
    if not methods:
        return False, "空序列"
    cur = "Init"
    for i, m in enumerate(methods):
        if m not in STATE_CHANGING:
            continue                      # 状态无关方法：不推进、不判非法
        cands = [t for f, mm, t in TRUTH if f == cur and mm == m]
        if not cands:
            return False, f"状态 {cur} 下不允许 {m}"
        cur = next((t for t in cands if t == cur), cands[0])
    return True, "合法"


def main() -> None:
    views = RS.load_fact_views("rtsp")
    base = RS.assemble_bundle(views, "rtsp", apply_allowed_methods=False)
    by_src = base.get("transitions_by_source") or {}
    skel = sorted(set(by_src.get("profile") or []))
    rfc = sorted(set(by_src.get("rfc") or []))
    mi_all = base.get("message_instances") or {}

    groups = {"A_骨架38(SIP式状态名)": skel, "B_RFC14(原生状态名)": rfc}
    out: dict = {}
    print("=" * 78)
    print("确定性层种子质量量化（真值 = RFC 2326 A.1+A.2 共 14 条边）")
    print("=" * 78)
    for name, trans in groups.items():
        b = dict(base)
        b["transitions"] = list(trans)
        mi = RS._align_message_instances(trans, mi_all, allow_migrate=True)
        ec = edge_cover(trans, b.get("required_headers"), b.get("methods"),
                        message_instances=mi, protocol="rtsp")
        gd = GD.generic_danger(
            trans, b.get("headers"), b.get("required_headers"),
            precondition=b.get("precondition"),
            session_header=b.get("session_header"),
            message_instances=mi, protocol="rtsp")
        seeds = list(ec) + list(gd or [])
        legal = 0
        illegal_reasons: dict[str, int] = {}
        for s in seeds:
            ms = [str(m.method).strip().upper() for m in s.messages
                  if getattr(m, "method", "")]
            ok, why = judge_method_seq(ms)
            if ok:
                legal += 1
            else:
                illegal_reasons[why] = illegal_reasons.get(why, 0) + 1
        total = len(seeds)
        out[name] = {
            "edge_cover": len(ec), "generic_danger": len(gd or []),
            "total": total, "legal": legal,
            "legal_rate": round(legal / total, 4) if total else 0.0,
            "illegal_reasons": dict(sorted(illegal_reasons.items(),
                                            key=lambda kv: -kv[1])[:6]),
        }
        print(f"\n── {name}")
        print(f"   确定性层种子总数 : {total}  (edge_cover {len(ec)} + generic_danger {len(gd or [])})")
        print(f"   方法序列合法     : {legal}/{total} = {legal / total:.1%}" if total else "   无")
        for why, n in list(out[name]["illegal_reasons"].items())[:5]:
            print(f"      非法原因 {why}: {n} 条")
    (Path(__file__).resolve().parent / "_eval_deterministic_layers.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
