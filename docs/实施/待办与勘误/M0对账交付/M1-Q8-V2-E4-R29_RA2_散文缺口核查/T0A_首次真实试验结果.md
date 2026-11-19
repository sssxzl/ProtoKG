# T0-A 首次真实试验结果（2026-11-19）

## 一、结论

链路跑通，Gold 未命中。两次运行，共 4 次真实请求。

```
status = completed
llm_call_success = true
norm_validation_success = true
canonical_validation_success = true
hub_integration_success = true
```

## 二、两次运行

| 运行 | 状态 | 请求 | Norm | Fact | 说明 |
|---|---|---|---|---|---|
| 第 1 次 | `cache_incomplete` | 2 | 9 | 9 | 两个批次都成功、缓存 complete，但守卫把「实际 token 超估算 1.3–1.5 倍」判为停止，完整性检查因此拦下，未写 Fact/Hub |
| 第 2 次 | `completed` | 2 | 13 | 13 | 估算改用 tiktoken 后通过，全链路完成 |

第 1 次失败原因是我自己写的守卫：`len(user)//4` 低估了中文+JSON 的 token 数，触发「超预估即停」。修正为 tiktoken 真实计数后重跑。这不是放宽安全线，是修掉一个错误的度量。

## 三、真实用量与费用

| 项 | 值 |
|---|---|
| 输入 token | 5 837（两次运行相同，输入一致） |
| 输出 token | 3 008（第 1 次）/ 3 632（第 2 次） |
| 按高峰单价折算 | 0.0357 + 0.0407 = **¥0.0764** |
| 按当时时段（20:28，空闲） | 0.0180 + 0.0204 = **¥0.0384** |
| 批准上限 | ¥0.15（未超） |

单价按 DeepSeek 官方 V4.1-Flash：输入未命中 1/2 元、输出 4/8 元每百万 token（空闲/高峰）。

## 四、产物

| 产物 | 值 |
|---|---|
| Norm | 13 条，全部 `kind=prose_semantics` |
| Fact | 13 条，全部 `aspect=definition` |
| Claim/Evidence | 每条 1 个 claim，证据锚点形如 `file:rfc3207.txt#@76` |
| 隔离 Hub 实体 | 12 个（`smtp:header:*`） |
| 证据行号分布 | 76、127、155、172、183、186、211、220、230、309、313、315、352 |

## 五、Gold 观察（只作观察）

| Gold | span | 结果 | 最近锚点 |
|---|---|---|---|
| `GK-B-smtp-rfc3207.txt-30-1` | 30-33 | **miss** | 76（差 46 行） |
| `GK-B-smtp-rfc3207.txt-30-2` | 33-35 | **miss** | 76（差 43 行） |

两条都在 Introduction 段，模型没有在该段产出知识；产出的 13 条集中在 76 行之后（STARTTLS 定义、服务行为、约束）。命中率 0/2 是真实结果，不用 Stub 补齐。

## 六、暴露的问题

1. **subject 类型误用**：`client`、`both parties`、`implementation` 被记成 `smtp:header:*`。散文知识不是头字段，这是既有映射的语义偏差，不是本轮引入。
2. **aspect 单一**：13 条全是 `definition`，没有 `legal_boundary`。说明约束类条目没有走到第二个 aspect，与 `prose_semantics_norm_to_facts` 的分支判据有关。
3. **首段漏抽**：Introduction 的规范性句子（30-35）没被模型抽到，属于模型/提示词层面，不在本轮工程范围。

## 七、状态

```
T0_A_live_run_completed_once
real_llm_output_validated_partially   # 链路与产物已验证；知识质量未通过（Gold 0/2）
production_merge_not_approved
```

未修改 main，未推送；正式 `derived/` 未被写入；所有产物在 `T0A_实跑_20261119/` 与临时目录。
