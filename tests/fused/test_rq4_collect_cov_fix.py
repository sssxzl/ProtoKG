# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_collect_cov_fix.py —— RQ4 采集链路的三项缺陷回归测试。

覆盖 QA-2 于 VM 上实测确认的三个缺陷：

* **P0（KP-1）** ``rq4_collect.sh`` 的 ``cov_last_row()`` 在**数据行**里逐字段
  匹配**列名** → 永远匹配不上 → **恒返回空串** → ``l_per`` / ``b_per`` 两列全丢
  → 论文必需的「bitmap_cvg 与 l_per 是否同向」检查完全无法进行。
* **P2（KP-2）** ``rq4_param_check.py`` 的尾部边界检查对「**服务端命令之后**
  追加选项」漏报（``... 8554 -X extra`` 判 OK）。
* **P2（KP-3）** ``rq4_collect.sh`` 的 ``docker exec cat cov_over_time.csv``
  只在容器**运行中**时执行 → 容器退出后 ``l_per`` / ``b_per`` **彻底没有来源**。

本文件通过**直接 source 生产脚本里的函数定义**来驱动被测实现
（与 QA 交付的 test_rq4_collect_cov_last_row.py 同一手法），
保证测的是**生产代码本身**，而不是在 Python 里重写一遍逻辑。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rq4_shell import run_bash_script  # noqa: E402
from scripts.rq4_param_check import (  # noqa: E402
    MISMATCH,
    OK,
    check_command_line,
    options_tail,
)

#: 被测脚本路径。
#: ★ 支持用环境变量 ``RQ4_COLLECT_SH`` 指向**副本** —— 变异测试必须走这条路径。
#:   原因（2026-10-30 真实事故）：变异测试若直接改生产脚本，恢复是**手动**步骤，
#:   中间会留下窗口期（实测 8 分钟），期间他人读到中间态 → 报出假失败。
#:   在副本上变异则**生产脚本全程零改动**，他人不可能读到中间态。
#:   默认行为不变（不设环境变量时就是生产脚本）。
COLLECT_SH = Path(
    os.environ.get("RQ4_COLLECT_SH") or (ROOT / "scripts" / "rq4_collect.sh")
)

#: 官方 cov_script 的 CSV 形态（表头 + 数据行；**数据行装的是数值，不是列名**）
SAMPLE_CSV = (
    "Time,l_per,l_abs,b_per,b_abs\n"
    "1793316462,11.9,2809,7.2,1331\n"
    "1793316463,13.1,3102,7.9,1455\n"
    "1793327218,24.7,5899,15.7,2914\n"
)


# ---------------------------------------------------------------------------
# 从生产脚本里抽取函数体并 source（测生产代码，不重写逻辑）
# ---------------------------------------------------------------------------
def _extract_function(name: str) -> str:
    text = COLLECT_SH.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(name)}\(\)\s*\{{.*?^\}}", text,
                  re.MULTILINE | re.DOTALL)
    if not m:
        pytest.skip(f"rq4_collect.sh 里找不到 {name}() 函数定义")
    return m.group(0)


def _run_shell(script: Path, *args: str) -> str:
    return run_bash_script(script, *args)


def _cov_last_row_runner(tmp_path: Path):
    """构造一个只含 cov_last_row() 的脚本，用法：runner(csv_path, key)。"""
    script = tmp_path / "cov_fn.sh"
    script.write_text(
        "#!/bin/bash\nset -uo pipefail\n" + _extract_function("cov_last_row") + "\n"
        'cov_last_row "$1" "$2"\n',
        encoding="utf-8",
    )

    def _run(csv_path: Path, key: str) -> str:
        return _run_shell(script, str(csv_path), key)

    return _run


# ---------------------------------------------------------------------------
# P0（KP-1）：cov_last_row 必须取到末行的真实数值
# ---------------------------------------------------------------------------
def test_cov_last_row_reads_l_per(tmp_path):
    """末行的 l_per 必须是 24.7（缺陷时返回空串）。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "cov_over_time.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    assert runner(csv_path, "l_per") == "24.7", (
        "cov_last_row 取不到末行的 l_per —— 它在**数据行**里找列名，"
        "而数据行装的是数值。必须改为：先由表头定位列号，再按列号取值。")


def test_cov_last_row_reads_b_per(tmp_path):
    """末行的 b_per 必须是 15.7。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "cov_over_time.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    assert runner(csv_path, "b_per") == "15.7"


