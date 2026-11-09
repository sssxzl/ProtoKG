# docs/设计/vuln_source_closure_design.md — vuln 源收口 + 中枢分层原则 + claim_class 裁定

> Step 4.8g 收口 · 设计真源
> 契约依据：`fused_hub/docs/fused_pipeline_v1.md` (v0.4.7 Final Frozen)、`fused_hub/docs/fused_policy_v1.md`、`fused_hub/docs/fused_registry_v1.md`、`fused_hub/docs/fused_schema_v1.md`
> 上游：`docs/设计/vuln_rules_design.md`、`docs/设计/pipeline_rules_design.md`
> 状态：Final Frozen
> 本文件为 standalone 设计真源，不依赖任何 superseded draft。

---

## 0. 本步要解决什么

Step 4.8g 完成后停在 claim_class 决策点。经多轮只读核查、用户拍板、审定意见，本步收口：

1. 中枢分层原则（source extraction 层 vs Fused Hub 层）
2. claim_class 裁定：新增全局 semantic rule，descriptive → observational
3. needs_review 缺口修复（Registry-driven）
4. `explicit_structural_rule` fail-fast 修复
5. peer_conflict 作为期望状态的正式定义
6. vuln fact_key 原则（完整 canonical fact_key）
7. fusion_version 原则与 release timing
8. seedgen 增量预判与验证方式
9. Semantic Release Transaction Boundary
10. Release Baseline
11. 未决项登记

---

## 1. 中枢分层原则（冻结）

### 1.1 两个「单源」概念

**第一层：单源知识处理 / extractor 调试**
- 输入：一个知识源
- 处理：抽取 → 结构化 → 保留 provenance
- 产物：`ProtocolNorm` / extraction artifacts
- **不进入 Phase A / Phase B，此处不存在 resolution 概念**

**第二层：单源输入的 Fused Hub build**
- 输入：一个 source 或多个 source
- 处理：Candidate → Claim → Phase A → Phase B → Fact
- 产物：完整 Fused Dataset
- **无论输入几个 source，Phase A / Phase B 始终运行**

### 1.2 核心原则

> **Claim 是必须完整保留的知识事实陈述；Resolution 只是依据当前 Fusion Policy 派生出的规范化消费视图，不替代、不覆盖、不删除任何 Claim。**

英文：Claims are the preserved knowledge; Resolution is a derived canonical view, not a replacement for the claims.

### 1.3 知识模型

```
Fact A = {
    Claims: { a1 @ source_1, ..., an @ source_n },
    Resolution: canonical conclusion | unresolved,
    Alignments: relations between non-basis claims and the resolution
}
```

### 1.4 Phase A 不是「裁判」

- 1 source / 1 eligible claim → `resolution.method = single`
- 1 source / N claims → consensus / precedence / unresolved
- N sources / N claims → consensus / precedence / unresolved

**Pipeline 不关心「是不是已经叫多源」。** 单源内部多个冲突 Claim → 允许 `unresolved / peer_conflict`。

### 1.5 LLM 的位置

**不得在当前 build 中 live 调用 LLM 决定 Resolution。**

正确路径：

```
多源 Claims
  → deterministic Fusion Policy
resolved | unresolved / peer_conflict
  → 外部 RAG + LLM / Human Review
reviewed decision 被物化到 fingerprinted immutable input snapshot
  → 重新 Full Build
deterministically resolved
```

### 1.6 单源 extractor 不提前裁决

单源层只负责：我看到了什么 / 从哪里看到 / 怎么结构化 / 原始 Evidence 是什么。

---

## 2. claim_class 裁定

### 2.1 现状与问题

14 条 vuln Claim 的 `claim_class` 全部为 `unknown`，走具名 rule `cc.fallback.unknown`（`claim_classification_rules.json` rules 数组 index 7）。后果（契约明文规定，非 bug）：
- `fused_hub/docs/fused_policy_v1.md` 条款 11：unknown claim 不得进入 Phase A eligible set
- 5 个 Fact 停在 `unresolved(insufficient_evidence)`

### 2.2 裁定：新增全局 semantic rule，descriptive → observational

**核心理由**：
1. vuln 描述的是实现弱点 / 历史观察事实，不是协议规范要求
2. 在本项目当前 claim_class taxonomy 中，本设计裁定其语义为 observational
3. classification 不由 source_type 直接决定（`fused_hub/docs/fused_registry_v1.md` 条款 8 L164）
4. observational 在相关 property 的 eligible classes 中合法（18/18 实测）

**不采用 `security` 的理由（收敛表述）**：
- 本步不采用 security。原因不是「security 一定等于 normative」，而是当前 vuln Claim 描述的是实现弱点 / 历史观察事实，在本项目当前 claim_class taxonomy 中，本设计裁定其语义为 observational
- RFC §16 的 Security Considerations 如何分类，仍按现有 classification rules 决定。**本文件不重新定义 security claim_class 的全部语义**

### 2.3 规则语义：全局 semantic rule，不是 vuln-scoped rule

> 所有未被更高优先级规则命中的 `modality=descriptive` Claim，分类为 observational。该规则是 semantic 且 source-independent。

**设计意图**：descriptive assertion 表示「这是描述性陈述，不是规范性要求」，observational 在 claim_class 枚举里的语义就是「观察性」，两者对齐。

**rule 定义**：

```json
{
  "rule_id": "cc.modality.descriptive.observational",
  "priority": 2,
  "match": {
    "content_or_assertion_semantic_rule": {
      "modality": ["descriptive"]
    }
  },
  "class_hint": "observational",
  "notes": "Classifies otherwise-unmatched descriptive assertions as observational. Semantic and source-independent. Placed below file/section hints so more specific rules take precedence."
}
```

### 2.4 priority / effective order（Pre + Follow-up 填实）

**effective_sort_key** = `(family_rank, priority, rule_id)` 升序。

- first-match-wins
- 数组顺序不参与求值

