#!/bin/bash
# version: 2026-10-24-v2
# ↑ 版本标记：编排前用 `grep '^# version:'` 校验 VM 副本与本地一致（防版本漂移）
# ★ RQ3 冒烟测试（VM 侧）—— 1 容器 × 短时，验证 S-3/S-4/S-6 等关键项
#
# 用法：bash rq3_smoke_test.sh [组] [秒数]
#   默认：C 组 150 s
#
# ★ 冒烟用独立名字（rq3_smoke_*）与独立目录（/home/zxy/rq3_out/smoke_*），
#   **绝不触碰** RQ1.2 的 rq2_* 容器与 /home/zxy/rq2_out、/home/zxy/rq2_seeds。
set -uo pipefail

IMG=rq2-live555:latest
GROUP=${1:-C}
DUR=${2:-150}
NAME="rq3_smoke_${GROUP}_chatafl_r1"
SEEDS="/home/zxy/rq3_seeds/$GROUP/seeds"
DICT_ROOT=/home/zxy/rq3_dict
OUT="/home/zxy/rq3_out/smoke_${GROUP}_chatafl/r1"

# 按组选字典
case "$GROUP" in
  C) DICT_FILE=c_targeted.dict; DICT_TOKENS=123 ;;
  *) DICT_FILE=rtsp_base.dict;  DICT_TOKENS=24  ;;
esac

echo "=== RQ3 冒烟测试：组=$GROUP 字典=$DICT_FILE（$DICT_TOKENS token）时长=${DUR}s ==="

rm -rf "$OUT"; mkdir -p "$OUT"
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" --user root --cpus=1 --memory=1.5g --network none \
  -v "$SEEDS:/seeds_ro:ro" -v "$OUT:/out" -v "$DICT_ROOT:/dict_rw:ro" \
  "$IMG" bash -c "
    cp -r /seeds_ro /seeds_work &&
    cd /home/ubuntu/experiments/live/testProgs &&
    timeout -k 2s $DUR /home/ubuntu/chatafl/afl-fuzz \
      -d -i /seeds_work -x /dict_rw/$DICT_FILE -o /out \
      -N tcp://127.0.0.1/8560 -P RTSP -D 10000 -q 3 -s 3 \
      -E -K -R -m none -t 1000 -- ./testOnDemandRTSPServer 8560" >/dev/null

echo "[冒烟] 容器 $NAME 已启动，跑 ${DUR}s ..."
# ★ 等待时间：容器启动 + fuzzer 进入校准/变异阶段需要时间。
#   VM 上 RQ1.2 的 20 个容器满载（load avg ≈ 12）→ 新容器起跑很慢，
#   故等待窗口取「DUR 的 2/3」且不少于 60 s。
WAIT_S=$((DUR * 2 / 3))
[ "$WAIT_S" -lt 60 ] && WAIT_S=60
sleep "$WAIT_S"

echo
echo "--- S-3 字典挂载正确性 ---"
echo -n "  容器内字典 MD5:   "; docker exec "$NAME" md5sum "/dict_rw/$DICT_FILE" 2>/dev/null | cut -d" " -f1
echo -n "  容器内字典 token:  "; docker exec "$NAME" bash -c "grep -c . /dict_rw/$DICT_FILE" 2>/dev/null
echo -n "  宿主字典 MD5:      "; md5sum "$DICT_ROOT/$DICT_FILE" | cut -d" " -f1

echo
echo "--- S-4 ★ ChatAFL 增强关闭 ---"
SEEDS_RAW=$(docker exec "$NAME" bash -c 'ls /seeds_work/*.raw 2>/dev/null | wc -l' 2>/dev/null)
ENR_SEEDS=$(docker exec "$NAME" bash -c 'ls /seeds_work 2>/dev/null | grep -c "^enriched_" || true' 2>/dev/null)
ENR_QUEUE=$(docker exec "$NAME" bash -c 'ls /out/queue 2>/dev/null | grep -c "orig:enriched" || true' 2>/dev/null)
QUEUE_N=$(docker exec "$NAME" bash -c 'ls /out/queue 2>/dev/null | wc -l' 2>/dev/null)
# ★ plot_data 用 ", " 分隔 → 切出的字段带前导空格，必须 strip 后再比较
CHAT=$(docker exec "$NAME" bash -c 'grep -v "^#" /out/plot_data 2>/dev/null | tail -1 | cut -d, -f14' 2>/dev/null | tr -d ' ')
EXECS=$(docker exec "$NAME" bash -c 'grep "^execs_done" /out/fuzzer_stats 2>/dev/null | awk "{print \$3}"' 2>/dev/null | tr -d ' ')
CVG=$(docker exec "$NAME" bash -c 'grep "^bitmap_cvg" /out/fuzzer_stats 2>/dev/null | awk "{print \$3}"' 2>/dev/null | tr -d ' ')
# ★ v2 V11 污染探针：队列中 ",orig:" 形式条目数必须 == 语料条数
INIT_Q=$(docker exec "$NAME" bash -c 'ls /out/queue 2>/dev/null | grep -c ",orig:" || true' 2>/dev/null)
EXPECT_SEEDS=$(ls "$SEEDS"/*.raw 2>/dev/null | wc -l)
echo "  seeds_work .raw 数:   $SEEDS_RAW（期望 = 语料条数）"
echo "  seeds_work enriched_*: $ENR_SEEDS（期望 0）"
echo "  queue orig:enriched*:  $ENR_QUEUE（期望 0）"
echo "  queue 条目数:          $QUEUE_N"
echo "  ★ V11 初始队列条目数:  $INIT_Q（期望 = 语料条数 $EXPECT_SEEDS）"
echo "  chat_times 末值:       $CHAT（期望 0 → runtime stall-chat 也已关闭）"
echo "  execs_done:            $EXECS"
echo "  bitmap_cvg:            $CVG"

echo
echo "--- 判定 ---"
FAIL=0
[ "$ENR_SEEDS" = "0" ] || { echo "  FAIL: seeds_work 出现增强种子"; FAIL=1; }
[ "$ENR_QUEUE" = "0" ] || { echo "  FAIL: queue 出现 orig:enriched*"; FAIL=1; }
[ "$CHAT" = "0" ] || { echo "  FAIL: chat_times ≠ 0"; FAIL=1; }
[ "${EXECS:-0}" -gt 0 ] 2>/dev/null || { echo "  FAIL: execs_done 未增长（fuzzing 未运行）"; FAIL=1; }
# ★ V11 污染探针（比 grep orig:enriched 更强：连「污染后恰好叫原名」也能抓到）
[ "$INIT_Q" = "$EXPECT_SEEDS" ] || { echo "  FAIL: V11 初始队列条目数 $INIT_Q != 语料条数 $EXPECT_SEEDS（初始队列被污染）"; FAIL=1; }
if [ "$FAIL" = "0" ]; then
  echo "  ✓ S-3 / S-4 / V11 全部通过"
else
  echo "  ✗ 冒烟失败"
fi

echo
echo "--- 清理 ---"
# ★ 容器以 root 运行 → /out 下文件属 root，宿主普通用户 rm 会 Permission denied。
#   先在容器内删（此时容器还在），再删容器。
docker exec "$NAME" bash -c 'rm -rf /out/* 2>/dev/null' >/dev/null 2>&1 || true
docker rm -f "$NAME" >/dev/null 2>&1 || true
rm -rf "$OUT" 2>/dev/null || true
rm -f /tmp/rq3_smoke.sh
echo "  容器与输出目录已清理"
exit $FAIL
