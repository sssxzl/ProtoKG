# D9 Aggregate Carrier 立项

> 状态：Proposal（未冻结）
> 上游：docs/设计/traffic_d9_design.md §6.x-gap-r1
> 合并自：GAP-R1（rate 承载）+ §7 independence 四量承载
> 勘察来源：§6-Pre6 阶段 B（rate）、§6-Pre8 阶段 B（independence）
> 本文件仅登记问题与路径，**不做技术裁定**。

---

## 0. 背景

两个独立勘察分别发现：

- **§6-Pre6 阶段 B**：§6.3 / §6.4 的 rate 三元组需要
  population-level 承载，当前 Hub 模型无位承载。
- **§6-Pre8 阶段 B**：§7 independence 四量需要 population-level 承载，
  现有 Fact 级模型无法表达。

两者**共享同一承载需求**：都要求一个能容纳「跨多个观测单元的聚合结果 +
该聚合所基于的总体界定」的结构。

本立项合并处理，避免 §6 与 §7 各建一套并行设计（违反单一真源原则）。

**GAP-R1 语义范围据此扩展**：从「rate 承载位缺失」扩为
「Hub Aggregate Carrier 缺失」。

---

## 1. 承载需求清单

### 1.1 §6 rate 三元组（来自 §6.3-F / §6.3-H）

| 需求 | 类型 | 契约约束 |
| --- | --- | --- |
| `numerator` | 整数 | ≤ denominator |
| `denominator` | 整数 | > 0 时 rate ∈ [0,1]；= 0 时为 `insufficient_observation` |
| `observed_rate` | 数值 | numerator / denominator；**禁止 `observed_rate = 0`** 伪造 |
| `population_scope` | 对象 | §6.w 已裁定归 Assertion.value |
| `eligible_measurement_count` | 整数 | §3.1.1 observation layer |
| `unknown_outcome_count` | 整数 | §6.3-G 必须同时保留 |
| `measurement_status` | 枚举 | `insufficient_observation`（§6.3-H 唯一 canonical status） |

### 1.2 §7 independence 四量（来自 §3.1.3）

| 需求 | 类型 | 契约约束 |
| --- | --- | --- |
| `support_unit_count` | 整数 | 总数 |
| `independent_support_count` | 整数 | 不得含 unknown |
| `dependent_support_count` | 整数 | 不增加 independent，但不从统计记录消失 |
| `unknown_support_count` | 整数 | **不得合入 independent** |
| 三态（`dependent` / `independent-under-policy` / `unknown`） | 枚举 | §2.2；须 scope-qualified（§2.2.x） |

**严格 partition（§3.1.3，此层唯一显式约束）**：

```
support_unit_count = independent_support_count
                   + dependent_support_count
                   + unknown_support_count
```

⟹ 该恒等式**可校验**，承载结构必须支持数值等式校验。

---

## 2. 与现有模型的关系

### 2.1 现有 Hub 模型（实测）

| 结构 | 层级 | 与 aggregate 的关系 |
| --- | --- | --- |
| `FactKey` | Fact identity | 5 字段（kind/actor/subject/property/condition），无总体维度；§6.2-9 禁止进入 |
| `Assertion` | Fact 实例 | `value` 无 type 约束（三层均无），结构由 property `value_schema` 委派 |
| `Claim` | Claim | `scope.constraints` 为无约束 object；`flags` 为 `list[str]` |
| `Resolution` | Fact | 四域（status/completeness/method/reason）均与 support 计数无关 |
| `Evidence` | Claim | `locator` 语义是「证据定位」 |

### 2.2 两项关键实测

1. **零 dict 形态生产先例**：当前 65 个 Facts 的 `assertion.value`
   全为标量（bool / str）。结构化 value 在契约层已定义
   （R2 / R11–R14 的 `value_schema`），**生产层从未验证**。
2. **零统计独立性概念**：`independent` 的 6 处命中**全部**是
   context-independence / provenance-independence / source-independent；
   `support_unit` / `support_count` / `cluster` / `raw_observation`
   全仓 0 命中。

### 2.3 与 §1.5 rule 10 的一致性

§1.5 rule 10 禁止 support multiplicity 影响 `claim_class` / `authority` /
`modality` / Phase A tier / voting weight / Phase B relation type。
现有 Resolution 四域与 Phase B relation taxonomy 均**不含** support 计数
⟹ 现状合规。

⟹ 承载结构必须是**旁挂**的（记录观测结构），**不得**回流进 fusion 语义。

---

## 3. 候选承载位置

**（列出，不裁定。）**

