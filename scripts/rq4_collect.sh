#!/bin/bash
# rq4_collect.sh —— RQ4 实验结果采集脚本
#
# 设计要点
# --------
# 1. **★ 绝不用 `docker cp` 采集产物**。
#    镜像内产物属主是 root（rq2-live555 / rq2-exim 的 Config.User=root），
#    `docker cp` 会**保留属主** → 宿主 zxy 读不到（实测：既往 rq2_out/*/r1/fuzzer_stats
#    为 `-rw------- root root`，`cat` 返回空 → 采集到空文件被误判为"无结果"）。
#    统一用 `docker exec <ctr> cat <path> > <host_file>`：宿主侧重定向 → 属主=zxy。
#    （容器已退出时用 `docker cp` 拿到 tar 再在宿主解包——tar 内的属主同样保留，
#    故此处对**已退出**的容器改用 `docker cp` + `tar` 时仍需 `sudo`，
#    故默认策略是：**在容器运行期间完成采集**（见 --wait 语义）。）
#
# 2. **采集 `command_line` 字段做参数自检**——把 afl-fuzz 实际执行的命令行原样落盘，
#    与预期 OPTIONS 逐字比对即可发现参数抄写漂移（如漏 `-l 5061`）。
#
# 3. **fuzzer_stats 关键字段**（afl-fuzz.c 的统计区）：
#    start_time last_update cycles_done execs_done execs_per_sec paths_total
#    paths_found max_depth cur_path stability bitmap_cvg unique_crashes
#    unique_hangs command_line peak_rss_mb
#
# 4. 汇总落盘 `/home/zxy/rq4/rq4_summary.csv`（每容器一行）。
#
# 5. **自证"两组只有种子不同"**：每行额外记录
#      seed_files   —— 该容器实际使用的种子文件数
#      seed_regions —— AFLNet 真实分区器切出的 region 总数（= 状态机消息数）
#      dict_tokens  —— 官方字典的 token 条数（两组必须相同 → 字典不是变量）
#    这三列由 `rq4_seed_profile.py` 计算（唯一真源，与本机自检共用同一实现）。
#
# 6. **次要指标 l_per / b_per**：来自官方 `cov_over_time.csv` 的**最后一行**
#    （l_per = 最后一行代码覆盖率 %，b_per = 分支覆盖率 %）。
#    这是 cov_script 的官方口径，与 AFLNet 自报的 bitmap_cvg（边覆盖 %）**不是同一个量**，
#    两者可能不一致 → 报告时须**同时列出，不做取舍**（见 rq4_analyze.py）。
#
# 用法
# ----
#   rq4_collect.sh [OPTIONS]
#     --protocols rtsp,sip,smtp      # 子集，默认全部
#     --groups    protorag,baseline   # 子集，默认全部
#     --reps      N                   # 默认 1
#     --out-root  DIR                 # 默认 /home/zxy/rq4/out
#     --wait                          # 阻塞等待所有容器退出后再采集
#     --timeout  SEC                  # --wait 的等待上限，默认 21600 (6h)
#     --snapshot-interval SEC          # 运行期间快照 fuzzer_stats 的间隔，默认 60
#     --snapshot-only                  # **只**跑快照循环、不做终态采集（前台阻塞）
#     --offline DIR                     # **离线汇总**：从已有产物目录生成 summary（不碰 docker）
#                                         DIR 结构: <DIR>/<proto>/<group>/r<rep>/{fuzzer_stats,cov_over_time.csv}
#                                         （用于"容器已删但产物已取出"时重算汇总，或用
#                                           dry-run 的真实 stats 验证 rq4_analyze.py）
#     --seed-root DIR                 # protorag 种子根，默认 /home/zxy/rq4/seeds
set -uo pipefail

# ===========================================================================
# 协议参数表 —— **唯一真源在 rq4_protocols.sh**（本脚本 source 它）
# ===========================================================================
# ★ 三个脚本（launch / collect / dryrun）共用同一张表，避免"三处复制"的漂移。
#   字段: image|proto|net|in_dir|work_dir|options
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/rq4_protocols.sh
source "${SCRIPT_DIR}/rq4_protocols.sh"

WORKDIR="$RQ4_WORKDIR"

