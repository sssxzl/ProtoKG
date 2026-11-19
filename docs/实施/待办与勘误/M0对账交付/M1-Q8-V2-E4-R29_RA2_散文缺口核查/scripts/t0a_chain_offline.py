# -*- coding: utf-8 -*-
"""T0-A 全链路离线集成：RFC → 六块 → 隔离客户端 → Raw → Norm → Fact → Canonical。

零网络。所有断言针对真实中间产物（norm 字典、Fact 对象、缓存文件），不看调用次数。
"""
from __future__ import annotations
import json, os, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import prose_semantics as PS   # noqa: E402
from core.fused.extraction import norm as NM              # noqa: E402
import t0a_adapter as AC                                  # noqa: E402

DOC = pathlib.Path("kb/smtp/spec/rfc3207.txt")
PROTO = "smtp"


def load_blocks():
    text = (ROOT / DOC).read_text(encoding="utf-8", errors="replace")
    src = __import__("hashlib").sha256((ROOT / DOC).read_bytes()).hexdigest()
    n = (len(text) // PS._MAX_BLOCK_CHARS) + 1
    return [{"doc": "rfc3207.txt", "start": st, "text": bt, "src_sha256": src}
            for st, bt in PS._split_blocks(text, n)], src


def stub_items(entity="STARTTLS", span=80):
    return {"items": [{"doc": "rfc3207.txt", "entity": entity,
                       "meaning": "SMTP 服务名称为 STARTTLS",
                       "constraint": "", "span": span, "action": "MUST"}]}


class Client:
    """确定性替身：走与真实适配器相同的 validate_response。"""
    model = ""
    def __init__(self, payload=None, finish="stop", exc=None):
        self.payload, self.finish, self.exc = payload, finish, exc
        self.calls = 0
        self.last_call_meta = None
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        if int(max_tokens) != AC.MAX_TOKENS:
            raise AC.PayloadError(f"max_tokens={max_tokens} 不符合固定值")
        self.last_call_meta = {"finish_reason": self.finish,
                               "input_tokens": 4000, "output_tokens": 100}
        if self.exc:
            raise self.exc
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return AC.validate_response(content, self.last_call_meta)


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t0a_chain_"))
    PS._cache_path = lambda p: tmp / f"{p}.prose.json"  # type: ignore
    os.environ["PROSE_BATCH_BLOCKS"] = "5"
    os.environ["PROSE_NO_RETRY"] = "1"     # T0-A：禁止链路内重试
    # T0-A 固定单次 4000：链路内 payload 由该常量决定，隔离运行才可改
    PS._MAX_TOKENS = AC.MAX_TOKENS
    blocks, src = load_blocks()
    C = []

    # 1 正常路径：真实 norms + facts
    cli = Client(stub_items())
    norms, stats = PS._extract_blocks(PROTO, blocks, llm=cli)
    facts = [f for n in norms for f in NM.map_norm_to_facts(n)]
    ok_norm = [n for n in norms if n.get("kind") == "prose_semantics"]
    C.append(("产出 prose_semantics Norm", len(ok_norm) >= 1))
    C.append(("Norm 带来源与文档", all("rfc3207" in (n.get("source") or "") for n in ok_norm)))
    C.append(("Norm 映射出 Canonical Fact", len(facts) >= 1))
    ev = [c.evidence for f in facts for c in (f.claims or []) if getattr(c, "evidence", None)]
    C.append(("Fact 有 aspect 且 Claim 带 Evidence",
              bool(facts) and all(getattr(f.fact_key, "aspect", "") for f in facts) and bool(ev)))
    if facts:
        print("  fact aspect=", facts[0].fact_key.aspect,
              "| claims=", len(facts[0].claims or []),
              "| evidence_id=", getattr(ev[0], "evidence_id", None) if ev else None,
              "| ev.doc=", getattr(ev[0], "document", None) if ev else None)

    # 2 缓存：全成功后完整，二次命中，身份一致
    f = PS._doc_cache_file(PROTO if PROTO != "smtp" else "smtp", "rfc3207.txt")
    d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    C.append(("六块完成后写完整缓存", d.get("complete") is True))
    C.append(("缓存 doc_sha256 == 原文 SHA", d.get("doc_sha256") == src))
    cli2 = Client(stub_items()); norms2, st2 = PS._extract_blocks(PROTO, blocks, llm=cli2)
    C.append(("同输入二次命中（0 调用且复用条目）", cli2.calls == 0 and len(norms2) == len(norms)))

    # 3 异常：不接受任何"伪装成功"
    cases = [("空串", Client("", finish="stop")),
             ("纯空格", Client("   ", finish="stop")),
             ("非法 JSON", Client("{bad", finish="stop")),
             ("Schema 不符", Client('{"items":"nope"}')),
             ("length", Client(stub_items(), finish="length"))]
    for name, c in cases:
        ns, st = PS._extract_blocks(f"x_{name}", blocks, llm=c)
        cache_f = PS._doc_cache_file(f"x_{name}", "rfc3207.txt")
        complete = (json.loads(cache_f.read_text(encoding="utf-8")).get("complete")
                    if cache_f.is_file() else False)
        C.append((f"{name} 不产 Norm 且不写完整缓存", len(ns) == 0 and complete is not True))

    # 4 首批成功、次批失败
    class Seq(Client):
        def chat_json(self, **kw):
            if self.calls >= 1:            # 第二次及以后的任何调用都失败
                self.calls += 1
                raise RuntimeError("batch2 failed")
            return super().chat_json(**kw)
    _seq = Seq(stub_items())
    ns, st = PS._extract_blocks("seq", blocks, llm=_seq)
    cf = PS._doc_cache_file("seq", "rfc3207.txt")
    C.append(("一批成功二批失败 ⇒ 无完整缓存且只发 2 次",
              (not cf.is_file()
               or json.loads(cf.read_text(encoding="utf-8"))["complete"] is not True)
              and _seq.calls == 2))

    # 5 缓存内部 doc 归属错误 ⇒ 拒收
    f5 = PS._doc_cache_file("mis", "rfc3207.txt"); f5.parent.mkdir(parents=True, exist_ok=True)
    meta = PS._doc_meta(blocks)
    bad = {"schema": PS._DOC_CACHE_SCHEMA, "doc": "other.txt",
           "doc_sha256": src,
           "key": PS._doc_key("mis", "rfc3207.txt", meta["rfc3207.txt"]["block_sig"], src, "v"),
           "complete": True, "items": []}
    f5.write_text(json.dumps(bad), encoding="utf-8")
    hit, miss = PS._load_doc_caches("mis", meta, "v")
    C.append(("缓存 doc 归属错误 ⇒ 拒收", ("rfc3207.txt" in miss) and not hit))

    # 6 来源 SHA 冲突 ⇒ 不写有效缓存
    clash = [dict(b) for b in blocks[:2]] + [dict(blocks[2], src_sha256="OTHER")] + \
            [dict(b) for b in blocks[3:]]
    ns, st = PS._extract_blocks("clash", clash, llm=Client(stub_items()))
    C.append(("来源冲突 ⇒ 不写有效缓存", not PS._doc_cache_file("clash", "rfc3207.txt").is_file()))

    # 7 Gold：只报块覆盖，不冒充命中
    text = (ROOT / DOC).read_text(encoding="utf-8", errors="replace").split("\n")
    cover = all(any(b["start"] <= ln <= b["start"] + b["text"].count("\n") for b in blocks)
                for ln in (30, 33))
    C.append(("两条 Gold 跨度落在块内", cover))

    os.environ.pop("PROSE_BATCH_BLOCKS", None)
    os.environ.pop("PROSE_NO_RETRY", None)
    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print(f"norm={len(norms)} prose={len(ok_norm)} fact={len(facts)}")
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
