# T0-A 三项阻断修正与放行结论

## 一、修正

### 1 完整性检查提前

原实现先写 Fact JSONL、建 Hub，最后才判完整性——「首批成功、二批被拒」会在 Hub 里留下半份知识。

现改为：写任何 Fact / Hub 文件之前，统一检查四项（批次数 `guard.calls == ceil(blocks/5)`、`stats.failures == 0`、`guard.stopped is False`、缓存 `complete is True`），任一不满足即 `cache_incomplete` 直接返回，`hub_integration_success` 保持未设置。

负例改为检查**文件是否存在**，不再只看 status：

| 断言 | 结果 |
|---|---|
| 门禁拒绝后 `per_source/facts/*.jsonl` 不存在 | PASS |
| 门禁拒绝后 `hub/entities.jsonl` 不存在 | PASS |
| `hub_integration_success` 未置真 | PASS |

### 2 失败调用与 usage 对账

- `calls` 一律取自 `Guard.calls`（真实发起次数），不再由调用方累加；
- 解析失败但已拿到 usage ⇒ `guard.after()` 记账，`billing_status=billed`；
- 超时未收到响应 ⇒ `billing_status=unknown`，不记 0 消耗；
- 失败分支同时写 `result.json` 与 `guard.json`，两者 `calls` 一致。

| 断言 | 结果 |
|---|---|
| 超时：status/timeout、calls=1、billing unknown | 2 PASS |
| 无效 JSON：billing=billed、usage≥700 已记账、calls 一致 | 3 PASS |

### 3 隔离根限域

只允许两类根：系统临时目录下，或 `T0A_WORKSPACE` 指定目录。新增拒绝：文件系统根、仓库根、`outside_workspace`；原有相对路径、`..`、符号链接、受保护目录规则保留。

| 断言 | 结果 |
|---|---|
| 文件系统根 / 仓库根 / 正式 `derived` 拒绝 | 3 PASS |
| 临时工作区仍可正常完成 | PASS |

## 二、回归

`t0a_executor_checks`（13）、`checks2`（18）、`checks3`（12）、F2 v2/v3、Hub 隔离，全部通过。

## 三、产物对照

| 项 | 值 |
|---|---|
| `derived/per_source` + `derived/hub` 文件数 | 190（未变） |
| 合并哈希摘要 | `6ace9d32…`（未变） |
| 历史散文缓存 | `558767f2…`，76 条 |
| 三协议 Norm / Fact | 63/107/92、82/152/99 |

## 四、放行结论

```
T0_A_live_runner_engineering_verified
T0_A_live_execution_ready_for_approval
real_llm_output_pending_validation
production_merge_not_approved
```

本轮 0 次 LLM、0 次网络。真实调用仍待费用授权；此后不再增加常规工程验收轮次。
