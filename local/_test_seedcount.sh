#!/bin/bash
# 复现 QA 场景：50 原始 .raw + 246 enriched_*.raw，验证 seed_count 过滤返回 50 而非 296
set -u
mkdir -p /seeds_work
rm -f /seeds_work/*.raw

for i in $(seq 1 50); do
  touch /seeds_work/$(printf '%02d' "$i")_orig.raw
done
for i in $(seq 1 246); do
  touch /seeds_work/enriched_${i}_foo.raw
done

echo "total .raw 计数（旧算法，应为 296）:"
ls /seeds_work | grep -c '\.raw$'
echo "排除 enriched 后计数（新算法，应为 50）:"
ls /seeds_work | grep -v '^enriched_' | grep -c '\.raw$'
echo "enriched 计数（应为 246）:"
ls /seeds_work | grep -c '^enriched_'
