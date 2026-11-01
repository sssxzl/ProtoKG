# 五源单源抽取 → Hub 全链路审查

**日期**：2026-10-08　**方法**：逐条 norm 实测 `_apply_rule`，不按 kind 推断
**复现**：`python local/_probe_five_sources.py` / `local/_probe_unconsumed.py`

> ⚠ 审查口径：**单源阶段**。每个源独立回答「我抽出了什么、有多少进了 Hub」，
> **不做任何跨源对比**。融合是后续阶段的事。

---

## 1. 总览

| 源 | ① 抽取 norm | ② 被 CR 消费 | ③ per_source Facts | claim_class |
|---|---|---|---|---|
| rfc | 11 | 11 (100%) | 11 | `normative` × 11 |
| expert_note | 89 | 76 (85.4%) | 99 | `interpretive` × 93、`security` × 7 |
| vuln | 37 | 7 (18.9%) | 5 | `observational` × 14 |
| traffic | 40998 | 27000 (65.9%) | 14 | `observational` × 34000 |
| source | 10 | 10 (100%) | 10 | `implementation` × 10 |

**修复后（2026-10-08，CR-8/CR-9 落地）**：`fused` 131 Facts / 81 entities /
1462 relations / 63 audits / 34135 lineage，
`build_fingerprint = sha256:3a244700709731ca531…`
（此前 106 Facts / 59 entities / 516 relations / 62 audits / 34110 lineage）。

各源在 fused Hub 中的 claim_class 分布：

| source_type | claim_class |
|---|---|
| rfc | `normative` × 11 |
| expert_note | `interpretive` × 68、`security` × 7 |
| vuln | `observational` × 14 |
| traffic_pcap | `observational` × 12000 |
| traffic_raw | `observational` × 22000 |
| source | `implementation` × 10 |

---

## 2. 未被消费的明细（逐 kind + extraction_method）

### expert_note：38 / 89 未消费

| kind | 条数 | 是否在契约 `NORM_KINDS` | 性质 |
|---|---|---|---|
| `field_constraint` | 18 | ❌ 不在 | 契约外 kind |
| `value_pool` | 7 | ❌ 不在 | 契约外 kind |
| `body_format` | 5 | ❌ 不在 | 契约外 kind |
| `sample` | 3 | ❌ 不在 | 契约外 kind |
| `session_rule` | 1 | ❌ 不在 | 契约外 kind |
| `timing` | 1 | ❌ 不在 | 契约外 kind |
| **`constraint`** | **3** | ✅ **在** | **★ 真缺口** |

★ **`constraint` 3 条是真缺口** —— 它们在契约的 `NORM_KINDS` 内、内容是高价值
协议约束，但 SR 规则（`cand.expert.state_existence` /
`cand.expert.transition_target_state`）只认 state_machine 格式，故 emit 0：

| norm_id | 内容 | 价值 |
|---|---|---|
| `constraint.required_headers` | `{"rules":{"SETUP":["CSeq","Transport"],"PLAY":["CSeq","Session"],…}}` | **每方法必需头** |
| `constraint.methods` | `{"methods":[{"name":"OPTIONS","type":"request","state_changing":false},…]}` | 方法表 |
| `constraint.header_naming` | `{"case_insensitive_full":["URL","UA","IP"],"standard_set":[…]}` | 大小写规则 |

**⟹ 用户要的「协议约束」目前一条都没进 Hub。** 这不是契约限制，是规则判据
只覆盖了 state_machine 一种 content 形态。

其余 35 条的 kind 不在契约 `NORM_KINDS`（protocol/actor/message/field/
state_machine/constraint/outcome 七值）内，属**契约外 kind**。它们由 6 个
expert_note extractor 产出（`field_constraints` / `value_pool` /
`body_format` / `samples` / `session_rules` / `timing`），但契约从未为它们
定义 `fact_key` 槽位。

### vuln：30 / 37 未消费

实测 content（`vuln.RTSP-004`）：

    [vuln] case_id=RTSP-004 avd_id=AVD-2023-51626 cve= cwe=CWE-787
    risk_level=(AVD_标签_NVD,操作系统类) scope=seedgen confidence=medium
    target=unknown expected= trigger_methods= trigger_field= | ...

**根因（实测确认）**：VR-1/VR-2/VR-3 三条规则都依赖 `trigger_method` /
`trigger_field`，而这批 vuln 的这两个字段**确实大面积为空**（`trigger_methods=`
后直接是 `trigger_field=`）。

但**并非全无信息**：`avd_id`（AVD-2023-51626）、`cwe`（CWE-787）都有值，
`risk_level` 也有。另有一部分 `scope=not_rtsp_protocol`（如 RTSP-008）属**正确排除**。

⟹ 属「规则只用了一半可用字段」，不是契约边界。

### traffic：13998 / 40998 未消费

| kind / 形态 | 条数 | 性质 |
|---|---|---|
| `state_machine`（4 个 producer） | 5000 | 契约边界（序列无槽位，见 design §8.3） |
| `outcome`（status 分布） | 2000 | 契约边界（分布需 `observation_scope`） |
| `actor` / `protocol.transport` | 3998 | 非协议问题（部署画像） |
| **`field` = `unique URLs=…`** | **3000** | **契约边界：URL 不是 header**（见 design §8.3.1） |
| 其余（message 全消费 / pcap field 全消费 / session_log public_methods 全消费） | — | ✅ |

### rfc / source：100%，无未消费

---

## 3. 缺口的处理结论

### 缺口① `constraint`（expert_note）—— **已修**

3 条 `kind="constraint"` 的 norm 在契约 `NORM_KINDS` 内、内容是高价值协议
约束，却因 SR 规则只认 state_machine 一种 content 形态而 emit 0。
**用户要的「协议约束」此前一条都没进 Hub。**

