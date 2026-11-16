# N1-B · 修改文件、护栏结果与提交哈希

> ★ 日期：2026-11-16 ｜★ 本轮 **0 次 LLM 调用**｜★ **未修改任何生产代码**

---

## 一、★ 本轮**未修改**的契约（★ 全部保持）

| 契约 | 状态 |
|---|---|
| 抽取 Prompt / 模型参数 / 已有抽取结果 | ★ **未改** |
| ★ **FactID** | ★ **未改** |
| ★ **21 aspects** | ★ **未改** |
| ★ **Rule Slot / Assertion 身份契约** | ★ **未改** |
| ★ **通道 J 影子模式** | ★ **未改** |
| 正式发布范围 | ★ **未扩大** |
| 正式知识中枢 / 种子 | ★ **未更新**（★ 逐字节一致） |
| 护栏期望集 | ★ **未改** |

---

## 二、★ 修改 / 新增文件

### 2.1 生产代码

★ **零改动**（★ 本轮为离线审查与质量分析）

### 2.2 交付目录（`N1-B人工真值与模型质量审查/`）

| 文件 | 内容 |
|---|---|
| `N1-B_人工真值冻结与一致性报告.md` | ★ 输入冻结、编码统一、真值冻结、一致性与 Kappa、字段归一化、仲裁身份 |
| `N1-B_模型语义质量评估报告.md` | ★ 口径、混淆矩阵、主口径敏感性、三项核心指标、第二层分类、字段准确率 |
| `N1-B_模型与人工混淆矩阵.csv` | ★ 两个口径的混淆矩阵 + 指标分母定义 |
| `N1-B_七字段一致性与错误归因.csv` | ★ 350 行（50 × 7）逐字段归因与修复点 |
| `N1-B_典型错误案例.md` | ★ 案例分类 + `@1#4` 重点复查（四问逐一回答） |
| `N1-B_抽样总体与统计适用范围.md` | ★ 总体/抽样框/未纳入对账、层内概率、适用范围与禁止外推项 |
| `N2-B_确认防护准入建议.md` | ★ 防护两面影响、分级设计、泛化限制、准入判定 |
| `N1-B_修改文件与验收记录.md` | ★ 本文件 |
| `scripts/p00~p10`（11 个） | ★ 可复算脚本 |
| `work_utf8/` | ★ UTF-8 工作副本（★ 与交付目录一致） |

★ **机器可读产物**：`N1-B_输入冻结与编码统一.json` / `N1-B_人工真值冻结.json` /
`N1-B_冻结人工真值.jsonl` / `N1-B_模型状态关联.json` + `…明细.jsonl` /
`N1-B_字段真值与第二层分类.json` + `…明细.jsonl` / `N1-B_模型质量指标.json` /
`N1-B_主口径敏感性.json` + `…逐样本.jsonl` / `N1-B_N2B防护评估.json` + `…逐样本.jsonl` /
`N1-B_逐样本对照.jsonl` / `N1-B_错误案例明细.csv` / `N1-B_字段归因.json` + `…明细.csv` /
`N1-B_编码归一与原件保管.json` / `N1-B_案例分类统计.json`

### 2.3 测试

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `tests/extraction/test_n1b_quality_stats.py` | ★ **14** | ★ 编码（GB18030/UTF-8）｜★ 缺失状态｜★ 重复 ID｜★ 标签冲突｜★ 字段缺省｜★ **分母异常（0 ⇒ N/A）**｜★ confirmed precision 分母｜★ pending 不计入误拒｜★ 总体对账｜★ **本阶段 0 次 LLM 调用** |
| `tests/extraction/test_n1_summary_script.py`（沿用） | 34 | ★ 上一阶段 |

---

## 三、★ 编码归一与原件保管（★ 关键处置）

★ **问题**：★ 审核者用 Excel 保存 ⇒ 三份表为 **GB18030** ⇒ **仓库不允许非 UTF-8**

| 项 | 处置 |
|---|---|
| ★ 原件（GB18030） | ★ 移至 `guard/_out/n1b/archive_gb18030/`（★ **不入库**），★ 哈希留档 |
| ★ 交付目录 | ★ 转 **UTF-8（LF、无 BOM）**，★ **逐字段差异 0**、★ 中文 3683/3691/1392 **全部保全** |
| ★ 人工标签内容 | ★ **零修改**（★ 字段差异 0 已验证） |
| ★ 记录 | ★ `N1-B_编码归一与原件保管.json` |

---

## 四、★ 护栏结果

```
5 failed / 1445 passed / 227 skipped
★ 新增 0 / 消失 0
★ 既有 5 条失败**身份未变**：
  tests/downstream/test_action_seq_hardening.py::…::test_action_seq_seeds_are_rewritten_by_seedgen
  tests/downstream/test_generic_danger.py::test_self_loop_has_describe_prefix_and_session
  tests/downstream/test_message_instance_migration.py::test_migrated_instances_are_labelled_profile
  tests/downstream/test_seed_legality.py::test_full_source_mode_unaffected
  tests/graph/test_graph_communities.py::test_communities_not_collapsed_to_one
```
★ 编码卫生：✅ **达标**（★ 混合行尾 0、★ 仓库内无 GB18030 残留）

---

## 五、★ 正式产物

| 目录 | 结果 |
|---|---|
| `derived/hub/` | ★ **逐字节一致** |
| `derived/seeds/` | ★ **逐字节一致** |

---

## 六、★ 提交哈希

| 提交 | 内容 |
|---|---|
| ★ **（见本轮末次提交）** | ★ N1-B 人工真值与模型质量审查（★ 文档 + 产物 + 测试 + 脚本） |

★ 回滚：★ 单提交 `git revert <提交哈希>`；★ **无生产代码改动 ⇒ 无需数据回滚**

---

## 七、★ 本轮的关键数字（★ 便于速查）

| 项 | 值 |
|---|---|
| ★ A/B truth_label 一致率 / Kappa | 49/50 = **0.9800** / **0.9599** |
| ★ A/B evidence_support 一致率 / Kappa | 46/50 = **0.9200** / **0.8654** |
| ★ 冻结真值 | valid_confirmed **24** / valid_rejection **26** |
| ★ 第二层 | ①12 ｜ ②9 ｜ ③3 ｜ ④26 |
| ★ **confirmed precision（单批次）** | ★ **N/A**（★ confirmed 样本 0） |
| ★ confirmed precision（口径 A/B/C） | **1.0000**（n=3 / 6 / 1） |
| ★ **错误拒收率** | ★ **11/12 = 91.67%**（CI 0.646~0.985） |
| ★ 有效知识被 pending 隔离 | 1/6 = 16.67% |
| ★ 有模型状态 / 无状态 | **32 / 18** |
| ★ 跨批次不一致（样本内） | **9**（★ 其中 6 条人工判成立） |
| ★ 现行放行的有效知识损失率 | ★ **87.5%（21 条）** |
| ★ 案例分布 | A 误拒 13 ｜ C 2 ｜ D 3 ｜ F 5 ｜ G 4 ｜ **B 误确认 0** |
