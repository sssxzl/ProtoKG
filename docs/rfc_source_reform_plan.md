# RFC 源知识抽取改造方案（基于 FlowFSM / SpecGPT / SemFuzz 三篇工作）

> 生成时间：2026-10-31
> 适用代码库：`E:\科研\想法idea\rag-chatafl`
> 状态：**v3 —— 已吸收 2026-10-31 外部技术评审报告（v2）+《改进v2.md》一致性评审（v3）**，见 §0 修订说明。

---

## 0　修订说明

### 0.0　v3 修订说明（吸收《改进v2.md》一致性评审）

《改进v2.md》是一份针对 **v2 方案自身**的一致性评审，不是新一轮设计挑战。它指出 8 条问题，核心判断是：

> 「整体架构设计基本通过；里程碑 A 修正 3 项后可实施；里程碑 B~D 保留为研究路线」
> 「下一步最重要的不是继续增加设计内容，而是进行一次全文件的『接口一致性清理』」

**我逐条复核后确认：8 条断言全部成立，无一条需要反驳。** 原因很清楚——v2 的修订是**分批局部改**的（先改数据模型 T2、后改伪代码 T6、再改里程碑结构 M6），而 §3.4/§3.5/§3.6 的伪代码与 bundle 契约是**上一轮**写的，**没跟上数据模型的升级**，于是出现「同一份文档里两套字段名并存」的自相矛盾。这正是评审所说的「新旧版本残留」。

v3 已完成**全文件接口一致性清理**，逐条处置如下：

| # | 评审问题（级别）| 复核结论 | v3 处置 |
|---|---|---|---|
| **①** A 阶段文档解析顺序仍写错（**阻塞**）| **成立**。§2.0 的顺序改对了，但 §3.2 伪代码仍是「清洗 → 章节树 → …TOC 过滤」，TOC 行**已经进了章节树**，事后过滤单个窗口无法恢复正确的树。另外 A1.3（章节树）在前、A1.4（标题放宽）在后，**实施依赖也是颠倒的**——章节树建在未放宽的标题正则上，仍只能匹配单词型标题 | §3.2 伪代码改为「清洗 → **TOC 识别与隔离** → **标题识别** → 章节树 → 块解析 → 类型判定」，TOC 行独立存入 `toc_lines` 不参与建树；**A1 任务表重编号**：A1.3 = 标题放宽、A1.4 = 章节树，依赖列同步对齐（A1.5/A1.6 依赖 A1.3+A1.4、A1.7 依赖 A1.4），正文 5 处交叉引用同步修正 |
| **②** TOC 清除与证据保留矛盾（重要）| **成立**。若 TOC 版 claim 仍进 `all_claims`，只是让「重复 ID 归零」，**知识污染未除** | A0.3 改为「**正文 claim 进正式 Fact；TOC claim 只进审计/诊断信息，不进 `all_claims` 有效证据集合**」，并在验收标准里加「TOC 内容不污染规范证据」 |
| **③** 质量闸缺可执行前提（重要）| **成立**。普通生产构建（尤其新增协议）**没有人工真值集**，要求每次 build 都算 P/R/F1 会导致新增协议**始终构建失败** | A0.4 **拆成两类**：① **构建质量闸**（schema / 重复 ID / TOC 残留 / 结构完整性）—— **阻断构建**，不依赖真值集；② **离线评测**（P/R/F1 / 层级准确率 / 人工真值）—— **发布准入**，缺真值集时**跳过而非失败** |
| **④** 新数据模型与旧伪代码不匹配（**阻塞**）| **成立**，且是本次最明显的问题。§3.4 用 `r.confidence` / `r.constraint_kind` / `r.constraint_text` / `r.expectation_class`，§3.6 的 bundle 示例也全是旧字段 | §3.4 全面改用 v2 字段（`r.evidence.explicitness` / `r.validated` / `r.constraint.operator` / `r.constraint.expected_behavior` / `r.rule_id`）；§3.6 bundle 示例**按 §3.1 两层模型重写**（evidence 层 + constraint 层 + 规则级字段），并补 `bundle_schema_version` 版本化与「空即缺失」契约；R5 风险条目里的 `confidence="explicit"` 同步改为 `evidence.explicitness` |
| **⑤** 反馈仍在修改权威规则内容（**阻塞**）| **成立**。`reflow_rules()` 里的 `replace(r, constraint_text=...)` 与 B5「覆盖率只调选择优先级、不改规则内容」**直接冲突**，且会改变规则身份/哈希，把实验反馈写进 RFC 规范事实 | `reflow_rules()` 重写为**纯排序**：读独立反馈表 `feedback[rule_id]["priority_score"]`，**规则本身一字不改**，排序键 `(-priority, rule_id)` 保证确定性 |
| **⑥** 投票仍有运行级错误（重要）| **成立**。`voting_models = {r.model_id for r in g}` 引用了 `SemanticRule` **并未定义**的 `model_id` | 引入投票输入层包装 `Candidate(rule, model_id, run_id)`——模型身份与 run_id 是**运行时信息**，不属于规范规则；`voting_models = {c.model_id for c in g}` 改为从 Candidate 取 |
| **⑦** Oracle 判定顺序问题（重要）| **成立**。原顺序 `crash → reset/close → semantic_deviation → unknown timeout` 下，`health=UNKNOWN & trans=TIMEOUT` 会先命中 `semantic_deviation`（因 `proto != expected`）而非 `inconclusive`——而超时原因未知（丢包/负载/静默丢弃/状态不匹配/真死锁），**不能断言语义偏离**。且 `ProcessHealth.EXITED` 不能不加区分当崩溃（目标收到 QUIT 后正常退出也是 EXITED）；`timeout`/`crash` 也不该是普通 RFC 协议响应期望 | `close_loop()` 判定顺序改为「**① UNKNOWN+TIMEOUT → inconclusive（最先）** → ② crash（EXITED 须经 `_is_abnormal_exit` 判别退出码/退出原因/生命周期）→ ③ reset/close → `connection_aborted` → ④ 语义偏离」；bundle 的 `expected_response_classes` **去掉 timeout/crash**（它们属传输轴与进程健康轴） |
| **⑧** 证据「显式性」判断不严谨（重要）| **成立**。§3.2 原顺序是「先按证据类型+区间非空设 `explicit`，再验证区间」——区间根本不存在的规则也可能被标成 explicit；且「**约束可机械验证**」≠「**RFC 用 MUST 规定了它**」，两者混淆会把模型推断错误提升为规范性强制要求 | 顺序改为「**先 `_verify_span_in_source()` 验证区间，再判 explicitness**」：验证通过 **且** 证据类型为 normative/abnf → `explicit`，有 span 文本 → `quoted`，否则 `paraphrased`；并**显式分离**「可机械验证」（由 operator/operand 决定）与「规范强制」（由 evidence_kind + explicitness 决定），两者互不推导 |

**v3 的性质**：这是**一致性清理**，不是新增设计。**没有引入任何新的架构元素、数据结构或里程碑**——只是让「修订说明、任务表、数据模型、伪代码、bundle 契约、风险清单」六处使用同一套约定。文档篇幅从 827 行增至约 900 行，增量全部来自把「为什么这样改」写清楚。

**采纳评审的推进建议**（直接作为 v3 的执行口径）：

> 「里程碑 A 只需优先修正前面三个问题，就可以正式进入实施和测试。不要为了修复 A 而提前实现 B～D 的完整系统。」

→ **里程碑 A 的编码范围锁定为 A0.1 ~ A0.6 + A1.1 ~ A1.7**（问题①②③ 已在本文档层面修完，编码按 A1 任务表顺序推进）；**B~D 保持研究路线状态**，进入各自开发前必须先统一数据模型 + 独立实验验证收益。

**同时采纳评审的一条补充提醒**（v3 已落实为具体条款）：

> 「原方案中的安全隔离、监控和灰度措施仍主要停留在风险清单，需要在相应阶段落实为明确的任务和验收用例。」

→ v3 在 §3.6 bundle 契约处补入了**版本化 + 空即缺失 + 消费入口写法**三条硬约束（对应灰度与回滚）；R19/R20/R21 三条风险对应的幂等键、错误分类、执行隔离已在 A0.5 / A0.6 落为**带验收标准的任务行**，不再只是风险条目。

**遗留（明确不修）**：评审指出「尚未拿到实际仓库源码和测试记录，因此不能确认文档中的根因分析及目标指标已经在代码层面得到验证」——**这一条对我成立**。本文档的根因分析（15.2% 标题命中率、TOC 污染 50/100、68 个 fact_id 冲突）**均已在本地仓库实测复现**，但**v3 新增的指标目标（如章节召回 ≥95%、precision 不低于基线）尚未验证**，它们是**待验收的验收标准**，不是已达成的事实。

---

### 0.1　v2 修订说明（吸收外部技术评审报告意见）

本方案经外部技术评审，评审指出 **5 个阻塞级问题**。经我逐条复核代码验证，**评审的关键断言全部成立**，v2 已按下列原则修订：

| 评审条目 | 复核结论 | v2 的处置 |
|---|---|---|
| **G1** 目标与实现冲突（称"任意 RFC 可靠有效"却依赖协议专属 Profile/dissector/响应映射）| **成立** | 目标改写为「协议无关的抽取核心 + 可插拔适配」，并引入**能力等级 L1~L5**（见 §2.0.5）|
| **T1** 投票算法错误 | **成立（已实算验证）**：我写的 `N//2+2` 在 N=1/2 时要求票数 > 模型数，**永不通过**；且 `votes=len(g)` 计的是候选数不是模型数；`SemanticRule` 缺 `expectation_span` 但投票要比较它 | 投票整体**降级为 P2 可选增强**，并把三条修正写进 §2.3 |
| **T2** `SemanticRule` 不可执行（`constraint_text` 是自由文本，缺 operator/operand/precondition）| **成立** | 改为**证据层 + 可执行规则层**两层模型（§3.1），不可转换者只作知识候选、不进生成链路 |
| **T3** 字段路径树与变异引擎**循环依赖**（原阶段 4.2 先实现 `apply_actions`，4.3 才建路径树，4.3 依赖又写 4.2）| **成立，是我写错了** | 顺序改为「解析能力 → 字段模型 → 编码能力 → 往返一致性 → 字段动作」，且**只选一个有成熟可逆 parser 的协议先做** |
| **T4** oracle 把 TCP reset 当 crash | **成立**。且实测现有 `seed_oracle_filter.py` **只判响应码、不看连接状态与进程健康** → crash 判定是全新能力 | 拆成**协议结果 / 传输结果 / 进程健康**三轴，reset 归入传输轴**不进 crash** |
| **T5** fact_id 冲突根因未查就改算法 | **成立，我已查明**：`compute_fact_id = sha256(canonical_serialize(fact_key))[:16]`，**68/68 冲突的 fact_key 完全相同**（同一状态码被 TOC 版与正文版各抽一次）→ **改 ID 派生解决不了**，必须先消除重复抽取 | 任务 A0.3 改为「**先消除重复抽取**」，ID 治理推迟到重复消除后（§2.0 里程碑 A）|
| **T6** 置信度伪代码三处错（`replace()` 不写回、`constraint_span: str` 却判 None、`and` 导致漏标）| **成立** | 重写该段伪代码（§3.2 末段）|
| **T7** TOC 过滤在章节树之后、ABNF 未区分命令/非终结符 | **成立** | 里程碑 A1 的执行顺序改为「清洗 → TOC → 章节树 → 块解析 → 分类 → 语义抽取」，且**每步都测 P/R**（不只看命中率）|
| **T8** 长度字段自动回填会消除测试意图 | **成立** | 变异引擎区分「目标违规字段保留 / 非目标依赖字段修复」，编码后**重新校验 `violation_of` 仍成立** |
| **T9** 「只增不删」+ 覆盖率直接改 `constraint_text` 会污染知识库 | **成立** | 权威规则 / 候选规则 / 已撤销规则 / 实验反馈**四库分离**；覆盖率只调**选择优先级**，不改规则内容 |
| **T10** LLM 调用契约隐性变化（原阶段 2 的 LLM 抽取进入每个段落主流程）| **成立** | 明确双模式：`rules_only`（保证纯离线确定性）/ `semantic_enhanced`（LLM 增强，独立超时/预算/缓存/失败隔离）|
| **M6** 验收口径问题（命中率≠正确率、`allowed_methods` 是人工配置存在信息泄漏、`8/68` 垃圾率不能推召回、逐字节一致不适合做投票验收、种子数对齐不足以控混杂）| **全部成立** | §2.2 全面重写：改用**独立人工标注真值集**、precision/recall/F1 + 章节层级正确率、投票验收改为「相对真值集的 P/R/F1 + 结果差异率」、fuzzing 对照**增加执行预算/有效种子率/起始状态/目标版本/随机重复数**控制 |
| **F1** 改造范围被低估（不只 bundle 一个键）| **成立** | 新增 §2.0.0 兼容性清单 + 数据回退设计 |
| **F2** 章节合并导致上下文膨胀 | **成立** | 引入**有预算的上下文组装**（最大展开深度、去重、引用环检测），静态解析与 LLM 上下文构造分离 |
| **F3** 投票成本被低估 | **成立** | 投票**不默认全量应用**，只对高风险/低置信/跨源冲突候选仲裁，并记录每条规则的实际 token/时间成本 |
| **F4** 「支持/不支持」二分法不诚实 | **成立** | 采用**能力等级 L1~L5**（见 §2.0.5）|
| **M2/M3/M4/M5** 并发幂等、错误分类、可观测性、安全 | 成立 | 并入里程碑 A0（幂等键、快照原子切换）与 §2.2（分层可观测性指标）|

