# -*- coding: utf-8 -*-
"""状态机消费口径对照实验（只读 / 不改生产代码 / 真调 LLM）。

★ 动因（「性能优先」原则下重估 RFC 源状态机的真实价值）：
  ① 已知事实：RTSP 骨架(profile)状态机的 6 个状态名在 RFC 2326 原文中
     **0/6 命中**（全是 SIP 式命名 Idle/Registered/Confirmed/Invited/
     Paused/Terminated）⇒ 这 38 条边既污染 prompt，又因状态名对不上而
     **100% 无法参与 `validate_seed` 的状态转移校验**（"有知识才校验"分支
     永不触发）⇒ 对 RTSP 而言是**死知识**。
  ② RFC 源(rfc)那 14 条状态名 **4/4 命中** RFC 原文（Init/Ready/Playing/
     Recording）⇒ 语义正确。
  ③ 先前判断「服务端状态机 A.2 是散文、表格抽不到 ⇒ 只有客户端那 12 条」
     **已被证伪**：A.2 也是定宽表格，且边集与 A.1 **逐条相同** ⇒ 抽了也无增量；
     且 LLM 通道 G 抽出的 14 条与确定性表格抽出的 14 条 **完全一致**
     ⇒ **RTSP 状态机 LLM 零增量**（SIP 才需要 LLM：§17 是 ASCII 图，确定性 0 条）。

  ⇒ 真正待决的不是「能不能多抽」，而是**消费端采用哪一套**。

★ 四组设计（只差 `[状态机转移]` 一节 ⇒ 归因干净）：
  G0 现状默认口径：骨架 38 条 + `profile.allowed_methods` 裁剪
     （⇒ RECORD 被裁 ⇒ RTSP 少 2 条边；这正是历史「58→17」的成因之一）
  G1 骨架 38 条，不裁白名单（隔离白名单的影响）
  G2 RFC 源 14 条（状态名原生、语义正确），不裁白名单
  G3 骨架 38 ∪ RFC 14（合并去重，两套状态名并存）

★ 指标：
  seeds_raw / seeds_kept   —— validate 前/后的种子数
  状态落位率               —— 种子 state_path 落在**本组**状态集合内的比例
  跨源污染率               —— 种子 state_path 落在**另一套**状态集合内的比例
  prompt 可溯源率          —— prompt 里的状态机条目，其状态名在 RFC 原文命中比
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402

PROTOCOL = "rtsp"
REPEATS = 3
N_SEEDS = 20
OUT = Path(__file__).resolve().parent / "_exp_state_machine_result.json"


def rfc_text(protocol: str) -> str:
    d = paths.kb_source_dir(protocol, "rfc")
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in sorted(d.glob("*.txt")))


def make_groups(bundle: dict) -> dict:
    """构造四组 bundle（只改 transitions 桶 + 白名单口径）。

    ★ 白名单对**骨架**无影响（骨架 38 条的方法全在 `allowed_methods` 内），
      但对 **RFC 那 14 条**有影响：其中 2 条用 `RECORD`，而 `allowed_methods`
      不含 RECORD ⇒ 裁后 12 条。⇒ 这正是历史「RFC 源 38→12 ⇒ 种子 58→17」
      的机制，必须单列一组才能归因。
    """
    by_src = bundle.get("transitions_by_source") or {}
    skel = sorted(set(by_src.get("profile") or []))
    rfc = sorted(set(by_src.get("rfc") or []))
    allowed = RS._load_allowed_methods(PROTOCOL)

    def filtered(rows: list) -> list:
        return [t for t in rows
                if (t[1] if isinstance(t, tuple) and len(t) >= 2 else t) in allowed]

    groups = {
        "A_现状(骨架38)": skel,
        "B_RFC14原生(不裁)": rfc,
        "C_RFC14被白名单裁后": filtered(rfc),
        "D_合并(骨架+RFC)": sorted(set(skel) | set(rfc)),
    }
    return {k: list(v) for k, v in groups.items() if v}


def _chat_json_retry(llm, system: str, user: str, *, tries: int = 3):
    """LLM 返回截断 JSON 时重试（生产 `chat_json` 无重试；此处仅实验用）。"""
    last = None
    for i in range(tries):
        try:
            resp = llm.chat_json(system=system, user=user,
                                 temperature=0.3, max_tokens=8000)
            if isinstance(resp, dict) and (resp.get("seeds") or resp.get("messages")):
                return resp
            last = f"空/非预期结构: {str(resp)[:120]}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        print(f"      (重试 {i + 1}/{tries}：{last[:80]})")
    raise RuntimeError(f"LLM 重试 {tries} 次仍失败：{last}")


def main() -> None:
    text = rfc_text(PROTOCOL)

    from core.llm import DeepSeekClient
    try:
        llm = DeepSeekClient()
    except Exception as exc:  # noqa: BLE001
        print(f"!! LLM 不可用：{exc}", file=sys.stderr)
        raise SystemExit(2)

    views = RS.load_fact_views(PROTOCOL)
    if not views:
        print("!! 中枢为空 ⇒ 先跑 build_hub", file=sys.stderr)
        raise SystemExit(2)
    base = RS.assemble_bundle(views, PROTOCOL, apply_allowed_methods=False)
    groups = make_groups(base)

    skel_states = {s for t in groups.get("A_现状(骨架38)", []) for s in (t[0], t[2])}
    rfc_states = {s for t in groups.get("B_RFC14原生(不裁)", []) for s in (t[0], t[2])}

    print("=" * 78)
    print(f"状态机消费口径对照实验  协议={PROTOCOL}  重复={REPEATS}  n_seeds={N_SEEDS}")
    print("=" * 78)
    for name, rows in groups.items():
        states = sorted({s for t in rows for s in (t[0], t[2])})
        hit = [s for s in states if s in text]
        print(f"  {name}: {len(rows)} 条边 / {len(states)} 状态名 / "
              f"RFC 原文命中 {len(hit)}/{len(states)}")
    print()

    results: dict[str, dict] = {}
    for name, rows in groups.items():
        states = {s for t in rows for s in (t[0], t[2])}
        # 「另一套」= 未被本组采用的那套状态名（用于测跨源污染）
        other = (rfc_states - states) if states == skel_states else (skel_states - states)
        if states & other:
            other = set()          # 合并组：两套都在 ⇒ 跨源指标无意义
        per_run = []
        for rep in range(REPEATS):
            b = dict(base)
            b["transitions"] = list(rows)
            t0 = time.time()
            system, user = RS.render_seed_prompt(
                b, protocol=PROTOCOL, n_seeds=N_SEEDS)
            try:
                resp = _chat_json_retry(llm, system, user)
            except Exception as exc:  # noqa: BLE001
                print(f"    [{name} rep{rep}] LLM 失败：{exc}", file=sys.stderr)
                per_run.append({"error": str(exc)})
                continue
            seeds = RS.parse_seed_response(resp, PROTOCOL, [], [])
            kept = [s for s in seeds if not RS.validate_seed(s, b)]

            # ★ 落盘**原始响应** ⇒ 事后可用任何外部真值离线重算，不必重调 LLM
            _raw_dir = Path(__file__).resolve().parent / "_exp_state_raw"
            _raw_dir.mkdir(parents=True, exist_ok=True)
            (_raw_dir / f"{name}_rep{rep}.json").write_text(
                json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")

            def paths_of(ss):
                return [str(x) for x in (ss.target_state_path or [])]

            def in_set(ss, st):
                return [p for p in paths_of(ss) if p in st]

            land = sum(len(in_set(s, states)) for s in seeds)
            total = sum(len(paths_of(s)) for s in seeds)
            cross = sum(len(in_set(s, other)) for s in seeds) if other else 0
            per_run.append({
                "seeds_raw": len(seeds),
                "seeds_kept": len(kept),
                "state_total": total,
                "state_on_target": land,
                "state_cross": cross,
                "sec": round(time.time() - t0, 1),
            })
            print(f"    [{name} rep{rep}] raw={len(seeds):>3} kept={len(kept):>3} "
                  f"落位={land}/{total} 跨源={cross} {per_run[-1]['sec']}s")
        results[name] = {"per_run": per_run, "transitions": [list(t) for t in rows]}

    # ---- 汇总 ----
    print()
    print("=" * 78)
    print("汇总（均值 ± 半极差）")
    print("=" * 78)
    summary = {}
    for name, r in results.items():
        runs = [x for x in r["per_run"] if "error" not in x]
        if not runs:
            print(f"  {name}: 全部失败")
            continue
        raw = [x["seeds_raw"] for x in runs]
        kept = [x["seeds_kept"] for x in runs]
        land = sum(x["state_on_target"] for x in runs)
        tot = sum(x["state_total"] for x in runs)
        cross = sum(x["state_cross"] for x in runs)
        summary[name] = {
            "raw_mean": round(statistics.mean(raw), 2),
            "raw_rng": max(raw) - min(raw),
            "kept_mean": round(statistics.mean(kept), 2),
            "kept_rng": max(kept) - min(kept),
            "land_rate": round(land / tot, 4) if tot else 0.0,
            "cross_rate": round(cross / tot, 4) if tot else 0.0,
        }
        s = summary[name]
        print(f"  {name:<24} raw={s['raw_mean']:>6} (±{s['raw_rng']})  "
              f"kept={s['kept_mean']:>6} (±{s['kept_rng']})  "
              f"落位率={s['land_rate']:.1%}  跨源污染={s['cross_rate']:.1%}")

    OUT.write_text(json.dumps(
        {"protocol": PROTOCOL, "repeats": REPEATS, "n_seeds": N_SEEDS,
         "results": results, "summary": summary},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {OUT}")


if __name__ == "__main__":
    main()
