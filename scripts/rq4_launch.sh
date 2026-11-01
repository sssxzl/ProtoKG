#!/bin/bash
# rq4_launch.sh —— RQ4 AFLNet 实验编排启动脚本（3 协议 × 2 组 × N 重复）
#
# 设计要点
# --------
# 1. **协议差异全部收敛到一张参数表**（PROTO_TABLE），六个字段：
#    image | proto | net | in_dir | work_dir | options
#    —— 既往 rq2_launch_target.sh 就是因为参数散落在 case 分支里才漏了 `-l 5061`
#       （kamailio 缺 -l → 服务端响应不回传 → AFLNet PFATAL "No server states"），
#       本脚本用「表驱动 + 唯一真源」杜绝同类漂移。
# 2. **复用镜像内官方 `run` 入口**，不自造 afl-fuzz 命令行（自造会丢掉 -c 清理脚本、
#    -K 优雅终止、cov_script 覆盖率时序）。
# 3. **官方参数逐字照抄** `/home/zxy/profuzzbench/scripts/execution/profuzzbench_exec_all.sh`：
#    TEST_TIMEOUT=5000（固定，非 `1000+` 自动标定）、TIMEOUT=3600、SKIPCOUNT=5。
#    -m none 必须有（否则 50MB rlimit 秒杀 ASAN 目标）。
# 4. **种子投放统一用同名 bind mount 覆盖**镜像内 in-* 目录（三协议同一机制，
#    run 脚本零改动）：
#      protorag 组 → -v <seed-root>/<proto>:<in_dir>:ro
#      baseline 组 → **零挂载**，直接用镜像自带官方种子（= 官方基线逐字节复现）
# 5. **容器启动前 docker rm -f 清同名旧容器**（容器名冲突会导致复用旧容器读到陈旧 stats）。
# 6. **不用 docker cp 采集**（镜像产物属主 root，宿主 zxy 读不到）——采集见 rq4_collect.sh。
#
# 用法
# ----
#   rq4_launch.sh [OPTIONS]
#     --protocols  rtsp,sip,smtp      # 子集，默认全部
#     --groups     protorag,baseline   # 子集，默认全部
#     --reps       N                   # 重复数，默认 1
#     --duration   SEC                 # 每容器 fuzz 时长秒，默认 10800 (3h)
#     --skipcount  N                   # cov_script 采样步长，默认 5（官方）
#     --seed-root  DIR                 # protorag 种子根，默认 /home/zxy/rq4/seeds
#     --out-root   DIR                 # 结果根目录，默认 /home/zxy/rq4/out
#     --memory     2g                  # 每容器内存上限，默认 2g
#     --min-disk   GB                  # 磁盘可用量门槛，默认 8（实测 3h×6 容器峰值约需 5GB）
#     --dry-run                       # 只打印将要执行的 docker run，不启动
#     --yes                          # 跳过交互确认
#
# 容器命名规范： rq4_<proto>_<group>_r<rep>
set -uo pipefail

# ===========================================================================
# 协议参数表 —— **唯一真源在 rq4_protocols.sh**（本脚本 source 它）
# ===========================================================================
# ★ 为什么不把表直接抄在这里：三个脚本各抄一份 = "散落"换成了"三处复制"，
#   改一处忘两处仍会漂移。详见 rq4_protocols.sh 的文件头注释。
# ★ options 逐字取自 VM `/home/zxy/profuzzbench/scripts/execution/profuzzbench_exec_all.sh`
#   （HEAD 8573ec8）：TEST_TIMEOUT=5000（固定，非 `1000+`/`3000+` 自动标定）、
#   TIMEOUT=3600、SKIPCOUNT=5。`-m none` 必须有（否则 50MB rlimit 秒杀 ASAN 目标）。
#   kamailio **无 -R**（官方如此，加了 -R 与既往 RQ1.2 SIP 结果不可比）。
# ===========================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/rq4_protocols.sh
source "${SCRIPT_DIR}/rq4_protocols.sh"

