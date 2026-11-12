# docs/设计/各源设计/流量源/traffic源观测独立性设计.md — traffic 源 D9 观测独立性口径设计

> 状态：Final Frozen（除 §6.5 BLOCKED）
> §0–§13: FINAL FROZEN
> §6.5: BLOCKED（等 M3 外部输入）
> §6.6-C1.x: PENDING（依赖 Metadata Recon）
> 上游：docs/工具/交接与工作流/项目交接说明.md、docs/设计/各源设计/漏洞源/vuln源收口设计.md（分层原则）
> 契约依据：docs/设计/顶层设计/规范化序列化规范.md、docs/设计/顶层设计/规范化序列化规范.md、docs/设计/顶层设计/规范化序列化规范.md、docs/设计/顶层设计/规范化序列化规范.md
> 本文件为 traffic D9 阶段设计真源。
> 本文件为 standalone 设计真源，不依赖任何 superseded draft。

---

## 0. 文档定位 / Scope

### 0.1 本设计要解决什么

traffic 源进入 中枢 前，必须先冻结观测独立性口径。否则存在 raw observation 被一对一 materialize 为 voting Claim 的风险，从而：

- 虚增 Phase A 中的 Claim multiplicity；
- 扩大 Phase B 产生的 alignment 数量；
- 使 raw sampling multiplicity 被误解释为 independent semantic support。

说明：Phase B 本身不是 voting algorithm。D9 不修改 Phase B relation taxonomy。上述第三项指「错误 Claim multiplicity 会扩大 Phase B 的输入与 alignment materialization」，不是「Phase B 被投票污染」。

**当前侦察快照**：25998 norm / 3000 capture。以上数量仅描述当前输入快照，不属于 D9 semantic invariant。

### 0.2 本设计暂不涉及什么

本阶段不决定具体 cluster key、clustering algorithm、schema field、代码接口或 migration。

但本阶段允许冻结后续实现必须满足的 deterministic semantic invariants。语义层与实现层的边界必须在第一轮就明确，避免「既然不涉及实现，那 deterministic / unknown 行为也不用定」的误解。

### 0.3 产物清单

| 产物 | 章节 | 内容 |
|---|---|---|
| A | §4 Observation Taxonomy | 观测层级语义 |
| B | §6 Property Measurement Contract | 每 property 的 measurement contract |
| C | §7 Independence Semantics | independence 三态与判据 |
| D | §9 Hub Boundary | cluster / independence 信息归属层 |
| E | §8 Traffic Claim Formation Contract | raw observation → Traffic Claim 的聚合契约 |

外加：
- §5 Observation Formation & Deduplication Boundary（dedup ≠ dependence）
- §6.x Contract / Binding / Validation Status Semantics（三层状态模型）
- §10 Downstream Interpretation Contract

---

## 1. D9 Hard Boundaries

以下 10 条为 D9 后续讨论的护栏。冻结后不得在后续章节被重新打开。

### 1.1 与 Hub 算法边界

1. **D9 不修改 Phase A Resolution Algorithm。**
2. **D9 不修改 Phase B relation taxonomy。**
3. **D9 不引入 Claim weighting。** `raw_support_count` / `independent_support_count` 不作为 Phase A voting weight。（此条比「不修改 Phase A」更具体。因为可能有人声称「算法没改，只是加了 weight 字段，consensus 用了它」——这已改变 Phase A 语义，禁止。）

### 1.2 与 fact_key 边界

4. **dependency cluster 不得进入 canonical fact_key。** `capture_id` / `session_id` / `cluster_id` / `scenario_id` / `collection_run_id` 表达的是「我在哪里、通过什么采样过程观察到这个 Fact」，不是「这个协议 Fact 在讨论什么」。若进入 fact_key，同一 `header.content-length × occurrence_frequency` 会因抓包批次不同被拆成数十个不同 Fact，违背「按协议目标信息组织，不按知识源 / 采集来源组织」。

### 1.3 与观测语义边界

5. **raw observation 不一对一形成 voting Claim。**
6. **independence semantics 在 traffic observation → traffic Claim 阶段消化。** Phase A 消费的是已经具有正确 observation semantics 的 Claim，不是 raw observation votes。

### 1.4 相关性与独立性的语义边界

7. **Different dependency clusters do not automatically imply independence.** 不同 cluster 只有在满足 Frozen Independence Policy 时才视为独立。
8. **`independence = unknown` 不得自动提升为 `independent-under-policy`。** unknown 不得自动进入 `independent_support_count`。
9. **Deduplication 与 dependency / independence assessment 是不同阶段，不得互相替代。** duplicate ≠ dependent；dependent ≠ duplicate。

### 1.5 Support semantics 与 Claim 语义等级的边界

10. **Support multiplicity 不得改变 Claim 的语义等级。**

    `raw_observation_count`、`support_unit_count`、`independent_support_count`、`dependent_support_count`、`unknown_support_count` 均不得改变 Claim 的：
    - `claim_class`
    - `authority`
    - `modality`
    - Phase A tier
    - Phase A voting weight
    - Phase B relation type

    它们描述「这条 observational assertion 由怎样的观测结构支持」，不描述「这条 Claim 在 Fusion Policy 中拥有多大的投票权或规范权威」。

**边界总则**：

```
Rule 3：禁止 weighted Claim mechanism。
Rule 10：禁止 support statistics 偷偷泄漏进 classification / authority / fusion semantics。
```

---

## 2. D9 第一原则

### 2.1 原则陈述（Frozen）

> **Traffic capture identity 不等于 evidence independence。**
>
> 不同 capture 不自动构成独立证据。
>
> 同一 dependency cluster 表示相关性已经被确定；同 cluster 内 observation 不得因为 observation 数量增加，形成额外 independent support。
>
> 不同 dependency cluster 也不自动意味着统计独立。
>
> 只有满足 Frozen Independence Policy 的 observation unit，才能标记为 `independent-under-policy`。
>
> 无法根据 Frozen Independence Policy 确定独立性的 observation unit：`independence = unknown`。
>
> unknown 不得自动按 independent 处理。
>
> 因此：**raw observation multiplicity 不得直接转化为 Claim multiplicity，也不得直接转化为 Phase A voting weight。**

### 2.2 三态语义

| 状态 | 含义 |
|---|---|
| `dependent` | Frozen Independence Policy 已确定该 support unit 与同 dependency scope 中其他 observation 存在需要避免重复计数的依赖关系。此判定是 D9 operational semantics，不声称完成一般统计意义上的 dependence proof。 |
| `independent-under-policy` | 满足 Frozen Independence Policy，视为独立。命名已包含「under-policy」限定：不是对真实世界统计独立性的绝对数学证明。 |
| `unknown` | 无法确定，禁止自动按独立处理 |

**关键界定**：三态属于 Frozen Independence Policy 下的 operational classification，不是对真实世界统计独立性的绝对数学证明。

### 2.2.x Scope Qualification

```
dependent / independent-under-policy / unknown
均是在明确以下 scope 下得到的 operational classification：

- aggregation scope
- dependency scope
- Frozen Independence Policy

该状态不得被解释为 support unit 脱离 scope 后的永久全局属性。

同一 support unit 在不同合法 scope 下，
允许产生不同 independence classification；
任何统计使用必须携带对应 scope semantics。
```

### 2.3 关键否定

- 同 cluster **≠ 只保留 1 条 Evidence**。cluster 约束的是 independent support accounting，**不是 Evidence preservation**。
- 不同 cluster ≠ automatically independent。
- unknown ≠ independent。

---

## 3. Quantity Separation Semantics

### 3.1 三层数量模型

本设计冻结**概念区分**，不冻结未来 Schema 必须有九个字段。未来 Schema Gap Review 才决定哪些直接存储、哪些可派生、哪些只存在于 traffic aggregation intermediate state。

#### 3.1.1 Observation Layer

| 量 | 定义 |
|---|---|
| `raw_observation_count` | Observation Formation 完成后、deduplication 之前的 observation 数量。这里的 raw 指 **pre-dedup observation**，不指 raw traffic record / raw packet record。Raw traffic records 属于 Observation Formation 之前的输入层 |
| `deduplicated_observation_count` | 经过 Exact / Deterministic Deduplication 后保留下来的 distinct observations 数量 |
| `eligible_measurement_count` | 对某 property 的 measurement contract，满足 eligibility predicate、实际进入 numerator / denominator 计算域的 measurement 数量。具体定义由 §6 每个 property 冻结 |

数学约束（此层唯一显式约束）：

```
deduplicated_observation_count <= raw_observation_count
```

#### 3.1.2 Materialization / Provenance Layer

| 量 | 定义 |
|---|---|
| `evidence_record_count` | 某 Traffic Claim 最终在 Hub provenance 中 materialize 的 Evidence records 数量。**它不是 observation count。** 例如 100 个连续 packet locator 完全可能被一个 packet_range Evidence 表示。因此 100 observations → 1 Evidence record 是合法的 |
| `claim_count` | 在明确 fact_key + observation / aggregation scope 下形成的 Traffic Claims 数量。**禁止脱离 scope 写 `claim_count = N`** 而不说明对哪个 fact、哪个 source snapshot、哪个 aggregation scope |

#### 3.1.3 Independence Support Layer

| 量 | 定义 |
|---|---|
| `support_unit_count` | 进入 Independence Assessment 的 support units 总数 |
| `independent_support_count` | 被 Frozen Independence Policy 明确判定为 `independent-under-policy` 的 support units 数量 |
| `dependent_support_count` | 被 Frozen Independence Policy 明确判定为 `dependent` 的 support units 数量。它们不增加 independent support multiplicity，**但不能从统计记录中消失** |
| `unknown_support_count` | 无法根据 Frozen Independence Policy 确定独立性的 support units 数量。**不得合入 `independent_support_count`** |

严格 partition（此层唯一显式约束）：

```
support_unit_count
=
independent_support_count
+
dependent_support_count
+
unknown_support_count
```

### 3.2 Semantic Non-Equivalence

以下数量属于不同 semantic domains：

```
raw_observation_count
deduplicated_observation_count
eligible_measurement_count
evidence_record_count
claim_count
support_unit_count
independent_support_count
dependent_support_count
unknown_support_count
```

它们之间即使数值偶然相等，也不意味着语义相同。

除非某 Property Measurement Contract 明确给出 deterministic derivation rule，**禁止通过一个数量隐式推导另一个数量**。

### 3.3 Scope-qualified Counts

所有 traffic statistical counts 都必须解释在明确 scope 下。

裸值：

```
independent_support_count = 37
```

本身语义不完整。至少必须能够回答：

- 哪个 protocol fact？
- 哪个 property？
- 哪个 observation population？
- 哪个 measurement unit？
- 哪个 source snapshot / collection scope？
- 哪个 Independence Policy version / semantics？

**D9 不允许脱离 scope 把 raw N 当成全局 prevalence / confidence。**

### 3.4 与 D9 第一原则的对应

§2.1 末句「raw observation multiplicity 不得直接转化为 Claim multiplicity，也不得直接转化为 Phase A voting weight」由本节落实：三层模型各自独立计数，任何一对一转化视为违反 D9 第一原则。

---

## 4. Observation Taxonomy

本节为 D9 五产物之 A。

### 4.1 Taxonomy Design Principles

1. **不做简单 containment tree。** 不用「packet → message → transaction → session → capture」的树形结构。改用 typed observation relations。
2. **三分 domain**：Protocol Semantic Units / Transport Units / Observation Containers。
3. **每个 observation type 用统一模板**：Name / Domain / Semantic definition / Identity semantics / Relations / Allowed cardinality / Partial semantics。
4. **只定义 semantic sameness，不定义 actual identity key。**
5. **capture 不是协议语义的父节点。**
6. **区分 direct observation 与 derived observation。** Capture 直接 records / observes **Packet observations**。Message / Transaction / Connection / Protocol Session 通常是通过 packet reconstruction **派生得到的 higher-level observations**。「Capture observes higher-level units」不意味着这些 units 被直接编码为 capture records。
7. **Partial observation 不放宽 identity criteria**（见 §4.8）。

### 4.2 Protocol Semantic Units

#### 4.2.1 Message

| 项 | 内容 |
|---|---|
| **Semantic definition** | 一次 **logical protocol message transmission occurrence**。RTSP 中表现为一次 logical request transmission occurrence 或 logical response transmission occurrence。**Message identity 由「是否属于同一次 logical protocol transmission occurrence」决定，而不是由 message 内容是否相同决定。** 发送端与接收端对同一次 logical transmission 产生的 observation，不因此形成两个不同 Message。 |
| **Identity semantics** | 以下 transport-level 现象**不产生新的 Message**（仍对应同一次 protocol-layer message occurrence）：segmentation / reassembly / TCP retransmission / capture duplication / packet-level reordering。但 **application layer 重新发送一次相同内容的 request → 新 Message**，即使 start-line / headers / body 全部完全相同。 |
| **Relations** | `Packet` → contributes_to → `Message`（M:N，见 §4.7）；`Message` → participates_in → `Transaction`（0..1） |
| **Allowed cardinality** | 一个 Message 可由多个 Packet observations 承载；一个 Packet 可贡献于 0、1 或多个 Message |
| **Partial semantics** | 若 Message 未完整传输（截断 / 缺 body / 语法错误），标记为 partial Message observation。**partial 不得放宽 identity criteria**（见 §4.8） |

**关键界定**：两个内容完全相同的 SETUP request 若是 application layer 真正发送了两次，是**两个 Message occurrences**，不得因内容相同而合并。

#### 4.2.2 Transaction

| 项 | 内容 |
|---|---|
| **Semantic definition** | 以**一个 initiating logical request Message 为中心**的一次协议交换 occurrence。正常 RTSP semantic contract：`1 request + 0..1 logically corresponding response` |
| **Identity semantics** | 「一个 initiating request 与其逻辑对应的 response（若有）」构成同一个 Transaction。配对标准是语义上的请求-响应对应关系，不是某个具体 header 字段。请求与响应之间被其他 transaction 的消息交织不改变 identity。 |
| **Relations** | `Message` → participates_in → `Transaction`（0..1 per Message）；`Transaction` → belongs_to → `Protocol Session`（0..1，可选） |
| **Allowed cardinality** | `1 request + 0..1 response`。`0 response` 表示 partial / timeout / observation incomplete。**若观察到一个 request 对应多个 candidate responses**：记作 `ambiguous / anomalous transaction reconstruction`，**不自动把 Transaction 定义扩大成 1 request + N responses。** |
| **Partial semantics** | 缺失 response 一侧为 partial Transaction；不得因配对未完成而丢弃 request observation。partial 不放宽 identity criteria。 |

#### 4.2.3 Protocol Session

| 项 | 内容 |
|---|---|
| **Semantic definition** | 由**目标协议语义定义的 stateful logical session instance**。对 RTSP：一组共享同一 RTSP session context / state lifecycle 的交互。 |
| **Identity semantics** | **Protocol Session 不是**：TCP connection / capture / collection run / 任意 client/server 连续通信段 / 单纯时间上连续的一组 transactions。以下不改变 identity：① Session 跨越多个 transport connection；② Session 内有空闲间隙。 |
| **Relations** | `Transaction` → belongs_to → `Protocol Session`（0..1）；`Protocol Session` ⟂ `Transport Connection` |
| **Allowed cardinality** | 一个 Protocol Session 可跨多个 Transport Connection；一个 Transport Connection 可承载多个 Protocol Session |
| **Partial semantics** | 会话边界不完整标记 partial；仍保留全部 Transaction observation。partial 不放宽 identity criteria。 |

**关键界定**：

1. **没有加入任何 RTSP protocol session 的 transaction 允许 `belongs_to Protocol Session = none`。** session-independent transactions 不应为 taxonomy 完整性被强行塞进「伪 Session」。
2. **RTSP Session header** 未来可以成为 Session identity / reconstruction 的 deterministic evidence，但**它是不是 identity key 现在不决定**。
3. 若 Metadata Recon 后 D9 确实需要一个「连续交互上下文」概念，未来单独定义 observation grouping（如 `Conversation Trace` / `Interaction Segment`），**它将是 traffic observation construct，不是 Protocol Session**。现在不需要增加该类型，只需留下「non-session Transaction 合法存在」。

### 4.3 Transport Units

