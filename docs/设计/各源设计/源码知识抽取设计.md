# 从协议实现源码提取种子生成知识 — 技术方案

> 目标：仅凭 `kb/协议实现源码/RTSPServer.cpp`，提取出种子生成所需的【状态机、字段、消息类型、字段取值】，
> 使单源码源也能支撑三层选择器生成有效种子（当前单源码源只能提取"方法清单"，生成 0 条种子）。

---

## 一、问题定位（为什么当前源码源"不够"）

当前 `source` 源（`handlecmd_server_definition`）只提取了「方法定义处」（10 个 `handleCmd_XXX` 函数名 + 文件行号），
**没有提取**种子生成必需的三类知识：

| 种子生成所需 | 现状 | 缺什么 |
|---|---|---|
| 方法清单 | ✅ 10 方法 | — |
| 状态机 transitions | ❌ 0 | 方法间的状态转移（DESCRIBE→SETUP→PLAY…）|
| 字段 headers | ❌ 0 | Transport/Session/CSeq 等头部字段 + 取值 |

## 二、技术综述（检索到的相关方法）

### 1. ProtocolGPT（最匹配，LLM 从源码推断状态机）⭐ 推荐
- 论文：*Inferring State Machine from the Protocol Implementation via Large Language Model*（USENIX Security / arXiv 2405.00393）
- **核心**：用 LLM + RAG 从协议实现源码推断 FSM（状态、消息类型、状态转移）
- 方法：① 从源码隔离 FSM 相关代码 → ② 分割成片段 → ③ 转向量存储（RAG 增强 LLM）→ ④ CoT（思维链）+ BAP（背景增强提示）引导 LLM 推断状态/消息类型/转移
- 评估：6 协议（IKEv2/TLS1.3/TLS1.2/BGP/**RTSP**/L2TP），精度 >90%，比 baseline 提升 >30% 精度、>55% 召回；集成 AFLNet 后覆盖率 +20%，发现 2 个 0-day
- **为什么适合你**：你已有 LLM（DeepSeek）+ RAG 基础设施（知识中枢），RTSP 是文本协议（方法名/字段名/状态都是可读文本），LLM 能直接理解

### 2. STCFuzz（静态分析状态变量 + 消息类型）
- 论文：*Fuzzing for Stateful Protocol Programs Based on Constraints between States and Message Types*
- 核心：静态分析识别【状态变量】（如 `protocol_state`）+【消息类型变量】（如 `msg_type`），提取状态转移 + 状态-消息约束，LLM 生成新消息类型
- 适合：结构化、有明显状态变量的实现（live555 的 `fSessionState`、`fStreamStates` 就是状态变量）

### 3. StateLifter（静态循环分析提取消息格式状态机）
- 论文：*Extracting Protocol Format as State Machine via Controlled Static Loop Analysis*（USENIX Security 2023）
- 核心：把解析循环的每次迭代当状态、迭代间依赖当转移，静态提取消息格式 FSM
- 局限：针对"循环+FSM"解析的**二进制协议**（ce-regex），对 RTSP 这种字符串解析的文本协议不直接适用

### 4. APFuzz（状态变量学习 = 静态 + 动态）
- 论文：*APFuzz: Towards Automatic Greybox Protocol Fuzzing*
- 核心：静态分析识别候选状态变量 + 轻量动态分析过滤噪声，自动状态跟踪
- 适合：状态变量识别（作为 ProtocolGPT 的补充/校验）

## 三、推荐方案：LLM + RAG 源码分析（ProtocolGPT 思路，针对 RTSP 定制）

### 提取流水线

```
kb/协议实现源码/RTSPServer.cpp（+ RTSPCommon.cpp）
        │
        │ ① 源码预处理：按"状态相关/字段相关/方法分发"切分代码片段
        ▼
        │ ② RAG 检索：片段向量化，检索"状态机/字段/方法"相关片段
        ▼
        │ ③ LLM 推断（CoT + BAP）：
        │    a. 方法清单（handleCmd_XXX）
        │    b. 状态机（状态变量 + 方法转移）
        │    c. 字段（字符串字面量 + 解析函数）
        ▼
        │ ④ 结构化落盘（六元组 fact）：
        │    method/state/transition/header fact
        ▼
知识中枢 derived/model/per_source/source/facts/（补充 transition + header aspect）
```

### 针对 live555 的三个提取点

**A. 状态机（transition）**
- live555 的状态变量：`RTSPServer::RTSPClientSession` 的字段（`fSessionState`、`fStreamStates`、`fOurServerMediaSession` 等）
- 方法处理函数：`handleCmd_DESCRIBE/SETUP/PLAY/PAUSE/TEARDOWN` 里对这些状态字段的读/写
- LLM 推断：每个方法的前置状态 + 后置状态（如 SETUP 需在 DESCRIBE 之后、PLAY 需在 SETUP 之后）

**B. 字段（header）**
- 字符串字面量：`"Transport"`、`"Session"`、`"CSeq"`、`"Accept"`、`"Range"`、`"User-Agent"`、`"Content-Length"` 等
- 解析函数：`parseTransportHeader`、`parseSessionHeader`、`parseRangeHeader`、`parseCSeq`
- LLM 推断：字段语义 + 取值格式（如 Transport 的 `RTP/AVP;unicast;client_port=...`）

**C. 消息类型（方法）**
- 已有（handleCmd_XXX），但可补 LLM 推断的"方法语义"（如 SETUP 建立会话、PLAY 开始播放）

## 四、与现有知识中枢的集成

现有 `source_norm_to_facts` 只产 `method + definition` fact。扩展为：

| 新增 aspect | 从源码提取 | 进 bundle 的哪个桶 |
|---|---|---|
| `transition` | LLM 推断的状态转移 | `bundle["transitions"]` |
| `header` | 字符串字面量 + 解析函数 | `bundle["headers"]` |
| `value_enum` | 字段取值格式 | `bundle["headers"][name]["values"]` |

这样 `transitions`/`headers` 非空后，三层选择器的①结构覆盖（edge_cover）和②通用危险（generic_danger）就能工作了。

## 五、实现步骤（分阶段）

1. **快速验证（字段字面量提取）**：正则扫描源码的字符串字面量（`"Transport"` 等），直接产出 header fact——这个零成本，先跑通"有字段知识"；
2. **LLM 状态机推断（ProtocolGPT 思路）**：写 `core/fused/source_fsm.py`，把 RTSPServer.cpp 按函数切分，调 DeepSeek 推断状态机（transition fact），CoT 提示；
3. **集成回 source 源**：`source_norm_to_facts` 或新抽取器产出 transition/header/value_enum fact，进 bundle；
4. **验证**：`build_hub --sources source` 后，`bundle["transitions"]`/`["headers"]` 非空，`run_seedgen --three-layer` 能生成种子。

## 六、参考文献

1. ProtocolGPT — *Inferring State Machine from the Protocol Implementation via LLM*（arXiv 2405.00393）
2. STCFuzz — *Fuzzing for Stateful Protocol Programs Based on Constraints between States and Message Types*（ACM 2025）
3. StateLifter — *Extracting Protocol Format as State Machine via Controlled Static Loop Analysis*（USENIX Security 2023）
4. APFuzz — *Towards Automatic Greybox Protocol Fuzzing*（arXiv 2602.21892）
