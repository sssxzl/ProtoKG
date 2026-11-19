# -*- coding: utf-8 -*-
"""grammar Value 隔离兼容性（零网络）：构造→序列化→Fact→view→Hub 读回。"""
from __future__ import annotations
import json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.hub.models import (Value, Subject, Claim, Fact, Evidence)
from core.fused.hub.canonical import compute_fact_id, compute_claim_id, canonical_serialize
from core.fused.hub.export import get_fact_view
from core.fused.hub import hub_entities as HE
from hub_isolated import isolated_hub

DATA = {"rule": "request-line",
        "expr": "method SP request-target SP HTTP-version CRLF",
        "deps": ["method", "SP", "request-target", "SP", "HTTP-version", "CRLF"]}


def build():
    v = Value(type="grammar", data=DATA)
    ev = Evidence(evidence_id="e2_test", claim_id="c2_test", source_type="rfc",
                  source_id="rfc9112", document="file:rfc9112.txt#@261",
                  locator=None, quote=DATA["expr"], content_fingerprint="", extraction_fingerprint="")
    c = Claim(claim_id="c2_test", fact_id="f2_test", value=v,
              epistemic_type="normative_unspecified", authority="rfc",
              scope=None, evidence=[ev], confidence=1.0)
    from core.fused.hub.models import FactKey, ConditionAlways
    fk = FactKey(protocol="http", version="1.1",
                 subject=Subject(type="header", name="request-line"),
                 aspect="syntax", condition=ConditionAlways())
    f = Fact(fact_id=compute_fact_id(fk), fact_key=fk, claims=[c],
             resolution=None, alignments=[], metadata={})
    return v, f


def main() -> int:
    C = []
    v, f = build()
    C.append(("Value 可构造", v.type == "grammar" and v.data["rule"] == "request-line"))
    raw = canonical_serialize(v)
    C.append(("可序列化且含 rule/expr/deps",
              b"request-line" in raw and b"deps" in raw))
    C.append(("deps 顺序保留且未去重",
              json.loads(raw)["data"]["deps"] == DATA["deps"]))
    view = get_fact_view(f)
    cv = view["all_claims"][0]["value"]
    C.append(("get_fact_view 保留 type=grammar", cv["type"] == "grammar"))
    C.append(("get_fact_view 保留 data 完整",
              cv["data"]["expr"] == DATA["expr"] and cv["data"]["deps"] == DATA["deps"]))

    root = pathlib.Path(tempfile.mkdtemp(prefix="grammar_"))
    fd = root / "per_source" / "facts"; fd.mkdir(parents=True)
    (fd / "syntax.jsonl").write_text(json.dumps(view, ensure_ascii=False) + "\n", encoding="utf-8")
    with isolated_hub(root):
        loaded = HE.load_facts("http")
        ents, _ = HE.build_entity_index(loaded)
        ep = HE.write_entity_index("http", ents)
        back = [json.loads(x) for x in ep.read_text(encoding="utf-8").splitlines() if x.strip()]
    C.append(("Hub 可接收并读回", len(loaded) == 1 and loaded[0]["all_claims"][0]["value"]["type"] == "grammar"))
    C.append(("读回后 deps 未丢", loaded[0]["all_claims"][0]["value"]["data"]["deps"] == DATA["deps"]))
    v2, f2 = build()
    C.append(("重复构造身份稳定", f2.fact_id == f.fact_id))
    ok = all(x for _, x in C)
    for n, x in C: print(("PASS " if x else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
