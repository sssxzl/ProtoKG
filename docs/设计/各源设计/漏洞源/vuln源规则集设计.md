# docs/设计/各源设计/漏洞源/vuln源规则集设计.md — vuln 源 Candidateization 规则集设计

> Step 4.8g · vuln 源收尾 · 设计真源
> 契约: `docs/设计/顶层设计/规范化序列化规范.md` 第二章 §2.1–§2.3（Rule Contract 8 字段）
> 参照实现: `core/fused/pipeline/rules/candidateization.py`（4.8b 的 CR-1..CR-5）
> 上游: `docs/设计/种子生成/规则集设计.md` §3（4.8b 四类规则集设计）


## 0. 素材实测（本步重新核对，非沿用描述）

37 条 `kind=vuln_seed` / `kb_source_type=vuln` 的 ProtocolNorm，`extraction_method=json_parse`，
`facets` 全部为 `["vuln_pattern", "has_mutation_hints"]`，`related_norms` 全部为空。

`norm.content` 是单行结构化文本，格式实测为：

```
[vuln] case_id=RTSP-001 avd_id=AVD-2021-39283 cve= cwe=CWE-617 risk_level=中危 \
scope=seedgen confidence=medium target=unknown expected= trigger_methods=SETUP+PLAY \
trigger_field= | trigger_condition=多个 SETUP 和 PLAY 命令 | desc=Live555 是一个…
```

**分隔规则（实测 37/37 全部可解析，无例外）**：

| 区段 | 分隔方式 | 说明 |
|---|---|---|
| 头部 | 单空格 | `case_id`..`trigger_methods` 共 10 个 key，值均为**单 token**（可为空串） |
| `trigger_field` | 值延伸到 ` \| ` 为止 | 值本身**可含空格**（实测 `Transport header`） |
| `trigger_condition` | ` \| ` 分隔 | 值可含空格（实测最长 64 字） |
| `desc` | ` \| ` 分隔 | 值可含空格（实测最长 300+ 字） |

**非空字段计数（37 条中）**：

| 字段 | 非空 | 取值样例 |
|---|---|---|
| `case_id` | 37/37 | `RTSP-001`..`RTSP-037` |
| `avd_id` | 37/37 | `AVD-2021-39283` |
| `cve` | 17/37 | `CVE-2026-31256` |
| `cwe` | 32/37 | 19 个 distinct，如 `CWE-617` / `CWE-476` / `CWE-287` |
| `risk_level` | 37/37 | 见下 |
| `scope` | 37/37 | `seedgen`(16) / `not_rtsp_protocol`(12) / `insufficient_source`(7) / `not_rtsp_client_side`(1) / `not_trigger_vulnerability`(1) |
| `confidence` | 37/37 | `n/a`(20) / `medium`(12) / `high`(5) |
| `target` | 37/37 | 全为 `unknown` |
| `expected` | **0/37** | 全空 |
| `trigger_methods` | **7/37** | `SETUP`(5) / `SETUP+PLAY`(1) / `SETUP+DESCRIBE+PLAY+TEARDOWN`(1) |
| `trigger_field` | **13/37** | 见 §3.2 |
| `trigger_condition` | **15/37** | 6–64 字中文自由文本 |
| `desc` | 37/37 | 漏洞描述全文 |

`risk_level` 分布（**关键：两种语义混在一列**）：

| 值 | 条数 | 性质 |
|---|---|---|
| `低危` | 7 | 真严重度 |
| `中危` | 5 | 真严重度 |
| `(AVD_标签_NVD,N/A)` | 17 | **溯源标签，不是严重度** |
| `(AVD_标签_NVD,操作系统类)` | 2 | 溯源标签 |
| `(AVD_标签_NVD,硬件设备类)` | 2 | 溯源标签 |
| `(AVD_标签_NVD,应用程序类)` | 2 | 溯源标签 |
| `(AVD_标签_安全社区,N/A)` | 2 | 溯源标签 |

→ 25/37 是 `(来源,类别)` 形态的溯源标签，**不是 severity**。见 §4.3 的处理。


