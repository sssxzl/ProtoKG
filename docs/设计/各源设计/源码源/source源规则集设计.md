# docs/设计/各源设计/源码源/source源规则集设计.md — 第五源 source Lane A Rule Set 设计

> 状态：**Final Frozen**（2026-10-05；§10 八条判据全部通过）
> **实现**：D39 已落地双包骨架 `core/source_a/`（provenance 轨）+ `core/source_hub/`（hub_fact 轨）
> 实测：端到端 26 条 observation；`method.register` 经 dispatcher 产出；skipped 9 → 0
> 上游：`docs/设计/各源设计/漏洞源/第五源设计.md`（Final Frozen Candidate）
> 　　　`docs/设计/各源设计/源码源/source源语料能力档位.md`（**ACTIVE**）
> 参照：`docs/设计/各源设计/流量源/traffic源规则集设计.md`（**结构类比，内容不复制**）
> 契约：`docs/设计/顶层设计/规范化序列化规范.md`、`core/fused/hub/registry/*.json`
> 裁定：`docs/工具/决策记录/已决事项.md` **D24 – D34**

---

## 0. 范围

### 0.1 本设计要解决什么

定义第五源 `source`（LIVE555 liveMedia 协议实现源码）的知识抽取规则集：
把「实现如何响应某种输入」表述为可审计的规则与 observation。

### 0.2 本设计不解决什么

- 不重新裁定 traffic 侧任何问题
- 不定义 source 源的 D9（D25 已裁定不需要）
- 不实施 `core/source_a/` 或 `core/source_hub/`（属实现阶段）

### 0.3 与 traffic Rule Set 的根本差异

> **这是两个 Rule Set 不能互相复制的原因。**

| | traffic | source |
|---|---|---|
| 记录什么 | 协议交互**实际发生**的内容 | 实现**如何响应**某种输入 |
| epistemic | 观察性（observational） | 规范性（normative） |
| 数据源 | 半结构化 pcap / csv | 结构化 C++ AST |
| 独立证人 | 有（udp 侧 client.log） | **无**（0 测试用例） |
| 与 Hub 的关系 | 不落 Hub（PROVENANCE-ONLY） | **双轨**（D24） |

⚠ 二者虽都用「非投票 provenance」形式，但 `observed` 字段语义
**完全不同**，schema 必须分开定义。
**禁止**把 source 的 branch/body 文本当成「实现做了什么」记录 ——
那是「实现规定做什么」。

### 0.4 前置已冻结

| 项 | 来源 | 结论 |
|---|---|---|
| 双轨裁定 | D24 | 能归 rfc fact → provenance；不能归 → 独立 Hub fact |
| 不需独立 D9 | D25 | 实现数 = 1，无变体 |
| 双包 | D26 | `core/source_a/` + `core/source_hub/` |
| 同源限制 | D27 / D29 | source 与 traffic 不得互为 validation oracle |
| 分流判据 | D28 | L1（方法）/ L2（错误响应），函数级粒度 |
| RFC 状态码基准 | D30 | §4.2 of `设计/source_source_design.md`，15 条 RTSP 特有码 |
| 第 3 档抽取规则 | §4.2b | R-1~R-5 |
| REGISTER 归属 | D32 | **沿用 method kind，只加 subject `method.REGISTER`** |

---

## 1. 硬边界

1. **不得**把实现选择表述为协议要求（§0.3 的直接推论）
2. **不得**把 source 与 traffic 当作彼此的独立证人（D27）
3. 独立 Hub fact **必须**标记来源实现（liveMedia），不得冒充协议事实
4. provenance 轨**不得** import `core.fused.*`（同 traffic 侧约束）
5. 第 3 档形态按 R-1~R-5 抽取，判不出者标 `NEEDS_REVIEW`，**不臆造**
6. 分流判据**不得**在实现期逐条重裁（结论须落盘，见 §5）

---

## 2. 源语料形态

> 勘察确认（`guard/audit/step_source_recon/corpus_shape.txt`）

```
kb/协议实现源码/       9 文件 / 271 KB / 6287 行
  .cpp 5 / .hh 4，扁平，0 子目录
  无 manifest / 无索引 / 无 README / 无测试用例
来源：LIVE555 liveMedia（LGPL, Live Networks, 1996-2026）
与 traffic 同源（traffic 的 client.log 含 openRTSP LIVE555 v2026.04.01）
```

### 2.1 代码形态三档（A3 实测）

| 档 | 特征 | 行数 / 分支 |
|---|---|---|
| 第 1 档 常量响应 | 单行字面量 | 1–6 行 / 0 分支 |
| 第 2 档 静态协议逻辑 | 条件来自请求参数 | 5–27 行 / 0–5 分支 |
| 第 3 档 运行时状态依赖 | 读 `fStreamStates[]` / `getCurrentNPT()` | 18–258 行 / 2–50 分支 |

**最锐利分界：主体方法常量响应 0/6**（错误路径是 5/6）。

### 2.2 Hub 侧现状

