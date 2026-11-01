#!/bin/bash
# version: 2026-10-24-v2
# ↑ 版本标记：编排前用 `grep '^# version:'` 校验 VM 副本与本地一致（防版本漂移）
# ★ RQ3 启动前健康检查（预检）—— 8 项必检 + 4 项记录，全部 PASS 才放行
#
# 用法（在 VM 上）：bash rq3_preflight.sh
# 退出码: 0 = 全部通过可放行；非 0 = 有 FAIL 项，禁止启动容器
#
# 检查项（技术方案 §3.6）：
#   H1  镜像存在且可运行
#   H2  四组语料条数正确（A=38 / B=50 / C=50 / D=50）
#   H3  字典 token 数与 MD5 正确
#   H4  镜像内基础字典 MD5 未变（防 Wave1/Wave2 间镜像被改）
#   H5  /out 为空（新目录）
#   H6  ★ LLM 端点不可达断言（宿主可达性记录）
#   H7  磁盘余量 ≥ 12 GB
#   H8  容器命名不冲突
#   H9-H12（不阻塞但必须记录）：RQ1.2 容器已停 / ASAN 服务器存在 / oracle 端口空闲
set -uo pipefail

IMG=rq2-live555:latest
SEED_ROOT=/home/zxy/rq3_seeds
DICT_ROOT=/home/zxy/rq3_dict
OUT_ROOT=/home/zxy/rq3_out
SNAP_ROOT=/home/zxy/rq3_snap
ORACLE_DIR=/home/zxy/live555-asan/testProgs

MIN_FREE_BYTES=$((12 * 1024 * 1024 * 1024))
LLM_ENDPOINT=192.168.37.1:18080

# 注意：不可用 GROUPS 作变量名——bash 内建特殊变量（当前用户组 ID 数组），赋值无效。
GRP_LIST="A B C D"
REPS="1 2 3 4 5"

PASS=0
FAIL=0
FAILLOG=/tmp/rq3_preflight_fail.log
: > "$FAILLOG"

ok()   { echo "[PASS] $1"; PASS=$((PASS+1)); }
bad()  { echo "[FAIL] $1"; FAIL=$((FAIL+1)); echo "$1" >> "$FAILLOG"; }
info() { echo "[INFO] $1"; }

echo "================ RQ3 预检 ================"
echo "时间: $(date -Is)"
echo

# ---- H0：脚本行尾格式（★ 防 CRLF 导致的语法错误）----
#   Windows 编辑器可能把脚本写成 CRLF → bash 报 "invalid option name" / "syntax error"。
#   本地仓库用 LF；此处**强制**检查，检出 CRLF 立即 FAIL（不是静默跳过）。
CRLF_BAD=0
for f in rq3_preflight.sh rq3_live555_abc.sh rq3_collect.sh rq3_snapshot.sh \
         rq3_oracle_batch.sh; do
  p="/home/zxy/$f"
  [ -f "$p" ] || continue
  if grep -qU $'\r' "$p" 2>/dev/null; then
    bad "H0 脚本含 CRLF 行尾（bash 会语法错误）: $p —— 请用 LF 重新上传"
    CRLF_BAD=1
  fi
done
[ "$CRLF_BAD" = "0" ] && ok "H0 全部脚本行尾为 LF"

# ---- H1 镜像存在且可运行 ----
if docker image inspect "$IMG" >/dev/null 2>&1; then
  if docker run --rm --network none "$IMG" true >/dev/null 2>&1; then
    ok "H1 镜像存在且可运行: $IMG"
  else
    bad "H1 镜像存在但无法运行: $IMG"
  fi
else
  bad "H1 镜像不存在: $IMG"
fi

