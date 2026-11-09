# -*- coding: utf-8 -*-
"""scripts/rq4_seed_profile.py —— 种子"画像"计算（唯一真源）。

RQ4 实验的自证要求：**两组之间只有种子不同**（同一镜像、同一官方字典、同一 OPTIONS）。
本脚本给出可量化、可复核的证据链：

  * ``seed_files``   —— 种子文件数
  * ``seed_regions`` —— AFLNet **真实协议分区器**切出的 region 总数
                        （region = 一条 AFLNet 状态机消息；这是"种子形状"的度量）
  * ``dict_tokens``  —— 官方字典的 token 条数（两组必须相同 → 证明字典不是变量）

为什么 region 数比"消息数"更可信
--------------------------------
AFLNet 的分区器（``aflnet.c``）决定一条输入被切成几个"消息"：

  * ``extract_requests_rtsp`` → 按 4 字节终结符 ``0D 0A 0D 0A`` 切，**不看方法名**
  * ``extract_requests_smtp`` → 按 2 字节终结符 ``0D 0A`` 切，**不看方法名**
  * ``extract_requests_sip``  → 只有当 ``\\r\\n`` 之后紧跟
    ``REGISTER/INVITE/ACK/BYE`` 之一才算新消息起点，**看方法名**

因此「消息数」与「region 数」不一定相等（SIP 尤其明显：以不被识别的方法开头的
消息会被并入前一条 → 消息边界被破坏 → 变异预算被浪费）。
本脚本**逐字节忠实移植**这三个分区器（与 ``rq4_verify_seeds.py`` 共用同一实现），
统计出来的 region 数即为 AFLNet 真正看到的状态机节点数。

用法
----
    # 输出 key=value 便于 shell 解析
    python scripts/rq4_seed_profile.py --seed-dir derived/model/seeds/rtsp/rq4_B \\
        --protocol rtsp --dict-file /path/rtsp.dict

    # 输出 JSON
    python scripts/rq4_seed_profile.py --seed-dir ... --protocol sip --json

    # 只算 region 数（不要求目录存在 .raw）
    python scripts/rq4_seed_profile.py --seed-dir ... --protocol smtp

本模块**零本地依赖**（只用标准库），可单独 scp 到 VM 上运行。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

#: AFLNet 的 SIP 分区器（aflnet.c: extract_requests_sip）只认这 4 个方法作新消息起点
AFLNET_SIP_BOUNDARY_METHODS = ("REGISTER", "INVITE", "ACK", "BYE")

#: 边界方法的字节形式（供分区计数复刻用）
AFLNET_SIP_BOUNDARY_BYTES = tuple(m.encode("ascii")
                                  for m in AFLNET_SIP_BOUNDARY_METHODS)

#: 各协议的 region 切分策略（与 aflnet.c 一一对应）
PROTO_TERMINATOR = {
    "rtsp": b"\x0d\x0a\x0d\x0a",   # extract_requests_rtsp：4 字节空行
    "smtp": b"\x0d\x0a",           # extract_requests_smtp：2 字节 CRLF
}


# ---------------------------------------------------------------------------
# 逐字节忠实移植 AFLNet 的三个分区器
# ---------------------------------------------------------------------------
def count_terminator_regions(data: bytes, terminator: bytes) -> int:
    """复刻 AFLNet ``extract_requests_rtsp`` / ``extract_requests_smtp``。

    源码逻辑（``aflnet.c``，两者仅终结符长度不同）::

        mem = ck_alloc(1024); mem_count = 0; cur_start = cur_end = 0;
        while (byte_count < buf_size) {
            memcpy(&mem[mem_count], buf + byte_count++, 1);
            if ((mem_count > T-1) && (memcmp(&mem[mem_count-(T-1)], terminator, T) == 0)) {
                region_count++;
                regions[region_count-1] = {cur_start, cur_end};
                mem_count = 0; cur_start = cur_end + 1; cur_end = cur_start;
            } else {
                mem_count++; cur_end++;
                if (cur_end == buf_size - 1) { region_count++; break; }
                if (mem_count == mem_size) { mem_size *= 2; mem = ck_realloc(...); }
            }
        }
        if (region_count == 0 && buf_size > 0) region_count = 1;   // 结构损坏兜底

    即：region 的 ``end_byte`` 是**终结符之前的最后一个字节**。
    """
    buf_size = len(data)
    if buf_size == 0:
        return 0
    tlen = len(terminator)
    mem = bytearray(1024)
    mem_count = 0
    byte_count = 0
    region_count = 0
    cur_end = 0
    while byte_count < buf_size:
        if mem_count >= len(mem):
            mem.extend(b"\x00" * len(mem))
        mem[mem_count] = data[byte_count]
        byte_count += 1

        if mem_count >= tlen and bytes(mem[mem_count - tlen + 1:mem_count + 1]) == terminator:
            region_count += 1
            mem_count = 0
            cur_end += 1
        else:
            mem_count += 1
            cur_end += 1
            if cur_end == buf_size - 1:
                region_count += 1
                break

    if region_count == 0:
        region_count = 1  # 结构损坏 → 整个缓冲区算 1 个 region
    return region_count


def count_sip_regions(data: bytes) -> int:
    """复刻 AFLNet ``extract_requests_sip`` 的分区计数（**逐字节忠实移植**）。

    源码逻辑（``aflnet.c``）：
      · 逐字节消费缓冲区，维护滑动窗口 ``mem``；
      · 判定条件：``mem[mem_count-1] == '\\r'``（消费位前一个字节是 CR）
        **且** 其后紧跟的字节以 REGISTER/INVITE/ACK/BYE 之一开头
        —— 即「方法名前面是 ``\\r\\n``」时切出一个新 region；
      · 命中即结算上一个 region 并把 ``mem_count`` 清零；
      · 未命中时若 ``cur_end == buf_size - 1`` 则结算最后一个 region 并退出；
      · 收尾兜底：region_count == 0（结构损坏）→ 整个缓冲区算 1 个 region。

    效果：**一条以边界方法开头、以 ``\\r\\n\\r\\n`` 与前一条分隔的消息 = 一个 region**。
    以其他方法开头的消息不会被切开 → 被并入前一条消息（消息边界被破坏）。
    """
    buf_size = len(data)
    if buf_size == 0:
        return 0
    mem = bytearray(1024)
    mem_count = 0
    byte_count = 0
    region_count = 0
    cur_end = 0
    while byte_count < buf_size:
        if mem_count >= len(mem):
            mem.extend(b"\x00" * len(mem))
        mem[mem_count] = data[byte_count]
        byte_count += 1

        # 判定：窗口前一个字节是 CR，且其后的字节以边界方法开头
        matched = False
        if mem_count > 1 and mem[mem_count - 1] == 0x0D:
            rest = data[byte_count:]
            for m in AFLNET_SIP_BOUNDARY_BYTES:
                if rest.startswith(m):
                    matched = True
                    break

        if matched:
            region_count += 1
            mem_count = 0
            cur_end = cur_end + 1
        else:
            mem_count += 1
            cur_end += 1
            if cur_end == buf_size - 1:
                region_count += 1
                break

    if region_count == 0:
        region_count = 1  # 结构损坏 → 整个缓冲区算 1 个 region
    return region_count


def count_regions(data: bytes, protocol: str) -> int:
    """按协议选择对应的 AFLNet 分区器计算 region 数。"""
    proto = (protocol or "").lower()
    if proto == "sip":
        return count_sip_regions(data)
    term = PROTO_TERMINATOR.get(proto)
    if term is None:
        # 未登记的协议：保守按 CRLF 切（RTSP/SMTP 的切分不会比这更细）
        term = b"\x0d\x0a"
    return count_terminator_regions(data, term)


def count_rtsp_regions(data: bytes) -> int:
    """复刻 ``extract_requests_rtsp``（4 字节 ``0D 0A 0D 0A`` 终结符）。"""
    return count_terminator_regions(data, PROTO_TERMINATOR["rtsp"])


def count_smtp_regions(data: bytes) -> int:
    """复刻 ``extract_requests_smtp``（2 字节 ``0D 0A`` 终结符）。"""
    return count_terminator_regions(data, PROTO_TERMINATOR["smtp"])


# ---------------------------------------------------------------------------
# 字典 token 统计
# ---------------------------------------------------------------------------
def count_dict_tokens(path: Optional[Path]) -> int:
    """统计 AFL 字典里的有效 token 条数。

    跳过空行与 ``#`` 注释行（AFL 的字典格式）。SIP 官方**不带字典**（镜像内无
    ``*.dict``），此时传 ``None`` → 返回 0。
    """
    if path is None:
        return 0
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# 目录级画像
# ---------------------------------------------------------------------------
def profile_seed_dir(seed_dir: Path, protocol: str,
                     dict_file: Optional[Path] = None) -> dict:
    """统计一个种子目录的画像。

    ★ 注意：只统计 ``*.raw``。AFLNet 的 ``read_testcases()`` 用 ``scandir()``
    遍历 ``-i`` 目录，会把**所有常规非空文件**都当成测试用例读进来
    （只跳过 ``README.txt``）—— 所以 ``MANIFEST.md5`` 之类必须放在种子目录
    **之外**，否则会污染种子集。
    """
    raws = sorted(seed_dir.glob("*.raw")) if seed_dir.is_dir() else []
    regions = 0
    for raw in raws:
        regions += count_regions(raw.read_bytes(), protocol)
    return {
        "protocol": protocol,
        "seed_dir": str(seed_dir),
        "seed_files": len(raws),
        "seed_regions": regions,
        "dict_tokens": count_dict_tokens(dict_file),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ4 种子画像计算")
    ap.add_argument("--seed-dir", required=True, help="种子目录")
    ap.add_argument("--protocol", required=True,
                    help="协议名（rtsp/sip/smtp）—— 决定用哪个 AFLNet 分区器")
    ap.add_argument("--dict-file", default=None,
                    help="官方字典路径（不存在则计 0；SIP 官方无字典）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    seed_dir = Path(args.seed_dir)
    dict_file = Path(args.dict_file) if args.dict_file else None
    result = profile_seed_dir(seed_dir, args.protocol, dict_file)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for key in ("protocol", "seed_dir", "seed_files", "seed_regions",
                    "dict_tokens"):
            print(f"{key}={result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
