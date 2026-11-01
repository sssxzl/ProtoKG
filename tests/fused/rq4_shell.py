# -*- coding: utf-8 -*-
"""tests/fused/rq4_shell.py —— 在本机（Windows）可靠地驱动 **bash** 跑生产脚本里的 shell 函数。

★ 为什么要这个模块
------------------
部分回归测试要**直接驱动 shell 函数**（如 ``rq4_collect.sh`` 的
``cov_last_row()``）：把生产脚本里的函数体抽出来 source 进独立 shell，
这样测的是**生产代码本身**，而不是在 Python 里重写一遍逻辑。

在 Windows 上有两个坑：

1. **路径**：``bash``（Git for Windows / PortableGit）是 MSYS2 环境，
   认不出 ``C:\\Users\\...`` 这种 Windows 路径 → 必须转 POSIX（``/c/Users/...``）。
2. **沙箱偶发拦截**：本机沙箱会**间歇性**拦截 bash 子进程，表现为
   返回码非 0 + stderr 出现非 UTF-8 乱码，且**与被测逻辑无关**。

★ 关键：用**金丝雀（canary）**区分"环境坏了"与"逻辑不对"
------------------------------------------------------
防御性用例的期望值常常就是**空串**（如"文件不存在 → 返回空"）。
若 bash 根本没跑起来，它也返回空 → 用例会**假绿**（看着过了，其实没验到东西）。

故本模块的做法是：
* 先跑一次**金丝雀**（与被测调用**同形态**：脚本文件 + 路径参数）；
* 金丝雀都跑不通 → 判定"环境不可用" → ``pytest.skip``（**明确跳过，不假绿**）；
* 金丝雀通过 → bash 是好的 → 脚本的返回值就是**真实结果**，照常断言。

★ 金丝雀必须与被测调用**同形态**（参数个数 + 路径形态都一致）
----------------------------------------------------------
只跑 ``bash -c 'echo X'`` 证明不了两件事：
  ① bash 能否按**路径**找到脚本文件；
  ② bash 能否读到**作为参数传进去的路径文件**（MSYS2 的路径坑就出在这里）。
若金丝雀形态与被测调用不同，就会出现「金丝雀通过 → 实际脚本却跑不起来」的假绿。
故金丝雀脚本**放在被测脚本同目录**，并以**同样的路径形态**传参。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

#: 金丝雀标记（金丝雀命令必须原样输出它）
CANARY = "__RQ4_BASH_CANARY__"

#: 单次用例最多尝试的次数（吸收沙箱偶发拦截）
MAX_ATTEMPTS = 4


def _to_posix(path_str: str) -> str:
    """Windows 绝对路径 → MSYS2 认得的 POSIX 路径。

    ``C:\\Users\\x\\a.sh`` → ``/c/Users/x/a.sh``
    其它（已是 POSIX / 相对路径 / 非路径）→ 原样返回。
    """
    if not path_str or not os.path.isabs(path_str):
        return path_str
    p = path_str.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        return "/" + p[0].lower() + p[2:]
    return p


def _run_raw(args: list[str], cwd: str | None) -> subprocess.CompletedProcess:
    """跑一次 bash（**仅转换参数里的路径**；文本解码放宽）。

    ★ 可执行文件路径**绝不转换** ——
      bash.EXE 在 ``D:\\...\\bash.EXE``，转成 POSIX（``/d/...``）后
      Windows 侧找不到该文件 → ``FileNotFoundError``。
      只有**传给脚本的参数**（脚本文件、CSV 文件）才需要 POSIX 化。
    """
    exe, *script_args = args
    posix_args = [
        _to_posix(a) if (isinstance(a, str) and len(a) >= 3
                         and a[1] == ":" and a[0].isalpha()
                         and a[2] in "\\/") else a
        for a in script_args
    ]
    return subprocess.run(
        [exe, *posix_args], capture_output=True, text=True, errors="replace",
        timeout=120, cwd=cwd,
    )


def _write_canary_script(work_dir: Path) -> Path:
    """写金丝雀脚本：把第一个参数当**文件路径**读出来，证明路径参数可用。

    ★ 刻意**读一次参数里的文件** —— 只 echo 标记证明不了
      "bash 能否把路径参数正确解析到文件"（这正是 MSYS2 最容易翻车的地方）。
    """
    script = work_dir / "_rq4_canary.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        f'if [[ -r "${{1:-}}" ]]; then echo {CANARY}; else echo {CANARY}_NOPATH; fi\n',
        encoding="utf-8",
    )
    return script


def bash_usable(work_dir: Path | None = None) -> bool:
    """金丝雀：验证 bash 能以**与被测脚本相同的调用形态**跑起来。

    Args:
        work_dir: 金丝雀脚本所在目录（默认用临时目录）。

    Returns:
        True = 本机 bash 真的能跑（返回值可信）；False = 环境不可用。
    """
    bash = shutil.which("bash")
    if bash is None:
        return False
    own_tmp = work_dir is None
    tmp = work_dir or Path(tempfile.mkdtemp(prefix="rq4_canary_"))
    try:
        tmp.mkdir(parents=True, exist_ok=True)
        probe = tmp / "_rq4_probe.txt"
        probe.write_text("probe\n", encoding="utf-8")
        script = _write_canary_script(tmp)
        # 与被测调用同形态：bash <脚本文件> <路径参数>
        r = _run_raw([bash, str(script), str(probe)], str(tmp))
        return r.returncode == 0 and CANARY in r.stdout
    except OSError:
        return False
    finally:
        if own_tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def run_bash_script(script: Path, *args: str) -> str:
    """跑一个 shell 脚本并返回其 stdout（已 strip）。

    Args:
        script: 脚本路径。
        *args: 传给脚本的参数。

    Returns:
        脚本 stdout（去空白）。

    Raises:
        pytest.skip: 本机 bash 不可用（沙箱/环境问题）—— **明确跳过，不假绿**。
    """
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("环境无 bash")
    # 金丝雀与被测调用**同形态**（脚本文件 + 路径参数），且放在被测脚本同目录
    if not bash_usable(script.parent):
        pytest.skip("本机 bash 不可用（沙箱/环境问题），跳过以免假绿")

    last: subprocess.CompletedProcess | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            last = _run_raw([bash, str(script), *args], str(script.parent))
        except OSError:
            continue
        if last.returncode == 0:
            return last.stdout.strip()
        # 沙箱拦截 → 重试前先确认环境是否恢复
        if not bash_usable(script.parent):
            pytest.skip("本机 bash 被沙箱拦截，跳过以免假绿")
    # bash 一直是好的 → 这次失败是**真实的**（被测逻辑问题）→ 照常断言
    assert last is not None
    return last.stdout.strip()
