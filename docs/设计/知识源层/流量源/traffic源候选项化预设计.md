# Traffic Candidateization Pre-Design

> 状态：Pre-Design（未冻结）
> 上游：`docs/设计/知识源层/流量源/traffic源观测独立性设计.md`（Final Frozen）
> 　　　`docs/设计/知识源层/流量源/traffic源语料能力档位.md`（ACTIVE）
> 本文件是**设计前的约束冻结**，不是 Rule Set。

---

## 状态澄清（2026-10-04 追加）

**1. 状态标注冲突**

`docs/设计/知识源层/流量源/traffic源规则集设计.md`（Final Frozen）的上游声明把本文件
标为 `ACTIVE`，与本文件自身状态行 `Pre-Design（未冻结）` 冲突。

**以本文件自身状态行为准：本文件从未冻结。** 产生该标注的一方是 Final Frozen
文档，按 Authority Rule D 未获单独授权不得反向修改，故 rule_set 原文保留，
在此登记澄清。实质影响：接手者不应因 rule_set 的标注而把本文件当作已冻结契约。

**2. 本文件 §4.0 与 §7 反映的是「Lane A Rule Set 开写之前」的状态**

§4.0 与 §7 中「Lane A Rule Set 暂不可开写」「C-6 / C-7 / C-8 阻塞 Lane A
Rule Set 开写」等表述，**在写作当时为真**，现已过时：

- `docs/设计/知识源层/流量源/traffic源规则集设计.md` 已 **Final Frozen**（2026-10-04）
- `docs/设计/知识源层/流量源/traffic源溯源接口.md` 已 **Final Frozen**（2026-10-04）
- Lane A 冻结为 **PROVENANCE-ONLY**；§4.7 / §4.8 的产物即规则集 §4.5–§4.11

保留 §4.0 / §7 原文不改写，是为了让「当时为何认为不可开写」这一推理过程
保持可审计。当前状态以 rule_set 为准；本文件的分析结论本身不因此失效。

**3. §7 计数更正**

§7 末尾原写「以上 8 项中，7 项未决、1 项（C-2）已解决」。按其自身表格，
C-2 与 C-8 **均**标为已解决，正确计数为 **6 项未决、2 项已解决（C-2 / C-8）**。
下表已按 6 / 2 表述。

---

## 0. 范围

本文件冻结「Traffic Candidateization Rule Set 设计前**必须确认的约束**」，
**不写具体规则**。

Rule Set 设计在本文件冻结后另立。

---

## 1. 继承的硬约束

### 1.1 D9 Final Frozen 语义

见 `docs/设计/知识源层/流量源/traffic源观测独立性设计.md` §0–§13。

### 1.2 Current Corpus Capability Profile

见 `docs/设计/知识源层/流量源/traffic源语料能力档位.md`。

### 1.3 Dependency Clustering Input Gap

见 Capability Profile §8。

**不得假装 clustering 判据可从当前语料导出。**

---

## 2. 两条 Lane 的边界

### Lane A — Structural Traffic Candidates

依赖 semantic reconstruction correctness，
**不依赖** cross-capture independence。

候选（见 Capability Profile §4）：

- Message reconstruction
- Request / response classification
- CSeq pairing
- Header / value observation
- method / status observation
- Message ordering
- Transaction structure
- Packet-role observations

### Lane B — Aggregate Observational Candidates

包括：

- occurrence_frequency
- co_occurrence
- 未来可能的 observed temporal / packet-position aggregates

发布前必须同时具备（见 D9 §6 / §7）：

- measurement scope
- observation population provenance
- support summary
- independence state
- non-generalization boundary

**若 Hub carrier 暂不能表达**：
Lane B = **no materialization**，不伪造 complete Claim。

---

## 3. Candidateization 第一原则

> Traffic Candidateization must not upgrade corpus
> repetition into semantic diversity or independent support.

展开：重复观察可以增加 provenance / raw observation count，
但**不得自动增加**：

- scenario diversity
- implementation diversity
- independent support count
- protocol-wide prevalence confidence

---

## 4. 设计前必须确认的问题

