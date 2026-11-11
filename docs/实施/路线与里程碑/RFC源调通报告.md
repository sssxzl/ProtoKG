# RFC 源调通报告（跨协议）

> ★ **范围**：只调 **rfc 源**（`--sources rfc`），**不涉及** source / traffic / expert_note / vuln
> ★ **纪律**：本轮**只观测、只记录，不改代码**（用户 2026-11-11 指示）
> ★ **基准**：2026-11-11 · 四协议各跑一遍（rtsp / sip / smtp / DHCPv4）

---

## 〇、先说「证据强度」（README §对齐设计思想）

### 概念

「证据强度」= **这条知识有多可靠、有多权威** ⇒ 落在每个 claim 的 `epistemic_type` 字段上 ⇒
**同一 fact 有多源陈述时，强度分别保留，不合并、不降级** ⇒ 消解时按强度决定「谁赢」。

### 实现载体（`core/fused/downstream/resolver.py:21-34`）

```python
SOURCE_PRIORITY = {
    "observed": 3,              # 实测观测（traffic）
    "normative": 2,             # 规范类
    "must": 2,                  # RFC 2119 MUST
    "normative_unspecified": 2, # optional/should/may
    "descriptive": 1,           # 推断/描述（source / expert_note / vuln）
}
```

⇒ 消解语义按 aspect 分档（`precedence` 取最高优先级来源 / `union` 取值池并集 / `consensus` 共识）。

### ★ 实测 vs README：**两处不一致**（记录，未改）

| 源 | README 声明 | **实测**（rtsp 全源） | 一致？ |
|---|---|---|---|
| rfc | `must` / `normative_unspecified` | must 180 / normative_unspecified 124 | ✔ |
| traffic | `observed` | observed 90 | ✔ |
| **source** | `observed` | **descriptive 198** | ✘ |
| **vuln** | `observed`（带漏洞锚点） | **descriptive 152** | ✘ |
| **expert_note** | `descriptive` | descriptive 16 / **normative 40** | ⚠️ 多出 normative |

⇒ `resolver.py` 的注释明写「值域必须覆盖各抽取器**实际**产出的 epistemic_type」⇒
⇒ **以实现为准 ⇒ README 那张表已过时**（待更新）。

### ★ 一个**设计疑点**（值得讨论，暂不动）

`observed`（3）> `must`（2）⇒ **实测观测的优先级高于规范强制**。
- 正面：抓包是「这个实现**真的这么发**」的事实
- 风险：某实现的**偶然行为**会压过「规范说必须 X」⇒ 若下游拿它判「种子是否合法」会误判
- ⇒ 影响面：`precedence` 语义只作用于 `existence` / `state_changing` / `target_state` 三个 aspect

---

## 一、rfc 源 × 4 协议 × 8 项验收表

| 协议 | kb 里 spec 文档 | norms | facts | 质量闸 | 触达的 spec 文件 | 状态机(fact) | 候选区(llm) | 必填头 | seedgen(rfc 单源) |
|---|---:|---:|---:|---|---|---:|---|---|---|
| **rtsp** | 1 | 107 | 152 | ✔ 0/0 | 1/1 | **14** | table 14 + llm 14 | 物化 9 | ✔ **30 条** |
| **sip** | 1 | 133 | 178 | ✔ 0/0 | 1/1 | **0** | **llm 12** | 物化 14（方法级仅 1/6） | ❌ **「无状态机转移」⇒ 退出码 1** |
| **smtp** | 4 | 63 | 82 | ✔ 0/0 | **4/4** | **0** | **（无）** | ★ profile 无声明 ⇒ 跳过 | ❌ **同上 ⇒ 退出码 1** |
| **DHCPv4** | **36** | 92 | 99 | ✔ 0/0 | ★ **11/36** | **19** | **llm 21** | ★ profile 无声明 ⇒ 跳过 | ✔ **9 条** |

### 各协议的 rfc 源 fact 分布

| 协议 | 分布 |
|---|---|
| rtsp | definition 142 · syntax 90 · value_enum_spec 32 · target_state 28 · existence 8 · required_header 2+2 |
| sip | definition 202 · syntax 90 · value_enum_spec 50 · required_header_global 12 · by_method 2 · **target_state 0** |
| smtp | definition 110 · syntax 38 · value_enum_spec 16 · **无必填头、无状态机** |
| DHCPv4 | **option_layout 74** · target_state 38 · **binary_layout 30** · definition 30 · syntax 26 |

