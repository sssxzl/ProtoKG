# -*- coding: utf-8 -*-
"""qa/batch23_ablation/stats.py —— 消融档位的**中枢 + 语料**统计。

★ 只读：不修改任何文件。
★ 用途：把「协议骨架的来源维度消融」三档的可比数字抽出来：
    骨架 facts 数 / 状态机转移数 / 消息实例数 / 种子数 / 层分布 / G1+G2 闸门。
"""
from __future__ import annotations

import argparse
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


def _count_facts(protocol: str) -> dict:
    """中枢 facts 目录：总条数 + 按 aspect 计数。"""
    from core import paths as P
    out = {"total": 0, "by_aspect": {}, "dir": ""}
    d = P.per_source_aspect_facts_dir(protocol)
    out["dir"] = str(d)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.jsonl")):
        n = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                n += 1
        out["by_aspect"][f.stem] = n
        out["total"] += n
    return out


def _count_skeleton_materialized(protocol: str) -> dict:
    """★ 中枢里 **profile 源**的物化条数（旧布局 ``profile/facts/profile.jsonl``）。

    ★ 该文件 = **协议骨架**（按 ``origin`` 维度过滤后）+ **必填头清单**
      ⇒ A 档 = 145 + 8 = 153；B 档 = 69(traffic 侧) + 8 = 77；
      C 档 = 0(骨架全排除) + 8 = 8 ⇒ 剩下的 8 条是**与来源维度无关的
      必填头知识**（设计如此，不是漏网）。

    ★ 必须**即时**读取（每档构建后立即取）⇒ 事后统一读会读到「最后一档」
      的状态 ⇒ 三档数字全一样（本次踩过）。

    ★ 注意：新布局 ``facts/<aspect>.jsonl`` 里**混着所有源**的 facts
      （RFC 源自己也产出 target_state / method_sequence 等同名 aspect）
      ⇒ **不能**用新布局的 aspect 条数当作「骨架条数」。
    """
    from core import paths as P
    out = {"profile_source_total": 0, "skeleton_only": 0,
           "required_headers_only": 0, "legacy_exists": False}
    f = P.per_source_facts_dir(protocol, "profile") / "profile.jsonl"
    if f.is_file():
        out["legacy_exists"] = True
        lines = [x for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        out["profile_source_total"] = len(lines)
        skel = req = 0
        for ln in lines:
            try:
                v = json.loads(ln)
            except json.JSONDecodeError:
                continue
            asp = ((v.get("fact_key") or {}).get("aspect")) or ""
            if asp == "required_headers":
                req += 1
            else:
                skel += 1
        out["skeleton_only"] = skel
        out["required_headers_only"] = req
    return out


def _count_skeleton_expected(protocol: str, exclude_dims=()) -> dict:
    """从骨架 JSON **按 origin 维度**算出的理论条数（用于交叉校验）。"""
    from scripts.build_hub import _skeleton_aspect_origin
    from core import paths as P
    src = P.target_skeleton(protocol)
    if not src.is_file():
        return {}
    doc = json.loads(src.read_text(encoding="utf-8"))
    facts = doc.get("facts") or []
    omap = _skeleton_aspect_origin(doc)
    kept = 0
    per_dim = {"source": 0, "traffic": 0, "other": 0}
    for f in facts:
        asp = ((f.get("fact_key") or {}).get("aspect")) or ""
        dim = omap.get(asp, "")
        if dim and dim in exclude_dims:
            continue
        kept += 1
        per_dim[dim or "other"] += 1
    return {"skeleton_total": len(facts), "kept": kept, "per_dim": per_dim}


def _count_bundle(protocol: str) -> dict:
    """组装 bundle：状态机转移数 / 消息实例数 / 方法数 / 头数。"""
    from core.fused.downstream.rag_seedgen import (
        assemble_bundle, load_fact_views,
    )
    from scripts.seedgen import resolve_source_set
    views = load_fact_views(protocol)
    if not views:
        return {"views": 0}
    src_set, _ = resolve_source_set(protocol, None)
    b = assemble_bundle(views, source_set=src_set or None)
    trs = b.get("transitions") or []
    mi = b.get("message_instances") or []
    return {
        "views": len(views),
        "transitions": len(trs),
        "message_instances": len(mi),
        "methods": len(b.get("methods") or {}),
        "headers": len(b.get("headers") or {}),
        "method_sequences": len(b.get("method_sequences") or []),
        "available_sources": sorted(b.get("available_sources") or []),
    }


def _count_state_machine_candidates(protocol: str) -> dict:
    """各源的状态机候选数（未消解，批次 2.3 的原始素材）。"""
    from core import paths as P
    f = P.per_source_root(protocol) / "state_machines.json"
    if not f.is_file():
        return {}
    doc = json.loads(f.read_text(encoding="utf-8"))
    return {k: len(v) for k, v in (doc.get("sources") or {}).items()}


def _count_seeds(seed_dir: Path) -> dict:
    """语料：种子数 + 层分布（从 manifest.json 读溯源）。"""
    out = {"seed_count": 0, "by_layer": {}, "by_layer_name": {},
           "raw_files": 0, "manifest": False}
    if not seed_dir.is_dir():
        return out
    out["raw_files"] = len(list(seed_dir.glob("*.raw")))
    mf = seed_dir / "manifest.json"
    if not mf.is_file():
        return out
    out["manifest"] = True
    doc = json.loads(mf.read_text(encoding="utf-8"))
    out["seed_count"] = doc.get("seed_count") or 0
    for s in doc.get("seeds") or []:
        for key in ("layer", "layer_name"):
            tgt = out["by_layer"] if key == "layer" else out["by_layer_name"]
            tgt[s.get(key) or "?"] = tgt.get(s.get(key) or "?", 0) + 1
    out["dict_tokens"] = (doc.get("dictionary") or {}).get("token_count")
    return out


def _read_gate(path: Path) -> dict:
    """解析 corpus_gate 的 JSON 报告。

    ★ corpus_gate 的 ``gates`` 是 **dict**（键 = G1/G2/G5，值 = 明细 dict），
      不是 list ⇒ 不能按列表迭代。
    """
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"_raw": path.read_text(encoding="utf-8")[:800]}
    raw = doc.get("gates")
    gates: dict = {}
    if isinstance(raw, dict):
        for name, g in raw.items():
            if not isinstance(g, dict):
                gates[name] = {"raw": g}
                continue
            gates[name] = {
                "status": g.get("status"),
                "violation_count": g.get("violation_count"),
                "pass": g.get("pass"),
                "applicable": g.get("applicable"),
            }
    elif isinstance(raw, list):
        for g in raw:
            if not isinstance(g, dict):
                continue
            name = g.get("name") or g.get("id") or g.get("gate") or "?"
            gates[name] = {
                "status": g.get("status"),
                "violation_count": g.get("violation_count")
                if "violation_count" in g else g.get("violations"),
                "pass": g.get("pass"),
            }
    return {"gates": gates, "overall_pass": doc.get("overall_pass")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--seed-dir", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--gate", default="")
    ap.add_argument("--exclude-dims", nargs="*", default=[])
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    doc = {
        "arm": args.arm,
        "protocol": args.protocol,
        "exclude_dims": list(args.exclude_dims),
        "hub_facts": _count_facts(args.protocol),
        "skeleton_materialized": _count_skeleton_materialized(args.protocol),
        "skeleton_expected": _count_skeleton_expected(
            args.protocol, tuple(args.exclude_dims)),
        "bundle": _count_bundle(args.protocol),
        "state_machine_candidates": _count_state_machine_candidates(args.protocol),
        "seeds": _count_seeds(Path(args.seed_dir)),
    }
    if args.gate:
        doc["gate"] = _read_gate(Path(args.gate))

    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
