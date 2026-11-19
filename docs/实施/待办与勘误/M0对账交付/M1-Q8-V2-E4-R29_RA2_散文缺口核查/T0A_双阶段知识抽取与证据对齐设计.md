# T0-A 双阶段知识抽取与证据对齐设计

## 一、为什么拆分

v5 把 quote 塞进主抽取后：条目 30→25、约束 16→13、Gold 两句直接消失。证据要求挤占了抽取预算。

改为两阶段：

| 阶段 | 职责 | Prompt | 是否产知识 |
|---|---|---|---|
| 1 | 语义抽取（v4 口径） | `prose-semantics-v4`（2 350 字符） | 是 |
| 2 | 证据回填 | `evidence-align-v1`（独立） | 否，只给 quote |

## 二、第一阶段

恢复 v4 内容：说明性章节要求、定义/能力/安全属性/约束；**不要求 quote**。原始 `span` 只作建议，标 `evidence_pending`。

## 三、第二阶段

输入：命题 id、命题文本、建议 span、RFC 全文（带行号）。
输出：`{id, status: ok|not_found|multi_source, evidence_quote}`。

约束：

- 不得改写命题、Subject、Aspect、action、condition、强度；
- quote 必须逐字来自原文，跨行可以，拼接不行；
- 需要多段原文支持时返回 `multi_source`，不强行拼；
- 每批 10 条，避免再次触顶。

## 四、确定性定位

复用 `locate_quote()`：精确 → 空白归一化 → 唯一性检查 → 行区间。

| 状态 | 含义 | 处置 |
|---|---|---|
| exact_match / whitespace_normalized_match | 唯一命中 | 写 `verified_span` |
| ambiguous | 多处命中 | 不进已验证集合 |
| quote_not_found | 原文没有 | 待核验区 |
| multi_source | 需多段证据 | 待人工核验 |

## 五、状态分层

`semantic_extraction_success`、`quote_location_success`、`evidence_support_verified`、`canonical_validation_success`、`hub_integration_success` 分别记录。

quote 命中 ≠ 语义支持通过。本轮 `evidence_support_verified` 只对两条 Gold 做了人工比对，其余标 `pending_review`。

## 六、身份与去重

Norm/Fact ID 算法未改；第二阶段的 id 用 `p<index>`，与 Fact 通过 `fact_id` 反查关联，不参与去重排序，避免「错误引用先登记、后续有效引用被丢弃」。
