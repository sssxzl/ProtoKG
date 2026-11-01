#!/bin/bash
# ★★ RQ1.2 Live555 实验停后「采集 + 回填 + 实验记录」收尾脚本（QA 交付）
#
# 用法（在 Windows 本机 Git Bash / WSL）：
#     bash local/rq1_2_finalize.sh
#     bash local/rq1_2_finalize.sh --force          # 忽略"已回填"标记，强制重跑回填
#     bash local/rq1_2_finalize.sh --collect-only    # 只采集，不回填、不写记录
#     bash local/rq1_2_finalize.sh --fill-only       # 只回填 + 写记录（跳过采集）
#     bash local/rq1_2_finalize.sh --docx "<abs path>"   # 指定目标 docx（默认正式文件）
#
# ════════════════════════════════════════════════════════════════════════════
# 幂等与重入设计
# ════════════════════════════════════════════════════════════════════════════
#   阶段用「标记文件」记录完成状态，标记落在 $STATE_DIR：
#     .stage_collect  —— 采集完成（4 个 CSV 已落到本地）
#     .stage_fill     —— docx 回填 + 回读校验完成
#     .stage_record   —— 实验记录 md 已生成
#
#   · 幂等：重复执行 → 已完成的阶段直接跳过；CSV 与 md 用原子写（.tmp → mv）；
#           docx 回填是「幂等覆写」（同一份 CSV → 同样的单元格值）。
#   · 可重入：任何阶段失败 → 不写该阶段的标记 → 重跑时**只补做失败/未做的阶段**。
#           例：回填失败后重跑，只重跑回填与记录，不重新采集。
#   · 安全：脚本**只读**地检查 rq2_* 容器；**从不** kill / restart / rm 这些容器。
#           若检测到 rq2_* 仍在跑 → 明确退出并提示，绝不擅自操作。
# ════════════════════════════════════════════════════════════════════════════
set -uo pipefail

# ── 配置 ────────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${RQ3_PYTHON:-E:/app/Anaconda3/python.exe}"
SSH_KEY="${RQ3_SSH_KEY:-$HOME/.ssh/vm_ubuntu_zxy}"
VM="${RQ3_VM:-zxy@192.168.37.130}"

DATA_DIR="$ROOT/derived/analysis/data/rq1_2"
#: 10-24 20:00 中间态快照目录（供实验记录 §7 做「中间态 → 最终态」差异对比）
INTERIM_DIR="$ROOT/derived/analysis/data/rq1_2_interim_20261024"
#: 污染证据链复核结果（E1–E6 + V8，由 qa_evidence_chains.py 产出）
EVIDENCE_JSON="$ROOT/derived/analysis/qa_rq1_2/qa_evidence_chains.json"
STATE_DIR="$DATA_DIR/.state"
DOCX_DEFAULT="$ROOT/local/实验方案_详细版.docx"
RECORD_MD="$ROOT/local/RQ1_2_Live555实验记录.md"

# 采集产物（VM 上的名字）
VM_P1=/home/zxy/rq1_2_p1.csv
VM_P2=/home/zxy/rq1_2_p2.csv
VM_SUM=/home/zxy/rq1_2_summary.csv
VM_TS=/home/zxy/rq1_2_timeseries.csv

LOCAL_P1="$DATA_DIR/rq1_2_p1.csv"
LOCAL_P2="$DATA_DIR/rq1_2_p2.csv"
LOCAL_SUM="$DATA_DIR/rq1_2_summary.csv"
LOCAL_TS="$DATA_DIR/rq1_2_timeseries.csv"

# 表 4 的定位签名（★ 运行时三重定位，绝不硬编码 table_id）
TABLE_INDEX=4
TABLE_HEADER_SIG="n_states(P1)"
TABLE_ROWS=5
TABLE_COLS=9

FORCE=0; COLLECT_ONLY=0; FILL_ONLY=0
DOCX_PATH="$DOCX_DEFAULT"
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --collect-only) COLLECT_ONLY=1 ;;
    --fill-only) FILL_ONLY=1 ;;
    --docx) shift; DOCX_PATH="$1" ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
  shift
done

step() { echo; echo "=============================================="; echo "== $*"; echo "=============================================="; }
info() { echo "  [INFO] $*"; }
ok()   { echo "  [PASS] $*"; }
bad()  { echo "  [FAIL] $*"; }
warn() { echo "  [WARN] $*"; }

mkdir -p "$DATA_DIR" "$STATE_DIR"

# ════════════════════════════════════════════════════════════════════════════
# 阶段 0：前置检查（容器是否已停）
# ════════════════════════════════════════════════════════════════════════════
step "阶段 0：前置检查（rq2_* 容器是否已停）"

DATA_FINAL=1
if [ "$COLLECT_ONLY" = "1" ] || [ "$FILL_ONLY" = "1" ]; then
  info "指定了 --collect-only/--fill-only → 跳过容器停止检查"
