# Q5 Candidateization Gap 立项

> **状态：已实现并已落盘（2026-10-07，D67）**
> `derived/fused/facts/state.jsonl` **4 条**、
> `transition.jsonl` **21 条**，既有 65 条 fact 零变化。
>
> 日期：2026-10-06
> 来源：`docs/设计/five_source_fusion_framework.md` Q5 / `实施/hub_contract_errata_backlog.md` §17

---

## 0.1 实现结果摘要（2026-10-06）

| 项 | 结果 |
|---|---|
| 阻塞（emit 0..N） | **已解除** —— D61 修复 `_apply_rule`，`_apply_rule` 每 rule 可产 N 个 |
| 阻塞（挂载点） | **已解除** —— 2026-10-06 批次获授权 |
| 规则文件 | `core/fused/pipeline/rules/state_rules.py`（SR-1 / SR-2） |
| 规则集规模 | **8 → 10** 条 |
| 实测产出 | **1 条 norm → 25 个 Candidate**（4 states + 21 transitions） |
| 修复前上限 | **2 个**（每 rule 最多 1） ⟹ 0..N 收益实测 **12.5×** |
| 单元测试 | `tests/fused/pipeline/rules/test_state_rules.py` **23 passed** |
| build | ✅ **已跑**（D67）：facts.total **65 → 90** |

⟹ **D58 登记的两个阻塞都已解除**；Q5 从「缺口」转为「规则已就绪、待 build」。


---

## 0. 一句话

`state` / `transition` 两类 fact 恒为 0 的根因是 **candidateization 缺规则**，
不是语料缺失，也不是契约缺失。补规则本身不难，难在**挂载点不可达**。

---

## 1. 探查结论

### 1.1 语料在

`kb/expert_note/state_machine.json`：

```json
{
  "schema_version": 1,
  "states": ["Init", "Ready", "Playing", "Recording"],
  "initial_state": "Init",
  "transitions": [
    {"from": "Init", "method": "SETUP", "code": 200, "to": "Ready"},
    ...
  ]
}
```

且它**已是 build 输入**（`derived/fused/meta.json` → `inputs[9]` =
`expert_note:expert_note/state_machine.json`，12 条 expert_note 输入之一）。

### 1.2 norm 在

`core/extractors/expert_notes_json.py:9` 明列 `state_machine.json` 是
「FALLBACK_TRANSITIONS 等价」，产出 **1 条 norm**，
类型 `kind=expert_note, facet=source_layer:expert_notes`
（与 `methods.json` / `required_headers.json` / `header_naming.json` 同型）。

⟹ CR-4 / CR-5 消费的正是这 4 条 norm 之一。

### 1.3 下游已就位

`core/fused/pipeline/rules/graph.py` 已有两条**等 state fact** 的规则：

| 规则 | 判据 | 现状 |
|---|---|---|
| `GR2_STATE_ENTITY` | `fact.fact_key.kind == "state"`（`graph.py:160`） | 永不命中（无 state fact） |
| `GR3_METHOD_VALID_IN_STATE` | 需 method-valid-in-state fact | 永不命中 |

⟹ **图层已经为 state 预留了入口，缺的只是中间一环。**

### 1.4 契约覆盖

| 层面 | 覆盖情况 |
|---|---|
| `fact.schema.json` `kind` enum | ✅ 含 `state` 与 `transition`（6 值） |
| `property_registry` | ✅ **11 个** property 的 `allowed_kinds` 含 state/transition（`existence` / `trigger_event` / `guard_condition` / `action` / `target_state` / …） |
| `fused_pipeline_v1.md:571` `canonicalize_subject` | ⚠️ `kind` 取值仅 `"method"` / `"header"` / **`"state"`** —— **不含 `transition`** |
| Rule Contract §2.2（8 字段） | ✅ 通用形式，与 kind 无关 |
| `subject_registry.initial_subjects.state` | ✅ 已列 `state.Init` / `state.Ready` / `state.Playing` / `state.Recording`（Title-Case） |

⟹ **`state` 类契约齐备；`transition` 类在 `canonicalize_subject` 上有缺口。**

---

## 2. 阻塞点（2026-10-06 更新：挂载已授权，真正阻塞在其下）

