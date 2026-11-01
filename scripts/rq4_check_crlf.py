# -*- coding: utf-8 -*-
"""scripts/rq4_check_crlf.py —— 检查目录内 .raw 是否全部为 CRLF 行尾。

**为什么需要独立脚本**：远端校验命令要经过 PowerShell → ssh → bash → python3 四层
转义，嵌套引号极易被吃掉（实测 `bash: -c: line 4: syntax error near unexpected
token '('`）。把检查逻辑放进脚本、只传目录参数，从根本上消除转义问题。

用法:
    python3 rq4_check_crlf.py <seed_dir> [<seed_dir> ...]

输出：每个目录一行 ``<dir> <bad_count>``；退出码 0 = 全部合格，1 = 有裸 LF。
"""
from __future__ import annotations

import glob
import os
import sys


def check_dir(seed_dir: str) -> tuple[int, int]:
    """返回 (种子文件数, 行尾非 CRLF 的文件数)。"""
    files = sorted(glob.glob(os.path.join(seed_dir, "*.raw")))
    bad = 0
    for path in files:
        with open(path, "rb") as fh:
            data = fh.read()
        # CRLF 文件里 \r\n 与 \n 计数相等；不等说明存在裸 LF（行尾被转换）
        if data.count(b"\r\n") != data.count(b"\n"):
            bad += 1
    return len(files), bad


def main(argv: list[str]) -> int:
    dirs = [a for a in argv[1:] if a]
    if not dirs:
        print("用法: rq4_check_crlf.py <seed_dir> [...]", file=sys.stderr)
        return 2
    rc = 0
    for d in dirs:
        total, bad = check_dir(d)
        print(f"{d} {bad}")
        if bad:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