#### 4.3.1 Packet

| 项 | 内容 |
|---|---|
| **Semantic definition** | 传输层的最小可观察单元（TCP segment / UDP datagram 等） |
| **Identity semantics** | 「同一个网络传输单元」；TCP retransmission 产生新的 packet observation，即使 payload 与之前相同 |
| **Relations** | `Packet` → contributes_to → `Message`（**M:N**）；`Packet` → belongs_to → `Transport Connection`（0..1 per Packet） |
| **Allowed cardinality** | **Packet ↔ Message 为 M:N**：一个 Message 可由多个 Packet observations 共同承载；一个 Packet observation 可贡献于 0、1 或多个 Message。`0`：纯 ACK 或不承载目标协议 payload 的 packet；`>1`：一个 TCP segment 包含 Message A 尾部 + Message B 开头甚至完整 Message B |
| **Partial semantics** | Packet observation 的 partial / incomplete 指 **capture 层实际只获得该传输单元的部分信息**，例如 snaplen 截断 / packet bytes 缺失 / capture artifact corruption。**reordering 不使单个 Packet observation 变 partial。packet loss 表示 expected packet 未被 observation 捕获，不是一个 partial Packet observation。** |

#### 4.3.2 Transport Connection

| 项 | 内容 |
|---|---|
| **Semantic definition** | 一条传输层连接（TCP connection 等） |
| **Identity semantics** | 「同一条传输层连接」；重连产生新 connection observation |
| **Relations** | `Packet` → belongs_to → `Transport Connection`（0..1 per Packet）；`Transport Connection` ⟂ `Protocol Session`（**M:N**） |
| **Allowed cardinality** | Transport Connection ↔ Protocol Session = **M:N**。允许：① 一个 Protocol Session 跨多个 Transport Connection；② 一个 Transport Connection 承载多个 Protocol Session；③ 一个 Transport Connection 也可承载不属于任何 Protocol Session 的 Transactions。**不得用 Transport Connection boundary 推导 Protocol Session boundary。** |
| **Partial semantics** | 连接部分观察（缺失 handshake / teardown）标记 partial |

**术语 scope 提醒**：`Transport Connection` 是当前 D9 taxonomy 的工作名称。严格来说 UDP flow 不是 connection。**若 Metadata Recon 证明 traffic corpus 包含需要独立建模的 connectionless transport flows，则在实现设计前进行 terminology gap review。本节不因理论上的 UDP 支持提前增加 `Transport Flow` 类型。**

### 4.4 Observation Containers

#### 4.4.1 Capture

| 项 | 内容 |
|---|---|
| **Semantic definition** | 一次抓包过程的产物（pcap 文件或等价容器） |
| **Identity semantics** | 「同一次抓包操作」 |
| **Relations** | `Capture` → observes → Observation Object（**M:N**）。一个 Capture 可观察多个对象；同一 semantic object 也可被多个 Capture 观察。**direct vs derived 区分**：Capture 直接 records / observes Packet observations；Message / Transaction / Connection / Protocol Session 通常是通过 packet reconstruction 派生得到的 higher-level observations。 |
| **Allowed cardinality** | M:N（不假设一一对应） |
| **Partial semantics** | 抓包窗口截断 → capture 本身完整，但包含 partial observations |

**关键界定**：`Capture` **不是协议语义的父节点**。同一 protocol session 可以跨多个 capture 出现。

#### 4.4.2 Collection Run

| 项 | 内容 |
|---|---|
| **Semantic definition** | 一组 capture 的集合，通常对应一次实验 / 测试运行 |
| **Identity semantics** | 「同一次采集运行」 |
| **Relations** | `Collection Run` → contains → `Capture`（1:N） |
| **Allowed cardinality** | 一个 Collection Run 含多个 Capture |
| **Partial semantics** | **若预期 collection plan 未完整执行或部分 captures 缺失，Collection Run 可标记 partial。** partial run 仍保留，但**不得仅因同一 run 中样本数量较大推导独立支持。** |

### 4.5 Typed Observation Relations

| Relation | 从 | 到 | Cardinality | 语义 |
|---|---|---|---|---|
| `contributes_to` | Packet | Message | **M:N** | packet 贡献于 message 形成 |
| `participates_in` | Message | Transaction | **0..1 per Message** | 每个 Message 最多属于一个 Transaction；允许 `Message → Transaction = none` |
| `belongs_to` | Transaction | Protocol Session | **0..1 per Transaction** | 允许 non-session Transaction 合法存在 |
| `belongs_to` | Packet | Transport Connection | **0..1 per Packet** | 完整 reconstruction 通常 materialize exactly 1 relation；信息不足则 relation 未解析 / unknown，但不会因此允许一个 Packet 属于多个 Connection |
| `observes` | Capture | Observation Object | **M:N** | 一个 Capture 可观察多个对象；同一 semantic object 也可被多个 Capture 观察 |
| `contains` | Collection Run | Capture | 1:N | collection run 包含 capture |

**正交性定义**：本文中的「orthogonal / ⟂」表示两个 taxonomy object 的 **identity boundary 不得互相推导**，**不表示统计学意义上的 independence**。本文件后面专门讨论 independence，避免同一词被误读。

### 4.6 Identity Semantics

本节只定义 **semantic sameness**，不定义 actual identity key。

| 层级 | semantic sameness 判据 |
|---|---|
| Message | 同一次 protocol layer logical transmission occurrence；transport-level 分片 / 重传 / 交织不产生新 Message；application layer 重新发送相同内容 → 新 Message |
| Transaction | 一个 initiating logical request 与其逻辑对应的 response（若有）的配对 |
| Protocol Session | 目标协议语义的 stateful logical session instance |
| Packet | 一个网络传输单元；retransmission 是新 observation |
| Transport Connection | 一条传输层连接；重连是新 observation |
| Capture | 一次抓包过程 |
| Collection Run | 一次采集运行 |

**不回答的问题**（留待 Metadata Recon + implementation）：用什么字段 hash？用哪些 header / 5-tuple / timestamp？

### 4.7 Cardinality / Non-tree Constraints

1. **Packet ↔ Message = M:N。**
2. **Protocol Session ⟂ Transport Connection。** 非一一对应。
3. **Capture ⟂ Protocol Session。** 同一 session 可跨多个 capture，同一 capture 可观察多个 session。
4. **Transaction → Protocol Session = 0..1。** 允许 non-session Transaction 合法存在。
5. **Capture 是 observation container，不是 protocol semantic 父节点。**
6. **不得用 connection 边界推断 session 边界。**
7. **Capture 直接观察 Packet，其余为 derived observations。**

### 4.8 Partial / Incomplete Observation Semantics

**通用 invariant**：

> **Partial observation 不得放宽 semantic identity criteria。**
>
> 当可用信息不足以确定两个 partial observations 是否属于同一 semantic object 时：**identity relation = unknown，不得自动 merge。**
>
> partial 只表示 observation completeness，不表示 identity criteria 下降。

核心原则：**不确定是不是同一个，不等于同一个。**

| 层级 | partial 情形 | 处置 |
|---|---|---|
| Message | 截断 / 缺 body / 语法错误 | 标记 partial；identity criteria 不变；不足判定时 identity = unknown |
| Transaction | 缺 response（timeout / observation incomplete） | 标记 partial；identity criteria 不变 |
| Protocol Session | 观察窗口截断，会话中途开始/结束 | 标记 partial；identity criteria 不变 |
| Packet | snaplen 截断 / bytes 缺失 / artifact corruption | 标记 partial。reordering 不使 packet 变 partial；packet loss 不是 partial Packet |
| Transport Connection | 缺 handshake / teardown | 标记 partial |
| Capture | 抓包窗口截断导致包含 partial observations | capture 本身完整，但包含 partial observations |
| Collection Run | 预期 collection plan 未完整执行 / 部分 captures 缺失 | 标记 partial；不得仅因样本数大推导独立支持 |

任何层级的不完整 observation **不得因不完整而丢弃**（provenance 优先）。partial observation 仍参与 §5 dedup 与 §7 independence 判定。

### 4.9 §4 Invariants

1. Taxonomy 不是 containment tree，是 typed relations。
2. 三个 domain 分离：Protocol Semantic Units / Transport Units / Observation Containers。
3. **Message identity = logical protocol transmission occurrence ≠ content equality。**
4. **Packet ↔ Message = M:N。**
5. **Protocol Session = protocol-semantic stateful session，不是 client/server 连续交互段。**
6. **Transaction → Protocol Session = 0..1。** non-session Transaction 合法存在。
7. **Protocol Session ⟂ Transport Connection。** 不得用 connection 边界推断 session 边界。
8. **Capture 不是协议语义的父节点。** Capture 直接观察 Packet，其余为 derived。
9. **Partial observation 不放宽 identity criteria。** 不确定是否同一 semantic object 时，identity = unknown，不得自动 merge。
10. Identity semantics 是 semantic sameness，不是 implementation key。
11. 本节不决定任何实现 key。
12. **Message identity 表示 logical protocol transmission occurrence。** 同一 transmission 在 sender / receiver / 多个 capture points 被观察，不得因此形成多个 Message objects。
13. **Observation multiplicity 不得自动形成 semantic object multiplicity。** 同一 Message / Transaction / Protocol Session / Transport Connection 可以被多个 Capture / Evidence records 观察，但 semantic object identity 保持不变。

### 4.10 Open Questions Carried to §5 / Later

| # | 问题 | 目标章节 |
|---|---|---|
| G | Message reconstruction 具体算法 | §5 / Metadata Recon |
| H | request-response pairing rule | §5 / Metadata Recon |
| I | cross-capture semantic-object co-reference / canonicalization rules | §5 |
| L | multi-capture observation 与 Evidence preservation 的精确规则 | §9 Hub Boundary |
| M | Raw Record duplicate proof 依赖哪些 observable fields？ | Metadata Recon |
| N | Observation occurrence duplicate / correspondence proof 依赖哪些 observable fields？ | Metadata Recon |
| O | Semantic-object co-reference 的 deterministic proof rules 是什么？ | Metadata Recon |

I 与 O 的区别：O = general proof rule；I = cross-capture application of O。

---

## 5. Observation Formation & Deduplication Boundary

本节为 D9 边界章节。定义 traffic 从 raw record 到 semantic object 的观测形成、去重、co-reference 语义。**本节不讨论 independence counting。**

### 5.1 Layer-local Dedup Principle

> **Dedup 必须是分层的。**
>
> 只有在某一层能够确定两个记录 / representation 是该层意义上的重复时，才允许在该层 collapse。
>
> 多个不同 observation 即使指向同一个 semantic object，也不得因此删除。
>
> semantic object 合并并不意味着 provenance / Evidence 被删除或合并。

**七条原则（Frozen）**：

1. Deduplication is layer-local.
2. Exact duplicate raw records / duplicate representations may be deterministically collapsed at the layer where duplication is proven.
3. Distinct observation occurrences must not be deleted merely because they refer to the same semantic object.
4. Semantic-object co-reference / merge does not erase observation provenance.
5. Semantic-object merge does not imply Evidence merge/delete.
6. Object sameness and observation sameness are different questions.
7. **Identity resolution is layer-local.** Raw Record Layer 与 Observation Layer 只允许在各自 identity domain 内对已确定的 duplicate representation / duplicate materialization 执行 deterministic dedup。Semantic Object Layer 执行的是 deterministic **co-reference / canonicalization**，不是 observation dedup。任何一层的 identity resolution 都不得隐式删除其他层的 provenance-bearing occurrences。

**三个域的动词**：

| 层 | 动词 |
|---|---|
| Raw Record | **deduplicate** |
| Observation | **deduplicate / correspondence** |
| Semantic Object | **co-reference / canonicalize** |

### 5.2 Three Identity Domains

```
record sameness
≠
observation sameness
≠
semantic-object sameness
```

**Observation Occurrence 定义**：

> **Observation occurrence**：在某个明确 observation context / observation point 中，对一个 traffic / protocol phenomenon 形成的一次 provenance-bearing observation。多个 Observation Occurrences 可以指向同一个 semantic object。**Observation occurrence 不是 semantic object 本身。**
>
> 这不是新增 Schema 类型，只是 §5 semantic contract 中的概念。

| 域 | 回答的问题 | 对象 |
|---|---|---|
| **Raw Record Identity** | 两份底层输入记录是否其实是同一份 observation materialization？ | 输入记录 |
| **Observation Identity** | 多个真实 observation occurrences 之间是什么关系？ | Packet / Message 等 observation occurrence |
| **Semantic Object Identity** | 多个 observations 是否指向同一个 protocol / transport semantic object？ | Message / Transaction / Protocol Session / Transport Connection |

### 5.3 A. Raw Record Duplication

**回答**：两份底层输入记录是否其实是同一份 observation materialization？

**例子**：同一个 pcap 文件被 pipeline 导入两次；同一 frame record 在 ingestion 中重复出现；同一原始 capture artifact 被复制两份进入 pipeline。

**处理目标**：去掉重复 representation / record；仍保留必要 provenance，记录其来自哪些 input references。

**护栏**：

> **Byte equality 不足以证明 raw-record duplication。** Raw Record duplication 必须由 **Frozen Raw Record Identity Rule** 确定为「同一 observation materialization 的重复 representation」。**Content / byte equality 只能是候选信号，不得单独证明 duplicate identity。**

### 5.4 Observation Formation

**Observation Formation 本身不承担 observation collapse。**

在进入 Observation Formation **之前**，Raw Record Layer 可以已经完成该层合法的 deterministic dedup（见 §5.10 处理顺序）。

Observation Formation 完成后，**只有在 Observation Identity Layer 能够证明 duplicate observation materialization 时**，才允许执行该层 dedup。

**Semantic-object co-reference 不是 observation dedup。**

### 5.5 B. Observation Multiplicity / Correspondence

**回答**：多个真实 observation occurrences 之间是什么关系？

**核心命题**：**多个 observation occurrences 不得因指向同一 semantic object 而被删除。**

**例子 1**：TCP original transmission + TCP retransmission → 是**两个 Packet observations**，不得 Packet-dedup，两者可能 `contributes_to` 同一个 Message。

**例子 2**：sender-side Capture A + receiver-side Capture B → **多个 observation occurrences**，provenance 必须完整保留这些 observations，provenance 可以 materialize 为**一个或多个 Evidence records**，具体 Evidence representation **不由 observation count 一对一决定**。

**术语冻结**：

- Observation layer: **correspondence**
- Semantic-object layer: **co-reference**

### 5.6 C. Semantic Object Identity / Co-reference

**回答**：多个 observations 是否指向同一个 protocol / transport semantic object？

**例子 1**：Capture A 观察 Message M / Capture B 观察 Message M → 2+ observation occurrences，完整 observation provenance，**1 Message semantic object**。Evidence record 数量由 §9 Hub Boundary 的 materialization contract 决定，**不得由 observation 数量直接推导**。

**例子 2**：application layer 真正发送两个内容完全相同的 SETUP → **2 Message semantic objects**。

**禁止**：content equality → Message dedup。

**Co-reference 的判定门槛**：只有 semantic sameness **能够被后续 deterministic rules 充分确认**时，才可 co-refer。不能确认时：`identity = unknown`，**不得自动 merge**。

### 5.7 Cross-capture Observation Semantics

**direct / derived 与 semantic-object co-reference 正交。**

direct / derived 描述 observation 如何获得（Packet 通常是 direct；Message / Transaction / Connection / Protocol Session 通常由 reconstruction 派生）。**它不决定 semantic-object co-reference 是否允许发生。**

因此 **cross-capture co-reference 既可能发生在 direct-observed Packet objects，也可能发生在 derived higher-level objects**。是否 co-refer，只由对应 semantic identity contract 与 deterministic reconstruction rules 决定。

**例子**：Capture A 观察 Packet P / Capture B 也观察同一个 Packet P → 在满足 deterministic sameness rule 的情况下，两个 capture observations 完全可能 co-refer **同一个 Packet semantic object**。

**同一次 logical transmission 被多个 capture point 观察时**：semantic object identity 保持唯一；observation multiplicity 保持真实；**不得因「看起来是同一个」而删 observation，也不得因多个 observation 而分裂成多个 semantic object。**

### 5.8 Provenance Preservation

