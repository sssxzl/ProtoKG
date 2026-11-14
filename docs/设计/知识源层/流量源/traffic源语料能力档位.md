# Traffic Corpus Capability Profile

> 状态：ACTIVE
> 来源：Traffic Metadata Recon（PASS）+ Q1 duplicate-pair Recon（PASS）
> 范围：current traffic corpus empirical capability
> 非 D9 semantic capability

---

## 0. Authority Boundary

本文件**只表示 current corpus capability**，
**不表示 D9 semantic capability**。

D9 semantic design 的权威真源是
`docs/设计/知识源层/流量源/traffic源观测独立性设计.md`（Final Frozen）。

**Corpus 弱不等于 contract 错。**

---

## 1. Current Corpus Snapshot

- **1000 capture units**（tcp_0001..0500 + udp_0001..0500）
- 每 capture 恒含 6 件套 + 根部 manifest.csv
- 每 2 个 capture unit（tcp_i / udp_i）共享 **500 组** distinct
  packet-level artifacts；capture unit 本身仍保有独立 manifest 行与独立
  client.log
- 观察到 single scenario configuration
- repeated fixed 5-message RTSP control flow
- `rtsp.session` 常量 `000022B8`
- 无 reliable run / transaction / connection / collector identity signal
- `capture.pcapng` = classic libpcap；`clean.pcapng` = pcapng
  （**扩展名与真实容器格式相反**，见 D9 §14 E33）

---

## 2. Capability Matrix

| Capability | Current Status | Evidence |
|---|---|---|
| Message reconstruction | **STRONG** | rtsp.csv（100%）+ capture.pcapng raw；client.log **仅 udp 侧 500 单位补充** |
| Request-response pairing | **STRONG** | CSeq（现仅 udp 侧 client.log 有）；100% 覆盖需扩展 rtsp.csv 解析或从 pcap 抽取 |
| Packet-role inference | **PARTIAL** | 有方向 / 协议字段 / frame 连续性；role-class mapping 待定。**retransmission 无任何可观察信号** |
| Temporal ordering | **PARTIAL** | packet / message order 可见，语义角色待确认 |
| Raw-record deduplication | **ESTABLISHED** | Q1: 500 对 capture.pcapng 首包时间戳逐微秒相同（全量 500/500） |
| Cross-capture independence | **NOT ESTABLISHED** | 缺 run / scenario / support identity |
| Support-unit identity | **NOT ESTABLISHED** | 无可靠 transaction / run / collector identity；`rtsp.session` 在 1000 capture 中恒为同一值 |
| Cross-scenario prevalence | **UNSUPPORTED BY CURRENT CORPUS** | single scenario configuration（manifest 6 字段 distinct 均为 1） |
| Implementation diversity | **UNSUPPORTED BY CURRENT CORPUS** | User-Agent distinct=1 |
| Scenario diversity | **UNSUPPORTED BY CURRENT CORPUS** | stream / url / duration distinct 均为 1 |

---

## 3. Independence Semantics 状态

当前 corpus 下：

    independent-under-policy：**无法建立**
    dependent：仅对能由确定性证据证明的重复 / 相关单元成立
    unknown：大量存在

**不得**把「single scenario」等同「已证明 dependent」。
**不得**把「1000 capture units」等同「1 independence unit」。

同样地：raw-record identity 相同（如 Q1 的 500 对）**不蕴含**
semantic independence 相同，也**不蕴含**dependent。

见 D9 §2 第一原则：unknown 不得自动按 independent 处理。

---

## 4. Candidateization Lanes

### Lane A — Structural Traffic Candidates

依赖 semantic reconstruction correctness，
**不依赖 cross-capture independence**。

候选：

- Message reconstruction
- Request / response classification
- CSeq pairing
- Header / value observation
- method / status observation
- Message ordering
- Transaction structure
- Packet-role observations

**当前可推进。**（STRONG / PARTIAL 能力足以支撑）

### Lane B — Aggregate Observational Candidates

包括：

- occurrence_frequency
- co_occurrence
- 未来可能的 observed temporal / packet-position aggregates

发布前必须同时具备：

- measurement scope
- observation population provenance
- support summary
- independence state
- non-generalization boundary

**若 Hub carrier 暂不能表达**：
Lane B = **no materialization**，不伪造 complete Claim。

**不修改 D9 Contract。**

---

## 5. Traffic Candidateization 第一原则

> **Traffic Candidateization must not upgrade corpus repetition
> into semantic diversity or independent support.**

展开：重复观察可以增加 provenance / raw observation count，
但**不得自动增加**：

- scenario diversity
- implementation diversity
- independent support count
- protocol-wide prevalence confidence

