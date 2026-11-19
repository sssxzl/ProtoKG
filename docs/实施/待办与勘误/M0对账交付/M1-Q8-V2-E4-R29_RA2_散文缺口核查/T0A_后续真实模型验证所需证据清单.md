# T0-A 后续真实模型验证所需证据清单

真实调用（获批后）必须逐项落盘，缺一项即视为该次运行不完整。

## 一、请求侧

| 证据 | 说明 |
|---|---|
| 完整请求 JSON | 含 model、messages、max_tokens=4000、thinking.type=disabled、response_format |
| 载荷断言结果 | `assert_payload_ok` 通过记录 |
| 请求序号与时间 | 第 1/2 次，本地时间与 UTC |
| 输入字节/token | 请求体大小 + tiktoken 计数 |

## 二、响应侧

| 证据 | 说明 |
|---|---|
| 原始响应全文 | 未截断，另存 SHA256 |
| `finish_reason` | 必须为 stop；length 即判失败 |
| usage | prompt_tokens / completion_tokens / 总 token |
| 解析结果 | items 条数、每条 doc/entity/span |
| 拒收原因 | 若被 schema 或来源校验拒收，记录具体字段 |

## 三、产物侧

| 证据 | 说明 |
|---|---|
| Norm 列表 | 每条 norm_id、kind、source、span_line |
| Fact/Claim/Evidence | fact_id、aspect、evidence_id、document |
| 缓存文件 | 每文档 key、doc_sha256、block_sig、complete、status |
| 二次运行 | 命中文件数、真实请求数（应为 0） |

## 四、成本侧

| 证据 | 说明 |
|---|---|
| 每次费用 | 按实际 usage × 单价 |
| 累计费用 | 与 ¥0.15 上限比较 |
| 停止原因 | 若触发预算/失败停止，记录触发点 |

## 五、Gold

| 项 | 说明 |
|---|---|
| 两条 Gold | `-30-1`（30-33）、`-30-2`（33-35） |
| 判定 | hit / partial_hit / miss / not_in_scope / invalid_evidence |
| 禁止 | 用 Stub 结果冒充真实命中 |

## 六、隔离

| 项 | 说明 |
|---|---|
| 正式基线快照 | 运行前后 63/107/92 与 82/152/99 |
| 写入范围 | 仅临时目录；正式 `derived/` 未被写 |