**原则**：任何层的合并 / co-reference **不得删除 provenance**。

- Raw record dedup 时保留 input reference。
- Observation co-reference 时保留全部 observation 与 Evidence locator。
- Semantic object 合并时保留全部原始 observation 与 Evidence references。

**Observation multiplicity 不得隐式决定 Evidence record multiplicity。** 多个 observations 必须完整保留 provenance，但它们可以根据 §9 Hub Boundary materialize 为一个或多个 Evidence records。**不得假设 1 observation = 1 Evidence record。**

**Evidence preservation 与 independent support accounting 是两个独立问题**（§2.3）。

### 5.9 Partial / Unknown Identity Handling

延续 §4.8：

> Partial observation 不得放宽 semantic identity criteria。
>
> 当可用信息不足以确定两个 partial observations 是否属于同一 semantic object 时：**identity relation = unknown，不得自动 merge。**

| 情形 | 处置 |
|---|---|
| 两个 raw records 是否 duplicate 无法确定 | 保留两份，标记 raw duplication = unknown |
| 两个 packet observations 是否属于同一传输 occurrence 无法确定 | 保留两份，标记 co-reference = unknown |
| 两个 message observations 是否同一 semantic object 无法确定 | 保留两份，标记 semantic identity = unknown |
| partial observation 的 semantic sameness 无法判定 | 不 merge |

**核心**：不确定是不是同一个，不等于同一个。

### 5.10 Processing Order

```
Raw traffic records
  ↓
Raw-record identity evaluation
  ↓
Raw-record layer deduplication
  （仅 collapse 已证明的 duplicate representations）
  ↓
Observation formation
  ↓
Observation identity / correspondence evaluation
  ↓
Observation-layer deduplication
  （仅 duplicate observation materialization）
  ↓
Semantic-object reconstruction / co-reference
  （不删除 observations / provenance）
  ↓
Property-specific measurement formation (§6)
  ↓
Property-specific eligibility filtering (§6)
  ↓
Dependency clustering (§7)
  ↓
Independence assessment (§7)
  ↓
Statistical aggregation
  ↓
Traffic Claim formation (§8)
```

**关键约束**：Dependency clustering 与 independence assessment **不在本层**。co-reference ≠ dependence。semantic co-reference ≠ statistical dependence。

### 5.11 §5 Invariants

1. **Dedup is layer-local.** 只在能证明重复的层 collapse。
2. **Record sameness ≠ observation sameness ≠ semantic-object sameness。**
3. **Distinct observation occurrences 不得仅因指向同一 semantic object 而删除。**
4. **Semantic-object merge does not erase observation provenance.**
5. **Semantic-object merge does not imply Evidence merge/delete.**
6. **TCP retransmission → 新 Packet observation，不是 duplicate Packet。**
7. **Content equality ≠ Message identity.** 两个内容完全相同的 SETUP 发送 → 两个 Message。
8. **Cross-capture co-reference 不改变 semantic object identity，也不减少 observation multiplicity。**
9. **partial observation 的 identity 不确定时 = unknown，不得自动 merge。**
10. **co-reference ≠ dependence.** 本层不涉及 independence counting。
11. **Evidence record count ≠ observation count**（延续 §3.1.2）。
12. **Observation multiplicity 不得隐式决定 Evidence record multiplicity。** 多个 observations 必须完整保留 provenance，但它们可以根据 §9 Hub Boundary materialize 为一个或多个 Evidence records。不得假设 1 observation = 1 Evidence record。

### 5.12 §5 开篇测试向量

#### Case A — duplicate ingestion

```
同一个 pcap 被 pipeline 导入两次
```

判定：**raw record duplication**，不是两个独立 observations。

#### Case B — TCP retransmission

```
Packet P1
TCP retransmitted as P2
```

判定：`P1 ≠ P2`：两个 distinct Packet observations；可能 `P1 → Message M` 且 `P2 → Message M`；**绝不能**因 payload 相同而 `P2 dedup/delete`。

#### Case C — two capture points

```
Capture A sees transmission T
Capture B sees transmission T
```

判定：multiple observations / multiple Evidence references；one Message semantic object；**前提**：semantic sameness 可被 deterministic rules 充分确认。不能确认 → `identity = unknown`，不得自动 merge。

#### Case D — identical application sends

```
Client sends SETUP X
Client later sends identical SETUP X again
```

判定：`Message M1 ≠ Message M2`，即使 bytes identical。**禁止 content-dedup**。

#### Case E — identical bytes, distinct packet occurrences

```
同一个 Capture 中：
  Frame 101: bytes = X
  Frame 205: bytes = X
```

假设它们确实是**两个不同 network transmission occurrences**，则：`Packet P1 ≠ Packet P2`，即使 packet bytes identical。判定：**NOT raw-record duplication**，**NOT Packet dedup**。除非 Frozen Raw Record Identity Rule 另有确定性证据证明它们其实是同一次 materialization 被 ingestion 重复表示。

**与 Case D 上下对称**：**content equality 既不能决定 Packet identity，也不能决定 Message identity。**

### 5.13 Open Questions Carried Forward

| # | 问题 | 目标 |
|---|---|---|
| G | Message reconstruction 具体算法 | Metadata Recon |
| H | request-response pairing rule | Metadata Recon |
| I | **Cross-capture semantic-object co-reference / canonicalization rules** | Metadata Recon |
| L | multi-capture observation 与 Evidence preservation 的精确规则 | §9 Hub Boundary |
| M | **Raw Record duplicate proof** 依赖哪些 observable fields？ | Metadata Recon |
| N | **Observation occurrence duplicate / correspondence proof** 依赖哪些 observable fields？ | Metadata Recon |
| O | **Semantic-object co-reference 的 deterministic proof rules** 是什么？ | Metadata Recon |
## 6. Property Measurement Contract

### 6.x Contract / Binding / Validation Status Semantics

本节为 §6 全部 property 的标准状态模型。D9 §6 区分三个独立状态：

| 状态 | 含义 |
|---|---|
| **Semantic Contract Status** | 定义 property 在协议知识层「表示什么、怎么算」 |
| **Machine Binding Status** | 定义该 semantic contract 与 Registry key / producer / derived aggregation 的绑定关系 |
| **Empirical Validation Status** | 定义当前真实 traffic corpus 是否已经产生过足以验证该 contract 的数据 |

**三层状态独立**：Semantic Contract = Frozen Candidate **不自动**意味着：

- Registry key 已确定；
- producer 已实现；
- derived aggregation 已实现；
- 当前 corpus 已有 materialized data；
- semantic contract 已通过真实数据验证。

**Binding Relation 模型**（每个 semantic contract 与每个候选 machine key 之间）：

| Relation | 含义 |
|---|---|
| `DIRECT_BINDING` | semantic contract 与 machine key 一对一直接对应 |
| `DERIVED_FROM` | semantic contract 由 machine key 经明确 aggregation / derivation 派生 |
| `DESIGN_ONLY` | Registry 定义存在但无 producer / data / consumer，仅作未来 contract placeholder |
| `LEGACY_ALIAS` | 当前运行使用另一个 canonical key，该 property 仅是旧名 / 兼容项 |
| `UNBOUND` | semantic contract 无任何 machine binding |
| `AMBIGUOUS` | 当前证据不足以判定以上类别 |

**Machine Binding Status**：

| Status | 含义 |
|---|---|
| `BOUND_AND_IMPLEMENTED` | binding 已确定且有 producer + data |
| `BOUND_AND_UNIMPLEMENTED` | binding 已确定但无 producer / data |
| `PENDING` | binding 待 recon |
| `UNBOUND` | 无 machine binding |
| `AMBIGUOUS` | 证据不足 |

**Empirical Validation Status**：

| Status | 含义 |
|---|---|
| `VALIDATED` | 当前 corpus 已产生足以验证该 contract 的数据 |
| `NOT_YET_ESTABLISHED` | 尚无验证数据 |
| `PARTIAL` | 部分情形已验证 |

---

### 6.1 Common Measurement Contract

本节定义每个 traffic property 必须回答的 semantic contract fields。**注意：这些是 semantic contract fields，不是现在要求新增 Schema 字段。**

#### A. Semantic Question

**每个 property 必须先用一句自然语言回答：它到底在测什么？**

此问题决定后续所有字段的方向。**未回答语义问题的 property 不得进入 measurement contract。**

#### B. Measurement Unit

**必须引用 §4 taxonomy 中已经冻结的 semantic unit。**

允许引用：Message / Transaction / Protocol Session / Packet / Transport Connection。

**禁止重新发明**：`sample` / `event` / `record` 等未定义单位。

**Contract 表述**：

> 每一个 **concrete Property Measurement Contract** 必须显式声明**一个 primary measurement unit**。
>
> 同一个 concrete contract 不得同时混用多个 measurement units。
>
> 若未来同一 property 确实需要不同 measurement units，**必须定义为不同的、可区分的 measurement contract variants**，不得在同一 contract 中隐式切换。

#### C1. Semantic Applicability Scope

**回答**：这条统计性协议事实本身是在什么协议语义条件下成立？

例：request direction / method = SETUP / state = Ready / header X exists。

**Contract**：

> 定义 measurement 所描述的**协议语义适用域**。
>
> 如果 scope 差异改变了「该 traffic Claim 在讨论哪个协议事实」，则该差异**必须在后续 Candidateization / fact identity mapping 中被显式表达**。
>
> **不得仅作为 observation provenance 丢失。**

**边界**：本节只冻结语义边界。C1 最终如何映射 fact_key.condition / actor / subject，留给后续 Candidateization / Schema Gap Review。**当前不修改 fact_key schema。**

**Target-outcome Leakage Guard**：

> Semantic Applicability Scope **不得隐式使用当前 measurement 的 target outcome 筛选 population**，否则会产生 **tautological / selection-biased measurement**。
>
> 只有当该条件本身属于一个**明确不同的 conditional semantic question** 时才允许使用，且该 conditional scope 必须被**显式表达**。

**无隐式 direction 默认值**：每个 concrete contract 必须显式声明 direction applicability（request / response / both）。`direction = unknown / unspecified` 不得生成最终 Claim。

#### C2. Observation Population Scope

**回答**：这条 observation 是从哪一批观测 population 得到的？

例：本次 3000 captures / 某个 collection run / 某个设备环境 / 某个 observation snapshot / 某个 capture subset。

**Contract**：

> 定义本次统计来自哪个**实际观测 population / collection snapshot**。
>
> 它表达 **observation provenance**，**不表达协议事实 identity**。
>
> `capture_id` / `collection_run_id` / `concrete_protocol_session_instance_id` / 具体设备 / 文件 / 抓包批次**不得进入 canonical fact_key**。

**注意**：本处禁止进入 fact identity 的是 **runtime observation instance identifier**。这不意味着协议中的 canonical session-related subject / condition 永远不能参与 fact identity。

#### D. Eligibility Semantics

**Eligibility Status 为三态**：

| Status | 含义 |
|---|---|
| `eligible` | 属于本次统计的 population |
| `not_eligible` | 不属于本次统计的 population |
| `unknown` | 连是否属于 population 都无法确定 |

**禁止**：`eligibility = unknown` → 自动转 `not_eligible`。

**Eligibility 与 Outcome 必须分离**：`not eligible` ≠ `eligible + negative outcome`。

#### E. Measurement Outcome

**对每一个 eligible unit，到底观察出什么。**

Outcome **可以不是数字**。可能类型：bool / category / position / relation / set。

**Outcome Status 为二态**：`known` / `unknown`。

**二维语义矩阵**：

| Eligibility | Outcome | 含义 |
|---|---|---|
| `eligible` | `known` | 正常 measurement |
| `eligible` | `unknown` | 属于 population，但 outcome 无法可靠观察 |
| `not_eligible` | N/A | 不属于本 measurement population |
| `unknown` | N/A | 连是否属于 population 都无法确定 |

**禁止**：`eligibility = unknown` → `not_eligible`；`eligible + outcome = unknown` → `outcome = false`。

#### F. Aggregation Semantics

**如何把 N 个 eligible unit 的 outcome 聚合成 property 层面的统计结果。**

常见形态：rate / proportion / distribution / co-occurrence matrix / position distribution / relation distribution。

**只有 aggregation semantics = rate / proportion 时，才要求显式定义 numerator + denominator。** 其余形态不强制。

#### G. Unknown / Incomplete Semantics

**Partial / incomplete observation 可能影响两个独立判断**：eligibility 是否可确定；eligible 后 outcome 是否可确定。**二者必须分别表达。**

- `eligibility = unknown` 不得自动转换为 `not_eligible`
- `outcome = unknown` 不得自动转换为 `false` / `absent` / `zero`

**对于 rate / proportion，D9 默认**：

> 只有 `eligibility = eligible` **且** `outcome = known` 的 units 进入 **point-estimate denominator**。
>
> `eligible + outcome = unknown` 以及 `eligibility = unknown` 必须**单独计数**，不得静默进入 numerator / denominator。

**新增两个 semantic quantities（非 Schema 字段）**：`unknown_eligibility_count` / `unknown_outcome_count`。

#### H. Insufficient Observation Semantics

**只冻结一个 canonical semantic status**：

```
measurement_status = insufficient_observation
```

**含义**：当前 observation population 没有足够 eligible known measurements 形成该 property 的统计 conclusion。此时 `aggregate value = undefined`。

**区分**：`insufficient_observation` = semantic status；`undefined` = aggregate value 没有定义。

**通用条件**：

> **如果没有任何可用于该 property aggregation semantics 的 known eligible outcomes，则结果为 `insufficient_observation`，不得伪造零值统计。**

**覆盖**：`eligible_measurement_count = 0`；`eligible_measurement_count > 0` 但全部 `outcome = unknown`。

**对 rate / proportion**：`effective_denominator = 0 → measurement_status = insufficient_observation`。

**禁止**：`observed_rate = 0`。

#### I. Handoff to Aggregation / Claim Formation

**§6 负责形成**：eligible measurement population；known / unknown measurement outcomes；property-specific aggregation semantics。

**§7 在此基础上形成**：dependency clusters；independence classification；support summary。

**随后 statistical aggregation** 按照 property contract 生成 observed aggregate，**同时携带 §7 的 independence support summary**。

**§7 不得覆盖 §6 已定义的 measurement semantics。**

**§6 不做**：independent_support weighting、Phase A reasoning、Traffic Claim formation（属 §8）。

#### 6.1.x Eligible Population vs Effective Aggregation Set

> `eligibility = eligible` 表示该 measurement unit **属于该 property 的 semantic measurement population**。
>
> 这**不等于**该 unit 一定能够进入当前 aggregate 的**有效计算集合**。
>
> 例如：`eligible + outcome = unknown` 仍然属于 eligible population，但在 D9 的 rate / proportion point estimate 中**不得进入 effective denominator**。

#### 6.1.y Measurement Aggregate vs Independence Support Summary

| 概念 | 例 | 描述 |
|---|---|---|
| **Measurement Aggregate** | `820 / 1000 eligible known Messages → observed_rate = 0.82` | 当前 observation population 中观察到什么 |
| **Independence Support Summary** | `37 support units / 20 independent / 10 dependent / 7 unknown` | 这条 observational assertion 背后的 independence structure |

**二者不能混。**

---

### 6.2 Common Measurement Invariants（14 条）

1. **Measurement unit 必须是 §4 taxonomy 中已有的 semantic unit**，或未来通过正式 taxonomy extension 增加。
2. **Eligibility 与 outcome 必须分离。** `not eligible` ≠ `eligible + negative outcome`。
3. **Partial / unknown observation 不得默认转换成 false / absent / zero。**
4. **只有 `eligibility = eligible` 的 units 才属于该 property 的 eligible measurement population。** 某 eligible unit 是否进一步进入 **effective aggregation set**，由其 outcome status 与 property aggregation semantics 决定。
5. **Rate / proportion 类 property 必须显式定义 numerator 和 denominator semantics。**
6. **若某 property 没有任何可用于其 aggregation semantics 的 known eligible outcomes：**
   ```
   measurement_status = insufficient_observation
   aggregate value = undefined
   ```
   不得以 `0` / `false` / `empty distribution` / `empty relation set` 等值伪造一个有效统计 conclusion。
