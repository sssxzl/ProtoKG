# Traffic Lane A Provenance Interface

> 状态：**Final Frozen**（阶段 4，2026-10-04；依 D14–D19 填实）
> 上游：`docs/设计/知识源层/流量源/traffic源规则集设计.md` §4.8
> 　　　`docs/设计/知识源层/流量源/traffic源观测独立性设计.md`（Final Frozen）
> 　　　`docs/设计/顶层与契约/规范化序列化规范.md`
> 　　　`docs/设计/顶层与契约/规范化序列化规范.md`
> 本文件为 Lane A → Hub provenance 接口设计真源。
> 本文件为 standalone 设计真源。

---

## 0. 范围

### 0.1 本设计要解决什么

定义 Lane A 的 StructuralObservation 如何以 **non-voting provenance** 形式附着到 existing Hub protocol Fact。

### 0.2 不解决什么

- 不定义 Lane A 结构抽取（见 `rule_set_design.md`）
- 不定义 D9 semantic contract
- 不引入 Hub Candidate / Claim / Fact（Lane A 不 emit）
- 不修改 Hub Storage Model 现有定义

### 0.3 前置已冻结

| 项 | 来源 |
|---|---|
| Lane A provenance-only invariant | `rule_set_design.md` §4.8 |
| Lane A 输出形态：StructuralObservation + Provenance | 同上 §4.8.2 |
| Evidence 非独立顶层对象 | `fused_canonical_spec.md` |
| Phase A Resolution 不可污染 | `rule_set_design.md` §4.8 |

---

## 1. 硬边界

1. Lane A observation 不得参与 Phase A Resolution
2. Lane A observation 不得改变 canonical assertion
3. Lane A 不得 emit Evidence DTO
4. 本接口不得引入新的 Fact identity
5. 本接口不得反向修改 Hub Storage Model

---

## 2. StructuralObservation 语义

> **状态：Final Frozen**（2026-10-04；原 Frozen Candidate，依 ERRATA-2 转正。
> 字段集经 25000 条 observation 实测验证）

### 2.1 什么是一个 StructuralObservation

**一个 StructuralObservation 是一条 Lane A 观察，及其与一条既有 Hub
Fact 的非投票关系。它不是 Hub 对象。**

按 D17，本接口**不向 Hub 写入任何东西**。Observation 是 Lane A 侧
记录，Hub 侧零改动。

```
StructuralObservation          (Lane A 侧记录，不落 Hub)
  ├─ observation_id            o1_<hash>      本接口内唯一
  ├─ source_unit                500 effective 中的哪一个
  ├─ nominal_unit               1000 nominal 中的哪一个
  ├─ observed                   观察到什么（method token / header name /
  │                             status / URI / 出现与否）
  ├─ observation_kind           观察的类型（见 2.2）
  ├─ target_fact_id             f1_<hash>，指向既有 Hub Fact
  ├─ relation                   见 §4 的 CORROBORATION_RELATION_DOMAIN
  └─ anchor                     (capture_unit, capture_frame) 区间，
                                来自 rule_set §4.6 P6
```

**按 D15，observation 不携带 property。** property 语义由 target
fact 自己的 fact_key 表达。这样 observation 与 fact 彻底解耦，也避免
在 Hub 词表里塞入单客户条目。

### 2.2 observation_kind

**判定：开放字符串，不设闭合枚举。**

依据 D14/D15：设闭合枚举需要在 models.py 增 *_DOMAIN 值，而 D14
判 Q3=YES（新增 domain 值触发 Schema Version Upgrade）。开放字符串
零触发。

代价：observation_kind 无机器校验，拼写错误不会被拦。接受该代价，
并在 Step 5 的实现立项中提出「实现期加一个非冻结的取值检查」。

### 2.3 message_ref

**判定：区间，不只是单 frame。**

依据：rule_set §4.5 P8 限制 5 明写「跨 TCP 段的 Message 在 corpus 中
不存在——splitter 对跨段 Message 的行为未经验证」。既然未验证，契约
就不能假设一条 message 恒等于一个 frame。用区间是唯一不撒谎的写法。

### 2.4 一个 observation 挂几个 target

**判定：恰好一个。**

依据 D16：relation 词表是四条离散值而非列表；若允许多 target，
`contradicts` 与 `corroborates` 会在同一 observation 上同时出现，
第四值 no_target 也失去意义。恰好一个让 §4 的三值+no_target 构成
完备划分。

需要「一条观察对多条 fact」的场景，由**多条 observation** 表达。

