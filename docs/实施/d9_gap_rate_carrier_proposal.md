# D9 GAP-R1/R2/R3 rate 承载立项

> 状态：Proposal（未冻结）
> 上游：docs/设计/traffic源观测独立性设计.md §6.x-gap-r1
> 勘察来源：local/backup/step_d9_6_pre6/rate_carrier_design/（§6-Pre6 阶段 B）
> 本文件仅登记问题与路径，**不做技术裁定**。

---

## 0. 背景

- **GAP-R1** rate 承载位缺失。§6.3 / §6.4 冻结的产物是 population-level rate
  （numerator / denominator / observed_rate），但当前 Hub 模型无位承载。
- **GAP-R2** Registry 无 rate 条目、normalizer / comparator 无分子分母处理。
  实测 `property_registry.json` 18 key 无任何 rate 声明；
  normalizer 9 种 / comparator 9 种无一处理 rate。
- **GAP-R3** Pipeline 键空间缺 rate 相关键。`resolution_required_fields`
  无分子分母类字段范式；Registry 侧亦无 rate 专用键空间约定。

三者共同根因：**模型在 fact identity 层（FactKey 5 字段）与 assertion 层
（单值）之间，缺「复合结构化语义对象」承载机制。**

---

## 1. 三个 GAP 的关系

三者**同根不同层**，不可合并计数：

| GAP | 层 | 缺什么 | 是否依赖路线选择 |
| --- | --- | --- | --- |
| GAP-R1 | 契约 / 归属 | 三元组放哪一层 | **是**（本立项的核心待裁定项） |
| GAP-R2 | Registry 资产 | property 条目 + normalizer + comparator | **否** |
| GAP-R3 | Pipeline | rrf 键空间范式 | **否** |

判定依据：

- GAP-R2 独立于路线 —— §6-Pre6 勘察结论「三条路线均需新增 property 条目
  + rate normalizer + rate comparator」，这与三元组放哪无关。
- GAP-R3 的**风险已消除** —— 上一轮 `_completeness` 双路径修复（§14 E7）
  已使 rrf 可引用 value 子字段。剩余的 GAP-R3 只是"尚无 rate 键的先例"，
  属**新增工作**而非**阻塞缺陷**。
- GAP-R1 是唯一真正的路线分歧点。

与 D9-GAP-PAIR-IDENTITY 的关系见 §4。

---

## 2. 依赖链

```
GAP-R5 (D9-ISSUE-COMPLETENESS-P0)  ← 已 FIXED（§14 E7，fusion_v3）
    ↓
GAP-R1（三元组归属裁定）
    ↓
GAP-R2（Registry 条目 + normalizer + comparator）  ┐
GAP-R3（rrf 键空间范式，先例）                     ┘ 二者可并行
```

最小依赖链：**GAP-R5 → GAP-R1 → {R2, R3}**

GAP-R5 已 FIXED ⟹ 链路起点已通。当前阻塞在 GAP-R1 的裁定。

---

## 3. 三条实现路线

### 路线甲：value 直接承载三元组 dict

- 改动面：Registry 新增 1 property（value_schema 声明三元组 +
  rrf = [value, numerator, denominator, population_scope]）；
  新增 rate normalizer 1 个、comparator 1 个；
  可能需在 registry_index / comparator 分派处登记。
- 是否属 D9 范围：**部分**。归属层裁定（§6.w）属 D9 且已完成；
  property 条目与 normalizer/comparator 不属 D9。
- 是否属 Schema Gap Review：**是**。
- 风险：零生产先例 —— 这是第一个真正落地结构化 value 的 property
  （当前 65 Facts 的 `assertion.value` 全为标量）。rrf 恒 partial 风险
  已由 GAP-R5 修复消除。

### 路线乙：value 承载 numerator，其他走并行字段

- 改动面：需先确定「并行字段」落点 —— Claim.scope.constraints（结构允许，
  但 §6.w 已判语义维度不同），或新增 Fact 顶层字段（改 fact.schema.json +
  models.py + `_PROFILE_REQUIRED_KEYS` 等）。
