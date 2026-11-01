#!/bin/bash
# 批量采集 4 个 FTP 目标 + Kamailio SIP 的真实流量（VM 上跑）。
# 接受参数：可选 run_id 前缀（默认 rq1_ftp_<日期>）
# 每个目标采 1-2 条会话。
set -uo pipefail
DATE=$(date +%Y%m%d_%H%M%S)
PREFIX=${1:-$DATE}

# (image, port, finalizer_proto, extra_run_args)
TARGETS=(
  "bftpd bftpd 21 bftpd"
  "proftpd proftpd 21 proftpd"
  "lightftp lightftp 2200 lightftp"
  "pure-ftpd pureftpd 21 pure-ftpd"
)

# 清理旧 tcpdump / 容器
docker rm -f $(docker ps -aq) 2>/dev/null || true
pkill -9 tcpdump 2>/dev/null || true
sleep 1
mkdir -p /tmp/captures

# 跑 FTP
for spec in "${TARGETS[@]}"; do
  read -r IMG PROTO PORT LABEL <<< "$spec"
  RUN_ID="${LABEL}_login_${PREFIX}"
  echo "=================== $RUN_ID ==================="
  /tmp/capture_run.sh "$PROTO" "$IMG" "$RUN_ID" "$PORT" 2>&1 | tail -3
  sleep 2
  if ss -tlnp 2>/dev/null | grep -q ":$PORT " || [ "$PORT" = "2200" ]; then
    /tmp/ftp_client.sh "$RUN_ID" 2>&1 | tail -1
    sleep 1
    /tmp/capture_finalize.sh "$RUN_ID" "$PROTO" 2>&1 | tail -3
    echo "  → $(ls /tmp/captures/$RUN_ID/*.raw 2>/dev/null | wc -l) raw, $(stat -c%s /tmp/captures/$RUN_ID/clean.pcapng 2>/dev/null) bytes clean"
  else
    echo "  → 服务未启动 (端口 $PORT 没监听), 跳过"
  fi
done

echo ""
echo "=== 全部完成 ==="
for d in /tmp/captures/*/; do
  echo "$d: $(ls $d/*.raw 2>/dev/null | wc -l) raw, $(stat -c%s $d/clean.pcapng 2>/dev/null) bytes clean"
done