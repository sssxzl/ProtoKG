# T0-A 真实模型知识质量对照报告（Prompt v3 + 8 000）

## 一、总量对比

| 指标 | 第一次真跑（v2/4000） | 本次（v3/8000） |
|---|---|---|
| Norm | 13 | **30** |
| Fact | 13 | 30 |
| legal_boundary | 0 | **18** |
| definition | 13 | 12 |
| subject actor / protocol / header | 0 / 0 / 13 | **19 / 11 / 0** |
| 实体 | 12 | 14 |
| 证据锚点数 | 13 | 30（30–352 行） |

Prompt v3 的覆盖要求与 8 000 的输出空间，同时改善了召回与分类。

## 二、Gold 逐条

| Gold | span | 本次结果 | 依据 |
|---|---|---|---|
| `-30-1` | 30-33 | **miss** | 唯一 #@30 的 Fact 是「SMTP 是简单邮件传输协议，服务器与客户端通常以明文通信」，讲的是上一句，不是「本文件描述一个扩展…」 |
| `-30-2` | 33-35 | **miss** | 30 条 Fact 中无「protect communications / eavesdroppers」类语义 |

Gold 仍然 0/2。这一次不是「没有 30 行的条目」，而是**有 30 行条目但命题不对**——比上一轮更接近，但仍未命中。

## 三、重点规范行

| span | 本次 | 说明 |
|---|---|---|
| 146 | hit（legal_boundary, actor: server） | 530 回复码规则 |
| 214 | hit | 客户端 MUST discard knowledge |
| 231 | hit（actor: server） | MUST NOT 启动 TLS |
| 341 | hit | clients and servers MUST discard |
| 127 / 155 / 158 / 217 / 232 | 邻近锚点（128/156/160/230/236） | 同一规则、锚点偏 1–4 行 |

9 条重点行中 4 条精确命中，5 条落在一行到四行内的邻近位置。说明模型抽到了规则，标点/跨行导致锚点偏移。

## 四、Evidence 真实性抽样

抽 3 条核对行号与原文：锚点 30 对应「SMTP ... plaintext」句；146 对应 530 回复码段；341 对应 discard 段。行号与引用内容一致，未发现凭空引用。

## 五、判定

| 维度 | 结论 |
|---|---|
| 抽取召回（Gold） | 0/2，未通过 |
| 规范义务完整性 | 30 条中 18 条约束，覆盖 MUST/MUST NOT/SHOULD |
| Subject/Aspect | header 归零，actor/protocol 正确区分 |
| Evidence | 抽样一致 |
| Canonical/Hub | 30 Fact 全部映射，Hub 14 实体读回 |

## 六、下一步建议

Gold 两句都在 Introduction 首段，模型倾向从「明文通信」这类陈述句开始抽，把「本文件描述一个扩展」当作元信息跳过。这是 Prompt 语义偏好问题，不是容量问题。建议下一轮在 Prompt 中显式要求「文档自述的目的/能力陈述（如 This document describes…）也要抽为知识」，再做一次验证。

本轮不自行修改，等批准。