**v2 的路线变更**：评审建议「**A → B → 验证收益 → 再决定 C/D**」优于预设 0~5 全做，我采纳并重排为 §2.0 的**四个里程碑**（A 可靠抽取 / B 可信语义知识 / C 单协议语义变异验证 / D 按价值扩展）。**里程碑 B~D 从「计划」降级为「研究路线」，每个里程碑有独立退出条件。**

**仍然保留的评审未否定部分**：核心诊断（15.2% 命中率的根因是单词正则 + 宽松版正则已存在但未接进主路径）、里程碑 A1 的三项具体任务、评测中「必须报覆盖率」（相对 SemFuzz 的优势）、「规则可用率」与「人工成本/协议」两个新增指标。

---

## 第一部分　三篇论文的设计思想对照总结

### 1.1 一句话定位

| 论文 | 它解决的层次 | 核心机制 | 与我们的关系 |
|---|---|---|---|
| **FlowFSM**（arXiv 2507.11222, 2025-07） | 从 RFC 文本抽出**命令级 rule-book** | Prompt chaining（命令抽取 → 状态转移分析 → rule-book 合成）+ 增量更新门控 | 提供**工序分解**思路；其「只抽取不 fuzzing」正是我们要补的 |
| **SpecGPT**（arXiv 2510.14348, 2025-10） | 从 3GPP 规范抽**状态机五元组** | 领域知情提示 + CoT + **多模型 span-overlap 对齐后多数投票** | 提供**投票降幻觉**机制 + **章节自底向上合并**（优于我们现策略） |
| **SemFuzz**（arXiv 2603.05989, 2026-03） | 用**字段级语义**驱动 fuzzing | LLM 读 RFC 抽语义规则（构造约束 C + 处理期望 P）→ 语义违规用例 → **期望响应 vs 实际响应**做 oracle | 提供**语义反馈闭环**与**抽象层/字节层分离** |

### 1.2 三篇的核心设计思想（各自最值得抄的一点）

#### FlowFSM：把「一次性大抽取」拆成串行工序，每步只做一件事

- **工序**：① Command Extraction（抽命令清单 + 功能分类）→ ② State Transition Analysis（为每个命令找 pre/postcondition 状态，映射所有合法命令序列）→ ③ Rulebook Synthesis（每命令产出三章节：Purpose / Valid Direct Preceding / Valid Direct Subsequent）
- **反幻觉的两道闸**：
  1. `updateFlag` 门控 —— LLM 显式回报「本 chunk 是否带来新信息」，无则不更新（`Algorithm 1` L10-15）
  2. 提示词规则「只在新信息时更新 / 永不删除已有信息 / 只加上下文直接支持的内容 / 无信息则保持不变」——**rule-book 只单调增长**
- **检索式召回**：第二遍按「chunk 是否包含该命令文本」检索相关 chunk 再喂给 agent（`SearchChunks(Containing(C_chunks, command))`）
- **关键边界**：FlowFSM **不做 state-aware mutation、不做 fuzzing**，作者明确列为未来工作；官方仓库**至今无代码**（README 只有「will be shared soon inshallah」），两个核心 prompt 全文未公开
- **它的弱点（正是我们的机会）**：章节标题必须单词式；无交叉引用处理；父节内容被丢弃；CoT 声称大于 CoT 证据（引 ReAct 但模板里无推理脚手架）

#### SpecGPT：把「单模型抽不准」变成「多模型投票」

- **输出结构**：五元组 `⟨Q, Σ, q0, δ, F⟩`，LLM 实际产出严格 JSON `{"states":[...], "transitions":[{"from","to","condition","action"}]}`
- **领域知情提示（domain-informed prompting）的四层**：
  1. 协议形态分类 → 选不同 prompt（state-oriented 如 NAS 显式状态名 / procedure-oriented 如 PFCP 状态=过程节点）
  2. 状态名规范约束（只抽协议正式节点、忽略「any state」这类描述性短语、缩写要联合推理还原全名）
  3. condition/action 语义切分 + few-shot
  4. Prompt 优化三招：**协作式上下文推理**（同时给历史上下文与当前段）、**显式+隐式信息整合**（严格 grounding + 合理性复核）、**交叉引用处理**（多文本同时输入，用章节号前缀构造章节级映射，**无需向量库**）
- **投票机制**：对**单个转移元组**投票。跨模型对齐用 **span-overlap**：`Overlap(A_i,A_j)=|span∩span|/min(|span|,|span|) ≥ θ`，`θ=0.75`；两个转移对齐 ⟺ 起点同、终点同、action 重叠达标、condition 重叠达标；然后**多数投票**
- **效果**：NAS 单模型 precision 仅 61.71%~80.39%（幻觉：生成过多转移），ensemble 达 **91.86 / 90.43 / 91.14**，相对最佳单模型 F1 提升 **5.85%~22.37%**
- **它的弱点**：投票阈值/平票/集体错误三处**未定义**；θ 无敏感性分析且**同时用于投票与评测**（方法论循环）；NGAP-UCM 只有 60.93 F1；有「manual alignment」人工步骤；R15 泛化只有计数无精度

#### SemFuzz：把「语义」降解为「字段级约束 + 期望响应」，用响应做 oracle

- **语义的形式化**（这是全文最关键的界定）：`SR = (p, m, f, C=(r,c), P=(r,c))` —— 字段级**构造约束 C**（role + 内容）+ **处理期望 P**（role + 内容）。**不是状态机、不是数据流**
- **它刻意不做状态机**：Related Work 明确批评 FSM 路线「lack fine-grained semantic modeling (such as field-level constraints)」
- **闭环**：RFC →（LLM）→ SR →（LLM）→ 变异策略 M=(p,m,f,d,e) →（LLM 出动作序列）→ 确定性引擎执行 → **按 C 的 role 发送、观察对端响应** → 响应映射为 normal/error → **与 e 不一致 ⇒ 候选漏洞**
- **两个关键工程决策**：
  1. **抽象层/字节层分离** —— LLM 只出 `add/remove/update(字段路径)`，字节级由确定性引擎负责（自动回填 `extension_len` 等长度字段）。论文给了明确失败证据：直接让 LLM 改 hex 在 TLS 这类嵌套协议上「may require cascading updates to other dependent fields」
  2. **期望响应强制二值化** —— 提示词内固化 `Normal feedback` / `Error feedback` 两个词表，**不让 LLM 自由生成期望响应**（否则期望值本身不稳定，oracle 失效）
- **效果**：4 协议 1,721 条语义规则，16 个潜在漏洞 / 10 个确认（准确率 62.5%），4 个 CVE；消融显示去掉动作序列层后测试用例准确率从 0.87 崩到 **0.36**（TLS 上崩到 **0.06**）
- **它的弱点（我们的机会）**：**完全无状态机**；oracle 只有二档；**每协议必须人工写 normal/error 响应映射表**（论文唯一的「协议专属」模块）；误报率 37.5%；4 个 CVE 中 2 个来自早期规则版

### 1.3 三篇的横向对照与可组合性

| 维度 | FlowFSM | SpecGPT | SemFuzz | **组合结论** |
|---|---|---|---|---|
| 核心路线 | **深度分解**（工序化）| **广度投票**（多模型共识）| **语义降解**（字段级 + oracle）| 三者正交，可叠 |
| 抑制幻觉 | 单模型内：`updateFlag` + 「只增不删」规则 | 跨模型外：span-overlap + 多数投票 | — | **FlowFSM 内部一致性 ⊕ SpecGPT 外部共识 = 双层护栏** |
| 幻觉表现 | 多抽（FTP FP=18）| 多抽（precision 61~80%）| 误报 37.5% | **FP 是三者共同敌人**，投票直接对症 |
| 上下文策略 | 叶节点 chunk（**丢父节**）| 章节树自底向上合并（**保留父节**）| 段落 + 章节路径前缀 | **采纳 SpecGPT 的合并**（对 RFC 尤其重要：语法总述常在父节）|
| 交叉引用 | **无** | 有（轻量 RAG + 章节号前缀）| 有（`See [H14.x]` 形式）| **采纳 SpecGPT**（RFC 跨引用密度远高于 3GPP）|
| 状态机 | 有（命令级 rule-book）| 有（五元组）| **无** | SemFuzz 是缺口；**我们已有 edge_cover 状态机层** |
| 语义粒度 | 命令/状态 | 状态/转移 | **字段级** | SemFuzz 的粒度最细，是我们的**差异化** |
| 是否做 fuzzing | 否（未来工作）| 否（明确只做状态机）| **是**（核心）| 我们已有三层检索 + 种子生成 |
| 文本处理能力 | 最强（专用 agent 框架）| 中（+ 领域提示）| 中（+ 语义规则）| 用 FlowFSM 的工序骨架 |

**★ 最值得组合的一点**：FlowFSM 的 rule-book 里写的是 `"User must be logged in"` 这类**改写过的自然语言**，而 SpecGPT 的投票对齐器依赖 **verbatim 原文 span**（重叠度 θ=0.75）。二者不能直接拼接。**改造点**：把 FlowFSM 的 rule-book 字段改成「原文 quoted 片段」形式，SpecGPT 的对齐器即可零改动复用。

**★ 最有性价比的单项借鉴**：SpecGPT 的**章节自底向上合并**（Algorithm 1）替换 FlowFSM 的叶节点 chunk —— 一处改动，直接解决我们 rfc 源「15.2% 章节命中率」与「父节信息丢失」两个问题。

---

## 第二部分　分阶段实施计划（v2：里程碑制）

### 2.0 现状基线（实测，作为验收参照）

