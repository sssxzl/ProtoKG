# R5B 实际引用歧义与错链风险报告

## 一、已验证事实

### 1.1 引用链

```
norm_id
  → norm.py:35  Evidence.source_id = norm.get("norm_id", "")
  → norm.py:36  document = norm.get("source", "")
  → norm.py:39  locator = None
  → canonical.py:142  compute_evidence_id = sha256(source_type + source_id + serialize(locator))[:16]
```

★ 因 `locator` 恒为 `None`，★ evidence_id 的输入实际只有两项：source_type（rfc）与 source_id（即 norm_id）。

### 1.2 碰撞传导

| 集合 | 记录数 | 唯一 norm_id | 唯一 evidence_id | norm_id 碰撞组 | evidence_id 碰撞组 |
|---|---:|---:|---:|---:|---:|
| R3 | 57 | 55 | 55 | 1 | **1** |
| H1 | 156 | 116 | 116 | 16 | **16** |

★ 两组数量完全相等，★ 碰撞是**一一传导**，★ 不存在只在 norm_id 层或只在 evidence_id 层出现的单独情形。

### 1.3 错链风险分级

按碰撞组内成员的跨度是否相同区分：

| 集合 | 碰撞组 | 组内跨度相同（★ 纯重复） | 组内跨度不同（★ **真实错链风险**） |
|---|---:|---:|---:|
| R3 | 1 | 0 | **1** |
| H1 | 16 | 9 | **7** |

R3 的碰撞组明细见 `R5B_碰撞分组明细.xlsx`。

## 二、★ 仅通过 source_id 关联的下游消费

`Evidence.document` 字段携带 `norm.get("source", "")`，★ 格式为 `file:<doc>#@<span_line>`，★ **本身含文档与跨度信息**。

★ ⇒ ★★ **这是关键发现**：★ `Evidence` 对象同时持有 `source_id`（碰撞）与 `document`（含文档与跨度）
★ ⇒ ★★ **因此下游若同时使用 document 字段，★ 可自行消解歧义；★ 只有【仅凭 source_id 或 evidence_id 关联】的消费路径会出错**

★ ⇒ ★★ **实际错链是否发生，取决于消费方是否使用 document 字段**
★ ⇒ ★★ **★ 缺少真实 canonical 视图，★ 该项结论保持 unmeasured**

## 三、★ 多跨度证据与同文档多候选

| 情形 | 是否被错误关联 | 依据 |
|---|:---:|---|
| 同文档多候选共享 norm_id | ★ 可能 | ★ R3 的 H1 中 rfc2326 的 `_server` 组 8 条跨 3 个 chunk，★ 同文档不同跨度共用 evidence_id |
| 多跨度证据 | ★ 未观察到 | ★ 当前 Evidence 构造中 locator 恒为 None，★ 未见多跨度 Evidence 实例 |
| 证据跨度错误关联 | ★ **unmeasured** | ★ 缺真实 canonical 产物 |

## 四、推论

1. 碰撞是确证的标识符复用，★ 语义载荷不同证明其为不同命题。
2. 由于 Evidence 同时携带 document 与 source_id，★ 消歧信息在对象层面是存在的，★ 丢失发生在「按标识符建索引」这一步。
3. 修复的最小侵入点是**为标识符补充可区分维度**，★ 而非修改 Evidence 结构。

## 五、限制

1. R3 与 H1 的记录均未附随 canonical FactID，★ **不能声明 canonical 已发生错链**。
2. 本轮未检查中枢消费视图的实际索引方式，★ 无法确定哪些路径会实际出错。
3. H1 的 9 个纯重复组虽跨度相同，★ 但语义载荷不同，★ 同样存在按标识符索引时的覆盖风险。

## 六、下一步

1. 在中枢消费视图侧核查：★ 是否存在仅按 source_id 或 evidence_id 建索引的路径。
2. 若确认存在，★ 按方案 C 的 sidecar 补充复合索引，★ 不改生产标识符。
3. 如发现真实错链，★ 输出证据与最小修复提案，★ 不自动合入生产。
