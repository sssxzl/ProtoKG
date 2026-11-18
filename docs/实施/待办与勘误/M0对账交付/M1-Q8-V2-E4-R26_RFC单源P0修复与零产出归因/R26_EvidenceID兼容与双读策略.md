# R26 EvidenceID 兼容与双读策略

## 一、EvidenceID 的生成规则（实测）

`core/fused/hub/canonical.py` 的 `compute_evidence_id()`：

```python
raw = (evidence.source_type.encode("utf-8")
       + evidence.source_id.encode("utf-8")
       + canonical_serialize(evidence.locator))
return "e2_" + hashlib.sha256(raw).hexdigest()[:16]
```

结论：**locator 参与哈希**。任务 A 把锚点名换成行号后，被改动条目的 EvidenceID 必然变化。

## 二、受影响范围（262 条逐条判定）

| 项 | 条数 | 说明 |
|---|---|---|
| locator 未变 | 219 | EvidenceID 不变 |
| locator 变化 | 43 | smtp 27、rtsp 16；locator 由锚点名变为行号 |
| EvidenceID 变化 | 43 | 与 locator 变化一一对应 |
| 双读键变化 | 43 | 双读键取 `source` 字符串（`file:<doc>#@<locator>`） |

旧的 91 个锚点名与新的行号之间**不存在机械映射**：旧锚点是类别级（`abnf-field`、`samples`、`message-list`、`state-table`），一个锚点对应同类的多条知识，只能按知识命题（`norm_id`）对齐，不能按字符串推导。

映射表见 `R26_EvidenceID兼容映射表.jsonl`，每行含旧/新 document、旧/新 locator、旧/新 source、locator 是否变化、EvidenceID 是否变化、双读键（旧/新）、冲突判定。

## 三、双读与冲突阻断规则

迁移期内读取端同时接受两种键：

1. 先按新键（行号）查。
2. 未命中再按旧键（锚点名）查，命中即视为"历史证据"，并在返回结果上标记 `legacy_locator=true`。
3. 若新旧键同时命中且指向**不同 `norm_id`**，判为冲突，直接阻断该条写入，不允许静默择一。
4. 若新旧键同时命中且指向同一 `norm_id`，取新键，旧键只作为兼容路径。

262 条逐条判定结果：219 条"无冲突（locator 未变）"，43 条"需双读核验（旧锚点与新行号指向同一知识）"，冲突 0 条。

## 四、限制

1. 43 条"需双读核验"是按 `norm_id` 对齐得出的，尚未在真实中枢读取路径上跑双读；双读代码未落地，本轮只给规则与判定表。
2. 行号精度问题（65 条落在空行）会连带影响 EvidenceID 的稳定性：若后续把行号回退到最近非空行，这 65 条的 EvidenceID 还会再变一次。建议在回退逻辑定稿后再一次性迁移，避免两轮迁移。
3. 本轮未改动 `compute_evidence_id()` 与任何身份契约。

## 五、下一步建议

1. 先定稿行号回退规则，再执行 EvidenceID 迁移，迁移时同步写入新旧键对照表。
2. 在中枢读取端实现第 3、4 条双读与阻断逻辑，并补一条冲突用例进护栏。
