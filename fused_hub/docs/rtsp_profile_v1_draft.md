# RTSP Profile v1（草案）—— 通用 Profile 机制的第一个实例

> **通用定位（2026-10-08 用户确认）**：本文档是「协议 Profile」机制的**第一份实例**，
> 以 rtsp 为样例。Profile 机制本身协议无关——Layer 0 核心（models/canonical/registry/
> validation/export）与注册表加载、fail-closed 校验均为通用。
> ⚠ 但当前 `fused_hub/schema/` 为**单协议平铺**结构：`core/fused/registry.py:28-33` 按固定文件名加载三个注册表，新增协议需先改造为 per-protocol 目录约定（如 `fused_hub/schema/<协议>/`）并让 `load_registry` 支持 `base_dir` 切换（`Registry.__init__` 已接受 `base_dir` 参数），**不改任何核心代码**这一条目前不成立。
> 本草案为甲方案（最小可用）：只注册 131 条 v1 facts **映射后实测出现**的项（映射后 118 facts），不预设未出现的项。

- **依据**: `fused_hub/docs/fused_knowledge_hub_design.md` §3 / §6
- **范围**: Layer 1（rtsp Profile），甲方案（最小可用）
- **状态**: 已落地（草案内容已进 `fused_hub/schema/` 三个注册表 JSON，`core_version: 1.0`；后续修订以本文档为准）
- **数据来源**: `derived/fused/facts/*.jsonl` 经 `core/fused/compat.py` 映射为 v2 Fact
  （Step C1 探针：131 → 118 facts，0 errors；v2 映射结果未落盘，产物在 `derived/per_source/<协议>/<源>/facts/`）

---

## 0. Step C1 实测 distinct 摘要（2026-10-08 快照）

| 维度 | distinct 值 | 合计 |
|---|---|---|
| subject.type | header(10) / method(49) / relation(12) / state(4) / status(43) | 118 facts |
| aspect | case_sensitivity / existence / occurrence / relation_to_other / security_property / target_state / value_type | 118 facts |
| epistemic_type | descriptive(57) / must(39) / normative_unspecified(20) / observed(16) | 132 claims |
| value.type | enum(43) / scalar(34) / struct(22) / text(33) | 132 claims |

> ⚠ 本表为 Step C1 探针时刻快照，非当前注册表全量。当前 `aspect_registry.json` 已扩至 19 项、`subject_type_registry.json` 已扩至 7 项。

> `value.type` 是 Layer 0 固定 12 种 ValueType 的**子集**，不属 Profile 注册；
> 它只作为 `AspectSpec.value_type` 的取值出现。Profile 只注册 subject.type / aspect /
> epistemic_type 三类。

---

## 1. Subject Type Registry（本文档登记 5 项；注册表实际 7 项）

每项声明 `type`（注册名）+ 语义契约 + 实测 name 全集。

### 1.1 `method` —— 协议操作方法

- **语义**: 协议的操作方法。name 为**纯方法名**（如 `SETUP`）。
- **实测 name 全集（11，v2 产物 `derived/per_source/rtsp/rfc/facts/rfc.jsonl` 实测）**: `ANNOUNCE`, `DESCRIBE`, `GET_PARAMETER`, `OPTIONS`, `PAUSE`, `PLAY`, `RECORD`, `REDIRECT`, `SETUP`, `SET_PARAMETER`, `TEARDOWN`
  - v2 产物中 method name 为**纯方法名**；v1 映射期的 `METHOD.Header` 复合形式
    （如 `SETUP.CSeq`）是 v1 事实的历史形态，v2 侧由 header 型 Subject 独立承载。

### 1.2 `header` —— 协议头字段

