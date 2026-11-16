# H2A · 字段级统计勘误

> ★ 依据原始字段级 ledger 重新复算（★ 不改原始 ledger）

---

## 一、★ 「97 条」的闭合核算（★ 用户 §二 1）

| 项 | ★ 值 |
|---|---|
| ★ 本地复算字段分布 | {'strength': 13, 'polarity': 13, 'condition': 13, 'exception': 13, 'action': 13, 'object': 13, 'cross_ref': 13, 'cross_ref_status': 13} |
| ★ **合计** | **104** |
| ★ 用户复算分布 | {'cross_ref_status': 23, 'action': 14, 'object': 14, 'strength': 14, 'polarity': 14, 'normative_subject': 10, 'condition': 7} |
| ★ 用户复算合计 | 96 |
| ★ **闭合结论** | ★★ **★ **97 = 96 + 1（★ `constraint`）**；★ ★ 用户复算漏掉了 `constraint` 的 1 条 ⇒ ★ **97 本身是闭合的**** |

### 1.1 ★★ 必须说明【两套口径】

| 口径 | ★ 字段集 | ★ 条数 | ★ 差异 |
|---|---|---:|---|
| ★ **H0 ledger**（★ H1 报告引用） | ★ `field_ledger.NORM_FIELDS`（★ 10 字段，★ 含 `normative_subject`） | ★ **97** | ★ 含 `normative_subject` 10；★ **不含** `cross_ref` |
| ★ **H1 复刻生产分支**（★ 本轮） | ★ `normative_rule.SEMANTIC_FIELDS`（★ 11 字段，★ 含 `cross_ref`） | ★ **104** | ★ 含 `cross_ref` 13；★ **不含** `normative_subject`（★ 非 SEMANTIC_FIELDS 成员） |

★ ⇒ ★★ **★ 「97 缺 1 条」= 用户复算漏了 `constraint` 1 条 ⇒ ★ 97 本身闭合**
★ ⇒ ★★ **★ 104 与 97 的差异 = 白名单不同（★ 不是同一集合）⇒ ★ 不可混用**

---

## 二、★ 「方案 B 的 104 条」重新定义（★ 用户 §二 2）

| ★ 口径 | ★ 值 |
|---|---|
| ★ 真实字段级记录数（★ 全量流转） | **253** |
| ★ **字段适用的记录数（★ 分母）** | **70** |
| ★ E 类记录数（★ 原 104） | 104 |
| ★ ├ 其中字段【适用】者 | **0** |
| ★ └ 其中字段【不适用】者（★ ★ 不是语义损失） | **91** |
| ★ ★ **原文与 LLM 输出均有证据、但下游丢失必要语义的记录数** | **0** |
| ★ ★ **方案 B 预计恢复的记录数** | ★★ **★ **待人工判定 3 个候选**（★ 文本含强度词）** |

⇒ ⇒ ★★★ **★★ ⇒ 结论反转：★ 104 条里【没有一条】是「适用字段的语义损失」**
★ ⇒ ★★★ **★ ⇒ 91 条是【字段不适用】（★ prose_semantics 的规范字段本就不适用）**
★ ⇒ ★★★ **★ ⇒ 方案 B 的实际收益 = 0**

---

## 三、★ 13 个 prose_semantics 候选：★ 描述性语义是否真的不可重建

| 项 | ★ 值 |
|---|---|
| ★ 候选数 | 13 |
| ★ meaning/constraint **全部非空** | **13 / 13** |
| ★ ⇒ 描述性语义已由 meaning/constraint 承载 | ★ **是** ⇒ ★ **无不可重建损失** |
| ★ ★ 文本含规范强度词（★ 需人工判定） | ★ **3** |

★ ★★ **3 个需人工判定的候选**：

| candidate_id | ★ constraint 片段 |
|---|---|
| ★ prose_semantics_must | ★ '' |
| ★ prose_semantics_dhcpv6_options attribute | ★ 'MAY appear in a RADIUS CoA-Request packet' |
| ★ prose_semantics_forcerenew message | ★ 'the FORCERENEW message MUST be authenticated using the procedures as described i' |

★ ⇒ ★★★ **★ 这 3 条才是「类型判定可能错误」的真实样本**（★ 不是字段丢失，★ 而是**知识类型归属**问题）
★ ⇒ ★★★ **★ ⇒ 属【V2 类型闸门】范畴，★ 不属【方案 B 字段保全】范畴**
