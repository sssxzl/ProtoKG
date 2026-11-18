# R24 LLM 事件与预算停止门禁

> ★ 本轮实际 LLM 调用 **0 次** ｜★ USD 0.00
> ★ FTP 单轮预算建议 USD 0.20（★ 计入既有 USD 5.00 总预算）

---

## 一、已验证事实

### 1.1 事件持久化能力

| 项 | 现状 | 证据 |
|---|---|---|
| ★ `LLMDiagnostics` 类 | ★ 存在 | ★ `llm_diagnostics.py:92` |
| ★ `flush()` | ★ 存在，★ 落 `<run_id>.jsonl` + `<run_id>_summary.json` | ★ `llm_diagnostics.py:116` |
| ★ ★ 写失败行为 | ★ **返回 None 不抛**（★ 符合「诊断写入失败不得使成功的抽取变成失败」） | ★ `llm_diagnostics.py:128-134` |
| ★ 记录字段 | ★ 30 个（★ 含 run_id、protocol、document、chunk_id、source_span、model、prompt_digest、cache_hit、cache_key、attempt、input_tokens、output_tokens、finish_reason、error_stage、error_type、raw_response_sha256、outcome 等） | ★ `llm_diagnostics.py:53-88` |
| ★ ★ 生产接线 | ★ ★ **`build_hub.py` 从不传 `diagnostics=`** ⇒ ★ 生产路径**零诊断** | ★ `prose_semantics.py:1460,1480` 的默认参数为 None |

### 1.2 三类事件是否分开

| 事件 | 是否有独立计数 | 证据 |
|---|---|---|
| ★ `actual_llm_request` | ★ 有 | ★ `R3_抽取汇总.json` 的同名字段 |
| ★ `cache_hit` | ★ 有 | ★ 同上 |
| ★ `local_replay` | ★ 有 | ★ 同上 |
| ★ retry | ★ 有 | ★ 同上 |
| ★ request_failure / batch_failure / block_failure | ★ 有 | ★ 同上 |

★ ⇒ ★ **事件模型本身完备**；★ ★ **缺的是生产接线**。

### 1.3 失败请求是否进入事件台账

★ `LLMCallRecord` 有 `error_stage` / `error_type` / `error_message` 字段；
★ 错误阶段常量含 `STAGE_REQUEST` / `STAGE_RESPONSE` / `STAGE_JSON_PARSE` /
★ `STAGE_SCHEMA` / `STAGE_MAPPING`（★ `llm_diagnostics.py:29-33`）。

★ ★ **但 `STAGE_MAPPING` 的记录不计入 `llm_calls`**（★ `llm_diagnostics.py:149-150`）
⇒ ★ **映射阶段失败只体现在 summary 的计数里，★ 不在逐条事件里** ⇒ ★ **不可完全重算**。

### 1.4 缓存是否绑定 RFC 来源版本

| 项 | 现状 |
|---|---|
| ★ 缓存键要素 | ★ prompt_version、★ prompt_digest、★ model、★ model_snapshot、★ inference、★ parser_version、★ schema_version、★ verifier_version、★ input_fingerprint（★ `cache_key.py:66-74`） |
| ★ ★ 来源版本绑定 | ★ ★ `input_fingerprint` 是**块文本指纹**，★ **不是 RFC 文件的 SHA256** ⇒ ★ ★ **RFC 文件被替换但文本块相同则缓存仍命中** |
| ★ 缓存路径 | ★ `derived/cache/source_blocks/<protocol>.prose.json`（★ 按协议，★ 不按文档） |

### 1.5 请求数、块数、token、费用能否由事件重算

