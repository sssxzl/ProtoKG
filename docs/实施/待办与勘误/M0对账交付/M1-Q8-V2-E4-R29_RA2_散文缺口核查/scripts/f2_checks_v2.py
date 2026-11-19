# -*- coding: utf-8 -*-
"""R29-RA2/F2 补强版离线测试：9 项回归 + 失败注入 / 身份 / 来源。

0 次真实 LLM；缓存目录 monkeypatch 到临时目录。
"""
from __future__ import annotations
import hashlib, json, pathlib, sys, tempfile
WT = pathlib.Path(__file__).resolve().parents[6]
sys.path.insert(0, str(WT))
from core.fused.extraction import prose_semantics as PS  # noqa: E402


def sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class Stub:
    model = ""
    def __init__(self, fail_docs=(), empty_docs=(), raise_after=None):
        self.calls, self.docs_seen = 0, []
        self.fail_docs, self.empty_docs = set(fail_docs), set(empty_docs)
        self.raise_after = raise_after
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        if self.raise_after is not None and self.calls > self.raise_after:
            raise RuntimeError("injected failure")
        docs = [d for d in ("a.txt", "b.txt") if f"[文档 {d}]" in user]
        self.docs_seen += docs
        if any(d in self.fail_docs for d in docs):
            raise RuntimeError("injected doc failure")
        items = [{"doc": d, "entity": "E", "meaning": f"m-{d}", "span": 1,
                  "action": "MUST", "constraint": ""}
                 for d in docs if d not in self.empty_docs]
        return {"items": items}


def blocks(a="A1", b="B1", order=("a.txt", "b.txt")):
    t = {"a.txt": a, "b.txt": b}
    return [{"doc": d, "start": 1, "text": t[d], "src_sha256": sha(t[d])} for d in order]


def run(proto, bl, llm):
    return PS._extract_blocks(proto, bl, llm=llm)