PROTOCOLS="rtsp,sip,smtp"
GROUP_LIST="protorag,baseline"
REPS=1
OUT_ROOT="/home/zxy/rq4/out"
SUMMARY="/home/zxy/rq4/rq4_summary.csv"
# ★ 产物自证清单（旁挂，不动 summary 的 28 列契约）
#   动机：容器可能被 `docker rm` 删除（磁盘清理 / 其它实验线的宽过滤器），
#   之后无法再 `docker cp` 回查容器内原始文件。此时唯一能自证"数据未被篡改"的
#   证据链是：**官方 tar.gz 里的产物** vs **宿主明文副本**，两者的 md5 必须相同。
#   把各产物的 md5 写进清单，日后核验脚本可直接比对，无需回查容器。
#   ★ 为什么旁挂而不加列：summary 的 28 列表头是**冻结合同**（下游分析脚本按列号取），
#     加列会破坏它。故用独立文件 `${SUMMARY%.csv}.artifacts.md5`。
#
# ⚠ 初始化顺序陷阱（已真实踩过）：**这里不能**写成
#     ARTIFACT_MANIFEST="${ARTIFACT_MANIFEST:-${SUMMARY%.csv}.artifacts.md5}"
#   因为本行的默认值在**参数解析之前**求值 → 此时 SUMMARY 还是默认的
#   /home/zxy/rq4/rq4_summary.csv → 用户传 `--summary /tmp/x.csv` 时，
#   清单仍会写到 rq4_summary.artifacts.md5（**写错地方**，实测踩过）。
#   故改为：这里只置空，由 artifact_manifest_path() **在使用时**惰性求值。
ARTIFACT_MANIFEST=""
LOG_DIR="/home/zxy/rq4/logs"
SEED_ROOT="/home/zxy/rq4/seeds"
WAIT=0
WAIT_TIMEOUT=21600
SNAPSHOT_INTERVAL=60
SNAPSHOT_ONLY=0
OFFLINE_DIR=""

# 种子画像计算器（唯一真源）；与本机 rq4_verify_seeds.py 共用同一份实现
SEED_PROFILE="${SEED_PROFILE:-/home/zxy/rq4/scripts/rq4_seed_profile.py}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --groups)    GROUP_LIST="$2";    shift 2 ;;
    --reps)      REPS="$2";      shift 2 ;;
    --out-root)  OUT_ROOT="$2";  shift 2 ;;
    --summary)   SUMMARY="$2";   shift 2 ;;
    --seed-root) SEED_ROOT="$2"; shift 2 ;;
    --wait)      WAIT=1;         shift ;;
    --snapshot-only) SNAPSHOT_ONLY=1; shift ;;
    --offline)   OFFLINE_DIR="$2"; shift 2 ;;
    --timeout)   WAIT_TIMEOUT="$2"; shift 2 ;;
    --snapshot-interval) SNAPSHOT_INTERVAL="$2"; shift 2 ;;
    -h|--help)   sed -n '2,45p' "$0"; exit 0 ;;
    *) echo "!! 未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "!! $*" >&2; exit 1; }

# ---- 产物自证清单路径（惰性求值）----
#   ★ 必须在**使用时**才从 SUMMARY 派生：SUMMARY 会被 `--summary` 改写，
#     而参数解析发生在变量初始化**之后** → 初始化时求值会写错地方（见上方注释）。
#   显式设置环境变量 ARTIFACT_MANIFEST 可覆盖。
artifact_manifest_path() {
  if [[ -n "$ARTIFACT_MANIFEST" ]]; then
    echo "$ARTIFACT_MANIFEST"
  else
    echo "${SUMMARY%.csv}.artifacts.md5"
  fi
}

# ★ proto_field 定义在 rq4_protocols.sh（唯一真源），此处不再重复实现。

container_outdir() {
  local proto="$1" group="$2" rep="$3" wd
  wd=$(proto_field "$proto" work_dir) || return 1
  echo "${wd}/out-${proto}-${group}-r${rep}"
}

# ===========================================================================
# 官方字典定位（字典是**两组共用**的镜像内官方字典 → dict_tokens 必须相同）
# ---------------------------------------------------------------------------
# 字典策略（裁决）：**两组都用镜像自带官方字典**
#   RTSP: -x ${WORKDIR}/rtsp.dict   （由镜像 run 脚本传入）
#   SMTP: -x ${WORKDIR}/smtp.dict   （由镜像 run 脚本传入）
#   SIP : 无 -x                     （镜像内确实没有 *.dict）
# ★ 严禁在 OPTIONS 里再追加 -x —— afl-fuzz.c:8897 对多个 -x 直接 FATAL。
# ★ 严禁把我们的 .dict 放进 in-* 目录 —— AFLNet 的 read_testcases() 用 scandir()
#   读取 -i 目录下**所有常规非空文件**（只跳过 README.txt）→ 字典会污染种子集。
# ===========================================================================
official_dict_path() {
  # ★ 定义在 rq4_protocols.sh（唯一真源）—— 那是**容器内**路径
  rq4_official_dict "$1"
}