# ===========================================================================
# 参数解析
# ===========================================================================
PROTOCOLS="rtsp,sip,smtp"
GROUP_LIST="protorag,baseline"
REPS=1
DURATION=10800
SKIPCOUNT=5
SEED_ROOT="/home/zxy/rq4/seeds"
OUT_ROOT="/home/zxy/rq4/out"
MEMORY="2g"
# 磁盘门槛：3h×6 容器的实测峰值约 5GB（queue 文件 + cov_html + 每容器 tar.gz）
MIN_DISK_GB=8
DRY_RUN=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --groups)    GROUP_LIST="$2";    shift 2 ;;
    --reps)      REPS="$2";      shift 2 ;;
    --duration)  DURATION="$2";  shift 2 ;;
    --skipcount) SKIPCOUNT="$2"; shift 2 ;;
    --seed-root) SEED_ROOT="$2"; shift 2 ;;
    --out-root)  OUT_ROOT="$2";  shift 2 ;;
    --memory)    MEMORY="$2";    shift 2 ;;
    --min-disk)  MIN_DISK_GB="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=1;      shift ;;
    --yes|-y)    ASSUME_YES=1;   shift ;;
    -h|--help)   sed -n '2,42p' "$0"; exit 0 ;;
    *) echo "!! 未知参数: $1" >&2; exit 2 ;;
  esac
done

# ===========================================================================
# 工具函数
# ===========================================================================
log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die()  { echo "!! $*" >&2; exit 1; }

# 从参数表取某协议的某个字段（**按字段名**，不用下标——下标容易 off-by-one）
# 用法: field=$(proto_field <proto> <field_name>)
# 字段名: image | proto | net | in_dir | work_dir | options
# ★ proto_field 定义在 rq4_protocols.sh（唯一真源），此处不再重复实现。
WORKDIR="$RQ4_WORKDIR"
FUZZER="$RQ4_FUZZER"

# 容器内产物目录（fuzzer_stats 所在）
container_outdir() {
  local proto="$1" group="$2" rep="$3" wd
  wd=$(proto_field "$proto" work_dir) || return 1
  echo "${wd}/out-${proto}-${group}-r${rep}"
}

# 容器内 tar 包路径
container_tar() {
  local proto="$1" group="$2" rep="$3"
  echo "${WORKDIR}/out-${proto}-${group}-r${rep}.tar.gz"
}

