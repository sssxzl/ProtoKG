#!/bin/bash
# 收尾捕获并生成 6 文件结构（去掉 set -e，避免 tshark 超时导致脚本中断）
# 用法: /tmp/capture_finalize.sh <run_id> <protocol>
set -uo pipefail
RUN_ID=${1:?"run_id required"}
PROTO=${2:?"protocol required"}

WORK=/tmp/captures
RDIR="$WORK/$RUN_ID"
status="$RDIR/status.txt"
[ -f "$status" ] || { echo "no $status"; exit 1; }
source "$status"

cd "$RDIR"

echo "=== 等 3s 让客户端流量收尾 ==="
sleep 3

echo "=== 停 tcpdump ==="
pkill -f "tcpdump -i any -w $RDIR/capture.pcapng" 2>/dev/null || true
sleep 2

echo "=== 关掉服务进程（容器内） ==="
case "$PROTO" in
  bftpd) docker exec $CID bash -c "pkill -9 -f bftpd" || true ;;
  proftpd) docker exec $CID bash -c "pkill -9 -f proftpd" || true ;;
  lightftp) docker exec $CID bash -c "pkill -9 -f fftp" || true ;;
  pure-ftpd|pureftpd) docker exec $CID bash -c "pkill -9 -f pure-ftpd" || true ;;
  sip|kamailio) docker exec $CID bash -c "pkill -9 -f kamailio" || true ;;
  ftp) docker exec $CID bash -c "pkill -9 -E bftpd|proftpd|fftp|pure-ftpd 2>/dev/null" || true ;;
esac
sleep 1

echo "=== 关掉容器 ==="
docker rm -f $CID 2>/dev/null || true

echo "=== clean.pcapng: 过滤端口(udp+tcp) + 去掉 RST/重传帧 ==="
# SIP/Kamailio 用 udp；FTP 等用 tcp — 用 OR 兼容
tshark -r "$RDIR/capture.pcapng" -Y "(tcp.port == $PORT or udp.port == $PORT) and not (tcp.analysis.flags or tcp.analysis.retransmission or tcp.analysis.fast_retransmission or arp or dns)" -w "$RDIR/clean.pcapng" 2>/dev/null
if [ ! -s "$RDIR/clean.pcapng" ]; then
  echo "filter 0 byte, 改用纯端口过滤"
  tshark -r "$RDIR/capture.pcapng" -Y "tcp.port == $PORT or udp.port == $PORT" -w "$RDIR/clean.pcapng" 2>/dev/null
  if [ ! -s "$RDIR/clean.pcapng" ]; then
    cp "$RDIR/capture.pcapng" "$RDIR/clean.pcapng"
  fi
fi

echo "=== packets.ndjson: tshark -T ek (单次，每行一个 JSON) ==="
tshark -r "$RDIR/clean.pcapng" -T ek > "$RDIR/packets.ndjson" 2>/dev/null
if [ ! -s "$RDIR/packets.ndjson" ]; then
  echo '{"error": "tshark ek produced no output"}' > "$RDIR/packets.ndjson"
fi

echo "=== ${PROTO}.csv ==="
case "$PROTO" in
  bftpd|proftpd|lightftp|pure-ftpd|pureftpd|ftp)
    tshark -r "$RDIR/clean.pcapng" -T fields -e frame.number -e ip.src -e ip.dst \
      -e ftp.request.command -e ftp.request.arg -e ftp.response.code -e ftp.response.arg \
      -E separator=, 2>/dev/null > "$RDIR/${PROTO}.csv" || true
    ;;
  sip|kamailio)
    tshark -r "$RDIR/clean.pcapng" -T fields -e frame.number -e ip.src -e ip.dst \
      -e sip.Method -e sip.Status-Line -e sip.Request-Line \
      -E separator=, 2>/dev/null > "$RDIR/${PROTO}.csv" || true
    ;;
esac

echo "=== rtp.csv (可能为空，RTP 流才有) ==="
tshark -r "$RDIR/clean.pcapng" -T fields -e frame.number -e ip.src -e ip.dst \
  -e rtp.p_type -e rtp.seq -e rtp.timestamp \
  -E separator=, 2>/dev/null > "$RDIR/rtp.csv" || echo "" > "$RDIR/rtp.csv"

echo "=== 完成 ==="
ls -la "$RDIR/"