| 项 | 实测值 | 备注 |
|---|---|---|
| 全 kb 真实章节标题命中 | **276 / 1815 = 15.2%** | 评审 M6：这不是"正确率"，只是标题召回 |
| 分协议可用性 | rtsp ✅ / sip ⚠️ / 其余 6 个 ❌ | |
| 全局 field 误抽 | 74/174 ≈ 43% | |
| method 垃圾率 | 8/68 ≈ 12% | ⚠️ **这是垃圾率，不能据此推召回率**（评审 M6）|
| SIP fact_id 冲突 | 241 facts → 唯一 173（**68 冲突**）| ★ 根因已查明：**68/68 是同一 fact_key 被抽两次**（TOC 版 `Trying ......183` + 正文版 `Trying`）→ **改 ID 派生无效** |
| TOC 污染 | SIP 100 条 outcome 中 **50 条** 是 TOC | |
| 确定性 | ✅ 8/8 协议两次抽取逐字节一致 | ⚠️ 评审 M6：此指标**不适合做投票验收**，仅作回归护栏 |
| 落盘 | `derived/per_source/<协议>/rfc/facts/rfc.jsonl`，过 `validate_fact` fail-closed | 视图含 `fact_key`/`resolution`/`all_claims`，**不含 fact_id**（ID 是计算出来的）|

### 2.0.0 兼容性清单（评审 F1：改造范围远不止 bundle 一个键）

| 改造区域 | 影响 | 复杂度 | v2 处置 |
|---|---|---|---|
| RFC 解析器 | 章节树 / ABNF / 表格 / 引用 | 中~高 | 里程碑 A |
| Fact / Registry | 新 aspect / 事实 ID / 验证规则 | 高 | 里程碑 A（ID 治理**推迟**到重复消除后）|
| Profile / Adapter | 配置拆分 / 加载 / 版本兼容 | 中 | 里程碑 A（新增 `rfc_config.json` 与 `adapter.json`，**不动现有 profile.json 结构**）|
| LLM 抽取 | Prompt / 缓存 / 模型版本 / 投票 | 高 | 里程碑 B/D |
| 下游消费层 | 检索与消解 / 新规则注入 | 中~高 | 里程碑 B |
| 字段变异引擎 | 解析 / 修改 / 重编码 / 校验 | 很高 | 里程碑 C（**仅一个有成熟可逆 parser 的协议**）|
| Oracle 与反馈 | 状态管理 / 复现 / 归因 | 高 | 里程碑 C |

**数据回退设计（评审 F5）**：新旧抽取器**并行输出到独立命名空间**（`derived/per_source/<协议>/rfc/facts/rfc.jsonl` vs `.../rfc_v2/facts/rfc.jsonl`），消费端按版本化 bundle 选取；发生异常时回退到旧版**数据快照**，而不只是关掉 LLM 开关。**幂等键** = `build_id + 输入哈希 + 配置版本 + 模型版本`。

### 2.0.5 协议能力等级（评审 F4：不用"支持/不支持"二分法）

| 等级 | 支持内容 | 当前状态 |
|---|---|---|
| **L1** | RFC 结构解析、知识抽取 | 8 协议（质量差异大：RTSP 可用 / SIP 半可用 / 其余不可用）|
| **L2** | 字段级语义与证据校验 | 待建（里程碑 B）|
| **L3** | 报文解析与**可逆编码** | ⚠️ **关键瓶颈**：dissector 能解析 ≠ 能重编码；TLS/DTLS/SSH 涉及嵌套长度、校验、加密、握手状态、跨消息依赖 |
| **L4** | 状态化会话执行 | 已有（AFLNet + edge_cover）|
| **L5** | 响应 oracle 与漏洞复现 | ⚠️ 现有 oracle **只判响应码**，无进程健康维度 |

**关键区分**：DNS 的 `QTYPE` 是字段、SMTP 的 `EHLO` 是命令、TLS 的 `ClientHello` 是握手消息 —— **不能靠统一的 ABNF 名称抽取把它们都当 `method`**。这就是为什么「章节语义判定」（依赖 `rfc_config` 的 `*_sections`）比「形态判定」更准，也说明**协议适配知识无法完全消除**，只能降低其成本。

### 2.0.6 双运行模式（评审 T10：LLM 契约隐性变化）

| 模式 | 行为 | 保证 |
|---|---|---|
| **`rules_only`** | 纯规则抽取（现状 + 里程碑 A 的解析改进），**完全不调 LLM** | 确定性、离线可跑、零成本 —— **默认模式，也是回归护栏** |
| **`semantic_enhanced`** | 允许 LLM 增强（语义规则、投票、动作生成）| 独立超时 / 预算 / 缓存 / 失败隔离；**LLM 不可用时自动回落到 rules_only** |

---

### 里程碑 A：可靠抽取（**立即做**，评审「有条件通过」）

**目标**：修掉已实测的四个数据缺陷，让 rfc 源从「6/8 协议不可用」变成「方法名可召回」。**不引入 LLM、不改下游契约、不改 ID 算法。**

#### A0　地基

| 任务 | 涉及文件 | 接口 | 依赖 | 验收标准 |
|---|---|---|---|---|
| A0.1 补 4 个缺失协议 Profile | `fused_hub/targets/{dns,dtls,ssh,tls}/profile.json` | `allowed_methods` / `canonical_flow` / `transport` / `message_schema` | 无 | 4 个 profile 存在且被 `paths.target_profile` 解析成功 |
| A0.2 Profile 拆分（评审 R3）| 新建 `fused_hub/targets/<协议>/rfc_config.json` | `method_sections` / `field_sections` / `status_sections` / `method_excludes` | A0.1 | **不动现有 `profile.json` 结构**；`_load_rfc_config` 在缺失时**显式警告**（不再静默返回空默认）|
| A0.3 **消除重复抽取**（评审 T5 的真解）| `core/fused/rfc_extractor.py` | 同 fact_key 多次命中时：**正文 claim 进入正式 Fact**；**TOC claim 只进审计/诊断信息，不进 `all_claims` 有效证据集合** | A1.2 | SIP 冲突数 **68 → 0**；且**TOC 内容不污染规范证据**（改进v2 问题②：否则只是「重复 ID 归零」，知识污染仍在）|
| A0.4 rfc 源质量闸（**拆成两类**，改进v2 问题③）| `scripts/build_hub.py` | 新增 `rfc_quality_report(facts, profile)` | A0.1 | ① **构建质量闸**（**阻断构建**）：schema 合法 / 重复 fact_id / TOC 残留 / 结构完整性 —— **不依赖人工真值集**，新增协议也能构建<br>② **离线评测**（**发布准入**，不阻断构建）：P/R/F1 / 章节层级准确率 / 人工真值对比 —— 需要真值集，缺失时**跳过而非失败** |
| A0.5 幂等与快照（评审 M2/F5）| `scripts/build_hub.py` | `build_id = hash(输入+配置版本+模型版本)`；产物写**独立快照**后原子切换 | 无 | 同输入两次 build 产出字节一致；并发 build 不互相覆盖 |
| A0.6 错误分类（评审 M3）| `core/fused/rfc_extractor.py` | 区分「文档解析失败 / 块分类失败 / 证据不匹配」三类，**不都变成空结果** | 无 | 报告能区分「没抽到规则」与「解析失败」|

#### A1　抽取器重写（核心）

**执行顺序（评审 T7 + 改进v2 问题①：必须按此顺序，且每步测 P/R）**：

```
文档清洗 → TOC 识别与隔离 → 标题识别 → 章节树 → 块解析 → 类型判定 → （语义抽取，里程碑 B）
```

> ★ **改进v2 问题①（已落实）**：标题识别（**A1.3**）必须**先于**章节树（**A1.4**）。
> 原表把「章节树」编为 A1.3、「标题放宽」编为 A1.4，导致实施依赖颠倒——
> 章节树建在未放宽的标题正则上，仍只能匹配单词型标题（实测命中 15.2%）。
> 已通过**重编号 + 依赖列对齐**修正：下表 A1.3 = 标题识别，A1.4 = 章节树。
> 同时 §3.2 伪代码的步骤编号（A1-3 标题识别 / A1-4 章节树）已与此对齐。

| 任务 | 涉及文件 | 接口 | 依赖 | 验收标准 |
|---|---|---|---|---|
| A1.1 文档清洗 | `core/fused/rfc_extractor.py` | 复用已有 `_clean_body`；补 TOC 标记 | 无 | 清洗前后行数差可解释 |
| A1.2 **TOC 过滤前置**（评审 T7）| 同上 | 新增 `_is_toc_line()`（点线 `\.{3,}` / 行尾页码）；**与 `infer_structures` 合并为同一函数**（消除两处不一致）| A1.1 | TOC 残留 **50 → 0**（SIP 口径）；**正文含数字的行不被误删** |
| A1.3 **标题放宽 + 语义判定**（改进v2 问题①：**前移到 A1.4 之前**）| 同上 | `_RE_ANY_SECTION` 标题组改 `(.+?)`；kind 由 `rfc_config` 的 `*_sections` 判定，替代形态猜测 | A0.2 + A1.2 | `4.1.  Basic Structure`、`10.1 The OPTIONS method`、`3.1.  DATA REPRESENTATION` 均被捕获且 kind 不误判 |
| A1.4 章节树 + **有预算的自底向上合并**（评审 F2，改进v2 问题①：**后移到 A1.3 之后**）| 同上（新增 `_parse_section_tree` / `_merge_leaf_windows`）| A1.3 | 父节内容进入窗口；**展开深度有上限、去重、引用环检测**；章节召回 ≥95% **且 precision 不低于当前基线** |
| A1.5 ABNF / 命令语法块抽取器 | 同上（新增 `_extract_abnf_names` / `_extract_command_syntax`）| **必须区分协议命令 / 语法非终结符 / 字段名**（评审 T7）| A1.3 + A1.4 | FTP 抽到 `RETRIEVE`/`RETR`；SMTP 抽到 `EHLO`/`MAIL`/`RCPT`/`DATA`/`QUIT`；DNS 抽到 `QNAME`/`QTYPE`/`RDLENGTH`；**非终结符不混入 method** |
| A1.6 表格抽取器 | 同上（新增 `_extract_status_table`）| 抽 `Code reason` 型状态码表 | A1.3 + A1.4 | RTSP 抽到 100/200/300/400/401/404（当前为 0）|
| A1.7 交叉引用处理 | 同上（新增 `_resolve_xref`）| 解析 `see Section X.Y` / `See [H14.x]` | A1.4 | RTSP 那 22 个 `See [H14.3]` 退化 content 被回填或**明确降级**（不当作有效语义）|

**里程碑 A 退出条件**：独立真值集上章节/命令/字段/状态码的 **P/R/F1 均高于当前基线**，且 **8 协议回归无非预期行为变化**（用固化 golden md5 做护栏）。

---

### 里程碑 B：可信语义知识（**评审「暂缓」→ 需先重构设计**）

**目标**：把 rfc 知识从「名称 + 自由文本定义」升级为「**有原文证据 + 可执行约束**」。**必须先完成 T2 的两层模型重设计再开工。**

