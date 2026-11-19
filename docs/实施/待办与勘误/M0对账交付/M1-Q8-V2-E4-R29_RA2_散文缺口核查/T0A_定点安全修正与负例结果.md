# T0-A 定点安全修正与负例结果

## 一、五组修正

| 组 | 原问题 | 修正 |
|---|---|---|
| 1 隔离根 | `resolve()` 后再查 `..`/符号链接不可靠 | 改为 resolve **之前**查原始路径：绝对路径、`..`、逐级父目录符号链接、受保护目录（`derived`/`kb`/`profiles`/`.git`）一律拒绝，返回 `preflight_failed` |
| 2 参数 | 校验前把 `max_tokens` 替换成常量，真实值没被检查 | 去掉替换，直接 `assert_payload_ok(params)`；补完成前置：批次数、`stats.failures`、`guard.stopped`、缓存 `complete` 四项全过才写 `completed` |
| 3 证据 | 失败时 `guard.json` 不落盘 | `Guard.before()` 内每次尝试即原子写 `guard.json`；所有失败分支同时写 `result.json` |
| 4 序列化 | `asdict` 后 `pop("claims")`，Evidence 丢失；全部写 `definition.jsonl` | 改用官方 `get_fact_view`（`fact_key`/`resolution`/`all_claims`），按 `fact_key.aspect` 分文件 |
| 5 状态恢复 | 只改不还 | `run()` 外层 `try/finally` 恢复 `PS._cache_path`、`PS._MAX_TOKENS`、`PROSE_NO_RETRY`、`PROSE_BATCH_BLOCKS`；Hub 路径由 `isolated_hub` 的 finally 负责 |

## 二、18 项负例与回归（`t0a_executor_checks2.py`）

| 组 | 断言 | 结果 |
|---|---|---|
| 1 | 相对路径 / 含 `..` / 受保护 `derived` 拒绝 | 3 PASS |
| 1 | 符号链接根拒绝（Windows 无权限，用 `is_symlink` 替身验证分支） | PASS |
| 2 | `max_tokens=8000` 在调用前被拒 | PASS |
| 2 | 第二批被门禁拒绝 ⇒ 非 completed、不建 Hub、无完整缓存 | 3 PASS |
| 3 | 超时后 `result.json` 与 `guard.json` 都在，`calls=1`，状态 `request_timeout` | 3 PASS |
| 4 | 落盘含 `all_claims`；证据摘要含 `@file:rfc3207.txt#@` | 2 PASS |
| 4 | 字段 Norm 产出两个 aspect（definition/syntax）并分文件 | PASS |
| 5 | 异常后 `PS._MAX_TOKENS`、`PROSE_NO_RETRY` 复原 | 2 PASS |
| 6 | 正常执行 fact ≥1、实体 ≥1 | PASS |

原 13 项执行器测试与 5 套既有离线测试（F2 v2/v3、载荷、链路、Hub）全部通过。

## 三、必须说明的边界

1. 官方 Hub 视图只保存 `evidence_summary`（形如 `rfc:<norm_id>@file:rfc3207.txt#@80`），**不持久化完整 Evidence 对象**。因此能回溯到文件与行号，但不是完整证据字段。
2. `Fact` 的官方 JSONL 键是 `all_claims`，不是 `claims`；用 `asdict` 会得到错误契约，这也是原实现丢证据的根因。
3. Windows 上无法创建符号链接，该分支用替身验证，不是真实文件系统行为。
