# 多段 Evidence 承载方案

## 一、D3 的实际形态

flags 保留位的知识需要两段原文：

1. 图例：`|B|             MBZ             |`（594 行）
2. 规范句：`flags field are reserved for future use. They MUST be set to zero`（587 行）

两段**不相邻**，拼成一段就是伪造。

## 二、三种承载方式

| 方案 | 做法 | 评价 |
|---|---|---|
| A 拼接 | 把两段合成一条 quote | **禁止**，伪造连续原文 |
| B 只取规范句 | 仅用 587 行 | 可接受但丢失"哪些位"的信息 |
| C 主证据 + 辅助证据 | 1 条 Evidence 主（587）+ 侧车 aux（594） | 推荐 |

## 三、C 的落法

- `Claim.evidence` 仍是一条（主证据，必须是完整句）；
- 侧车 `evidence_aux.json`：`claim_id → [{span, quote, role:"legend"}]`；
- 读取时按 claim_id 合并展示，**不改变** Hub 契约。

## 四、与现有契约的关系

现有 `Claim.evidence` 是列表结构（实测 `evidence` 为 tuple/list），理论上可放多条。需确认：

- 多条 Evidence 是否参与 EvidenceID 计算（会否冲突）；
- Hub 导出 `evidence_summary` 是否支持多条。

若支持，则不需要侧车；若不支持，用侧车。

## 五、建议

先做只读实验：给一条 Claim 挂两条 Evidence，看 `evidence_summary` 与 EvidenceID 的实际表现，再定方案。本轮不做。
