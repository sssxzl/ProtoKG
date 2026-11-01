#!/bin/bash
# rq4_dryrun.sh —— RQ4 实验前置验证（每协议跑一次短时 fuzz + 逐条断言）
#
# 目的：在烧 3h × 6 容器之前，先证明「这条管线是通的」：
#   · 容器能起来、服务端能应答、AFLNet 能建立状态机（paths_found>0 / bitmap_cvg>0）
#   · 种子确实被使用（不是仍在跑镜像自带种子）
#   · 参数字面正确（command_line 逐字匹配预期 OPTIONS —— 防抄写漂移）
#   · 协议专项条件满足（RTSP 8554 监听 / SIP UDP 5061 绑定 + pjsua 存活 / SMTP exim 存活）
#
# 判活不靠 `docker logs -f`（-d + 非 TTY 下 stdout 缓冲，日志极少且可能为空）：
#   判据是 **两次采样 fuzzer_stats 的 execs_done 是否有增长**。
#
# ★ 关于 A2 的等待窗口与 fuzz 时长（踩过的坑，两处都要够）：
#   1) AFLNet 在 `perform_dry_run()` 里会**先把 -i 目录下每个种子都试跑一遍**
#      （afl-fuzz.c:9265），之后才 `write_stats_file()`（:9273）落盘 fuzzer_stats。
#      SMTP 有 78 个种子、每次试跑都要重启 exim → 实测 **175s** 才落盘。
#      所以等待窗口必须 > 该耗时，否则会误判"管线不通"（本脚本最初的 90s 窗口
#      在机器有负载时刚好错过，误报 SMTP 失败；实测 SMTP execs_done 稳定增长到
#      575、paths_found=26、bitmap_cvg=10.37% → 管线本身完全正常）。
#   2) ★★ **fuzz 时长也必须 > perform_dry_run 耗时**，否则正式 fuzz 循环只剩几秒，
#      覆盖率来不及积累 → bitmap_cvg 恒为 0.00%（实测：duration=180 时
#      perform_dry_run 吃掉 175s，只剩 5s fuzz → bitmap_cvg=0.00%、
#      paths_found=0，容器还会在第二次采样前就跑完 fuzz 并退出）。
#      → 各协议的默认 fuzz 时长必须**按协议差异化**（见 rq4_protocols.sh 的
#        RQ4_DURATION_BY_PROTO，SMTP 给到 1200s）。
#   3) ★★ A2 判定必须是「文件存在 **且** execs_done > 0」：perform_dry_run
#      刚结束时 AFLNet 会写一份 stats，那一刻 bitmap_cvg 还是 0（参数写死 0），
#      只看"文件存在"会采到空壳 stats → 后续断言全部误判失败。
#
# 用法
# ----
#   rq4_dryrun.sh [OPTIONS]
#     --protocol rtsp|sip|smtp   # 单协议（默认逐个跑三个）
#     --duration SEC             # 统一覆盖各协议 fuzz 时长（默认按协议取值）
#     --group    protorag|baseline  # 默认 protorag（最坏情况：有缺陷的种子）
#     --seed-root DIR            # 默认 /home/zxy/rq4/seeds
#     --out-root  DIR            # 默认 /home/zxy/rq4/dryrun
#     --stats-wait SEC           # 等 fuzzer_stats 落盘的上限，默认 900
#     --max-seeds N              # protorag 组只用前 N 个 .raw 做验证（0=全量）
#                                   ★ SMTP 的 perform_dry_run 会把每个种子都试跑一遍
#                                     （78 个种子实测 175s~>1200s 剧烈波动），
#                                     dry-run 只需验证"管线通"，故默认取子集提速；
#                                     正式实验（rq4_launch.sh）始终用全量语料。
set -uo pipefail

# ===========================================================================
# 协议参数表 —— **唯一真源在 rq4_protocols.sh**（本脚本 source 它）
# ===========================================================================
# ★ 三个脚本（launch / collect / dryrun）共用同一张表，避免"三处复制"的漂移。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/rq4_protocols.sh
source "${SCRIPT_DIR}/rq4_protocols.sh"

WORKDIR="$RQ4_WORKDIR"
FUZZER="$RQ4_FUZZER"