| 任务 | 涉及文件 | 接口 | 依赖 | 验收标准 |
|---|---|---|---|---|
| B1 **两层语义模型重设计**（评审 T2）| `core/fused/models.py` | `SemanticRule` 拆为**证据层**（原文 span / 章节 / 规范版本 / source_anchor）+ **可执行层**（target_field / operator / operand / precondition / expected_behavior）；新增唯一 `rule_id` | A1 | **不可转换为可执行规则的内容只作知识候选，不进自动生成链路** |
| B2 证据有效性校验 | 同上 | 在来源窗口中**验证引用的字符区间真实存在**（评审 T6）| B1 | 引用不存在 → 规则被拒；`MUST`/`SHOULD`/`MAY`/ABNF **区分约束强度** |
| B3 期望响应词表 | `fused_hub/targets/<协议>/rfc_config.json` | `expected_response_classes`；提示词内固化该词表，**禁止 LLM 自由生成** | B1 | 抽出的期望值只允许取词表内值；词表由配置提供而非硬编码 |
| B4 规范版本与冲突模型（评审 M1）| `core/fused/models.py` + registry | 区分**规范证据 / 实际观察 / 模型推断 / 人工确认**四类来源；支持规则撤销、替代、版本隔离 | B1 | `normative > observed` **不足以**完成消解；同字段多版本约束可共存 |
| B5 **四库分离**（评审 T9）| `core/fused/downstream/rule_store.py` | 权威规则 / 候选规则 / 已撤销规则 / 实验反馈**分库存储** | B1 | 覆盖率**只调选择优先级**，不修改规则内容；错误规则可撤回 |
| B6 置信度判定重写（评审 T6）| `core/fused/rfc_extractor.py` | 见 §3.2 末段（修 `replace()` 不写回、类型契约矛盾、`and` 漏标）| B2 | 显式程度 / 证据有效性 / 模型置信度**三者分开记录** |
| B7 `bundle` 契约扩展 | `core/fused/downstream/rag_seedgen.py:assemble_bundle` | 新增 `semantic_rules` 键（**唯一破坏性改动**，四层签名不变，向后兼容）| B1 | 旧消费者读旧 bundle 不受影响 |

**里程碑 B 退出条件**：规则 **P/R/F1**（对独立真值集）、**可执行率**、**人工复核成本**达到预先设定门槛；且 `semantic_enhanced` 模式下每条规则可追溯到原文证据。

---

### 里程碑 C：单协议语义变异验证（**评审「需重新设计」**）

**目标**：**先在一个协议上**证明「语义约束种子比普通种子更有效」，再考虑推广。

| 任务 | 涉及文件 | 接口 | 依赖 | 验收标准 |
|---|---|---|---|---|
| C1 **选定一个有成熟可逆 parser 的协议** | — | 评估哪些协议有 parse+serialize 双向能力 | — | **至少一个协议能通过往返一致性测试**（parse→serialize→parse 等价）|
| C2 字段模型 | `core/fused/downstream/field_model.py` | 字段路径 + 类型 + 长度依赖关系 | C1 | 复用 traffic 源已抽出的真实字段值 |
| C3 **编码能力**（评审 T3）| 同上 | 修改后能**重新编码为合法报文** | C2 | 往返一致；TLS 式嵌套场景不产生级联长度不一致 |
| C4 定向变异 | `core/fused/downstream/field_mutation.py` | 动作 = `add/remove/update(字段路径)`；**目标违规字段保留、非目标依赖字段修复**（评审 T8）；编码后**重新校验 `violation_of` 仍成立** | C3 | 生成种子的 `violation_of` 成立率 ≥ 95% |
| C5 **三轴 oracle**（评审 T4）| `core/fused/downstream/response_oracle.py` | **协议结果**（success/protocol_error/application_error/silence）× **传输结果**（response/reset/close/timeout）× **进程健康**（alive/exited/restarted/sanitizer_failure/unknown）| C1 | **reset 不进 crash**；只有独立证据（进程退出/异常重启/运行时错误）才进 crash 路径 |
| C6 独立复现 | `core/fused/downstream/repro.py` | `reproduce(seed)`：重放 + **canary 健康探测** | C5 | 复现率可量化；**不学 SemFuzz 的 off-by-one 间接判定** |
| C7 归因记录（评审 M7）| `core/fused/downstream/attribution.py` | 记录 `rule_id` + 变异动作 + 原始种子 + 完整会话 + 执行环境 + 复现结果 | C6 | `violation_of` **能唯一标识一条规则**；用单变量变异 + 最小化 + 对照重放辅助归因 |

**里程碑 C 退出条件**：相同执行预算下，对比现有 fuzzing 基线获得**可复现**收益。

---

### 里程碑 D：按价值扩展（**研究路线，需独立预算**）

| 任务 | 前置条件 | 备注 |
|---|---|---|
| D1 **选择性模型仲裁**（评审 F3/P2）| B 完成 | **不默认全量投票**；只对高风险/低置信/跨源冲突候选仲裁；**每条规则记录实际 token 与时间成本**；**投票保持可关闭** |
| D2 投票算法修正（评审 T1）| D1 | 三处必改：① 阈值改 `N//2+1`（严格多数）② **同一模型每组最多一票**（`votes` 计**模型数**不是候选数）③ 对齐时**分别比较主体/规则类型/操作符/约束值/期望/证据位置**，span 重叠**仅作辅助条件**（span 不具传递性，简单聚类会混合矛盾约束）|
| D3 跨协议推广 | C 证明净收益 | 先单协议，再协议族 |

---

### 2.1 依赖关系图（v2）

```
里程碑 A（可靠抽取，不调 LLM）
  A0 地基（Profile 拆分 / 消除重复抽取 / 质量闸 / 幂等快照 / 错误分类）
   └─→ A1 抽取器重写（清洗→TOC→章节树→块解析→分类）
          └─→ 里程碑 B（可信语义知识）
                 B1 两层模型（证据层 + 可执行层）← ★ 必须先于任何生成链路
                 B2 证据校验 / B3 词表 / B4 版本冲突 / B5 四库 / B6 置信度 / B7 bundle 扩展
                        └─→ 里程碑 C（单协议语义变异验证）
                               C1 选协议 → C2 字段模型 → C3 编码 → C4 变异 → C5 三轴oracle → C6 复现 → C7 归因
                                      └─→ 里程碑 D（按价值扩展：选择性投票 → 跨协议）
```

### 2.2 评测方式与对照基线（v2：按评审 M6 重写）

#### 内部评测（每次改动的回归，全部自动可测）

| 指标 | 当前基线 | 目标 | 口径说明 |
|---|---|---|---|
| 章节 **precision** | 未测 | 不低于基线 | ⚠️ 评审 M6：放宽正则会提 recall 但产生大量假章节，**必须同时测 P 与 R** |
| 章节 **recall** | 15.2%（标题命中）| ≥95% | 真值集需覆盖 TOC/附录/图表/重复标题 |
| 章节**层级正确率** | 未测 | ≥90% | 树结构对不对（不只是抓到没有）|
| **TOC 误删**（正文含数字的行被删）| 未测 | 0 | 误删比漏抽更危险 |
| 引用解析成功率 | 未测 | ≥80% | `see Section X.Y` 能否定位 |
| method **precision** | 垃圾率 12%（8/68）| 垃圾率 ≤5% | ⚠️ 垃圾率 ≠ 召回率，两者分开报 |
| method **recall** | ftp 0% / smtp 0% / sip 0% | ≥90% | **对独立人工标注集**，不用 `allowed_methods`（见下）|
| field 误抽率 | 43%（74/174）| ≤10% | |
| fact_id 冲突 | 68 | **0** | 通过消除重复抽取达成，**不改 ID 算法** |
| 规则可执行率 | — | 里程碑 B 目标 | 评审新增：能转成可执行规则的比例 |
| 逐字节确定性 | ✅ 8/8 | 保持 | ⚠️ 仅作**回归护栏**，**不做投票验收**（不同模型子集本就该不同）|

> **⚠️ 关于 `allowed_methods` 的信息泄漏（评审 M6）**：该字段是 `fused_hub/targets/<协议>/profile.json` 里
> **人工撰写**的配置。若用它同时（a）配置抽取、(b) 判定 method 召回，就是**人工知识既当输入又当标准**。
> 实测已显示这个风险真实存在：RTSP 的 `allowed_methods` 有 8 个，而 rfc 实抽到 11 个，
> 差集 `ANNOUNCE` / `RECORD` / `REDIRECT` **是真实 RTSP 方法**，只是 profile 没列 ——
> 若按「不在 allowed_methods 即垃圾」判定，会把它们误判为垃圾。
> → **必须建立独立人工标注真值集**，且真值集需区分「命令 / 字段 / 消息类型」三类。

#### 外部评测（论文级）

| 维度 | 方法 | 对照基线 |
|---|---|---|
| 语义规则质量 | P / R / F1，判定要求「消息名与字段名**严格一致**」（学 SpecGPT）| **独立人工标注集**：多标注者交叉 + 专家仲裁（学 SemFuzz 的做法，**但必须报告我们自己的工时**）|
| **规则可用率** | 规则能否导向一条「可发送 + 有可验证响应」的用例 | 无（SemFuzz 未报此指标）|
| **人工成本 / 协议** | 每接入一个新协议的人工工时，**分项列出** | SemFuzz 只报了「选消息类型 20 分钟」，**没报响应映射表成本**——我们公开它本身即贡献 |
| 下游效果 | 覆盖率 / 状态覆盖（`paths_found`）/ 崩溃数 / 漏洞候选数 | 见下方 5 条基线 |

#### fuzzing 对照基线（5 条 + 混杂因素控制）

1. 官方自带种子（ProFuzzBench `in-<proto>/`）
2. **同种子数量对齐组**（protorag 抽样到 baseline 同数量）
3. 规则版 rfc 抽取（无 LLM）—— 分离 LLM 贡献
4. 单模型无投票 —— 分离 ensemble 贡献
5. 无语义规则（只有名称+定义）—— 分离语义建模贡献

**除种子数量外，还必须控制**（评审 M6 第五点）：执行预算、总运行时间、**实际执行次数**、起始状态、种子有效率、目标版本、插桩环境、随机重复次数。否则覆盖率差异无法归因到 RFC 语义能力。

**关键警告**：SemFuzz 明确不用覆盖率（闭源不可插桩）。我们能插桩（AFLNet），**必须报覆盖率**，这是相对 SemFuzz 的优势。

### 2.3 建议的执行顺序（v2）

**只做一件事的话**：**里程碑 A**（评审「有条件通过」）。

理由：
- 改动集中在 `core/fused/rfc_extractor.py` 一个文件 + `scripts/build_hub.py` 两处，**不依赖 LLM、不改 ID 算法、不改下游契约、不增成本**
- 直接命中已实测的四个问题（15.2% 召回 / 50 条 TOC 垃圾 / 68 个 fact_id 冲突 / 父节信息丢失）
- 完成后 rfc 源从「6/8 协议不可用」变成「方法名可召回」，下游三层检索才有东西可用
- **先固化 golden md5**（8 协议 × 2 次抽取）作为回归护栏 —— 语义允许变，但「非预期行为变化」必须为零

**明确不做**（评审暂缓项）：里程碑 B 语义建模、D 投票、里程碑 C 跨协议变异引擎、反馈闭环。**它们是研究路线，不是本轮交付。**

## 第三部分　关键流程伪代码与核心数据结构

### 3.1 核心数据结构

