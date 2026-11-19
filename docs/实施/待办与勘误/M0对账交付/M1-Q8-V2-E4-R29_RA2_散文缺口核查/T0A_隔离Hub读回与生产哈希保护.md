# T0-A 隔离 Hub 读回与生产哈希保护

## 一、隔离 Hub 读回

用本轮 22 条 Fact 写入隔离目录，经 `isolated_hub` 走既有 `load_facts` / `build_entity_index` / `write_entity_index`：

| 项 | 值 |
|---|---|
| 读回 Fact | 22 |
| 读回 Claim | 22 |
| 实体 | 13 |
| 索引文件 | 生成并可读回 |

不是只检查写盘前的列表——读回后重新统计的 claim 数与写入前一致。

## 二、生产保护

| 项 | 值 |
|---|---|
| `derived/per_source` + `derived/hub` 文件数 | 190（未变） |
| 合并哈希摘要 | `6ace9d32…`（未变） |
| 历史散文缓存 | `558767f2…`，76 条 |
| 三协议 Norm / Fact | 63/107/92、82/152/99 |

## 三、边界

- 本轮 0 次 LLM、0 次网络；
- 未改 FactID 算法、21 aspects、Schema、Prompt v3；
- 未写正式 `derived/`、Hub、Seed；
- 单进程，无并发验证。

## 四、状态

```
T0_A_prose_fact_identity_verified
T0_A_second_live_test_preflight_passed
```

第二次真实试验仍受原独立请求与费用授权约束，本轮不发起。
