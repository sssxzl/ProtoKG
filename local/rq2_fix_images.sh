#!/bin/bash
# RQ2 6目标镜像 chatafl 修复：黄金标准覆盖，统一 DeepSeek 后端
# 黄金标准 = rq2-live555 已验证的 chat-llm.h/.c
#   (token 完整 + URL 走代理 192.168.37.1:18080 + model=deepseek-chat + JSON 转义 + enrich 改 turbo)
# 用法: bash rq2_fix_images.sh
set -e
FIX=/home/zxy/rq2_chatafl_fix
GOLD_H="$FIX/chat-llm.h"
GOLD_C="$FIX/chat-llm.c"

fix_img() {
  local src=$1 out=$2
  echo "===== [$src] -> [$out] ====="
  local cid
  cid=$(docker run -d --entrypoint sh "$src:latest" -c 'sleep 900')
  echo "  容器 $cid 启动"
  docker cp "$GOLD_H" "$cid:/home/ubuntu/chatafl/chat-llm.h"
  docker cp "$GOLD_C" "$cid:/home/ubuntu/chatafl/chat-llm.c"
  echo "  重编译 afl-fuzz ..."
  docker exec "$cid" sh -c 'cd /home/ubuntu/chatafl && make afl-fuzz > /tmp/make.log 2>&1; rc=$?; tail -6 /tmp/make.log; exit $rc'
  echo "  验证修复点 (token=1, 代理URL>=2, 旧值=0) ..."
  # ★ 安全整改（2026-11-01）：这里检查的是「容器内是否还残留旧的 DeepSeek token」，
  #   用**形态正则**（sk- + 32 位十六进制）即可判定，不需要硬编码完整密钥。
  #   原写法把真实 key 写进脚本，会随版本库分发。
  docker exec "$cid" sh -c 'echo -n "token: "; grep -cE "sk-[0-9a-fA-F]{32}" /home/ubuntu/chatafl/chat-llm.h; echo -n "proxy_url: "; grep -c "192.168.37.1:18080" /home/ubuntu/chatafl/chat-llm.c; echo -n "old_deepseek: "; grep -c "api.deepseek.com\|deepseek-v4-flash\|minimaxi\|MiniMax" /home/ubuntu/chatafl/chat-llm.c; true'
  docker commit "$cid" "$out:latest"
  docker rm -f "$cid"
  echo "  [OK] $out 完成"
  echo
}

fix_img bftpd      rq2-bftpd
fix_img proftpd    rq2-proftpd
fix_img pureftpd   rq2-pureftpd
fix_img pure-ftpd  rq2-pure-ftpd
fix_img exim       rq2-exim
fix_img kamailio   rq2-kamailio

echo "===== 全部镜像修复完成 ====="
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep '^rq2-'