| # | 候选位 | 结构可行 | 依据 | 主要风险 |
| --- | --- | --- | --- | --- |
| 1 | `Assertion.value` 内嵌 | ✓ | §6.w 已裁定 population_scope 归此；schema 三层无约束 | §6.1-y 禁止 aggregate 与 support summary 混同；四量与 rate 混同风险 |
| 2 | `Claim.scope.constraints` | △ | 结构允许（无约束 object） | §6.w 已判语义维度不同（协议适用域） |
| 3 | `flags`（list[str]） | △ | 结构可行，不进 identity payload | 无域约束、零先例、**无法承载计数值** |
| 4 | Fact 之外独立 aggregate artifact | ✓ | §6.3-I 本就把 aggregate 视为独立阶段产物 | 需新增 artifact 类型；§8 与 §7 均需新读取路径 |
| 5 | `Evidence.locator` | ✗ | — | 契约语义是「证据定位」，语义挪用 |
| 6 | `Resolution` 扩展 | ✗ | 四域为封闭枚举 | 需改域；且违反 rule 10 的旁挂原则 |
| 7 | `FactKey` 扩展 | ✗ | additionalProperties=false | **§6.2-9 明令禁止** |

---

## 4. 与 GAP-PAIR-IDENTITY 的关系

沿用 §6-Pre3 判定（`step_d9_6_pre3/gap_relationship.txt`）：

**同一根因的两种表现，落在不同层，方向相反。**

- 共同根因：模型在 fact identity 层与 assertion 层之间，
  缺「复合结构化语义对象」承载机制。
- **D9-GAP-PAIR-IDENTITY** 落 `fact_key` 层，方向是**需要向上扩张**
  进入 fact identity（无位可进）。
- **GAP-R1（Aggregate Carrier）** 落 Registry + assertion 层，
  方向是**在 fact identity 之外**另寻归属。

⟹ 二者不可合并计数，需分别登记；
  但建议在**同一次 Schema Gap Review** 中一并处置。

**依赖差异**：PAIR-IDENTITY 无前置；Aggregate Carrier 的
`rrf` 键空间风险已由 GAP-R5（§14 E7 `_completeness` 双路径修复）消除。

---

## 5. 与 §6.2-9 禁令的关系

**§6.2-9 原文**：

> 9. **一个 property 的 measurement contract 不得通过 `capture_id` /
>    `concrete_protocol_session_instance_id` / `cluster_id` / `scenario_id` /
>    `collection_run_id` 修改 canonical fact identity。**

**判定：禁令不排除 population-level 承载。** 三点依据：

1. **作用对象**是 canonical `fact identity`（fact_key），
   不是「任何与观测有关的信息」⟹ assertion / claim scope / 独立 artifact
   均不在字面禁令内。
2. **列举式约束**（5 个标识符 + §6.1-C2 的「具体设备 / 文件 / 抓包批次」），
   不是「一切观测总体信息」的概括禁令。
3. §6.2-11 给出**功能性判据**：「不得因采集实例不同拆分 canonical Fact」
   ⟹ 判据是「是否改变 fact identity」，而非「字段名在不在枚举内」。

⟹ 精确边界：排除「**以采集实例标识改变 fact identity**」，
**不排除**「在 fact identity 之外记录观测总体」。

**但需注意**：`scope-qualified` 要求（§2.2.x / §3.3）意味着 aggregate
必须携带 population scope。§6.2-9 禁止的是**采集实例标识**（capture_id 等）
进入 fact_key，而 population scope 是**统计总体描述**（dataset /
sample_count / time_range）——两者语义不同，R11–R14 的 `observation_scope`
即为此形态（且该形态在契约层已获冻结文档认可）。

---

## 6. 待裁定问题

1. **承载位置**：§3 的 7 个候选中选哪个（或组合）？
2. **rate 与 independence 四量是否共用同一结构**？
   合并可避免并行设计，但 §6.1-y 禁止 aggregate 与 support summary 混同
   ⟹ 若共用，**如何在结构上保持两者的语义可分**？
3. **是否复用 `observation_scope` 命名**：复用可与 R11–R14 同构，
   但需裁定 rate 的 scope 与 observed_* 的 scope 是否同一概念。
4. **partition 恒等式的校验位置**：等式校验属 Schema 变更还是
   pipeline 侧 invariant？
5. **是否扩 assertion `type` 域**：若扩，触发 `schema_version` 判定
   （§11.3）。不扩则需确认 rate 用哪个既有 type 承载。
6. **traffic 数据源何时进入 build**：当前 R2 / R11–R14 全部
   producer = 0，承载结构无法被真实数据验证。
7. **§7 是否随之解冻**：Aggregate Carrier 裁定后，§7 方可独立起草
   （§7 起草前置已在 §6.x-gap-r1 语义升级段与 §7 章节登记）。

---

## 7. 建议路径

**（建议，不裁定。）**

1. **先做 §1 之外的公共构件**：Registry 的 rate property 条目骨架、
   rate normalizer、rate comparator。三条路线都需要，可先行推进，
   不与承载位置裁定耦合。
2. **承载位置裁定与 §6.5 / §6.6 / §7 / §8 排期合并**：
   四个章节共同阻塞于 Metadata Recon（3000 captures 可用字段未知），
   建议作为单一前置里程碑统一解决。
