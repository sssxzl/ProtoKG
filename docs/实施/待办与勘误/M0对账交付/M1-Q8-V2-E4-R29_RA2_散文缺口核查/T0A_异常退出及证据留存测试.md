# T0-A 异常退出及证据留存测试（G4）

## 一、状态集合

`preflight_failed / request_failed / request_timeout / response_truncated / response_invalid / source_validation_failed / cache_incomplete / canonical_failed / hub_failed / completed`

当前实现覆盖其中 8 个；`response_truncated` 由适配器 `FinishReasonError` 触发，落到 `request_failed` 并带 `reason=FinishReasonError`；`source_validation_failed` 由缓存来源校验触发，表现为该文档不命中并最终 `cache_incomplete`。

## 二、13 项离线回归

| # | 场景 | 结果 |
|---|---|---|
| 1 | 两批正常 | completed，三段全 true |
| 2 | 第二批失败 | request_failed，`partial_norms` 记录已产出的 Norm |
| 3 | 首批超时 | request_timeout，calls=1 |
| 4 | `finish_reason=length` | 非 completed |
| 5 | 无效 JSON | request_failed |
| 6 | 输入超限 | 请求前拒绝 |
| 7 | 请求数超限 | 网络前拒绝 |
| 8 | 缓存写失败 | 无完整缓存 |
| 9 | Canonical 失败 | canonical_failed，不写 Hub |
| 10 | Hub 失败 | hub_failed，正式目录不变 |
| 11 | 正常后隔离 Hub 可读回 | PASS |
| 12 | 证据含 fact_ids 与 doc_sha256 | PASS |
| 13 | 部分失败不得 completed | PASS（专用断言） |

## 三、证据落盘

- `evidence/result.json`：状态、调用数、usage、fact_ids、doc_sha256、失败原因；
- `evidence/guard.json`：每次尝试的时间、预估 token、累计；
- 写入用 `.tmp` + `replace`，避免半个 JSON。

## 四、限制

1. 进程被 `kill -9` 时，最后一次原子替换可能未发生——不声称系统级崩溃一定留痕；
2. 已发出但无响应的请求，记 `request_timeout` 且不重发，计费状态标为未知；
3. Key 不写日志（证据只存 usage 与状态）。