结构性事实只要 deterministic reconstruction 足够可靠，
仍可正常生成 Structural Traffic Candidate。

---

## 6. 未来语料扩充（路径丙）

状态：**DEFER**。

属独立 data acquisition project，非当前主线。

先利用当前 corpus 把 Message reconstruction /
Request-response pairing / Structural Traffic Candidateization 跑通。

---

## 7. 更新规则

本文件是 current corpus capability 记录。
Corpus 扩充或 Q1 有新结论后 append / amend。
**不改 D9 semantic contract。**

## 8. Dependency Clustering Input Gap

以下结论来自 Traffic Metadata Recon / Q1 Recon 的实测。

**D9 §7.2 要求 dependency clustering 的 deterministic 判据。**
当前 corpus 下：

- 唯一可观测的差异轴是 **transport**（tcp / udp）和 **scenario index**
- 两者 **完全共变**——分不清是 transport 还是 scenario index
  造成了 pair 结构
- 无独立的 run identity / collector identity / connection id /
  transaction id / request id 信号

**结论**：

> 当前 corpus 无法导出 dependency clustering 的
> 非共变 differentiation axis。
>
> Traffic Candidateization Design **不得**假装
> 「按 transport 分 cluster」或「按 scenario index 分 cluster」
> 是有效的 dependency policy。
>
> 二者只是同一个变量的两种标记。

**D9 §7.2 语义不变**——这是 corpus 事实限制，不是 contract 缺陷。

**恢复条件**：corpus 扩充（路径丙）后提供独立 differentiation axis。

### 8.1 Q1 关键数字（登记备查）

- 1000 capture units = **500 组** distinct packet-level artifacts
- 每组 = 1 tcp + 1 udp 目录，**同 index**
- pair 内 6 个 sidecar 中 **5 个逐字节相同**（仅 `client.log` 不同，
  其 1000 个文件全 distinct）
- `capture.pcapng` 首包时间戳 pair 内**逐微秒相同**（全量 500/500）
- `client.log` 首个 Date 相对 capture 首包偏移：
  - **udp 侧 0s（244 对）/ -1s（256 对）** ← 与 capture 同刻
  - **tcp 侧 +11s(14) +12s(380) +13s(77) +14s(5) +15s(16) +16s(7)**
- 判定：**duplicate replication**（证据等级 *inferred*；生成器源码不可得，
  未由日志明示，不提升为 observed）
- 落入 D9 §5 **Q1-A** 分支：raw-record identity 层可处理，
  但**仍不能推出 dependent**

### 8.2 rtsp.csv 三变体（历史记录，已更正）

**原记录**：3-variant 与 pair 结构不吻合。

**更正**（见 §10）：实测 **500/500 ALIGNED**。
原记录是 pre-Q1 Recon 阶段的初版判断，已被本轮实测推翻。

以 §10 为准。

---

*§8 依据：`guard/audit/step_traffic_post_recon/`（Metadata Recon + Q1 Recon）*

---

## 9. D9 Post-Freeze Follow-up：Independence State 承载层

本节登记一项**不属于 corpus capability**、但直接影响本文件 §4
Lane B materialization 判定的 follow-up 项。

### 9.1 性质

**D9 semantic contract 的定义空白，不是本 corpus 的能力缺口。**

D9 §7 已定义三态语义（§7.1）、三态判定（§7.3）、四量承载（§7.4），
但**未定义单个 support unit 的三态标签存放在哪一层、哪个字段**。

⟹ 该缺口**不随 corpus 扩充而消失**。即使未来 corpus 提供了完美的
run / scenario / support identity，使每个 unit 都能被判出三态，
「这个标签该写到哪里」依然未答。

因此本节**不是** Capability Matrix 的一行，**不进入** §2 的
Status 判定；它属于 contract 层的 follow-up。

**与 §0 Authority Boundary 的一致性**：§0 说「Corpus 弱不等于
contract 错」。本节是反向的一例——**Corpus 强也不能补上 contract 的
定义空白**。两句话是同一条边界的两面。

### 9.2 与 §3 / §4 的关系

- §3 描述的是**取值分布**：当前语料下三态各取什么值
- §9 描述的是**承载位置**：那个值应该写到哪里
- 二者正交。§3 已有内容；§9 补的是「写出取值之前」的那个问题。

§4 Lane B 发布前置条件中的 `independence state` 一项，
在 §9 闭合前**无法判定为满足**——不是因为算不出值，
而是因为没有地方放这个值。

### 9.3 对本文件既有结论的影响