**新 rule**：
- `rule_id`：`cc.modality.descriptive.observational`
- `family`：`content_or_assertion_semantic_rule`
- `family_rank`：3
- `priority`：2
- 当前 effective position：
  - overall：#8/9
  - family：#5/5

**Follow-up 验证（priority 1 / 2 等价）**：

| 维度 | priority=1 | priority=2 |
|---|---|---|
| changed claims | 14 | 14 |
| changed set symmetric diff | — | 0 |
| matched_rule diff | — | 0 |
| non-changed claim diff | — | 0 |
| resolution distribution | 62 resolved / 3 peer | 相同 |

**priority=2 的设计意义**（非当前数据正确性必要条件）：

本 rule 语义为 `otherwise-unmatched descriptive → observational`，因此在同 family 中将其**显式放在现有更具体 semantic rules 之后**，使其承担 **generic semantic default** 角色。这样未来若出现 match payload 与本 rule 相交的更具体 semantic rule，semantic precedence **不依赖 rule_id lexical ordering**。

**contract 表述**：
- 不同 family：`family_rank` 决定 precedence
- 同 family：`priority` 决定 precedence
- priority 相同：`rule_id` lexical ascending 仅作 deterministic tie-breaker
- 不得依赖 rule_id 命名表达本 rule 的 generic-default 语义

**当前位置观察的定位**：`overall #8/9` / `family #5/5` 是当前 Registry snapshot 的观察结果，非永久 Contract。冻结的是「本 rule 作为同 family generic default，不得被 rule_id lexical order 意外提升到更具体 semantic rules 之前」。未来新增 rule 时须重新验证 effective precedence。

### 2.5 全局 delta 验证（冻结条件）

**Pre 核查结果**：
- BEFORE：`{interpretive 43, normative 11, security 7, unknown 14}`
- AFTER：`{interpretive 43, normative 11, observational 14, security 7}`
- changed claims：**exactly 14**，全为 `source_type=vuln + modality=descriptive`，`cc.fallback.unknown → cc.modality.descriptive.observational`

**其余 61 条未被捕获的原因**：expert_note 有 43 条 descriptive，与候选 rule 完全重叠，但被 rank=1 的 `file_or_path_hint` 抢先命中，first-match-wins 使其走不到 rank=3。

**脆弱性登记**（U18）：该隔离依赖 document 字符串前缀（`kb/expert_note/`）。4.8g 已实测 vuln 的 document 不带 kb/ 前缀——一旦 expert_note 的解析失效，会一次多吃 43 条。**见 §9.3 回归断言**。

### 2.6 改动面

**需改**：
- `fused_hub/schema/v1/claim_classification_rules.json`：追加 1 条 rule
- `fusion_version`：见 §7

**不需改**：
- `property_registry.json`：observational 已在全部 18 个 eligible 里
- `condition.schema.json`
- `fused_hub/docs/fused_policy_v1.md`：不承载 class 语义
- `core/` 代码（除 §3 的 needs_review 接线）
- `fused_hub/docs/fused_registry_v1.md`

### 2.7 预期效果

| 项 | 现状 | 裁定后 |
|---|---|---|
| Facts | 65 | 65 |
| resolution | 59 resolved / 5 insufficient / 1 peer | 62 resolved / 3 peer |
| vuln claim_class | 14 unknown | 14 observational |
| sec_flagged_headers | 4 项 | 6 项（raw，见 §8） |
| sec_flagged_methods | {SETUP} | {SETUP}（不变） |

新增 2 个 peer_conflict 与 claim_class 取值无关，是 vuln 源内部的（§5）。

---

## 3. needs_review 缺口修复（Registry-driven）

### 3.1 契约要求（8 处，跨 5 文件）

| 文件 | 行 | 原文 |
|---|---|---|
| `fused_hub/docs/fused_pipeline_v1.md` | L482 | needs_review 不新增 Lineage outcome |
| `fused_hub/docs/fused_policy_v1.md` | L218 | Unknown claim 在 Phase B 中 relation 为 not_comparable，reason 为 unknown_claim_class，flags 加 needs_review |
| `fused_hub/docs/fused_policy_v1.md` | L228 | （"仍然必须保存"清单末项）- needs_review |
| `fused_hub/docs/fused_registry_v1.md` | L177 | 无法可靠分类时：claim_class 为 unknown，flags 加 needs_review。不得猜测 |
| `fused_hub/docs/fused_registry_v1.md` | L293 | unknown 映射到 needs_review，不进入 Phase A |
| `fused_hub/schema/v1/claim_classification_rules.json` | L4 | Unreliable classification defaults to unknown + needs_review |
| `fused_hub/schema/v1/claim_classification_rules.json` | L93-94 | `"fallback_flags": ["needs_review"]` / Caller MUST set flags=['needs_review'] |
| `fused_hub/schema/v1/comparison_policy.json` | L39-40 | resolution_competition: needs_review, action: flag for needs_review; do NOT enter Phase A |

### 3.2 现状

`core/fused/pipeline/evidence_claim.py:436` 硬编码 `Claim(..., flags=[])`。全 `core/` grep `fallback_flags` / `needs_review` → 0 命中。

### 3.3 修复方案：fallback-path only

**裁定：`fallback_flags` 仅在 fallback classification path 生效。** 普通 rule 暂不支持 flags declaration。

**理由**：
- 字段名 `fallback_flags` 而非 `flags`，命名已表达 scope
- Pre 已确认：CASE 1（普通 rule flags 来源）不存在；CASE 3（未来普通 rule 加 flags）当前静默忽略
- needs_review 本就是 fallback-unknown 的状态

**真实 Registry structure（Pre 已确认）**：

`fused_hub/schema/v1/claim_classification_rules.json` 中，`cc.fallback.unknown` 是**具名 Registry rule**（rules 数组 index 7 / 共 8 条）。`fallback_flags = ["needs_review"]` 挂在该 rule 上。全文 fallback 相关键只有两处，均挂在 rules[7]：`"fallback": true`（match）与 `"fallback_flags": ["needs_review"]`。Registry 顶层无 fallback 字段。

