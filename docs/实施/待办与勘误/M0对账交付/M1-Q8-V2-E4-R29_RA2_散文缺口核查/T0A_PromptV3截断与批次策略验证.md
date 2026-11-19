# T0-A Prompt v3 截断与批次策略验证

## 一、参数契约变更

| 项 | 值 |
|---|---|
| 变更 | `max_tokens` 4 000 → 8 000 |
| 版本标识 | `t0a-params-r2` |
| 同步位置 | `t0a_adapter.MAX_TOKENS`、`t0a_executor.MAX_TOKENS`、`Guard.before` 实参校验、`assert_payload_ok`、`PS._MAX_TOKENS` |
| 未改 | Prompt v3 内容、模型、thinking=disabled、批大小 5+1、Schema、aspects |

`assert_payload_ok` 现在比对真实常量 8 000，不再接受调用方任意值。

## 二、离线验证（Stub）

| 断言 | 结果 |
|---|---|
| `max_tokens=8000` 通过全部请求前校验 | PASS |
| `max_tokens=9999` 在调用前被拒 | PASS |
| `finish_reason=length` 仍判失败 | PASS |
| 首批失败后第二批不发出 | PASS |
| 失败时已收 usage 仍保存 | PASS |
| 未完成响应不写完整缓存 / Fact / Hub | PASS |

`t0a_payload_checks`、`t0a_executor_checks`、`checks2`、`checks3` 全部通过（参数改为 8 000 后）。

## 三、真实运行

| 项 | 值 |
|---|---|
| 状态 | `completed` |
| 请求 | 2（5 块 + 1 块） |
| 输入 | 5 965 token |
| 输出 | 4 539 token（< 8 000，未截断） |
| Norm / Fact | 30 / 30 |
| 实体 | 14 |

结论：8 000 足以容纳 v3 下的单批输出；5+1 的批安排可保留，无需降为 2+2+2。
