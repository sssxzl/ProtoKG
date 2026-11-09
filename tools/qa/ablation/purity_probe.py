# -*- coding: utf-8 -*-
"""tools/qa/ablation/purity_probe.py —— **逐条判定**每颗种子的知识来源。

★ 目的：把「这批种子到底有多少知识不是 RFC 给的」变成**可复算的数字**。
★ 判定依据（全部来自仓库内的既有事实，不臆测）：
  ① ⑤ 层种子（layer_name=action_seq）⇒ 底料来源决定其知识来源：
     · 底料目录 ``derived/model/seeds/<proto>/<组>`` 的 manifest 里若含
       ``vuln_boundary`` 层 ⇒ 该目录**含 vuln 源知识**。
     · 底料来源标签 ``traffic-capture`` ⇒ **traffic 源**（真实抓包）。
  ② canonical 层 ⇒ 资源清单来自 ``fused_hub/targets/<proto>_streams.json``
     （文件自述：**提取自源码**）⇒ **source 源**。
  ③ ③ 层 vuln_boundary ⇒ 来自 ``rfc/semantic/rules.jsonl``
     ⇒ 源是 rfc，但**可能含跨协议规则**（实测 RTSP 库里 3/5 条是 SIP 的 RFC 3261）。
  ④ ① ② 层 ⇒ 来自 bundle；bundle 的 ``by_source`` 给出各桶的来源构成。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for cand in [here.parent] + list(here.parents):
        if (cand / "core" / "paths.py").is_file():
            return cand
    return here.parents[3]


REPO = _repo_root()
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _base_corpus_facts(protocol: str, group: str | None) -> dict:
    """⑤ 层底料目录的层构成（从 manifest 读）+ 各层知识来源判定。"""
    from core import paths as P
    from core.fused.downstream.action_seq import _published_group_dirs
    root = P.seeds_dir(protocol)
    out = {"dirs": [], "vuln_seeds": 0, "total_seeds": 0, "has_manifest": True,
           "layer_counts": {}, "source_side_seeds": 0, "used_dir": None}
    for d in _published_group_dirs(protocol, group, root):
        mf = d / "manifest.json"
        info = {"dir": d.name, "total": 0, "vuln_boundary": 0,
                "canonical": 0, "manifest": mf.is_file()}
        if mf.is_file():
            try:
                doc = json.loads(mf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                doc = {}
            for s in doc.get("seeds") or []:
                lay = s.get("layer_name") or "?"
                info["total"] += 1
                out["layer_counts"][lay] = out["layer_counts"].get(lay, 0) + 1
                if lay == "vuln_boundary":
                    info["vuln_boundary"] += 1
                if lay == "canonical":
                    # ★ canonical 底料的**资源清单**来自源码侧（rtsp_streams.json）
                    info["canonical"] += 1
                    out["source_side_seeds"] += 1
        else:
            out["has_manifest"] = False
        out["dirs"].append(info)
        # ★ `_load_published_seeds` **只取第一个有 .raw 的目录**（`if seeds: break`）
        #   ⇒ 底料事实只来自那一个 ⇒ 统计也必须一致，否则会误判 strict。
        if info["total"] > 0 and out["used_dir"] is None:
            out["used_dir"] = info["dir"]
            out["vuln_seeds"] = info["vuln_boundary"]
            out["total_seeds"] = info["total"]
            out["layer_counts"] = {}
            out["source_side_seeds"] = info["canonical"]
    return out


def _strict_applied(manifest_doc: dict, base: dict) -> bool:
    """判定本次是否启用了 strict（⑤ 层底料是否已被过滤）。

    判据：manifest 记录的 ``action_seq.base_count`` < 底料目录的可用条数
    ⇒ 说明有底料被排除 ⇒ strict 生效。
    """
    seq = (manifest_doc.get("seedgen") or {}).get("action_seq") or {}
    used = seq.get("base_count")
    if used is None:
        return False
    return int(used) < int(base.get("total_seeds") or 0)


def _base_source(protocol: str, group: str | None) -> str:
    """⑤ 层底料的实际来源标签（published-corpus / traffic-capture / ""）。"""
    from core import paths as P
    from core.fused.downstream.action_seq import load_real_base_seeds
    prof_path = P.target_profile(protocol)
    profile = {}
    if prof_path.is_file():
        try:
            profile = json.loads(prof_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            profile = {}
    _, src = load_real_base_seeds(protocol, profile, group=group,
                                  derived_root=P.seeds_dir(protocol))
    return src


def _streams_source(protocol: str) -> str:
    """canonical 层用的资源清单文件及其自述来源。"""
    from core import paths as P
    for cand in (P.targets_root() / protocol / f"{protocol}_streams.json",
                 P.targets_root() / f"{protocol}_streams.json"):
        if cand.is_file():
            try:
                doc = json.loads(cand.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return "unknown"
            note = str(doc.get("note") or doc.get("source") or "")
            return f"{cand.name} | {note[:80]}"
    return "(未找到)"


def _semantic_rules(protocol: str) -> dict:
    """语义规则库里的跨协议情况（spec_version 分布）。"""
    from core import paths as P
    f = P.per_source_root(protocol) / "rfc" / "semantic" / "rules.jsonl"
    if not f.is_file():
        return {}
    c: Counter = Counter()
    for ln in f.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            v = json.loads(ln)
        except json.JSONDecodeError:
            continue
        sv = (((v.get("rule") or {}).get("evidence") or {}).get("spec_version")) \
            or ((v.get("evidence") or {}).get("spec_version")) or "?"
        c[str(sv)] += 1
    return dict(c)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--seed-dir", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--group", default="B")
    ap.add_argument("--gate", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    sd = Path(args.seed_dir)
    mf = sd / "manifest.json"
    doc = json.loads(mf.read_text(encoding="utf-8")) if mf.is_file() else {}
    seeds = doc.get("seeds") or []
    by_layer = Counter(s.get("layer_name") or "?" for s in seeds)

    # ★ 批次 2.5（F5）：底料事实**优先**从**本次 manifest** 的 action_seq 元信息读
    #   —— 因为 F5 之后默认走「内部两段式」，底料根本不是 published 目录；
    #   沿用旧模型去查 published 目录 ⇒ 会把「同源底料」误判成「含 vuln 的历史语料」。
    seq = (doc.get("seedgen") or {}).get("action_seq") or {}
    base_src = str(seq.get("source") or "") or _base_source(args.protocol, args.group)
    base = _base_corpus_facts(args.protocol, args.group)
    if base_src == "internal-two-stage":
        # 底料 = **本次刚产的基准层** ⇒ 底料的层构成 = 本次语料的基准层构成
        _base_layers = Counter(
            s.get("layer_name") or "?"
            for s in seeds if (s.get("layer_name") or "") != "action_seq")
        base = {
            "dirs": [{"dir": "(本次基准层·内部两段式)", "total": seq.get("base_count"),
                      "vuln_boundary": _base_layers.get("vuln_boundary", 0),
                      "canonical": _base_layers.get("canonical", 0),
                      "manifest": True}],
            "vuln_seeds": _base_layers.get("vuln_boundary", 0),
            "total_seeds": seq.get("base_count") or 0,
            "has_manifest": True,
            "layer_counts": dict(_base_layers),
            "source_side_seeds": _base_layers.get("canonical", 0),
            "used_dir": "(本次基准层·内部两段式)",
            "two_stage": True,
        }
    rules = _semantic_rules(args.protocol)

    # ---- 逐层判定「知识来源」 ----
    strict = _strict_applied(doc, base)
    provenance: dict = {}
    for layer, n in by_layer.items():
        if layer == "action_seq":
            if base_src == "traffic-capture":
                tag = "traffic(真实抓包)"
            elif base_src == "internal-two-stage":
                tag = ("★同源(底料=本次基准层·内部两段式 ⇒ 无跨源)"
                       + ("；基准层含 canonical ⇒ 资源清单=源码侧"
                          if base.get("source_side_seeds") else ""))
            elif strict:
                tag = ("基准层语料（已滤 vuln）"
                       + ("；但其中含 canonical 底料 ⇒ 资源清单=源码侧"
                          if base.get("source_side_seeds") else ""))
            elif base["vuln_seeds"] > 0:
                tag = f"★混合(vuln {base['vuln_seeds']} 条 + 基准层)"
            else:
                tag = "基准层语料"
        elif layer == "canonical":
            tag = "★source(资源清单 rtsp_streams.json=源码侧)"
        elif layer == "vuln_boundary":
            tag = "rfc(语义规则；可能跨协议)"
        else:
            tag = "rfc+bundle(骨架)"
        provenance[layer] = {"count": n, "knowledge_origin": tag}

    # ---- 「真正只由 RFC 知识支撑」的条数 ----
    pure = 0
    for layer, n in by_layer.items():
        if layer in ("edge_cover", "generic_danger"):
            pure += n
    doc_out = {
        "arm": args.arm,
        "protocol": args.protocol,
        "seed_count": doc.get("seed_count"),
        "by_layer": dict(by_layer),
        "strict_source_only_applied": strict,
        "per_layer_provenance": provenance,
        "seed_count_pure_rfc_only": pure,
        "base_corpus": base,
        "base_source_label": base_src,
        "resource_list": _streams_source(args.protocol),
        "semantic_rules_spec_version": rules,
    }
    if args.gate and Path(args.gate).is_file():
        g = json.loads(Path(args.gate).read_text(encoding="utf-8"))
        gg = g.get("gates") or {}
        doc_out["gate"] = {
            "G1": (gg.get("G1") or {}).get("violation_count"),
            "G2": (gg.get("G2") or {}).get("violation_count"),
            "G2_by_layer": (gg.get("G2") or {}).get("by_layer"),
            "overall_pass": g.get("overall_pass"),
        }
    text = json.dumps(doc_out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
