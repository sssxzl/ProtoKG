#!/bin/bash
# 在容器内验证断言 A / B2 的内层探测逻辑（用构造的 enriched_* 样例）
set -u
mkdir -p /seeds_work
rm -f /seeds_work/enriched_*

# 样例1：合法 RTSP（CRLF，首行是合法请求行，无散文）
printf 'DESCRIBE rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n' > /seeds_work/enriched_good

# 样例2：散文首行（污染）
printf 'Here is the modified sequence of client requests:\n\nDESCRIBE rtsp://127.0.0.1:8554/x RTSP/1.0\n' > /seeds_work/enriched_bad1

# 样例3：代码围栏（含反引号）
BT=$(printf '\140')
printf '%s%s%s\n' "${BT}${BT}${BT}" 'DESCRIBE rtsp://127.0.0.1:8554/y RTSP/1.0' "${BT}${BT}${BT}" > /seeds_work/enriched_bad2

RE="^(OPTIONS|DESCRIBE|SETUP|PLAY|PAUSE|TEARDOWN|GET_PARAMETER|SET_PARAMETER|ANNOUNCE|RECORD|REDIRECT)[[:space:]]+[^[:space:]]+[[:space:]]+RTSP/1\.0"

echo "=== 断言 A 内层：首行正则校验（期望：good=OK，bad1/bad2=BAD）==="
for f in /seeds_work/enriched_*; do
  [ -e "$f" ] || continue
  if ! head -n 1 "$f" | grep -Eq "$RE"; then
    echo "  BAD首行: $f"
  else
    echo "  OK首行: $f"
  fi
done

echo "=== 断言 B2 内层：首行+散文/围栏探测（期望：good=0，bad1=2，bad2=2）==="
BT=$(printf "\140")
for f in /seeds_work/enriched_*; do
  [ -e "$f" ] || continue
  bad=0
  head -n 1 "$f" | grep -Eq "$RE" || bad=$((bad+1))
  if grep -Eiq "here is|note:|explanation|sure|below" "$f" || grep -Fq "$BT" "$f"; then bad=$((bad+1)); fi
  echo "  $f -> bad=$bad"
done