def test_cov_last_row_takes_last_row_not_first(tmp_path):
    """必须取**末行**（l_per = 24.7），不是首行数据行（11.9）。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "cov_over_time.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    assert runner(csv_path, "l_per") == "24.7"


def test_cov_last_row_with_crlf(tmp_path):
    """CRLF 行尾也要能取值。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "crlf.csv"
    csv_path.write_bytes(SAMPLE_CSV.replace("\n", "\r\n").encode("utf-8"))
    assert runner(csv_path, "l_per") == "24.7"
    assert runner(csv_path, "b_per") == "15.7"


def test_cov_last_row_header_only_returns_empty(tmp_path):
    """只有表头没有数据行 → 返回空串（不能把列名 "l_per" 当数值读出来）。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "hdr.csv"
    csv_path.write_text("Time,l_per,l_abs,b_per,b_abs\n", encoding="utf-8")
    assert runner(csv_path, "l_per") == ""


def test_cov_last_row_skips_trailing_empty_value_rows(tmp_path):
    """末行该列**为空**时，要回退到最后一个有值的行（不能凭空丢测量值）。

    ★ 实测依据：VM 上 SIP 的 cov_over_time.csv 存在**整行字段全空**的采样行
      （如 ``1793322269,,,,``）—— cov_script 某些时刻没取到覆盖数据。
      若这些空行落在末尾，死盯物理末行会让 l_per/b_per **凭空消失**，
      论文必需的「两口径是否同向」检查就又做不了了。
    """
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "trailing_empty.csv"
    csv_path.write_text(
        "Time,l_per,l_abs,b_per,b_abs\n"
        "1793322212,6.5,15512,1.5,8755\n"
        "1793322269,,,,\n"          # ← cov_script 采空
        "1793322288,,,,\n"          # ← cov_script 采空
        "1793322364,6.5,15514,1.5,8768\n",
        encoding="utf-8")
    assert runner(csv_path, "l_per") == "6.5", (
        "末行该列为空时应回退到最后一个有值的行（6.5），"
        "否则 l_per/b_per 会凭空丢失")
    assert runner(csv_path, "b_per") == "1.5"


def test_cov_last_row_uses_last_row_when_it_has_a_value(tmp_path):
    """末行该列**有值**时，一律用末行（保持"终值"语义，不回退）。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "normal_last.csv"
    csv_path.write_text(
        "Time,l_per,l_abs,b_per,b_abs\n"
        "1793322212,6.5,15512,1.5,8755\n"
        "1793322364,6.6,15514,1.6,8768\n",
        encoding="utf-8")
    assert runner(csv_path, "l_per") == "6.6"
    assert runner(csv_path, "b_per") == "1.6"


