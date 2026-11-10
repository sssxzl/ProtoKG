# rfc 源改造方案 —— 借鉴 SemFuzz 的「语义约束抽取」

> 日期：2026-10-20。本文档是 rfc 源从「结构抽取」升级为「语义约束抽取」的设计真源。
> 借鉴对象：SemFuzz（arXiv 2603.05989, 2026）的「构造约束 + 处理期望」知识抽象。

---

## 一、改造目标与背景

### 背景（现状诊断）

当前 rfc 源（`core/fused/rfc_extractor.py`）用**确定性正则**抽取，只能拿到协议的「骨架结构」：

| 现有产物 | 数量（RTSP） | 知识层次 |
|---|---|---|
| 方法（method definition）| 11 | 结构（方法名 + 一句话语义）|
| 字段（header syntax/definition）| 44 | 结构（字段名 + 语法）|
| 状态码（status definition）| 15/43 | 结构（状态码 + 含义）|

**缺失的关键知识**：字段的**语义约束**（"这个字段该满足什么约束"）和**处理期望**（"违反约束后该得到什么响应"）。这两者才是协议知识里**最接近漏洞触发**的部分——而现有 rfc 源完全没抽。

对照同领域（调研见 `docs/rfc_knowledge_extraction_survey` 相关讨论）：
- FlowFSM 只抽状态机（不全面，已被你否决）
- **SemFuzz** 抽「构造约束 C + 处理期望 P」配对，是当前最全、最贴合本项目技术路线的。

### 改造目标

1. 让 rfc 源产出**语义约束知识**：`(字段, 构造约束, 处理期望)` 三元组，而非只有字段名/状态码。
2. 约束映射进**六元组知识中枢**（保持可溯源）。
3. 约束**接入边界探针**，成为「源 A 协议语义」的自动候选来源（无需人工找边界）。

---

## 二、核心思路与借鉴要点

### 借鉴 SemFuzz 的抽象

SemFuzz 把 RFC 规范形式化为 **SR = (协议 p, 消息 m, 字段 f, 构造约束 C, 处理期望 P)**：

- **构造约束 C**：消息「应该长什么样」（有效格式的边界），如 "QNAME 单 label ≤ 63 字节"。
- **处理期望 P**：接收方「应该怎么响应」，如 "超长 label 应返回 RCODE=1 (FORMERR)"。

**关键洞察**：C 和 P 是**配对**的——违反哪条 C，就该触发哪个 P。这正是「语义 oracle」的基础。

### 借鉴什么、不借鉴什么

| 借鉴 | 不借鉴 |
|---|---|
| 「构造约束 + 处理期望」配对抽象 | 黑盒 fuzz 框架（直接跑真实服务器）|
| 故意违反约束做语义 oracle 的思想 | 需用户提供消息类型清单 + 种子流量（我们自抽方法）|
| 约束与响应的配对可做漏洞判定 | — |

### 与本项目技术路线的对齐

| 本项目特点 | SemFuzz 抽象如何对齐 |
|---|---|
| 六元组可溯源 | SR 的 (p,m,f,C,P) 映射进 Subject/Aspect/Value/Evidence |
| 五源分工（rfc=规范源）| 约束+期望正是"规范"的核心内容 |
| 边界探针（legal_boundary）| 构造约束 C = 边界候选；处理期望 P = oracle 判定依据 |
| 协议无关 | 约束+期望抽象是协议通用的 |

---

## 三、具体改造内容与步骤

### 阶段 1：新增 aspect（数据结构层）

在 `core/fused/hub/registry/aspect_registry.json` 新增/扩展两个 aspect：

```json
// ① 扩展 legal_boundary 的 applicable，加入 header（字段级边界）
{"name": "legal_boundary", "value_type": "struct",
 "applicable_subject_types": ["method", "header"], ...}

// ② 新增 response_expectation（处理期望，语义 oracle）
{"name": "response_expectation", "value_type": "struct",
 "applicable_subject_types": ["method", "header"],
 "resolution_semantics": "consensus", "cardinality": "many",
 "description": "违反某约束后接收方应给出的响应（{violation, expected_code, expected_behavior}，SemFuzz 的 P）"}
```

### 阶段 2：LLM 语义约束抽取器（新增模块）

在 `core/fused/rfc_extractor.py` 里新增约束抽取（rule 先打底，LLM 补语义）：

- **rule 部分（确定性，先做）**：识别 RFC 里的规范性关键词 `MUST/MUST NOT/SHALL/SHOULD/长度/范围`，定位含约束的句子 → 候选约束。
- **LLM 部分（`-m llm`，后补）**：把候选约束段落喂 LLM，结构化输出三元组：

