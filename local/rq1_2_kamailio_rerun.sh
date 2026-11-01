#!/bin/bash
# RQ1.2 种子有效性（Kamailio SIP）—— 冒烟 2h / 正式 24h
# version: 2026-10-28-v1
# 对照 rq1_2_rerun.sh（RTSP）与 rq1_2_bftpd_rerun.sh（FTP）：
#   IMG=rq2-kamailio、端口 5060、-P SIP、UDP 传输（-N udp://，与 RTSP/FTP 的 TCP 不同）
#   目标 ./src/kamailio -f kamailio-basic.cfg -L src/modules -Y runtime_dir -n 1 -D -E
#   状态复位 -c run_pjsip（镜像原生：kill+重启 pjsua 客户端维持注册态，依赖镜像内 pjproject）
# chatafl 走宿主机代理 192.168.37.1:18080（chat-llm.c 硬编码，同 BFTPD，无需内嵌代理）
set -e
IMG=rq2-kamailio:latest
SEED_REUSE=/home/zxy/rq1_sip_seeds/seed_reuse
PROTORAG=/home/zxy/rq1_sip_seeds/protorag
DICT=/home/zxy/rq1_sip_seeds/sip.dict
BASE=/home/zxy/rq1_sip_out

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
  local name="rq1sip_${group}_r${rep}"
  local out="$BASE/$group/r$rep"
  mkdir -p "$out"
  docker run -d --name "$name" --user root --cpus=1 --memory=2g --network bridge \
    -v "$seeds:/seeds_ro:ro" -v "$DICT:/sip.dict:ro" -v "$out:/out" \
    "$IMG" bash -c "cp -r /seeds_ro /seeds_work && export WORKDIR=/home/ubuntu/experiments KAMAILIO_MODULES=src/modules KAMAILIO_RUNTIME_DIR=runtime_dir && cd /home/ubuntu/experiments/kamailio && { ( while [ ! -s /out/fuzzer_stats ]; do sleep 5; done; sleep $DUR; pkill -TERM afl-fuzz 2>/dev/null; sleep 5; pkill -KILL afl-fuzz 2>/dev/null || true ) & timeout -k 2s --preserve-status $TIMEOUT ${FUZZER[$fuzzer]} -d -i /seeds_work -x /sip.dict -o /out -N udp://127.0.0.1/5060 -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -R -m none -t 3000+ -c /home/ubuntu/experiments/run_pjsip ./src/kamailio -f /home/ubuntu/experiments/kamailio-basic.cfg -L src/modules -Y runtime_dir -n 1 -D -E; }"
  echo "  [启动] $name ($group/$fuzzer rep$rep)"
}

echo "=== Kamailio RQ1.2：${DUR_H}h，rep ${R1}-${R2}，chatafl 走宿主机代理 192.168.37.1:18080 ==="
for rep in $(seq $R1 $R2); do
  launch seed_reuse_chatafl chatafl "$SEED_REUSE" "$rep"
  launch seed_reuse_aflnet aflnet "$SEED_REUSE" "$rep"
  launch protorag_chatafl chatafl "$PROTORAG" "$rep"
  launch protorag_aflnet aflnet "$PROTORAG" "$rep"
done
echo "=== Kamailio RQ1.2 容器启动完成 ==="
docker ps --format '{{.Names}}' | grep -c '^rq1sip_' | xargs echo '运行中容器数:'