- §4 Lane A：**无影响**。Lane A 不依赖 cross-capture independence。
- §4 Lane B：维持 **no materialization**。理由从单一的
  「corpus 能力不足」细化为**两条并存**：
  1. corpus 侧：Cross-capture independence **NOT ESTABLISHED**（§2）
  2. contract 侧：independence state **承载层未定义**（§9.1）
- §5 第一原则：**不变**。§9 不放宽任何一条。
- **不修改 D9 §0–§13**，不伪造承载位，不把 unknown 折叠掉。

### 9.4 处置

以 **D9 post-freeze amendment** 闭合。amendment 需至少满足：

1. 明确定义三态标签的承载层与字段
2. 承载层必须能表达 `unknown` 这一状态**本身**，
   不得把 unknown 折叠成 false 或省略
3. 必须可读回——Claim 消费方能取到 **unit 级**三态，
   而非只有总体口径的汇总值

本文件**不预设**以上任一条的具体形式（不改 `Assertion.value`、
不改 `S2.support`、不新增字段、不扩展 carrier）。
具体形式由你裁定。

### 9.5 登记来源

`docs/设计/知识源层/流量源/traffic源候选项化预设计.md` §4.4
（同轮的 §4.0 已把它归入 **Lane B 前置**类）。

---

*§9 登记于 2026-10-02，依据 D9 §7 文本 + Hub carrier 现状，
不修改 D9 §0–§13 冻结体。*

---

## 10. Capture Identity / Frame Mapping（本轮确认）

**来源**：Traffic Pre-Design Closure 阶段 A / B 实测
（证据等级 *observed*，除末尾标注项外）

### 10.1 Frame 命名空间

- 同一命名空间，四个投影：
  `rtsp.csv` ∪ `rtp.csv` = 49 = clean EPB 数 = ndjson record 数
  （1000/1000 成立）
- CSV frame.number 就是 capture.pcapng 记录序号
- **capture 内 canonical identity**：`(unit, capture_frame)`
- **全局无主键**

四个投影与 `capture.pcapng` 的关系：

| 载体 | 帧号 | 角色 |
|---|---|---|
| `capture.pcapng` | 1..N，N = 55/56/57/58 | **父时间线**（classic libpcap） |
| `clean.pcapng` | 49 个保留帧（pcapng 本身不存号） | capture 的顺序保持子集 |
| `packets.ndjson` | `frame_frame_number` ∈ 1..N | 保留 capture 原始编号 |
| `rtsp.csv` / `rtp.csv` | `.frame.number` ∈ 1..N | 二者的并集 = 49 个保留帧 |

⟹ 字段名 `frame.number` 在本语料**只对应一件事**：
capture.pcapng 的 1-based 记录序号。原先「两个不同命名空间」
的记法已作废。

### 10.2 deterministic 映射

`clean.pcapng → capture.pcapng` 按载荷 sha256 映射：

- 1000/1000 唯一命中
- 1000/1000 严格单调
- 0 ambiguous / 0 not-found

⟹ `clean.pcapng` 的帧号是**派生**的、需重算，不是 canonical；
canonical 身份是 capture.pcapng 侧的记录序号。

### 10.3 丢弃规则

dropped = N − 49 = 6/7/8/9
CSV 的 gap（13,15,17 + RTP 段）就是被丢弃的帧。

分布（N = capture.pcapng 记录数）：

| N | capture units | 对应 3-variant |
|---|---|---|
| 55 | 936 | 早期（主变体） |
| 56 | 60 | 当前（尾部 +1） |
| 57 | 2 | V3（尾部 +2） |
| 58 | 2 | V3（尾部 +2） |

**唯一 UNKNOWN**：被丢弃帧是什么
（ACK / retransmission / 未解析）——语料内无标注。

### 10.4 对 Lane A 的影响

- Lane A **前置已清零**
- `(unit, capture_frame)` 可作为 Lane A 的 frame identity 基础
- 但**不得**用它作为跨 capture 的 identity——无全局主键
- **不得**以绝对 `frame.number` 取值作为判据：三变体会在尾部
  产生 0/+1/+2 的偏移。规则应以消息内容、method/status/session，
  或帧的**相对顺序**为依据

### 10.5 与 §8.2 的关系

§8.2 登记的「3-variant 不服从 pair 结构」已被本轮推翻：
实测 pair 对齐 500/500，且偏移只落在 `frame.number` 尾部 6 行。
§8.2 为 backup 式历史登记，本轮授权仅限追加 §10，
故**未改写 §8.2**，在此交叉声明以免两节互相矛盾。

### 10.6 登记来源

