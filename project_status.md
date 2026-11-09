Current project resume/status authority:
`fused_hub/README.md`（中枢资产与契约的当前真源）
`docs/工具/project_handoff.md`（实验侧交接，2026-10-08）

This file is retained as:
milestone / historical status log.

---

# project_status.md

> 文档定位声明：本文件是项目恢复入口与状态索引，不是设计真源。Contract 真源以 `fused_hub/docs/` 下各文档为准。本文件不重复 Contract 规则细节，只记录"做到哪一步、资产在哪、下一步是什么"。若本文件与 `fused_hub/docs/` 下任何文档冲突，以文档为准。

生成时间：2026-09-29（**本文件自此未再更新；本轮已按 2026-10-30 实际现状刷新**）
最后刷新：2026-10-30
项目根目录：`E:\科研\想法idea\rag-chatafl`

---

## 第一章 当前项目目标

面向目标协议实现的协议模糊测试，通过多源知识加 RAG 加 LLM 生成高质量初始种子。

## 第二章 当前阶段

**v1 架构（Storage / Runtime / Pipeline Contract 三层）已于 2026-10-09 整体退役并从 `core/fused/` 移除**
（见 `core/fused/__init__.py` 模块 docstring）。

当前主线是 **v2 结构化知识中枢**：Layer 0 核心（`core/fused/` 顶层 22 个模块）+ Layer 2 五源抽取
（`norm.py` / `expert_note.py` / `vuln.py` / `source.py` / `traffic.py`）+ `downstream/` 11 个下游消费模块，
以及 RQ1 有效性 / RQ2 消融 / RQ3 种子聚焦 / RQ4 三协议对照四条实验线。

## 第三章 结构化知识中枢状态

- **v1 Storage / Runtime / Pipeline 三层**：2026-10-09 已退役，代码移除
- **v2 结构化知识中枢**：Layer 0 核心 + Layer 2 五源抽取 + `downstream/` 下游消费，已落地

## 第四章 设计资产索引

`fused_hub/docs/` 下实际 4 份文档（截至 2026-10-30）：

- `fused_knowledge_hub_design.md`
  - 版本：v2 设计（Layer 0 核心结构 + LLM 安全接口）
  - 状态：Draft（待用户审后冻结）
  - 职责：知识原子六元组、Subject / Aspect / Condition / Value(12 种) / Claim / Resolution / Alignment 定义，防矛盾机制 P9
- `fused_canonical_spec.md`
  - 版本：v2
  - 状态：Draft
  - 职责：canonical 序列化 10 条规范 + 确定性 ID 计算
- `fused_compatibility_mapping.md`
  - 版本：v1→v2
  - 状态：参考
  - 职责：v1 扁平 fact_key 到 v2 Subject/Aspect 的映射规则
- `rtsp_profile_v1_draft.md`
  - 版本：rtsp Profile v1
  - 状态：草案
  - 职责：Layer 1 Profile 首个实例（甲方案最小可用）

## 第五章 已落地代码资产索引

`core/fused/` 下共 **33** 个 Python 文件，全部状态 implemented。顶层 **22** 个、`downstream/` 子包 **11** 个。

顶层：

