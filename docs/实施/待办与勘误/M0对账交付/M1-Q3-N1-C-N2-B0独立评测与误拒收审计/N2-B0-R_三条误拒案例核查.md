# N2-B0-R · 三条误拒案例核查

> ★ 日期：2026-11-16 ｜★ **0 次 LLM 调用**｜★ **未按候选 ID 特例**（★ 判据只看原文与字段）
> ★ 事实基础：`guard/_out/n1c/n2b0r_three_cases_context.json`（★ 由脚本从同版本 RFC 原文恢复）

---

## 〇、★ 遗漏勘误补齐（★ 用户指出）

★ V0 的 `contradicted → rejected` **完整清单为 3 条**（★ 此前报告仅列前 2 条）：

| # | candidate_id | 人工真值 | V0 拒收原因 |
|---|---|---|---|
| 1 | ★ `rfc2326.txt@2030#5` | `valid_confirmed` | ★ 出现 `must` |
| 2 | ★ `rfc5321.txt@5226#1` | `valid_confirmed` | ★ 出现 `must` |
| 3 | ★ `rfc5321.txt@5226#2` | `valid_confirmed` | ★ 出现 `must` |

★ ⇒ ★ **三条人工真值均为 `valid_confirmed`**；★ 拒收原因**均涉及出现 `must`** ✔

---

## 一、★ 案例 1：`rfc2326.txt@2030#5`（RFC 3261 · SIP）

### 1.1 原始候选字段
| 字段 | 值 |
|---|---|
| entity | `request` |
| normative_subject | ★ **（空）** |
| action | `contain` |
| object | `a single parameter` |
| strength | `SHOULD` |
| constraint（生成） | `请求应只包含单个参数` |

### 1.2 完整规范句与上下文（★ 锚点 2097）

```
2097: A request SHOULD only contain a single parameter to allow the client
2098: (continuation)
2099: several parameters, the server MUST only act on the request if all of
2100: the parameters can be set successfully.  A server MUST allow a
2101: parameter to be set repeatedly to the same value, but it MAY disallow
2104: Note: transport parameters for the media stream MUST only be set with
```

### 1.3 六问回答

| # | 问题 | 回答 |
|---|---|---|
| ① | ★ **`must` 实际约束哪一个主体和行为？** | ★ **`the server`**（★ 行 2099-2100）★ 动作 = **「only act on the request if all of several parameters can be set successfully」** |
| ② | ★ 候选的 SHOULD 是否来自同一句、同一命题？ | ★ **是**：★ 候选命题 = 行 2097「**A request SHOULD only contain a single parameter**」 |
| ③ | ★ 是否存在真正的否定或互斥要求？ | ★ **否**：★ 行 2099 的 MUST 是**另一个义务**（★ 强度更高），★ **不是**对候选 SHOULD 的否定 |
| ④ | ★ 原来的 `contradicted` 是否由无关义务触发？ | ★ **是**（★ **完全无关**：★ 主体 server vs request；★ 动作 act on the request vs contain） |
| ⑤ | ★ 修正后应该进入 supported 还是 uncertain？ | ★ **supported**（★ 同命题句 2097 命中 SHOULD + 动作 + 对象）★ ⇒ V1 实测 **supported（routed_to_LLM）** ✔ |
| ⑥ | ★ 是否仍存在字段不完整问题？ | ★ **是**：★ **`normative_subject` 为空**（★ 主体只能从原文反推）★ ★ ⇒ **即使 V1 判 supported，★ 该候选仍缺主体字段 ⇒ 不可直接发布** |

---

## 二、★ 案例 2：`rfc5321.txt@5226#1`（RFC 5321 · SMTP）

### 2.1 原始候选字段
| 字段 | 值 |
|---|---|
| entity | `Clients` |
| normative_subject | `Clients` |
| action | `provide` |
| object | `SEND, SAML, or SOML as services` |
| strength | ★ **`SHOULD`**（★ **丢掉了 NOT**） |
| constraint（生成） | ★ **`Clients SHOULD NOT provide SEND, SAML, or SOML as services.`**（★ **含 NOT**） |

### 2.2 完整规范句与上下文（★ 锚点 5238）
```
5238: Clients SHOULD NOT provide SEND, SAML, or SOML as services.  Servers
5239: MAY implement them.  If they are implemented by servers, the
5240: implementation model specified in RFC 821 MUST be used and the
5241: command names MUST be published in the response to the EHLO command.
```

### 2.3 六问回答

