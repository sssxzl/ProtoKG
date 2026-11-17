# R5B 碰撞统计口径勘误

## 一、已验证事实

### 1.1 「156 - 116 = 40」的含义

| 口径 | R3 | H1 |
|---|---:|---:|
| 记录数 | 57 | 156 |
| 唯一 norm_id | 55 | 116 |
| **重复超额（★ 记录数减唯一数）** | **2** | **40** |
| norm_id 碰撞组数 | 1 | 16 |
| 碰撞涉及记录数 | 3 | 40 |

★ **★ 口径澄清**：★ 40 是「记录数减去唯一标识数」的**超额量**，★ 而非「被丢弃的记录数」。
★ H1 的 156 条记录**全部保留在 `frozen_blocks.jsonl`**，★ `drop_counts` 汇总中 `duplicate` 为 0。
★ 16 个碰撞组共含 40 条记录，★ 平均每组 2.5 条。

### 1.2 payload hash 不同是否对应真正不同语义

★ H1 的 16 个碰撞组中，**没有任何一组包含相同 semantic_payload_hash 的记录**。
★ R3 的 1 个碰撞组中，3 条成员的 payload hash 同样互不相同。

★ 语义载荷包含 kind、entity、meaning、constraint、action、object、strength、polarity、condition、exception 十项。
★ payload 不同说明这些记录承载**不同的知识命题**，★ 而非同一命题的重复写入。

★ 举例：H1 中 `_server` 组 8 条记录，★ 分别来自 rfc2326 的三个不同 chunk 与 rfc3261 等，★ 语义载荷各异。

### 1.3 Evidence ID 是否出现实际碰撞

★ **确证碰撞**。沿真实生产链路复算：

```python
# core/fused/hub/canonical.py:142
def compute_evidence_id(evidence) -> str:
    raw = (evidence.source_type.encode("utf-8")
           + evidence.source_id.encode("utf-8")
           + canonical_serialize(evidence.locator))
    return "e2_" + hashlib.sha256(raw).hexdigest()[:16]
```

而 `core/fused/extraction/norm.py:35` 的 `_make_evidence` 传入 `locator=None`。

★ ⇒ ★★ **evidence_id 实际只由 source_type（rfc）与 source_id（即 norm_id）决定**
★ ⇒ ★★ **norm_id 碰撞必然传导为 evidence_id 碰撞**

| 集合 | 唯一 evidence_id | evidence_id 碰撞组数 |
|---|---:|---:|
| R3 | 55 | **1** |
| H1 | 116 | **16** |

★ 两组的碰撞组数与 norm_id 碰撞组数**完全相等**，★ 说明碰撞是**一一传导**的。

## 二、★ 错链风险的量化

按碰撞组内成员的跨度是否相同区分：

| 集合 | 碰撞组 | 组内跨度相同（★ 纯重复） | 组内跨度不同（★ **真实错链风险**） |
|---|---:|---:|---:|
| R3 | 1 | 0 | **1** |
| H1 | 16 | 9 | **7** |

★ R3 的唯一碰撞组 `prose_constraint_server`：

| 候选 | 文档 | 跨度 | evidence_id |
|---|---|---|---|
| X-smtp-rfc1870-02 | rfc1870.txt | 207 | e2_d97066edaf0d2e52 |
| X-sip-rfc2543-01 | rfc2543.txt | 1824 | e2_d97066edaf0d2e52 |
| X-rtsp-rfc7826-02 | rfc7826.txt | 5390 | e2_d97066edaf0d2e52 |

★ 三条分属不同 RFC、不同跨度、不同语义载荷的命题，★ **共用同一个 evidence_id**。

## 三、推论

1. 碰撞是**确证的引用歧义**，★ 不是推测。★ 下游按 evidence_id 关联证据时，★ 会把三条不同命题的证据指向同一标识。
2. 「重复超额 40」这一数字**不应**被解读为「40 条知识丢失」，★ 记录全部保留。
3. 修复的必要性在于**关联正确性**，★ 而非数据完整性。

## 四、限制

1. R3 与 H1 的记录**均未附随 canonical FactID**（★ R3 为 shadow/proposed，★ H1 的 FactID 未随记录保存）。
2. 因此**不能声明 canonical 已发生错链**，★ 只能声明：**在 canonical 视图上按 evidence_id 关联时会指向错误跨度**（★ 实际错链结论保持 unmeasured）。
3. 16 个 H1 碰撞组中 9 组的组内跨度相同，★ 这 9 组是同一跨度内的不同命题，★ 错链风险同样存在但跨度不显现。

## 五、下一步

按方案 C 建立复合索引 sidecar 并核对真实 canonical 产物上的引用关系。