- `core/fused/__init__.py`：包导出面（仅 5 类异常，无 reader / writer 导出）
- `core/fused/exceptions.py`：异常树（FusedError / FusedSchemaError / FusedRegistryError / FusedValidationError / FusedIOError）
- `core/fused/models.py`：Layer 0 全部 frozen dataclass（**26** 个），含 12 种 ValueType
- `core/fused/canonical.py`：canonical 序列化唯一入口 + 三类确定性 ID（`compute_fact_id` / `compute_claim_id` / `compute_evidence_id`）
- `core/fused/registry.py`：3 个注册表的 strict 加载（subject_type / aspect / epistemic_type），未注册引用 fail-closed
- `core/fused/validation.py`：**7 级**校验（`validate_value` / `validate_subject` / `validate_aspect` / `validate_epistemic` / `validate_claim` / `validate_fact` / `validate_all`）
- `core/fused/export.py`：LLM 安全接口（P10）视图导出
- `core/fused/compat.py`：v1 fact → v2 Fact 双轨映射（`convert_v1_fact`）
- `core/fused/norm.py`：spec 源 ProtocolNorm → v2 Fact（5 种 kind：transition / field / outcome / method / constraint）
- `core/fused/expert_note.py`：expert_note 源 JSON → v2 Fact
- `core/fused/vuln.py`：vuln 源（`kb/历史漏洞/*.json`）→ v2 Fact
- `core/fused/source.py`：source 源 → v2 Fact（现走 AutoSeeder，不再经 norms.jsonl）
- `core/fused/traffic.py`：traffic 源（client.log / csv / **packets.ndjson 真实字段**）→ v2 Fact
- 其余抽取与探测辅助模块：`protocol_patterns.py`(DEPRECATED) / `rfc_extractor.py` / `traffic_extractor.py` /
  `source_autoseeder.py` / `source_fsm.py`(DEPRECATED) / `source_probe.py` / `source_retrieval.py` /
  `vuln_pattern.py` / `vuln_vector.py`

`core/fused/downstream/`（11 个）：

- `edge_cover.py`：① 结构覆盖层（贪心最小边覆盖，确定性）
- `generic_danger.py`：② 通用危险层（规则推导，不调 LLM）
- `boundary_probe.py`：③ 漏洞导向边界探针 + 协议无关定向字典（`generate_protocol_dict`）
- `rag_seedgen.py`：中枢 → RAG → LLM → 种子（`retrieve_subgraph` / `generate_seeds_react`）
- `selector.py`：三层语料库选择器编排 + 降级（`select_seeds` / `prioritize_seeds` / `vuln_proximity_score`）
- `strategy.py`：多导向自适应种子生成（漏洞导向 P0）
- `source_availability.py`：五源可用性与 `whitelist_methods` 降级链
- `source_retrieval.py`：源内容检索（7 条 query）
- `resolver.py`：claim 冲突消解（`resolve_claims`）
- `seed_manifest.py`：种子清单
- `target_env.py`：目标环境探测（可播会话白名单）

> ⚠️ 孤岛提示：`source_fsm.py` + `protocol_patterns.py` + `source.py` 三者均标 DEPRECATED 且生产链路无调用方，
> 仅 `tests/fused/test_source.py` 覆盖 `source.py`。

## 第六章 Schema 与 Registry 资产

canonical path 为 `fused_hub/schema/`（**无 `v1/` 子目录**），共 **3** 个 JSON（括号内为字节数）：

- `subject_type_registry.json`（1211 B）—— 7 个 subject type：method / header / state / status / relation / protocol / actor
- `aspect_registry.json`（5148 B）—— 19 个 aspect（rtsp Profile v1 7 项 + expert_note 扩展 12 项）
- `epistemic_type_registry.json`（965 B）—— 4 个 epistemic type：must(100) / normative_unspecified(80) / descriptive(50) / observed(20)

3 个 registry 的 `core_version` 字段统一为字符串 `"1.0"`（**无独立 `version` 字段**）。fingerprint 规则为 `sha256:` 加 64 位小写十六进制。

## 第七章 当前验证状态

最近一次全量回归（2026-10-30 实测，命令 `E:/app/Anaconda3/python.exe -m pytest tests/ -q`）：

- passed：**560**
- skipped：**0**
- failed：**0**
- errors：0
- 耗时：约 28.7 s

`kb/` 覆盖 8 个协议（dns / dtls / ftp / rtsp / sip / smtp / ssh / tls），每个协议下 5 个源目录
（spec / 协议实现源码 / 数据流量 / 历史漏洞 / expert_note）；`kb/sip/_bak_pjproject` 为源码备份目录，非五源之一。
`kb/` 全程只读。

