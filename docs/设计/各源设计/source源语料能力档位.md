# docs/设计/各源设计/source源语料能力档位.md — Source 语料能力档案

> 状态：**ACTIVE**（2026-10-05 新建）
> 来源：`local/backup/step_source_recon/`（只读勘察）、`step_source_a/`、`step_source_a2/`
> 范围：**current source corpus empirical capability**
> **非** Hub Contract capability（Hub 侧能力见 `fused_hub/docs/`）
> 参照：`docs/设计/各源设计/traffic源语料能力档位.md`（结构类比，内容不复制）

**本档案的作用**：记录**当前语料能支撑什么、不能支撑什么**，
使后续 Rule Set 的组边界有据可依，并防止「实现选择」被读成「协议要求」。

---

## 0. Authority Boundary

| 项 | 归属 |
|---|---|
| 本档案 | **仅记录语料事实**，不是设计真源 |
| 设计真源 | `docs/设计/各源设计/第五源设计.md`、`docs/设计/各源设计/source源规则集设计.md` |
| 契约真源 | `fused_hub/docs/fused_registry_v1.md`、`fused_hub/schema/v1/*.json` |
| Hub 能力 | **不在本档案范围**（Hub 侧能力是 Hub Contract 的事） |

⚠ 本档案**不得**被引用为「协议要求」的依据。
它只能支撑「**该实现如此**」的陈述（D33 / §1-1）。

---

## 1. Current Corpus Snapshot

```
路径        kb/协议实现源码/
结构        扁平，9 文件，0 子目录
规模        9 文件 / 271,249 B / 6,287 行
类型        .cpp 5 / .hh 4（无 .py / .c / 测试文件）
索引        无 manifest / 无索引 / 无 README / 无 LICENSE
测试        **0 个**（无 gtest / Catch2 / doctest / TEST() / assert()）
来源        LIVE555 liveMedia（LGPL, Live Networks, Inc., 1996-2026）
版本        2026-04-01（由 traffic 语料 client.log 的
            "openRTSP (LIVE555 Streaming Media v2026.04.01)" 推定）
```

### 1.1 与 traffic 的同源关系

traffic 语料的 `client.log` 内含
`openRTSP (LIVE555 Streaming Media v2026.04.01)`。

⟹ **source 与 traffic 是同一实现**（D27）。

**后果**：两者**不得互为独立证人**。
traffic D9 §4.5 P8-1 已冻结「同源生成器非独立证人」，本档案直接引用。

### 1.2 语料身份

- **实现数 = 1**（liveMedia）
- **无版本变体**：语料内无 version 标记 / 无编译配置 / 无 feature flag
- **无多次观测**：同一实现只有一份快照

⟹ 这三点是 D25「不需要独立 D9」的依据。

---

## 2. Capability Matrix

| Capability | Status | Evidence |
|---|---|---|
| **方法级覆盖** | **STRONG** | 19 个 `handleCmd_*` 定义（13 方法处理器 + 6 错误路径） |
| **错误响应** | **STRONG** | 5 个 `setRTSPResponse("<code>")` 常量点；6 个错误路径函数；6 个状态码全部合规 RFC 2326（D30） |
| **扩展方法** | **STRONG** | REGISTER 59 处 / 7 文件，含完整类层次（`RTSPRegisterSender` / `RTSPDeregisterSender` / `RegisterRequestRecord` / `DeregisterRequestRecord`） |
| **参数处理** | **PARTIAL** | Range / Scale / Transport 解析定义**在语料内**（3 个函数）；NPT 计算与 Session ID 解析**在基类，不可抽**（§4） |
| **状态机** | **NOT ESTABLISHED** | `sessionstate` / `statemachine` / `playing` / `paused` **全语料 0 处**；`fStreamStates` 46 处但那是**流数组索引**不是状态机 |
| **独立验证** | **NOT ESTABLISHED** | 0 个测试用例；无 oracle |

### 2.1 代码形态三档（A3 实测）

| 档 | 特征 | 行数 / 分支 |
|---|---|---|
| 第 1 档 常量响应 | 单行字面量 | 1–6 行 / 0 分支 |
| 第 2 档 静态协议逻辑 | 条件来自请求参数 | 5–27 行 / 0–5 分支 |
| 第 3 档 运行时状态依赖 | 读 `fStreamStates[]` / `getCurrentNPT()` | 18–258 行 / 2–50 分支 |

