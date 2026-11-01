# Fused Knowledge Hub v2 — 设计真源

> **状态：Draft（待用户审后冻结）**
>
> 本文档定义 **Layer 0（中枢核心）** 的结构契约。Layer 1（协议 Profile）已有首个实例（rtsp Profile v1，见 `rtsp_profile_v1_draft.md`）；Layer 2（知识填充）已实现于 `core/fused/norm.py` / `expert_note.py` / `vuln.py` / `source.py` / `traffic.py`，其具体行为不在本文档规格内。
>
> 落盘日期：2026-10-08（Layer 0 抽象部分持续有效；注册表实际内容见 `fused_hub/schema/` 三个 JSON，已于 2026-10-09 扩展至 7 个 subject type / 19 个 aspect）

---

## 第一部分：设计哲学

核心原则：

- **P1 开放组合，不封闭枚举** —— 知识两个维度（讨论什么、断言什么）都可扩展
- **P2 事实身份与证据来源分离** —— fact_key 不含来源/时间/观测实例
- **P3 一切皆可追溯** —— 任何 fact 可回放到原始字节
- **P4 关系是一等公民** —— 对象间关系是 Subject，不是属性
- **P5 条件可复合** —— 逻辑表达式，不是 always/unknown 两值
- **P6 值类型丰富** —— 12 种（Layer 0 定义的 ValueType 全集；Profile 只注册实际使用的子集，见 `fused_hub/schema/aspect_registry.json`）
- **P7 确定性、可复现** —— 内容决定 ID；规范序列化
- **P8 Fail-closed** —— 未注册的引用是硬错误，不静默
- **P9 矛盾可见** —— 同 fact_key 值冲突显式 unresolved，不静默覆盖
- **P10 LLM 安全** —— 每条事实携带 epistemic + support + generalization

---

## 第二部分：三层架构

```
Layer 0  中枢核心       协议无关的元结构
Layer 1  协议 Profile    每协议一份，注册 type / aspect / 值域 / epistemic
Layer 2  知识填充        五源各自映射到 Profile
```

**Layer 0 里不出现任何具体协议的对象类型、aspect 名、值域。**

---

## 第三部分：Layer 0 核心结构

### 【一条知识的原子】

```
知识原子 = ⟨Subject, Aspect, Condition, Value, Epistemic, Evidence⟩
```

其中 `(Subject, Aspect, Condition)` 构成 **fact_key**（身份）；
`Value / Epistemic / Evidence` 属于 **Claim** 层。

### 【Subject】

```python
Subject = {
    type: str,              # 类型标识（字符串，值域由 Profile 定义）
    name: str,              # 对象标识
    qualifiers: dict = {},  # 可选限定（role / direction / instance / ...）
    path: list[str] = [],   # 子路径（嵌套对象）
}
```

**关系作为 Subject（P4）：**

```python
Subject = {
    type: "relation",
    name: "<relation-type>",
    qualifiers: {
        source: Subject,
        target: Subject,
    }
}
```

Layer 0 不知道 `type` 有哪些值。值域由 Profile 提供。

### 【Aspect】

Layer 0 只定义 Aspect 是字符串键，每项有语义契约：

```python
AspectSpec = {
    name: str,
    value_type: ValueType,                       # 接受哪种 value
    applicable_subject_types: list[str] | "*",   # 适用于哪些 subject type
    resolution_semantics: str,                   # 裁决语义（consensus / precedence / ...）
    cardinality: "one" | "many",                 # 单值 or 多值
}
```

具体 aspect 值由 Profile 定义。**Layer 0 不含 existence / value_domain 等具体名。**

### 【Condition】

```python
Condition =
    | {type: "always"}
    | {type: "never"}
    | {type: "unknown"}
    | {type: "predicate", subject: Subject, aspect: str, op: str, value: Value}
    | {type: "and", operands: [Condition, ...]}
    | {type: "or",  operands: [Condition, ...]}
    | {type: "not", operand: Condition}
    | {type: "ref", condition_id: str}
```

