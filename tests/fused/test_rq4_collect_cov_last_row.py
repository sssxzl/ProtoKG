# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_collect_cov_last_row.py —— rq4_collect.sh 的 cov_last_row 回归测试。

★ 本文件针对一个**已被 QA 实测确认的 P0 缺陷**：
   ``rq4_collect.sh`` 的 ``cov_last_row()`` 试图从 ``cov_over_time.csv`` 的**末行**
   里找出与列名（``l_per`` / ``b_per``）相等的**字段**：

       tail -1 "$csv" | tr -d '\\r' | awk -F',' -v k="$key" '
         NR==1 { for (i=1;i<=NF;i++) { if ($i==k) { print $i; exit } } }'

   但**数据行里装的是数值，不是列名**::

       Time,l_per,l_abs,b_per,b_abs      ← 表头（第 1 行）
       1793327218,24.7,5899,15.7,2914     ← 末行（数据行）

   末行的字段是 ``1793327218 / 24.7 / 5899 / 15.7 / 2914``，
   **没有任何一个字段等于字符串 ``l_per``** → 永远匹配不上 → 函数**恒返回空串**。

   实测后果（QA 于 VM 上跑通 collect.sh 验证）：
     · ``rq4_summary.csv`` 的 ``l_per`` / ``b_per`` 两列 **6 行全部为空**
     · 下游 ``rq4_analyze.py`` 的「次要指标」表因缺 l_per → 只能输出「—」
     · **「bitmap_cvg 与 l_per 两个口径是否同向」这条论文必需的检查完全无法进行**

正确做法：先从**表头**定位列号，再按**列号**取末行的值。

建议的参考实现（QA 已在 VM 上验证：除「仅表头」需额外守卫外全部通过）::

    cov_last_row() {
      local csv="$1" key="$2"
      [[ -s "$csv" ]] || { echo ""; return; }
      local hdr col
      hdr=$(head -1 "$csv" | tr -d '\\r')
      echo "$hdr" | grep -q '^Time,' || { echo ""; return; }
      col=$(echo "$hdr" | awk -F',' -v k="$key" \\
              '{for(i=1;i<=NF;i++) if($i==k){print i; exit}}')
      [[ -n "$col" ]] || { echo ""; return; }
      # ★ 守卫：只有表头没有数据行时，`tail -1` 会把**表头**当数据行读出来
      #   （会返回列名 "l_per" 本身）→ 必须显式挡掉
      local nrows
      nrows=$(wc -l < "$csv" | tr -d ' ')
      [[ "$nrows" -ge 2 ]] || { echo ""; return; }
      tail -1 "$csv" | tr -d '\\r' | awk -F',' -v c="$col" '{print $c}'
    }

本测试文件通过**直接 source rq4_collect.sh 的函数定义**来驱动被测实现，
使回归测试与生产脚本共用同一份代码（而不是在测试里重写一遍逻辑）。

用法:
    pytest tests/fused/test_rq4_collect_cov_last_row.py -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# 允许 `from rq4_shell import ...`（本目录作为 sys.path 的一部分）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rq4_shell import run_bash_script  # noqa: E402

#: 仓库根目录（本文件在 tests/fused/ 下，向上两级）
REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECT_SH = REPO_ROOT / "scripts" / "rq4_collect.sh"

#: cov_script 的官方 CSV 样例（表头 + 若干数据行）
SAMPLE_CSV = (
    "Time,l_per,l_abs,b_per,b_abs\n"
    "1793316462,11.9,2809,7.2,1331\n"
    "1793316463,13.1,3102,7.9,1455\n"
    "1793327218,24.7,5899,15.7,2914\n"
)


def _load_cov_last_row(tmp_path: Path):
    """把 rq4_collect.sh 里的 cov_last_row 函数抽出来，source 进一个独立 shell 执行。

    ★ 刻意**不**在 Python 里重写一遍逻辑 —— 那样测的就不是生产代码了。
    """
    if not COLLECT_SH.exists():
        pytest.skip(f"找不到 {COLLECT_SH}")
    text = COLLECT_SH.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^cov_last_row\(\)\s*\{.*?^\}", text, re.MULTILINE | re.DOTALL)
    if not m:
        pytest.skip("rq4_collect.sh 里找不到 cov_last_row() 函数定义")
    fn = m.group(0)
    script = tmp_path / "fn.sh"
    script.write_text(
        "#!/bin/bash\nset -uo pipefail\n" + fn + "\n"
        'csv="$1"; key="$2"\n'
        'cov_last_row "$csv" "$key"\n',
        encoding="utf-8",
    )
    return script