- `derived/per_source/source/`：**空目录**（已接入目录，未产出）
- `derived/hub/facts` 中 `source_type=source`：**0 条**
- `build_hub.py` 的 `KNOWN_SOURCES` **已含** `"source"`
- `extractor_dispatcher.py:400` **已含** `"source"` 在允许集合

⟹ 调度路径已预留，缺 extractor 实现。
**「0 facts」≠「语义上不存在」**（agent_rules 原则）。

---

## 3. 知识分组（候选，未裁定）

> **未填实。** 以下是基于 A/B/C 三步实测的**候选分组**，
> 每组的最终成员、抽取粒度、契约条款待逐组讨论。

### 3.0 分组总表（已裁定）

| 组 | 范围 | 实测机械化 | 轨道 | 依赖 |
|---|---|---|---|---|
| **S-M** 方法级 | `handleCmd_<METHOD>` 的覆盖范围 | ✅ 100% | provenance（D24） | — |
| **S-E** 错误响应级 | `setRTSPResponse("<code>")` + 触发条件 | ✅ 100% | provenance（L2） | — |
| **S-PH** 参数处理级 | Range / Scale / Transport 解析规则 | ⚠ **部分**（基类不可抽） | provenance | 边界已收窄（D33） |
| **S-EX** 扩展级 | REGISTER 等非 RFC 方法 | ✅ 100% | **hub_fact**（D24/D32） | Hub subject **已落地**（D34） |

> **S-SM 状态机组已剔除**（D33 / §9 问题 8 裁定确认）：
> 全语料 `sessionstate` / `statemachine` / `playing` / `paused` 均 **0 处**；
> `fStreamStates`（46 处）是**流数组索引**不是状态机
> ⟹ 语料内无可抽取对象。**5 组 → 4 组**。

### 3.1 S-M 方法级

```
实测：RTSPServer.cpp 有 19 个 handleCmd_* 定义
  方法处理器 13 / 错误路径 6
映射：BASE ∈ Hub rfc method 池 → provenance；否则 → hub_fact（D28 L1）
特例：handleCmd_redirect 的 BASE 归一为 REDIRECT（小写）
```

**待裁定**：每个方法处理器产出几条 observation？
（本方法有 24 条 if 分支，逐条产出还是整函数产出一条？）

### 3.2 S-E 错误响应级

```
实测：setRTSPResponse 常量点 5 个码
  200×2 / 401 / 404×2 / 454 / 461
RFC 基准：6 个码全部合规（§4.2 of source_source_design.md）
判定：<code> ∈ RFC 2326 状态码集 → provenance（D28 L2）
```

**待裁定**：错误响应 observation 的 anchor 用什么？
`setRTSPResponse` 调用点所属函数，还是错误路径函数本身？

### 3.3 S-SM 状态机级 ❌ **已探查：不可抽取，建议剔除**

> 2026-10-05 探查结论（关闭原 §9 问题 3）

```
全语料关键词计数（大小写不敏感）：
  sessionstate   0 处      ← 没有任何状态机抽象
  statemachine   0 处
  playing        0 处
  paused         0 处
  fstreamstates 46 处      ← 但这是「流数组索引」，不是状态机
```

`fStreamStates[i].subsession / .streamToken` 是**并发流的句柄数组**，
liveMedia 的 RTSP session **不是显式状态机**——没有 state 变量、
没有 transition 表、没有状态枚举。

⟹ **S-SM 组在 9 文件语料内没有可抽取的对象。**
   liveMedia 的 RTSP 会话状态隐含在「stream 是否存在」里，
   不存在显式的状态转移规则可供抽取。

**建议（待裁定）**：**剔除 S-SM 组**，5 组变 4 组。
理由：抽取不出 ⟹ 无 Contract 可写 ⟹ 无 fact 可产。
**注意**：这**不是**「liveMedia 没有状态机语义」，
而是「该语义不以可抽取的形式存在于本语料」。
若将来语料补全（纳入 `RTSPClientSession` 的完整定义），本组可重新评估。

### 3.4 S-PH 参数处理级 ✅ **已探查：可抽取**

> 2026-10-05 探查结论（关闭原 §9 问题 4）

关键解析函数的**定义位置**（不在基类，全部在 9 文件语料内）：

| 函数 | 定义位置 | 说明 |
|---|---|---|
| `parseRangeHeader` | RTSPServer.cpp L284 / RTSPCommon.cpp L55 | Range 头解析 |
| `parseScaleHeader` | RTSPServer.cpp L300 / RTSPCommon.hh L57 | Scale 头解析 |
| `parseTransportParams` | RTSPServer.cpp L1129 / RTSPCommon.cpp L290 | Transport 参数解析 |

⚠ **但** `getCurrentNPT` 与 `parseSessionIdStr` 的定义**不在语料内**
（`getCurrentNPT` 是基类 `Medium`/`ServerMediaSubsession` 的方法）。
⟹ **部分可抽**：

