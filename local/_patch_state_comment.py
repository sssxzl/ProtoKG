# -*- coding: utf-8 -*-
"""byte-patch：更新 assemble_bundle 里关于状态机择一的过时注释。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "fused" / "downstream" / "rag_seedgen.py"

OLD = '''    #   ★ 当前默认采用**协议骨架**（profile）那套：它是「跨实验复用的协议结构」，
    #     覆盖面最广（rtsp 38 条 vs RFC 客户端 12 条）⇒ 保持现有产物不变。
    #   ★ 后期 LLM 判别时**只需替换 `_select_active_transitions()`** 这一个函数。
'''

NEW = '''    #   ★ 当前采用规则见 `_select_active_transitions()`：**规范原生（rfc）优先，
    #     协议骨架兜底**（2026-11-05 修正）。旧规则是「骨架优先」⇒ RTSP 采用了
    #     骨架那 38 条 SIP 式状态名的边（RFC 原文命中 0/6）⇒ 种子状态路径
    #     精确率 **0%**；改用 RFC 原生那 14 条 ⇒ 精确率 **100%**
    #     （依据：``local/状态机消费口径对照实验报告.md``）。
    #   ★ 后期 LLM 判别时**只需替换 `_select_active_transitions()`** 这一个函数。
'''


def main() -> None:
    text = TARGET.read_bytes().decode("utf-8")
    cnt = text.count(OLD)
    if cnt != 1:
        print(f"!! 匹配数 = {cnt}（应为 1）⇒ 中止", file=sys.stderr)
        raise SystemExit(1)
    text = text.replace(OLD, NEW, 1)
    TARGET.write_bytes(text.encode("utf-8"))
    ast.parse(TARGET.read_text(encoding="utf-8"))
    print("注释已更新，语法自检通过")


if __name__ == "__main__":
    main()
