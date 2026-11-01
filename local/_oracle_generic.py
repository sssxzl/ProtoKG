#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 dry-run 重放 oracle：判定种子重放后目标服务器是否崩溃。

用法:
    python3 oracle_generic.py <seed.raw> <server> <port> [retries]

server: bftpd / proftpd / lightftp / pure-ftpd / exim / kamailio
输出: LEGAL(不崩) 或 ILLEGAL(崩) 或 ERROR

机制:
  1. 启动目标服务器（本地编译二进制，非 ASAN 也行，靠进程退出判崩）
  2. 等服务器就绪
  3. 按协议切分消息（ftp/smtp 每行 \r\n；sip \r\n\r\n 分隔，UDP）
  4. 逐条发送
  5. 检查服务器进程是否仍存活
"""
import socket
import subprocess
import sys
import time

# 服务器二进制路径（本地编译）
SERVERS = {
    "bftpd": {"bin": "/home/zxy/target programs/bftpd/bftpd",
              "args": ["-D", "-c", "/home/zxy/lightftp/fftp.conf"], "cwd": None},
    "lightftp": {"bin": "/home/zxy/target programs/LightFTP/Source/Release/fftp",
                 "args": ["/home/zxy/lightftp/fftp.conf"], "cwd": None},
    "proftpd": {"bin": None, "args": [], "cwd": None},
    "pure-ftpd": {"bin": None, "args": [], "cwd": None},
    "exim": {"bin": None, "args": [], "cwd": None},
    "kamailio": {"bin": None, "args": [], "cwd": None},
}

# 协议属性
PROTO = {
    "bftpd": {"transport": "tcp", "sep": b"\r\n"},
    "lightftp": {"transport": "tcp", "sep": b"\r\n"},
    "proftpd": {"transport": "tcp", "sep": b"\r\n"},
    "pure-ftpd": {"transport": "tcp", "sep": b"\r\n"},
    "exim": {"transport": "tcp", "sep": b"\r\n"},
    "kamailio": {"transport": "udp", "sep": b"\r\n\r\n"},
}


def read_seed(path):
    with open(path, "rb") as f:
        return f.read()


def split_messages(data, sep):
    msgs = []
    rest = data
    while True:
        idx = rest.find(sep)
        if idx == -1:
            if rest.strip():
                msgs.append(rest)
            break
        msgs.append(rest[:idx + len(sep)])
        rest = rest[idx + len(sep):]
    return msgs


def wait_port(port, transport="tcp", timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if transport == "tcp":
                s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                s.close()
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.sendto(b"", ("127.0.0.1", port))
                s.close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def oracle(seed_path, server, port, retries=3):
    verdicts = []
    for _ in range(retries):
        v = _run_once(seed_path, server, port)
        verdicts.append(v)
        if v == "LEGAL":
            return "LEGAL"
    return "ILLEGAL" if any(v == "ILLEGAL" for v in verdicts) else "ERROR"


def _run_once(seed_path, server, port):
    cfg = SERVERS.get(server)
    proto = PROTO.get(server)
    if not cfg or not proto or not cfg["bin"]:
        return "ERROR"
    data = read_seed(seed_path)
    msgs = split_messages(data, proto["sep"])
    if not msgs:
        return "ERROR"

    # 启动服务器
    cmd = [cfg["bin"]] + cfg["args"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, cwd=cfg["cwd"])
    if not wait_port(port, proto["transport"]):
        proc.kill()
        return "ERROR"

    # 逐条发送
    try:
        if proto["transport"] == "tcp":
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            for m in msgs:
                s.sendall(m)
                time.sleep(0.05)
            s.close()
        else:  # udp
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for m in msgs:
                s.sendto(m, ("127.0.0.1", port))
                time.sleep(0.05)
            s.close()
    except OSError:
        pass

    time.sleep(0.5)
    # 判崩：进程退出 => ILLEGAL；仍存活 => LEGAL
    alive = proc.poll() is None
    if not alive:
        proc.kill()
        return "ILLEGAL"
    proc.kill()
    return "LEGAL"


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: oracle_generic.py <seed.raw> <server> <port> [retries]")
        sys.exit(2)
    retries = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    print(oracle(sys.argv[1], sys.argv[2], int(sys.argv[3]), retries))