```python
# ---------- 规范窗口（任务 A1.4 章节树 + 自底向上合并） ----------
@dataclass(frozen=True)
class SpecWindow:
    """带层级路径的规范文本窗口。参考 SpecGPT Algorithm 1 的自底向上合并。"""
    path: tuple[str, ...]        # 章节路径，如 ("4.1", "Basic Structure")
    section_no: str              # "4.1"
    title: str                   # 原始标题（可多词）
    level: int                   # 层级深度
    text: str                    # 合并后的正文（含子节）
    kind_hint: str | None        # 由 profile 的 *_sections 映射给出的类型提示

# ---------- 语义规则（里程碑 B1：两层模型，评审 T2） ----------
# 评审 T2 的核心批评：constraint_text 是自由文本 → 确定性引擎无法执行/校验/归因。
# 对策：拆成「证据层」与「可执行层」两层。不可转换为可执行规则的内容
#       只作 KnowledgeCandidate，不进自动生成链路。

@dataclass(frozen=True)
class EvidenceAnchor:
    """证据层：这条规则从哪来。用于溯源、人工复核、投票对齐。

    ★ 本层**不含规则身份**（规则身份属规则层，见 `SemanticRule.rule_id`）——
      本层只有 `evidence_id`：一条规则可有多条证据 → 多条 evidence_id。
      见 §2.1 审计项 I-1。
    """
    evidence_id: str                    # 本条证据自身的唯一 id（多条证据 → 多 id）
    spec_version: str                   # 规范版本，如 "RFC3261"
    section_path: tuple[str, ...]        # ("21", "1.1") 章节路径
    source_anchor: str                  # "file:rfc3261.txt#@10560"（★ 行锚点：行号按 splitlines() 口径，见下）
    span_text: str                      # ★ verbatim 原文片段（可为空 → 则不能定为 explicit）
    span_start: int | None              # 源文件**字符区间**起点（半开区间 [start, end)，供 B2 校验真实性）
    span_end: int | None                # 源文件**字符区间**终点（**半开区间**：raw[start:end] == span_text）
    # ★ 行锚点口径：RFC 原文含换页符 `\x0c`，`str.splitlines()` 会把它当行边界而
    #   `text.count("\n")` 不会 ⇒ **两种口径的行号相差 9~11 行**。本项目的行锚点
    #   一律采用 **splitlines() 口径**（与 core/fused/rfc_extractor.py 一致）；
    #   按 `\n` 口径核对将**全部对不上**。
    evidence_kind: str                  # "normative" | "abnf" | "table" | "prose"
                                      #   ★ 区分约束强度：MUST/SHOULD/MAY/ABNF 各不相同
    explicitness: str                   # "explicit" | "quoted" | "paraphrased"
    source_class: str                   # "normative_spec" | "observation" | "model_inference" | "human"
                                      #   ★ 评审 M1：四类来源分开，不能只靠 normative > observed

@dataclass(frozen=True)
class ExecutableConstraint:
    """可执行层：确定性引擎能解释、执行、校验的约束。"""
    target_field: str                   # 字段路径或消息级约束的字段名
    operator: str                       # "eq" | "ne" | "lt" | "gt" | "le" | "ge" | "in" | "present" | "absent" | "range"
    operand: tuple[str, ...]            # 比较值；空表示该算子无参（如 present）
    operand_source: str                 # "constant" | "field_ref"（长度由另一字段决定）
    operand_ref: str | None             # operand_source == "field_ref" 时指向该字段
    applies_to_state: tuple[str, ...]   # 适用的协议状态（空 = 任意状态）
    applies_to_method: tuple[str, ...]  # 适用的方法（空 = 任意）
    expected_behavior: str              # 期望行为类别，取自 rfc_config.expected_response_classes
    sender_role: str                    # 构造约束的发送方："client" | "server"
    receiver_role: str                  # 处理期望的接收方
    # ★ 评审 T2：构造约束与处理期望的 role 分开，不合并成一个 role
    precondition: Optional[str]         # 前置条件（可为空 = 无前置）

@dataclass(frozen=True)
class SemanticRule:
    """完整语义规则 = 证据层 + 可执行层 + 生命周期状态 + 规则身份。

    ★ `rule_id` 属**规则层**顶层；`EvidenceAnchor` 内只有 `evidence_id`
      （一条规则可有多条证据）—— 见 §2.1 审计项 I-1。
    """
    rule_id: str                        # 全局唯一，由结构化身份派生（§3.2）
    evidence: EvidenceAnchor
    constraint: ExecutableConstraint
    subject_type: str                   # "method" | "header" | "status" | "message_type"
    subject_name: str
    rule_state: str                     # ★ 评审 M1/T9：权威 / 候选 / 已撤销 / 实验反馈（四库分离）
    supersedes: tuple[str, ...]         # 被本规则替代的 rule_id
    model_confidence: float | None      # ★ 评审 T6：与 explicitness / 证据有效性**分开记录**
    validated: bool                     # B2 证据区间校验是否通过

@dataclass(frozen=True)
class KnowledgeCandidate:
    """知识候选：**不可转换为可执行规则**的内容。

    ★ 这是「不可转换者只作知识候选、不进自动生成链路」的**载体类型**。
      它**没有** constraint 字段 —— 结构上就装不下 operator/operand。
      落盘到独立文件 candidates.jsonl，自动生成链路**读不到**它（§3.3 强制机制 3）。
    """
    candidate_id: str
    evidence: EvidenceAnchor
    subject_type: str
    subject_name: str
    raw_text: str                       # 原始自由文本（仅供人工复核/检索）
    convertible: bool = False           # 恒为 False；显式保留以表达「曾尝试转换」
    reject_reason: Optional[str] = None # 为何不可转换（可观测性，评审 M4）

# ---------- 字段路径树（任务 C2，供变异引擎使用） ----------
@dataclass(frozen=True)
class FieldNode:
    path: tuple[str, ...]        # ("tls.handshake.extension", "type")
    value_type: str              # "int" | "bytes" | "string" | "enum"
    length_field: str | None     # 若本字段长度由另一字段决定，记录之（自动回填用）
    children: tuple["FieldNode", ...]

# ---------- 变异动作（任务 C4，SemFuzz 的抽象层/字节层分离） ----------
@dataclass(frozen=True)
class MutationAction:
    op: str                      # "add" | "remove" | "update"
    field_path: tuple[str, ...]
    position: str | None         # add 时用
    value: str | None            # None → 由引擎按上下文推断
    violation_of: str | None      # ★ 评审 M7：必须是 rule_id（唯一标识一条规则），
                                  #   不能是 "subject_name + constraint_kind"（不唯一）
    keep_violation: bool = True  # ★ 评审 T8：目标违规字段**不自动回填**，
                                  #   仅修复非目标的依赖字段（如长度字段）
```

### 3.2 抽取主流程（里程碑 A1 + B1 合并伪代码）

```python
def extract_rfc_semantics(protocol: str, cfg: RfcConfig) -> list[SemanticRule]:
    """从 RFC 规范抽取字段级语义规则。协议无关：一切协议差异来自 cfg（= profile 的 rfc 段）。"""

    # ---- A1-1：清洗（去页眉/页脚/form-feed/版权行）----
    raw = read_spec_files(protocol)                    # kb/<协议>/spec/*.txt
    cleaned = [strip_page_furniture(t) for t in raw]

    # ---- A1-2：★ TOC 识别与隔离（必须在章节树之前）----
    #   ★ 改进v2 问题①：原写法把 TOC 判定放在章节树之后 → TOC 行已进入树结构，
    #   事后过滤单个窗口无法恢复正确的树。正确顺序：
    #   清洗 → TOC 识别 → 标题识别 → 章节树 → 块解析 → 类型判定
    doc_lines, toc_lines = [], []
    for t in cleaned:
        for ln in t.split("\n"):
            (toc_lines if _is_toc_line(ln) else doc_lines).append(ln)
    #   TOC 行**单独保留为诊断信息**，不参与章节树构建（见 A0.3：TOC 不作有效规范证据）

    # ---- A1-3：标题识别（宽松形态，任务 A1.3 的内容；改进v2 问题①：必须先于章节树）----
    heads = [_parse_heading(ln) for ln in doc_lines]   # 多词标题；返回 (sec_no, title) 或 None

    # ---- A1-4：章节树 ----
    trees = [_build_section_tree(heads)]
    windows = []
    for tree in trees:
        windows += _merge_leaf_windows(tree)          # ★ 自底向上合并（SpecGPT Alg.1）
        windows += _collect_tables(tree)              # 状态码表等
        windows += _collect_abnf_blocks(tree)         # ABNF / 命令语法块

    # ---- A1-5：类型判定（语义判定，非形态猜测）----
    typed = []
    for w in windows:
        kind = _section_kind(w, cfg)                 # ★ 查 cfg.method_sections / field_sections / status_sections
        if kind is None:
            kind = _infer_kind_from_content(w)       # 语法块 → method；表头含 "Code reason" → status
        if kind is None:
            continue
        typed.append((kind, w))

    # ---- B1：语义抽取（SemFuzz 的 C/P）----
    rules = []
    for kind, w in typed:
        for para in _split_paragraphs(w):
            # 交叉引用回溯（任务 A1.7）
            ctx = _resolve_xref(para, trees)          # "see Section 3.2" → 拉入被引段落
            r = llm_extract_semantic_rule(
                kind=kind, window=w, paragraph=para, context=ctx,
                field_paths=field_paths_for(protocol),  # 任务 C2 的字段路径（可为空）
                expected_classes=cfg.expected_response_classes,  # ★ 词表注入，禁止自由生成
            )
            if r is None: continue
            # ★ 约束类判定：verifiable（可机械校验）→ normative(must)；否则 → advisory
            rules.append(_to_semantic_rule(r, kind, w, cfg))

    # ---- B2：置信度分级（已按评审 T6 重写）----
    # 原写法有三处错：① replace() 返回新对象但没写回列表 → 原对象不变；
    #              ② constraint_span 声明为 str 却允许 None → 类型契约矛盾；
    #              ③ 用 and 会让「有普通文本片段但无规范性依据」的规则**漏标** inferred。
    # 新写法：**就地改写**（rules[i] = ...），三个维度**分开**记录，
    #         且 explicitness 的判定**基于证据区间与证据类型**，不基于文本里是否出现 MUST。
    for i, r in enumerate(rules):
        ev = r.evidence
        # ★ 改进v2 问题⑧：**先验证证据，再判断它是否明确支持该约束**。
        #   原顺序是先按「证据类型 + 区间非空」设 explicit，再去验证区间 —— 可能把
        #   一个区间根本不存在的规则标成 explicit。
        #   ① 证据有效性：区间必须能在源文件里核对出来（B2）
        validated = _verify_span_in_source(ev)
        # ② explicitness：验证通过 **且** 证据类型是规范性 → explicit
        if validated and ev.evidence_kind in ("normative", "abnf"):
            explicitness = "explicit"
        elif ev.span_text:
            explicitness = "quoted"
        else:
            explicitness = "paraphrased"
        # ★ 关键分离（问题⑧）：**「约束可机械验证」≠「RFC 用 MUST 规定了它」**
        #   —— 前者由 operator/operand 决定，后者由 evidence_kind + explicitness 决定。
        #   两者必须分别记录，不能互相推导。
        rules[i] = replace(r,
                           evidence=replace(ev, explicitness=explicitness),
                           validated=validated,
                           model_confidence=r.model_confidence)
    # ★ 关键分离：**"没有规范性依据"不等于"该规则是模型推测"**
    #   → 用 explicitness / validated / model_confidence 三个独立字段表达。
    return rules
```

### 3.3 投票降幻觉（里程碑 D2）