```json
{"constraints": [
  {"field": "QNAME", "constraint": "单 label ≤ 63 字节，域名总长 ≤ 255",
   "violation": "label 长度字段 > 实际内容", 
   "expected_code": "1", "expected_behavior": "FORMERR",
   "rfc_section": "RFC 1035 §3.1"}
]}
```

- **幻觉抑制**：对齐 ChatAFL 的自一致性（同一段落重复采样取一致）+ 对齐 SpecGPT 的 ensemble 投票（可选）。

### 阶段 3：约束 → 六元组 fact 映射

在 `core/fused/norm.py` 新增映射（对齐 SemFuzz 的 C/P 配对）：

| SemFuzz 抽象 | 六元组 fact | 说明 |
|---|---|---|
| 字段 f | `Subject(type=header, name=f)` | 字段作为 subject |
| 构造约束 C | `Aspect=legal_boundary` | value=`{dim:f, legal:约束, illegal:违反, trigger:预期后果}` |
| 处理期望 P | `Aspect=response_expectation` | value=`{violation:违反, expected_code, expected_behavior}` |
| RFC 章节 | `Evidence.locator` | 可溯源（保持本项目卖点）|

### 阶段 4：接入边界探针

边界探针（`docs/设计/种子生成/边界探针设计.md`）的「源 A 协议语义」目前靠人工推导，改造后：

```
rfc 源抽取的 legal_boundary（构造约束）
   → 直接作为边界探针的「候选边界」
   → oracle 判定（复用 dry run 重放）确认合法/非法
   → 处理期望 P 作为 oracle 的「预期响应」基准
```

这样边界探针从「人工找边界」变成「从 RFC 约束自动推导边界」。

---

## 四、关键模块与数据结构调整

### 涉及模块

| 模块 | 改动 |
|---|---|
| `core/fused/rfc_extractor.py` | 新增 `_extract_constraints`（rule + LLM 三元组抽取）|
| `core/fused/norm.py` | 新增 `constraint_norm_to_facts`（C/P → fact）|
| `core/fused/hub/registry/aspect_registry.json` | 扩展 legal_boundary + 新增 response_expectation |
| `core/fused/downstream/rag_seedgen.py` | assemble_bundle 新增 `constraints` 分桶 |
| `core/fused/downstream/edge_cover.py` 或 generic_danger | 消费约束做「故意违反」种子 |
| 边界探针 | 消费 legal_boundary 作候选来源 |

### 数据结构调整

1. **新增 norm 类型**：`constraint`（区别于现有 method/field/outcome），content 存 `field=... constraint=... violation=... code=...`。
2. **新增 fact aspect**：`response_expectation`；`legal_boundary` 扩展 applicable。
3. **assemble_bundle 新增桶**：`constraints` = 字段约束列表，供种子生成消费。

---

## 五、预期效果与潜在风险

### 预期效果

1. **知识补齐**：rfc 源从「字段名/状态码」升级为「字段 + 约束 + 期望响应」，补齐最接近漏洞的知识层。
2. **边界探针自动化**：从「人工找边界」变为「从 RFC 约束自动推导边界」，强化「多协议低成本迁移」卖点。
3. **可溯源的语义 oracle**：处理期望 P 提供「违反约束该得到什么响应」的判定基准，比 crash-only oracle 更细。
4. **论文卖点**：rfc 源借鉴 SemFuzz 的「约束+期望」抽象 + 保持结构化可溯源，是相对 SemFuzz（黑盒）和 FlowFSM（只状态机）的差异化。

### 潜在风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| **LLM 幻觉**（约束抽错）| 错误约束污染种子 | 自一致性（ChatAFL）+ ensemble（SpecGPT）+ fail-closed 校验 |
| **二进制协议字段依赖**（dtls/tls/ssh 长度字段级联）| LLM 难处理二进制约束 | 先只做 text 协议（dns/ftp/sip/smtp/rtsp），二进制协议后补或降级 rule |
| **约束与边界探针耦合** | 抽错约束误导探针 | 约束带 evidence 溯源，oracle 用多次重放取多数 |
| **LLM 调用成本** | 每条约束一次 LLM 调用 | 缓存 + 只对含 MUST/长度/范围关键词的段落调 LLM |

---

## 六、落地节奏建议

1. **先做阶段 1+2 的 rule 部分**（确定性抽约束候选，零 LLM，可测）——快速验证「约束能抽到」。
2. **再做阶段 3**（映射进 fact + fail-closed）——让约束进知识中枢。
3. **后做 LLM 部分 + 边界探针对接**（阶段 2 LLM + 阶段 4）——对齐 SemFuzz 的完整闭环。
4. **验证**：RTSP（text 协议）端到端，看「约束 → 边界探针 → 种子」链路。

---

*v1 设计 · 2026-10-20 · 待用户确认后进入实施*