**op 集合（Layer 0 基础，Profile 可扩）：**

| op | 含义 |
|---|---|
| `eq` / `neq` | 等 / 不等 |
| `in` / `not_in` | 属于 / 不属于 |
| `gt` / `gte` / `lt` / `lte` | 数值比较 |
| `matches` | 正则 / ABNF / 模式 |
| `contains` | 集合包含 |
| `exists` / `not_exists` | 存在性 |
| `before` / `after` | 时间 / 顺序 |

**为什么支持 `ref`**：防条件表达式重复、便于复用、便于审计。

### 【Value —— 12 种类型】

| # | 类型 | 用途 | 落地状态 |
|---|---|---|---|
| 1 | `scalar` | 原子值（bool/int/float/str） | 已落地 |
| 2 | `enum` | 受控集合的成员 | 已落地 |
| 3 | `set` | 无序唯一集合 | 已落地 |
| 4 | `sequence` | 有序列表 | 实现待补 |
| 5 | `range` | 数值 / 时间区间 | 实现待补 |
| 6 | `pattern` | 正则 / ABNF / 语法 | 已落地 |
| 7 | `struct` | 字段映射 | 已落地 |
| 8 | `ref` | 对象引用 | 实现待补 |
| 9 | `observation` | 观测统计（count / rate / sample） | 实现待补 |
| 10 | `binary` | 原始字节（二进制协议） | 实现待补 |
| 11 | `union` | 标签联合（消息变体） | 实现待补 |
| 12 | `text` | 自由文本（LLM 兜底） | 已落地 |

**落地现状（2026-10-30 实测）**：`Value` 在 Layer 0 是通用二字段 dataclass
（`core/fused/models.py:22-25`），**不按 type 分派校验分支** —— 12 种是
`ValueType` 别名声明的词表；实际落地情况见上表「落地状态」列：
`binary` / `observation` / `range` / `sequence` / `union` 五种目前**无任何
代码生产者，也无 aspect 引用**；`ref` 仅被 `precondition` aspect 声明
（`value_type=ref`），但该 aspect 当前无产物，故亦标为「实现待补」。
类型一致性由 `core/fused/validation.py::validate_value` 强制
（`value.type` 必须等于 `AspectSpec.value_type`，否则抛
`ValueTypeMismatchError`）。

**边界说明（2026-10-08 增补）**：

- transition 类知识用 `struct`（含 `from_state` / `on_trigger` / `to_state`），**不是** `sequence`
- `sequence` 用于**多个对象的顺序**（如 method 序列 `OPTIONS → DESCRIBE → SETUP`）
- `pattern` 用于 ABNF / 正则 / 语法约束（如 RTSP-Version 的 BNF 形式）
- `observation` 用于 count / rate / sample 等统计值（与 `range` 不同：range 是值域，observation 是已发生）

**值结构：**

```python
Value = {
    type: ValueType,   # 12 种之一
    data: any,
}
```

**验证（P8 fail-closed）：** aspect 声明的 `value_type` 必须与 `value.type`
一致；不一致 → **硬错误**。

### 【Fact】

```python
Fact = {
    fact_id: str,
    fact_key: {
        protocol: str,
        version: str,
        subject: Subject,
        aspect: str,
        condition: Condition,
    },
    claims: list[Claim],
    resolution: Resolution | None,
    alignments: list[Alignment],
    metadata: {
        created_at: str = "",        # 事实落盘时间
        profile_version: str = "",   # Profile 注册表版本（与 fact_key.version 不同：
                                     # 后者是协议版本，如 "1.0"）
    },
}
```

`metadata.profile_version` 记录该事实所依据的 Profile 注册表版本
（`core/fused/models.py:248-251` 的 `FactMetadata`）；它与
`fact_key.version`（协议版本，如 `"1.0"`）是两个独立字段，不构成重复。

### 【Claim】

