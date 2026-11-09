# Hub Contract Errata Backlog

> 状态：Backlog（未排期）
> 范围：Hub 冻结文档与 schema 的一致性维护
> **不属 D9 范围**

---

## 0. 背景

D9 Q3 kind 扩展后暴露一个**流程性缺口**：Hub Contract 层缺
「schema 变更时，冻结文档描述如何跟进」的既定机制。

Q3 实施时（§6-Pre21）已出现一次：扩展了
`fused_hub/schema/v1/fact.schema.json` 的 `kind` 枚举，
但**漏改**了同文件内的 `kind.description`
（仍写 "one of the 5 fixed kinds (v1)"），直到 §6-Pre22 阶段 A 才补正。

⟹ 这不是单次疏忽，而是**缺机制**的表征：
当 schema 变更时，没有流程保证冻结文档与其同步。

---

## 1. 已知不一致项

### 1.1 `fused_schema_v1.md` 的 5-kind 描述（**当前未修**）

D9 Q3 将 `fact.schema.json` 的 `kind` 枚举从 **5 值扩至 6 值**
（新增 `packet_role_pair`），但 `fused_schema_v1.md` 仍描述 5 kind。

实测命中位置：

| 行 | 原文 | 性质 |
|---|---|---|
| L167 | `v1 保持五类：method、header、constraint、state、transition。` | **枚举本体描述**，已与 schema 的 6 值矛盾 |
| L175 | `facts/` 目录含 `method.jsonl`、`header.jsonl`、`constraint.jsonl`、`state.jsonl`、`transition.jsonl` **五个文件** | 描述**当前事实布局**，未随新 kind 变 |
| L32 | `fact_key` 含五个**子字段** | **正确**（子字段数未变，仍是 kind/actor/subject/property/condition） |

⚠ **L167 与 L175 的性质不同**：

- **L167** 是对 `kind` **取值域**的描述 ⟹ 已**事实错误**
- **L175** 是对 `facts/` **目录布局**的描述 ⟹ 取决于是否为新 kind
  新增 `packet_role_pair.jsonl`；若不新增（因为该 kind 尚无 producer），
  则 L175 仍**正确**

⟹ 修 L167 前需先决定：**新 kind 是否拥有独立的 `facts/packet_role_pair.jsonl`？**
该问题依赖 §6.5（`observed_packet_position` 解封）与 Metadata Recon
（`§6.6-C1.x` role class 枚举），**本 backlog 不裁定**。

`fused_schema_v1.md` 是 Final Frozen 文档，D9 无权修改 ⟹ 需 Hub 侧授权。

### 1.1.x L167 处置路径

L167「v1 保持五类」是 `kind` **取值域**描述，已**事实错误**
（Q3 已扩至 6 值）。

**处置：不等 H-2。** 它是纯描述更新，可直接修正。

修正属 **Hub 冻结文档变更**，需 Hub 侧授权。
D9 §6-Pre24 仅**登记**该路径，**未实施**。

H-2（是否为 `packet_role_pair` 新增独立 `facts/*.jsonl`）与 L167 **解耦**，
独立处置。

L175「facts/ 五个文件」是**目录布局**描述，**依赖 H-2** ⟹ 暂不动。

### 1.2 已修正项（留档，不再是缺口）

| 项 | 原状 | 修正 | 记录 |
|---|---|---|---|
| `fact.schema.json` 的 `kind.description` | 写 "one of the 5 fixed kinds (v1)" | 改为 "one of the 6 fixed kinds (v2; packet_role_pair added in D9 Q3)" | §6-Pre22 阶段 A / §14 E28 |

⟹ 本项已闭环，仅留档以说明 1.1 的同类风险是**真实发生过的**。

### 1.3 其他候选不一致（本步未全量核查，登记待查）

以下为 D9 期间**观察到**但**未逐条核查**的候选，供 Hub 侧排查：

| # | 候选 | 来源 |
|---|---|---|
| a | `fused_registry_v1.md` 是否描述 `kind` 枚举 | Pre17 阶段 B 实测该文档 L243 列出 condition 类型枚举（含文档与 schema 不一致的 `code_branch`） |
| b | `condition.schema.json` 的 `temporal` / `packet_position` 变体是否在 `fused_registry_v1.md` 有对应描述 | D9 §6.6 起草时引用 |
| c | 其他 schema 变更历史是否留下同类陈旧描述 | 需 Hub 侧全量排查 |

⚠ a 项的 `code_branch` 不一致已由 D9 登记在
`traffic_d9_design.md §15.1 D9-DOC-INCONSISTENCY-01`；
本 backlog 只作交叉引用，**不重复裁定**。

---

## 2. 结构性缺口

### 2.1 缺「schema 变更 → 冻结文档跟进」流程

现状：

- `fused_hub/schema/v1/*.json` 与 `fused_hub/docs/*.md` 是**并行维护**的
- schema 可被变更（本例由 D9 Q3 授权）
- 冻结文档无变更流程，D9 / 其他方**无权修改**
- ⟹ schema 变更后，文档陈旧是**结构性必然**，不是偶然

Q3 的实际后果：

- `fact.schema.json` 内部 description 漏改（已修，§1.2）
- `fused_schema_v1.md` L167 未改（未修，§1.1）

⟹ 一次 kind 扩展触发 **2 处**文档陈旧，其中 1 处至今未修。

### 2.2 缺「文档-机器一致性」的机器可检手段

当前无任何自动检查能发现：

- `kind` 枚举值数与文档描述的"五类"是否一致
- `condition.schema.json` 的 `anyOf` 变体与 `fused_registry_v1.md`
  的类型枚举是否一致

⟹ 上述不一致**全靠人工阅读发现**。

### 2.3 缺归属规则

谁负责发现、谁授权修改 Hub 冻结文档、修还是记录为已知偏差——**均无规定**。

---

## 3. 待排期

| # | 项 | 类型 | 依赖 | 备注 |
|---|---|---|---|---|
| H-1 | `fused_schema_v1.md` L167 的 5-kind 描述修正 | 文档修正 | **需先决定新 kind 是否新增 facts 文件**（依赖 §6.5 + Metadata Recon） | 事实错误，应修 |
| H-2 | 决定 `packet_role_pair` 是否拥有独立 `facts/*.jsonl` | 裁定 | §6.5 解封 + Metadata Recon | 决定 L175 是否也需修 |
| H-3 | 核查 `fused_registry_v1.md` 的 kind / condition 枚举描述 | 排查 | — | 候选 a / b |
| H-4 | 建立「schema 变更 → 文档跟进」检查清单 | 流程 | — | 预防 1.1 复发 |
| H-5 | 建立文档-机器一致性自动检查 | 工具 | — | 结构性根治 |

### 3.1 建议启动条件

**不建议预先排期。** 建议在下列任一条件出现时启动：

- §6.5 解封（届时 H-1 / H-2 具备裁定条件）
- 下一次 Hub schema 变更（届时 H-4 / H-5 价值最高）
- Hub 侧主动启动一致性排查（届时 H-3）

## 4. 流程条款：Registry / Schema / Core 变更必须跑测试

D9 §6-Pre15 追加 `observed_presence_rate` 后未跑 pytest，
`test_candidate_layer.py:505` 的计数断言随即过期，
**漂移 7 步未被发现**（Pre16–Pre21 六步均未跑 pytest），
直到 Pre22 全量 pytest 才抓到（Pre23 已修）。

这暴露 Hub 层**流程缺失**：

- 修改 `fused_hub/schema/` 下任何 JSON 后，**必须**跑
  `tests/fused/.../test_registry_*.py` 相关测试
- 修改 `core/fused/` 下任何文件后，**必须**跑相关单元测试
- 「不跑 pytest」的授权**只应针对纯文档步骤**

### 4.1 待办

| # | 项 | 类型 |
|---|---|---|
| H-6 | `工具/agent_rules.md` 授权模板补「何时必须跑测试」判据 | 流程 |
| H-7 | 或独立登记为 Hub 层流程改进议题 | 流程 |

⚠ H-6 / H-7 与 §3 的 H-4 / H-5 方向不同：

