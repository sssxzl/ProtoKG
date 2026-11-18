# R23 完整 NormID 迁移风险评估（★ 仅研究，★ 不实施）

> ★ 依审批：★ **本轮不实际实施完整迁移** ｜★ 0 次 LLM 调用

---

## 一、迁移的动机与前提

★ R23 的复核证明：**现有数据上不存在跨 RFC 的 norm_id 碰撞**（★ 三协议 norm_id 全部唯一）。
★ 因此「把 RFC 编号拼入 norm_id」**没有要修的具体缺陷**，★ 其动机只能是**预防性加固**：
★ 若将来某协议的扩展 RFC 与基础 RFC 定义同名实体，★ 现行去重键会丢弃后者。

### 1.1 预计变化的 NormID 数量

| 协议 | 抽取层 norm 数 | 跨文档同串组数（★ 实测） | 迁移后 ID 会变的 norm 数 |
|---|---:|---:|---:|
| smtp | 63 | **0** | ★ **63（100%）** |
| rtsp | 107 | **0** | ★ **107（100%）** |
| DHCPv4 | 92 | **0** | ★ **92（100%）** |
| 合计 | 262 | 0 | ★ **262（100%）** |

★ ★ **因 norm_id 是「协议+kind+名」的确定性派生，★ 加一个维度必然改写全部 262 条的 ID。**
★ ⇒ ★ **迁移不是「修少数问题」，★ 而是「全量 ID 换血」。**

### 1.2 受影响的 EvidenceID 数量

★ `compute_evidence_id`（★ `canonical.py:142-146`）= hash(source_type + source_id + locator)。
★ `source_id` 来自 norm_id ⇒ ★ **norm_id 变 ⇒ evidence_id 全变**。

| 项 | 数量 | 依据 |
|---|---:|---|
| ★ 受影响 EvidenceID | ★ **等于受影响 norm 数（262）** | ★ source_id 派生链 |
| ★ 其中 evidence_id 不变的 | **0** | ★ locator 恒 None、★ 不含 quote ⇒ 无第二稳定锚点 |

★ ⇒ ★ **262 个 evidence_id 全部失效。**

### 1.3 FactID 是否保持稳定

★ **保持稳定。** ★ `compute_fact_id`（★ `canonical.py:132-134`）只吃 fact_key
（★ protocol × subject × aspect × condition），★ **不含 source_id、不含 evidence_id**。
★ ⇒ ★ **中枢的 fact 身份不受迁移影响。**

★ ★ **这是本次迁移唯一的低成本点**：★ 迁移改变的是「证据身份」而非「事实身份」。

### 1.4 历史引用与下游消费者范围

| 消费者 | 是否引用 norm_id / evidence_id | 影响 |
|---|---|---|
| ★ `core/fused/extraction/norm.py:35` | ★ evidence.source_id = norm_id | ★ 变 |
| ★ `core/fused/hub/canonical.py:142` | ★ evidence_id 派生 | ★ 变 |
| ★ `core/fused/hub/hub_layout.py` | ★ 按 fact_key 落盘 | ★ 不变 |
| ★ `core/fused/hub/hub_view.py` | ★ 按 fact_key 组桶 | ★ 不变 |
| ★ `core/fused/graph/graph_ops.py:217` | ★ 按 name 对齐节点 | ★ 间接（★ 按名字，★ 不读 id） |
| ★ `core/fused/downstream/*` | ★ 按 name 取桶 | ★ 不变 |
| ★ `seedcheck/*` | ★ 按桶校验 | ★ 不变 |
| ★ `derived/cache/source_blocks/*.prose.json` | ★ 缓存键含 input_fingerprint（★ 文本指纹） | ★ 不变（★ 不含 norm_id） |
| ★ `derived/hub/index/entities.jsonl` | ★ entity_id 由 protocol/type/name 派生 | ★ 不变 |
| ★ 审计文档与 R8～R21 的冻结件 | ★ 文本引用 | ★ ★ **须重新核对其断言** |

### 1.5 是否需要双版本映射或兼容读取

★ **需要。** 建议：

| 方案 | 内容 | 代价 |
|---|---|---|
| ★ 双读 | ★ 读取时同时接受旧 `norm_id` 与新 `source_instance_id` | ★ 低；★ 需在 hub_layout 加兼容分支 |
| ★ 映射表 | ★ 落一份 `old_norm_id → new_source_instance_id` 的 sidecar | ★ 低；★ 可审计 |
| ★ ★ **不推荐** | ★ 直接改写并在同一产物里混用两种 ID | ★ 高；★ 无法审计 |

★ ⇒ ★ **推荐：双读 + 映射表 sidecar**，★ 且 **norm_id 字段保持不变**（★ 新增独立的
★ `source_instance_id` 字段），★ ⇒ ⇒ **★ 这实际上就是 R23 影子方案的正式版**。

### 1.6 数据重建与回滚方案

| 阶段 | 内容 | 回滚 |
|---|---|---|
| ★ 1 | ★ 加 `source_instance_id` 字段（★ **norm_id 不变**） | ★ 删字段即可 |
| ★ 2 | ★ 抽取层去重键改为 `source_instance_id` | ★ 改回 `norm["norm_id"]` |
| ★ 3 | ★ 重跑 `build_hub` | ★ 恢复旧产物（★ 需有快照） |
| ★ 4 | ★ 落 old→new 映射 sidecar | ★ 删 sidecar |

★ ⇒ ★ **★ 因为 fact_id 不变，★ 重建后中枢的 fact 集合与顺序应保持一致，
★ ★ 只有 evidence 的 source_id 变化。** ★ 这使回滚成本可控。

---

## 二、结论

| 项 | 结论 |
|---|---|
| ★ 预计变化的 NormID 数量 | ★ **262（全部）** |
| ★ 受影响 EvidenceID 数量 | ★ **262（全部）** |
| ★ FactID 是否稳定 | ★ **是**（★ 不含 source_id） |
| ★ 是否需要双版本映射 | ★ **需要**（★ 推荐双读 + sidecar） |
| ★ 数据重建 | ★ 需要（★ 重跑 build_hub）；★ 但 fact 集合不变 |
| ★ 回滚 | ★ 分四阶段，★ 每阶段可独立回滚 |
| ★ ★ 迁移的必要性 | ★ ★ **当前无缺陷可修**；★ 属预防性加固；★ **优先级应低于「跨源对齐接入 L4」**（★ 后者有实测的零多来源 fact 支撑） |

---

## 三、限制

1. ★ 本轮只做理论评估，★ **未实际实施迁移**。
2. ★ 「262」基于当前三协议的抽取层实跑；★ 若将来协议更多则按比例增长。
3. ★ 历史冻结件（R8～R21）的文本断言需重新核对，★ 本轮未逐项做。
