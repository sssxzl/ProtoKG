# R18 V2-next 区分性合成回归报告

> ★ 合成样本 ｜★ **不构成独立泛化证据** ｜★ 0 次 LLM 调用

---

## 一、已验证事实

### 1.1 样本设计（★ 覆盖审批要求的五类）

| 样本 ID | 场景 | 期望 kind | 期望 elig |
|---|---|---|---|
| D-01 | ★ 锚点句与相邻句分担主体和行为动词 | normative_rule_candidate | eligible |
| D-02 | ★ 上下文无显式 BCP14，但存在协议行为语义 | normative_rule_candidate | eligible |
| D-03 | ★ 描述性过程可能被错误升级为规范义务（★ 负例） | protocol_descriptive_semantics | ineligible |
| D-04 | ★ 原文有规范关键词但作用范围不覆盖当前锚点（★ 负例） | protocol_descriptive_semantics | ineligible |
| D-05 | ★ 跨 RFC 引用（★ 负例） | non_protocol_metadata | ineligible |
| D-06 | ★ 描述性语义（★ 负例） | protocol_descriptive_semantics | ineligible |
| D-07 | ★ 元数据（★ 负例） | non_protocol_metadata | ineligible |
| D-08 | ★ 行为义务句且含协议主体与行为动词（★ 正面基准） | normative_rule_candidate | eligible |

### 1.2 实测

| 指标 | V2 | V2-next |
|---|---:|---:|
| 符合期望 | 4/8 | 4/8 |
| 预测变化 | —— | 0 条 |
| 新增反向误判 | —— | 0 条 |

### 1.3 逐条实测

| 样本 ID | 场景 | V2 | V2-next | 期望 | V2 符合 | V2-next 符合 |
|---|---|---|---|---|---|---|
| D-01 | ★ 锚点句与相邻句分担主体和行为动词 | protocol_descriptive_semantics | protocol_descriptive_semantics | normative_rule_candidate | 否 | 否 |
| D-02 | ★ 上下文无显式 BCP14，但存在协议行为语义 | normative_rule_candidate | normative_rule_candidate | normative_rule_candidate | 是 | 是 |
| D-03 | ★ 描述性过程可能被错误升级为规范义务（★ 负例） | protocol_descriptive_semantics | protocol_descriptive_semantics | protocol_descriptive_semantics | 是 | 是 |
| D-04 | ★ 原文有规范关键词但作用范围不覆盖当前锚点（★ 负例） | normative_rule_candidate | normative_rule_candidate | protocol_descriptive_semantics | 否 | 否 |
| D-05 | ★ 跨 RFC 引用（★ 负例） | protocol_descriptive_semantics | protocol_descriptive_semantics | non_protocol_metadata | 否 | 否 |
| D-06 | ★ 描述性语义（★ 负例） | protocol_descriptive_semantics | protocol_descriptive_semantics | protocol_descriptive_semantics | 是 | 是 |
| D-07 | ★ 元数据（★ 负例） | protocol_descriptive_semantics | protocol_descriptive_semantics | non_protocol_metadata | 否 | 否 |
| D-08 | ★ 行为义务句且含协议主体与行为动词（★ 正面基准） | normative_rule_candidate | normative_rule_candidate | normative_rule_candidate | 是 | 是 |

### 1.4 ★★ 结论：★ 当前方案的盲区已明确

★ **8 条中 V2 与 V2-next 都是 4/8，★ 预测变化 0 条。**

★ 这说明：

1. ★ **未引入新误判**（★ 反向误判 0 条，★ D-03 的描述性负例未被错误升级）；
2. ★ **但也未在区分性样本上产生任何区分**（★ 0 变化）；
3. ★ 原因是：★ 当前方案的三条边界要求「锚点句具备行为义务特征」，
   ★ 而 **D-01（★ 主体与行为动词分跨锚点句与相邻句）★ 恰好不满足该条件**，
   ★ 因此**不触发扩展**，★ 维持单句判据的描述性结果。

★ ★ **⇒ 当前方案在「锚点句自身不含协议主体」的情形下是空操作。**
★ ★ 这与它在已接触 57 条上的表现一致（★ 触发扩展的候选仅 3 条）。

### 1.5 与 R16 合成样本的关系

★ R16 的 15 条样本**全部不触发**扩展路径（★ 故 0 变化）。
★ 本轮的 8 条**同样全部不触发**（★ 其中 D-01 是有意设计的触发失败样本）。
★ ⇒ **★ 两组合成样本都未能覆盖当前方案的有效路径。**

★ **结论**：★ 当前方案的有效路径（★ 锚点句含协议主体与行为动词、★ 受限上下文无 BCP14、
★ 且单句判据落 mixed）**在合成样本中未被构造出来**，★ 需专门补一条。

## 二、限制

1. ★ 合成样本只检验判据行为，★ 不检验真实 RFC 的语义正确性。
2. ★ 本轮未构造出触发扩展的样本，★ 故**无法用合成样本验证修复有效性**。

## 三、下一步

★ 补一条「受限上下文无 BCP14、★ 锚点句含协议主体与行为动词、★ 但单句判据因主体或动词
★ 分散而落 mixed」的样本；★ 之后进入新 RFC 独立验证准备。
