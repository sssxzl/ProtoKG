# -*- coding: utf-8 -*-
"""T0-A 零调用检查：载荷、分批、预算、失败门禁（不联网）。"""
from __future__ import annotations
import json, os, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import prose_semantics as PS  # noqa: E402
import t0a_adapter as AC  # noqa: E402

MAX_TOKENS = 4000
THRESHOLD = 7500
PRICE = {"in_miss": 1, "out": 4}      # CNY / 1M，空闲时段
CAP = 0.15


def payloads():
    f = ROOT / "kb/smtp/spec/rfc3207.txt"
    text = f.read_text(encoding="utf-8", errors="replace")
    blocks = PS._split_blocks(text, (len(text) // PS._MAX_BLOCK_CHARS) + 1)
    parts = [blocks[:5], blocks[5:]]
    out = []
    for part in parts:
        body = "".join(f"\n\n===== [文档 rfc3207.txt]（起始行号 {st}）=====\n{bt}"
                       for st, bt in part)
        out.append(AC.build_payload("你是协议规范分析员。只输出 JSON。", PS._PROMPT + body))
    return parts, out


class Stub:
    model = ""
    def __init__(self, content, finish="stop"):
        self.content, self.finish, self.calls = content, finish, 0
        self.last_call_meta = None
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        self.last_call_meta = {"finish_reason": self.finish,
                               "input_tokens": 100, "output_tokens": 10}
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


def main() -> int:
    C = []
    parts, pays = payloads()

    # 1-6 载荷与分批
    for p in pays:
        AC.assert_payload_ok(p, expect_max_tokens=MAX_TOKENS)
    C.append(("载荷合法：model/thinking/max_tokens/response_format",
              all(p["model"] == "deepseek-flash" and p["thinking"]["type"] == "disabled"
                  and p["max_tokens"] == 4000 and p["response_format"]["type"] == "json_object"
                  for p in pays)))
    C.append(("分批为 5+1", [len(parts[0]), len(parts[1])] == [5, 1]))

    # 显式破坏参数 ⇒ 必须抛错（网络前终止）
    bad = AC.build_payload("s", "u"); bad["thinking"] = {"type": "enabled"}
    err = False
    try:
        AC.assert_payload_ok(bad)
    except AC.PayloadError:
        err = True
    C.append(("参数不符在网络前终止", err))

    # 7 预算预检
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        toks = [len(enc.encode(p["messages"][0]["content"] + p["messages"][1]["content"])) for p in pays]
    except Exception:
        toks = [int(len(p["messages"][1]["content"]) / 3.5) for p in pays]
    worst = sum(toks) * PRICE["in_miss"] / 1e6 + 8000 * PRICE["out"] / 1e6
    C.append((f"输入 {sum(toks)} <= {THRESHOLD} 且最坏 {worst:.3f} 元 <= {CAP}",
              sum(toks) <= THRESHOLD and worst <= CAP))

    # 8 Stub：正常 JSON 可被消费
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t0a_"))
    PS._cache_path = lambda p: tmp / f"{p}.prose.json"  # type: ignore
    os.environ["PROSE_BATCH_BLOCKS"] = "5"
    blocks = [{"doc": "rfc3207.txt", "start": st, "text": bt, "src_sha256": "S"}
              for st, bt in PS._split_blocks((ROOT / "kb/smtp/spec/rfc3207.txt").read_text(encoding="utf-8"), 6)]
    ok_items = {"items": [{"doc": "rfc3207.txt", "entity": "E", "meaning": "m", "span": 1,
                           "action": "MUST", "constraint": ""}]}
    s1 = Stub(ok_items); PS._extract_blocks("ok1", blocks, llm=s1)
    C.append(("正常 JSON 被现有解析器消费", s1.calls >= 1))

    # 9 finish_reason=length 不得写完整缓存
    s2 = Stub(ok_items, finish="length"); PS._extract_blocks("len1", blocks, llm=s2)
    f = PS._doc_cache_file("len1", "rfc3207.txt")
    C.append(("length 不写 complete", (not f.is_file())
              or json.loads(f.read_text(encoding="utf-8"))["complete"] is not True))

    # 10 空串 / 纯空格 / 无效 JSON 不得 success_empty
    for name, content in (("empty", ""), ("spaces", "   "), ("badjson", "{not json")):
        s = Stub(content)
        if name == "badjson":
            s = Stub(ValueError("JSONDecodeError: mock"))
        PS._extract_blocks(f"e_{name}", blocks, llm=s)
        f = PS._doc_cache_file(f"e_{name}", "rfc3207.txt")
        good = (not f.is_file()) or json.loads(f.read_text(encoding="utf-8")).get("status") != "success_empty"
        C.append((f"{name} 不标 success_empty", good))

    # 11 第一批成功、第二批失败 ⇒ 不 complete
    class Seq(Stub):
        def chat_json(self, *, system, user, temperature, max_tokens):
            self.calls += 1
            self.last_call_meta = {"finish_reason": "stop", "input_tokens": 1, "output_tokens": 1}
            if self.calls == 1:
                return ok_items
            raise RuntimeError("second batch failed")
    PS._extract_blocks("seq1", blocks, llm=Seq(ok_items))
    f = PS._doc_cache_file("seq1", "rfc3207.txt")
    C.append(("首批成功二批失败 ⇒ 不 complete", (not f.is_file())
              or json.loads(f.read_text(encoding="utf-8"))["complete"] is not True))
    os.environ.pop("PROSE_BATCH_BLOCKS", None)

    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print(f"输入 token={sum(toks)}（{['batch1','batch2'][0]}={toks[0]}, batch2={toks[1]}）最坏费用={worst:.4f} 元")
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
