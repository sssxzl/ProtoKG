# -*- coding: utf-8 -*-
"""byte-patch：更新两条「守旧行为」的状态机测试断言。

★ 这两条测试守的是**旧规则**（采用协议骨架那套），而 2026-11-05 的对照实验
  已用外部真值（RFC 2326 A.1+A.2 共 14 条边）证明旧规则导致种子状态路径
  精确率 **0%**，改用规范原生那套后 **100%**
  （依据：``local/状态机消费口径对照实验报告.md``）。
  ⇒ 断言改为守**新规则**，并保留「LLM 判别接入点」这条设计不变式。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests" / "fused" / "test_all_sources_state_machines.py"

OLD1 = '''def test_active_transitions_unchanged(bundle):
    """★ `transitions` 仍是**当前采用的一套**（本期 = 协议骨架那套）。"""
    by_src = bundle.get("transitions_by_source") or {}
    profile_rows = by_src.get("profile") or []
    assert profile_rows, "协议骨架那套不在（本期采用它）"
    assert set(bundle["transitions"]) == set(
        tuple(r) for r in profile_rows), "采用的一套与协议骨架不一致"
'''

NEW1 = '''def test_active_transitions_prefers_rfc_native(bundle):
    """★ `transitions` = **当前采用的一套** = **规范原生（rfc）优先**。

    ★ 2026-11-05 修正（旧断言守的是「协议骨架优先」，已推翻）：
      协议骨架那套的 6 个状态名（Idle/Registered/…）在 RFC 2326 原文中
      **0/6 命中**（是 `source_autoseeder` 提示词里硬塞的 SIP 式范例）
      ⇒ 旧规则下种子的状态路径精确率 **0%**；改用 RFC 原生那套后 **100%**
      （依据：`local/状态机消费口径对照实验报告.md`）。
    """
    by_src = bundle.get("transitions_by_source") or {}
    rfc_rows = by_src.get("rfc") or []
    assert rfc_rows, "RFC 源那套不在（rtsp 开了 enable_transitions）"
    assert set(bundle["transitions"]) == set(
        tuple(r) for r in rfc_rows), "采用的一套与 RFC 源不一致"
    # ★ 两套状态名**不得并存**（并存 ⇒ LLM 在两套间摇摆 ⇒ 精确率/召回率双 0）
    prof_states = {s for r in by_src.get("profile") or [] for s in (r[0], r[2])}
    rfc_states = {s for r in rfc_rows for s in (r[0], r[2])}
    assert not (prof_states & rfc_states), \\
        f"两套状态名并存了：{sorted(prof_states & rfc_states)}"
'''

OLD2 = '''    fn = RS._select_active_transitions
    assert callable(fn)
    # 当前默认：优先协议骨架那套
    by_src = {"profile": [("Init", "SETUP", "Ready")],
              "rfc": [("A", "B", "C")]}
    assert fn(by_src) == [("Init", "SETUP", "Ready")]
    # 没有协议骨架时 ⇒ 用全部
    assert fn({"rfc": [("A", "B", "C")]}) == [("A", "B", "C")]
    # 空输入不炸
    assert fn({}) == []
'''

NEW2 = '''    fn = RS._select_active_transitions
    assert callable(fn)
    # 当前默认（2026-11-05 修正）：**规范原生（rfc）优先**，协议骨架兜底
    by_src = {"profile": [("Init", "SETUP", "Ready")],
              "rfc": [("A", "B", "C")]}
    assert fn(by_src) == [("A", "B", "C")]
    # 没有规范原生那套时 ⇒ 回退协议骨架
    assert fn({"profile": [("Init", "SETUP", "Ready")]}) == [
        ("Init", "SETUP", "Ready")]
    # 两者都没有 ⇒ 用全部（去重、排序）
    assert fn({"traffic": [("X", "Y", "Z")]}) == [("X", "Y", "Z")]
    # 空输入不炸
    assert fn({}) == []
'''


def main() -> None:
    text = TARGET.read_bytes().decode("utf-8")
    for name, old, new in (("采用规则断言", OLD1, NEW1),
                           ("LLM 接入点断言", OLD2, NEW2)):
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