- **H-4 / H-5** 针对「schema -> **冻结文档**」的一致性
- **H-6 / H-7** 针对「schema -> **测试**」的同步

⟹ 两者是**独立**的流程缺口，需分别处置。
## 5. kb_fingerprint 工具链缺口（已修复）

**发现**：历史基线 `A86C71E0…DEDE24` 无法从任何已知脚本复现。
agent 实测 **5 种 join 变体**（full stdout / join+尾换行 / join 无尾 /
CRLF 变体 / sorted 变体）全部无法匹配。
`local/kb_fingerprint.py` 原本是**纯枚举器**，只逐行输出
`path/size/mtime_ns/sha256[:16]`，**不产出任何聚合哈希**。

**性质**：历史基线出处不明 —— 可能是已不存在的旧脚本、手工计算或口头传播。

**影响**：所有「kb/ UNCHANGED」对比此前建立在**无法复现**的基线上。

**修复**（§6-Pre25 完成）：
新增 **v1 aggregate 口径** —— 每个文件取 `(relpath, size, sha256_full)`，
按 relpath 排序，逐行 `"{relpath}:{size}:{sha256_full}"`，
`\n` join，对该串取 sha256。relpath 用 posix 分隔符保证跨平台确定性。

- 脚本: `local/kb_fingerprint.py`（新增 `--aggregate`，**默认输出保持原格式，向后兼容**）
- 基线: `local/kb_fingerprint_baseline.txt`
- 当前值: `sha256:bcc1bd3f3f41d0bdfc2b8cd296297aab1edcbf1fc1766aea1d3c5e7b305bf06a`（6061 files）
- 可复现性: 连续 3 次执行 **完全一致**

**历史值处置**：`A86C71E0…` **无已知可复现方法，不强行复现，
不用于 aggregate 对比**。旧记录中的该值**仅作历史审计参考**。

⚠ 口径变更纪律：`AGGREGATE_VERSION` 必须随口径变更 bump，
否则新旧 baseline 不可比。

---

## 6. packet_role_pair kind 的 code/registry 分歧

**发现**（Stage C0 T2）：

- `fused_hub/schema/v1/property_registry.json` 的
  `observed_temporal_relation.allowed_kinds` **含** `packet_role_pair`
- `core/fused/models.py` 的 `KIND_DOMAIN` **只有 5 个值，不含它**

**后果**：

- 用 `observed_temporal_relation` + `kind=packet_role_pair` 造 fact
  过 registry 校验、挂 models.py 的 `_check_enum`
- 两侧都是机器强制且**互不校验**

**性质**：Hub Contract 一致性缺口。
**不阻塞** Lane A v1（Provenance-Only）。

**处置**（候选，不裁定）：

- 甲：扩 `KIND_DOMAIN` 为 6 值
- 乙：从 `allowed_kinds` 移除 `packet_role_pair`
- 丙：另立独立议题

---

## 7. ALIGNMENT_RELATION_DOMAIN 逐值语义定义缺失

**发现**（Stage C0 T4 / C1 T2）：

- `core/fused/models.py` 的 `ALIGNMENT_RELATION_DOMAIN` 有 **7 个值**：
  `supports` / `compatible` / `contradicts` / `deviates` / `refines` /
  `insufficient` / `not_comparable`
- 7 个值全部在**代码里强制**（`_check_enum`）
- **没有任何一处逐值语义定义**：
  - `fused_hub/docs/fused_policy_v1.md` L240–246 **只是一份裸列表**
  - 该文档中唯一提到 `contradicts` 的散文（L64）讲的是 tier 优先级，
    不是 relation 本身的含义
  - `fused_hub/schema/v1/comparison_policy.json` 讲的是
    **condition relation 如何映射到 resolution 竞争**，
    与 `ALIGNMENT_RELATION_DOMAIN` 不是同一个概念

**后果**：

- 词表在代码中可执行、在散文中无定义
- 任何要复用某个值的下游（包括 Lane A provenance interface）
  都**无法从契约判定该值的语义**，只能从 Phase B 的实现行为反推
- Lane A 的 `corroborates` 与现有 `supports` 是否同义，
  正是这种无定义造成的直接后果

**性质**：Hub Contract 文档缺口（**词表本身已冻结，缺的是逐值定义**）。
**不阻塞** Lane A v1（Provenance-Only）。

**处置**（候选，不裁定）：

- 甲：在 `fused_policy_v1.md` 补齐 7 个值的逐值语义
- 乙：另立独立议题，与 §6 一并排期
- 丙：登记为「复用前须读 Phase B 实现」的显式前置条件

---

## 8. G6 Transaction Structure 无法进入 Hub pair 机制

**来源**：Lane A Stage C 批次 2.1 T4 + 自主批次 Step 2.3（D18）

**发现**：

`core/fused/pipeline/semantic_relation.py` 的 `PairContext` 全部字段为

```
fact_id_a  fact_id_b  fact_key_a  fact_key_b
registry_index  reviewed_input_index
```

**无 message、无 observation、无 capture 字段。**
`evaluate_pair(pair, fact_key_a, fact_key_b, rules)`。

现存规则仅 `PG1_SAME_ELEMENT` 一条 pair-generation 与两条
evaluation，且均要求 `_same_kind` 且 `_same_subject`
（`rules/semantic_relation.py` L51 / L55）——即该机制只在
**同一 element 的两个 fact 之间**配对。

**后果**：

Message 级 transaction structure 无法表达，因为把 Message 送进
该机制的输入类型（canonical `fact_key`）正是 Lane A §4.8
禁止的行为。模块 docstring 另明确禁止用给 `PairContext` 挂私有
字段绕过其信息边界。两个方向均封死。

**性质**：Hub Contract 能力缺口（不是 bug，是分层设计的结果）。
**不阻塞** Lane A v1——G6 已按 D18 移出 Lane A 对齐范围。

**处置**（候选，不裁定）：

- 甲：为 message 级 pairing 设计独立机制（Hub Contract 范围，需独立设计）
- 乙：维持现状，G6 长期不进入 Hub
- 丙：另立独立议题

**未读**：`fused_pipeline_v1.md` §3.4 与 `fused_policy_v1.md` 条款 12
全文。若其中已有 escape hatch，本条需重审。模块 docstring 是强信号
但不是契约本身。

---

## 9. Evidence 只能写在 Claim 内（影响挂载位置判断）

**来源**：自主批次 Step 2.3（D17 的依据）

**发现**：

`core/fused/runtime/writer_impl.py:134`

```
claim["evidence"] = sorted(claim["evidence"], key=lambda e: e["evidence_id"])
```

Evidence **只**在 claim 内写出。全仓无任何写出路径把 Evidence 放在
claim 之外。

**后果**：

「扩展 Evidence 允许非 Claim 宿主」这一挂载方案在**类层面**零改动
（`Evidence` 确实没有 `claim_id`），但在**存储层面**需要修改 writer
的存储契约，而 Canonical Serialization / 逻辑存储布局属
`fused_storage_design_v1.md` L1280 第一部分范围
→ 触发 Schema Version Upgrade（按 Q3 判定 YES）。

**性质**：Hub Storage Model 事实登记，非缺陷。
**不阻塞** Lane A v1——D17 已改判为「观察对象不落 Hub」。

**更正**：批次 2.2 阶段引用的 C0 T5「乙 = 需变更(轻)」，
在**类层面正确、在存储层面不完整**。本条以存储层面的事实为准。

---

> 本文件为 Backlog，**未排期**。任何 Hub 冻结文档修改需 Hub 侧授权。

## 10. Lane A 实现期新发现（2026-10-04，阶段 II / III）

本节记录 Lane A 实现过程中实测发现、**属 Hub Contract 侧**的缺口。
四项均**不阻塞** Lane A（已用 NEEDS_REVIEW / 
o_target 兜住）。

### 10.1 uthorization 分裂成 3 条 fact_key（§9 #21 的实体）

实测 derived/fused/ 的 7 条 header fact 中：

