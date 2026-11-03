# -*- coding: utf-8 -*-
"""tools/qa/ablation/purity_summary.py —— 纯净度阶梯（2×2 因子）的汇总。

★ 口径：种子数 + **分层知识来源** + 闸门（绝对数 + 比率）。
"""
from __future__ import annotations

import json
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for cand in [here.parent] + list(here.parents):
        if (cand / "core" / "paths.py").is_file():
            return cand
    return here.parents[3]


REPO = _repo_root()
OUT = REPO / "tools" / "qa" / "ablation" / "_out"

LABEL = {
    "S0": "S0 = 全量骨架 + 默认旁路（★ 历史基线口径）",
    "S1": "S1 = 全量骨架 + 关旁路",
    "S2": "S2 = 纯 RFC 骨架 + 默认旁路（= 上轮消融 C 档）",
    "S3": "S3 = 纯 RFC 骨架 + 关旁路（★ 真·纯净 RFC）",
}


def main() -> int:
    rows = []
    for arm in ("S0", "S1", "S2", "S3"):
        p = OUT / f"parm_{arm}.json"
        if not p.is_file():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        g = d.get("gate") or {}
        g2 = g.get("G2_by_layer") or {}
        base_layer = g2.get("base") or {}
        rows.append({
            "档": arm,
            "含义": LABEL.get(arm, arm),
            "种子数": d.get("seed_count"),
            "层分布": d.get("by_layer"),
            "⑤层底料来源": d.get("base_source_label"),
            "⑤层底料含vuln种子数": (d.get("base_corpus") or {}).get("vuln_seeds"),
            "G1违规": g.get("G1"),
            "G2违规": g.get("G2"),
            "G2比率(基准层)": base_layer.get("violation_ratio"),
            "每层知识来源": d.get("per_layer_provenance"),
        })
    text = json.dumps(rows, ensure_ascii=False, indent=2)
    (REPO / "local" / "purity_stair.json").write_text(
        text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