# ===========================================================================
# 官方字典的**宿主缓存**（两组共用同一份 → dict_tokens 必须相同）
# ---------------------------------------------------------------------------
# ★ 为什么必须缓存到宿主：
#   字典在**镜像内**（${WORKDIR}/<proto>.dict），protorag 组的种子在宿主，
#   若直接用容器内路径去数 token，宿主上找不到文件 → dict_tokens=0
#   → 两组自证列出现"字典不一致"的假象（实测踩过）。
#   故：从镜像提取一次到 ${DICT_DIR}/<proto>.dict 缓存，两组都用这个宿主副本。
# ===========================================================================
DICT_DIR="${DICT_DIR:-/home/zxy/rq4/dicts}"

host_dict_file() {
  local proto="$1" img path
  path="${DICT_DIR}/${proto}.dict"
  [[ -s "$path" ]] && { echo "$path"; return 0; }
  [[ -s "$path" ]] || mkdir -p "$DICT_DIR" 2>/dev/null || return 1
  img=$(proto_field "$proto" image) || return 1
  local in_container
  in_container=$(official_dict_path "$proto")
  [[ -z "$in_container" ]] && return 1        # SIP 官方无字典
  local ctr
  ctr=$(docker create "$img" 2>/dev/null) || return 1
  if docker cp "$ctr:$in_container" "$path" >/dev/null 2>&1 && [[ -s "$path" ]]; then
    docker rm "$ctr" >/dev/null 2>&1 || true
    echo "$path"; return 0
  fi
  docker rm "$ctr" >/dev/null 2>&1 || true
  return 1
}

# ===========================================================================
# 种子画像：seed_files / seed_regions / dict_tokens
# ---------------------------------------------------------------------------
# protorag 组 → 种子在宿主 SEED_ROOT/<proto>/（我们挂进去的那份）
# baseline  组 → 种子在镜像自带 in-* 目录（宿主没有副本）→ 从容器内读
# 两者都交给 rq4_seed_profile.py 计算，保证口径一致。
# ===========================================================================
seed_profile_of() {
  local proto="$1" group="$2" name="$3" in_dir dict_path
  in_dir=$(proto_field "$proto" in_dir)
  # ★ 字典一律用**宿主缓存副本**（两组同一份 → dict_tokens 必须相同）
  dict_path=$(host_dict_file "$proto" || true)

  if [[ "$group" == "protorag" ]]; then
    local host_dir="${SEED_ROOT}/${proto}"
    if [[ -f "$SEED_PROFILE" && -d "$host_dir" ]]; then
      python3 "$SEED_PROFILE" --seed-dir "$host_dir" --protocol "$proto" \
        ${dict_path:+--dict-file "$dict_path"} 2>/dev/null
      return 0
    fi
    # 画像脚本不可用 → 至少给出文件数（region/dict 留空）
    if [[ -d "$host_dir" ]]; then
      echo "seed_files=$(find "$host_dir" -maxdepth 1 -name '*.raw' | wc -l)"
      return 0
    fi
    echo "seed_files=0"
    return 0
  fi

  # baseline：种子在容器内 in-* 目录。
  # 容器在运行时可直接 docker exec 读取；已退出则用 docker create+cp 提取
  # （docker cp 对已退出容器同样可用，且保留属主 —— 这里只统计数量/内容，
  #  统计由宿主上的 rq4_seed_profile.py 完成，故先把种子复制到宿主临时目录）。
  local tmp_dir
  tmp_dir=$(mktemp -d "/tmp/rq4_seedprof.XXXXXX") || { echo "seed_files=0"; return 0; }
  local extracted=0
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    if docker exec "$name" sh -c "tar cf - -C '$(dirname "$in_dir")' '$(basename "$in_dir")'" \
        2>/dev/null | tar xf - -C "$tmp_dir" 2>/dev/null; then
      extracted=1
    fi
  else
    local ctr
    ctr=$(docker create "$(proto_field "$proto" image)" 2>/dev/null || true)
    if [[ -n "$ctr" ]]; then
      if docker cp "$ctr:$in_dir" "${tmp_dir}/$(basename "$in_dir")" >/dev/null 2>&1; then
        extracted=1
      fi
      docker rm "$ctr" >/dev/null 2>&1 || true
    fi
  fi
  if [[ "$extracted" -eq 1 ]]; then
    python3 "$SEED_PROFILE" --seed-dir "${tmp_dir}/$(basename "$in_dir")" \
      --protocol "$proto" ${dict_path:+--dict-file "$dict_path"} 2>/dev/null || echo "seed_files=0"
    rm -rf "$tmp_dir"
    return 0
  fi
  rm -rf "$tmp_dir"
  echo "seed_files=0"
  return 0
}

