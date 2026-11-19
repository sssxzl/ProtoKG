# T0-A v6 23 条既有 supported 复核

## 一、复核方法

对每条比对「命题文本」与「引用原文」，重点看主体、动作、对象、强度、条件。不因历史标 supported 直接放过。

## 二、重点复查项

| span | 复查结果 |
|---|---|
| 82 | `(2) the EHLO keyword value … is STARTTLS` — 与命题一致 |
| 89 | `(4) a new SMTP verb, "STARTTLS", is defined` — 一致 |
| 141 | `may refuse to accept messages for relay based on authentication` — 一致 |
| 152 | `status code … SHOULD be 5.7.0` — 一致 |
| 155 | `client MUST start the TLS negotiation before giving any other SMTP commands` — 一致 |
| 159 | `it SHOULD abort the connection` — 一致 |
| 177b | `The SMTP client and server may decide to move ahead even if…` — 一致 |
| 217 | `The client MUST discard any knowledge obtained from the server, such as the list of SMTP service extensions` — 一致 |

## 三、其余 15 条

逐条与引用比对，未发现主体错配或强度拔高。两条依赖归一化：

- 210：引用与原文仅空白差异，定位状态为 `whitespace_normalized_match`；
- 285：原文小写 `must`，Canonical 记 MUST，属自然语言义务归一化，**不是**原文出现 BCP 14 大写关键词。

## 四、结论

23 条全部维持 supported；其中 2 条记录归一化依据。
