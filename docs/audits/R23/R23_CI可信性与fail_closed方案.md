# R23 CI 可信性与 fail-closed 方案

> ★ **只提方案，★ 不修改正式 CI** ｜★ 不通过删测试、★ 跳测试或降阈值让 CI 变绿

---

## 一、已验证事实

### 1.1 CI 的 job 结构

| job | OS | 含中枢构建 | 含护栏 | 含 pytest |
|---|---|---|---|---|
| push / pull_request / workflow_dispatch | —— | 否 | 否 | ★ workflow_dispatch 有 |
| static-checks | ubuntu-latest | 否 | 否 | 否 |
| byte-contract | windows-latest | 否 | 否 | **是** |
| seedcheck | ubuntu-latest | ★ **是** | 否 | ★ tests/seedcheck/ |
| guarded-pytest | ubuntu-latest | **否** | **是** | 是 |
| guarded-pytest-windows | windows-latest | **否** | **是** | 是 |

★ ★ **两个 guarded job 都不构建中枢** ⇒ 护栏0（★ 中枢协议校验）★ 在 CI 上跳过。

### 1.2 基线文件（★ 平台不同、失败集不同）

| 文件 | 说明 |
|---|---|
| ★ `expected_b_class_failed_ids.txt` | ★ 本机基线（★ 5 项） |
| ★ `expected_b_class_failed_ids.{dhcpv4,rtsp,sip,smtp}.txt` | ★ 按协议分列 |
| ★ `ci_expected_failed_ids_ubuntu.txt` | ★ CI（Ubuntu）基线 |
| ★ `ci_expected_failed_ids_windows.txt` | ★ CI（Windows）基线 |
| ★ `ci_expected_errors.txt`、`baseline_errors_pre_cleanup.txt` | ★ 错误类基线 |
| ★ `env_variant_failed_ids.txt` | ★ 环境变体基线 |
| ★ `encoding_known_issues.txt` | ★ 编码已知问题 |

★ ★ **⇒ 本地 5 项失败与 CI 的失败集合不同**，★ 两套基线必须分别使用。

### 1.3 未执行却可能显示通过的门禁

| 门禁 | 现状 | 风险 |
|---|---|---|
| ★ 护栏0（中枢协议校验） | ★ CI 不构建中枢 ⇒ 跳过 | ★ ★ 中枢产物在 CI 上**完全不受保护** |
| ★ 护栏1（树静止快照） | ★ `SNAPSHOT_GLOBS` 不覆盖 hub/graph/extraction/semantic/seedcheck | ★ 中枢与图层的改动不被快照拦 |
| ★ `verify_*` | ★ CI 只接 `verify_docs_consistency` 与 `verify_seedcheck_wiring` | ★ 其余检查未接 |

---

## 二、★ 最小 fail-closed 改进方案

| # | 改进 | 具体做法 | 判据 |
|---|---|---|---|
| ★ F1 | ★ **护栏执行确认** | ★ guarded job 增加 `if: always()` 的结果文件存在性检查 | ★ `_guarded_result.json` 不存在 ⇒ **job 必须 failed**；★ 不得因 skip 而显示 passed |
| ★ F2 | ★ **中枢产物纳入保护** | ★ 在 guarded job 前加中枢构建步骤，★ 并把构建产物路径纳入 `SNAPSHOT_GLOBS` | ★ 中枢产物的哈希变化须被护栏1 拦下 |
| ★ F3 | ★ **快照面补齐** | ★ `SNAPSHOT_GLOBS` 增补 `core/fused/hub/`、`core/fused/graph/`、`core/fused/extraction/`、`core/fused/semantic/`、`seedcheck/`、`tests/**` | ★ ★ 补齐后**必然**出现新的「新增失败」（★ 这正是要暴露的） |
| ★ F4 | ★ **基线失败带原因** | ★ 基线文件改为「测试 ID + 性质 + 处置计划」三列；★ 报告逐条列出 | ★ 基线 5 项不得再是永久豁免；★ 性质分类：★ 1 项模块缺失、★ 3 项断言过时、★ 1 项真实算法缺陷 |
| ★ F5 | ★ **真实负例测试** | ★ 在隔离目录构造**已知应当失败**的样例（★ 产物缺失、★ ID 重复、★ 证据缺失） | ★ ★ 证明门禁真的会红；★ 不依赖真实候选 |
| ★ F6 | ★ **平台基线分离且显式** | ★ ubuntu 与 windows 各用自己的 failed_ids；★ 报告同时给「基线项数」与「新增项数」 | ★ 两个数字都报；★ 不得只报一个 |

★ ★ **F3 的直接后果**：★ 补齐快照面后，★ 由于中枢与图层的产物当前不在快照内，
★ ★ **一旦纳入，★ 首次运行极可能出现「新增失败」**；★ ★ 这不是回归，★ 而是**首次把该层纳入保护**。

---

## 三、★ 验收方式（★ 隔离实验，★ 不改正式 CI）

| # | 验证 | 方法 |
|---|---|---|
| 1 | ★ F1 有效 | ★ 在隔离工作副本中让 guarded job 跳过，★ 验证 job 结论为 failed |
| 2 | ★ F3 无遗漏 | ★ 列出补齐后的快照清单，★ 逐项确认覆盖 hub/graph/extraction/semantic/seedcheck |
| 3 | ★ F5 有效 | ★ 隔离目录跑负例，★ 确认门禁红 |
| 4 | ★ F4 可追溯 | ★ 基线文件带原因列，★ 报告逐条列出 |

---

## 四、限制

1. ★ 本轮**未修改** `.github/workflows/ci.yml`。
2. ★ 未在 CI 环境中实跑；★ 全部结论来自 workflow 文件的静态解析与本地基线文件。
3. ★ ubuntu/windows 的 CI 失败集差异来自既有基线文件，★ 本轮未实跑 CI 复现。
