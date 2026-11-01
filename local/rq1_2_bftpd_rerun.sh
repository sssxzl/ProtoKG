#!/bin/bash
# RQ1.2 种子有效性（BFTPD FTP）—— 冒烟 2h / 正式 24h
# version: 2026-10-28-v1
# 对照 rq1_2_rerun.sh（RTSP）：IMG=rq2-bftpd、端口 21、-P FTP、目标 ./bftpd -D -c basic.conf
# chatafl 走宿主机代理 192.168.37.1:18080（rq2-bftpd 的 chat-llm.c 已硬编码该地址，无需内嵌代理）
set -e
IMG=rq2-bftpd:latest
SEED_REUSE=/home/zxy/rq2_ftp_seeds/seed_reuse
PROTORAG=/home/zxy/rq2_ftp_seeds/protorag
BASE=/home/zxy/rq2_ftp_out

R1=${1:-1}
R2=${2:-5}
DUR_H=${3:-24}
DUR=$((DUR_H * 3600))
BOOTSTRAP_BUDGET=$((6 * 3600))
TIMEOUT=$((DUR + BOOTSTRAP_BUDGET))

declare -A FUZZER
FUZZER[chatafl]=/home/ubuntu/chatafl/afl-fuzz
FUZZER[aflnet]=/home/ubuntu/aflnet/afl-fuzz

launch() {
  local group=$1 fuzzer=$2 seeds=$3 rep=$4
  local name="rq2ftp_${group}_r${rep}"
  local out="$BASE/$group/r$rep"
  mkdir -p "$out"
  docker run -d --name "$name" --user root --cpus=1 --memory=1.5g --network bridge \
    -v "$seeds:/seeds_ro:ro" -v "$out:/out" \
    "$IMG" bash -c "cp -r /seeds_ro /seeds_work && cd /home/ubuntu/experiments/bftpd && { ( while [ ! -s /out/fuzzer_stats ]; do sleep 5; done; sleep $DUR; pkill -TERM afl-fuzz 2>/dev/null; sleep 5; pkill -KILL afl-fuzz 2>/dev/null || true ) & timeout -k 2s --preserve-status $TIMEOUT ${FUZZER[$fuzzer]} -d -i /seeds_work -x /home/ubuntu/experiments/ftp.dict -o /out -N tcp://127.0.0.1/21 -P FTP -D 10000 -q 3 -s 3 -E -K -R -m none -t 1000+ -c /home/ubuntu/experiments/clean ./bftpd -D -c /home/ubuntu/experiments/basic.conf; }"
  echo "  [启动] $name ($group/$fuzzer rep$rep)"
}

echo "=== BFTPD RQ1.2：${DUR_H}h，rep ${R1}-${R2}，chatafl 走宿主机代理 192.168.37.1:18080 ==="
for rep in $(seq $R1 $R2); do
  launch seed_reuse_chatafl chatafl "$SEED_REUSE" "$rep"
  launch seed_reuse_aflnet aflnet "$SEED_REUSE" "$rep"
  launch protorag_chatafl chatafl "$PROTORAG" "$rep"
  launch protorag_aflnet aflnet "$PROTORAG" "$rep"
done
echo "=== BFTPD RQ1.2 容器启动完成 ==="
docker ps --format '{{.Names}}' | grep -c '^rq2ftp_' | xargs echo '运行中容器数:'
