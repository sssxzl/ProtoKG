#!/bin/bash
# BFTPD 6.1 ASAN 崩溃定性：编译 -O1 ASAN 版 + gdb 启动崩溃点 + 重放 MLSD/RMD/LIST
set -u
WORK=/work

echo "=== 1. 编译 -O1 ASAN bftpd ==="
cd /home/ubuntu/experiments/bftpd
make clean >/dev/null 2>&1
sed -i 's/^CFLAGS=/CFLAGS=-fsanitize=address /' Makefile
sed -i 's/ -O2 / -O1 /' Makefile
sed -i 's/^LDFLAGS=/LDFLAGS=-fsanitize=address /' Makefile
grep -E '^(CFLAGS|LDFLAGS)=' Makefile
make 2>&1 | tail -3
cp bftpd "$WORK/bftpd-asan" && echo "编译 OK: $(ls -la $WORK/bftpd-asan | awk '{print $5}') 字节"
echo "验证 ASAN 链接: $(ldd $WORK/bftpd-asan | grep -c asan) 处 asan"

echo ""
echo "=== 2. ASAN bftpd 多次重放（每次独立连接，看是否概率性崩溃）==="
cd "$WORK"
rm -f /tmp/asan_report.*
ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:log_path=/tmp/asan_report \
  ./bftpd-asan -D -c basic.conf >/tmp/bf.log 2>&1 &
BFPID=$!
sleep 3
python3 - <<'PYEOF'
import socket, time
crashes = 0
for i in range(15):
    try:
        s = socket.create_connection(("127.0.0.1", 21), timeout=3)
        s.sendall(b"MLSD\r\nRMD\r\nLIST\r\n")
        time.sleep(0.3)
        try:
            r = s.recv(4096)
            # 连接被服务器关闭 = 可能崩溃
        except (OSError, ConnectionResetError):
            crashes += 1
        try: s.close()
        except OSError: pass
    except OSError as e:
        crashes += 1
        print(f"  第{i+1}次: 连接失败({e})")
        break
print(f"  完成 {i+1} 次重放, 连接异常 {crashes} 次")
PYEOF
sleep 2
if kill -0 $BFPID 2>/dev/null; then
  echo "主进程存活（多次重放后）"; kill $BFPID 2>/dev/null
else
  echo "主进程已退出（多次重放后）"
fi
wait $BFPID 2>/dev/null
echo "exit code: $?"

echo ""
echo "=== 3. ASAN 报告 ==="
ls -la /tmp/asan_report.* 2>/dev/null || echo "  无 ASAN 报告文件"
echo "--- 报告内容（前 60 行）---"
head -60 /tmp/asan_report.* 2>/dev/null
echo ""
echo "=== bf.log（前 30 行）==="
head -30 /tmp/bf.log 2>/dev/null
