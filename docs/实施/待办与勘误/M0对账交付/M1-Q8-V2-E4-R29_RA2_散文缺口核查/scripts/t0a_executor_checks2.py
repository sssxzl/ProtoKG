# -*- coding: utf-8 -*-
"""T0-A 定点负例：隔离根、真实参数、部分成功、失败证据、多 aspect、状态恢复。"""
from __future__ import annotations
import json, os, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import t0a_adapter as AC      # noqa: E402
import t0a_executor as EX     # noqa: E402
from core.fused.extraction import prose_semantics as PS  # noqa: E402

ITEMS = [{"doc": "rfc3207.txt", "entity": "STARTTLS", "meaning": "服务名为 STARTTLS",
          "constraint": "", "span": 80, "action": "MUST"},
         {"doc": "rfc3207.txt", "entity": "STARTTLS", "meaning": "客户端须先发 EHLO",
          "constraint": "客户端支持 STARTTLS", "span": 82, "action": "MUST"}]


class Stub:
    model = ""
    def __init__(self, items=ITEMS, fail_at=None, timeout_at=None):
        self.items, self.fail_at, self.timeout_at, self.calls = items, fail_at, timeout_at, 0
        self.last_call_meta = None
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        if self.timeout_at and self.calls >= self.timeout_at:
            raise TimeoutError("boom")
        if self.fail_at and self.calls >= self.fail_at:
            raise RuntimeError("boom")
        self.last_call_meta = {"finish_reason": "stop", "input_tokens": 500, "output_tokens": 50}
        return AC.validate_response(json.dumps({"items": self.items}), self.last_call_meta)


def main() -> int:
    C = []

    # 1 危险根
    for label, root in (("相对路径", "rel/tmp"),
                        ("含 ..", str(ROOT / "derived" / ".." / "x")),
                        ("受保护 derived", str(ROOT / "derived" / "t0a_x"))):
        r = EX.run("smtp", "rfc3207.txt", Stub(), root)
        C.append((f"危险根拒绝：{label}", r["status"] == "preflight_failed"))

    # Windows 无创建符号链接权限时，用确定性替身验证判定分支
    from unittest import mock
    fake = pathlib.Path(tempfile.mkdtemp()) / "lnk"
    with mock.patch.object(pathlib.Path, "is_symlink",
                           lambda self: str(self).endswith("lnk")):
        r = EX.run("smtp", "rfc3207.txt", Stub(), fake)
    C.append(("符号链接根拒绝", r["status"] == "preflight_failed"
              and "symlink" in r.get("reason", "")))

    # 2 真实参数（max_tokens 非 4000）
    g = EX.Guard(pathlib.Path(tempfile.mkdtemp()))
    bad = False
    try:
        g.before(10, {"model": AC.MODEL, "thinking": {"type": "disabled"},
                      "response_format": {"type": "json_object"},
                      "temperature": 0.1, "max_tokens": 9999})
    except Exception:
        bad = True
    C.append(("max_tokens 非 8000 在调用前拒绝", bad))

    # 3 第二批被门禁拒绝（输入上限）⇒ 不得 completed
    root3 = pathlib.Path(tempfile.mkdtemp(prefix="t0a_b3_"))
    old_in = EX.MAX_IN
    EX.MAX_IN = 10                 # 第一批估 4000+ 即超；用超小阈值模拟第二批被拒
    try:
        r3 = EX.run("smtp", "rfc3207.txt", Stub(), root3)
    finally:
        EX.MAX_IN = old_in
    hub3 = root3 / "hub" / "entities.jsonl"
    cache3 = root3 / "cache" / "smtp.prose.d" / "rfc3207.txt.json"
    C.append(("门禁拒绝批次 ⇒ 非 completed", r3["status"] != "completed"))
    C.append(("门禁拒绝 ⇒ 不建 Hub", not hub3.is_file()))
    C.append(("门禁拒绝 ⇒ 无完整缓存",
              (not cache3.is_file())
              or json.loads(cache3.read_text(encoding="utf-8")).get("complete") is not True))

    # 4 失败证据：超时后 guard/result 都在，calls 反映真实次数
    root4 = pathlib.Path(tempfile.mkdtemp(prefix="t0a_b4_"))
    r4 = EX.run("smtp", "rfc3207.txt", Stub(timeout_at=1), root4)
    gj = root4 / "evidence" / "guard.json"
    rj = root4 / "evidence" / "result.json"
    C.append(("超时：result 与 guard 均落盘", gj.is_file() and rj.is_file()))
    if gj.is_file():
        gd = json.loads(gj.read_text(encoding="utf-8"))
        C.append(("超时：calls=1 且记录尝试", gd.get("calls") == 1 and len(gd.get("log") or []) == 1))
    C.append(("超时：状态为 request_timeout", r4["status"] == "request_timeout"))

    # 5 多 aspect Fact 分文件 + Claim/Evidence 读回
    root5 = pathlib.Path(tempfile.mkdtemp(prefix="t0a_b5_"))
    r5 = EX.run("smtp", "rfc3207.txt", Stub(), root5)
    fdir = root5 / "per_source" / "facts"
    files = sorted(p.name for p in fdir.glob("*.jsonl")) if fdir.is_dir() else []
    C.append(("完成且至少一个 aspect 文件", r5["status"] == "completed" and bool(files)))
    views = []
    for p in fdir.glob("*.jsonl"):
        views += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    C.append(("落盘含 all_claims（官方契约）", all("all_claims" in v for v in views) and bool(views)))
    # 官方 view 用 evidence_summary（形如 "rfc:...@file:rfc3207.txt#@80"）
    ev_ok = any(any("@file:rfc3207.txt#@" in str(x) for x in (c.get("evidence_summary") or []))
                for v in views for c in (v.get("all_claims") or []))
    C.append(("Evidence 摘要读回含文件名与行号锚点", ev_ok))

    # 6 状态恢复：异常路径后 PS 常量与环境变量复原
    before_mt = PS._MAX_TOKENS
    before_env = os.environ.get("PROSE_NO_RETRY")
    EX.run("smtp", "rfc3207.txt", Stub(fail_at=1), pathlib.Path(tempfile.mkdtemp()))
    C.append(("异常后 PS._MAX_TOKENS 复原", PS._MAX_TOKENS == before_mt))
    C.append(("异常后 PROSE_NO_RETRY 复原", os.environ.get("PROSE_NO_RETRY") == before_env))

    # 6b 两个不同 aspect 分文件（用既有映射函数构造，不手写 Fact）
    from core.fused.extraction import norm as NM
    fld = {"norm_id": "smtp.field.starttls", "kind": "field", "name": "STARTTLS",
           "content": "STARTTLS | required: 启动 TLS 协商", "kb_source_type": "rfc",
           "source": "file:rfc3207.txt#@80", "protocol": "smtp"}
    f_field = NM.map_norm_to_facts(fld)
    aspects = {f.fact_key.aspect for f in f_field}
    d6 = pathlib.Path(tempfile.mkdtemp(prefix="t0a_asp_"))
    counts = EX.write_facts_by_aspect(f_field, d6)
    C.append((f"字段 Norm 产出两个 aspect（{sorted(aspects)}）",
              len(aspects) >= 2 and len(counts) >= 2))

    # 7 六块完整走到隔离 Hub
    C.append(("正常执行 fact 数 ≥ 1 且实体 ≥ 1",
              r5.get("facts", 0) >= 1 and r5.get("entities", 0) >= 1))

    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