`derived/fused/`：**存在**，为 v1 时代遗留的融合产物（131 facts / 81 entities / 34135 claims，
`fusion_version: fusion_v3+rules.sha256:43f7c7fe6`），fact_key 仍是 v1 扁平 `kind`/`property` 格式。
v2 产物在 `derived/per_source/<协议>/<源>/facts/<源>.jsonl`，覆盖 ftp / rtsp / sip / smtp 四协议 × 五源。

`derived/` 顶层现有目录：`analysis`、`fused`、`lane_a`、`per_source`、`rq3`、`rq4`、`seeds`、`source_a`、
`source_blocks`、`spec`、`vuln`、`vuln_pattern_vectors`（另有 `fused_status.txt` 与 `per_source.bak_20261018`）。

代码卫生：`core/fused/` 与 `tests/fused/` 共 **71** 个文件（33 + 38），`ruff --select F401,F811,F821,F841`
全部通过，fused 范围内无占位 skip 残留。

工程约定（继续推进时需遵守）：

- `kb/` 全程只读，改动前后做逐文件 diff 确认 UNCHANGED
- pytest 在沙箱内需加 `-p no:cacheprovider --basetemp=<项目外目录>`
- 失败即停，不自行绕过失败，改为汇报失败明细
- 本项目不是 git 仓库，回滚依赖 `derived/per_source.bak_20261018/` 与 `local/` 内的实验记录

## 第八章 已完成关键能力

- Models：26 个数据类与 12 种 ValueType 落地，构造期强制校验
- Canonical：canonical serialization 唯一入口落地，`_normalize` 递归过滤 None
- IDs：三类确定性 ID（f2_ / c2_ / e2_ 前缀）落地，同输入必得同 ID
- Validation：7 级 fail-closed 校验落地，未注册引用硬错误
- Registry：3 个注册表 strict 加载落地
- 五源抽取：spec / expert_note / traffic / vuln / source 各自产出 v2 六元组 Fact
- **traffic 真实字段管道**：`traffic_extractor.extract_packet_fields` 从 `packets.ndjson` 抽应用层真实字段
  （过滤 Wireshark 分解字段），真实值经 `assemble_bundle` 覆盖 LLM 模板值
- **source 确定性**：`_ngram_embed` 用 `zlib.crc32`（跨进程确定）+ LLM 结果按 code_blocks hash 缓存到
  `derived/source_blocks/<协议>.state.json`
- **source 语义锚点**：初始化注入 `canonical_flow` + `allowed_methods`，状态机从「响应码状态机」变为
  「语义化会话状态机」（Idle / Registered / Invited / Confirmed / InCall / Subscribed / Terminated …）
- **漏洞导向去门控**：vuln_boundary 层对所有协议可用（不再 `protocol != "rtsp"` 一刀切）
- 三层检索 + ReAct refine + `.raw` / `.dict` 落盘全链路跑通

## 第九章 v1 Pipeline 层状态

v1 Pipeline Contract 定义的 11 项能力（Candidate DTO / Normalization / Fact Matching / Claim Materialization /
Phase A / Phase B execution / Lineage / Graph / Profile derivation / Deterministic replay / Fusion runner）
随 v1 架构于 2026-10-09 整体退役，代码已从 `core/fused/` 移除。

v2 下的对应实现为：

- 候选与规范化：`core/fused/norm.py` / `expert_note.py` / `vuln.py` / `source.py` / `traffic.py`（源侧直出 v2 Fact，无 Candidate 中间层）
- 冲突消解：`core/fused/downstream/resolver.py`（`resolve_claims`）
- 溯源与清单：`core/fused/downstream/seed_manifest.py`；v1 遗留 lineage 见 `derived/fused/audit/lineage.jsonl`
- LLM 导出：`core/fused/export.py`

## 第十章 已知待办

