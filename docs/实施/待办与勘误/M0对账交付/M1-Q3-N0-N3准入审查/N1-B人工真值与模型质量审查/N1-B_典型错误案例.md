# N1-B · 典型错误案例

> ★ 日期：2026-11-16 ｜★ 明细：`N1-B_错误案例明细.csv`（★ 27 条，★ 含原文证据/人工判断/模型判断/失效环节/修复点）

---

## 一、★ 案例分布

| 类别 | 条数 |
|---|---:|
| ★ **A 真实规范义务被错误拒收** | **13** |
| ★ **C 义务存在但主体/动作/对象错误** | 2 |
| ★ **D 强度/极性识别错误** | 3 |
| ★ **F L2 相同输入出现状态分歧** | 5 |
| ★ **G 原文证据存在但候选语义不完整** | 4 |
| ★ **B 非规范文本被错误确认** | **0**（★ 本批未观察到） |

★ ⇒ ★★ **★ 失败模式高度集中于「误拒」侧（13/27）**，★ 而非误确认侧

---

## 二、★★ 重点复查：`rfc1534.txt@1#4`（★ DHCPv4 · R 组）

### 2.1 原文证据（RFC 1534 行 65–77）

```
65: The format of DHCP messages is defined to be compatible with the
66: format of BOOTP messages, so that existing BOOTP clients can
67: interoperate with DHCP servers.  Any message received by a DHCP
68: server that includes a 'DHCP message type' (51) option is assumed to
69: have been sent by a DHCP client.  Messages without the DHCP Message
70: Type option are assumed to have been sent by a BOOTP client.  Support
71: of BOOTP clients by a DHCP server is optional at the discretion of
72: the local system administrator.  If a DHCP server that is not
73: configured to support BOOTP clients receives a BOOTREQUEST message
74: from a BOOTP client, that server silently discards the BOOTREQUEST
75: message.
```

★ 锚点行 **71**｜证据句行 **71**｜**★ 该 RFC 全文不使用 RFC 2119 关键词**

### 2.2 四个问题的明确回答

| # | 问题 | ★ 结论 |
|---|---|---|
| ① | ★ **是否构成规范约束** | ★ **是**（★ 仲裁改判为 confirmed）★ 理由：陈述式句式承载规范效力，★ 且 72–75 行是「条件→必须行为」的规则句（★ 对合规实现的行为约束）★ ★ 并指出 A 的取舍与自身对 71 行「is optional at the discretion of…」（同文档、同样无关键词、已判 MAY 级 confirmed）不一致 |
| ② | ★ **规范强度如何确定** | ★★ **由语义推断，★ 非原文显式给出**（★ RFC 1534 无 2119 关键词）★ ★ **候选 `strength` 字段为空** ⇒ ⇒ ★ **强度无原文依据** |
| ③ | ★ **候选是否缺失触发条件** | ★★ **是**（★ `condition` 未填）★ ★ 原文条件为**两个合取项**：「服务器未配置支持 BOOTP 客户端」**且**「收到来自 BOOTP 客户端的 BOOTREQUEST」 |
| ④ | ★ **是否适合进入正式规则库** | ★★ **当前不适合**：★ strength 无原文依据 + condition 缺失 + **6 个字段待仲裁**（subject/action/object/strength/polarity/condition） |

### 2.3 模型判断与失效环节

| 项 | 值 |
|---|---|
| ★ 模型 L2 | **rejected**（★ B5-P1 批次的 old/new 两侧**均为 rejected**，★ 且**两侧都是确定性短路** ⇒ ★ 未真正调用 LLM） |
| ★ 人工真值 | **valid_confirmed**（★ 仲裁改判） |
| ★ 第二层 | ② 原文存在规范义务，但候选缺少条件或主体等关键字段 |
| ★ evidence_support | **partially_supported**（★ 仲裁明确保留） |
| ★ **失效环节** | ★★ **① 确定性前置闸门（semantic_support）在 LLM 之前就拒收**（★ 未进 LLM）★ ★ **② 候选 strength 为空 ⇒ 前置闸门无法在原文找到强度词 ⇒ 拒收** |
| ★ **推荐修复点** | ★★ **① 对「无 2119 关键词但具备『条件→行为』结构」的陈述式规范句，★ 增加独立的强度判定路径（★ 而不是要求 BCP14 关键词）**★ ★ **② condition 必须显式抽取合取条件**★ ★ **③ strength 为空时不得直接拒收，★ 应转 pending 并交人工/规则判读** |

---

## 三、★ 各类案例的失效环节与修复点（★ 摘要）

| 类别 | 典型失效环节 | ★ 推荐修复点 |
|---|---|---|
| ★ **A 误拒（13 条）** | ★ 确定性前置闸门过严（★ strength/极性/实体匹配任一不满足即拒） | ★ **降低确定性闸门的拒绝力**：★ 改为「**证据不足 ⇒ pending**」而非「**⇒ rejected**」 |
| ★ **C 主体/动作/对象错误（2 条）** | ★ 跨行对象截断；★ 指代主体未解析 | ★ 对象跨行完整性检查；★ 指代主体归属核验（P0.7-A 已有）并入生产 |
| ★ **D 强度/极性（3 条）** | ★ 候选 strength 空；★ SHOULD NOT 被拆成 SHOULD | ★ 强度须有原文依据；★ **否定形式不可拆解** |
| ★ **F 同输入分歧（5 条）** | ★ L2 非确定（★ temperature=0 仍跳变） | ★ 确定性校验前置；★ L2 只作风险筛查；★ 分歧候选一律 pending |
| ★ **G 语义不完整（4 条）** | ★ condition/exception 未抽取 | ★ 条件抽取须覆盖跨句继承 |

---

## 四、★ 明细查阅

★ `N1-B_错误案例明细.csv`（★ 27 行 × 17 列）
★ 列：★ 案例类别 / sample_id / 分组 / 原文证据（锚点行）/ 证据句 / 原文上下文 /
★ LLM 候选字段 / 人工 A·B 真值 / 仲裁结论 / 冻结真值 / 第二层分类 / evidence_support /
★ 模型 L2 状态 / 模型各批次判定 / 跨批不一致 / A·B review_note
