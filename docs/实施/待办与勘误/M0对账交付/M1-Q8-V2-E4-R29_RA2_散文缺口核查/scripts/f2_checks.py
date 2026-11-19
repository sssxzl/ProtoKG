# -*- coding: utf-8 -*-
"""R29-RA2/F2：文档级散文缓存离线测试（0 次真实 LLM）。"""
from __future__ import annotations
import hashlib, json, pathlib, sys, tempfile
WT = pathlib.Path(__file__).resolve().parents[6]
sys.path.insert(0, str(WT))
from core.fused.extraction import prose_semantics as PS  # noqa: E402

class Stub:
    model = ""
    def __init__(self):
        self.docs_seen, self.calls = [], 0
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        docs = [d for d in ("a.txt", "b.txt") if f"[文档 {d}]" in user]
        self.docs_seen += docs
        return {"items": [{"doc": d, "entity": "E", "meaning": f"m-{d}",
                           "span": 1, "action": "MUST", "constraint": ""} for d in docs]}

def blocks(a="A1", b="B1", order=("a.txt", "b.txt")):
    t = {"a.txt": a, "b.txt": b}
    return [{"doc": d, "start": 1, "text": t[d]} for d in order]

def run(proto, bl, llm):
    return PS._extract_blocks(proto, bl, llm=llm)

def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="f2cache_"))
    PS._cache_path = lambda proto: tmp / f"{proto}.prose.json"  # type: ignore
    C = []

    s = Stub(); run("p1", blocks(), s)
    fs = sorted((tmp / "p1.prose.d").glob("*.json"))
    C.append(("首次运行生成两份文档缓存且 complete=True",
              len(fs) == 2 and all(json.loads(f.read_text(encoding="utf-8"))["complete"] is True
                                   for f in fs)))

    s = Stub(); run("p2", blocks(), s)          # 预热
    s2 = Stub(); r2, st2 = run("p2", blocks(), s2)
    C.append(("相同输入第二次全命中（0 次调用）", s2.calls == 0 and st2.get("cache_hit") is True))

    run("p3", blocks(), Stub())
    s3 = Stub(); run("p3", blocks(b="B2"), s3)
    C.append(("改一份文档只重抽该文档", s3.calls == 1 and s3.docs_seen == ["b.txt"]))

    run("p4", blocks(), Stub())
    s4 = Stub(); _, st4 = run("p4", blocks(order=("b.txt", "a.txt")), s4)
    C.append(("输入顺序不影响身份", s4.calls == 0 and st4.get("cache_hit") is True))

    run("p5", blocks(), Stub())
    old = PS.PROSE_SEMANTICS_PROMPT_VERSION
    PS.PROSE_SEMANTICS_PROMPT_VERSION = old + "-alt"
    s5 = Stub(); _, st5 = run("p5", blocks(), s5)
    PS.PROSE_SEMANTICS_PROMPT_VERSION = old
    C.append(("换 prompt 版本导致失效", s5.calls >= 1 and st5.get("cache_hit") is not True))

    legacy = tmp / "p6.prose.json"
    legacy.write_text(json.dumps({"block_hash": "x", "items": [{"doc": "a.txt"}],
                                  "complete": False}), encoding="utf-8")
    h0 = hashlib.sha256(legacy.read_bytes()).hexdigest()
    s6 = Stub(); run("p6", blocks(), s6)
    C.append(("complete=false 历史缓存不被读取（必须重跑）、不被改写",
              s6.calls >= 1 and hashlib.sha256(legacy.read_bytes()).hexdigest() == h0))

    C.append(("同文件名不同内容键不同",
              PS._doc_key("t", "a.txt", "A1", "v1") != PS._doc_key("t", "a.txt", "A2", "v1")))

    run("p7", blocks(), Stub())
    (tmp / "p7.prose.d" / "a.txt.json.tmp").write_text("{bad", encoding="utf-8")
    s7 = Stub(); run("p7", blocks(), s7)
    C.append(("残留 .tmp 不被当作缓存", s7.calls == 0))

    fa = tmp / "p1.prose.d" / "a.txt.json"
    h1 = hashlib.sha256(fa.read_bytes()).hexdigest()
    run("p1", blocks(), Stub())
    C.append(("重复运行幂等（缓存字节不变）",
              h1 == hashlib.sha256(fa.read_bytes()).hexdigest()))

    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
