# T0-A 散文 Norm 身份冲突修正结果

## 一、结论

Norm 层修好了：22 条真实 Raw 全部保留，9 条此前被合并的规则全部回来。
Fact 层仍有合并：22 条 Fact 只有 19 个不同 fact_id，命中「Norm 已区分、Fact 仍合并」的情况，按审批要求报告而不改 FactID。

```
T0_A_prose_norm_identity_verified
T0_A_second_live_test_preflight_failed_factid_collision
```

## 二、身份规则

```
{kind}_{entity}.{rule_slot}
rule_slot = sha256(canonical_json({v, subject, action, object,
                                   condition, exception, polarity, strength, text}))[:12]
```

- 版本：`prose-rule-slot-v1`
- 序列化：`json.dumps(sort_keys=True, separators=(",",":"))`，UTF-8
- 排除：文档名、行号、批次、数组下标
- `name` 字段未改，仍是实体名

## 三、还改了一处去重键

原去重键是 `(kind, entity.lower())`，与 norm_id 无关，所以只改 norm_id 不会生效。改为 `(kind, entity.lower(), rule_slot)`。

这是本次「修了不生效」的第一现场：先改 norm_id、回放仍是 13 条，才发现去重发生在更早的地方。

## 四、22 条逐项去向

| 指标 | 修正前 | 修正后 |
|---|---|---|
| Norm | 13 | 22 |
| Fact | 13 | 22 |
| Aspect | definition 13 | legal_boundary 14 / definition 8 |
| Subject | header 13 | actor 16 / protocol 6 |
| 重点行 88/94/146/158/214/217/231/232/341 | 全丢 | 全部保留 |

逐条对照见 `T0A_身份修正_逐条去向.csv`。

## 五、Fact 层碰撞（阻断项）

| fact_id | 涉及 span | 情况 |
|---|---|---|
| `f2_35eb41cad94db68b` | 76 / 88 / 94 | 三条 STARTTLS「定义」同 subject+aspect+condition ⇒ 同 id（可视为同一实体的多个 claim，不是错误丢失） |
| `f2_6ebb9b8192ed2599` | 127 / 146 | **两条不同义务**（MUST 要求 STARTTLS 才能本地投递 vs SHOULD 返回 530）撞同一 id |

第二条是真正的问题。原因：这两条 `subject_status=unresolved`，走兜底分支，`Subject` 不带 `qualifiers`（action/object），而 FactID 由 subject+aspect+condition 计算 ⇒ 主体相同即撞。

8 条 Norm 的 `subject_status=unresolved`，都存在这个风险。

## 六、为什么不动 FactID

审批写明「不自动扩大到 FactID 算法修改」。改 FactID 需要把 qualifiers 或 value 摘要纳入哈希，影响全部历史 FactID，属于契约级变更。

可在契约内做的备选（需另行批准）：

| 选项 | 内容 | 影响 |
|---|---|---|
| D | 兜底分支也填 `qualifiers`（action/object） | 可能已足够：FactID 若含 qualifiers 就会分开 |
| E | 兜底分支把主体名细化为「主体+动作」 | 改 name 语义，不建议 |
| F | 接受合并 | 两条义务只留一条，不建议 |

选项 D 值得先验证：先看 `compute_fact_id` 是否真的用了 qualifiers。若用了，D 就能在不碰算法的前提下解决。

## 七、状态与建议

- Norm 身份：已验证，可登记 `T0_A_prose_norm_identity_verified`；
- 第二次真跑：**不建议放行**，先定 D；
- 本轮 0 次调用、0 元。

## 八、补充：尝试 D 后的实测（仍未闭合）

按选项 D 在兜底分支补了 `qualifiers`（action/object），回放结果仍是 22 Fact / 19 唯一 id。打印两条碰撞条目的 FactKey：

```
span 127 status=unresolved type=actor quals={} aspect=definition
span 146 status=unresolved type=actor quals={} aspect=definition
```

两条都落在 `definition`、且 qualifiers 为空——说明它们没有走 `legal_boundary` 的 Rule Slot 分支，而是走了「action/object 缺失或等于主体」的兜底。D 只改了 Rule Slot 侧，改不到这里。

进一步核验：这两条的 `constraint` 字段确实非空（`MUST NOT require use of the STARTTLS…`、`SHOULD return the reply code 530…`），却仍被判为 `definition`，说明 `kind` 判定或 Rule Slot 的进入条件与预期不一致。根因尚未定位，本轮时间不足以安全修改。

## 九、结论与建议

| 项 | 状态 |
|---|---|
| Norm 身份（22 条全保留） | 已验证 |
| Fact 身份（19/22） | 未闭合，2 组碰撞 |
| 第二次真跑 | **不放行** |

建议下一步（需批准）：定位 `kind` 判定与 Rule Slot 进入条件为何把带 action/object 的约束判成 `definition`。这是明确、可测的单点问题，不需要动 FactID。