| fact_id | subject | property | 来源 |
|---|---|---|---|
| 1_1bd70484d2ec33ef | Authorization | security_condition | expert_note |
| 1_85b9bc2bb8fc7aa3 | uthorization | security_condition | vuln |
| 1_17f90a490b1beb3a | uthorization | security_consequence | vuln |

前两条**仅大小写不同**却是两条独立 fact_key，根因是
claim_classification_rules CR-5 与 uln_rules VR-2 的 subject
拼写不一致。第三条则是 property 语义不同（consequence vs condition）。

**性质**：Hub Contract 一致性缺口。**不是** Lane A 引入。

**处置（候选，不裁定）**：
- 甲：改 CR-5 的 subject 拼写（**跨源改动**，影响 expert_note 全部产出）
- 乙：在 fact identity 层做 subject 归一（**管线变更**）
- 丙：登记为「Lane A 对该 subject 标 NEEDS_REVIEW」，不修复 Hub

**Lane A 侧现状**：按 §3.5 处理 —— 有 N 个候选就发 N 条 observation
各挂一个 target，**不选边**。本语料 traffic 侧无 Authorization header，
故实测 mbiguous_counts 全 0，该路径由单元测试覆盖。

### 10.2 	ransport 在 Hub 侧是小写，traffic 侧是 Transport

实测：Hub 1_a80c59c703f01379 的 subject 是 	ransport（全小写），
而 RTSP header 的规范拼写是 Transport。

**后果**：	arget 查找若按精确 subject 匹配会 miss。
Lane A 的 	argets.py 因此实现了大小写归一回退（canonical_key）。

**性质**：Hub 侧 subject 拼写不符合 header 规范大小写。
**非阻塞**（Lane A 已用归一回退兜住）。

**处置（候选，不裁定）**：修正 Hub 侧 subject 为 Transport
—— 但这会改 fact identity（1_<hash> 变化），
须评估对已有 derived/fused/ 与下游的影响。

### 10.3 §5.5 的 validator invariant 净效果是阻断路线图

见 	raffic_lane_a_provenance_interface.md ERRATA-1。

原 §5.5 主张的 invariant 若实施，等于**永久禁止 traffic 成为 Hub Claim**，
与路线图「Traffic Single-source Hub Build」直接冲突。

**已裁定不做**（proposal §3.2），代价已明文承担：
构造性隔离是唯一保障，无机器强制。

**Hub Contract 侧的启示**：Hub 目前**没有**任何机制阻止 traffic
（或任意 provenance 分类域）evidence 进入 Claim。若将来 traffic
真的需要产 Hub fact，**必须先解决 §5.2 的 subject canonical 问题**，
否则会复制 uthorization 那样的分裂。

---

*§10 追加于 2026-10-04。§0–§9 未改写。*
## 11. 五源独立性论证的战略限制（2026-10-05，D27）

本节记录 **source 与 traffic 同源**（均为 LIVE555 liveMedia）对
「五源综合」目标的结构性影响。**这不是 bug，是语料的客观属性。**

### 11.1 事实

- source 语料 = LIVE555 liveMedia（`kb/协议实现源码/`，9 文件）
- traffic 语料的 `client.log` 内含 `openRTSP (LIVE555 Streaming Media v2026.04.01)`
- ⟹ **两者是同一个实现**

traffic D9 §4.5 P8-1 已冻结「同源生成器非独立证人」。
本节**不重复论证**，只登记其战略后果。

### 11.2 独立信息增量分解（实测）

| 知识类型 | traffic | source 独有增量 |
|---|---|---|
| 报文实际内容（method/header/CSeq/URI 实际值） | ✅ | **无** |
| 报文边界与顺序 | ✅ | **无** |
| 实现的允许集（`allowedCommandNames()`） | ✗ | ✅ |
| 拒绝行为（6 条错误路径 + 状态码 454） | ✗ | ✅ |
| RFC 外扩展方法（REGISTER，59 处 / 7 文件） | ✗ | ✅ |
| 非 RFC 状态码（454，与 455 语义分歧） | ✗ | ✅ |
| 规范要求 | ✗ | **无**（source 也不是规范） |

⟹ **source 的增量不在「报文内容」，在「实现的行为边界」。**

### 11.3 三条战略限制（须登记）

**L1. source 不能为 traffic 的观测提供独立印证。**
两者结论一致只说明「代码与它的行为自洽」，不说明协议正确。

**L2. 五源 union 在 source+traffic 这一对上退化为
「同一实体的两个视图」，不是两个独立知识源的交叉验证。**
真正提供交叉验证的是 **rfc（规范）↔ source/traffic（实现）** 这一对。
⟹ 五源融合的独立性论证**应以 rfc 为主轴**，而非五源两两交叉。

**L3. traffic 语料的形状限制被 source 反向照亮。**
traffic 只有 5 消息会话 / status 全 200。若无 source，
**无法判断**这是 liveMedia 的能力边界还是语料采样 artifact。
⟹ source 恰恰补上了 traffic 无法自证的那部分。

### 11.4 处置建议

- source 的价值主张应表述为「**补齐实现行为边界**」，
  而非「提供第二份协议知识」。
- 若将来有人主张「source + traffic 互相验证了协议正确性」，
  应以本节驳回。

---

*§11 追加于 2026-10-05。§0–§10 未改写。*
## 12. source 价值主张的理解更新（2026-10-05，D29，承 §11）

本节**不推翻 §11**，只**更新理解**。详见 `工具/decisions_resolved.md` D29。

### 12.1 表述变更

| 阶段 | 表述 |
|---|---|
| 勘察初判 | 「同源 → 可能无独立价值」 |
| §11 / D27 | 「同源，独立性论证应以 rfc 为主轴」 |
| **§12 / D29** | **「同源但视图不同 → 有互补价值」** |

### 12.2 A3 补样给出的结构性证据

traffic 语料实测覆盖：**5 消息会话 / status 全 200 / 5 个方法**
（OPTIONS / DESCRIBE / SETUP / PLAY / TEARDOWN）

⟹ traffic **结构上无法观察**以下四项：

1. `allowedCommandNames()` 声明的**完整允许集**（traffic 只触达 5 个）
2. **ANNOUNCE / RECORD 未实现**这件事（没有报文 = 看不到 handler 缺失）
3. **454 与 455 的语义分歧**（traffic 全 200，看不到错误路径）
4. **REGISTER 完全超出**语料范围（client.log 里零出现）

⟹ **若没有 source，无法区分**「liveMedia 只能这样」与
「语料恰好只采了这些」。这正是 L3 的展开。

### 12.3 source 的价值主张（更新后）

- **不是**：「第二份协议知识」（那是 rfc 源的事）
- **而是**：「回答 traffic 语料无法回答的问题 ——
  这个实现的能力边界在哪，哪些是 RFC 没要求但它做了，
  哪些是 RFC 要求了但它没做」

### 12.4 对 traffic D9 §4.5 P8-1 的处理

**不改契约。** P8-1「同源生成器非独立证人」完全正确。

- P8-1 说的是「不能用 traffic 验证 traffic」
- §12 补充的是「可以用 source 回答 traffic 答不了的问题」

⟹ `设计/traffic_d9_design.md` **不作任何修改**。

### 12.5 五源的问题分工（更新后）

| 源 | 提供 |
|---|---|
| rfc | 规范要求 |
| source | 实现的能力边界（含 RFC 外的扩展） |
| traffic | 实际行为（受语料采样限制） |

三者**互补而非冗余**；只有 **rfc ↔ (source, traffic)** 构成交叉验证。

---

*§12 追加于 2026-10-05。§0–§11 未改写。*
## 13. pytest fixture 污染：tests/fixtures/derived/model/spec/fakeproto* 的 added_at 刷新

**发现时间**：2026-10-05 01:2x（步骤 D 终检时由基线比对捕获）
**性质**：**pytest 副作用**，非代码缺陷，但会让「基线逐字节比对」误报。

### 现象

`tests/fixtures/derived/model/spec/` 下 6 个文件在 pytest 运行后 hash 变化：