| 抽取单元 | 可抽性 |
|---|---|
| Range / Scale / Transport 的**解析规则** | ✅ 可抽（定义在语料内） |
| NPT 当前值的**计算规则** | ❌ 不可抽（基类） |
| Session ID 的**解析规则** | ❌ 不可抽（不在语料） |

**裁定**：S-PH 组**收窄为「Range / Scale / Transport 解析规则」**，
不覆盖 NPT 计算与 Session ID 解析。

⟹ 这也解释了 §2.2 记载的「语料是子集（基类不在内）」的实际影响：
**基类里的方法不可抽**，这会限制多组的边界。
详见 `设计/source_corpus_capability_profile.md` §4（**85+ 处基类引用、零定义**）。

### 3.5 S-EX 扩展级 —— **当前无 Hub fact 产出**

> **2026-10-05 修订（D40）**：S-EX 的语义归属经查证后**由 hub_fact 轨
> 改为 provenance 轨**。D24 的「混合双轨」结构保留，但**当前无任何组
> 实际走 hub_fact 轨**。

```
实测：handleCmd_REGISTER 3 处定义 / 全语料 59 处
```

**REGISTER 的语义归属查证（回原文，5 条证据一致）**：

| # | 证据来源 | 结果 |
|---|---|---|
| 1 | RFC 2326 全文检索 REGISTER | **6 次命中全是否定**：L70/L994 是「Registering New Option Tags with IANA」小节标题，L991/L996/L4519 是「register the new option / new encodings」动词，L1356 是「registered status codes」形容词。**无一处作为方法定义** |
| 2 | RFC 2326 §10 Methods 小节清单 | **10.1–10.11 共 11 个方法，无 REGISTER 小节** |
| 3 | 与 `subject_registry` 差集 | 差集恰为 `REGISTER`（D34 新增那条） |
| 4 | **IANA「RTSP 2.0 Methods」注册表（RFC 7826）** | 列举 DESCRIBE / GET_PARAMETER / OPTIONS / PAUSE / PLAY / PLAY_NOTIFY / REDIRECT / SETUP / SET_PARAMETER / TEARDOWN，**无 REGISTER** |
| 5 | 专利文献旁证（CN102761550B） | 「表 2 为本发明实施例**增加的** RTSP 方法：REGISTER / POUR」——业界视为私有扩展 |

⟹ **REGISTER 是 implementation extension，不是 protocol-semantic。**

**为何必须走 provenance 而非 hub_fact**：

Hub 的定位是 **protocol-semantic**（`fused_canonical_spec.md` 第一部分：
「数据类 / Canonical Serialization / Hub Candidate Input Contract」）。
「某个私有实现声明自己能处理一个非标准方法」**不是协议语义**，
若进 Hub 会把实现声明冒充为协议事实 —— 正是 §1-1 硬边界禁止的。

**产出**：

```
【服务端定义处】→ provenance observation
    group    = S-EX
    kind     = S-EX.server_definition
    relation = unspecified（§6.1.1：X ∉ RFC 定义域 ⟹ 实现自主选择）
    target_fact_id = None  ← Hub 无对应 fact
    observed  = {method: REGISTER, defined_at: <locator>,
                 rfc_2326_has_method: false}
```

**与 D32 已落盘 subject 的关系（不冲突）**：

D32 在 `subject_registry.json` 加了 `method.REGISTER`，其含义是
**「liveMedia 声明自己支持名为 REGISTER 的方法」** —— 这是**实现事实登记**；
本步判定的是 **「REGISTER 不是 IANA/RFC 标准方法」** —— 这是**标准归属**。

⟹ 二者是不同问题，**subject 登记保留不动**。
   但**不得据此产出 Hub fact**（无 candidateization 规则，也不得为此新增）。

⚠ **D32 前提被部分推翻**：其裁定「REGISTER 需在 Hub 有表示」的前提
（「REGISTER 应进 Hub fact 空间」）经查证**不成立**。D40 显式登记此推翻。

**hub_fact 轨的当前状态**：设计保留（D24 双轨结构），但**无实际使用者**。
触发条件：若将来出现**有标准依据**的 source 侧 protocol 语义
（如某方法被 IANA 正式注册），才重新启用。见 §9 问题 13。

**关于 property**：`existence` 的裁定（§3.5 旧版）在当前判定下**不再适用** ——
无 Hub fact ⟹ 无 property 可言。相关裁定已由 D40 撤回。

### 3.6 S-EX 的「方法定义 vs 调用点」区分规则（§9 问题 11 关闭）

> 2026-10-05 实测裁定

**问题**：REGISTER 在 liveMedia 内既是**服务端接收**（`handleCmd_REGISTER`），
又是**客户端发出**（`RTSPRegisterSender`）。同一方法名如何区分？

**实测证据**：

| 侧 | 位置 | 特征 |
|---|---|---|
| **服务端接收** | `RTSPServer.cpp:914`、`RTSPServerRegister.cpp:226`、`RTSPServer.hh:126/131/190` | 函数名 `handleCmd_REGISTER` |
| **客户端发出** | `RTSPRegisterSender.cpp:93/145/173/223` | `class ... : public RTSPClient` + `sendRequest(new RequestRecord_REGISTER(...))` |

