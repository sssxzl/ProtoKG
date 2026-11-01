#!/bin/bash
# RQ2 通用编排脚本：对指定目标启动 4 组 × N 重复的 fuzzing 容器
#
# 用法:
#   rq2_launch_target.sh <target> <reps> <duration_sec> <seed_reuse_dir> <protorag_dir> [out_base]
#
#   target        : bftpd | proftpd | pure-ftpd | exim | kamailio | lightftp
#   reps          : 每组重复次数（4 组 = seed_reuse/protorag × chatafl/aflnet）
#   duration_sec  : 单次 fuzz 时长（秒）
#   seed_reuse_dir: Seed Reuse 原始种子目录（ProFuzzBench 官方种子，如 /home/zxy/rq2_seeds/<t>/seed_reuse）
#   protorag_dir  : ProtoRAG 协议级种子目录（后续重新生成，路径待填）
#   out_base      : 输出根目录（默认 /home/zxy/rq2_out_<target>）
#
# 镜像: rq2-<target>:latest（已统一 DeepSeek 后端，黄金标准 chat-llm.h/.c）
# 每组 fuzzer: chatafl = /home/ubuntu/chatafl/afl-fuzz（增强型）, aflnet = /home/ubuntu/aflnet/afl-fuzz
set -e

TARGET=$1; REPS=$2; DUR=$3; SEED_REUSE=$4; PROTORAG=$5; OUT_BASE=${6:-/home/zxy/rq2_out_$TARGET}
IMG="rq2-$TARGET:latest"

case "$TARGET" in
  bftpd)
    PROTO=FTP; NET="tcp://127.0.0.1/21";   DICT="/home/ubuntu/experiments/ftp.dict"
    CLEAN="/home/ubuntu/experiments/clean";  WORKDIR="/home/ubuntu/experiments/bftpd"
    SERVER="./bftpd -D -c /home/ubuntu/experiments/basic.conf"; PRECMD=""
    ;;
  proftpd)
    PROTO=FTP; NET="tcp://127.0.0.1/21";   DICT="/home/ubuntu/experiments/ftp.dict"
    CLEAN="/home/ubuntu/experiments/clean";  WORKDIR="/home/ubuntu/experiments/proftpd"
    SERVER="./proftpd -n -c /home/ubuntu/experiments/basic.conf -X"; PRECMD=""
    ;;
  pure-ftpd)
    PROTO=FTP; NET="tcp://127.0.0.1/21";   DICT="/home/ubuntu/experiments/ftp.dict"
    CLEAN="/home/ubuntu/experiments/clean";  WORKDIR="/home/ubuntu/experiments/pure-ftpd"
    SERVER="src/pure-ftpd -A"; PRECMD=""
    ;;
  exim)
    PROTO=SMTP; NET="tcp://127.0.0.1/25";  DICT="/home/ubuntu/experiments/smtp.dict"
    CLEAN="/home/ubuntu/experiments/clean";  WORKDIR="/home/ubuntu/experiments/exim"
    SERVER="exim -bd -d -oX 25 -oP /var/lock/exim.pid"
    PRECMD="cp ./src/build-Linux-x86_64/exim /usr/exim/bin/exim"
    ;;
  kamailio)
    PROTO=SIP;  NET="udp://127.0.0.1/5060"; DICT=""
    CLEAN="/home/ubuntu/experiments/run_pjsip"; WORKDIR="/home/ubuntu/experiments/kamailio"
    SERVER="./src/kamailio -f /home/ubuntu/experiments/kamailio-basic.cfg -L src/modules -Y runtime_dir -n 1 -D -E"
    PRECMD="export KAMAILIO_MODULES=src/modules KAMAILIO_RUNTIME_DIR=runtime_dir"
    ;;
  lightftp)
    PROTO=FTP; NET="tcp://127.0.0.1/2200"; DICT="/home/ubuntu/experiments/ftp.dict"
    CLEAN="/home/ubuntu/experiments/ftpclean"; WORKDIR="/home/ubuntu/experiments/LightFTP/Source/Release"
    SERVER="./fftp fftp.conf 2200"; PRECMD=""
    ;;
  *)
    echo "未知目标: $TARGET（支持 bftpd|proftpd|pure-ftpd|exim|kamailio|lightftp）"; exit 1
    ;;
esac

DICT_ARG=""
[ -n "$DICT" ] && DICT_ARG="-x $DICT"

declare -A FUZZER
FUZZER[chatafl]=/home/ubuntu/chatafl/afl-fuzz
FUZZER[aflnet]=/home/ubuntu/aflnet/afl-fuzz

launch() {
  local group=$1 fuzzer=$2 seeds=$3 rep=$4
  local name="rq2_${TARGET}_${group}_r${rep}"
  local out="$OUT_BASE/$group/r$rep"
  mkdir -p "$out"
  # 容器内复制种子到 /seeds_work，避免增强写回污染原始目录 + 重复间污染
  docker run -d --name "$name" --user root --cpus=1 --memory=1.5g \
    -v "$seeds:/seeds_ro:ro" -v "$out:/out" \
    "$IMG" bash -c "cp -r /seeds_ro /seeds_work && cd $WORKDIR && $PRECMD && timeout -k 2s --preserve-status $DUR ${FUZZER[$fuzzer]} -d -i /seeds_work -o /out $DICT_ARG -N $NET -P $PROTO -c $CLEAN -m none -t 1000 -- $SERVER"
  echo "  [启动] $name  ($group/$fuzzer rep$rep)"
}

for rep in $(seq 1 "$REPS"); do
  launch seed_reuse_chatafl chatafl "$SEED_REUSE" "$rep"
  launch seed_reuse_aflnet aflnet "$SEED_REUSE" "$rep"
  launch protorag_chatafl  chatafl "$PROTORAG"   "$rep"
  launch protorag_aflnet  aflnet "$PROTORAG"   "$rep"
done

echo "=== $TARGET 编排完成（$((REPS*4)) 容器） ==="
docker ps --format "{{.Names}}" | grep -c "^rq2_${TARGET}_" | xargs echo "运行中容器数:"
