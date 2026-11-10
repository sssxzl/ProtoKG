#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dry-run 重放 oracle：判定一个 RTSP .raw 种子重放后是否让 live555 服务器崩溃。

用法:
    python3 oracle.py <seed.raw> <port> [retries]

输出: LEGAL(不崩) 或 ILLEGAL(崩) 或 ERROR

机制:
  1. 以子进程启动 live555 ASAN 服务器(testOnDemandRTSPServer)监听 <port>
  2. 等服务器就绪
  3. 把种子按 RTSP 消息边界(\r\n\r\n)切分, 逐条通过 TCP 发送
  4. 每条发送后短暂读响应(服务器不回也无妨)
  5. 全部发完后检查服务器进程是否仍存活
  6. 存活 + 无 ASAN 崩溃输出 => LEGAL; 进程退出/ASAN 报错 => ILLEGAL
"""
import os
import socket
import struct
import subprocess
import sys
import time

try:
    import json
except ImportError:  # pragma: no cover
    json = None

SERVER_BIN = "/home/zxy/live555-asan/testProgs/testOnDemandRTSPServer"
SERVER_CWD = "/home/zxy/live555-asan/testProgs"


def read_seed(path):
    with open(path, "rb") as f:
        data = f.read()
    return data


def _frames_look_plausible(msgs):
    """判断帧解码出的负载是否像 RTSP 文本（可打印 ASCII 占比高）。

    帧格式探测的双重保险之一：纯文本 RTSP 流的首 4 字节作为 u32 必然是巨大值
    （'DESC' = 0x43534544 ≫ 1 MiB）→ 天然被长度上限拒绝；本函数额外要求
    解码后的负载是可打印文本，防止「纯文本恰好被误读成若干帧」的极端情形
    （实测存在首字节恰为 'B'（0x42）的真实崩溃样本，不能用「首字节是大写
    字母」这类语义判据）。
    """
    if not msgs:
        return False
    sample = b"".join(msgs[:4])[:4096]
    if not sample:
        return False
    printable = sum(1 for b in sample
                    if 0x20 <= b < 0x7f or b in (0x09, 0x0a, 0x0d))
    return printable / len(sample) >= 0.80


def split_messages(data):
    """自适应切分 RTSP 消息：先试 4 字节长度前缀帧，失败则回退 \\r\\n\\r\\n。

    ★ v2 修正（技术方案 §4.1.1）：实测存在**两种线格式**——
      · 种子文件（/seeds_work/*.raw、宿主语料目录）与 /out/queue/* = **纯文本**
        （消息以 \\r\\n\\r\\n 分隔）
      · /out/replayable-crashes/* = **4 字节长度前缀帧**（<I 小端长度 + 负载）
    原实现只按 \\r\\n\\r\\n 切分 → 会**错切崩溃样本**（把长度前缀当消息内容），
    使重放输入与 AFL 原始输入不一致 → 重放结论不能严格成立。
    → 本实现保证：对**纯文本种子**的行为逐字节不变（回归断言见
      tests/fused/test_rq3_oracle_split.py）。

    长度前缀误判风险：纯文本前 4 字节可能被误读成长度（如 'DESC' = 0x43534544
    远超上限 → 被拒）。**双重保险**：① 0 < n <= 1 MiB；② 全部帧必须**精确
    消费**文件长度；③ 解码负载必须是可打印文本。
    注：帧负载实测可达 16417 B（v2 伪码的 4096 上限会把真实崩溃样本误判为
    纯文本 —— 实测 7 个样本有 6 个被误判）。

    Args:
        data: 原始字节。

    Returns:
        消息列表。
    """
    if not data:
        return []
    # --- 尝试长度前缀帧 ---
    msgs = []
    off = 0
    while off + 4 <= len(data):
        n = struct.unpack("<I", data[off:off + 4])[0]
        if n <= 0 or n > 1024 * 1024 or off + 4 + n > len(data):
            break
        msgs.append(data[off + 4: off + 4 + n])
        off += 4 + n
    if msgs and off == len(data) and _frames_look_plausible(msgs):
        return msgs                       # 长度前缀帧（精确消费）
    # --- 回退：纯文本 \\r\\n\\r\\n 切分 ---
    sep = b"\r\n\r\n"
    out = []
    rest = data
    while True:
        idx = rest.find(sep)
        if idx == -1:
            if rest.strip():
                out.append(rest)
            break
        out.append(rest[:idx + len(sep)])
        rest = rest[idx + len(sep):]
    return out


def wait_port(port, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def oracle(seed_path, port, retries=3):
    """判定一条种子的重放结果。

    语义（对齐技术方案 §4.1）：
      · LEGAL   —— 服务器存活且发送未失败；**任一次判 LEGAL 即返回**（早退，
                    排除概率性 UAF 抖动造成的误判）
      · ILLEGAL —— 进程退出 / 发送失败（ASAN abort）；3 次全 ILLEGAL 才判 ILLEGAL
      · ERROR   —— 服务器 15 s 内未就绪 / 无可切分消息 → **不可判定**
                    （从 Rv 分母中剔除并单独计数）

    Args:
        seed_path: 种子 .raw 路径。
        port: 服务器监听端口（每个种子用独立端口）。
        retries: 重试次数。

    Returns:
        "LEGAL" / "ILLEGAL" / "ERROR"。
    """
    verdicts = []
    for _ in range(retries):
        v = _run_once(seed_path, port)
        verdicts.append(v)
        if v == "LEGAL":
            # 合法(不崩) 只要一次成功即可判定不崩
            return "LEGAL"
        # ILLEGAL 时重试, 排除概率性/时序抖动
    # 多次都崩 => ILLEGAL
    return "ILLEGAL" if any(v == "ILLEGAL" for v in verdicts) else "ERROR"


def oracle_json(seed_path, port, retries=3):
    """判定一条种子并返回结构化结果（含重试明细，供干跑报告使用）。

    Args:
        seed_path: 种子 .raw 路径。
        port: 服务器监听端口。
        retries: 重试次数。

    Returns:
        `{"seed", "verdict", "attempts", "port"}` 字典。
    """
    attempts = []
    verdict = "ERROR"
    for _ in range(retries):
        v = _run_once(seed_path, port)
        attempts.append(v)
        if v == "LEGAL":
            verdict = "LEGAL"
            break
    else:
        verdict = "ILLEGAL" if any(v == "ILLEGAL" for v in attempts) else "ERROR"
    return {
        "seed": os.path.basename(seed_path),
        "verdict": verdict,
        "attempts": attempts,
        "port": port,
    }



def _run_once(seed_path, port):
    data = read_seed(seed_path)
    msgs = split_messages(data)
    if not msgs:
        return "ERROR"

    log = open("/tmp/oracle_server.log", "wb")
    proc = subprocess.Popen(
        [SERVER_BIN, str(port)],
        cwd=SERVER_CWD,
        stdout=log, stderr=log,
        env=dict(os.environ, ASAN_OPTIONS="abort_on_error=1:detect_leaks=0"),
    )
    try:
        if not wait_port(port, timeout=15.0):
            proc.terminate()
            return "ERROR"

        crashed = False
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=3.0)
            s.settimeout(2.0)
            for m in msgs:
                try:
                    s.sendall(m)
                except OSError:
                    crashed = True
                    break
                # 尝试读一点响应
                try:
                    s.recv(4096)
                except OSError:
                    crashed = True
                    break
            try:
                s.close()
            except OSError:
                pass
        except OSError:
            crashed = True

        # 等服务器处理完
        time.sleep(0.5)

        # 判定: 进程是否还活着
        alive = proc.poll() is None
        if alive and not crashed:
            # 清理
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            return "LEGAL"
        else:
            # 崩了
            if proc.poll() is None:
                proc.kill()
            return "ILLEGAL"
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        log.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: oracle.py <seed.raw> <port> [retries] [--json]",
              file=sys.stderr)
        sys.exit(2)
    seed = sys.argv[1]
    port = int(sys.argv[2])
    retries = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    if "--json" in sys.argv:
        print(json.dumps(oracle_json(seed, port, retries), ensure_ascii=False))
    else:
        print(oracle(seed, port, retries))