**判定规则（丙，方向 + 调用方向双重判据）**：

```
对含扩展方法名（如 REGISTER）的 code unit：

1. 函数名匹配 ^handleCmd_<METHOD>$        → 【定义】服务端接收该方法
2. 或 所在类的继承链含 public RTSPClient  → 【调用】客户端发出该方法
3. 或 函数体含 sendRequest(... "<METHOD>" ...) → 【调用】客户端发出
4. 其余                                → NEEDS_REVIEW（R-5），不臆造
```

**为何选丙而非甲/乙**：

| 候选 | 判定 |
|---|---|
| 甲 按函数归属（handleCmd_* = 定义） | ❌ 不完备 —— 调用侧函数名不叫 `handleCmd_*`（叫 `sendRequest` / `RequestRecord_REGISTER` 构造），仅凭函数名会漏判 |
| 乙 按代码位置（同文件 = 定义） | ❌ **实测反证**：`handleCmd_REGISTER` 在 `RTSPServer.cpp` 与 `RTSPServerRegister.cpp` **两个文件**都有；`RTSPRegisterSender.cpp` 与 `RTSPServerRegister.cpp` 也都涉及 REGISTER ⟹ 文件边界与角色边界**不对应** |
| **丙 按调用方向** | ✅ 与代码结构一致：`handleCmd_*` 是服务端分派入口；`public RTSPClient` + `sendRequest` 是客户端发出 |

**产出去向**：

```
【定义】处 → 产出 Hub fact（method.REGISTER / existence，D34 已就位）
【调用】处 → 产出 provenance observation（relation 按 §6.1.1 判据）
```

⚠ **不得**把「客户端发出 REGISTER」表述为「liveMedia 支持 REGISTER 方法」——
   发出是**使用**该方法，服务端能处理才是**提供**该方法。
   二者语义不同，落到不同轨。

---

## 4. Rule Contract

> 填实于 2026-10-05（步骤 D）。结构类比 traffic 的 §4.x Primitive Contract，
> 但因 §0.3 的 epistemic 差异，条款内容**未复制**。

### 4.0 通用结构（P1–P8）

| 条款 | 内容 |
|---|---|
| **P1** Primitive Question | 这条规则回答实现的能力边界的哪一部分？ |
| **P2** Input Source Binding | 代码函数体 / header 解析结果 / 常量字面量 |
| **P3** Deterministic Rule | 提取规则（引用 `设计/source_source_design.md` §4.1 L1/L2 与 §4.2b R-1~R-5） |
| **P4** Observability / Conflict Policy | 判不出标 `NEEDS_REVIEW`（R-5），**不臆造** |
| **P5** Output | 产出 observation 的粒度（见 §4.1） |
| **P6** Provenance | `file:line` 级 locator |
| **P7** Downstream Consumers | 分流判据 L1/L2、attachment |
| **P8** Known Limitations | **必须含**：不声称对 RTSP 协议泛化；0 测试用例 ⟹ 无独立验证 |

### 4.1 observation 粒度与 anchor（§9 问题 1 / 2 关闭）

**粒度裁定：函数级，一条分支一条 observation。**

依据（三条独立来源）：

| 来源 | 依据 |
|---|---|
| 分流判据已是函数级 | D28：分流粒度 = 函数级（SETUP 有 3 个函数，DESCRIBE 有 2 个） |
| 形态实测 | 第 1/2 档函数分支少（0–5），整函数一条会丢失分支信息；第 3 档分支多（50），整函数一条无法定位 |
| R-1 原则 | 「看分支条件不看分支体」——条件是**规则的判据**，故分支是自然单位 |

**anchor 裁定：`file:line` 级函数定位 + 分支序号。**

```
anchor = {
  "locator":     "RTSPServer.cpp:1772",     // 函数起点
  "branch_ord":  12,                          // 该函数内第 N 条 if 分支（0-based）
  "symbol":      "handleCmd_PLAY"
}
```

**为何不沿用 traffic 的 `(capture_unit, frame_from, frame_to)`**：
traffic 的 anchor 是**帧区间**（§2.3：契约不能假设一条 message 恒等于一 frame）；
source 的观测单位是**代码位置**，不存在「区间」语义 —— 函数起点 + 分支序号
是代码位置的自然表达。

⚠ **禁止**伪造 `frame_from` / `frame_to`：
   source observation **没有帧概念**，编造帧号会污染 reader 语义。

### 4.2 S-M 方法级 Contract

