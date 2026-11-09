# docs/设计/各源设计/vuln源设计.md — vuln 源 GLMFuzz 本地化适配方案

> 定位：五源深化收尾。参照 GLMFuzz（QRS 2025）「漏洞知识引导的协议 fuzzing」，
> 结合本项目「知识源 → 结构化知识中枢 → 生成初始种子」架构，给出 vuln 源的
> 本地化适配方案（改造目标 / 抽取范围 / 数据模型 / 种子生成 / 本地化改造点 / 流程依赖）。
>
> 落盘日期：2026-10-20
> 上游：`docs/设计/各源设计/vuln源规则集设计.md`（早期 pipeline 时代，已脱节）、
>        `docs/设计/各源设计/vuln源收口设计.md`（claim_class 裁定，已脱节）
> 对标本：rfc→SemFuzz（`docs/设计/抽取与形态/RFC源改造设计.md`）、source→AutoSeeder、
>        traffic→LLM-Boofuzz、expert_note→v3 主观定位

---

## 一、改造目标与背景

### 1.1 现状盘点（vuln 源已有，但缺深化）

| 层 | 现有实现 | 问题 |
|---|---|---|
| 抽取 | `core/fused/vuln.py`：CVE JSON → `security_property` fact（method/field/condition 薄映射，rtsp 53 facts） | 只搬 description 原文，未结构化「漏洞模式」 |
| 下游分类 | `strategy.py::classify_vuln`：CWE/条件关键词 → `action`（`_CWE_ACTION` + `_COND_KEYWORD_ACTION`） | **规则匹配**，覆盖不了规则外的漏洞/协议 |
| 边界 | `boundary_probe.py` 源 B：`action → 边界参数 → 候选 → oracle` | 边界参数 `_ACTION_BOUNDARY` 是**手写硬编码**，仅 6 个 action |

### 1.2 缺什么（GLMFuzz 能补的）

对照其他四源都「借鉴一篇对口文献 + 专门设计」：rfc→SemFuzz、source→AutoSeeder、
traffic→LLM-Boofuzz、expert_note→最终版。vuln 缺三点：

1. **漏洞序列自动补全**：CVE 原文常缺完整 request 序列（实测 `trigger_requests`
   与 `mutation_hints` 大多 `missing`），GLMFuzz 用 LLM 从描述 + 触发条件里补全；
   我们目前只做关键词 action 分类，没做序列/变异提示的补全。
2. **向量化检索**：我们现在是「CWE/关键词 → action」规则匹配；GLMFuzz 是「漏洞
   序列 → 向量库 → 相似性检索」，能覆盖规则未命中的新漏洞、支持**跨协议漏洞知识迁移**。
3. **定向变异（种子语料增强）**：GLMFuzz 在 fuzzing 中做定向变异；我们定位是
   ChatAFL 上游的种子生成器，需把它本地化为「定向变异字典 + 边界种子语料」。

### 1.3 目标

把「历史漏洞 → 触发序列 → 边界种子 + 定向变异语料」这条链**自动化、可检索、可跨协议迁移**，
并落到六元组知识中枢（可溯源），与现有 boundary_probe（源 B）/strategy（漏洞导向）无缝衔接。

---

## 二、GLMFuzz 核心方法提炼与借鉴要点

### 2.1 原方法（从摘要 + 引言提炼）

GLMFuzz 针对状态协议 fuzzing 的两个瓶颈——初始种子质量低 + 变异无法覆盖深状态——
提出三组件：

| 组件 | 作用 |
|---|---|
| **漏洞知识向量库** | 分析历史漏洞序列（含能触发边界条件/异常行为的特殊**状态 + 字段**），构建向量库 |
| **LLM 生成多样初始种子** | 用漏洞知识引导 LLM 生成**接近漏洞边界**的多样种子（不是规范化的标准消息） |
| **定向变异 + 自动 prompt 工程** | fuzzing 中用漏洞序列引导 LLM 定向变异；按 fuzzing 结果动态调 prompt |