**Contract（写死，无 conditional 分支）**：

```
Claim classification materialization:

classify_claim(...)
  ↓
返回四元组：
  (
    class_hint,
    Classification,
    rule_id,
    classification_flags
  )
  ↓
其中：
  正常 rule 命中：
    classification_flags = ()
  fallback path（真实 rule_id = "cc.fallback.unknown"）：
    classification_flags = canonicalize(fallback_flags)
    class_hint = unknown
  ↓
调用方直接：
  Claim.flags = classification_flags
```

**核心 invariant**：

> `classification_flags` 必须完全由 Registry 配置导出。不得根据 `claim_class == "unknown"` / `source_type` / `document` / 其他 Python hard-code 额外推导 `needs_review`。

**fallback rule_id provenance**：真实 Registry 存在具名 `cc.fallback.unknown`，因此 fallback classification 的 `rule_id` 必须返回该真实 rule_id（不再置空）。需修复 `evidence_claim.py:295-298` 当前把 rule_id 置空为 `""` 的行为。

**本步不支持普通 rule flags**：正式冻结——claim_classification_v1 普通 classification rule 不支持 flags declaration；fallback path 支持 `fallback_flags`。未来如需普通 rule flags，属 classification registry schema expansion，另立项并按 fusion_version 规则升级。

### 3.3.1 Exact Registry flag materialization path（Pre 填实）

数据流：
- registry JSON 的 `fallback_flags` 存在于内存，且是活对象
- `classify_claim` 拿得到
- `core/fused/pipeline/evidence_claim.py:288` return 三元组无 flags 槽位，`fallback_flags` 在此止步
- `core/fused/pipeline/evidence_claim.py:295-298` 兜底分支 rule_id 置空为 `""`，与 Registry 侧具名 `cc.fallback.unknown` 不一致
- `core/fused/pipeline/evidence_claim.py:430` `_class_rule` 前缀下划线 = 显式丢弃
- `core/fused/pipeline/evidence_claim.py:436` `Claim(..., flags=[])` 硬编码是唯一缺口

**修复位置**：`core/fused/pipeline/evidence_claim.py` 单文件。

**CASE 结果**：
- CASE 1：普通 rule flags 来源 → 不存在（概念尚未存在）
- CASE 2：needs_review 来源 → registry L93 + L94 notes，挂在具名 rule `cc.fallback.unknown` 上
- CASE 3：未来普通 rule 加 flags → 不支持，静默忽略

**约束**：`tests/fused/pipeline/test_audit_lineage.py:334-336` 断言 `needs_review` 不在 `REASON_CODE_OUTCOME` 与 `LINEAGE_OUTCOME_DOMAIN`（`fused_hub/docs/fused_pipeline_v1.md` §7.11 L482）。不得违反。

### 3.4 验证（修正验证矛盾）

**CASE A：独立 synthetic fallback-unknown fixture**
- 构造一个不命中任何 classification rule 的 Claim
- 预期：`claim_class = unknown`，`Claim.flags = ["needs_review"]`

**CASE B：真实 vuln build**
- 加入 observational rule 后：14 vuln Claim → `claim_class = observational`
- 预期：`Claim.flags` 不含 `needs_review`

**Step 4.8h 最终验收**：
1. synthetic fallback unknown Claim → `needs_review` PASS
2. 14 vuln Claim → observational 14
3. vuln Claim 中 `needs_review` → 0
4. 5 个 Fact → 3 resolved + 2 peer_conflict

**禁止**：要求「14 vuln claim flags 带 needs_review」。

---

## 4. `explicit_structural_rule` fail-fast 修复

### 4.1 问题

`_eval_match` 中该 family 实现为 `bool(match["explicit_structural_rule"])`，链位第 1（rank=0），任何非空值恒命中，静默压过后续所有规则。实测吞掉 75/75。当前 0 用户。

**根因**：`_eval_match` 签名只有 `source_types / modality / document`，无任何通道传入结构化字段。该 family 在当前输入下无法正确实现。

### 4.2 修复方案

**双保险，fail-fast + fail-closed。**

**甲、Registry 加载期 fail-fast**：
- 在 `RegistryLoader.load_claim_classification_rules()` 中加语义校验
- **只要 `match` 出现 `explicit_structural_rule` key，就失败**（判断条件只有「key 是否存在」，不看 truthiness）
- 以下全部必须失败：
  ```
  "explicit_structural_rule": "anything"
  "explicit_structural_rule": {}
  "explicit_structural_rule": ""
  "explicit_structural_rule": null
  ```

**乙、evaluator 防御性 fail-closed**：
- `_eval_match` 若收到该 family，必须 raise
- 禁止 `return True` / `return False` / ignore / fallback

**丙、当前不实现 `StructuredMatchContext`**：不新增入参，不扩展 DTO。未来通过 classification contract/version upgrade 正式启用。

### 4.3 固定 error contract

- exception class：`FusedRegistryError`（5 类异常中承载 artifact 加载失败）
- error code：`registry_unsupported_match_family`（沿用 `registry_*` 4 个先例）

### 4.4 测试对象

- **核心 invariant**：当前 `fused_hub/schema/v1/claim_classification_rules.json` 不得实际使用 `explicit_structural_rule`
- **不给 `comparison_policy.json` 加此测试**——它不承载 match family 语义

### 4.5 验证

- 加载期：构造含该 family 的临时 registry → 断言加载失败
- 运行期：直接调 `_eval_match` 传含该 family 的 rule → 断言 raise
- 其他四种 match family 行为完全不变
- 全量测试零回归

---

## 5. peer_conflict 作为期望状态

### 5.1 定义

