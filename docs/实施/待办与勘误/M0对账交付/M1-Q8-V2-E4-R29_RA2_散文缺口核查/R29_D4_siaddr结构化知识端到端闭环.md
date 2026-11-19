# D4 siaddr 结构化知识端到端闭环

## 一、做到了什么

用 `field` Norm 走既有 `map_norm_to_facts`，产出 1 条 Fact：

| 项 | 值 |
|---|---|
| fact_id | `f2_12b22d0911565eb5` |
| aspect | `syntax` |
| subject | header / siaddr |
| claim | `c2_f57cc9c278f74c83` |
| Evidence | `rfc:@file:rfc2131.txt#@541` |
| 隔离 Hub 读回 | 2 Fact / 2 实体（D4+H2） |
| 重复构建 | 身份稳定（两次 fact_id 一致） |

原文 541 行：`siaddr  4  IP address of next server to use in bootstrap;`

## 二、没做到的

**只产出了 syntax(syntax=pattern "4")，definition 没出来**——字段语义"IP address of next server"没进 Fact。

原因：`parse_field_content` 对 content 的切分与我的构造不一致，语义段被当成了 pattern 的一部分/丢弃。

所以准确状态是：

```
structural_d4_syntax_verified
structural_d4_definition_blocked
```

不能登记 `structural_d4_canonical_evidence_verified`——语义那一半没进去。

## 三、修法（未执行）

按 `field` Norm 既有 content 格式重写（syntax 段与语义段用既有分隔符），再跑一次；
不需要改任何契约，是我构造 Norm 的格式不对。