# ===========================================================================
# 参数自检：command_line 的 OPTIONS 段 vs 参数表预期的 OPTIONS
# ---------------------------------------------------------------------------
# ★ 判定是**逐 token 序列全等**（顺序 + 个数 + 每个 token 的字面值都相等），
#   不是"子串包含"—— 子串判定挡不住数值漂移（-t 5000 vs -t 50000）
#   与尾部多选项（-X extra），会让护栏形同虚设。
# ★ 判定逻辑在 rq4_param_check.py（唯一真源；tests/fused/test_rq4_param_check.py
#   直接覆盖同一份实现）。本函数只负责取参数 + 调用，不重复实现判定规则。
# ★ 期望 OPTIONS 仍从 rq4_protocols.sh 的参数表取（唯一真源），绝不硬编码。
# ★ KP-2 修复：同协议各容器的**服务端命令尾巴**也必须一致。
#   规则 1 的 OPTIONS 窗口看不到「服务端命令**之后**被追加选项」
#   （如 `... ./testOnDemandRTSPServer 8554 -X extra`）—— 服务端自己的参数
#   （-f / -L / -Y / -n / -D / -E …）长得就像选项，不能靠"数 -开头的 token"判断，
#   只能**与同协议的参照容器逐字比对**。参照取该协议**首个**采集到的容器。
# ===========================================================================
PARAM_CHECK="${PARAM_CHECK:-${SCRIPT_DIR}/rq4_param_check.py}"

#: 每个协议的首个容器命令行（用作服务端命令尾巴的参照）
declare -A PARAM_REF_CMD=()

param_check_of() {
  local proto="$1" command_line="$2" reference="${3:-}"
  local expected net
  expected=$(proto_field "$proto" options) || { echo "MISMATCH"; return 1; }
  net=$(proto_field "$proto" net) || net=""

  # command_line 为空 → 容器尚未产出 fuzzer_stats（不是参数漂移）
  if [[ -z "$command_line" ]]; then
    echo "NO_COMMAND_LINE"
    return 0
  fi

  if [[ ! -f "$PARAM_CHECK" ]]; then
    echo "!! 找不到参数自检脚本: $PARAM_CHECK（无法判定，按 MISMATCH 处理）" >&2
    echo "MISMATCH"
    return 1
  fi

  local verdict
  if ! verdict=$(python3 "$PARAM_CHECK" \
        --options "$expected" --net "$net" --command-line "$command_line" \
        ${reference:+--reference-command-line "$reference"} 2>/dev/null); then
    echo "MISMATCH"
    return 1
  fi
  echo "$verdict"
}

# ===========================================================================
# cov_over_time.csv 末行的 l_per / b_per（官方 cov_script 口径）
# ---------------------------------------------------------------------------
# ★ 正确做法：**先由表头定位列号，再按列号取末行（数据行）的值**。
#   ✗ 历史实现在**数据行**里逐字段匹配**列名**（`if ($i==k)`）——
#     但数据行装的是**数值**（`1793327218,24.7,5899,15.7,2914`），
#     没有任何字段等于字符串 "l_per" → **永远匹配不上 → 恒返回空串**。
#     实测后果（QA 于 VM 上跑通 collect.sh 证实）：l_per / b_per 两列 6 行全空，
#     下游「bitmap_cvg 与 l_per 是否同向」这条论文必需的检查**完全无法进行**。
# ★ 守卫：只有表头没有数据行时，`tail -1` 会把**表头**当数据行读出来
#   （返回列名 "l_per" 本身）→ 必须显式挡掉。
# ★ 取**最后一个该列有值的数据行**（而不是死盯物理末行）：
#   实测 SIP 的 cov_over_time.csv 里存在**整行字段全空**的采样行
#   （如 `1793322269,,,,` —— cov_script 某些时刻没取到覆盖数据）。
#   那些空行若恰好落在末尾，死盯末行会让 l_per/b_per **凭空丢失**；
#   故从末尾往前找**该列非空**的那一行（覆盖率是累计量，非空行的值才是有效测量）。
#   ⚠ 只在**该列取值为空**时回退；末行本身有值时一律用末行（保持"终值"语义）。
# ===========================================================================
cov_last_row() {
  local csv="$1" key="$2"
  [[ -s "$csv" ]] || { echo ""; return; }
  # 表头: Time,l_per,l_abs,b_per,b_abs
  local hdr col last
  hdr=$(head -1 "$csv" | tr -d '\r')
  echo "$hdr" | grep -q '^Time,' || { echo ""; return; }
  # 由表头定位列号（未知列名 → 空 → 返回空串，不误取别的列）
  col=$(echo "$hdr" | awk -F',' -v k="$key" \
          '{for(i=1;i<=NF;i++) if($i==k){print i; exit}}')
  [[ -n "$col" ]] || { echo ""; return; }
  # 数据行（排除空行与表头行）
  local rows
  rows=$(tr -d '\r' < "$csv" | grep -v '^[[:space:]]*$' | tail -n +2)
  [[ -n "$rows" ]] || { echo ""; return; }
  # 该列有值的最后一行；找不到 → 返回空串
  last=$(echo "$rows" | awk -F',' -v c="$col" \
           '{v=$c; gsub(/[[:space:]]/,"",v); if (v != "") line=$0} END{print line}')
  [[ -n "$last" ]] || { echo ""; return; }
  echo "$last" | awk -F',' -v c="$col" '{print $c}'
}