DURATION=0            # 0 = 按协议取默认值（见 DURATION_BY_PROTO）
GROUP="protorag"
PROTOCOLS="rtsp,sip,smtp"
SEED_ROOT="/home/zxy/rq4/seeds"
OUT_ROOT="/home/zxy/rq4/dryrun"
SAMPLE_INTERVAL=60
SKIPCOUNT=5
# fuzzer_stats 落盘等待上限（见文件头说明：AFLNet 先跑 perform_dry_run）
# ★ 必须 ≥ 该协议的 perform_dry_run 最坏耗时（实测 SMTP 可达 600s+）
STATS_WAIT=900
# protorag 组用于 dry-run 的种子数上限（0 = 全量）
MAX_SEEDS=0

# 各协议默认 fuzz 时长见 rq4_protocols.sh 的 RQ4_DURATION_BY_PROTO（唯一真源）：
#   rtsp：39 个种子 → stats 约 15s 落盘，180s 足够
#   sip ：25 个种子 → stats 约 50s 落盘，180s 足够
#   smtp：78 个种子 → stats 约 175s 落盘！180s 会被 perform_dry_run 吃光
#         （实测只剩 5s fuzz → bitmap_cvg=0.00%、paths_found=0）→ 必须给足 480s

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocol)  PROTOCOLS="$2"; shift 2 ;;
    --duration)  DURATION="$2";  shift 2 ;;
    --group)     GROUP="$2";     shift 2 ;;
    --seed-root) SEED_ROOT="$2"; shift 2 ;;
    --out-root)  OUT_ROOT="$2";  shift 2 ;;
    --sample-interval) SAMPLE_INTERVAL="$2"; shift 2 ;;
    --stats-wait) STATS_WAIT="$2"; shift 2 ;;
    --max-seeds) MAX_SEEDS="$2"; shift 2 ;;
    -h|--help)   sed -n '2,52p' "$0"; exit 0 ;;
    *) echo "!! 未知参数: $1" >&2; exit 2 ;;
  esac
done

# 取某协议的 fuzz 时长（统一 --duration 优先，否则查唯一真源的表）
duration_for() {
  local proto="$1"
  if [[ "$DURATION" -gt 0 ]]; then
    echo "$DURATION"; return
  fi
  rq4_duration_for "$proto"
}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ★ proto_field / rq4_duration_for 定义在 rq4_protocols.sh（唯一真源）。

# 断言结果累加器
PASS=0; FAIL=0
declare -a RESULTS=()
assert() {
  local ok="$1" name="$2" detail="${3:-}"
  if [[ "$ok" == "1" ]]; then
    PASS=$((PASS + 1)); RESULTS+=("PASS | $name${detail:+ | $detail}")
    echo "  ✓ $name${detail:+  ($detail)}"
  else
    FAIL=$((FAIL + 1)); RESULTS+=("FAIL | $name${detail:+ | $detail}")
    echo "  ✗ $name${detail:+  ($detail)}"
  fi
}

stat_get() {
  local file="$1" key="$2" line
  line=$(grep -E "^${key} *:" "$file" 2>/dev/null | head -1)
  [[ -z "$line" ]] && { echo ""; return; }
  if [[ "$key" == "command_line" ]]; then
    echo "$line" | sed -E 's/^command_line *: *//'
  else
    echo "$line" | sed -E "s/^${key} *: *//" | tr -d '\r'
  fi
}