（agent 基于 Recon + Capability Profile 列出，**不裁定**）

### 4.0 优先级分类

本节 6 个问题**不等价**。按「阻塞哪条 Lane」分三类：

| 类 | 定义 | 成员 |
|---|---|---|
| **Lane A 前置** | 未确认则 Lane A Rule Set 无法开写 | **§4.7、§4.8、§4.9** |
| **Lane B 前置** | 未确认则 Lane B 无法 materialize | §4.1、§4.3、§4.4 |
| **独立低优先** | 不阻塞任一 Lane 的开写，可并行推进 | §4.2、§4.5、§4.6 |

- ⚠ **「Lane A 前置已清零」不再成立。** 上一轮清零只覆盖了
  frame.number 这一个子问题。Lane A 依赖矩阵 recon 之后，
  新增 3 个 Lane A 前置（§4.7 / §4.8 / §4.9），⟹
  **Lane A Rule Set 暂不可开写**。
- §4.7 / §4.8 / §4.9 的建立依据是 Capability Profile §11：
  tcp 侧 client.log 与 capture 在协议头层面矛盾，被判定为
  外部 artifact；由此派生出源权威、coverage 口径、CSeq 路径
  三个必须先定的问题。
- §4.1 / §4.3 / §4.4 全部指向 Lane B 的 **materialization 前置条件**，
  对 Lane A **无阻塞**。三者在全部落定前，Lane B = no materialization。
- §4.2 / §4.5 / §4.6 不阻塞任一 Lane 的开写。§4.2 的 frame.number
  子问题与 §4.5 均已解，仅成因细节仍为 UNKNOWN，且不参与任何判据。
  §4.6 仍待你裁定 role class 边界。

### 4.0.1 前序结论更正记录

以下 §4 条目的初版表述已被本轮实测推翻，正文已按新结论改写：

- §4.2 原「frame.number 是两个不同命名空间」
  → 实为同一命名空间，四个投影（详见 §4.2）
- §4.5 原「3-variant 不服从 pair」
  → 实为 500/500 ALIGNED（详见 §4.5）
- 附带更正：`capture.pcapng` 包数原记为 `486–490`
  → 实为 `55/56/57/58`（936/60/2/2），修正后分布恰对上
  936/60/2/2 的 3-variant 切分。原数字来源不明，不臆造。

推翻依据：见
`guard/audit/step_traffic_pre_design_closure/stage_a_overturn_sweep/`
（`report.txt` / `hit_list.txt` / `classification.txt` / `detail.txt`），
以及上一轮实证
`guard/audit/step_traffic_pre_candidateization/stage_a_rtsp_variants/`
与 `.../stage_b_frame_number/`。

**本轮未授权、未改写的陈旧点**（已登记，待你裁定）：

- §7 冲突表行 `C-2`（仍写「3-variant 异常成因 **未解决**」）
- Capability Profile §8.2（仍写「不服从 pair 结构」）

### 4.1 raw-record dedup 的触发点（由 Q1 新增，最高优先）

Q1 判定 duplicate replication，1000 capture units 承载 500 组
distinct packet-level artifacts。

必须确认：

- raw-record dedup 发生在 Candidateization **之前**还是**之内**？
  （若之前，dedup 的 artifact 是否仍保留 capture-unit 级 provenance？）
- 若发生在 Lane B 的 observation population 计数中，
  500 组是否构成 effective population 上界？
- D9 §5.3 Raw Record Duplication 层的「deterministic proof」在本语料下
  已有证据（微秒时间戳相同），可**直接采信**还是需独立规则再确认？

⟹ 未确认前，Lane B 的 population 分母不确定。

### 4.2 frame.number 命名空间（已澄清）

**结论（本轮实测，evidence_level: observed）**

- 同一命名空间，四个投影：
  `rtsp.csv` ∪ `rtp.csv` = 49 = clean EPB 数 = ndjson record 数
  （1000/1000 成立）
- CSV frame.number 就是 capture.pcapng 记录序号
- **canonical identity**：capture 内 `(unit, capture_frame)`
- **全局无主键**——跨 capture 无统一 frame identity

