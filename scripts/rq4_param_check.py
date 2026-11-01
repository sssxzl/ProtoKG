# -*- coding: utf-8 -*-
"""scripts/rq4_param_check.py —— RQ4 参数自检：command_line 与参数表 OPTIONS 的**逐 token 全等**比对。

为什么不能用「子串包含」判定
--------------------------
旧实现（内联在 rq4_collect.sh 里）是::

    [[ "$command_line" != *"$expected"* ]] && param_ok="MISMATCH"

这是**子串包含**判定，挡不住两类最要命的参数漂移：

1. **数值漂移**：期望 ``-t 5000``，实际 ``-t 50000`` → 子串命中 → 误判 OK；
2. **尾部多选项**：实际命令行尾部多出 ``-X extra`` → 子串仍命中 → 误判 OK。

而这个自检的定位恰恰是「防参数抄写漂移的长期护栏」—— 漏报等于没有护栏。
故本模块把判定升级为**逐 token 序列全等**（顺序、个数、每个 token 的字面值都必须一致）。

判定规则（本模块是唯一真源，rq4_collect.sh / rq4_analyze.py 都调用它）
-----------------------------------------------------------------
**规则 1（单容器）**：OPTIONS 段逐 token 全等
    AFLNet 的实际命令行形态（三个协议的官方 run 脚本逐字一致）::

        afl-fuzz -d -i <in> [-x <dict>] -o <out> -N <net> <OPTIONS> [-c <cleanup>] <server cmd>

    * 起点锚点 = ``-N <net>`` 之后的第一个 token（``-N <net>`` 取自参数表，
      是真源；OPTIONS 紧随其后，见官方 run 脚本）。
    * 长度 = 期望 OPTIONS 的 token 数（参数表决定）。
    * 该窗口内的 token 必须与期望**逐位相等** → 挡住数值漂移 / 缺 token / 顺序颠倒。
    * 窗口之后的第一个 token 必须是「服务端命令起点」：非选项 token，
      或 ``-c``（AFLNet 清理脚本标记，RTSP/SMTP 官方 run 脚本用它接服务端命令）。
      → 挡住**尾部多出的额外选项**。
    * 可选传入 ``reference_command_line``（同协议兄弟容器）→ 额外把
      **服务端命令尾巴**与参照逐字比对。这是挡住「在服务端命令**之后**
      追加选项」（如 ``... 8554 -X extra``）的唯一可靠手段 ——
      服务端自己的参数（``-f``/``-L``/``-Y``/``-n``/``-D``/``-E``/``-oX`` …）
      长得就像选项，**不能**靠"数 -开头的 token"来判断。

**规则 2（跨容器）**：同协议所有容器的命令行必须一致
    同协议、同一次编排里，afl-fuzz 的调用形态只随**协议**变化（官方 run 脚本固定），
    唯一随容器变化的是 ``-o <outdir>``。故把 ``-o`` 的值遮蔽后，同协议的所有容器
    （两组 × 全部 rep）的 command_line 必须**逐字相同**。
    这条规则不依赖任何镜像内部知识（不硬编码服务端命令），却能挡住**任何位置**
    的命令行漂移（含命令��末尾多出的杂选项）。

返回值
------
``OK`` / ``MISMATCH`` / ``NO_COMMAND_LINE`` —— 与 rq4_collect.sh 写进
rq4_summary.csv 的 ``param_check`` 列枚举完全一致（28 列表头不变）。

CLI
---
    python3 rq4_param_check.py --options "<OPTIONS>" --net "<net>" --command-line "<cmd>"
    # stdout: OK / MISMATCH / NO_COMMAND_LINE；stderr: 失败原因（便于排查）
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

#: 判定通过
OK = "OK"
#: 判定不通过（参数漂移）
MISMATCH = "MISMATCH"
#: command_line 为空（容器尚未产出 fuzzer_stats / 采集失败）
NO_COMMAND_LINE = "NO_COMMAND_LINE"

#: OPTIONS 段之后允许出现的**分隔/标记** token：
#:   ``-c`` —— AFLNet 官方 run 脚本用它接「清理脚本 + 服务端命令」（SIP/SMTP 用，
#:             RTSP 不用；它属于镜像 run 脚本，不属于我们的参数表 OPTIONS）。
#:   ``--`` —— AFLNet/afl-fuzz 惯用的「其后是服务端命令」分隔符。
#: 除它们以外的 "-xxx" token 一律视为「OPTIONS 段多出来的选项」→ MISMATCH。
ALLOWED_TRAILING_TOKENS = ("-c", "--")


def split_tokens(text: str) -> list[str]:
    """按空白把字符串切成 token 数组（与 shell 的 word splitting 一致）。"""
    return text.split()


def find_net_anchor(tokens: list[str], net: str) -> int:
    """定位 ``-N <net>`` 锚点，返回 ``-N`` 的下标；找不到返回 -1。

    ``net`` 非空时要求锚点后紧跟的 net 值完全一致（net 本身也是实验参数，
    漂了同样要报出来）；``net`` 为空则只认 ``-N`` 这个 flag 本身。
    """
    if net:
        for idx, tok in enumerate(tokens):
            if tok == "-N" and idx + 1 < len(tokens) and tokens[idx + 1] == net:
                return idx
        return -1
    for idx, tok in enumerate(tokens):
        if tok == "-N":
            return idx
    return -1


def check_command_line(expected_options: str, command_line: str,
                       net: str = "",
                       reference_command_line: str = "") -> tuple[str, str]:
    """规则 1：逐 token 全等比对 command_line 里的 OPTIONS 段与 expected_options。

    Args:
        expected_options: 参数表里的 OPTIONS 字符串（如 ``-P RTSP -D 10000 ...``）。
        command_line: fuzzer_stats 的 command_line 字段（整行）。
        net: 参数表里的 net（如 ``tcp://127.0.0.1/8554``），用于定位锚点。
        reference_command_line: 同协议**兄弟容器**的命令行（可选）。
            给了就额外做"服务端命令尾巴逐字比对" —— 这是挡住
            **服务端命令之后**被追加选项（如 ``... 8554 -X extra``）的唯一
            可靠手段（理由见 ``options_tail`` 的说明）。

    Returns:
        ``(verdict, reason)``；verdict ∈ {OK, MISMATCH, NO_COMMAND_LINE}。
    """
    if not command_line or not command_line.strip():
        return NO_COMMAND_LINE, "command_line 为空"

    expected = split_tokens(expected_options)
    if not expected:
        return MISMATCH, "参数表的 options 为空（无从比对）"

    tokens = split_tokens(command_line)
    anchor = find_net_anchor(tokens, net)
    if anchor < 0:
        if any(tok == "-N" for tok in tokens):
            return MISMATCH, (f"command_line 里 -N 的取值与参数表不一致"
                              f"（期望 {net}）")
        return MISMATCH, "command_line 里找不到 '-N' 锚点"

    start = anchor + 2
    end = start + len(expected)
    if end > len(tokens):
        return MISMATCH, (f"command_line 在 OPTIONS 段处提前结束"
                          f"（需要 {len(expected)} 个 token，实际只剩 "
                          f"{len(tokens) - start} 个）")

    actual = tokens[start:end]
    if actual != expected:
        for i, (exp_tok, act_tok) in enumerate(zip(expected, actual)):
            if exp_tok != act_tok:
                return MISMATCH, (f"OPTIONS 段第 {i + 1} 个 token 不符："
                                  f"期望 '{exp_tok}'，实际 '{act_tok}'")
        return MISMATCH, "OPTIONS 段与期望不一致"

    # ---- 尾部边界：OPTIONS 之后必须紧跟服务端命令，不能再多出选项 ----
    if end >= len(tokens):
        return MISMATCH, "OPTIONS 段之后缺少服务端命令"
    tail = tokens[end]
    if tail.startswith("-"):
        if tail not in ALLOWED_TRAILING_TOKENS:
            return MISMATCH, f"OPTIONS 段尾部多出选项 '{tail}'"
        if tail == "-c" and (end + 1 >= len(tokens) or "/" not in tokens[end + 1]):
            # `-c` 之后必须是服务端脚本路径（防止 `-c` 被当成夹带的额外选项）
            return MISMATCH, "选项 '-c' 之后缺少服务端脚本路径"

    # ---- 服务端命令尾巴：与参照命令行逐字比对 ----
    #   （挡住"服务端命令之后"追加选项 —— 规则 1 的 OPTIONS 窗口看不到那里）
    if reference_command_line:
        ref_tail = options_tail(reference_command_line, expected_options, net)
        own_tail = options_tail(command_line, expected_options, net)
        if ref_tail is None or own_tail is None:
            return MISMATCH, "无法定位服务端命令尾巴（参照或实际命令行不完整）"
        if own_tail != ref_tail:
            return MISMATCH, (f"服务端命令与参照容器不一致："
                              f"期望 '{ref_tail[:120]}'，实际 '{own_tail[:120]}'")

    return OK, "逐 token 全等"


def mask_outdir(command_line: str) -> str:
    """把 ``-o <outdir>`` 的**值**遮蔽掉，其余部分逐字保留。

    同协议的所有容器只有 outdir 不同（官方 run 脚本里 ``-o $OUTDIR``），
    遮蔽后即可直接比较两行 command_line 是否逐字相同。
    """
    tokens = split_tokens(command_line)
    masked: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            masked.append("<OUTDIR>")
            skip_next = False
            continue
        masked.append(tok)
        if tok == "-o":
            skip_next = True
    return " ".join(masked)


def options_tail(command_line: str, expected_options: str,
                 net: str = "") -> Optional[str]:
    """返回 OPTIONS 窗口**之后**的整段命令行（规范化空白后）。

    定位失败（找不到锚点 / OPTIONS 段不完整）时返回 None。

    ★ 这段"尾巴"装的是**服务端命令**（如 ``./testOnDemandRTSPServer 8554``、
      ``-c <cleanup.sh> ./src/kamailio -f ... -n 1 -D -E``），
      **不能**靠"看有没有 -开头的 token"来判多选项 —— 服务端自己的参数
      （``-f`` / ``-L`` / ``-Y`` / ``-n`` / ``-D`` / ``-E`` / ``-bd`` / ``-oX`` …）
      长得就像选项（连 SIP 的 OPTIONS 里的 ``-D`` / ``-E`` 都会在尾巴里再出现）。
      故尾巴只能**与同协议的参照命令行逐字比对**（见 ``check_command_line`` 的
      ``reference_command_line`` 参数）。
    """
    if not command_line or not command_line.strip():
        return None
    expected = split_tokens(expected_options)
    tokens = split_tokens(command_line)
    anchor = find_net_anchor(tokens, net)
    if anchor < 0:
        return None
    start = anchor + 2
    end = start + len(expected)
    if end > len(tokens):
        return None
    return " ".join(tokens[end:])


def check_command_lines_consistent(command_lines: list[str]) -> tuple[bool, str]:
    """规则 2：同协议所有容器的 command_line（遮蔽 outdir 后）必须逐字相同。

    Args:
        command_lines: 同协议各容器的 command_line 列表。

    Returns:
        ``(consistent, reason)``。
    """
    if len(command_lines) < 2:
        return True, "只有一个容器，无需比对"
    masked = [mask_outdir(cl) for cl in command_lines]
    first = masked[0]
    for idx, cl in enumerate(masked):
        if cl != first:
            return False, (f"第 {idx + 1} 个容器的 command_line 与第 1 个不一致"
                           f"（遮蔽 -o outdir 后）")
    return True, "同协议各容器 command_line 一致"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：stdout 打印判定，stderr 打印原因。"""
    ap = argparse.ArgumentParser(
        description="RQ4 参数自检：command_line 与 OPTIONS 逐 token 全等比对")
    ap.add_argument("--options", required=True, help="参数表里的 OPTIONS 字符串")
    ap.add_argument("--net", default="", help="参数表里的 net（用于定位 -N 锚点）")
    ap.add_argument("--command-line", required=True, help="fuzzer_stats 的 command_line")
    ap.add_argument("--reference-command-line", default="",
                    help="同协议兄弟容器的 command_line（可选；用于比对服务端命令尾巴）")
    args = ap.parse_args(argv)

    verdict, reason = check_command_line(args.options, args.command_line, args.net,
                                          args.reference_command_line)
    if verdict != OK:
        print(f"[rq4_param_check] {verdict}: {reason}", file=sys.stderr)
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