### 8 项判据逐条

| # | 判据 | rtsp | sip | smtp | DHCPv4 |
|---|---|---|---|---|---|
| 1 | 抽取不报错（质量闸 0/0） | ✔ | ✔ | ✔ | ✔ |
| 2 | 方法集正确 | 11 个（ANNOUNCE…SET_PARAMETER） | 6 个（ACK/BYE/CANCEL/INVITE/OPTIONS/REGISTER） | — | 需查 |
| 3 | 必填头知识 | ✔ 9 条 | ⚠️ 14 条但方法级仅 1/6 | ✘ 无 | ✘ 无 |
| 4 | 取值域知识 | ✔ 32 | ✔ 50 | ✔ 16 | ✘ 无（二进制协议） |
| 5 | 状态机（规范有表则必须有） | ✔ 14 | ✔（规范无表 ⇒ 0 合理） | ✔（同上） | ✔ 19 |
| 6 | 状态存在性（existence） | ✔ 8 | ✔ 0（无状态机 ⇒ 合理） | ✔ 0 | ✔（在 target_state 内） |
| 7 | **无协议特化硬编码** | ✔ 四协议同一份代码跑通 | ✔ | ✔ | ✔ |
| 8 | **逐字节可复现** | ✔（缓存命中 ⇒ 不调 LLM） | ✔ | ✔ | ✔ |

⇒ ⇒ **8 项里 6 项全绿**；两项有缺口（见下）

---

## 二、★ 隐藏问题清单（**本轮发现，未改代码**）

### H1 · 多文档覆盖不足（★ 最严重）

**现象**：DHCPv4 的 kb 有 **36 个 spec 文档**，rfc 源只触及 **11 个** ⇒ **26 个完全没被抽**。

**未触及的文档（部分）**：`rfc1534` `rfc2937` `rfc2939` `rfc3004` `rfc3011` `rfc3046`
`rfc3074` `rfc3118` `rfc3203` `rfc3256` `rfc3442` …

**定性（抽样验证）**：这些是**散文型扩展 RFC**（如 rfc3004 = DHCP Lease Management、
rfc3203 = DHCP Reconfigure 扩展、rfc2939 = 新 DHCP 选项定义流程）
⇒ ⇒ **不是解析失败，是「形态覆盖不足」**：rfc 源的 10 个通道覆盖的是
**结构化形态**（ABNF / 表格 / 命令列表 / 状态转移表），**纯散文**没有对应通道。

**⇒ 影响**：这些文档定义的**选项语义与流程约束**（如选项 61/62/63）**全部丢失**
⇒ ⇒ 正好落进「rfc 源不接 LLM ⇒ 散文型知识抽不出」的空白
⇒ ⇒ ★ **这正是用户记忆里「RFC 切片喂 LLM」方案要解决的场景**。

**⇒ 建议（未实施）**：给 rfc 源加**第 11 条通道 G（LLM 语义切片）**，
只喂「**没有结构化形态命中**」的文档/章节 ⇒ 产出 `definition` / `legal_boundary` 类知识
⇒ 需配套：① 新 kind（LLM 产的语义落哪个 aspect）② 缓存同构（按 block_hash）保证可复现。

### H2 · 种子层对「状态机」是硬依赖

**现象**：sip / smtp 的 rfc 源**没有状态机**（规范里本来就没有转移表）
⇒ ⇒ `seedgen` 直接 **`!! 无状态机转移，无法生成种子`（退出码 1）** ⇒ **rfc 单源跑不出任何种子**。

**⇒ 影响**：「rfc 源调通」在 sip/smtp 上**止步于中枢**，**到不了种子层**
⇒ ⇒ 若要让 rfc 单源也能出种子，种子层需要一条「**无状态机时降级**」的路
（如只用 canonical_flow / 方法序列做种子）。

### H3 · 必填头知识缺口

| 协议 | 现象 |
|---|---|
| sip | 物化 14 条，但 `[必填头·方法级] 剔除消息级通用头 [CSeq,Call-ID,From,Max-Forwards,To,Via] ⇒ 1/6 条` ⇒ **方法级必填头只剩 1/6** ⇒ SIP 的必填头几乎全是**消息级** ⇒ 方法级判定名存实亡 |
| smtp / DHCPv4 | `profile.json 无 required_headers ⇒ 跳过` ⇒ **完全没有必填头知识** ⇒ 种子不会带 CSeq 等 |