| # | 问题 | 回答 |
|---|---|---|
| ① | ★ `must` 实际约束哪一个主体和行为？ | ★ **实现者 / servers**（★ 行 5240-5241）★ 动作 = **「use the implementation model specified in RFC 821」** 与 **「publish the command names in the response to the EHLO command」** |
| ② | ★ 候选的 SHOULD 是否来自同一句、同一命题？ | ★ **来自同一句（5238）**，★ **但候选 strength 字段与原文本不一致**（★ 原文 **SHOULD NOT** ⇒ 禁止；★ 字段只记 **SHOULD** ⇒ 允许）⇒ ★★ **★ 候选字段自身矛盾** |
| ③ | ★ 是否存在真正的否定或互斥要求？ | ★ **否**（★ 相对候选而言）★ ★ 原文本身就是**禁止性**要求，★ **而非与候选互斥的另一条义务** |
| ④ | ★ 原来的 `contradicted` 是否由无关义务触发？ | ★ **是**（★ 行 5240-5241 的 MUST 与候选命题无关）★ ★ **且真正的问题不是反证，★ 而是候选把 SHOULD NOT 记成了 SHOULD** |
| ⑤ | ★ 修正后应该进入 supported 还是 uncertain？ | ★★ **uncertain**（★ **候选字段自相矛盾** ⇒ ★ 按 §三 第 5 条「强度范围不一致 ⇒ 优先 uncertain」）★ ⇒ V1 实测 **uncertain（pending）** ✔ |
| ⑥ | ★ 是否仍存在字段不完整问题？ | ★★ **是**：★ **strength 丢失 NOT**（★ 语义方向被颠倒）；★ **polarity 亦需由 SHOULD NOT 推出 negative** ⇒ ★ **必须回修候选抽取** |

---

## 三、★ 案例 3：`rfc5321.txt@5226#2`（RFC 5321 · SMTP）

### 3.1 原始候选字段
| 字段 | 值 |
|---|---|
| entity | `Servers` |
| normative_subject | `Servers` |
| action | `implement` |
| object | ★ `them (SEND, SAML, SOML)`（★ **代词 them**） |
| strength | `MAY` |
| constraint（生成） | `Servers MAY implement them.` |

### 3.2 完整规范句（★ **跨行**）
```
5238: Clients SHOULD NOT provide SEND, SAML, or SOML as services.  Servers
5239: MAY implement them.  If they are implemented by servers, the
5240: implementation model specified in RFC 821 MUST be used and the
5241: command names MUST be published in the response to the EHLO command.
```
★ ★ **候选命题实际在行 5239**（★ 主语 `Servers` 在 5238 行末、★ 谓语 `MAY implement them` 在 5239 行）

### 3.3 六问回答

| # | 问题 | 回答 |
|---|---|---|
| ① | ★ `must` 实际约束哪一个主体和行为？ | ★ **实现者 / servers**（★ 行 5240-5241）★ 动作 = **use the implementation model / publish the command names** |
| ② | ★ 候选的 MAY 是否来自同一句、同一命题？ | ★ **来自行 5239 的 MAY**（★ 与 5240-5241 的 MUST **不是同一命题**）★ ★ 候选命题本身**跨行**（主语在 5238 行末） |
| ③ | ★ 是否存在真正的否定或互斥要求？ | ★ **否** |
| ④ | ★ 原来的 `contradicted` 是否由无关义务触发？ | ★ **是**（★ 行 5240-5241 的 MUST 属别的义务） |
| ⑤ | ★ 修正后应该进入 supported 还是 uncertain？ | ★★ **uncertain**（★ **对象 `them` 是代词，★ 需回指 5238 行的 `SEND, SAML, or SOML`；★ 跨句归属未解析** ⇒ ★ 按 §三 第 5 条「跨句归属不清 ⇒ 优先 uncertain」）★ ⇒ V1 实测 **uncertain（pending）** ✔ |
| ⑥ | ★ 是否仍存在字段不完整问题？ | ★★ **是**：★ **对象为代词，★ 未解析回指**；★ **主语跨行** ⇒ ★ **需补指代恢复与跨行主体合并** |

---

## 四、★ 三条小结（★ 均未使用候选 ID 特例）

| # | 候选 | V0 | ★ V1 | 真正的根因 |
|---|---|---|---|---|
| 1 | `@2030#5` | contradicted ⇒ rejected | ★ **supported ⇒ routed_to_LLM** | ★ 无关义务的 must 触发；★ **候选缺主体** |
| 2 | `@5226#1` | contradicted ⇒ rejected | ★ **uncertain ⇒ pending** | ★ **候选 strength 丢 NOT（★ 字段自相矛盾）** |
| 3 | `@5226#2` | contradicted ⇒ rejected | ★ **uncertain ⇒ pending** | ★ **对象为代词、★ 跨句归属不清** |

⇒ ⇒ ★★ **三条的真正根因各不相同**（★ 无关义务 / 字段自相矛盾 / 跨句指代未解析）
⇒ ⇒ ★★ **⇒ 但 V1 的同一套判据同时正确处理了三条**（★ **命题级 + 作用域级 + 字段一致性**）
⇒ ⇒ ★★ **⇒ 且 V1 修掉这三条时，★ **未引入新的误拒**（★ V1 误拒总数 = **0**）