## 1. 设计原则（承 4.8b C1–C4，本源的具体化）

- **C1 只处理能明确识别的知识。** 判不出 → projection 返回 `None` → 契约 §2.3 规定 **emit 0**，
  **不是** rule contract violation。
- **C2 property 名取自 `property_registry` 的 18 个受控 property。** 本源只用 3 个中的 2 个（§3.4）。
- **C3 condition 取自 `condition_schema` 的 8 类 AST**（`always` / `unknown` / `state` / `direction` /
  `field` / `numerical` / `temporal` / `packet_position` / `composite`）。
- **C4 不发明新 kind。** `fact_key.kind` 只取 `KIND_DOMAIN` = {method, header, constraint, state, transition}；
  `actor` 只取 `ACTOR_DOMAIN` = {client, server, both, not_applicable, unknown}。
- **C5（本步新增）subject 必须能落到注册过的 subject。** `subject_registry.initial_subjects` +
  `alias_registry` 是唯一权威。落不进去 → emit 0，并把值记入「ontology gap」清单（§5）。
- **C6（本步新增）不把「漏洞是什么」塞进「触发条件」。** `security_condition` 只放 `trigger_condition`
  （它才是 pre-condition）；`desc` 归 `security_consequence`。


## 2. eligibility 谓词：`scope` 作为门禁（本步设计决定，非契约明文）

`scope` 是 vuln extractor **自己**对每条种子的可用性判定，5 个受控值：

| scope | 条数 | 语义 | 本步处理 |
|---|---|---|---|
| `seedgen` | 16 | 可直接用于种子生成 | **eligible** |
| `not_rtsp_protocol` | 12 | 与 RTSP 协议无关 | emit 0 |
| `insufficient_source` | 7 | 溯源不足 | emit 0 |
| `not_rtsp_client_side` | 1 | 非客户端侧 | emit 0 |
| `not_trigger_vulnerability` | 1 | 非可触发漏洞 | emit 0 |

**为什么不门禁是错的**：`not_rtsp_protocol` 里有一条带 `trigger_methods=SETUP`（RTSP-027）。
不门禁就会在 `method.SETUP` 上产出一条「SETUP 存在 security_condition」的 Fact，而这条漏洞
根本不是关于 RTSP 的 —— 它会污染中枢，并可能与 RFC 在 `method.SETUP` 上的规范性陈述争夺
同一个 fact_key 的 resolution。

**为什么这不是真决策点**：两个设计并非五五开。不门禁的那一侧会往中枢注入已知的错误陈述，
没有可辩护性。故直接门禁，并在 audit 中显式记录该决定。

**实测影响**（门禁 vs 不门禁）：

| 维度 | 不门禁 | 门禁 scope==seedgen |
|---|---|---|
| 有 `trigger_methods` 的种子 | 7 | 6（去掉 RTSP-027） |
| 有 `trigger_field` 的种子 | 13 | 9 |
| 有 `trigger_condition` 的种子 | 15 | 14 |


## 3. 规则集清单

全部 3 条规则的 `applicable_protocol_norm_type` 均为 `vuln_seed`。
`scope_projection` 全部为 `unrestricted`（vuln 数据无任何 scope 约束信息）。

### 3.1 VR-1 `cand.vuln.method_security_condition`

| 字段 | 值 |
|---|---|
| `applicable_protocol_norm_type` | `vuln_seed` |
| `eligibility_predicate` | content 可解析 **且** `scope == "seedgen"` **且** `trigger_methods` 非空 **且** `trigger_methods[0]` 解析为注册 `method.*` subject **且** `trigger_condition` 非空 |
| `fact_key_projection` | `kind="method"`, `actor="client"`, `subject="method.<METHOD>"`, `property="security_condition"`, `condition={"type":"direction","direction":{"value":"request"}}` |
| `assertion_projection` | `value=trigger_condition`, `type_hint="text"`, `modality_hint="descriptive"` |
| `scope_projection` | `unrestricted` |
| `evidence_projection` | 1 条，`locator_type="vuln_case"`，`locator_value={case_id, avd_id, cve, cwe, risk_level, trigger_methods_all}` |
| `emit_cardinality` | `EMIT_ONE`（**理由见 §6.1**） |