关键洞察（对本项目最有价值的）：CHATAFL 的 LLM 会生成「符合规范的标准消息」，反而
**远离**漏洞边界；GLMFuzz 用「漏洞序列」这一先验，把 LLM 往「触发边界条件/异常行为」
方向拽。

### 2.2 借鉴要点（3 条）

1. **「漏洞模式」是一等知识**：把每条历史漏洞结构化成一个「可检索的模式」
   （触发序列 + 触发字段 + 边界动作），而不是散落的 description 文本。
2. **向量检索补规则**：规则（CWE/关键词）打底，向量相似性检索兜底，二者叠加，
   覆盖「规则未命中的新漏洞 / 新协议」。
3. **定向变异落到种子语料**：因为我们是种子生成器（不接管 fuzzing 循环），把
   GLMFuzz 的「定向变异」翻译成「定向变异字典 + 边界种子语料」，交给下游 fuzzer。

---

## 三、整体架构

三层，与现有「知识源 → 结构化中枢 → 种子生成」一一对应：

```
┌─ 阶段一 知识源层（vuln 源深化）──────────────────────────────┐
│  kb/<协议>/历史漏洞/*.json（CVE 结构化）                      │
│    → rule 抽取（case_id/cwe/trigger.method/field/condition） │
│    → LLM 补全（trigger_requests 漏洞序列 + mutation_hints）   │
│    → 漏洞模式 vuln_pattern（结构化）                          │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─ 阶段二 结构化知识中枢（数据模型 + 索引）────────────────────┐
│  六元组 Fact：新增 aspect=vuln_pattern                        │
│    value = {action, trigger_sequence, trigger_field,          │
│              boundary{legal,illegal,dim}, cwe, streams,       │
│              mutation_hint}                                   │
│  存储：derived/per_source/<协议>/vuln/facts/vuln.jsonl        │
│  索引：漏洞模式向量库（复用 source_retrieval 的 embedder）     │
│        —— 支持「新漏洞/新协议 → 相似漏洞模式」检索             │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─ 阶段三 种子生成层（边界种子 + 定向变异语料）────────────────┐
│  漏洞模式 → 边界候选（复用 boundary_probe.generate_candidates）│
│  漏洞模式 → 定向变异字典（复用 boundary_probe.generate_dict）  │
│  质量筛选：validate_seed（结构）+ oracle（dry run 重放）       │
│           + 覆盖率/崩溃反馈（可选 ReAct refine）               │
└───────────────────────────────────────────────────────────────┘
```

---

## 四、阶段一：本地知识源抽取范围与整理方式

### 4.1 抽取范围（CVE JSON → 漏洞模式字段）

从 `kb/<协议>/历史漏洞/*.json` 抽取（已实测字段，见 `RTSP-001.json`）：

| CVE 字段 | 抽取到 vuln_pattern 的哪个 | 说明 |
|---|---|---|
| `scope` | 门禁（`== "seedgen"` 才产） | 沿用现有门禁 |
| `case_id` / `avd_id` | evidence locator | 标识符不进断言 |
| `cwe_avd` | `cwe` | 根因类型（`CWE-416`/`CWE-617`…） |
| `trigger.method.value` | `trigger_sequence` 的锚点 | 方法锚点（如 SETUP） |
| `trigger.field.value` | `trigger_field` | 触发字段（如 track/Transport） |
| `trigger.condition.value` | `mutation_hint` 的素材 | 触发条件（自由文本） |
| `description_raw` | `mutation_hint` 的素材 + evidence quote | 漏洞描述 |
| `trigger_requests`（大多 missing） | **LLM 补全 → `trigger_sequence`** | 完整消息序列 |
| `mutation_hints`（大多 missing） | **LLM 补全 → `mutation_hint`** | 变异提示 |

### 4.2 整理方式：漏洞模式 `vuln_pattern`（结构化定义）

