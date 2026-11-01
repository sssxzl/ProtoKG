#!/bin/bash
# 批量 Rv 测量（docker 版，退出码判崩 + 概率性崩溃重试）
# 用法: /tmp/measure_rv.sh <server> <seeds_dir> <port> [retries]
# 判崩逻辑（与 Live555 oracle 一致）:
#   - 服务器持续运行(running) => LEGAL
#   - 退出且 ExitCode=0 => LEGAL (正常单连接退出)
#   - 退出且 ExitCode!=0 => 疑似崩溃，重试(最多 retries 次)，任一次 LEGAL 即判 LEGAL
set -uo pipefail
SERVER=${1:?"server"}
SEED_DIR=${2:?"seed dir"}
PORT=${3:?"port"}
RETRIES=${4:-3}

case "$SERVER" in
  bftpd)   IMG=bftpd:latest;    CMD="cd /home/ubuntu/experiments/bftpd && exec ./bftpd -D -c /home/ubuntu/experiments/basic.conf" ;;
  proftpd) IMG=proftpd:latest;  CMD="cd /home/ubuntu/experiments/proftpd && exec ./proftpd -n -c /home/ubuntu/experiments/basic.conf -X" ;;
  lightftp) IMG=lightftp:latest; CMD="cd /home/ubuntu/experiments/LightFTP/Source/Release && exec ./fftp fftp.conf 2200" ;;
  pure-ftpd) IMG=pure-ftpd:latest; CMD="cd /home/ubuntu/experiments/pure-ftpd && exec src/pure-ftpd -A" ;;
  exim)     IMG=exim:latest;     CMD="exec exim -bd -d -oX 25 -oP /var/lock/exim.pid" ;;
  kamailio) IMG=kamailio:latest; CMD="cd /home/ubuntu/experiments/kamailio && export KAMAILIO_MODULES=src/modules && export KAMAILIO_RUNTIME_DIR=runtime_dir && mkdir -p \$KAMAILIO_RUNTIME_DIR && exec ./src/kamailio -f /home/ubuntu/experiments/kamailio-basic.cfg -L \$KAMAILIO_MODULES -Y \$KAMAILIO_RUNTIME_DIR -n 1 -D -E" ;;
  *) echo "unknown server: $SERVER" >&2; exit 2 ;;
esac
if [ "$SERVER" = "kamailio" ]; then TRANSPORT=udp; else TRANSPORT=tcp; fi

# 单次重放判崩，输出 "LEGAL"/"ILLEGAL"/"ERROR"
run_once() {
  local seed=$1
  local CID
  CID=$(docker run -d --name "rv_${SERVER}_$$" -p "${PORT}:${PORT}/${TRANSPORT}" "$IMG" bash -c "$CMD" 2>/dev/null)
  [ -z "$CID" ] && { echo "ERROR"; return; }
  # 等端口就绪
  local ready=0 i
  for i in $(seq 1 40); do
    if [ "$TRANSPORT" = "tcp" ]; then
      if timeout 1 bash -c "echo > /dev/tcp/127.0.0.1/$PORT" 2>/dev/null; then ready=1; break; fi
    else
      sleep 0.3
      if [ "$i" -ge 12 ]; then ready=1; break; fi
    fi
    sleep 0.2
  done
  if [ "$ready" != "1" ]; then
    local RC0
    RC0=$(docker inspect -f "{{.State.ExitCode}}" "$CID" 2>/dev/null)
    docker rm -f "$CID" >/dev/null 2>&1
    if [ "$RC0" != "0" ] && [ -n "$RC0" ]; then echo "ILLEGAL"; else echo "ERROR"; fi
    return
  fi
  sleep 1
  python3 /tmp/replay_seed.py "$seed" "$PORT" "$TRANSPORT" >/dev/null 2>&1
  sleep 2
  local STATUS RC
  STATUS=$(docker inspect -f "{{.State.Status}}" "$CID" 2>/dev/null)
  RC=$(docker inspect -f "{{.State.ExitCode}}" "$CID" 2>/dev/null)
  docker rm -f "$CID" >/dev/null 2>&1
  if [ "$STATUS" = "running" ]; then echo "LEGAL"
  elif [ "$RC" = "0" ]; then echo "LEGAL"
  else echo "ILLEGAL"; fi
}

legal=0; illegal=0; error=0
for seed in "$SEED_DIR"/*.raw; do
  [ -f "$seed" ] || continue
  verdict=""
  for t in $(seq 1 "$RETRIES"); do
    v=$(run_once "$seed")
    if [ "$v" = "LEGAL" ]; then verdict="LEGAL"; break; fi
    if [ "$v" = "ERROR" ]; then verdict="ERROR"; break; fi
    # ILLEGAL：重试排除概率性抖动
  done
  [ -z "$verdict" ] && verdict="ILLEGAL"
  case "$verdict" in
    LEGAL) echo "LEGAL $(basename "$seed")"; legal=$((legal+1)) ;;
    ILLEGAL) echo "ILLEGAL $(basename "$seed")"; illegal=$((illegal+1)) ;;
    *) echo "ERROR $(basename "$seed")"; error=$((error+1)) ;;
  esac
done
echo "=== $SERVER: LEGAL=$legal ILLEGAL=$illegal ERROR=$error 总=$((legal+illegal+error)) ==="