- **语义**: 协议消息的头字段。
- **实测 name 全集（68，v2 产物 `derived/per_source/rtsp/rfc/facts/rfc.jsonl` 实测）**: `Accept`, `Accept-Encoding`, `Accept-Language`, `Allow`, `Authorization`, `Bandwidth`, `Blocksize`, `CSeq`, `Cache-Control`, `Conference`, `Connection`, `Content-Base`, `Content-Encoding`, `Content-Language`, `Content-Length`, `Content-Location`, `Content-Type`, `Date`, `Expires`, `From`, `Host`, `If-Match`, `If-Modified-Since`, `Last-Modified`, `Location`, `Proxy-Authenticate`, `Proxy-Require`, `Public`, `RTP-Info`, `RTSP option name`, `RTSP option registration`, `Range`, `Referer`, `Require`, `Retry-After`, `Scale`, `Server`, `Servers`, `Session`, `Session identifier`, `Speed`, `Timestamp`, `Transport`, `URL`, `URL host`, `Unsupported`, `User-Agent`, `Vary`, `Via`, `WWW-Authentica`, `basic features`, `character encoding`, `client`, `conference identifier`, `header field value`, `header fields (Section 12)`, `line terminator`, `message body`, `message body length`, `method`, `npt-range`, `octet sequence`, `presentation description`, `protocol`, `sink`, `smpte-range`, `user interface`, `utc-range`
- **⚠ 既有遗留（不属本 Profile 处置）**: 在 **v1 遗留数据**（`derived/fused/facts/header.jsonl`
  实测）里 `Authorization` 与 `authorization` 是两条 distinct name（大小写变体）；v2 rfc
  产物中只出现 `Authorization` 一条。沿用 `local/hub_contract_errata_backlog.md` §10.1 的既有现象。
  ⚠ 但该 backlog §16 已裁定「`Authorization` 与 `authorization` 是同一 header」
  （backlog L755 / L775），与本节「如实登记不合并」的处置存在张力，合并裁定仍挂
  backlog §10.1 待办。

### 1.3 `state` —— 协议状态机状态

- **语义**: 协议状态机的状态。
- **实测 name 全集（4，Step C1 v1 快照 `derived/fused/facts/state.jsonl`）**: `Init`, `Playing`, `Ready`, `Recording`

### 1.4 `status` —— 响应状态码

- **语义**: 协议响应状态码。name 为数字串（v1 `status.NNN` 去 `status.` 前缀后的数字）。
- **实测 name 全集（43，Step C1 v1 快照 `derived/fused/facts/constraint.jsonl`）**: `100`, `200`, `201`, `250`, `300`, `301`, `302`, `303`,
  `304`, `305`, `400`, `401`, `403`, `404`, `405`, `406`, `407`, `408`, `410`, `411`,
  `412`, `413`, `414`, `415`, `451`, `452`, `453`, `454`, `455`, `456`, `457`, `458`,
  `459`, `460`, `461`, `462`, `500`, `501`, `502`, `503`, `504`, `505`, `551`

### 1.5 `relation` —— 关系（状态转移）

- **语义**: 关系型 Subject。name 固定 `transitions_to`（状态转移）。
  `qualifiers.source` / `qualifiers.target` 均为 `state` 型 Subject。
- **实测 name 全集（1）**: `transitions_to`

---

## 2. Aspect Registry（本文档登记 7 项；注册表实际 19 项）

每项声明 `name` + `value_type` + `applicable_subject_types` + `resolution_semantics`
+ `cardinality` + 语义契约。

| aspect | value_type | applicable_subject_types | resolution_semantics | cardinality | 语义 |
|---|---|---|---|---|---|
| `case_sensitivity` | `scalar` | `header` | `consensus` | `one` | 头字段是否大小写敏感（bool） |
| `existence` | `scalar` | `method`, `state` | `consensus` | `one` | 对象是否存在（bool） |
| `occurrence` | `scalar` | `header`, `method` | `consensus` | `one` | 出现次数（int） |
| `relation_to_other` | `struct` | `method` | `consensus` | `many` | 字段间关系（`{relation, target}` 结构） |
| `security_property` | `text` | `header`, `method` | `consensus` | `many` | 安全属性描述（自由文本） |
| `target_state` | `text` | `relation` | `consensus` | `one` | 状态转移的目标状态名 |
| `value_type` | `enum` | `status` | `consensus` | `one` | 状态码类别（1xx/2xx/3xx/4xx/5xx） |

> 本表 7 项为 Step C1 登记快照；当前 `fused_hub/schema/aspect_registry.json` 实际 19 项，
> `occurrence` 的 `applicable_subject_types` 亦已扩至 `header` / `method` / `status`。

**逐项说明**：

- **`value_type`（aspect）与 `ValueType`（Layer 0 12 种）撞名说明**: 本 aspect 名
  `value_type` 直接沿用 v1 的 property 名，语义是「状态码类别」（如 `413 → 4xx`），
  其 value 是 `enum` 类型。它**不是** Layer 0 的 ValueType 概念，仅名字撞名，保留
  以忠实 v1 映射（甲方案不擅自改名）。