```
P1: 这个 handler 为哪个 METHOD 实现了哪部分能力边界？
P2: RTSPServer.cpp 的函数体；分支条件中的请求头解析结果
P3: 逐条 if/else-if 分支提取（D28 L1 定轨；R-1/R-2/R-3 判形态）
P4: 分支条件判不出形态 → NEEDS_REVIEW（R-5）
P5: 一条分支一条 observation（§4.1）
P6: file:line + branch_ord（§4.1）
P7: 分流判据 L1；provenance 轨 attachment
P8: ① 不声称对 RTSP 协议泛化
    ② 0 测试用例 ⟹ 无独立验证（Capability Profile §2）
    ③ 基类方法不可抽（Capability Profile §4）
    ④ 本语料仅 5 个方法有 traffic 观测，其余方法的实现能力**未被任何观测交叉检验**
```

### 4.3 S-E 错误响应级 Contract

```
P1: 这个错误响应对应哪个状态码、在什么条件下返回？
P2: setRTSPResponse("<code> <reason>") 常量字面量
P3: 提取 code → 查 RFC 2326 基准（D28 L2）
    ∈ 基准 → provenance；∉ 基准 → hub_fact
P4: 参数不是字面量而是变量 → 人工裁定（本批 0 例）
P5: 一处 setRTSPResponse 常量一条 observation
P6: file:line（调用点）
P7: 分流判据 L2
P8: ① liveMedia 实测 6 码全部合规（零协议偏离，D30）
    ② **但零偏离 ≠ 覆盖完整**（Capability Profile §3.5）
       不得读成「实现完备」
    ③ 本语料只出现 6 个码，其余 RFC 码未被该实现触发 ⟹ 不代表不支持
```

### 4.4 S-PH 参数处理级 Contract

```
P1: 该参数解析规则如何把 header 文本转成结构化值？
P2: RTSPCommon.cpp / RTSPServer.cpp 的解析函数体
P3: 逐条分支提取（Range / Scale / Transport 三类）
P4: NEEDS_REVIEW（R-5）
P5: 一条分支一条 observation
P6: file:line + branch_ord
P7: provenance 轨
P8: ① **仅覆盖 Range / Scale / Transport**
    ② **不覆盖** NPT 计算与 Session ID 解析（基类不可抽，§3.4）
    ③ 解析规则的正确性无 oracle 可验（0 测试）
```

### 4.5 S-EX 扩展级 Contract

```
P1: 这个非 RFC 方法提供了什么 RFC 未定义的能力？
P2: handleCmd_REGISTER 的 3 处定义 + 全语料 59 处引用
P3: 提取「方法定义」与「调用点」的区分 —— 定义产 fact，调用产 provenance
P4: 无法区分定义/调用 → NEEDS_REVIEW
P5: 定义处一条 Hub fact；调用点处 provenance observation
P6: file:line
P7: hub_fact 轨（进 Hub）；调用点走 provenance 轨
P8: ① **单一实现**的扩展，不代表其他实现（Capability Profile §3.4）
    ② REGISTER 59 处中「定义 vs 调用」的划分规则本身是实现决定，
       不得表述为协议要求
    ③ **D40 查证**：REGISTER 经 RFC 2326 全文（6 次命中全为动词/流程）、
       §10 方法清单（11 个，无 REGISTER 小节）、**IANA RFC 7826 方法注册表**
       三重查证，确认为 **implementation extension**，非 protocol-semantic
    ④ **不得**产出 Hub fact —— 私有实现的自我声明不是协议语义，
       产出会把实现声明冒充协议事实（违反 §1-1 / I-1）
```

---

## 5. Fact Key 投影规则

### 5.1 provenance 轨

```
StructuralObservation（source 语义）—— 不落 Hub
  observed 记录「实现如何响应某种输入」（规范性）
  anchor  = {locator, branch_ord, symbol}（§4.1）
  ⚠ 与 traffic 的 observed 语义不同（§0.3），schema 必须分开
```

### 5.2 hub_fact 轨（仅 S-EX 组）
  ⚠ **当前无使用者（D40）**：REGISTER 经查证为 implementation extension，
  走 provenance 轨 ⟹ 本节描述的 hub_fact 路径**暂无实际使用者**。
  重新启用的触发条件见 §9 问题 13。

```
走 core/source_hub/ → core/extractors/ → candidateization → fusion
产出 ProtocolNorm，映射到 Hub fact：

  fact_id    由 fusion 依 canonical 规则生成（不预指定）
  fact_key.kind     = method
  fact_key.subject  = method.REGISTER
    fact_key.property = （D40 后 **不适用** —— 无 Hub fact ⟹ 无 property）
  assertion.value   = true               （该实现支持此方法）
  modality          = must / normative  （由 candidateization 依 registry 定）

✅ subject 已落地（D34）；property / assertion 属实现阶段
```

⚠ **不得**为 REGISTER 产出 `observed_*` 类 property：
   语料无运行数据（Capability Profile §2）。

---

## 6. Provenance Interface 接口

### 6.1 relation 词表（§9 问题 6 关闭）

**裁定：source 侧独立定义 relation 词表，不沿用 traffic 的。**

依据（回契约原文实测）：

