# local/traffic_lane_a_rule_set_design.md — Traffic Lane A Rule Set 设计

> 状态：**Final Frozen**（批次 4，2026-10-04；带 1 条 PARTIAL 判据，见 §10.1 判据 4）
> 上游：`local/traffic_d9_design.md`（Final Frozen）
>       `local/traffic_corpus_capability_profile.md`（ACTIVE）
>       `local/traffic_candidateization_pre_design.md`（ACTIVE）
> 本文件为 Lane A Rule Set 设计真源。
> 本文件为 standalone 设计真源，不依赖任何 superseded draft。

---

## 0. 范围

### 0.1 本设计要解决什么

定义 **Lane A — Structural Traffic Candidates** 的规则集：从 traffic corpus 抽取 instance-level structural 事实，投影到 Hub fact_key。

### 0.2 不解决什么

- 不定义 Lane B（aggregate observational）
- 不修改 D9 §0–§13
- 不定义 §8 扩展实现（Q5，独立议题）
- 不定义 CSeq 覆盖路径实现选择（Capability Profile §11.3，独立议题）
- 不做 G1–G8 的具体规则填实（本文件只冻结框架）

### 0.3 前置已冻结

| 项 | 状态 |
|---|---|
| Q1–Q4 / Q6 | 已裁定（Pre-Design §4） |
| Q5（§8 扩展） | 独立议题 |
| Q7（依赖矩阵） | 已完成（Lane A recon） |
| Pre-Design §4.7 / §4.8 / §4.9 | 源权威性收口后的新前置（见 §7） |
| 源权威分层 | Capability Profile §11.2 |
| 有效 unit 口径（500 effective + 1000 nominal） | Capability Profile §11.4 |
| role class 收缩（保留 5 / 剔除 3 / 待定 3） | Capability Profile §13 |
| Corpus Constants 与 ratio 禁止 | Capability Profile §12 |
| G1 semantic role | DECIDED — PRIMITIVE ONLY |
| G1 Message boundary rule | RESOLVED（§4.5） |
| G1 Request/Response classifier | DECIDED — RTSP start-line grammar |

---

## 1. 硬边界

### 1.1 继承 D9 硬边界

- 不得依赖 cross-capture independence
- 不得假装 clustering 判据可导出
- 不得升级 corpus repetition 为 semantic diversity
- 不对 corpus 常量做 ratio / aggregate

### 1.2 Lane A 专属硬边界

1. **Lane A 是 instance-level structural assertion**——不经 §6.3 / §6.4 measurement contract
2. **Lane A 不得输出 population-level aggregate**
3. **tcp 侧 client.log 完全排除**——不是本 corpus 源
4. **不使用 retransmission 相关信号**——语料不可观察

---

## 2. 源权威与依赖

### 2.1 源权威分层

| 层 | 源 | 覆盖 | 用途 |
|---|---|---|---|
| Ground truth | `capture.pcapng` | 100% | 原始，需解析 |
| Structured | `rtsp.csv` / `packets.ndjson` / `rtp.csv` | 100% | 无 CSeq 列 |
| Supplemental | udp 侧 `client.log` | 500 units | 含 CSeq / RTP-Info |
| Excluded | tcp 侧 `client.log` | — | 不属于本 corpus |

### 2.2 字段级主源 / 兜底源

**待逐字段填实**。设计原则：

- 每条规则显式声明 primary source + fallback source
- 不设全局单一主源
- fallback 亦不可确认时走 §4.E（Observability / Emission Policy）

### 2.3 有效 unit 口径

- Coverage 分母 = **500 effective**
- Provenance 记录 = **1000 nominal**
- **500 effective 是 corpus dedup / coverage reporting unit，不是 500 independent support units**
- Coverage **不得**进入 Fact identity / Claim authority / voting weight / independence count
- 见 Capability Profile §11.4

---

## 3. Candidate 类型清单

### 3.1 分组

**Lane A v1 = Provenance-Only Structural Observation Lane**

所有组共同遵循 §4.8 Provenance-Only Invariant。

| 组 | 内容 | 主依赖 |
|---|---|---|
| **G1 — Message Reconstruction / Classification**<br>Emission Class: **PRIMITIVE ONLY** | Message identity / Request-Response 分类 | pcap / structured path（production）；udp client.log（validation oracle） |
| **G2 — CSeq Pairing**<br>Emission Class: **EVIDENCE EMITTING** | request ↔ response correspondence | CSeq |
| **G3 — Request Line / Method / Status / URI**<br>Emission Class: **PRIMITIVE ONLY** | method 值 / status 值 / request URI | client.log / rtsp.csv |
| **G4 — Header / Body Presence / Value**<br>Emission Class: **EVIDENCE EMITTING** | header 存在性 / 值 / body（含 SDP） | client.log / pcap |
| **G5 — Message Ordering**<br>Emission Class: **NO_TARGET_PENDING_EXTRACTION** | Message 间 order / sequence relation | client.log / pcap 记录序号 |
| **G6 — Transaction Structure**<br>Emission Class: **OUT_OF_SCOPE** | 在 G2 pairing 结果上构造 transaction semantics | G2 下游 |
| **G7 — Packet-Role Observations**<br>Emission Class: **NO_TARGET_PENDING_EXTRACTION** | 保留 5 类 role class | pcap + sidecar |
| **G8 — Protocol Context（Session / Transport Connection）**<br>Emission Class: **EVIDENCE EMITTING（弱）** | Session / Transport Connection 观察 | pcap + sidecar |

### 3.2 22 候选 mapping 表

（agent 从 recon 输出机械填入）

