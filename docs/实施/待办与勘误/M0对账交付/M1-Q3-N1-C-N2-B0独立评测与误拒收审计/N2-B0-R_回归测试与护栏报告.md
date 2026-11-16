# N2-B0-R · 回归测试与护栏报告

> ★ 日期：2026-11-16 ｜★ **0 次 LLM 调用**

---

## 一、★ 反证边界回归测试（★ §六 八个场景）

★ 文件：`tests/extraction/test_n2b0r_tristate_v1.py`（★ **14 个测试，全通过**）

| # | 场景 | 断言 |
|---|---|---|
| ① | ★ MUST 与 SHOULD **同段但约束不同动作** | ★ **不是矛盾**（≠ contradicted） |
| ② | ★ MUST 与 SHOULD **同句但约束不同主体** | ★ **不是矛盾** |
| ③ | ★ 同一命题存在**不同强度表述** | ★ uncertain（★ **强度不一致 ≠ 矛盾**） |
| ④ | ★ 同一命题**明确肯定与否定冲突** | ★ **contradicted** ＋ 记录反证句/行号/跨度 |
| ⑤ | ★ **不同条件下的义务** | ★ 条件从句里的 not（★ 「that is not configured」）**不构成反证** |
| ⑥ | ★ **跨句代词或条件未解析** | ★ uncertain（★ 对象为代词、★ 跨句未解析） |
| ⑦ | ★ **缺少强度字段** | ★ **不得凭推测确认**（★ V1 **无 confirmed 出口**） |
| ⑧ | ★ **无明确反证的词形不匹配** | ★ supported（★ 词形等价）或 uncertain（★ 词缺失），★ **绝不 rejected** |

★ ★ 附加断言：
★ **子句切分生效**（★ `that/if/which/and/…` 切分）｜★ **否定紧邻判定**（★ 词距 ≤ 2）
★ **V0 仍在且可独立运行**（★ 未被覆盖）｜★ **V1 源码无 LLM 客户端**（★ 0 次调用）

### 1.1 ★ 测试暴露并修正的两个真实缺陷

| # | 缺陷 | 修法 |
|---|---|---|
| ① | ★ V1 **漏了 V0 已有的「合法缺省不阻塞」规则**（★ strength 无值 ⇒ ★ 错误阻止 supported） | ★ 补上 |
| ② | ★ V1 **未查「候选 strength 极性 vs 原文同子句强度极性」**（★ 原文 SHOULD NOT 而候选 SHOULD ⇒ ★ 被误判 contradicted） | ★ 新增一致性检查 ⇒ 不一致 ⇒ uncertain |

⇒ ⇒ ★ **★ 这两项都不是「为让样本通过而设的特例」⇒ ★ 判据本身更严格、更完整**

---

## 二、★ 护栏结果

```
5 failed / 1494 passed / 227 skipped
★ 新增 0 / 消失 0
★ 既有 5 条失败**身份未变**：
  tests/downstream/test_action_seq_hardening.py::…::test_action_seq_seeds_are_rewritten_by_seedgen
  tests/downstream/test_generic_danger.py::test_self_loop_has_describe_prefix_and_session
  tests/downstream/test_message_instance_migration.py::test_migrated_instances_are_labelled_profile
  tests/downstream/test_seed_legality.py::test_full_source_mode_unaffected
  tests/graph/test_graph_communities.py::test_communities_not_collapsed_to_one
```
★ 编码卫生：✅ **达标**｜中枢与种子：**逐字节一致**（★ 本轮未触碰）

---

## 三、★ 版本冻结哈希（★ §八 要求）

