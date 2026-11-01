#!/bin/bash
# version: 2026-10-24-v2
# ↑ 版本标记：编排前用 `grep '^# version:'` 校验 VM 副本与本地一致（防版本漂移）
# ★ RQ3 队列快照器（T+1h / T+2h）—— M9 早期指标的必需采集
#
# 用法（VM 上）：nohup bash rq3_snapshot.sh &
#
# 为什么必须做：AFL 队列轮转会让所有种子最终都被变异，排序的效应**只体现在前期
# 预算分布**。要证明 H2（排序把变异预算集中到漏洞边界层），必须有 T+1h / T+2h
# 的队列快照来计算 bp_layer_share_T1h（③层种子派生占比）——末态快照算不出这个量。
#
# T0 定义：T0 = 各容器 fuzzer_stats 的 start_time（与 watcher 的计时起点一致）。
#          快照器**必须读取每个容器自己的 T0**，而不是用启动脚本的时刻。
set -uo pipefail

SNAP_ROOT=/home/zxy/rq3_snap
SNAP_SECONDS_LIST="${*:-3600 7200}"

mkdir -p "$SNAP_ROOT"

# 读取容器的 T0（fuzzer_stats.start_time）
container_t0() {
  docker exec "$1" bash -c \
    "grep '^start_time' /out/fuzzer_stats 2>/dev/null | awk '{print \$3}'" \
    2>/dev/null | head -1
}

now_epoch() { date +%s; }

for T in $SNAP_SECONDS_LIST; do
  echo "[快照] 等待 T+${T}s ..."
  # 轮询到点（每个容器按自己的 T0 计算）
  while :; do
    DONE=1
    for n in $(docker ps --format '{{.Names}}' | grep '^rq3_'); do
      T0=$(container_t0 "$n")
      if [ -z "$T0" ]; then
        continue
      fi
      ELAPSED=$(( $(now_epoch) - T0 ))
      if [ "$ELAPSED" -lt "$T" ]; then
        DONE=0
        break
      fi
    done
    [ "$DONE" = "1" ] && break
    sleep 30
  done

  TAG="T${T}s"
  for n in $(docker ps --format '{{.Names}}' | grep '^rq3_'); do
    d="$SNAP_ROOT/$TAG/$n"
    mkdir -p "$d"
    # 只导出「文件名 + MD5 + 血缘根名」，不搬运全量队列内容
    docker exec "$n" bash -c '
      cd /out/queue 2>/dev/null || exit 0
      for f in *; do
        printf "%s\t%s\t%s\n" "$f" "$(md5sum "$f" | cut -d" " -f1)" \
          "$(echo "$f" | sed -n "s/^id:[0-9]*,orig://p")"
      done' > "$d/queue_index.tsv" 2>/dev/null || true
    docker exec "$n" bash -c \
      'cp /out/plot_data /out/fuzzer_stats '"$d"'/ 2>/dev/null' || true
    echo "[快照] $n → $d ($(wc -l < "$d/queue_index.tsv" 2>/dev/null || echo 0) 条)"
  done
done

echo "[快照] 完成"