- `guard/audit/step_traffic_pre_candidateization/stage_a_rtsp_variants/`
- `guard/audit/step_traffic_pre_candidateization/stage_b_frame_number/`
- `guard/audit/step_traffic_pre_design_closure/stage_a_overturn_sweep/`
- `docs/设计/知识源层/流量源/traffic源候选项化预设计.md` §4.2 / §4.5

---

*§10 登记于 2026-10-02，corpus 事实澄清，
不改变 D9 semantic contract（见 D9 §14 E36）。*

---

## 11. Source Authority Model（Lane A 用）

**来源**：Lane A 依赖矩阵 recon（步骤 A 阶段）

### 11.1 关键发现：tcp 侧 client.log 是外部 artifact

- udp 侧 client.log（500）：完整会话，与 capture 一致
- tcp 侧 client.log（500）：3 请求 / 2 响应，止于 SETUP 请求头；
  其 SETUP Transport = `RTP/AVP/TCP;...interleaved=0-1`
  与 capture 的 `RTP/AVP;unicast;client_port=...` **协议头层面矛盾**

**结论**：tcp 侧 client.log 记录的是一次**从未被抓到**的
TCP-interleaved 运行，**不属于本 corpus**。

### 11.2 源权威分层

| 层 | 源 | 覆盖 | 说明 |
|---|---|---|---|
| Ground truth | `capture.pcapng` | 100% | 原始，需解析 |
| Structured | `rtsp.csv` / `packets.ndjson` / `rtp.csv` | 100%（500 distinct × 2 dirs） | 无 CSeq 列 |
| Supplemental | **udp 侧** `client.log` | 500 units | 含 CSeq / RTP-Info |
| Excluded | **tcp 侧** `client.log` | — | 不同 session |

### 11.3 CSeq 覆盖路径

CSeq 是 RFC 2326 强制 header，**存在于 capture.pcapng 的 RTSP 报文内**。
`rtsp.csv` 无 CSeq 列是**解析器限制**，不是数据限制。

阶段 B 核验：29 样本 deterministic 抽取成功，与 udp 侧 client.log 100% 一致。
解析器按 magic 判定 classic libpcap，不依赖扩展名。

**路径丙（接受 50%）事实排除。**

两条候选（实现选择，不裁定）：

- 甲：扩展 rtsp.csv 解析加 CSeq 列（持久化，100% 覆盖）
- 乙：Lane A 运行时从 pcap 直接抽（无新 artifact）

实现选择留 Lane A Rule Set 设计阶段。

**未对 1000 全量证明——29 样本是覆盖性核验，非全量证明。这一约束保留。**

### 11.4 有效 unit 口径（已裁定）

**Lane A 计数分两层**：

| 层 | 计数 | 理由 |
|---|---|---|
| Provenance | **1000 nominal** | 保留 1000 目录 manifest 行——来源可溯 |
| Measurement population | **500 effective** | raw-record dedup 后的 distinct artifacts |

**依据**：D9 §5.1 layer-local dedup + §3.1 quantity separation。
dedup 不删 provenance。

背景（保留供追溯）——若 tcp 侧 500 client.log 是外部 artifact，
「1000 capture units」的有效数是 **500**：

- 500 distinct pcap artifacts（duplicate 到 2 dirs）
- 500 udp client.log（匹配 capture）
- 500 tcp client.log（**不**匹配 capture）

**Lane A 设计约束**：

- coverage 分母用 **500 effective**
- provenance 记录保留 **1000 nominal**

⟹ 引用本口径时必须写明是哪一层。裸写「1000 units」或裸写
「500 units」都不合规：前者会虚增 measurement 分母，
后者会丢失 provenance。

## 12. Corpus Constants 与 Ratio 构造问题

**来源**：Lane A 依赖矩阵 recon（§8 接口）

以下字段在当前语料中为**常量**：

- method 集 / status 集 / URL 集 / Session / User-Agent /
  请求数 / 响应数 / RTP 帧数

**由常量算出的任何比率按构造就是 0 或 1。**

Lane A 设计**不得**对这些字段做 ratio / aggregate。
见 Capability Profile §2（single scenario →
cross-scenario prevalence UNSUPPORTED）
+ Pre-Design §3（Candidateization 第一原则）。

## 13. Role Class Shrinkage（capability 记录）

基于 §4.6（retransmission 不可观察）：

候选 role class 中：

- **保留** 5（不依赖 retransmission）
- **剔除** 3（control / retransmission / transport-control）
- **待定** 3

**不裁定最终角色类**——本项登记供 §6.6-C1.x 后续。

---

*§11 / §12 / §13 登记于 2026-10-02，
源自 Lane A 依赖矩阵 recon，只读勘察阶段。
不改变 D9 semantic contract，不进入 Rule Set 设计。*
