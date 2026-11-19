# T0-A 正式产物保护与放行检查表

## 一、前后对照

| 项 | 值 |
|---|---|
| `derived/per_source` + `derived/hub` 文件数 | 190（未变） |
| 合并哈希摘要 | `6ace9d32…`（未变） |
| 历史散文缓存 | `558767f2…`，76 条 |
| 三协议 Norm / Fact | 63/107/92、82/152/99 |

## 二、放行检查表

| # | 检查 | 状态 |
|---|---|---|
| 1 | 请求前门禁成立（调用数/输入/费用/参数） | 通过 |
| 2 | 无自动重试、无第三次请求 | 通过 |
| 3 | 全产物隔离，危险根拒绝 | 通过 |
| 4 | 完整链路到隔离 Hub 并读回 | 通过 |
| 5 | 部分成功不判完成 | 通过 |
| 6 | 失败留证、非零退出 | 通过 |
| 7 | Claim/Evidence 按官方契约落盘 | 通过（摘要级） |
| 8 | 正式产物未变 | 通过 |
| 9 | 本轮 0 次 LLM、0 次网络 | 成立 |

## 三、状态

```
T0_A_live_runner_engineering_verified
T0_A_live_execution_ready_for_approval
real_llm_output_pending_validation
production_merge_not_approved
```

真实调用仍待费用授权；批准前不发起任何请求。
