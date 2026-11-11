# -*- coding: utf-8 -*-
"""guard/verify_seedcheck_wiring.py —— **种子校验层的架构护栏**。

★ 为什么需要
  种子校验层（``seedcheck/``）是**产物审查器**：它**只读**中枢与种子、只出报告。
  ⇒ 一旦它开始 **import 被它校验的层**（``core.fused.downstream``），
    就会形成**反向耦合** ⇒ ① 校验逻辑可能被被校验对象的实现「带偏」
    ② 下游一改 ⇒ 校验口径悄悄变 ⇒ 失去独立审查的意义。

★ 本护栏检三条
  ① **不反向依赖**：`seedcheck/` 不得 import ``core.fused.downstream``
     （可 import ``core.fused.hub`` —— 那是**判据来源**，是允许的）
  ② **不直读知识源**：``seedcheck/`` 不得引用 ``kb/`` 路径 API
     （``kb_root`` / ``kb_source_dir`` / 字面 ``kb/``）
     ⇒ 判据必须来自**中枢**（知识源是原始底料，校验器不该直读）
  ③ **不写回**：``seedcheck/`` 不得写 ``derived/hub/`` 与 ``derived/seeds/``
     （只允许写自己的报告目录 ``seedcheck/_out/``）

★ 用法
  python guard/verify_seedcheck_wiring.py      # 退出码 0 = 合规
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDCHECK = ROOT / "seedcheck"

#: 允许的包前缀（判据来源：中枢）
ALLOWED_IMPORT_PREFIXES = ("core.fused.hub", "core.paths", "core.llm",
                           "core.fused.semantic")

#: 禁止反向依赖的包
FORBIDDEN_IMPORT_PREFIX = "core.fused.downstream"

#: 禁止引用的知识源路径 API
FORBIDDEN_KB_TOKENS = ("kb_root", "kb_source_dir", 'kb/"', "kb/'", "kb/")

#: 禁止写入的目录
FORBIDDEN_WRITE_TOKENS = ("derived/hub", "derived/seeds",
                          "derived\\hub", "derived\\seeds")

#: 允许写的目录（自己的报告目录）
ALLOWED_WRITE_PREFIX = "seedcheck/_out"

#: **写操作**标记（与目标路径同现才算违规 ⇒ 避免把只读引用误判）
WRITE_OPS = ('"w"', "'w'", '"wb"', "'wb'", '"a"', "'a'",
              "write_text", "write_bytes", "shutil.copy", "shutil.move",
              "os.replace", "unlink", "rmtree")


def _py_files() -> list[Path]:
    if not SEEDCHECK.is_dir():
        return []
    return sorted(p for p in SEEDCHECK.rglob("*.py")
                  if "__pycache__" not in p.parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="种子校验层架构护栏")
    ap.add_argument("--json", default=None, help="机器可读结果")
    args = ap.parse_args(argv)

    files = _py_files()
    if not files:
        print("== 护栏：种子校验层架构 ==")
        print("   ⚠️ seedcheck/ 不存在或无 .py ⇒ 跳过")
        return 0

    problems: list[dict] = []
    print("== 护栏：种子校验层架构 ==")
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding="utf-8")
        hits: list[str] = []

        # ① 不反向依赖 downstream
        for m in re.finditer(r"^\s*(?:from|import)\s+([\w.]+)", text, re.M):
            mod = m.group(1)
            if mod.startswith(FORBIDDEN_IMPORT_PREFIX) or \
                    f"{FORBIDDEN_IMPORT_PREFIX}." in mod:
                hits.append(f"反向依赖 {mod}")

        # ② 不直读知识源
        for tok in FORBIDDEN_KB_TOKENS:
            if tok in text:
                hits.append(f"引用知识源路径 {tok}")

        # ③ 不写回中枢/种子
        #   ★ **行级**判定：只有「同一行既出现目标路径、又出现**写操作**」才报
        #     （否则会把「只读该路径」的正常代码误判 ⇒ 护栏自身产生噪声）
        for ln in text.splitlines():
            if not any(tok in ln for tok in FORBIDDEN_WRITE_TOKENS):
                continue
            if any(op in ln for op in WRITE_OPS):
                hits.append(f"疑似写回：{ln.strip()[:60]}")

        ok = not hits
        print(f"  {rel}: {'✅ 合规' if ok else '❌ ' + '; '.join(hits)}")
        if not ok:
            problems.append({"file": rel, "hits": hits})

    print()
    if problems:
        print(f"  ❌ {len(problems)} 个文件违反架构约束")
        if args.json:
            import json
            Path(args.json).write_text(json.dumps(problems, ensure_ascii=False,
                                                  indent=2), encoding="utf-8")
        return 1
    print("  ✅ 全部合规（不反向依赖 / 不直读知识源 / 不写回中枢与种子）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
