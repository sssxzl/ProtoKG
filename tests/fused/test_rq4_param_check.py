# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_param_check.py —— RQ4 参数自检（param_check）的回归测试。

背景
----
``rq4_collect.sh`` 的参数自检原先是**子串包含**判定::

    [[ "$command_line" != *"$expected"* ]] && param_ok="MISMATCH"

它挡不住两类最要命的参数漂移（QA 实跑证实）：

1. **数值漂移**：期望 ``-t 5000``、实际 ``-t 50000`` → 子串命中 → 误判 OK；
2. **尾部多选项**：实际命令行尾部多出 ``-X extra`` → 子串仍命中 → 误判 OK。

本文件覆盖：

* **规则 1**（单容器）：``rq4_param_check.check_command_line`` —— OPTIONS 段
  逐 token 序列全等（顺序 + 个数 + 每个 token 字面值）。
* **规则 2**（跨容器）：``rq4_param_check.check_command_lines_consistent`` ——
  同协议各容器 command_line（遮蔽 ``-o`` 的值后）必须逐字一致。
* **回归护栏**：``rq4_collect.sh`` 里不得再出现子串包含判定
  （防止有人"顺手改回去"）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.rq4_param_check import (  # noqa: E402
    MISMATCH,
    NO_COMMAND_LINE,
    OK,
    check_command_line,
    check_command_lines_consistent,
    mask_outdir,
)

# ---------------------------------------------------------------------------
# 真实命令行样本（取自 VM 上正在跑的 rq4_* 容器，与官方 run 脚本形态一致）
# ---------------------------------------------------------------------------
RTSP_OPTIONS = "-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 5000"
RTSP_NET = "tcp://127.0.0.1/8554"
RTSP_CMD = (
    "/home/ubuntu/aflnet/afl-fuzz -d -i /home/ubuntu/experiments/in-rtsp "
    "-x /home/ubuntu/experiments/rtsp.dict -o out-rtsp-protorag-r1 "
    f"-N {RTSP_NET} {RTSP_OPTIONS} ./testOnDemandRTSPServer 8554"
)

SIP_OPTIONS = "-m none -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -t 5000"
SIP_NET = "udp://127.0.0.1/5060"
SIP_CMD = (
    "/home/ubuntu/aflnet/afl-fuzz -d -i /home/ubuntu/experiments/in-sip "
    "-o out-sip-protorag-r1 "
    f"-N {SIP_NET} {SIP_OPTIONS} "
    "-c /home/ubuntu/experiments/run_pjsip ./src/kamailio "
    "-f /home/ubuntu/experiments/kamailio-basic.cfg -L src/modules "
    "-Y runtime_dir -n 1 -D -E"
)

SMTP_OPTIONS = "-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100 -m none -t 5000"
SMTP_NET = "tcp://127.0.0.1/25"
SMTP_CMD = (
    "/home/ubuntu/aflnet/afl-fuzz -d -i /home/ubuntu/experiments/in-smtp "
    "-x /home/ubuntu/experiments/smtp.dict -o out-smtp-protorag-r1 "
    f"-N {SMTP_NET} {SMTP_OPTIONS} "
    "-c /home/ubuntu/experiments/clean exim -bd -d -oX 25 "
    "-oP /var/lock/exim.pid"
)


# ---------------------------------------------------------------------------
# 规则 1：正常命令行必须判 OK
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("options,net,cmd", [
    (RTSP_OPTIONS, RTSP_NET, RTSP_CMD),
    (SIP_OPTIONS, SIP_NET, SIP_CMD),
    (SMTP_OPTIONS, SMTP_NET, SMTP_CMD),
])
def test_correct_command_line_is_ok(options, net, cmd):
    """完全正确的命令行必须判 OK（三个协议都要过）。"""
    verdict, reason = check_command_line(options, cmd, net)
    assert verdict == OK, f"期望 OK，实际 {verdict}: {reason}"


def test_empty_command_line_reports_no_command_line():
    """command_line 为空 → NO_COMMAND_LINE（不是 MISMATCH：容器还没产出 stats）。"""
    verdict, _ = check_command_line(RTSP_OPTIONS, "", RTSP_NET)
    assert verdict == NO_COMMAND_LINE


def test_known_good_prefix_still_matches_with_substring_style_options():
    """只给 OPTIONS（不给 net）时也应能定位锚点并判 OK。"""
    verdict, reason = check_command_line(RTSP_OPTIONS, RTSP_CMD, "")
    assert verdict == OK, reason


