#!/bin/bash
# 把黄金标准(含 curl 超时 + stall 转义修复)重新应用到 8 个 rq2 镜像 + 重编译 + commit(覆盖 tag)
set -e
FIX=/home/zxy/rq2_chatafl_fix
GOLD_H="$FIX/chat-llm.h"
GOLD_C="$FIX/chat-llm.c"

fix_img() {
  local img=$1
  echo "===== [$img] 应用 curl超时+stall转义修复 ====="
  local cid
  cid=$(docker run -d --entrypoint sh "$img:latest" -c 'sleep 900')
  docker cp "$GOLD_H" "$cid:/home/ubuntu/chatafl/chat-llm.h"
  docker cp "$GOLD_C" "$cid:/home/ubuntu/chatafl/chat-llm.c"
  docker exec "$cid" sh -c 'cd /home/ubuntu/chatafl && make afl-fuzz > /tmp/make.log 2>&1; rc=$?; tail -3 /tmp/make.log; exit $rc'
  docker exec "$cid" sh -c 'echo -n "  timeout: "; grep -c "CURLOPT_TIMEOUT" /home/ubuntu/chatafl/chat-llm.c; echo -n "  stall转义: "; grep -c "prompt_escaped" /home/ubuntu/chatafl/chat-llm.c; true'
  docker commit "$cid" "$img:latest"
  docker rm -f "$cid"
  echo "  [OK] $img"
  echo
}

for img in rq2-bftpd rq2-proftpd rq2-pureftpd rq2-pure-ftpd rq2-exim rq2-kamailio rq2-lightftp rq2-live555; do
  fix_img "$img"
done
echo "===== 全部镜像修复完成 ====="
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep '^rq2-'