`fused_hub/docs/fused_policy_v1.md` 契约 §5.2 第 6 步规定的合法状态。不是 bug，不是数据错误。表达「有多条都说得通、但值不同的 claim」。

### 5.2 处理

- **保留全部 claim**，不写回、不删除、不覆盖
- `resolution.status = unresolved`，`resolution.reason = peer_conflict`
- 与既有 D13 先例一致：两条无法裁决的安全陈述同时成立时，接受 peer_conflict 为合法结果，不得为规避冲突而编造 condition 编码（D13 已在 `docs/工具/decisions_resolved.md` 中拍板）
- seedgen 桥接只收 resolved，peer_conflict 的 Fact 进不来——正确保守行为

### 5.3 LLM 裁决通道（占位，本步不实现）

按 §1.5，LLM 裁决位于 deterministic Fusion Core 外。通道设计留 pipeline 全通后立项。

### 5.4 可复核性

**不做 `Fact.flags += peer_conflict`。**

**理由**：
- `resolution.reason = peer_conflict` 已是 canonical semantic truth
- `audit/conflicts.jsonl` 是正式审计记录
- 再加 `Fact.flags = ["peer_conflict"]` 会形成第三个状态副本，与「避免第二真源」原则相悖

**检索约定**：
- 状态查询：`Fact.resolution.reason == "peer_conflict"`
- 审计查询：`audit/conflicts.jsonl`
- 汇总查询：`profile.resolution_stats`
- 若未来 RAG 查询性能需要额外索引：做派生索引 / query index，**不要把同一 semantic state 复制进 Fact.flags**

---

## 6. vuln fact_key 原则

> vuln 与其他 source 使用完全相同的 canonical fact_key identity contract。source_id / source_type 永远不进入协议语义身份。是否汇合由完整 canonical fact_key 决定，其中 subject / property / condition 是本次 vuln 讨论中特别关键的区分维度。

完整 identity 包含：`protocol`、`version`、`kind`、`actor`、`subject`、`property`、`condition`。

### 6.1 对照 4.8g 实测

- `method.SETUP × security_condition`：vuln 用 `security_condition` property；RFC 用 modality 类。**不是同一 property，不竞争**
- 5 个 vuln claim 在 `method.SETUP × security_condition` 下的 peer_conflict 是 **vuln 源内部**的冲突

### 6.2 推论

**不需要为 vuln 单开独立数据流。** fact_key 本身的区分已实现「不同角度的知识不互相污染」。

---

## 7. fusion_version 原则与 release timing

### 7.1 原则

Pipeline Contract 中 `fusion_version` 绑定 Claim Classification semantics 与相关 rule contents/order。

> **classification semantics changed → fusion_version must change。**
>
> **同一个 fusion_version 必须唯一对应一套 immutable deterministic semantics。**

### 7.2 release timing

- **Step 4.8h**：落 rule + 实现 materialization + tests + dry-run + temp 验证。**不 bump fusion_version。不以新 classification semantics 覆盖正式 canonical `derived/fused/`。**
- **Step 4.8i**：fail-fast 实现 + tests。**不 bump。**
- **Classification Semantic Release Finalization**（4.8i 之后）：确认两步全部 PASS → **一次性 bump fusion_version** → 更新真实 Registry fingerprint snapshot → 执行 Full Fused Build → seedgen regression → 最终 verification
- **从此新 fusion_version 唯一对应 4.8h + 4.8i 完成后的语义。**

### 7.3 fusion_version（Pre + Follow-up 填实）

- current value：`"fusion_v1"`
- next value for this semantic release：`"fusion_v2"`
- type：`str`（opaque string version identifier）
- convention：`fusion_v<n>`
- 定义位置：`core/fused/pipeline/dto.py:144`（+L148 校验）
- 默认值：`core/fused/pipeline/build_inputs.py:251`
- Meta model：`core/fused/models.py:1320`
- 读取位置：`core/fused/pipeline/finalization.py:142` / `core/fused/pipeline/pipeline.py:213` / `core/fused/validation.py:849`
- 落盘路径：`Meta.fusion_version`
- Writer：`core/fused/runtime/writer_impl.py:146-159`，最终通过 `canonicalize_bytes(meta.to_dict())` 写入 Meta
- 无 x.y.z / semver 先例

**§11.3 义务**：Claim Classification semantics 属于 fusion_version 管辖范围。本轮 4.8h + 4.8i 属于同一个未发布 Classification Semantic Release Transaction，中间 workspace state 不构成独立 released semantics。4.8h 不 bump，4.8i 不 bump，Finalization 一次性 `fusion_v1 → fusion_v2`。

**§11.3 的规范性解释**（依据 `fused_hub/docs/fused_pipeline_v1.md` L860–L895）：

> §11.3 的 version-bump obligation 适用于 committed / released semantic state。Step 4.8h 与 Step 4.8i 在 Classification Semantic Release = COMMITTED 之前属于同一 pre-release transaction，因此二者的中间 workspace states 不构成独立 fusion_version。本轮 fusion_version obligation 在 Classification Semantic Release Finalization 中一次性履行。

### 7.4 Classification Semantic Release Transaction Boundary

Step 4.8h、Step 4.8i 与 Classification Semantic Release Finalization 共同属于同一个 semantic release transaction。

在 `Classification Semantic Release = COMMITTED` 之前，本轮 semantic release 始终属于未发布状态。

**具体规则**：

