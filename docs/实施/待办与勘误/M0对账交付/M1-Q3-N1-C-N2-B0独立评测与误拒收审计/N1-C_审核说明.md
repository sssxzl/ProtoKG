# N1-C · 独立人工评测 · 审核说明

> ★ **阶段状态：评测集已冻结，等待人工真值**
> ★ 本批**不得**由 Agent / LLM 自动填写；★ 标签必须由**真实独立人工**提供

---

## 一、★ 本批是什么

★ **N1-C = 第二批独立人工评测集**（★ 50 条）
★ 与 N1-A（第一批 50 条）共同覆盖 **100 条 `evidence_supported` 候选**
★ ★ **抽样方式：★ 机械提取**（★ `population.jsonl` 中 `not_sampled_in_frame` 全集）⇒ ★ **未按错误类型挑选**

---

## 二、★ 盲审文件（三份）

| 文件 | 行 × 列 | 说明 |
|---|---|---|
| `N1-C_盲审标注表_A.csv` | 50 × 37 | ★ 审核者 A |
| `N1-C_盲审标注表_B.csv` | 50 × 37 | ★ 审核者 B |
| `N1-C_仲裁表.csv` | 50 × 8 | ★ 第三位人类审核者仲裁 |

★ ★ **盲审文件只含**：★ 候选字段 + ★ **真实 RFC 原文证据**（★ 绝对行号 / 锚点行 / 证据句 / ±6 行上下文 / RFC SHA256）
★ ★ **不含**：★ 模型状态、★ 前一轮错误归因、★ 建议结论、★ 任何 L2 结果（★ 已做列级泄漏检查：0 处）

---

## 三、★ 十项标注（★ 与 N1-A 完全一致 ⇒ ★ 两批可比）

| # | 列 | 说明 |
|---|---|---|
| 1-7 | `★ A:subject` / `action` / `object` / `strength` / `polarity` / `condition` / `exception` | ★ 主体（含**指代解析后的实际承担者**）/ 动作 / 对象 / 强度 / 极性 / 条件 / 例外<br>★ `condition` / `exception` 无则 `null`；★ ★ **`condition` 不得填整条 constraint** |
| 8 | `★ A:evidence_support` | ★ `supported` / `partially_supported` / `contradicted` / `evidence_insufficient` |
| 9 | `★ A:truth_label` | ★ **独立语义真值**：`valid_confirmed` / `valid_rejection` / `pending_insufficient_evidence` / `uncertain_requires_human` |
| 10 | `★ A:review_note` | ★ 独立审核理由 |

★ ★ **不要**判断 `false_confirmation` / `false_rejection`（★ 那两个由汇总脚本结合隐藏模型状态自动生成）

---

## 四、★ 证据列怎么读

| 列 | 含义 |
|---|---|
| `★ raw_span` / `★ resolved_span` / `★ span_mode` | ★ 按 M1-Q2 契约解析的锚点（★ `absolute` / `relative`） |
| `★ 锚点行原文（★ 合法可为空）` | ★ 锚点行原文（★ **可能为空，★ 合法**） |
| `★ 证据句（含 entity 的非空行）` | ★ ±3 内含 entity 的非空行（★ 锚点空白时的证据载体） |
| `★ RFC 原文上下文（锚点 ±6 行）` | ★ 同版本 RFC 原文（★ 判断用这个） |
| `★ entity / normative_subject / action / object / strength`（LLM 候选） | ★ **模型产出的字段**（★ 待核对，★ 不是真值） |
| `★ LLM meaning` / `★ LLM constraint` | ★ **生成文本，★ 不是 RFC 原文**（★ 勿当作原文引用） |
| `★ 推导 polarity` | ★ 由 strength 推导（★ 供核对） |

---

## 五、★ 发放规则

| # | 规则 |
|---|---|
| 1 | ★ **A 与 B 各自独立填写**；★ **不查看对方标签**，★ **不查看隐藏的模型结论** |
| 2 | ★ **分歧样本交第三位人类审核者仲裁**（★ 填 `N1-C_仲裁表.csv`） |
| 3 | ★ **仲裁须记录**：★ **匿名审核者 ID**、★ **审核日期**、★ **仲裁理由**（★ 三者缺一 ⇒ ★ 该条仲裁来源待核实） |
| 4 | ★ **未完成标注不得纳入质量率分母** |
| 5 | ★ **所有人工标签与审核者信息保留审计记录**（★ 原始文件不覆盖） |
| 6 | ★ **不得用 LLM 代替人工标注** |

---

## 六、★ 关键约定（★ 沿用 N1-A 口径，★ 避免两批口径漂移）

★ **「义务成立性」与「字段完整性」分两层**：
① 第一层 = `truth_label`（★ 原文是否构成该候选声称的规范义务）
② 第二层 = 字段完整性（★ ①全部正确 / ②缺关键字段 / ③部分字段错 / ④义务不成立 / ⑤证据不足）

★ ★ **`valid_confirmed` ≠ `fully_supported`**（★ N1-A 实测：24 条成立中仅 7 条 fully supported）
★ ★ **对无 RFC 2119 关键词但具「条件→行为」结构的陈述式规范句**：★ N1-A 仲裁已确立
★ 「★ 规范效力由陈述式句式承载」⇒ ★ **请按语义判断，★ 不要因缺 MUST 就判不成立**
