docs/实施/project_taskbook.md

定位：本文件是项目调试任务书，覆盖从当前阶段到阶段 6 完成的全部任务。任何 session 开始前按 docs/工具/agent_rules.md 第六章的顺序读取。

一、项目目标

项目目标：面向目标协议实现的协议模糊测试。输入五类知识源（RFC 规范、expert_note 专家笔记、数据流量、历史漏洞、协议实现源码），通过 RAG 与 LLM 抽取知识，融合到结构化知识中枢，再由 LLM 基于融合知识生成高质量初始种子（.raw），供 AFLNet 等 fuzzing 引擎使用。

二、整体路线图

阶段 0.5：前置阶段。kb/ 全程 read-only。已完成。

阶段 1：KB 结构从 6 文件扩到 13 文件。新增 7 个 extractor。建 protocol_profile 中枢。加 expert_note_template 与 expert_note_minimal。收尾 611 passed。kb/ 授权窗口关闭。已完成。

阶段 2：RFC 独立驱动。输入 kb/spec/rfc2326.txt。验收口径：dispatcher 识别 rfc family，rfc extractor 抽 norm，TypedKB.build 单源，seedgen 单源生成 .raw，AFLNet 可消费。进行中，当前处在中枢前置建设末端。

阶段 2.5（内嵌于阶段 2）：结构化知识中枢建设。含 Storage Contract、Runtime I/O Contract、Pipeline Contract 三套设计与实现。当前 Storage 与 Runtime 已 Final Frozen。Pipeline Contract 已收口到 v0.4.7 Final Freeze Candidate，待 Gate B 与 Final Frozen。

阶段 3：数据流量独立驱动。输入 kb/数据流量/ 下 pcapng 与 ndjson。默认 kb/ read-only。

阶段 4：协议实现源码独立驱动。输入 kb/协议实现源码/ 下 live555 C++。默认 kb/ read-only。

阶段 5：expert_note 与历史漏洞入中枢。两者是补充信息源，流程到结构化知识中枢停止，不产 .raw，不做独立驱动。默认 kb/ read-only。

阶段 6：五源综合。union 生成综合 .raw。

三、常设机制引用

本任务书依赖 docs/工具/agent_rules.md 的十条固定约束。任何 session 开始前必须先读该文件。

越界审计：见 agent_rules.md 第四章。
决策点必须停：见 agent_rules.md 第五章。
pytest 规范：见 agent_rules.md 第八章。
长期审计准则：见 agent_rules.md 第十章。

契约索引见 local/contracts/README.md。六份契约正文在 fused_hub/docs/ 下，按需读取，不在此复制。

四、当前阶段任务

当前阶段：阶段 2 的中枢前置建设末段。

子任务 A：Pipeline Contract Final Freeze。
目标：把 fused_pipeline_v1.md 从 v0.4.7 Final Freeze Candidate 升级为 Final Frozen。
前置：Gate A 已 PASS。Gate B 落盘（Step 3.2b）、Pipeline Contract 占位符替换与 Final Hygiene（Step 3.2c）、Final Freeze Verification 与 Final Frozen 落盘（Step 3.2d）待执行。
验收：四份契约全部 Final Frozen。pipeline_status.md 与 project_handoff.md 已更新。

子任务 B：阶段 2 主线恢复。
目标：把 RFC 单源从中枢消费到 seedgen 产出 .raw。
前置：Pipeline 实现完成，Fused Facts 可生成。
验收：RFC 单源驱动到 seedgen，产出至少 1 个 .raw，AFLNet 可消费。
依赖：Pipeline 实现。

五、后续阶段任务

Pipeline 实现。
目标：把 Pipeline Contract 落地为可执行代码。
范围：core/fused/pipeline/ 下实现 Candidate DTO、Candidateization、Normalization、Fact Identity Resolution、Semantic Relation Detection、Evidence 与 Claim Materialization、Phase A、Phase B、Lineage、Audit、Graph Derivation、Profile Derivation、Build Finalization、Deterministic Replay。
拆分建议：按模块分阶段指令，每阶段一次汇报。例如 Candidate 层、Fact 与 Claim 层、Phase A 与 B 层、Graph 层、Finalization 与 Replay 层。
验收：Pipeline Contract 所有条款有对应实现，端到端跑通 RFC 单源 build，产出 Fused Facts，pytest 全绿。

阶段 3：数据流量独立驱动。
输入：kb/数据流量/ 下 pcapng 与 ndjson。
验收：dispatcher 识别 traffic family，traffic extractor 抽 norm，TypedKB.build 单源，seedgen 单源生成 .raw。
注意：classifier 与 dispatcher 已经过 B1 修复，单源过滤应当直接生效。

阶段 4：协议实现源码独立驱动。
输入：kb/协议实现源码/ 下 live555 C++。
验收：同阶段 3。
注意：source 源当前无 extractor，可能需要新建。

阶段 5：expert_note 与历史漏洞入中枢。
输入：kb/expert_note/ 与 kb/历史漏洞/。
验收：两源入中枢，profile 与 spec_graph 相应更新。不产 .raw。

阶段 6：五源综合。
输入：五源产物 union。
验收：综合 .raw 生成，AFLNet 可消费。

六、决策点清单

以下情形必须停下问用户，不得自行决定：

一类，契约问题。契约缺条款、语义不明、两种实现都合理。
二类，冻结文档修改。需要改任何 fused_* 契约文档或对应 JSON 配置。
三类，已冻结代码修改。需要改 core/fused/ 下已 Final Frozen 的模块语义。
四类，kb 写操作。需要写 kb/ 下任何文件。
五类，derived 写操作。需要写 derived/fused/ 下任何文件。正常 Pipeline 运行通过 Writer 写入不算写操作，此条针对绕过 Writer 的直接写。
六类，测试失败。pytest failed 或 errors 不为 0。
七类，fingerprint 变化。kb/ fingerprint 与基线不一致。
八类，前序越界。发现前序 Step 有未记录的越界或未决项。
九类，跨阶段决策。进入新阶段前的整体方案，需先给用户审定。

决策提出格式见 docs/工具/decisions_pending.md。

七、审计要求

每个 Step 结束必须写 audit 到 local/backup/step_<N>/audit.txt。audit 含四项：
改动文件清单。
越界检查。
未授权自动转换检查。
未落盘判断检查。

audit 不是汇报，不替代汇报。汇报面向用户，audit 面向审计。

每个阶段结束做一次独立 review，只读扫描本阶段全部 audit 文件，找越界模式与重复问题。review 指令由用户出，不自动做。

八、停工汇报触发条件

触发停工即停止当前动作，写决策请求到 docs/工具/decisions_pending.md，汇报用户，等回。

触发条件：
决策点清单任一条命中。
动作失败。
pytest failed 或 errors。
kb/ fingerprint 变化。
发现前序未决项。
不确定契约语义。
用户要求暂停。

停工不等于放弃。停工后 agent 保留全部已落盘动作，等用户回复继续。