# ===========================================================================
# 前置检查
# ===========================================================================
preflight() {
  log "=== 前置检查 ==="

  # 1. 磁盘：可用量门槛（默认 8GB；3h×6 容器的实测峰值约需 5GB）
  #    ★ 解析要点：`df -BG` 输出形如 "8.0G"，直接 `tr -dc '0-9'` 会得到 "80"（错了 10 倍）。
  #      这里先剥掉 "G" 再取整数部分。
  local avail_gb
  mkdir -p "$OUT_ROOT" 2>/dev/null || true
  avail_gb=$(df -BG "$OUT_ROOT" 2>/dev/null | awk 'NR==2 {gsub(/G/,"",$4); printf "%d", $4}')
  if [[ -z "$avail_gb" || "$avail_gb" -eq 0 ]]; then
    avail_gb=$(df -BG / 2>/dev/null | awk 'NR==2 {gsub(/G/,"",$4); printf "%d", $4}')
  fi
  log "磁盘可用: ${avail_gb}GB（要求 ≥${MIN_DISK_GB}GB）"
  if [[ "$avail_gb" -lt "$MIN_DISK_GB" ]]; then
    log "!! 磁盘不足 ${MIN_DISK_GB}GB。先清理（仅限下面两类安全操作）："
    log "   docker ps -aq --filter status=exited | xargs -r docker rm -f"
    log "   docker image prune -f        # 仅 dangling（不删有 tag 的镜像）"
    die "磁盘不足（${avail_gb}GB < ${MIN_DISK_GB}GB），已中止。请先清理后重试。"
  fi

  # 2. 停掉仍在运行的既往 RQ1 SIP 容器（CPU/内存争抢会污染本实验）
  #    ★ 只 stop 不 rm —— 不删容器、不动 /home/zxy/rq1_sip_out 的 P4 实验数据。
  local stale
  stale=$(docker ps --format '{{.Names}}' | grep -E '^rq1sip_.*_chatafl_r[0-9]+$' || true)
  if [[ -n "$stale" ]]; then
    log "停止既往 RQ1 SIP 容器（只 stop，不删容器/数据）: $stale"
    # shellcheck disable=SC2086
    docker stop $stale >/dev/null 2>&1 || true
  else
    log "无运行中的 rq1sip_* 容器"
  fi

  # 3. 种子目录存在性检查（protorag 组才需要）
  #    ★ 纯净性要求：目录里**只允许 .raw**。
  #      AFLNet 的 read_testcases() 用 scandir() 遍历 -i 目录，会把所有常规非空文件
  #      都当测试用例读进来（只跳过 README.txt）→ MANIFEST.md5 / *.dict 落在目录里
  #      会污染种子集，两组对比就不成立。
  local p
  for p in $(echo "$PROTOCOLS" | tr ',' ' '); do
    [[ -d "$SEED_ROOT/$p" ]] || die "种子目录不存在: $SEED_ROOT/$p（先跑 rq4_sync_seeds.ps1）"
    local n
    n=$(find "$SEED_ROOT/$p" -maxdepth 1 -type f -name '*.raw' | wc -l)
    [[ "$n" -gt 0 ]] || die "种子目录为空: $SEED_ROOT/$p"
    local extra
    extra=$(find "$SEED_ROOT/$p" -maxdepth 1 -type f ! -name '*.raw' 2>/dev/null \
            | xargs -r -n1 basename | tr '\n' ' ')
    if [[ -n "$extra" ]]; then
      die "种子目录含非 .raw 文件: ${extra} —— 会污染 AFLNet 种子集（read_testcases 读取 -i 下所有常规非空文件）"
    fi
    log "种子就绪: $SEED_ROOT/$p（$n 个 .raw，目录纯净）"
  done

  # 4. 镜像存在性检查
  local img p
  for p in $(echo "$PROTOCOLS" | tr ',' ' '); do
    img=$(proto_field "$p" image) || die "参数表里没有协议 $p"
    docker image inspect "$img" >/dev/null 2>&1 || die "镜像不存在: $img"
  done
  log "镜像检查通过"
}