1. Step 4.8h / Step 4.8i 的修改均属于 pre-release workspace changes。
2. 不得将任何中间状态声明为新的 released classification semantics。
3. Step 4.8h / Step 4.8i 阶段不得使用中间 semantics 覆盖正式 canonical `derived/fused/`。
4. 不得将旧 fusion_version 与已经变化的 classification semantics 作为合法 released state 使用。
5. 不得在仅完成 Step 4.8h、尚未完成 Step 4.8i 时，将该状态 merge / release 为正式 semantic release。
6. 只有 Step 4.8h PASS + Step 4.8i PASS 后，才允许进入 Classification Semantic Release Finalization。
7. Step 4.8h、Step 4.8i 或 Classification Semantic Release Finalization 在 COMMITTED 前任一步失败：
   - semantic release abort
   - 不得将当前 workspace 状态声明为 released state
   - 若 fusion_version 尚未 bump：保持旧 fusion_version
   - 若 Finalization 已经临时 bump fusion_version：该状态仍属于 unreleased workspace state，不得作为正式 release 使用
   - 若尚未执行 canonical Full Fused Build：不得执行该 build
   - 若 canonical Full Fused Build 已经开始或完成，但后续 verification / regression 失败：当前 `derived/fused/` 属于 failed-release workspace output，不得视为合法 released Fused Dataset
   - 不得记录 `Classification Semantic Release = COMMITTED`
   - 不得更新正式 release status / project status 为本轮新 semantic release
   - 根据 release-start baseline 明确判断当前 workspace 是否发生变化，并按执行计划选择：A. 恢复到 release-start baseline；或 B. 保持为明确的 uncommitted / unreleased workspace state
8. 只有 Finalization 的全部步骤 PASS 后，才允许写 `Classification Semantic Release = COMMITTED`。
9. COMMITTED 是本轮 semantic release 唯一的正式发布边界。

---

## 8. seedgen 增量预判

### 8.1 桥接逻辑

`core/fused/downstream/seedgen_bridge.py` 过滤：`_resolved_true` 且 `property == security_condition` 且 `kind ∈ {method, header}`。

### 8.2 裁定后预期

被收入 2 条：`authorization × security_condition`、`transport × security_condition`。

### 8.3 预期变化（raw regression metric）

| 项 | 现状 | 裁定后 |
|---|---|---|
| `sec_flagged_methods` | `{SETUP}` | `{SETUP}`（不变） |
| `sec_flagged_headers` | 4 项 | 4 项 + authorization + transport = 6 项（raw） |

### 8.4 表述约束

**`sec_flagged_headers: 4 → 6` 只作为 raw regression expectation，不能解释为语义上新增两个不同 security headers。**

至少 `Authorization` / `authorization` 存在 canonicalization / alias 问题（U1）。

**验证文案**：Raw seedgen bridge output: 4 → 6。其中 Authorization / authorization 属已登记 U1 normalization issue。本步只验证 vuln 信息已成功进入 bridge，不把 raw count=6 当最终 semantic unique-header count。

---

## 9. Step 拆分

### 9.1 Step 4.8h-Pre：只读核查（已完成）

**已完成**。Pre + Follow-up 结果已填实 §2.4、§3.3、§3.3.1、§4.3、§7.3。

### 9.2 Step 4.8h-U17-Pre：Determinism Probe（已完成）

**已完成，判定 GO**。U17 撤销，见 §10。

### 9.3 Step 4.8h：Claim Classification + needs_review（不 bump）

1. 落盘新 observational rule
2. 实现 needs_review Registry-driven materialization
3. 增加 synthetic fallback-unknown test
4. 增加 expert_note 回归断言（见下）
5. 运行 classification delta dry-run（全局）
6. 运行相关 unit / E2E tests
7. 允许使用 temp output 验证：14 vuln unknown → 14 observational、3 resolved + 2 peer_conflict
8. 记录 prospective registry fingerprint
9. **不得 bump fusion_version**
10. **不得以新 classification semantics 覆盖正式 canonical `derived/fused/`**

**expert_note 回归断言（防退化）**：

不得只断言「count = 43」。必须断言：
- 当前所有 expert_note descriptive Claims 仍由预期的 `file_or_path_hint` rule 命中
- matched_rule identity ≠ `cc.modality.descriptive.observational`

失败含义：若 document path normalization 变化导致这些 Claim 不再命中 file/path hint，测试必须失败。这不是 global descriptive rule 出 bug，而是 classification-specific override 失去作用。届时须重新核查 document normalization 或 classification rule guard。

### 9.4 Step 4.8i：`explicit_structural_rule` fail-fast（不 bump）

1. RegistryLoader semantic validation：只要 match 出现 `explicit_structural_rule` key → `registry_unsupported_match_family`
2. `_eval_match` defense-in-depth：收到该 family → raise
3. 禁止 return True / return False / ignore / fallback
4. 测试：non-empty string / `{}` / `""` / `null` 全部 fail-fast
5. 其他四种 match family 行为完全不变
6. **不得 bump fusion_version**

### 9.5 Classification Semantic Release Finalization（4.8i 之后）

**进入条件**：Step 4.8h PASS + Step 4.8i PASS。

**执行顺序**：
1. 确认 Step 4.8h PASS
2. 确认 Step 4.8i PASS
3. 确认所有 classification semantic tests PASS
4. 确认当前 workspace semantic changes 与本轮 release scope 一致，不包含未授权 semantic change
5. 一次性 bump fusion_version（`fusion_v1 → fusion_v2`）
6. 计算 / 更新最终 Registry fingerprint snapshot
7. 执行 Full Fused Build
8. 执行 derived/fused verification
9. 执行 seedgen regression
10. 执行全量 regression
11. 记录：old / new fusion_version、old / new registry fingerprint、classification delta、4.8h result、4.8i result、Full Fused Build verification result、seedgen regression result、full regression result、release verification result
12. 只有步骤 1–11 全部 PASS 后，写 `Classification Semantic Release = COMMITTED`
13. COMMITTED 后，新 fusion_version 才成为正式 released semantic version

**边界**：fusion_version bump 必须发生在所有 semantic code / config changes 完成以后，但发生在任何正式 canonical Fused Dataset 以新 semantics 发布之前。若步骤 5 以后、步骤 12 以前任一步失败：按 §7.4 处理。不得将该状态视为 committed release。

### 9.6 Classification Semantic Release Baseline

Step 4.8h 开始前，记录 Classification Semantic Release 的 release-start baseline。