7. **Measurement semantics 不得直接使用 raw observation count 作为 confidence / independence。**
8. **Measurement formation 发生在 semantic-object reconstruction 之后、dependency clustering 之前。**
9. **一个 property 的 measurement contract 不得通过 `capture_id` / `concrete_protocol_session_instance_id` / `cluster_id` / `scenario_id` / `collection_run_id` 修改 canonical fact identity。**
10. **§6 不引入 weighted Claim，不修改 Phase A / Phase B。**
11. **Semantic Applicability Scope 与 Observation Population Scope 必须区分。** 前者如果改变协议事实语义，必须在后续 fact identity mapping 中被显式表达；后者属于 observation provenance，不得因采集实例不同拆分 canonical Fact。
12. **Eligibility unknown 与 Outcome unknown 必须区分。** 二者均不得隐式转换为 not eligible / false / absent / zero。
13. **Measurement Aggregate 与 Independence Support Summary 是两个不同 semantic dimensions。** §7 不得静默重定义 §6 property aggregation semantics。
14. **Measurement population 不得由当前 target outcome 隐式定义。** Outcome-dependent population filtering 必须属于**显式 conditional measurement semantics**，否则视为 **measurement contract 错误**，不得生成 Traffic Claim。

#### 6.2.x §6 / §7 Boundary Reminder

**不要把 `eligible_measurement_count` 和 `support_unit_count` 混起来。**

```
1000 eligible Messages
  ↓ dependency clustering
37 support units
  ├── 20 independent
  ├── 10 dependent
  └── 7 unknown
```

`eligible_measurement_count ≠ support_unit_count`（§3.2 Semantic Non-Equivalence）。

**§7 不得静默重定义 §6 的 measurement numerator / denominator / outcome distribution**。若未来需要 independence-adjusted rate / weighted prevalence，必须定义新的显式 measurement semantics，**不得覆盖 raw observed aggregate**。

---

### 6.3 occurrence_frequency

**Semantic Contract Status**: FINAL FROZEN
**Machine Binding Status**: PENDING（可能 LEGACY_ALIAS → observed_occurrence_rate，待 §6-Pre3 最终判定）
**Empirical Validation Status**: NOT_YET_ESTABLISHED

#### A. Semantic Question

> `occurrence_frequency` 回答：**在明确 Semantic Applicability Scope 下，target subject 在 eligible Message semantic objects 中出现至少一次的比例是多少？**

**定义冻结**：`occurrence_frequency = Message-level presence rate`。

**不是**：within-Message multiplicity。二者回答不同协议问题。

**Target subject** 属于正在测量的协议对象，不是 Observation Population Scope。

#### B. Measurement Unit

**Primary measurement unit：Message。**

计数对象是经过 §5 semantic-object reconstruction / co-reference 后的 **Message semantic object**，**不是 raw Message observation occurrence**。

**当前适用域**：D9 的 `occurrence_frequency` **只覆盖 Registry 已授权的 Header subject**。若未来扩展到其他 subject / kind，**必须建立新的 concrete measurement contract variant**。

#### C1. Semantic Applicability Scope

**本节只放**：`direction`（request / response / both）/ `method` / `state` / 其他**真正的 semantic applicability condition**。

**Target subject 不在此处**。

**Scope 差异必须在 fact identity 中显式表达**：`header.Session × direction=request × method=SETUP` 与 `header.Session × direction=request × method=PLAY` 是**两个不同 semantic applicability domains**。

**Target-outcome Leakage Guard**：不得把 `header.Session exists` 作为默认 applicability / eligibility condition。

**无隐式 direction 默认值**。

#### C2. Observation Population Scope

与 §6.1-C2 一致。

**防 cross-capture double counting**：多个 Observation Population records 若 co-refer 到同一 Message semantic object，在同一个 concrete aggregate scope 内**只形成一个 Message measurement unit**。

#### D. Eligibility Semantics

**一个 Message 的 eligibility 只由两个条件决定**：是否属于 C2 Observation Population；是否能可靠判断并满足 C1 Semantic Applicability Scope。

**三态**：`eligible` / `not_eligible` / `unknown`。

**关键修正**：**Message completeness 本身不决定 eligibility。**

**示例**：partial SETUP request，若仍能可靠确认 `direction=request` + `method=SETUP` → `eligibility = eligible`，即使无法判断 Session 是否出现 → `eligible + outcome=unknown`，**不是 not_eligible**。

#### E. Measurement Outcome

**Outcome 类型：bool。**

| Outcome | 含义 |
|---|---|
| `true` | target subject 在该 logical Message 中**至少出现一次** |
| `false` | 已可靠确定 target subject 在该 logical Message 中**未出现** |

**出现 1 次 / 2 次 / 10 次，对 `occurrence_frequency` 都是 `true`。每个 Message 对 numerator 最多贡献 1。**

**Outcome Status 二态**：`known` / `unknown`。

**Outcome known / unknown 必须 target-sensitive**：只有当 observation incompleteness **影响 target presence 的可靠判定**时，才 `outcome = unknown`。

**跨 observation 内容冲突**：`materially conflicting observations → outcome = unknown`，同时保留 conflict provenance。

#### F. Aggregation Semantics

**形态：rate / proportion。**

```
numerator   = count of eligible Message semantic objects
              with outcome = known + true

denominator = count of eligible Message semantic objects
              with outcome = known

observed_rate = numerator / denominator
```

**约束**：`0 <= numerator <= denominator`；当 `denominator > 0` 时 `0 <= observed_rate <= 1`；**每个 eligible Message semantic object 对 denominator 最多贡献 1，对 numerator 最多贡献 1**。

**Denominator 定义**：所有满足该 concrete contract C1、`eligibility = eligible` 且 `outcome = known` 的 Message semantic objects。

**示例**：

```
eligible_measurement_count = 1000
  ├── outcome = known: 950
  │     ├── true: 820
  │     └── false: 130
  └── outcome = unknown: 50

numerator = 820
denominator = 950
observed_rate = 820 / 950 ≈ 0.8632

同时保留：eligible_measurement_count = 1000；unknown_outcome_count = 50
```

#### G. Unknown / Incomplete Semantics

**四类（target-sensitive）**：

| 情形 | 结果 |
|---|---|
| C1 可判 + 满足 C1 + target 可判 present | `eligible / known / true` |
| C1 可判 + 满足 C1 + target 可判 absent | `eligible / known / false` |
| C1 可判 + 满足 C1 + target 不可靠判定 | `eligible / unknown` |
| C1 本身不可靠判定 或 无法判断是否属于 C2 aggregate population | `eligibility = unknown` |

**D9 默认**：只有 `eligible + known` 进入 numerator / denominator。

**必须同时保留**：`unknown_eligibility_count` / `unknown_outcome_count`。

#### H. Insufficient Observation Semantics

```
denominator = 0
→ measurement_status = insufficient_observation
→ aggregate value = undefined
```

**覆盖**：`eligible_measurement_count = 0`；`eligible_measurement_count > 0` 但全部 `outcome = unknown`。

**禁止**：`observed_rate = 0`。

#### I. Handoff

**§6.3 负责定义并形成**：Message measurement units；eligibility classification；known / unknown presence outcomes；occurrence_frequency aggregation formula；numerator / denominator membership rules；insufficient-observation rule。

**§7 接收这些 measurement outcomes，形成**：dependency clusters；independence classifications；support summary。

**随后 Statistical Aggregation Stage** 按 §6.3 已冻结的公式 **materialize**：numerator / denominator / observed_rate，同时携带 §7 的 Independence Support Summary。

**§7 不得修改** numerator / denominator 成员资格与 observed_rate 公式。

#### §6.3 Property-specific Invariants（9 条）

1. `occurrence_frequency` 表示 **Message-level presence rate**。
2. **Primary measurement unit = Message semantic object**。
3. 一个 Message 对 denominator **最多贡献 1**。
4. 一个 Message 对 numerator **最多贡献 1**。
5. subject 出现 ≥ 1 次 → `outcome = true`；具体 occurrence multiplicity **不改变本 property outcome**。
6. 多个 observations / captures co-refer 同一 Message **不得重复增加 numerator / denominator**。
7. `outcome = false` 必须基于**足够完整的信息可靠证明 target absent**；partial **不得默认 false**。
8. `observed_rate` **不得被 §7 independence summary 重新定义或重加权**。
9. 每个 concrete contract 必须**显式声明 direction applicability**；`direction = unknown / unspecified` 不得生成最终 Claim。

#### Deferred Candidate: occurrence_multiplicity

现在不新增第五个 traffic property。若未来证明 within-Message multiplicity 是目标信息，**另立独立 property**（不是 `occurrence_frequency` variant）。

---

### 6.4 co_occurrence

**Semantic Contract Status**: FINAL FROZEN
**Machine Binding Status**: PENDING（可能 LEGACY_ALIAS → observed_co_occurrence，待 §6-Pre3 最终判定）
**Empirical Validation Status**: NOT_YET_ESTABLISHED

#### A. Semantic Question

> `co_occurrence` 回答：**在明确 Semantic Applicability Scope 下，两个不同的 canonical Header subjects 在同一 eligible Message semantic object 内均至少出现一次的 observed joint-presence rate 是多少？**

**定义冻结**：`co_occurrence = Message-level symmetric joint presence rate`。

**措辞冻结**：以「**同一 Message 内均出现**」代替「同时出现」，明确 **same measurement unit**，不是 **same timestamp**。

**对称性冻结**：`co_occurrence(A, B) ≡ co_occurrence(B, A)`。

**不是**：joint distribution（00/01/10/11）——属 Deferred Candidate。

#### B. Measurement Unit

**Primary measurement unit：Message**（同 §6.3）。

**当前适用域**：与 §6.3 一致，**只覆盖 Registry 已授权的 Header subjects**。

#### C1. Semantic Applicability Scope

与 §6.1-C1 一致。**Target subjects 不在此处**。

**Target-outcome Leakage Guard**：禁止把 `A exists OR B exists` 或 `A exists AND B exists` 作为默认 applicability / eligibility condition。

**无隐式 direction 默认值**。

#### C2. Observation Population Scope

与 §6.3 一致。

#### D. Eligibility Semantics

与 §6.3 一致。三态：`eligible` / `not_eligible` / `unknown`。

#### E. Measurement Outcome

**Operand presence states（semantic intermediate，非 Schema 字段）**：

```
A_presence = present | absent | unknown
B_presence = present | absent | unknown
```

**Final measurement outcome type：`bool` + `outcome status`。**

**三值 AND 规则（AND3）**：

| A | B | joint outcome |
|---|---|---|
| present | present | `known / true` |
| absent | present | `known / false` |
| present | absent | `known / false` |
| absent | absent | `known / false` |
| absent | unknown | `known / false` |
| unknown | absent | `known / false` |
| present | unknown | `unknown` |
| unknown | present | `unknown` |
| unknown | unknown | `unknown` |

**Operand-level conflict 处理**：

```
A presence observations conflict → A_presence = unknown
B presence observations conflict → B_presence = unknown
然后重新计算 AND3
```

**禁止**：直接因任何 operand conflict 就把整个 co_occurrence outcome 无条件置 unknown。

**不区分 outcome=false 的 00 / 01 / 10 构成**（joint distribution 属 Deferred Candidate）。

#### F. Aggregation Semantics

**形态：rate / proportion。**

```
numerator   = count of eligible Message semantic objects
              with joint outcome = known + true

denominator = count of eligible Message semantic objects
              with joint outcome = known
```

**Denominator 定义**：所有满足该 concrete contract C1、`eligibility = eligible` 且 `joint outcome = known` 的 Message semantic objects。

**明确禁止**：`A exists OR B exists` 作为 denominator population filter；`A exists AND B exists` 作为 eligibility。

#### G. Unknown / Incomplete Semantics

对每个 eligible Message，**先分别确定 A_presence / B_presence**，**然后应用 AND3**。

**target-sensitive 规则**：只有当 observation incompleteness **影响该 operand presence 的可靠判定**时，该 operand 才 = unknown。

**D9 默认**：只有 `joint outcome = known` 进入 numerator / denominator。

**必须同时保留**：`unknown_eligibility_count` / `unknown_outcome_count`。

#### H. Insufficient Observation Semantics

与 §6.3 一致。

#### I. Handoff

与 §6.3 一致。

#### §6.4 Canonical Target Pair

**Canonicalization 顺序（冻结）**：

```
raw target
  ↓
subject alias / canonical normalization
  ↓
得到 canonical subject IDs
  ↓
检查 A != B
  ↓
对两个 canonical IDs 执行 deterministic ordering
  ↓
canonical unordered pair
```

**禁止**：先对 raw spelling 排序，再做 alias normalization。

**Pair identity 属于 fact semantic identity**：

> Canonical target pair 必须基于 canonical subject IDs 形成 **unordered deterministic pair**。Pair identity **属于 fact semantic identity**，**不得仅存在于 assertion / Evidence / provenance 中**。

**禁止 self-pair**：`A != B`。`co_occurrence(A, A)` → INVALID measurement contract。

#### §6.4 Property-specific Invariants（14 条）

1. `co_occurrence` 表示 **Message-level symmetric joint presence rate**。
2. **Primary measurement unit = Message semantic object**。
3. 一个 Message 对 denominator **最多贡献 1**。
4. 一个 Message 对 numerator **最多贡献 1**。
5. A、B 均 present → `outcome = true`；具体 multiplicity **不改变本 property outcome**。
6. 多个 observations / captures co-refer 同一 Message **不得重复增加 numerator / denominator**。
7. `outcome = false` 必须有足够证据可靠证明：`A_presence = absent` **OR** `B_presence = absent`。**不要求 A、B 两侧信息都完整。** partial observation 不得在没有可靠 absent operand 时默认产生 false。
8. `observed_rate` **不得被 §7 independence summary 重新定义或重加权**。
9. 每个 concrete contract 必须**显式声明 direction applicability**；`direction = unknown / unspecified` 不得生成最终 Claim。
10. **`co_occurrence(A, B) ≡ co_occurrence(B, A)`**，canonical pair identity 有序化。
11. **Denominator 不得使用 outcome-dependent filtering**。
12. **不区分 outcome=false 的 00 / 01 / 10 构成**；joint distribution 属 Deferred Candidate。
13. **Canonical target pair 必须基于 canonical subject IDs 形成 unordered deterministic pair。** Pair identity **属于 fact semantic identity**，不得仅存在于 assertion / Evidence / provenance 中。
14. **A 与 B canonicalize 后必须不同。** 若 `A == B`：该 measurement contract invalid，不得生成 co_occurrence Traffic Claim。

#### Deferred Candidate: joint_distribution

现在不新增第五个 traffic property。若未来证明 00 / 01 / 10 / 11 四分类是目标信息，**另立独立 property**（不是 `co_occurrence` variant）。

#### D9-GAP-PAIR-IDENTITY（Deferred Schema / Candidateization Gap）

**问题**：现有 canonical fact_key 如何承载 symmetric binary target pair？

**Frozen semantic requirement**：Pair identity **必须进入 fact semantic identity**。**禁止**只把第二 target 存在 assertion / Evidence / provenance。

**处理阶段**：§9 Hub Boundary + Candidateization / Schema Gap Review。

**当前**：NON-BLOCKING for §6 semantic contract。

---

### 6.5 observed_packet_position（BLOCKED）

**Status**: BLOCKED FOR SEMANTIC CONTRACT DRAFTING

**Reason**: canonical property binding / implementation status / authoritative intended semantics pending D9 property inventory。

**Semantic Contract Status**: NOT YET DRAFTED
**Machine Binding Status**: PENDING
**Empirical Validation Status**: NOT_YET_ESTABLISHED

**已确认事实**（§6.5-Pre）：
- canonical property 名是 `observed_packet_position`（非 `packet_position`）
- 该 property 当前 0 direct producer / 0 data
- semantic judgment = AMBIGUOUS（乙 Transport Packet placement 最贴近字面证据；甲与字面冲突；丙非专属性）
- property vs condition = B（相关但不同层语义）
- 歧义来源：provenance gap（主因）+ registry ambiguity（次因）

**前置条件**（解除 BLOCKED 需）：
1. §6-Pre3 binding recon 完成
2. property status decision（REGISTERED_UNIMPLEMENTED / REGISTERED_DESIGN_ONLY / ORPHANED / 其他）
3. M3 authoritative semantic provenance（若保留该 property）

