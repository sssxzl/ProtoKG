#!/bin/bash
# version: 2026-10-24-v2
# ↑ 版本标记：编排前用 `grep '^# version:'` 校验 VM 副本与本地一致（防版本漂移）
# ★ RQ3 干跑 oracle 批处理（VM 侧）—— 对 A/B/C/D 四组种子逐条重放判定
#
# 用法（在 VM 上，语料已 scp 到 /home/zxy/rq3_seeds/<组>/seeds/）：
#     bash rq3_oracle_batch.sh [组列表]
#
# 关键设计（技术方案 §4.2 / §4.4）：
#   · **串行**执行 —— 并发会让多个 ASAN 服务器互相污染（端口 + 媒体文件 fd + ASAN 状态）
#   · 端口从 **8571** 起、每条种子递增 —— 与容器内 fuzzing 的 8560 **物理隔离**
#     （容器独立 netns，宿主 8560 无监听；脚本启动前再查一次 ss 双重保险）
#   · 每条重试 3 次，LEGAL 早退（排除概率性 UAF 抖动）
#   · 整组墙钟看门狗 30 min，超时未跑的条目标 ERROR（不静默跳过）
#   · ASAN 服务器不可用 → 该组标记「干跑不可用」，**先修环境再跑 fuzz**
#
# 产出（回传到 Windows 的 derived/rq3/<组>/ 下）：
#   dryrun.tsv / dryrun_summary.json
set -euo pipefail

SEED_ROOT=/home/zxy/rq3_seeds
OUT_ROOT=/home/zxy/rq3_out
ORACLE_DIR=/home/zxy/live555-asan/testProgs
WORK=/tmp/rq3_oracle
PORT_BASE=8571
RETRIES=3
WATCHDOG=1800

# 注意：不可用 GROUPS 作变量名——bash 内建特殊变量（当前用户组 ID 数组），赋值无效。
GRP_LIST="${1:-A B C D}"

mkdir -p "$WORK"

# ---- 前置检查 ----
if [ ! -x "$ORACLE_DIR/testOnDemandRTSPServer" ]; then
  echo "!! ASAN 服务器不存在: $ORACLE_DIR/testOnDemandRTSPServer" >&2
  echo "   → 干跑不可用，先修环境再跑 fuzz" >&2
  exit 2
fi
# 端口隔离双重保险：宿主 8560/857x 不应有监听
if ss -tln 2>/dev/null | grep -qE ':(8560|857[0-9])\b'; then
  echo "!! 检测到 8560/857x 端口被占用，端口隔离不成立" >&2
  ss -tln 2>/dev/null | grep -E ':(8560|857[0-9])\b' >&2 || true
  exit 2
fi

# 把 oracle 脚本放到工作目录
cp -f "$(dirname "$0")/_oracle.py" "$WORK/oracle.py"
cp -f "$(dirname "$0")/_batch_oracle.py" "$WORK/batch_oracle.py"

PORT=$PORT_BASE
for g in $GRP_LIST; do
  SEED_DIR="$SEED_ROOT/$g/seeds"
  if [ ! -d "$SEED_DIR" ]; then
    echo "!! 缺少语料目录: $SEED_DIR" >&2
    exit 2
  fi
  N=$(ls "$SEED_DIR"/*.raw 2>/dev/null | wc -l)
  echo "=== 干跑组 $g（$N 条，端口自 $PORT 起）==="
  MANIFEST=""
  for cand in "$SEED_ROOT/$g/manifest.json" "$SEED_ROOT/$g/seeds/manifest.json"; do
    [ -f "$cand" ] && MANIFEST="$cand" && break
  done
  python3 "$WORK/batch_oracle.py" "$SEED_DIR" "$PORT" "$RETRIES" \
      --manifest "$MANIFEST" \
      --out "$OUT_ROOT/$g/dryrun.tsv" \
      --summary "$OUT_ROOT/$g/dryrun_summary.json" \
      --watchdog "$WATCHDOG" --group "$g"
  # 端口继续递增，组间不重叠
  PORT=$((PORT + N + 10))
done

echo
echo "=== 干跑完成，产出 ==="
ls -la "$OUT_ROOT"/*/dryrun.tsv "$OUT_ROOT"/*/dryrun_summary.json 2>/dev/null || true
