# T0-A Evidence 已验证状态隔离接入与读回

## 一、结果

| 项 | 值 |
|---|---|
| Fact | 30 |
| 验证元数据条数 | 30 |
| claim_id 唯一 | 是（无重复键） |
| supported | 30（27 model + 3 corrected） |
| 隔离 Hub 读回 | 30 Fact / 12 实体 |
| 关联读回 | 30/30 可经 claim_id 取到 verified_span 与 quote |

## 二、做法

1. 用 v4 归档的 30 条 Fact 写进隔离 `per_source/facts/`；
2. 审查侧车 v2 以 `proposition_id → fact_id/claim_id` 建立映射，写入 `evidence_meta.json`；
3. 经 `isolated_hub` 走既有 `load_facts` / `build_entity_index` / `write_entity_index`；
4. 读回后用 claim_id 反查元数据，30 条全部命中。

## 三、p7/p8/p13 来源标识

三条 `quote_origin=corrected`，verified_span 分别为 98–102、104–109、144–150，未被标成模型原始输出。

## 四、边界

官方 Hub 视图只保存 `evidence_summary`，不承载完整 quote 与验证状态。因此本验收的准确表述是：

```
isolated_hub_evidence_sidecar_join_verified
```

不是「正式 Hub 已具备原生 Evidence 能力」。