| 事实 | 来源 |
|---|---|
| traffic 的 `CORROBORATION_RELATION_DOMAIN` 是 **Lane A 侧自有** | 实测 `core/fused/models.py` 命中 **0 处**（D16 守住） |
| Hub 侧另有 `ALIGNMENT_RELATION_DOMAIN`（7 值） | `core/fused/models.py` 实测：supports / compatible / contradicts / deviates / refines / insufficient / not_comparable |

⟹ **两层关系词表本就分离**：
- Hub 的 `ALIGNMENT_RELATION_DOMAIN` 是 **Phase B 对齐**用的（fact 间）
- traffic 的 `CORROBORATION_RELATION_DOMAIN` 是 **Lane A provenance** 用的（observation → fact）

source 侧的 relation 表达「实现选择 vs 规范要求」，与两者语义都不同 ⟹ 独立定义。

**词表**：

```
SOURCE_PROVENANCE_RELATION_DOMAIN = {
    conforms_to_spec,     # 实现遵循规范
    deviates_from_spec,   # 实现偏离规范（需指明 RFC 条款）
    unspecified,          # 规范未覆盖，实现自主选择
    no_target,            # 无可对齐的 target（同 traffic §3.4）
}
```

**不写入 `core/fused/models.py`**（沿 D16 的做法，避免触发 Schema Version Upgrade）。

### 6.1.1 四值逐值判据（填实于 2026-10-05，关闭 §9 问题 10）

**判据基准的选择**：

| | traffic | source |
|---|---|---|
| relation 表达的关系 | 观察值 ↔ **既有 fact 的 assertion 值** | 实现选择 ↔ **RFC 2326 规范条款** |
| 客体是什么 | Hub 里已存在的断言 | 规范原文（**语料之外**） |

⟹ 判据基准必须换：traffic 比的是「两个数据」，source 比的是
「语料内的代码」与「语料外的规范」。这是两层语义的根本差异（§0.3）。

**逐值判据**：

| relation | 判据（可机械化） | 需要的数据 |
|---|---|---|
| `conforms_to_spec` | 该分支处理对象 X ∈ RFC 2326 定义域，**且**分支返回值/行为与该域的规范条款一致 | RFC 状态码基准 + RFC 方法/header 语义 |
| `deviates_from_spec` | 存在 RFC 条款规定值 A，但该分支返回/使用值 B ≠ A，**且** B 在 RFC 中未定义 | RFC 基准集 + 代码常量 |
| `unspecified` | X ∉ RFC 2326 定义域（RFC 全文检索 0 命中），**且**该行为是实现自主选择 | RFC 全文检索 |
| `no_target` | 该 code unit 按 D28 L1/L2 判定为无 Hub target | 分流判据结果 |

**「RFC 定义域」的机械化判定**：

```
给定处理对象 X（方法名 / 状态码 / header 名）：

1. 查 kb/spec/rfc2326.txt 全文：
   - X 命中 ≥1 处且**为方法/状态码/header 的定义用法**
        → X ∈ RFC 域
   - X 命中 0 处  → X ∉ RFC 域
2. 命中但**仅为动词/散文用法**
   （如 REGISTER 的 "register ... with the IANA"）
        → X ∉ RFC 方法域（prose hit，须人工确认）
3. 命中为 3 位状态码且在 §11 或 HTTP 复用码内 → X ∈ RFC 域
```

⚠ **第 2 步是已知的人工兜底** —— 本批实测 REGISTER 正是此情形
（rfc2326.txt 命中 2 次，均为动词）。故 `unspecified` 的判定
**对 prose hit 类输入需人工确认**，这属 §4.4 已声明的人工裁定范围。

**四值的划分结构**：

```
X ∈ RFC 域 ─┬─ 行为与规范一致  → conforms_to_spec
            └─ 行为与规范不一致 → deviates_from_spec

X ∉ RFC 域 ──→ unspecified

no_target ── 独立维度：该 code unit 无可对齐的 Hub fact
             （与上三者正交，非互斥）
```

⟹ 与 traffic 同构（traffic 的 `no_target` 也是正交维度，见其 §4.4），
但前三维的**划分依据不同**：traffic 按「观察值与 assertion 是否相容」，
source 按「X 是否在 RFC 域内 + 行为是否与规范一致」。

### 6.1.2 与 traffic 侧四值的语义对照

| traffic | source | 关系 |
|---|---|---|
| `corroborates` | `conforms_to_spec` | 都表示「与既有基准相容」，基准不同 |
| `contradicts` | `deviates_from_spec` | 都表示「与基准冲突」，冲突对象不同 |
| `insufficient` | **无对应值** | traffic 需要它（证据不足以判断相容性）；source 不需要 —— 「X 在不在 RFC 域」是**可判定的**（全文检索） |
| `no_target` | `no_target` | **语义相同**，正交维度 |
| — | `unspecified` | traffic 无对应 —— traffic 的 observation 不与「规范域」比较 |

⚠ **source 侧不含 `insufficient`，这是推导结果不是设计偏好**：
「X ∈ RFC 域吗」是确定性检索问题，不存在证据不足的情形。
若出现检索不确定的输入（§6.1.1 第 2 步的 prose hit），
处理方式是**人工确认后落入三值之一**，而非新增第四个不确定值。

