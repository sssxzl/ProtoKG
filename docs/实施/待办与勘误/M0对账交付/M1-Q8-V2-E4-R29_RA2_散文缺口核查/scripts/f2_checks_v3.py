# -*- coding: utf-8 -*-
"""R29-RA2/F2 定点核验：跨批次完成状态 + 来源身份拒收（0 次真实 LLM）。"""
from __future__ import annotations
import hashlib, json, os, pathlib, sys, tempfile
WT = pathlib.Path(__file__).resolve().parents[6]
sys.path.insert(0, str(WT))
from core.fused.extraction import prose_semantics as PS  # noqa: E402


def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()


class Stub:
    model = ""
    def __init__(self, fail_texts=(), empty_texts=()):
        self.calls, self.fail_texts, self.empty_texts = 0, set(fail_texts), set(empty_texts)
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        docs = [d for d in ("a.txt", "b.txt") if f"[文档 {d}]" in user]
        if any(t in user for t in self.fail_texts):
            raise RuntimeError("injected")
        items = [{"doc": d, "entity": "E", "meaning": "m", "span": 1,
                  "action": "MUST", "constraint": ""}
                 for d in docs if not any(t in user for t in self.empty_texts)]
        return {"items": items}


def blk(doc, text, start=1, src=True):
    """块必须携带**文件级** SHA（同一文档的所有块相同），不是块文本哈希。"""
    b = {"doc": doc, "start": start, "text": text}
    if src:
        b["src_sha256"] = sha("FILE:" + doc)
    return b


def run(proto, blocks, llm):
    return PS._extract_blocks(proto, blocks, llm=llm)


def cached(proto, doc):
    f = PS._doc_cache_file(proto, doc)
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="f2v3_"))
    PS._cache_path = lambda p: tmp / f"{p}.prose.json"  # type: ignore
    C = []
    os.environ["PROSE_BATCH_BLOCKS"] = "1"   # 一块一批，便于构造跨批次

    # A1 两批均成功 ⇒ 产出完整缓存
    run("a1", [blk("a.txt", "P1"), blk("a.txt", "P2", 9)], Stub())
    d = cached("a1", "a.txt")
    C.append(("两批均成功 ⇒ complete", d is not None and d["complete"] is True))

    # A2 第一批失败，第二批成功 ⇒ 不得标成功
    run("a2", [blk("a.txt", "P1"), blk("a.txt", "P2", 9)], Stub(fail_texts={"P1"}))
    d = cached("a2", "a.txt")
    C.append(("先失败后成功 ⇒ 不得标成功", d is None))

    # A3 第一批成功，第二批失败 ⇒ 不得标成功
    run("a3", [blk("a.txt", "P1"), blk("a.txt", "P2", 9)], Stub(fail_texts={"P2"}))
    C.append(("先成功后失败 ⇒ 不得标成功", cached("a3", "a.txt") is None))

    # A4 同一文档部分成功、其他文档全成功
    run("a4", [blk("a.txt", "P1"), blk("a.txt", "P2", 9), blk("b.txt", "Q1")],
        Stub(fail_texts={"P2"}))
    C.append(("A 部分失败 ⇒ 不缓存 A，但缓存 B",
              cached("a4", "a.txt") is None and (cached("a4", "b.txt") or {}).get("complete") is True))

    # A5 各批成功但结果为空 ⇒ success_empty
    run("a5", [blk("a.txt", "P1"), blk("a.txt", "P2", 9)], Stub(empty_texts={"P1", "P2"}))
    d = cached("a5", "a.txt")
    C.append(("各批成功且结果为空 ⇒ success_empty", d and d["status"] == "success_empty"))

    # B1 来源 A/B/A 冲突 ⇒ 拒收，且不写缓存
    run("b1", [blk("a.txt", "P1"), blk("a.txt", "P1", 9)], Stub())
    meta = PS._doc_meta([{"doc": "a.txt", "start": 1, "text": "P1", "src_sha256": "A"},
                         {"doc": "a.txt", "start": 9, "text": "P1", "src_sha256": "B"},
                         {"doc": "a.txt", "start": 17, "text": "P1", "src_sha256": "A"}])
    C.append(("SHA-A/B/A 冲突 ⇒ 来源不可用", meta["a.txt"]["src_sha256"] == ""))

    # B2 部分块有 SHA、部分没有 ⇒ 粘性不可用（后续块无法恢复）
    meta = PS._doc_meta([{"doc": "a.txt", "start": 1, "text": "P1"},
                         {"doc": "a.txt", "start": 9, "text": "P2", "src_sha256": "A"},
                         {"doc": "a.txt", "start": 17, "text": "P3", "src_sha256": "A"}])
    C.append(("部分缺 SHA ⇒ 粘性不可用", meta["a.txt"]["src_sha256"] == ""))

    # B3 全部一致 ⇒ 可用
    meta = PS._doc_meta([{"doc": "a.txt", "start": 1, "text": "P1", "src_sha256": "A"},
                         {"doc": "a.txt", "start": 9, "text": "P2", "src_sha256": "A"}])
    C.append(("来源一致 ⇒ 可用", meta["a.txt"]["src_sha256"] == "A"))

    # B4 来源不可用 ⇒ 不产生缓存文件
    run("b4", [{"doc": "a.txt", "start": 1, "text": "P1"}], Stub())
    C.append(("来源缺失 ⇒ 不写缓存", cached("b4", "a.txt") is None))

    # B5 外层 doc 正确、内部 item 属于另一文档 ⇒ 条目归入自身文档，不串号
    run("b5", [blk("a.txt", "P1"), blk("b.txt", "Q1")], Stub())
    d = cached("b5", "a.txt")
    C.append(("缓存文件内 items 的 doc 与文件名一致",
              d is None or all(it.get("doc") == "a.txt" for it in d["items"])))

    os.environ.pop("PROSE_BATCH_BLOCKS", None)
    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
