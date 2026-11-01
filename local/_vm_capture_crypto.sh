#!/bin/bash
# 自抓 SSH/TLS/DTLS 真实握手流量（VM 本地）。
# 输出 6 文件结构：capture.pcapng / clean.pcapng / client.log / packets.ndjson / {proto}.csv
# 用法: /tmp/capture_crypto.sh <proto> <run_id>
#   proto: ssh | tls | dtls
set -uo pipefail
PROTO=${1:?"proto required"}
RUN_ID=${2:?"run_id required"}

WORK=/tmp/captures
RDIR="$WORK/$RUN_ID"
mkdir -p "$RDIR"

# 生成自签证书（TLS/DTLS 用）
CERTDIR=/tmp/selfsigned
mkdir -p "$CERTDIR"
if [ ! -f "$CERTDIR/cert.pem" ]; then
  openssl req -x509 -newkey rsa:2048 -keyout "$CERTDIR/key.pem" \
    -out "$CERTDIR/cert.pem" -days 1 -nodes -subj "/CN=localhost" 2>/dev/null
fi

start_tcpdump() {
  local port=$1
  nohup tcpdump -i any --immediate-mode -w "$RDIR/capture.pcapng" \
    > "$RDIR/tcpdump.log" 2>&1 &
  echo $! > "$RDIR/tcpdump.pid"
  sleep 1
}

stop_tcpdump() {
  [ -f "$RDIR/tcpdump.pid" ] && kill $(cat "$RDIR/tcpdump.pid") 2>/dev/null
  sleep 1
}

case "$PROTO" in
  ssh)
    PORT=22
    start_tcpdump $PORT
    # ssh -vvv 连本地 sshd，握手在认证前完成；BatchMode 让认证失败即退出
    ssh -vvv -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o BatchMode=yes -o ConnectTimeout=3 \
      -o PreferredAuthentications=none localhost "echo hi" \
      > "$RDIR/client.log" 2>&1 || true
    stop_tcpdump
    ;;
  tls)
    PORT=4443
    # 本地 s_server + s_client 走 TLS1.2 握手
    openssl s_server -accept $PORT -cert "$CERTDIR/cert.pem" -key "$CERTDIR/key.pem" \
      -tls1_2 -quiet > /dev/null 2>&1 &
    SRV=$!
    sleep 1
    start_tcpdump $PORT
    echo | openssl s_client -connect 127.0.0.1:$PORT -tls1_2 \
      -servername localhost > "$RDIR/client.log" 2>&1 || true
    stop_tcpdump
    kill $SRV 2>/dev/null
    ;;
  dtls)
    PORT=4444
    # 本地 s_server + s_client 走 DTLS1.2 握手（UDP）
    openssl s_server -dtls1_2 -accept $PORT -cert "$CERTDIR/cert.pem" -key "$CERTDIR/key.pem" \
      -quiet > /dev/null 2>&1 &
    SRV=$!
    sleep 1
    start_tcpdump $PORT
    echo | openssl s_client -dtls1_2 -connect 127.0.0.1:$PORT \
      > "$RDIR/client.log" 2>&1 || true
    stop_tcpdump
    kill $SRV 2>/dev/null
    ;;
esac

echo "=== 抓包完成，拆 6 文件 ==="
# clean.pcapng: 按端口过滤
case "$PROTO" in
  ssh|tls)
    tshark -r "$RDIR/capture.pcapng" -Y "tcp.port == $PORT" -w "$RDIR/clean.pcapng" 2>/dev/null || cp "$RDIR/capture.pcapng" "$RDIR/clean.pcapng"
    ;;
  dtls)
    tshark -r "$RDIR/capture.pcapng" -Y "udp.port == $PORT" -w "$RDIR/clean.pcapng" 2>/dev/null || cp "$RDIR/capture.pcapng" "$RDIR/clean.pcapng"
    ;;
esac

# packets.ndjson
tshark -r "$RDIR/clean.pcapng" -T ek > "$RDIR/packets.ndjson" 2>/dev/null

# {proto}.csv
case "$PROTO" in
  ssh)
    tshark -r "$RDIR/clean.pcapng" -T fields \
      -e frame.number -e ip.src -e ip.dst \
      -e ssh.protocol -e ssh.message_code -e tcp.len \
      -E separator=, > "$RDIR/ssh.csv" 2>/dev/null
    ;;
  tls)
    tshark -r "$RDIR/clean.pcapng" -T fields \
      -e frame.number -e ip.src -e ip.dst \
      -e tls.record.content_type -e tls.handshake.type -e tls.handshake.extensions_server_name \
      -E separator=, > "$RDIR/tls.csv" 2>/dev/null
    ;;
  dtls)
    tshark -r "$RDIR/clean.pcapng" -T fields \
      -e frame.number -e ip.src -e ip.dst \
      -e dtls.record.content_type -e dtls.handshake.type \
      -E separator=, > "$RDIR/dtls.csv" 2>/dev/null
    ;;
esac

echo "RUN_ID=$RUN_ID CID=LOCAL PORT=$PORT WORK=$RDIR" > "$RDIR/status.txt"
echo "完成: $RDIR"
ls -la "$RDIR/"