# ---------------------------------------------------------------------------
# 规则 1：四种反例必须全部判 MISMATCH
# ---------------------------------------------------------------------------
def test_numeric_drift_is_mismatch():
    """反例 1：数值漂移（-t 5000 → -t 50000）。

    旧实现是子串包含判定：``-t 5000`` 是 ``-t 50000`` 的子串 → 漏报。
    """
    drifted = RTSP_CMD.replace("-t 5000", "-t 50000")
    assert drifted != RTSP_CMD, "构造漂移命令行失败"
    verdict, reason = check_command_line(RTSP_OPTIONS, drifted, RTSP_NET)
    assert verdict == MISMATCH, f"数值漂移必须判 MISMATCH，实际 {verdict}: {reason}"


def test_trailing_extra_option_is_mismatch():
    """反例 2：尾部多出额外选项（``-X extra``）。

    旧实现是子串包含判定：期望 OPTIONS 仍被包含 → 漏报。
    """
    extra = RTSP_CMD.replace(
        "./testOnDemandRTSPServer 8554", "-X extra ./testOnDemandRTSPServer 8554")
    assert extra != RTSP_CMD, "构造多余选项命令行失败"
    verdict, reason = check_command_line(RTSP_OPTIONS, extra, RTSP_NET)
    assert verdict == MISMATCH, f"尾部多余选项必须判 MISMATCH，实际 {verdict}: {reason}"


def test_extra_option_in_middle_is_mismatch():
    """反例 2b：多余选项插在 OPTIONS 中间也必须判 MISMATCH。"""
    extra = RTSP_CMD.replace("-q 3", "-q 3 -X extra")
    verdict, reason = check_command_line(RTSP_OPTIONS, extra, RTSP_NET)
    assert verdict == MISMATCH, f"中间多余选项必须判 MISMATCH，实际 {verdict}: {reason}"


def test_reversed_token_order_is_mismatch():
    """反例 3：token 顺序颠倒必须判 MISMATCH。"""
    reversed_cmd = RTSP_CMD.replace("-D 10000 -q 3", "-q 3 -D 10000")
    assert reversed_cmd != RTSP_CMD, "构造顺序颠倒命令行失败"
    verdict, reason = check_command_line(RTSP_OPTIONS, reversed_cmd, RTSP_NET)
    assert verdict == MISMATCH, f"顺序颠倒必须判 MISMATCH，实际 {verdict}: {reason}"


def test_missing_token_is_mismatch():
    """反例 4：缺 token 必须判 MISMATCH。"""
    missing = RTSP_CMD.replace("-K -R ", "")
    assert missing != RTSP_CMD, "构造缺 token 命令行失败"
    verdict, reason = check_command_line(RTSP_OPTIONS, missing, RTSP_NET)
    assert verdict == MISMATCH, f"缺 token 必须判 MISMATCH，实际 {verdict}: {reason}"


def test_missing_option_from_table_is_mismatch():
    """表里多了一个选项（实际命令行没有）→ MISMATCH。"""
    expected = RTSP_OPTIONS + " -Z 9"
    verdict, reason = check_command_line(expected, RTSP_CMD, RTSP_NET)
    assert verdict == MISMATCH, f"表与实际不一致必须判 MISMATCH，实际 {verdict}: {reason}"


def test_net_mismatch_is_mismatch():
    """net 本身漂了（连锚点都对不上）→ MISMATCH。"""
    verdict, reason = check_command_line(RTSP_OPTIONS, RTSP_CMD, "tcp://127.0.0.1/9999")
    assert verdict == MISMATCH, f"net 不符必须判 MISMATCH，实际 {verdict}: {reason}"


def test_options_empty_is_mismatch():
    """参数表的 options 为空 → MISMATCH（无从比对，不能默认放行）。"""
    verdict, reason = check_command_line("", RTSP_CMD, RTSP_NET)
    assert verdict == MISMATCH, reason


# ---------------------------------------------------------------------------
# 规则 2：跨容器一致性
# ---------------------------------------------------------------------------
def test_same_protocol_consistent_command_lines_pass():
    """同协议各容器仅 ``-o`` 不同 → 遮蔽后一致 → 通过。"""
    a = RTSP_CMD.replace("out-rtsp-protorag-r1", "out-rtsp-protorag-r1")
    b = RTSP_CMD.replace("out-rtsp-protorag-r1", "out-rtsp-baseline-r1")
    consistent, reason = check_command_lines_consistent([a, b])
    assert consistent, reason


def test_cross_container_extra_option_is_detected():
    """规则 2：一个容器尾部多出 ``-X extra`` → 与同协议兄弟容器不一致 → 检出。

    这是规则 1 看不到的位置（不在 OPTIONS 窗口里），必须由规则 2 兜住。
    """
    good = RTSP_CMD.replace("out-rtsp-protorag-r1", "out-rtsp-protorag-r1")
    bad = RTSP_CMD.replace("out-rtsp-protorag-r1", "out-rtsp-baseline-r1")
    bad = bad.replace("./testOnDemandRTSPServer 8554",
                      "-X extra ./testOnDemandRTSPServer 8554")
    consistent, reason = check_command_lines_consistent([good, bad])
    assert not consistent, "跨容器多出选项必须被检出"
    assert "不一致" in reason