**deterministic 映射**：
`clean.pcapng → capture.pcapng` 按载荷 sha256 映射，
1000/1000 唯一命中、1000/1000 严格单调。

**丢弃规则**：dropped = N − 49 = 6/7/8/9，
CSV 的 gap（13,15,17 + RTP 段）就是被丢弃的帧。

**唯一 UNKNOWN**：被丢弃帧是什么（ACK / retransmission /
未解析）——语料内无标注，只到 inferred。

**Lane A 前置已清零。**

⟹ §4.2 中原「以哪个命名空间为准」的问题**不再成立**：
本语料只有一个命名空间，歧义是**文档缺口**而非数据缺口。
凡引用 `frame.number` 的规则只需写明所指容器（capture.pcapng 记录
序号），无需再做取舍裁定。

**残留（不阻塞 Lane A 开写）**

- 上述两个子问题仍未裁定，**不属** frame.number 问题：
  - 哪些结构性事实**必须**由 reconstructed Message 而非 raw packet 得出？
    （client.log 提供原文，packets.ndjson 亦含 rtsp layer，冲突时以谁为准）
  - client.log 的 CSeq 配对与 packets.ndjson 的
    `rtsp.request_in_frame` / `rtsp.response_in_frame` 是否需交叉验证？
- 本条已由「Lane A 前置」降级为「独立低优先」，见 §4.0。

### 4.3 Lane B 的实际 materialization 条件

必须确认：

- 在 independence NOT ESTABLISHED + support-unit identity signal
  insufficient 的前提下，Lane B 的 Claim **是否一律不 materialize**？
  （Capability Profile §4 已写「若 carrier 不能表达则 no materialization」，
   但此处需确认是否**语义上**就不该 materialize）
- Aggregate Carrier 承载位（S2）已裁定，但**四量**的取值在当前语料
  全部为 unknown 时，Claim 该如何表达？

### 4.4 Independence State 承载层 gap

> 分类：**D9 semantic contract 的定义空白**（post-freeze follow-up）
> **不是** corpus capability 缺口，**不是** contract contradiction。

**性质**

D9 §7 已定义 independence 的三态语义（§7.1）、三态判定条件（§7.3）、
以及四量的承载（§7.4）。**唯独没有定义**：

> 一个已判定出三态的 support unit，其标签本身存放
> 在哪一层、哪个字段。

这是**定义层面的空白**，不是判定层面的空白：

- §7.1 已说清 `independent-under-policy` / `dependent` / `unknown`
  各指什么 ⟹ 语义不缺
- §7.3 已说清在什么条件下判为哪一态 ⟹ 判据不缺
- §7.4 已说清四量（scope / population / support / non-generalization）
  归 S2 ⟹ 承载位已裁定
- **缺的只有一件事**：标签如何进入 Hub carrier，以及如何被读回

**属性**

| 维度 | 取值 |
|---|---|
| 缺口类型 | 定义空白（undefined carrier slot） |
| 归属 | D9 §7 语义层；§6.6 / §6.w 已裁定部分**不受影响** |
| 是否语料相关 | **否**。即使语料完美、每条都能判出三态，缺口依然存在 |
| 是否可绕过 | **否**。不能靠「本轮都是 unknown 所以不表达」绕过——缺的正是「unknown」这一状态本身能否被承载 |
| 是否阻塞 Lane A | **否**。Lane A 不依赖 cross-capture independence |
| 是否阻塞 Lane B | **是**。Lane B 发布前置条件之一 |
| 严重度 | Lane B blocking precondition / Lane A non-blocking |

**处置**

1. **不修改 D9 §0–§13 冻结体。** 以 post-freeze amendment 追加，
   或在 Rule Set 文档中另立补充节——二选一由你裁定。
2. **不自行定层。** 本文件只登记缺口，不预设标签落在
   `Assertion.value` / `S2.support` / 新字段 / carrier 扩展。
3. **§4.0 重排后，Lane A 前置已清零（§4.2 已解）。**
   本项（Independence State 承载层）是 **Lane B blocking
   precondition**，与 Lane A 无关。