```python
Claim = {
    claim_id: str,
    fact_id: str,
    value: Value,
    epistemic_type: str,     # 开放注册（Profile 定义值域）
    authority: str,
    scope: Scope,
    evidence: list[Evidence],
    flags: list[str],
    confidence: float | None,
}

Scope = {
    observation_population: str | None,
    measurement_unit: str | None,
    independence: str | None,        # independent / dependent / unknown
    bounded: bool,
    bounds: dict,
}
```

### 【Epistemic Type 语义元属性】（2026-10-08 增补）

每个 `epistemic_type` 注册项必须声明：

| 字段 | 含义 |
|---|---|
| `authority_rank: int` | 权威层级（裁决排序用，越大越权威） |
| `can_be_canonical: bool` | 是否可作为 canonical 结论 |
| `scope_required: bool` | 是否必须携带 scope |
| `llm_interpretation: str` | 给 LLM 的解释提示 |

**Layer 0 只定义元属性框架**。具体 `epistemic_type` 值由 Layer 1 Profile 定义。

常见候选（Layer 1 定义时参考）：

- `normative` — 协议规范要求
- `observational` — 实测观察
- `descriptive` — 描述性陈述
- `observed` — 单次观测事实
- `uncertain` — 不确定性声明

### 【Evidence】

```python
Evidence = {
    evidence_id: str,
    claim_id: str,
    source_type: str,
    source_id: str,
    document: str,
    locator: Locator,
    quote: str | None,
    content_fingerprint: str,
    extraction_fingerprint: str,
}
```

```python
Locator =
    | {type: "line",   file: str, line: int, col: int | None}
    | {type: "byte",   file: str, offset: int, length: int}
    | {type: "time",   file: str, timestamp: str}
    | {type: "field",  file: str, path: list[str]}
    | {type: "range",  file: str, start: int, end: int}
```

### 【Resolution】

```python
Resolution = {
    status: "resolved" | "unresolved",
    method: "single" | "consensus" | "precedence" | "conflict" | "insufficient",
    basis_claim_ids: list[str],
    reason: str,
    reason_code: str,
    policy_version: str,
    support: {
        independent: int,
        dependent: int,
        unknown: int,
        total: int,
    } | None,
    generalization: {
        scope: str,             # protocol-wide / single-scenario / unknown
        confidence: float | None,
    } | None,
}
```

`support` 和 `generalization` 为 LLM 服务（P10）。

### 【Alignment】

```python
Alignment = {
    claim_id: str,
    relation: str,           # supports / contradicts / refines / deviates / ...
    target: "resolution" | {"claim_id": str},
    reason: str | None,
}
```

---

## 第四部分：防矛盾机制（P9）

### 1. 身份确定性

```
fact_id = "f2_" + sha256(canonical_serialize(fact_key)).hexdigest()[:16]
```

`canonical_serialize` 有严格规范：键排序、编码固定、null 处理规则。
任何歧义 → **报错，不生成 ID**。

（实现见 `core/fused/canonical.py:128`；`f2_` 前缀是 v1 退役后保留的
v2 前缀，与历史 `f1_` 产物隔离。）

### 2. 值冲突显式化

同一 fact_key 下多条 Claim 若 canonical value 不同：

- **不静默覆盖**
- 显式 `status = unresolved`, `method = conflict`
- 所有冲突 Claim 保留，`alignment.relation = contradicts` 互相指向

### 3. 注册治理

每个 Profile 是**封闭声明**。未注册的引用 = **硬错误**。
防止拼写错误静默创建幽灵类型。

### 4. 序列化唯一性

同一逻辑内容 → 唯一字节序列。提供 `canonical_serialize` 作为唯一入口。
任何非 canonical 输入 → 规范化再处理。

### 5. 变更审计

- Profile 版本变化 → 记录在 `metadata.profile_version`
- 事实内容变化 → 新 `fact_id`
- 事实内容不变但 Profile 演进 → `fact_id` **不变**

