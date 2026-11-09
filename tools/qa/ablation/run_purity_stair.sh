#!/usr/bin/env bash
# tools/qa/ablation/run_purity_stair.sh —— **2×2 因子设计**的「单源纯净度阶梯」。
#
# ★ 目的：把「协议骨架里的来源维度」与「绕过 source_set 的跨源旁路」两个因素
#   **分离**，回答：RFC 单源实验**到底**有多少知识不是 RFC 给的？
#
#   因子 A（骨架维度）：
#     A0 = 全量骨架（含 source 侧 + traffic 侧）
#     A1 = 纯 RFC 骨架（--exclude-skeleton-dims source traffic）
#   因子 B（跨源旁路）：
#     B0 = 默认（⑤ 层底料含 vuln/traffic 知识；allowed_methods 源码白名单裁剪）
#     B1 = --strict-source-only（全部关掉）
#
#   四档：
#     S0 = A0+B0  ← **当前基线**（历史实验与基线文件都是这一档）
#     S1 = A0+B1  ← 只关旁路
#     S2 = A1+B0  ← 只换骨架（= 上一轮的消融 C 档）
#     S3 = A1+B1  ← ★ **真·纯净 RFC**
#
# ★ 纪律：三档/四档必须在**同一条命令**内跑完并立即比对（中间产物会被外部清掉）。
# ★ 纪律：build_hub 的批次清空会删掉各源 ``semantic/``（语义四库），
#   而语义规则**不能从 kb 重建**（需 LLM）⇒ 每档构建后**必须**恢复，
#   否则 ③ 层少 6 条 ⇒ 绝对数失真。
set -u

PY="E:/app/Anaconda3/python.exe"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT" || exit 1

OUT=tools/qa/ablation/_out
PROTO=rtsp
BACKUP_ROOT="${PROTORAG_SEMANTIC_BACKUP:-}"
if [ -z "$BACKUP_ROOT" ]; then
  if [ -d "$REPO_ROOT/.semantic_backup" ]; then
    BACKUP_ROOT="$REPO_ROOT/.semantic_backup"
  else
    BACKUP_ROOT="E:/科研/想法idea/ProtoRAG_快照_20261102/semantic_backup"
  fi
fi
export PROTORAG_SEMANTIC_BACKUP="$BACKUP_ROOT"
mkdir -p "$OUT" out

restore_semantic () {
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

run_step () {
  name="$1"; dims="$2"; strict="$3"
  echo ""
  echo "######## $name  (骨架维度=${dims:-全量}  旁路=${strict:-默认}) ########"
  # ★ 跑前**清空输出目录**：旧产物残留会污染 corpus_gate 的 G1/G2 统计
  #   （实测：S0 目录残留 47 个上一轮的 .raw ⇒ G2 虚高）
  rm -rf "out/pur_$name" "out/pur_$name.build.log" "out/pur_$name.seed.log"
  if [ -n "$dims" ]; then
    $PY scripts/build_hub.py --protocol "$PROTO" --sources rfc \
        --exclude-skeleton-dims $dims > "out/pur_$name.build.log" 2>&1
  else
    $PY scripts/build_hub.py --protocol "$PROTO" --sources rfc \
        > "out/pur_$name.build.log" 2>&1
  fi
  echo "[build rc=$?]"
  restore_semantic
  if [ "$strict" = "1" ]; then
    $PY scripts/seedgen.py --protocol "$PROTO" --out "out/pur_$name" \
        --manifest --focus-group B --strict-source-only \
        > "out/pur_$name.seed.log" 2>&1
  else
    $PY scripts/seedgen.py --protocol "$PROTO" --out "out/pur_$name" \
        --manifest --focus-group B > "out/pur_$name.seed.log" 2>&1
  fi
  echo "[seedgen rc=$?]"
  $PY scripts/corpus_gate.py --protocol "$PROTO" --seed-dir "out/pur_$name" \
      --group B --json > "$OUT/pgate_$name.json" 2> "$OUT/pgate_$name.err"
  echo "[gate rc=$?]"
  $PY tools/qa/ablation/purity_probe.py --protocol "$PROTO" \
      --seed-dir "out/pur_$name" --arm "$name" \
      --gate "$OUT/pgate_$name.json" --out "$OUT/parm_$name.json" \
      > /dev/null 2> "$OUT/pprobe_$name.err"
  echo "[probe rc=$?]"
}

run_step S0 ""        0     # 当前基线
run_step S1 ""        1     # 只关旁路
run_step S2 "source traffic" 0   # 只换骨架
run_step S3 "source traffic" 1   # ★ 真·纯净 RFC

echo ""
echo "######## 恢复基线档（S0）作为最终中枢状态 ########"
$PY scripts/build_hub.py --protocol "$PROTO" --sources rfc \
    > "out/pur_restore.build.log" 2>&1
echo "[restore rc=$?]"
restore_semantic

echo ""
echo "######## 纯净度阶梯汇总 ########"
$PY tools/qa/ablation/purity_summary.py