4. **Lane B 在缺口闭合前 = no materialization**（与 §4.3 同向叠加）。
5. **恢复条件**：D9 post-freeze amendment 明确定义 independence state
   的承载层，且 Hub carrier 能在该层**无损**表达三态（含 `unknown`）。

**当前语料下该标签会取什么值**（供 amendment 参考，非裁定）

见 Capability Profile §3：`independent-under-policy` 无法建立；
`dependent` 仅对 Q1 以确定性证据证明的 raw-record 重复成立；
`unknown` 大量存在。⟹ amendment 至少必须能表达
「三态并存、以 unknown 为主」这一实际分布，而不是只表达单一态。

### 4.5 rtsp.csv 三变体（已澄清）

**结论（本轮实测，evidence_level: observed）**

差异只有 6 行、只有 1 列（`frame.number`）、且恒在尾部。

- 20 行里 384 个差异单元格**全部**落在 `frame.number`
- `ip.src`/`ip.dst`、`method`、`status`、`url`、`session`
  在全部 1000 个 capture 中逐字节相同
- 前 14 行的帧号 `[1..11,16,18,21]` 是 n=1000 的唯一前缀
- 尾部算术：早期 `49,50,51,53,54,55` / 当前 `+1` / V3 `+2`
  —— 纯加性偏移，无重排、无丢行、无消息变化

**不是语义差异，是 capture 时间线 artifact。**

**与 pair 结构 ALIGNED，500/500**（推翻前序结论）。
其余 5 个 sidecar 的 sha 分组与 `rtsp.csv` 分组**完全同构**
（500/500 pure）——偏移是整条 capture 的属性。
（早期 = 468 pairs、当前 = 30 pairs、V3 = 2 pairs；
936/60/4 的文件切分即 468/30/2 的 pair 切分。）

**对 Lane A / Lane B 影响**：

- 非判别轴（transport 各变体恒 50%；index 不规则）
- 不构成 Candidateization 的差异化维度
- **Lane A / Lane B 均不受阻塞**

⟹ 原「是数据损坏还是多样性信号」的二选一**已消解**：
两者都不是。它既不是损坏，也不是协议语义多样性。
§7 冲突表 C-2「成因未解决」随之失效（该表不在本轮授权范围，
已登记为待裁定项，见 `stage_a_overturn_sweep/report.txt` ADDENDUM）。

**残留（UNKNOWN，evidence_level: inferred）**

- 30/500 pair 得 `+1`、2/500 得 `+2` 的**成因**未确定
- 被丢弃帧的语义（ACK / retransmission / 未解析）未确定
- 生成器源码不在语料内，故成因不提升为 observed

### 4.6 packet-role 的可行性边界

必须确认：

- Capability Profile §2 记录 retransmission **无任何可观察信号**
- §6.6-C1.x 的 role class 枚举（request/response/data/control）在此约束下
  能否完整落地？
- 若不能，§6.6 的 role class 是否需收缩为「仅可观察维度」？
- Capability Profile §13 已给出收缩候选的**登记**（保留 5 / 剔除 3 /
  待定 3），但**未裁定**。本项的裁定仍待你给出。

### 4.7 tcp 侧 client.log 的排除（Lane A 新增前置）

Lane A 依赖矩阵 recon 实测：

- udp 侧 client.log（500）：完整会话，与 capture 一致
- tcp 侧 client.log（500）：3 请求 / 2 响应，止于 SETUP 请求头

且其 SETUP `Transport` = `RTP/AVP/TCP;unicast;interleaved=0-1`，
与 capture 的 `RTP/AVP;unicast;client_port=…` **在协议头层面矛盾**。

必须确认：

- tcp 侧 client.log 是否**整体排除**出 Lane A 的可用输入？
  （Capability Profile §11.2 已把它列为 Excluded 层）
- 排除后，`client.log` 在 Lane A 中是否降级为
  **仅 udp 侧 supplemental**？还是完全不作为 Lane A 输入？
