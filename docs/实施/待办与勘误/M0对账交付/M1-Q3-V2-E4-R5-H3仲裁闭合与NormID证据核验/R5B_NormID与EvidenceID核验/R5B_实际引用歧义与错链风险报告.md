# R5B 实际引用歧义与错链风险报告

## 一、已验证事实

### 1.1 引用链

```
norm_id
  → norm.py:35   Evidence.source_id = norm.get("norm_id", "")
  → norm.py:36   Evidence.document  = norm.get("source", "")   ★ 含 file:<doc>#@<span>
  → norm.py:39   Evidence.locator   = None
  → canonical.py:142  evidence_id = sha256(source_type + source_id + serialize(None))[:16]
```

因 `locator` 恒为 `None`，evidence_id 的输入只有 source_type 与 source_id。

### 1.2 碰撞传导（实测）

| 集合 | 记录数 | 唯一 norm_id | 唯一 evidence_id | norm_id 碰撞组 | evidence_id 碰撞组 |
|---|---:|---:|---:|---:|---:|
| R3 | 57 | 55 | 55 | 1 | 1 |
| H1 | 156 | 116 | 116 | 16 | 16 |

两组数量完全相等，碰撞一一传导。

### 1.3 ★ 下游消费路径核查（本轮新增）

对 `core/fused/hub/` 与 `core/fused/downstream/` 全部检索 `evidence_id` 与 `source_id`，并逐条检查 `derived/hub/` 的实际产物：

| 检查项 | 结果 |
|---|---|
| 中枢产物是否含 evidence_id 字段 | **否**。★ 414 条 claim 的键为 authority、claim_id、confidence、epistemic_type、evidence_summary、fact_id、scope、value |
| 中枢产物是否含 evidence 数组 | **否**。★ evidence 元素数为 0 |
| 中枢的证据表示 | `evidence_summary`，格式 `authority:标识@路径`。★ rfc 类样例：`rfc:rtsp.field.status-line@file:rfc2326.txt#@1233` |
| ★ 摘要是否含可消歧信息 | **是**。★ 摘要同时携带 **norm_id** 与 **file:<doc>#@<span_line>** |
| claim_id / fact_id 是否由 norm_id 派生 | **否**。★ claim_id 为 `c2_<hash>`、fact_id 为 `f2_<hash>`，★ 由 fact_key（protocol、version、subject、aspect、condition）派生 |
| 中枢聚合键 | fact_key（★ 按协议、版本、主体、aspect、条件聚合） |
| 是否存在仅按 source_id 或 evidence_id 建索引的路径 | **未发现**。★ `export.py:252` 的 `evidence_id=f"e_{len(new_claims)}"` 属旧格式反序列化路径，★ 为**重新分配**而非按原 ID 索引 |

### 1.4 错链风险分级

| 集合 | 碰撞组 | 组内跨度相同（★ 纯重复） | 组内跨度不同（★ 真实错链风险） |
|---|---:|---:|---:|
| R3 | 1 | 0 | 1 |
| H1 | 16 | 9 | 7 |

R3 的碰撞组 `prose_constraint_server` 使 rfc1870 第 207 行、rfc2543 第 1824 行、rfc7826 第 5390 行三条不同命题共用 evidence_id `e2_d97066edaf0d2e52`。

## 二、★★ 实际错链是否已发生

**结论：现有中枢产物中未发生。**

依据：

1. 中枢产物不含 evidence_id，也不含 evidence 对象，★ 不存在按 evidence_id 关联的路径。
2. 中枢的证据表示 `evidence_summary` 同时携带 norm_id 与 `file:<doc>#@<span_line>`，★ 消费者可自行消歧。
3. claim_id 与 fact_id 由 fact_key 派生，★ 不经由 norm_id，★ 不受碰撞影响。

⇒ ⇒ ★★ **因此「evidence_id 碰撞」在当前架构下是标识符层面的隐患，★ 而非已发生的引用错链**
⇒ ⇒ ★★ **该结论的适用范围限于当前中枢产物形态；★ 若未来新增仅按 evidence_id 或 source_id 建索引的消费路径，★ 隐患即会显现**

## 三、★ 仍存在的两类风险

| 风险 | 说明 |
|---|---|
| 标识符复用 | 同一 norm_id 对应多条不同命题，★ 按 norm_id 查询会得到多条结果，★ 需靠 document 字段区分 |
| 未来消费路径 | 若新增按 evidence_id 建索引的路径，★ 碰撞将直接导致错链 |

## 四、限制

1. 结论基于当前 `derived/hub/` 产物的实际形态，★ 未覆盖种子生成与漏洞模式向量等其他下游。
2. 未逐行核查全部 414 条 claim 的 evidence_summary 与源规范的逐条对应，★ 结论针对结构层面。
3. 复合索引的唯一性结论基于 R3 的 57 条与 H1 的 156 条。

## 五、最小修复提案（★ 不自动合入）

**提案：方案 C 的 sidecar 与现有 evidence_summary 并行提供复合索引。**

| 项 | 内容 |
|---|---|
| 修改位置 | 新增 sidecar 文件，★ 不改 `prose_semantics.py`、不改 `norm.py`、不改中枢消费代码 |
| 内容 | 每条记录给出 `scheme_c_index`（文档、起始行、语义载荷哈希）与其 legacy norm_id、evidence_id 的对应 |
| 对 FactID 的影响 | 无。★ claim_id 与 fact_id 由 fact_key 派生，★ 不变 |
| 对中枢与 Seed 的影响 | 无。★ sidecar 为旁路产物 |
| 回滚 | 删除 sidecar |
| 风险 | 低。★ 唯一性在 212 条记录上为 100% |

**不采用**：★ 直接改 `prose_semantics.py:1208` 的 norm_id 构造式（★ 会改变 evidence_id 并波及既有产物）；★ 随机 UUID（★ 牺牲可复算性）。

## 六、下一步

若未来新增按 evidence_id 建索引的消费路径，★ 先落地 sidecar；★ 本轮不改动生产身份。