# ===========================================================================
# 启动单个容器
# ===========================================================================
launch_one() {
  local proto="$1" group="$2" rep="$3"
  local image net in_dir work_dir options
  image=$(proto_field "$proto" image) || { echo "!! 未知协议 $proto" >&2; return 2; }
  net=$(proto_field "$proto" net)
  in_dir=$(proto_field "$proto" in_dir)
  work_dir=$(proto_field "$proto" work_dir)
  options=$(proto_field "$proto" options)

  local name="rq4_${proto}_${group}_r${rep}"
  local outdir="out-${proto}-${group}-r${rep}"
  local host_out="${OUT_ROOT}/${proto}/${group}/r${rep}"

  # --- 清理同名旧容器（容器名冲突 → 复用旧容器读到陈旧 stats） ---
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    log "清理同名旧容器: $name"
    docker rm -f "$name" >/dev/null 2>&1 || true
  fi

  # --- 种子挂载：protorag 覆盖 in-*；baseline 零挂载（用镜像自带官方种子）---
  # ★ **绝不 bind-mount 输出目录**：
  #   容器内产物属主是 root，bind-mount 到宿主会产出宿主 zxy 读不到的
  #   root 属主文件（既往 rq2_out 的坑）。产物一律留在容器内，
  #   由 rq4_collect.sh 用 `docker exec <ctr> cat <path> > <host_file>` 取回。
  #   → 本脚本的 -v 只有种子挂载一处，输出目录**始终不挂载**。
  local mount=""
  if [[ "$group" == "protorag" ]]; then
    mount="-v ${SEED_ROOT}/${proto}:${in_dir}:ro"
  fi

  # --- 组装 docker run 命令 ---
  #     --cpus=1  : 官方 exec_common.sh 同款，限制单容器 CPU（防止组间争抢影响 exec 速率）
  #     --memory   : 限制单容器内存
  #     -d -it     : 官方同款（-it 保留 TTY 行为 + docker logs 可见 AFL UI）
  local cmd="docker run --cpus=1 --memory=${MEMORY} -d -it --name ${name}"
  [[ -n "$mount" ]] && cmd="${cmd} ${mount}"
  cmd="${cmd} ${image} /bin/bash -c \"cd ${WORKDIR} && run ${FUZZER} ${outdir} '${options}' ${DURATION} ${SKIPCOUNT}\""

  # ★ 防御性断言：命令里**绝不能**出现输出目录的 bind-mount。
  #   （输出目录一旦挂到宿主，容器内 root 属主的产物会让宿主 zxy 读不到 →
  #    既往 rq2_out 就是这么踩坑的。产物只走 docker exec cat 取回。）
  if echo "$cmd" | grep -q -- "-v .*:${OUT_ROOT}"; then
    die "拒绝启动：docker run 命令里出现了输出目录挂载（${OUT_ROOT}）"
  fi

  log "启动 $name"
  log "  image=${image} net=${net} group=${group} rep=${rep}"
  log "  options='${options}' duration=${DURATION}s skipcount=${SKIPCOUNT}"
  log "  挂载: ${mount:-（无 —— baseline 用镜像自带官方种子）}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: ${cmd}"
    echo "DRY-RUN: 容器内产物 ${work_dir}/${outdir}"
    return 0
  fi

  mkdir -p "$host_out"
  # shellcheck disable=SC2086
  if ! eval "${cmd}"; then
    echo "!! 容器启动失败: $name" >&2
    return 1
  fi
  log "  容器已启动（ID: $(docker ps -q --filter "name=^${name}$" | cut -c1-12)）"
  return 0
}

# ===========================================================================
# 主流程
# ===========================================================================
main() {
  echo "=============================================================="
  echo " RQ4 AFLNet 实验编排"
  echo "=============================================================="
  echo " protocols : $PROTOCOLS"
  echo " groups    : $GROUP_LIST"
  echo " reps      : $REPS"
  echo " duration  : ${DURATION}s/容器"
  echo " skipcount : $SKIPCOUNT"
  echo " seed-root : $SEED_ROOT"
  echo " out-root  : $OUT_ROOT"
  echo " memory    : ${MEMORY}"
  [[ "$DRY_RUN" -eq 1 ]] && echo " 模式     : DRY-RUN（不实际启动）"
  echo "=============================================================="

  if [[ "$DRY_RUN" -eq 0 ]]; then
    preflight
  else
    log "DRY-RUN：跳过前置检查（不实际启动容器）"
  fi

  local proto group rep n=0 failed=0
  for proto in $(echo "$PROTOCOLS" | tr ',' ' '); do
    for group in $(echo "$GROUP_LIST" | tr ',' ' '); do
      for ((rep = 1; rep <= REPS; rep++)); do
        launch_one "$proto" "$group" "$rep" || failed=1
        n=$((n + 1))
      done
    done
  done

  echo "=============================================================="
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo " DRY-RUN 结束：共生成 $n 条启动命令（未启动任何容器）"
  else
    echo " 共启动 $n 个容器"
    echo " 容器名规范: rq4_<proto>_<group>_r<rep>"
    echo " 结果目录  : ${OUT_ROOT}/<proto>/<group>/r<rep>/"
    echo " 日志目录  : /home/zxy/rq4/logs/"
    echo " 下一步    : rq4_collect.sh --wait   # 等待并采集"
    if [[ "$failed" -ne 0 ]]; then
      echo "!! 有容器启动失败，请检查上方日志"
      exit 1
    fi
  fi
  echo "=============================================================="
}

main "$@"
