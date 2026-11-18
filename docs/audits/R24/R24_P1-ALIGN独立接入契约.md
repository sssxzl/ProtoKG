# R24 P1-ALIGN 独立接入契约（★ 仅设计，★ 不接生产）

> ★ **本轮不调用正式 resolver 于生产路径** ｜★ 0 次 LLM 调用

---

## 一、★ 立项依据

★ R23/R24 实测：★ **三协议的中枢多来源 fact 数均为 0**，★ 且 resolution **全部为 null**。
★ ⇒ ★ 跨源语义对齐与多 Claim 消解**在产物上完全不存在**。

★ ★ **★ 不得把「六个合成场景可运行」解释为「生产跨源对齐已验收」。**
★ 六个场景证明的是**引擎可达**，★ 不是**接入已验证**。

---

## 二、接入契约（★ 七项）

### 2.1 哪些来源实例有资格进入语义对齐

| 条件 | 判据 |
|---|---|
| ★ 来源类别 | ★ `file_source` 与 `generated_source` **均可**；★ `unresolved_source` **不可**（★ 身份不可解析 ⇒ 不得进入） |
| ★ 来源身份完整 | ★ 文件来源须有 SHA256；★ 生成器来源须有生成器版本与输入身份（★ 当前待补） |
| ★ 同 fact_key | ★ 候选必须落在同一 (protocol, subject, aspect, condition) |
| ★ 证据非空 | ★ 每条 claim 至少一条可定位 evidence |

### 2.2 多 Claim Fact 的身份与证据保留

| 项 | 规则 |
|---|---|
| ★ fact_id | ★ **不变**（★ 由 fact_key 决定，★ 不含来源） |
| ★ claim_id | ★ 每条 claim 独立（★ `canonical.py:137`） |
| ★ ★ 证据保留 | ★ ★ **每条 claim 各自保留其 evidence**；★ **禁止**把不同来源的证据合到一条 claim |
| ★ superseded | ★ 被消解覆盖的 claim **保留**（★ `resolver.py:133` 的 superseded） |

### 2.3 哪些 aspect 允许 consensus / 需要 precedence

| aspect 语义 | 允许方法 | 依据 |
|---|---|---|
| ★ 单值判定（★ existence、state_changing、target_state） | ★ **precedence** | ★ `resolver.py:40-42` |
| ★ 取值池（★ value_enum_spec、value_enum_observed） | ★ **union** | ★ `resolver.py:50-51` |
| ★ ★ 其余 aspect | ★ **★ 当前落默认 consensus** | ★ `resolver.py:39-52` 只列了 5 个键（★ 21 个 aspect 中） |
| ★ ★ 规范性 vs 观测性 | ★ ★ **需为每个 aspect 显式定义** | ★ 合成场景 SYN-3 实测：★ definition 落 consensus ⇒ **优先级差异未被利用** |

### 2.4 规范性要求与观测事实如何区分

★ 靠 `epistemic_type` 的优先级（★ `resolver.py:28-34`）：
★ `observed`(3) > `normative`/`must`/`normative_unspecified`(2) > `descriptive`(1)。

★ ★ **但该优先级只在 precedence 语义下生效**；★ consensus 语义下取「多源一致即取其一」，
★ ★ **不区分认识论强度** ⇒ ★ **★ 若不先补齐 aspect 语义定义，★ 规范性要求可能被观测值覆盖。**

### 2.5 冲突与 superseded 声明的保留

| 情形 | 方法 | 保留内容 |
|---|---|---|
| ★ 同优先级、值不同 | ★ conflict | ★ 全部 claim 都在 basis；★ **不选边** |
| ★ 不同优先级 | ★ precedence | ★ 胜出者在 basis；★ 其余在 superseded |
| ★ 取值池 | ★ union | ★ 全部 claim 都在 basis |

### 2.6 缺乏显式消解语义的 aspect 如何处理

★ **两条可选路径（★ 须审批选择）**：

| 路径 | 做法 | 代价 |
|---|---|---|
| ★ A | ★ 为 21 个 aspect 逐一定义语义 | ★ 需逐 aspect 论证；★ 但语义正确 |
| ★ B | ★ 未定义语义时**阻断并标 unresolved** | ★ 保守；★ 但会阻断多数 fact |

★ ★ **推荐 A + B 兜底**：★ 已论证的 aspect 用显式语义；★ 未论证的标 unresolved 而非静默 consensus。

### 2.7 接入的前置条件

| # | 条件 | 状态 |
|---|---|---|
| 1 | ★ P0-1A 身份保全通过 | ★ 待 |
| 2 | ★ 来源实例身份完整（★ 含生成器版本与输入身份） | ★ 待补字段 |
| 3 | ★ aspect 语义定义齐备 | ★ 待 |
| 4 | ★ 冲突与 superseded 的落盘 shape 确定 | ★ 待（★ 当前落盘是 `hub_layout.py:114` 的另一种 shape） |
| 5 | ★ 回归：★ 接入后多来源 fact 数 > 0 且 claim 归属正确 | ★ 待 |

---

## 三、★ 验收标准（★ 不得低于此）

| # | 标准 |
|---|---|
| 1 | ★ 至少一个协议的**多来源 fact 数 > 0**（★ 当前全为 0） |
| 2 | ★ 每条多来源 fact 的 **claim 数 = 来源实例数**（★ 不合并证据） |
| 3 | ★ resolution **非 null** 且记录 method 与 basis_claim_ids |
| 4 | ★ superseded 的 claim **在产物中可见** |
| 5 | ★ 规范性 vs 观测性冲突时**按显式优先级裁决**（★ 不落 consensus） |
| 6 | ★ 未定义语义的 aspect 标 unresolved，★ 不静默合并 |

---

## 四、限制

1. ★ 本轮**未接入**；★ **未调用**正式 resolver 于生产路径。
2. ★ 合成场景证明引擎可达，★ **不构成接入验收**。