**condition 选型理由**：`trigger_condition` 是自由中文文本，无法确定性地拆成
`field`/`numerical`/`state` AST 的 predicate（拆了就是编造）。8 类 AST 里唯一能从现有数据
**无臆测**推出的是 `direction` —— `actor="client"` + `kind="method"` 已经决定了这是客户端
发起的请求方向。保守替代方案是 `{"type":"unknown"}`（CR-5 在抽不到条件时的做法）。
选 `direction=request`：`comparison_policy` 的 `conservative_returns_unknown` 会让任何
无法判定的比较退化为 `unknown`，不会产生假冲突，故此项增强**零风险**。

**实测产出**：`trigger_condition` 非空 ∩ 有 method ∩ scope=seedgen = 5 条种子，
其中 4 条单 method、1 条双 method（`RTSP-001 SETUP+PLAY`）。取 `[0]` 后 → **5 Candidates**
（SETUP ×4、PLAY ×0 —— 见 §6.1）。
被 `trigger_condition` 非空这一条挡掉的：`RTSP-003`（`SETUP+DESCRIBE+PLAY+TEARDOWN`，
condition 为空）。这是 C1「判不出就 emit 0」的直接后果，不是缺陷。

### 3.2 VR-2 `cand.vuln.header_security_condition`

| 字段 | 值 |
|---|---|
| `applicable_protocol_norm_type` | `vuln_seed` |
| `eligibility_predicate` | content 可解析 **且** `scope == "seedgen"` **且** `trigger_field` 非空 **且** 归一化后命中注册 `header.*` subject **且** `trigger_condition` 非空 |
| `fact_key_projection` | `kind="header"`, `actor="client"`, `subject="header.<lower-hyphen>"`, `property="security_condition"`, `condition={"type":"field","field":{"name":...,"predicate":...}}` |
| `assertion_projection` | `value=trigger_condition`, `type_hint="text"`, `modality_hint="descriptive"` |
| `scope_projection` | `unrestricted` |
| `evidence_projection` | 同 VR-1（`locator_type="vuln_case"`） |
| `emit_cardinality` | `EMIT_ONE` |

**field AST 构造**（与 CR-5 `_build_note_condition` 同形，predicate 语义是「该 header 参与触发」，
不编造具体比较值）：

```json
{"type": "field",
 "field": {"name": "authorization",
           "predicate": {"lhs": {"type": "ref", "ref": "authorization"},
                         "op": "eq",
                         "rhs": {"type": "literal", "value": ""}}}}
```

**归一化 + 命中判定（C5 的落点）**：先去掉尾部的 ` header` / ` 头` 字样（实测 `Transport header`），
再转 lower-hyphen，最后查 `subject_registry.initial_subjects.header` ∪ `alias_registry`
（`status == "accepted"`）的 `header.*`。13 条 `trigger_field` 的判定结果：

| `trigger_field` | 归一化 | 注册? | 处置 |
|---|---|---|---|
| `Authorization` ×2 | `authorization` | ✅ `header.authorization` | **emit** |
| `Content-Length` ×1 | `content-length` | ✅ `header.content-length` | 仅在 scope 允许时 emit（实测 scope=`insufficient_source` → **emit 0**） |
| `Transport header` ×1 | `transport` | ✅ `header.transport` | **emit** |
| `Digest` ×2 | `digest` | ❌ 不在 `initial_subjects`，`alias_registry` 也无 `digest` 条目 | emit 0（ontology gap） |
| `nonce` | `nonce` | ❌ 非 header（认证参数） | emit 0 |
| `interleaved` | `interleaved` | ❌ 非 header（URI query 参数） | emit 0 |
| `client_port` | `client_port` | ❌ 非 header（TCP 端口） | emit 0 |
| `授权头` | — | ❌ 中文描述，非 header 名 | emit 0 |
| `序列号` | — | ❌ 中文描述 | emit 0 |
| `传输参数` | — | ❌ 中文描述 | emit 0 |
| `响应` | — | ❌ 中文描述，且指 response 方向非 field | emit 0 |

