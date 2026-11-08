#!/usr/bin/env python3
# 重放种子：按协议切分 + 发送。ftp/smtp 每行 \r\n（tcp），sip \r\n\r\n（udp）。
import socket
import sys
import time

seed_path, port, transport = sys.argv[1], int(sys.argv[2]), sys.argv[3]

with open(seed_path, "rb") as f:
    data = f.read()

sep = b"\r\n\r\n" if transport == "udp" else b"\r\n"
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

if transport == "udp":
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    for m in msgs:
        s.sendto(m, ("127.0.0.1", port))
        time.sleep(0.05)
        try:
            s.recvfrom(4096)
        except socket.timeout:
            pass
    s.close()
else:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        for m in msgs:
            s.sendall(m)
            time.sleep(0.05)
        s.close()
    except OSError as e:
        print(f"replay error: {e}", file=sys.stderr)
