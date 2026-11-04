# B-10 实验结果（里程碑 B 出口闸门）

- 生成时间：`2026-11-02 06:02:39`
- 候选集：`derived/exp_semantic_gain/candidates_frozen.jsonl`（md5 `b392118d5070f6a68d55d105d04aae40`，源 `derived/exp_semantic/candidates_frozen.jsonl` md5 `6060457e78f253699fcf2da8dc343733`）
- 候选句总数：**120**（{'rtsp': 40, 'sip': 40, 'smtp': 40}）
- LLM：实际调用 **120** 次，缓存命中 **0** 次，失败 **0** 次

> ★ 本文件只放**结果**；预登记在 `docs/semantic_gain_report.md`（实验前定稿）。
>
> ★ **证据链**：预登记提交 = `3c70731`（`feat(b-10): 预登记冻结 + 实验脚本`）。
> 该提交**只含预登记与脚本、不含任何实测结果**（复核：预登记文件 grep 实测百分比/条数 = 0 命中，
> 121 行）⇒ **git 历史本身即「预登记先于结果」的证明**，无需依赖文件 mtime。
> 本结果文件由**后续独立提交**落地，预登记文件自 `3c70731` 起**再未被修改**。

## 1　M1 可执行率

| 协议 | 候选句 | C0 可判定 | C0 可判定率 | E1 可执行规则 | E1 可执行率 | E2 可执行规则 | E2 可执行率 | E1−C0 (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rtsp | 40 | 8 | 20.00% | 7 | 17.50% | 4 | 10.00% | -2.50 |
| sip | 40 | 7 | 17.50% | 6 | 15.00% | 3 | 7.50% | -2.50 |
| smtp | 40 | 5 | 12.50% | 1 | 2.50% | 0 | 0.00% | -10.00 |
| TOTAL | 120 | 20 | 16.67% | 14 | 11.67% | 7 | 5.83% | -5.00 |

- C0「可判定率」判定实现：`scripts/exp_semantic_gain.py::probe_operator()`（有序模式表，中英双语；C0 与 E1 的 LLM 兜底**共用**同一函数）。
- C0「可判定率」主口径 = 能解析出 operator（与 §4.2 口径一致）。

| 协议 | C0 可判定率（主口径） | 其中数值型算子且抓到操作数 | 其中存在性算子（present/absent，本就无操作数） |
|---|---:|---:|---:|
| rtsp | 20.00% | 5.00% | 15.00% |
| sip | 17.50% | 2.50% | 15.00% |
| smtp | 12.50% | 5.00% | 7.50% |
| TOTAL | 16.67% | 4.17% | 12.50% |

⚠ **「数值型算子且抓到操作数」这一列不是更严的同口径指标**，而是主口径的**子集**：存在性算子（`present`/`absent`）按定义**不需要操作数**，把它判为不可判定对 C0 不公平。⇒ **判定口径只用主口径**；该列仅作参考。

## 2　M2 规则 P/R/F1 —— **不可计算**

### 2.1　M1 差异的归因拆解（为什么 E1 与 C0 不等）

| 协议 | 两者皆规则 | 仅 C0 可判定 | 仅 E1 规则 | 皆否 | 仅 C0 可判定且**原文无规范动词** |
|---|---:|---:|---:|---:|---:|
| rtsp | 5 | 3 | 2 | 30 | 1 |
| sip | 5 | 2 | 1 | 32 | 2 |
| smtp | 1 | 4 | 0 | 35 | 2 |

**读法（诚实说明）**：

- 「仅 C0 可判定」= C0 的**自由文本**里能解析出算子，但 E1 **未**产出规则 —— 逐条原因见下表。
- 「仅 C0 可判定且**原文无规范动词**」是**关键的一类**：C0 判为可判定，但 **RFC 原句里根本没有 MUST/SHALL 等规范动词** ⇒ 是 LLM 在中文改写里**幻觉出了规范力**。这类项 C0 计入可判定、E1 按 C3（`non_normative_kind`）正确拒绝 ⇒ **C0 的可判定率被 LLM 幻觉虚高**。
- 「仅 E1 规则」= 规则表在**RFC 原文**上命中了算子，而 C0 的中文自由文本里没有可解析的算子 ⇒ **两层模型从原文取证的优势**。

逐条明细（仅 C0 可判定的条目）：

| 协议 | candidate_id | E1 拒绝原因 | 阶段A | 阶段B | 原文 modality | C0 算子 |
|---|---|---|---|---|---|---|
| rtsp | `rtsp-6b0abdbbee5a` | `field_unbound` | `operator_unresolved` | `field_unbound` | mandatory | `absent` |
| rtsp | `rtsp-931303084a4e` | `non_normative_kind` | `non_normative_kind` | `non_normative_kind` | none | `present` |
| rtsp | `rtsp-97d6818e2146` | `field_unbound` | `field_unbound` | `field_unbound` | recommended | `le` |
| sip | `sip-7e0210b35d55` | `non_normative_kind` | `non_normative_kind` | `non_normative_kind` | none | `present` |
| sip | `sip-b7849cf998af` | `non_normative_kind` | `non_normative_kind` | `non_normative_kind` | none | `eq` |
| smtp | `smtp-42e625694616` | `non_normative_kind` | `non_normative_kind` | `non_normative_kind` | none | `le` |
| smtp | `smtp-4be41b9657d1` | `field_unbound` | `operator_unresolved` | `field_unbound` | mandatory | `absent` |
| smtp | `smtp-98738dfebfd9` | `non_normative_kind` | `non_normative_kind` | `non_normative_kind` | none | `gt` |
| smtp | `smtp-e9fe203045cc` | `field_unbound` | `operator_unresolved` | `field_unbound` | mandatory | `absent` |

> 标注集不可用作最终评测集：derived/exp_semantic/truth/ 共 120 条，其中已标注 3 条、待标（pending 占位）117 条；已标注记录只含标注者 ['A']（1 人）⇒ 缺第二名真人标注者，Cohen's κ **无法计算**；且 holdout 仅 20 条、其中已标注 1 条。⇒ M2（规则 P/R/F1，对 holdout）**本轮不可计算**。

> §4.5 要求同时给出「C0 组在同一标注集上的 F1」；因同一标注集当前不可用（见 M2.reason），**C0 的 F1 本轮同样不可计算**，此项**不得省略、也不得伪造**。

- 标注集现状：总计 120 条，已标注 3 条，待标 117 条；标注者 {'A': 3}。
- holdout：共 20 条，其中已标注 1 条。
- Cohen's κ：**无法计算**（缺第二名真人标注者）。

## 3　M3 / M4 / M5

| 组 | 协议 | 规则数 | M3 证据可验证率 | explicit 规则 | M4 纯净度 | M5 MAY 误升率 | explicit 集合 == MUST 集合 |
|---|---|---:|---:|---:|---:|---:|:---:|
| E1 | rtsp | 7 | 100.00% | 5 | 100.00% | 0.00% | 是 |
| E1 | sip | 6 | 100.00% | 5 | 100.00% | 0.00% | 是 |
| E1 | smtp | 1 | 100.00% | 0 | 0.00% | 0.00% | 是 |
| E1 | TOTAL | 14 | 100.00% | 10 | 100.00% | 0.00% | 是 |
| E2 | rtsp | 4 | 100.00% | 3 | 100.00% | 0.00% | 是 |
| E2 | sip | 3 | 100.00% | 3 | 100.00% | 0.00% | 是 |
| E2 | smtp | 0 | 0.00% | 0 | 0.00% | 0.00% | 是 |
| E2 | TOTAL | 7 | 100.00% | 6 | 100.00% | 0.00% | 是 |

- M4 主口径：原文含 MUST/SHALL/REQUIRED（大小写不敏感，与 `core.fused.semantic.detect_modality` 同口径）。
- M5 主口径：原文**有效规范强度**为 optional（MAY/OPTIONAL 为最强动词）。
- 「explicit 集合 == MUST 集合」即**辅助命题 B-3**（不多不少）。

## 4　M6 rule_id 幂等性

- 重复抽取 **3** 次（E2 口径：纯规则表 ⇒ 完全确定性），**三协议全跑**。
- 三协议全部轮次 rule_id 集合**完全相同**：**是**。

### rtsp

- 重复 3 轮，全部轮次集合相同：**是**（4 条规则）。
- 第 1 轮 rule_id 集合（4 条）：`['r455b41f6c67874e8', 'r46f46d7984b68d0e', 'r48dd6863ab61fa57', 'rdac451febf1bad1a']`
- 第 2 轮 rule_id 集合（4 条）：`['r455b41f6c67874e8', 'r46f46d7984b68d0e', 'r48dd6863ab61fa57', 'rdac451febf1bad1a']`
- 第 3 轮 rule_id 集合（4 条）：`['r455b41f6c67874e8', 'r46f46d7984b68d0e', 'r48dd6863ab61fa57', 'rdac451febf1bad1a']`
- 轮 1 vs 轮 2：仅在 A=[]，仅在 B=[]，相同=True
- 轮 1 vs 轮 3：仅在 A=[]，仅在 B=[]，相同=True
- 轮 2 vs 轮 3：仅在 A=[]，仅在 B=[]，相同=True

### sip

- 重复 3 轮，全部轮次集合相同：**是**（3 条规则）。
- 第 1 轮 rule_id 集合（3 条）：`['r40fe56d8ba724097', 'r8c7c27ff4c807d85', 'rfbc91afe5aca7b3d']`
- 第 2 轮 rule_id 集合（3 条）：`['r40fe56d8ba724097', 'r8c7c27ff4c807d85', 'rfbc91afe5aca7b3d']`
- 第 3 轮 rule_id 集合（3 条）：`['r40fe56d8ba724097', 'r8c7c27ff4c807d85', 'rfbc91afe5aca7b3d']`
- 轮 1 vs 轮 2：仅在 A=[]，仅在 B=[]，相同=True
- 轮 1 vs 轮 3：仅在 A=[]，仅在 B=[]，相同=True
- 轮 2 vs 轮 3：仅在 A=[]，仅在 B=[]，相同=True

### smtp

- 重复 3 轮，全部轮次集合相同：**是**（0 条规则）。
- 第 1 轮 rule_id 集合（0 条）：`[]`
- 第 2 轮 rule_id 集合（0 条）：`[]`
- 第 3 轮 rule_id 集合（0 条）：`[]`
- 轮 1 vs 轮 2：仅在 A=[]，仅在 B=[]，相同=True
- 轮 1 vs 轮 3：仅在 A=[]，仅在 B=[]，相同=True
- 轮 2 vs 轮 3：仅在 A=[]，仅在 B=[]，相同=True

## 5　M7 拒绝原因分布

### E1

| 协议 | 拒绝原因分布 |
|---|---|
| rtsp | {'field_unbound': 4, 'non_normative_kind': 12, 'operator_unresolved': 16, 'optional_modality': 1} |
| sip | {'non_normative_kind': 7, 'operator_unresolved': 26, 'optional_modality': 1} |
| smtp | {'field_unbound': 2, 'non_normative_kind': 4, 'operator_unresolved': 31, 'optional_modality': 2} |
| **合计** | {'field_unbound': 6, 'non_normative_kind': 23, 'operator_unresolved': 73, 'optional_modality': 4} |

### E2

| 协议 | 拒绝原因分布 |
|---|---|
| rtsp | {'field_unbound': 4, 'non_normative_kind': 12, 'operator_unresolved': 19, 'optional_modality': 1} |
| sip | {'non_normative_kind': 7, 'operator_unresolved': 29, 'optional_modality': 1} |
| smtp | {'non_normative_kind': 4, 'operator_unresolved': 34, 'optional_modality': 2} |
| **合计** | {'field_unbound': 4, 'non_normative_kind': 23, 'operator_unresolved': 82, 'optional_modality': 4} |

## 6　LLM 调用统计

- 实际 LLM 调用：**120** 次
- 缓存命中：**0** 次
- 本次运行前**已存在**的缓存条目（上一轮已付费）：**0** 条
- 缓存文件内**去重后**的响应总数：**120** 条（= 不同候选句数；C0 与 E1 共用 ⇒ 同一候选句只调一次 LLM）
- 失败：**0** 次
- 缓存文件：`derived/exp_semantic_gain/llm_cache.jsonl`（缓存键 `sha256(candidate_text + prompt_version + model)`，`prompt_version=rfc-constraint-prompt-v1`，`model=deepseek-chat`）

## 6.1　运行间方差（LLM 非确定性）

- 上一次运行：`2026-11-02 05:59:37`（该次实际 LLM 调用 120 次）

| 指标 | 上一次 | 本次 | 差 |
|---|---:|---:|---:|
| C0 可判定率 % | 19.1667 | 16.6667 | -2.50 |
| E1 可执行率 % | 13.3333 | 11.6667 | -1.67 |
| E2 可执行率 % | 5.8333 | 5.8333 | +0.00 |
| E1−C0 (pp) | -5.8334 | -5.0 | +0.83 |

- 缓存命中 ⇒ 两次数值完全相同（抖动 0）；冷缓存重跑 ⇒ 抖动来自 LLM 温度 0.2 的非确定性。

## 7　综合判定

> **暂不可判定** —— M2 本轮**不可计算**（见 §2）。

- M1（E1 − C0 = -5.00 个百分点）：落「不成立」档（E1 < C0 + 5 个百分点）。
  - **档位稳定性**：上一次冷跑 E1−C0 = -5.83 pp（不成立档），本次 -5.00 pp（不成立档） ⇒ **两次落在同一档**，说明本轮 M1 的**档位结论对 LLM 抖动稳健**（抖动幅度见 §6.1）。

  ⚠ **M1 的诚实解读**（见 §2.1 归因拆解）：本轮 E1 的可执行率**低于** C0 的可判定率，但这**不等于**「两层模型更差」。原因有二：

  ① **C0 的可判定率被 LLM 幻觉虚高**：C0 判为可判定的条目中，有一部分的 **RFC 原句里没有任何规范动词** —— 是 LLM 在中文改写里**幻觉出了规范力**，而 C0 的自由文本照样能被解析出算子。E1 按 C3（`non_normative_kind`）把这类**正确拒绝**了 ⇒ **C0 的分子含「幻觉项」**。
  ② **两者的分母/门槛不同**：C0 只需「文本里能解析出算子」；E1 还要过 C2（区间核对）、C3（证据类型）、C6（字段绑定）、可选性闸门等 —— 这正是两层模型的设计意图（**不污染**）。

  ⇒ 因此本轮 M1 应读作：**「按『规则表+闸门』的严格口径，E1 只覆盖 11.67% 的候选句；而 C0 的『可判定』里有相当比例来自 LLM 改写时的幻觉规范力」** —— **不能**读作「表达层升级没有收益」。真正的知识质量收益（M2/F1）仍待标注集定稿后评。
- M3 E1 = 100.00%（目标 100%）；M4 E1 = 100.00%（目标 100%）；M5 E1 = 0.00%（目标 0%）；B-3（explicit 集合 == MUST 集合）= 成立。
- M3 E2 = 100.00%（目标 100%）；M4 E2 = 100.00%（目标 100%）；M5 E2 = 0.00%（目标 0%）；B-3（explicit 集合 == MUST 集合）= 成立。
- M6（rule_id 幂等性，三协议 × 3 轮）：全部完全相同。

- 按 §4.5：M2 缺失 ⇒ **不得**宣告「收益成立」或「收益不成立」，综合判定只能是「**暂不可判定**」。
- M1/M3/M4/M5/M6/M7 的实测值**已足以支持**「表达层升级是否带来可执行性收益」这一部分结论；「知识质量收益（F1）」这一部分要等标注集定稿后再评。
- **C0 组在同一标注集上的 F1** 同样不可计算（§4.5 要求必报，此处如实标注为不可计算并说明原因，不省略、不伪造）。



---

## ★ 批次 2 的 M7 分布正式复测（2026-11-03）

> ★ **前提补齐**：`semantic.sanitize_rule()` 此前**从未接入** B-10 链路
>   ⇒ 本次先把 `sanitize_rule()` 接进 `scripts/exp_semantic_gain.py` 的规则转换
>   （被拦者**落候选库**并记 `reject_reason`，**不静默丢弃**），并新增
>   `--no-sanitize` 开关以便做「基线 vs +sanitize」对照。
> ★ **零成本**：两轮都复用既有 `llm_cache.jsonl` ⇒ **本次未调 LLM、未花 API 成本**。
> ★ 对比工件：`qa/exp/batch2_gain.json`。
> ★ **未覆盖生产产物**：两轮结果写在临时目录，**未**覆盖
>   `derived/exp_semantic_gain/`（该目录被 `build_hub._republish_rules` 读取
>   ⇒ 覆盖会改变中枢 `legal_boundary` 桶 ⇒ 改变种子语料）。

### M7 拒绝原因分布（基线 → +sanitize）

| 组 | 拒绝原因 | 基线 | +sanitize | Δ |
|---|---|---|---|---|
| E1 | **empty_subject** | 0 | **9** | **+9 ← 新增** |
| E1 | field_unbound | 6 | 6 | 0 |
| E1 | non_normative_kind | 23 | 23 | 0 |
| E1 | operator_unresolved | 73 | 73 | 0 |
| E1 | optional_modality | 4 | 4 | 0 |
| E2 | **empty_subject** | 0 | **5** | **+5 ← 新增** |
| E2 | field_unbound | 4 | 4 | 0 |
| E2 | non_normative_kind | 23 | 23 | 0 |
| E2 | operator_unresolved | 82 | 82 | 0 |
| E2 | optional_modality | 4 | 4 | 0 |

### 判定（对齐方案 §3.2 验收）

- ✅ **「M7 分布中出现新的拒绝原因计数且可解释」** —— `empty_subject`
  E1 +9 / E2 +5，且**其它四类拒绝原因计数全部不变** ⇒ sanitize 只动它该动的那一类。
- ✅ **`gate_exercised` 不变** —— M3/M4/M5 与基线**完全一致**。
- ✅ **幂等性不变** —— M6（三协议 × 3 轮 rule_id 集合全同）与基线一致。
- ✅ **全量护栏不漂移**。
- ⚠ **M1 反而下降**（E1 可执行率 11.67% → 4.17%）：这**不是**收益，而是
  「**去掉了假阳性**」的证据 —— 被拦的是**结构合法但语义无效**的规则
  （空 subject ⇒ 投影不出任何桶 ⇒ 无效负载）。
- ⚠ 按 §4.5，**M2 不可计算 ⇒ 不得宣告「收益成立/不成立」** ⇒ 综合判定仍是
  「**暂不可判定**」。与方案预判一致：sanitize 只处理「空值/自指」类，
  对占比最大的 `operator_unresolved`（73/106 = 68.9%）**帮不上**
  ⇒ 真正的知识质量收益仍待批次 4（CoT / 领域提示）。
