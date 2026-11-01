# 数据流量库（SIP 抓包语料）

本目录是 rag-chatafl 的 SIP 协议流量知识库，用于 RAG 检索 + 模糊测试种子生成。
对标 `kb/rtsp/数据流量/README.md` 的 6 文件结构。

## 目录结构（按「抓包来源」分组）

```
数据流量/
├── public_aaa_0001/                    # Wireshark SampleCaptures - aaa.pcap
├── public_dtmfsipinfo_0001/            # Wireshark SampleCaptures - DTMFsipinfo.pcap
├── public_magicjack_short_call_0001/   # Wireshark SampleCaptures - MagicJack short call
├── public_asterisk_zfone_xlite_0001/   # Wireshark SampleCaptures - Asterisk+ZFONE+XLITE
└── manifest.csv
```

## 每个 run 目录的 7 个文件

| 文件 | 说明 |
|------|------|
| `capture.pcapng` | 原始公开 pcap（拷贝自 Wireshark SampleCaptures） |
| `clean.pcapng` | 清洗后（去掉 ARP/DNS/RST/重传） |
| `client.log` | SIP Method/Status 摘要（前 30 条） |
| `packets.ndjson` | 逐包结构化 dump（tshark -T ek 兼容 Elasticsearch） |
| `sip.csv` | SIP 控制消息字段抽取（frame.number / ip.src/dst / sip.Method / sip.Status-Line / sip.Request-Line） |
| `rtp.csv` | RTP 包字段抽取（frame.number / ip.src/dst / rtp.p_type / rtp.seq / rtp.timestamp） |
| `status.txt` | 捕获元信息（run_id, SIZE 等） |

## 数据来源

**降级方案**：本地 Kamailio ASAN 镜像启动后 UDP 只 UNCONN 不响应（启动到 `probe_max_receive_buffer` 后无更多日志，子进程未起来），无法抓真实 SIP 流量；改用 Wireshark SampleCaptures 公开数据集。

| run_id | 来源 |
|----|------|
| public_aaa_0001 | <https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/aaa.pcap> — 通用 SIP/RTP 示例 |
| public_dtmfsipinfo_0001 | <https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/DTMFsipinfo.pcap> — SIP INFO DTMF |
| public_magicjack_short_call_0001 | <https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/MagicJack-_short_call.pcap> — 完整 SIP 电话 |
| public_asterisk_zfone_xlite_0001 | <https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/Asterisk_ZFONE_XLITE.pcap> — ZRTP 媒体保护 |

## 补充说明

- 转换脚本：`local/_vm_convert_public_sip.sh`（拷贝 pcap → tshark 拆解为 6 文件）。
- 后续待补：本地 Kamailio 二进制（`/home/zxy/target programs/kamailio/` 或自己编译非 ASAN 版）+ pjsip client 模拟完整 INVITE/REGISTER 会话，替换公开数据。