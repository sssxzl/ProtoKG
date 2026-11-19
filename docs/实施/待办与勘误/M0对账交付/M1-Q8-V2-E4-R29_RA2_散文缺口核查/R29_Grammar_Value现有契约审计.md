# grammar Value 现有契约审计

## 一、静态结论

| 检查点 | 实现 | 结论 |
|---|---|---|
| `Value.type` 定义 | `core/fused/hub/models.py:24` `type: ValueType` | — |
| `ValueType` 类型 | `models.py:17` `ValueType = str` | **不是封闭枚举**，是字符串别名；注释列了 12 种，但运行时不校验 |
| Schema 校验 / 白名单 | 无（`canonical_serialize` 注释明说"本函数不做类型检查"） | 未知 type 静默通过 |
| 序列化 | `canonical_serialize`：`json.dumps(sort_keys=True)` | 与 type 无关，保留任意结构 |
| FactID | `compute_fact_id(fact_key)`，**不含 Value** | grammar 不影响身份 |
| ClaimID | `compute_claim_id` 用 `claim.value` 的规范序列化 | **会受 value 内容影响** |
| `get_fact_view` | `{"type": v.type, "data": v.data}` 原样透传 | 无损 |
| Hub 存取 | 读写 JSON 行，无 type 过滤 | 无损 |

## 二、四个问题

1. **grammar 是否被接受**：是，但属于"未注册值"——因为根本没有注册表。
2. **是否静默降级 text**：否。
3. **是否被过滤/截断**：否。
4. **对身份的影响**：FactID 不受影响（不含 value）；ClaimID 受影响（含 value 序列化），但这是设计如此。

## 三、真正需要扩展的是什么

不是 Schema，也不是映射器或读取器——**是一个类型校验层**。现在的问题不是"接不住"，而是"什么都接"，包括拼错的 type。

这让本轮兼容性测试的结论必须打折：**结构无损 ≠ 语义合规**。
