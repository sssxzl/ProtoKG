# T0-A 请求前门禁与无重试验证（G1）

## 一、门禁位置

`t0a_executor.Guard.before()` 在**真实客户端调用之前**执行，`GuardedClient` 包住任意 client，因此链路里每次实际调用都要过它。

检查顺序（任一不满足即抛错，被包住后不会发出请求）：

1. 状态已停止 ⇒ `state_stopped`
2. 已用调用数 ≥ 2 ⇒ `call_limit_exceeded`
3. 累计输入 + 本次估计 > 7 500 ⇒ `input_limit_exceeded`
4. 最坏费用 + 已花 > ¥0.15 ⇒ `cost_limit_exceeded`
5. 参数（model / thinking / response_format / max_tokens=4000）不符 ⇒ `PayloadError`

## 二、无重试

| 层 | 处理 |
|---|---|
| 链路内 | `PROSE_NO_RETRY=1`，`_extract_blocks` 只尝试 1 次 |
| 适配器 | `T0AClient` 无重试分支 |
| 执行器 | 失败即 `guard.stop()`，后续请求在 `before()` 被拒 |
| SDK | 未使用 SDK，`urllib` 单次请求，无隐式重试 |

## 三、验证

| 断言 | 结果 |
|---|---|
| 正常两批恰好 2 次 | PASS |
| 请求数已满时第 3 次在网络前被拒 | PASS（`call_limit_exceeded`） |
| 超时后不再发第二次 | PASS（`request_timeout`，calls=1） |
| 输入超限在网络前被拒 | PASS（`input_limit_exceeded`） |

## 四、计费口径

门禁用 `len(user)//4` 估输入，只作**预检**；真实停止判断用返回的 `usage`：`Guard.after()` 累计实际 token，并置 `spent`。若实际输入超过预估 1.5 倍，立即 `stop()`，不再发下一次。

估计值不会被当作计费值写进费用结论。
