# -*- coding: utf-8 -*-
"""byte-patch：`validate_seed` 的状态转移校验只覆盖**状态改变方法**。

★ 动因（2026-11-05）：RFC 的状态转移表（A.1/A.2）只列**改变状态**的方法
  （RTSP：SETUP / PLAY / PAUSE / RECORD / TEARDOWN）。而 DESCRIBE / OPTIONS /
  GET_PARAMETER / SET_PARAMETER 是**状态无关**方法 —— RTSP 允许在会话进行中
  随时发它们。

  ⇒ 旧实现里，只要 `trans_by_from` 对当前状态**非空**（即该状态有出边），
    就要求「该状态必须存在该方法的出边」⇒ 含 DESCRIBE/OPTIONS 的**合法**种子
    被误判为非法（实测：漏洞导向的合法攻击种子 DESCRIBE→OPTIONS→SETUP→PLAY→
    PAUSE→TEARDOWN 被整条丢弃 ⇒ 「有漏洞时应叠加更多种子」断言失效）。

  ⇒ 修法：**只对出现在状态机里的方法**（= 状态改变方法）做转移校验；
    状态无关方法**跳过状态校验**（方法白名单 / 必填头校验照旧）。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "fused" / "downstream" / "rag_seedgen.py"

OLD = '''    transitions = bundle["transitions"]
    trans_by_from: dict = {}
    for src, method, dst in transitions:
        trans_by_from.setdefault(src.upper(), set()).add((method.upper(), dst))
'''

NEW = '''    transitions = bundle["transitions"]
    trans_by_from: dict = {}
    #: ★ 2026-11-05：**状态改变方法**集合 = 出现在状态机转移里的方法。
    #:   RFC 的状态转移表（A.1/A.2）只列改变状态的方法（RTSP：SETUP / PLAY /
    #:   PAUSE / RECORD / TEARDOWN）；DESCRIBE / OPTIONS / GET_PARAMETER /
    #:   SET_PARAMETER 是**状态无关**方法 —— RTSP 允许在会话进行中随时发。
    #:   ⇒ 状态转移校验**只覆盖状态改变方法**，否则会把含 DESCRIBE/OPTIONS 的
    #:   **合法**种子误判为非法（实测：漏洞导向的合法攻击种子被整条丢弃）。
    state_changing_methods: set = set()
    for src, method, dst in transitions:
        trans_by_from.setdefault(src.upper(), set()).add((method.upper(), dst))
        if method:
            state_changing_methods.add(method.upper())
'''

OLD2 = '''        allowed = trans_by_from.get(current.upper(), set())
        if allowed:'''

NEW2 = '''        if method not in state_changing_methods:
            # 状态无关方法（DESCRIBE/OPTIONS/…）⇒ 不做状态转移校验
            continue
        allowed = trans_by_from.get(current.upper(), set())
        if allowed:'''


def main() -> None:
    text = TARGET.read_bytes().decode("utf-8")
    for name, old, new in (("状态改变方法集合", OLD, NEW),
                           ("校验范围", OLD2, NEW2)):
        cnt = text.count(old)
        if cnt != 1:
            print(f"!! 补丁「{name}」匹配数 = {cnt}（应为 1）⇒ 中止", file=sys.stderr)
            raise SystemExit(1)
        text = text.replace(old, new, 1)
        print(f"  补丁「{name}」已应用")
    TARGET.write_bytes(text.encode("utf-8"))
    ast.parse(TARGET.read_text(encoding="utf-8"))
    print("语法自检通过")


if __name__ == "__main__":
    main()