### 6.1.3 判据 6 核对

**满足**。四值均有：可机械化的判据 / 不依赖 corpus 常量
（基准是 RFC 原文而非语料统计）/ 与 source 语料特性一致
（§4.2b R-1~R-5 在此复用）。

已知限制：prose hit 类输入需人工确认（§6.1.1 第 2 步）。
属 §4.4 已声明的人工裁定范围，**不影响判据 6 通过**。

### 6.2 与 traffic provenance 接口的关系

| | traffic | source |
|---|---|---|
| relation 词表 | `CORROBORATION_RELATION_DOMAIN`（4 值，D16） | `SOURCE_PROVENANCE_RELATION_DOMAIN`（4 值候选，**独立**） |
| anchor | `(capture_unit, frame_from, frame_to)` 帧区间 | `{locator, branch_ord, symbol}` 代码位置 |
| 写入 Hub | 否 | 否（provenance 轨） |
| schema | `StructuralObservation` | **独立 schema**（§0.3：observed 语义不同） |

---

## 7. 与 traffic Lane A 的差异

| 维度 | traffic Lane A | source Lane A |
|---|---|---|
| 记录对象 | 协议交互**实际发生** | 实现**如何响应输入** |
| epistemic | 观察性 | 规范性 |
| 轨道 | 单一（PROVENANCE-ONLY） | **双轨**（D24） |
| 分流判据 | 无（全部 provenance） | L1 / L2（D28） |
| relation 词表 | 已定义（D16） | **待定**（§6.1） |
| 独立证人 | 有（client.log） | **无** |
| 语料互证 | — | **禁止**（同源，D27） |

---

## 8. Invariants

> **待逐条填实。** 以下为候选：

| # | Invariant | 依据 |
|---|---|---|
| I-1 | 任何 source observation 不得声称「协议要求如此」，只能声称「该实现如此」 | §1-1 |
| I-2 | source 与 traffic 的 observation 不得互相作为验证依据 | D27 |
| I-3 | provenance 轨的 observation 不得出现在任何 `Claim.evidence` 内 | 同 traffic 侧 §3.2 的**相同**约束（但用 source 侧自己的 validator，见 D32 备注） |
| I-4 | 第 3 档形态按 R-1~R-5 抽取；判不出必标 `NEEDS_REVIEW` | §1-5 |
| I-5 | 分流结论落盘且带 `rfc_pool_version`，可检出过期 | D28 §4.3 |
| I-6 | 归一化禁用通用 `split("_")` | D28（D29 教训） |

---

## 9. Open Questions

> 2026-10-05 更新：原 7 项全部处置。新登记待细化项。
> 2026-10-06 更新：新增问题 14（S-EX 客户端侧符号表，首次落盘实测暴露）。

| # | 问题 | 状态 |
|---|---|---|
| ~~1~~ | ~~S-M 每条方法处理器产出几条 observation？~~ | **✅ 裁定**：**函数级，一条分支一条**（§4.1）。三条独立依据：分流判据已函数级 / 形态实测（分支 0–50）/ R-1 |
| ~~2~~ | ~~S-E 的 anchor 用调用点还是错误路径函数？~~ | **✅ 裁定**：`file:line` 级 + 分支序号，**不沿用 traffic 的帧区间**（§4.1）。source 无帧概念，禁止伪造 `frame_from` |
| ~~3~~ | ~~S-SM 能否抽取？~~ | **✅ 剔除**（D33） |
| ~~4~~ | ~~S-PH 函数定义是否在语料内？~~ | **✅ 部分可抽**，组边界已收窄（§3.4） |
| ~~5~~ | ~~`method.REGISTER` 用哪个 property？~~ | **✅ 曾裁定 `existence`；D40 已撤回** —— 查证 REGISTER 非 protocol-semantic ⟹ 无 Hub fact ⟹ 无 property 可言（§3.5） |
| ~~6~~ | ~~relation 词表是否独立？~~ | **✅ 裁定独立定义**（§6.1）。依据：traffic 的词表未写入 Hub（D16 守住），两层词表本就分离 |
| ~~7~~ | ~~Hub 侧加 subject 的授权~~ | **✅ 已落地**（D34），但见问题 13 —— subject 登记保留，**不得据此产 Hub fact** |
| ~~8~~ | ~~确认剔除 S-SM~~ | **✅ 已确认**（§3.0），5 组 → 4 组 |
| ~~9~~ | ~~「基类方法不可抽」登记为 Capability 限制？~~ | **✅ 已建档**：`设计/source_corpus_capability_profile.md` §4（85+ 处基类引用、零定义） |
| ~~10~~ | ~~`SOURCE_PROVENANCE_RELATION_DOMAIN` 逐值判据~~ | **✅ 已论证**（§6.1.1 + §6.1.2）。四值均基于 RFC 2326 全文检索，不依赖 corpus 常量 |
| ~~11~~ | ~~S-EX「方法定义 vs 调用点」区分规则~~ | **✅ 已裁定**（§3.6）。选「丙 按调用方向」：`handleCmd_*` = 服务端定义；`public RTSPClient` + `sendRequest` = 客户端调用。甲/乙 已实测反证 |
| ~~12~~ | ~~`test_subject_canonical_lists` 计数断言~~ | **✅ 已修**（2026-10-05）：`11` → `12`，保留字面量 + 注释 |
| **14** | **S-EX 客户端调用侧的符号表是什么？** | **新增**（D44，2026-10-06）。首次落盘实测：`S-EX.client_invocation` 产出 **0** —— `writer.is_client_invocation` 分支的**前置条件永不成立**。根因：`RTSPRegisterSender.cpp` 产出 **0 个函数单元**（`sendRegister` 等客户端符号**不匹配任何模式**）⟹ 该分支为**不可达代码**。§3.6 判定规则 3 只给了**语义**（`public RTSPClient` + `sendRequest`），**未给符号表** ⟹ 属契约级缺口。⚠ **C-1 要求两侧分别产出，当前仅服务端侧落地** —— 客户端侧缺失 = C-1 的**一半尚未实现**。待补符号表后重跑验证 |
| **13** | **hub_fact 轨何时重新启用？** | **新增**（D40）。当前**无任何组实际走 hub_fact 轨** —— REGISTER 经查证为 implementation extension。触发条件：出现**有标准依据**（IANA 正式注册等）的 source 侧 protocol 语义。见 §3.5 |

