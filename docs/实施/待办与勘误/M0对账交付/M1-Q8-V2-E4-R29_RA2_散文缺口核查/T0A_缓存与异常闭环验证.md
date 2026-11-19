# T0-A 缓存与异常闭环验证

脚本：`scripts/t0a_chain_offline.py`，15 项，全部针对真实产物（Norm 条数、缓存 JSON 字段、Fact 对象），不看调用次数。

## 一、正常与缓存（7 项）

| 断言 | 结果 |
|---|---|
| 产出 prose_semantics Norm | PASS（1 条） |
| Norm 带来源与文档 | PASS（source 含 rfc3207） |
| Norm 映射出 Canonical Fact | PASS（aspect=definition） |
| Fact 有 aspect 且 Claim 带 Evidence | PASS |
| 六块完成后写完整缓存 | PASS（complete=true） |
| 缓存 doc_sha256 == 原文 SHA | PASS |
| 同输入二次命中、条目复用 | PASS（0 次调用，Norm 数一致） |

## 二、异常（8 项）

| 场景 | 期望 | 结果 |
|---|---|---|
| 空串 | 不产 Norm、不写完整缓存 | PASS |
| 纯空格 | 同上 | PASS |
| 非法 JSON | 同上 | PASS |
| Schema 不符（items 非数组） | 同上 | PASS |
| `finish_reason=length` | 同上 | PASS |
| 首批成功、二批失败 | 无完整缓存，且只发 2 次请求 | PASS |
| 缓存内 doc 归属错误 | 加载时拒收 | PASS |
| 来源 SHA 冲突 | 不写有效缓存 | PASS |

## 三、本轮补的两处工程缺口

1. **适配器把空内容当成功**：原 `return json.loads(content) if content.strip() else {}` 会返回空 dict，下游可能当作「跑完没抽到」。现改为统一 `validate_response()`：空/空白、非法 JSON、Schema 不符、`finish_reason` 非 `stop` 一律抛错。
2. **链路内隐含重试**：`_extract_blocks` 原本对每批重试 2 次，2 批最坏 4 次请求，与「最多 2 次」冲突。已加 `PROSE_NO_RETRY=1` 开关（默认关闭，不影响生产），T0-A 强制打开。

## 四、弱断言修正

上一轮部分测试只验「Stub 被调用」，本轮全部改为验产物：

- 缓存测试先证正常路径能生成合格缓存，再证异常路径拒绝生成；
- `Fact` 断言从「facts 非空且 aspect 存在」升级为「claims 里有 Evidence 且 document 可回溯」；
- 失败批次的断言同时校验请求次数，防止「静默多调」被算作通过。

## 五、限制

- 仍无真实模型输出，`success_empty` 的真实语义未验证；
- Evidence 的 `locator` 为空，回溯依赖 `document` 行号后缀。
