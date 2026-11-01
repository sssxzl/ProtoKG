#!/bin/bash
# rq4_protocols.sh —— RQ4 实验的**协议参数唯一真源**（被三个脚本 source）
#
# 为什么单独抽一个文件
# --------------------
# 既往 rq2_launch_target.sh 的参数散落在各个 case 分支里 → 漏了 `-l 5061`
# （kamailio 缺 -l → 服务端响应不回传 → AFLNet "No server states" PFATAL）。
# 修法是"表驱动"，但如果**每个脚本各抄一份表**，就等于把散落换成了"三处复制"
# —— 改一处忘两处，仍会漂移。故本文件是唯一真源，三脚本 source 它。
#
# ★ 改这张表 = 改实验配置。三个脚本（launch / collect / dryrun）必须同步生效。
# ★ options 逐字取自 VM `/home/zxy/profuzzbench/scripts/execution/profuzzbench_exec_all.sh`
#   （HEAD 8573ec8）：TEST_TIMEOUT=5000（固定值，不是 1000+/3000+ 自动标定）、
#   TIMEOUT=3600、SKIPCOUNT=5。`-m none` 必须有（否则 50MB rlimit 秒杀 ASAN 目标）。
# ★ 字典**不在**这张表里：RTSP/SMTP 的 `-x ${WORKDIR}/*.dict` 由镜像自带的 run 脚本
#   传入；SIP 官方无字典。绝不能在这里追加 `-x`（afl-fuzz.c:8897 对多个 -x FATAL）。
#
# 字段: image|proto|net|in_dir|work_dir|options
#   in_dir   —— 容器内种子目录（protorag 组用同名 bind mount 覆盖它）
#   work_dir —— 容器内目标程序工作目录（产物 fuzzer_stats 就在它下面）
#
# 用法（被 source，不是直接执行）:
#   source /home/zxy/rq4/scripts/rq4_protocols.sh
#   PROTO_TABLE            # 表内容
#   proto_field rtsp options
#
# ★ proto_field 按**字段名**取值（不用下标）——下标容易 off-by-one，
#   历史上正是"按序号取字段"导致 image/proto/net/options 全体错位一格。

# 协议参数表（唯一真源）
PROTO_TABLE=$(cat <<'EOF'
rq2-live555:latest|rtsp|tcp://127.0.0.1/8554|/home/ubuntu/experiments/in-rtsp|/home/ubuntu/experiments/live/testProgs|-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 5000
rq2-kamailio:latest|sip|udp://127.0.0.1/5060|/home/ubuntu/experiments/in-sip|/home/ubuntu/experiments/kamailio|-m none -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -t 5000
rq2-exim:latest|smtp|tcp://127.0.0.1/25|/home/ubuntu/experiments/in-smtp|/home/ubuntu/experiments/exim|-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100 -m none -t 5000
EOF
)

# 容器内官方工作目录（镜像 run 脚本的 cd 目标）
RQ4_WORKDIR="/home/ubuntu/experiments"

# 模糊测试器名（镜像内 /home/ubuntu/<FUZZER>/afl-fuzz）
RQ4_FUZZER="aflnet"

# 各协议默认 dry-run fuzz 时长（秒）—— 必须显著大于该协议的 perform_dry_run 耗时：
#   rtsp：39 个种子 → stats 约 15s 落盘
#   sip ：25 个种子 → stats 约 50s 落盘
#   smtp：78 个种子 → stats 约 175~600s+ 落盘！
#         （AFLNet 先跑 perform_dry_run 把每个种子试跑一遍；
#          SMTP 每次试跑都要重启 exim，而 exim 是 ASAN 构建、启动慢，
#          加之 -D 10000（server 初始化只等 10ms）不足 → 部分用例等满 -t 5000
#          → 实测 perform_dry_run 在 175s~600s+ 之间波动）
#         → 正式实验的 3h 同样要吃掉这段，dry-run 必须给足余量。
RQ4_DURATION_BY_PROTO="rtsp=180 sip=180 smtp=1200"

# 取某协议的某个字段
# 用法: field=$(proto_field <proto> <field_name>)
# 字段名: image | proto | net | in_dir | work_dir | options
proto_field() {
  local proto="$1" fname="$2" line
  line=$(echo "$PROTO_TABLE" | awk -F'|' -v p="$proto" '$2==p {print; exit}')
  [[ -z "$line" ]] && return 1
  case "$fname" in
    image)   echo "$line" | cut -d'|' -f1 ;;
    proto)   echo "$line" | cut -d'|' -f2 ;;
    net)     echo "$line" | cut -d'|' -f3 ;;
    in_dir)  echo "$line" | cut -d'|' -f4 ;;
    work_dir) echo "$line" | cut -d'|' -f5 ;;
    options) echo "$line" | cut -d'|' -f6 ;;
    *) echo "!! 未知参数字段: $fname" >&2; return 2 ;;
  esac
}

# 官方字典路径（SIP 官方无字典 → 空）
# 字典是**两组共用**的镜像内官方字典（裁决：option b），
# 故 dict_tokens 必须相同 → 证明"两组只有种子不同"。
rq4_official_dict() {
  case "$1" in
    rtsp) echo "${RQ4_WORKDIR}/rtsp.dict" ;;
    smtp) echo "${RQ4_WORKDIR}/smtp.dict" ;;
    *)    echo "" ;;
  esac
}

# 某协议的默认 dry-run fuzz 时长
rq4_duration_for() {
  local proto="$1" d
  d=$(echo "$RQ4_DURATION_BY_PROTO" | tr ' ' '\n' | grep "^${proto}=" | cut -d= -f2)
  echo "${d:-180}"
}