def f(proto, name):
    return PS._doc_cache_file(proto, name)


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="f2v2_"))
    PS._cache_path = lambda p: tmp / f"{p}.prose.json"  # type: ignore
    C = []

    # ---- 回归 9 项 ----
    s = Stub(); run("r1", blocks(), s)
    fs = sorted((tmp / "r1.prose.d").glob("*.json"))
    C.append(("首次生成两份文档缓存", len(fs) == 2 and all(
        json.loads(x.read_text(encoding="utf-8"))["complete"] is True for x in fs)))

    run("r2", blocks(), Stub())
    s2 = Stub(); _, st2 = run("r2", blocks(), s2)
    C.append(("二次相同输入 0 调用", s2.calls == 0 and st2.get("cache_hit") is True))

    run("r3", blocks(), Stub())
    s3 = Stub(); run("r3", blocks(b="B2"), s3)
    C.append(("改一份只重抽该份", s3.calls == 1 and s3.docs_seen == ["b.txt"]))

    run("r4", blocks(), Stub())
    s4 = Stub(); _, st4 = run("r4", blocks(order=("b.txt", "a.txt")), s4)
    C.append(("顺序无关", s4.calls == 0 and st4.get("cache_hit") is True))

    run("r5", blocks(), Stub())
    old = PS.PROSE_SEMANTICS_PROMPT_VERSION
    PS.PROSE_SEMANTICS_PROMPT_VERSION = old + "-alt"
    s5 = Stub(); _, st5 = run("r5", blocks(), s5)
    PS.PROSE_SEMANTICS_PROMPT_VERSION = old
    C.append(("换 prompt 失效", s5.calls >= 1 and st5.get("cache_hit") is not True))

    legacy = tmp / "r6.prose.json"
    legacy.write_text(json.dumps({"block_hash": "x", "items": [{"doc": "a.txt"}],
                                  "complete": True}), encoding="utf-8")
    h0 = sha(legacy.read_text(encoding="utf-8"))
    s6 = Stub(); run("r6", blocks(), s6)
    C.append(("旧批次缓存（complete=true）不被消费、不被改写",
              s6.calls >= 1 and sha(legacy.read_text(encoding="utf-8")) == h0))

    C.append(("同名不同内容键不同", PS._doc_key("t", "a.txt", "sig1", "shaX", "v1")
              != PS._doc_key("t", "a.txt", "sig2", "shaX", "v1")))

    run("r7", blocks(), Stub())
    (tmp / "r7.prose.d" / "a.txt.json.tmp").write_text("{bad", encoding="utf-8")
    s7 = Stub(); run("r7", blocks(), s7)
    C.append((".tmp 不算缓存", s7.calls == 0))

    fa = tmp / "r1.prose.d" / "a.txt.json"
    h1 = sha(fa.read_text(encoding="utf-8"))
    run("r1", blocks(), Stub())
    C.append(("重复运行幂等", h1 == sha(fa.read_text(encoding="utf-8"))))

    # ---- F2-1 失败隔离 ----
    run("f1", blocks(), Stub())
    a_before = sha(f("f1", "a.txt").read_text(encoding="utf-8"))
    s8 = Stub(fail_docs={"b.txt"}); run("f1", blocks(b="B9"), s8)
    a_after = sha(f("f1", "a.txt").read_text(encoding="utf-8"))
    C.append(("A 命中 + B 失败 ⇒ A 缓存不变", a_before == a_after))
    _b9_key = PS._doc_key("f1", "b.txt", PS._block_signature(
        [{"doc": "b.txt", "start": 1, "text": "B9"}]), sha("B9"), PS.PROSE_SEMANTICS_PROMPT_VERSION)
    C.append(("B 失败不落该内容的成功缓存", (not f("f1", "b.txt").exists())
              or json.loads(f("f1", "b.txt").read_text(encoding="utf-8")).get("key") != _b9_key))
    s9 = Stub(); run("f1", blocks(b="B9"), s9)
    C.append(("下次只处理 B", s9.docs_seen == ["b.txt"]))

    import os as _os
    _os.environ["PROSE_BATCH_BLOCKS"] = "1"
    run("f2", blocks(), Stub(fail_docs={"a.txt"}))   # 单块批次 ⇒ A 失败、B 成功
    _os.environ.pop("PROSE_BATCH_BLOCKS", None)
    C.append(("A 失败 B 成功 ⇒ 只缓存 B",
              (not f("f2", "a.txt").exists()) and f("f2", "b.txt").exists()))

    run("f3", blocks(), Stub(empty_docs={"a.txt"}))
    d3 = json.loads(f("f3", "a.txt").read_text(encoding="utf-8"))
    C.append(("空结果记为 success_empty 且可消费", d3["status"] == "success_empty"
              and d3["complete"] is True))

    s10 = Stub(raise_after=0); run("f4", blocks(), s10)
    C.append(("中途异常不产生成功缓存",
              not f("f4", "a.txt").exists() or json.loads(
                  f("f4", "a.txt").read_text(encoding="utf-8"))["complete"] is not True))

    # ---- F2-3 身份参数 ----
    run("i1", blocks(), Stub())
    from core.fused.extraction import cache_key as CK
    oldpv = CK.PARSER_VERSION
    s11 = Stub()
    _k = PS._doc_key("i1", "a.txt", "sig", "shaX", oldpv + "-alt")
    C.append(("parser 版本进入键", _k != PS._doc_key("i1", "a.txt", "sig", "shaX", oldpv)))

    b1 = [{"doc": "a.txt", "start": 1, "text": "A1", "src_sha256": "s"}]
    b2 = [{"doc": "a.txt", "start": 1, "text": "A1", "src_sha256": "s"},
          {"doc": "a.txt", "start": 9, "text": "A1", "src_sha256": "s"}]
    C.append(("块边界不同 ⇒ 指纹不同",
              PS._block_signature(b1) != PS._block_signature(b2)))

    run("i2", blocks(), Stub())
    bl_same_text_new_sha = [{"doc": "a.txt", "start": 1, "text": "A1", "src_sha256": "NEW"}]
    s12 = Stub(); run("i2", bl_same_text_new_sha, s12)
    C.append(("原始 SHA 变化（块文本相同）⇒ 失效", s12.calls >= 1))

    # ---- F2-4 来源缺失/冲突 ----
    no_src = [{"doc": "a.txt", "start": 1, "text": "A1"}]
    s13 = Stub(); run("i3", no_src, s13)
    C.append(("来源 SHA 缺失 ⇒ 不命中缓存", not f("i3", "a.txt").exists()))

    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