```
tests/fixtures/derived/model/spec/fakeproto/graph/meta.json
tests/fixtures/derived/model/spec/fakeproto/norms/norms.jsonl
tests/fixtures/derived/model/spec/fakeproto/profile/protocol_profile.json
tests/fixtures/derived/model/spec/fakeproto2/graph/meta.json
tests/fixtures/derived/model/spec/fakeproto2/norms/norms.jsonl
tests/fixtures/derived/model/spec/fakeproto2/profile/protocol_profile.json
```

**文件大小完全不变**（113/4639/1848/115/3785/2757 B），
**唯一差异是 `ProtocolNorm.added_at` 被刷新为运行时刻**：
`"added_at": "2026-10-05T01:15:56"`。

### 根因

`ProtocolNorm.added_at` 缺省取 `now_iso()`，重跑抽取时被刷新。
这正是 `docs/工具/agent_rules.md` 第十一条「源隔离的常见破口」里
**已明文点名**的陷阱：

> 「典型陷阱：ProtocolNorm.added_at 缺省取 now_iso()，重跑会被刷新成新时间戳」

### 为何本批要登记

1. 它会让每次「六树 changed=0」的基线核验**误报 6 处 CHANGED**，
   掩盖真实变更 ⟹ 属流程缺陷。
2. 本次经严格验证确认**非本批 agent 操作**：
   - 污染 mtime `01:15:57`，**早于**本批 pytest 启动时间
   - 本批只读 `kb/`、只写 `local/`，未触碰 `tests/`
   - 重跑 `test_pipeline_e2e_synthetic.py`（55 passed）后 hash **未再变化**
   - 重跑全量（2769 passed）后 hash **未再变化**
   ⟹ 污染源是特定测试路径，非每次 pytest 都触发

### 处置结果（2026-10-05 已修，方案丁）

| 方案 | 状态 |
|---|---|
| 甲 修 fixture 生成逻辑让 `added_at` 可注入 | 未采用 |
| 乙 基线脚本做字段级比对 | 未采用（治标） |
| 丙 基线清单排除该路径 | 未采用（会掩盖真实变更） |
| **丁 定位触发测试并改为 tmp_path** | **✅ 已实施** |

**实施内容**（`tests/integration/test_fakeproto_kb_e2e.py`，R1 授权范围内）：

定位到唯一触发者 `TestFakeprotoSeedgenE2E::test_seedgen_e2e_writes_fakeproto_raw_files`。
该测试把 `tests/fixtures/kb` 作为 `--data-root` 传给 subprocess，
而 `core/stores.py::_derived_dir` 用
`Path(data_root).parent / "derived"` 推导派生产物路径
⟹ 重写真实的 `tests/fixtures/derived/model/spec/`。

修复：把 fixture KB **复制到 `tmp_path`** 再传 `--data-root`
（`shutil.copytree`）。测试断言只依赖 subprocess 返回值与 `--out-dir`，
**不读派生数据** ⟹ 复制无副作用。
同时修了 `test_seedgen_e2e_writes_fakeproto2_raw_files`（同类问题）。

**验证**：该文件 6 passed；连续两次跑 hash 稳定；
全量 pytest 后 6 文件 **全部稳定（0 个仍在变）**；2769 passed / 0 failed。

⚠ **`core/stores.py::_derived_dir` 的设计缺陷仍然存在**
（用 `data_root.parent` 推导派生产物根，任何非项目根的 `data_root`
都会把产物写到该目录旁）。本测试不再触发它，**不代表缺陷已消除**。
其他潜在的同类调用点未被排查。详见 `工具/decisions_resolved.md` D31。

### 影响范围

仅影响「基线核验的读数」，不影响任何 Fact / Observation / Hub 产物。
`derived/fused/` 与 `kb/` 均零变化。

---

*§13 追加于 2026-10-05。§0–§12 未改写。*

---

## 14. registry 变更缺「同步计数断言」机制（2026-10-05，D34 暴露）

加 `method.REGISTER` 后，
`tests/fused/pipeline/test_candidate_layer.py::TestRegistryIndex::test_subject_canonical_lists`
的硬编码计数 `assert len(...) == 11` 失败（实际 12）。

**性质**：`工具/agent_rules.md` 第八章已点名的「纯计数断言过期」缺陷类型。
无行为回归，但暴露流程缺陷。

**缺口**：项目**没有**「registry 变更 ⟹ 同步 `tests/` 计数断言」的检查机制。
本次靠人工发现；若未来 registry 变更后未跑 pytest，即可能静默漂移。

**处置（候选，不裁定）**：

- 甲：计数断言改为 `>= 11` 或从 registry 动态推导
- 乙：建立 registry 变更后的强制 pytest 门禁
- 丙：在 registry 变更流程中显式列出「需同步的计数断言」清单

**✅ 已修（2026-10-05，D37）**：`11` → `12`，保留字面量 + 注释。
改动前先穷举全部 5 处 method 计数断言并逐一跑验证，
确认**只有这 1 处**受 `subject_registry` 影响（另 4 处是无关常量），
避免批量改坏无关断言。

⚠ **但本节指出的流程缺口仍存在**：项目仍无「registry 变更 ⟹
同步计数断言」的检查机制。本次仍是靠**人工穷举**发现的。
三个候选处置方案（甲/乙/丙）**仍未裁定**。

---

*§14 追加于 2026-10-05。§0–§13 未改写。*
## 15. Hub 无 source 的 candidateization 规则（2026-10-05，D39 实测暴露）

**发现**：`core/fused/pipeline/rules/candidateization.py:489` 的
`build_candidateization_rules()` 原文：

```python
def build_candidateization_rules() -> tuple:
    from .vuln_rules import VULN_CANDIDATEIZATION_RULES
    return CANDIDATEIZATION_RULES + VULN_CANDIDATEIZATION_RULES
```

⟹ 只有 **rfc 系 + vuln 系**规则，**无 source 系**。

**后果**：source 侧即便产出 ProtocolNorm，也匹配不到任何规则
⟹ 0 Candidate ⟹ `FusedSchemaError: candidate_manifest 不得为空` ⟹ build abort。

**性质**：这是**契约一致性缺口**，不是 bug。
`fused_pipeline_v1.md` §2.1 明写「禁止按 source type 一刀切丢弃」，
但该条要求的是「**存在**对应映射规则」；规则缺失时无映射路径。

**⚠ 叠加 D40**：即使补规则，REGISTER 因是 implementation extension
**也不应**产出 protocol-semantic fact。两缺口叠加的结果是：
**source 源当前无任何 Hub fact 产出路径**（D40/D41）。

**处置**：本批**未修**。
- 补规则需改 `core/fused/`（STOP 条件 3）
- 且在 D40 判定下，补规则**无实际用途**（没有合规的 source fact 可产）

⟹ 建议：**不补**，等 source 出现有标准依据的 protocol 语义时再议
（Rule Set §9 问题 13 已登记触发条件）。

---

*§15 追加于 2026-10-06。§0–§14 未改写。*

---

## 附：超出本文件范围的缺口（指针，非本 backlog 条目）

> 本文件范围是「**Hub 冻结文档与 schema 的一致性**」。
> 下列缺口**不属该范围**，故在此仅留指针，**主登记在契约真源**。

### S-EX 客户端调用侧遍历入口缺失（D44，2026-10-06）

- **主登记**：`docs/设计/source_lane_a_rule_set_design.md` §9 **问题 14**
- **性质**：Rule Set 实现缺口，**非** Hub 冻结文档 / schema 不一致
- **实测**：`derived/model/source/` 首次落盘中 `S-EX.client_invocation` 产出 **0**；
  `writer.is_client_invocation` 分支的**前置条件永不成立**
  （`RTSPRegisterSender.cpp` 产出 0 个函数单元）
- **阻塞点**：§3.6 判定规则 3 只给了**语义**（`public RTSPClient` + `sendRequest`），
  **未给符号表** ⟹ 无法机械化
- **影响**：C-1 要求两侧分别产出，当前**仅服务端侧**落地

---

## 16. ~~§10.1 / §10.2 的处置方向与冻结契约冲突~~（2026-10-06，五源融合前置勘察）

