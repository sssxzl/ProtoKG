#!/bin/bash
# SIP 客户端：python sip/sdp 模拟 INVITE/REGISTER/BYE/CANCEL 多会话。
# 用法: /tmp/sip_client.sh <run_id>
set -uo pipefail
RUN_ID=${1:?"run_id required"}

LOG=/tmp/captures/$RUN_ID/client.log
mkdir -p /tmp/captures/$RUN_ID

python3 - <<PYEOF > "$LOG"
import socket, time

run_id = "$RUN_ID"
log_lines = []

def L(s): log_lines.append(s); print(s, file=open("$LOG", "a"))

def udp_send(addr, data):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    s.sendto(data.encode("utf-8"), addr)
    try:
        resp, _ = s.recvfrom(8192)
        return resp.decode("utf-8", errors="replace")
    except socket.timeout:
        return "[timeout]"
    finally:
        s.close()

addr = ("127.0.0.1", 5060)
L(f"=== SIP 会话：{run_id} ===")
L(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
L(f"客户端: python udp socket")
L("")
L("--- 开始对话 ---")

# 1) REGISTER
call_id = "abc123@127.0.0.1"
from_uri = "sip:alice@127.0.0.1"
to_uri = "sip:bob@127.0.0.1"
local_tag = "tag1"
branch = "z9hG4bK-1"

reg = (
    f"REGISTER {from_uri} SIP/2.0\r\n"
    f"Via: SIP/2.0/UDP 127.0.0.1:5070;branch={branch}\r\n"
    f"From: <{from_uri}>;tag={local_tag}\r\n"
    f"To: <{to_uri}>\r\n"
    f"Call-ID: {call_id}\r\n"
    f"CSeq: 1 REGISTER\r\n"
    f"Contact: <sip:alice@127.0.0.1:5070>\r\n"
    f"Max-Forwards: 70\r\n"
    f"User-Agent: ProtoRAG-sip-client\r\n"
    f"Content-Length: 0\r\n\r\n"
)
L(f"C> REGISTER alice@127.0.0.1")
resp = udp_send(addr, reg)
for line in resp.split("\r\n")[:6]:
    L(f"S> {line}")
L("")

# 2) INVITE
inv = (
    f"INVITE {to_uri} SIP/2.0\r\n"
    f"Via: SIP/2.0/UDP 127.0.0.1:5070;branch={branch}-2\r\n"
    f"From: <{from_uri}>;tag={local_tag}\r\n"
    f"To: <{to_uri}>\r\n"
    f"Call-ID: {call_id}\r\n"
    f"CSeq: 2 INVITE\r\n"
    f"Contact: <sip:alice@127.0.0.1:5070>\r\n"
    f"Max-Forwards: 70\r\n"
    f"User-Agent: ProtoRAG-sip-client\r\n"
    f"Content-Type: application/sdp\r\n"
    f"Content-Length: 0\r\n\r\n"
)
L(f"C> INVITE bob@127.0.0.1")
resp = udp_send(addr, inv)
for line in resp.split("\r\n")[:6]:
    L(f"S> {line}")
L("")

# 3) OPTIONS
opt = (
    f"OPTIONS {from_uri} SIP/2.0\r\n"
    f"Via: SIP/2.0/UDP 127.0.0.1:5070;branch={branch}-3\r\n"
    f"From: <{from_uri}>;tag={local_tag}-opt\r\n"
    f"To: <{from_uri}>\r\n"
    f"Call-ID: {call_id}-opt\r\n"
    f"CSeq: 1 OPTIONS\r\n"
    f"Max-Forwards: 70\r\n"
    f"Content-Length: 0\r\n\r\n"
)
L(f"C> OPTIONS {from_uri}")
resp = udp_send(addr, opt)
for line in resp.split("\r\n")[:4]:
    L(f"S> {line}")
L("")

# 4) MESSAGE
msg = (
    f"MESSAGE {to_uri} SIP/2.0\r\n"
    f"Via: SIP/2.0/UDP 127.0.0.1:5070;branch={branch}-4\r\n"
    f"From: <{from_uri}>;tag={local_tag}-msg\r\n"
    f"To: <{to_uri}>\r\n"
    f"Call-ID: {call_id}-msg\r\n"
    f"CSeq: 1 MESSAGE\r\n"
    f"Content-Type: text/plain\r\n"
    f"Content-Length: 5\r\n\r\nhello"
)
L(f"C> MESSAGE bob@127.0.0.1")
resp = udp_send(addr, msg)
for line in resp.split("\r\n")[:4]:
    L(f"S> {line}")
L("")

# 5) SUBSCRIBE
sub = (
    f"SUBSCRIBE {to_uri} SIP/2.0\r\n"
    f"Via: SIP/2.0/UDP 127.0.0.1:5070;branch={branch}-5\r\n"
    f"From: <{from_uri}>;tag={local_tag}-sub\r\n"
    f"To: <{to_uri}>\r\n"
    f"Call-ID: {call_id}-sub\r\n"
    f"CSeq: 1 SUBSCRIBE\r\n"
    f"Event: presence\r\n"
    f"Max-Forwards: 70\r\n"
    f"Content-Length: 0\r\n\r\n"
)
L(f"C> SUBSCRIBE bob@127.0.0.1")
resp = udp_send(addr, sub)
for line in resp.split("\r\n")[:4]:
    L(f"S> {line}")
L("")

L("--- 客户端结束 ---")
PYEOF

echo "client log: $LOG ($(wc -l < $LOG) 行)"