| candidate_id | candidate_name | primary_group | category | 依赖轴 | fact kind | emission status |
|---|---|---|---|---|---|---|
| C01 | Request message existence | G1 | `PRIMITIVE` | det=YES / xcap=NO / retrans=NO | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C02 | Response message existence | G1 | `PRIMITIVE` | det=YES / xcap=NO / retrans=NO | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C03 | Request/response classification | G1 | `PRIMITIVE` | det=YES / xcap=NO / retrans=NO | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C04 | Method value observation | G3 | `PRIMITIVE` | det=YES / xcap=NO / retrans=NO | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C05 | Status value observation | G3 | `PRIMITIVE` | det=YES / xcap=NO / retrans=NO | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C06 | Request URI observation | G3 | `PRIMITIVE` | det=YES / xcap=NO / retrans=NO | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C07 | Header presence (by name) | G4 | `HUB_EMITTING` | det=YES / xcap=NO / retrans=NO | 待审 | EMIT（待逐 rule 确认） |
| C08 | Header value observation | G4 | `HUB_EMITTING` | det=PARTIAL / xcap=NO / retrans=NO | 待审 | EMIT（待逐 rule 确认） |
| C09 | Body presence / SDP observation | G4 | `HUB_EMITTING` | det=YES / xcap=NO / retrans=NO | 待审 | EMIT（待逐 rule 确认） |
| C10 | CSeq value observation | G2 | `HUB_EMITTING` | det=YES / xcap=NO / retrans=NO | 待审 | EMIT（待逐 rule 确认） |
| C11 | Request-response pairing | G2 | `HUB_EMITTING` | det=PARTIAL / xcap=NO / retrans=NO | 待审 | EMIT（待逐 rule 确认） |
| C12 | Transaction existence | G6 | `OUT_OF_SCOPE` | det=PARTIAL | 不适用（OUT_OF_SCOPE 不 emit） | OUT_OF_SCOPE（移出 Lane A 对齐范围，D18） |
| C13 | Partial transaction (request, no respo | G6 | `OUT_OF_SCOPE` | det=YES | 不适用（OUT_OF_SCOPE 不 emit） | OUT_OF_SCOPE（移出 Lane A 对齐范围，D18） |
| C14 | Message ordering (relative) | G5 | `NO_TARGET_PENDING_EXTRACTION` | det=YES | 不适用（无 target，relation=no_target） | NO_TARGET_PENDING_EXTRACTION（§4.12） |
| C15 | Message phase (pre-play / post-play) | G5 | `NO_TARGET_PENDING_EXTRACTION` | det=YES | 不适用（无 target，relation=no_target） | NO_TARGET_PENDING_EXTRACTION（§4.12） |
| C16 | Protocol Session grouping | G8 | `HUB_EMITTING` | det=YES but DEGENERATE / xcap=RISK / retrans=NO | 待审 | EMIT（待逐 rule 确认） |
| C17 | Packet to Message contribution | G1 | `PRIMITIVE` | det=PARTIAL / xcap=NO / retrans=YES | 不适用（PRIMITIVE 不填 Fact Key） | PRIMITIVE（不 emit 为 Hub candidate） |
| C18 | Packet role class: origin direction | G7 | `NO_TARGET_PENDING_EXTRACTION` | det=YES | 不适用（无 target，relation=no_target） | NO_TARGET_PENDING_EXTRACTION（§4.12） |
| C19 | Packet role class: protocol function | G7 | `NO_TARGET_PENDING_EXTRACTION` | det=PARTIAL | 不适用（无 target，relation=no_target） | NO_TARGET_PENDING_EXTRACTION（§4.12） |
| C20 | Transport Connection observation | G8 | `HUB_EMITTING` | det=PARTIAL / xcap=NO / retrans=PARTIAL | 待审 | EMIT（待逐 rule 确认） |
| C21 | Message partial / truncation flag | G1 | `CROSS_CUTTING` | det=YES / xcap=NO / retrans=NO | 不适用（CROSS_CUTTING 不填 A–J） | CROSS_CUTTING（归 §4.E Observability / Emission Policy） |
| C22 | Ambiguous pairing flag | G6 | `OUT_OF_SCOPE` | det=YES | 不适用（OUT_OF_SCOPE 不 emit） | OUT_OF_SCOPE（移出 Lane A 对齐范围，D18） |

**`category` 列即 emission class，取值**：

- `HUB_EMITTING` —— 正常 Hub candidate
- `PRIMITIVE` —— reconstruction primitive，**不 emit 为 Hub candidate**（含 G1 全部 C01 / C02 / C03，以及 C17 Packet→Message contribution）
- `CROSS_CUTTING` —— 横切规则（如 C21 Message partial/truncation），归 §4.E

**核验**：

- 22/22 assigned to exactly one primary group
- duplicate primary assignment = 0
- unassigned = 0
- HUB_EMITTING + PRIMITIVE + CROSS_CUTTING 三类合计 = 22

**fact kind 列说明**：本列全部为「待审」。§5.1 明确 22 候选逐条 kind
映射属于本设计内逐组讨论议题（见 §9 #4），本步不预判。

**primary_group 列说明**：22/22 全部有 primary group，**无 `—`**。

C17 / C21 归 **G1**：

- C17 reconstruction primitive 是 Message reconstruction 的产物，
  G1 是其逻辑上游
- C21 cross-cutting observability 从 reconstruction 派生，源头在 G1

**不新开 CROSS_CUTTING_GROUP**——`category` 列已标识二者非
HUB_EMITTING（`PRIMITIVE` / `CROSS_CUTTING`），primary group 只表达
逻辑上游，不表达 emission 资格。§4.4 已声明 C21「不独立成组」。

### 3.3 组间依赖

```
Raw Traffic
  ↓
G1 Message Reconstruction / Classification
  [PRIMITIVE — 不 emit Hub Fact]
  ↓
Message semantic object
  ↓
┌──────────────────────────────┐
│ G3 Method / Status           │
│ G4 Header Presence / Value   │
│ G5 Message Ordering          │
│ G2 CSeq Pairing              │
└──────────────────────────────┘
              ↓
             G6
      Transaction Structure

G7 Packet-Role Observations
  主要来自 Packet / Message correspondence
  可消费 G1 reconstruction，但不必完全依赖 G1
```

讨论顺序（非编号）：G1 → G3 → G4 → G5 → G8 → G2 → G6 → G7。

理由：

- G1 建立 Message object / classification
- G3 / G4 是最直接的 Message-local facts
- G5 基于 reconstruction sequence
- G8 基于 reconstruction context
- G2 引入跨 Message pairing
- G6 建立在 G2 pairing 上
- G7 有独立 role-class dependency，最后处理最安全

### 3.4 G1 Emission Boundary

**G1 = reconstruction-only group。**

C01 / C02 / C03 全部 **PRIMITIVE**，**不直接 emit Hub Fact**。

**理由**：

- Message 是 instance-level semantic object
- `fact_key: subject = message.<instance-id>` 会让 observation instance
  进入 canonical knowledge identity
- 违反 Hub「按协议目标信息组织，不按 observation instance 组织」原则

**G1 输出**（内部 reconstruction state，非 Hub Fact）：

- Message object
- Message boundary
- Message class：request / response / unknown
- message-local provenance
- ordering anchor

**下游消费者**：G3 / G4 / G5 / G2 / G6

**Hub emission 从下游规则开始。**

### 3.5 状态口径

```
Lane A v1 整体状态：PROVENANCE-ONLY
─────────────────────────────────────────
G1 Message Reconstruction / Classification：FROZEN CANDIDATE（PRIMITIVE）
G3 Method / Status / URI：FROZEN CANDIDATE（PRIMITIVE）
G2 CSeq Pairing：FROZEN CANDIDATE（EVIDENCE EMITTING）
G4 Header / Body Presence / Value：FROZEN CANDIDATE（EVIDENCE EMITTING）
G8 Protocol Context：FROZEN CANDIDATE（EVIDENCE EMITTING，本语料弱）
G5 Message Ordering：NO_TARGET_PENDING_EXTRACTION（上游 extraction 缺口）
G7 Packet-Role：NO_TARGET_PENDING_EXTRACTION（上游 extraction 缺口）
G6 Transaction Structure：OUT_OF_SCOPE（D18，移出 Lane A 对齐范围）
```

**所有组的最终输出形态**：

- Primitive（reconstruction 中间态）
- StructuralObservation + Provenance（最终 observation）

**没有任何组 emit Hub Candidate / Claim / Fact。**

G1 Known Limitations 见 §4.1 P8；不声称对 RTSP 协议泛化。

G3 裁定理由见 §4.7；C05 / C06 的登记见 §4.7。

role class 待定 3 项 → Metadata Recon。

---

## 4. Lane A Rule Contracts

Lane A 有两种 Contract，按 emission class 区分：

### 4.1 Reconstruction Primitive Contract（P1–P7）

适用于 category = `PRIMITIVE` 的 structural item。

| 字段 | 说明 |
|---|---|
| **P1. Primitive Question** | 要恢复 / 分类什么对象？ |
| **P2. Input Source Binding** | primary observation source + validation / fallback source |
| **P3. Deterministic Reconstruction Rule** | 什么可观察条件足以形成 primitive？ |
| **P4. Observability / Conflict Policy** | partial / conflict / unknown 怎么处理？ |
| **P5. Primitive Output** | 产生什么内部 semantic object / attribute？ |
| **P6. Provenance** | primitive 如何回溯 raw observation？ |
| **P7. Downstream Consumers** | 哪些 HUB_EMITTING rules 消费它？ |
| **P8. Known Limitations** | 本契约在什么范围内已验证、在什么范围内**未**验证？ |

**PRIMITIVE 不填写 Fact Key Projection / Assertion Projection。**

### 4.2 Hub-Emitting Rule Contract（A–J）

适用于 category = `HUB_EMITTING` 的 structural item。

| 字段 | 说明 |
|---|---|
| **A. Structural Question** | 这条规则抽什么结构事实？ |
| **B. Structural Anchor / Candidate Unit** | 显式声明 rule 的 structural unit（见 §4.3） |
| **C. Source Binding** | primary + fallback + source authority reason |
| **D. Extraction Predicate** | deterministic observable conditions |
| **E. Observability / Emission Policy** | required observable fields / partial / conflict / emit / no-emit / review semantics |
| **F. Fact Key Projection** | protocol / version / kind / actor / subject canonicalization / property / condition |
| **G. Assertion Projection** | value / type_hint / modality_hint |
| **H. Evidence / Provenance Projection** | source / locator / nominal unit / effective-unit relationship where applicable |
| **I. Coverage / QA** | denominator = 500 effective；not a semantic vote / independence count |
| **J. Handoff / Lineage** | downstream carrier requirement / lineage outcome |

**与 D9 §6.1 A–I 的差异**：

| D9 §6.1 | Lane A |
|---|---|
| Measurement Unit | Structural Anchor / Candidate Unit |
| Semantic Applicability Scope | Extraction Predicate（+ condition projection §5.3） |
| Eligible Population | 不适用（population-level concept） |
| Aggregation | 不适用 |
| Unknown / Insufficient（population-level） | 不适用；**instance observability semantics 由 §4.E 承担** |

**核心差异**：Lane A 是 instance-level，无 population eligibility / aggregation。

**但保留**：instance observability / partial / unknown / source conflict / no-emit / review behavior（由 §4.E 承担）。

### 4.3 Structural Anchor 泛化

**每条 rule 必须显式声明自己的 structural unit。**

**Message 是 Lane A 的主要 anchor unit，但不是所有规则唯一合法的 semantic unit。**

v1 允许引用的 structural unit（来自已冻结 taxonomy / committed extension）：

- Message
- Message Pair / Relation
- Transaction
- Packet
- Packet Role Pair
- Protocol Session
- Transport Connection

**若现有 Candidate DTO 只能承载 Message**：

这是 Candidate carrier / §8 interface gap，**不能通过把 Transaction / Pair 强行叫 Message 来解决**。

### 4.4 E. Observability / Emission Policy

**§4.E 不是重新引入 Lane B 的 population-level 概念**（eligible population / unknown outcome count / insufficient observation aggregate）。

**只回答**：

> 对某一个 structural instance，如果证据不足，当前 rule 应怎么办？

**至少允许表达**：

| Token | 含义 |
|---|---|
| `EMIT` | structural fact 可可靠确定 |
| `NO_EMIT_NOT_OBSERVABLE` | 当前 evidence 不足以支持 assertion |
| `NO_EMIT_NOT_APPLICABLE` | 本 rule 不适用于该 structural unit |
| `NEEDS_REVIEW` | 存在无法由 deterministic rule 消解的冲突 |

**C21 Message partial/truncation 归本 Policy**（cross-cutting observability，不独立成组）。

**CROSS_CUTTING** 规则（如 C21）归 §4.4 语义，不独立成组，不填写 A–J。

**具体 token 与现有 contract 对齐**：

- 若最终 token 与现有 lineage / candidate terminology 冲突，**以现有 contract 为准**
- 本设计语义作为上层要求，**不得反向修改 contract 以迎合 Lane A**

**Lane A emission 独立于 §6 measurement_status**：

- §6 measurement_status = population-level（insufficient_observation / undefined）
- Lane A emission = instance-level（EMIT / NO_EMIT_* / NEEDS_REVIEW）
- 二者**不互相替代**

### 4.5 Message Reconstruction Primitive Contract

适用于 C01 Request existence / C02 Response existence 的底层 reconstruction。

**P1. Primitive Question**

这条 traffic observation 是否构成一个完整的 logical RTSP message transmission occurrence？

**P2. Input Source Binding**

- Production reconstruction source：`capture.pcapng` + `rtsp.csv`（deterministic structured path）
- Validation oracle：udp 侧 `client.log`（显式 application-level boundary）

不采用 primary + fallback 模型——production 与 validation 职责不同。

**P3. Deterministic Reconstruction Rule**

契约给不变量，不给具体算法。

边界不变量：

- 一条 logical Message 的边界由该 Message 的 transport-layer payload 序列唯一确定
- 分片 / 重组 / 重传 / 交织不产生新 Message（D9 §4.2.1）
- 具体 splitter 算法由实现决定，但必须满足：
  - 对 500 effective units 与 validation oracle 一致
  - 不依赖 cross-capture state
  - 不依赖启发式（仅依赖 grammar + protocol headers）

具体算法在实现阶段冻结。

**P4. Observability / Conflict Policy**

- Boundary conflict（production ≠ validation）：`NEEDS_REVIEW / reconstruction unresolved`；不得自动生成依赖该 Message boundary 的 downstream HUB_EMITTING Candidate
- 不预设 pcap wins——pcap 虽为 ground truth，但 pcap→Message 经过 reconstruction algorithm，冲突可能来自 algorithm
- 不预设 client.log wins——同源生成器，非独立证人
- Partial Message：保留（provenance 优先，D9 §4.8）；标记 partial 状态供 §4.4 消费

**P5. Primitive Output**

内部 reconstruction state（非 Hub Fact）：

- Message object（instance-level）
- Message boundary（frame 序号起止）
- message-local provenance
- ordering anchor（供 G5 使用）

不输出 fact_key / assertion。

**P6. Provenance**

- 回溯到 raw observation：
  - `(unit, capture_frame)`（见 Capability Profile §10）
  - frame 序号本身就是 rtsp.csv / packets.ndjson 已在用的 frame number
- 1000 nominal 保留——provenance 不因 dedup 而丢失

**P7. Downstream Consumers**

- G2 CSeq Pairing
- G3 Method / Status
- G4 Header Presence / Value
- G5 Message Ordering
- G6 Transaction Structure
- G7 Packet-Role Observations（间接）

**P8. Known Limitations**

当前 corpus 下本契约对本语料充分，**不声称对 RTSP 协议泛化**。

1. **一致 ≠ 互证**：pcap 与 client.log 同源生成器——log 是客户端声明，非独立证人
2. **形状覆盖为零**：当前 corpus 全是同一种 5 消息会话（OPTIONS→DESCRIBE→SETUP→PLAY→TEARDOWN，全 200 响应）——其他 method 集 / 非 200 状态 / 跨 TCP 段的报文全未测
3. **tcp 半不是第二证人**：tcp 侧 client.log 与 udp 侧来自同一批 artifact，排除后不构成独立验证
4. **6–9 个丢弃帧仍无标签**：dropped = N−49 = 6/7/8/9 帧的语义（ACK / retransmission / 未解析）——语料内无标注
5. **分段容忍度未测**：跨 TCP 段的 Message 在 corpus 中不存在——splitter 对跨段 Message 的行为未经验证

### 4.6 Request / Response Classification Primitive Contract

适用于 C03 Request/Response classification。

**P1. Primitive Question**

这个 Message 是 request 还是 response？

**P2. Input Source Binding**

- Primary classifier：RTSP start-line grammar
- Validation signal：direction（client→server / server→client）
- 不参与：CSeq（属 G2）

**P3. Deterministic Classification Rule**

RTSP start-line grammar 是唯一 primary deterministic classifier。

- Request：`<METHOD> SP <URI> SP RTSP/1.0`
- Response：`RTSP/1.0 SP <status-code> ...`

direction 作为 consistency signal 而非联合 primary rule。

**P4. Observability / Conflict Policy**

- Consistent：start-line 与 direction 一致 → 正常输出
- Conflict：start-line 与 direction 冲突 → `NEEDS_REVIEW / classification unresolved`；不得生成依赖该 classification 的 downstream HUB_EMITTING Candidate
- 不得 direction 覆盖 start-line grammar
- Unknown：start-line 不匹配任一 grammar → classification = `unknown`

**P5. Primitive Output**

- classification ∈ {`request`, `response`, `unknown`}
- 归入 Message object（不产生独立 Hub Fact）

**P6. Provenance**

- 首行 raw text
- 首行的 source locator（frame / line offset）

**P7. Downstream Consumers**

- G2 CSeq Pairing
- G3 Method / Status
- G4 Header Presence / Value
- G5 Message Ordering
- G6 Transaction Structure

**P8. Known Limitations**

共享 Message Reconstruction Primitive Contract §4.5 P8 的全部 5 条限制。

附加分类特有约束：

- 当前 corpus 所有 response 均为 200；非 200 状态未在 corpus 出现——classifier 对非 200 的行为未经验证

### 4.7 G3 三候选裁定与登记

**裁定**：C04 Method / C05 Status / C06 URI 全部 **PRIMITIVE**——不直接 emit Hub Fact。

**理由**（必须说准确）：

三者都是**单条消息的 attribute**——属 observation instance 层。与 G1 的 C01/C02/C03 同性质。

instance-level attribute **不进入 canonical knowledge identity**。

**理由不是「值恒定」**——那会把语料覆盖陈述误当语义结论。

#### 4.7.1 C05 Status 的登记

当前 corpus status 值集 = `{200}`。这是**corpus 覆盖陈述**，不是语义属性。

**不得**读成「status 不值得进 Hub」——若未来 corpus 有多值 status，C05 仍是 PRIMITIVE——因为它是 instance attribute。

见 Capability Profile §12（Corpus Constants）。

#### 4.7.2 C06 URI 与 C04 的 relation 登记

T4 实测：method → URI 是函数（每个 method 恰好一个 URI）；URI → method 非单射（3 个 URI 中 2 个各被 2 个 method 共用）。

**结论**：URI 能区分 OPTIONS/DESCRIBE 与 PLAY/TEARDOWN，method 单独做不到——这个观察是真的。

**但**：它是 **instance-internal relation**，不构成 C06 独立 emission 价值。

当前 corpus 无法区分：

- protocol-semantic relation
- corpus sampling artifact

登记为本项**待未来 corpus 澄清**，不裁定。

#### 4.7.3 G3 裁定触发一个待决问题

G1 = PRIMITIVE ONLY，G3 = PRIMITIVE ONLY。两者都是 instance-level。

**Lane A 的 HUB_EMITTING 从哪一组开始？** 见阶段 B 的 Emission Boundary 分析。

> **已答（2026-10-03）**：不问。见 §4.8 —— Lane A v1 整体 PROVENANCE-ONLY，**没有任何组 emit Hub Candidate / Claim / Fact**。本小节保留为该问题的提出记录。

### 4.8 Provenance-Only Invariant（核心）

**Traffic Lane A v1 is a provenance-only structural observation lane.**

**No Lane A structural item may directly emit a Hub Candidate, Claim, or Fact.**

**Lane A observations may be deterministically aligned to existing protocol-semantic Facts as non-voting provenance, but must not:**

- **participate in Phase A Resolution**
- **alter canonical assertions**

**Any future traffic-derived Hub-emitting semantics require a separately designed and frozen lane; they are not an exception inside Lane A.**

本节同时封死三个漏洞：

1. observation → protocol fact 的 identity 升级
2. observation → Phase A vote 的 resolution 污染
3. 未来例外 → Lane A 内部重新变成 per-fact 混合

#### 4.8.1 C04 作为决定性反例

现有 Hub 已有事实：

```
RFC:
kind=method
subject=SETUP
property=existence
value=true
```

C04 若投影成相同 fact_key：

```
traffic:
kind=method
subject=SETUP
property=existence
value=true
```

**它们回答的是两个不同问题**：

- RFC：SETUP 是否属于协议定义 / 允许 / 要求的 method 空间？
- Traffic C04：在这个 observation instance 中，是否观察到了一个 SETUP request？

**把二者压成同一个 fact_key，就是在 Candidateization 之前已经发生语义升级：instance observation 错误提升为 protocol proposition。**

Phase A 再精确也救不回来——输入 identity 已经错。

与 Hub 核心设计一致：fact_key 表达「讨论什么」，sources / evidence 才表达证据来自哪里。

**此结论推广到整个 Lane A，不限于 C04。**

#### 4.8.2 Lane A 输出形态

Lane A v1 输出：

```
StructuralObservation + Provenance
```

这些 observation 可以：

1. 被 provenance interface 消费
2. 与已有 protocol Fact 建立 corroborates / contradicts / insufficient 等证据关系
3. **不参与**该 Fact 的 Phase A claim resolution
4. **不改变** canonical assertion

第 3 / 4 条尤其重要——否则只是把「traffic Candidate 污染 Phase A」改成「traffic Evidence 间接污染 Phase A」。

**Lane A v1 不得 emit Evidence DTO**——Hub Storage Model 中 Evidence 不是独立顶层对象；它属于 Claim，Claim 属于 Fact。没有 Fact/Claim 宿主时 Evidence 无处挂载。

挂载机制由 `local/traffic_lane_a_provenance_interface.md` 定义。

#### 4.8.3 Future Lane（严格例外条款）

**不得**在 Lane A 内开 HUB_EMITTING 例外——「RFC/expert_note 未覆盖」不是充分条件。

若未来出现 traffic-derived information，能够满足：

- 不依赖单个 observation identity
- 具有明确 bounded scope / observational semantics
- 确定性映射为 Hub protocol-semantic Fact

则：

**另立独立 Traffic HUB_EMITTING Lane**，完成：

- Fact identity 设计
- Scope 设计
- Claim class 设计
- Resolution participation 设计
- Generalization boundary 设计

并经**独立 Freeze Gate** 后方可进入 Candidateization。

**不得**成为 Lane A 内部的 per-fact 混合状态。

### 4.9 Evidence Emission Rule Contract

**A–J Contract 保留，但重构为 Evidence Emission Rule Contract。**

A–J 字段的语义变化：

| 字段 | 原（Hub-Emitting） | 现（Evidence Emission） |
|---|---|---|
| A. Structural Question | 抽什么结构事实 | **观察到什么 structural fact** |
| B. Structural Anchor | structural unit | 同 |
| C. Source Binding | 同 | 同 |
| D. Extraction Predicate | 同 | 同 |
| E. Observability / Emission Policy | 同 | 同 |
| **F. Fact Key Projection** | **投影到 fact_key** | **→ Alignment Target**：能与哪类 existing protocol Fact 对齐 |
| **G. Assertion Projection** | **assertion value** | **→ Alignment Semantics**：corroborates / contradicts / insufficient 的判定 |
| H. Evidence / Provenance Projection | 同 | 同 |
| I. Coverage / QA | 同 | 同 |
| **J. Handoff / Lineage** | **Hub carrier** | **→ Provenance Attachment**：如何被 provenance interface 消费 |

**不得通过 A–J 重新引入 HUB_EMITTING 语义。**

### 4.10 G3 Method / Status / URI Primitive Contract

> **状态：Frozen Candidate**（G3-C，依 D15 / D19 填实）
> 覆盖 C04 Method value / C05 Status value / C06 Request URI

**P1. Primitive Question**

单条 message 的 request line 上，method / status / URI 各自是什么？

**P2. Input Source Binding**

- Production：`capture.pcapng`（按 magic 判定 classic libpcap）
  + `rtsp.csv`（1000 文件，含 method / status / url 三列）
- Validation oracle：udp 侧 `client.log`（显式首行文本）
- **tcp 侧 `client.log` 排除**（Capability Profile §11.2）

**P3. Deterministic Reconstruction Rule**

- Request：首行 `<METHOD> SP <URI> SP RTSP/<ver>`
- Response：首行 `RTSP/<ver> SP <status-code> [SP reason]`
- grammar 是唯一 primary classifier（承 §4.6 P3）
- CSeq 不参与本契约（属 G2）

**P4. Observability / Conflict Policy**

- start-line 与 direction 一致 → 正常输出
- 冲突 → `NEEDS_REVIEW / classification unresolved`
- 不匹配任一 grammar → classification = `unknown`
- Partial Message 保留并标记（§4.8.2）

**P5. Primitive Output**

Message object + 三条 instance attribute（method / status / URI）。
**不输出 fact_key / assertion。**

**P6. Provenance**

`(unit, capture_frame)` 区间 + 1000 nominal 保留（§4.6 P6）

**P7. Downstream Consumers**

G2 / G4 / G5 / G8 的 observation 记录

**P8. Known Limitations**

继承 §4.5 P8 全部 5 条，另加分类特有约束（承 §4.6 P8）：

- 本语料 status 值集 = `{200}`。非 200 状态未出现，classifier 对
  非 200 的行为未经验证。
- **本语料不构成分类器语义的证据**：method / status / URI 三者值集
  全为常量，按 §4.7.1 的登记，这是 corpus 覆盖陈述不是语义结论。
  若未来语料出现多值，C05 / C06 仍是 PRIMITIVE——因为它们是
  instance attribute，不是值集大小的问题。

### 4.11 G2 / G4 / G8 Evidence Emission Rule Contract

> **状态：Frozen Candidate**（依 D16 / D17 填实）
> 字段为 §4.9 的 A–J 重构版

**A. Structural Question**

- **G2**：这条 message 的 CSeq 与哪条 response 的 CSeq 构成配对？
- **G4**：这条 message 携带了哪些 header，各取值为何；body 是否存在？
- **G8**：这条 message 处于哪个 Session / Transport 上下文？

**B. Structural Anchor**

G2 = Message Pair；G4 = Message；G8 = Message（上下文属性）

**C. Source Binding**

- G2：CSeq 走 §4.10 P2 同源；**CSeq 覆盖路径（甲/乙）未裁**，
  见 §9 #18
- G4：`client.log` / `rtsp.csv`（header 存在性）；`capture.pcapng`
  （header 取值）
- G8：`capture.pcapng`（Transport）；udp 侧 `client.log`（Session）

**D. Extraction Predicate**

- G2：同一 session 内 CSeq 相同的一对 request / response
- G4：首行之后到首个空行之间的 `Name: value` 序列
- G8：SETUP 请求的 Session / Transport header

**E. Observability / Emission Policy**

用 §4.4 的四个 token：`EMIT` / `NO_EMIT_NOT_OBSERVABLE` /
`NO_EMIT_NOT_APPLICABLE` / `NEEDS_REVIEW`。
partial 保留不丢弃（§4.8.2）。

**F. Alignment Target**

> **2026-10-04 细化（依 `provenance_interface.md` §3.5）**：
> 下列「target」是**候选集合**，不是每条 observation 都要挂满。
> 对齐单元精确到 **(group, header)** 级：
>
> | 情形 | relation | target_fact_id |
> |---|---|---|
> | 该 header 在 Hub 有 1 条对应 fact | `insufficient` / `corroborates` / `contradicts` | 非空 |
> | 该 header 在 Hub **无**对应 fact | `no_target` | `null` |
>
> 500 units 实测：`CSeq` / `Session` / `Transport` 各 1 候选；
> `Date` / `User-Agent` / `Accept` / `Range` / `Content-*` / `Public` /
> `RTP-Info` 均 0 候选 → `no_target`。
> 合计 11000 条带 target、14000 条 `no_target`。

- G2：`header` / `CSeq` / `security_condition`（1 条）
- G4：7 条 `header` fact（subject 匹配前须先解 §5.2 canonical 问题）
- G8：`header` / `Session`、`header` / `transport`（2 条，弱）

**G4 的 7 条候选 fact 全清单**（2026-10-04 实测 Hub `derived/fused/`）：

| fact_id | subject | property | 来源 |
|---|---|---|---|
| `f1_7c7ed1518df0c33f` | `CSeq` | `security_condition` | expert_note |
| `f1_7ddfe7b3efd04d57` | `Session` | `security_condition` | expert_note |
| `f1_a80c59c703f01379` | `transport` | `security_condition` | vuln |
| `f1_15263dea8e38af7d` | `URL` | `security_condition` | expert_note |
| `f1_1bd70484d2ec33ef` | `Authorization` | `security_condition` | expert_note |
| `f1_85b9bc2bb8fc7aa3` | `authorization` | `security_condition` | vuln |
| `f1_17f90a490b1beb3a` | `authorization` | `security_consequence` | vuln |

末三条即 **§9 #21** 的实体：同一 subject 大小写分裂成 3 条 fact_key。
按 §2.4「由多条 observation 表达」，发 3 条 observation 各挂一个，
**不选边**、relation 一律 `insufficient`、token 取 `NEEDS_REVIEW`。

**本语料中该歧义不触发**：traffic 侧 12 种 header 里**没有** `Authorization`，
故 500 units 实测 `ambiguous_counts` 全为 0。歧义路径由单元测试覆盖。

**G. Alignment Semantics**

`CORROBORATION_RELATION_DOMAIN` 四值，见
`traffic_lane_a_provenance_interface.md` §4.1。

本语料下的诚实预期：
- G2 → 大概率 `insufficient`（无法观察 replay 攻击）
- G4 → `corroborates` 为主；`authorization` / `Authorization` 两条
  subject 大小写冲突，**在 §5.2 未解前无法唯一选定 target**
- G8 → 两条 target 在本语料均退化（Session 是常量），大概率
  `insufficient`

**H. Evidence / Provenance Projection**

- 1000 nominal 保留
- 500 effective 用于 coverage 分母
- observation **不落 Hub**（D17）

**I. Coverage / QA**

分母 = 500 effective。coverage **不是**语义投票、不进 independence 计数。

**J. Provenance Attachment**

Lane A 侧独立记录；Hub 侧零改动（D17）。
读出口与格式校验留 Step 5 立项。

### 4.12 G5 / G7 无 target 的处理

> **状态：Frozen Candidate**（依 D18 及批次 1 阶段 D 的缺口定位）

**G5 / G7 的 emission class = `NO_TARGET_PENDING_EXTRACTION`。**

含义：这两组的 observation **照常产生**，但 `relation = no_target`，
且不进入任何 Hub 侧对齐。

理由：它们的语义（message 间的顺序关系、packet 的角色）在本 Hub
语料里**没有可对齐的既有 fact**，而能承载这两种关系的 property
（`observed_temporal_relation` / `observed_packet_position`）是
D9 §6 的 population-level 词表，Lane A 不可用（D19）。

**上游议题（非 Lane A 可解）**：
- G5：RFC 有顺序语义，extractor 侧无对应词汇
- G7：RFC 抽取路径里 role 词汇基本不存在
- 二者共同点：extraction coverage 缺口，修复属 Hub Contract 侧

**解除条件**：`derived/fused/facts/` 中出现承载该语义的事实，
或 Hub 侧提供 instance-level property。二者均非 Lane A 内部可解。

### 4.13 C17 Packet→Message contribution Primitive Contract

> **状态：Frozen Candidate**（补齐 §10 判据 2 的遗漏）
> 覆盖 C17 — category = `PRIMITIVE`

**P1. Primitive Question**

这条 packet observation 是否对某条 Message 的形成有贡献？

**P2. Input Source Binding**

- Production：`capture.pcapng`（frame ordinal 已知，见 Capability Profile §10）
- 无 validation oracle：client.log 不记录 packet→message 贡献关系

**P3. Deterministic Reconstruction Rule**

一个 frame 归属于某条 Message，当且仅当该 frame 的 payload 字节落在
该 Message 的 reassembled 区间内。

**P4. Observability / Conflict Policy**

- 归属唯一确定 → 正常输出
- 一 frame 落进两个 Message 区间（D9 §4.7 允许 M:N）→ 输出贡献集，
  不二选一
- 不可判定 → `NEEDS_REVIEW`
- **retransmission 不参与判定**（§1.2 硬边界 4：本语料不可观察）

**P5. Primitive Output**

`(frame_ordinal → message_anchor)` 的贡献集。**不输出 fact_key / assertion。**

**P6. Provenance**

`(unit, capture_frame)` + 1000 nominal 保留

**P7. Downstream Consumers**

G1 的 Message boundary（§4.5 P3）、G5 的 ordering anchor（§4.12）

**P8. Known Limitations**

- 承 §4.5 P8 第 4 条：本语料 6–9 个丢弃帧**无标签**，因此它们不落入
  任何 Message 的贡献集。这是构造性事实，不是抽取失败。
- 承 §4.5 P8 第 5 条：跨 TCP 段的 Message 在本语料不存在，跨段归属
  行为未经验验。

---

## 5. Fact Key 投影规则

### 5.1 kind 使用

复用现有 6 kind（method / header / constraint / state / transition / packet_role_pair）。

**待审**：22 候选逐条映射到哪个 kind。

### 5.2 Subject canonical authority（P1-1）

**唯一规则**：

> **Lane A fact_key.subject 必须是 `subject_registry` canonicalization 后的 canonical subject ID。**

流程：

```
raw observed token
  ↓
alias_registry / subject_registry
  ↓
canonical subject ID
  ↓
fact_key.subject
```

**禁止** Lane A 自己：

- `lower()`
- 加前缀 / 去前缀
- 点号拼接
- 裸名 fallback
- `replace("_","-")`

**即使当前 canonical 结果确实是 `method.SETUP` 或 `header.content-length`**，
也不得由 Lane A 重新实现格式化。

**Raw spelling**（`SETUP` / `Session` / `Content-Length`）：

保留在 Evidence / extraction provenance，**不作为 fact identity**。

**理由**：vuln fact split 教训——真正问题不是「点号好还是裸名好」，
而是**同一个 semantic subject 存在两个 local formatting rules**。
Lane A 应冻结的是 **Single Canonical Subject Authority = subject_registry**。

### 5.3 condition projection（P0-3）

**Lane A 不因 instance-level 自动使用 always。**

Hub Schema 已明确：

- `condition={"type":"always"}` = 已知无条件成立
- `condition={"type":"unknown"}` = 适用条件未知
- **没抽到 condition 不得自动写 always**

**Lane A 的 condition 来源只能是**：

经 rule 明确识别、且属于 protocol-semantic identity 的 applicability semantics。

允许：

- `method = SETUP`
- `direction = request`
- `state = Ready`

**禁止进入 condition**：

- `capture_id`
- `nominal_unit_id` / `effective_unit_id`
- `CSeq` concrete value
- `timestamp`
- `frame number`
- `source file`
- `collection artifact`

这些属于 provenance / scope。

Observation-instance context 只进入 Evidence / provenance，**不得污染 canonical fact_key**。

### 5.4 Fact Identity Guard

**任何 Lane A rule 在 projection 前必须区分**：

- **Protocol-semantic identity** → 只有前者能进入 `protocol / version / kind / actor / subject / property / condition`
- **Observation-instance identity** → 后者只能进入 `scope / Evidence / locator / lineage / audit`

这条挡住：

- `CSeq=4` 进入 fact_key
- `frame=22` 进入 fact_key
- `capture=17` 进入 fact_key

---

## 6. Lane A 与 §8 接口

### 6.1 Q5 裁定：§8 需扩展

Lane A 是 instance-level structural fact；§8 是 population-level Claim。语义不匹配。

**§8 需 post-freeze amendment**——独立议题。

### 6.2 最小需求 M1–M6

**本文件冻结**：Lane A 需要向下游交付什么 semantic payload。

**本文件不冻结**：§8 最终怎么修改 schema / class / algorithm。

| ID | canonical requirement summary | source |
|---|---|---|
| **M1** | A structural-fact result kind that can exist WITHOUT a measurement aggregate, distinct from both Traffic Claim and raw observation. **→ 本设计以 StructuralObservation 满足；它不落 Hub（D17）** | Stage C-Pre §8 接口 |
| **M2** | An explicit statement of whether a structural fact may be emitted when §8.2's two conditions are NOT met, or must be held upstream. **→ held upstream：Lane A 永不 emit Hub 对象（§4.8）** | 同上 |
| **M3** | A declared relationship between structural facts and fact_key: §8.3 says every Traffic Claim projects to exactly one fact_key; M1 needs the analogous rule or an explicit exemption. **→ 显式豁免：StructuralObservation 无 fact_key（D15）** | 同上 |
| **M4** | A rule for the case where a structural fact exists but every aggregate computed from it would be degenerate. **→ 由 corpus 常量算出的任何比率按构造就是 0 或 1——不得做 ratio** | 同上 |
| **M5** | Whether a structural fact derived from a PARTIAL observation may be emitted at all, given §4.8 says partial never relaxes identity. **→ 允许观察、标注 partial、不放宽 identity（§4.8.2）** | 同上 |
| **M6** | Naming of the carrier. §9 Hub Boundary is where fact_key is defined; M1 cannot be closed before that, so §8 extension and §9 must be sequenced. **→ §9 对 Lane A 不适用（无 fact_key）；§8 扩展仍独立待做** | 同上 |

**M1–M6 全文见**：`local/backup/step_traffic_lane_a_pre/section8_interface.txt`

---

## 7. Lane A / Lane B 边界

| 维度 | Lane A | Lane B |
|---|---|---|
| 语义层 | instance-level structural | population-level aggregate |
| 经 §6.3/§6.4 | 否 | 是 |
| 依赖 independence | 否 | 是 |
| **规则设计前置** | **G1–G6 READY**；G7 PARTIAL BLOCK；G8 READY | blocking precondition §4.1/§4.3/§4.4 |
| **Lane A 全局前置** | §4.7 / §4.8 / §4.9 作为**跨组约束**，不阻塞 G1–G6 具体规则设计 | — |

---

## 8. Invariants

1. Lane A 是 instance-level structural assertion
2. 不经 §6.3 / §6.4
3. 不依赖 cross-capture independence
4. tcp 侧 client.log 排除
5. 不使用 retransmission 信号
6. Coverage 分母 = 500 effective
7. Provenance 保留 1000 nominal
8. 500 effective ≠ 500 independent support units
9. 不对 corpus 常量做 ratio
10. 不修改 D9 §0–§13
11. 不假装 clustering 判据可导出
12. subject 必须来自 subject_registry canonical ID
13. condition 不因 instance-level 默认 always
14. protocol-semantic identity 与 observation-instance identity 严格分离
15. Lane A emission 独立于 §6 measurement_status
16. structural anchor 显式声明，Message 是主要 anchor 但非唯一
17. reconstruction primitive 与 Hub-emitting candidate 严格分离
18. Fact Key 只保留区分 protocol semantic question 所必需的最小 identity dimensions（**Identity Minimality**）。禁止同一语义在 subject / actor / condition 重复编码。
19. G1 classification metadata 进入 **downstream projection context**，不固定进入 `fact_key.condition`。G3 / G4 等规则逐条决定是否需要 actor / condition。
20. G1 Primitive Contract 对本语料充分，不声称对 RTSP 协议泛化。5 条 Known Limitations 见 §4.5 P8。
21. Message boundary 冲突（production ≠ validation）→ `NEEDS_REVIEW`；不预设 pcap wins 或 client.log wins。
22. G3 三候选（C04/C05/C06）为 PRIMITIVE——单条消息的 attribute 属 observation instance 层。
23. 不得因 corpus 值集恒定就把 instance attribute 判为「不值得进 Hub」——值集恒定是 corpus 覆盖陈述，不是语义结论。
24. Traffic Lane A v1 is provenance-only。任何 Lane A structural item 不得直接 emit Hub Candidate / Claim / Fact。
25. Lane A observation 不得参与 Phase A Resolution，不得改变 canonical assertion。
26. Lane A 不得 emit Evidence DTO——Evidence 在 Hub Storage Model 中不是独立顶层对象。
27. 未来 traffic-derived Hub-emitting 语义必须另立独立 lane，不得作为 Lane A 内部例外。
28. Lane A 的输出形态是 StructuralObservation + Provenance。

---

## 9. Open Questions

| # | 问题 | 处理 |
|---|---|---|
| 1 | CSeq 覆盖路径甲/乙 | 独立议题 |
| 2 | §8 扩展设计 | 独立议题 |
| 3 | role class 待定 3 项 | Metadata Recon（**G7 因此无法升级**） |
| 4 | 22 候选逐条 kind 映射 | **OBSOLETE** — Lane A v1 不产生 fact_key（§4.8） |
| 5 | G1 reconstruction-only vs Hub-emitting 边界 | **RESOLVED** — G1 = PRIMITIVE ONLY（§4.8） |
| 6 | E token 与现有 contract 对齐 | 实现 binding 时 |
| 7 | G1 Message boundary production rule | RESOLVED（§4.5） |
| 8 | G1 Request/Response classifier corpus conformance | RESOLVED（§4.6） |
| 9 | Message Boundary splitter 具体算法 | 实现阶段冻结 |
| 10 | 5 条 Known Limitations 的解除条件 | corpus 扩充后 amend |
| 11 | G3 Primitive Contract（P1–P7） | **RESOLVED**（§4.10，G3-C） |
| 12 | C06 URI 与 C04 method 的 relation 是否含 protocol-semantic 信息 | corpus 扩充后；**不阻塞**（§4.7.2 已登记为 instance-internal relation） |
| 13 | Lane A emission boundary（instance-level vs protocol-semantic） | **RESOLVED** — PROVENANCE-ONLY（§4.8） |
| 14 | Lane A → existing Fact 的 provenance attachment 机制 | **RESOLVED** — observation 不落 Hub（D17，§4.11 J） |
| 15 | corroborates / contradicts / insufficient 的判定标准 | **RESOLVED** — 见 provenance_interface §4.2 |
| 16 | Alignment Target 的枚举范围 | **RESOLVED** — 见 provenance_interface §3.2 |
| 17 | packet_role_pair code/registry 分歧 | 见 hub_contract_errata_backlog §6 |
| 18 | **CSeq 覆盖路径甲/乙的具体实现选择** | 独立议题；**未阻塞** Lane A v1 冻结（§4.11 C 注明） |
| 19 | **G6 移出 Lane A 对齐范围** | **已裁定**（D18）。理由：`PairContext` 输入类型是 canonical `fact_key`，无 message / observation / capture 字段；把 Message 送进该机制即 §4.8 所禁。改 `PairContext` 属 Hub Contract 范围，已登记 hub_contract_errata_backlog §8 |
| 20 | **G5 / G7 = `NO_TARGET_PENDING_EXTRACTION`** | 上游 extraction coverage 缺口，Hub Contract 侧，非 Lane A 可解（§4.12） |
| 21 | **subject canonical ID 未解前 G4 的 target 无法唯一选定** | 承 §5.2（P1-1）；`authorization` / `Authorization` 两条并存 |

---

## 10. Freeze Criteria

1. 22 / 22 structural items 完成 emission_class 裁定
2. 所有 PRIMITIVE：完成 Primitive Contract（P1–P7）
   - 所有 PRIMITIVE Contract 含 Known Limitations 段
   - 所有 PRIMITIVE Contract 不得声称对 RTSP 协议泛化
3. 所有组完成 Evidence Emission Rule Contract（A–J 重构版）
4. 所有组完成 provenance alignment target 定义
5. 所有组不得产生 Hub Candidate / Claim / Fact
6. 与 `local/traffic_lane_a_provenance_interface.md` 无矛盾
7. 所有 subject：只使用 Registry canonical subject ID
8. 所有 condition：只表达真实 protocol-semantic applicability，不得由 observation-instance metadata 污染
9. 22/22 primary group assigned
10. unassigned = 0
11. duplicate primary-group assignment = 0
12. Lane A → §8 required handoff semantics 明确
13. §8 amendment implementation / design 可保持独立未完成
14. 与 Capability Profile 无矛盾
15. Markdown hygiene 清理
16. 所有 PRIMITIVE Contract 的裁定理由必须明确为「instance-level attribute」或「instance-internal relation」，**不得**表述为「值恒定」或「覆盖不足」


### 10.1 冻结判据核对（批次 4，Step 4.1）

逐条核对结果。**未通过的两条如实标出，不粉饰。**

| # | 判据 | 结果 | 依据 / 缺口 |
|---|---|---|---|
| 1 | 22/22 emission_class 裁定 | **PASS** | PRIMITIVE 7 / HUB_EMITTING 7 / NO_TARGET_PENDING_EXTRACTION 4 / OUT_OF_SCOPE 3 / CROSS_CUTTING 1 = 22 |
| 2 | 所有 PRIMITIVE 完成 Primitive Contract | **PASS** | G1 → §4.5 §4.6（C01/C02/C03）；G3 → §4.10（C04/C05/C06）；C17 → §4.13 |
| 3 | 所有组完成 Evidence Emission Rule Contract | **PASS** | G2/G4/G8 → §4.11（A–J 重构版）。G5/G7 无 target、G6 OUT_OF_SCOPE，不适用 |
| 4 | 所有组完成 provenance alignment target 定义 | **PARTIAL** | G1/G3 不需独立 target；G5/G7/G6 记为无 target 并说明。**G4 的 target 因 §5.2 canonical 未解而无法唯一选定**（见 §9 #21） |
| 5 | 所有组不得产生 Hub Candidate / Claim / Fact | **PASS** | §4.8 冻结；D17 判 observation 不落 Hub |
| 6 | 与 provenance_interface.md 无矛盾 | **PASS** | 两份 §5 同判「不落 Hub」；§4 同用四值词表 |
| 7 | 所有 subject 只用 Registry canonical ID | **PASS（约束已写）** | §5.2 P1-1 未改。**注意：约束写下了，但 Hub 现有数据里 `authorization` / `Authorization` 并存，说明该约束尚未被满足**（见 §9 #21） |
| 8 | condition 不被 observation-instance metadata 污染 | **PASS** | §5.3 + Invariant 19；Lane A 无 fact_key 故该约束自动成立 |
| 9 | 22/22 primary group assigned | **PASS** | §3.2，22 行均有 primary_group |
| 10 | unassigned = 0 | **PASS** | 同上 |
| 11 | duplicate primary-group assignment = 0 | **PASS** | 0 |
| 12 | Lane A → §8 handoff semantics 明确 | **PASS** | §6.2 M1–M6 已逐条给出本设计的答复 |
| 13 | §8 amendment 可保持独立未完成 | **PASS** | 未触碰 §8 |
| 14 | 与 Capability Profile 无矛盾 | **PASS** | §11.2 源分层、§11.4 双层计数均被遵守 |
| 15 | Markdown hygiene 清理 | **PASS** | 纯 LF、围栏配平、表格列数一致 |
| 16 | PRIMITIVE 裁定理由为 instance-level attribute / instance-internal relation | **PASS** | §4.7 明确写「理由不是「值恒定」」；§4.10 P8 重申 |

**未通过的 1 条：判据 4 为 PARTIAL。**

G4 的 7 条 `header` fact 中，`authorization` 与 `Authorization`
是两条独立 fact_key（Hub 现有数据实测）。在 §5.2 的 subject
canonical 问题解决前，「这条 observation 对齐到哪一个 fact」
本身是有歧义的。

**处置选择（两条路，本文件不自行拍板）**：

- 甲：把判据 4 降级为「已定义 target 集合，但未定义唯一选择规则」，
  冻结文件保持 Final Frozen，把 canonical 问题留给 Step 5
- 乙：判据 4 视为未通过，Rule Set **不冻结**，等 canonical 问题先解

**本文件按甲处理并显式标注**：§10 判据 4 状态为 PARTIAL，
§9 #21 登记为未决。原因见下。

**本文件状态：Final Frozen（带 1 条 PARTIAL 判据）**。
---

**Draft Framework 完毕。§3.2 22 候选 mapping 表由 agent 机械填入。§4 起的规则内容待逐组讨论填实。**
