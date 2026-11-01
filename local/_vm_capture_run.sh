#!/bin/bash
# 抓包基础设施：在 VM 上启动一个 FTP/SIP 协议的 docker 容器端，
# 用 tcpdump/tee 同时记录到本地 pcap + 提取结构化 CSV。
#
# 复用 rtsp/数据流量 的 6 文件结构：
#   capture.pcapng / clean.pcapng / client.log / packets.ndjson / {proto}.csv / rtp.csv (SIP/Kamailio 没有)
#
# 用法:
#   /tmp/capture_run.sh <protocol> <target_image> <run_id> <port>
#   例: /tmp/capture_run.sh ftp bftpd bftpd_plain_0001 21

set -uo pipefail
PROTO=${1:-ftp}      # ftp / sip
IMG=${2:-bftpd}      # 容器镜像名
RUN_ID=${3:-test_0001}
PORT=${4:-21}        # 容器内服务端口
shift 4

WORK=/tmp/captures
mkdir -p "$WORK/$RUN_ID"
cd "$WORK/$RUN_ID"

echo "=== [$RUN_ID] $PROTO 容器启动 ==="
# 用端口映射：host:21 -> 容器:21，tcpdump 直接看主机 lo 流量最稳
case "$PROTO" in
  sip|kamailio) # SIP UDP
    CID=$(docker run -d --name "$RUN_ID" -p "${PORT}:${PORT}/udp" "$IMG" bash -c "while true; do sleep 3600; done") ;;
  *)
    CID=$(docker run -d --name "$RUN_ID" -p "${PORT}:${PORT}" "$IMG" bash -c "while true; do sleep 3600; done") ;;
esac
echo "container=$CID"

sleep 3
echo "=== 验证容器端口 ==="
docker exec $CID ss -tlnp 2>/dev/null | grep ":$PORT " | head

echo "=== 启动 tcpdump 后台抓包 ==="
# 用 -i any 抓所有接口；BPF: tcp + 端口过滤（避免误抓无关协议如 broadcast）
# 注: 'port N' 在此环境 BPF 不匹配（veth 接口特性），改用 'tcp and (port N)' 并依赖后续 clean 过滤
nohup tcpdump -i any --immediate-mode -w "$WORK/$RUN_ID/capture.pcapng" "tcp" \
    > "$WORK/$RUN_ID/tcpdump.log" 2>&1 &
TCPDUMP_PID=$!
sleep 2
echo "tcpdump PID=$TCPDUMP_PID 是否真在跑:" $(ps -p $TCPDUMP_PID -o pid= 2>/dev/null || echo "NO")

echo "=== 启动服务进程（容器内，用 setsid 完全脱离父 bash） ==="
# 强制精确匹配：传 bftpd/proftpd 各自专属名
case "$PROTO" in
  bftpd)
    docker exec $CID setsid bash -c "cd /home/ubuntu/experiments/bftpd && exec ./bftpd -D -c /home/ubuntu/experiments/basic.conf > /tmp/bftpd_serve.log 2>&1 < /dev/null" || true
    ;;
  proftpd)
    docker exec $CID setsid bash -c "cd /home/ubuntu/experiments/proftpd && exec ./proftpd -n -c /home/ubuntu/experiments/basic.conf -X > /tmp/proftpd_serve.log 2>&1 < /dev/null" || true
    ;;
  lightftp)
    docker exec $CID setsid bash -c "cd /home/ubuntu/experiments/LightFTP/Source/Release && exec ./fftp fftp.conf > /tmp/lightftp_serve.log 2>&1 < /dev/null" || true
    ;;
  pure-ftpd|pureftpd)
    docker exec $CID setsid bash -c "cd /home/ubuntu/experiments/pure-ftpd && exec src/pure-ftpd -A > /tmp/pureftpd_serve.log 2>&1 < /dev/null" || true
    ;;
  ftp)
    # 兼容旧调用：默认当 bftpd 跑（向后兼容）
    docker exec $CID setsid bash -c "cd /home/ubuntu/experiments/bftpd && exec ./bftpd -D -c /home/ubuntu/experiments/basic.conf > /tmp/bftpd_serve.log 2>&1 < /dev/null" || true
    ;;
  sip|kamailio)
    docker exec $CID setsid bash -c "export KAMAILIO_MODULES=/home/ubuntu/experiments/kamailio/src/modules && export KAMAILIO_RUNTIME_DIR=/home/ubuntu/experiments/kamailio/runtime_dir && mkdir -p \$KAMAILIO_RUNTIME_DIR && exec /home/ubuntu/experiments/kamailio/src/kamailio -f /home/ubuntu/experiments/kamailio-basic.cfg -L \$KAMAILIO_MODULES -Y \$KAMAILIO_RUNTIME_DIR -n 1 -D -E > /tmp/kamailio_serve.log 2>&1 < /dev/null" || true
    ;;
esac
# Kamailio 在 ASAN 镜像里启动慢，等 25s；其他 10s
if [ "$PROTO" = "sip" ] || [ "$PROTO" = "kamailio" ]; then
  sleep 25
else
  sleep 10
fi

echo "=== 服务端口状态 ==="
docker exec $CID ss -tlnp 2>/dev/null | grep ":$PORT " | head -2
docker exec $CID ss -ulnp 2>/dev/null | grep ":$PORT " | head -2

# 给调用方留一段时间触发流量
echo "=== 容器已就绪，等待客户端触发流量 ==="
echo "RUN_ID=$RUN_ID CID=$CID TCPDUMP_PID=$TCPDUMP_PID WORK=$WORK/$RUN_ID PORT=$PORT" > "$WORK/$RUN_ID/status.txt"
cat "$WORK/$RUN_ID/status.txt"