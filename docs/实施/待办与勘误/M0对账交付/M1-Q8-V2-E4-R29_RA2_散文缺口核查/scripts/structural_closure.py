# -*- coding: utf-8 -*-
"""结构化最小闭环：D4 siaddr / H2 request-line → Norm → Fact → Evidence → 隔离 Hub。"""
from __future__ import annotations
import dataclasses, hashlib, json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import norm as NM
from core.fused.extraction.prose_semantics import locate_quote
from core.fused.hub import hub_entities as HE
from core.fused.hub.export import get_fact_view
from hub_isolated import isolated_hub
from structural_extract import extract


def _norm(name, content, source, doc):
    return {"kind": "field", "name": name, "content": content, "kb_source_type": "rfc",
            "protocol": doc, "source": source, "channel": "structural"}


def build() -> dict:
    d4 = _norm("siaddr", "siaddr | 4 | IP address of next server to use in bootstrap",
               "file:rfc2131.txt#@541", "DHCPv4")
    h2 = _norm("request-line",
               "request-line | method SP request-target SP HTTP-version CRLF | "
               "HTTP 请求行由方法、请求目标、协议版本依次以单个空格分隔组成",
               "file:rfc9112.txt#@261", "http")
    out = {}
    for tag, n in (("D4", d4), ("H2", h2)):
        fs = NM.map_norm_to_facts(n)
        out[tag] = {"norm": n, "facts": fs}
    return out


def main() -> int:
    res = build()
    rows = []
    root = pathlib.Path(tempfile.mkdtemp(prefix="struct_"))
    fd = root / "per_source" / "facts"; fd.mkdir(parents=True)
    for tag, r in res.items():
        for f in r["facts"]:
            v = get_fact_view(f)
            rows.append({"tag": tag, "name": r["norm"]["name"],
                         "fact_id": f.fact_id, "aspect": f.fact_key.aspect,
                         "subject_type": f.fact_key.subject.type,
                         "claim_id": (v["all_claims"][0]["claim_id"]),
                         "evidence": v["all_claims"][0]["evidence_summary"],
                         "value": str(v["all_claims"][0]["value"])[:120]})
    (fd / "structural.jsonl").write_text(
        "\n".join(json.dumps(get_fact_view(f), ensure_ascii=False)
                  for r in res.values() for f in r["facts"]) + "\n", encoding="utf-8")
    with isolated_hub(root):
        loaded = HE.load_facts("DHCPv4")
        ents, _ = HE.build_entity_index(loaded)
        ep = HE.write_entity_index("DHCPv4", ents)
        back = [json.loads(x) for x in ep.read_text(encoding="utf-8").splitlines() if x.strip()]
    # 重复构建稳定性
    ids1 = [x["fact_id"] for x in rows]
    rows2 = [x["fact_id"] for tag, r in build().items() for x in
             [{"fact_id": f.fact_id} for f in r["facts"]]]
    print("facts", len(rows), "ids", ids1, "stable", ids1 == rows2,
          "entities", len(ents), "hub_read", len(loaded))
    for x in rows:
        print(" ", x["tag"], x["aspect"], x["subject_type"], x["claim_id"], x["evidence"])
    pathlib.Path("structural_closure.json").write_text(
        json.dumps({"rows": rows, "stable": ids1 == rows2, "entities": len(ents)},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
