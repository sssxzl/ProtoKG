# RFC 2131 Gold 判定口径校准

## 一、D5：Gold 本身缺条件，Norm 又丢了条件

原文（950–952）：`if the client has a network address, it MUST NOT fill in the 'ciaddr' field`。

- 预登记 Gold 写的是「ciaddr 必须为 0」，**没有带"客户端已有地址"这一前提**；
- Norm 959 写「客户端不得填写 ciaddr」，同样丢了条件。

严格评分应判 `partially_supported`：动作对、条件丢。原评分（命中）保留，另记严格分（部分）。

## 二、D2：不是"Therefore 句首"失败

原文 1711–1712 的 `servers SHOULD NOT reuse offered addresses` 是**独立规范句**，`Therefore` 在前一段 1704，且该句不带连接词开头。

因此我上一轮"承接型规则在表格型文档失效"的说法**不准确**：D2 是漏抽了一条独立 SHOULD NOT，不是连接词引导句失效。

## 三、D6：消息类型不同

D6 要求 DHCPDISCOVER 中不得填 server identifier；Norm 2150 是 DHCPREQUEST 中 MUST NOT。**不判命中**，维持部分。

## 四、其余

D3、D4 维持未命中。6 条未定位知识与 68 条已定位知识状态不变（后者仍 `pending_review`）。