> ★ **本节已重写。** 挂载点（`candidateization.py`）在 2026-10-06 的批次中
> **已获授权**，但实测发现其下方存在一个**更大的结构性阻塞**。

### 2.0 ★ 真正的阻塞：emit cardinality 框架只支持 0..1

契约侧（`candidateization.py:250` docstring）明写：

> 每条 eligible rule 产生 **0..N** CandidateProposal

实现侧却是：

| 位置 | 实测 |
|---|---|
| `fact_key_projection` 返回类型 | `Optional[RawFactKeyCandidate]` —— **单个** |
| `_apply_rule` 结尾（line 240） | **无条件** `return (proposal,)` |
| `emit_cardinality` 用途（line 236） | 仅一个 `pass`，**不影响发出数量** |

⟹ **一条规则对一条 norm 最多产 1 个 Candidate。**

而 `state_machine.json` 是**一条** norm
（实测 `norm_id=constraint.state_machine`、`kind=constraint`、
`source=expert_note/state_machine.json`），
要表达 **4 个 state + N 个 transition**。

⟹ **框架无法表达 Q5 所需的结果。**

**修法与其代价**：把 `fact_key_projection` 的返回类型改为序列，
**会波及全部 8 条既有规则**（CR-1..CR-5 / VR-1..VR-3）的签名
⟹ **框架级重构，须整批处理**，不宜与 Q5 夹带。

⚠ 这**推翻了 D54 的判断**「实现是 `build_candidateization_rules()` 内一处增量」——
挂载确实只是一行，但**挂载之后仍然无法工作**。

登记为 L5 Proposal 的 **L5-Q9**（P0）。

### 2.1 挂载点（阻塞已解除）

当前规则装配是**硬编码**的：

```python
# core/fused/pipeline/rules/candidateization.py:489-502
def build_candidateization_rules() -> tuple:
    from .vuln_rules import VULN_CANDIDATEIZATION_RULES
    return CANDIDATEIZATION_RULES + VULN_CANDIDATEIZATION_RULES
```

新增 `state_rules.py` 后要生效，**必须**改这一行 —— 而
`core/fused/ 现有文件` 在本批禁止区。

### 2.2 为什么本批不写「可写但挂不上」的模块

D44 已经踩过这个坑：`writer.is_client_invocation` 分支因缺少遍历入口
而成为**不可达代码**，当时被登记为「C-1 只落地了一半」。

**写一个明知挂不上的 `state_rules.py`，等于主动制造 D44。**

⟹ 本批只出提案。挂载授权到位后，实现是一处函数体内的一行增量。

---

## 3. 待裁定问题

| # | 问题 | 影响 |
|---|---|---|
| **Q5-A** | `state` / `transition` fact 的 subject 用**裸名**（`Init`）还是**点号**（`state.Init`）？ | **2026-10-06 回原文查证**：`initial_subjects.state` = `['state.Init', ...]`（点号）；`lexical_normalization.state` = 「Title-Case, e.g. Init, Ready」（裸名 token）；`canonical_format` = `"<category>.<canonical_name>"`。⟹ **与 header 完全同型**（点号 vs 裸名的两套约定并存）。依指令「与 D49 同型的问题合并裁定，不单独选」⟹ **本批只登记，不选** |
| **Q5-B** | `transition` 的 `canonicalize_subject` 缺口是否要先补契约？ | 契约是冻结文件，改它需授权 |
| **Q5-C** | 一个 transition 拆成几条 fact？`{from, method, code, to}` 是 1 条 `transition` fact（property=`action`）还是 3 条（`trigger_event` / `target_state` / `guard_condition`）？ | 决定 facts 数量与 graph 形态 |
| **Q5-D** | 与 `derived/model/spec/rtsp/state_machine/state_machine.json` 的**权威边界** | spec 侧已有状态机产物。若 Hub 也产 state/transition fact，两者的真源关系必须明确，否则会出现第二处「同一事实两个真源」（第一处是 §10.1 的 Authorization 分裂） |
| **Q5-E** | `state_machine.json` 的 `code: 200` 是否要产 fact？ | 200 已是 CR-4 产出的 `status.200` fact；若 transition 再产一条，属冗余 |
| ~~**Q5-F**~~ | ~~emit cardinality 框架何时修？~~ | **✅ 已完成（D61）** —— `_apply_rule` 支持 0..N，8 条规则签名同步 |
| **Q5-G** | **L5 state 通道何时接通？** | **P1** —— state fact 已就位（4+21），但 `inventory.states` 仍只进 manifest ⟹ **数据在管道里，没有出口**（与丙/戊同型） |