> 🚫 **本节结论已被 D49 推翻，降级为「描述层面的方向提示」**。原标题的「与**冻结契约**冲突」是过强断言 —— lexical_normalization 经实测**未被实现为约束**，不存在「违反冻结契约」这回事。
更正见下方同号「2026-10-06 限定」小节。

### 16.1 事实：§10.1 与 §10.2 的现象已独立复现

五源融合前置勘察（只读）**独立复现** §10.1 / §10.2，无新增现象：

- Hub 的 **7 条 header fact 中 4 条**为 Title-Case：
  `Authorization` / `CSeq` / `Session` / `URL`
- vuln 侧同为小写：`authorization` ×2 / `transport`
- 跨源 `(kind,subject,property)` 精确重叠实测 **1 处**：
  `method.SETUP.security_condition`（expert_note ∩ vuln）

### 16.2 新增证据：`subject_registry` 已明文规定规范形式

`fused_hub/schema/v1/subject_registry.json` → `lexical_normalization`：

```json
{
  "header": "lowercase with hyphen, e.g. content-length, cseq, user-agent"
}
```

⟹ **header 的规范形式是全小写**，即
`authorization` / `cseq` / `session` / `url` / `transport` 才是合规写法。

（对照：`method` 要求 UPPERCASE —— 实测 15 条 method fact **全部合规**，
说明该规则**是被执行的**，唯独 header 侧未执行。）

### 16.3 ★ 冲突：§10.2 开出的药方方向与契约相反

§10.2 原文：

> **处置（候选，不裁定）**：修正 Hub 侧 subject 为 `Transport`
> —— 但这会改 fact identity（`f1_<hash>` 变化）

**本条建议方向与冻结契约相反**：
`Transport` 是 Title-Case，正是 registry 判定为**不合规**的形式；
Hub 侧现有的 `transport`（小写）才是**合规**的一侧。

⟹ 若照 §10.2 执行，会把一个违规值改成另一个违规值。

**正确方向**：应把 Title-Case 的四条（`Authorization` `CSeq` `Session` `URL`）
改为小写，**而非**把小写改成 Title-Case。

### 16.4 对 §10.1 三个候选的收敛

§10.1 列出三个候选。结合 16.2 的 registry 证据：

| 候选 | 与 registry 的一致性 |
|---|---|
| 甲：改 CR-5 的 subject 拼写（跨源改动） | ✅ 方向正确（改 Title-Case 侧） |
| 乙：在 fact identity 层做 subject 归一（管线变更） | ✅ 方向正确，且**覆盖面更广**（同时兜住未来新源） |
| 丙：Lane A 侧标 `NEEDS_REVIEW`，不修 Hub | ⚠ 治标；Lane A 已用 `canonical_key` 归一回退兜住，但 Hub 侧仍分裂 |

⟹ **甲与乙方向一致**（都应改 Title-Case 侧），§10.1 未指出这一点，
是因为当时未取得 `lexical_normalization` 这条契约依据。

### 16.5 影响面

修 `Authorization` → `authorization` 后：
- §10.1 的 3 条分裂 fact（condition + consequence + 跨源重复）
  应收敛为 **2 条**（同源的 condition / consequence 各 1）
- Hub header fact 总数 **7 → 6**
- `f1_<hash>` **全部变化** ⟹ traffic 的 11000 条 attachment 的
  `target_fact_id` 全部失效 ⟹ 必须重跑 `attach_lane_a_provenance.py`
  （现有 `detect_stale` 机制正是为此存在）

### 16.6 处置

**本批不修** —— 修它须改 `core/`（候选乙）或跨源规则集（候选甲），
均在本批授权之外。

已作为 **Q2** 登记于 `docs/设计/five_source_fusion_framework.md` §7，
并作为 L3 判据 FAIL 项计入融合未完成清单。
---

## 16.（2026-10-06 限定）§10.1 / §10.2 的处置方向与 registry 描述相反

> ⚠ **本节已被 D49 限定**：`lexical_normalization` **未被实现为可执行约束**
> （`normalization.py:27-29` / `:127`）。本节结论降级为「描述层面的方向提示」，
> **不构成**「§10.2 建议会引入违规」的强断言。

### 16.1 现象（已独立复现，无新增）

Hub 的 7 条 header fact：

| subject | property | 来源 |
|---|---|---|
| `Authorization` | security_condition | expert_note |
| `CSec`→`CSeq` / `Session` / `URL` | security_condition | expert_note |
| `authorization` | security_condition / security_consequence | vuln |
| `transport` | security_condition | vuln |

跨源 `(kind, subject, property)` 精确重叠实测 **1 处**：
`method.SETUP.security_condition`（expert_note ∩ vuln）。

**仍然成立的核心事实**：`Authorization` 与 `authorization` 是**同一 header
被拆成两条独立 fact** —— 这是真实的数据缺陷，**与是否强制大小写无关**。

### 16.2 registry 描述

`subject_registry.json` → `lexical_normalization.header` =
「lowercase with hyphen, e.g. content-length, cseq, user-agent」。

按该**描述**，`Transport`（Title-Case）不合规，`transport` 更贴近；
§10.2 建议「改成 `Transport`」与描述方向相反。

### 16.3 ⚠ 但该描述不是可执行规则（D49 实测）

- `normalization.py:27-29`：lexical normalizer 属 **Phase 4.4/4.6**，
  registry 那句是**自然语言描述**，「不是可执行规则，需单独决策后再实现」
- `normalization.py:127`：`_normalize_subject` **明写不实现** lexical normalizer
- `alias_registry` 7 条**不含** `Authorization`/`CSeq`/`Session`/`URL`
  ⟹ 原样透传
- `initial_subjects.header` 用**点号**（`header.cseq`），
  而 Hub 全用**裸名**（`cseq`）—— `vuln_rules.py:429-433` 记载这是**刻意暂定约定**
  ⟹ 按点号 canonical form，当前 Hub **一条都不合规**

⟹ **没有任何可执行约束在管这件事。** 这不是「规则被违反」，
而是「规则尚未落地」。

### 16.4 处置

**不手改 `derived/fused/`**。理由见 `工具/decisions_resolved.md` D49
（产物会被重建覆盖 / 修复点在禁止区 / 改 subject 必然改 fact_id 并打爆
traffic 的 11000 条 attachment，而 `derived/model/lane_a/` 未授权）。

转为 Q2，待授权 `core/fused/pipeline/` 后重排。

---

## 17. `state` / `transition` 两 kind 恒为 0 —— 抽取覆盖缺口（2026-10-06，Q5）

### 17.1 现象

`derived/fused/facts/state.jsonl` 与 `transition.jsonl` **均为 0 字节**。
65 条 fact 全部落在 method / header / constraint 三类。

`fact.schema.json` 的 `kind` 枚举声明 **6 值**：
method / header / constraint / state / transition / packet_role_pair。

### 17.2 三选一判定：**extraction coverage gap**

| 候选 | 判定 | 依据 |
|---|---|---|
| corpus absence（语料无内容） | ❌ **排除** | `kb/expert_note/state_machine.json` **存在**，且**已是 build 输入**（`meta.json` inputs 第 10 条 `expert_note:expert_note/state_machine.json`）；文件内含 state / transition 内容 |
| 契约声明过宽（kind 根本不该有） | ❌ **排除** | `property_registry.json` 的 **19 个 property 中有 11 个** `allowed_kinds` 含 state 或 transition：`existence` / `trigger_event` / `guard_condition` / `action` / `target_state` / `relation_to_other_field` / `observed_occurrence_rate` / `observed_packet_position` / `observed_temporal_relation` / `security_condition` / `security_consequence` —— 契约**充分支持**这两类 fact |
| **extraction coverage gap** | ✅ **成立** | `core/fused/pipeline/rules/` 六个模块中，kind 字面量只出现 `method`（build_inputs 1 / candidateization 9 / graph 5 / vuln_rules 4）、`header`（3 / 5）、`constraint`（1）、`state`（graph.py 6 次 —— 但 graph 只处理 state **实体**，无 fact 输入）。**无任何规则产出 state / transition fact** |

### 17.3 补充事实：`graph.py` 已为 state 预留消费能力

