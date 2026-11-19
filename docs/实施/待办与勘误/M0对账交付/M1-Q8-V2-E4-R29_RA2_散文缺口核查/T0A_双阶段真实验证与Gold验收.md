# T0-A 双阶段真实验证与 Gold 验收

## 一、两阶段状态

| 阶段 | 来源 | 状态 |
|---|---|---|
| 1 语义抽取 | v4 归档（`T0A_实跑4`） | `semantic_extraction_success = true`（30 条） |
| 2 证据对齐 | 本轮真实调用 4 次 | `quote_location_success = 29/30` |

本轮**未重跑第一阶段**：v4 的 30 条 Raw 与原文都完整，足以做回填补验；重跑只会重复消耗。

## 二、Gold 验收

| Gold | 语义 | Evidence | 判定 |
|---|---|---|---|
| `-30-1` | p0 命题正确 | quote 唯一定位 [30,33]，与 Gold 跨度一致 | **命中** |
| `-30-2` | p1 命题正确 | quote 唯一定位 [33,35]，与 Gold 跨度一致 | **命中** |

判定条件：语义正确 + quote 在原文唯一命中 + 行区间落在 Gold 跨度内 + quote 人工比对确实支持命题。四条都满足，才记 2/2。

这是 T0-A 首次两条 Gold 同时通过。

## 三、五段状态

| 状态 | 值 |
|---|---|
| semantic_extraction_success | true（沿用 v4） |
| quote_location_success | true（29/30） |
| evidence_support_verified | **2/30 人工确认**，其余 pending_review |
| canonical_validation_success | true（Fact 由既有函数产出） |
| hub_integration_success | 未在本轮重跑（沿用离线验证） |

## 四、必须说明的三点

1. **知识不是本轮模型抽的**：p0/p1 来自 v4 归档；本轮只是把证据补上。不能宣称「双阶段端到端在新模型输出上跑通」。
2. **evidence_support_verified 只有 2 条**：其余 27 条 quote 定位成功，但没有逐条人工判断「这句话是否支持这个命题」。
3. **p7 是 multi_source**：STARTTLS 命令格式需要多处原文，按规则不拼 quote，留待人工。

## 五、结论

Gold 2/2 成立，且是「语义 + 证据」双重成立，不是关键词命中。
但这只覆盖两条；整体知识质量仍需逐条验收。