---

## 3. Alignment Target

> **状态：Final Frozen**（2026-10-04；原 Frozen Candidate，依 ERRATA-2 转正。
> 含新增 §3.5「组粒度」；500 units 实测 CSeq/Session/Transport 各 1 候选）

### 3.1 什么可以对齐

**Alignment Target = 一条既有 Hub Fact，其 evidence 的 source_type 属于
rfc / expert_note / vuln 三者。**

`traffic_pcap` / `traffic_raw` **不是 target 池**——它们是
provenance 分类域的保留值（models.py L67 注释原文：「这是 provenance
classification domain，**不是**协议语义 identity domain」），标记的是
**观察本身的来源**，不是被对齐的协议事实。

### 3.2 各组的 target 现状

| 组 | 候选 fact 形态 | 状态 |
|---|---|---|
| G1 Message Reconstruction | `existence` 等 | observation 本身，无独立 target 需求 |
| G2 CSeq Pairing | `header` / `CSeq` / `security_condition` | 部分：本语料无法观察 replay |
| G3 Method / Status / URI | `method` / `existence` | 有 target（同 element 的 existence fact） |
| G4 Header presence / value | 7 条 `header` fact | 部分：property 不匹配 |
| G5 Message Ordering | 无 | **NO_TARGET_PENDING_EXTRACTION**（见 3.4） |
| G6 Transaction Structure | 无 | **OUT_OF_SCOPE**（D18） |
| G7 Packet-Role | 无 | **NO_TARGET_PENDING_EXTRACTION**（见 3.4） |
| G8 Session / Transport | `header` / `Session`、`transport` | 弱：两条都退化于本语料 |

### 3.3 关键约束：observed_* 不是 Lane A 的 target 池

按 D19，`observed_*`（5 个）全部是 D9 §6 的 population-level
measurement 词表。Lane A 依 rule_set §1.2 不经 §6.3 / §6.4，因此
**G5 想表达的顺序、G7 想表达的角色关系，没有可对齐的 property**。

这不是缺陷，是分层结果：instance-level 观察在 Hub 里**没有**
property 词汇，而按 D15 我们也不新增一个。

### 3.4 无 target 的三组

- **G6** 按 D18 移出，category = `OUT_OF_SCOPE`
- **G5 / G7** 标 `NO_TARGET_PENDING_EXTRACTION`：其 extraction
  coverage 缺口是上游议题（Hub Contract 侧），不是 Lane A 可解的。
  在缺口修复前，它们的 observation 记录为 `relation = no_target`。

### 3.5 组粒度：对齐单元是 (group, header)

> **2026-10-04 裁定追加。** §2.4 与 §4.11 F 曾存在一处张力，
> 本节给出唯一自洽解。**§2.4 与 §3.4 原文均不改写。**

**问题**：§4.11 F 给 G2 / G4 / G8 列了 target（1 / 7 / 2 条），
按 §4.11 G 的诚实预期它们的 relation 多为 `insufficient` /
`corroborates`。但 §2.4 要求 target_fact_id 非空，
而 §3.4 的 `no_target` 定义是「该组**无候选 fact**」。
若按「整组」判定，一个组内同时存在「有候选」与「无候选」的 header 时，
无法为每条 observation 同时满足两条约束。

**解**：把 §4.11 F 与 §3.4 里的「组」精确到 **(group, header)** 级。

| 情形 | relation | target_fact_id | 依据 |
|---|---|---|---|
| 该 header 在 Hub 有 1 条对应 fact | `insufficient` / `corroborates` / `contradicts` | 非空 | §2.4 |
| 该 header 在 Hub **无**对应 fact | `no_target` | `null` | §3.4 |

这样 §2.4「恰好一个」与 §3.4「无候选」**同时成立**，无需放宽任何条款。

**实测印证**（2026-10-04，500 units）：

| header | Hub 候选 | relation |
|---|---|---|
| `CSeq` | 1（`f1_7c7ed1518df`） | `insufficient` + target |
| `Session` | 1（`f1_7ddfe7b3efd`） | `insufficient` + target |
| `Transport` | 1（`f1_a80c59c703f`） | `insufficient` + target |
| `Date` / `User-Agent` / `Accept` / `Range` / `Content-*` / `Public` / `RTP-Info` | 0 | `no_target` + null |

合计 **11000 条带 target / 14000 条 no_target**。

