# -*- coding: utf-8 -*-
"""qa/batch23_ablation/summarize.py —— 三档消融的**分层**对比汇总。

★ 纪律：闸门报告要同时给**绝对数与比率**，并**按层拆分**
  ⇒ 「绝对数持平」会被误读成「没改善」；反过来，
     「种子变少 ⇒ 违规条数变少」也会被误读成「质量改善」。
  ⇒ 口径 = 每层的 (种子数, 违规数, 违规率)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

def _repo_root() -> Path:
    """向上找**仓库根**（含 ``core/paths.py`` 的目录）⇒ 不依赖相对层级。

    ★ 脚本从 ``qa/batch23_ablation/`` 迁到 ``tools/qa/ablation/`` 后层级变了
      ⇒ 固定 ``parents[N]`` 会指错目录（实测指到 ``tools/``）⇒ 改成向上查找。
    """
    here = Path(__file__).resolve()
    for cand in [here.parent] + list(here.parents):
        if (cand / "core" / "paths.py").is_file():
            return cand
    return here.parents[3]


REPO = _repo_root()
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "local" / "ablation_rtsp"
ARMS = {"A": "全量骨架（source+traffic）", "B": "去 source 侧（仅 traffic 观测）",
        "C": "纯 RFC（骨架全排除）"}


def _load(arm: str) -> dict:
    arm_p = OUT / f"arm_{arm}.json"
    gate_p = OUT / f"gate_{arm}.json"
    if not arm_p.is_file():
        return {}
    d = json.loads(arm_p.read_text(encoding="utf-8"))
    gate = json.loads(gate_p.read_text(encoding="utf-8")) if gate_p.is_file() else {}
    d["_gate"] = gate
    return d


def _skeleton_count() -> dict:
    """（保留：仅供调试）当前磁盘上的骨架物化条数。"""
    from core import paths as P
    out = {}
    for proto in ("rtsp", "sip", "smtp"):
        f = P.per_source_facts_dir(proto, "profile") / "profile.jsonl"
        if f.is_file():
            out[proto] = len([x for x in f.read_text(encoding="utf-8").splitlines()
                              if x.strip()])
    return out


def main() -> int:
    table = []
    for arm, label in ARMS.items():
        d = _load(arm)
        if not d:
            continue
        h, b, s = d["hub_facts"], d["bundle"], d["seeds"]
        sk = d.get("skeleton_materialized", {})
        se = d.get("skeleton_expected", {})
        gate = d["_gate"].get("gates", {})
        g1, g2 = gate.get("G1", {}), gate.get("G2", {})
        n = s.get("seed_count") or 0
        table.append({
            "档": arm,
            "含义": label,
            "排除维度": d.get("exclude_dims"),
            "中枢facts总数": h["total"],
            "profile源物化(骨架+必填头)": sk.get("profile_source_total"),
            "其中骨架": sk.get("skeleton_only"),
            "其中必填头": sk.get("required_headers_only"),
            "骨架理论条数": se.get("kept"),
            "骨架按维度": se.get("per_dim"),
            "transitions": b.get("transitions"),
            "message_instances": b.get("message_instances"),
            "headers": b.get("headers"),
            "种子数": n,
            "G1违规": g1.get("violation_count"),
            "G1比率": g1.get("violation_ratio"),
            "G2违规": g2.get("violation_count"),
            "G2比率": g2.get("violation_ratio"),
            "层分布": s.get("by_layer_name"),
            "G2按层": g2.get("by_layer"),
            "闸门通过": d["_gate"].get("overall_pass"),
        })
    text = json.dumps(table, ensure_ascii=False, indent=2)
    (REPO / "local" / "ablation_skeleton_dims.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