```
vuln_pattern = {
  "action":             "double_setup",        # 边界动作（复用 strategy._ACTION_* 全集）
  "trigger_sequence":   ["DESCRIBE","SETUP","SETUP"],  # 触发消息序列（LLM 补全，可为空→仅锚点）
  "trigger_field":      "track",               # 触发字段（归一化）
  "boundary": {                                 # 边界参数（复用 boundary_probe.BoundaryParam）
     "dim": "track_number",
     "legal": "对不同 track 分别 SETUP",
     "illegal": "对同一 track 连续两次 SETUP"
  },
  "cwe":                "CWE-416",
  "streams":            ["matroskaFileTest"],   # 触发流（复用 strategy._extract_stream_hints）
  "mutation_hint":      "同 track 双 SETUP"      # 变异提示（LLM 补全）
}
```

### 4.3 LLM 补全（核心，对标 GLMFuzz 的「漏洞序列」）

两条缺字段用 LLM 补全（rule 打底 + LLM 补语义，与 rfc 源 SemFuzz 改造同构）：

- **`trigger_sequence` 补全**：给定 `trigger.method`（锚点）+ `condition` + `description`，
  LLM 推断完整触发消息序列（含前置方法），如「SETUP」→ 补全「DESCRIBE→SETUP→SETUP」。
- **`mutation_hint` 补全**：给定 `condition` + `description` + `cwe`，LLM 提炼一条
  「该漏洞靠什么字段/序列的哪类变异触发」，如「同一 track 连续两次 SETUP」。

**降级**：LLM 不可用 → 只保留 rule 抽取的锚点（trigger_sequence=仅锚点方法，
mutation_hint=condition 原文），漏洞模式仍可用（只是向量语义弱一点）。

---

## 五、阶段二：结构化知识中枢的数据模型、存储与索引

### 5.1 数据模型（六元组，新增一个 aspect）

**新增 aspect：`vuln_pattern`**（applicable_subject_types = `["method","header"]`，
epistemic = `descriptive`，authority = `vuln`）。

```
FactKey = {
  subject:   method.SETUP（或 header.transport，取 trigger 主锚点）,
  aspect:    "vuln_pattern",
  condition: always
}
Value(type=struct, data = vuln_pattern)   # 见 §4.2
```

**与已有 aspect 的分工（关键决策）**：

| aspect | 承载 | 来源 | 状态 |
|---|---|---|---|
| `security_property`（已有） | 漏洞描述文本（"这个 subject 有安全后果"） | CVE description 原文 | 保留，薄映射 |
| `vuln_pattern`（新增） | 结构化漏洞模式（"这个 subject 有可触发的模式"） | CVE 结构化 + LLM 补全 | 新增 |
| `legal_boundary`（已有） | oracle 验证后的边界 | boundary_probe 回写 | 保留，作为 vuln_pattern 的**验证出口** |

> 关系：`vuln_pattern` 是「未验证漏洞知识」，`legal_boundary` 是「oracle 验证后的边界」。
> boundary_probe 用 `vuln_pattern` 生成候选，oracle 验证后回写 `legal_boundary`（闭环）。

### 5.2 存储

沿用现有五源 facts 落盘：`derived/per_source/<协议>/vuln/facts/vuln.jsonl`，
每行一个 fact view（与 rfc/source/traffic/expert_note 同构，`load_fact_views` 直接可读）。

### 5.3 索引：漏洞模式向量库（核心新增）

**复用 `source_retrieval.py` 的 embedding 基础设施**（`_build_embedder`：sentence-transformer
优先、n-gram 降级 + `_cosine`），零新依赖。

- **建库**：每条 `vuln_pattern` 拼接语义文本 `f"{action} {boundary.illegal} {mutation_hint} {cwe}"`
  → embedding → 存向量（带 protocol + case_id + fact_id）。
- **检索**：给定「新漏洞描述 / 新协议名」→ embedding → top-k 相似漏洞模式（cosine）。
- **缓存**：`derived/vuln_pattern_vectors/<协议>.json`（对齐 source_blocks_cache 先例）。