def test_cov_last_row_unknown_key_returns_empty(tmp_path):
    """未知列名 → 返回空串（不能误取别的列）。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "c.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    assert runner(csv_path, "no_such_column") == ""


def test_cov_last_row_missing_file_returns_empty(tmp_path):
    """文件不存在 → 返回空串（不是报错）。"""
    runner = _cov_last_row_runner(tmp_path)
    assert runner(tmp_path / "nope.csv", "l_per") == ""


def test_cov_last_row_bad_header_returns_empty(tmp_path):
    """表头不是 ``Time,l_per,...`` → 返回空串（防御非 cov_script 产物）。"""
    runner = _cov_last_row_runner(tmp_path)
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert runner(csv_path, "l_per") == ""


# ---------------------------------------------------------------------------
# P2（KP-2）：服务端命令之后追加选项必须被判出来
# ---------------------------------------------------------------------------
RTSP_OPTIONS = "-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 5000"
RTSP_NET = "tcp://127.0.0.1/8554"
RTSP_GOOD = (
    "/home/ubuntu/aflnet/afl-fuzz -d -i /home/ubuntu/experiments/in-rtsp "
    "-x /home/ubuntu/experiments/rtsp.dict -o out-rtsp-protorag-r1 "
    f"-N {RTSP_NET} {RTSP_OPTIONS} ./testOnDemandRTSPServer 8554"
)


def test_trailing_extra_option_after_server_cmd_is_mismatch_with_reference():
    """服务端命令**之后**追加 ``-X extra`` → 有参照时必须判 MISMATCH。

    无参照时（规则 1 单容器视角）OPTIONS 窗口看不到那里 —— 那是规则的边界，
    不是缺陷；缺陷在于**没有拿参照容器比对**。本测试锁死"有参照就必须挡住"。
    """
    drifted = RTSP_GOOD + " -X extra"
    verdict, reason = check_command_line(RTSP_OPTIONS, drifted, RTSP_NET,
                                         reference_command_line=RTSP_GOOD)
    assert verdict == MISMATCH, (
        f"服务端命令之后追加选项必须判 MISMATCH，实际 {verdict}: {reason}")


def test_same_server_cmd_with_reference_is_ok():
    """命令行与服务端命令都与参照一致 → OK（不能误报）。"""
    verdict, reason = check_command_line(RTSP_OPTIONS, RTSP_GOOD, RTSP_NET,
                                         reference_command_line=RTSP_GOOD)
    assert verdict == OK, reason


def test_options_tail_isolates_server_command():
    """options_tail 必须切出 OPTIONS 之后的服务端命令部分。"""
    tail = options_tail(RTSP_GOOD, RTSP_OPTIONS, RTSP_NET)
    assert tail == "./testOnDemandRTSPServer 8554"
    # 加了尾巴 → 尾巴随之变化（这正是要比对的东西）
    assert options_tail(RTSP_GOOD + " -X extra", RTSP_OPTIONS, RTSP_NET) == \
        "./testOnDemandRTSPServer 8554 -X extra"


def test_options_tail_none_when_anchor_missing():
    """找不到锚点 → 返回 None（不瞎猜）。"""
    assert options_tail("afl-fuzz -d -i in", RTSP_OPTIONS, RTSP_NET) is None


# ---------------------------------------------------------------------------
# KP-2 接线：**不只定义接口，还要真的把参照传进去**
# ---------------------------------------------------------------------------
def test_collect_sh_wires_reference_command_line():
    """``rq4_collect.sh`` 必须把"同协议参照容器"真正接进判定调用。

    ★ 只在 Python 侧实现参照比对是不够的 —— bash 侧若没把参照传下去，
      采集时（collect.sh）就退化回"看不见服务端命令尾巴"的盲区。
      故这里直接检查生产脚本的接线：
        ① 维护一个"每协议首个容器命令行"的参照表；
        ② 调用 param_check_of 时把它作为第三个参数传进去；
        ③ param_check_of 把它转成 --reference-command-line 传给判定器。
    """
    text = COLLECT_SH.read_text(encoding="utf-8")
    # ① 参照表
    assert "PARAM_REF_CMD" in text, "collect.sh 必须维护每协议的参照命令行"
    # ② 调用点传参照
    assert re.search(r'param_check_of\s+"\$proto"\s+"\$command_line"\s+"?\$\{?PARAM_REF_CMD', text), \
        "collect.sh 调用 param_check_of 时必须传入参照命令行"
    # ③ 转发给判定器
    assert "--reference-command-line" in text, \
        "param_check_of 必须把参照命令行以 --reference-command-line 传给判定器"


def test_collect_sh_records_reference_after_first_container():
    """首个容器采集后要**记录**参照（后续容器才有参照可比）。"""
    text = COLLECT_SH.read_text(encoding="utf-8")
    assert re.search(r'PARAM_REF_CMD\["\$proto"\]\s*=', text), \
        "collect.sh 必须在采集后记录该协议的参照命令行"


def test_collect_sh_param_check_passes_third_argument():
    """param_check_of 的第三个形参是参照命令行（而不是被忽略）。"""
    body = _extract_function("param_check_of")
    assert re.search(r'local\s+proto="\$1"\s+command_line="\$2"\s+reference="\$\{3:-\}"', body), \
        "param_check_of 必须接收第三个参数作为参照命令行"
    assert "${reference:+--reference-command-line" in body, \
        "param_check_of 必须把参照转成 --reference-command-line 传给判定器"


# ---------------------------------------------------------------------------
# P2（KP-3）：容器退出后 cov_over_time.csv 仍必须有来源
# ---------------------------------------------------------------------------
def test_collect_sh_takes_cov_from_tar_for_exited_container():
    """容器已退出时，cov_over_time.csv 必须能从 tar 里取（不能只有 docker exec 一条路）。

    ★ 官方 run 脚本的收尾是 ``tar -zcvf ${WORKDIR}/${OUTDIR}.tar.gz ${OUTDIR}``，
      而 cov_over_time.csv 就产在 OUTDIR 里 → tar 内必然带得上。
    """
    text = COLLECT_SH.read_text(encoding="utf-8")
    # 退出分支必须出现 tar 路径下的 cov_over_time.csv 取用
    assert "cov_over_time.csv" in text, "collect.sh 必须处理 cov_over_time.csv"
    tar_branch = text.split("容器已退出", 1)
    assert len(tar_branch) == 2, "collect.sh 里找不到「容器已退出」分支"
    exited = tar_branch[1]
    assert "cov_over_time.csv" in exited, (
        "容器退出分支必须从 tar 里取 cov_over_time.csv"
        "（只走 docker exec 的话，容器一退出 l_per/b_per 就彻底没有来源）")


def test_collect_sh_still_has_docker_exec_path():
    """容器运行中时仍走 docker exec 取 cov_over_time.csv（两条路径都要有）。"""
    text = COLLECT_SH.read_text(encoding="utf-8")
    assert 'docker exec "$name" cat "${outdir}/cov_over_time.csv"' in text, \
        "容器运行中的 docker exec 取值路径必须保留"


# ---------------------------------------------------------------------------
# 护栏：生产脚本被回退时**立刻**失败（不让它悄悄溜过去）
# ---------------------------------------------------------------------------
def test_collect_sh_cov_last_row_is_not_reverted_to_substring_matching():
    """``cov_last_row`` 必须仍是"表头定位列号"的实现。

    ★ 这条护栏的由来（真实事故）：
      有人把本地 ``scripts/rq4_collect.sh`` 换成了"只有 cov_last_row 回退成旧实现"
      的版本 → 本机与 VM 的 md5 悄悄不一致 → QA 交付的回归测试在本机挂 5 条、
      而全量跑只挂 2 条（**因为脚本在测试跑的过程中被换掉了** → 结果不可复现）。
      有这条护栏，任何回退都会**立刻**、**确定性地**失败，而不是靠人肉比对 md5。
    """
    text = COLLECT_SH.read_text(encoding="utf-8")
    body = _extract_function("cov_last_row")
    # 旧实现（缺陷版）的**特征签名**：拿**末行**去和列名比对
    #   → 数据行装的是数值，永远匹配不上 → 恒返回空串。
    #   注意：新实现里也有 `$i==k`（那是**表头**里定位列号），
    #   所以不能拿 `$i==k` 本身当特征，必须看它跟哪个输入管道在一起。
    assert not re.search(r'tail\s+-1[^\n]*\|[^\n]*\$i==k', body), (
        "cov_last_row 被打回旧实现（拿末行去匹配列名）→ 恒返回空串，"
        "l_per/b_per 两列会全丢")
    # 新实现：先由表头定位列号，再按列号取末行的值
    assert "由表头定位列号" in body, (
        "cov_last_row 必须由表头定位列号后取值（当前实现不是修复版）")
    # 按**列号**取值（awk -v c="$col" ... {print $c}），不是按列名匹配
    assert re.search(r"-v\s+c=", body) and re.search(r"print\s+\$c", body), (
        "cov_last_row 必须按**列号** c 取值（awk -v c=... {print $c}），"
        "不是按列名匹配")


def test_collect_sh_has_no_crlf_line_endings():
    """shell 脚本必须是 LF 行尾。

    ★ CRLF 会让 bash 把 ``\\r`` 当成命令的一部分 → 脚本行为诡异
      （且会让本机与 VM 的 md5 恒不一致，掩盖真实差异）。
    """
    raw = COLLECT_SH.read_bytes()
    assert b"\r\n" not in raw, (
        f"rq4_collect.sh 存在 CRLF 行尾（{raw.count(bytes([13, 10]))} 处）"
        "—— 会被 bash 当成命令的一部分，且导致本机与 VM md5 恒不一致")


def test_local_scripts_have_no_crlf_line_endings():
    """三个 rq4 脚本都必须是 LF 行尾（与 VM 保持字节一致的前提）。"""
    for name in ("rq4_collect.sh", "rq4_analyze.py", "rq4_param_check.py"):
        path = ROOT / "scripts" / name
        if not path.exists():
            continue
        raw = path.read_bytes()
        assert b"\r\n" not in raw, f"scripts/{name} 存在 CRLF 行尾"