```python
# ---------- 投票输入层包装（改进v2 问题⑥）----------
@dataclass(frozen=True)
class Candidate:
    """投票候选 = 规则 + 本次生成的运行时身份。
    ★ 模型身份/run_id 属于**运行时信息**，不属于规范规则本身 → 不放进 SemanticRule。
    """
    rule: SemanticRule
    model_id: str
    run_id: str


def vote_semantic_rules(
    per_model: list[list[Candidate]],
    theta: float = 0.75,
    quorum: int | None = None,
) -> tuple[list[SemanticRule], list[SemanticRule]]:
    """跨模型对齐 + 多数投票。

    ★ 本函数已按外部评审 T1 修正三处错误：
      ① 阈值：原写 N//2+2 —— 在 N=1/2 时要求票数 > 模型数，**永不通过**。
         改为严格多数 N//2+1（N=1→1, N=2→2, N=3→2, N=5→3）。
      ② 计票：原 votes=len(g) 计的是**候选数**，一个模型产出多个相似候选会人为抬票。
         改为按**模型去重**后计数（每模型每组最多一票）。
      ③ 对齐：原只比 span 重叠。span-overlap **不具传递性**
         （A≈B、B≈C 不蕴含 A≈C），简单聚类会混合互相矛盾的约束。
         改为：主体/规则类型/操作符/约束值/期望/证据位置**逐项比对**，
         span 重叠降级为**辅助条件**。

    返回 (确定规则, 待人工复核的不确定规则)
    """
    N = len(per_model)
    if N == 0:
        return [], []
    quorum = quorum if quorum is not None else (N // 2 + 1)   # ★ 严格多数

    # 1) 对齐：主判据 = 结构化字段全等；span 重叠仅作辅助
    #    ★ 改进v2 问题⑥：模型身份**不放在 SemanticRule 里**（规范规则不该携带
    #      「哪个模型推的」这种运行时信息），而是在投票输入层包装：
    groups = _align_by_structural_equality(per_model, theta=theta)

    confirmed, uncertain = [], []
    for g in groups:
        # ② ★ 按**模型**计票，不按候选数
        #    Candidate 包装层：Candidate(rule, model_id, run_id)
        voting_models = {c.model_id for c in g}
        votes = len(voting_models)
        if votes >= quorum:
            confirmed.append(_merge_group(g))        # 选证据最完整者（解包出 rule）
        elif len(g) == 1 and len(voting_models) == 1:
            # 单模型独有且未达 quorum → 丢弃（孤立候选噪声大）
            continue
        else:
            # ③ ★ 平票 / 未达 quorum 但有多模型支持 → 标记不确定而非丢弃
            #   理由（学 FlowFSM §VI 的取舍）："漏掉一条真实约束"比"多出一条候选"更危险
            uncertain.append(_merge_group(g, mark="uncertain"))
    return confirmed, uncertain

# ★ 评审 T1 的第四条未解风险（明确写出，不假装解决）：
#   当所有模型共享同一偏差时，投票无法识别集体错误（SpecGPT 未讨论）。
#   对策：① 保留 uncertain 队列进人工复核；② 关键规则用**不同 prompt 变体**二次仲裁；
#        ③ 不追求 100% 自动化 —— 目标是把"模型不确定"显式暴露出来，而不是掩盖。
```

### 3.4 状态感知生成与变异（里程碑 C4）

```python
def generate_semantic_violation_seeds(
    rules: list[SemanticRule],
    bundle: dict,
    profile: Profile,
) -> list[SeedCorpus]:
    """用字段级语义规则生成"刻意违规"的种子。

    ★ 借鉴 SemFuzz 的核心：LLM 只出符号动作，字节层由确定性引擎执行。
      论文给出的失败证据：直接让 LLM 改 hex，在 TLS 这类嵌套协议上会因长度字段
      未级联更新而产生大量无效用例。
    """
    seeds = []
    for r in rules:
        # ★ 改进v2 问题④：改用 v2 两层模型字段
        if r.evidence.explicitness == "paraphrased": continue   # 纯推测证据不用于自动生成
        if not r.validated: continue                            # 证据区间未通过校验 → 不进生成链路
        op = r.constraint.operator
        if op not in ("eq","ne","lt","gt","le","ge","in","present","absent","range"): continue

        # 1) 找一条能承载该约束的种子（协议会话前置已由 edge_cover 保证）
        base = _pick_seed_for(r, bundle)
        if base is None: continue

        # 2) LLM 只产出符号动作序列（SemFuzz Algorithm 2 的第 4 行）
        actions = llm_generate_actions(
            base_field_paths=_field_paths(base),
            constraint=_describe_constraint(r.constraint),      # 由可执行层生成描述（不手写自由文本）
            expected_class=r.constraint.expected_behavior,
            allowed_ops=("add","remove","update"),
        )
        if not actions: continue

        # 3) 确定性引擎执行（SemFuzz Algorithm 2 的第 5 行）
        mutated = apply_actions(base, actions, profile)   # ★ 长度字段自动回填
        if mutated is None: continue                       # 违反后语法不可编码 → 丢弃

        # 4) 标注违规点 + 期望响应类别 → 供 oracle 用
        mutated.violation_of = r.rule_id                 # ★ 问题④/M7：必须用唯一 rule_id
        mutated.expected_class = r.constraint.expected_behavior
        seeds.append(mutated)
    return seeds
```

### 3.5 反馈闭环（里程碑 C5~C7）

> ★ **编号说明**：本文件里的「C」有**三种**，互不相关，引用时请带前缀以免混淆：
>  · **oracle-C** = 三轴判定（本节 §3.5；对应 roadmap §5.1 的 C-1~C-7）——
>    判定顺序（UNKNOWN+TIMEOUT 最先）、EXITED 判别、reset/close 不算 crash 等。
>  · **convert-C** = 规则可转换性判定（roadmap §3.4 的 C1~C7；`try_convert` 的七步）——
>    no_span / span_unverified / non_normative_kind / operator_unresolved /
>    operand_unresolved / field_unbound / expectation_not_in_vocab。
>  · **milestone-C** = 里程碑 C 的任务号（本文件 §2.0 任务表的 C1~C7：
>    选协议 / 字段模型 / 编码 / 定向变异 / 三轴 oracle / 独立复现 / 归因记录）。
> 下文提到「C7 特例」等一律指 **convert-C**；「C5~C7」这类里程碑提法一律指 **milestone-C**。

```python
# ---------- 三轴执行结果模型（评审 T4：reset ≠ crash） ----------
class ProtocolOutcome(str, Enum):
    """协议层结果：服务端在协议语义上如何回应。"""
    SUCCESS = "success"                 # 符合期望的正常响应
    PROTOCOL_ERROR = "protocol_error"   # 协议层错误响应（4xx/5xx 等）
    APPLICATION_ERROR = "application_error"  # 协议层成功但应用层拒绝
    SILENCE = "silence"                 # 无响应但不拒绝（协议允许丢弃）

class TransportOutcome(str, Enum):
    """传输层结果：连接发生了什么。"""
    RESPONSE = "response"
    RESET = "reset"                     # ★ TCP RST —— **不是 crash**
    CLOSE = "close"                     # 主动断开
    TIMEOUT = "timeout"

class ProcessHealth(str, Enum):
    """进程健康：只有这里能证明崩溃。"""
    ALIVE = "alive"
    EXITED = "exited"                   # 进程退出
    RESTARTED = "restarted"             # 异常重启
    SANITIZER_FAILURE = "sanitizer_failure"   # ASAN/UBSAN 报告
    UNKNOWN = "unknown"


def close_loop(seed: SeedCorpus, result: ExecResult,
               expected: str | None = None) -> Feedback | None:
    """把执行结果回流成可用的反馈信号。

    ★ 已按评审 T4 重写：原写法把 `reset` 与 `crash` 并列判定，这是错的 ——
      TCP reset / 主动断开 / 拒绝非法请求**都不等价于服务进程崩溃**，
      很多协议允许对非法输入直接丢弃或关闭连接。
      timeout 同理：可能来自丢包、负载、静默丢弃、状态不匹配或真死锁。

    三轴分离后，**只有独立的进程健康证据**才进 crash 路径。

    ★ `expected` 由**调用方显式传入**；`None` = 「无处理期望」⇒ **跳过**语义偏离判定
      （**不回退**读 `seed.expected_class` —— 否则该契约会被种子的属性破坏）。
    """
    proto = classify_protocol_outcome(result)   # → ProtocolOutcome
    trans = classify_transport_outcome(result)   # → TransportOutcome
    health = probe_process_health(result)        # → ProcessHealth（canary 探测）
    # ★ expected 直接取形参（见签名），不再从 seed 回退读 seed.expected_class。

    # ---- ① 进程健康未知 + 传输超时 → **最先判定为不确定** ----
    #   ★ 改进v2 问题⑦：原顺序里 `proto != expected` 在 inconclusive 之前，
    #   导致 health=UNKNOWN & trans=TIMEOUT 的超时被误判成「语义偏离」。
    #   超时的原因未知（丢包/负载/静默丢弃/状态不匹配/真死锁），不能断言偏离。
    if health is ProcessHealth.UNKNOWN and trans is TransportOutcome.TIMEOUT:
        return Feedback(kind="inconclusive", expected=expected, actual=proto,
                        transport=trans, health=health,
                        violated=seed.violation_of, seed=seed)

    # ---- ② crash 路径：必须有**独立证据**，且 EXITED 需判别退出原因 ----
    #   ★ 问题⑦：EXITED 不能不加区分地当崩溃 —— 目标正常退出（如收到 QUIT 后退出）
    #   也是 EXITED。必须结合退出码 / 退出原因 / 目标生命周期判断。
    if health in (ProcessHealth.RESTARTED, ProcessHealth.SANITIZER_FAILURE):
        repro = reproduce(seed)   # 形参：注入式可调用对象（里程碑 C6：canary 健康探测）
        return Feedback(kind="crash", reproducible=repro.ok,
                        health=health, transport=trans,
                        violated=seed.violation_of, seed=seed)
    if health is ProcessHealth.EXITED:
        # 区分「异常退出」与「正常退出」：由 canary 探测目标生命周期
        abnormal = _is_abnormal_exit(result)   # 退出码非 0 / 有 sanitizer 报告 / 非请求收尾导致
        if abnormal:
            repro = reproduce(seed)
            return Feedback(kind="crash", reproducible=repro.ok,
                            health=health, transport=trans,
                            violated=seed.violation_of, seed=seed)
        return Feedback(kind="target_exited_normally", reproducible=None,
                        protocol=proto, transport=trans, health=health,
                        violated=seed.violation_of, seed=seed)

    # ---- ③ 传输异常但进程健康 → 只是**候选**，不是崩溃 ----
    if trans in (TransportOutcome.RESET, TransportOutcome.CLOSE):
        return Feedback(kind="connection_aborted", reproducible=None,
                        protocol=proto, transport=trans, health=health,
                        violated=seed.violation_of, seed=seed)

    # ---- ④ 语义偏离：期望与实际协议结果不符（此时健康已知且非超时）----
    if proto != expected:
        return Feedback(kind="semantic_deviation",
                        expected=expected, actual=proto,
                        transport=trans, health=health,
                        violated=seed.violation_of, seed=seed)

    return None   # 符合预期 → 无反馈

# 覆盖率回流（任务 B5 / C7）：未被覆盖的规则 → 只调选择优先级，不改规则内容
# ★ 改进v2 问题⑤：反馈**不改规则内容**，只改调度信号。
#   原写法把提示词补强直接写回 constraint_text —— 与 B5「覆盖率只调选择优先级」冲突，
#   且会改变规则身份/哈希、让 RFC 规范事实被实验反馈污染。
#   改为独立的反馈表：rule_id → {priority_score, selection_count, coverage_signal}
def reflow_rules(rules: list[SemanticRule],
                 feedback: dict[str, dict]) -> list[SemanticRule]:
    """按反馈表调整规则的**选择优先级**，返回按优先级排序的规则列表。

    ★ 规则本身（evidence / constraint）**一字不改** —— 反馈是独立数据，
      不写回 SemanticRule。规范事实与实验反馈严格分离（B5 四库分离）。
    """
    def priority(r: SemanticRule) -> float:
        fb = feedback.get(r.rule_id) or {}
        return float(fb.get("priority_score", 0.0))
    # 排序稳定：同优先级保持原顺序（按 rule_id 兜底，保证确定性）
    return sorted(rules, key=lambda r: (-priority(r), r.rule_id))
```

**契约（`close_loop` 的 `expected`）**：`expected` 由**调用方显式传入**，是期望结果的**唯一来源**。★「无处理期望」有**两种等价表示**——`None`（调用方未提供）与 `""`（B 阶段 `try_convert` 的 **convert-C7** 特例产出：缺处理期望时 `ExecutableConstraint.expected_behavior == ""`，**不是 None、不猜一个**）；`close_loop` 内部**统一归一为 `None`**，两者都 ⇒ **跳过**语义偏离判定，只走传输层与进程健康判定（与 **convert-C7** 的特例一致，见 roadmap §3.4：`expected_behavior` 缺失**不阻断**转换，缺处理期望的规则只能用于「构造违规种子」，不能用于「判定 oracle 预期」）。