# ===========================================================================
# fuzzer_stats 字段解析
# ===========================================================================
# 从 fuzzer_stats 文本里抽 key:value（afl-fuzz 的格式是 "key : value"）。
# 注意：command_line 自身含冒号与空格，必须整行取（用 sed 去掉前缀）。
stat_field() {
  local file="$1" key="$2" line
  line=$(grep -E "^${key} *:" "$file" 2>/dev/null | head -1)
  if [[ -z "$line" ]]; then
    echo ""
    return
  fi
  if [[ "$key" == "command_line" ]]; then
    # command_line 整行保留（去掉 "command_line :" 前缀）
    echo "$line" | sed -E 's/^command_line *: *//'
  else
    echo "$line" | sed -E "s/^${key} *: *//" | tr -d '\r'
  fi
}

# ===========================================================================
# 采集单个容器
# ===========================================================================
collect_one() {
  local proto="$1" group="$2" rep="$3"
  local name="rq4_${proto}_${group}_r${rep}"
  local outdir host_out stats
  outdir=$(container_outdir "$proto" "$group" "$rep") || { echo "!! 未知协议 $proto" >&2; return 1; }
  host_out="${OUT_ROOT}/${proto}/${group}/r${rep}"
  stats="${host_out}/fuzzer_stats"

  # --- 离线模式：产物已在宿主，直接读（不碰 docker）---
  if [[ -n "$OFFLINE_DIR" ]]; then
    host_out="${OFFLINE_DIR}/${proto}/${group}/r${rep}"
    stats="${host_out}/fuzzer_stats"
    if [[ ! -s "$stats" ]]; then
      echo "!! 离线产物缺失 fuzzer_stats: $stats" >&2
      return 1
    fi
  else
    if ! docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
      echo "!! 容器不存在: $name" >&2
      return 1
    fi
  fi

  mkdir -p "$host_out"

  # ★ 用 docker exec + 宿主侧重定向 —— 不用 docker cp（属主 root 读不到）
  #   离线模式：产物已在宿主（host_out），无需再取。
  local running=0
  if [[ -n "$OFFLINE_DIR" ]]; then
    :
  else
    docker ps --format '{{.Names}}' | grep -qx "$name" && running=1

    if [[ "$running" -eq 1 ]]; then
      if ! docker exec "$name" cat "${outdir}/fuzzer_stats" > "$stats" 2>/dev/null; then
        echo "!! 采集 fuzzer_stats 失败: $name" >&2
        return 1
      fi
    else
      # 容器已退出：docker cp 保留属主 → 读不到。改为用 docker cp 拿整个 tar，
      # 再在**容器内**（root 身份）解出 fuzzer_stats 并 cat 出来。
      local tar_path="${WORKDIR}/out-${proto}-${group}-r${rep}.tar.gz"
      if ! docker cp "$name":"$tar_path" "${host_out}/out.tar.gz" >/dev/null 2>&1; then
        echo "!! 采集 tar 失败: $name" >&2
        return 1
      fi
      # ★ 解包在容器内做（root 身份），产物经 stdout 重定向回宿主 → 属主=zxy
      if ! docker run --rm -v "${host_out}:/out" --entrypoint /bin/bash "$(
          proto_field "$proto" image)" -c \
          "cd /out && tar xzf out.tar.gz && cat $(basename "$outdir")/fuzzer_stats" \
          > "$stats" 2>/dev/null; then
        echo "!! 从 tar 解出 fuzzer_stats 失败: $name" >&2
        return 1
      fi
      # ★ KP-3 修复：容器退出后 cov_over_time.csv **同样要从 tar 里取**。
      #   历史实现在下面用 `docker exec` 取 cov_over_time.csv，而 docker exec
      #   **只能对运行中的容器用** → 容器一退出，l_per / b_per 就**彻底没有来源**
      #   （次要指标两列全空 → 论文必需的「口径一致性检查」无法进行）。
      #   官方 run 脚本的收尾是 `tar -zcvf ${WORKDIR}/${OUTDIR}.tar.gz ${OUTDIR}`，
      #   而 cov_over_time.csv 就产在 OUTDIR 里 → tar 内必然带得上。
      if ! docker run --rm -v "${host_out}:/out" --entrypoint /bin/bash "$(
          proto_field "$proto" image)" -c \
          "cd /out && cat $(basename "$outdir")/cov_over_time.csv" \
          > "${host_out}/cov_over_time.csv" 2>/dev/null; then
        # 取不到不算致命（次要指标缺失只影响口径检查，主指标不受影响）→ 仅告警
        echo "!! 从 tar 解出 cov_over_time.csv 失败（次要指标将缺失）: $name" >&2
        rm -f "${host_out}/cov_over_time.csv"
      fi
    fi
  fi

  if [[ ! -s "$stats" ]]; then
    echo "!! fuzzer_stats 为空: $name（容器可能尚未产出统计）" >&2
    return 1
  fi

  # ---- 采集其余产物（同样走 docker exec，避免属主问题）----
  #   注：容器**运行中**时 cov_over_time.csv 由 docker exec 取；
  #   容器**已退出**时由上面的 tar 分支取（KP-3 修复）——两条路径都要有来源。
  if [[ "$running" -eq 1 ]]; then
    docker exec "$name" cat "${outdir}/cov_over_time.csv" \
      > "${host_out}/cov_over_time.csv" 2>/dev/null || true
  fi
  # 归档容器日志（post-mortem 用）
  if [[ -z "$OFFLINE_DIR" ]]; then
    mkdir -p "$LOG_DIR"
    docker logs "$name" > "${LOG_DIR}/${name}.log" 2>&1 || true
  fi

  # ---- 抽字段 ----
  local f
  f() { stat_field "$stats" "$1"; }
  local start_time last_update cycles_done execs_done execs_per_sec
  local paths_total paths_found max_depth cur_path stability bitmap_cvg
  local unique_crashes unique_hangs command_line peak_rss_mb
  start_time=$(f start_time);        last_update=$(f last_update)
  cycles_done=$(f cycles_done);      execs_done=$(f execs_done)
  execs_per_sec=$(f execs_per_sec); paths_total=$(f paths_total)
  paths_found=$(f paths_found);      max_depth=$(f max_depth)
  cur_path=$(f cur_path);           stability=$(f stability)
  bitmap_cvg=$(f bitmap_cvg);       unique_crashes=$(f unique_crashes)
  unique_hangs=$(f unique_hangs);   peak_rss_mb=$(f peak_rss_mb)
  command_line=$(f command_line)

  # ---- 次要指标：官方 cov_over_time.csv 末行的 l_per / b_per ----
  local l_per b_per
  l_per=$(cov_last_row "${host_out}/cov_over_time.csv" l_per)
  b_per=$(cov_last_row "${host_out}/cov_over_time.csv" b_per)

  # ---- 种子画像（自证"两组只有种子不同"）----
  local seed_files seed_regions dict_tokens
  local prof
  prof=$(seed_profile_of "$proto" "$group" "$name")
  seed_files=$(echo "$prof" | sed -n 's/^seed_files=//p' | head -1)
  seed_regions=$(echo "$prof" | sed -n 's/^seed_regions=//p' | head -1)
  dict_tokens=$(echo "$prof" | sed -n 's/^dict_tokens=//p' | head -1)
  seed_files="${seed_files:-0}"; seed_regions="${seed_regions:-}"
  dict_tokens="${dict_tokens:-}"

  # fuzz_sec：last_update - start_time（afl-fuzz 用秒）
  local fuzz_sec=""
  if [[ -n "$start_time" && -n "$last_update" ]]; then
    fuzz_sec=$((last_update - start_time))
  fi

  # ---- 参数自检：command_line 的 OPTIONS 段必须与参数表**逐 token 全等** ----
  #   ★ 历史实现在这里内联做「子串包含」判定（[[ "$cmd" != *"$expected"* ]]），
  #     挡不住两类最要命的参数漂移（QA 实跑证实）：
  #       · 数值漂移：期望 "-t 5000"、实际 "-t 50000" → 子串命中 → 漏报
  #       · 尾部多选项：实际尾部多出 "-X extra"      → 子串命中 → 漏报
  #     现改为**逐 token 序列全等**（顺序 + 个数 + 逐 token 相等）。
  #   ★ 判定逻辑在 rq4_param_check.py（唯一真源，pytest 直接覆盖同一实现），
  #     本脚本只负责取参数 + 调用 —— 避免"bash 一份 / python 一份"两处实现漂移。
  #   ★ KP-2：同协议的服务端命令尾巴也要与参照容器逐字一致（挡住"服务端命令
  #     之后"被追加选项 —— OPTIONS 窗口看不到那里）。
  local param_ok
  param_ok=$(param_check_of "$proto" "$command_line" "${PARAM_REF_CMD[$proto]:-}")
  # 该协议的首个容器 → 记为后续容器的参照（服务端命令尾巴比对用）
  if [[ -z "${PARAM_REF_CMD[$proto]:-}" && -n "$command_line" ]]; then
    PARAM_REF_CMD["$proto"]="$command_line"
  fi

  # ---- 写汇总行 ----
  local image exit_code
  image=$(proto_field "$proto" image)
  exit_code=""
  if [[ -z "$OFFLINE_DIR" ]]; then
    exit_code=$(docker inspect -f '{{.State.ExitCode}}' "$name" 2>/dev/null || echo "")
  fi
  local esc
  esc=$(echo "$command_line" | sed 's/"/""/g')
  # ★ 格式串的占位符个数必须与实参个数**严格相等**（28 个）。
  #   否则 bash printf 会**重用格式串**（多余的参数触发第二遍）→
  #   每行后面多出一条全空行，且最后一个字段被丢弃。
  #   改动字段时务必同步核对：`printf '%s'` 的个数 == 下面实参的个数 == 表头列数。
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$proto" "$group" "$rep" "$name" "$image" \
    "$start_time" "$last_update" "$fuzz_sec" "$cycles_done" "$execs_done" \
    "$execs_per_sec" "$paths_total" "$paths_found" "$max_depth" "$cur_path" \
    "$stability" "$bitmap_cvg" "$unique_crashes" "$unique_hangs" \
    "$peak_rss_mb" "$param_ok" "$exit_code" "\"$esc\"" \
    "$seed_files" "$seed_regions" "$dict_tokens" "$l_per" "$b_per" \
    >> "$SUMMARY"

  # ---- 写产物自证清单（旁挂 md5 日志；不动 summary 的 28 列）----
  #   每行格式：<md5>  <路径>   —— 与 md5sum 的输出同构，可直接 `md5sum -c` 校验。
  #   收录三类产物：宿主明文副本（fuzzer_stats / cov_over_time.csv）与官方 tar.gz。
  #   日后核验：md5sum -c artifacts.md5 → 全部 OK 即证明产物自采集以来未被改动。
  #
  #   ★ 路径用**绝对路径**（2026-10-30 定案）：
  #     - 相对 OUT_ROOT 写 → 清单在 summary 目录、产物在 out/ 下 → 两者不同源
  #       → md5sum -c 找不到文件（实测 0/18 OK）；
  #     - 相对「清单所在目录」写 → 生成时可用，但**清单被移动/复制到别处就失效**
  #       （实测复制到 /home/zxy/rq4 后 0/18 OK）。
  #     - 绝对路径 → 在**任意目录**执行 md5sum -c 都是 18/18 OK（已实测两种 cwd）。
  #     代价：换机器/换 out_root 后需重新生成清单（采集时会自动重建）。
  {
    local f abs_f
    for f in "$host_out/fuzzer_stats" "$host_out/cov_over_time.csv" "$host_out/out.tar.gz"; do
      [[ -f "$f" ]] || continue
      abs_f=$(cd "$(dirname "$f")" && pwd)/$(basename "$f")
      printf '%s  %s\n' "$(md5sum "$f" 2>/dev/null | cut -d' ' -f1)" "$abs_f" \
        >> "$(artifact_manifest_path)"
    done
  }

  log "采集完成 $name（execs_done=$execs_done bitmap_cvg=$bitmap_cvg l_per=$l_per 参数自检=$param_ok 种子=${seed_files}文件/${seed_regions}regions 字典=${dict_tokens}tokens）"
  return 0
}

