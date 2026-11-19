# -*- coding: utf-8 -*-
"""把 Evidence 审查侧车接到隔离 Hub：按 fact_id/claim_id 关联并读回验收。"""
from __future__ import annotations
import json, pathlib, sys, tempfile, csv

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.hub import hub_entities as HE
from hub_isolated import isolated_hub


def load_review(base: pathlib.Path) -> dict:
    rows = list(csv.DictReader((base / "T0A_30条Evidence语义支持逐条审查.csv")
                               .open(encoding="utf-8")))
    side = json.loads((base / "T0A_双阶段_20261119/evidence_review_sidecar_v2.json")
                      .read_text(encoding="utf-8"))
    return {r["id"]: r for r in rows}, side


def main() -> int:
    base = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q8-V2-E4-R29_RA2_散文缺口核查"
    review, side = load_review(base)
    facts, metas = [], []
    for f in sorted((base / "T0A_实跑4_20261119_promptv4").glob("*.jsonl")):
        if f.name.startswith(("entities", "SHA256")):
            continue
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                facts.append(json.loads(ln))

    # p<idx> 与 fact 的对应：按 facts 顺序与 align 的 p0..p29 一一对应
    align = json.loads((base / "T0A_双阶段_20261119/align_v4_30items.json")
                       .read_text(encoding="utf-8"))["items"]
    assert len(align) == len(facts), (len(align), len(facts))
    for i, (a, f) in enumerate(zip(align, facts)):
        c = (f.get("all_claims") or [{}])[0]
        fix = (side.get("items") or {}).get(a["id"])
        metas.append({
            "proposition_id": a["id"],
            "fact_id": c.get("fact_id") or f.get("fact_id"),
            "claim_id": c.get("claim_id"),
            "model_span": a.get("model_span"),
            "model_quote": a.get("quote"),
            "verified_span": (fix or {}).get("corrected_span") or a.get("verified_span"),
            "corrected_quote": (fix or {}).get("corrected_quote") or a.get("quote"),
            "quote_origin": "corrected" if fix else "model",
            "match": (fix or {}).get("match") or a.get("match"),
            # 侧车 v2 已修正的三条（p7/p8/p13）覆盖首轮审查结论
            "evidence_support_status": ("supported" if fix
                                        else review[a["id"]]["status"]),
            "doc_sha256": side["doc_sha256"],
        })

    keys = [m["claim_id"] for m in metas]
    dup = len(keys) != len(set(keys))
    supported = [m for m in metas if m["evidence_support_status"] == "supported"]
    origin = {o: sum(1 for m in metas if m["quote_origin"] == o) for o in ("model", "corrected")}

    out = pathlib.Path(tempfile.mkdtemp(prefix="t0a_ev_"))
    fd = out / "per_source" / "facts"; fd.mkdir(parents=True)
    (fd / "mixed.jsonl").write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in facts) + "\n", encoding="utf-8")
    (out / "evidence_meta.json").write_text(json.dumps(metas, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    with isolated_hub(out):
        loaded = HE.load_facts("smtp")
        ents, _ = HE.build_entity_index(loaded)
        ep = HE.write_entity_index("smtp", ents)
        back = [json.loads(x) for x in ep.read_text(encoding="utf-8").splitlines() if x.strip()]

    # 读回关联：claim_id 必须在 meta 中唯一命中
    meta_by_claim = {m["claim_id"]: m for m in metas}
    joined = [meta_by_claim.get((f.get("all_claims") or [{}])[0].get("claim_id"))
              for f in loaded]

    print(f"facts={len(facts)} metas={len(metas)} dup_key={dup} "
          f"supported={len(supported)} origin={origin} entities={len(ents)}")
    print("readback facts", len(loaded), "entities_file", ep.is_file(),
          "join_ok", all(x is not None for x in joined))
    print("p7/p8/p13 origin",
          [(m["proposition_id"], m["quote_origin"], m["verified_span"])
           for m in metas if m["proposition_id"] in ("p7", "p8", "p13")])
    pathlib.Path("evidence_join_result.json").write_text(json.dumps({
        "facts": len(facts), "metas": len(metas), "dup_key": dup,
        "supported": len(supported), "origin": origin,
        "readback": len(loaded), "join_ok": all(x is not None for x in joined),
        "out_dir": str(out)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