**§9 #21 在本粒度下的处理**：`authorization` 在 Hub 有 **3 条** fact_key
（大写 `Authorization` 1 条 + 小写 `authorization` 2 条，后者 property 各异）。
§2.4 已给处方——「需要『一条观察对多条 fact』的场景，由**多条 observation**
表达」。

⟹ 发 **3 条** observation，各挂一个 target，`relation` 一律 `insufficient`
（无法确定哪个是真 target）、`token` 取 `NEEDS_REVIEW`。
**不给一条 observation 挂多个 target，也不选边。**

**本粒度的代价（明确记录）**：同一 `(group, header)` 在 Hub 无候选时，
不能退而用「同 kind 的其他 fact」当 target —— 那等于放宽 §2.4 的对齐语义。
本接口**不做**这种退让，`no_target` 就是诚实的答案。

---

## 4. Alignment Semantics

> **状态：Final Frozen**（2026-10-04；原 Frozen Candidate，依 ERRATA-2 转正。
> 四值词表经 25000 条记录验证；D16 守住：未写入 core/fused/hub/models.py）

### 4.1 词表

```
CORROBORATION_RELATION_DOMAIN = {
    corroborates,
    contradicts,
    insufficient,
    no_target,
}
```

**该 domain 声明在本文件内，不写入 `core/fused/hub/models.py`。**
理由见 D16：Lane A 的 relation 约束的是 Lane A 自己的记录，不落在
任何 Hub 数据类的合法值集合上，因此既不扩 `ALIGNMENT_RELATION_DOMAIN`
（扩即触发，Q3=YES）也不新增 Hub frozenset（新增即触发）。

### 4.2 逐值语义

| 值 | 含义 | 判据 |
|---|---|---|
| `corroborates` | 观察与 target 的既有断言一致 | 观察值与 fact 的 assertion 值语义相容 |
| `contradicts` | 观察与 target 的既有断言冲突 | 观察值与 assertion 值语义不相容 |
| `insufficient` | 证据不足以判定 | 观察存在但不覆盖该断言的判据域 |
| `no_target` | 无可对齐的 target | 该组无候选 fact（见 §3.4） |

### 4.3 为何不用 `supports`

`supports` 在 Phase B 有确定语义：claim 与**同一条 fact 的 resolved
assertion** 的关系，隐含「参与过 resolution」。Lane A 的 relation
主语是 observation，客体是一条**从未进入 Phase A 候选集**的既有
fact，且**明确不参与** resolution。两者 epistemic layer 不同。

复用同名词会让后续读数据的人把非投票关系看成投票关系——这正是
rule_set §4.8 要防的失效模式。

### 4.4 no_target 为何是第四值而不是「不产生记录」

若「无 target」用不产生记录表达，则「已考虑并确认无目标」与
「从未被考虑」在数据上**不可区分**。第四值让前者可观测。

这是本接口唯一依赖 cardinality 之外的一个值，代价是 relation 域从
三值变四值。

---

## 5. Provenance Attachment Mechanism

> **状态：Final Frozen**（2026-10-04；原 Frozen Candidate，依 ERRATA-1 + ERRATA-3 转正）
> **转正依据**：§5.4「Lane A 侧独立记录」已由 `core/lane_a/attachment.py`
> 实现并验证——25000 条 observation 产出 **11000** 条 attachment，
> 落点 `derived/lane_a/provenance/`，运行后 `derived/hub/` 13 文件
> 逐字节不变（§5.4「Hub 侧零改动」得证）。
> **注意**：本节 §5.5 的「强制（留给实现）」主张已被 ERRATA-1 推翻，
> 转正的是 §5.1–§5.4 的判定本身，**不是** §5.5。

### 5.1 判定

**观察对象不落 Hub。Hub 侧零改动。U12 = 不需要新增任何冻结结构。
U13 = 不触发 Schema Version Upgrade。**

### 5.2 为什么 P6 的默认选项（乙）不可行

P6 默认「乙：扩展 Evidence 允许非 Claim 宿主」。实测否证：

- `core/fused/runtime/writer_impl.py:134` 实测
  `claim["evidence"] = sorted(claim["evidence"], ...)`——
  **Evidence 只在 claim 内写出**。让它出现在 claim 之外必须改
  writer 的存储契约。
- Canonical Serialization 与逻辑存储布局属 L1280 第一部分范围
  → 触发 Schema Version Upgrade（Q3 = YES，D14）。
- 阶段 2.2 阶段 C0 T5 曾判乙为「类层面零字段改动」——该判断在
  **类层面正确、在存储层面不完整**。Evidence 类确实没有宿主指针，
  但 writer 从不把它写在 claim 之外。此处更正。

