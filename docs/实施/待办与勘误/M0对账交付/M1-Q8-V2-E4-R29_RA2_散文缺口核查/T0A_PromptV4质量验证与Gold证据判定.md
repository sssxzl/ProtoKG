# T0-A Prompt v4 质量验证与 Gold 证据判定

## 一、Prompt v3 → v4

| 项 | v3 | v4 |
|---|---|---|
| 版本 | `prose-semantics-v3` | `prose-semantics-v4` |
| 字符 | 1 508 | 2 350 |
| SHA256 | `84cc0e5b…` | `4e7b6019…` |

新增内容为英文通用规则：说明性章节中的实质性技术陈述（文档目的、扩展能力、预期安全属性、威胁缓解目标、所启用的技术行为）同样要抽；`This document describes` / `This specification defines` / `This extension allows` 这类引导句要抽其技术命题，而不是「某文档描述了某事」；不得用邻近句子替代，不得推断原文未写的保证。

未改 Schema、模型、thinking、max_tokens、批大小、身份算法。快照与哈希见 `T0A_实跑4_20261119_promptv4/prompt_v4.txt` 与 `prompt_v4_meta.json`。

## 二、运行结果

| 项 | 值 |
|---|---|
| 状态 | `completed` |
| 请求 | 2（5+1） |
| 输入 / 输出 | 6 297 / 5 505 |
| Norm / Fact | 30 / 30 |
| Aspect | legal_boundary 16 / definition 14 |
| Subject | actor 18 / protocol 12 |
| 实体 | 12 |

## 三、Gold：语义命中，证据锚点错误

| Gold | 语义 | 锚点 | 判定 |
|---|---|---|---|
| `-30-1` | 命中：「该文档描述了一个 SMTP 服务扩展，允许服务器与客户端用 TLS 提供私密、经认证的通信」 | **22** | 不计命中 |
| `-30-2` | 命中：「TLS 使 SMTP 代理能够保护其部分或全部通信免受窃听者和攻击者的侵害」 | **25** | 不计命中 |

锚点核对：

| 行 | 实际文本 |
|---|---|
| 22 | `and status of this protocol.  Distribution of this memo is unlimited.`（样板文字） |
| 25 | 空行（Copyright 段空白处） |
| 30 | `This document describes an extension to the SMTP (Simple Mail` ← 正确位置 |
| 33 | `communication over the Internet.  This gives SMTP agents the abilit` ← 正确位置 |

模型把两句的语义抽对了，但行号偏了 8 行，落在样板段与空白行上。证据不支持命题，按规则不能算命中。

**结论：v4 的 Gold 为 `semantic_hit_evidence_wrong`，不是 2/2，也不是 0/2。**

## 四、为什么 span 校验没拦住

现有校验只要求「该行原文出现所声称的 entity」。这两条的 entity 是 `SMTP`，第 22 行确实出现，于是通过。校验不检查「该行是否承载命题」。

这是校验强度问题，不是模型理解问题。

## 五、规范义务回归（对照 R4）

| span | v4 | 说明 |
|---|---|---|
| 155 / 158 / 214 / 217 / 232 | 精确命中 | 与 R4 一致 |
| 127 / 146 / 231 | 邻近 ±1–2 行（129/148/228 或 232） | 规则抽到，锚点偏移 |
| 341 | 未命中 | R4 有、v4 无，属回退 |

legal_boundary 从 18 降到 16，两条是「v4 新增了摘要类知识、挤掉了部分约束」——不是去重，是模型输出分布变化。

## 六、判断与下一步

v4 达到了本轮主要目标：文档目的与安全属性这类说明性命题被抽出来了。剩下的是证据锚点精度问题。

两个候选方向（需批准，本轮不动）：

1. 增强 span 校验：要求锚点行包含命题关键词（entity 之外），否则拒收或就近重定位；
2. 让模型输出 `quote`，用 quote 反查行号，替代直接给行号。

方向 2 更稳，但要改 Prompt 输出字段，属于 Schema 层面变更，需要单独批。