**契约（`close_loop` 的 `reproduce`）**：`reproduce` 是**注入式可调用对象**（形参，**非全局函数**）；调用方传入 `reproduce(seed)` 即可。★ **未注入时 `reproducible` 记为 `None`（未探测）**，而**不是**「不可复现」——「未探测」与「不可复现」是两种不同的结论，这是评审 T4 关心的语义。

### 3.6 与现有代码的接口对接（关键：改造点在哪）

| 新能力 | 落点 | 复用现有 |
|---|---|---|
| `SpecWindow` / 章节树 | `core/fused/rfc_extractor.py`（新增函数）| 复用 `_clean_body`（已能清页眉页脚）|
| `SemanticRule` | `core/fused/models.py`（新增 dataclass）+ `core/fused/registry.py`（注册 aspect）| 复用 `Subject` / `Fact` / `ConditionAlways` / `ConditionPredicate` |
| `map_norm_to_facts` 扩展 | `core/fused/norm.py`（`RFC_KIND_MAP` 增 "constraint" / "expectation"）| 复用现有 kind→Fact 分派 |
| 期望响应词表 | `fused_hub/targets/<协议>/profile.json`（新增段）+ `core/fused/rfc_extractor.py` | 复用 `profile.seedgen` 的 per-protocol 配置模式 |
| 投票层 | 新建 `core/fused/llm_ensemble.py` | 复用 `core/llm.py` 的 `chat_json` |
| 字段路径树 | 新建 `core/fused/downstream/field_mutation.py` | 复用 traffic 源已抽出的真实字段值（P4 成果）|
| 变异引擎 | 同上 | 复用 `core/fused/downstream/edge_cover.py` 的 `build_message` |
| 语义 oracle | 新建 `core/fused/downstream/response_oracle.py` | 复用其现有 SIP 响应码正则 |
| bundle 契约 | `core/fused/downstream/rag_seedgen.py:assemble_bundle` | **新增 `semantic_rules` 键**（下游三层的输入）|

**bundle 契约扩展（唯一的破坏性改动）**：

```python
# core/fused/downstream/rag_seedgen.py: assemble_bundle 返回值新增
# ★ 改进v2 问题④：必须与 §3.1 的 v2 两层模型**完全一致**，
#   不再使用已删除的 constraint_kind / constraint_text / constraint_span /
#   expectation_class / confidence 这套旧字段。
{
    ...现有键...,
    "bundle_schema_version": "2.0",   # ★ 新增：契约版本，下游按版本分支（旧 bundle 缺此键 → 视为 "1.0"）
    "semantic_rules": [          # ★ 新增：字段级语义规则（里程碑 B 产出）
        {
            # ---- 证据层（§3.1 EvidenceAnchor）----
            "rule_id": "rfc3261.21.1.content_length.must_match_body",
            "spec_version": "RFC3261",
            "section_path": ["21", "1.1"],
            "source_anchor": "file:rfc3261.txt#@10560",
            "span_text": "The Content-Length header field MUST equal the size of the message body",
            "span_start": 10560,
            "span_end": 10642,
            "evidence_kind": "normative",       # normative|abnf|table|prose
            "explicitness": "explicit",          # explicit|quoted|paraphrased
            "source_class": "normative_spec",    # normative_spec|observation|model_inference|human
            # ---- 可执行层（§3.1 ExecutableConstraint）----
            "target_field": "Content-Length",
            "operator": "eq",
            "operand": ["field_ref:Body"],
            "operand_source": "field_ref",
            "operand_ref": "Body",
            "applies_to_state": [],
            "applies_to_method": [],
            "expected_behavior": "protocol_error",
            "sender_role": "client",
            "receiver_role": "server",
            # ---- 规则级字段（§3.1 SemanticRule）----
            "subject_type": "header",
            "subject_name": "Content-Length",
            "rule_state": "authoritative",       # authoritative|candidate|revoked|feedback
            "supersedes": [],
            "model_confidence": 0.91,
            "validated": True,
        },
    ],
    # ★ 期望词表：只含**协议层**结果类别。timeout / crash 属于传输轴与进程健康轴
    #   （§3.5 三轴模型），不是普通 RFC 协议响应期望 → 不进此词表。
    "expected_response_classes": ["success", "protocol_error", "application_error", "silence"],
}
```
`edge_cover` / `generic_danger` / `vuln_boundary` / `canonical` 四层**不改签名**（向后兼容），新增能力以可选参数注入。

**bundle 契约的版本化要求（改进v2 问题④的延伸）**：新增 `semantic_rules` 是**破坏性改动**，须配套

1. `bundle_schema_version` 字段（当前 `"2.0"`），下游按版本分支，避免旧 bundle 被新代码误读；
2. `semantic_rules` **为空时视为缺失**（不报错），保证 A 阶段（只产出旧式知识）时 bundle 仍可用；
3. 下游消费入口统一走 `bundle.get("semantic_rules") or []`，**不得**用 `bundle["semantic_rules"]` 直接索引。

---

## 第四部分　风险点与应对措施

| # | 风险 | 等级 | 触发条件 | 应对 |
|---|---|---|---|---|
| R1 | **LLM 成本失控** | 高 | 里程碑 D 全量投票 | SpecGPT 实测 5 模型 ensemble **$1.5~2.7/协议/次**、10~202 分钟/协议。**投票做成默认关闭的开关**；先用「单模型 + 规则过滤」跑通全链路，只在消融实验时开投票。按 Table IV 的精度/延迟比选模型（GPT 4o 20 分钟 vs Gemini 2.5 Pro 202 分钟但精度接近）|
| R2 | **Phase 1 改动引入回归** | 中 | 重写 `_extract_rfc_file` | 现有确定性是干净的（8/8 逐字节一致）→ **改造前先固化 golden 文件**（8 协议 × 2 次抽取的 md5），每次改动后 diff。语义允许变、但「非预期协议的行为变化」必须为零 |
| R3 | **profile 段膨胀** | 中 | A0.2 + B3 + 里程碑 D 适配包都往 profile 加段 | profile.json 会变成大杂烩。**建议分层**：`profile.json`（协议身份 + 现有段）、`rfc_config.json`（抽取配置）、`adapter.json`（人工适配包）三文件分离 |
| R4 | **人工成本被低估** | 中 | 里程碑 D（协议适配包）| SemFuzz 报了「选消息类型 20 分钟」，**没报响应映射表成本**（那才是大头）。我们必须**实测并公开**每项人工成本，否则「通用性」无法证伪 |
| R5 | **跨引用回溯引入幻觉** | 中 | 任务 A1.7 | 回溯来的段落可能被误当规范要求。**约束**：回溯内容只作 context，不作「显式约束」的依据；只有原文段落本身能产出 `evidence.explicitness == "explicit"`（改进v2 问题④：字段名统一为 v2 两层模型）|
| R6 | **状态机与语义规则冲突** | 中 | 里程碑 B + C | rfc 源的状态转移（source 源也有）与字段级约束（rfc 源）可能矛盾。**处置**：两者并存于 bundle，`resolver.py` 按 `epistemic_type` 排序（normative > observed），冲突进 audit 不静默丢弃 |
| R7 | **fact_id 语义变更破坏下游** | 中 | 里程碑 A（ID 治理，**已推迟**）| ID 是跨源去重键。改派生方式会使**已落盘事实的 ID 全变**。**处置**：ID 派生规则变更走版本号（`fact_key.version` 从 1.0 → 1.1），旧事实保留；或只对 rfc 源启用新规则并记录 |
| R8 | **后续里程碑收益不确定** | 高 | 全部 | 里程碑 A 是**确定性收益**（召回 15.2%→95% 是可证的），B/C/D 是**概率性收益**（投票、闭环）。**务必按里程碑分别验收，不要捆成一个 milestone** |
| R9 | **字段路径树依赖 dissector** | 高 | 任务 C1/C2 | 无 dissector 的协议拿不到字段路径 → 里程碑 C 无法做。这是**硬前提**，同 SemFuzz。必须明确「哪些协议有可逆 parser」|
| R10 | **期望响应 oracle 二值化过粗** | 中 | 里程碑 B3 | SemFuzz 用 2 档（normal/error），我们若也只 2 档会丢掉分辨率。**建议 5 档**（success/protocol_error/app_error/timeout/crash），但每多一档，per-protocol 映射的人工成本线性上升 → 需权衡 |
| R11 | **投票的集体错误** | 中 | 任务 D2 | 所有模型共享同一偏差时投票无效（SpecGPT 未讨论）。**应对**：prompt 变体二次仲裁 + 保留 uncertain 队列进人工复核，不追求 100% 自动化 |
| R12 | **评测集本身不可靠** | 高 | 外部评测 | 若人工基准有偏（FlowFSM 未报标注人数/一致性），结论不可信。**必须**：多标注者 + 仲裁 + 报一致性（Cohen's κ）；且**评测集与投票参数分离**（避免 SpecGPT 那种同一 θ 管两事的循环）|
| R13 | **下游 fuzzing 不改善** | 高 | 全阶段 | rfc 源修好了，不代表覆盖率提升（当前 SMTP 的落后源于**种子形态**而非 rfc 知识）。**必须诚实**：把「知识抽取质量」与「fuzzing 效果」分开评估，不因前者好看而声称后者 |
| R14 | **磁盘与算力** | 低 | 实验 | 当前 VM 磁盘 4.9G（95%）。投票实验 token 成本换算成存储可控，但多模型并发 + 多轮迭代会吃 CPU。实验前清空间（dangling 镜像 ~1.2G 可回收）|

### v2 新增风险（来自外部评审，均已核实成立）

| # | 风险 | 等级 | 触发条件 | 应对 |
|---|---|---|---|---|
| R15 | **协议无关性是伪命题** | 高 | 宣称"支持任意 RFC"时 | 评审 G1：DNS 的 `QTYPE` 是字段、SMTP 的 `EHLO` 是命令、TLS 的 `ClientHello` 是握手消息 —— **统一的 ABNF 抽取无法区分**。→ 改用**能力等级 L1~L5**（§2.0.5）诚实呈现自动化覆盖程度；并做**从未参与开发的新协议**的零配置测试，区分「通用能力」与「人工注入的知识」|
| R16 | **`allowed_methods` 造成信息泄漏** | 高 | 用它当 method 召回的真值集 | 评审 M6：该字段是 profile.json 里**人工撰写**的配置，既当输入又当标准 = 循环论证。**已实测该风险真实存在**：RTSP 的 allowed_methods 有 8 个，rfc 实抽 11 个，差集 `ANNOUNCE`/`RECORD`/`REDIRECT` **是真实 RTSP 方法**（只是 profile 没列）→ 按"不在列表即垃圾"判定会误判。→ **必须建独立人工标注真值集**，且区分「命令/字段/消息类型」三类 |
| R17 | **章节召回提升可能换成假章节激增** | 高 | 放宽标题正则后 | 评审 M6：命中率 ≠ 正确率。→ 每步**同时测 P 与 R**（§2.2 内部评测已加 precision / 层级正确率 / TOC 误删三项）；**误删比漏抽更危险**（正文含数字的行被当 TOC 删掉）|
| R18 | **上下文膨胀** | 中 | 里程碑 A1.4 自底向上合并 | 评审 F2：父节正文被每个子节携带 → 重复上下文 + 截断 + 错误引用传播。→ **有预算的上下文组装**：最大展开深度、去重、引用环检测；**静态解析与 LLM 上下文构造分离**|
| R19 | **并发构建互相覆盖** | 中 | 多任务并行 build | 评审 M2：两个任务同时覆盖 `rfc.jsonl`、旧任务覆盖新版本。→ **幂等键**（build_id + 输入哈希 + 配置版本 + 模型版本）；每次生成**独立快照**，验证通过后**原子切换** |
| R20 | **失败被误判为"无约束"** | 中 | 解析失败 / LLM 失败 | 评审 M3：不能所有错误都变成空结果，也不能都触发全局失败。→ 区分**文档解析失败 / 块分类失败 / 证据不匹配 / 模型调用失败 / JSON 校验失败 / 字段无法编码 / 目标不可达 / oracle 不确定**；报告必须能区分「没抽到规则」与「抽取失败」|
| R21 | **提示注入与越权** | 中 | 把 RFC/流量/专家笔记喂 LLM | 评审 M5：外部文本可能含注入；LLM 输出的字段路径/变异动作**不能获得任意文件访问或命令执行**。→ 模型输入/输出边界校验、敏感信息脱敏、**变异动作走操作白名单 + 编码器校验**、协议目标白名单、容器隔离、审计日志 |
| R22 | **规范版本漂移** | 中 | 同字段被多版本 RFC 约束 | 评审 M1：同一字段可能同时受多个规范版本约束，且有 MUST/SHOULD/条件例外。→ `EvidenceAnchor.spec_version` + `rule_state`（权威/候选/已撤销/实验反馈四库分离）+ `supersedes`；**`normative > observed` 不足以完成消解** |
| R23 | **证据被推断污染** | 中 | LLM 复述规范 | 评审 T9：覆盖率提示词若直接写回 `constraint_text`，会污染权威规则且改变规则哈希。→ 覆盖率**只调选择优先级**；规则内容**只增不删**只适用于**规范事实**，不适用于实验反馈 |
| R24 | **集体错误无法被投票发现** | 中 | 里程碑 D1 | 评审 T1 补充：所有模型共享同一偏差时投票失效（SpecGPT 未讨论）。→ 保留 uncertain 队列进人工复核 + 关键规则用**不同 prompt 变体**二次仲裁；目标是**暴露不确定性**而非掩盖 |

