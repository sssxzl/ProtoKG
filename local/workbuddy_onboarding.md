# workbuddy 入职包 — rag-chatafl

> 本文件是你的入口。每次开工**先读本文件**，再按「工作流」章节读其他文档。
> 落盘日期：2026-10-08

## 一、项目一句话

面向目标协议实现的协议模糊测试：五源知识（RFC / expert_note / vuln / traffic / source）
→ Fused Hub → RAG + LLM → `.raw` 种子 → AFLNet + live555 靶子。

## 二、当前状态（截至 2026-10-08）

- **Layer 0（v2 中枢核心）已完成**：6 个 `core/fused/*_v2.py` + 3 个 `fused_hub/schema/v2/` 注册表
- **全量 pytest**：3005 passed / 8 skipped / 1 xfailed / 0 failed
- **v1 → v2 转换**：131 facts → 118 facts（合并 13 条）+ 27081 distinct evidence（保留率 100%）
- **Layer 1（rtsp Profile）未启动**
- **Layer 2（五源映射）未启动**
- **v2 产物未落盘**（决策未定）

**已知遗留（都在 `local/hub_contract_errata_backlog.md`，读它看细节）**：
- T2 目录越界（§14）
- traffic outlier evidence 体量（§15，14 fact 各 1000-5000 evidence）
- v2 产物未落盘
- fail-closed 未在真实 131 facts 上首跑

## 三、目录导航（按需读）

| 路径 | 是什么 |
|---|---|
| `local/agent_rules.md` | **硬约束（必读）** |
| `local/roadmap_next.md` | **当前下一步（必读）** |
| `local/workbuddy_onboarding.md` | 本文件 |
| `fused_hub/docs/fused_knowledge_hub_v2_design.md` | v2 设计真源 |
| `local/hub_contract_errata_backlog.md` | 已知遗留 |
| `local/project_handoff.md` | 项目恢复入口（部分过时） |
| `local/backup/step_v2_*/audit.txt` | 各步证据 |
| `core/fused/*_v2.py` | v2 中枢代码 |
| `tests/fused/v2/` | v2 测试 |
| `kb/` | 知识库（**只读**） |
| `derived/` | 派生产物（**不许写，除指定步**） |

## 四、硬约束（不可违反）

1. **`kb/` 默认只读**。任何写 `kb/` 必须先停、汇报、等授权
2. **失败即停**。任一步失败不继续、不自行修
3. **不自行假设**。契约未写、语义不明、两方案都合理 → 停
4. **每步写 audit**（`local/backup/step_<N>/audit.txt`，四项固定内容）
5. **每步备份**到 `local/backup/step_<N>/before/`
6. **pytest 一律 `pytest -n auto`**
7. **不改冻结文档**（`fused_hub/docs/` 下六份 `fused_*`）
8. **源隔离**：调一源（rfc / expert_note / vuln / traffic / source）不动他源
9. **量具自证**：探针/核查脚本首次运行前先自证（路径归一化、类型归一化、已知答案样本）
10. **报告实测不引用历史数字**——除非是基线，且基线与实测在同一步对比

## 五、工作流（每次开工按序做）

1. 读本文件（`workbuddy_onboarding.md`）
2. 读 `local/agent_rules.md`
3. 读 `local/roadmap_next.md`——找到「当前步骤」
4. 读 `local/backup/` 下最近一个 `step_*/audit.txt`——了解上次停在哪
5. 判断：
   - **可自决** → 执行（见 agent_rules「自主执行协议」章节）
   - **需裁定** → 停下，写清「待裁定项 + 选项 + 推荐 + 理由」，等用户
6. 执行 → 写 audit + 汇报（≤60 行）
7. 更新 `local/roadmap_next.md`——勾销完成项，写入下一项

## 六、汇报格式（固定）

```
本步目标：一句话
动作汇总：每步 PASS / FAIL
关键数值：实测值（不引用历史）
未决项：待裁定 / 待观察
下一步建议：一句话
```

≤60 行；过长时写详细到 `local/backup/step_<N>/detail.txt`，汇报只给摘要。