# -*- coding: utf-8 -*-
"""tools/qa/_m1_sensitivity.py —— M1 可执行率的**同等严格度敏感性分析**（可复现脚本）。

★ 为什么需要这个脚本（2026-11-07）：
  M1 的**主口径**存在**两把尺子不一样**的问题：

    · C0（基线）的 `field` 是从**自由文本**反推的（`probe_source:"legal"`），
      没有 `validated` 字段、也不做证据校验；
    · E1（结构化方案）要求**字段绑定 + 证据可验证 + 显式性纯净**。

  ⇒ 两者严格度**不等价**，直接相减得到的「E1 − C0」不能干净归因给「表达层升级」。

  ★ 之前这些数字只存在于一次**临时口径审计**里（未固化成脚本）⇒ 不可复现、
    写进论文会被要求给出敏感性分析。本脚本把该审计固化为**可复现**的产物。

★ 三档口径（本脚本逐档给出，并标明每档的可归因性）：

  | 口径 | C0 判据 | E1 判据 | 归因边界 |
  |---|---|---|---|
  | **主口径** | `decidable`（能解析出算子） | 规则数 | ⚠ **不对称** —— E1 更严 |
  | **带操作数** | 可执行（**存在类算子免操作数**） | 规则数 | ⚠ **不对称**，但差距缩小 |
  | **同等严格度** | `decidable_with_operand` | 只算**绑定字段 + 可验证证据**的规则 | ✅ 两边都要求「有操作数 + 有依据」 |

★ 不臆造：人工标注上界（26.7% = 32/120）来自 `docs/annotation_status.md`
  的**实际标注结果**，本脚本只**引用**不改写；M2 的 F1 / Cohen's κ
  **不可计算**（标注集未完成、缺第二名标注者）⇒ 明确标注为「不可计算」。

用法::

    E:/app/Anaconda3/python.exe tools/qa/_m1_sensitivity.py
    # ⇒ 打印表格 + 写入 derived/exp_semantic_gain/m1_sensitivity.json
"""
from __future__ import annotations

import collections
import io
import json
import os
import sys
from pathlib import Path

# ★ 2026-11-08：移到 tools/qa/ ⇒ 层级 +1 ⇒ parents[2] 才是项目根
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EXP_DIR = ROOT / "derived" / "exp_semantic_gain"
PROTOCOLS = ("rtsp", "sip", "smtp")

#: 预登记阈值（`docs/semantic_gain_report.md` §4.6 / `docs/rfc_source_bcd_roadmap.md` §4.5）
PREREG = {"成立": 15.0, "部分成立": 5.0}

#: 人工标注实测的可执行率**上界**（`docs/annotation_status.md` §2.4）
#: —— 120 条候选里人工判定可执行的只有 32 条 ⇒ 任何口径下 E1 都不应显著超过它
ANNOTATION_UPPER_BOUND = {"total": 32, "denominator": 120, "pct": 26.6667}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


#: **存在类算子** —— 语义是「字段必须存在 / 不得出现」，**没有值域** ⇒
#:   天然不需要操作数。把它们排除在「带操作数」口径外会**系统性低估 C0**。
#:   （实测：C0 可判定但无 operand 的 17 条**全部**是 present/absent。）
PRESENCE_OPERATORS = frozenset({"present", "absent"})


def _pct(num: int, den: int) -> float:
    return round(num * 100.0 / den, 4) if den else 0.0


def _c0_executable(c0_item: dict) -> bool:
    """C0 侧「可执行」的**同等严格度**判据。

    ★ 修正（2026-11-07）：原口径直接用 ``decidable_with_operand``，
      那是「抓到操作数」的口径 ⇒ 把**存在类算子**（present/absent，语义上
      本就没有值域）的 17 条全排除了 ⇒ C0 被系统性低估 ⇒
      「带操作数」口径下 E1−C0 变成 +10.83pp，与主口径 −3.33pp **方向相反**
      （那是口径假象，不是真实收益）。
      ⇒ 修正为：**存在类算子也算可执行**（它同样是一条可执行的约束），
        非存在类算子才要求抓到操作数。
    """
    if not c0_item.get("decidable"):
        return False
    op = str(c0_item.get("operator") or "")
    if op in PRESENCE_OPERATORS:
        return True
    return bool(c0_item.get("operand"))