| 文件 | SHA256 |
|---|---|
| ★ V0 冻结判据 | `89dbd535bad548e90afe0fe96677a6c23af917fa47e7d1f999bfe83ce0d1d419` |
| ★ V1 修正判据 | `39703e4f086a12cdafbfcde5148ce6d306e41e00c1769507d0c3e97e190d8e31` |
| ★ V0/V1 对账脚本 | `4ecd9a32786859b5ba946447978646278a7829706e9e8376f42bbfeb323c4396` |
| ★ V0 重算脚本 | `f3c5641f88bd63894e07716d74d946e9ab53567a7590111849836e5d3dd67561` |
| ★ 三案例上下文脚本 | `8eb2f1388a0018163dd065462769db048ecd809800f2692c86de28d562cddf87` |
| ★ V1 回归测试 | `65cbc3fbbc712da8b89703e95db96efa3956a8ac0d7ce19d52d0c92a5aad6896` |
| ★ V0/V1 逐候选对照 CSV | `b4f30b933b094c14009e86fc58b583dfac2fb37f0d9526e996d23fe02ac2f5ab` |
| ★ 反证判据修正说明 | `17b3fba3c6a2880246b399bc9974d8ea1a335533e9f259b6c1aac0f0c11975e7` |
| ★ 三条误拒案例核查 | `bfd5e9c825467bc7beecb349b701e36fe71b3d6ba0998e3a9a0ff80c17d30200` |
| ★ 风险与成本评估 | `d2f9d6a4a551860eaf2cbf864f703e7d01775e78f24412d6d73865fd391f9d2b` |

★ **冻结基线**：★ V1 代码、配置、测试与产物哈希已固定
★ ⇒ ★ **待 N1-C 独立人工审核完成后，方可开展独立验证**
★ ⇒ ★ ★ **★ 不得将本轮开发集上的改善直接写为泛化性能提升**

---

## 四、★ 工程约束核对

| 约束 | 状态 |
|---|---|
| ★ 不调用 LLM | ✅ **0 次**（★ V1 源码无 LLM 客户端，★ 测试断言） |
| ★ 不修改生产代码和现有校验路径 | ✅ V0/V1 均在 `guard/_out/_n1c/`（★ **不进 `core/`**） |
| ★ 不修改原始 N1-B 人工标签 | ✅ |
| ★ 不修改 N1-C 评测包 | ✅（★ 未读取、未参考、未推测其人工真值） |
| ★ 不修改 FactID / 21 aspects / Rule Slot 身份 | ✅ |
| ★ 通道 J 继续影子 | ✅ |
| ★ 不发布新的 canonical 事实 | ✅（★ 本轮发布资格全部 false） |
| ★ 不改变正式中枢或种子 | ✅ **逐字节一致** |
| ★ 不修改已有护栏期望 | ✅ |
| ★ 护栏无新增失败 | ✅ **5 failed / 1494 passed，新增 0 / 消失 0** |
| ★ 所有结果保留原版与修正版，★ 可独立复算 | ✅ V0/V1 并行，★ 逐条 CSV 并列，★ 脚本可重跑 |

---

## 五、★ 修改文件与回滚

| 文件 | 改动 | ★ 回滚 |
|---|---|---|
| `guard/_out/_n1c/n2b0_tristate_v1.py` | ★ **新增**（★ V1 修正判据） | ★ 删除 |
| `guard/_out/_n1c/p07~p09*.py` | ★ **新增**（★ 重算 / 案例上下文 / V0-V1 对账） | ★ 删除 |
| `tests/extraction/test_n2b0r_tristate_v1.py` | ★ **新增**（★ 14 个测试） | ★ 删除 |
| `N2-B0-R_*`（5 份文档 + CSV + 哈希 + JSON） | ★ **新增** | ★ 删除 |
| `guard/_out/_n1c/n2b0_tristate.py`（★ **V0**） | ★ **未改**（★ 冻结保留） | —— |

★ **整体回滚**：★ 单提交 `git revert <提交哈希>`；★ **无生产代码改动 ⇒ 无需数据回滚**

---

## 六、★ 状态

> ★★ **「N2-B0-R 反证判据修正版影子实验完成，等待 N1-C 独立评估」**
> ★ ★ **不得宣布 N2-B 正式接入通过；★ 不得批准 N4/P1 扩量**
