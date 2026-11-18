# CI 实验依赖与正式测试的分离方案

> ★ 分类依据：**实际用途**，★ 不是按目录名

---

## 一、A 类：正式 CI 必须运行的测试（★ 已迁入版本控制）

| 项 | 内容 |
|---|---|
| ★ 判定依据 | ★ 这些测试**验证生产代码的行为**，★ 且其依赖的实现模块**本身是源码** |
| ★ 依赖形态 | ★ `sys.path.insert(0, str(ROOT / "guard/_out/..."))` 后 import |
| ★ 处置 | ★ **9 个模块迁入 `tests/_fixtures/`**；★ 6 个测试的路径插入改为指向新位置 |
| ★ 未改动的 | ★ **测试的断言、测试数、测试语义全部未变** |

### 1.1 迁移对照

| 原位置（未跟踪） | 新位置（已入库） | 字节 |
|---|---|---:|
| ★ guard/_out/_n1c_v2/h0/source_contract.py | ★ tests/_fixtures/h0/source_contract.py | 6303 |
| ★ guard/_out/_n1c_v2/h0/run_events.py | ★ tests/_fixtures/h0/run_events.py | 7667 |
| ★ guard/_out/_n1c_v2/h0/field_ledger.py | ★ tests/_fixtures/h0/field_ledger.py | 8340 |
| ★ guard/_out/_n1c_v2/h2a/sidecar.py | ★ tests/_fixtures/h2a/sidecar.py | 9243 |
| ★ guard/_out/_n1c/n2b0_tristate.py | ★ tests/_fixtures/n1c/n2b0_tristate.py | 6830 |
| ★ guard/_out/_n1c/n2b0_tristate_v1.py | ★ tests/_fixtures/n1c/n2b0_tristate_v1.py | 14014 |
| ★ guard/_out/_n1c_v2/e1/sampler.py | ★ tests/_fixtures/e1/sampler.py | 12358 |
| ★ guard/_out/_n1c_v2/e1/section_kinds.py | ★ tests/_fixtures/e1/section_kinds.py | 4334 |
| ★ guard/_out/_n1c_v2/v2_knowledge_gate.py | ★ tests/_fixtures/v2/v2_knowledge_gate.py | 17580 |

★ **V2 判据说明**：★ 该文件的 SHA256 与 `docs/实施/待办与勘误/M0对账交付/
M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py` **完全相同**
（`81566fb71905e313…`）⇒ ★ **是逐字节复制已入库版本，★ 未改动判据内容**。

### 1.2 稳定性保障

| 项 | 做法 |
|---|---|
| ★ 路径 | ★ 固定 `tests/_fixtures/<组>/`，★ 不再指向实验目录 |
| ★ 依赖 | ★ 显式 import；★ 9 个模块**逐一单独 import 均成功**（★ 无隐藏传递依赖） |
| ★ 版本 | ★ 每个夹具的 SHA256 登记在 `guard/baseline/CI_BASELINE_CHANGELOG.md` 与本方案 |

---

## 二、B 类：依赖历史实验产物的审计测试

| 项 | 现状 |
|---|---|
| ★ 典型 | ★ 依赖冻结 Gold、★ 人工审核表、★ 历史 LLM 输出的测试 |
| ★ 是否公开 | ★ **否**；★ 含人工真值与未揭盲相关材料 |
| ★ ★ 本轮处置 | ★ ★ **未迁移**；★ **未删除**；★ ★ 它们的收集错误已由「夹具入库」间接解决（★ 那 29 个 ERROR 模块**同时**依赖夹具与历史产物，★ 迁移夹具后它们**能收集**，★ 但其中的历史产物依赖**在断言阶段**才显现） |
| ★ ★ 结论 | ★ ★ **这部分测试在公开 CI 上仍会失败或依赖本地产物**；★ 已在新基线中如实登记；★ **未计为 passed** |

★ ★ **★ 必须明确的覆盖边界**：★ 本轮 CI 绿灯**只代表**：
★ ★ 「在有夹具、有中枢、无历史产物的干净环境中，★ 失败集合与基线一致」。
★ ★ **不代表**依赖冻结 Gold 与人工审核表的测试被真正执行并通过。

---

## 三、C 类：已不具备真实依赖的旧测试

| 项 | 处置 |
|---|---|
| ★ 是否删除 | ★ **未删除任何测试** |
| ★ 是否跳过 | ★ **未跳过任何测试** |
| ★ 是否弱化 | ★ **未弱化任何断言** |
| ★ 范围变化 | ★ **零**；★ 只改了 6 个测试文件的 `sys.path.insert` 一行 |

---

## 四、差异清单（★ 全部改动）

| 文件 | 改动 | 性质 |
|---|---|---|
| ★ `tests/extraction/test_h0_extraction_hardening.py` | ★ 1 行 sys.path | ★ 路径迁移 |
| ★ `tests/extraction/test_h2a_scheme_a.py` | ★ 2 行 sys.path | ★ 路径迁移 |
| ★ `tests/extraction/test_n1c_n2b0.py` | ★ 1 行 sys.path | ★ 路径迁移 |
| ★ `tests/extraction/test_n2b0r_tristate_v1.py` | ★ 1 行 sys.path | ★ 路径迁移 |
| ★ `tests/extraction/test_v2e1_sampler.py` | ★ 1 行 sys.path | ★ 路径迁移 |
| ★ `tests/extraction/test_v2_knowledge_gate.py` | ★ 1 行 sys.path | ★ 路径迁移 |
| ★ `tests/_fixtures/**`（9 个新文件） | ★ 新增 | ★ 夹具入库 |
| ★ `.github/workflows/ci.yml` | ★ 两 job 各加 3 步 | ★ 中枢构建 + fail-closed |
| ★ `guard/baseline/ci_expected_failed_ids_*.txt` | ★ 重采 | ★ 见《CI_基线与测试覆盖差异报告.md》 |

★ ⇒ ★ **测试的断言、条数、语义、覆盖范围全部未变。**
