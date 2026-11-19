# T0-A 第二次真实试验前置检查与暂停说明

## 一、结论：暂停真实调用，保留阻断

前置检查发现**不同规范义务被同一 Norm 身份合并**，9/22 条真实 Raw 条目在 Norm 层消失。按审批条件「若现有身份契约无法安全保留这些不同规则，保留阻断，暂停真实调用」，本轮未发起请求。

## 二、Prompt 已按批准修正并冻结

| 项 | 值 |
|---|---|
| 版本 | `prose-semantics-v3` |
| 字符 | 1 508（原 1 371） |
| SHA256 | `84cc0e5b5f4379ac…` |
| 新增条款 | 覆盖 Abstract / Introduction 等段落的实质性知识（能力、用途、安全属性、定义、行为、约束），不得只抽标题后的正文 |
| 未改 | JSON Schema、模型、thinking=disabled、max_tokens、21 aspects |

快照与补丁：`T0A_第二次前置_prompt_v3.txt`、`T0A_prompt_v3修正.patch`。

## 三、Raw → Norm → Fact 对照（22 条）

| 结果 | 条数 |
|---|---|
| Raw 条目 | 22 |
| 产出 Norm | 13 |
| 丢失 | 9 |

丢失条目（全部有 constraint + action + object）：

| span | entity | 说明 |
|---|---|---|
| 88 / 94 | STARTTLS | 与 76 行同实体，identity 冲突 |
| 146 | SMTP server | 与 127 行同实体 |
| 158 / 214 / 217 / 231 | client | 与 155 行同实体，四条不同义务 |
| 232 | server | 与同实体较早条目冲突 |
| 341 | clients and servers | 同上 |

## 四、根因

`_extract_blocks` 的 Norm 身份是 `{protocol}.{kind}.{name}`（`_norm()` 里拼），`name` 取实体名。同一实体在一份 RFC 里出现多条不同规范时，后到的条目因 `norm_id` 相同被 `seen` 去重丢弃。

结果：**实体越常见，丢的规则越多**——`client` 出现 5 次，只留 1 条。

## 五、为什么不能在"现行契约内"直接修

| 方案 | 问题 |
|---|---|
| 改 NormID 算法（把 action/object 拼进 id） | 违反「不得改变冻结的 NormID 算法」 |
| 把 action 拼进 name | 改的是 name 语义，FactID 的 subject.name 随之变化，等价于改身份 |
| 一个 Norm 存多条规则 | 映射函数一次只产一个 Fact，仍丢 |
| 按 kind 细分（prose_constraint_client…） | 等于按实体扩展 kind，破坏 kind 语义 |

四个方案都触碰冻结项，所以按审批要求**停下**，不硬修。

## 六、提请决策（三选一）

| 选项 | 内容 | 代价 |
|---|---|---|
| A | 批准一次「NormID 增加 rule_slot 摘要」的契约变更 | 需改 ID 算法，影响面最大 |
| B | 批准把 action/object 并入 name（如 `client#abort_connection`） | 不改算法，但改变 name 语义；新知识身份与原实体不同 |
| C | 接受当前合并（每条实体只保留首条规则） | 知识大量丢失，不建议 |

## 七、对 Gold 的影响

两条 Gold（30-35）与本次冲突无关：模型仍无该段输出，Prompt v3 是否改善只能靠真实调用验证。也就是说，即使解决 identity 冲突，Gold 仍可能 0/2。

## 八、状态

```
T0_A_prompt_v3_frozen
T0_A_second_run_blocked_identity_collision
```

本轮 0 次请求、0 元。上一轮超授权的 4 次请求事实保留，未被本次追认。