def _run(script: Path, csv_path: Path, key: str) -> str:
    return run_bash_script(script, str(csv_path), key)


@pytest.fixture()
def cov_last_row_runner(tmp_path: Path):
    script = _load_cov_last_row(tmp_path)
    csv_path = tmp_path / "cov_over_time.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

    def _run_key(key: str) -> str:
        return _run(script, csv_path, key)

    return _run_key


# ---------------------------------------------------------------------------
# 缺陷复现：这两个断言在修复前**必然失败**（红）
# ---------------------------------------------------------------------------
def test_l_per_last_row_value(cov_last_row_runner):
    """末行的 l_per 必须是 24.7。

    缺陷表现：返回空串 ''。
    """
    assert cov_last_row_runner("l_per") == "24.7", (
        "cov_last_row 取不到末行的 l_per —— 它在**数据行**里找列名，"
        "而数据行装的是数值。必须改为：先由表头定位列号，再按列号取值。"
    )


def test_b_per_last_row_value(cov_last_row_runner):
    """末行的 b_per 必须是 15.7。"""
    assert cov_last_row_runner("b_per") == "15.7", (
        "cov_last_row 取不到末行的 b_per —— 同 l_per，"
        "必须按**表头列号**取值而不是按列名匹配数据行。"
    )


# ---------------------------------------------------------------------------
# 行为约束（修复后仍必须成立）
# ---------------------------------------------------------------------------
def test_missing_file_returns_empty(cov_last_row_runner, tmp_path: Path):
    """文件不存在 → 返回空串（不是报错）。"""
    script = _load_cov_last_row(tmp_path)
    missing = tmp_path / "nope.csv"
    assert _run(script, missing, "l_per") == ""


def test_empty_file_returns_empty(cov_last_row_runner, tmp_path: Path):
    """空文件 → 返回空串。"""
    script = _load_cov_last_row(tmp_path)
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert _run(script, empty, "l_per") == ""


def test_bad_header_returns_empty(cov_last_row_runner, tmp_path: Path):
    """表头不是 ``Time,l_per,...`` → 返回空串（防御非 cov_script 产物）。"""
    script = _load_cov_last_row(tmp_path)
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert _run(script, bad, "l_per") == ""


def test_header_only_returns_empty(cov_last_row_runner, tmp_path: Path):
    """只有表头没有数据行 → 返回空串（不能把表头当数据行读出列名）。"""
    script = _load_cov_last_row(tmp_path)
    hdr_only = tmp_path / "hdr.csv"
    hdr_only.write_text("Time,l_per,l_abs,b_per,b_abs\n", encoding="utf-8")
    assert _run(script, hdr_only, "l_per") == ""


def test_crlf_line_endings_supported(cov_last_row_runner, tmp_path: Path):
    """CRLF 行尾也要能取值（VM 上 git checkout 可能带 CRLF）。"""
    script = _load_cov_last_row(tmp_path)
    crlf = tmp_path / "crlf.csv"
    crlf.write_bytes(SAMPLE_CSV.replace("\n", "\r\n").encode("utf-8"))
    assert _run(script, crlf, "l_per") == "24.7"
    assert _run(script, crlf, "b_per") == "15.7"


def test_unknown_key_returns_empty(cov_last_row_runner):
    """未知列名 → 返回空串（不能误取别的列）。"""
    assert cov_last_row_runner("no_such_column") == ""


def test_takes_last_row_not_first(cov_last_row_runner, tmp_path: Path):
    """必须取**末行**（不是首行数据行）—— l_per 应为 24.7 而非 11.9。"""
    script = _load_cov_last_row(tmp_path)
    csv_path = tmp_path / "c.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    got = _run(script, csv_path, "l_per")
    assert got == "24.7", f"应取末行的 24.7，实际 {got!r}（首行是 11.9）"
