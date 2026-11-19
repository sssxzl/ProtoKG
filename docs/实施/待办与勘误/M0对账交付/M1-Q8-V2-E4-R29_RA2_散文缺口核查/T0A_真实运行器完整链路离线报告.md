# T0-A 真实运行器完整链路离线报告（G3）

## 一、执行器做了什么

`t0a_executor.run()` 一条路径走完：

```
RFC 读取 → 6 块 → _extract_blocks(GuardedClient) → Norm
        → map_norm_to_facts → Fact/Claim/Evidence
        → 写 JSONL → isolated_hub → load_facts → build_entity_index → write_entity_index → 读回校验
```

没有第二套转换逻辑，ID 全部由既有函数计算。

## 二、分段成功标记

结果里分成四个字段，不用一个 `success` 掩盖中途失败：

| 字段 | 正常执行 |
|---|---|
| `status` | `completed` |
| `norm_validation_success` | true |
| `canonical_validation_success` | true |
| `hub_integration_success` | true |

任一阶段失败，`status` 立即写成对应错误码并返回，不再往后走。

## 三、实测

| 项 | 值 |
|---|---|
| Norm | 1（`kind=prose_semantics`） |
| Fact | 1（`aspect=definition`） |
| FactID | 由 `compute_fact_id` 生成，读回一致 |
| 实体 | 1（含 STARTTLS） |
| 调用次数 | 2 |

## 四、未覆盖

- 完整中枢（sources.json / 社区 / 图）未构建，只到实体索引；
- 真模型下 Norm 数量与字段分布未知。
