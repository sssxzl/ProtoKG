# T0-A v6 Claim / Evidence 关联与隔离 Hub 读回

## 一、数量

| 项 | 值 |
|---|---|
| Norm / Fact | 28 / 28 |
| 唯一 fact_id | 25 |
| Claim | 28 |
| 实体 | 13 |

## 二、25 与 28 的差额

`f2_35eb41ca…` 挂 4 个 Claim（80/82/89/234），其余 24 个 Fact 各 1 个 Claim：24 + 1 = 25 个 FactID，对应 28 个 Claim。

其中 234 号 Claim 锚点可疑（见审查 CSV 的 ambiguous），**该 Fact 不算整体通过**。

## 三、读回

隔离构建后 `load_facts` 读回 28 条，claim_id 与审查 CSV 一一对应；侧车保留 `model_span`、`verified_span`、`quote_origin`。

缺失侧车时读回结果为 None，不会被默认当作已验证。

## 四、边界

官方 Hub 视图仍只存 evidence_summary；本轮未改写 Schema，也未宣称原生 Evidence 能力。