---

## 第五部分：LLM 安全接口（P10）

### 导出格式

```json
{
  "protocol": "<profile-id>",
  "profile_version": "...",
  "facts": [
    {
      "fact_key": {},
      "resolution": {
        "status": "resolved",
        "value": {},
        "epistemic": "...",
        "support": {"independent": 0, "dependent": 0, "unknown": 0, "total": 0},
        "generalization": {"scope": "...", "confidence": null}
      },
      "all_claims": [
        {
          "claim_id": "...",
          "value": {},
          "epistemic": "...",
          "evidence_summary": "..."
        }
      ]
    }
  ]
}
```

**LLM 看到三层：**

1. 断言内容（value）
2. 认识论属性（epistemic_type）
3. 支持与泛化（support + generalization）

### 冲突显式呈现

```json
{
  "resolution": {"status": "unresolved", "method": "conflict"},
  "conflicting_claims": []
}
```

---

## 第六部分：扩展治理

### 三类注册表

| 注册表 | 归属 |
|---|---|
| Subject Type Registry | Profile |
| Aspect Registry | Profile |
| Epistemic Type Registry | Profile |

实际落地于 `fused_hub/schema/` 三个 JSON（`core_version: "1.0"`）。

### 扩展协议

**新增对象类型 / aspect：**

1. Profile 声明新的注册项（含语义契约）
2. 版本号 minor bump
3. 已有 `fact_id` **不变**

**新增值类型：**

1. 属于 Layer 0 变更
2. 需中枢核心版本 bump
3. 极少发生

### 版本管理

| 版本号 | 覆盖范围 | 触发条件 |
|---|---|---|
| `core_version` | Layer 0 | 核心结构变化 |
| `profile_version` | Layer 1 | Profile 项增减 / 改语义 |
| `policy_version` | 裁决策略 | 裁决策略变化 |

**`fact_id` 不含任何版本** —— 同一事实不因版本演进换 ID。

---

## 第七部分：与旧设计的关系

### 保留

- Fact / Claim / Evidence 三层模型
- Claim 是知识本体，Resolution 是派生视图
- 确定性 ID
- Phase A / B 分离
- 跨源聚合机制

### 推翻

| 旧 | 新 |
|---|---|
| kind 固定 6 值枚举 | 并入 `Subject.type`（开放） |
| property 固定 18 值 | 并入 `Aspect`（开放） |
| 扁平 subject | 结构化 |
| 粗糙 condition | 复合表达式 |
| 受限 value | 12 种类型 |

### 新增

- Scope / support / generalization（LLM 安全）
- fail-closed 治理
- 冲突显式化
- 三层架构（Layer 0 / 1 / 2）

### 迁移策略：双轨并行

1. 新结构落地 + 一个协议 Profile 初版
2. 双轨：旧 `fact_key` 作为兼容层保留，新知识走新格式
3. 切换：五源走新格式，旧格式归档

**当前进展（2026-10-30）**：第 1 步已完成（v2 结构落地 + rtsp Profile v1 注册表）；第 2 步双轨已实现 —— v1 产物在 `derived/fused/`（131 facts），v2 产物在 `derived/per_source/`（4 协议 × 五源），`core/fused/compat.py` 提供 v1 → v2 映射与 `core/fused/export.py` 的 v1 回退入口。第 3 步（切换）未触发。

---

## 第八部分：Layer 1（Profile）现状

Layer 1 已落地首个实例：**rtsp Profile v1（甲方案最小可用）**，见 `fused_hub/docs/rtsp_profile_v1_draft.md`。实际注册表内容在 `fused_hub/schema/` 三个 JSON（subject_type_registry 7 项 / aspect_registry 19 项 / epistemic_type_registry 4 项），其中已含 2026-10-09 traffic 源扩展的 `protocol` / `actor` 两个 subject type。协议运行期参数（allowed_methods / transport / message_schema）在 `fused_hub/targets/<协议>/profile.json`。