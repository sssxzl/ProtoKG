# T0-A Evidence 审查状态与 Hub 接入边界

## 一、最终统计

| 状态 | 条数 |
|---|---|
| supported | **30** |
| partially_supported | 0 |
| multi_source_pending | 0 |

其中：
- 模型原生 quote 直接支持：27；
- 经人工审查 + 确定性扩展后支持：3（p7、p8、p13）。

## 二、这个 30/30 的含义

它表示：**v4 已抽取的这 30 条知识，现在都有可定位、可支撑其命题的原文证据**。

它**不**表示：
- RFC 3207 全文召回 100%（341 行就漏了）；
- 模型自己能稳定给出正确 quote（本轮 3 条是程序补的）；
- Hub 里已经有 30 条已验证知识。

## 三、Hub 接入边界

本轮没有重跑 Hub 写入，因此不能声称"已验证状态已进入 Hub"。

要真正生效，需要一次接入步骤：把侧车里的 `verified_span` 与 quote 关联到对应 Claim/Evidence，再构建隔离 Hub 并读回核对。这一步涉及 Evidence 内容写入，尚未做。

## 四、Fact / Claim 关联

侧车以 `proposition_id` 连接 `fact_id` / `claim_id`，身份均未改。多 Claim 的 Fact（`f2_35eb41ca…` 三条）逐条证据有效。

## 五、状态

```
T0_A_evidence_support_review_completed
T0_A_verified_knowledge 30/30 (v4 已抽集合)
T0_A_normative_gap_341_open
T0_A_hub_verified_state_not_yet_applied
```