**因 D40 而变更的契约**：§10 判据 8 的表述（「除 S-EX」）需更新 ——
当前**所有 4 组均走 provenance 轨**，无例外。

---

## 10. Freeze Criteria

> 2026-10-05 重核（步骤 D：判据 6 经 §6.1.1 填实后通过）

| # | 判据 | 结果 | 依据 |
|---|---|---|---|
| 1 | 每个知识组的成员清单完整 | **PASS** | 4 组，成员见 §3.1–§3.5 |
| 2 | 每组完成 Rule Contract（P1–P8） | **PASS** | §4.2–§4.5 |
| 3 | 每组的 observation 粒度明确 | **PASS** | §4.1：函数级，一条分支一条（D35） |
| 4 | 每组声明 Known Limitations，含「不声称对 RTSP 协议泛化」 | **PASS** | §4.2–§4.5 各 P8 |
| 5 | §3.3/§3.4 已勘察并给出可抽/不可抽结论 | **PASS** | S-SM 剔除（D33）/ S-PH 收窄 |
| 6 | relation 词表完成逐值语义论证 | **PASS** | §6.1.1 四值判据 + §6.1.2 与 traffic 对照 |
| 7 | 与 traffic provenance interface 的关系明确 | **PASS** | §6.2 |
| 8 | 不产生 Hub Candidate（除 S-EX） | **PASS** | §5.1。**D40 后修订**：当前 **4 组全部走 provenance 轨，无例外** —— S-EX 亦已改轨（§3.5） |

**8 / 8 全部 PASS。**

判据 6 的填实要点：
- 四值判据均基于 **RFC 2326 原文全文检索**（可机械化）
- **不依赖 corpus 常量**（基准是规范原文，非语料统计）
- source 侧**不含 `insufficient`** —— 「X ∈ RFC 域吗」是确定性检索问题，
  推导结果而非设计偏好（§6.1.2）
- 已知限制：prose hit 类输入需人工确认（§6.1.1 第 2 步），
  属 §4.4 已声明范围，不影响判据通过

---

## 11. 下一步

Rule Set 已 **Final Frozen**。后续：

1. ~~实现 `core/source_a/`（provenance 轨）~~ → **2026-10-06 已实现并首次落盘**
   （22 个函数单元 / 4 组 / 43 条 observation，`derived/source/`，
   幂等与只读区零变化均已验证，D43）
2. 实现时须固化 §8 的 I-6：禁止通用 `split("_")`（D28 教训）→ **已固化**
   （`tests/source_a/test_i6_no_generic_underscore_split.py` AST 级强制）
3. 落地 §6.1.1 的 RFC 全文检索工具
4. ~~Hub 侧 `method.REGISTER` fact 的实际抽取~~ →
   **已由 D40 撤回**：REGISTER 为 implementation extension，
   **不产 Hub fact**；hub_fact 轨重新启用条件见 §9 问题 13
5. **补齐 §9 问题 14 的客户端侧符号表** —— 当前 C-1 只落地了服务端侧

---

*本文件 2026-10-05 新建，同日完成 §3–§6 填实与 §10 全判据通过。*
*状态：Final Frozen。*
*§9 剩余项：问题 10 / 11 已关闭；问题 12（计数断言）已修复并关闭；问题 13 / 14 待触发。*
*2026-10-06：`core/source_a/` 实现完成，provenance 轨**首次持久化落盘**（D43）。*