新增两条规则：

| 规则 | 消费字段 | 映射到 | 产出 |
|---|---|---|---|
| CR-8 `cand.expert.header_case_insensitivity.v1` | `header_naming.case_insensitive_full` | `case_sensitivity`（kind=header, bool）—— **契约原生匹配** | 3 Facts |
| CR-9 `cand.expert.required_header.v1` | `required_headers.rules` | `relation_to_other_field`（kind=method, relation） | 22 Facts |

**★ CR-9 的 subject 必须是复合名 `<METHOD>.<HEADER>`** —— 这是实测逼出来的：

初版让 `subject=<METHOD>`，期望同一方法的多个必需 header 聚合成
「1 Fact N Claims」。端到端跑出：

    relation_to_other_field  11 个 Fact
      resolution: {'resolved': 1, 'unresolved': 10}, reason='peer_conflict'

只有 1 个必需头的 `OPTIONS` 恰好 resolved（因仅 1 个 claim）——**这恰好反证
问题出在「多 claim 撞同一 fact_key」，而非 relation 类型不被 resolver 支持**。
一个 Fact 的 assertion 是**单值**，装不下「需要 CSeq 且需要 Accept」。

改复合 subject 后：**22/22 全部 resolved**。每个 (方法, header) 对独立成
Fact、各挂 1 个 claim，既保住 method 限定又可 resolve。

**刻意不产的部分**（宁可少产不硬塞）：
- `header_naming.standard_set` / `special_map` / `split_token`
  —— 集合归类不是协议事实；拼写映射规则属 `subject_registry` 职责
- `constraint.methods` —— `type`(request/response) 在契约里是 **condition**
  的 direction 类而非 property；`state_changing` 需 state 名才能表达

### 缺口② vuln 30 条 —— **不改代码**，属契约边界

⚠ **初判「规则只用了一半字段」是错的**。探针修正后逐条判定：

| 类别 | 条数 | 判定 |
|---|---|---|
| OK | 7 | 正常产出 |
| **A** | **21** | `scope ≠ seedgen`（`not_rtsp_protocol` 12 / `insufficient_source` 7 / `not_rtsp_client_side` 1 / `not_trigger_vulnerability` 1）⟹ **正确排除**，非缺陷 |
| **B** | **0** | **零判据问题** |
| C | 9 | `scope=seedgen` 但 `trigger_methods` 空 ⟹ 无法构造合法 subject |

**没有任何一条是规则判据过严。** VR-1 的设计
（`_resolve_method(...) is not None`，拿不到 method 就拒绝发，C6）
已经很严密，与 CR-8/CR-9 是同一原则：判不出就 emit 0，不臆造 subject。

那 9 条 C 类里 5 条 `trigger_field` 反有值（`授权头`/`nonce`/`Digest`×3）
——「哪个字段有问题」确定，缺的是「哪个方法触发」，属**数据缺失**，
代码解决不了。**不为了多收 9 条而放宽判据。**

### 确属契约边界（不硬塞）

traffic 13998 条（见 design §8.3 / §8.3.1）、expert_note 35 条契约外 kind
（`field_constraint` / `value_pool` / `body_format` / `sample` /
`session_rule` / `timing` —— 都不在契约 `NORM_KINDS` 七值内）。

---

## 4. 审查结论

**达标**：rfc（100%）、source（100%，本轮从 0 打通）。

**已修缺口**：expert_note 的 `constraint` 3 条 → 新增 CR-8/CR-9，
产出 25 个 Fact 且全部 resolved。

**剩余非消费项全部有据可查**：契约边界（A/C 类）或刻意留空（design §8）。

⚠ **另记一个未解决的一致性问题**：`subject_registry.json` 规定 header 的
规范拼写是**小写连字符**（`cseq`、`content-length`），而 Hub 现状是
`CSeq`、`Authorization`、`authorization` **同时存在**（即 §9 #21 记录的大小写
歧义）。CR-8/CR-9 沿用 kb 原拼写以免新增变体，但**未解决根因**。

---

## 5. 本轮已修（source 源）

| 步骤 | 内容 | 实测效果 |
|---|---|---|
| CR-7 | `cand.source.method_definition.v1`，eligibility **不依赖 RFC modality** | source 首次进 Hub（0 → 1 Fact） |
| Step 2 | 移除 `HUB_FACT_METHODS = {"REGISTER"}` 闸门（**理由本身是跨源判断**） | 1 → 10 norm / 1 → 10 Facts |
| Step 3 | `evidence_context` 派生通道（`_EVIDENCE_CONTEXT_BY_LOCATOR_TYPE`） | claim_class `unknown` → `implementation` ×10，`needs_review` 消失 |

---

## 6. 附：一条旧测试曾编码跨源原则（已改）

`tests/source_hub/test_source_extractor.py` 原有
`test_rfc_methods_not_duplicated`，docstring 为
「§1-1：RFC 侧已有的方法不重复产 Hub fact（只作 provenance）」，
断言 `RTSPServer.cpp` 产出 **0 条**。

Step 2 移除闸门后该测试失败（实得 9 条）。经查，该测试编码的正是
**「与 RFC 侧比对」这一跨源判断**，与单源原则冲突 ⟹ 改测试而非回退代码：

| 旧测试 | 新测试 |
|---|---|
| `test_rfc_methods_not_duplicated`（断言 0 条） | `test_all_server_definitions_produced`（断言 9 个方法全产出） |
| `test_only_register_produced` | `test_register_file_produces_register` |
| —（新增） | `test_files_without_server_definitions_produce_nothing`：无 `handleCmd_` 定义的文件仍产 0 条，证明过滤依据是**有无服务端定义**而非方法名白名单 |