- 被排除的 500 份 artifact 是否仍需保留 provenance 记录
  （D9 §4.8「partial 不得因不完整而丢弃」）？

⟹ 未确认前，任何「client.log 为主」的规则在 50% 单元上无依据。

### 4.8 源权威裁定（Lane A 新增前置）

Capability Profile §11.2 给出四层分层（Ground truth / Structured /
Supplemental / Excluded），但**层间冲突时的裁决规则尚未裁定**。

必须确认：

- `rtsp.csv` 与 `capture.pcapng` 不一致时以谁为准？
  （实测二者在方法/状态层面一致，但 `rtsp.csv` 缺 CSeq 列）
- `packets.ndjson` 与 `capture.pcapng` 不一致时以谁为准？
- 冲突**不可判定**时的表达方式？是否沿用 D9 §4.8
  「identity = unknown，不得自动 merge」？
- 是否为每个字段类（而非全局）分别声明主源与兜底源？

### 4.9 有效 unit 口径（Lane A 新增前置）

Capability Profile §11.4 提出但当时**未裁定**：

- 若 tcp 侧 500 份 client.log 属外部 artifact，
  「1000 capture units」的有效数可能是 **500**
  （500 distinct pcap artifacts + 500 匹配 capture 的 udp client.log）
- Lane A 的 coverage 口径是 **1000 nominal** 还是 **500 effective**？

**已裁定**（见 §4.10）：

- ✅ 上述三组计数构成**统一**的 effective unit 计数：
  **500 effective**。理由与依据见 §4.10 / Capability Profile §11.4。

**仍未裁定**：

- ❓ coverage 声明在两种口径下是否需要**分别标注**？
  （若标注，标注写在哪一层：Claim 层还是 fact 层？）

⟹ 本项**部分**已裁定。剩余的层归属问题仍阻塞 Lane A，
故本节仍保留在 §4.0 的 Lane A 前置类中。

### 4.10 有效 unit 口径（已裁定）

Lane A coverage 分母 = **500 effective**。
Provenance 保留 **1000 nominal**。

见 Capability Profile §11.4。

---

## 5. 明确不做

- **不写具体 Candidateization 规则**
- **不修改 D9 semantic contract**
- **不假装 clustering 判据可导出**

---

## 6. 下一步

本文件冻结后：

```
Traffic Candidateization Rule Set Design
  → Lane A 先行（结构信息可支撑）
  → Lane B 待 Hub carrier 确认后
```

或按实际讨论结果重排。

---

## 7. 已识别的冲突 / 未决

| # | 项 | 状态 |
|---|---|---|
| C-1 | Q1 duplicate replication 与 Lane B population 分母 | **未决**（§4.1） |
| C-2 | rtsp.csv 3-variant 异常成因 | **已解决**（见 §4.5） |
| C-3 | independence state 的承载层未裁定 | **未决**（§4.4） |
| C-4 | retransmission 不可观察 vs role class 完整性 | **未决**（§4.6） |
| C-5 | client.log 与 packets.ndjson 的 RTSP 层冲突时优先级 | **未决**（§4.2 残留子问题） |
| C-6 | tcp 侧 client.log 与 capture 协议头矛盾，是否整体排除 | **未决**（§4.7） |
| C-7 | 源层间冲突的裁决规则（无既定 precedence） | **未决**（§4.8） |
| C-8 | 有效 unit 口径：1000 nominal vs 500 effective | **已裁定**（§4.10） |

以上 8 项中，**6 项未决、2 项已解决（C-2 / C-8）**。它们均**不构成**
与 D9 Final Frozen 的矛盾，而是**当前语料能力**与**设计需求**
之间的缺口。

其中 **C-6 / C-7 / C-8** 为 Lane A 依赖矩阵 recon 新增，
依据见 Capability Profile §11。它们**不阻塞 Lane B**。
（原文此处写「但**阻塞 Lane A Rule Set 开写**」——该判断在写作当时为真，
现已过时，见文首「状态澄清」第 2 条。）

---

*本文件为 Pre-Design，**未冻结**。冻结后 Rule Set 设计方可启动。*
