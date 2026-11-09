# Traffic Lane A 实现立项

> 状态：**Implemented**（2026-10-04；阶段 I / II / III 全部完成）
> 上游：`docs/设计/各源设计/traffic源规则集设计.md`（Final Frozen）
> 　　　`docs/设计/各源设计/traffic源溯源接口.md`（Final Frozen，§0–§6 全部转正）
> 　　　`docs/设计/各源设计/traffic源观测独立性设计.md` §14 E38
> 本文件为 Lane A 实现阶段的立项书。**Lane A v1 实现已完成。**

**实现产出（2026-10-04）**

```
core/lane_a/        11 模块   pcap / g1 / g2 / g4 / targets /
                              observation / writer / reader / schema / attachment
tests/lane_a/       85 项测试  全部构造数据 + tmp_path，不碰真实 derived/
scripts/attach_lane_a_provenance.py   独立入口（不改 build_hub.py）

derived/model/lane_a/     500 unit   25000 observation
                              (insufficient 11000 / no_target 14000)
derived/model/lane_a/provenance/
                   11000 attachment，覆盖 3 条 distinct Hub fact
```

**已完成的阶段**

| 阶段 | 内容 | 结果 |
|---|---|---|
| I | 只读探针：G1 重建器 | 500/500 与 udp 侧 `client.log` 一致；两生产源 `capture.pcapng` × `rtsp.csv` 交叉验证 500/500 |
| II | `derived/model/lane_a/` 落盘 + reader + schema | 5000 条 G1 observation；模块边界 4 条 AST/落点测试 |
| III | G2 / G3 / G4 / G8 + target 对齐 | 25000 条 observation；11000 条带 target |
| — | Provenance Attachment（§5.4） | 11000 条 attachment；`derived/model/hub/` 13 文件逐字节不变 |

**核心不变量（每步均复验）**

- `derived/model/hub/` 13 文件**逐字节不变**
- `core/fused/` 与 `core/` 既有源码**零改动**（只新增 `core/lane_a/`）
- `kb/` aggregate `sha256:bcc1bd3f…`（6061 files）不变
- `derived/model/spec/rtsp/` NO DIFF
- 全量 pytest **0 failed / 0 errors**

---

## 0. 背景

Lane A v1 已冻结为 **PROVENANCE-ONLY**：从 traffic corpus 抽取
instance-level structural 事实，以**非投票 provenance** 形式附着到既有
Hub protocol Fact，**不产生任何 Hub Candidate / Claim / Fact**。

22 个 structural item 的 emission class 已全部裁定
（`设计/traffic_lane_a_rule_set_design.md` §3.2）：

| category | 数量 |
|---|---|
| `PRIMITIVE` | 7 |
| `HUB_EMITTING` | 7 |
| `NO_TARGET_PENDING_EXTRACTION` | 4 |
| `OUT_OF_SCOPE` | 3 |
| `CROSS_CUTTING` | 1 |

---

## 1. 实现范围

### 1.1 在范围内

1. **G1 重建器**：从 `capture.pcapng`（按 magic 判定 classic libpcap）
   重建 Message boundary 与 request/response class。契约见规则集 §4.5 §4.6。
   规则已冻结，**具体算法由实现决定**（§9 #9）。
   **阶段 I 已在 scratch 验证该算法可行**：500/500 与 oracle 一致，
   且独立复现 N 分布 55/56/57/58 与三变体 468/30/2（见 §5.2）。
2. **G3 提取器**：method / status / URI 的 instance attribute 提取。
   契约见 §4.10。
   **注意（阶段 I 新发现）**：response 侧 method 不在 start-line 内，
   只能由 G2 的 CSeq 配对派生 ⟹ **G2 必须先于 G3 的 response 侧执行**。
3. **C17 贡献集**：frame → message 的归属判定。契约见 §4.13。
4. **StructuralObservation 记录器**：按
   `设计/traffic_lane_a_provenance_interface.md` §2 的形状写 Lane A 侧记录。
   **不写 Hub。**落点见 §3.1.1（`derived/model/lane_a/<unit_id>/`）。
5. **G2 / G4 / G8 提取器**：CSeq pairing、header presence/value、
   Session/Transport 上下文。契约见 §4.11。

### 1.2 明确不在范围内

- 任何 Hub Candidate / Claim / Fact 的生成
- Message Boundary splitter 的算法选择（§9 #9，实现阶段冻结）
- G5 / G7 的 extraction coverage 修复（Hub Contract 侧，见 §2.2）
- G6（已按 D18 移出，见 §2.1）
- §8 扩展（独立议题）
- **`core/fused/validation.py` 的 validator invariant**——§3.2 已裁定为「不做」
- `derived/model/hub/` 下任何写入（含测试；`fused_runtime_io_v1.md` L664 契约）

---

## 2. 依赖

