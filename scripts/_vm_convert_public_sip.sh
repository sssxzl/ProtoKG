#!/bin/bash
# 把公开 pcap 转成 ProtoKG 数据流量 6 文件结构。
# 用法: /tmp/convert_public_sip.sh <src.pcap> <run_id>
#   例: /tmp/convert_public_sip.sh /tmp/sip_public/aaa.pcap public_aaa_0001

set -uo pipefail
SRC=${1:?"src required"}
RUN_ID=${2:?"run_id required"}

WORK=/tmp/captures
RDIR="$WORK/$RUN_ID"
mkdir -p "$RDIR"

# 1) capture = src 原文件
cp "$SRC" "$RDIR/capture.pcapng"

# 2) clean = 过滤掉 ARP/DNS/RST/重传
tshark -r "$RDIR/capture.pcapng" -Y "not (arp or dns or tcp.analysis.flags or tcp.analysis.retransmission or tcp.analysis.fast_retransmission)" -w "$RDIR/clean.pcapng" 2>/dev/null || cp "$RDIR/capture.pcapng" "$RDIR/clean.pcapng"

# 3) packets.ndjson: tshark -T ek
tshark -r "$RDIR/clean.pcapng" -T ek > "$RDIR/packets.ndjson" 2>/dev/null

# 4) sip.csv
tshark -r "$RDIR/clean.pcapng" -T fields \
  -e frame.number -e ip.src -e ip.dst \
  -e sip.Method -e sip.Status-Line -e sip.Request-Line \
  -E separator=, > "$RDIR/sip.csv" 2>/dev/null

# 5) rtp.csv (可能为空)
tshark -r "$RDIR/clean.pcapng" -T fields \
  -e frame.number -e ip.src -e ip.dst \
  -e rtp.p_type -e rtp.seq -e rtp.timestamp \
  -E separator=, > "$RDIR/rtp.csv" 2>/dev/null

# 6) client.log: 从公开 pcap 里抽出 SIP 对话文本
{
  echo "=== 公开 SIP 抓包：$RUN_ID ==="
  echo "源文件: $(basename $SRC)"
  echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "客户端: Wireshark SampleCaptures (公开抓包)"
  echo ""
  echo "--- SIP Method/Status 摘要（前 30 条）---"
  tshark -r "$RDIR/clean.pcapng" -Y "sip" -T fields \
    -e frame.number -e ip.src -e ip.dst \
    -e sip.Method -e sip.Status-Line -e sip.Request-Line \
    -E separator=' | ' 2>/dev/null | head -30
} > "$RDIR/client.log"

# 7) status.txt（保持与现有一致）
PCAP_SIZE=$(stat -c%s "$SRC")
{
  echo "RUN_ID=$RUN_ID CID=NONE TCPDUMP_PID=0 WORK=$RDIR PORT=0"
  echo "SRC=$SRC SIZE=$PCAP_SIZE"
} > "$RDIR/status.txt"

echo "完成：$RDIR"
ls -la "$RDIR/"