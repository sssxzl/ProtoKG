# R4B 生产代码与下游引用分析

## 一、已验证事实

### 1.1 norm_id 的构造

`core/fused/extraction/prose_semantics.py:1208`：

```python
"norm_id": f"{kind}_{ent.lower().replace('-', '_')}",
```

构造式准确：是 `kind` 加 `entity` 的小写形式，**不含文档、协议、跨度或任何隐式来源上下文**。

`core/fused/extraction/rfc_extractor.py:1074` 的构造式不同，为 `f"{protocol}.{kind}.{name.lower()...}"`。

### 1.2 norm_id 在下游的用途

| 位置 | 用途 | 影响 |
|---|---|---|
| `core/fused/extraction/norm.py:35` | `source_id=norm.get("norm_id", "")` 传入 `Evidence` | ★ evidence_id 由 source_type 加 source_id 加 locator 计算 ⇒ ★ **norm_id 重复会使 evidence_id 重复** |
| `core/fused/extraction/prose_semantics.py:1185` | `_dedup_key = (kind, ent.lower())` 加局部 `seen` 集合 | ★ **去重键与 norm_id 同构** |
| `core/fused/extraction/rfc_extractor.py:1709` 等 | `if n["norm_id"] in seen_ids: return` | ★ **作用域为单份文档内**，且只作用于 field 类 norm |

### 1.3 去重的实际作用域

`prose_semantics` 的 `seen` 集合是单次 `_extract_blocks` 调用内的局部变量。因此：

1. 同一批次内同 kind 同 entity 的候选被去重。
2. **不同批次之间的同 key 候选不被去重**，会同时保留。

这解释了 H1 中同一 block 内出现多条同 entity 记录的现象：它们来自不同的 LLM 调用批次。

### 1.4 碰撞复算

| 集合 | 记录数 | 唯一 norm_id | 碰撞组数 | 碰撞记录数 |
|---|---:|---:|---:|---:|
| R3 | 57 | 55 | 1 | 3 |
| H1 | 156 | 116 | 16 | 40 |

R3 的碰撞组 `prose_constraint_server` 跨 3 份文档（rfc1870、rfc2543、rfc7826），组内 3 条的语义载荷哈希**各不相同**。

H1 的 16 个碰撞组中，**没有任何一组包含语义载荷完全相同的记录**。

### 1.5 记录完整性

`frozen_blocks.jsonl` 的 `raw_items` 总数为 156，与记录的候选总数一致。`drop_counts` 汇总中 `duplicate` 为 0，说明写入时未按 norm_id 去重。

## 二、影响分类

| 类别 | R3 | H1 | 判定依据 |
|---|---:|---:|---|
| A 标识符重复但记录与语义完整保留 | 0 | 0 | —— |
| B 标识符重复产生引用歧义 | 1 | 16 | ★ 组内语义载荷不同，★ 但均未进入 canonical Fact 空间，★ 无引用指向歧义目标 |
| C 发生记录覆盖、错误合并或来源误关联 | 0 | 0 | ★ 记录数与产出数一致，★ 无覆盖 |
| D 证据不足标记 unresolved | 0 | 0 | —— |

## 三、推论

1. 碰撞目前**没有造成记录丢失**。156 条 raw_items 全部保留，组内成员语义载荷互不相同。
2. 碰撞会造成**证据关联歧义**。`norm.py:35` 把 norm_id 作为 `source_id` 传入 `Evidence`，evidence_id 由 source_type 加 source_id 加 locator 计算。当两条不同命题共享 norm_id 且 locator 相同时，evidence_id 会重复。
3. H1 的问题比 R3 严重：40 条记录涉及 16 个碰撞组，R3 只有 3 条。

## 四、限制

1. 本审计未取得真实的 canonical Fact 视图。**不能声明 canonical 无损，也不能声明 canonical 损坏**。事实是：这些记录未进入 canonical Fact 空间（R3 为 shadow/proposed，H1 的 canonical FactID 未随记录保存）。
2. evidence_id 是否实际重复，需要在有 canonical 视图的产物上核对，本轮不具备该数据。
3. `drop_counts` 中 `entity_not_in_span` 丢弃 29 条，属另一类过滤，与 norm_id 碰撞无关。

## 五、下一步

按三类兼容方案评估，产出提案与影子证明，不修改生产标识符生成逻辑。
