# R28 历史 Gold 复用与当前质量对账（R28-A 进行中）

> 依据：`docs/设计/知识源层/规范源/ProtoKG_RFC单源调试与验收固定计划_V1.0.md`
> 状态：R28-A 已完成文件级盘点与 8 份关键 Gold 登记；R28-B 未开始。

## 一、G0 核验（不重复推送）

| 项 | 结果 |
|---|---|
| main 完整 SHA | `0f99da8445ea093246824e62d1244b88732e009e` |
| 与 origin/main | 一致 |
| 三项修复是否已合入 | 是（`ec08370`、`5d17027`、`f3012f2`，另 `6459b14` 修 CI 重复键） |
| 合并提交 | `0f99da8`（PR #2） |
| PR 运行 | `44437120188`：4 个 Windows job 全部 success |
| main 运行 | `44437313936`：4 个 Windows job 全部 success |
| 远端分支 | 仅 `main`（一次性分支已删） |

受保护文件哈希（本轮实测）：

| 文件 | SHA256 |
|---|---|
| `derived/cache/source_blocks/rtsp.prose.json` | `1149a345a8d50fcd73eb88d26ba64dbba8dd0f85053d3f82e2698528d21d9697` |
| `derived/cache/source_blocks/DHCPv4.prose.json` | `558767f24bf2e80745567fbd0e417a8a38dfa5fe318822b1746e2c95e6fc5f49` |
| `derived/cache/source_blocks/dhcpv4.transitions.json` | `7e45a317b9de9a5e9b7bc30166c49f96b593c8b4d5ee8b2ce7fcde1318c49056` |
| `guard/baseline/ci_expected_failed_ids_windows.txt` | 见 `R28A_G0核验与资产规模.json` |
| `guard/baseline/expected_b_class_failed_ids.txt` | 同上 |
| `.github/workflows/ci.yml` | 同上 |

结论：G0 已完成，无需重复推送。main 作为 R28 基线冻结。

## 二、R28-A 盘点结果

| 项 | 数值 |
|---|---|
| 扫描范围 | `docs/实施/待办与勘误/M0对账交付/` 下 31 个 M1-Q3 目录 |
| 文件总数 | 440（csv / jsonl / json / xlsx / md / html） |
| 关键 Gold 登记 | 8 份（见 `R28A_Gold资产登记册.csv`） |
| 与计划数字的一致性 | V2-E4 队列 B 清单 130 行 = 121 条有效 + 9 条无目标片段，与计划一致 |

8 份登记的定位：

| 编号 | Gold | 条数 | 状态判断 |
|---|---|---|---|
| G-N1B | N1-B 人工真值 | 50 | 已用于开发，非独立 |
| G-N1C | N1-C 独立评测集 | 50 | 已揭盲，只能作历史回归 |
| G-B1 | V2-E4 队列 B | 121 + 9 | 片段级清点，可算可比片段内召回 |
| G-H3 | H3 候选 | 23 | 盲审后已揭盲 |
| G-H3S | H3 补充知识 | 5 | 与 H3 同批，不重复计 |
| G-R13 | R13 候选级分类 Gold | 57 | 分类维度可比 |
| G-R14 | R14 一次性事后评估 | 结果表 | 仅历史对照，不覆盖 |
| G-R19 | 原子 Gold v5 | 6 | 字段级可用，样本极小 |

规则遵守：

- 未把不同 Gold 的数量相加；
- 未重做任何人工裁定；
- 已揭盲样本（N1-C、H3）在登记册中明确标注，不得再当独立测试集；
- 原始标注与仲裁文件原位保留（440 文件清单见 `R28A_Gold资产登记册_原始文件清单.csv`）。

## 三、下一步（R28-B）

按计划只做对齐，不发放新审核：

1. 以 `G-R19`（6 条，字段级）与 `G-B1`（121 条，片段级）为起点，把 Gold 的 sample_id 映射到当前 `norm_id`。
2. 逐条打九类标签（exact_match / semantic_equivalent / partial_match / missing_extraction / incorrect_extraction / duplicate_knowledge / incompatible_version / outside_current_scope / unresolved）。
3. 只对「可比片段」计算召回，不外推到 41 份 RFC。

## 四、本轮未做

- 未发放 60 条 Norm / 6 份 RFC 的人工审核任务。
- 未启动 R29、R30。
- 未调用 LLM。
- 未修改任何 Gold 或抽取代码。