- 是否属 D9 范围：**否**（属 Hub 模型 / Schema 层）。
- 是否属 Schema Gap Review：**是，且更重**。
- 风险：分子分母分离后可被独立改动，破坏 §6.3-F 聚合完整性；
  与 §1-y 张力；新增 Fact 顶层字段属破坏性变更
  （fact.schema.json 当前 additionalProperties=false）；
  **与 §6.w 已裁定归属直接冲突**。

### 路线丙：新增 assertion_type / value_schema

- 改动面：models.py `ASSERTION_TYPE_DOMAIN` 扩枚举；fact.schema.json
  `assertion.type` enum 扩枚举；property_registry 新 property；
  validation.py / registry_loader.py 域校验与分派同步；
  可能波及 tests 中的域集合断言。语义发布：Registry fingerprint 变化。
- 是否属 D9 范围：**否**（纯 Hub 契约层）。
- 是否属 Schema Gap Review：**是，且最重**。
- 风险：type 域是封闭枚举，扩枚举属 Storage Contract 语义变化
  ⟹ 可能触发 `schema_version` 判定；波及面最大；本轮明令禁止改
  Registry / Schema。

**（不裁定。以上仅列。）**

---

## 4. 与 D9-GAP-PAIR-IDENTITY 的关系

沿用 §6-Pre3 的关系判定（`step_d9_6_pre3/gap_relationship.txt`）：

**同一根因的两种表现，落在不同层，方向相反。**

- 共同根因：模型缺「复合结构化语义对象」承载机制。
- D9-GAP-PAIR-IDENTITY 落 **fact_key 层**，方向是**需要向上扩张**进入
  fact identity（无位可进）。
- GAP-R1/R2/R3 落 **Registry + assertion 层**，方向是**在 fact identity
  之外**另寻归属（§6.2-9 明令禁止进 fact_key）。

因此二者：

- 不可合并计数，需分别登记；
- 建议在**同一次 Schema Gap Review** 中一并处置；
- PAIR-IDENTITY 无 GAP-R5 前置依赖，RATE-CARRIER 有。

**追加耦合（本阶段勘察发现）**：D9 §3.1.3 的 support 四量
（support_unit_count / independent / dependent / unknown）同为
population 级 aggregate，若 GAP-R1 的承载方案落地，**应同时评估
能否承载 §7 四量**，避免 §6 与 §7 各建一套并行结构。

---

## 5. 待裁定问题

1. **三元组归属**：采用哪条路线？（§6.w 已裁定 population_scope 归
   Assertion.value，但分子分母的归属仍待定）
2. **是否复用 observation_scope**：若复用，rate 与 observed_* 将共享
   scope 命名，Registry 侧需裁定二者是否同一概念
3. **是否扩 assertion type 域**：若选路线丙，需同时裁定
   `schema_version` 是否 bump
4. **§7 四量是否共用承载**：GAP-R1 与 §7 承载的耦合处理
5. **normalizer / comparator 的命名与契约**：属 Registry 变更范围，
   需独立授权
6. **是否需要 traffic 数据源先行**：当前 R2 / R11–R14 全部 producer = 0，
   无数据则新 property 同样零 producer

---

## 6. 建议路径

**（建议，不裁定。）**

1. **先做 GAP-R2 的三件公共构件**：新增 property 条目骨架、
   rate normalizer、rate comparator。三条路线都需要，可先行推进，
   不与路线裁定耦合。
2. **GAP-R1 裁定与 §7 承载合并考虑**：两者同为 population 级 aggregate，
   建议一次性裁定承载结构，避免两套并行设计。
3. **路线甲可作为默认工作假设推进勘察**，理由是与 §6.w 归属一致、
   改动面最小、不触发 schema_version 判定；但**在裁定前不落地**。
4. **traffic 数据源进入 build 应作为前置里程碑**：否则新 property
   与 §6.5 一样停在零 producer，承载设计无法被真实数据验证。
5. **与 §6.5 BLOCKED 合并排期**：§6.5 / §6.6 / §7 / §8 四个章节
   共同阻塞于 Metadata Recon（3000 captures 可用字段未知），
   建议作为单一前置里程碑统一解决。

---

> 本文件为 Proposal，**未冻结**。任何路线裁定需另行授权。