`Digest` 是**真实的 RTSP 认证头**，只是 `subject_registry` 的 `initial_subjects` 没收录、
`alias_registry` 也没有对应条目。本步**不发明** `header.digest`（那是改冻结 JSON），
按 C5 记入 ontology gap（§5）。

**实测产出**：scope=seedgen ∩ 注册 header ∩ `trigger_condition` 非空 =
`RTSP-002`（`header.transport`）+ `RTSP-035`（`header.authorization`）→ **2 Candidates**。
`RTSP-003`（Authorization）被 `trigger_condition` 空挡掉。

### 3.3 VR-3 `cand.vuln.security_consequence`

| 字段 | 值 |
|---|---|
| `applicable_protocol_norm_type` | `vuln_seed` |
| `eligibility_predicate` | content 可解析 **且** `scope == "seedgen"` **且** 至少能解析出 1 个**锚定 subject**（VR-1 的 method 或 VR-2 的 header，**不要求** `trigger_condition` 非空） |
| `fact_key_projection` | `kind`/`actor`/`subject` 与锚定维度一致，`property="security_consequence"`，`condition={"type":"always"}` |
| `assertion_projection` | `value=` §4 构造的后果文本，`type_hint="text"`，`modality_hint="descriptive"` |
| `scope_projection` | `unrestricted` |
| `evidence_projection` | 同 VR-1 |
| `emit_cardinality` | `EMIT_ONE` |

**为什么 VR-3 不要求 `trigger_condition`**：`security_consequence` 装的是「后果」，
`desc` 37/37 非空，正是后果的天然载体。要求 `trigger_condition` 非空会白白丢掉 37−14 条。

**condition 用 `always`**：后果陈述与触发条件无关（`CR-4` 的 `error_code value_type`
已用 `always` 作先例）。保守替代是 `unknown`；选 `always` 因为「该 subject 存在此后果」
本身就是无条件成立的。

**实测产出**：VR-1 锚点（method 维度，5 个）∪ VR-2 锚点（header 维度，2 个）= 7 个锚点。
`RTSP-002` 同时有两个锚点（`method.SETUP` + `header.transport`），但 VR-3 是 `EMIT_ONE`，
`fact_key_projection` 取 `anchors[0]`（method 优先，与 CR-5 的 method 优先一致），
所以该种子只贡献 `method.SETUP` 一条 → 实测 **7 Candidates = 6 method + 1 header**。

`EMIT_ONE` 下「一个种子最多一条 security_consequence」是 `_apply_rule` 的既有行为
（单 rule × 单 norm 只产出 1 个 Proposal，见 §6.1）。**`trigger_methods_all` 与
`trigger_field` 原文都在 evidence locator 里**，第二个锚点不丢信息、可回溯。

### 3.4 为什么**不**用 `security_boundary`

`property_registry` 的 `security_boundary`：

```
allowed_kinds           = ["header"]          ← 只允许 header 维度
allowed_assertion_types = ["range", "text"]
normalizer              = "numeric_range_v1"
comparator              = "range_relation_v1"
```

37 条 vuln 数据里**没有任何可提取的数值边界**。`trigger_condition` 是自由中文文本，
唯一沾边的是 `RTSP-011`「`Content-Length` 字段为较大整数」—— 没有 `min`/`max`，
而且它的 `scope` 是 `insufficient_source`。要产出 `security_boundary` 就必须从
「较大整数」这种定性描述里编造一个数值区间，那是**发明**，违反 C1。

→ **本步不设计 `security_boundary` 规则。** 理由记录在此。
若将来 KB 里出现结构化边界（如 `{"header":"Content-Length","min":0,"max":2147483647}`），
再补一条规则，届时应同步扩充 `subject_registry` 的 `initial_subjects.header`。

