#!/usr/bin/env bash
# qa/batch23_ablation/run_ablation.sh —— 协议骨架**来源维度消融**三档对照。
#
# ★ 纪律：QA 目录下的实验产物会被外部清掉 ⇒ 三档必须在**同一条命令**内
#   跑完并立即统计比对（不能分三次会话跑）。
# ★ 纪律：build_hub 默认**清空中枢** ⇒ 三档必须**串行**，且最后恢复 A 档。
# ★ Windows 路径坑：`--out` 必须用**相对路径**（`/tmp/x` 会被解析成 C:\tmp\x）。
#
# ★★ 关键（同态保障）：build_hub 的批次清空会删掉各源的 ``semantic/``
#   （语义四库）。规则**不能从 kb 重建**（需 LLM）⇒ 每档构建后必须把
#   语义规则**恢复回来**，否则三档不在同一状态上：
#     · 少了 semantic ⇒ bundle.legal_boundary 为空 ⇒ ③ 层少 6 条
#       ⇒ rtsp/B 由 85 条掉到 79 条 ⇒ 绝对数全部失真。
#   恢复源 = 仓库外备份 ``SEMANTIC_BACKUP_ROOT``（build_hub 自己写的备份）。
set -u

PY="E:/app/Anaconda3/python.exe"

# ★ 仓库根**从脚本自身位置推导**（不能硬编码绝对路径）
#   —— 否则在**副本**里跑这个脚本时，实际 cd 到了主仓库
#      ⇒ 「副本里跑通」是假的（产物落在主仓库、副本的 out/ 里什么都没有）。
#   ★ 已踩过一次：本轮副本自测时 build/seedgen 全在主仓库执行，
#     而副本的 derived/model/per_source 根本没被碰过。
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT" || exit 1

OUT=tools/qa/ablation/_out
PROTO=rtsp

# 语义四库备份根：环境变量 > 仓库内 .semantic_backup（副本用）> 仓库外默认（主仓库用）
BACKUP_ROOT="${PROTORAG_SEMANTIC_BACKUP:-}"
if [ -z "$BACKUP_ROOT" ]; then
  if [ -d "$REPO_ROOT/.semantic_backup" ]; then
    BACKUP_ROOT="$REPO_ROOT/.semantic_backup"
  else
    BACKUP_ROOT="E:/科研/想法idea/ProtoRAG_快照_20261102/semantic_backup"
  fi
fi
# ★ 让 build_hub.py 的备份也落到同一个根（否则副本跑构建会污染主仓库的备份）
export PROTORAG_SEMANTIC_BACKUP="$BACKUP_ROOT"

mkdir -p "$OUT" out

restore_semantic () {
  # 把仓库外备份的 semantic 恢复到中枢（逐源）
  local n=0
  if [ -d "$BACKUP_ROOT/$PROTO" ]; then
    for src in "$BACKUP_ROOT/$PROTO"/*; do
      [ -d "$src" ] || continue
      sname=$(basename "$src")
      mkdir -p "derived/model/per_source/$PROTO/$sname/semantic"
      cp -p "$src"/*.jsonl "derived/model/per_source/$PROTO/$sname/semantic/" 2>/dev/null && \
        n=$((n + $(ls "$src"/*.jsonl 2>/dev/null | wc -l)))
    done
  fi
  echo "[语义] 已恢复 $n 个规则文件（保证各档同态）"
}

run_arm () {
  name="$1"; shift
  dims="$*"
  echo ""
  echo "################ ARM $name  (exclude-skeleton-dims: ${dims:-none}) ################"
  if [ -n "$dims" ]; then
    $PY scripts/build_hub.py --protocol "$PROTO" --sources rfc \
        --exclude-skeleton-dims $dims > "out/ab_$name.build.log" 2>&1
  else
    $PY scripts/build_hub.py --protocol "$PROTO" --sources rfc \
        > "out/ab_$name.build.log" 2>&1
  fi
  echo "[build rc=$?]  日志: out/ab_$name.build.log"
  restore_semantic
  $PY scripts/seedgen.py --protocol "$PROTO" --out "out/abl_$name" \
      --manifest --focus-group B > "out/ab_$name.seed.log" 2>&1
  echo "[seedgen rc=$?]  日志: out/ab_$name.seed.log"
  $PY scripts/corpus_gate.py --protocol "$PROTO" --seed-dir "out/abl_$name" \
      --group B --json > "$OUT/gate_$name.json" 2> "$OUT/gate_$name.err"
  echo "[gate rc=$?]  日志: $OUT/gate_$name.json"
  $PY tools/qa/ablation/stats.py --protocol "$PROTO" --seed-dir "out/abl_$name" \
      --arm "$name" --gate "$OUT/gate_$name.json" \
      --exclude-dims $dims \
      --out "$OUT/arm_$name.json" > /dev/null 2> "$OUT/stats_$name.err"
  echo "[stats rc=$?]  → $OUT/arm_$name.json"
}

# A 全量（含骨架 source+traffic 两侧）
run_arm A
# B 去 source 侧（只保留 traffic 观测侧骨架）
run_arm B source
# C 纯 RFC（骨架全排除 ⇒ 只剩 RFC 源自己抽出的知识）
run_arm C source traffic

echo ""
echo "################ 恢复 A 档（全量骨架）作为最终中枢状态 ################"
$PY scripts/build_hub.py --protocol "$PROTO" --sources rfc \
    > "out/ab_restore.build.log" 2>&1
echo "[restore build rc=$?]"
restore_semantic

echo ""
echo "################ 三档对比汇总 ################"
# 工件入 local/ablation_rtsp/（入库留档）；_out/ 是运行时目录（gitignore）
mkdir -p local/ablation_rtsp
cp -f "$OUT"/arm_*.json "$OUT"/gate_*.json local/ablation_rtsp/ 2>/dev/null
$PY tools/qa/ablation/summarize.py
