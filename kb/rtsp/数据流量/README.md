# 数据流量库（RTSP 抓包语料）

本目录是 rag-chatafl 的 RTSP 协议流量知识库，用于 RAG 检索 + 模糊测试种子生成。

## 目录结构（按「流 / 服务器实现」分组）

```
数据流量/
├── mp3AudioTest/          # live555 testOnDemandRTSPServer，UDP 传输，500 条
│   ├── mp3AudioTest_0001/   # 每条含 6 个文件（见下）
│   └── ... 至 mp3AudioTest_0500
├── somasexy_Jasmine/      # Darwin Streaming Server 6.0.3，TCP 交错传输，1 条
│   └── somasexy_Jasmine_0001/
├── hikvision_ch101/       # 海康威视摄像头，H.265 + Digest 认证，UDP 传输，1 条
│   └── hikvision_ch101_0001/
├── _duplicates_tcp/       # ⚠️ 归档的重复数据（500 条，详见下方说明）
├── manifest.csv           # 全库索引（run_id, transport, stream, url, duration, pcap, ...）
└── manifest.csv.bak       # 整理前的 manifest 备份（可回滚）
```

## 每个 run 目录的 6 个文件

| 文件 | 说明 |
|------|------|
| `capture.pcapng` | 原始抓包 |
| `clean.pcapng` | 清洗后的抓包 |
| `client.log` | RTSP 会话文字记录（等价 openRTSP 日志） |
| `packets.ndjson` | 逐包结构化 dump（tshark -T ek 兼容结构） |
| `rtsp.csv` | RTSP 控制消息字段抽取 |
| `rtp.csv` | RTP 包字段抽取 |

## ⚠️ 关于 _duplicates_tcp/（500 条归档数据）

这 500 条（原 `tcp_0001~0500`）经字节级比对，与 `udp_0001~0500` 存在 **5/6 文件完全重复**：

- capture.pcapng / clean.pcapng / packets.ndjson / rtsp.csv / rtp.csv —— 100% 相同
- 仅 client.log 不同（记录了 `Transport: RTP/AVP/TCP;interleaved=0-1` 的协商尝试）

**根因**：采集时 TCP 交错（interleaved）模式未生效，实际抓到的仍是 UDP 流量，导致 tcp 目录与 udp 目录重复、且 `transport` 标签失实。

处理方式：**归档（非删除）** 到 `_duplicates_tcp/`，manifest 已移除这 500 条。如需回滚，把目录移回并恢复 `manifest.csv.bak` 即可。

## 数据来源

| 流 | 服务器实现 | 传输 | 来源 |
|----|-----------|------|------|
| mp3AudioTest | live555 | UDP | 本地 testOnDemandRTSPServer 采集 |
| somasexy_Jasmine | DSS 6.0.3 | TCP 交错 | 公开抓包（CorePlayer 客户端） |
| hikvision_ch101 | 海康威视 | UDP | Wireshark SampleCaptures |

## 补充说明

- `manifest.csv` 的 `pcap` 列沿用原采集机路径占位 `/home/zxy/数据流量/<流>/<run_id>/capture.pcapng`（实际文件在 Windows 本机）。
- 生成/转换工具见工作区：`rtsp_capture_to_kb.py`（pcap→统一格式）、`generate_rtsp_captures/`（本地生成更多实现抓包）。
