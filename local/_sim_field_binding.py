#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读模拟：量化「C6 字段绑定」修复对 E1 可执行规则数的真实上限。

★ **零写盘、零 LLM 调用、零仓库改动** —— 复用 B-10 实验的**真实代码路径**
  （``run_group_two_layer``），只把 ``known_fields`` / 字段别名换掉再数一遍规则。

★ 三组对照：
  甲（现状）   = 当前 ``known_field_set(协议)``，无别名表
  乙（补真头） = 甲 ∪ {LLM 给出且确属协议真字段者}
  丙（乙+别名）= 乙 ∪ {别名表命中项}

★ 自检：甲组算出的规则数必须等于 ``group_E1/rules.jsonl`` 的实际条数
  —— 不等则模拟不可信，直接报错退出。

用法：
    E:/app/Anaconda3/python.exe local/_sim_field_binding.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.fused.rfc_extractor import known_field_set  # noqa: E402
from core.fused.semantic_rules import bind_field  # noqa: E402

import scripts.exp_semantic_gain as esg  # noqa: E402

PROTOCOLS = ("rtsp", "sip", "smtp")
FROZEN = REPO_ROOT / "derived/exp_semantic/candidates_frozen.jsonl"
C0_ITEMS = REPO_ROOT / "derived/exp_semantic_gain/group_C0/items.jsonl"
E1_RULES = REPO_ROOT / "derived/exp_semantic_gain/group_E1/rules.jsonl"

#: 字段别名表（LLM 常见表述 → 协议真字段名）。
#: ★ 只收「确定是同一个字段」的映射，不做模糊猜测。
#: ★ 目标字段必须**确实在**该协议的 known_fields 里，否则不映射。
FIELD_ALIASES: dict[str, dict[str, str]] = {
    "rtsp": {
        "session identifier": "Session",
        "session-id": "Session",
        "url host": "Host",
        "status-code": "Status-Line",
    },
    "sip": {
        "route set": "Route",
        "parameter-name": "Parameter-Name",
    },
    "smtp": {},
}

#: LLM 实际给出、但**确实属于协议真字段**却不在 known_fields 里的字段。
#: ★ 依据：RFC 3261 §7.1.1（Request-Line 用 SIP-Version）、§8.1.1.1（Request-URI）、
#:   §18（Transport）—— 而 sip 的 field_sections 只覆盖 §7.3/§19/§20。
EXTRA_REAL_FIELDS: dict[str, set[str]] = {
    "rtsp": set(),
    "sip": {"SIP-Version", "Request-URI", "Transport"},
    "smtp": set(),
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")


#: 阶段 B 的「LLM 已启用」哨兵。
#: ★ `run_group_two_layer` 只用 ``llm is not None`` 判断是否走阶段 B；
#:   LLM 响应本体来自 ``llm_facts`` 字典 ⇒ **不需要真实客户端、不产生 API 调用**。
#: ★ 传 ``None`` 会让阶段 B 整条关闭 ⇒ 规则数必然对不上基线（自检会拦住）。
_LLM_SENTINEL = object()


def run_arm(label: str, fields_by_proto: dict[str, set[str]],
            apply_alias: bool) -> dict:
    """跑一组对照，返回各协议规则数与明细。"""
    esg._KNOWN_FIELDS.clear()
    for p, fs in fields_by_proto.items():
        esg._KNOWN_FIELDS[p] = tuple(sorted(fs))

    frozen = [json.loads(l) for l in
              FROZEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    llm_facts: dict[str, dict] = {}
    for l in C0_ITEMS.read_text(encoding="utf-8").splitlines():
        if l.strip():
            row = json.loads(l)
            llm_facts[row["candidate_id"]] = row

    # ── 别名表：把 LLM 给的字段名改写成协议真字段名 ──────────────────
    if apply_alias:
        for row in llm_facts.values():
            proto = row.get("protocol") or ""
            raw = (row.get("field") or "").strip()
            if not raw:
                continue
            fields = fields_by_proto.get(proto, set())
            if bind_field(raw, fields):
                continue                       # 已能绑定 ⇒ 不动
            target = FIELD_ALIASES.get(proto, {}).get(_norm(raw))
            if target and target in fields:
                row["field"] = target

    out: dict[str, dict] = {}
    for proto in PROTOCOLS:
        cands = [c for c in frozen if c.get("protocol") == proto]
        res = esg.run_group_two_layer(
            proto, cands, llm=_LLM_SENTINEL,
            known_fields=sorted(fields_by_proto[proto]),
            llm_facts=llm_facts, use_sanitize=True,
        )
        by_reason: dict[str, int] = {}
        for it in res["items"]:
            r = it.get("reject_reason") or ""
            if r:
                by_reason[r] = by_reason.get(r, 0) + 1
        out[proto] = {"rules": len(res["rules"]), "rejects": by_reason}
    out["_total"] = sum(out[p]["rules"] for p in PROTOCOLS)
    print(f"\n=== {label} ===")
    for p in PROTOCOLS:
        print(f"  {p:5s} 规则={out[p]['rules']:3d}  拒绝={out[p]['rejects']}")
    print(f"  TOTAL 规则 = {out['_total']}")
    return out


def main() -> int:
    base = {p: set(known_field_set(p)) for p in PROTOCOLS}
    actual = len([l for l in E1_RULES.read_text(
        encoding="utf-8").splitlines() if l.strip()])
    print(f"基准：group_E1/rules.jsonl 实际规则数 = {actual}")

    # ── 甲组：现状（自检）────────────────────────────────────────────
    arm_a = run_arm("甲（现状：无补字段、无别名）", base, apply_alias=False)
    if arm_a["_total"] != actual:
        print(f"\n✘ 自检失败：甲组算得 {arm_a['_total']} ≠ 实际 {actual}"
              f" ⇒ 模拟不可信，退出。")
        return 2
    print(f"  ✓ 自检通过：甲组 = 实际 {actual} 条")

    # ── 乙组：补真头字段 ────────────────────────────────────────────
    extended = {p: set(fs) | EXTRA_REAL_FIELDS.get(p, set())
                for p, fs in base.items()}
    arm_b = run_arm("乙（补协议真头字段）", extended, apply_alias=False)

    # ── 丙组：乙 + 别名表 ───────────────────────────────────────────
    arm_c = run_arm("丙（补真头字段 + 别名表）", extended, apply_alias=True)

    print("\n=== 结论（E1 可执行规则数，分母 120）===")
    for name, arm in (("甲 现状", arm_a), ("乙 补真头", arm_b),
                      ("丙 乙+别名", arm_c)):
        d = arm["_total"] - arm_a["_total"]
        print(f"  {name:12s} {arm['_total']:3d} 条  "
              f"({arm['_total'] / 120 * 100:6.2f}%)  Δ={d:+d}")
    print(f"\n  当前 E1−C0 = -4.1666 pp（C0 = 22/120 = 18.3333%）")
    print(f"  修 C6 后 E1−C0 = "
          f"{(arm_c['_total'] - 22) / 120 * 100:+.4f} pp")
    print(f"  门槛：+15 pp 成立 / +5 pp 部分成立 / <+5 pp 不成立")

    print("\n=== 拒绝原因变化（甲 → 丙）===")
    for p in PROTOCOLS:
        a, b = arm_a[p]["rejects"], arm_c[p]["rejects"]
        keys = sorted(set(a) | set(b))
        if not keys:
            continue
        print(f"  -- {p} --")
        for k in keys:
            print(f"     {k:22s} {a.get(k, 0):3d} → {b.get(k, 0):3d} "
                  f"({b.get(k, 0) - a.get(k, 0):+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