- `models docstring` 标注滞后。`core/fused/models.py` 的模块 docstring 仍写「本模块与 core/fused/models.py (v1) 共存, 不删旧模块」，但 v1 已于 2026-10-09 退役，本文件现为唯一版本（26 个 dataclass）。属标注滞后，非实现缺陷。
- ~~`layout.py` Violation 数据类未统一~~ —— 属 v1 Runtime 层（已于 2026-10-09 退役），不再适用。
- ~~`graph_registry` relation_type 字段名差异~~ —— 属 v1 Registry 体系（`fused_hub/schema/v1/graph_registry.json` 已随 v1 移除），不再适用。
- **字典受控**：P4 引入真实字段后，sip 字典 token 从 35 涨到 163（含 Wireshark 分解字段已被下划线规则过滤，但噪音仍偏多）。后续应只保留 `required_headers` 声明字段的取值。
- **source 语义锚点的稳定性**：锚点已让状态机语义化，但初始化仍是一次 LLM 采样；可考虑多次采样取最优或引入 rfc 源状态机做交叉锚定。
- **非 RTSP 协议的会话级覆盖**：SIP/SMTP 的 `canonical_flow` 尚未像 RTSP 那样形成完整的跨消息状态链。

## 第十一章 当前主线

v2 结构化知识中枢的实验化与下游深化：

1. **RQ4 三协议对照实验**（Live555 / Kamailio / Exim × ProtoRAG vs 官方自带种子 × aflnet × 3h）
2. **RQ2 消融实验**（leave-one-out + 知识表示三路）
3. **协议扩展**：kb 下已有 8 协议，`fused_hub/targets/` 已建 4 个 Profile（ftp / rtsp / sip / smtp），可继续建 dns / dtls / ssh / tls 的 Profile

## 第十二章 暂缓事项

无。RFC 单源到 seedgen 已实跑通过，当前重心在 RQ2 / RQ3 / RQ4 实验线。

## 第十三章 恢复工作所需阅读顺序

1. `project_status.md`（本文件，先建立全局坐标）
   - 作用：只回答"做到哪、资产在哪、下一步是什么"，不回答"规则是什么"
2. `fused_hub/README.md`（中枢资产与契约的当前真源）
   - 作用：目录结构 / 资产分布 / 当前状态的权威索引
3. `docs/工具/project_handoff.md`（实验侧状态入口）
   - 作用：RQ1/RQ2/RQ3 实验状态与教训
4. `fused_hub/docs/fused_knowledge_hub_design.md`（v2 Layer 0 结构真源）
   - 作用：数据模型与设计原则依据
5. `fused_hub/docs/fused_canonical_spec.md`（canonical 序列化规范）
   - 作用：ID 计算与字节契约依据
6. `fused_hub/docs/fused_compatibility_mapping.md`（v1→v2 映射规则）
   - 作用：读懂 v1 遗留产物与双轨兼容的边界
7. `fused_hub/docs/rtsp_profile_v1_draft.md`（Layer 1 Profile 实例）
   - 作用：注册表实际内容与 profile 机制示例
8. `上下文交接_20261024.md`（实验侧交接）
   - 作用：RQ1/RQ2/RQ3 实验状态与教训

顺序理由：先读状态与索引建立坐标，再读设计真源，最后读 Profile 实例与实验交接。

恢复实操提示：改代码前确认 `kb/` 只读约束不被破坏（`core/paths.py` 的 `SOURCE_DIRS` 给出五源 → kb 子目录映射）；
全量回归用 `pytest tests/ -q`（沙箱内需加 `-p no:cacheprovider --basetemp=<项目外目录>`），基线为
**560 passed / 0 skipped / 0 failed**。

需要追溯历史测试输出时，查 `local/` 内的实验记录与 `derived/analysis/` 的分析产物；需要实时结论时直接重跑命令取当前值，不依赖历史输出。