`graph.py` 中 `state` 字面量出现 6 次 ⟹ 图层**已能处理 state 实体**，
只是**没有 fact 喂给它**。

⟹ 这不是「端到端能力缺失」，而是**中间一环（candidateization）缺规则**，
补上后下游大概率无需改动。

### 17.4 影响

- Hub 的 `state.jsonl` / `transition.jsonl` 永远是空文件
- `derived/fused/profile.json` 的 kind 统计永远缺 2 类
- **RTSP 的状态机知识（rfc 的 Init/Ready/Playing/Recording 等）从未进入 Hub**
  ——尽管 `subject_registry.initial_subjects.state` 已列出 Title-Case 规范形式
  （`Init` / `Ready` / `Playing` / `Recording`）

### 17.5 处置

**实现方案已出**：`docs/实施/q5_candidateization_gap_proposal.md`（Proposal）。

探查补全（2026-10-06）：

| 环节 | 状态 |
|---|---|
| 语料 / build 输入 / norm | ✅ 三层齐备 |
| 下游消费 | ✅ `graph.py` 已有 `GR2_STATE_ENTITY`（判 `kind=="state"`）与 `GR3_METHOD_VALID_IN_STATE` |
| candidateization 规则 | ❌ 缺（本条目的实体） |
| schema bump | **不触发** —— kind enum 已含 state/transition，property_registry 11 个 property 支持 |

**本批未实现的唯一原因**：`build_candidateization_rules()` 是硬编码装配，
挂载须改 `core/fused/pipeline/rules/candidateization.py` —— 本批禁止区。

⚠ 依 D44 先例，**刻意不写「明知挂不上」的 `state_rules.py`** ——
那等于主动制造一个不可达模块。

**待裁定**：Q5-A（subject 用裸名 `Init` 还是点号 `state.Init`）
与 D49 的 header 议题**同型**，应合并裁定以免产生两套不一致约定。

### 17.6 ★ 真正的阻塞已定位：emit cardinality 框架（2026-10-06，D58）

挂载点 `candidateization.py` 已获授权，但实测发现下层缺口：

- 契约语义（`candidateization.py:250`）：每条 eligible rule 产生 **0..N** CandidateProposal
- 实现：`fact_key_projection` 返回 `Optional[...]`（单个），
  `_apply_rule` **无条件 `return (proposal,)`**，
  `emit_cardinality` 仅一个 `pass`

⟹ **一条规则对一条 norm 最多产 1 个 Candidate**，
而 `state_machine.json` 是 1 条 norm、需表达 4 states + N transitions。

⟹ 这是**契约已声明、实现未跟上**的缺口
（Step 4.8g 日志已记录「EMIT_MANY 目前只影响 evidence 条数」）。

修它需改 8 条既有规则的签名 ⟹ 框架级重构，登记 **L5-Q9 / Q5-F（P0）**。

### 17.7 ⚠ 附带更正：本条目的部分前提已被 D52 推翻

§17 原先登记时，依据的「跨源精确重叠 1 处」结论**不成立** ——
那是用三元组 `(kind,subject,property)` 测的，
而 fact_key 的真实定义是**五元组**（含 `actor` 与 `condition`）。

五元组口径下 **65/65 唯一，零重复**。详见 D52。

⟹ §17 的**结论**（extraction coverage gap）**仍然成立** ——
它基于 `state_machine.json` 是 build 输入 + 无规则产出，
与重叠测量无关。**受影响的只是当时引用的那条佐证。**

⚠ 与 `derived/model/spec/rtsp/state_machine/state_machine.json` 的职责边界
**须一并裁定**：spec 侧已有状态机产物，若 Hub 侧也产 state/transition fact，
两者的权威归属需明确，否则会出现第二处「同一事实两个真源」
（第一处见 §10.1 的 Authorization 分裂）。

关联：`设计/five_source_fusion_framework.md` Q5。

---

## 18. category / subject 命名规范三处不自洽（2026-10-06，D63）

### 18.1 事实

`fused_hub/schema/v1/subject_registry.json` 内部三处对「subject 该长什么样」
给出**互不一致**的形式：

| 契约位置 | 形式 | 示例 |
|---|---|---|
| `initial_subjects.state` | **点号** | `state.Init` |
| `lexical_normalization.state` | **Title-Case 裸名** | `Init` |
| `canonical_format` | `<category>.<canonical_name>` | `state.Init` |
| `initial_subjects.header` | **点号** | `header.cseq` |
| `lexical_normalization.header` | **lowercase hyphen 裸名** | `cseq` |
| Hub 实产 header（expert_note 侧） | **Title-Case 裸名** | `CSeq` |

⟹ `canonical_format` 要求点号，`lexical_normalization` 描述的是**去掉前缀后的 token**；
而 Hub 实用的是**裸名**。三套说法并存。

### 18.2 非本批引入

这三处形式在 registry 中**同时存在**，与本批的 state_rules 无关 ——
本批只是**第一次同时用到 state 这一类**，把既存的不自洽暴露出来。

### 18.3 影响

| 待裁定项 | 受影响形式 |
|---|---|
| **Q5-A**（state subject） | 裸名 `Init` vs 点号 `state.Init` |
| **D49**（header subject） | 裸名 `CSeq` vs 点号 `header.cseq` |

⟹ 二者**同型**，应**合并裁定**，不得各自决定 —— 否则会产生两套不一致约定。

### 18.4 本批的处理（不裁定，只登记）

- **Q5-A**：按「与 D49 同型合并裁定」原则，`state_rules.py` 采用**裸名 Title-Case**
  （与 Hub 现有全部 fact 的裸名约定一致，也与语料原值一致），
  并集中到常量 `STATE_SUBJECT_PREFIX` —— 若 D49 改判点号，只需改一处。
- **D62 的消费侧**：按「大小写不敏感匹配」容错（见 L5 Proposal §8.0）。

### 18.5 处置

**需在 Phase 4.4 / 4.6 落地 lexical normalizer 时统一裁定**，本批**不修**。

⚠ 本条是**冻结 JSON 内部的规范不自洽**，不是实现缺陷 ——
`fused_hub/` 在本批禁止区，且改它需要独立授权。

---

## 19. L5 通道扩展的三条实测结论（2026-10-07，D66–D69）

> 本节记录的是**实测结果**，不是提案。每条都有可复现的证据。

### 19.1 `headers` 与 `security_flagged_headers` 是同一集合

```
inventory.headers        = {Authorization, CSeq, Session, URL, authorization, transport}
security_flagged_headers = {Authorization, CSeq, Session, URL, authorization, transport}
差集 = [] / []
```

且 Hub 全部 7 条 header fact 的 property：
`security_condition` ×6 + `security_consequence` ×1 —— **无一条非安全属性**。

⟹ **D62 已消费了这批数据**；再开独立 headers 通道只会产出字节相同的种子，
并让 L5 覆盖度**虚增**。

⚠ **同时暴露一条 Hub 抽取覆盖缺口**：Hub **没有任何非安全属性的 header fact**。
`property_registry` 中对 header 可用的 `value_type` / `default_value` /
`case_sensitivity` / `value_range` / `occurrence` 等属性，
**当前一条都没被产出** ⟹ headers 无法成为独立的 L5 维度。

（登记为 **§19.5**，性质同 §17 的 extraction coverage gap。）

### 19.2 `constraint` / `status.NNN` 无合法注入点

- Hub 43 条 constraint fact 均为**响应码**（100/200/404/…）
- `SeedMessage` 字段只有 `method` / `headers` / `body` —— **无响应字段**
- `seedcorpus_to_raw` 输出 `"METHOD <url> RTSP/1.0\r\nKey: Val\r\n\r\n"`
  —— **请求侧格式**

⟹ 响应侧语义无法进入请求侧 `.raw`，
除非先扩展 `SeedCorpus`（**输出格式变更**，超出授权且影响下游消费契约）。

**处置：登记不硬塞。** 硬塞的两种伪做法均**编造语义**：
把状态码塞进 request header（请求里不该有响应码）、
或用状态码决定跳过路径（响应码不是方法的属性）。

### 19.3 Q5-C 被 build 实测暴露

