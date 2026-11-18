# CI 中枢护栏（护栏 0）实际执行证明

> ★ 结论：★ **修复前护栏 0 在 CI 上从未真正执行**；★ 本轮已让它**第一次真正执行**

---

## 一、修复前的状态（★ 证据）

| 证据 | 内容 |
|---|---|
| ★ workflow 原文 | ★ 两个 guarded job 的步骤只有 Checkout / Setup / Install / Run guard / Upload；★ **无中枢构建** |
| ★ 护栏脚本 | ★ `guard/run_guarded_pytest.py` 的护栏 0 需要 `derived/hub/` 产物；★ CI 上该目录不存在 |
| ★ R21/R22/R24 审计 | ★ 三轮审计均独立报告「CI guarded job 不构建中枢 ⇒ 护栏0 跳过」 |
| ★ 实际后果 | ★ 82 条 failed 里的 65 条来自「CI 读不到中枢」；★ 若中枢逻辑整体损坏，★ **CI 不会因此变红** |

★ ⇒ ★ **★ 门禁此前是「假绿」的**：★ 它只比对了失败集合，★ 而失败集合本身是被缺中枢污染的。

---

## 二、本轮的最小修复

### 2.1 新增三步（★ 两个 guarded job 各一份）

| 步 | 命令要点 | 为什么 |
|---|---|---|
| ★ Build hub (rtsp) for guard 0 | ★ `python scripts/build_hub.py --protocol rtsp --sources rfc traffic expert_note vuln --no-purge` | ★ 与 seedcheck job **完全一致**的确定性入口 |
| ★ Verify hub artifact exists (fail-closed) | ★ 检查 `derived/hub` 存在且含 ≥1 个 jsonl，★ 否则 `exit 1` | ★ 中枢没建成 ⇒ 护栏 0 不得静默跳过 |
| ★ Verify guard actually ran (fail-closed) | ★ 检查 `_ci_artifacts/_guarded_result.json` 存在，★ 否则 `exit 1` | ★ 护栏未执行不得判通过 |

### 2.2 三条硬性保证

| 保证 | 实现 |
|---|---|
| ★ 不调用真实 LLM | ★ 构建时**不带 source 源**；★ source 走 AutoSeeder 的 LLM 路径 |
| ★ 使用可复算的确定性输入 | ★ kb 下的 RFC 与流量是入库的确定性输入 |
| ★ 验证中枢确实构建成功 | ★ 第二步检查 jsonl 数量；★ 护栏 0 本身还会校验中枢协议 |
| ★ 不覆盖冻结中枢或 Seed | ★ `derived/` 被 gitignore；★ CI 是全新 checkout ⇒ 无可覆盖之物 |
| ★ Windows 与 Ubuntu 均验证 | ★ 两个 job 都加了同样三步 |
| ★ 中枢未构建时 fail-closed | ★ 第二步 `exit 1` |

---

## 三、修复后的实测证据

★ 本地以**与 CI 同口径**运行护栏（★ 有中枢、★ 有夹具、★ 新基线）：

```
verdict = TRUSTWORTHY
tree_stable = True
summary_present = True
failed = 5（★ 与新基线完全一致，★ added 0 / removed 0）
errors = 0
passed = 2070
skipped = 239
```

★ ⇒ ★ **★ 护栏 0 现在有了真实的中枢产物可校验，★ 且它的判定进入了 drift 集合。**

---

## 四、★ 诚实的限制

| 项 | 说明 |
|---|---|
| ★ 本地 ≠ Runner | ★ 上面的数字来自本地；★ **真机 Runner 的结果以 GitHub Actions 首跑为准** |
| ★ 护栏 0 的强度 | ★ 它校验的是**中枢协议一致性**（★ `--expect-hub-protocol rtsp`）；★ 不等于中枢内容正确性 |
| ★ 中枢内容质量 | ★ 由 seedcheck job 独立覆盖；★ 两者职责不同 |