**报告落**：`local/backup/step_4.8h/`

**至少记录**：
- `fused_hub/schema/v1/claim_classification_rules.json` path + fingerprint
- `core/fused/pipeline/evidence_claim.py` path + fingerprint
- `core/fused/registry_loader.py` path + fingerprint
- 本轮计划修改的相关 tests path + fingerprint
- fusion_version 当前值
- fusion_version 实际承载位置
- 当前 Registry fingerprint
- Registry fingerprint snapshot 实际承载位置
- current derived/fused aggregate fingerprint
- 当前 classification rule effective state 所需的其他既有 release metadata

**Baseline 性质**：
- Step 4.8h / Step 4.8i / Finalization 的执行审计数据
- 非新增 Hub metadata
- 不进入 Fused Dataset
- 不改变任何 fact / claim / evidence identity

**用途**：
1. 明确记录本轮 semantic release 开始前的 released repository state
2. 在任一步失败时，判断本轮 workspace 相对 baseline 发生了哪些变化
3. 支持验证是否已经恢复到 release-start baseline
4. 若选择保留 failed-release workspace，明确证明该 workspace 与正式 release baseline 不同，因而不得误认为 released state

**注意**：fingerprint 本身只能用于验证 / 比较 baseline。如果执行计划要求自动恢复某个文件或 artifact，必须另有可恢复内容或既有版本控制 / backup 机制。**不得把「记录 fingerprint」解释为「已经具备内容恢复能力」。**

### 9.7 顺序

```
Step 4.8h-Pre（已完成）
  → Step 4.8h-U17-Pre（已完成）
    → Step 4.8h
      → Step 4.8i
        → Classification Semantic Release Finalization
```

各步独立汇报。任一步失败即停止向后执行。Step 4.8h 之后发生的失败，还必须执行 §7.4 规定的 release-abort 处理。「失败即停」不等于允许 repository 停留在一个被误认为正式 release 的中间状态。

---

## 10. 未决与登记

| # | 项 | 性质 | 处理时机 |
|---|---|---|---|
| U1 | subject 拼写不一致（Authorization vs authorization） | 既有缺陷 | 需授权跨源改 CR-5 或在 fact identity 层全局归一 |
| U2 | `vuln` 物理文件在 `kb/历史漏洞/` 而 `norm.source` 写 `vuln/` | 既有缺陷 | 修则违反源隔离，需授权 |
| U3 | ontology gap 8 值 | 治理缺口 | 需改冻结 JSON |
| U4 | `risk_level` 受控 token 集合硬编码 | 治理缺口 | 应升格进 registry |
| U5 | `EMIT_MANY` 未真正扇出 | 框架级缺口 | 将来有规则要真扇出时单独一步做 fan-out |
| U6 | `build_fingerprint` 是输入侧指纹 | 口径澄清 | 已写入 fused_status.txt |
| U7 | `derived/fused/status.txt` 与契约 §3.2 冲突 | 契约一致性 | 需授权 |
| U8 | `tests/` 下 10 项既有 ruff | 代码卫生 | 未授权未动 |
| U9 | `tests/conftest.py` 顶部 docstring 过时 | 文档过时 | 未授权未动 |
| U10 | 4.8f 记录的 2 个 order-dependent 串行失败未复现 | 观察 | 无复现路径 |
| U11 | `step_4.8g.5/audit.txt` 3 处转录错误 | 报告誊错 | 未修改 |
| U12 | `%TEMP%\a7sim2_0c99acrq` 残留 13 文件 | 环境 | 仓库之外 |
| U13 | peer_conflict 可复核性：profile.json 无 fact_id 列表、alignment_stats 不可见 | 增强 | 记 backlog |
| U14 | LLM 裁决通道 | 新立项 | pipeline 全通后 |
| U15 | `cc.traffic.observational` 与条款 8 抵触 | 契约一致性 | 未来治理 |
| U16 | Markdown artifact 清理 | 文档卫生 | 本文档正式冻结时处理 |
| U17 | `tests/fixtures/derived/graph/entities.jsonl` 非确定性 | ❌ **撤销** | entities.jsonl 从未改变；该判断源于 Pre 阶段错误外推 |
| U18 | 候选 rule 隔离依赖 expert_note document 前缀 | 脆弱性 | Step 4.8h 加回归断言（§9.3） |
| U19 | fallback_flags 为 fallback-path only | ✅ **已裁定** | Step 4.8h 实现并测试（§3.3） |
| U20 | legacy writer append 模式确定性依赖 overwrite=True | 潜在风险 | 当前四条 seedgen 路径均 True，未触发；若未来出现 overwrite=False 路径会追加重复 entity |

### 10.1 U17 撤销的 Errata

**CORRECTION**

此前关于 `tests/fixtures/derived/graph/entities.jsonl` 存在非确定性变化的表述不成立。

U17 Probe 已验证：
- 三份 entities.jsonl snapshot SHA-256 完全一致
- 四种测试执行模式均稳定
- entities.jsonl 实际从未发生变化

原判断来源：Pre 阶段把其他 timestamp-bearing fixture files 的变化错误外推到 entities.jsonl。

该结论现正式撤销。后续不得继续引用「entities.jsonl nondeterminism」作为项目事实。

原则：错误结论要撤销，但错误曾经发生过这一审计事实要保留。

### 10.2 U20 触发条件

出现新的 `overwrite=False` production / seedgen / fixture build path 时，再评估：
- append semantics
- duplicate entity behavior
- deterministic replay impact

当前不因 U20 修改 legacy writer / Fused Writer / Storage Contract / 阻塞 Step 4.8h。

---

## 11. 验证检查点

Finalization 后需验证：

**检查点 1：Repository Semantic Cleanliness Gate**

`kb/`、`derived/spec/`、`fused_hub/`、`core/`、正式 tests source files、Registry、Schema 不存在非预期 diff。

