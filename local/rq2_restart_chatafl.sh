#!/bin/bash
# 重启 live555 的 8 个 chatafl 容器（新镜像已含 curl 超时 + stall 转义修复）
# 只重启 chatafl，不动 aflnet（aflnet 不调 LLM，正常 fuzzing 中）
set -e
IMG=rq2-live555:latest
SEED_REUSE=/home/zxy/rq2_seeds/seed_reuse
PROTORAG=/home/zxy/rq1_protorag_seeds
BASE=/home/zxy/rq2_out

restart() {
  local group=$1 seeds=$2 rep=$3
  local name="rq2_${group}_r${rep}"
  local out="$BASE/$group/r$rep"
  # 停旧容器
  docker stop "$name" 2>/dev/null || true
  docker rm "$name" 2>/dev/null || true
  # 清理 /out（afl-fuzz -o 要求空目录；容器 root 写入，需 sudo 删除）
  sudo rm -rf "$out"
  mkdir -p "$out"
  # 重启（与 rq2_launch.sh 完全相同的命令）
  docker run -d --name "$name" --user root --cpus=1 --memory=1.5g \
    --entrypoint "" \
    -v "$seeds:/seeds_ro:ro" -v "$out:/out" \
    "$IMG" bash -c "cp -r /seeds_ro /seeds_work && cd /home/ubuntu/experiments/live/testProgs && timeout 86400 /home/ubuntu/chatafl/afl-fuzz -d -i /seeds_work -x /home/ubuntu/experiments/rtsp.dict -o /out -N tcp://127.0.0.1/8560 -P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 1000 -- ./testOnDemandRTSPServer 8560"
  echo "  [重启] $name"
}

for rep in 1 2 3 4; do
  restart seed_reuse_chatafl "$SEED_REUSE" $rep
  restart protorag_chatafl  "$PROTORAG"   $rep
done
echo "=== 8 个 chatafl 容器重启完成 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep "chatafl"
