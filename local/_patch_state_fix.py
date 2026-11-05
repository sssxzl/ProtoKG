# -*- coding: utf-8 -*-
"""byte-patch（修复）：删除上次补丁残留的旧 docstring 尾部。

★ 教训（补丁脚本自检项）：OLD 必须包含**完整**待替换块，
  否则 count=1 也会留下残余 ⇒ 语法错误。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "fused" / "downstream" / "rag_seedgen.py"

OLD = '''    """

    ★★ **后期 LLM 判别的接入点**：用户要求「各源状态机都保存到中枢，
      后期让 LLM 依据我们定的规则进行判别」⇒ 本函数就是那个「判别」的落点：
      届时把这里的默认规则换成「LLM 判别结果」即可，**其它环节不必改动**。

    ★ 本期默认规则（**刻意保持现状** ⇒ 消费端产物逐字节不变）：
      ① 优先用**协议骨架**（authority=profile）那套 —— 它覆盖面最广
         （实测 rtsp：骨架 38 条 vs RFC 客户端 12 条）；
      ② 骨架没有时 ⇒ 用**全部**（去重、排序）。
    """
'''

NEW = '''    """
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
    print("残留已删除，语法自检通过")


if __name__ == "__main__":
    main()
