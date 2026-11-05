# -*- coding: utf-8 -*-
"""状态机种子质量 · 离线真值重算（零 LLM 成本）。

★ 为什么需要独立判据：`kept`（校验后种子数）**不是**质量指标 ——
  它衡量的是「本系统自己的校验器裁掉了多少」，而校验器用的就是**被测对象**
  自己的状态机 ⇒ 自证循环。
  ⇒ 必须用**外部真值**（RFC 原文的状态转移表）统一评判所有组。

★ 外部真值：RFC 2326 **A.1 客户端表 ∪ A.2 服务端表**（两表边集逐条相同，
  共 14 条；已逐行核对原文，见 local/_diag_state_names.py）。

★ 指标：
  P（精确率）= 保留下来的种子中，状态路径在真值下合法的比例
  R（召回率）= raw 种子中，状态路径在真值下合法的比例
  合法判定：state_path 的每一对相邻状态 (s_i, s_{i+1}) 都必须出现在真值边集
  严格判定： additionally，state_path[i] --messages[i].method--> state_path[i+1]
            必须在真值边集里（方法级对齐）

用法：E:/app/Anaconda3/python.exe local/_eval_state_truth.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fused.downstream import rag_seedgen as RS        # noqa: E402

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "_exp_state_raw"

#: RFC 2326 A.1（客户端）+ A.2（服务端）状态转移真值（14 条）
TRUTH_EDGES: set[tuple[str, str, str]] = {
    ("Init", "SETUP", "Ready"),
    ("Init", "TEARDOWN", "Init"),
    ("Ready", "PLAY", "Playing"),
    ("Ready", "RECORD", "Recording"),
    ("Ready", "TEARDOWN", "Init"),
    ("Ready", "SETUP", "Ready"),
    ("Playing", "PAUSE", "Ready"),
    ("Playing", "TEARDOWN", "Init"),
    ("Playing", "PLAY", "Playing"),
    ("Playing", "SETUP", "Playing"),
    ("Recording", "PAUSE", "Ready"),
    ("Recording", "TEARDOWN", "Init"),
    ("Recording", "RECORD", "Recording"),
    ("Recording", "SETUP", "Recording"),
}
TRUTH_STATES = {s for f, _, t in TRUTH_EDGES for s in (f, t)}
#: (from, method) → 允许的目标态集合
TRUTH_BY_FROM_METHOD: dict[tuple[str, str], set[str]] = {}
for _f, _m, _t in TRUTH_EDGES:
    TRUTH_BY_FROM_METHOD.setdefault((_f, _m), set()).add(_t)

#: 各组采用的 transitions（须与 _exp_state_machine.py 一致）
GROUP_TRANSITIONS: dict[str, list] = {}


def load_groups() -> dict[str, list]:
    """从实验结果 JSON 复原各组的 transitions。"""
    res = json.loads((HERE / "_exp_state_machine_result.json").read_text(encoding="utf-8"))
    out = {}
    for name, r in res["results"].items():
        out[name] = [tuple(x) for x in r["transitions"]]
    return out


def _path_states(seed) -> list[str]:
    return [str(x) for x in (seed.target_state_path or [])]


def judge_path(states: list[str]) -> bool:
    """状态路径在真值下是否合法（相邻对必须是真值边）。"""
    if len(states) < 2:
        return False
    for a, b in zip(states, states[1:]):
        if (a, b) not in {(f, t) for f, _, t in TRUTH_EDGES}:
            return False
    return True


def judge_strict(seed) -> bool:
    """严格判定：状态对合法 **且** 方法对齐（state_path[i] --msg[i]--> state_path[i+1]）。"""
    states = _path_states(seed)
    if not judge_path(states):
        return False
    msgs = [m for m in seed.messages if getattr(m, "method", "")]
    for i in range(min(len(states) - 1, len(msgs))):
        a, b, meth = states[i], states[i + 1], str(msgs[i].method).strip().upper()
        if b not in TRUTH_BY_FROM_METHOD.get((a, meth), set()):
            return False
    return True


def main() -> None:
    groups = load_groups()
    print("=" * 80)
    print("状态机种子质量 · 外部真值重算（真值 = RFC 2326 A.1+A.2 共 14 条边）")
    print("=" * 80)

    summary: dict[str, dict] = {}
    for name, trans in groups.items():
        gstates = {s for f, _, t in trans for s in (f, t)}
        rows = []
        for f in sorted(RAW_DIR.glob(f"{name}_rep*.json")):
            resp = json.loads(f.read_text(encoding="utf-8"))
            seeds = RS.parse_seed_response(resp, "rtsp", [], [])
            bundle = {"methods": {}, "required_headers": {},
                      "transitions": list(trans)}
            # 复原该组校验器：用完整 bundle 的 methods/headers（来自中枢）
            kept = _keep_mask(name, seeds)
            raw_ok = sum(1 for s in seeds if judge_path(_path_states(s)))
            raw_strict = sum(1 for s in seeds if judge_strict(s))
            keep_ok = sum(1 for s, k in zip(seeds, kept) if k and judge_path(_path_states(s)))
            keep_strict = sum(1 for s, k in zip(seeds, kept) if k and judge_strict(s))
            # 用了哪些状态名
            used = {x for s in seeds for x in _path_states(s)}
            rows.append({
                "rep": f.name, "raw": len(seeds), "kept": sum(kept),
                "raw_ok": raw_ok, "raw_strict": raw_strict,
                "keep_ok": keep_ok, "keep_strict": keep_strict,
                "used_states": sorted(used),
                "foreign_states": sorted(used - TRUTH_STATES),
            })
        if not rows:
            continue
        n = len(rows)
        raw = [r["raw"] for r in rows]
        kept = [r["kept"] for r in rows]
        raw_ok = sum(r["raw_ok"] for r in rows)
        raw_tot = sum(r["raw"] for r in rows)
        keep_ok = sum(r["keep_ok"] for r in rows)
        keep_tot = sum(r["kept"] for r in rows)
        raw_strict = sum(r["raw_strict"] for r in rows)
        keep_strict = sum(r["keep_strict"] for r in rows)
        foreign = sorted({x for r in rows for x in r["foreign_states"]})
        summary[name] = {
            "raw_mean": round(statistics.mean(raw), 2),
            "kept_mean": round(statistics.mean(kept), 2),
            "R_召回": round(raw_ok / raw_tot, 4) if raw_tot else 0.0,
            "P_精确": round(keep_ok / keep_tot, 4) if keep_tot else 0.0,
            "R_严格": round(raw_strict / raw_tot, 4) if raw_tot else 0.0,
            "P_严格": round(keep_strict / keep_tot, 4) if keep_tot else 0.0,
            "非法状态名": foreign,
            "本组状态名数": len(gstates),
            "本组RFC命中": len(gstates & TRUTH_STATES),
        }
        s = summary[name]
        print(f"\n── {name}")
        print(f"   raw={s['raw_mean']}  kept={s['kept_mean']}")
        print(f"   R(召回,raw中合法率)   = {s['R_召回']:.1%}      "
              f"R(严格,方法对齐) = {s['R_严格']:.1%}")
        print(f"   P(精确,kept中合法率) = {s['P_精确']:.1%}      "
              f"P(严格)           = {s['P_严格']:.1%}")
        print(f"   本组状态名 {s['本组状态名数']} 个 / RFC 真值命中 {s['本组RFC命中']} 个")
        print(f"   种子用到的**非法状态名** {len(s['非法状态名'])}: {s['非法状态名']}")

    (HERE / "_eval_state_truth_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {HERE / '_eval_state_truth_result.json'}")


def _keep_mask(name: str, seeds: list) -> list[bool]:
    """用该组自己的 transitions 复算校验器判定（与实验脚本同口径）。"""
    groups = load_groups()
    trans = groups.get(name) or []
    by_from: dict[str, set] = {}
    for src, method, dst in trans:
        by_from.setdefault(str(src).upper(), set()).add((str(method).upper(), dst))
    out = []
    for s in seeds:
        states = _path_states(s)
        current = (states[0] if states else "Init")
        ok = True
        for i, m in enumerate(s.messages):
            method = str(getattr(m, "method", "") or "").upper()
            if not method:
                continue
            allowed = by_from.get(current.upper(), set())
            if allowed:
                cands = sorted(d for mm, d in allowed if mm == method)
                if not cands:
                    ok = False
                    break
                current = next((d for d in cands if d == current), cands[0])
        out.append(ok)
    return out


if __name__ == "__main__":
    main()