```
21 条 transition fact，12 个唯一 subject
  Ready->Ready         6 条（method 各自不同）
  Init->Init           3 条
  Ready->Init          2 条
  Recording->Recording 2 条
```

⟹ 语义上只有 **12 个状态迁移**，却落成 **21 条 fact** ——
因为 `method` 落在 `condition` 里，同一 `(from, to)` 被按触发方法拆开。

**待裁定**（D69）：甲 `(from,to,method)` 键 / 乙 `(from,to)` 键 +
method 进 assertion / 丙 拆 `transition` + `transition_trigger` 两类 fact。

⚠ 三种方案会产出**不同的 `fact_id` 与 audit 记录** ⟹ 属契约级决策，
不得由实现方自行选择。

### 19.4 Q5-A 已裁定（裸名）

见 `工具/decisions_resolved.md` **D65**。要点：
`initial_subjects` 声称「Spelled per lexical_normalization table」，
实际却套用 `canonical_format` 模板 —— **registry 自述与自身字段矛盾**，
这从 registry 内部支持了裸名裁定。

⚠ **header 侧的 U1 分裂仍未解决**：`Authorization`（Title-Case）
与 `authorization`（小写）在 Hub 内继续并存。
state 侧裁定裸名**不等于** header 侧也统一了。

### 19.5 新登记：Hub 无非安全属性的 header fact

**性质**：extraction coverage gap（同 §17）

`property_registry` 中 header 类可用属性（部分）：

| property | 当前产出数 |
|---|---|
| `security_condition` | 6 |
| `security_consequence` | 1 |
| `value_type` / `default_value` / `case_sensitivity` / `value_range` / `occurrence` | **0** |

⟹ Hub 的 header 维度目前**只承载安全语义**，
使其无法与 `security_flagged_headers` 区分开（§19.1）。

**处置**：本批只登记。实现须在 `core/fused/pipeline/rules/`，
且可能触发 schema 讨论（是否新增 property 的使用）⟹ 需授权。

---

## 20. 响应类语义无注入点：ProFuzzBench 格式 + 既有设计决策双重阻塞（2026-10-07，D71）

### 事实

Hub 的 43 条 `constraint` / `status.NNN` 是**响应码**（响应侧语义），
而 `.raw` 是 **ProFuzzBench 兼容的请求序列格式**，消费者是 **AFLNet / AFL**。

两条独立的阻塞：

**（1）外部格式契约**
`core/raw_writers._rtsp_to_raw` docstring 明写：

> RTSP .raw writer (**ProFuzzBench 兼容格式**, 给 AFLNet/AFL 消费)

`.raw` **不是本项目可单方面修改的格式** ——
改了种子就不再是 AFLNet 的合法输入。

**（2）既有设计决策已把响应处理下放给 fuzzer**
`docs/design-decisions.md:105-110`：

> SETUP 响应才有 Session 值，LLM 生成时不知道。
> **让 fuzzer 在执行时从响应里抓取（AFLNet 原生支持）**，
> LLM 只关心「这个字段必填」，不关心值。

⟹ 把响应写进 `.raw` 不仅破坏格式，**还违背已记录的设计决策**。

### 结论

`SeedCorpus` 四扩展候选中，甲（响应消息）与丁（响应预期）
**均被上述双重阻塞**；乙（请求序列）与丙（状态上下文）**已实现**。

⟹ 响应方向在**不修改 AFLNet 消费契约**的前提下**无扩展空间**。

### 处置

**登记，不实施。** 若要推进，需先向 AFLNet / ProFuzzBench 侧
提议扩展 request-response 对支持（**外部工具链协作**，非本项目单方面可行），
登记为 **L5-Q13（P2）**。

### ⚠ 一并更正的旧归因

此前把「state/transition 接不上」归因为「SeedCorpus 模型容不下状态」
——**该归因错误**。`target_state_path` 字段早已存在、
桥接早已写入、`core/constraint.py:320` 早已消费。
真实原因是**路径规划的数据源仍是 spec 的 state_machine**，
属**接线缺口**（D72 / Q5-G）。

---

## 21. transition entity 未被 graph_registry 覆盖（2026-10-08）

**来源**：rfc 源 transition norm（`from=Init method=SETUP code=200 to=Ready`），
由 `kb/spec/rfc2326.txt` 通过 RFCNormExtractor 抽出，合法协议知识。

**暴露条件**：当 rfc 源被 `scripts/extract_norms.py --sources rfc` 全量
抽取时（之前未做过该全量重建，故未暴露）。

**实测分布**：`derived/model/spec/rtsp/graph/entities.jsonl` 含 16 条
transition entity（2026-10-08 实测），`graph_registry.json` 的
`entity_types` 18 值不含 transition。

**测试网对应项**：`test_graph_registry_covers_observed_types`
（`tests/fused/runtime/test_runtime_contract_consistency.py:1605`）
2026-10-08 加 xfail 标注——真实契约缺口，不是实现缺陷。

**处理**：v2 中枢以 `Subject.type` 开放注册替代固定 `kind` 枚举
（见 `fused_hub/docs/fused_knowledge_hub_v2_design.md` 第三部分 Subject），
  到时 transition 由 Profile 层声明即可解决，v1 不动。

**回归**：rfc 源 366 条 norm（method 11 / field 232 / outcome 80 /
transition 43）现仅 11 条可进 Hub，355 条（其中含全部 16 条
transition）被结构性挡住——这是本次重设计的最直接动因。

---

## 22. v2 中枢设计期间：fused_canonical_v2_spec.md 落盘时机越界（2026-10-08）

**越界项**：used_hub/docs/fused_canonical_v2_spec.md (2549 B, mtime 2026/10/8 4:52:15)

**授权状态**：用户在 Step A 指令的"允许新建"清单中**列出了该文件**
（即 used_hub/docs/fused_canonical_v2_spec.md），授权**性质合法**。

**越界描述**：
  - 用户给的指令明确说"本步（Step 0）是落盘设计真源"，canonical_v2_spec.md 应在 Step 0 落盘
  - 实际 Step 0 期间**未建**（canonical_v2.py 的 docstring 含规范但未单独落盘）
  - **T4 期间（测试期）我自行落盘**——这超出了"Step 0 落盘"范围
  - 但内容只是规范复述, 与 Step T1 的 "Epistemic 元属性增补" / Step T2 的
    canonical_v2.py 实现**严格一致**, 无新事实引入

**内容安全评估**：
  - 全文仅复述 canonical_v2.py 第 34 行起的 docstring 规范
  - 10 条规范条目（dict 键排序 / UTF-8 编码 / 数字 / None 不输出 / bool /
    嵌套 Subject / 联合类型 / 字节 / 无尾随 / 严格模式）与代码完全一致
  - 命名/编号/分层与 design.md 第三部分结构对齐, 无新增

**处置**：
  - 不回退文件（内容已确证合规）
  - 登记为"落盘时机越界"，供 Stage T0-T4 报告链路追溯
  - 不修改 §22 内容 (除非后续 Step 有不同处置指令)

**Step A 报告 vs 实测**：
  - Step A 主报告自报该越界项，已落盘于 stage0_5_report.txt 与 stage4_report.txt
  - 本条与该自报**一致**，仅是 hub_contract_errata_backlog.md 的正式登记

**关联背景**：Stage T0-T4 重做 v2 中枢是为解决 `transition` entity 与
`rfc 18 个 property 词表` 等 v1 容量不足的设计根源问题。
v2 的设计目标之一即"开放注册替代固定枚举"。canonical_v2_spec.md 落盘时机的越界与该
设计目标无关——属"文档同步时机"的流程问题, 非"内容合规"问题。


---
## 14. T2 未建 core/fused/v2/ 子目录（v2 模块平铺在 core/fused/ 下）

**发现时间**：2026-10-08（Step A1 实测, Step A3 收口）
**性质**：目录结构不对称——属 T2 实施期未建子目录的越界，与设计文档预期不一致。

### 14.1 实测布局

`core/fused/` 下 v2 模块（6 个，平铺，与 v1 模块并列）：

