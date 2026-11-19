# grammar Value 隔离兼容性测试

测试脚本 `scripts/test_grammar_value.py`，8 项，全 PASS：

| # | 断言 |
|---|---|
| 1 | Value(type="grammar", data={rule,expr,deps}) 可构造 |
| 2 | 可序列化，含 rule/expr/deps |
| 3 | deps 顺序保留、重复项未去重（SP 出现两次仍是两条） |
| 4 | `get_fact_view` 保留 `type=grammar` |
| 5 | view 中 expr 与 deps 完整 |
| 6 | 隔离 Hub 接收并可读回 |
| 7 | 读回后 deps 未丢 |
| 8 | 重复构造 FactID 一致 |

## 判定

**A：完全兼容（结构层）**

```
grammar_value_isolated_readback_verified
```

## 必须附带的限定

1. 这是**结构无损**，不是"语义批准"——系统没有类型校验层，grammar 和拼错的 `grammr` 一样会被接受；
2. 测试对象 `provenance=test_constructed`，未进入任何知识集合；
3. subject 仍用 `header`，语法规则的真实主体没有建模范式。