3. **路线甲（value 内嵌）可作为默认工作假设推进勘察**：
   与 §6.w 归属一致、改动面最小、不触发 `schema_version` 判定；
   但**在裁定前不落地**。
4. **partition 恒等式应尽早定校验位置**：它是 §3.1.3 唯一的显式约束，
   若等到实现阶段才发现无法校验，会反过来推翻承载位置的选择。
5. **与 GAP-PAIR-IDENTITY 合并排 Schema Gap Review**，但保持分别登记。
   （§6-Pre10 阶段 C 重判：二者**同根 + 不同改动层 + 可并行**。
   Aggregate Carrier 只动 Registry 层，**不必等 Schema Gap Review**；
   PAIR-IDENTITY 必须改 fact_key，仍须进 review。知情即可，不必捆绑。）

---

## 8. GAP-R2 工作量重估（§6-Pre10 结论）

### 8.1 范围固化（§6-Pre12 裁定）

GAP-R2 在 **D9 范围内**的工作 = rate normalizer / comparator
的**声明与设计**（不涉及补齐现有 9 个）。

「9 个 normalizer 全部零实现」是 **Hub 层面独立议题**，
**不属 D9 范围**，另见 `docs/实施/normalizer_implementation_backlog.md`。

**排期关系**：

- D9 内的 GAP-R2 排期**不因**独立议题而变（声明与设计可独立推进）
- 但 D9 的**实际落地**依赖独立议题的排期（无实现则 rate property
  无法完成归一与比较）

### 8.3 原估计

「新增 rate normalizer + comparator 声明」——按字面理解为
在 Registry 中增加两个 `normalizer` / `comparator` 字段值。

### 8.4 实测更正

**9 个 normalizer 在 `core/` 中全部零实现。**

| normalizer | core/ 实现 |
|---|---|
| boolean_normalize_v1 | 0 |
| condition_normalize_v1 | 0 |
| enum_normalize_v1 | 0 |
| numeric_range_v1 | 0 |
| ref_normalize_v1 | 0 |
| relation_normalize_v1 | 0 |
| set_normalize_v1 | 0 |
| temporal_normalize_v1 | 0 |
| text_normalize_v1 | 0 |

`temporal_normalize_v1` / `temporal_relation_v1` 全仓各仅 1 处命中，
即 `property_registry.json:382` / `:383` 的**声明字符串**。

契约侧确认这是既定范围划分，非缺陷：

- `registry_index.py:158-160` —「该字段是自然语言描述, 不是可执行规则。
  Step 4.1 只做读取与暴露; 具体的 normalizer 实现属于 Phase 4.4
  (Phase A 判定) 与 Phase 4.6 (canonicalize_subject operator) 的范围。」
- `normalization.py:27-29` —「完整的 8 类 lexical normalizer 实现属
  Phase 4.4 / 4.6 范围 —— …, 不是可执行规则, 需单独决策后再实现。」
- `normalization.py:127` —「不实现 lexical normalizer」

⟹ **这不是 rate 专属问题，而是 18 个 property 的全域状态。**

### 8.5 实际工作量

| 层 | 内容 | 原估计 | 实际 |
|---|---|---|---|
| 声明 | Registry 侧新增 2 个字段值 | 有 | 有 |
| 实现 | core/ 侧 normalizer + comparator 逻辑 | **无** | **需从零实现** |
| 测试 | normalizer / comparator 单测 + property 集成测 | **无** | **需新建** |
| 集成 | 与 `normalization.py` 架构对接 | **无** | **需设计** |

⟹ 工作量从「声明级」跃升为「**实现级**」。

### 8.6 对其他 GAP 的连锁影响

- **对 GAP-R1（承载位裁定）**：**不阻塞**。
  承载位置裁定只决定三元组放哪，不需要 normalizer 已存在。
- **对 GAP-R3（rrf 键空间）**：影响有限。
  该风险已由 GAP-R5（§14 E7 `_completeness` 双路径修复）消除，
  与 normalizer 无关。
- **对排期**：依赖链 `GAP-R5 → GAP-R1 → {R2, R3}` 中 **R2 应上调**。
  原按「新增声明」估算，实际需「实现一对 normalizer/comparator + 测试」。

### 8.7 建议

1. **不阻塞 GAP-R1 裁定** —— 承载位置可先行决定。
2. R2 单独排期，估算按「实现级」重算。
3. 需先裁定：rate normalizer 是**独立于**现有 9 个，
   还是**先补齐**现有 9 个（后者是更大的独立议题，
   影响全部 18 个 property 的比较语义）。
4. 第 3 点若选择「先补齐 9 个」，则 GAP-R2 的实际范围远超 rate，
   建议单独立项，不并入本 Proposal。

---

> 本文件为 Proposal，**未冻结**。任何承载位置裁定需另行授权。