def _verdict(delta_pp: float) -> str:
    """按预登记阈值给档位（不新建口径）。"""
    if delta_pp >= PREREG["成立"]:
        return "成立"
    if delta_pp >= PREREG["部分成立"]:
        return "部分成立"
    return "不成立"


def load_c0() -> list[dict]:
    return _read_jsonl(EXP_DIR / "group_C0" / "items.jsonl")


def load_e1() -> list[dict]:
    return _read_jsonl(EXP_DIR / "group_E1" / "items.jsonl")


def load_e2() -> list[dict]:
    return _read_jsonl(EXP_DIR / "group_E2" / "items.jsonl")


def _e1_strict_rules(items: list[dict]) -> list[dict]:
    """E1 的**同等严格度**子集：绑定字段 + 证据可验证 + （非存在类算子时）有操作数。

    ★ 与 C0 的 `_c0_executable()` 口径**逐条对齐** —— 两边都要求
      「是一条能落地的约束」+「有依据」：
        · 存在类算子（present/absent）：两边都不要求操作数（语义上没有值域）；
        · 非存在类算子（eq/ne/ge/…）：两边都要求抓到操作数。
    """
    out = []
    for it in items:
        if not it.get("outcome"):
            continue                      # outcome 非空 ⇒ 这条成了规则
        if it.get("reject_reason"):
            continue                      # 被拒的候选不算
        if not it.get("target_field"):
            continue                      # 字段未绑定 ⇒ 不算「可执行」
        op = str(it.get("operator") or "")
        if op not in PRESENCE_OPERATORS and not it.get("operand"):
            continue                      # 非存在类却无操作数 ⇒ 不可比
        if not it.get("validated"):
            continue                      # 证据不可验证 ⇒ 不算
        out.append(it)
    return out