**两个检索场景**（这是 GLMFuzz 向量库的本地化落点）：

1. **同协议新 CVE**：新 CVE 描述 → 检索相似历史模式 → 复用其 `boundary` / `action`。
2. **跨协议迁移**（多协议低成本迁移护城河的关键）：新协议无漏洞库 → 检索**其他协议**
   的相似漏洞模式（如 RTSP「同 track 双 SETUP UAF」→ 检索出「重复建立会话」类模式）
   → 迁移生成边界种子，证明「无漏洞先验也能从历史漏洞知识跨协议迁移」。

---

## 六、阶段三：种子生成规则、变异策略、质量筛选

### 6.1 生成规则（漏洞模式 → 边界种子）

复用现有 `boundary_probe.generate_candidates` + `strategy._ACTION_GUIDANCE`：

- 命中 `_ACTION_BOUNDARY` 的 action → 生成「legal（满足边界）/ illegal（违反边界）」候选对；
- 未命中（规则外的漏洞模式）→ 用 `mutation_hint` 引导 LLM 生成「接近该漏洞边界」的合法种子
  （这正是 GLMFuzz「LLM 生成非规范化、接近边界种子」的落点，替代现在的关键词规则分类）。

### 6.2 变异策略（GLMFuzz「定向变异」的本地化）

我们定位是 ChatAFL 上游种子生成器，**不接管 fuzzing 循环**，故「定向变异」落为两类语料：

1. **定向变异字典**：从漏洞模式的 `boundary` + `trigger_field` 自动生成 AFL 字典 token
   （复用 `boundary_probe.generate_dict` 的机制，注入 `track1/track2`、`interleaved=0-1`、
   触发 Session 值等），让 fuzzer 的随机变异**有偏**地向漏洞方向展开。
2. **边界种子语料**：`legal_boundary` 验证通过的「最接近非法仍合法」种子（复用
   `probe_boundary`），让 fuzzer 只需 1~2 次变异即触发。

### 6.3 质量筛选标准（三道闸）

| 闸 | 判定 | 作用 |
|---|---|---|
| ① 结构校验 | `validate_seed`（方法白名单 + 必填头 + 状态转移） | 过滤非法结构 |
| ② oracle 重放 | dry run 重放（复用 VM oracle，多次重放取多数，防 UAF 时序抖动） | 过滤「dry run 即崩」的越界种子 |
| ③ 反馈 refine | 覆盖率/崩溃反馈（可选，ReAct 迭代） | 定向加强未覆盖状态 / 已触发模式 |

---

## 七、本地化改造点对照表及理由

| # | GLMFuzz 原方法 | 本项目本地化 | 理由 |
|---|---|---|---|
| 1 | 漏洞序列 → **纯向量库**（无结构化本体） | 漏洞模式 → **六元组 fact + 向量索引** | 保留「可溯源」核心卖点：向量只是检索手段，fact 才是知识本体（与 GraphRAG 定位一致） |
| 2 | LLM 生成**标准化种子**的缺点 | 用漏洞模式把 LLM **往边界拽** | 同源动机；但我们有 boundary_probe 的合法/非法域先验，比 GLMFuzz 更结构化 |
| 3 | **fuzzing 循环内**定向变异 | **种子语料**（字典 + 边界种子） | 我们定位是 ChatAFL 上游种子生成器，不接管变异循环 |
| 4 | 自动 prompt 工程（fuzzing 结果驱动） | **ReAct 迭代 refine**（覆盖率/崩溃反馈） | 复用现有 `generate_attack_seeds` 的带错重生成 + 可加覆盖率反馈 |
| 5 | 单协议（demo 目标） | **跨协议漏洞知识迁移** | 多协议低成本迁移是我们的护城河，向量检索天然支持跨协议相似漏洞模式 |
| 6 | 手写 action 边界 | action 边界**从漏洞模式推导** + 向量检索兜底 | 复用现有 `_ACTION_BOUNDARY` 但扩展到可检索、可 LLM 推导，去掉「只覆盖 6 个 action」的硬编码限制 |

