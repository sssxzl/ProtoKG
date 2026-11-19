# T0-A 运行时载荷核验（零调用）

## 一、适配器

新增隔离模块 `scripts/t0a_adapter.py`，不进入生产路径（`core/llm.py` 未改）：

- 载荷显式带顶层 `thinking: {"type": "disabled"}`；
- `assert_payload_ok()` 在**发出网络请求前**校验 model / thinking / max_tokens / response_format / temperature，任一不符抛 `PayloadError`；
- `T0AClient` 无重试逻辑。

## 二、八项载荷检查

| # | 检查 | 结果 |
|---|---|---|
| 1 | model == `deepseek-flash` | PASS |
| 2 | thinking.type == `disabled` | PASS |
| 3 | max_tokens == 4 000 | PASS |
| 4 | response_format == json_object（冻结格式） | PASS |
| 5 | 两批为 5 + 1 块 | PASS |
| 6 | 无自动重试、无第三次请求 | PASS（适配器与运行器均无 retry） |
| 7 | 输入与费用预检 | PASS（5 958 ≤ 7 500；最坏 0.038 元 ≤ 0.15） |
| 8 | 参数不符在网络前终止 | PASS（构造错误 thinking 时抛 PayloadError） |

## 三、Stub 场景

| 场景 | 结果 |
|---|---|
| 正常 JSON 被现有解析器消费 | PASS |
| `finish_reason=length` 不写完整缓存 | PASS（修后） |
| 空字符串不标 `success_empty` | PASS |
| 纯空格不标 `success_empty` | PASS |
| 无效 JSON 不标 `success_empty` | PASS |
| 首批成功、二批失败 ⇒ 不 complete | PASS |
| 实际计费超预期 ⇒ 不再发下一次 | 已在 `t0a_run.py` 实现（本次未联网，未触发） |

## 四、本轮发现并修复的一处真实缺口

`prose_semantics` 原来只把 `finish_reason` 记进诊断，**不据此拒收**。若截断的响应恰好仍是合法 JSON，会被当作成功写入缓存。

已在影子中加最小判断：`finish_reason == "length"` ⇒ 计入失败、不写缓存、不产 Norm。这条属于行为变更，仅在影子 worktree 内，未进入 main。

## 五、成本

| 情形 | 输入 | 输出 | 合计 |
|---|---|---|---|
| 空闲时段 | 5 958 ×1 元/M | 8 000 ×4 元/M | 0.038 元 |
| 高峰最坏 | ×2 元/M | ×8 元/M | 0.076 元 |

两者都在 ¥0.15 内。

## 六、运行器

`scripts/t0a_run.py` 默认 dry-run，只打印计划；真正联网需同时满足 `--execute`、`DEEPSEEK_API_KEY`、`T0A_BUDGET_APPROVED=1`。运行器内含输入预算、费用上限、实际计费超 1.5 倍即停、length 即停四条硬约束，且无重试分支。

## 七、状态

```
T0_A_preflight_verified
T0_A_runtime_payload_verified
live_llm_execution_pending_explicit_approval
real_output_equivalence_unavailable
```

未联网、未扣费。技术方案已具备执行条件，仍缺项目方账户费用授权。