### 2.1 Hub Contract 议题（阻塞或影响）

| 议题 | 登记位置 | 对 Lane A 的影响 |
|---|---|---|
| G6 无法进入 Hub pair 机制 | `实施/待办与勘误/中枢契约勘误待办.md` §8 | G6 已 OUT_OF_SCOPE，不阻塞 |
| Evidence 只能写在 Claim 内 | `实施/待办与勘误/中枢契约勘误待办.md` §9 | 已导致 D17 改判为「不落 Hub」 |
| `packet_role_pair` code/registry 分歧 | `实施/待办与勘误/中枢契约勘误待办.md` §6 | 影响 G7 未来升级，不阻塞 |
| `ALIGNMENT_RELATION_DOMAIN` 逐值语义缺失 | `实施/待办与勘误/中枢契约勘误待办.md` §7 | 不阻塞（D16 已另立 Lane A 词表） |
| 读出口与格式校验无机器强制 | 本文件 §3 | **实现期必须解决** |

### 2.2 extraction coverage 议题（不阻塞 v1）

- **G5 Message Ordering**：`core/extractors/` 侧无 RFC 顺序词汇
  （实测 2 处命中均偶然）
- **G7 Packet-Role**：RFC 抽取路径中 role 词汇基本不存在
  （唯一命中是 `graph.py` 的 `upstream_origin=None` 与 `vuln_rules.py`）

两者的 target 缺位是 Hub Contract 侧问题，**Lane A 侧以
`relation = no_target` 记录**（规则集 §4.12）。

### 2.3 前置数据事实（已冻结，不需重测）

- 500 effective / 1000 nominal 双层计数（Capability Profile §11.4）
- tcp 侧 `client.log` 排除（Capability Profile §11.2）
- `capture.pcapng` 是 classic libpcap，`clean.pcapng` 是 pcapng
  （Capability Profile §10 / D9 E33）
- frame ordinal 即 `rtsp.csv` / `packets.ndjson` 已在用的 frame number

---

## 3. 待裁定问题

> **✅ 2026-10-04 全部裁定完成，本文件据此 Final Frozen。**
> §3.1 三项已落定，§3.2 已裁定为「不做」。每项附依据与承担的后果。
> 裁定依据为本仓库实测，非推测。
> 保留章节标题「待裁定问题」不改名，作为裁定前的原始指代。

### 3.1 实现期必须先解

> **✅ 已落定（2026-10-04）**

#### 3.1.1 observation 的落点与命名 — `derived/model/lane_a/`

**裁定**：`derived/model/lane_a/<unit_id>/`，与 Hub 的 `derived/model/hub/` 物理隔离。

**依据**：

- `core/fused/runtime/layout.py:124` 的 `verify_layout` 的 root 是
  `workspace_root / "derived" / "fused"`，**只校验 `derived/model/hub/` 一个子树**，
  不对 `derived/` 顶层做白名单 ⟹ 新增顶层不产生 `layout_unexpected`。
- 既有先例：`derived/model/vuln/` 已是 `derived/` 下的非 `fused`/`per_source`/`spec`
  顶层目录。
- **排除 `derived/model/per_source/traffic/lane_a/`**：traffic 尚未入 Hub，
  建一个空的 `per_source/traffic/` 会让接手者误读为 traffic 已入中枢，
  与 D17「不落 Hub」的隔离意图相反。

**后果**：Lane A 产物在 `derived/` 下可见但与 Hub 一眼可分；不承担
`per_source` 的持久化契约（那套契约面向 Hub 五源）。

#### 3.1.2 读出口 — `core/lane_a/reader.py`

**裁定**：Lane A 自带 reader，**不复用** `core/fused/reader.py`（后者只认
`derived/model/hub/` 的 layout，且其契约由 `fused_runtime_io_v1.md` 冻结）。

**依据**：§4.5 P4 规定 boundary conflict 时输出 `NEEDS_REVIEW`——这要求
消费者能读出「哪些 unit 有未解决冲突」，而 Hub reader 无此能力。
阶段 III 的 G2/G4/G8 提取器需要读回阶段 II 的记录作为输入，接口必须先定。

**后果**：新增一个 Hub 契约之外的读取路径。**该路径不进 version control
判定范围**（见 3.1.1 后果），但必须是纯读、不得反向写 Hub。

#### 3.1.3 格式校验 — 独立于 Hub validator 的 Lane A schema

**裁定**：新增 `fused_hub/schema/v1/` 之外的 Lane A schema
（位置随 3.1.1 定为 `derived/model/lane_a/` 同级的 schema 定义），
校验 `设计/traffic_lane_a_provenance_interface.md` §2 的记录形状。

**依据**：Hub validator 校验的是 `Fact`/`Meta`/`Graph`/`Audit`，
`StructuralObservation` 不属其中任何一种，无法被 `validate_build` 覆盖。
复用 Hub validator 等于把非 Hub 产物塞进 Hub 契约。