def test_cross_container_numeric_drift_is_detected():
    """规则 2：一个容器的数值漂了 → 与兄弟容器不一致 → 检出。"""
    good = RTSP_CMD.replace("out-rtsp-protorag-r1", "out-rtsp-protorag-r1")
    bad = RTSP_CMD.replace("out-rtsp-protorag-r1", "out-rtsp-baseline-r1")
    bad = bad.replace("-t 5000", "-t 50000")
    consistent, reason = check_command_lines_consistent([good, bad])
    assert not consistent, "跨容器数值漂移必须被检出"


def test_single_container_is_trivially_consistent():
    """只有一个容器时无从比对 → 视为一致（不误报）。"""
    consistent, reason = check_command_lines_consistent([RTSP_CMD])
    assert consistent, reason


def test_mask_outdir_only_masks_outdir_value():
    """mask_outdir 只遮蔽 ``-o`` 的**值**，其余 token 逐字保留。"""
    masked = mask_outdir(RTSP_CMD)
    assert "-o <OUTDIR>" in masked
    assert "out-rtsp-protorag-r1" not in masked
    # 其余部分必须原样保留
    assert masked.split(" ", 3)[0] == RTSP_CMD.split(" ", 1)[0]
    assert RTSP_OPTIONS in masked


def test_mask_outdir_does_not_mask_o_within_other_flags():
    """``-o`` 只作独立 token 匹配（``-oX``/``-op`` 这类不算）。"""
    masked = mask_outdir("afl-fuzz -o out-x -oX 25 -op 1")
    assert "-o <OUTDIR>" in masked
    assert "-oX 25" in masked
    assert "-op 1" in masked


# ---------------------------------------------------------------------------
# 回归护栏：rq4_collect.sh 不得再退回子串包含判定
# ---------------------------------------------------------------------------
COLLECT_SH = ROOT / "scripts" / "rq4_collect.sh"


@pytest.mark.skipif(not COLLECT_SH.exists(), reason="未找到 rq4_collect.sh")
def test_collect_sh_no_longer_uses_substring_matching():
    """rq4_collect.sh 里的参数自检必须走逐 token 全等判定，不能是子串包含。"""
    text = COLLECT_SH.read_text(encoding="utf-8")
    # 只看**真正的代码行**（剔除注释行），避免误伤说明性注释
    code = "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("#"))
    # 旧的子串判定形态：`[[ "$command_line" != *"$expected"* ]]`
    assert not re.search(r'\$\{?command_line\}?\s*!=\s*\*', code), \
        "rq4_collect.sh 仍用子串包含判定参数自检（会漏报数值漂移与多余选项）"
    # 必须调用唯一真源的判定实现
    assert "rq4_param_check.py" in text, "rq4_collect.sh 未调用 rq4_param_check.py"


@pytest.mark.skipif(not COLLECT_SH.exists(), reason="未找到 rq4_collect.sh")
def test_param_check_helper_does_not_reimplement_the_rule():
    """param_check_of 只负责取参数 + 调用，不得自己再实现一套判定规则。"""
    text = COLLECT_SH.read_text(encoding="utf-8")
    body = text.split("param_check_of() {", 1)[1].split("\n}", 1)[0]
    # 判定逻辑必须在 Python 侧（唯一真源）；bash 侧只能做取参数/调用
    assert "python3" in body, "param_check_of 必须调用 rq4_param_check.py"
    for forbidden in ("!= *\"$expected\"*", "== *\"$expected\"*"):
        assert forbidden not in body, \
            f"param_check_of 内不得自行实现子串判定（{forbidden}）"


@pytest.mark.skipif(not COLLECT_SH.exists(), reason="未找到 rq4_collect.sh")
def test_collect_sh_keeps_28_column_header():
    """summary csv 的 28 列表头不能变（param_check 列名与位置必须保持）。"""
    text = COLLECT_SH.read_text(encoding="utf-8")
    header_line = next(
        (ln for ln in text.splitlines()
         if '"protocol,group,rep,container,image,' in ln),
        None)
    assert header_line is not None, "未找到 summary 表头"
    cols = header_line.split('"')[1].split(",")
    assert len(cols) == 28, f"表头列数应为 28，实际 {len(cols)}"
    assert cols[20] == "param_check", f"第 21 列应为 param_check，实际 {cols[20]}"