### 6.6 observed_temporal_relation（FINAL FROZEN）

**Status**: FINAL FROZEN

**Semantic Contract Status**: FINAL FROZEN
**Machine Binding Status**: PENDING
**Empirical Validation Status**: NOT_YET_ESTABLISHED

**说明（历史）**：本节原 PAUSED，理由为「与 §6.5 同步暂停，避免 §6.5 停而
绕过去继续冻结 §6.6」。该 PAUSED 系**自同步决定，非技术依赖**，
已于 §6-Pre10 解除（见 §14 E9）。

#### §6.6-A Semantic Question

`observed_temporal_relation` 回答：

> 在明确 Semantic Applicability Scope 下，
> **两个 Packet semantic objects 之间的 temporal relation**
> 在 **eligible observation pairs** 中的分布（或 rate）。

temporal_relation 的**值**是**离散关系**
（before / after / during / overlap / 等）。

**packet timestamp 只是推导手段，不进 fact_key。**

**关键约束（显式冻结）**：

- `capture` 仅为 **observation context**，**不进 fact_key**
- temporal_relation 的**两端主体是 Packet semantic objects**（§4 taxonomy 定义）
- 本裁定为「丙-2」版本：capture 不进 identity
- **「Capture 内 Packet 序号」不等同于 capture 身份**
- `packet timestamp` **不进 fact_key**（仅为推导手段）
- `capture_id` **不进** fact_key

注意：Packet 是 **instance-level object**，不是 named entity。
fact_key 里如何表达「某两 Packet 的关系」留 §6.6-C1 澄清。

#### §6.6-B Measurement Unit

**Primary measurement unit：Packet。**

与 §6.3 / §6.4 一致：计数对象是经 §5 semantic-object reconstruction /
co-reference 后的 **Packet semantic object**，**不是** raw Packet observation。

#### §6.6-C1 Semantic Applicability Scope

回答：这条统计性协议事实本身是在什么协议语义条件下成立？

本节只放 direction / method / state / 其他真正的 semantic
applicability condition。**Target pair 不在此处。**

**两端主体裁定**：限定为 **Packet role classes**。

Packet role class 的定义由 **deterministic normalizer** 判定。

具体 role class 枚举（request / response / data / 其他）
留 **§6.6-C1.x** 或 Metadata Recon。

`capture` 不进 fact_key；**具体 Packet instance 不进 fact_key**。

**fact_key 表达形态**（命名待 §9 Hub Boundary / Schema Gap Review）：

```
kind      = packet_role_pair
subject   = <packet_role_class_A> × <packet_role_class_B>
property  = temporal_relation
condition = <semantic applicability scope>
```

⚠ **本形态的已知落差**：`packet_role_pair` **不在当前 `fact_key.kind`
枚举内**（实测枚举 = method / header / constraint / state / transition）。
该形态在 §9 Hub Boundary 或 Schema Gap Review 落定前**不具可实施性**；
本节只冻结「两端主体为 Packet role classes」这一语义裁定。

#### §6.6-C1.x Packet Role Class 枚举（待 Metadata Recon）

§6.6-C1 已裁定两端主体为 **Packet role classes**。
**具体 role class 枚举待定**。

候选（**不裁定**）：

- `request` / `response`（协议语义）
- `data` / `control`（功能）
- `client-origin` / `server-origin`（方向）
- 其他

具体枚举由 **deterministic normalizer** 判定，依赖：

- §4 taxonomy 的 Packet 定义
- Metadata Recon 的可用字段
- `temporal_normalize_v1` 的实现（属 backlog，见
  `docs/实施/路线与里程碑/归一化实现待办（已结案）.md`）

#### §6.6-C2 Observation Population Scope

与 §6.3 / §6.4 一致。

**防 cross-capture double counting**：多个 Observation Population
records 若 co-refer 到同一 Packet semantic object，在同一
concrete aggregate scope 内只形成一个 Packet measurement unit。

#### §6.6-D Eligibility Semantics

三态：eligible / not_eligible / unknown。

一个 Packet pair 的 eligibility 由两个条件决定：

- 是否属于 C2 Observation Population
- 是否能可靠判断并满足 C1 Semantic Applicability Scope

与 §6.3 一致：partial 本身不决定 eligibility。

#### §6.6-E Measurement Outcome

**Outcome 类型：category**（不是 bool）。

可能取值：

- before
- after
- during / overlap
- concurrent
- 其他（由 deterministic normalizer 判定）

**Outcome Status 二态**：known / unknown。

二维矩阵与 §6.3 一致。

注：具体 category 枚举由 temporal_normalize_v1 的
deterministic 定义决定（正常化器实现属 Hub 独立议题，
见 `docs/实施/路线与里程碑/归一化实现待办（已结案）.md`）。
§6.6 只冻结「outcome 是 category」这一形态。

#### §6.6-F Aggregation Semantics

**形态：distribution**。

输出：各 category 的 observed frequency。

约束：

- 每个 eligible Packet pair 对 distribution 最多贡献 1
- 多个 captures / observations co-refer 同一 pair 不得重复计数
- **不要求 numerator / denominator**（与 §6.3 / §6.4 不同）

示例（示意）：

    eligible pair count = 940
    known outcome = 940
      before: 480
      after: 350
      during: 80
      concurrent: 30

输出为 distribution，不是 rate。

**关键含义**：§6.6 独立于 Aggregate Carrier（GAP-R1）——
不需要 S2 / S4 承载位。

#### §6.6-G Unknown / Incomplete Semantics

与 §6.3 一致：eligibility unknown / outcome unknown 分别表达，
不得自动转 false / absent。

D9 默认：只有 eligible + known 进入 distribution 的有效计数。

必须同时保留：unknown_eligibility_count / unknown_outcome_count。

#### §6.6-H Insufficient Observation Semantics

与 §6.3 一致，但触发条件改为：

    effective_known_outcome_count = 0
    → measurement_status = insufficient_observation
    → aggregate value = undefined

禁止伪造空 distribution。

#### §6.6-I Handoff

§6.6 负责定义并形成：

- Packet pair measurement units
- eligibility classification
- known / unknown category outcomes
- temporal_relation distribution aggregation
- insufficient-observation rule

§7 接收这些 measurement outcomes，形成 independence summary。

随后 Statistical Aggregation Stage 按 §6.6 已冻结的公式
materialize distribution，同时携带 §7 的 Independence Support Summary。

§7 不得修改 distribution 成员资格与 aggregation 公式。

#### §6.6 Property-specific Invariants（10 条）

1. `observed_temporal_relation` 表示 Packet pair 的 temporal
   relation distribution。
2. Primary measurement unit = Packet semantic object pair。
3. 一个 Packet pair 对 distribution 最多贡献 1。
4. 多个 observations / captures co-refer 同一 pair 不得重复计数。
5. `outcome = unknown` 不得默认转 false / absent。
6. 每个 concrete contract 必须显式声明 direction applicability。
7. packet timestamp 不进 fact_key；timestamp 只是推导手段。
8. capture 仅为 observation context，不进 fact_key。
9. aggregation 形态为 distribution，不是 rate。
   §6.1-F 的 numerator / denominator 要求不适用。
10. §6.6 独立于 Aggregate Carrier（GAP-R1）。
11. 两端主体限定为 **Packet role classes**，不是具体 instances。
12. **具体 Packet instance 不进 fact_key。**
13. Packet role class 定义由 **deterministic normalizer** 判定。

**冻结范围说明**：§6.6-C1.x 的 role class 枚举属**实现细节**，
不影响 §6.6 的 semantic contract 冻结。§6.6 保持 FINAL FROZEN。

### 6.w population_scope 归属判定（GAP-R4）

**判定**：rate 类 property 的 population_scope 归 **Assertion.value**。

**依据**：

1. R11–R14 已有 observation_scope 放在 value dict 内的现成先例
   （`property_registry.json` value_schema.properties.observation_scope）
2. Claim.scope 语义是「与当前 fact 兼容」（`fused_canonical_spec.md` eligibility gate），
   即协议适用域，与观测总体是不同维度
3. §6.1-y 明确禁止 Measurement Aggregate 与 Independence Support Summary 混同
4. population_scope 更接近「测量数据的来源说明」，属 assertion 元信息

**排除位**：

- `Claim.scope`：条件合法但语义维度不同（见依据 2、3）
- `Evidence.locator`：契约语义是「证据定位」，不合法

**边界**：

- §6.2-9 禁令作用对象是 fact identity，功能性判据是
  「是否因采集实例改变 fact identity」——不排除「在 fact identity
  之外记录观测总体」
- 本判定只定归属层，不定具体 Schema 字段形态（留 Schema Gap Review）

### 6.y Binding Graph（§6-Pre3 产出）

**表**（每个 semantic contract 一行，测试所有 Registry 候选）：

| Semantic Contract | Registry Candidate | Binding Relation | Registry Defined | Producer | Data | Consumer | Semantic Status | Machine Binding Status | Empirical Validation Status |
|---|---|---|---|---|---|---|---|---|---|
| occurrence_frequency | occurrence | PENDING: possible DERIVED_FROM | ✅ | ✅ 2 条 | ❌ 0 | ❌ 0 | FINAL FROZEN | PENDING | NOT_YET_ESTABLISHED |
|  | occurrence_frequency | observed_occurrence_rate | 保持原状（§6.3-B 排除 packet 语义） | ✅ | ❌ 0 | ❌ 0 | ❌ | FINAL FROZEN | PENDING | NOT_YET_ESTABLISHED |  |
|  | co_occurrence | observed_co_occurrence | 保持原状（§6.4-B 排除 packet 语义） | ✅ | ❌ 0 | ❌ 0 | ❌ | FINAL FROZEN | PENDING | NOT_YET_ESTABLISHED |  |
|  | packet_position semantic slot | observed_packet_position | 待 §6.5 解封 | ✅ | ❌ 0 | ❌ 0 | ❌ | NOT YET DRAFTED | PENDING | NOT_YET_ESTABLISHED |  |
| temporal_relation semantic slot | observed_temporal_relation | RESOLVED 方案 (b) | ✅ | ✅ 1 条 | ❌ 0 | ❌ | FINAL FROZEN | PENDING | NOT_YET_ESTABLISHED |

**说明**：

- `occurrence_frequency` ↔ `occurrence` 关系待定：可能是 `DERIVED_FROM`（若 occurrence 是 per-observation 层，frequency 是聚合），也可能是别的。**不得写成 ALIAS_OF。**
- `occurrence_frequency` ↔ `observed_occurrence_rate` 由 §1.2 rule 4 与冻结文档 L104-109 双证：**LEGACY_ALIAS**（改名关系）。
- `co_occurrence` / `observed_co_occurrence` 关系待 §6-Pre3 最终判定。
- `observed_*` family 逐 property 状态待 binding decision 后裁定。**FAMILY POLICY = PENDING。**

### 6.x-gap-r1 GAP-R1 rate 承载勘察结论

**勘察来源**：§6-Pre6 阶段 B（GAP-R1 rate 承载设计只读勘察）。

**7 种候选编码形态**（不裁定）：

| 代号 | 形态 | 判定 |
|---|---|---|
| A | `value = {"numerator": N, "denominator": D, "population_scope": {...}}` | 合法，§6.3-F 强 |
| B | `value = rate 标量`，分子分母与 scope 外置 | 与 §6.w 归属冲突 |
| C | `value = "820/950"` 字符串 | 硬约束排除 |
| D | 拆分为多个 assertion | 硬约束排除 |
| E | `value` 承载分子分母对，scope 复用 `observation_scope` 结构 | 合法，与 R11–R14 同构度最高 |
| F | 独立 measurement aggregate artifact（不进 Fact） | 需重新裁定归属 |
| G | `value` 承载 observed_rate，其余走 provenance / flags | 合法但丢失结构化校验 |

**硬约束排除**：

- C（字符串）：违反 assertion `type` 枚举（无 ratio/fraction 型），
  且无法表达 `denominator = 0` → `insufficient_observation`
- D（拆多 assertion）：破坏 §6.3 invariant 3/4 的聚合完整性
  （分子与分母可被独立 fusion / 独立 resolution）
- B：与 §6.w 归属冲突（population_scope 已裁定归 Assertion.value）

**关键实测**：

- 当前 65 个 Facts 的 `assertion.value` **全是标量**（bool / str）
- **零 dict 形态生产先例**（契约层已定义 dict，生产层从未验证）
- R11–R14 的 value 内 `observation_scope` 是**契约层先例，非生产层先例**
  （四者 producer = 0，data = 0）

**agent 倾向（非裁定）**：路线甲。

理由：与 §6.w 归属一致；改动面最小（不碰 `fact.schema.json`、不扩 type 域）；
不触发 §11.3 的 `schema_version` 判定；上一轮 `_completeness` 双路径修复
已为 rrf 扩展铺路。

**GAP-R1 / R2 / R3 三条路线均需做**，与编码形态选择无关，单独立项：

- GAP-R1：rate 承载位缺失（三元组放哪）
- GAP-R2：Registry 无 rate property 条目，normalizer / comparator 各缺 1 个
- GAP-R3：Pipeline 键空间缺 rate 相关键

### GAP-R1 语义升级（§6-Pre8 阶段 B 结论）

§6-Pre8 阶段 B 勘察发现：§7 independence 四量
（support_unit_count / independent / dependent / unknown）
与 GAP-R1 rate 三元组（numerator / denominator / population_scope）
**需要同一类承载结构**——population-level aggregate。

这不是两个独立问题，是同一承载问题的两个面。

若分开做，§6 与 §7 会各建一套并行设计，违反单一真源原则。

**GAP-R1 重新定义**：
Hub Aggregate Carrier 缺失——现有 Hub 模型无 population-level
aggregate 承载结构，同时阻塞 §6 rate 落地与 §7 independence 四量表达。

这不改变已冻结内容，只扩展 GAP-R1 语义范围。

---

### 6.y.1 Aggregate Carrier 承载位裁定（GAP-R1）

**裁定**：选 **S2（双子对象结构）**。

**依据**：

1. §6.1-y 是**硬约束**——Measurement Aggregate 与 Independence Support
   Summary 是不同 semantic dimensions。S2 结构上分离，天然满足；
   S4 靠命名约定，属软约束。
2. S4 的主要优势（复用 R11–R14 解析逻辑）**已被实测证伪**——
   R11–R14 producer=0 / data=0，该解析逻辑不存在。
3. S2 改动面更小——结构层即达到 S3（独立 artifact）的物理分离效果。
4. 下游消费代价：S2 路径略深，但语义混同代价更大。

**S2 结构形态**：

```
Assertion.value = {
  "measurement": {                      ← §6.3 / §6.4 的 rate 侧
    "numerator":         <int>,
    "denominator":       <int>,
    "observed_rate":     <number>,       ← = numerator / denominator
    "population_scope":  {               ← §6.w 裁定归 Assertion.value
      "dataset":      <string>,
      "capture":      <string>,
      "sample_count": <integer>,
      "time_range":   <string>
    }
  },
  "support": {                           ← §7 的 independence 侧
    "support_unit_count":          <int>,
    "independent_support_count":   <int>,
    "dependent_support_count":     <int>,
    "unknown_support_count":       <int>
    /* 严格 partition: support_unit_count
         = independent + dependent + unknown */
  }
}
```

**承载范围**：

- §6.3 / §6.4 rate 三元组 → `value.measurement`
- §7 independence 四量 → `value.support`
- **§6.6 不在此范围**（distribution 形态，独立；见 §14 E12）

**下一步**：GAP-R2 Registry 条目设计（需单独授权 Registry 变更）。

### 6.z §6 待关闭项

| 项 | 状态 |
|---|---|
| occurrence ↔ occurrence_frequency binding relation | PENDING（DIRECT_BINDING vs DERIVED_FROM） |
| co_occurrence derivation 是否存在 | PENDING |
| observed_* family per-property status | PENDING |
| completeness 问题归属（语义错 vs plumbing 错） | PENDING |
| D9-ISSUE-COMPLETENESS-P0 | 登记，待裁定 |
| R2 value_range P0 | 登记，待裁定 |
| AMBIGUOUS 项（packet_boundary / packet_sequence / inter_arrival_time_us / R11 ⟷ R7） | 登记，待裁定 |