else
  RUNNING=$(ssh -i "$SSH_KEY" "$VM" \
    'docker ps --format "{{.Names}}" | grep -c "^rq2_" || true' 2>/dev/null | tr -d '[:space:]')
  if [ -z "$RUNNING" ]; then
    bad "无法连接 VM $VM —— 停止（不做任何操作）"
    exit 4
  fi
  if [ "$RUNNING" != "0" ]; then
    echo "  ✗✗✗ 仍有 $RUNNING 个 rq2_* 容器在跑 —— RQ1.2 实验尚未停止 ✗✗✗"
    echo "     本脚本**不会** kill / restart / rm 任何 rq2_* 容器。"
    echo "     请等到实验结束（计划 2026-10-25 11:09）后再执行。"
    echo "     若只想先取数（容器仍跑，数值非最终），用 --collect-only 并注意数值会变。"
    exit 5
  fi
  DATA_FINAL=1
  ok "rq2_* 容器已全部停止（$RUNNING 个在跑）→ 可以采集最终值"
fi

# ════════════════════════════════════════════════════════════════════════════
# 阶段 1：采集（VM 上跑 rq1_collect_live555.sh → 拉 4 个 CSV 回本地）
# ════════════════════════════════════════════════════════════════════════════
step "阶段 1：VM 采集（P1/P2/summary/timeseries）"

if [ "$FILL_ONLY" = "1" ]; then
  info "--fill-only → 跳过采集"
elif [ -f "$STATE_DIR/.stage_collect" ] && [ "$FORCE" != "1" ]; then
  ok "阶段 1 已完成（存在 .stage_collect）→ 跳过（--force 可强制重跑）"
else
  # 1a. 先确认采集脚本在 VM 上
  if ! ssh -i "$SSH_KEY" "$VM" 'test -x /home/zxy/rq1_collect_live555.sh' 2>/dev/null; then
    bad "VM 上缺少 /home/zxy/rq1_collect_live555.sh —— 无法采集"
    exit 6
  fi
  # 1b. 执行采集（幂等：脚本本身写 .tmp 再 mv）
  info "执行 bash /home/zxy/rq1_collect_live555.sh ..."
  COLLECT_LOG=$(ssh -i "$SSH_KEY" "$VM" 'bash /home/zxy/rq1_collect_live555.sh 2>&1')
  COLLECT_RC=$?
  echo "$COLLECT_LOG" | tail -30 | sed 's/^/    /'
  if [ "$COLLECT_RC" != "0" ]; then
    bad "采集脚本退出码 $COLLECT_RC —— 阶段 1 失败（不写标记，可重入重跑）"
    exit 7
  fi
  # ★ 数据状态标记：容器仍在跑 → 本次采集是**中间态**，不可当最终值用
  if [ "$COLLECT_ONLY" = "1" ]; then
    echo "interim" > "$STATE_DIR/.data_status"
    info "⚠ --collect-only → 本次数据标记为 **中间态**（实验未停，数值会变）"
    info "  实验停止后请重跑（不带 --collect-only）以生成最终值"
  else
    echo "final" > "$STATE_DIR/.data_status"
  fi
  # 1c. 拉回 4 个 CSV
  for f in p1 p2 summary timeseries; do
    src="/home/zxy/rq1_2_${f}.csv"
    dst="$DATA_DIR/rq1_2_${f}.csv"
    if ! scp -q -i "$SSH_KEY" "$VM:$src" "$dst.tmp" 2>/dev/null; then
      bad "拉取 $src 失败"
      exit 8
    fi
    mv "$dst.tmp" "$dst"
    ok "已拉取 $src → $dst（$(wc -l < "$dst") 行）"
  done
  # 1d. 拉回附加证据文件（**可选**：缺失不致命，但会导致实验记录缺少
  #     §3.3 pooled / §3.4 执行量归一化 / §5.5 崩溃样本散文核查 等章节）
  #     - extra_crashdist       崩溃首次出现时刻
  #     - extra_hangs           unique_hangs 明细
  #     - extra_lineage         队列血缘（污染指纹）
  #     - extra_seedprovenance  种子语料散文溯源
  #     - extra_prose.txt       散文核查完整报告
  for f in extra_crashdist extra_hangs extra_lineage extra_seedprovenance; do
    src="/home/zxy/rq1_2_${f}.csv"
    dst="$DATA_DIR/rq1_2_${f}.csv"
    if scp -q -i "$SSH_KEY" "$VM:$src" "$dst.tmp" 2>/dev/null; then
      mv "$dst.tmp" "$dst"
      ok "已拉取 $src → $dst（$(wc -l < "$dst") 行）"
    else
      rm -f "$dst.tmp"
      warn "可选文件 $src 不存在 → 跳过（实验记录将缺少对应章节）"
    fi
  done
  src="/home/zxy/rq1_2_extra_prose.txt"
  dst="$DATA_DIR/rq1_2_extra_prose.txt"
  if scp -q -i "$SSH_KEY" "$VM:$src" "$dst.tmp" 2>/dev/null; then
    mv "$dst.tmp" "$dst"
    ok "已拉取 $src → $dst"
  else
    rm -f "$dst.tmp"
    warn "可选文件 $src 不存在 → 跳过（实验记录将缺少 §5.5 散文核查）"
  fi
  touch "$STATE_DIR/.stage_collect"
  ok "阶段 1 完成（已写 .stage_collect）"
