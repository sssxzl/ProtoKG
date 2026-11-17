# H3 Gold 冻结门禁报告

> ★ 第三方仲裁已回收（仲裁者 C，2026-11-17）｜★ **门禁 10 项全部通过**
> ★ 本报告只做结构核验，★ 语义裁定由第三方作出

---

## 一、已验证事实

### 1.1 十项门禁

| # | 门禁项 | 结果 | 依据 |
|---|---|:---:|---|
| 1 | 23 条候选都有最终处理状态 | 通过 | 23/23；confirmed_valid 22、excluded 1 |
| 2 | 所有关键类型、路由、资格分歧有归宿 | 通过 | 关键待裁 8/8 已裁定；逐字段差异 44/44 已填；★ 其中 14 行关键判断类全部有裁定 |
| 3 | 所有补充知识有接受、合并或排除结论 | 通过 | 5 条原子命题全部 accepted，均有 Gold ID 与裁定理由 |
| 4 | 未决项单独标记，不伪造 resolved | 通过 | unresolved 0 条；★ excluded 1 条已单列且不计入有效 Gold |
| 5 | 证据跨度可追溯至冻结 RFC 原文 | 通过 | 23 条候选跨度与 R1 冻结基线逐条一致，不一致 0 条 |
| 6 | 原始 A/B 标注没有被覆盖 | 通过 | A、B 原件 SHA256 与发放包记录完全一致 |
| 7 | 审核者真实独立性得到确认 | 通过 | 仲裁者标识集合 = {C}，与 A、B 不相交；★ 无真实姓名；日期统一 2026-11-17 |
| 8 | 机器身份与 R1 冻结基线一致 | 通过 | 23 条候选 ID 与补充知识候选 ID 全部见于 R1 基线（基线 23 条） |
| 9 | Gold ID 唯一且稳定 | 通过 | 28 条 Gold ID 全部唯一；★ 补充知识 Gold ID 由第三方给出（GK-H3-05-2 等） |
| 10 | 文件 SHA256 与版本清单完整 | 通过 | 两份回收文件已登记 SHA256；A/B 原件哈希已登记 |

### 1.2 枚举合法性

| 列 | 允许集合 | 实际取值 | 结论 |
|---|---|---|:---:|
| 最终状态 | agreed / arbitrated / unresolved / not_applicable | arbitrated 7、agreed 1 | 合法 |
| 是否语义等价 | equivalent / not_equivalent / partially_equivalent / unresolved | equivalent 24、not_equivalent 16、partially_equivalent 4 | 合法 |
| 最终处置 | accepted / merged / excluded / unresolved | accepted 5 | 合法 |
| 是否拆分或合并 | 同上 | accepted 5、merged 3 | 合法 |
| 最终处理状态 | confirmed_valid / confirmed_invalid / unresolved / excluded | confirmed_valid 22、excluded 1 | 合法 |

★ 无越界取值。★ 候选最终状态表的最终类型、资格、强度、路由四列取值全部落在同行 A/B 机器列的既有值域内。

## 二、Gold 基线

| 项 | 值 |
|---|---:|
| Gold 总条数 | 28 |
| 候选级 | 23 |
| 补充知识级 | 5 |
| 计入有效 Gold | **27** |
| excluded（单列，不计入有效 Gold） | 1 |
| unresolved | 0 |
| Gold ID 唯一 | True |

分布：

| 维度 | 分布 |
|---|---|
| 知识类型 | {'non_protocol_metadata': 4, 'normative_rule_candidate': 17, 'protocol_descriptive_semantics': 5, 'protocol_syntax': 1} |
| 目标路由 | {'metadata_channel': 4, 'rule_channel': 17, 'descriptive_channel': 5, 'structured_channel': 1} |
| 强度 | {'not_applicable': 9, 'SHOULD': 8, 'MUST': 7, 'MAY': 3} |

★ Gold 基线文件：`H3_Gold冻结基线.jsonl`，SHA256 `f4bfbdb5da1746416321ff2f20bcbf070330fa606f79c0715fccd8545fec6044`

## 三、第三方裁定的要点（★ 原样记录，★ 不改写）

| 候选 | 裁定 |
|---|---|
| H3-02 | 小写 should 构成规范义务，强度 SHOULD，资格 eligible，路由 rule_channel |
| H3-13 | 属规范建议而非协议语法；候选声称的 MUST 实际对应同跨度另一句，完整性判 partial |
| H3-20 | RADIUS 的 DHCPv6-Options 不属 DHCPv4 目标知识，最终 excluded |
| H3-03 | 双方共同 uncertain 不等于已解决；主体定为 DHCP 服务器（发送方） |
| H3-16 | 选项弃用陈述不含规范字段，完整性记 not_applicable |
| H3-19 | without any explicit request 不单列为条件；完整性判 partial（object 混入状语） |
| H3-05 | 双方一致，记 agreed |
| H3-15 | 极性相反的两条义务必须拆分，否决合并 |

补充知识 5 条全部 accepted，其中 AU-04 与 AU-05 的候选归属裁定为 H3-16（采纳 A 的拆分）。

## 四、限制与需注意项

1. **一处表述差异需留意**：H3-19 在关键待裁的裁定结论填 no，而候选最终状态为 confirmed_valid。★ 两者语义不同——★ 关键待裁的 no 指的是「条件不单列」这一子问题的否定答复，★ 而非「候选无效」。★ 已交叉核对，★ 不构成矛盾，★ 但在机器解析时应按列语义分别处理。
2. ★ 候选级 Gold 的结构化字段（主体、动作、对象、条件）取自逐字段差异表的仲裁结果，★ 其中 partly_equivalent 的取值依仲裁结果中的明确指定（如 Gold 取 A、Gold 统一为 X）解析，★ 无明确指定时取 A 值。★ **建议人工复核这 5 个字段的取值**。
3. ★ Gold 条目的极性字段（polarity）未在候选级填入——★ 反馈表未提供该列，★ 补充知识级有。★ 不做推断。
4. ★ H3-20 为 excluded，★ 其理由中提到 RFC 9445 第 3.2 节的 DHCPv4-Options 属性在目标范围内，★ 建议后续补抽。
5. ★ 未开始任何 V2 指标评估。

## 五、状态

H3 双人盲审完成，第三方仲裁已完成，Gold 已冻结。