### v2 的风险处置原则（评审 §五 的核心意见）

> **先证明知识正确，再证明规则可执行，最后证明 fuzzing 有收益。**

对应到里程碑：**A 证明知识正确 → B 证明规则可执行 → C 证明 fuzzing 有收益 → D 按价值扩展**。
阶段 0~1 是**确定性收益**（可证），阶段 2~5 是**概率性收益**（不确定），**务必按里程碑分别验收，不要捆成一个 milestone**。

---

## 附录　与论文结论的对应关系（便于评审追溯）

| 我们的设计决策 | 借鉴自 | 论文依据 |
|---|---|---|
| 章节自底向上合并（任务 A1.4）| SpecGPT Algorithm 1 | SpecGPT §III-C-b：段落切分过细→无效查询多；章节合并保留上下文 |
| TOC 判定（任务 A1.2）| SpecGPT §III-C-a | SpecGPT 明确把目录列入需正则清理的噪声 |
| 交叉引用回溯（任务 A1.7）| SpecGPT Cross-Reference Handling | SpecGPT §III-D-b：多文本 + 章节号前缀，无需向量库 |
| span-overlap 对齐 + θ=0.75（任务 D2）| SpecGPT §III-E | SpecGPT 定义 Overlap 与四条对齐条件 |
| 投票阈值/平票/集体错误三条退化规则（任务 D2）| **我们自补**（SpecGPT 未定义）| 论文未给 → 显式实现并注释来源 |
| 增量门控「只增不删」（任务 D1）| FlowFSM Fig.4 Rules 1/2/3/5 | FlowFSM §IV-C 的 updateFlag 机制 |
| 抽象层/字节层分离（任务 C4）| SemFuzz §3.5.1 | SemFuzz 给出失败证据：LLM 直接改 hex 在嵌套协议上产生级联长度不一致 |
| 期望响应词表固化（任务 B3）| SemFuzz §3.4 | SemFuzz 强制 LLM 输出限于 Normal/Error 两类，保证 oracle 可比较 |
| 显式崩溃复现（任务 C6）| **我们改进 SemFuzz**（它靠下一条策略错配间接发现，有 off-by-one）| SemFuzz 附录 D 显示崩溃表现为 timeout→error |
| 人工成本全项公开（里程碑 D）| **我们补 SemFuzz 的空白**（它只报了选消息类型 20 分钟）| SemFuzz §5 只量化了消息类型选择 |

## 附录　《改进v2.md》一致性评审 → v3 处置追溯表

| # | 评审问题 | 级别 | 复核结论 | v3 处置位置 |
|---|---|---|---|---|
| ① | A 阶段解析顺序仍写错（TOC 在章节树之后）| 阻塞 | 成立（§3.2 伪代码与 §2.0 顺序不一致）| §3.2 步骤重排（`toc_lines` 隔离）；A1 任务表**重编号** |
| ①b | A1.3 章节树 / A1.4 标题放宽 实施依赖颠倒 | 阻塞 | 成立 | A1.3 = 标题放宽、A1.4 = 章节树；依赖列 + 5 处交叉引用同步 |
| ② | TOC 清除与证据保留矛盾 | 重要 | 成立 | A0.3「正文进 Fact / TOC 只进诊断」 |
| ③ | 质量闸缺可执行前提（无真值集则构建失败）| 重要 | 成立 | A0.4 拆分「构建质量闸（阻断）」+「离线评测（发布准入）」 |
| ④ | 新数据模型与旧伪代码不匹配 | 阻塞 | 成立（最明显问题）| §3.4 改 v2 字段；§3.6 bundle 按两层模型重写 + 版本化；R5 字段名统一 |
| ⑤ | 反馈仍修改权威规则内容 | 阻塞 | 成立 | §3.5 `reflow_rules()` 改为纯排序（`priority_score`） |
| ⑥ | 投票引用未定义的 `model_id` | 重要 | 成立 | §3.3 引入 `Candidate(rule, model_id, run_id)` |
| ⑦ | Oracle 判定顺序 + EXITED 不分 + timeout/crash 不该是协议期望 | 重要 | 成立 | §3.5 判定顺序重排 + `_is_abnormal_exit`；bundle 词表去 timeout/crash |
| ⑧ | 证据显式性判断顺序不严谨 + 可验证≠规范性强制 | 重要 | 成立 | §3.2 先 `_verify_span_in_source` 再判 explicitness；两者显式分离 |

**一致性清理的验证方式**（可复算）：

```bash
# 只扫描 ```python 代码块（正文与表格里的「引用旧字段名」说明不算残留）
python - <<'PY'
import re, pathlib
src = pathlib.Path("docs/rfc_source_reform_plan.md").read_text(encoding="utf-8")
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
code = "\n".join(blocks)
old = ["r.confidence", "r.constraint_kind", "r.constraint_text", "r.expectation_class",
       "constraint_text=", "constraint_kind=", "expectation_class=", 'confidence="explicit"']
print("旧字段残留:", {k: code.count(k) for k in old} or "全部为 0")
new = ["class Candidate", "EvidenceAnchor", "ExecutableConstraint", "rule_id",
       "validated", "explicitness", "priority_score", "_is_abnormal_exit",
       "toc_lines", "_parse_heading", "bundle_schema_version", "model_id", "run_id"]
print("新结构计数:", {k: code.count(k) for k in new})
PY
```

> 说明：本文档 §0 追溯表与风险条目会**引用**旧字段名来说明「已删除哪些字段」，那是**说明性文字**而非代码残留；上面的校验只扫 Python 代码块，因此不受影响。

---

## 附录　外部评审意见 → v2 处置追溯表

| 评审条目 | 级别 | 复核结论 | v2 处置位置 |
|---|---|---|---|
| G1 协议无关性是伪命题 | 阻塞 | 成立 | §2.0.5 能力等级 L1~L5；§2.2 独立真值集；R15 |
| G2 近期/长期目标混在一起 | 重要 | 成立 | §2.0 改为**里程碑制**（A/B/C/D 独立验收）|
| G3 论文机制适用范围未验证 | 重要 | 成立 | §1.3 可组合性分析；D2 投票降为可选增强 |
| T1 投票算法错误 | 阻塞 | **成立（已实算验证）**：阈值 N//2+2 在 N=1/2 时永不通过 | §3.3 修正为严格多数 + 按模型计票 + 结构化对齐；D2 |
| T2 SemanticRule 不可执行 | 阻塞 | 成立 | §3.1 拆为 `EvidenceAnchor` + `ExecutableConstraint` 两层；B1 |
| T3 字段路径树与变异引擎循环依赖 | 阻塞 | 成立（我写错了）| 里程碑 C 顺序改为「解析→字段模型→编码→往返一致→动作」；C1 只选一个协议 |
| T4 oracle 把 reset 当 crash | 阻塞 | 成立（且现有 oracle 只判响应码）| §3.5 三轴模型（ProtocolOutcome / TransportOutcome / ProcessHealth）；C5 |
| T5 fact_id 冲突根因未查 | 阻塞 | **成立，我已查明**：68/68 是同一 fact_key 被抽两次 | A0.3 消除重复抽取（**不改 ID 算法**）；§2.0 基线表已更新 |
| T6 置信度判定伪代码三处错 | 重要 | 成立 | §3.2 重写（就地改写 + 三维度分离）|
| T7 解析顺序与启发式误判 | 重要 | 成立 | A1 执行顺序固定；A1.5 区分命令/非终结符/字段 |
| T8 长度回填消除测试意图 | 重要 | 成立 | §3.1 `MutationAction.keep_violation`；C4 编码后重校验 `violation_of` |
| T9 单调更新污染知识库 | 重要 | 成立 | B5 四库分离；覆盖率只调优先级 |
| T10 LLM 契约隐性变化 | 重要 | 成立 | §2.0.6 双模式 `rules_only` / `semantic_enhanced` |
| F1 改造范围被低估 | 重要 | 成立 | §2.0.0 兼容性清单 + 数据回退设计 |
| F2 章节合并上下文膨胀 | 重要 | 成立 | A1.4 有预算的上下文组装；R18 |
| F3 投票成本被低估 | 重要 | 成立 | D1 选择性仲裁 + 记录每条规则成本 |
| F4 「支持/不支持」二分法 | 重要 | 成立 | §2.0.5 能力等级 |
| F5 回退机制不完整 | 重要 | 成立 | §2.0.0 独立命名空间 + 快照原子切换；A0.5 幂等键 |
| M1 缺版本化/证据状态/冲突语义 | 阻塞 | 成立 | B4 + `rule_state` + `supersedes` + 四类 source_class |
| M2 缺并发与幂等 | 重要 | 成立 | A0.5；R19 |
| M3 错误处理缺分类 | 重要 | 成立 | A0.6；R20 |
| M4 可观测性不足 | 重要 | 成立 | §2.2 内部评测 11 项指标；A0.4 质量闸 |
| M5 安全/权限/执行隔离 | 重要 | 成立 | R21 |
| M6 验收口径问题 | 阻塞 | **全部成立** | §2.2 全节重写（P/R/F1 + 层级正确率 + 独立真值集 + 混杂因素控制）|
| M7 崩溃归因证据不足 | 重要 | 成立 | `violation_of` 改指 `rule_id`；C7 归因记录 |
| 替代方案 A→B→验证→C/D | — | 采纳 | §2.0 里程碑 A/B/C/D；§2.3 只做里程碑 A |

## 附录　论文原文获取位置

| 论文 | 来源 | 本地临时路径（未写入文献库）|
|---|---|---|
| FlowFSM | arxiv.org/pdf/2507.11222 | `%TEMP%\papers\flowfsm.pdf` |
| SpecGPT | arxiv.org/pdf/2510.14348 | `%TEMP%\papers\specgpt.pdf` |
| SemFuzz | `E:\科研\文献\文献资料\SemFuzz： A Semantics-Aware Fuzzing Framework for Network Protocol Implementations.pdf` | 已有原文 |
