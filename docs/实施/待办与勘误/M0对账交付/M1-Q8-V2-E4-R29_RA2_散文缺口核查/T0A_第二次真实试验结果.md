# T0-A 第二次真实试验结果（Prompt v3）

## 一、结论：第一批即被截断，按规则停止

```
status = request_failed
reason = FinishReasonError (finish_reason='length')
calls = 1（第 2 批被门禁拒绝，未发出）
norms = 0
```

失败点不是模型不可用，是**输出被 4000 token 上限截断**。适配器按冻结规则把 `length` 判为失败，守卫随即停掉整次试验，第二批发不出去。

## 二、四段状态

| 段 | 值 |
|---|---|
| llm_call_success | 否（截断） |
| norm_validation_success | 否（0 条） |
| canonical_validation_success | 未执行 |
| hub_integration_success | 未执行 |

## 三、用量与费用

| 项 | 值 |
|---|---|
| 请求次数 | 1 / 2 |
| 输入 token | 4 991（预估 5 038，误差 0.9%） |
| 输出 | 达 4 000 上限被截断 |
| 计费状态 | billed |
| 费用（高峰折算） | ¥0.0420 |
| 累计（含前两次运行） | 高峰折算约 ¥0.118；空闲约 ¥0.058 |

## 四、产物

| 项 | 结果 |
|---|---|
| 缓存 | 未生成（未完整完成） |
| Fact / Claim / Hub | 均未生成 |
| 证据 | `evidence/result.json`、`guard.json` 已落盘 |

失败路径按设计没有留下任何可被误读为完成的东西。

## 五、Gold

未产生任何 Raw 条目，`-30-1`、`-30-2` 无从判定。Prompt v3 是否覆盖到 30-35 行，**本轮没有证据**。

## 六、为什么会被截断

Prompt v3 要求覆盖 Abstract/Introduction 等段落的实质性知识，模型在第一批（5 块、约 1.9 万字符）里产出的条目数量随之上升，4000 token 装不下，`finish_reason=length`。

这是「补充覆盖要求」与「单次输出上限」两个已冻结参数之间的直接冲突。

## 七、可选的下一版参数（需另行批准）

| 方案 | 内容 | 代价 |
|---|---|---|
| A | 批大小 5 → 2（块/次），3 次请求 | 超出现有 2 次上限 |
| B | max_tokens 4 000 → 8 000 | 单次输出上限翻倍，费用上限需重算 |
| C | 保留 v3，但只跑前 2 块 | 覆盖不全，违反试验范围 |

我倾向 B：一次改一个参数，且不突破请求次数上限。

## 八、状态

```
T0_A_second_run_failed_truncated
T0_A_second_live_test_consumed   # 本次 1 次请求已用掉
```

本轮不再发起请求。前序 4 次请求超授权的记录保留，本次为独立授权下的 1 次调用，不追认前者。