fi

# ════════════════════════════════════════════════════════════════════════════
# 阶段 2：docx 回填（运行时三重定位表 4 → 写 col3..col9 → save → 回读校验）
# ════════════════════════════════════════════════════════════════════════════
step "阶段 2：docx 回填（表 4，行 2..5 的 col3..col9）"

if [ "$COLLECT_ONLY" = "1" ]; then
  info "--collect-only → 跳过回填"
elif [ -f "$STATE_DIR/.stage_fill" ] && [ "$FORCE" != "1" ]; then
  ok "阶段 2 已完成（存在 .stage_fill）→ 跳过（--force 可强制重跑）"
else
  if [ ! -f "$LOCAL_SUM" ]; then
    bad "缺少 $LOCAL_SUM —— 无法回填（先跑采集阶段）"
    exit 9
  fi
  # ★ 安全闸：中间态/未知状态的数据禁止写进正式 docx
  #   （避免把非最终数值固化进论文；QA 实测 fail-open 会真的写坏正式文件）
  #   ★ 默认值是 **unknown**（不是 final）—— 状态缺失时必须保守拒绝。
  DATA_STATUS="unknown"
  [ -f "$STATE_DIR/.data_status" ] && DATA_STATUS=$(cat "$STATE_DIR/.data_status")
  IS_REAL_DOCX=0
  case "$(cd "$(dirname "$DOCX_PATH")" && pwd)/$(basename "$DOCX_PATH")" in
    */local/实验方案_详细版.docx) IS_REAL_DOCX=1 ;;
  esac
  if [ "$DATA_STATUS" != "final" ]; then
    if [ "$IS_REAL_DOCX" = "1" ]; then
      bad "当前数据状态 = **$DATA_STATUS**（非 final）→ **禁止**写入正式 docx"
      echo "     · unknown = 状态标记缺失（从未在本脚本内采集过）"
      echo "     · interim = 采集自实验运行中的中间态"
      echo "     请在 RQ1.2 实验停止后重跑：bash local/rq1_2_finalize.sh"
      echo "     （不带 --collect-only）"
      exit 12
    fi
    info "当前数据状态 = $DATA_STATUS（非 final）—— 仅写入**副本**，不碰正式文件"
  fi
  # 回填脚本（内含运行时三重定位 + 回读校验）
  FILL_OUT=$("$PY" "$ROOT/local/rq1_2_fill_docx.py" \
              --docx "$DOCX_PATH" --summary "$LOCAL_SUM" \
              --table-index "$TABLE_INDEX" \
              --header-sig "$TABLE_HEADER_SIG" 2>&1)
  FILL_RC=$?
  echo "$FILL_OUT" | sed 's/^/    /'
  if [ "$FILL_RC" != "0" ]; then
    bad "回填失败（退出码 $FILL_RC）—— 阶段 2 未写标记，可重入重跑"
    exit 10
  fi
  touch "$STATE_DIR/.stage_fill"
  ok "阶段 2 完成（已写 .stage_fill）"
fi

# ════════════════════════════════════════════════════════════════════════════
# 阶段 3：生成实验记录 md
# ════════════════════════════════════════════════════════════════════════════
step "阶段 3：生成实验记录 $RECORD_MD"

if [ "$COLLECT_ONLY" = "1" ]; then
  info "--collect-only → 跳过实验记录"
elif [ -f "$STATE_DIR/.stage_record" ] && [ "$FORCE" != "1" ]; then
  ok "阶段 3 已完成（存在 .stage_record）→ 跳过（--force 可强制重跑）"
else
  DATA_STATUS="unknown"
  [ -f "$STATE_DIR/.data_status" ] && DATA_STATUS=$(cat "$STATE_DIR/.data_status")
  REC_ARGS=(--data-dir "$DATA_DIR" --out "$RECORD_MD")
  [ "$DATA_STATUS" != "final" ] && REC_ARGS+=(--interim)
  # 10-24 20:00 中间态快照（用于 §7 差异对比；不存在则自动跳过）
  [ -d "$INTERIM_DIR" ] && REC_ARGS+=(--interim-dir "$INTERIM_DIR")
  # 污染证据链复核结果（E1–E6 + V8；不存在则自动跳过）
  [ -f "$EVIDENCE_JSON" ] && REC_ARGS+=(--evidence-json "$EVIDENCE_JSON")
  REC_OUT=$("$PY" "$ROOT/local/rq1_2_make_record.py" "${REC_ARGS[@]}" 2>&1)
  REC_RC=$?
  echo "$REC_OUT" | tail -20 | sed 's/^/    /'
  if [ "$REC_RC" != "0" ]; then
    bad "实验记录生成失败（退出码 $REC_RC）"
    exit 11
  fi
  touch "$STATE_DIR/.stage_record"
  ok "阶段 3 完成（已写 .stage_record）"
fi

step "收尾完成"
ok "数据目录: $DATA_DIR"
ok "实验记录: $RECORD_MD"
[ -n "$DOCX_PATH" ] && ok "docx: $DOCX_PATH"
exit 0
