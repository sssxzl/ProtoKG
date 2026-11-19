# D4 siaddr 结构化知识端到端闭环

## 一、结果：syntax + definition 都落地了

| 项 | 值 |
|---|---|
| 来源 | RFC 2131 第 541 行 `siaddr  4  IP address of next server to use in bootstrap` |
| syntax fact | `f2_12b22d09…`，pattern = `4` |
| definition fact | `f2_a1248172…`，text = `IP address of next server to use in bootstrap` |
| subject | header / siaddr（沿用既有字段类型） |
| Claim | 2 条，各自独立 |
| Evidence | `file:rfc2131.txt#@541`（两条同源） |
| 隔离 Hub 读回 | 4 Fact / 2 实体 |
| 重复构建 | fact_id 两次一致 |

## 二、上一版失败的原因

content 格式写错：`siaddr | 4 | IP address…` 不符合 `syntax | word: semantic` 契约，`parse_field_content` 找不到 `| word:` 分隔点，语义段被丢弃。

改成 `4 | optional: IP address…` 后 definition 正常产出。**这是实现错误，不是契约问题。**

## 三、判定

```
structural_d4_canonical_evidence_verified
```

条件全部满足：Quote 真实（541 行原文）、连续、单段；语义未被映射改写；身份唯一；Claim↔Evidence 关联正确；隔离 Hub 可读回。

## 四、边界

- 来源是结构通道，`channel=structural`，不是 v6 模型输出；
- `optional` 模态词是我加的容器（原文没有 MUST/SHOULD），只影响 epistemic 标记，未添加义务语义。