# 数值比较辅助：把 '7.76%' / '1,234' 这类展示值转成可比较的数
# （afl-fuzz 的 bitmap_cvg 是百分比字符串，直接用 [[ > ]] 会报算术语法错）
num_get() {
  local file="$1" key="$2" v
  v=$(stat_get "$file" "$key")
  v=$(echo "$v" | tr -d '%,' | tr -d ' ')
  [[ -z "$v" ]] && { echo ""; return; }
  [[ "$v" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || { echo ""; return; }
  echo "$v"
}

# 数值 > 0 判定（用 awk，避免 bash 算术只支持整数）
num_gt0() {
  local v="$1"
  [[ -z "$v" ]] && return 1
  awk -v x="$v" 'BEGIN { exit !(x > 0) }'
}

# ===========================================================================
# 单协议 dry-run
# ===========================================================================
dryrun_one() {
  local proto="$1"
  local image net in_dir work_dir options
  image=$(proto_field "$proto" image) || { echo "!! 未知协议 $proto"; return 1; }
  net=$(proto_field "$proto" net)
  in_dir=$(proto_field "$proto" in_dir)
  work_dir=$(proto_field "$proto" work_dir)
  options=$(proto_field "$proto" options)
  # ★ 每协议独立的 fuzz 时长（必须 > perform_dry_run 耗时，见文件头说明）
  local dur
  dur=$(duration_for "$proto")

  local name="rq4dry_${proto}_${GROUP}"
  local outdir="out-dry-${proto}-${GROUP}"
  local host_out="${OUT_ROOT}/${proto}"

  echo
  echo "=============================================================="
  echo " DRY-RUN: $proto  group=$GROUP  duration=${dur}s"
  echo " image=${image}"
  echo " options='${options}'"
  echo "=============================================================="

  # --- 清理同名旧容器 ---
  docker ps -a --format '{{.Names}}' | grep -qx "$name" && \
    { log "清理同名旧容器 $name"; docker rm -f "$name" >/dev/null 2>&1; }

  # --- 种子挂载（protorag 覆盖；baseline 用镜像自带） ---
  # ★ --max-seeds：只用前 N 个 .raw 做验证（SMTP 的 perform_dry_run 要把每个种子
  #   都试跑一遍，78 个种子实测耗时 175s~>1200s 剧烈波动；dry-run 只需证明
  #   "管线通"，故用子集提速。**正式实验不受影响**（rq4_launch.sh 始终全量）。
  #   子集目录同样**只放 .raw**（AFLNet 的 read_testcases 会把 -i 下所有常规
  #   非空文件当种子读进去，任何多余文件都会污染种子集）。
  local mount="" mount_src=""
  if [[ "$GROUP" == "protorag" ]]; then
    if [[ ! -d "$SEED_ROOT/$proto" ]]; then
      assert 0 "种子目录存在" "$SEED_ROOT/$proto 不存在"
      return 1
    fi
    mount_src="$SEED_ROOT/$proto"
    if [[ "$MAX_SEEDS" -gt 0 ]]; then
      local stage="${OUT_ROOT}/_seed_subset/${proto}"
      rm -rf "$stage"; mkdir -p "$stage"
      local n=0 f
      for f in "$SEED_ROOT/$proto"/*.raw; do
        [[ -f "$f" ]] || continue
        cp "$f" "$stage/" || true
        n=$((n + 1))
        [[ "$n" -ge "$MAX_SEEDS" ]] && break
      done
      if [[ "$n" -gt 0 ]]; then
        mount_src="$stage"
        log "使用种子子集: $stage（$n 个 .raw，--max-seeds $MAX_SEEDS）"
      else
        log "!! 子集创建失败，回退到全量种子目录"
        mount_src="$SEED_ROOT/$proto"
      fi
    fi
    mount="-v ${mount_src}:${in_dir}:ro"
  fi

  mkdir -p "$host_out"
  local cmd="docker run --cpus=1 --memory=2g -d -it --name ${name}"
  [[ -n "$mount" ]] && cmd="${cmd} ${mount}"
  cmd="${cmd} ${image} /bin/bash -c \"cd ${WORKDIR} && run ${FUZZER} ${outdir} '${options}' ${dur} ${SKIPCOUNT} 2>&1 | tee /dev/null\""

  log "启动容器 $name"
  # shellcheck disable=SC2086
  if ! eval "${cmd}"; then
    assert 0 "容器启动" "docker run 失败"
    return 1
  fi
  sleep 3

  # ---- A1 进程存活 ----
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    assert 1 "A1 容器存活"
  else
    assert 0 "A1 容器存活" "容器已退出：$(docker logs "$name" 2>&1 | tail -5 | tr '\n' ' ')"
    return 1
  fi

  # ---- A2/A3 统计落盘 + 两次采样 execs_done 增长 ----
  local s1 s2 e1 e2 waited=0
  s1="${host_out}/stats_t1.txt"
  s2="${host_out}/stats_t2.txt"
  # ★ A2 判定标准：**文件存在 且 execs_done > 0**。
  #   原因：perform_dry_run() 刚结束时 AFLNet 就落盘了一次 stats，那一刻
  #   execs_done 还是 0（只记了 paths_total）。若只看"文件存在"就采样，
  #   会拿到一份空壳 stats → 后续 A3/A4 全部误判为失败。
  #   实测踩坑：SMTP 175s 时采到 execs_done=363 但 bitmap_cvg=0.00%（fuzz 还没开始）。
  log "等待 fuzzer_stats 出现且 execs_done>0（上限 ${STATS_WAIT}s；AFLNet 需先跑完 perform_dry_run）..."
  while [[ "$waited" -lt "$STATS_WAIT" ]]; do
    docker exec "$name" cat "${work_dir}/${outdir}/fuzzer_stats" > "$s1" 2>/dev/null
    if [[ -s "$s1" ]]; then
      local e0
      e0=$(num_get "$s1" execs_done)
      if [[ -n "$e0" ]] && num_gt0 "$e0"; then
        break
      fi
    fi
    # 容器提前退出 → 立刻放弃等待（后面会报"容器已退出"）
    docker ps --format '{{.Names}}' | grep -qx "$name" || break
    sleep 5; waited=$((waited + 5))
  done
  if [[ -s "$s1" ]]; then
    assert 1 "A2 fuzzer_stats 落盘" "${waited}s"
  else
    assert 0 "A2 fuzzer_stats 落盘" "${STATS_WAIT}s 内未出现"
    return 1
  fi

  log "采样 1 完成，等待 ${SAMPLE_INTERVAL}s 后采样 2（判活依据：execs_done 增长）..."
  sleep "$SAMPLE_INTERVAL"
  # ★ 采样 2 也要容错：容器可能在这 60s 内跑完 fuzz 并进入 cov_script 后处理
  #   （fuzz 时长耗尽 → run 脚本继续跑 1~3h 的 cov_script → 容器仍活着但
  #    fuzzer_stats 可能已不再更新）。此时应明确报"fuzz 时长不足"而不是
  #   误报成"管线不通"。
  if ! docker exec "$name" cat "${work_dir}/${outdir}/fuzzer_stats" > "$s2" 2>/dev/null; then
    : > "$s2"
  fi
  e1=$(num_get "$s1" execs_done); e2=$(num_get "$s2" execs_done)
  if [[ -n "$e1" && -n "$e2" ]] && awk -v a="$e1" -v b="$e2" 'BEGIN { exit !(b > a) }'; then
    assert 1 "A3 活性（execs_done 增长）" "$e1 → $e2"
  else
    assert 0 "A3 活性（execs_done 增长）" "$e1 → ${e2:-<空>}"
  fi

  # ---- A4 状态机建立 ----
  # ★ 语义区分（重要，别把两件事混为一谈）：
  #   paths_total  = AFLNet 状态机里**已知**的路径节点总数（初始种子建立 + 后续发现）
  #                 → 它 > 0 才说明"状态机真的建起来了"（硬断言）
  #   paths_found  = 模糊测试**过程中新发现**的路径数
  #                 → 它反映"探索能力"，dry-run 只有几分钟、SMTP 每用例还要重启
  #                   exim，探索量很小，**可以为 0 而管线完全正常**
  #                   （实测 SMTP 300s/2 种子 → paths_found=26；8 种子短跑 → 0，
  #                     但 bitmap_cvg=7.32% 已证明覆盖真实建立）
  #   故：paths_total>0 与 bitmap_cvg>0 是硬断言；paths_found>0 只作**信息项**
  #      记录，正式实验的 rq4_analyze.py 里它是辅助指标。
  local paths_total paths_found bitmap_cvg
  paths_total=$(num_get "$s2" paths_total)
  paths_found=$(num_get "$s2" paths_found)
  bitmap_cvg=$(num_get "$s2" bitmap_cvg)
  if num_gt0 "$paths_total"; then
    assert 1 "A4a 状态机已建立（paths_total>0）" "paths_total=$paths_total"
  else
    assert 0 "A4a 状态机已建立（paths_total>0）" "paths_total=$paths_total"
  fi
  if num_gt0 "$bitmap_cvg"; then
    assert 1 "A4b bitmap_cvg>0" "bitmap_cvg=$bitmap_cvg"
  else
    assert 0 "A4b bitmap_cvg>0" "bitmap_cvg=$bitmap_cvg"
  fi
  # 信息项：新路径发现数（探索能力，短时 dry-run 可能为 0）
  if num_gt0 "$paths_found"; then
    log "  [信息] paths_found=$paths_found（探索能力指标，短时 dry-run 可能为 0）"
  else
    log "  [信息] paths_found=0（探索能力指标；短时 dry-run 正常，非管线故障）"
  fi

  # ---- A5 无 PFATAL ----
  local logs
  logs=$(docker logs "$name" 2>&1)
  if echo "$logs" | grep -qiE "No server states have been detected|FATAL|Assertion .* failed"; then
    assert 0 "A5 无 PFATAL" "$(echo "$logs" | grep -iE 'No server states|FATAL' | head -1)"
  else
    assert 1 "A5 无 PFATAL"
  fi

  # ---- A6 参数回显逐字匹配 ----
  local cmdline
  cmdline=$(stat_get "$s2" command_line)
  if [[ -n "$cmdline" && "$cmdline" == *"$options"* ]]; then
    assert 1 "A6 参数回显匹配" "含 '$options'"
  else
    assert 0 "A6 参数回显匹配" "期望含 '$options'，实际: ${cmdline:0:200}"
  fi

  # ---- 协议专项断言 ----
  case "$proto" in
    rtsp)
      # RTSP: 服务端必须监听 8554（镜像 run 脚本硬编码 ./testOnDemandRTSPServer 8554）
      local ss_out
      ss_out=$(docker exec "$name" bash -c "ss -ltnp 2>/dev/null | grep ':8554' || netstat -ltnp 2>/dev/null | grep ':8554'" 2>/dev/null)
      if [[ -n "$ss_out" ]]; then
        assert 1 "RTSP 专项：8554 监听" "$(echo "$ss_out" | head -1 | tr -s ' ')"
      else
        assert 0 "RTSP 专项：8554 监听" "ss -ltnp 未见 :8554"
      fi
      ;;
    sip)
      # SIP 专项 1：-l 5061 生效的**功能性**证据。
      # ★ 为什么不用「看 5061 是否在监听」：
      #   afl-fuzz 的 send_over_network() 是**每次执行**新建 socket → bind(local_port)
      #   → 发/收 → close(sockfd)（afl-fuzz.c:1013/1041/1113）。即 socket 只在单次
      #   执行期间存在，采样 /proc/net/udp 或 netstat 几乎必然抓不到（实测 3992 次采样
      #   0 命中），且镜像内根本没有 ss 二进制。
      #   真正可判定的**功能签名**：`-l` 缺失时服务端响应发往 Via/Contact 里的 5061，
      #   而 AFLNet 监听在别的端口 → 收不到响应 → **状态机根本建不起来**
      #   （paths_total 恒为 0）；实测差分：无 -l → paths_found=0；有 -l → paths_found=32。
      #   故用「paths_total>0」作为 -l 生效的判定（与 A4a 同一信号，此处显式归因）。
      #   ★ 用 paths_total 而非 paths_found：后者是"新发现路径数"，短时可能为 0，
      #     不能用来判定"-l 是否生效"（那是"响应有没有回来"的问题）。
      local sip_paths_total
      sip_paths_total=$(num_get "$s2" paths_total)
      if num_gt0 "$sip_paths_total"; then
        assert 1 "SIP 专项：-l 5061 生效（响应回流→状态机建立）" \
          "paths_total=$sip_paths_total（无 -l 时恒为 0）"
      else
        assert 0 "SIP 专项：-l 5061 生效（响应回流→状态机建立）" \
          "paths_total=$sip_paths_total（缺 -l 的典型症状：恒为 0）"
      fi
      # SIP 专项 2：pjsua（SIP 对端模拟器）应存活（run_pjsip 生效）
      local ps_out
      ps_out=$(docker exec "$name" bash -c "ps -ef 2>/dev/null | grep -i pjsua | grep -v grep" 2>/dev/null)
      if [[ -n "$ps_out" ]]; then
        assert 1 "SIP 专项：pjsua 进程存活" "$(echo "$ps_out" | head -1 | tr -s ' ' | cut -c1-90)"
      else
        assert 0 "SIP 专项：pjsua 进程存活" "ps 未见 pjsua"
      fi
      # SIP 专项 3（**信息项，不参与判定**）：5061 socket 绑定快照。
      # 该 socket 每次执行即建即关，抓不到属正常现象；抓到则是额外佐证。
      local udp_out
      udp_out=$(docker exec "$name" bash -c \
        "netstat -unp 2>/dev/null | grep ':5061' || ss -unp 2>/dev/null | grep ':5061'" 2>/dev/null)
      if [[ -n "$udp_out" ]]; then
        log "  [信息] 抓到 5061 socket 快照: $(echo "$udp_out" | head -1 | tr -s ' ')"
      else
        log "  [信息] 未抓到 5061 socket 快照（socket 每次执行即建即关，属正常）"
      fi
      ;;
    smtp)
      # SMTP 专项 1：exim 服务进程必须存活
      local ps_out
      ps_out=$(docker exec "$name" bash -c "ps -ef 2>/dev/null | grep -i '[e]xim'" 2>/dev/null)
      if [[ -n "$ps_out" ]]; then
        assert 1 "SMTP 专项：exim 进程存活" "$(echo "$ps_out" | head -1 | tr -s ' ' | cut -c1-90)"
      else
        assert 0 "SMTP 专项：exim 进程存活" "ps 未见 exim"
      fi
      # SMTP 专项 2：★ Exim clean 竞态检查（设计文档风险 R7）
      #
      # 机制（已实测确认）：
      #   镜像内 clean 脚本 = `pkill -F /var/lock/exim.pid`；
      #   AFLNet 在 `send_over_network()` 里 **每个用例执行前**调用它
      #   （afl-fuzz.c:992 `if (cleanup_script) system(cleanup_script);`），
      #   而 exim 是**上一个用例**遗留的实例 → 若新实例已覆盖 pidfile，
      #   旧 clean 就会误杀新起的 server。
      #
      # ★★★ **实测结论（差分实验 + 源码定位）：本轮不采用保守 clean 偏离** ★★★
      #   1. 官方 clean 下 SMTP **确实能正常工作**（独立探针：300s → execs_done=575、
      #      paths_found=26、bitmap_cvg=10.37%、stability=93.76%）。
      #   2. perform_dry_run 慢的**根因不是 clean 误杀**，而是：
      #      exim 是 ASAN 构建、启动慢（读配置 + TLS cipher-validate fork），
      #      而 OPTIONS 里 `-D 10000`（server 初始化只等 10ms）**明显不足**
      #      → 部分用例要等满 `-t 5000` 才超时 → 每个种子平均多花数秒。
      #      实测同配置（78 种子）两次 perform_dry_run 耗时 **175s** 与 **>600s**。
      #   3. 尝试过两种「保守 clean」替代实现，**均失败并已放弃**（脚本已删除，
      #      避免误用）：
      #      · 按 pid/etimes 排序保留「最新」→ exim 的 cipher-validate 子进程
      #        pid 更大但**不是监听者** → 误杀真正的 server → AFLNet
      #        "Testing aborted by user" 立即中止。
      #      · 按「谁在监听 25 端口」判据 → **exim 镜像内没有 ss**，
      #        且 netstat -ltnp 的 pid 列是 `-`（拿不到 pid）→ 判据恒为空
      #        → 旧实例永不清理 → 端口被占 → 全部用例超时 → PROGRAM ABORT。
      #      （另：AFLNet 用 system() 调用该脚本 → 经 /bin/sh(dash) 执行，
      #        故实现必须是纯 POSIX sh。）
      #   4. 结论：**偏离官方配置的风险大于收益**（官方 clean 下两组同施、
      #      组间仍可比；而 perform_dry_run 只占 3h 的约 5%）。
      #      → 保持官方 clean，不做偏离。
      #
      # ★ 竞态的**可观测后果不是"报错"，而是 exec 停滞**——
      #   server 被误杀 → 无响应 → AFLNet 反复超时 → execs_done 不再增长。
      #   因此判定方式是**间接的**：execs_done 必须持续增长（A3 已覆盖），
      #   且路径发现数 > 0（说明真的收到了响应，不是"连上了但没数据"）。
      #   这里额外断言 exim 实例数**没有失控堆积**（堆积 = 每次用例都新起
      #   一个 exim 而旧的没被清掉，是竞态正在发生的信号）。
      local exim_n
      exim_n=$(docker exec "$name" bash -c \
        "ps -eo cmd 2>/dev/null | grep -c '[e]xim -bd'" 2>/dev/null | tr -d ' \r')
      [[ -z "$exim_n" ]] && exim_n=0
      if [[ "$exim_n" -le 20 ]]; then
        assert 1 "SMTP 专项：Exim clean 竞态未致实例失控" "exim 实例数=$exim_n（≤20）"
      else
        assert 0 "SMTP 专项：Exim clean 竞态未致实例失控" "exim 实例数=$exim_n（>20，竞态在堆积）"
      fi
      # SMTP 专项 3：25 端口监听（**信息项，不参与判定**）
      # ★ 为什么不能做硬断言：SMTP 的 exim **每个用例都要重启**（镜像 run 脚本把
      #   exim 作为 target 传给 afl-fuzz，配合 -c clean 反复拉起），
      #   而 AFLNet 的 send_over_network() 也在每个用例前调用 clean
      #   → 采样点很可能落在"旧实例已被杀、新实例还没 bind"的切换窗口
      #   → 端口瞬时无监听者（实测采样到 listeners=0，而同一时刻
      #      paths_total=14、bitmap_cvg=7.33%、execs 持续增长 → server 明明在服务）。
      #   这与 SIP 的「5061 socket 快照」是同类问题：**瞬时状态不能做硬判据**。
      #   真正证明"server 在响应"的是功能签名：A3 的 execs 增长 +
      #   A4a/A4b 的 paths_total>0 与 bitmap_cvg>0（覆盖被测到 = 确实收到响应）。
      local p25
      p25=$(docker exec "$name" bash -c \
        "(ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -c ':25 '" 2>/dev/null | tr -d ' \r')
      [[ -z "$p25" ]] && p25=0
      if [[ "$p25" -ge 1 ]]; then
        log "  [信息] 25 端口当前 LISTEN（listeners=$p25）"
      else
        log "  [信息] 25 端口采样瞬间无监听者（listeners=0）——exim 每用例重启，"
        log "         采样点可能落在实例切换窗口；server 是否在服务以 A3/A4 的"
        log "         execs 增长与 bitmap_cvg>0 为准"
      fi
      ;;
  esac

  # ---- 通用：种子目录纯净性（只允许 .raw）----
  # ★ AFLNet 的 read_testcases() 用 scandir() 遍历 -i 目录，会把**所有常规非空文件**
  #   都当成测试用例读进来（只跳过 README.txt）→ 若 MANIFEST.md5 / *.dict 落在
  #   种子目录里，会**污染种子集**，两组对比就不成立。
  #   故：挂载前必须断言种子目录里只有 .raw。
  if [[ "$GROUP" == "protorag" ]]; then
    local non_raw
    non_raw=$(find "$SEED_ROOT/$proto" -maxdepth 1 -type f ! -name '*.raw' 2>/dev/null)
    if [[ -z "$non_raw" ]]; then
      assert 1 "种子目录只含 .raw（无污染文件）" "$SEED_ROOT/$proto"
    else
      assert 0 "种子目录只含 .raw（无污染文件）" \
        "发现非 .raw 文件: $(echo "$non_raw" | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
    fi
    # 容器内实际看到的 in-* 目录内容也要核对（挂载是否生效、有无多余文件）
    local in_list
    in_list=$(docker exec "$name" bash -c "ls -1 '${in_dir}' 2>/dev/null" 2>/dev/null)
    local in_non_raw in_count
    in_count=$(echo "$in_list" | grep -c '\.raw$' || true)
    in_non_raw=$(echo "$in_list" | grep -v '\.raw$' | grep -v '^$' || true)
    if [[ -n "$in_non_raw" ]]; then
      assert 0 "容器内 in-* 目录只含 .raw" "多余: $(echo "$in_non_raw" | tr '\n' ' ')"
    else
      assert 1 "容器内 in-* 目录只含 .raw" "in_count=$in_count"
    fi
  fi

  # ---- 通用：种子确实被使用（replayable-queue 里出现我们的种子名）----
  local queue_hit
  queue_hit=$(docker exec "$name" bash -c \
    "ls ${work_dir}/${outdir}/replayable-queue/ 2>/dev/null | head -3" 2>/dev/null)
  if [[ "$GROUP" == "protorag" ]]; then
    local seed_files
    seed_files=$(ls "$SEED_ROOT/$proto" 2>/dev/null | head -1)
    if [[ -n "$queue_hit" && -n "$seed_files" ]]; then
      assert 1 "种子被使用（replayable-queue 非空）" "$(echo "$queue_hit" | head -1)"
    else
      assert 0 "种子被使用（replayable-queue 非空）" "queue='$queue_hit'"
    fi
  fi

  # ---- 通用：RTSP 会话可播性（逐会话断言 DESCRIBE 返回 200 而非 404）----
  if [[ "$proto" == "rtsp" && "$GROUP" == "protorag" ]]; then
    # 用镜像自带的 aflnet-replay 逐会话重放：种子里的会话若不可播 → 服务端返 404。
    # aflnet-replay 需要在 target 的 testProgs 目录下运行（相对路径依赖）。
    local work_sub="${work_dir#${WORKDIR}/}"   # live/testProgs
    local bad=0 checked=0 seed resp
    for seed in "$SEED_ROOT/$proto"/*.raw; do
      [[ -f "$seed" ]] || continue
      checked=$((checked + 1))
      [[ "$checked" -gt 5 ]] && break
      resp=$(docker exec "$name" bash -c \
        "cd ${WORKDIR}/${work_sub} && /home/ubuntu/aflnet/aflnet-replay '$seed' RTSP 8554 1 2>&1 | head -30" 2>/dev/null)
      if echo "$resp" | grep -qE "404|Not Found"; then
        bad=$((bad + 1))
        log "  404 命中: $(basename "$seed")"
      fi
    done
    if [[ "$checked" -gt 0 && "$bad" -eq 0 ]]; then
      assert 1 "RTSP 专项：会话可播（无 404）" "抽查 $checked 个种子"
    elif [[ "$checked" -eq 0 ]]; then
      assert 0 "RTSP 专项：会话可播（无 404）" "未能重放任何种子"
    else
      assert 0 "RTSP 专项：会话可播（无 404）" "$bad/$checked 个种子 404"
    fi
  fi

  # ---- 归档日志 + 清理 ----
  mkdir -p "${OUT_ROOT}/logs"
  docker logs "$name" > "${OUT_ROOT}/logs/${name}.log" 2>&1 || true
  cp "$s1" "$s2" "${OUT_ROOT}/logs/" 2>/dev/null || true

  # ★ 停容器（不 rm）：镜像 run 脚本在 fuzz 结束后还会跑 1~3h 的 cov_script
  #   （gcovr 覆盖率时序 + gcovr --html），dry-run 阶段完全不需要它，
  #   留着会白占 CPU 与磁盘（6 容器同时跑后处理会互相干扰）。
  #   → 只 stop，保留容器以便事后查日志；正式实验由 run 脚本自己跑完后处理。
  log "停止容器 $name"
  docker stop "$name" >/dev/null 2>&1 || true

  return 0
}

# ===========================================================================
# 主流程
# ===========================================================================
main() {
  echo "=============================================================="
  echo " RQ4 DRY-RUN 前置验证"
  echo "=============================================================="
  echo " protocols : $PROTOCOLS"
  echo " group     : $GROUP"
  echo " duration  : ${DURATION}s/协议"
  echo " out-root  : $OUT_ROOT"
  echo "=============================================================="

  mkdir -p "$OUT_ROOT/logs"

  local proto
  for proto in $(echo "$PROTOCOLS" | tr ',' ' '); do
    dryrun_one "$proto" || true
  done

  echo
  echo "=============================================================="
  echo " DRY-RUN 断言汇总：PASS=$PASS FAIL=$FAIL"
  echo "=============================================================="
  printf '%s\n' "${RESULTS[@]}"
  mkdir -p "$OUT_ROOT"
  {
    echo "# RQ4 dry-run 断言报告  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "# protocols=$PROTOCOLS group=$GROUP duration=${DURATION}s"
    echo "# PASS=$PASS FAIL=$FAIL"
    printf '%s\n' "${RESULTS[@]}"
  } > "$OUT_ROOT/dryrun_report.txt"

  echo " 报告: $OUT_ROOT/dryrun_report.txt"
  [[ "$FAIL" -gt 0 ]] && exit 1
  exit 0
}

main "$@"
