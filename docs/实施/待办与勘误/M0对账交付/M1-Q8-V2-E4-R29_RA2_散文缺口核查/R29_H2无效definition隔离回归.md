# H2 无效 definition 隔离回归

| 检查 | 结果 |
|---|---|
| 已验证集合是否含 `f2_0732306f…` | **否** |
| 侧车标记 | `provenance=test_constructed`、`verified=false` |
| 正式查询是否返回它 | 否（不在任何 verified 列表） |
| 导出是否重新包含 | 否（`structural_closure.json` 中已标 false） |
| H2 syntax `f2_f5d4a14e…` | 未变 |

## 说明

该条仍保留在隔离产物中，用于错误审计；但任何"已验证知识"统计都排除它。

## 教训

`authority=rfc` 不等于"文本来自 RFC"。以后 definition 的 text 必须先做原文匹配，匹配不到就只能进侧车说明。
