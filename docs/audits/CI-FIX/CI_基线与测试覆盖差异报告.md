# CI 基线与测试覆盖差异报告

> ★ 重采依据：**实测**，★ 附可复算原因与版本记录
> ★ 基线版本记录：`guard/baseline/CI_BASELINE_CHANGELOG.md`

---

## 一、★ 基线变化

| 项 | 原 | 新 | 变化原因 |
|---|---:|---:|---|
| ★ ubuntu failed | 70 | **5** | ★ 夹具恢复 + 中枢构建 |
| ★ windows failed | 67 | **5** | ★ 同上；★ 待真机校正 |
| ★ errors（两平台共用） | 29 | **0** | ★ 夹具恢复后收集错误归零 |

### 1.1 新基线内容（★ 5 条，★ 恰是已知的本地五项失败）

- tests/downstream/test_action_seq_hardening.py::TestActionSeqPostProcessing::test_action_seq_seeds_are_rewritten_by_seedgen
- tests/downstream/test_generic_danger.py::test_self_loop_has_describe_prefix_and_session
- tests/downstream/test_message_instance_migration.py::test_migrated_instances_are_labelled_profile
- tests/downstream/test_seed_legality.py::test_full_source_mode_unaffected
- tests/graph/test_graph_communities.py::test_communities_not_collapsed_to_one

★ ★ **★ 这 5 条就是 R21～R24 反复记录的「已知本地五项失败」**：
★ ★ ① corpus_gate 模块缺失；★ ② 中枢 claim 覆盖度不足；★ ③ ③ authority 语义变更；
★ ★ ④ transitions 择一策略变更；★ ⑤ dhcpv4 社区退化（★ 真实算法缺陷）。

---

## 二、★★ 差异的三类归因（★ 任务要求）

| 类别 | 条数 | 说明 |
|---|---:|---|
| ★ ① 因缺少夹具而产生的历史环境失败 | **0** | ★ 那 29 个 ERROR 模块**从未进入 failed 基线**；★ 它们属于 **errors 集合** |
| ★ ② 因 CI 未构建中枢而产生的历史环境失败 | **65** | ★ `load_fact_views()` 在 CI 上读不到 fact；★ 本地有中枢故不失败 |
| ★ ③ 真正的算法失败 | **5** | ★ 夹具与中枢都具备后仍失败 |
| ★ ④ 测试范围变化 | **0** | ★ 未删除、未跳过、未弱化任何测试 |

★ ⇒ ★ **★ 原基线 70 条 = 65 条「缺中枢」环境失败 + 5 条真正的算法失败。**
★ ⇒ ★ **原基线记录的是「缺夹具 + 缺中枢」的历史环境状态，★ 而非算法真实状态。**

---

## 三、★ 「errors 置空」不是放宽

★ 修复后实测 errors = **0**，★ 故基线置空。
★ ★ **★ 若将来再次出现收集错误，★ 护栏会立即判红（★ added > 0 ⇒ exit 1）**；
★ ★ 这比「把 29 写进允许集」严格得多。

★ 负例测试 NT-03 已实测该机制（★ 注入收集错误 ⇒ 护栏能检出）。

---

## 四、★ 平台差异

| 项 | 原 | 新 |
|---|---:|---:|
| ★ ubuntu 独有 | 3 | 0 |
| ★ windows 独有 | 0 | 0 |
| ★ 两者共有 | 67 | 5 |

★ 新基线两平台同集合。★ **windows 待 CI 首跑校正**：★ 若 Windows 出现额外失败
★ （★ 如行尾相关），★ 护栏会判红并给出具体差异，★ 再单独申请平台基线。

---

## 五、★ 哈希

| 文件 | 原 SHA256 | 新 SHA256 |
|---|---|---|
| ★ ci_expected_failed_ids_ubuntu.txt | `462edf1724c3c962…` | `526c19e561e7c862…` |
| ★ ci_expected_failed_ids_windows.txt | `21690d304904b97e…` | `526c19e561e7c862…` |
| ★ ci_expected_errors.txt | `e3b0c44298fc1c14…` | `e3b0c44298fc1c14…` |