### 3.5 规则集汇总

| rule_id | property | 维度 | 触发字段 | 实测 Candidate 数 |
|---|---|---|---|---|
| `cand.vuln.method_security_condition` | `security_condition` | method | `trigger_methods` ∩ `trigger_condition` | 5 |
| `cand.vuln.header_security_condition` | `security_condition` | header | `trigger_field` ∩ `trigger_condition` | 2 |
| `cand.vuln.security_consequence` | `security_consequence` | method 优先，header 兜底 | 锚点 subject | 7（6 method + 1 header） |
| **合计** | 2 个 property | 2 个维度 | | **14** |

**property 分布**：`security_condition` 7（method 5 + header 2）、`security_consequence` 7
（method 6 + header 1）。
**未使用**：`security_boundary`（§3.4）。**18 个 property 中本步只动 2 个**。


## 4. assertion value 的构造

### 4.1 `security_condition` 的 value = `trigger_condition` 原文

C6 的直接落地：触发条件就是 pre-condition，不掺 `desc`、不掺 CWE、不掺 risk_level。
`type_hint="text"`（`security_condition.allowed_assertion_types` 含 `text`），
`modality_hint="descriptive"`（`MODALITY_DOMAIN` 成员；vuln 观察既非 normative 也非 observed 频次）。

### 4.2 `security_consequence` 的 value = 三段拼接

`property_registry` 对 `security_consequence` 的 `value_schema.description` **明文**写着：

> "Effect of the security issue (e.g. **CWE class, severity**)"

→ **CWE 与 risk_level 由注册表明确认可承载在 `security_consequence` 上，不是发明。**
这直接回答了「severity 无对应 property」的疑问：`security_consequence` 就是它的落点。
（`security_consequence.resolution_required_fields` 只有 `["value"]`，无 `modality`，
所以 modality 缺失不影响 resolution。）

构造：

```
"<desc 全文>"  +  ("| cwe=CWE-617" 若 cwe 非空)  +  ("| risk_level=中危" 若 risk_level 是受控严重度 token)
```

### 4.3 `risk_level` 的受控 token 判定

25/37 的 `risk_level` 是 `(来源,类别)` 溯源标签而非严重度。**只**在值命中下列受控 token
集合时追加该片段，否则**整个片段省略**（C1：识别不出就不写，不把溯源标签冒充 severity）：

```
高危 / 中危 / 低危 / 严重 / 超高危 / 极危 / critical / high / medium / low
```

实测命中：`中危` ×5、`低危` ×7，共 12/37 会在后果文本里带 severity 片段；
另外 25 条不带 severity 片段（但 32 条带 CWE 片段中的大部分）。

**这是本步的设计决定，不是契约明文。** 受控 token 集合硬编码在实现里并在此登记，
将来若要治理，应升格进 `property_registry` 或新建 severity 词表（属改冻结 JSON，需授权）。

### 4.4 `cve` / `avd_id` / `confidence` / `target` / `expected` 的处置

| 字段 | 处置 | 理由 |
|---|---|---|
| `cve`(17) / `avd_id`(37) | **进 evidence locator，不进 assertion** | 它们是**标识符**不是知识。`property_registry` 的 18 个 property 没有任何一个的语义是「CVE 编号」或「AVD 编号」。发明一个 property 违反 C2。 |
| `confidence`(37) | **不进任何 Candidate** | 它是 vuln extractor 对**自己抽取结果**的置信度，不是协议知识。与 `scope` 同属元判定。 |
| `target`(37) | **丢弃** | 全为 `unknown`，无信息量。 |
| `expected`(0) | **丢弃** | 37/37 全空。 |

> 上述三项都**完整保留在 evidence locator 与 `norm.content` 里**，可审计、可回溯，
> 只是不作为 Fact 断言。信息没有丢，只是不进中枢语义层。


## 5. Ontology gap 清单（C5 的可见性出口）

