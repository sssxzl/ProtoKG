# CI 版本保护与交付索引

> ★ 分支 `fix/ci-hermetic-guarded-pytest`（★ 从 main `65d162b` 建立，★ **未合并 main**）
> ★ **0 次 LLM 调用**

---

## 一、★ 交付物

| # | 文件 | 内容 |
|---|---|---|
| 1 | `CI_29收集错误与12新增失败逐项归因.md` | ★ 三类异常逐项登记 |
| 2 | `CI_实验依赖与正式测试分离方案.md` | ★ A/B/C 三类依赖与处置 |
| 3 | `CI_测试环境修复源码差异.md` | ★ ci.yml 与 6 个测试的 diff |
| 4 | `CI_基线与测试覆盖差异报告.md` | ★ 基线 70→25 的可复算归因 |
| 5 | `CI_中枢护栏实际执行证明.md` | ★ 护栏 0 从假绿到真正执行 |
| 6 | `CI_负例测试报告.md` | ★ 八项负例实测 |
| 7 | `CI_Windows与Ubuntu运行结果.md` | ★ ★ 真机五项全绿与真实性核验 |
| 8 | `CI_版本保护与交付索引README.md` | ★ 本文件 |

★ 另：`guard/baseline/CI_BASELINE_CHANGELOG.md`（★ 四轮基线变更的可复算记录）。

---

## 二、★ 真机验收结果

★ ★ **run 44274634440 与 44274624465：★ 五个检查全部成功。**
★ ★ 护栏 verdict = TRUSTWORTHY（★ 两平台），★ 漂移 added 0 / removed 0。
★ ★ 链接：★ https://github.com/sssxzl/ProtoKG/actions/runs/44274634440
★ ★ PR：★ https://github.com/sssxzl/ProtoKG/pull/1

### 2.1 全绿的真实性（★ 未靠跳过或放宽）

| 核验项 | 结果 |
|---|---|
| ★ 删除的测试 | **0**（★ 2078 → 2078） |
| ★ 断言总数 | **未减少**（★ 4720 → 4720） |
| ★ 断言或测试数减少的文件 | **0** |
| ★ ★ 覆盖缺口披露 | ★ 229 个用例 not_run（★ 4 条 skip 规则 + 1 个收集前排除钩子） |

---

## 三、★ 版本保护核验

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
| ★ **不靠跳过测试或放宽基线换取绿色 CI** | ★ 满足；★ errors 基线由 29 降为 0 是**消除环境缺陷后的实测值**；★ 失败基线按 CI 口径重采并逐条登记 |

---

## 四、★ 版本哈希

基线提交：2784cea

| 文件 | SHA256 |
|---|---|
| CI_29收集错误与12新增失败逐项归因.md | `86a69d794b32866e9e40ab057d4dfc275356db9ed15c0c02485e55f714afe07c` |
| CI_Windows与Ubuntu运行结果.md | `baf2b02673d7e954b065f280104c7ee3006874e0a5db739b9d5d79f988e3119c` |
| CI_中枢护栏实际执行证明.md | `f7aff47d66d2a2222387156aaea566517f534d654a178fc2a6143d6d208b79c9` |
| CI_基线与测试覆盖差异报告.md | `a3ffcd8ab75937bafb387d457075e1649e916b2648aa091243a3914fa74cc2e4` |
| CI_实验依赖与正式测试分离方案.md | `f283e54c9dde272c7c5910676140585846c3f87e98d6de234bc03b586cf1d835` |
| CI_测试环境修复源码差异.md | `09538da7f8912f928b752001c67fe670c3950cce0c3f5c8ce4c232bd07a98b5c` |
| CI_版本保护与交付索引README.md | `413d5548f35535e8a1762f95dc52f889df5da984314e1bb9e997522986232e1b` |
| CI_负例测试报告.md | `c9749e8d27b67fd680332e7f3cc5e2ecb3e0883b8525d382fd29b438f013406b` |
| V2 判据（★ ★ 未改） | `81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047` |
| core/fused/extraction/rfc_extractor.py（★ ★ 未改） | `7b91622987e8943866473325208ff8b1e0974b67ed93238427c0763d92c4eff0` |
| core/fused/hub/knowledge_slots.json（★ ★ 未改） | `955f5368865063b5b882e9856f93995500c4b4eaa80daf97e541a05808bcad89` |
| guard/baseline/ci_expected_errors.txt（★ 置空） | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| guard/baseline/ci_expected_failed_ids_ubuntu.txt（★ CI 口径重采） | `3cb6a9caf8ce01cfec58c5223a3b9793fce6858c317a2b86494c1902e2285d72` |
| guard/baseline/ci_expected_failed_ids_windows.txt（★ CI 口径重采） | `c1a8bc5f04ee0b225115123de2eeb6919cf4d21ee878427d3fbe2e64992e543b` |
| 原子 Gold v5（★ ★ 未改，★ 位于审计分支） | `6ba3ae961ab564908aa8879d81ac77788931376c256e039027327022ff2b110c` |

---

## 五、★ 状态

R24C CI 修复已完成并经真机 Runner 验证（★ 五项全绿）；★ **PR 未合并 main**。