---

## 4. 建议实现路径（获授权后）

```
0. ~~先修 emit cardinality 框架~~ ✅ D61 已完成
1. 裁定 Q5-A ~ Q5-G
2. 新建 core/fused/pipeline/rules/state_rules.py
     - 仿 vuln_rules.py 的 8 字段 Rule Contract
     - SR-1: state.<X> 存在性      → kind=state,   property=existence
     - SR-2: from→to 迁移           → kind=transition, property=<Q5-C 裁定>
3. 挂载：candidateization.py 的 build_candidateization_rules() 加一行
     from .state_rules import STATE_CANDIDATEIZATION_RULES
     return CANDIDATEIZATION_RULES + VULN_CANDIDATEIZATION_RULES + STATE_CANDIDATEIZATION_RULES
4. 单元测试（新建 tests/ 下，不动现有）
5. ★ 先不跑 build —— 只验证规则本身；跑 build 会改 derived/fused/
6. 跑一次 build 观察 facts 增量 + GR2/GR3 是否开始产出
```

### 4.1 schema bump 评估

**不触发 bump。** 依据：

- `kind` enum 已含 `state` / `transition`（`fact.schema.json` v2 已是 6 值）
- `property_registry` 的 `allowed_kinds` 已含之 ⟹ 用现有 property 不需改 registry
- 新增的是**规则**，不是 schema —— `fusion_version` 视实现是否改变产物而定

⚠ 若 Q5-C 裁定为「新增 property」，则需改 `property_registry.json`（冻结文件）
⟹ 那才需要 schema bump + 授权。**建议 Q5-C 限定在现有 property 内。**

---

## 5. 与其它待办的关系

| 项 | 关系 |
|---|---|
| **D49 / L3** | Q5-A 与 header 的裸名 vs 点号议题**同型**，应合并裁定，否则产生两套不一致约定 |
| **backlog §17** | 本提案是该条目的**实现方案**；§17 保留「缺口」登记，本提案记录「怎么补」 |
| **L5 通道** | state/transition fact 进入 Hub 后，**若 seedgen 桥接不消费 state**，则对 L5 仍无传导 —— 补规则**不等于**提升传导 |

---

*本文件 2026-10-06 新建。状态：Proposal。*
*探查结论全部来自磁盘实测，命令见 `local/backup/step_fusion_b/stage_c_q5_rules/`。*

---

## 6. 待办：跑 build（另批 transaction）

规则已就绪但**未落盘**。跑 build 后应观察：

| 观察项 | 预期 |
|---|---|
| `derived/fused/facts/state.jsonl` | 0 B → **4 条** |
| `derived/fused/facts/transition.jsonl` | 0 B → **≤ 21 条**（按 condition 去重后可能更少） |
| `facts.total` | 65 → **约 86**（+4 state +17 transition，去重后可能略少） |
| `graph/entities.jsonl` | `GR2_STATE_ENTITY` 开始产出 state 实体 |
| `fusion_version` | 可能需 bump —— **须先判定**：新增 fact kind 属产物语义变化 |
| `validation.jsonl` | 观察是否有新的 validation finding |

⚠ **`transition` 的 subject 采用 `src->dst` 拼接形式**，
若多个 method 从同一状态到同一状态（如 `Init->Init` 出现 3 次），
它们会被 `condition` 里的 method 区分开 ⟹ 是**不同 fact_key**，
但语义上可能是同一状态迁移的多个触发条件 ⟹ **Q5-C 的问题依然待裁定**。

⚠ **跑 build 前建议先裁定 Q5-A**：subject 裸名 vs 点号会直接决定
`state.Init` 还是 `Init`，改起来成本不同（点号需同步改 GR2 的 `canonical_name`）。