---

## 7. Independence Semantics

**Status**: FINAL FROZEN

**Semantic Contract Status**: FINAL FROZEN
**Machine Binding Status**: PENDING
**Empirical Validation Status**: NOT_YET_ESTABLISHED

**适用范围**：§7 Independence Semantics **只服务 §6.3 / §6.4 的 rate
aggregate**。四量随 rate 承载在 S2 内（§6.y.1），**不单独建 property**。

其他 property 的 independence 不在适用范围。未未来如需泛化，
属 D9 后续版本或独立议题。

**说明（历史）**：本节原 NOT YET DRAFTED。其起草前置为
「§7 与 GAP-R1 合并裁定承载结构」，已于 §6-Pre13/Pre14 完成
（承载位裁定 S2），前置解除。

### 7.1 Independence 三态

`dependent` / `independent-under-policy` / `unknown` 三态。
定义见 §2.2。

**三态是 D9 operational semantics**，不是对真实世界统计独立性的
绝对数学证明（§2.2）。

### 7.2 Dependency Clustering

dependency cluster 表示「已确定相关」的 observation 集合。

**关键约束**：

- 同 cluster 内 observation 不得因数量增加形成额外 independent support
- 不同 cluster **不自动独立**（§2.1）
- cluster **不进 fact_key**（§1.2 rule 4）

**deterministic 判据留 Metadata Recon**（3000 captures 可用字段）。
§7 只冻结语义，**不冻结 clustering 算法**。

### 7.3 Independence Assessment

对每个 support unit 判定三态之一。

**support unit 是 §7 的语义对象**：

- 由 dependency clustering 产生
- 每个 support unit 承担 1 个独立支持角色
- support unit 的 identity 语义留 Metadata Recon

**Frozen Independence Policy** 的判定规则留 Metadata Recon。
§7 只冻结「三态分类」这一语义结构。

### 7.4 Support Summary

四量承载在 S2（§6.y.1）：

    support_unit_count
    independent_support_count
    dependent_support_count
    unknown_support_count

严格 partition：

    support_unit_count
    = independent_support_count
    + dependent_support_count
    + unknown_support_count

四量随 rate aggregate 同时 materialize。

### 7.5 §6 / §7 Boundary

§6 定义 measurement semantics（rate / distribution）。
§7 定义 independence semantics（三态 / 四量）。

二者独立（§6.1-y）。

§7 **不得修改** §6 的 numerator / denominator / outcome distribution。
§6 **不引用** §7 三态。

### 7.6 §7 Invariants

1. 三态是 operational semantics，不是数学独立性证明。
2. 同 cluster 不重复计数。
3. 不同 cluster 不自动独立。
4. `unknown` 不自动按 `independent` 处理。
5. cluster 不进 fact_key。
6. support unit 由 dependency clustering 产生。
7. 四量承载在 S2。
8. §7 只服务 §6.3 / §6.4。
9. §7 不修改 §6 语义。

## 8. Traffic Claim Formation Contract

**Status**: FINAL FROZEN

**Semantic Contract Status**: FINAL FROZEN
**Machine Binding Status**: PENDING
**Empirical Validation Status**: NOT_YET_ESTABLISHED

### 8.0 §8 范围

§8 定义 raw observation → Traffic Claim 的聚合契约。

它从 §5（dedup / co-reference）+ §6（measurement contract）
+ §7（independence summary）取材，形成 Traffic Claim。

§8 **不修改** §5 / §6 / §7 已冻结的语义。

### 8.1 Traffic Claim 定义

一条 Traffic Claim = 一条 **population-level observational assertion**。

它携带：

- measurement aggregate（§6）
- independence support summary（§7）
- provenance（§5）

它**不是** raw observation，也不是单一 instance assertion。

### 8.2 Claim Formation 条件

Traffic Claim 形成的必要条件：

1. `measurement_status` ≠ `insufficient_observation`
2. 至少 1 个 eligible known outcome

不满足时：不形成 Claim，或形成 `insufficient_observation`
状态的占位 Claim（待裁定，见 §8.5）。

**§8 默认：不形成 Claim。**
`insufficient_observation` 属测量层状态，**不 materialize 为 Claim**。

### 8.3 Claim 与 fact_key 的关系

每条 Traffic Claim 投影到一个 canonical fact_key。

fact_key 构成由 **§9 Hub Boundary** 定义。
§8 只冻结「每条 Traffic Claim 必须**唯一**投影到一个 fact_key」。

**每个 fact_key 下的 Claim 数**：

§8 默认：**一个 fact_key 下可有多条 Traffic Claim**
（不同 population scope / 不同 measurement unit）。
多 Claim 在 Phase A 相遇时按既有 resolution 机制处理。

### 8.4 Claim 的聚合语义

Traffic Claim 的 assertion 承载：

- measurement aggregate（rate / distribution，来自 §6）
- independence summary（四量，来自 §7）

具体承载结构由 **S2**（§6.y.1）定义。

**禁止**：把 raw observation count 作为 Claim 的语义依据（§1.5 rule 10）。

### 8.5 §8 未决

- `insufficient_observation` 是否 materialize 为 Claim（默认否）
- 一个 fact_key 下多条 Claim 的 resolution 细节
- 与 §9 Hub Boundary 的接口（待 §9 起草后回填）

### 8.6 §8 Invariants

1. Traffic Claim 是 population-level observational assertion。
2. 每条 Traffic Claim 唯一投影到一个 fact_key。
3. raw observation count 不得作为 Claim 语义依据。
4. §8 不修改 §5 / §6 / §7 语义。
5. `insufficient_observation` 默认不形成 Claim。
6. Claim 携带 measurement aggregate + independence summary。
7. 一个 fact_key 下可有多条 Claim。

## 9. Hub Boundary

**Status**: FINAL FROZEN

**Semantic Contract Status**: FINAL FROZEN
**Machine Binding Status**: PENDING
**Empirical Validation Status**: NOT_YET_ESTABLISHED

### 9.0 §9 范围

§9 定义 **cluster / independence 信息在 Hub 中的归属层**。
它回答 §11 Traceability Matrix 的 **Q6**。

§9 **不设计 schema 字段**，只冻结**归属层**。

### 9.1 S2 承载位落点

GAP-R1 承载位裁定为 **S2**（§6.y.1）。

S2 结构承载：

- rate 三元组（§6.3 / §6.4）
- independence 四量（§7）

落点：

- measurement aggregate：**Assertion.value**（§6.w）
- independence summary：随 measurement aggregate 同结构
  （S2 双子对象）

具体 schema 字段形态留 Schema Gap Review。

### 9.2 D9-GAP-PAIR-IDENTITY 处置

Q2（co_occurrence 的 header pair）判定**方案 (b) 可行**。

pair identity 用 **subject 复合编码**承载：

- 两端均为 Header（`kind=header` 已在枚举内）
- `subject` 无 pattern 约束
- 编码规则由 §6.4 提供（alias 归一 → A≠B 检查 →
  deterministic ordering → canonical unordered pair）

具体分隔符留 §9 内裁（见 §9.2.x）。

**不触发 Schema Gap Review。**

### 9.2.x Q2 分隔符裁定

**裁定**：`::`（双冒号）

**理由**：

- **ASCII**，不在 RFC 7230 token 字符集内，与 header name 无冲突
  （实测：subject_registry 现有 8 个 category
  `method / header / state / url / session / status / event / other`
  **无一含** token 字符）
- 候选 `+` / `&` / `|` **均在** RFC 7230 token 字符集内 → 排除
- 候选 `×` 的 UTF-8 兼容性未验证 → 排除
- **双字符**降低与未来扩展冲突的概率

**canonical pair 编码形式**：

```
subject = "<header_A>::<header_B>"
```

两端 header name **已 alias 归一**，按 §6.4 规则做 deterministic ordering
（§6.4 Canonicalization 顺序：raw → alias 归一 → canonical IDs
→ A≠B 检查 → deterministic ordering → canonical unordered pair）。

### 9.3 Q3 kind 扩展

Q3（`packet_role_pair`）判定**方案 (b) 不可行**。

**状态：RESOLVED** —— `fact_key.kind` 枚举已扩展 `packet_role_pair`
（实施于 §6-Pre21 阶段 C，§14 E27）。

```
fact_key.kind.enum:
  [method, header, constraint, state, transition, packet_role_pair]   <- 6 值
```

`observed_temporal_relation.allowed_kinds` 同步扩展；
`schema_version` 已 bump 至 `"2.0"`；`derived/` 已重跑同步。

规范依据：`docs/实施/立项提案/D9第三问α扩展草案.md`（Frozen）。

### 9.4 independence 归属层

§7 四量承载在 S2（§6.y.1）。
**cluster 不进 fact_key**（§1.2 rule 4）。

cluster 的具体承载位置（Evidence / 其他）留 Schema Gap Review。

### 9.5 population scope 归属

GAP-R4 裁定 population_scope 归 **Assertion.value**（§6.w）。

§6.2-9 禁令作用对象是 fact identity，**不排除**「在 fact identity
之外记录观测总体」。

具体字段形态留 Schema Gap Review。

### 9.6 §9 Invariants

1. S2 承载 rate + independence summary，两者结构分离（§6.1-y）。
2. Q2 pair identity 用 subject 复合编码，不触发 Schema Gap Review。
3. Q3 需扩展 kind 枚举，触发 Schema Gap Review。
4. cluster 不进 fact_key。
5. population_scope 归 Assertion.value。
6. §9 不设计 schema 字段，只冻结归属层。

## 10. Downstream Interpretation Contract

**Status**: FINAL FROZEN

**Semantic Contract Status**: FINAL FROZEN

### 10.0 §10 范围

§10 定义 rate / distribution / independence summary
在**下游**（RAG / seedgen / LLM）应被**如何解释**。

§10 **不设计** RAG / seedgen 实现。

### 10.1 raw_support 解释约束

`raw_support_count` **不得被描述为「独立支持次数」**。

只有 `independent_support_count` 是独立支持。
`unknown_support_count` **不得合入** `independent_support_count`。

### 10.2 observed_rate 解释约束

`observed_rate` **必须同时携带 denominator semantics**
（即 population scope + eligibility 条件）。

**裸 rate（无 denominator）语义不完整。**

### 10.3 independence summary 解释约束

三态语义必须**完整呈现**：independent / dependent / unknown。

下游**不得**：

- 把 unknown 当 independent
- 把 dependent 从 summary 中省略
- 用 independent / support_unit 替代 observed_rate

### 10.4 LLM / RAG 硬约束

RAG / LLM **不得仅根据 raw N 推导 confidence / prevalence**。

任何 confidence / prevalence 声明**必须同时引用**：

- measurement aggregate（含 denominator）
- independence support summary

### 10.5 §10 Invariants

1. `raw_support_count` 不得被描述为独立支持次数。
2. `observed_rate` 必须携带 denominator semantics。
3. independence 三态必须完整呈现。
4. 不得仅根据 raw N 推导 confidence / prevalence。

## 11. Q0–Q10 Traceability Matrix

**Status**: FINAL FROZEN

| Question | Canonical answer section | Status |
|---|---|---|
| Q0 Traffic Claim 代表什么 | §8 | FINAL FROZEN |
| Q1 measurement unit | §6 | FINAL FROZEN |
| Q2 population / numerator / denominator | §6 | FINAL FROZEN |
| Q3 independence unit | §7 | FINAL FROZEN |
| Q4 cluster vs independence | §7 | FINAL FROZEN |
| Q5 dedup / dependency observable inputs | §5 + Metadata Recon | Partial |
| Q6 信息归属 | §9 | Pending |
| Q7 raw observation → Claim | §8 | FINAL FROZEN |
| Q8 Phase A | §1 | Frozen: NO CHANGE |
| Q9 Phase B | §1 | Frozen: NO CHANGE |
| Q10 RAG / seedgen interpretation | §10 | FINAL FROZEN |

## 12. Semantic Contract -> Metadata Recon Boundary

**Status**: FINAL FROZEN

D9 第一轮**只冻结 semantic contract**。
Metadata Recon（3000 captures 可用字段）之前**不决定实际 cluster key**。

**第一轮已完成**：§0-§8、§10 的 semantic contract。

**Metadata Recon 待解**：

- dependency clustering 的 deterministic 判据
- Frozen Independence Policy 判定规则
- support unit identity semantics
- Packet role class 枚举（§6.6-C1.x / §15.1 #22）
- Message reconstruction 算法
- request-response pairing rule

**Metadata Recon 不改变已冻结的 semantic contract**。

**不阻塞 §9 起草**：§9 的 fact_key 承载问题（Q2 / Q3）与上述 6 项**无依赖**。

## 13. Relationship to Frozen Hub Contracts

**Status**: FINAL FROZEN

本设计**不改**以下冻结文档：

- fused_canonical_spec.md
- fused_canonical_spec.md
- fused_canonical_spec.md
- fused_canonical_spec.md
- fused_canonical_spec.md
- fused_canonical_spec.md

本设计**新增 / 修改**：

- `property_registry.json` 追加 `observed_presence_rate`（已落盘，§14 E15）
- `fact.schema.json` 追加 `packet_role_pair` kind（已实施，§14 E27）
- `property_registry.allowed_kinds` 扩展（已实施，§14 E27）
- `schema_version` 已 bump 至 `"2.0"`（已实施，§14 E27）

本设计触发的 Schema Gap Review 项：

- D9-GAP-PAIR-IDENTITY **不触发**。实测（§6-Pre17 阶段 B）：
  Q2 两端为 Header subject，`kind = header` 已在现有枚举内；
  `subject` 无 pattern 约束 => 方案 (b) 可行，无需 Schema 变更
- Q3 kind 扩展 **已实施**（§14 E27）

## 14. Errata

### E1. §6-Pre2 结论更正：occurrence_frequency / co_occurrence 非「全仓 0 命中」

§6-Pre2 记的「occurrence_frequency / co_occurrence 全仓 0 命中」不准确。

**更正**：六 root（core / fused_hub / tests / scripts / derived / kb）确实是 0，但 `docs/` 有 26 / 76 处。其中 `step_2.5.1/property_candidates.txt:79-80` 是真实历史记录——`occurrence_frequency` 是设计期名，含义「traffic_pcap kind=field 出现次数」。

准确表述是「机器资产中无同名 key」。

### E2. occurrence_frequency ↔ observed_occurrence_rate 改名关系确认

经 §6-Pre3 与 §1.2 rule 4 双证：`occurrence_frequency` 是 D9 契约层活跃术语（§1.2 rule 4 直接使用），经冻结文档 L104-109 的改名条款落地为 `observed_occurrence_rate`。Binding Relation = **LEGACY_ALIAS**。

### E3. 4.8b 选型记录范围更正

4.8b 选型记录（pipeline_rules_design.md:137-143）只提了 `observed_occurrence_rate` 一个，**漏了 R2 value_range P0**。该 P0 同因 `_completeness` 缺陷：min/max 在 value dict 内部而 `view.get()` 恒为 None。

### E4. completeness 缺陷归属

`_completeness`（phase_a.py:403）键空间只有 3 个 key，而 `resolution_required_fields` 里 min/max/observation_scope 都在 value dict 内部 → `view.get()` 恒为 None → 恒 partial。

**关键证据**：同文件 `_supplement`（L349-393）已正确实现双路径解析，docstring 明写 field 指向 "value 子字段，不是 Assertion 自身的 3 个字段"，而 `_completeness` 没有这层分支。

**判定**：这是 **plumbing bug，不是语义模型错误**。波及 5 个 property，含 R2 value_range P0。

### E5. §6.y Consumer 行事实更正

§6.y 原写 occurrence 的 Consumer = ✅（core/ 3 行）为事实错误。

实测 consumer = 0。那 3 行为：

- 2 个 producer（candidateization.py:224 / :279）
- 1 条 docstring（semantic_relation.py:106）

SR-2 判据是 property-agnostic 的 `a.property != b.property`，未引用 occurrence。

### E6. GAP-R4 population_scope 归属判定

GAP-R4（population_scope 归属未定）已裁定：
归 Assertion.value。详见 §6.w。

### E7. _completeness 修复（GAP-R5）