# ---- H2 四组语料条数 ----
declare -A EXPECT=( [A]=38 [B]=50 [C]=50 [D]=50 )
for g in $GRP_LIST; do
  n=$(ls "$SEED_ROOT/$g/seeds"/*.raw 2>/dev/null | wc -l)
  e=${EXPECT[$g]}
  if [ "$n" = "$e" ]; then
    ok "H2 组 $g 语料条数 $n（期望 $e）"
  else
    bad "H2 组 $g 语料条数 $n（期望 $e）"
  fi
done

# ---- H3/H4 字典 token 数与 MD5 ----
if [ -f "$DICT_ROOT/rtsp_base.dict" ]; then
  n=$(grep -c . "$DICT_ROOT/rtsp_base.dict")
  m=$(md5sum "$DICT_ROOT/rtsp_base.dict" | awk '{print $1}')
  if [ "$n" = "24" ] && [ "$m" = "464351f88db6c3f0bdac0de01859316b" ]; then
    ok "H3 基础字典 24 token 且 MD5 正确"
  else
    bad "H3 基础字典 token=$n md5=$m（期望 24 / 464351f88db6c3f0bdac0de01859316b）"
  fi
else
  bad "H3 缺少基础字典 $DICT_ROOT/rtsp_base.dict"
fi

if [ -f "$DICT_ROOT/c_targeted.dict" ]; then
  n=$(grep -c . "$DICT_ROOT/c_targeted.dict")
  m=$(md5sum "$DICT_ROOT/c_targeted.dict" | awk '{print $1}')
  FROZEN_MD5=""
  if [ -f /home/zxy/rq3_dict/DICT_FROZEN.json ]; then
    FROZEN_MD5=$(python3 -c "
import json,sys
d=json.load(open('/home/zxy/rq3_dict/DICT_FROZEN.json'))
for r in d.get('dictionaries',[]):
    if r.get('kind')=='targeted': print(r.get('md5',''))
" 2>/dev/null)
  fi
  if [ "$n" = "123" ]; then
    ok "H3 定向字典 123 token"
  else
    bad "H3 定向字典 token=$n（期望 123）"
  fi
  if [ -n "$FROZEN_MD5" ] && [ "$m" != "$FROZEN_MD5" ]; then
    bad "H3 定向字典 MD5 与 DICT_FROZEN.json 不一致（$m vs $FROZEN_MD5）→ 字典已漂移"
  elif [ -n "$FROZEN_MD5" ]; then
    ok "H3 定向字典 MD5 与冻结记录一致"
  else
    info "H3 未找到 DICT_FROZEN.json，跳过定向字典 MD5 冻结核对"
  fi
else
  bad "H3 缺少定向字典 $DICT_ROOT/c_targeted.dict"
fi

# ---- H4 镜像内基础字典 MD5 未变 ----
IMG_MD5=$(docker run --rm --network none "$IMG" \
  md5sum /home/ubuntu/experiments/rtsp.dict 2>/dev/null | awk '{print $1}')
if [ "$IMG_MD5" = "464351f88db6c3f0bdac0de01859316b" ]; then
  ok "H4 镜像内基础字典 MD5 未变"
elif [ -z "$IMG_MD5" ]; then
  bad "H4 无法读取镜像内 rtsp.dict"
else
  bad "H4 镜像内 rtsp.dict MD5 已变: $IMG_MD5"
fi

# ---- H5 /out 为空 ----
DIRTY=0
for g in $GRP_LIST; do
  for fz in chatafl aflnet; do
    for r in $REPS; do
      d="$OUT_ROOT/${g}_${fz}/r${r}"
      if [ -d "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ]; then
        bad "H5 输出目录非空: $d"
        DIRTY=1
      fi
    done
  done
done
[ "$DIRTY" = "0" ] && ok "H5 所有输出目录为空"

# ---- H5b 输出根目录可写（★ 编排脚本以普通用户 mkdir -p $OUT_ROOT/<组>_<fzzer>/r<n>）----
#   踩坑：若 $OUT_ROOT 曾被容器内 root 创建（属主 root），宿主用户 mkdir 会
#   Permission denied → 启动直接失败。
if [ ! -d "$OUT_ROOT" ]; then
  bad "H5b 输出根目录不存在: $OUT_ROOT —— 请先 mkdir -p 并 chown 到当前用户"
elif ! mkdir -p "$OUT_ROOT/.rq3_wtest" 2>/dev/null; then
  bad "H5b 输出根目录不可写: $OUT_ROOT（属主 $(stat -c %U "$OUT_ROOT")）—— chown 修复"
else
  rmdir "$OUT_ROOT/.rq3_wtest" 2>/dev/null
  ok "H5b 输出根目录可写: $OUT_ROOT"
fi

# ---- H5c 语料/字典根目录可读 ----
for d in "$SEED_ROOT" "$DICT_ROOT"; do
  if [ ! -r "$d" ]; then
    bad "H5c 目录不可读: $d"
  fi
done
[ -r "$SEED_ROOT" ] && [ -r "$DICT_ROOT" ] && ok "H5c 语料与字典根目录可读"

# ---- H6 LLM 端点不可达断言（宿主可达性记录；容器内已由 --network none 隔离）----
if timeout 5 bash -c "exec 3<>/dev/tcp/$LLM_ENDPOINT" 2>/dev/null; then
  info "H6 宿主可达 LLM 端点 $LLM_ENDPOINT —— 但容器 --network none 已隔离，不阻塞"
else
  ok "H6 宿主不可达 LLM 端点 $LLM_ENDPOINT"
fi

# ---- H7 磁盘余量 ----
# ★ v2 修正（推翻「17 MB 无风险」的说法）：`du -sh /home/zxy/rq2_out` 的 17 MB 是
#   **权限假象**（容器以 root 运行 → 宿主普通用户看不到 queue/ 等目录）。
#   真实占用：`sudo -n du -sh` = 3.0 GB，容器内 `du -sb /out` 求和 = 2747 MB。
#   → 按 3.0 GB / 20 容器 / 9 h 外推，**24 h 单波 20 容器约 8–12 GB**。
#   → 磁盘剩 20 GB → **最多 1 波**；Wave 2 前必须先归档并删除 Wave 1 的 /out。
MIN_FREE_BYTES=$((12 * 1024 * 1024 * 1024))
WAVE_ESTIMATE_BYTES=$((12 * 1024 * 1024 * 1024))

FREE=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
if [ "$FREE" -ge "$MIN_FREE_BYTES" ]; then
  ok "H7 磁盘可用 $((FREE / 1024 / 1024 / 1024)) GB（≥ 12 GB）"
else
  bad "H7 磁盘可用 $((FREE / 1024 / 1024 / 1024)) GB < 12 GB —— 先归档清理"
fi

# ---- H7b：真实占用口径（★ 不用普通用户的 du —— 那是权限假象）----
# 用容器内 du -sb 求和（唯一可信口径）；无容器在跑时退回 sudo。
USED_REAL=0
for n in $(docker ps --format '{{.Names}}' 2>/dev/null); do
  b=$(docker exec "$n" bash -c 'du -sb /out 2>/dev/null | cut -f1' 2>/dev/null)
  [ -n "$b" ] && USED_REAL=$((USED_REAL + b))
done
if [ "$USED_REAL" = "0" ]; then
  USED_REAL=$(sudo -n du -sb /home/zxy/rq2_out 2>/dev/null | cut -f1)
  [ -z "$USED_REAL" ] && USED_REAL=0
fi
USED_GB=$((USED_REAL / 1024 / 1024 / 1024))
info "H7b 真实占用口径（容器内 du -sb 求和 / sudo）：${USED_GB} GB"
if [ $((USED_REAL + WAVE_ESTIMATE_BYTES)) -gt "$FREE" ]; then
  bad "H7b 磁盘不足：现有 ${USED_GB} GB + 单波预估 12 GB > 可用 $((FREE / 1024 / 1024 / 1024)) GB"
  echo "     → 先归档并删除上一波的 /out，再启动（单波最多 20 容器）" >> "$FAILLOG"
else
  ok "H7b 磁盘可容纳 1 波（现有 ${USED_GB} GB + 预估 12 GB ≤ 可用 $((FREE / 1024 / 1024 / 1024)) GB）"
fi

# ---- H8 容器命名不冲突 ----
EXIST=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -c '^rq3_' || true)
if [ "$EXIST" = "0" ]; then
  ok "H8 无遗留 rq3_ 容器"
else
  bad "H8 存在 $EXIST 个 rq3_ 容器 —— 先清理（旧 /out 不可复用）"
fi

# ---- H13（QA-3）：★ 版本漂移检测 ----
#   VM 上的脚本副本必须与本地一致。校验手段：
#     ① 版本标记 `# version: <VER>` 必须存在且与本脚本一致
#     ② 关键脚本的 MD5 必须与本地一致（本地清单由 deploy 时写入 .rq3_manifest）
EXPECT_VER="2026-10-24-v2"
DRIFT=0
for f in rq3_preflight.sh rq3_live555_abc.sh rq3_collect.sh rq3_snapshot.sh \
         rq3_oracle_batch.sh; do
  if [ ! -f "/home/zxy/$f" ]; then
    bad "H13 VM 缺少脚本: /home/zxy/$f"
    DRIFT=1
    continue
  fi
  v=$(grep -m1 '^# version:' "/home/zxy/$f" | awk '{print $3}')
  if [ "$v" != "$EXPECT_VER" ]; then
    bad "H13 版本漂移: /home/zxy/$f 版本='$v'（期望 '$EXPECT_VER'）—— 请重新同步"
    DRIFT=1
  fi
done
if [ "$DRIFT" = "0" ]; then
  ok "H13 VM 脚本版本一致（$EXPECT_VER）"
fi

# ---- H14（QA-3）：字典与语料的 MD5 清单一致性 ----
#   deploy 时生成的 .rq3_manifest 记录了每个字典/语料的 MD5 → 防止上传过程被破坏
if [ -f /home/zxy/rq3_dict/.rq3_manifest ]; then
  while IFS=',' read -r f expect; do
    [ -z "$f" ] && continue
    got=$(md5sum "/home/zxy/rq3_dict/$f" 2>/dev/null | awk '{print $1}')
    if [ "$got" != "$expect" ]; then
      bad "H14 字典 MD5 不符: $f got=$got expect=$expect"
    fi
  done < /home/zxy/rq3_dict/.rq3_manifest
  ok "H14 字典 MD5 清单核对完成（$(wc -l < /home/zxy/rq3_dict/.rq3_manifest) 项）"
else
  info "H14 未找到 /home/zxy/rq3_dict/.rq3_manifest（跳过 MD5 清单核对）"
fi

# ---- H9-H12 ----
# ★ v3 修正（主理人发现的安全缺口）：H9/H10 原为「不阻塞的记录项」，
#   导致 RQ1.2 还在跑时预检仍输出「全部通过 → 允许启动 RQ3 容器」，
#   会让 RQ3 与 RQ1.2 抢 16 核 CPU + 磁盘 → 两侧数据都不可信。
#   现改为**硬阻断**：只要还有 rq2_ 容器在跑，就必须 FAIL 并禁止启动。
RQ2=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c '^rq2_' || true)
if [ "$RQ2" = "0" ]; then
  ok "H9/H10 无 rq2_ 容器在跑（不与 RQ1.2 抢资源）"
else
  bad "H9/H10 仍有 $RQ2 个 rq2_ 容器在跑 —— RQ1.2 未停，禁止启动 RQ3（须等 10-25 11:09 实验停止）"
fi

if [ -x "$ORACLE_DIR/testOnDemandRTSPServer" ]; then
  ok "H11 ASAN 服务器存在（干跑可用）"
else
  info "H11 ASAN 服务器不存在（仅影响干跑阶段）"
fi

if ss -tln 2>/dev/null | grep -qE ':(8560|857[0-9])\b'; then
  info "H12 端口 8560/857x 有监听 —— 启动前确认非本实验占用"
else
  ok "H12 端口 8560/857x 空闲"
fi

echo
echo "================ 预检结论 ================"
echo "PASS: $PASS    FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "!! 存在 FAIL 项 —— 禁止启动容器。失败清单:"
  cat "$FAILLOG"
  exit 3
fi
echo "全部通过 → 允许启动 RQ3 容器"
exit 0
