# T0-A 异常停止与证据留存证明

## 一、状态映射

| 触发 | 状态 | 证据 |
|---|---|---|
| 危险根 | `preflight_failed` | 只返回，不写盘 |
| 首批超时 | `request_timeout` | `result.json` + `guard.json`（calls=1） |
| 首批/二批异常 | `request_failed` | 同上，含 `partial_norms` |
| 响应截断（length） | `request_failed`，`reason=FinishReasonError` | 同上 |
| 无 Norm 且无异常 | `response_invalid` 或 `cache_incomplete` | 同上 |
| Canonical 失败 | `canonical_failed` | 不写 Hub |
| Hub 失败 | `hub_failed` | 正式目录不变 |
| 完成前置不满足 | `cache_incomplete` | 记录 calls/expect/failures/stopped/cache_complete |

## 二、持久化方式

- `evidence/guard.json`：每次 `before()` 原子覆盖（`.tmp` + `replace`），含 attempt 序号、预估 token、时间；
- `evidence/result.json`：每条退出路径都写；
- 不记录 Key；`usage` 保存返回的真实值，缺失记 null。

## 三、限制

进程被强杀时的最后一次原子替换不保证完成；已发出未收到响应的请求，费用标 unknown 且不重发。