**最锐利分界**：主体方法常量响应 **0/6**（错误路径是 5/6）。

---

## 3. 已知限制

### 3.1 语料是子集，不是完整可编译工程

无 Makefile、无上游基类。⟹ **不能编译、不能运行**，只能静态分析。

### 3.2 无 validation oracle

0 个测试用例。⟹ **任何抽取结果都无法交叉验证**。
这与 traffic 侧有 `client.log` 作 oracle 形成对比。

⟹ **不得**声称「source 侧的抽取被独立验证过」。

### 3.3 与 traffic 同源

见 §1.1。⟹ source 的抽取**不能**用来印证 traffic 的观测。

### 3.4 单一实现

实现数 = 1（§1.2）。⟹

- **不得**声称「RTSP 实现都如何如何」
- **不得**把 liveMedia 的实现选择读成协议要求
- REGISTER 是 liveMedia 独有能力，**不代表其他实现**

### 3.5 状态码零偏离 ≠ 覆盖完整

liveMedia 实测 6 个状态码全部合规 RFC 2326（D30）。
⟹ **但**这只说明「用了的都对」，**不说明「该支持的都支持了」**。

⚠ **不得**把「零协议偏离」读成「实现完备」。

---

## 4. 系统性约束：语料是子集

> **这是本档案最重要的一节。** D33 勘察发现，它会**系统性限制多个组的抽取边界**。

### 4.1 实证

语料**引用**以下基类，但**一个类定义都没有**：

| 基类 | 引用处数 | 类定义在语料内 |
|---|---|---|
| `UsageEnvironment` | **30** | **否** |
| `ServerMediaSubsession` | **15** | **否** |
| `Source` | **13** | **否** |
| `Medium` | **12** | **否** |
| `GenericMediaServer` | **11** | **否** |
| `RTPInterface` | **4** | **否** |

⟹ **85+ 处基类引用，零定义。**

### 4.2 直接后果

| 抽取对象 | 可抽性 | 原因 |
|---|---|---|
| `parseRangeHeader` / `parseScaleHeader` / `parseTransportParams` | ✅ 可抽 | 定义在 RTSPServer.cpp / RTSPCommon.cpp |
| `getCurrentNPT` | ❌ 不可抽 | 基类 `ServerMediaSubsession` 方法 |
| `parseSessionIdStr` | ❌ 不可抽 | 不在语料内 |
| 状态机转移规则 | ❌ 不可抽 | 语料内无状态抽象（§2 状态机行） |

### 4.3 使用规则

⚠ **不得**把「基类方法不可抽」当作「勘察不充分」——
   **这是语料边界，不是分析遗漏**。重新勘察不会改变结论。

⚠ 语料补全后（纳入 `RTSPClientSession` 等完整定义），
   本节须重新评估并 amend。

---

## 5. 更新规则

| 触发条件 | 动作 |
|---|---|
| 语料扩充（新增文件 / 版本 / 子目录） | **amend §1 §2 §4**，重跑全部关键词计数 |
| 发现新的可抽/不可抽对象 | amend §2 / §4.2 |
| liveMedia 版本升级 | amend §1（版本号），并复核 §3.4 |
| Rule Set 组边界裁定 | 回写本档案对应的 Capability 行 |

**amend 原则**：本档案记录**实测事实**，不记录裁定。
裁定结果写入 Rule Set，本档案只提供依据。

---

## 6. 与其他文档的关系

| 文档 | 关系 |
|---|---|
| `设计/traffic_corpus_capability_profile.md` | **姊妹文档**，同一作用、不同语料。两者都不可引用为「协议要求」依据 |
| `设计/source_source_design.md` | 本档案为其提供 §4 的依据（D33） |
| `设计/source_lane_a_rule_set_design.md` | 本档案为其组边界（§2）提供依据 |
| `设计/traffic_d9_design.md` §4.5 P8-1 | 本档案 §1.1 **引用**其「同源非独立证人」结论 |

---

*本档案为 ACTIVE，2026-10-05 新建。*
*§4 是本档案的核心发现（语料是子集），它限制 Rule Set 的多个组边界。*
*本档案只记录语料事实，不做裁定。*