`subject_registry.notes` 原文：`"other_role": "escape hatch only; frequent 'other' indicates ontology gap"`。

本步实测到 9 个 `trigger_field` 值无法落到注册 `header.*` subject：

| 值 | 出现种子 | 判定 | 建议（**均需改冻结 JSON，本步不做**） |
|---|---|---|---|
| `Digest` | RTSP-017 / RTSP-019 | 真实 RTSP 认证头，registry 未收录 | 加进 `subject_registry.initial_subjects.header` |
| `nonce` | RTSP-010 | Digest 认证的 nonce 参数，非 header | 归 `other.nonce`，但 `security_condition` 不允许 `other` kind |
| `interleaved` | RTSP-005 | RTSP URI query 参数 | 同上 |
| `client_port` | RTSP-037 | TCP 端口，非 header | 同上 |
| `授权头` | RTSP-004 | 中文描述「授权头」= `Authorization` | 归一化后与 `header.authorization` 同义，**建议进 `alias_registry`** |
| `序列号` | RTSP-018 | 中文描述 | 无对应 header |
| `传输参数` | RTSP-025 | 中文描述 ≈ `header.transport` | 同 `授权头`，建议进 `alias_registry` |
| `响应` | RTSP-036 | 指 response 方向，非 field | 无对应 header |
| （另 `Transport header`） | RTSP-002 | 归一化**成功**（剥 ` header`） | 已 emit，仅记录归一化规则来源 |

实现里提供 `unresolved_trigger_fields(norms)` 辅助函数，让这张清单可被测试与 audit 直接消费，
避免 gap 静默存在。


## 6. 两处主动的实现取舍（写明理由，便于复核）

### 6.1 多 method 只取 `[0]`，不改 `_apply_rule`

**实测**：`core/fused/pipeline/candidateization.py::_apply_rule` 对「单 rule × 单 norm」
只产出 **1 个** `CandidateProposal`（`fact_key_projection` 返回单个 `RawFactKeyCandidate`）。
即 `EMIT_MANY` 目前**只影响 evidence 条数，不产生 N 个 Candidate**。
契约 §2.2 写的是「每条 eligible rule 产生 **0..N** CandidateProposal」，所以这是实现未跟上契约。

`trigger_methods` 用 `+` 分隔，`RTSP-001` 是 `SETUP+PLAY`。要产出 2 个 Candidate 必须改
`_apply_rule`（让 projection 可返回序列），那是**共享模块**的语义变更。

**本步选择不改**：受 `trigger_condition` 非空这一条约束后，5 条存活种子里只有 `RTSP-001`
是多 method，取 `[0]` 只损失 **1 个** Candidate（`method.PLAY`）。
代价与收益不成比例，且 CR-5 已有 `trigger_methods[0]` 先例，保持一致。
**完整方法列表写进 evidence locator 的 `trigger_methods_all`**，信息不丢、可审计。

**记为待办**：若将来 vuln 源的多 method 种子变多，或需要完整扇出，
应单独一步做 `_apply_rule` 的 fan-out（向后兼容：projection 返回单对象时行为完全不变），
并用全量 pytest 证明 CR-1..CR-5 行为零变化。

### 6.2 `scope` 门禁写在 `eligibility_predicate` 里

`eligibility_predicate` 的语义就是「这条 rule 适不适用于这条 norm」。
`scope` 是 vuln 源自带的可用性判定，属于 eligibility 的天然组成部分。
门禁不满足 → emit 0（契约 §2.3 正常路径），**不是** violation。


## 7. 预期产出（供实现后核对）

| 产物 | 预期值 | 实测值 | 依据 |
|---|---|---|---|
| vuln Candidates | 14 | **14** ✅ | §3.5 |
| ├ `security_condition` / method 维度 | 5 | **5** ✅ | VR-1 |
| ├ `security_condition` / header 维度 | 2 | **2** ✅ | VR-2 |
| └ `security_consequence` | 7（6 method + 1 header） | **7** ✅ | VR-3 |
| **Facts（按 fact_key 折叠后）** | — | **5** | §7.1 |
| emit 0 的 vuln_seed | 23 | **23** ✅ | 37 − 14 |
| 落盘 `derived/per_source/vuln/` | 13 文件（对齐 rfc / expert_note） | 待 §四 实测 | `fused_canonical_spec.md` §3.2 冻结文件集 |