---

## 八、各阶段关键流程、输入输出与依赖

```
[阶段一 漏洞模式抽取]   (依赖：kb/<协议>/历史漏洞/*.json)
  输入:  CVE JSON × N
  流程:  rule 抽锚点 → LLM 补全 trigger_sequence/mutation_hint → vuln_pattern
  输出:  vuln_pattern × M（≤ N，scope 门禁后）
  依赖:  core.llm.DeepSeekClient（可降级）；strategy._CWE_ACTION/_COND_KEYWORD_ACTION（action 全集）

[阶段二 中枢 + 向量库]  (依赖：阶段一输出)
  输入:  vuln_pattern × M
  流程:  映射 vuln_pattern fact → 落盘 vuln.jsonl → embedding 建向量库 → 缓存
  输出:  derived/per_source/<协议>/vuln/facts/vuln.jsonl + vuln_pattern_vectors/<协议>.json
  依赖:  core.fused.extraction.vuln（扩展）、core.fused.extraction.source_retrieval（embedder 复用）、aspect_registry（新增 vuln_pattern）

[阶段三 种子生成]       (依赖：阶段二 + bundle)
  输入:  bundle（assemble_bundle 含 vuln_pattern 桶）+ 向量库
  流程:  漏洞模式 → generate_candidates/LLM 边界种子 → generate_dict 定向字典
         → validate_seed → oracle → （可选 ReAct refine）
  输出:  合法边界种子 .raw + 定向变异字典 .dict
  依赖:  boundary_probe、strategy、rag_seedgen.assemble_bundle（加 vuln_pattern 桶）、oracle
```

**依赖链**：阶段一 → 阶段二 → 阶段三（线性）；但阶段三的「边界种子生成」可复用阶段一
未入库前的 rule 锚点先行（与现有 boundary_probe 源 B 兼容）。

---

## 九、预期效果与潜在风险

### 9.1 预期效果

- **覆盖规则外的漏洞**：向量检索兜底，不再受 `_CWE_ACTION`/`_COND_KEYWORD_ACTION` 关键词表限制。
- **跨协议迁移**：新协议无漏洞库时，从其他协议检索相似漏洞模式生成边界种子（护城河）。
- **种子更接近漏洞**：漏洞模式 + 定向字典让 fuzzer 变异有偏，契合「崩溃发现只奖励离漏洞近的种子」的认知纠偏。

### 9.2 潜在风险

| 风险 | 缓解 |
|---|---|
| LLM 补全的 trigger_sequence 可能编造 | rule 锚点打底 + LLM 只补全，补不全就降级为仅锚点 |
| 向量检索的语义漂移（跨协议「相似」≠「同类漏洞」） | cosine 阈值 + 只复用 boundary 结构、不搬具体字段值 |
| 边界种子「太精确」直接打崩目标（dry run 崩被拒） | 保留「接近但不触发」原则，oracle 多次重放过滤 |
| embedding 依赖 sentence-transformers（环境） | 已有 n-gram 降级兜底（source_retrieval 先例） |

---

## 十、落地节奏（对齐 rfc 源「先 rule 后 LLM」）

1. **Phase 1（rule，零 LLM，可测）**：`vuln_pattern` aspect 注册 + rule 抽取锚点 +
   映射 fact + assemble_bundle 加 vuln_pattern 桶 + 测试。快速验证「漏洞模式能抽到」。
2. **Phase 2（LLM 补全）**：`trigger_sequence`/`mutation_hint` 的 LLM 补全 + 降级。
3. **Phase 3（向量库 + 检索）**：复用 embedder 建漏洞模式向量库 + 同协议/跨协议检索。
4. **Phase 4（种子 + 定向）**：漏洞模式 → 边界种子 + 定向字典 + 质量筛选 + 闭环回写 legal_boundary。
5. **Phase 5（反馈 refine）**：覆盖率/崩溃反馈驱动的 ReAct 迭代（可选，后置）。