def main() -> int:
    c0 = load_c0()
    e1 = load_e1()
    e2 = load_e2()
    if not c0 or not e1:
        print("★ 缺实验产物（C0/E1 items.jsonl）⇒ 无法计算", file=sys.stderr)
        return 2

    n_candidates = len(c0)
    result: dict = {
        "prereg": {
            "source": "docs/semantic_gain_report.md §4.6",
            "threshold_pp": PREREG,
        },
        "denominator": {"candidates": n_candidates,
                        "note": "三组共用同一批冻结候选句（candidates_frozen.jsonl）"},
        "annotation_upper_bound": dict(ANNOTATION_UPPER_BOUND,
                                       source="docs/annotation_status.md §2.4"),
        "m2": {
            "computable": False,
            "reason": "人工标注集未完成、缺第二名真人标注者 ⇒ "
                      "F1 与 Cohen's κ 不可计算（不得臆造）",
        },
        "by_protocol": {},
    }

    print("=" * 78)
    print("M1 同等严格度敏感性分析（口径审计固化版，2026-11-07）")
    print("=" * 78)
    print(f"分母（冻结候选句）：{n_candidates} 条，三组共用\n")

    # ---- 主口径 ----
    print("-" * 78)
    print("【主口径】C0 可判定（含存在类算子） vs E1 规则数")
    print("-" * 78)
    print(f"{'协议':6s} {'C0':>12s} {'E1':>12s} {'E1−C0':>10s} {'档位':>8s}")
    main_tot = {"c0": 0, "e1": 0, "e2": 0}
    for p in PROTOCOLS:
        c0_p = [i for i in c0 if i.get("protocol") == p]
        e1_p = [i for i in e1 if i.get("protocol") == p]
        e2_p = [i for i in e2 if i.get("protocol") == p]
        n_p = len(c0_p) or 1
        c0_dec = sum(1 for i in c0_p if i.get("decidable"))
        e1_rules = sum(1 for i in e1_p if i.get("outcome") and not i.get("reject_reason"))
        e2_rules = sum(1 for i in e2_p if i.get("outcome") and not i.get("reject_reason"))
        c0_rate = _pct(c0_dec, n_p)
        e1_rate = _pct(e1_rules, n_p)
        delta = round(e1_rate - c0_rate, 4)
        verdict = _verdict(delta)
        main_tot["c0"] += c0_dec
        main_tot["e1"] += e1_rules
        main_tot["e2"] += e2_rules
        print(f"{p:6s} {c0_dec:3d}/{n_p:<3d}{c0_rate:5.1f}% "
              f"{e1_rules:3d}/{n_p:<3d}{e1_rate:5.1f}% {delta:+8.2f}pp {verdict:>8s}")
        result["by_protocol"].setdefault(p, {})["main"] = {
            "candidates": len(c0_p), "c0_decidable": c0_dec,
            "c0_rate_pct": c0_rate, "e1_rules": e1_rules, "e1_rate_pct": e1_rate,
            "e2_rules": e2_rules, "delta_pp": delta, "verdict": verdict,
        }
    n_all = n_candidates
    c0_rate = _pct(main_tot["c0"], n_all)
    e1_rate = _pct(main_tot["e1"], n_all)
    delta = round(e1_rate - c0_rate, 4)
    verdict = _verdict(delta)
    print(f"{'合计':6s} {main_tot['c0']:3d}/{n_all:<3d}{c0_rate:5.1f}% "
          f"{main_tot['e1']:3d}/{n_all:<3d}{e1_rate:5.1f}% {delta:+8.2f}pp {verdict:>8s}")
    result["main_total"] = {
        "c0_decidable": main_tot["c0"], "c0_rate_pct": c0_rate,
        "e1_rules": main_tot["e1"], "e1_rate_pct": e1_rate,
        "e2_rules": main_tot["e2"], "delta_pp": delta, "verdict": verdict,
        "caveat": "⚠ 两把尺子不对称（C0 只解析算子，E1 还要求字段绑定+证据可验证）"
                  " ⇒ 该差值**不能干净归因**给「表达层升级」",
    }

    # ---- 带操作数口径 ----
    print()
    print("-" * 78)
    print("【带操作数】C0 可执行（存在类算子免操作数） vs E1 规则数")
    print("-" * 78)
    print(f"{'协议':6s} {'C0':>12s} {'E1':>12s} {'E1−C0':>10s}")
    op_tot = {"c0": 0, "e1": 0}
    for p in PROTOCOLS:
        c0_p = [i for i in c0 if i.get("protocol") == p]
        e1_p = [i for i in e1 if i.get("protocol") == p]
        n_p = len(c0_p) or 1
        c0_op = sum(1 for i in c0_p if _c0_executable(i))
        e1_rules = sum(1 for i in e1_p if i.get("outcome") and not i.get("reject_reason"))
        op_tot["c0"] += c0_op
        op_tot["e1"] += e1_rules
        print(f"{p:6s} {c0_op:3d}/{n_p:<3d}{_pct(c0_op, n_p):5.1f}% "
              f"{e1_rules:3d}/{n_p:<3d}{_pct(e1_rules, n_p):5.1f}% "
              f"{_pct(e1_rules, n_p) - _pct(c0_op, n_p):+8.2f}pp")
    c0r = _pct(op_tot["c0"], n_all)
    e1r = _pct(op_tot["e1"], n_all)
    d2 = round(e1r - c0r, 4)
    print(f"{'合计':6s} {op_tot['c0']:3d}/{n_all:<3d}{c0r:5.1f}% "
          f"{op_tot['e1']:3d}/{n_all:<3d}{e1r:5.1f}% {d2:+8.2f}pp  "
          f"档位：{_verdict(d2)}")
    result["with_operand_total"] = {
        "c0": op_tot["c0"], "c0_rate_pct": c0r,
        "e1": op_tot["e1"], "e1_rate_pct": e1r,
        "delta_pp": d2, "verdict": _verdict(d2),
        "caveat": "⚠ 仍不对称 —— E1 侧未额外要求「字段绑定 + 证据可验证」",
    }

    # ---- 同等严格度 ----
    print()
    print("-" * 78)
    print("【同等严格度】两边都要求「有操作数 + 有依据」")
    print("-" * 78)
    print(f"{'协议':6s} {'C0':>12s} {'E1严格':>12s} {'E1−C0':>10s} {'档位':>8s}")
    eq_tot = {"c0": 0, "e1": 0}
    for p in PROTOCOLS:
        c0_p = [i for i in c0 if i.get("protocol") == p]
        e1_p = [i for i in e1 if i.get("protocol") == p]
        n_p = len(c0_p) or 1
        c0_op = sum(1 for i in c0_p if _c0_executable(i))
        e1_strict = len(_e1_strict_rules(e1_p))
        eq_tot["c0"] += c0_op
        eq_tot["e1"] += e1_strict
        cr = _pct(c0_op, n_p)
        er = _pct(e1_strict, n_p)
        d = round(er - cr, 4)
        print(f"{p:6s} {c0_op:3d}/{n_p:<3d}{cr:5.1f}% "
              f"{e1_strict:3d}/{n_p:<3d}{er:5.1f}% {d:+8.2f}pp {_verdict(d):>8s}")
        result["by_protocol"].setdefault(p, {})["equal_strictness"] = {
            "c0_with_operand": c0_op, "e1_strict_rules": e1_strict,
            "c0_rate_pct": cr, "e1_rate_pct": er, "delta_pp": d,
            "verdict": _verdict(d),
        }
    cr = _pct(eq_tot["c0"], n_all)
    er = _pct(eq_tot["e1"], n_all)
    d3 = round(er - cr, 4)
    print(f"{'合计':6s} {eq_tot['c0']:3d}/{n_all:<3d}{cr:5.1f}% "
          f"{eq_tot['e1']:3d}/{n_all:<3d}{er:5.1f}% {d3:+8.2f}pp  "
          f"档位：{_verdict(d3)}")
    result["equal_strictness_total"] = {
        "c0": eq_tot["c0"], "c0_rate_pct": cr,
        "e1_strict": eq_tot["e1"], "e1_rate_pct": er,
        "delta_pp": d3, "verdict": _verdict(d3),
        "e1_strict_criteria": "绑定字段 + 有操作数 + 证据可验证（validated=True）",
    }

    # ---- 值域类约束口径（只算真正带值域比较的）----
    print()
    print("-" * 78)
    print("【值域类约束】只算「带操作数的值域比较」（存在类算子不计入）")
    print("-" * 78)
    print(f"{'协议':6s} {'C0':>12s} {'E1':>12s} {'E1−C0':>10s}")
    vr_tot = {"c0": 0, "e1": 0}
    for p_ in PROTOCOLS:
        c0_p = [i for i in c0 if i.get("protocol") == p_]
        e1_p = [i for i in e1 if i.get("protocol") == p_]
        n_p = len(c0_p) or 1
        c0_v = sum(1 for i in c0_p
                   if i.get("decidable")
                   and str(i.get("operator") or "") not in PRESENCE_OPERATORS
                   and i.get("operand"))
        e1_v = sum(1 for i in e1_p
                   if i.get("outcome") and not i.get("reject_reason")
                   and str(i.get("operator") or "") not in PRESENCE_OPERATORS
                   and i.get("operand"))
        vr_tot["c0"] += c0_v
        vr_tot["e1"] += e1_v
        print(f"{p_:6s} {c0_v:3d}/{n_p:<3d}{_pct(c0_v, n_p):5.1f}% "
              f"{e1_v:3d}/{n_p:<3d}{_pct(e1_v, n_p):5.1f}% "
              f"{_pct(e1_v, n_p) - _pct(c0_v, n_p):+8.2f}pp")
    cr = _pct(vr_tot["c0"], n_all)
    er = _pct(vr_tot["e1"], n_all)
    d4 = round(er - cr, 4)
    print(f"{'合计':6s} {vr_tot['c0']:3d}/{n_all:<3d}{cr:5.1f}% "
          f"{vr_tot['e1']:3d}/{n_all:<3d}{er:5.1f}% {d4:+8.2f}pp  "
          f"档位：{_verdict(d4)}")
    print("  ★ 这才是 M1 的**真实弱点**：E1 的 20 条规则里 14 条是存在类算子")
    print("    （present/absent，语义上只说「必须存在/不得出现」，无值域比较），")
    print("    真正带值域的只有 6 条 ⇒ 「可执行」的**含金量**远低于条数。")
    result["value_domain_only_total"] = {
        "c0": vr_tot["c0"], "c0_rate_pct": cr,
        "e1": vr_tot["e1"], "e1_rate_pct": er,
        "delta_pp": d4, "verdict": _verdict(d4),
        "note": "只算带操作数的值域比较（存在类算子不计）⇒ 衡量「可执行的含金量」",
    }

    # ---- 阈值可达性 ----
    print()
    print("-" * 78)
    print("【预登记阈值可达性】")
    print("-" * 78)
    need_rate = round(c0_rate + PREREG["成立"], 4)
    need_n = round(need_rate * n_all / 100.0)
    ub = ANNOTATION_UPPER_BOUND
    print(f"  主口径 C0 = {c0_rate:.2f}% ⇒ 「成立」档需 E1 ≥ {need_rate:.2f}%"
          f" = {need_n}/{n_all} 条")
    print(f"  人工标注实测可执行率**上界** = {ub['pct']:.2f}%（{ub['total']}/{ub['denominator']}）")
    reachable = ub["pct"] >= need_rate
    print(f"  ⇒ 预登记的 +15pp 在当前候选池上{'**可达**' if reachable else '**数学上不可达**'}")
    result["threshold_feasibility"] = {
        "c0_rate_pct": c0_rate, "required_rate_pct": need_rate,
        "required_rules": need_n, "denominator": n_all,
        "annotation_upper_bound_pct": ub["pct"],
        "reachable": reachable,
        "note": "上界来自实际标注结果（docs/annotation_status.md §2.4）；"
                "标注文档另注明「粒度修正后上界会抬高、预登记须重算」",
    }

    # ---- 逐候选归因（E1 拒了什么、C0 却判了）----
    dec = {i.get("candidate_id"): i for i in c0}
    buckets = collections.Counter()
    detail = {"c0_only": [], "e1_only": [], "both": [], "neither": []}
    for it in e1:
        cid = it.get("candidate_id")
        c0_item = dec.get(cid)
        c0_ok = bool(c0_item and c0_item.get("decidable"))
        e1_ok = bool(it.get("outcome") and not it.get("reject_reason"))
        key = ("both" if (c0_ok and e1_ok) else
               "c0_only" if c0_ok else
               "e1_only" if e1_ok else "neither")
        buckets[key] += 1
        detail[key].append({
            "candidate_id": cid, "protocol": it.get("protocol"),
            "c0_operator": (c0_item or {}).get("operator"),
            "e1_reject_reason": it.get("reject_reason"),
            "e1_stage_a_reason": it.get("stage_a_reason"),
            "e1_stage_b_reason": it.get("stage_b_reason"),
            "source_modality": it.get("source_modality"),
        })
    print()
    print("-" * 78)
    print("【逐候选归因】120 条的四种组合")
    print("-" * 78)
    for k in ("both", "c0_only", "e1_only", "neither"):
        print(f"  {k:10s} {buckets[k]:3d}")
    print("  ⇒ c0_only 的条目 = 「C0 能判、E1 拒」= 两把尺子的差来源")
    result["attribution"] = {"buckets": dict(buckets), "detail": detail}

    # ---- E1 规则的构成（解释 M1 的真实弱点）----
    e1_rules_all = [i for i in e1 if i.get("outcome") and not i.get("reject_reason")]
    presence = sum(1 for i in e1_rules_all
                   if str(i.get("operator") or "") in PRESENCE_OPERATORS)
    value_dom = len(e1_rules_all) - presence
    print()
    print("-" * 78)
    print("【E1 规则的构成】")
    print("-" * 78)
    print(f"  规则总数 {len(e1_rules_all)}")
    print(f"    ├─ 存在类算子（present/absent，无值域）: {presence}")
    print(f"    └─ 值域类算子（eq/ne/ge/…，有值域）  : {value_dom}")
    print(f"  ⇒ 带值域的比例 = {_pct(value_dom, len(e1_rules_all) or 1):.1f}%")
    result["e1_rule_composition"] = {
        "total": len(e1_rules_all),
        "presence_operators": presence,
        "value_domain_operators": value_dom,
        "value_domain_pct": _pct(value_dom, len(e1_rules_all) or 1),
        "note": "存在类算子语义上只说「必须存在/不得出现」，无值域比较 ⇒ "
                "M1 的条数会高估「可执行约束」的实质数量",
    }

    out_path = EXP_DIR / "m1_sensitivity.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"结果已写入：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