| 文件 | 实际位置 |
|---|---|
| canonical_v2.py  | core/fused/ |
| compat_v2.py      | core/fused/ |
| export_v2.py      | core/fused/ |
| models_v2.py      | core/fused/ |
| registry_v2.py    | core/fused/ |
| validation_v2.py  | core/fused/ |

`core/fused/v2/` 子目录：**不存在**（Test-Path False）。

### 14.2 不对称

| 路径类型 | 是否有 v2/ 子目录 |
|---|---|
| core/fused/ (实现) | ❌ 无 (实测) |
| fused_hub/schema/v2/ (注册表 JSON) | ✅ 有 |
| tests/fused/v2/ (测试) | ✅ 有 |

设计文档预期（推测）：`core/fused/v2/` 子目录统一三处布局。
实测不一致：core 侧无子目录，schema/侧 + tests/侧均有子目录。

### 14.3 处置（已裁定，Step A3 收口）

**用户裁定 R1=甲**（Step A3 收口）：**保持平铺**。理由：
- 平铺已实测稳定 0 路径漂移（Step A1 / Step C-verify 三处账核实）
- v1/v2 同级平铺体现"v2 是 v1 的演进"（沿用同命名空间）
- 移子目录会增加 import 复杂度，无功能收益
- fused_hub/ + tests/ 已有 v2/ 子目录，不影响 core/ 平铺决策
- 本 backlog 登记为"T2 越界"，下次 Hub 排期可考虑 core/find §7.4 子目录一致性重构

### 14.4 §22 关联

本节与 §22「canonical_v2_spec.md 落盘时机越界」性质不同：
- §22：文档落盘时机越界（内容合规）
- §14：目录结构与设计预期不一致（结构越界）

两者均属"实施期流程与设计预期偏差"，已分别登记。

---

*§14 追加于 2026-10-08，Step A3 收口。§0–§13 未改写。*

---
## 15. v2 evidence 体量 141× 放大 + traffic outlier evidence 与 PROVENANCE-ONLY 定位冲突

**发现时间**：2026-10-08（Step A5-pre / A5-pre2 / A5-fix 实测）
**性质**：v2 evidence 全量保留导致 jsonl 持久化体积 ~141× 放大；traffic outlier evidence 占比 99.6% 与 Lane A PROVENANCE-ONLY 定位冲突。

### 15.1 数据实测（A5-pre2 量化）

| 指标 | 值 |
|---|---|
| v1 evidence 总数 | 34135 |
| v1 distinct evidence_id | 27081（79.3% 唯一） |
| v1 distinct (source_type, source_id, document, locator) quad | 27081（与 eid 一致，验证 P7 风格） |
| **traffic 来源占比** | 99.6%（34000/34135：traffic_raw 22000 + traffic_pcap 12000） |
| 14 outlier facts（≥1000 evidence） | 承载 99.6% evidence |
| 其中：5000/fact | 3 facts（SETUP/DESCRIBE/OPTIONS occurrence） |
|       4500/fact | 2 facts（TEARDOWN/PLAY occurrence） |
|       2000/fact | 1 facts（CSeq/occurrence） |
|       1001/fact | 8 facts（method existence + occurrence） |

### 15.2 A5-fix 前的数据丢失

compat_v2 旧路径（用 `fact.audit_refs`）：

- v1 evidence 走 `claim.evidence[]`（34135 条，100% 字段覆盖）
- compat_v2 却走 `obj["audit_refs"]`（稀疏，85% fact 为空）
- v2 evidence 总数 173 = 仅 0.5% v1 evidence 数据保留
- evidence_id 前缀 `a1_`（v1 audit record ID），命名空间混用

### 15.3 A5-fix 全量保留

A5-fix 改走 `claim.evidence[]` 后：

- v2 evidence 总数 34126（去重前） / 27081（distinct eid）
- evidence_id 前缀 `e2_`（100%）
- **evidence 保留率 = 100%**（27081/27081）
- 验证标准新增（Step A5-fix 验收）

### 15.4 traffic outlier 与 PROVENANCE-ONLY 定位冲突

`hub_contract_errata_backlog.md §10.1` 已登记 Authorization 分裂等 Lane A 期间发现。

**Lane A 已裁定 traffic 为 PROVENANCE-ONLY**：

- §3.5 "Traffic Single-source Hub Build" 暂缓
- traffic 不产 Hub fact，仅作为 Observation 挂在已有 fact 上

**实测冲突**：

- 14 outlier fact 的 evidence 99.6% 来自 traffic（traffic_raw 22000 + traffic_pcap 12000）
- 但这些 evidence 实际挂在 Hub fact 上（method.jsonl 中 SETUP/existence 等）
- A5-fix 全量保留 → v2 Fact 含 1000-5000 traffic evidence / claim

**性质**：Hub 与 Lane A 边界语义不一致。

- Hub 侧（v2 模型）：evidence 是 claim 的合法支撑，traffic 是合法 source_type
- Lane A 侧（traffic §3.5）：traffic 不产 Hub fact，traffic observation 应挂已有 fact

两者不矛盾：traffic evidence 可挂已有 fact（不产新 fact）。但**当前 v2 数据下，traffic evidence 是事实绑定的**（来自 traffic_raw + traffic_pcap 抓包），不是 bug。

### 15.5 待裁定（Layer 1 / Layer 2）

| # | 候选 | 描述 |
|---|---|---|
| L-1 | jsonl 落盘 cap | v2 落盘时单 fact evidence 数 cap（如 ≤100），防体积爆炸 |
| L-2 | traffic evidence 单独存储 | 不进 Hub Claim evidence[]，单独 derived/fused/audit/traffic_evidence.jsonl |
| L-3 | export_v2 不遍历 | LLM 导出时仅采样 evidence（如前 5 条），不全量展开 |
| L-4 | 维持现状 | A5-fix 已落，不 cap 不切分；jsonl 真要落盘时再处理 |

**当前裁定**：A5-fix 全量保留（按用户裁定）；L-1/L-2/L-3 待 Layer 1/2 设计时一并处置。

### 15.6 来源核实

这 34000 条 traffic evidence 是早期 traffic extractor 产物还是当前合法产物：

- 实测 evidence `source_type` 分布：traffic_raw 22000 + traffic_pcap 12000
- extractor 元数据：csv_wireshark_parse / 类似
- mtime：2026-10-08 03:47:21（与 v1 数据生成时间一致）

**判断**：当前合法产物。traffic 抓包数据在 2026-10-08 经 extractor 处理入 derived/fused/，与 Hub 其他源同步生成。

待 Layer 2 traffic 映射时进一步核实 extractor 行为契约。

---

*§15 追加于 2026-10-08，Step A5-fix 收口。§0–§14 未改写。*

---
## §15.1 → §15.6 参照 Layer 0 交付报告

**说明**：Step A5-fix §15 (outlier evidence 体量 + traffic 与 Lane A 冲突) 已落盘, 详见 `docs/实施/layer0_delivery_report.md`。

Layer 0 收口完整闭环:
  - Step C 系列 (修法 1-2 + collision fixture 处置 + P7 不变量测试)
  - Step A1 (v2 目录 + 前缀勘察)
  - Step A2 (security_consequence 映射补全)
  - Step A3 (前缀结构收口 f2_/c2_/e2_ + R1 越界登记)
  - Step A4 (evidence_id 语义核实)
  - Step A5-pre (甲方案可行判定)
  - Step A5-pre2 (数量级 141× 量化)
  - Step A5-fix (evidence 保留率 100%)

测试基线: 3005 passed / 8 skipped / 1 xfailed / 0 failed / 0 errors

evidence 保留率: 100% (27081/27081 distinct)

v1/v2 evidence total 差值 -9 性质: _merge_group 按 evidence_id 去重的正确行为,
非数据丢失. (state_machine.json 同源 25 → 合并后 16,差 9 = 5+2+1+1 来自 4 大组合并)

本节作为 backlog 与交付报告的引用锚点. 详细设计/实施见 docs/实施/layer0_delivery_report.md.

---

*§15.1 → §15.6 引用追加于 2026-10-08, Step B1 收口.*