**实现后实测（Step 4.8g，已核对一致）**：

```
CANDIDATES: 14
  security_condition  / method  : 5
  security_condition  / header  : 2
  security_consequence/ method  : 6
  security_consequence/ header  : 1
```

逐条落点：`RTSP-001`(2) `RTSP-002`(3) `RTSP-003`(1) `RTSP-005`(2) `RTSP-016`(2)
`RTSP-035`(2) `RTSP-037`(2) = 14。

**ontology gap 实测 8 个值**（`unresolved_trigger_fields` 直接吐出）：

| 原始值 | 归一化 | 出现种子 |
|---|---|---|
| `Digest` | `digest` | RTSP-017, RTSP-019 |
| `nonce` | `nonce` | RTSP-010 |
| `interleaved` | `interleaved` | RTSP-005 |
| `client_port` | `client-port` | RTSP-037 |
| `授权头` | `授权头` | RTSP-004 |
| `序列号` | `序列号` | RTSP-018 |
| `传输参数` | `传输参数` | RTSP-025 |
| `响应` | `响应` | RTSP-036 |

### 7.1 ⚠ 已知状态：`claim_class` 门禁让 5 个 Fact 停在 unresolved

**实测（用真实 registry 逻辑跑完整 build，不是推断）**：

```
document=kb/vuln/RTSP-001.json  source_type=['vuln']
   HIT cc.fallback.unknown   family=fallback  -> unknown
```

`core/fused/hub/registry/claim_classification_rules.json` 的 8 条 rule 里
**没有任何一条覆盖 `vuln` 源**（`cc.security_notes.security_hint` 的 hint 是
`kb/expert_note/security_notes.json`；`cc.expert_note.default_interpretive` 的 hint 是
`kb/expert_note/`；`cc.rfc.*` 按 `source_type == "rfc"`；`cc.traffic.observational` 按
`source_type ∈ {traffic_pcap, traffic_raw}`；`cc.implementation.*` 按 `source_type == "source"`）。

于是全部 14 个 Claim 都是 `claim_class=unknown`。而 `docs/设计/顶层设计/规范化序列化规范.md`
**条款 11**：

> `claim_class` 为 `unknown` 的 claim **不得进入 Phase A eligible set**。

`phase_a._eligible_claims` 忠实执行了这条（且显式排除 `unknown`，注释写明
「全部 property 的 eligible_claim_classes 均不含 unknown，此处显式排除以免未来 registry
加入 unknown 时回归」）。后果走契约 §5.2 第 4 步「无 eligible candidate → unresolved」：

```
Candidates : 14
Facts      : 5      ← 全部 status=unresolved  reason=insufficient_evidence
Claims     : 14     ← 全部 claim_class=unknown
lineage    : 14
audits     : 2
entities   : 1      relations: 0
```

**14 → 5 的折叠**（契约 §1.11「同源同 assertion 聚合」+ fact_key 唯一）：

| fact_key | 折叠的 Candidate 数 |
|---|---|
| `method.SETUP` × `security_condition` | 5（RTSP-001/002/005/016/037） |
| `method.SETUP` × `security_consequence` | 6（上列 5 条 + RTSP-003） |
| `header.authorization` × `security_condition` | 1（RTSP-035） |
| `header.authorization` × `security_consequence` | 1（RTSP-035） |
| `header.transport` × `security_condition` | 1（RTSP-002） |

**关键澄清 —— 不是「0 Fact」**：Fact **照样落盘**，14 个 Claim 全部挂在 Fact 上，
lineage / audit 完整，meta 正常写。丢的只是 **resolved assertion**：这 5 个 Fact 永远停在
`unresolved(insufficient_evidence)`，即「知道有这个 subject 的这条安全陈述，但无法判定其
resolution」。这与「知识没进中枢」有本质区别。

