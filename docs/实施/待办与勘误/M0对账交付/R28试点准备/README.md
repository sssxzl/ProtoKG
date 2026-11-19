# R27C 阶段性交付与 R28 试点准备

> 状态：三项修复已合入 main（`0f99da8`），四项 Windows CI job 全绿。
> R28 材料为试点准备，人工评审尚未开始，相关质量指标一律 unavailable。

## 一、已合入 main 的内容

| 提交 | 内容 |
|---|---|
| `ec08370` | Windows 单平台 CI + 基线缺失 fail-closed |
| `5d17027` | 散文缓存测试隔离 + 护栏产物改到 guard/_out |
| `f3012f2` | field_value 合并结果写回最终保留的 Norm |
| `6459b14` | 修 CI 重复键（首次推送启动失败） |
| `0f99da8` | 合并提交（PR #2） |

main 完整 SHA：`0f99da8445ea093246824e62d1244b88732e009e`。

## 二、GitHub 实跑结果

| 运行 | 事件 | 结论 |
|---|---|---|
| `44437120188` | pull_request | 4 个 Windows job 全部 success |
| `44437313936` | push 到 main | 4 个 Windows job 全部 success |

远端分支现只有 `main`；一次性分支 `release/r27c-integration` 已删除。

## 三、本地整链验收

| 项 | 结果 |
|---|---|
| 干净 worktree + 构建 rtsp 中枢后跑护栏（windows 基线） | 23 failed / 1392 passed / 0 errors / 229 skipped，新增 0、消失 0 |
| smtp | 63 Norm / 82 Fact |
| rtsp | 107 Norm / 152 Fact |
| DHCPv4 | 92 Norm / 99 Fact |
| 缓存隔离 | 连续两次 test_llm_diagnostics 各 10 passed，`rtsp.prose.json` 保持 `1149a345…` |
| field_value | 8 条真实路径测试通过；旧语义反向对照 5 failed |
| 身份契约 | 未改 Canonical Schema / 21 aspects / FactID·NormID·EvidenceID |

## 四、一次真实的 CI 失败（必须记录）

第一次推 `f3012f2` 时 CI 直接 `startup_failure`，0 个 job。原因：替换 Job 4 注释块时把 `name` / `runs-on` 各留了两份，PyYAML 默认接受重复键（所以我早前「YAML 解析通过」的结论是假阳性），但 GitHub Actions 拒绝重复键。

修复提交 `6459b14` 后 CI 正常。教训：本地 YAML 校验必须用「重复键即报错」的加载器，普通 `yaml.safe_load` 不足。

## 五、R28 材料清单

| 文件 | 说明 |
|---|---|
| `R28_基线清单.json` | main SHA、Python 版本、8 个关键源码哈希、42 份 RFC 哈希 |
| `R28_试点抽样_60条Norm.csv` | 60 条分层抽样，含人工判定空列 |
| `R28_RFC清点包_6份.csv` | 6 份 RFC 的路径、行数、SHA256、是否零产出 |
| `R28_标注规范.md` | 五个维度的判据与反例 |
| `R28_指标口径.md` | 每个指标的分子、分母、可计算性 |
| `R28_Gold登记与状态.md` | Gold 版本登记方式与当前状态（未开始） |

## 六、未完成与待审批

| 项 | 状态 |
|---|---|
| 人工双评与仲裁 | 未开始（无评审人员参与），五维指标 unavailable |
| C-3 行号基准 | 未合入，待 Ubuntu 复验（当前 CI 已无 Ubuntu） |
| C-4 定位精修 | 冻结，未进 R28 基线 |
| 实时 LLM 抽取 | 0 次调用 |
| CLI 文档推送 | 本目录在本地分支 `r28/pilot-prep`，未推送 |

## 七、回滚

三项修复各自独立提交，可分别 revert：

```
git revert --no-commit f3012f2 5d17027 ec08370   # 代码
git revert -m 1 0f99da8                          # 整批回退（合并提交）
```

回滚 field_value 后 `_dedup_one` 消失，去重逻辑回到内联旧写法；回滚缓存隔离后测试会重新写真实 `rtsp.prose.json`（不建议）。
