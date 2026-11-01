#!/bin/bash
# FTP 客户端：用 python 内置 ftplib 做完整匿名会话（LIST/RETR/QUIT）。
# 用法: /tmp/ftp_client.sh <run_id>
set -uo pipefail
RUN_ID=${1:?"run_id required"}

LOG=/tmp/captures/$RUN_ID/client.log
mkdir -p /tmp/captures/$RUN_ID

python3 - <<PYEOF > "$LOG"
import ftplib, socket, sys, time
run_id = "$RUN_ID"

class TraceFTP(ftplib.FTP):
    """ftplib 子类：记录 client/server 对话"""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._log = []
    def _logline(self, tag, line):
        self._log.append(f"{tag}> {line}")
    def sendcmd(self, cmd):
        self._logline('C', cmd)
        resp = super().sendcmd(cmd)
        self._logline('S', resp)
        return resp
    def voidcmd(self, cmd):
        self._logline('C', cmd)
        resp = super().voidcmd(cmd)
        self._logline('S', resp)
        return resp
    def getline(self):
        line = super().getline()
        # 截前 200 字符
        self._log.append(f"[RAW S] {line.rstrip()[:200]}")
        return line
    def connect(self, host='127.0.0.1', port=21, timeout=10):
        super().connect(host, port, timeout)

with open("$LOG", "w") as f:
    print(f"=== FTP 会话：{run_id} ===", file=f)
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", file=f)
    print(f"客户端: python ftplib", file=f)
    print("", file=f)
    print("--- 开始对话 ---", file=f)
    ftp = TraceFTP()
    try:
        ftp.connect('127.0.0.1', 21, timeout=10)
        # 不需要自动欢迎（connect 后 getwelcome 已读）
        for line in ftp.welcome.split('\n'):
            ftp._logline('S', line)
        try:
            ftp.login('anonymous', 'anonymous@example.com')
        except Exception as e:
            ftp._log.append(f"[login err] {e}")
        try:
            ftp.sendcmd('PWD')
        except Exception as e:
            ftp._log.append(f"[PWD err] {e}")
        try:
            ftp.sendcmd('TYPE A')
        except Exception as e:
            ftp._log.append(f"[TYPE err] {e}")
        try:
            ftp.sendcmd('NOOP')
        except Exception as e:
            ftp._log.append(f"[NOOP err] {e}")
        try:
            # 尝试列出（FTPS 不支持匿名列表时退出码 530）
            ftp.retrlines('LIST')
        except ftplib.error_perm as e:
            ftp._log.append(f"[LIST err] {e}")
        except Exception as e:
            ftp._log.append(f"[LIST err] {e}")
        try:
            ftp.sendcmd('QUIT')
        except Exception as e:
            ftp._log.append(f"[QUIT err] {e}")
        ftp.close()
    except Exception as e:
        ftp._log.append(f"[top err] {e}")
    for line in ftp._log:
        print(line, file=f)
    print("", file=f)
    print("--- 客户端结束 ---", file=f)
PYEOF
echo "client log: $LOG ($(wc -l < $LOG) 行)"