# 数据流量库（SMTP 抓包语料）

本目录是 ProtoKG 的 SMTP 协议流量知识库，用于 RAG 检索 + 模糊测试种子生成。

## 目录结构（按「会话 / 服务器实现」分组）

```
数据流量/
├── smtp_exim_0001/         # Exim 4.69，端口 25，AUTH LOGIN + MIME 邮件
├── smtp_submission_0001/   # SMTP Submission（587），AUTH LOGIN + MIME patch 附件
├── smtp_tnef_0001/         # SMTP Submission（587），AUTH LOGIN + TNEF(winmail.dat) 附件
├── smtp_plaintext_0001/    # Postfix domex，明文邮件（Thunderbird 发信）
├── smtp_plaintext_0002/    # Postfix domex，明文邮件
├── smtp_plaintext_0003/    # Postfix domex，明文邮件
├── _raw_downloads/         # 原始 .pcap/.pcap.gz 下载归档（含 faf-exercise 全量）
└── manifest.csv            # 全库索引
```

## 每个 run 目录的 5 个文件

| 文件 | 说明 |
|------|------|
| `capture.pcapng` | 原始抓包（转为 pcapng） |
| `clean.pcapng` | 清洗后抓包（去掉纯 ACK / 空 payload 的控制包） |
| `client.log` | SMTP 会话文字记录（按时间交错、TCP 流重组去重 + 行级乱码过滤） |
| `packets.ndjson` | 逐包结构化 dump（frame/ip/tcp/smtp 关键字段） |
| `smtp.csv` | SMTP 命令/响应字段抽取（frame.number, smtp.command, smtp.response_code, smtp.mail_from, smtp.rcpt_to） |

> 说明：SMTP 为纯文本 TCP 协议，无 RTP/RTCP 媒体层，故每个 run 为 5 个文件（对照 RTSP 库去掉 `rtp.csv`）。

## 数据来源

| 会话 | 服务器实现 | 端口 | 传输 | 来源 |
|------|-----------|------|------|------|
| smtp_exim_0001 | Exim 4.69 | 25 | TCP | Wireshark SampleCaptures `smtp.pcap` |
| smtp_submission_0001 | SMTP Submission | 587 | TCP | Wireshark SampleCaptures `sample-imf.pcap` |
| smtp_tnef_0001 | SMTP Submission | 587 | TCP | Wireshark SampleCaptures `sample-TNEF.pcap` |
| smtp_plaintext_0001~0003 | Postfix (domex) | 25 | TCP | Bro/Zeek `faf-exercise.pcap`（明文子会话） |

## 会话概要

- **smtp_exim_0001**：10.10.1.4 → 74.53.140.153:25。EHLO → AUTH LOGIN → MAIL FROM → RCPT TO → DATA（multipart/mixed，text/plain + text/html + NEWS.txt）→ QUIT。
- **smtp_submission_0001**：192.168.1.4 → 217.12.11.66:587。EHLO → AUTH LOGIN → MAIL FROM → RCPT TO → DATA（quoted-printable patch）→ QUIT。
- **smtp_tnef_0001**：→ 217.12.11.66:587。EHLO → AUTH LOGIN → MAIL FROM → RCPT TO → DATA（TNEF `application/ms-tnef` 附件）→ QUIT。
- **smtp_plaintext_0001~0003**：192.168.1.104 → 192.168.1.1:25（Postfix domex）。EHLO → MAIL FROM（含 SIZE=）→ RCPT TO → DATA → 正文 → QUIT，为明文邮件（Thunderbird 客户端）。

## ⚠️ 关于 faf-exercise.pcap（STARTTLS 加密会话）

`_raw_downloads/faf-exercise.pcap` 是 Bro/Zeek 官方练习包（5902 包），内含约 20 条 SMTP 会话：

- **3 条明文邮件会话** → 已提取为 `smtp_plaintext_0001~0003`（服务器 Postfix domex）。
- **17 条 STARTTLS 加密会话** → 明文部分仅 EHLO / STARTTLS / 220 协商，邮件内容经 TLS 加密不可见，故仅归档原始抓包、未逐条转换。

如需 STARTTLS 协商语料，可直接对 `faf-exercise.pcap` 过滤端口 25 提取握手部分。

## 补充说明

- `manifest.csv` 的 `pcap` 列沿用原采集机路径占位 `/home/zxy/数据流量/<run_id>/capture.pcapng`（实际文件在本机）。
- 生成/转换工具：`smtp_capture_to_kb.py`（pcap → 统一格式，见工作区）。
- `packets.ndjson` 由 scapy 生成，字段结构贴近 tshark `-T ek` 输出（frame/ip/tcp/smtp 层），非 tshark 原生输出。
