#!/bin/bash
# lightftp: 补 chatafl 运行时依赖 + 从 rq2-bftpd 复制 chatafl 目录 -> rq2-lightftp:latest
# 前置: rq2-bftpd:latest 已存在（主脚本先修好）
set -e
SRC_IMG=rq2-bftpd:latest
OUT_IMG=rq2-lightftp:latest

echo "===== lightftp: 启动容器(root) ====="
cid=$(docker run -d --user root --entrypoint sh lightftp:latest -c 'sleep 1200')
echo "  容器 $cid"

echo "===== apt 安装 libcurl4 libjson-c4 ====="
docker exec "$cid" bash -c 'apt-get update >/dev/null 2>&1 && apt-get install -y libcurl4 libjson-c4 2>&1 | tail -4'

echo "===== 从 $SRC_IMG 提取 chatafl 目录 ====="
src=$(docker run -d --entrypoint sh "$SRC_IMG" -c 'sleep 600')
docker cp "$src:/home/ubuntu/chatafl" /tmp/chatafl_copy
docker rm -f "$src"

echo "===== 复制 chatafl 到 lightftp ====="
docker cp /tmp/chatafl_copy "$cid:/home/ubuntu/chatafl"

echo "===== 验证 afl-fuzz 可运行 ====="
docker exec "$cid" sh -c 'ldd /home/ubuntu/chatafl/afl-fuzz 2>&1 | grep -E "not found" || echo "ldd: 所有依赖已满足"; /home/ubuntu/chatafl/afl-fuzz -h 2>&1 | head -3'

echo "===== commit -> $OUT_IMG ====="
docker commit "$cid" "$OUT_IMG"
docker rm -f "$cid"
rm -rf /tmp/chatafl_copy

echo "===== lightftp 完成 ====="
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep '^rq2-'