**后果**：多一套 schema 与校验器。这是「不落 Hub」的必然成本——
不落 Hub 就得不到 Hub 的免费校验。

### 3.2 建议新增的 validator invariant — **裁定：不做**

> **✅ 已裁定（2026-10-04）：明确记为「不做」，并承担后果。**
> **冲突已闭合（2026-10-04）**：本裁定原与
> `设计/traffic_lane_a_provenance_interface.md` §5.5 的「两者都要」相反，
> 已由该文件文末 **ERRATA-1** 正式勘误 §5.5。两份 Final Frozen
> 文档现立场一致。

原建议内容：

> `source_type ∈ {traffic_pcap, traffic_raw}` 的 Evidence 不得出现在
> 任何 `Claim.evidence` 内。

**不采用的依据（三条）**：

1. **与路线图冲突。** 该 invariant 按 `source_type` 全局禁止，等于
   **永久禁止 traffic 通过任何路径成为 Hub Claim**。而本项目路线图
   （handoff §10）明确包含「Traffic Single-source Hub Build」一步。

2. **会打破既有测试。** `tests/fused/pipeline/test_pipeline_e2e_synthetic.py:64`
   定义 `PCAP = ("traffic_pcap:capture/run-0001.pcap", "traffic_pcap")`
   并用它造 claim，而同文件第 779 行 `test_validate_build_passes_for_real_run`
   断言真实 run 的 `validate_build` 零 violations。
   **基线实测（2026-10-04）该三文件 317 passed**；实现后必然失败，
   需同步改测试——那等于用测试去追认一条未经论证的语义禁令。

3. **对 §3.2 自己担心的风险保护不完全。** 原建议的理由是
   「构造性隔离只保证『现在不可达』，不保证『将来不可达』」。
   但 validator 只遍历 `fact.claims`。若将来有人把 observation 写到
   **claim 外**（正是所担心的方向），它根本不会被任何 Claim 遍历到，
   invariant **不会触发**。它只能抓「意外泄漏进 claim」这一个方向，
   代价却是全局禁令——收益与代价不成比例。

**承担的后果（明确记录，不掩饰）**：

- 构造性隔离是**唯一**保障：`writer_impl.py:134` 的
  `claim["evidence"] = sorted(...)` 证明 Evidence 只在 claim 内写出，
  且 `phase_a.py:296/312` 只遍历 `claims`。
- **无机器强制**。若将来有人修改 writer 使 Evidence 可写在 claim 外，
  本方案**抓不到**。
- 缓解：阶段 II 落盘时在 `derived/model/lane_a/` 内自带格式校验（见 3.1.3），
  该校验覆盖记录自身形状，但不覆盖「是否被误写入 Hub」。

**何时应重新评估**：若 traffic 真的进入 Hub 并开始产出 Claim
（`Traffic Single-source Hub Build` 落地时），需重新评估是否存在
**按 provenance 标记**而非按 `source_type` 的更精确隔离手段。

### 3.3 承接的未决项

- 规则集 §9 #18 CSeq 覆盖路径甲/乙
- 规则集 §9 #20 G5 / G7 extraction gap
- 规则集 §9 #21 subject canonical 未解前 G4 target 无法唯一选定

> **§9 #21 根因已查明（2026-10-04，读 `derived/model/hub_status.txt` + 实测）**：
> 分裂来自 `claim_classification_rules` 的 **CR-5 产出 `Authorization`**，
> 而 `vuln_rules` 的 **VR-2 产出规范化的 `authorization`**，同一 header
> 因此落成两个 Fact。候选解法两条——改 CR-5（跨源）或在 fact identity
> 层做全局归一（管线变更）——**均需修改冻结资产，未授权**。
>
> 该缺口**不阻塞实现**：target 集合已定义，且规则集 §4.4 的
> `NEEDS_REVIEW` token 正是为「无法由 deterministic rule 消解的冲突」
> 准备的。G4 对该 subject 的 attribution 标 `NEEDS_REVIEW` 并同时记
> 两个候选即可，属输出质量降级。

---

## 4. 建议路径

### 阶段 I — 只读探针（不改任何仓库文件）

1. 实现 G1 重建器，在 500 effective units 上跑通
2. 断言：Message count / class / CSeq 与 udp 侧 `client.log` 500/500 一致
   （Stage C-Pre T6 已用 29 样本验证过 500/500 的一致性，此处扩到全量并固化）
3. 断言：Message Boundary **不落 Hub**——跑一次 pipeline，确认
   `derived/model/hub/facts/` 逐字节不变

阶段 I 的价值：在写任何持久化代码之前，先证明「重建正确 + 零 Hub 副作用」。

### 阶段 II — Lane A 侧记录落盘

