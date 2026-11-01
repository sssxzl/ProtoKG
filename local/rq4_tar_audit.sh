#!/bin/bash
# rq4_tar_audit.sh —— RQ4 终态产物的**独立可复现性核验**（只读）
#
# 目的
# ----
# 容器已被删除（`docker rm`），无法再 `docker cp` / `docker exec` 回查容器内原始文件。
# 本脚本从**官方 tar.gz** 里解出关键产物，与宿主 `/home/zxy/rq4/out/` 下的**明文副本**
# 做逐字节比对 —— 这是「数据未被篡改」的最终证据。
#
# 严格只读：只解包到 /tmp，不写 out/，不碰容器，不删任何东西。
set -uo pipefail

OUT_ROOT=/home/zxy/rq4/out
SUMMARY=/home/zxy/rq4/rq4_summary.csv
WORK=$(mktemp -d /tmp/rq4_tar_audit_XXXXXX)
trap 'rm -rf "$WORK"' EXIT

echo "=== RQ4 tar 独立核验（只读）==="
echo "tar 源 : $OUT_ROOT/<proto>/<group>/r1/out.tar.gz"
echo "对账基准: $OUT_ROOT/<proto>/<group>/r1/{fuzzer_stats,cov_over_time.csv}"
echo "summary : $SUMMARY"
echo

printf '%-16s %-12s %-12s %-12s %-12s %s\n' \
     "组" "fs(tar)" "fs(host)" "cov(tar)" "cov(host)" "判定"
printf '%s\n' "--------------------------------------------------------------------------------"

all_ok=1
for proto in rtsp sip smtp; do
  for group in protorag baseline; do
    d="$OUT_ROOT/$proto/$group/r1"
    tar_path="$d/out.tar.gz"
    sub="out-$proto-$group-r1"

    if [[ ! -f "$tar_path" ]]; then
      printf '%-16s %s\n' "$proto/$group" "★缺 tar.gz"
      all_ok=0
      continue
    fi

    rm -rf "$WORK/x"; mkdir -p "$WORK/x"
    if ! gzip -dc "$tar_path" | tar -xf - -C "$WORK/x" \
          "$sub/fuzzer_stats" "$sub/cov_over_time.csv" 2>/dev/null; then
      printf '%-16s %s\n' "$proto/$group" "★解包失败"
      all_ok=0
      continue
    fi

    fs_tar=$(md5sum "$WORK/x/$sub/fuzzer_stats"        2>/dev/null | cut -d' ' -f1)
    fs_host=$(md5sum "$d/fuzzer_stats"                  2>/dev/null | cut -d' ' -f1)
    cv_tar=$(md5sum "$WORK/x/$sub/cov_over_time.csv"    2>/dev/null | cut -d' ' -f1)
    cv_host=$(md5sum "$d/cov_over_time.csv"             2>/dev/null | cut -d' ' -f1)

    verdict="OK"
    [[ -z "$fs_tar" || -z "$fs_host" ]] && { verdict="★缺文件"; all_ok=0; }
    if [[ -n "$fs_tar" && -n "$fs_host" && "$fs_tar" != "$fs_host" ]]; then
      verdict="★fuzzer_stats 不一致"; all_ok=0
    fi
    if [[ -n "$cv_tar" && -n "$cv_host" && "$cv_tar" != "$cv_host" ]]; then
      verdict="${verdict/OK/}★cov_over_time 不一致"; all_ok=0
    fi
    [[ -n "$cv_tar" && -n "$cv_host" && "$cv_tar" == "$cv_host" && \
       -n "$fs_tar" && -n "$fs_host" && "$fs_tar" == "$fs_host" ]] && verdict="逐字节一致 ✓"

    printf '%-16s %-12s %-12s %-12s %-12s %s\n' \
      "$proto/$group" "${fs_tar:0:10}" "${fs_host:0:10}" \
      "${cv_tar:0:10}" "${cv_host:0:10}" "$verdict"
  done
done

echo
echo "=== command_line 逐字比对（tar 内 fuzzer_stats  vs  summary 第 23 列）==="
if [[ ! -f "$SUMMARY" ]]; then
  echo "★找不到 summary: $SUMMARY"
  all_ok=0
else
  # summary 表头定位 command_line 所在列号（不硬编码列号）
  hdr=$(head -1 "$SUMMARY" | tr -d '\r')
  cmd_col=$(echo "$hdr" | awk -F',' '{for(i=1;i<=NF;i++) if($i=="command_line"){print i; exit}}')
  if [[ -z "$cmd_col" ]]; then
    echo "★summary 里找不到 command_line 列"
    all_ok=0
  else
    echo "command_line 列号 = $cmd_col"
    printf '%-16s %-10s %s\n' "组" "判定" "逐字比对"
    for proto in rtsp sip smtp; do
      for group in protorag baseline; do
        d="$OUT_ROOT/$proto/$group/r1"
        sub="out-$proto-$group-r1"
        rm -rf "$WORK/y"; mkdir -p "$WORK/y"
        gzip -dc "$d/out.tar.gz" | tar -xf - -C "$WORK/y" "$sub/fuzzer_stats" 2>/dev/null
        tar_cmd=$(grep -E '^command_line' "$WORK/y/$sub/fuzzer_stats" 2>/dev/null \
                  | head -1 | sed -E 's/^command_line[[:space:]]*:[[:space:]]*//' | tr -d '\r')
        # summary 是 CSV，字段值带引号 → 必须剥掉外层引号才能逐字比
        sum_cmd=$(awk -F',' -v c="$cmd_col" -v k="$proto" -v g="$group" \
                    'NR>1 && $1==k && $2==g {print $c; exit}' "$SUMMARY" \
                  | tr -d '\r' | sed -E 's/^"(.*)"$/\1/')
        if [[ -z "$tar_cmd" ]]; then
          printf '%-16s %-10s %s\n' "$proto/$group" "★tar 无" "(tar 内无 command_line)"
          all_ok=0
        elif [[ -z "$sum_cmd" ]]; then
          printf '%-16s %-10s %s\n' "$proto/$group" "★summary 无" "(summary 无该行)"
          all_ok=0
        elif [[ "$tar_cmd" == "$sum_cmd" ]]; then
          printf '%-16s %-10s %s\n' "$proto/$group" "一致 ✓" "$tar_cmd"
        else
          printf '%-16s %-10s %s\n' "$proto/$group" "★不一致" ""
          echo "    tar    : $tar_cmd"
          echo "    summary: $sum_cmd"
          all_ok=0
        fi
      done
    done
  fi
fi

echo
if [[ "$all_ok" == "1" ]]; then
  echo "总判定: 全部一致 ✓ —— 宿主明文副本与官方 tar 内原始产物逐字节相同，数据未被篡改。"
else
  echo "总判定: 存在不一致或缺失 ★ —— 见上表。"
fi
exit $((1 - all_ok))
