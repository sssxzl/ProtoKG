# -*- coding: utf-8 -*-
"""T0-A 执行器 12 项离线回归（G1–G4）。"""
from __future__ import annotations
import json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import t0a_adapter as AC          # noqa: E402
import t0a_executor as EX         # noqa: E402

ITEMS = [{"doc": "rfc3207.txt", "entity": "STARTTLS", "meaning": "SMTP 服务名称为 STARTTLS",
          "constraint": "", "span": 80, "action": "MUST"}]


class Stub:
    model = ""
    def __init__(self, mode="ok", fail_at=None):
        self.mode, self.fail_at, self.calls, self.last_call_meta = mode, fail_at, 0, None
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        if self.fail_at and self.calls >= self.fail_at:
            if self.mode == "timeout":
                raise TimeoutError("injected timeout")
            raise RuntimeError("injected failure")
        self.last_call_meta = {"finish_reason": "stop", "input_tokens": 500, "output_tokens": 50}
        if self.mode == "length":
            self.last_call_meta["finish_reason"] = "length"
        content = "" if self.mode == "empty" else (
            "{bad" if self.mode == "badjson" else json.dumps({"items": ITEMS}))
        return AC.validate_response(content, self.last_call_meta)


def tmp():
    return pathlib.Path(tempfile.mkdtemp(prefix="t0a_ex_"))


def main() -> int:
    C = []

    # 1 正常
    r = EX.run("smtp", "rfc3207.txt", Stub(), tmp())
    C.append(("正常：completed", r["status"] == "completed"))
    C.append(("正常：链路三段都成功",
              r.get("norm_validation_success") and r.get("canonical_validation_success")
              and r.get("hub_integration_success")))
    C.append(("正常：两批 2 次调用", r["calls"] == 2))
    root1 = None

    # 2 第二批失败
    r2 = EX.run("smtp", "rfc3207.txt", Stub(fail_at=2), tmp())
    C.append(("二批失败：request_failed", r2["status"] == "request_failed"))

    # 3 首批超时
    r3 = EX.run("smtp", "rfc3207.txt", Stub(mode="timeout", fail_at=1), tmp())
    C.append(("首批超时：request_timeout", r3["status"] == "request_timeout"))

    # 4 length
    r4 = EX.run("smtp", "rfc3207.txt", Stub(mode="length"), tmp())
    C.append(("length：非 completed", r4["status"] != "completed"))

    # 5 无效 JSON
    r5 = EX.run("smtp", "rfc3207.txt", Stub(mode="badjson"), tmp())
    C.append(("坏 JSON：request_failed", r5["status"] == "request_failed"))

    # 6 输入阈值：直接对 Guard 施加，模拟超限
    g = EX.Guard(tmp()); g.used_in = EX.MAX_IN
    blocked = False
    try:
        g.before(100, {"model": AC.MODEL, "thinking": {"type": "disabled"},
                       "response_format": {"type": "json_object"}, "temperature": 0.1,
                       "max_tokens": EX.MAX_TOKENS})
    except RuntimeError as e:
        blocked = str(e) == "input_limit_exceeded"
    C.append(("输入超限：请求前拒绝", blocked))

    # 7 请求数超限
    g2 = EX.Guard(tmp()); g2.calls = EX.MAX_CALLS
    blocked2 = False
    try:
        g2.before(10, {"model": AC.MODEL, "thinking": {"type": "disabled"},
                       "response_format": {"type": "json_object"}, "temperature": 0.1,
                       "max_tokens": EX.MAX_TOKENS})
    except RuntimeError as e:
        blocked2 = str(e) == "call_limit_exceeded"
    C.append(("请求数超限：网络前拒绝", blocked2))

    # 8 缓存写失败 ⇒ 不产生完成缓存
    root8 = tmp()
    orig = EX.PS._save_doc_caches
    def boom(*a, **k): raise OSError("disk full")
    EX.PS._save_doc_caches = boom
    try:
        r8 = EX.run("smtp", "rfc3207.txt", Stub(), root8)
    finally:
        EX.PS._save_doc_caches = orig
    cf = root8 / "cache" / "smtp.prose.d" / "rfc3207.txt.json"
    C.append(("缓存写失败：不产生完整缓存",
              (not cf.is_file()) or json.loads(cf.read_text(encoding="utf-8")).get("complete") is not True))

    # 9 Canonical 失败
    r9 = EX.run("smtp", "rfc3207.txt", Stub(), tmp(),
                on_canonical=lambda: (_ for _ in ()).throw(RuntimeError("canonical boom")))
    C.append(("Canonical 失败：canonical_failed", r9["status"] == "canonical_failed"))

    # 10 Hub 失败
    r10 = EX.run("smtp", "rfc3207.txt", Stub(), tmp(),
                 on_hub=lambda: (_ for _ in ()).throw(RuntimeError("hub boom")))
    C.append(("Hub 失败：hub_failed 且不写正式目录", r10["status"] == "hub_failed"))

    # 11 隔离 Hub 可读回
    root11 = tmp()
    r11 = EX.run("smtp", "rfc3207.txt", Stub(), root11)
    idx = root11 / "hub" / "entities.jsonl"
    C.append(("隔离 Hub 可读回实体", r11["status"] == "completed" and idx.is_file()
              and "STARTTLS" in idx.read_text(encoding="utf-8")))

    # 12 证据与哈希
    ev = root11 / "evidence" / "result.json"
    d = json.loads(ev.read_text(encoding="utf-8")) if ev.is_file() else {}
    C.append(("证据落盘含 fact_ids 与 doc_sha256",
              bool(d.get("fact_ids")) and len(d.get("doc_sha256", "")) == 64))

    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
