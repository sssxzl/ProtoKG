# CI Windows 与 Ubuntu 运行结果

> ★ **★ 真机结果待 GitHub Actions 首跑填写**；★ 本文件先给出本地口径与差异解释

---

## 一、修复前的真机结果（★ 已有证据）

| 项 | ubuntu | windows |
|---|---|---|
| ★ workflow run ID | ★ 44215326226 | ★ 44215326226 |
| ★ job ID | ★ 134503610450 | ★ 134503609957 |
| ★ Actions 链接 | ★ https://github.com/sssxzl/ProtoKG/actions/runs/44215326226 | ★ 同左 |
| ★ 失败步骤 | ★ step 5 `Run guarded pytest (drift gate)` | ★ step 6 同名 |
| ★ failed | ★ 期望 70 / 实测 82（★ 新增 12） | ★ 期望 67 / 实测 79（★ 新增 12） |
| ★ errors | ★ 期望 0 / 实测 29（★ 新增 29） | ★ 期望 0 / 实测 29（★ 新增 29） |
| ★ tree_stable | ★ True | ★ True |
| ★ summary_present | ★ True | ★ True |

★ ⇒ ★ **★ 两个平台的失败结构完全一致 ⇒ ★ 差异不是平台特有的。**

---

## 二、修复后的本地口径（★ 两平台同）

| 指标 | 值 |
|---|---|
| ★ failed | 5（★ 与新基线一致，★ added 0 / removed 0） |
| ★ errors | 0 |
| ★ passed | 2070 |
| ★ skipped | 239 |
| ★ verdict | **TRUSTWORTHY** |

---

## 三、★ 平台差异的解释

| 差异来源 | 说明 |
|---|---|
| ★ 行尾物化 | ★ Windows runner 的 `core.autocrlf=true` ⇒ LF blob 变 CRLF；★ **CI 里已有显式归一化步骤**（★ `checkout-index --all --force` + CRLF 校验） |
| ★ 基线本身不同 | ★ 原 ubuntu 基线 70 条、★ windows 67 条；★ 差 3 条（★ ubuntu 独有：★ `test_binary_protocol` 2 条 + `test_dhcpv4_graph_has_expected_states` 1 条） |
| ★ 新基线 | ★ 两平台同集合（★ 5 条）；★ **windows 待真机校正** |

★ ⇒ ★ **★ 若 Windows 首跑出现额外失败（★ 如行尾相关），★ 护栏会判红并给出具体差异，
★ ★ ★ 再单独申请平台基线；★ ★ 不预先放宽。**

---

## 四、★ 待填（★ Actions 首跑后）

| 项 | 值 |
|---|---|
| ★ 新 run ID | ★ 待填 |
| ★ ubuntu job 链接 | ★ 待填 |
| ★ windows job 链接 | ★ 待填 |
| ★ ubuntu 实际 failed / errors | ★ 待填 |
| ★ windows 实际 failed / errors | ★ 待填 |
| ★ 五个检查是否全绿 | ★ 待填 |
| ★ ★ 全绿时须额外确认 | ★ **未静默排除、★ 未跳过、★ 未降断言强度**（★ 用新增测试数与 collected 数对比确认） |
