# B-10 实验预登记（ProtoRAG 里程碑 B 出口闸门）

> ★ **本文件是实验前定稿的预登记，事后不得修改。**
> 依据：`docs/rfc_source_bcd_roadmap.md` §4.1~§4.6。
> 实验结果**不写在本文件**，另见 `docs/semantic_gain_results.md` 与
> `derived/exp_semantic_gain/results.json`（git 历史可证明「预登记先于结果」）。

## 1　预登记（§4.5 阈值表，逐字照抄）

| 指标 | 收益成立 | 部分成立 | 不成立 |
|---|---|---|---|
| **M1 可执行率** | E1 ≥ C0 + **15 个百分点** | E1 ≥ C0 + 5 个百分点 | E1 < C0 + 5 个百分点 |
| **M2 规则 F1** | **≥ 0.70**（对 holdout） | 0.50 ~ 0.70 | **< 0.50** |
| **M3 证据可验证率** | **= 100%** | — | **< 100%**（任一不可验证却算规则 ⇒ 污染） |
| **M4 显式性纯净度** | **= 100%** | — | **< 100%** |
| **M5 MAY 误升率** | **= 0%** | — | **> 0%**（任一误升 ⇒ 阻断，先修再继续） |
| **M6 rule_id 幂等性** | **N 次完全相同** | — | **任一次不同**（⇒ 派生规则有 bug，先修） |

## 2　综合判定规则（§4.5，逐字照抄）

- **收益成立** = M1 达「收益成立」档 **且** M2 达「收益成立」档 **且** M3/M4/M5/M6 **全部达标**。
  → 允许进入里程碑 C 的开发准备。
- **部分成立** = M1 或 M2 落在「部分成立」档，但 M3~M6 全部达标。
  → **不进入 C**；转为「B 阶段只交付知识层（规则入库 + 人工复核），不接自动生成链路」；把 M7 的拒绝原因分布反馈给模式表迭代，下轮再评。
- **收益不成立** = M2 < 0.50 或 M1 提升 < 5 个百分点。
  → **B 阶段终止自动生成链路方向**。保留两层模型作为**知识表示**（人工复核用），但**不承诺** fuzzing 收益；C 阶段应改为「先做无向量的规则化变异」这一更轻的替代路线（评审报告 §四 替代方案 A/B 的取舍）。

## 3　已知契约漂移（不参与本实验判定）

rtsp: A 38→52 / B 50→65 / C 50→65 / D 50→65
sip:  A 15→?  / B 25→20 / C 25→?  / D 25→?
smtp: A 76→?  / B 78→61 / C 78→?  / D 78→?
根因（docs/rfc_reform_a_implementation_report.md §10.4 已实测）：source 源引入
LIVE555 真实状态名，取代 expert_note v3 的虚构状态名 → 状态机层与种子序列全变。
★ 与 rfc 源**零影响**（剔除 rfc 源后条数与 md5 完全相同）。
本实验的判定指标中**不含任何种子条数**，故该漂移不影响结论。

## 4　实验方法（预登记）

### 4.1　被测命题

- **命题 B-1**：把 RFC 约束从「自由文本」升级为「两层可执行模型」后，产出的规则中
  **可机械判定**的比例（可执行率）显著高于当前影子实现的可判定比例，
  且**不引入新的知识污染**。
- **辅助命题 B-2（幂等性）**：同一 RFC 重复抽取 N 次（N ≥ 2），`rule_id` 集合完全相同。
- **辅助命题 B-3（无污染）**：两层模型的规则中 `explicitness == "explicit"` 的集合与
  「原文含 MUST/SHALL/REQUIRED」的规则集合完全一致（不多不少）。

### 4.2　三组 × 三协议

| 组 | 输入 | 输出 |
|---|---|---|
| **C0（基线）** | 当前影子实现（`core/fused/rfc_extractor.py::infer_constraints` + LLM） | `legal_boundary` / `response_expectation` **自由文本** fact |
| **E1（实验）** | **同一批候选句** + 同一 LLM 模型/温度/提示词 | `SemanticRule` + `KnowledgeCandidate` |
| **E2（消融）** | 同一批候选句，**只跑规则表**（无 LLM 兜底） | 两层模型 |

- 三协议全跑（rtsp / sip / smtp），**不做跨协议收益比较**（协议差异过大），
  每个协议内部做对照。
- C0 与 E1 共用同一份 LLM 缓存 ⇒ 同一候选句**只调一次** LLM。

### 4.3　候选集（冻结）

- **来源**：复用既有冻结集 `derived/exp_semantic/candidates_frozen.jsonl`
  （md5 `6060457e78f253699fcf2da8dc343733`），**不重新冻结**。
- **复用理由**：该文件同时满足 §4.2 的三项硬要求 ——
  ① C0/E1/E2 **共用同一批候选句**；② 每条**含 span**（`span_start`/`span_end`）；
  ③ **三协议各 40 条**（实测 rtsp 40 / sip 40 / smtp 40）。
