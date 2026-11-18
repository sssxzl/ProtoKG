# CI 版本保护与交付索引

> ★ 分支 `fix/ci-hermetic-guarded-pytest`（★ 从 main `65d162b` 建立，★ **未合并 main**）
> ★ **0 次 LLM 调用**

---

## 一、交付物清单

| # | 文件 | 内容 |
|---|---|---|
| 1 | `CI_29收集错误与12新增失败逐项归因.md` | ★ 29 个 ERROR 与 82 条 failed 的**逐项**登记与三类归因 |
| 2 | `CI_实验依赖与正式测试分离方案.md` | ★ A/B/C 三类依赖的判定与处置 |
| 3 | `CI_测试环境修复源码差异.md` | ★ ci.yml 与 6 个测试的完整 diff |
| 4 | `CI_基线与测试覆盖差异报告.md` | ★ 基线 70→5 的**可复算**三类归因 |
| 5 | `CI_中枢护栏实际执行证明.md` | ★ 护栏 0 从「假绿」到真正执行 |
| 6 | `CI_负例测试报告.md` | ★ 八项负例的实测 |
| 7 | `CI_Windows与Ubuntu运行结果.md` | ★ 两平台结果与差异解释 |
| 8 | `CI_版本保护与交付索引README.md` | ★ 本文件 |

★ 另：`guard/baseline/CI_BASELINE_CHANGELOG.md`（★ 基线版本记录）。

---

## 二、★ 版本保护核验

| 约束 | 结果 |
|---|---|
| ★ 0 次新增 LLM 调用 | 满足 |
| ★ **不修改 `rfc_extractor.py` 的生产合并逻辑** | ★ 满足；★ field_value 修复与本轮严格分离 |
| ★ 不修改 V2 或 V2-next | 满足；★ V2 判据 SHA256 未变 |
| ★ 不修改 Gold | 满足 |
| ★ 不修改 FactID、EvidenceID、NormID 和 21 aspects | 满足；★ `knowledge_slots.json` 未变 |
| ★ 不修改生产抽取、中枢、图或种子生成业务逻辑 | 满足；★ `core/`、`scripts/`、`seedcheck/`、`profiles/` 零改动 |
| ★ 不合并 R21～R24 审计分支 | 满足；★ 本分支从 main 建立 |
| ★ 不修改正式生产数据 | 满足 |
| ★ 不上传私人审核信息或敏感凭据 | 满足；★ 9 个夹具逐一扫描无凭据 |
| ★ **不靠跳过测试或放宽基线换取绿色 CI** | 满足；★ 未删除、未跳过、未弱化任何测试；★ errors 基线由 29 降为 0 是**消除环境缺陷后的实测值** |

---

## 三、★ 版本哈希

基线提交：65d162b

| 文件 | SHA256 |
|---|---|
| CI_29收集错误与12新增失败逐项归因.md | `86a69d794b32866e9e40ab057d4dfc275356db9ed15c0c02485e55f714afe07c` |
| CI_Windows与Ubuntu运行结果.md | `bb0fc0cefcc9cb2e7f939e0e88ee28ef23afad2a81efcb58b459c637d28daac1` |
| CI_中枢护栏实际执行证明.md | `f7aff47d66d2a2222387156aaea566517f534d654a178fc2a6143d6d208b79c9` |
| CI_基线与测试覆盖差异报告.md | `a62e7cd0d8d139eb3350dc6aefc3464d9a7f93b4ffc954ff95d1e0bbe9434e31` |
| CI_实验依赖与正式测试分离方案.md | `f283e54c9dde272c7c5910676140585846c3f87e98d6de234bc03b586cf1d835` |
| CI_测试环境修复源码差异.md | `09538da7f8912f928b752001c67fe670c3950cce0c3f5c8ce4c232bd07a98b5c` |
| CI_负例测试报告.md | `c9749e8d27b67fd680332e7f3cc5e2ecb3e0883b8525d382fd29b438f013406b` |
| V2 判据（★ ★ 未改） | `81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047` |
| core/fused/extraction/rfc_extractor.py（★ ★ 未改） | `7b91622987e8943866473325208ff8b1e0974b67ed93238427c0763d92c4eff0` |
| core/fused/hub/knowledge_slots.json（★ ★ 未改） | `955f5368865063b5b882e9856f93995500c4b4eaa80daf97e541a05808bcad89` |
| guard/baseline/ci_expected_errors.txt（★ 重采） | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| guard/baseline/ci_expected_failed_ids_ubuntu.txt（★ 重采） | `526c19e561e7c862496ced594126b882981aaf6a966b84eb636df9c451b0a18f` |
| guard/baseline/ci_expected_failed_ids_windows.txt（★ 重采） | `526c19e561e7c862496ced594126b882981aaf6a966b84eb636df9c451b0a18f` |

---

## 四、★ R24B 来源差集统计的自洽性核对（★ 审查方第 4 项）

| 协议 | both | prod_only | shadow_only | recovered_source_instances |
|---|---:|---:|---:|---:|
| smtp | 63 | 0 | 0 | 0 |
| rtsp | 96 | 9 | 2 | 2 |
| DHCPv4 | 73 | 0 | 5 | 5 |
| **合计** | **232** | **9** | **7** | **7** |

★ **★ 重要更正**：★ R24 报告的「恢复 11 条」表述**不成立**。
★ ★ **16 = prod_only(9) + shadow_only(7)**，★ 两者是**相反方向**：
★ ★ 影子**多 7 条**（★ 被生产丢弃的生成器来源）、★ **少 9 条**（★ RTSP 的 transition）。
★ ★ 少 9 条的原因：★ 影子键的候选身份只含 `kind.name`，★ 对 transition 粒度太粗
★ ★ （★ `from`/`to` 未纳入）⇒ ★ 同一 method 的多条 `from→to` 被折叠。
★ ★ ⇒ ★ **这是影子方案自身的缺陷，★ 不是生产的缺陷；★ 影子相对生产的净变化是 -2 条。**

★ 计算方式（★ 可复算）：★ `guard/_out/_n1c_v2/r24c/p00_diffset_reconcile.py`
★ ★ 分别按生产规则（★ `rfc_extractor.py:4103-4131`）与影子规则（★ 按
★ `source_instance_key`）复算两套保留集合，★ 再求交与双向差。

---

## 五、状态

R24C CI 修复已实施并本地验证；★ **GitHub Actions 真机首跑与 PR 待提交后进行**。
