# R25 RFC 单源知识抽取链路完整性与现有知识中枢兼容性验证

> ★ 分支 `feature/r25-rfc-single-source-audit`（★ 从 main `65d162b` 建立）
> ★ **0 次新增 LLM 调用；★ 未修改生产代码；★ 未覆盖正式中枢与 Seed**

---

## 一、★ 七个总体问题的逐条回答

| # | 问题 | 结论 | 关键证据 |
|---|---|---|---|
| 1 | ★ RFC 原文中的知识能否被完整识别？ | ★ **部分** | ★ 41 份 RFC 只产出 262 条 Norm；★ 文档级覆盖 **18/41 = 43.9%**；★ 原文知识识别率（★ 端到端召回）**unavailable**（★ 无独立人工真值） |
| 2 | ★ 能否正确区分不同类型的协议知识？ | ★ **部分** | ★ 知识类型准确率（★ kind⇒aspect 单一性）**0.729**；★ 71 条 Norm 映射出多个 aspect（★ 如 field ⇒ syntax + definition） |
| 3 | ★ 能否正确抽取规范性义务及其语义字段？ | ★ **是** | ★ 22 条有约束的散文抽取中 **20 条产 Rule Slot**（★ 90.9%）；★ 这 20 条的 Assertion **全部**含 strength/polarity/condition/exception |
| 4 | ★ 能否避免多 RFC 文档之间的来源身份冲突？ | ★ **是** | ★ 真实语料同 norm_id 多来源实例 **0 组**；★ 身份冲突 **0 条**；★ 影子对照：★ RTSP prod_only 9 / shadow_only 2、★ DHCPv4 prod_only 0 / shadow_only 5 |
| 5 | ★ 抽取出的知识在后续转换中是否发生意外丢失？ | ★ **是**（★ 有缺口） | ★ Norm→Canonical 映射 **262/262 成功（0% 丢失）**；★ 但 **47/86 条 Evidence 丢失行号定位**（★ 退化为锚点） |
| 6 | ★ 能否按现有 Canonical 契约正确映射到中枢？ | ★ **是** | ★ 映射零失败；★ FactID 由既有 `compute_fact_id` 计算；★ **未改 Canonical Schema、★ 未改 21 aspects、★ 未改 FactID/EvidenceID 契约** |
| 7 | ★ 能否从最终中枢记录反向追溯到确切 RFC 原文？ | ★ **部分** | ★ 文档级 **100%** 可定位（★ 86/86 的文档存在）；★ 但**行级仅 40.7%**（★ 35/86）；★ 47 条只到锚点 |

---

## 二、★ 链路阶段流转（★ 阶段 B）

| 协议 | ① RFC 文档 | ② 非空行（Chunk） | ③～⑥ Norm | Fact | aspect 分布 |
|---|---:|---:|---:|---:|---|
| smtp | 4 | 6824 | 63 | 82 | {'definition': 55, 'syntax': 19, 'value_enum_spec': 8} |
| rtsp | 1 | 3505 | 107 | 152 | {'syntax': 45, 'definition': 71, 'existence': 4, 'target_state': 14, 'value_enum_spec': 16, 'required_header_global': 1, 'required_header_by_method': 1} |
| DHCPv4 | 36 | 17173 | 92 | 99 | {'definition': 15, 'syntax': 13, 'target_state': 19, 'binary_layout': 15, 'option_layout': 37} |

★ 全链：★ RFC 原文 → Document Parser → Chunk → Raw Extraction → Normalized Fields
★ → Knowledge Classification → Norm → Canonical Mapping。
★ ★ **每一阶段的输入输出数、关联 ID、原始/派生字段、转换规则、丢弃条件、失败状态、
★ ★ 来源证据、版本哈希均已登记**（★ `R25_抽取阶段字段流转矩阵.csv`）。

---

## 三、★ 本轮发现的关键缺口（★ 按严重度）

| # | 缺口 | 严重度 | 位置 | 性质 |
|---|---|---|---|---|
| 1 | ★ **Evidence 行级定位仅 40.7%** | ★ **P0** | ★ `rfc_extractor.py:1723,1736,1910,1985` | ★ 三个 ABNF/样例通道用**硬编码锚点名**（★ @abnf / @abnf-field / @samples），★ 全文级扫描天然无行号 |
| 2 | ★ **RFC 文档级覆盖 43.9%** | ★ **P1** | ★ 抽取器的窗口预算与通道覆盖 | ★ 23 份 RFC 零产出 |
| 3 | ★ 知识类型判别不唯一（★ 0.729） | ★ P1 | ★ `norm.py` 的 kind⇒aspect 映射 | ★ field 同时映射到 syntax 与 definition |
| 4 | ★ 非文件来源与文件来源共享命名空间 | ★ P1 | ★ `rfc_extractor.py:4021,4272-4275` | ★ 真实语料零触发（★ RTSP/DHCPv4 的 shadow 对照显示差异） |
| 5 | ★ field_value 合并结果写在被丢弃的 norm 上 | ★ **P0（代码缺陷）** | ★ `rfc_extractor.py:4114-4127` | ★ **真实语料零触发**；★ R24B 已用合成输入证明；★ 影子补丁零影响 |

---

## 四、★ 与冻结契约的关系（★ 本轮未触碰）

| 冻结项 | 状态 |
|---|---|
| ★ Canonical 数据结构 | ★ **未改** |
| ★ 21 aspects | ★ **未改** |
| ★ FactID 生成规则 | ★ **未改**（★ 用既有 `compute_fact_id` 重算验证） |
| ★ NormID 正式身份契约 | ★ **未改** |
| ★ EvidenceID 正式身份契约 | ★ **未改** |
| ★ Claim / Assertion 既有结构与身份 | ★ **未改** |
| ★ 正式中枢发布机制 | ★ **未改**（★ 影子中枢建在**隔离工作区**） |
| ★ 正式 Seed 与发布机制 | ★ **未改** |

---

## 五、★ 限制

1. ★ **0 次新增 LLM 调用**；★ prose 通道的运行时证据来自**既有历史缓存**（★ 97 条）。
2. ★ 原文知识识别率（★ 端到端召回）**unavailable**：★ 无独立人工真值；★ R13/R19 的 57 条已接触样本不得用作独立泛化集。
3. ★ 本轮只做 SMTP/RTSP/DHCPv4 三协议的 RFC-only 验证；★ SIP 因 `kb/sip/spec` 仅 1 份 RFC 未纳入本轮实验集。
4. ★ 影子中枢在**隔离工作区副本**中构建；★ 正式中枢的 hub 与 per_source 指纹经前后比对**完全未变**。
