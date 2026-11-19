# T0-A 审批复核回应

> 复核日期：2026-11-19（项目方）
> 本文件只回应「正式执行前的最后条件」1-3；第 4 条为签署，仍待项目方。

## 一、条件 1：可复算的预检脚本

| 项 | 内容 |
|---|---|
| 脚本 | `scripts/t0a_preflight.py`（零 LLM 调用） |
| 命令 | `python t0a_preflight.py --out t0a_evidence.json` |
| 输出 | 6 块身份、2 条 Gold 归属、全文重建校验、完整请求 token、两批计划 |

复算结果：

| 项 | 值 |
|---|---|
| 块数 | 6 |
| 全文重建一致 | `True`（`len("\n".join(blocks)) == len(text) == 18 679`） |
| Gold 覆盖 | 2/2（均在块 1，行 1-114） |
| 累计 token | 5 958 |
| 阈值 7 500 | 满足 |

批明细：批 1（块 1-5）19 307 字符 / 4 924 token；批 2（块 6）2 385 字符 / 1 034 token。

上一版 `t0a_evidence.json` 由临时脚本生成、无对应源码，本条件已补齐。

## 二、条件 2：清单循环引用

原来清单列入「除自己以外的所有文件」，但侧车文件内容又依赖清单 ⇒ 二者互相引用。现改为：

- 清单与侧车**都不进入** `outputs`，并在 `excluded` 字段显式列出；
- 侧车只保存清单自身 SHA256；
- 新增 `scripts/verify_manifest.py` 校验。

校验结果：

```
checked=49 mismatches=0 sidecar_ok=True
```

## 三、条件 3：非思考模式与离线 Token 计数

### 3.1 Token 计数（已完成）

用 `tiktoken` 的 `cl100k_base` 编码对**完整请求**（system + user prompt + 每块头部 + 块正文）计数，结果 5 958，见 `t0a_evidence.json` 的 `batches`。

必须注明：这是近似计数，不是 DeepSeek 官方 tokenizer；两者可能有 ±10% 偏差。原按 3.5 字符/token 估的 6 200 与实测 5 958 相差 3.9%，方向一致。阈值 7 500 留有 26% 余量。

### 3.2 非思考模式（未完成，阻断）

核查 `core/llm.py` 的请求载荷，字段只有：

```json
{"model", "messages", "temperature", "max_tokens", "response_format"}
```

**没有任何 thinking / reasoning / reasoning_effort 开关。** 适配器无法显式关闭思考。

而代码注释自己写明（`core/llm.py:301-306`）：「deepseek-flash 是推理模型，reasoning_tokens 会先吃掉 max_tokens；给 4000 时实测 finish_reason=length」。

后果：T0-A 规定的 2 000 token 单次输出上限，可能全部被推理消耗，返回空内容或截断。这不是预算问题，是**输出能力问题**。

三个可选处置（都需项目方定）：

| 选项 | 内容 | 代价 |
|---|---|---|
| A | 提高单次 max_tokens（如 4 000），预算按最坏重算 | 输出费用上限从 0.032 元升至 0.064 元，仍在 0.15 元内 |
| B | 换非推理模型（如 deepseek-chat 非 flash） | 需确认该模型是否仍然可用、价格是否不同 |
| C | 保持 2 000 并接受可能空输出 | T0-A 可能无法产出任何知识，白花一次调用 |

在选定之前，`live_llm_execution_pending_explicit_approval` 继续有效。

## 四、条件 4：签署

审批单已按复核意见更新三项（官方直连、CNY 0.15、`deepseek-flash`），签署栏留空。本文件不构成授权。

## 五、状态

```
T0_A_preflight_verified
live_llm_execution_pending_explicit_approval
non_thinking_mode_unavailable   ← 本轮新增阻断
```