phase_a.py _completeness（L403-413 → L403-440）修复完成。
采用候选 2：按 _supplement docstring 已冻结的「field 分两层」口径
重写 _completeness，实现双路径解析。

- value 子字段路径：先取 Assertion.value 再取子键
- Assertion 自身字段路径：直取
- value 非 dict + required_field 指向 value 子字段：跳过不判 partial

影响：R2 value_range、R11–R14 observed_* 的 completeness 判定。

### E8. relations.jsonl 数更正

此前记录「516 relations」为错误记录。
实测 relations.jsonl 为 **473 行**，且全程逐字节未变。
473 一直是真实数量。

### E9. §6.6 PAUSED 解除

§6.6 observed_temporal_relation 原 PAUSED 理由为
「与 §6.5 同步暂停」，属自同步决定，非技术依赖。

§6-Pre9 阶段 D 实测对比确认：

- R14 value.desc "temporal AST of observation" 不含糊
- R14 引用 temporal_normalize_v1 / temporal_relation_v1
  （**仅为 Registry 声明字符串**；§6-Pre10 阶段 B 实测：全部 9 个
  normalizer / comparator 在 `core/` 中**均无实现**，
  仅被 `registry_index.py:123-124` 读为字符串，
  实现属 Phase 4.4 / 4.6 范围。故此项**不构成 §6.6 的实现优势**）
- M3 依赖为否

解除 PAUSED，状态改为 READY FOR PRECEDING RECON。
前置为 temporal_relation semantic recon。

### E10. normalizer / comparator 实现状态更正

§6-Pre9 阶段 D 曾记「R14 已有 temporal_normalize_v1 + temporal_relation_v1
配套机器构件已就位」。

Pre10 阶段 B 更正：9 个 normalizer 在 core/ 中全部零实现。
temporal_normalize_v1 / temporal_relation_v1 全仓各只有 1 处命中，
即 property_registry.json:382/383 的声明字符串，无任何分派实现。

契约侧确认这是既定范围划分（registry_index.py:158-160、
normalization.py:27-29/127 记实现属 Phase 4.4 / 4.6 范围）。

含义：normalizer / comparator 不构成 §6.6 相对 §6.5 的实现优势——
18 个 property 全部零实现。

### E11. §6.6 A 项语义裁定

§6.6 observed_temporal_relation 的 A 项语义裁定为
「Packet semantic objects 之间的 temporal relation」。

排除版本：

- 丙-1（capture 进 fact_key identity）— 违反 §1.2 rule 4
- 丁（跨 capture / run）— 直接违反 §1.2 rule 4
- 甲 / 乙 / 戊 — 无 Registry 层客观证据

capture 仅为 observation context，不进 fact_key。
「Capture 内 Packet 序号」不等同于 capture 身份。

### E12. §6.6 aggregation 形态裁定

§6.6 observed_temporal_relation 的 aggregation 形态裁定为
**distribution**，不是 rate / proportion。

§6.1-F 的 numerator / denominator 要求不适用。

含义：§6.6 独立于 Aggregate Carrier（GAP-R1）。

timestamp 修正：packet timestamp 不进 fact_key，
timestamp 只是推导手段。消除与 §6.2-11 的张力。

### E13. Aggregate Carrier 承载位裁定

GAP-R1 承载位裁定为 **S2**（双子对象结构）。

依据：§6.1-y 硬约束 + S4 优势被实测证伪 + S2 改动面更小。

承载范围：§6.3 / §6.4 rate 三元组 + §7 independence 四量。

§6.6 不在此范围（distribution 形态，独立）。

### E14. §6.6-C1 两端主体裁定

§6.6 observed_temporal_relation 的两端主体裁定为
**Packet role classes**，不是具体 Packet instances。

排除候选：

- 甲（任意两个 Packet）— 太泛，无法形成稳定 fact
- 丙（Transaction 内 positions）— 依赖 §5 reconstruction（全未实现）

具体 role class 枚举留 §6.6-C1.x 或 Metadata Recon。

### E15. GAP-R2 Registry 条目落盘

追加 `observed_presence_rate` 至 `property_registry.json`（18 → 19 条）。
与 R11 `observed_occurrence_rate` **并列共存**。

**语义区分**：**presence rate vs multiplicity**——
前者是 §6.3 定义的 Message-level presence rate（S2 双子对象承载），
后者是 within-Message occurrence multiplicity。**不是同一 property 的两个版本。**
R11 保持原状。

Registry fingerprint 因文件变更而改变：
sha256_full `0c6e5853…` → `5a168877…`

**连带后果**：`derived/hub/meta.json` 记录的 Registry fingerprint 与
`build_fingerprint` **均已陈旧**（实测不一致）。该产物需重跑融合才能恢复
一致；本步禁止 build experiment，故暂留待后续授权。

注：Registry property 条目**无** `notes` / `comment` 字段（实测 0/18），
故本并列关系按 A2 的回退条款登记于此。

### E16. §7 Independence Semantics 起草

§7 起草完成，只服务 §6.3 / §6.4 的 rate aggregate。

三态 / 四量语义已冻结。clustering / policy / support unit identity
的 deterministic 判据留 Metadata Recon。

### E17. §6.6-C1.x role class 枚举登记

§6.6 的两端主体为 Packet role classes。
具体枚举留 §6.6-C1.x 与 Metadata Recon。

此项**不阻塞** §6.6 的 semantic contract 冻结。

### E18. Registry 变更后的 canonical 同步

property_registry.json 变更后，derived/hub/meta.json 的
registry fingerprint 陈旧（磁盘 actual = sha256:5a168877…，
meta expected = sha256:0c6e5853…）。

重跑 build_hub.py 后同步完成。

**同步结果**（`--sources rfc expert_note vuln --skip-per-source`）:

- derived/hub 13 文件: **11 SAME / 2 CHANGED**
  （仅 meta.json / profile.json；facts / audit / graph 全部逐字节不变）
- registry fingerprint 对齐: `sha256:5a168877…` ✔
- build_fingerprint: `b0d457b1…` → `e7711ab2…`
- fusion_version: **仍为 fusion_v3**（未 bump，见下）
- profile 统计全部未变（65 Facts / 62 complete / 75 claims）

**fusion_version 判定: 不需 bump。**
§11.3 的 10 条绑定项全为**规则内容 / 语义**（Pair-Generation、
SemanticRelationEvaluationRule、Claim Classification、Authority、
Phase A / Phase B、Lineage、Graph Derivation、Profile Derivation），
**不含 property registry 的内容**。新增一个零 producer、零 data 的
property 不改变任何一条绑定项 ⟹ 不触发 bump。
（对照 §14 E4：`_completeness` 修复改的是 Phase A 判定逻辑本身，故已 bump）

**per_source 同步: 已完成（§6-Pre17 阶段 A）。**
derived/per_source/{rfc, expert_note, vuln}/meta.json **均含 `registries`**
字段，其 registry fingerprint 此前同样陈旧。
重跑范围：`derived/hub/` + `derived/per_source/{rfc, expert_note, vuln}`。

**同步结果**：三源 registry fingerprint 全部对齐 `sha256:5a168877…` ✔

★ 实际变更范围为**每源 2 个文件**（meta.json + profile.json），
   而非 A2 预期的「仅 meta.json」。原因是 `profile.json` 内嵌
   `build_fingerprint` 字段，Registry 变更必然使其同步改变——
   与 §6-Pre16 中 `derived/hub/profile.json` 的变化**同源同机制**。
   三源 profile.json 文件大小均未变（1721 / 1372 / 3417 B），
   与 build_fingerprint 为定长字符串一致。
   facts / audit / graph 共 11 个文件/source **全部逐字节不变**。

### E19. §8 Traffic Claim Formation 起草

§8 起草完成。定义 raw observation → Traffic Claim 的聚合契约。

与 §9 Hub Boundary 的接口留 §8.5 待回填。

### E20. §10 Downstream Interpretation 起草

§10 起草完成。定义下游解释约束。

不含实现设计。

### E21. §11–§13 起草

§11 Traceability Matrix / §12 Metadata Recon Boundary /
§13 Relationship to Frozen Hub Contracts 起草完成。

**修正（对 §6-Pre16 阶段 D）**：该阶段判「Q2 / Q3 同源，可合并处置」。
§6-Pre17 阶段 B 实测推翻该判断：
- Q2 两端是 Header（协议语义单位）→ `kind=header` 已在枚举内，
  且 `subject` 无 pattern 约束 ⟹ 方案 (b) 可行，**不触发 Schema 变更**
- Q3 两端是 Packet（传输层单位）→ 5 个 kind **无对应类目**
  ⟹ 方案 (a) 必需，**触发 Schema Gap Review**
⟹ 二者**必须分开处置**；以 §6-Pre17 阶段 B 结论为准。

**Pre17 修正**：Pre16 阶段 D 判「Q2 / Q3 同源可合并」不成立——
它漏了「Q2 两端是 Header 已有 kind」这一关键事实。

- Q2：Header pair，`kind=header` 已在枚举内，subject 无 pattern 约束 → 方案 (b) 可行
- Q3：`packet_role_pair`，Packet 是 §4.3 传输层单位，5 个 kind 均为协议语义单位，
  无对应类目 → 方案 (b) 不可行，(a) 必需

两者阻塞点不同，不能合并处置。

### E22. §9 Hub Boundary 起草

§9 起草完成，冻结归属层语义。

Q3 相关部分 PENDING Schema Gap Review。

### E23. Q2 分隔符裁定

§9.2.x 分隔符裁定为 `::`。

排除依据：RFC 7230 token 字符集含 `+` / `&` / `|`。

实测佐证：subject_registry 现有 8 个 category 无一含 token 字符。

### E24. Q3 α 规范冻结

`docs/实施/立项提案/D9第三问α扩展草案.md` 状态转 **Frozen**。

待裁定项：

- kind 名称：`packet_role_pair`
- `allowed_kinds` 必扩展：`observed_temporal_relation`
- `schema_version`：逐步演进
- 3 个待评估 property：待下一轮

实施顺序见规范 §7。

★ §6-Pre20 阶段 B 勘察修正: 原列为「待评估」的
  `observed_occurrence_rate` / `observed_co_occurrence`，
  其契约适用域（§6.3-B / §6.4-B）**已明确排除 packet 语义**
  ⟹ 二者属**过度保守**，建议裁定为**保持原状**；
  仅 `observed_packet_position` 因 §6.5 BLOCKED 真正待评估。

---

### E25. Pre17 §12/§13 报告错误更正

Pre17 报告曾称「§12 / §13 已起草」为假消息。

根因：Pre17 阶段 C 脚本只插入了 §11，`new12` / `new13` 虽构造但未写入文件，
脚本 log 却打印了「C2 / C3 起草」的假消息。

**文件正确（始终是 stub），报告错误。**

Pre20 已修正状态行；§6-Pre21 已补写 §12 / §13 正文。

---

### E26. Q3 待评估 property 裁定

- `observed_occurrence_rate`：**保持原状**（§6.3-B 排除 packet 语义）
- `observed_co_occurrence`：**保持原状**（§6.4-B 排除 packet 语义）
- `observed_packet_position`：**待 §6.5 解封**（Q3 kind 扩展**不必**等它，两者解耦）

§6-Pre20 阶段 B 勘察修正: 前两项原列为「待评估」属**过度保守**，
其契约适用域已明确排除 packet 语义。

---

### E27. Q3 kind 扩展实施

- `fact.schema.json`：`kind` 枚举 `+packet_role_pair`（5 `→` 6 值）
- `property_registry.json`：`observed_temporal_relation.allowed_kinds`
  `+packet_role_pair`（**仅此 1 条**，其余 18 条逐条未变）
- `schema_version`：逐步演进（`build_inputs.py:250` + `synthetic.py:99`）
- `derived/` 已同步（fused + per_source 三源）

fingerprint:
  Registry   `5a168877…` `→` `3165d8fd…`
  build      `e7711ab2…` `→` `073a1101…`

**4 个受改文件各恰好 1 行差异**（逐行 diff 验证）。

`fusion_version` 保持 `fusion_v3`（新增 kind 不改变任何既有 Fact 的
resolution 语义，见 §11.3 绑定清单）。

### E28. fact.schema.json kind.description 修正

Q3 加 `packet_role_pair` 时漏改 `kind.description`——
其原文仍写「one of the 5 fixed kinds」，
与 enum 的 6 值**矛盾**。

本步修正为「one of the 6 fixed kinds (packet_role_pair added in D9 Q3)」。
逐行 diff：283 行 `→` 283 行，**差异恰好 1 行**（L31）。

**schema_version 不 bump**——description 修正不改变语义约束，
不影响 Fact 合法性（§11.3 L862：仅「Storage Contract 语义变化」才 bump）。

`derived/` 已重跑同步 fingerprint：
  build `073a1101…` `→` `5017304a…`
  Registry 不变（`3165d8fd…`，description 属 schema 文件但不入 Registry 指纹）


### E29. Pre15 回归 7 步未抓到（流程教训）

§6-Pre15 追加 `observed_presence_rate` 至 `property_registry.json`，
`test_candidate_layer.py:505` 的计数断言过期。

但 Pre15 明示「不跑 pytest」，Pre16–Pre21 六步也均未跑，
**漂移 7 步未被发现**，直到 Pre22 全量 pytest 才抓到。

**性质**：
- 纯计数断言过期，不是行为回归
- RegistryIndex 功能未受影响（该测试其余断言全部通过）
- 65 Facts 逐字节未变（`observed_presence_rate` 无 producer / 无 data）

**修复**：Pre23 单行修改 `== 18` `→` `== 19`，**保留字面量**
（不改动态读取——与 vuln 处理先例一致，自指断言会丧失钉死能力）。

**流程缺陷**：
- 修改 Registry / Schema / core 的步骤应包含至少相关测试
- 「不跑 pytest」的授权只应针对纯文档步骤
- 授权模板缺「何时必须跑」的判据


### E30. D9 Final Frozen

§0–§13 全部 semantic contract 已审定。

§6.5 保持 BLOCKED——等 M3 authoritative semantic provenance
（外部输入，仓库内不存在权威源）。

§6.6-C1.x 保持 PENDING——依赖 Metadata Recon。

其余全部 Final Frozen。

D9 设计阶段关闭。


### E31. D9 关闭清单

A. 本设计范围内待解：§6.5 / §6.6-C1.x
B. 独立议题：Q3 / Aggregate Carrier / Normalizer / Hub Errata
C. 已关闭：GAP-R1/R2/R4/R5、PAIR-IDENTITY、Pre15 流程缺陷

详见 §15.1。


### E32. Traffic corpus capture-count correction

旧：D9 §0.1 记「3000 capture」。
新：当前 corpus layout / manifest 确认 **1000 capture units**。

此前 3000 的来源 / 误计原因当前未建立，**不猜**。

性质：empirical corpus fact correction，不改变 D9 semantic contract。

注：不得写成「1000 独立 captures」，也不得写成「1000 dependent captures」。
只写 **1000 capture units**。

### E33. Capture extension / container-format mismatch

- `capture.pcapng` → actual container: **classic libpcap**
- `clean.pcapng` → actual container: **pcapng**

Parser selection **不得仅依赖 filename extension**。
必须使用 magic / container signature 或等价 deterministic format detection。

这是后续 Traffic parser 很容易踩中的坑，需尽快传播。

### E34. Traffic Metadata Recon empirical findings

Traffic Metadata Recon（独立 backup 目录）已完成，PASS。

**关键发现**：
- 1000 capture units，每个目录恒含 6 件套
  （capture.pcapng / clean.pcapng / client.log / packets.ndjson /
   rtp.csv / rtsp.csv）+ 根部 1 个 manifest.csv
- manifest 里 stream / url / duration / 各包计数 distinct 全为 1
  → 观察到单一场景配置
- 每 capture RTSP 控制流固定 5 条消息
  （OPTIONS→DESCRIBE→SETUP→PLAY→TEARDOWN）
- rtsp.session 在 1000 capture 中全为 `000022B8`
- 无 transaction id / request id / tcp.stream / connection id /
  collector 字段

**Capability 分布**（详见
 `docs/设计/各源设计/流量源/traffic源语料能力档位.md`）：
