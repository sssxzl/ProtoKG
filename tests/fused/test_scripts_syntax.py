# -*- coding: utf-8 -*-
"""tests/fused/test_scripts_syntax.py —— scripts/ 下所有脚本必须语法合法。

为什么需要这一条
----------------
`scripts/seedgen.py` 等脚本是**子进程**被调用的（不是被 import 的），
所以它们的**语法错误不会在 import 期暴露**，只会在 pytest 里表现为
「某个 rq3 用例莫名失败」—— 根因极难一眼看出。

实测踩过一次：用 heredoc 打补丁时把 ``"\\n"`` 写成了字面量 ``/n``，
产出 ``if do_endpoint:/n    msg.url = ...`` → `ast.parse` 直接 SyntaxError，
连带让 ``test_rq3_manifest.py::test_cli_no_manifest_without_flag`` 多出一个失败
（failed 37 → 38），看起来像"契约回归"，实则是脚本语法错。

所以这里加一条**独立、廉价、零副作用**的前置闸：任何 `scripts/*.py` 语法错，
都会以一条清晰的失败呈现，而不是伪装成别的用例失败。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"


def test_scripts_dir_exists():
    """前置断言：scripts/ 目录存在（否则下面的 glob 会空转、闸形同虚设）。"""
    assert SCRIPTS_DIR.is_dir(), f"scripts/ 目录不存在: {SCRIPTS_DIR}"


def test_all_scripts_parse():
    """scripts/ 下所有 .py 必须能 ast.parse —— 语法错立即暴露，不伪装成别的用例失败。"""
    files = sorted(SCRIPTS_DIR.glob("*.py"))
    assert files, "scripts/ 下没有 .py 脚本（闸形同虚设？）"

    bad: list[str] = []
    for f in files:
        try:
            ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as exc:
            bad.append(f"{f.name}:{exc.lineno} {exc.msg}")
    assert not bad, "scripts/ 下存在语法错误:\n" + "\n".join(bad)


def test_shell_scripts_use_lf_line_endings():
    """scripts/ 下所有 **.sh** 必须是 LF 行尾（**硬断言**）。

    ★ 为什么 .sh 硬断言、.py 不硬断言（2026-11-01 定稿）：
      · `.sh` 在 Linux 上执行，CRLF 会让 bash 报
        `syntax error near unexpected token 'in\r'` → **真会炸**，必须挡住。
        （本仓的 .sh 脚本此前就踩过这个坑，已全部规范为 LF。）
      · `.py` 的 CRLF 对 Python **语义无害**（Python 解析器接受 CRLF），
        且仓库 `core.autocrlf=true` → `git checkout --` 会把仓库里存的 LF blob
        **物化成 CRLF** 落盘（`git diff` 仍干净，因为 git 会归一化）。
        ⇒ 对 .py 硬断言 CRLF 必然**偶发误报**（任何一次 checkout 都会触发），
        会把"验收 failed 数"搅成不稳定值。
        故 .py 只做**信息性检查**（见 test_python_scripts_crlf_report）。
        根治办法是加 `.gitattributes`（`*.py text eol=lf`），属仓库级策略，
        不在本测试范围内。
    """
    crlf_files: list[str] = []
    for f in sorted(SCRIPTS_DIR.glob("*.sh")):
        if b"\r\n" in f.read_bytes():
            crlf_files.append(f.name)
    assert not crlf_files, "scripts/ 下存在 CRLF 行尾的 .sh（Linux 上会语法错）: " \
                           + ", ".join(crlf_files)


def test_python_scripts_crlf_report():
    """`.py` 的 CRLF 只**报告**不失败（原因见上条测试的说明）。

    用 `print` 而非断言：仓库 `core.autocrlf=true` 下 CRLF 会被 checkout 物化，
    硬断言会把验收的 failed 数搅成不稳定值。这里把清单打出来供人工处理。

    ★ 附还原方法（实测有效，engineer-12 提供）::

        raw = p.read_bytes(); p.write_bytes(raw.replace(b"\\r\\n", b"\\n"))
        # 校验：还原后应与 git show HEAD:<file> 逐字节相同

      ⚠ 但**不要在别人正在改的文件上做**（还原会覆盖在飞改动）——
      先确认该文件不在 `git status` 的 ` M` 列表里。
    """
    crlf_files = [f.name for f in sorted(SCRIPTS_DIR.glob("*.py"))
                  if b"\r\n" in f.read_bytes()]
    if crlf_files:
        print("\n[信息] scripts/ 下存在 CRLF 行尾的 .py（无害，但建议转 LF；"
              "根治需 .gitattributes 的 '*.py text eol=lf'）: "
              + ", ".join(crlf_files))
        print("       还原: raw = p.read_bytes(); "
              "p.write_bytes(raw.replace(b'\\r\\n', b'\\n'))"
              "   （先确认该文件不在 git status 的 ' M' 列表里）")
