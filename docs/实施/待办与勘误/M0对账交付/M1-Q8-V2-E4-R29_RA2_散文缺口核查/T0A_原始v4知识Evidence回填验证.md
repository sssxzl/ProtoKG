# T0-A 原始 v4 知识 Evidence 回填验证

## 一、输入

v4 归档的 30 条 Raw（`T0A_实跑4_20261119_promptv4/cache.json`），RFC 3207 冻结原文，未重新抽取。

## 二、结果

| 指标 | 值 |
|---|---|
| 命题 | 30 |
| 定位成功 | **29** |
| not_found | 0 |
| multi_source | 1（p7：STARTTLS 命令格式需多处原文） |
| 请求 | 4 次（1 次因校验器不兼容失败 + 3 批） |

## 三、两条 Gold

| 命题 | 模型原 span | 验证 span | 匹配 | quote |
|---|---|---|---|---|
| p0：文档描述一个 SMTP 扩展，允许用 TLS 提供私密认证通信 | 22 | **[30, 33]** | exact_match | `This document describes an extension to the SMTP (Simple Mail Transfer Protocol) service that allows an SMTP server and client to use TLS…` |
| p1：TLS 使 SMTP 代理能保护通信免受窃听 | 25 | **[33, 35]** | exact_match | `This gives SMTP agents the ability to protect some or all of their communications from eavesdroppers and attackers.` |

两条都是「模型行号错、quote 对」的典型：程序按原文重定位到 30/33，与 Gold 跨度一致。

## 四、负例覆盖

| 场景 | 结果 |
|---|---|
| quote 不存在 | `quote_not_found`（离线构造） |
| quote 多处出现（`the`） | `ambiguous`（离线构造） |
| 需多段证据 | `multi_source`（真实：p7） |
| 模型行号错、quote 对 | 重锚定（真实：p0/p1） |

## 五、边界

- 该验证用的是 v4 的旧 Raw，**不是**新 quote 契约下模型自己产出的 quote；第二阶段是程序提问、模型作答，属于新调用，但第一阶段知识仍是旧的。
- quote 支持命题这一点，只对 p0/p1 做了人工比对；其余 27 条标 `pending_review`。