**检查点 2：Generated Fixture Output Gate**

`tests/fixtures/derived/` 不是整体豁免目录。当前 pytest 确认会变化的只有 3 类文件，每类各两份：

| 文件 | volatile field |
|---|---|
| `graph/meta.json` | `updated_at` |
| `norms/norms.jsonl` | `added_at` |
| `protocol_profile.json` | `last_updated` |

另 6 个 fixture output（entities / relations / state_machine 各两份）在 U17 Probe 中确认保持稳定。

**验证规则**：
- 对上述 3 类 volatile-bearing files：仅归一化已登记 volatile fields，再比较其余内容。**不得忽略整个文件。**
- 对其余 6 个文件：按普通 cleanliness / byte or canonical-content contract 执行验证
- 任何未登记字段发生变化：不得自动归类为 pytest noise。必须作为 unexpected fixture delta 单独调查

**检查点 3：其他基线**

1. 全量 `pytest -n auto`：基线 2589 passed / 8 skipped / 0 failed，0 回归
2. `kb/`：6061 files，SHA256 `A86C71E0…DEDE24` UNCHANGED
3. `derived/spec/rtsp/`：6 文件 size+mtime_ticks+sha256 NO DIFF
4. `derived/per_source/rfc/` 与 `derived/per_source/expert_note/`：各 13 文件 size+sha256 全等（跨源隔离）
5. `derived/fused/`：13 文件重跑后与预期一致
6. `verify_layout(.)` = 0 violation
7. `ruff core/fused/ + tests/fused/` 全清
8. registry fingerprint 新旧对比记录
9. fusion_version 新旧对比记录
10. seedgen 复测：`sec_flagged_headers` raw 4 → 6，`sec_flagged_methods` 不变
11. classification delta dry-run 报告：全局，不只是 vuln

---

## 12. 与既有冻结文档的关系

- `fused_hub/docs/fused_policy_v1.md`：不动
- `fused_hub/docs/fused_registry_v1.md`：不动
- `fused_hub/docs/fused_schema_v1.md`：不动
- `fused_hub/docs/fused_pipeline_v1.md`：不动
- `fused_hub/docs/fused_storage_design_v1.md` / `fused_hub/docs/fused_runtime_io_v1.md`：不动
- `fused_hub/schema/v1/claim_classification_rules.json`：追加 1 条 rule（`cc.modality.descriptive.observational`）
- `core/fused/pipeline/evidence_claim.py`：2 处改动（needs_review materialization + `_eval_match` fail-closed）
- `core/fused/registry_loader.py`：1 处改动（加载期语义校验）
- `fusion_version`：Finalization 时 bump `fusion_v1 → fusion_v2`（见 §7）
- `tests/fused/pipeline/rules/test_vuln_rules.py`：断言更新（预期变更）

---

## 13. 冻结前必办清单

| # | 项 | 状态 |
|---|---|---|
| 1 | descriptive → observational 是 global semantic rule | ✅ 已定（§2.3） |
| 2 | 冻结 rule_id / priority / effective order | ✅ 已定（§2.4） |
| 3 | needs_review 从 Registry materialize（Contract 形式） | ✅ 已定（§3.3、§3.3.1） |
| 4 | Step 4.8h 验证矛盾已修 | ✅ 已定（§3.4） |
| 5 | classification semantics 纳入 fusion_version | ✅ 已定（§7.1） |
| 6 | fusion_version release timing 已修 | ✅ 已定（§7.2） |
| 7 | explicit_structural_rule error semantics | ✅ 已定（§4.3） |
| 8 | 取消 Fact.flags peer_conflict | ✅ 已定（§5.4、§9） |
| 9 | fact_key 改成完整 canonical fact_key | ✅ 已定（§6） |
| 10 | 删除「security 压过 RFC MUST」理由 | ✅ 已定（§2.2） |
| 11 | seedgen 4→6 只作 raw regression | ✅ 已定（§8.4） |
| 12 | security class 定义收敛 | ✅ 已定（§2.2） |
| 13 | 设计稿 standalone（不引用初稿） | ✅ 已定（全文） |
| 14 | Pre 核查「只读」定义修 | ✅ 已定（已执行） |
| 15 | priority 跨 family 表述修 | ✅ 已定（§2.4） |
| 16 | Semantic Release Transaction Boundary | ✅ 已定（§7.4） |
| 17 | Release Baseline 记录 | ✅ 已定（§9.6） |
| 18 | U17 撤销 | ✅ 已定（§10.1） |
| 19 | U20 独立登记 | ✅ 已定（§10.2） |
| 20 | Generated Fixture Output Gate | ✅ 已定（§11 检查点 2） |
| 21 | expert_note regression 断言 | ✅ 已定（§9.3） |
| 22 | §3.3 fallback provenance 写死（具名 rule） | ✅ 已定（§3.3，Pre 确认） |
| 23 | D13 展开 | ✅ 已定（§5.2） |
| 24 | Markdown artifact 清理 | ✅ 已清理 |

**所有设计输入已填实，具备 Final Frozen 条件。**

---

**设计稿 Final Frozen 完毕。**
## 14. Errata（Classification Semantic Release COMMITTED 后追加）

本节记录 Final Frozen 文档中发现的事实更正。
不改既有章节内容，按「错误结论要撤销，但错误曾经发生过这一审计事实要保留」原则追加。

追加时间: 2026-10-01
依据: Classification Semantic Release = COMMITTED（Step 4.8h + Step 4.8i + Finalization）

### E1. §3.3.1 缺口位置描述错误

原文称「L295-298 兜底分支把 rule_id 置空为 `""`」是 needs_review materialization 缺口。

实测更正：

- 14 条 unknown claim 走的是 **L288-291 正常匹配分支**
  （`cc.fallback.unknown` 的 match 为 `{"fallback": true}`，
  `_eval_match` 对其恒真，虽在 effective order 中排最后（key=`(4,5,...)`），
  仍被 `for` 循环正常命中）