### 5.3 为什么 DerivedFrom 模式也只拿到一半

按 P6 的 blocking read，DerivedFrom 是 Hub 里唯一的「聚合 provenance
引用集」先例（§7.7 图节点的 provenance 聚合）。但：

- `DerivedFrom{fact_ids, claim_ids}` **没有 relation 位**。
- 给它加字段属于改第一部分模型（L1280 明列「Graph 与 Profile 与
  Audit 模型」）→ 同样触发。
- `GraphEntity{entity_id, entity_type, canonical_name,
  derived_from, flags}` 同样在第一部分范围内。

故 DerivedFrom 模式可复用其**形状**（一个 observation 挂若干引用
id），不能复用其**落点**。

### 5.4 落点

**Lane A 侧独立记录。** Hub 侧什么都不写。

由此产生两个 Hub 之外的缺口，本节明确承担：

1. **读出口**：observation 不在 Hub 内，Hub 的任何消费者都读不到它。
   Lane A 需要自己的读出口（本文件即为其规范）。
2. **格式校验**：Hub validator 不覆盖本接口的记录。

### 5.5 non-voting 隔离：当前是结构性的，强制留给实现

- **当前（结构性，零成本）**：`writer_impl` 只在 claim 内写 Evidence；
  `phase_a.py` 只遍历 `claims`（L296 / L312）。一个不落 Hub 的
  observation 因此**在构造上**无法被 Phase A 或 Phase B 触达。