**要修需要改 `core/fused/hub/registry/claim_classification_rules.json`（冻结 JSON），
且 `claim_class` 取值有两种都合理的答案**：

| 候选 | `security_condition` 优先级 | 后果 | 风险 |
|---|---|---|---|
| `security` | `[security, normative, observational]` | vuln claim **压过** RFC 的 normative claim | `method.SETUP` 上 vuln 的「多个 SETUP 和 PLAY」会盖掉 RFC 的 MUST —— 语义上错，RFC 才是协议真相 |
| `observational` | 第 3 位 | normative 保持最高优先级，vuln 只作低 tier 补全 | 保守；但 `security_consequence` 的 `resolution_required_fields` 只有 `["value"]`，无 modality，tier 影响小 |
| `interpretive` | 不在 `eligible_claim_classes` 内 | 仍会被排除 | 不可行 |

→ **属真决策点**（改冻结 JSON + 两种设计都合理），本步停下等裁定。
裁定后的预期效果：5 个 Fact 从 `unresolved(insufficient_evidence)` 转为 `resolved`，
而不是从 0 变成 N。`tests/extraction/test_vuln_rules.py::TestVulnSourceEndToEnd`
里对该状态有精确断言，裁定生效时会失败并提醒更新。

### 7.2 附带发现：vuln 的 evidence document 无法解析到物理文件

`norm.source` 写的是 `vuln/RTSP-001.json`，但物理文件实际在 **`kb/历史漏洞/RTSP-001.json`**
（37 个文件）。`build_inputs.resolve_source_file` 只会试 `kb/vuln/...` 与 `kb/spec/vuln/...`，
两者都不存在 → 返回 `None`。

后果（三条，均按契约的既定降级路径处理，不是错误）：

1. `EvidenceCandidate.document` = `vuln/RTSP-001.json`，**无 `kb/` 前缀、无 `#`**。
   将来若加 `file_or_path_hint`，hint 必须写 `vuln/` 而不是 `kb/vuln/`。
2. `content_fingerprint` 走**确定性兜底**（同组全部 `norm.content` 排序拼接的 sha256），
   而不是物理文件 bytes 的 sha256。这是 `build_inputs.py` 文档字符串里写明的正确兜底。
3. 即便按 §7.1 加了 hint，也必须匹配 `vuln/`。

**本步不修**，三个理由：(a) 修 `norm.source` 要写 `（已移除）rtsp/norms/norms.jsonl`
（derived 产物，且属 vuln extractor 的输出）；(b) 扩 `resolve_source_file` 的探测路径会
**同时影响 rfc 与 expert_note 的 document 与 content_fingerprint** → 违反源隔离第十一章的
跨源禁令；(c) §1.10 Input Closure 的 content fingerprint 本就允许确定性兜底。
→ 列入未决项上报。


## 8. 与既有规则集的边界

| 维度 | CR-1..CR-5（4.8b/4.8e） | 本步 VR-1..VR-3 |
|---|---|---|
| 源 | rfc / traffic / expert_note | vuln |
| `applicable_protocol_norm_type` | method / message / field / error_code / security_note | `vuln_seed` |
| property | existence / occurrence / value_type / security_condition | security_condition / security_consequence |
| claim 会否命中既有 registry rule | ✅ rfc / traffic / expert_note 各有对应 rule | ❌ 见 §7.1 |
| 接线 | 已在 `CANDIDATEIZATION_RULES` | 追加到同一 tuple 末尾（保持 frozen order） |

`security_condition` property 上 CR-5 与 VR-1/VR-2 会产生**同名 property 的不同 fact_key**
（CR-5 锚 expert_note 的 method/header，VR 锚 vuln 触发的同一 method/header），
因此二者会在 Phase A 的同一 resolution domain 里相遇 —— 这正是 `peer_conflict` /
`match` 机制存在的意义。**不得为规避冲突而编造 condition 编码**（D13 先例）。