| 项 | 可重算？ | 依据 |
|---|---|---|
| ★ 请求数 | ★ **可** | ★ `actual_llm_request` 逐条计数 |
| ★ 块数 | ★ **可** | ★ 逐条 `chunk_id` / `source_span` |
| ★ token | ★ **可** | ★ 逐条 `input_tokens` / `output_tokens` |
| ★ 费用 | ★ **可** | ★ 费用 = token × 项目费率（★ `extract_runner.py:26-27,97`） |
| ★ ★ 映射阶段失败 | ★ ★ **不可完全重算** | ★ 不在 llm_calls 内 |
| ★ ★ 历史 H2/H3 | ★ ★ **不可** | ★ 沿用既有结论：★ 保持 `unavailable`，★ **不补造** |

### 1.6 预算接近与超出阈值是否 fail-closed

| 项 | 现状 | 证据 |
|---|---|---|
| ★ 单批费用闸 | ★ **有**（★ `extract_runner.py:117-118`） | ★ `if new_cost > LIMITS["max_cost_usd"]: reasons.append(...)` |
| ★ 累计闸 | ★ **有**（★ `:108,117`） | ★ `used_cost = sm["cost_usd"]` |
| ★ ★ 生产路径 | ★ ★ **未接线**（★ 生产不走 `extract_runner.py`） | ★ `build_hub.py` 路径不同 |
| ★ ★ 通用成本闸 | ★ ★ **死代码** | ★ `block_budget.py` 全仓零 import；★ `PROSE_MAX_CALLS` / `PROSE_MAX_TOKENS` / `PROSE_COST_PER_1K` **无读取点** |
| ★ ★ 隔离负例测试 | ★ ★ **不存在** | ★ 无针对「预算超限 ⇒ 停止」的测试 |

★ ⇒ ★ **★ 硬停止机制目前只存在于 R3 的抽取脚本，★ 且从未做过隔离负例测试。**

---

## 二、★ 门禁方案（★ 供下一轮执行审批时使用）

| # | 要求 | 现状 | 须补 |
|---|---|---|---|
| 1 | ★ 事件持久化可用 | ★ 能力完备 | ★ ★ **生产/FTP 抽取脚本须显式传 `diagnostics=`** |
| 2 | ★ 三类事件独立留痕 | ★ 模型完备 | ★ 确认 FTP 抽取脚本启用 |
| 3 | ★ 缓存绑定来源版本 | ★ **不足** | ★ ★ 缓存键须纳入 RFC 文件 SHA256 |
| 4 | ★ 失败请求进入台账 | ★ 部分（★ 映射阶段缺） | ★ 映射失败也须落逐条事件 |
| 5 | ★ 统计可由事件重算 | ★ 除映射阶段外可 | ★ 同上 |
| 6 | ★ 阈值接近/超出 fail-closed | ★ 仅 R3 脚本有 | ★ ★ **须在 FTP 抽取脚本实现并做隔离负例测试** |
| 7 | ★ 单轮硬上限 | ★ 建议 USD 0.20 | ★ 计入既有 USD 5.00 总预算 |

---

## 三、★ 隔离负例测试设计（★ 待实施）

| # | 负例 | 期望 |
|---|---|---|
| 1 | ★ 模拟累计费用达到 USD 0.20 | ★ ★ 下一批**被拒绝**，★ 且事件中留下拒绝记录 |
| 2 | ★ 模拟 token 累计超限 | ★ 同上 |
| 3 | ★ 模拟 `flush()` 写盘失败 | ★ 抽取**仍成功**，★ 且有独立错误证据 |
| 4 | ★ 模拟 RFC SHA256 变更但块文本相同 | ★ 缓存**须失效**（★ 当前不失效） |
| 5 | ★ 模拟映射阶段失败 | ★ 该条须出现在逐条事件中（★ 当前缺失） |

★ ⇒ ★ **★ 这五项负例当前均无测试；★ 硬停止的可信度尚未被证明。**

---

## 四、限制

1. ★ 本轮 0 次调用；★ 上述结论全部来自**静态源码阅读与既有产物**（★ R3 的抽取汇总与诊断文件）。
2. ★ 未在真实调用上验证任何门禁。
3. ★ H2/H3 的历史数据保持 `unavailable`，★ 未补造。