- STRONG：Message reconstruction / Request-response pairing
- NOT ESTABLISHED：Cross-capture independence /
  Support unit identity / Cross-scenario prevalence /
  Implementation diversity / Scenario diversity

**性质**：empirical corpus capability limitation，
**不是** D9 contract contradiction。
D9 §0–§13 Final Frozen 不变。

### E35. §7.2 Dependency Clustering input status

Traffic Metadata Recon + Q1 Recon 实测：
当前 corpus 唯一可观测的差异轴是 transport 和 scenario index，
二者完全共变；无独立 run / collector / connection / transaction
 / request identity 信号。

**结论**：当前 corpus 无法导出 dependency clustering 的
非共变 differentiation axis。

**§7.2 语义不变**——这是 corpus 事实限制，不是 contract 缺陷。

详见 `docs/设计/各源设计/流量源/traffic源语料能力档位.md` §8。

**不得**在 Candidateization Design 中假装该判据
能从当前语料导出。

### E36. Traffic Pre-Design Closure findings

Traffic Pre-Design Closure 实测推翻两个前序记录，
并确认 capture identity / frame mapping：

- `rtsp.csv` 三变体与 pair 结构 **500/500 ALIGNED**
  （推翻「不服从 pair」）
- `capture.pcapng` 包数 **55/56/57/58**
  （推翻「486–490」；修正后分布恰好对上 936/60/2/2）
- `frame.number` 同一命名空间，四个投影；
  capture 内 canonical identity = `(unit, capture_frame)`
- `clean.pcapng → capture.pcapng` deterministic 映射
  （1000/1000 唯一命中）

**性质**：corpus 事实澄清，不改变 D9 semantic contract。

**对 §0–§13 的影响**：无。被推翻的两个数字从未进入 D9 正文
（全量盘查 `docs/` 无 actionable 命中），故本条只需 §14 登记，
**不需要** 对 §0–§13 开 errata。

**Lane 影响**：Lane A 前置条件已清零（见
`docs/设计/各源设计/流量源/traffic源候选项化预设计.md` §4.0）。
Lane B 仍为 no materialization，理由见该文件 §4.1 / §4.3 / §4.4。

详见 `docs/设计/各源设计/流量源/traffic源语料能力档位.md` §10。

---

## 15. Open Items / Deferred / Freeze Criteria

### 15.1 Open Items

| # | 项 | 状态 |
|---|---|---|
| 1 | D9-ISSUE-COMPLETENESS-P0 | FIXED（§14 E7） |
| 2 | R2 value_range P0 | FIXED（同 E7，同根因） |
| 3 | occurrence ↔ occurrence_frequency binding relation | PENDING |
| 4 | co_occurrence derivation | PENDING |
| 5 | observed_* family per-property status | PENDING |
| 6 | packet_boundary / packet_sequence / inter_arrival_time_us → R13/R14 | AMBIGUOUS |
| 7 | R11 ⟷ R7 语义等价性 | AMBIGUOUS |
| 8 | D9-GAP-PAIR-IDENTITY | RESOLVED 方案 (b)（见 §13）——pair identity 用 subject 复合编码承载，**不触发 Schema Gap Review** |
| 9 | joint_distribution | Deferred Candidate |
| 10 | occurrence_multiplicity | Deferred Candidate |
| 11 | Metadata Recon（3000 captures 可用字段） | Pending |
| 12 | M3 authoritative semantic provenance | Pending（§6.5 解除 BLOCKED 前置） |
| 13 | FAMILY POLICY | PENDING |
| 14 | GAP-R4 population_scope 归属 | RESOLVED（归 Assertion.value，见 §6.w） |
| 15 | GAP-R1 Hub Aggregate Carrier 承载位 | RESOLVED（选 S2，见 §6.y.1） |
| 16 | GAP-R2 Registry rate 条目设计 | RESOLVED（`observed_presence_rate` 已落盘，见 §14 E15） |
| 17 | GAP-R3 Pipeline rate 键空间 | PENDING（依赖 GAP-R2） |
| 18 | GAP-R5（= #1 D9-ISSUE-COMPLETENESS-P0 别名） | FIXED（见 #1） |
| 19 | §6.6 temporal_relation semantic recon | DONE（Pre10 阶段 B） |
| 20 | §6.6 P1 / P2 裁定（measurement unit / 两端主体） | PENDING（依赖 #19） |
| 21 | §6.6 A 项语义候选方案（P1 / P2 前置） | RESOLVED（Pre11 阶段 B，裁定见 §14 E11） |
| 22 | §6.6-C1.x Packet role class 枚举 | PENDING（依赖 Metadata Recon） |
| 23 | Q3 packet_role_pair 扩展 kind 枚举 | DONE（已实施，见 §14 E27） |
| 24 | Q2 分隔符 | RESOLVED（`::`，见 §9.2.x） |
| 25 | Q3 α 规范草案审阅 | DONE（已冻结，`docs/实施/立项提案/D9第三问α扩展草案.md`） |
| D9-DOC-INCONSISTENCY-01 | `fused_canonical_spec.md:243` condition 枚举含 `code_branch`，`condition.schema.json` anyOf 无对应 | 契约一致性，非 D9 范围 |
| D9-DOC-INCONSISTENCY-02 | `models.py:456-458` 声称 `Locator.type` 由 `fact.schema.json` discriminated schema 定义，实测为 `{"type":"string"}` | 契约一致性，非 D9 范围 |

### 15.2 Final Freeze Statement

**本设计已 Final Frozen。**

**冻结范围**：
    §0–§5：Final Frozen
    §6.1 / §6.2 / §6.3 / §6.4：Final Frozen
    §6.6：Final Frozen
    §7 / §8 / §9 / §10 / §11 / §12 / §13：Final Frozen
    §14 Errata：Final Frozen
    §15 Open Items：Final Frozen

**开放项**（不属 Final Frozen 范围）：
    §6.5 observed_packet_position：BLOCKED
      等 M3 authoritative semantic provenance（外部输入）
    §6.6-C1.x Packet role class 枚举：PENDING
      依赖 Metadata Recon

**关联独立议题**（不属本设计范围）：
    - `docs/实施/立项提案/D9第三问类型扩展立项.md`（已 COMMITTED）
    - `docs/实施/立项提案/D9聚合载体立项.md`
    - `docs/实施/路线与里程碑/归一化实现待办（已结案）.md`
    - `docs/实施/待办与勘误/中枢契约勘误待办.md`

**Freeze 依据**：
    - §0–§13 全部 semantic contract 已审定
    - Q3 kind 扩展 Transaction 已 COMMITTED
    - Hub 侧 schema_version / fusion_version 已同步
    - 全量 pytest 2684 passed / 8 skipped / 0 failed

**当前状态**：
    Final Frozen（除 §6.5 / §6.6-C1.x 外）

---

**traffic_d9_design.md Partial Frozen Candidate 完毕。**

**traffic_d9_design.md Final Frozen 完毕。**

**§0–§13 Final Frozen。§6.5 BLOCKED。§6.6-C1.x PENDING。**
| 26 | Q3 schema_version bump 实施 | DONE（已 bump，见 §14 E27） |
| 27 | Q3 3 个待评估 property 裁定 | PARTIAL——2 保持原状 / 1 待 §6.5 |
| 28 | observed_packet_position allowed_kinds 评估 | PENDING（依赖 §6.5） |
| 29 | Hub Contract Errata（`fused_canonical_spec.md` 5-kind 陈旧） | 独立 backlog（`docs/实施/待办与勘误/中枢契约勘误待办.md`，非 D9 范围） |
| 30 | Hub 层流程：Registry/Schema 变更后必须跑测试 | 独立 backlog（见 `实施/待办与勘误/中枢契约勘误待办.md` §4） |

**关闭清单（三类）**：

**A. 本设计范围内待解**：

| # | 项 | 状态 |
|---|---|---|
| §6.5 | observed_packet_position 全部（含 allowed_kinds 评估 #28） | BLOCKED（等 M3 外部输入） |
| §6.6-C1.x | Packet role class 枚举（#22） | PENDING（依赖 Metadata Recon） |

**B. 独立议题（已立项）**：

| 议题 | 状态 | 文档 |
|---|---|---|
| Q3 kind 扩展 | COMMITTED | `docs/实施/立项提案/D9第三问类型扩展立项.md` |
| Aggregate Carrier | RESOLVED | `docs/实施/立项提案/D9聚合载体立项.md` |
| Normalizer implementation | Backlog | `docs/实施/路线与里程碑/归一化实现待办（已结案）.md` |
| Hub Contract Errata | Backlog | `docs/实施/待办与勘误/中枢契约勘误待办.md` |

**C. 已关闭**：

| 项 | 状态 |
|---|---|
| GAP-R1 Hub Aggregate Carrier 承载位 | RESOLVED（选 S2） |
| GAP-R2 Registry rate 条目 | RESOLVED（`observed_presence_rate` 已落盘） |
| GAP-R4 population_scope 归属 | RESOLVED（归 Assertion.value） |
| GAP-R5 / D9-ISSUE-COMPLETENESS-P0 | FIXED（§14 E7） |
| R2 value_range P0 | FIXED（同 E7） |
| D9-GAP-PAIR-IDENTITY | RESOLVED（方案 (b)，不触发 Schema Gap Review） |
| Pre15 流程缺陷 | 已登记 §14 E29 + `工具/验收与规范/agent长期工作约束.md` 第八章 |
### E37. Traffic Lane A Rule Set Final Frozen

**状态**：Lane A = **PROVENANCE-ONLY**（阶段 4，2026-10-04）

**性质**：Lane A 规则集冻结记录。**不改变 D9 §0–§13 任何语义**；
本条为 §14 errata 日志的追加条目。

**冻结对象**：

- `docs/设计/各源设计/流量源/traffic源规则集设计.md` — Final Frozen
  （带 1 条 PARTIAL 判据，见其 §10.1 判据 4）
- `docs/设计/各源设计/流量源/traffic源溯源接口.md` — Final Frozen

**22 候选的 emission_class 分布**：

| category | 数量 | 候选 |
|---|---|---|
| `PRIMITIVE` | 7 | C01 C02 C03 C04 C05 C06 C17 |
| `HUB_EMITTING` | 7 | C07 C08 C09 C10 C11 C20 + （见 §3.2） |
| `NO_TARGET_PENDING_EXTRACTION` | 4 | C14 C15 C18 C19 |
| `OUT_OF_SCOPE` | 3 | C12 C13 C22 |
| `CROSS_CUTTING` | 1 | C21 |

**核心裁定摘要**（完整记录见 `docs/工具/决策记录/已决事项.md` D14–D19）：

- **Lane A 不产生任何 Hub Candidate / Claim / Fact。** observation
  是 Lane A 侧记录，Hub 侧零改动（Invariant 24–28）。
- **不触发 Schema Version Upgrade。** 判据为
  `fused_canonical_spec.md` L1292（是否发生 Storage Schema
  Contract 语义变化）+ L1280 范围清单。本设计不新增任何 Hub domain
  值、不新增任何第一部分字段（D14 / D16 / D17）。
- **G6 移出 Lane A 对齐范围**（D18）。`PairContext` 的输入类型是
  canonical `fact_key`，无 message / observation / capture 字段；
  把 Message 送入该机制即本文件 §4.8 所禁。改 `PairContext` 属
  Hub Contract 范围。
- **G5 / G7 = `NO_TARGET_PENDING_EXTRACTION`**。其语义在现有 Hub
  语料中无可对齐的既有 fact，而能承载的 property
  （`observed_temporal_relation` / `observed_packet_position`）是
  D9 §6 的 population-level 词表，Lane A 不可用。
- **`observed_*` 与 Provenance-Only 无张力**（D19）。5 个
  observed_* property 全部是 §6 measurement 词表，Lane A 依 §1.2
  本就不经 §6.3 / §6.4。

**未决项**（不阻塞本冻结）：

- §9 #18 CSeq 覆盖路径甲/乙的具体实现选择
- §9 #20 G5 / G7 的上游 extraction coverage 缺口
- §9 #21 subject canonical ID 未解前 G4 的 target 无法唯一选定
  （Hub 现有数据中 `authorization` / `Authorization` 并存）

**与 §8 的关系**：§8 扩展仍为独立议题，本批次未触碰。Lane A 对
§8 的 payload 要求见规则集 §6.2 M1–M6。

**D9 §0–§13 未被本条目修改。**

### E38. Traffic Lane A 实现完成

**状态**：Lane A 实现 = **Implemented**（2026-10-04）

**性质**：实现完成记录。**不改变 D9 §0–§13 任何语义**；
本条为 §14 errata 日志的追加条目。

**实现产出**

| 项 | 数量 |
|---|---|
| `core/lane_a/` 模块 | 11（pcap / g1 / g2 / g4 / targets / observation / writer / reader / schema / attachment / `__init__`） |
| `tests/lane_a/` 测试 | 85 项，全部构造数据 + `tmp_path` |
| `scripts/attach_lane_a_provenance.py` | 独立入口（**未改** `build_hub.py`） |
| `derived/lane_a/` | 500 unit，25000 observation |
| `derived/lane_a/provenance/` | 11000 attachment，覆盖 3 条 distinct Hub fact |

**四个阶段**

| 阶段 | 内容 | 结果 |
|---|---|---|
| I | 只读探针，G1 重建器 | 500/500 与 udp 侧 `client.log` 一致 |
| II | `derived/lane_a/` 落盘 + reader + schema | 5000 条 G1 observation |
| III | G2 / G3 / G4 / G8 + target 对齐 | 25000 条；11000 条带 target |
| — | Provenance Attachment（§5.4） | 11000 条；`derived/hub/` 零变化 |

**每步复验的核心不变量**

- `derived/hub/` 13 文件**逐字节不变**
- `core/` 既有 105 个 `.py` 源码**零改动**（只新增 `core/lane_a/`）
- `kb/` aggregate `sha256:bcc1bd3f…`（6061 files）不变
- `（已移除）rtsp/` NO DIFF
- 全量 pytest **0 failed / 0 errors**

**对本批次前序判定的修正（3 处显式记录）**

1. **「§9 #21 实现期硬阻塞 G4」是过强表述**。§10.1 甲方案定义的是
   「target 集合已定、未定唯一选择规则」，加 §4.4 的 `NEEDS_REVIEW`
   token（含义：「存在无法由 deterministic rule 消解的冲突」）——
   实际后果是 **G4 输出质量降级**，不是实现阻塞。
2. **`provenance_interface.md` §5.5 与 `implementation_proposal.md`
   §3.2 曾立场相反**，已由前者文末 **ERRATA-1** 正式勘误。
   关键点：§5.5 声称 validator invariant 保证「将来不可达」，但该
   invariant 只遍历 `fact.claims`，而它担心的场景是 Evidence 被写到
   claim **外** —— 那种情况下它根本不会触发。
3. **§2.4「恰好一个 target」与 §4.11 F/G 曾冲突**，已由
   `provenance_interface.md` **§3.5** 解出：对齐单元精确到
   **(group, header)** 级 —— 有 Hub 对应 fact 的挂 target + 三值
   relation，无对应的落 `no_target` + null。**§2.4 与 §3.4 原文未改写。**

**语料事实补充（实测）**

- Hub 现有 7 条 `header` fact，其中 `authorization` **分裂成 3 条**
  fact_key（大写 1 条 + 小写 2 条，后者 property 各异），即 §9 #21 的实体
- traffic 侧 12 种 header 里**没有** `Authorization`，
  故该歧义在本语料**不触发**（实测 `ambiguous_counts` 全 0）

**§9 剩余未决项的状态变化**

| # | 项 | 变化 |
|---|---|---|
| 18 | CSeq 覆盖路径甲/乙 | 实现期裁定 **甲**（直接从已重建 Message 的 header 块取 CSeq）；排除乙的理由：`rtsp.csv` **无 CSeq 列** |
| 20 | G5 / G7 extraction coverage | **仍未决**（Hub Contract 侧）。G5 / G7 未实现，其 observation 记 `relation = no_target` |
| 21 | subject canonical | **未解但已不阻塞**。实现按 §3.5 处理；歧义路径由单元测试覆盖 |

**与 §8 的关系**：§8 扩展仍为独立议题，本条目未触碰。

**D9 §0–§13 未被本条目修改。**