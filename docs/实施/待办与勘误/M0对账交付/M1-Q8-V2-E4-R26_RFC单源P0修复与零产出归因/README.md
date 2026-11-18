# R26 RFC 单源链路的 P0 影子修复与零产出归因 —— 交付索引

分支 `feature/r26-rfc-p0-fix-shadow`（从 main `65d162b` 建立）
本轮不修改生产代码、不覆盖正式中枢、不新增 LLM 调用；全部改动落在 `guard/_out/_n1c_v2/r26/` 的影子副本与脚本。

## 一、交付物

| # | 文件 | 内容 |
|---|---|---|
| 1 | `README.md` | 本索引：范围、复算命令、关键数字 |
| 2 | `R26_总体结论报告.md` | 五个任务的结论、证据与限制 |
| 3 | `R26_Evidence行号修复报告.md` | 任务 A：ABNF 与样例通道返回真实行号 |
| 4 | `R26_EvidenceID兼容与双读策略.md` | locator 变更对 EvidenceID 的影响与双读规则 |
| 5 | `R26_field_value影子修复验证.md` | 任务 B：合并结果写回保留条目的最小修复 |
| 6 | `R26_零产出逐文档归因.md` | 任务 C：19 份零产出文档的逐条归因 |
| 7 | `R26_零产出逐文档归因.csv` | 41 份实验文档的逐文档指标与归因 |
| 8 | `R26_来源身份与指标口径复核.md` | 任务 D：绑定率、82/86 与 20/22 三项口径 |
| 9 | `R26_三协议整链影子回归报告.md` | 任务 E：三协议完整链路影子回归 |
| 10 | `R26_改动与未改动清单.md` | 逐文件说明改了什么、没改什么 |
| 11 | `R26_EvidenceID兼容映射表.jsonl` | 262 条 Norm 的旧/新 locator 与 EvidenceID 判定 |
| 12 | `R26_来源身份核验.jsonl` | 262 条 Norm 的来源身份九字段核验 |
| 13 | `R26_Evidence定位形态逐条.jsonl` | 262 条 Norm 的定位形态与原文核对结果 |
| 14 | `R26_Evidence定位形态汇总.json` | 上者的按协议汇总 |

## 二、关键数字

| 指标 | 数值 | 口径 |
|---|---|---|
| 三协议 Norm 总数 | 262（smtp 63 / rtsp 107 / DHCPv4 92） | 影子抽取器，`llm=None` |
| 生产与影子 Norm 集合 | 完全一致，content 差异 0 | 同输入同参数逐条比对 |
| 带数字行号的 Norm | 214 / 262 = 81.7% | locator 为纯数字 |
| 行号落在非空原文 | 149 / 262 = 56.9% | 回到 `kb/<协议>/spec` 逐行核对 |
| 行号落在空行或分页 | 65 / 262 = 24.8% | 同上 |
| 仍为锚点名 | 27 / 262 = 10.3% | `@abnf` / `@samples` 之类 |
| 无定位符 | 19 / 262 = 7.3% | 全部来自 DHCPv4 |
| source 变化（任务 A 引起） | 43 条（smtp 27 / rtsp 16） | 锚点名改为行号 |
| 零产出文档 | 19 / 41 | 12 条 LLM 通道 + 7 条确定性抽取 |
| 来源身份绑定率 | 262 / 262 = 100% | 九字段清单 |
| 护栏 | 5 failed / 2070 passed / 0 errors / 239 skipped | 新增 0、消失 0 |

## 三、复算命令

全部脚本在 `guard/_out/_n1c_v2/r26/`，解释器固定 `E:/app/Anaconda3/python.exe`。

```bash
# 任务 A：行号化影子包与生产逐条比对
python guard/_out/_n1c_v2/r26/p02_run_shadow.py
python guard/_out/_n1c_v2/r26/p13_evidence_id_compat.py

# 任务 B：合成用例 + 真实语料
python guard/_out/_n1c_v2/r26/p14_field_value_fix.py
python guard/_out/_n1c_v2/r26/p18_fv_real.py

# 任务 C：零产出归因
python guard/_out/_n1c_v2/r26/p11_zero_attr_v2.py

# 任务 D：来源身份与口径复核
python guard/_out/_n1c_v2/r26/p12_source_identity_audit.py

# 任务 E：三协议整链回归（先跑 p15，再跑 p17 定位形态）
python guard/_out/_n1c_v2/r26/p15_pipeline_regression.py
python guard/_out/_n1c_v2/r26/p17_evidence_breakdown.py

# 护栏
python guard/run_guarded_pytest.py --out-dir guard/_out/_n1c_v2/r26/_guard
```

## 四、读前须知

1. 任务 E 的运行需要两份隔离工作副本（`_ci_work_prod`、`_ci_work_shadow`），已含 kb 三协议与冻结的 LLM 散文缓存；`p18` 依赖 `p15` 先执行。
2. 冻结散文缓存 `derived/cache/source_blocks/DHCPv4.prose.json` 是抽取输入的一部分。缺它时 DHCPv4 从 92 条降到 73 条，所有 DHCPv4 数字必须与该缓存状态一起引用。
3. 本轮无 `DEEPSEEK_API_KEY`，LLM 状态机通道整轮跳过；239 条 skipped 用例即由此产生，与代码改动无关。
