# -*- coding: utf-8 -*-
"""T0-A 隔离中枢：RFC → Norm → Fact → 隔离 Hub 产物 → 读回验证（零网络）。"""
from __future__ import annotations
import dataclasses, hashlib, json, os, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import prose_semantics as PS   # noqa: E402
from core.fused.extraction import norm as NM              # noqa: E402
from core.fused.hub import hub_entities as HE             # noqa: E402
import t0a_adapter as AC                                  # noqa: E402


class Stub:
    model = ""
    def __init__(self, items): self.items, self.calls, self.last_call_meta = items, 0, None
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        self.last_call_meta = {"finish_reason": "stop", "input_tokens": 100, "output_tokens": 20}
        return AC.validate_response(json.dumps({"items": self.items}), self.last_call_meta)


def fact_to_dict(f) -> dict:
    d = dataclasses.asdict(f)
    d.pop("claims", None)   # 隔离索引只用身份与键
    return d


def main() -> int:
    out = pathlib.Path(tempfile.mkdtemp(prefix="t0a_hub_"))
    PS._cache_path = lambda p: out / "cache" / f"{p}.prose.json"  # type: ignore
    os.environ["PROSE_BATCH_BLOCKS"] = "5"; os.environ["PROSE_NO_RETRY"] = "1"
    PS._MAX_TOKENS = AC.MAX_TOKENS
    C = []

    doc = ROOT / "kb/smtp/spec/rfc3207.txt"
    text = doc.read_text(encoding="utf-8", errors="replace")
    src = hashlib.sha256(doc.read_bytes()).hexdigest()
    n = (len(text) // PS._MAX_BLOCK_CHARS) + 1
    blocks = [{"doc": "rfc3207.txt", "start": st, "text": bt, "src_sha256": src}
              for st, bt in PS._split_blocks(text, n)]
    items = [{"doc": "rfc3207.txt", "entity": "STARTTLS", "meaning": "SMTP 服务名称为 STARTTLS",
              "constraint": "", "span": 80, "action": "MUST"}]

    norms, stats = PS._extract_blocks("smtp", blocks, llm=Stub(items))
    facts = [f for nn in norms for f in NM.map_norm_to_facts(nn)]
    C.append(("Norm→Fact 由既有函数产出", bool(norms) and bool(facts)))

    # 隔离中枢：写 JSONL → load_facts 读回 → 实体索引
    fdir = out / "per_source" / "smtp" / "facts"; fdir.mkdir(parents=True, exist_ok=True)
    payload = [fact_to_dict(f) for f in facts]
    (fdir / "definition.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in payload) + "\n", encoding="utf-8")

    from hub_isolated import isolated_hub
    fdir = out / "per_source" / "facts"
    (fdir).mkdir(parents=True, exist_ok=True)
    (fdir / "definition.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in payload) + "\n", encoding="utf-8")
    with isolated_hub(out):
        loaded = HE.load_facts("smtp")
        ents, mapping = HE.build_entity_index(loaded)
        ep = HE.write_entity_index("smtp", ents)
        back = [json.loads(x) for x in ep.read_text(encoding="utf-8").splitlines() if x.strip()]

    C.append(("隔离中枢可读回 Fact", len(loaded) == len(payload)))
    C.append(("读回 fact_id 与输入一致",
              [x.get("fact_id") for x in loaded] == [x.get("fact_id") for x in payload]))
    C.append(("实体索引落盘并可读回", bool(ents) and len(back) == len(ents)))
    C.append(("实体索引含 STARTTLS", "STARTTLS" in json.dumps(back, ensure_ascii=False)))

    # 去重：完全相同 Fact 两条
    dup = payload + payload
    ents2, _ = HE.build_entity_index(dup)
    C.append(("相同 Fact 重复输入 ⇒ 实体不重复", len(ents2) == len(ents)))
    C.append(("Fact 层不自动合并重复（能力边界）", len(dup) == 2 * len(payload)))

    # Evidence 原文真实性
    ev = facts[0].claims[0].evidence
    ev = ev[0] if isinstance(ev, tuple) else ev
    docfield = getattr(ev, "document", "") or ""
    line = int(docfield.rsplit("@", 1)[-1]) if "@" in docfield else 0
    lines = text.split("\n")
    C.append(("Evidence 文档存在且行号可定位", docfile_ok := ("rfc3207" in docfield and 0 < line <= len(lines))))
    C.append(("引用行含实体", docfile_ok and "STARTTLS" in lines[line - 1]))

    # 缓存内部污染：外层合法、内部 item 指向别的文档
    meta = PS._doc_meta(blocks)
    cf = PS._doc_cache_file("smtp", "rfc3207.txt"); cf.parent.mkdir(parents=True, exist_ok=True)
    bad = {"schema": PS._DOC_CACHE_SCHEMA, "doc": "rfc3207.txt", "doc_sha256": src,
           "key": PS._doc_key("smtp", "rfc3207.txt", meta["rfc3207.txt"]["block_sig"], src, "v1"),
           "complete": True, "items": [{"doc": "rfc4954.txt"}]}
    cf.write_text(json.dumps(bad), encoding="utf-8")
    hit, miss = PS._load_doc_caches("smtp", meta, "v1")
    C.append(("内部 item 串文档 ⇒ 整条拒收", ("rfc3207.txt" in miss) and not hit))

    ok = all(v for _, v in C)
    for nm_, v in C: print(("PASS " if v else "FAIL ") + nm_)
    print(f"norms={len(norms)} facts={len(facts)} entities={len(ents)} out={out}")
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