# ===========================================================================
# 快照（运行期间）：周期性抓 fuzzer_stats，用于画覆盖率时序曲线
# ===========================================================================
snapshot_loop() {
  local proto group rep name outdir host_out
  while true; do
    for proto in $(echo "$PROTOCOLS" | tr ',' ' '); do
      for group in $(echo "$GROUP_LIST" | tr ',' ' '); do
        for ((rep = 1; rep <= REPS; rep++)); do
          name="rq4_${proto}_${group}_r${rep}"
          outdir=$(container_outdir "$proto" "$group" "$rep") || continue
          host_out="${OUT_ROOT}/${proto}/${group}/r${rep}"
          mkdir -p "$host_out"
          docker ps --format '{{.Names}}' | grep -qx "$name" || continue
          docker exec "$name" cat "${outdir}/fuzzer_stats" \
            > "${host_out}/stats_$(date +%s).txt" 2>/dev/null || true
        done
      done
    done
    sleep "$SNAPSHOT_INTERVAL"
  done
}

# ===========================================================================
# 主流程
# ===========================================================================
main() {
  echo "=============================================================="
  echo " RQ4 结果采集"
  echo "=============================================================="
  echo " protocols : $PROTOCOLS"
  echo " groups    : $GROUP_LIST"
  echo " reps      : $REPS"
  echo " out-root  : $OUT_ROOT"
  echo " summary   : $SUMMARY"
  [[ "$WAIT" -eq 1 ]] && echo " 模式     : --wait（等待容器退出后采集）"
  echo "=============================================================="

  mkdir -p "$OUT_ROOT" "$LOG_DIR"

  # --snapshot-only：只跑快照循环（供 rq4_analyze.py 做 execs_done 对齐插值），
  #   **不做终态采集** —— 终态采集留给 QA，避免 summary.csv 被重复追加行。
  if [[ "$SNAPSHOT_ONLY" -eq 1 ]]; then
    log "仅快照模式：每 ${SNAPSHOT_INTERVAL}s 抓一次 fuzzer_stats（Ctrl-C 结束）"
    snapshot_loop
    exit 0
  fi

  # 表头（与 collect_one 的 printf 字段顺序严格一致）
  if [[ ! -f "$SUMMARY" ]]; then
    echo "protocol,group,rep,container,image,start_time,last_update,fuzz_sec,cycles_done,execs_done,execs_per_sec,paths_total,paths_found,max_depth,cur_path,stability,bitmap_cvg,unique_crashes,unique_hangs,peak_rss_mb,param_check,exit_code,command_line,seed_files,seed_regions,dict_tokens,l_per,b_per" \
      > "$SUMMARY"
    # ★ 产物自证清单与 summary **同生命周期**：summary 重建 → 清单一并重建。
    #   否则旧清单的行会残留，与新一轮的行混在一起 → md5sum -c 会误判。
    : > "$(artifact_manifest_path)"
  fi

  # 等待模式：先起快照循环，再等容器退出
  local snap_pid=""
  if [[ "$WAIT" -eq 1 ]]; then
    snapshot_loop &
    snap_pid=$!
    log "等待容器退出（上限 ${WAIT_TIMEOUT}s）..."
    local names=()
    local proto group rep name
    for proto in $(echo "$PROTOCOLS" | tr ',' ' '); do
      for group in $(echo "$GROUP_LIST" | tr ',' ' '); do
        for ((rep = 1; rep <= REPS; rep++)); do
          name="rq4_${proto}_${group}_r${rep}"
          docker ps -a --format '{{.Names}}' | grep -qx "$name" && names+=("$name")
        done
      done
    done
    if [[ ${#names[@]} -gt 0 ]]; then
      # docker wait 会等到容器停止；但 run 脚本在 fuzz 结束后还有 1~3h 的 cov_script 后处理，
      # 因此额外设超时上限，超时后仍继续采集已有产物（主指标不依赖后处理）。
      timeout "$WAIT_TIMEOUT" docker wait "${names[@]}" >/dev/null 2>&1 || true
    fi
    [[ -n "$snap_pid" ]] && kill "$snap_pid" 2>/dev/null
    wait "$snap_pid" 2>/dev/null || true
  fi

  local proto group rep ok=0 fail=0
  for proto in $(echo "$PROTOCOLS" | tr ',' ' '); do
    for group in $(echo "$GROUP_LIST" | tr ',' ' '); do
      for ((rep = 1; rep <= REPS; rep++)); do
        if collect_one "$proto" "$group" "$rep"; then
          ok=$((ok + 1))
        else
          fail=$((fail + 1))
        fi
      done
    done
  done

  echo "=============================================================="
  echo " 采集成功 $ok 个 / 失败 $fail 个"
  echo " 汇总表: $SUMMARY"
  echo "=============================================================="
  [[ "$fail" -gt 0 ]] && exit 1
  exit 0
}

main "$@"
