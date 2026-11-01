local/contracts/README.md

定位：契约索引。契约正文仍在 fused_hub/docs/ 下，本目录只做索引，不做副本。

一、契约清单

fused_hub/docs/fused_storage_design_v1.md
  版本：v0.13
  状态：Final Frozen
  职责：第一部分核心静态契约（数据模型、canonical serialization、确定性 ID、Invariant 体系、logical storage layout）

fused_hub/docs/fused_runtime_io_v1.md
  版本：v0.3.1
  状态：Final Frozen
  职责：第二部分 Runtime I/O Contract（path 常量与 resolver、目录创建、atomic 写入、Reader 与 Writer、JSONL record ordering、Runtime Registry Consistency、Registry Cache、Publication Addendum）

fused_hub/docs/fused_schema_v1.md
  版本：v0.2
  状态：Final Frozen
  职责：结构化知识中枢静态数据模型（Fact、Claim、Evidence、Alignment、Meta 等记录结构与字段语义）

fused_hub/docs/fused_registry_v1.md
  版本：v1
  状态：Final Frozen
  职责：Registry 清单与规范化、分类规则（subject、alias、property、authority、precedence、comparison 的真源定义）

fused_hub/docs/fused_policy_v1.md
  版本：v1
  状态：Final Frozen
  职责：融合算法策略（Phase A 与 Phase B 分离、处理流程、resolution 与 alignment 判定规则）

fused_hub/docs/fused_pipeline_v1.md
  版本：v0.4.7
  状态：Final Freeze Candidate（非 Final Frozen）
  职责：Pipeline Contract（ProtocolNorm 到 Candidate 的 Ingress Stage、Candidate 到 Fused Dataset 的 Fusion Core、Fusion 编排与发布、确定性重放）
  待办：依赖 Runtime Publication Addendum（已落盘于 v0.3.1 第二十二章）与 graph_registry.json 的 derived_field_mapping 段（已落盘，version 2）。两者齐备且 version 与 fingerprint snapshot 更新后方可改为 Final Frozen。

二、机器资产

fused_hub/schema/v1/ 下 10 个 JSON，是上述契约的 machine 可读形态：
  subject_registry.json、alias_registry.json、property_registry.json、
  authority_registry.json、claim_classification_rules.json、precedence_rules.json、
  comparison_policy.json、graph_registry.json、fact.schema.json、condition.schema.json

version 字段：graph_registry.json 为 2（Step 3.2b Gate B 落盘），其余 9 个为 1。
fingerprint 规则：sha256 加 64 位小写十六进制，由 RegistryLoader 从本次实际解析的 content 计算。

三、边界

契约正文以 fused_hub/docs/ 下各文档为准。本索引不复制正文，不做解释。
若本索引与契约正文冲突，以契约正文为准。
修改任何一份契约或 JSON 都属冻结文档变更，按 local/agent_rules.md 第五章必须停下汇报。