1. 定 §3.1.1 的落点与命名
2. 实现 §2 的记录形状 + §3.2 的 validator invariant
3. 建立读出口与格式校验

### 阶段 III — G2 / G4 / G8 提取器

1. 逐组按 §4.11 的 A–J 实现
2. 每组先在 500 units 上验证 relation 分布是否符合 §4.11 G 的预期
   （G2 大概率 `insufficient`、G4 `corroborates`、G8 `insufficient`）

### 不建议的做法

- **不建议**为 G5 / G7 在 Lane A 内部补 extraction 缺口。缺口在 Hub
  Contract 侧，Lane A 自行补会造成两套抽取语义。
- **不建议**让 observation 进入 `synthetic.py` 已有的
  `traffic_pcap → cc.traffic.observational` 路径。那条路径会让 traffic
  observation 成为 claim 并参与 resolution，与 §4.8 冲突
  （`provenance_interface.md` §6.2 已说明两者并存不矛盾）。

---

## 5. 冻结条件

本立项书转为 Frozen 需：

1. ~~§3.1 三项实现期问题全部落定~~ → **✅ 2026-10-04 已落定**（见 §3.1.1 / §3.1.2 / §3.1.3）
2. ~~§2.3 前置数据事实复核仍成立~~ → **✅ 2026-10-04 已复核**（阶段 I 报告 §5）
3. §3.2 validator invariant 要么实现、要么明确记为「不做」并承担后果
   → **✅ 2026-10-04 已裁定为「不做」，后果已在 §3.2 明文承担**
4. ~~阶段 I 的两条断言（重建一致 + Hub 零副作用）在全量 500 units 上通过~~
   → **✅ 2026-10-04 阶段 I 执行，500/500 match + 0 mismatch**

### 5.1 条件 4 的执行结果与口径声明

| 断言 | 结果 |
|---|---|
| ① Message count / class / CSeq 与 udp 侧 `client.log` 一致 | **500 / 500** |
| ② Hub 零副作用 | 探针形态下 **13/13 UNCHANGED**，kb / 七树 / 7 份 Frozen 文档均未变 |

**口径声明（不得冒充）**：原条件 ④ 写的是「跑一次 pipeline，确认
`derived/model/hub/` 逐字节不变」。阶段 I 是只读探针，G1 未接入 `core/`，
pipeline 根本看不到它——真去跑 pipeline 等于什么都没验。
实际执行的是该断言在阶段 I 下**可实际检验**的形态：
**验证探针自身不产生任何仓库副作用**。
「G1 接入 pipeline 后 Hub 仍零副作用」这一更强断言，
**只能在阶段 II 真正集成代码后检验，尚未完成**。

### 5.2 阶段 I 的独立收获

- **N 分布独立复现冻结事实**：实测 55×468 / 56×30 / 57×1 / 58×1（500 udp units），
  ×2 = 936/60/2/2，与 Capability Profile §10.3 精确吻合；
  3-variant 切分 468/30/2 与 §4.5 精确吻合。
- **两生产源交叉验证 PASS**：`capture.pcapng` × `rtsp.csv` 在
  message 数 / method / status / C17 贡献集 上 500/500 一致。
- **新发现（建议补入规则集 §4.5 P8 作为第 6 条）**：
  **RTSP response 的 start-line 不含 method**。G1 能独立产出 response 的
  `status` 与 `CSeq`，**产不出 method**；response → method 归属只能由
  CSeq 配对得到，那是 **G2 的职责**。§4.7 裁定 C04 Method 为 PRIMITIVE
  实际**只对 request 侧成立**，response 侧 method 是派生属性，
  依赖 G2 先跑。**本批次未修改任何冻结文档，仅登记建议。**
- **量具缺陷 ×2（已修正并重测）**：①按方向分组排序破坏 request/response
  交错顺序；②拿 response 的 `method` 比对，但该字段在 start-line 中
  结构上不存在。初版 0/3 是量具错而非重建错。

### 5.3 冻结后的下一步

```
阶段 I  ✅ 完成（2026-10-04）
   ↓
本文件转 Frozen
   ↓
阶段 II —— Lane A 侧记录落盘
  1. 按 §3.1.1 落点写 StructuralObservation 到 derived/model/lane_a/<unit>/
  2. 实现 §3.1.2 reader（core/lane_a/reader.py，纯读，不反向写 Hub）
  3. 实现 §3.1.3 Lane A schema 校验
  4. 本阶段完成后方可检验「G1 接入后 Hub 仍零副作用」的强断言
   ↓
阶段 III —— G2 / G4 / G8 提取器
  （G4 对 authorization / Authorization 标 NEEDS_REVIEW，见 §3.3）
```

---

*本文件状态见头部。本文件为 Proposal。§3.1 的落点与命名未冻结，实现不得先于本文件冻结。*
