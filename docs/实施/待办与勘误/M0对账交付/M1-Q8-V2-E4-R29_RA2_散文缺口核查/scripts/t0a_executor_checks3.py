# -*- coding: utf-8 -*-
"""T0-A 三项阻断的定点负例：提前完整性、失败对账、限域。"""
from __future__ import annotations
import json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import t0a_adapter as AC      # noqa: E402
import t0a_executor as EX     # noqa: E402

ITEMS = [{"doc": "rfc3207.txt", "entity": "STARTTLS", "meaning": "服务名为 STARTTLS",
          "constraint": "", "span": 80, "action": "MUST"}]


class Stub:
    model = ""
    def __init__(self, mode="ok", fail_at=None, meta_first=True):
        self.mode, self.fail_at, self.calls = mode, fail_at, 0
        self.meta_first = meta_first
        self.last_call_meta = None
    def chat_json(self, *, system, user, temperature, max_tokens):
        self.calls += 1
        if self.fail_at and self.calls >= self.fail_at:
            if self.mode == "timeout":
                raise TimeoutError("boom")
            if self.meta_first:      # 先拿到 usage，再解析失败
                self.last_call_meta = {"finish_reason": "stop",
                                       "input_tokens": 700, "output_tokens": 30}
            raise ValueError("JSONDecodeError: mock")
        self.last_call_meta = {"finish_reason": "stop", "input_tokens": 500, "output_tokens": 50}
        return AC.validate_response(json.dumps({"items": ITEMS}), self.last_call_meta)


def main() -> int:
    C = []

    # 1 首批成功、第二批请求前被拒 ⇒ 不得有任何 Fact/Hub 文件
    root = pathlib.Path(tempfile.mkdtemp(prefix="t0a_c1_"))
    old_in = EX.MAX_IN
    EX.MAX_IN = 3000          # 首批约 4.9k ⇒ 首批即被拒，等价于后续批次被拒
    try:
        r = EX.run("smtp", "rfc3207.txt", Stub(), root)
    finally:
        EX.MAX_IN = old_in
    facts_dir = root / "per_source" / "facts"
    hub_idx = root / "hub" / "entities.jsonl"
    C.append(("门禁拒绝：status 非 completed", r["status"] != "completed"))
    C.append(("门禁拒绝：未写任何 Fact 文件",
              not facts_dir.is_dir() or not list(facts_dir.glob("*.jsonl"))))
    C.append(("门禁拒绝：未建 Hub 索引", not hub_idx.is_file()))
    C.append(("门禁拒绝：hub_integration_success 未置真",
              not r.get("hub_integration_success")))

    # 2a 超时：guard/result 一致、billing unknown、calls=1
    r2 = EX.run("smtp", "rfc3207.txt", Stub(mode="timeout", fail_at=1),
                pathlib.Path(tempfile.mkdtemp(prefix="t0a_c2_")))
    C.append(("超时：status=request_timeout 且 calls=1",
              r2["status"] == "request_timeout" and r2.get("calls") == 1))
    C.append(("超时：billing_status=unknown", r2.get("billing_status") == "unknown"))

    # 2b JSON 无效但已收到 usage ⇒ 必须保留用量
    root3 = pathlib.Path(tempfile.mkdtemp(prefix="t0a_c3_"))
    r3 = EX.run("smtp", "rfc3207.txt", Stub(fail_at=1, meta_first=True), root3)
    gj = json.loads((root3 / "evidence" / "guard.json").read_text(encoding="utf-8"))
    C.append(("无效 JSON：billing_status=billed", r3.get("billing_status") == "billed"))
    C.append(("无效 JSON：已收到 usage 被记账", (gj.get("used_in") or 0) >= 700))
    C.append(("无效 JSON：calls 与 guard 一致", r3.get("calls") == gj.get("calls") == 1))

    # 3 限域
    for label, rootp in (("文件系统根", pathlib.Path(pathlib.Path.cwd().anchor)),
                         ("仓库根", ROOT),
                         ("正式 derived", ROOT / "derived" / "x")):
        rr = EX.run("smtp", "rfc3207.txt", Stub(), rootp)
        C.append((f"限域拒绝：{label}", rr["status"] == "preflight_failed"))

    # 4 正常路径仍可完成（临时目录属工作区）
    r4 = EX.run("smtp", "rfc3207.txt", Stub(), pathlib.Path(tempfile.mkdtemp(prefix="t0a_c4_")))
    C.append(("临时工作区可正常完成", r4["status"] == "completed"
              and r4.get("hub_integration_success") is True))

    ok = all(v for _, v in C)
    for n, v in C: print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