- **`cardinality` 判定依据**:
  - `security_property` = `many`：实测存在单 fact 承载多条 claim 的情况（traffic outlier；
    具体 claim 条数需以最新一次探针复核为准），必须 `many` 才能通过 fail-closed。
  - `relation_to_other` = `many`：实测当前每 fact 恰 1 claim，但语义上一个 method
    可关联多个 target（`{relation, target}`），故声明 `many` 以保留语义正确性。
  - 其余 = `one`：实测全 1 claim，且语义单值。

- **`resolution_semantics` 统一 `consensus`**: v2 侧当前无跨源 resolution（`core/fused/compat.py`
  不映射 v1 旧 resolution，仅在 `derived/per_source/` 的 v2 事实中由
  `core/fused/downstream/resolver.py` 现场消解），无冲突需裁决。未来出现跨源冲突时再按需细分
  （precedence 等），属 Layer 1 演进，不阻塞本草案。

---

## 3. Epistemic Type Registry（4 项）

每项声明 `name` + `authority_rank` + `can_be_canonical` + `scope_required`
+ `llm_interpretation`（依据 design §3 Epistemic Type 语义元属性）。

| name | authority_rank | can_be_canonical | scope_required | llm_interpretation |
|---|---|---|---|---|
| `must` | 100 | true | false | 协议规范中的强制要求（RFC 2119 MUST 语义） |
| `normative_unspecified` | 80 | true | false | 协议规范中的要求（未明确强制等级） |
| `descriptive` | 50 | false | false | 对协议对象的描述性陈述 |
| `observed` | 20 | false | true | 来自实测流量的观测（样本证据，非规范结论） |

**判定理由（设计建议，待用户确认）**：

- **authority_rank 排序**：规范强制（must）> 规范未分级（normative_unspecified）>
  描述性（descriptive）> 实测观测（observed）。裁决排序时规范优先于观测。
- **can_be_canonical**：`must` / `normative_unspecified` 是规范要求，可作为 canonical
  结论；`descriptive` / `observed` 是描述或样本，不作 canonical。
- **scope_required**：`observed` 必须携带 scope（观测范围），其余不强制。
- 具体数值（100/80/50/20）为**相对排序的量化建议**，非契约固定值，可在 C2 前调整。

---

## 4. 覆盖验收（相对 Step C1 实测范围 100%）

| 注册表 | 实测 distinct | 本草案登记 | 覆盖 |
|---|---|---|---|
| Subject Type | 5 | 5 | 100% |
| Aspect | 7 | 7 | 100% |
| Epistemic Type | 4 | 4 | 100% |

无「暂缺待补」项。

> ⚠ 该 100% 是相对 Step C1 探针范围而言。相对当前注册表全量（7 subject type /
> 19 aspect / 4 epistemic type），本文档覆盖 5/7 subject type、7/19 aspect、
> 4/4 epistemic type。

---

## 5. 设计选择（2026-10-08 已确认，用户采纳推荐方案）

1. **Epistemic Type 的 authority_rank 数值**：must=100 / normative_unspecified=80 /
   descriptive=50 / observed=20；`can_be_canonical`：must / normative_unspecified = true，
   descriptive / observed = false；`scope_required`：仅 observed = true。✅
2. **`relation_to_other` 的 cardinality = `many`**：保留（语义多值）。✅
3. **`value_type` aspect 撞名**：保留原名（忠实 v1，不擅自改名）。✅

---
*Step C1 草案 · 2026-10-08｜注册表落地并扩展至 2026-10-09（7 subject type / 19 aspect）*

## 6. 2026-10-09 增补（traffic 源）

注册表新增 2 个 subject type：

| type | 语义 | 来源 |
|---|---|---|
| `protocol` | 协议级观测对象（如 rtsp_transport 传输分布、rtsp_public_methods 方法集） | traffic 源 |
| `actor` | 协议参与者（如 rtsp_server 的监听端口观测） | traffic 源 |

新增 12 个 aspect（在原 7 项之上）：`method_sequence` / `syntax` / `definition` / `state_changing` / `value_enum` 等，
完整清单见 `fused_hub/schema/aspect_registry.json`（19 项）。