---

## 7. build 实测结果（2026-10-07，D67）

```
python scripts/build_hub.py --sources rfc expert_note vuln
  [fused] 融合 137 条
  [fused] -> derived/fused/  90 Facts / 58 entities / 473 relations
                             / 34 audits / 100 lineage
```

> 注：`--sources ... source` 会因 source 载入 0 条 norm 而报
> `input_entries 至少 1 条` —— 这是 **D40 已登记的既有行为**，非回归。

### 落盘结果

| 文件 | before | after |
|---|---|---|
| `facts/state.jsonl` | 0 | **4** |
| `facts/transition.jsonl` | 0 | **21** |
| `graph/entities.jsonl` | 54 | **58**（GR2 首次产出 state 实体） |
| `audit/lineage.jsonl` | 75 | 100 |
| `audit/matches.jsonl` | 11 | 31 |

新增 25 条 fact **全部 `resolved`**；既有 65 条**零消失、零内容变化**；
attachment **零悬挂**。

### ★ Q5-C 被实测暴露（D69）

```
21 条 transition fact，12 个唯一 subject
  Ready->Ready         6 条（SETUP / ANNOUNCE / DESCRIBE / SET_PARAMETER / OPTIONS / GET_PARAMETER）
  Init->Init           3 条（DESCRIBE / OPTIONS / TEARDOWN）
  Ready->Init          2 条（TEARDOWN / REDIRECT）
  Recording->Recording 2 条（SETUP / RECORD）
```

⟹ 语义上只有 **12 个状态迁移**，却落成 **21 条 fact**：
`method` 落在 `condition` 里，同一 `(from, to)` 按触发方法被拆开。

**三种建模待裁定**（会改 `fact_id` 与 audit ⟹ 契约级）：

| 方案 | 键 | fact 数 |
|---|---|---|
| **甲**（当前实现） | `(from, to, method)` | 21 |
| **乙** | `(from, to)`，method 进 assertion / scope | 12 |
| **丙** | 拆 `transition` + `transition_trigger` 两类 | 更多但语义最清 |

⚠ **不得由实现方自行裁定。**

### 待办

1. **跑 build** ✅ 已完成
2. **裁定 Q5-C**（transition 建模）—— 会改 `fact_id`
3. **接 L5 state 通道**（Q5-G）—— 数据已在管道里，仍无出口
   ⟹ ★ 2026-10-07 更正：这**不是模型扩展需求**。
   `SeedCorpus.target_state_path` 早已存在且下游已在消费，
   桥接也已写入 ⟹ Q5-G 是**接线级改动**（D72）。
4. `fusion_version` 是否 bump？本次**未 bump**（`build_fingerprint` 输入未变），
   但产物已变 ⟹ **须评估**（另批）

---

## 8. 依赖链的更正（2026-10-07，D72）

指令 C3 假设「Q5-C 裁定依赖 SeedCorpus 扩展结论」。实测后该依赖**不成立**：

| 原假设 | 实测 |
|---|---|
| Q5-C 依赖「SeedCorpus 是否扩展为多请求」 | ❌ SeedCorpus **本就是**多请求模型 |
| Q5-G 依赖「SeedCorpus 能否承载状态序列」 | ❌ `target_state_path` **早已存在**且下游在消费 |

⟹ **Q5-C 与 Q5-G 都不依赖 SeedCorpus 扩展**，
两者都是**独立可做**的：

- **Q5-G**（接线）：把路径规划数据源从 spec 换成 Hub transition
  ⟹ 改了才能让已落盘的 25 条 state/transition fact 产生下游价值
- **Q5-C**（建模裁定）：21 → 12 还是 21 条
  ⟹ 改 `fact_id` 与 audit，属契约级，需授权

⚠ **建议顺序**：先做 Q5-G（低风险，不改 Hub 产物），
拿到「state 通道确实能改变产物」的证据后，
再决定 Q5-C 是否值得重建这 21 条 fact。

理由：若 Q5-G 的接线本身不产生可观测增量，
则 Q5-C 的重建代价（fact_id 变更 + audit 重写 + attachment 重挂）
将缺乏收益支撑。
