#!/bin/bash
# 精确定位：哪个命令触发 bftpd 退出，以及退出性质
set -u
WORK=/work
cd "$WORK"

test_one() {
  local label="$1" payload="$2"
  rm -f /tmp/asan_report.*
  ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:log_path=/tmp/asan_report \
    ./bftpd-asan -D -c basic.conf >/tmp/bf.log 2>&1 &
  local pid=$!
  sleep 2
  python3 - "$payload" <<'PYEOF'
import socket, time, sys
payload = sys.argv[1].encode()
try:
    s = socket.create_connection(("127.0.0.1", 21), timeout=3)
    s.sendall(payload)
    time.sleep(0.5)
    try:
        r = s.recv(4096)
        print("    recv:", r[:120])
    except OSError as e:
        print("    recv err:", e)
    try: s.close()
    except OSError: pass
except OSError as e:
    print("    连接失败:", e)
PYEOF
  sleep 1
  if kill -0 $pid 2>/dev/null; then
    echo "  [$label] bftpd 存活"; kill $pid 2>/dev/null
  else
    echo "  [$label] bftpd 退出"
  fi
  wait $pid 2>/dev/null
  local code=$?
  local asan=$(ls /tmp/asan_report.* 2>/dev/null | wc -l)
  echo "  [$label] exit=$code asan报告=$asan"
  if [ "$asan" -gt 0 ]; then
    head -30 /tmp/asan_report.* 2>/dev/null
  fi
  echo ""
}

echo "=== 逐个命令测试 ==="
test_one "仅 MLSD"        "MLSD\r\n"
test_one "仅 RMD"         "RMD\r\n"
test_one "仅 LIST"        "LIST\r\n"
test_one "MLSD+RMD+LIST"  "MLSD\r\nRMD\r\nLIST\r\n"
test_one "USER+PASS+RMD"  "USER ubuntu\r\nPASS ubuntu\r\nRMD\r\n"

echo "=== 连续多次 MLSD+RMD+LIST（同一实例，看第几次退出）==="
ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:log_path=/tmp/asan_report \
  ./bftpd-asan -D -c basic.conf >/tmp/bf.log 2>&1 &
pid=$!
sleep 2
python3 - <<'PYEOF'
import socket, time
for i in range(10):
    try:
        s = socket.create_connection(("127.0.0.1", 21), timeout=3)
        s.sendall(b"MLSD\r\nRMD\r\nLIST\r\n")
        time.sleep(0.3)
        try: s.recv(4096)
        except OSError: pass
        try: s.close()
        except OSError: pass
        print(f"  第{i+1}次: OK")
    except OSError as e:
        print(f"  第{i+1}次: 失败({e})")
        break
PYEOF
wait $pid 2>/dev/null
echo "exit=$?"
ls -la /tmp/asan_report.* 2>/dev/null && head -40 /tmp/asan_report.* 2>/dev/null
