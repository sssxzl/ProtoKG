# T0-A v6 五条异常修正逐项证据

## 一、截断问题先定性

上一份 CSV 的 quote 只到 120 字符，是**报告生成时 `quote[:120]` 截断**，不是侧车丢数据。`align_v4_30items.json` / `align_v6_10pending.json` 里保存的是完整引用。

## 二、五条修正

| span | 原引用（错） | 修正引用 | 定位 | 结论 |
|---|---|---|---|---|
| 213 | server MUST discard | `The client SHOULD send an EHLO command as the first command after a successful TLS negotiation.` | 217–218 exact | supported |
| 210 | 附录 bullet | `The client MUST discard any knowledge obtained from the server, such as the list of SMTP service extensions, which was not obtained from the TLS negotiation itself.` | 214–217 whitespace_normalized | supported |
| 234 | server MUST NOT return | `STARTTLS is a valid ESMTP extension when used on the Submission port, as defined in [RFC2476].` | 243–244 exact | supported |
| 310 | 攻击描述句 | `The additional option of using TLS when possible SHOULD also be provided.` | 315–316 exact | supported |
| 353 | [SMTP-AUTH] 句 | `the SASL EXTERNAL mechanism [SASL] MAY be used in conjunction with the STARTTLS command to provide an authorization identity.` | 354–355 exact | supported |

## 三、每条修正的语义对齐

- 213：命题是"客户端应首先发 EHLO"，原文正是 client SHOULD send EHLO；不再是 server 丢弃句。
- 210：命题是"客户端丢弃从服务器获得、非 TLS 所得的知识"，原文 214–217 完整表达，主体 client、强度 MUST 均在。
- 234：命题是"STARTTLS 在 Submission 端口有效"，4.3 节首句正是该断言。
- 310：命题是"应提供可选 TLS 能力"，原文 `additional option … SHOULD also be provided`，强度 SHOULD 保留。
- 353：MAY、主体（SASL EXTERNAL mechanism）、对象（authorization identity）、搭配（with STARTTLS）齐全。

## 四、修正性质

全部为**引用改配**，不涉及命题改写、不改 Schema、不改身份。原始 model_span 与原始错误引用保留在旧 CSV 中。
