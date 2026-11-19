# D4 syntax / definition 双知识映射核验

| 项 | syntax | definition |
|---|---|---|
| fact_id | `f2_12b22d0911565eb5` | `f2_a124817238b02080` |
| aspect | syntax | definition |
| 值 | pattern `4` | text `IP address of next server to use in bootstrap` |
| subject | header / siaddr | 同 |
| Claim | 1 | 1 |
| Evidence | `file:rfc2131.txt#@541` | 同 |

## 核验

- 两条 aspect 不同 ⇒ 未互相覆盖；
- subject 相同但 aspect 不同 ⇒ FactID 不同，非碰撞；
- definition 文本与原文 541 行一致（`IP address of next server to use in bootstrap;`，去掉句末分号）；
- 未添加 MUST / SHOULD，模态为 `optional`（仅影响 epistemic，不产生义务）。

## H2 对照

`f2_f5d4a14e…`（syntax）保持不变，新增 `f2_0732306f…`（definition）。两者身份未互相影响。