⇒ ⇒ **profile（协议档案）的人工资产缺失** ⇒ 属「接入档案未填」而非代码缺陷。

### H4 · LLM 状态机腿的产出**未进中枢 fact**

**现象**：sip 有 `rfc:llm` **12 条**候选、DHCPv4 有 **21 条**候选
⇒ ⇒ 但 `[状态机] 各源贡献` 里 sip 是 **（无）**、DHCPv4 是 `rfc:target_state 19`（**表格腿**）
⇒ ⇒ **LLM 腿只停在候选区**（`state_machines.json`），未进 fact
⇒ ⇒ 消费端 `_select_active_transitions` 按规则选一套 ⇒ 选了表格腿。

**⇒ 判定**：这是**设计如此**（note 明说「候选区未消解，后期由 LLM 依据规则判别」）
⇒ 但 **sip 的情况是「表格腿为空 ⇒ 选不了」** ⇒ ⇒ **sip 的状态机知识实际为空**
⇒ ⇒ 需要一条「表格腿空时用 LLM 腿」的兜底规则（**未实施**）。

### H5 · 「无字段级实例」警告的文案**写死了 rtsp 的实测数字**

**现象**：四个协议都打印同一句，其中含 `实测 missing_required_header 234 条 / 36 条种子全部越界`
⇒ ⇒ 那是 **rtsp 的数字** ⇒ 在 sip / smtp / DHCPv4 的语境下**误导**
⇒ ⇒ 应改为协议无关表述（或去掉具体数字）。（**未改**）

### H6 · rfc 单源产物的 seedcheck 结果

| 协议 | 结果 |
|---|---|
| rtsp | **合规 30/30**、越界 0、非法 0 ✔（今天修完必填头/profile 问题后） |
| DHCPv4 | （二进制协议 ⇒ seedcheck 的 V1「首行 ≥2 空格」判据不适用 ⇒ 需单独判据） |

---

## 三、护栏状态（区分「数据状态」与「代码回归」）

中枢当前 = **DHCPv4 的 rfc-only** ⇒ 护栏 **23 failed / 1443 passed**（期望 10）
⇒ ⇒ 新增 16 / 消失 3 ⇒ **逐条核对后确认全部是「依赖多源数据」的断言**：

| 新增失败 | 依赖 |
|---|---|
| `test_load_fact_views_has_all_five_sources` | 五源齐全 |
| `test_assemble_security_from_vuln` | vuln 源 |
| `test_assemble_message_instances_state_normalized` / `test_downstream_message_fields_are_per_method` / `test_rtsp_default_path_now_has_instances` | source 源的 message_instances |
| `test_retrieve_subgraph_filters_security_by_subject` | security |
| `test_generate_protocol_dict_protocol_specific_and_clean` | traffic（字典会话名） |
| `test_real_corpus_url_gap_closed` / `test_rtsp_strict_single_source_unchanged` | rtsp 语料 |
| `test_seedgen_focused_prioritizes_boundary_candidates` | vuln |

⇒ ⇒ **结论：全部为「中枢数据状态」所致，非代码回归** ⇒ ⇒ 按用户指示**不为此重建 rtsp**。

---

## 四、结论

1. ★ **rfc 源在 4 个协议上都能跑通抽取**（质量闸全绿、无协议特化硬编码、可复现）⇒ **抽取层本身是跨协议能力**
2. ★ **但 rfc 源 ≠ 「协议知识全覆盖」**：
   - **结构化形态**（ABNF / 表格 / 状态表）覆盖良好
   - **散文型语义**（DHCPv4 的 26 个扩展 RFC）**完全丢失**（H1）
3. ★ **「rfc 源调通」目前止步于中枢**：sip / smtp 因无状态机 ⇒ 种子层退出码 1（H2）
4. ★ **证据强度**：实现载体是 claim 的 `epistemic_type` + `SOURCE_PRIORITY`；
   实测与 README 有两处不一致（source / vuln 实为 `descriptive`），README 待更新
5. ⇒ ⇒ **下一步的结构调整方向**（待用户拍板，本轮**未实施**）：
   ① rfc 源加「通道 G：LLM 语义切片」（补 H1 的空白）
   ② 种子层加「无状态机降级路」（解 H2）
   ③ profile 的 `required_headers` 人工资产补齐（解 H3）
   ④ 状态机候选的「表格腿空 ⇒ 用 LLM 腿」兜底（解 H4）