- L295-298 只在 **registry 异常缺 fallback rule** 时触发
  （代码注释自述「若 registry 异常缺 fallback, 显式降级为 unknown」），
  即在合法 registry 下**不可达**
- **真正缺口是 L288-291 无 flags 槽位** —— 三元组返回里没有位置放 `fallback_flags`

旁证（Finalization 前的 derived/fused 全量 claim 扫描）:

    unknown  method=rule  rule_id=cc.fallback.unknown  n=14

14 条 claim 的 `classification.method` 是 `rule` 而非 `fallback`，`rule_id` 已是真实
具名值，从未被置空。

§3.3 的核心 invariant（Registry-driven，不硬编码 `unknown → needs_review`）**不受影响**，
已在 4.8h 实现并由 `tests/fused/pipeline/test_needs_review_materialization.py` 强制。

### E2. §7.3 `build_inputs.py` 路径错误

原文（及 Finalization 指令）称 `core/fused/pipeline/build_inputs.py:251`。

实测更正：实际路径为 **`core/fused/pipeline/rules/build_inputs.py`**。
`core/fused/pipeline/build_inputs.py` **不存在**。

### E3. §7.3 fusion_version 承载点漏项

原文列 1 个承载点（`build_inputs.py` 的默认值）。

实测更正：生产代码实为 **2 个**承载点，漏了
`core/fused/pipeline/synthetic.py:101` 的 `SYNTHETIC_FUSION_VERSION`。

本轮 Finalization 已一并 bump（`fusion_v1` → `fusion_v2`）。

理由：synthetic 路径用于**镜像生产**；若真实 build 产出 `fusion_v2` 而 synthetic 仍产
`fusion_v1`，则 `tests/fused/pipeline/test_pipeline_e2e_synthetic.py` 验证的是一个
生产环境永不产出的 version 字符串。已实测无测试断言该常量的值，bump 零风险。

### E4. §7.3 Registry fingerprint 口径错误

原文（及 Step 4.8h 汇报）称 Registry fingerprint 为文件 bytes 的 sha256。

实测更正：

- **文件 bytes sha256** = `406dd552e23fd0bdc190a794c9d343ba147dd5f13901b4a2d7650e12770cb0f7`
  （Step 4.8h 记为「prospective registry fingerprint」，**非真实 fingerprint**）
- **真实 Registry fingerprint** = `sha256_full(解析后 payload)`（canonical JSON 的 sha256）
  = `sha256:50361c1b446cc5999927709abb04ca9d73dbb76b95bf0a145a2a435f0a8e6826`
  （9-rule 状态，Finalization 后实测）

两者在 `local/backup/step_4.8i_finalization/release_record.txt` 中均已保留。

**后续所有「Registry fingerprint」引用须显式区分**：

- 文件 bytes hash（**不是** fingerprint）
- `sha256_full(parsed payload)`（真 fingerprint）

计算点：`core/fused/registry_loader.py` `load_bundle()` 内 `sha256_full(payload)`
→ `RegistrySnapshot` → `Meta.registries` → 参与 `build_fingerprint` 重算
（`core/fused/validation.py` L840-850）。**运行时计算，无硬编码 snapshot，无需改文件。**

### E5. §4.2 乙 raise 位置未指定

原文只说「`_eval_match` 若收到该 family，必须 raise」，未指明 raise 应在何处。

实测更正：raise **必须在所有求值分支之前**，包括 `fallback` 与
`content_or_assertion_semantic_rule` 的 early-return 分支。否则：

    {"fallback": true, "explicit_structural_rule": ...}

会先命中 `return True` 而**绕过** raise —— 正是 §4.2 乙明文禁止的
「return True / return False / ignore / fallback」。

4.8i 实现已按此前移；末尾另保留一处**标注不可达**的 raise，防未来分支重排导致退化。

配套事实：4.8i 实现期还发现 `load_bundle()`（**主加载路径**，
`scripts/build_hub.py` / `build_pipeline_build_context` / 几乎全部测试都走它）
用 `_batch_read` 批量读取，**完全不经过** `load_claim_classification_rules()`。
只在单文件方法里加校验会得到一个「看起来通过、实际无效」的防护。
现已在 `load_bundle` 补同一道校验，并有源码级测试锁定两处调用都在。

### E6. §12 改动面清单漏项

原文 §12 列「需改」时漏了 `tests/fused/pipeline/test_fact_assembly.py`。

实测更正：`classify_claim` 改为四元组返回后，该文件 L163 / L173 / L182 / L191
四处三值解包需同步改为四值。4.8h 已将该文件加入授权清单并同步修改
（`got, classification, rule_id, _class_flags = classify_claim(...)` 等）。

该文件 L191-194 的 `rule_id == "cc.fallback.unknown"` 断言在改动后继续 PASS，
是 fallback 真实 rule_id 的既有回归护栏。

### E7. §11 检查点 2 的 fixture 分类（补充，非更正）

§11 检查点 2 已把 `tests/fixtures/derived/` 的 volatile 文件按
`updated_at` / `added_at` / `last_updated` 三个字段分类。本轮实测确认该分类准确：

- volatile 6 个（3 类 × 2 份）：每次 pytest 都变
- 稳定 6 个（entities / relations / state_machine 各 2 份）：U17 Probe 已实测 6 次
  独立构建 + 4 种运行模式全部逐字节相同

附带撤销一条此前登记的错误未决项：曾有「`graph/entities.jsonl` 非确定性」的判断，
源于把其他 timestamp-bearing fixture 的变化错误外推。**该判断自始不成立，已撤销**
（U17 撤销说明，见 §10 U17 与 §10.1 Errata）。

---

**Errata 结束。本节不改变 §0–§13 的任何内容，也不改变 §3.3 的核心 invariant、
§4.3 的 error contract、§7.1/§7.2 的 fusion_version 原则与 release timing。**