- **差异说明**：既有冻结文件**不含 `section_no_path`**（章节号链），而
  `rule_id` 派生需要它 ⇒ 按 `(protocol, text, span_start)` 与
  `extract_constraint_candidates()` 新鲜抽取做**确定性 join** 补齐，
  实测命中 **120/120** 条
  （未命中 0 条）。
  ⚠ **不得**用 `section_no.split(".")` 代替 —— 实测仅 29/120 与真值一致。
- 实验内副本落在 `derived/exp_semantic_gain/candidates_frozen.jsonl`
  （md5 `90ee8994f0fa028ad5aca9fecb3c1af0`）；**`derived/exp_semantic/` 全程只读**。

### 4.4　LLM 调用

- 模型/温度/提示词：**与影子实现完全一致**（`DeepSeekClient` +
  `core.fused.rfc_extractor._PROMPT_CONSTRAINT`，temperature 0.2，max_tokens 3000）。
- **缓存键** = `sha256(candidate_text + prompt_version + model)`，
  `prompt_version = rfc-constraint-prompt-v1`；缓存文件
  `derived/exp_semantic_gain/llm_cache.jsonl`（**不含任何凭据**）。
- C0 与 E1 的 LLM 兜底**共用**该缓存 ⇒ 同候选只调一次。
- LLM 失败（网络/额度）时**如实记录失败条数与原因**，并继续跑完不依赖 LLM 的部分
  （E2 消融组、M3/M4/M5/M6/M7），在结果中标注哪些指标受限。

### 4.5　不触碰 rq3/rq4 语料（§4.6 第 1 条）

- **不调用** `scripts/seedgen.py`、`scripts/rq3_build_corpus.py`、`scripts/corpus_gate.py`。
- 产物只落在 `derived/exp_semantic_gain/` 与 `docs/semantic_gain_results.md`。

### 4.6　判定口径（指标定义 M1~M7）

| 指标 | 定义（口径） | 目标 |
|---|---|---|
| **M1 可执行率** | E1/E2：`len(rules) / (len(rules) + len(candidates))`（= 可执行规则数 ÷ 候选句数，逐候选归因）；C0：**自由文本能否解析出 operator**（判据：能否从 `legal_boundary` 的 `legal`（失败则 `illegal`）机械解析出 operator，数值型算子还须抓到操作数）。**三个组分母同为 120 条候选句**。 | E1 ≥ C0 + **15 个百分点**（成立）/ +5（部分）/ <+5（不成立） |
| **M2 规则 P/R/F1** | 对**独立人工标注集**（holdout）的 P/R/F1 | ≥ 0.70（holdout） |
| **M3 证据可验证率** | `validated=True` 的比例（`validated` 取**真实的区间核对结果**） | **= 100%** |
| **M4 显式性纯净度** | `explicitness == "explicit"` 的规则中原文确实含 MUST/SHALL/REQUIRED 的比例 | **= 100%** |
| **M5 MAY 误升率** | 原文**有效规范强度**为 MAY/OPTIONAL（取最强动词，与 `core.fused.semantic.detect_modality` 同口径）却被标为 executable 的比例 | **= 0%** |
| **M6 rule_id 幂等性** | 同一批候选句重复抽取 N 次（N ≥ 2），`rule_id` **集合**是否完全相同 | **完全相同** |
| **M7 拒绝原因分布** | 候选按 `reject_reason` 的直方图（观测项） | 观测项 |

**C0 可判定率的判定实现**：单函数 `probe_operator()`（`scripts/exp_semantic_gain.py`），
有序模式表（中文 + 英文），**C0 的可判定率与 E1 的 LLM 兜底共用同一函数** ⇒ 两个口径同源。

### 4.7　本轮**已知不可计算**的项（预登记）

- **M2（本轮不可计算）**：人工标注集当前不可用作最终评测集
  —— `derived/exp_semantic/truth/` 120 条中**仅 3 条已标注、117 条待标**（`pending` 占位），
  且已标注记录**只含标注者 A**，**缺真人标注者 B ⇒ Cohen's κ 无法计算**。
  ⇒ **绝不**用这 3 条、也**绝不**用规则自身推导出的「伪标注」冒充人工标注集算 F1。
- **C0 组在同一标注集上的 F1**：同一原因 ⇒ **不可计算**（§4.5 要求必报，标为不可计算并说明原因）。
- **综合判定**：因 M2 不可计算 ⇒ 综合判定只能写「**暂不可判定**」；
  M1/M3/M4/M5/M6/M7 的实测值只支持「表达层升级是否带来可执行性收益」这一部分结论，
  「知识质量收益（F1）」须等标注集定稿后再评。

## 5　结果

**结果待填：实验尚未执行。**