- **强制（留给实现）**：应新增一条 validator invariant
  「source_type ∈ {traffic_pcap, traffic_raw} 的 Evidence 不得出现在
  任何 Claim.evidence 内」。其形状与既有 Invariant 18 相同
  （validation.py:798 遍历 claim 内 evidence 并比对 source_type）。
  实现需改 `core/fused/hub/validation.py`，**本批次禁止修改 core/**，
  故只在设计层写明，留 Step 5 立项。

**这不是「靠遗忘获得的隔离」**：遗忘只保证当前不可达，validator
invariant 才保证将来不可达。两者都要，第 5.5 节同时记下。

> ⚠ **本节已被勘误推翻（2026-10-04，见文末 ERRATA-1）。**
> 上面的「强制（留给实现）」及其论证**不成立**，不得据以实施。

---

## 6. 与 Phase A / Phase B 的关系

> **状态：Final Frozen**（2026-10-04；原 Frozen Candidate，依 ERRATA-2 + 步骤 C 转正）
> **转正依据**：§6.1 三条承诺已由实测验证——阶段 II/III 执行后
> `derived/hub/` 13 文件逐字节不变、`core/` 既有 105 个 `.py` 源码零改动、
> `kb/` aggregate 指纹 `bcc1bd3f…`（6061 files）一致。

### 6.1 三条承诺

1. **不进入 Phase A Resolution 输入。** observation 不落 Hub，因此
   不在任何 claim 内，`PhaseAResult.basis_claim_ids` 与
   `Resolution.basis_claim_ids` 都不可能引用它。
2. **不进入 Phase B 对齐。** Phase B 只写 alignments，且其规则是
   「basis claim 不得产生 entry」（phase_b.py 文档字符串）。observation
   不是 claim，本就不进。
3. **不改 canonical assertion。** 结构保证：observation 不产生
   assertion 对象，因此不进入任何 `Fact.assertion`。

### 6.2 与既有 traffic 接线的对照

`core/fused/downstream/synthetic.py:39` 已有
`traffic_pcap → cc.traffic.observational → observational`，
且 `claim_class_priority` 把 `observational` 排在 rank 2
（normative、security 之后）。

**本接口不使用该路径。** 那条路径会让 traffic observation 成为
claim、进而参与 resolution，与 §4.8 冲突。本接口选择**根本不进
claim 图**。两者并存不矛盾：synthetic 路径是 Hub 自己的
traffic 测试通道，本接口是 Lane A 的 provenance-only 通道。

### 6.3 可读性承诺

observation 必须能被外部读出来，否则「不参与 Phase A」与
「不存在」不可区分。Lane A 的读出口是本文件所定义的记录格式，
落点由 Step 5 立项决定。

### 6.4 验证归属

**当前无机器验证。** Hub validator 不覆盖本接口的记录。格式校验
与读出口测试一并留给 Step 5。

---

## 7. Open Questions

（待讨论）

---

## 8. Freeze Criteria

（待讨论）

---

## ERRATA

> 追加式勘误。不改写上文正文——错误曾经发生过这一审计事实要保留
> （沿用 `设计/traffic_d9_design.md` §14 的做法）。

### ERRATA-1（2026-10-04）— §5.5 的 validator invariant 主张不成立

**被勘误的原文**：§5.5 的「**强制（留给实现）**：应新增一条 validator
invariant `source_type ∈ {traffic_pcap, traffic_raw}` 的 Evidence
不得出现在任何 Claim.evidence 内」，及其论证「遗忘只保证当前不可达，
validator invariant 才保证将来不可达。**两者都要**」。

**裁定**：**该 invariant 不做。** 依据见
`docs/实施/立项提案/traffic源通道A实现立项.md` §3.2（Final Frozen）。

**推翻理由（三条，均基于本仓库实测）**

1. **与路线图冲突。** invariant 按 `source_type` 全局禁止，等于**永久
   禁止 traffic 通过任何路径成为 Hub Claim**。而项目路线图明确包含
   「Traffic Single-source Hub Build」（见 `工具/交接与工作流/项目交接说明.md` §10）。
   本条的净效果是**用 validator 阻断路线图的下一步**。

2. **会打破既有测试。** `（该测试已随论文实验层移除）`
   以 `PCAP = ("traffic_pcap:...", "traffic_pcap")` 源造 claim，
   同文件 `test_validate_build_passes_for_real_run` 断言真实 run 的
   `validate_build` 零 violations。基线实测（2026-10-04）该三文件
   **317 passed**。实现后必然失败，需同步改测试——等于用测试去追认
   一条未经论证的语义禁令。

3. **对本节自己声称要防的风险保护不完全——这是关键推翻点。**
   本节的论证是「构造性隔离只保证『现在不可达』，validator invariant
   才保证『将来不可达』」。但该 invariant 的形状是
   `for fact.claims: for evidence in claim.evidence`——
   **它只能看见 claim 内的 Evidence**。而本节担心的「将来不可达」
   场景恰恰是：有人改 `writer_impl` 使 Evidence 可写在 claim **外**。
   那种情况下 Lane A observation 不在任何 claim 内，
   **invariant 永远不会触发**。

   ⟹ 本节想要的「将来不可达」，恰恰是这条 invariant **够不到**的那个方向。
   它只能抓「意外泄漏进 claim」单一方向，代价却是全局禁令。
   **收益与代价不成比例。**

**§5.5 第一条（非结构性隔离）仍然成立，且已加强核实**

> `writer_impl` 只在 claim 内写 Evidence；`phase_a.py` 只遍历 `claims`

2026-10-04 重新核实，结论比原文更强：

- `core/fused/runtime/writer_impl.py:134` — `claim["evidence"] = sorted(...)`
  确认。全文仅此一处 `evidence` 写入（第 129 行 docstring 除外）。
- `core/fused/downstream/phase_a.py` — **全文 0 处**引用 `.evidence`。
  即 Phase A **根本不接触 Evidence 对象**，比原文「只遍历 claims」更强。
  L296 / L312 行号核实准确，二者确为遍历 claims 的语句。

**改由什么保障「不落 Hub」**

不再依赖 Hub validator（理由见上），改由 Lane A 侧的构造性边界，
均已在阶段 II 落地并有测试守护：

| 保障 | 实现 | 守护测试 |
|---|---|---|
| 落点与 Hub 物理隔离 | `derived/lane_a/<unit_id>/`（`layout.py:124` verify_layout 只校验 `derived/hub/` 子树） | `test_no_hub_dir_created` |
| 模块不依赖 Hub | `core/lane_a/*` **不 import** `core.fused.*` | `test_does_not_import_hub_modules`（AST 解析真实 import） |
| 读出口不复用 Hub reader | `core/lane_a/reader.py` 纯读 | `test_reader_does_not_import_hub_reader`、`test_reader_is_pure_read` |
| 格式校验独立于 Hub validator | `core/lane_a/schema.py` 不 import `core.fused.*` | `test_schema_does_not_import_hub_validator` |

**残余风险（明确承担，不掩饰）**

- 构造性隔离是**唯一**保障，**无机器强制**。
- 若将来有人修改 `writer_impl` 使 Evidence 可写在 claim 外，
  本方案**抓不到**（如理由 3 所述，这条 invariant 本身也抓不到）。
- 缓解手段：上述 4 条 AST/落点测试会在有人引入 `core.fused.*`
  依赖时立即失败；但它们**不覆盖** writer 契约被改的情况。
- **重新评估时机**：traffic 真正入 Hub 并开始产出 Claim 时。
  届时若需要机器强制，应寻找**按 provenance 标记**而非按
  `source_type` 的隔离手段——`traffic_pcap` / `traffic_raw` 是
  Hub 的 provenance 分类域（见本文件 §3.1），不是 Lane A 专属标记，
  按它一刀切会误伤合法的 Hub traffic 数据。

---

### ERRATA-3（2026-10-04）— §5 / §6 转正 Final Frozen

**性质**：**纯状态变更记录，不重述内容。**

§2 / §3 / §4 已于 ERRATA-2 转正。本条把 §5（Provenance Attachment
Mechanism）与 §6（与 Phase A / Phase B 的关系）一并转正。

至此本文件 §0–§6 **全部 Final Frozen**。

**§5 转正依据**（attachment mechanism 已被实现验证）：

| 判据 | 实测 |
|---|---|
| §5.4「Lane A 侧独立记录」 | 落点 `derived/lane_a/provenance/`，非 `derived/hub/` |
| §5.4「Hub 侧零改动」 | 跑 attachment 后 `derived/hub/` **13 文件逐字节不变** |
| §5.3「可复用 DerivedFrom 的**形状**，不可复用其**落点**」 | attachment 记录含 `fact_id` 引用集，落点在 Lane A 侧 |
| 产出规模 | 25000 observation → **11000** attachment，覆盖 **3** 条 distinct Hub fact |

**§6 转正依据**（§6.1 三条承诺已被验证）：

| 承诺 | 验证方式 | 结果 |
|---|---|---|
| 不进 Phase A Resolution | `core/lane_a/*` 零 `core.fused.pipeline.*` import（AST 测试） | ✅ |
| 不进 Phase B 对齐 | 同上 + `derived/hub/` 13 文件零变化 | ✅ |
| 不改 canonical assertion | attachment 只写 `derived/lane_a/provenance/`；Hub fact 内容逐字节未变 | ✅ |

**§5.5 未被转正的部分**（重申，避免误读）：§5.5 主张的
validator invariant 已被 ERRATA-1 判定「不实施」，本次转正的是
§5.1–§5.4。§5.5 的原文保留作为审计痕迹，其效力以 ERRATA-1 为准。

---

---

### ERRATA-2（2026-10-04）— 追加 §3.5 组粒度；§2 / §3.4 / §4 状态转 Final Frozen

**性质**：**补充 ERRATA-1，不推翻它。** ERRATA-1 处理的是
「validator invariant 做不做」；本条处理的是「observation 如何携带
target」——两者是正交的独立问题。

**追加内容**：§3.5「组粒度：对齐单元是 (group, header)」。
该节给出 §2.4 与 §4.11 F 之间的唯一自洽解，
**§2.4 与 §3.4 原文均未改写**。

**本次一并转 Final Frozen 的原 Frozen Candidate 章节**
（2026-10-04，依据阶段 II / 阶段 III 实测）：

| 章节 | 原状态 | 现状态 | 依据 |
|---|---|---|---|
| §2 StructuralObservation 语义 | Frozen Candidate | **Final Frozen** | 字段集 8 项经 25000 条 observation 实测验证；R3 的 `target_source_build_fingerprint` 为**实现期增补**，属 §2.1 之外的字段，不改写 §2.1 的 8 字段集合 |
| §3 Alignment Target（含新增 §3.5） | Frozen Candidate | **Final Frozen** | 500 units 实测：CSeq/Session/Transport 各 1 候选；Date 等 0 候选落 no_target；§9 #21 的 3 候选按 §2.4 展开为 3 条 observation |
| §4 Alignment Semantics | Frozen Candidate | **Final Frozen** | 四值词表经实现与 25000 条记录验证；`CORROBORATION_RELATION_DOMAIN` 全程未写入 `core.fused.models.py`（D16 守住） |

**§2.1 未被改动的确认**：本次新增的 `target_source_build_fingerprint`
是实现期字段，**不在 §2.1 的 8 字段集合内**，且其语义不改变任何既有字段 ——
它只回答「这个 target 是从哪个 Hub build 解析来的」。
§2.1 的 8 字段集合原样保留。

**实测数据**：500 units / **25000** observation /
**0** `ObservationError` / **0** schema violation；
relation 分布 `insufficient` 11000 / `no_target` 14000。

---
