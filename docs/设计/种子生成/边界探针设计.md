# 边界探针（Boundary Probe）设计与实现

> 定位：主动寻找「合法边界」，把人工找边界（同 track→不同 track 等 guidance）变成自动探边界，
> 提升合法种子的命中率与覆盖度。
>
> 落盘日期：2026-10-14

---

## 一、核心概念：合法边界

「合法边界」= 仍合法（目标服务器正常处理、不 dry run 崩溃），但离非法（触发漏洞）最近的点，
使 fuzzer 只需 1~2 次变异即能触发漏洞。

以 RTSP matroska UAF 为例：

| 种子 | 合法？ | 离崩溃距离 |
|---|---|---|
| 同 track 双 SETUP | ❌ 非法（直接 UAF） | 0（越界） |
| **不同 track 双 SETUP** | ✅ 合法 | **1 次变异（track2→track1）** ← 边界 |
| 单 SETUP | ✅ 合法 | 远 |

## 二、双源设计

边界候选有两个来源，统一为「边界参数」（边界维度 + 合法域 + 非法域）：

| 源 | 依赖漏洞库？ | 推导依据 |
|---|---|---|
| **源 A 协议语义** | ❌ 无需，永远可用 | 状态机自环、生命周期、字段取值域、字段约束 |
| **源 B 漏洞知识** | ✅ 有漏洞库更精确 | classify_vuln 的 action + 触发流 |

**关键洞察**：源 A 是更强的卖点——证明「无漏洞先验也能从协议语义主动发现危险边界」，
与「多协议低成本迁移」自洽（新协议常无漏洞库）。

## 三、流程

```
边界候选推导（源A 协议语义 / 源B 漏洞知识）
        ↓
候选序列化 .raw → scp 到虚拟机
        ↓
oracle 判定（重放检测崩溃，多次取多数）→ LEGAL / ILLEGAL
        ↓
probe_boundary 定位「合法边界」（合法候选中最接近非法的）
        ↓
输出合法边界种子 + 回写知识中枢(legal_boundary，待实现)
```

## 四、实现清单

| 文件 | 职责 |
|---|---|
| `core/fused/downstream/boundary_probe.py` | BoundaryParam + derive_boundary_param(源B) + generate_candidates(源B) + derive_semantic_candidates(源A，自环+生命周期) + probe_boundary + emit_boundary_fact(回写) |
| `scripts/run_boundary_probe.py` | 端到端：候选 → scp → oracle → 定位边界 → 回写知识中枢；`--semantic` 切源 A |
| 虚拟机 `/tmp/oracle.py` | 重放 .raw 判定合法/非法（多次重放取多数） |

## 五、验证结果

**源 B（漏洞知识）**，18 候选：

| action | legal | illegal | 边界识别 |
|---|---|---|---|
| double_setup | 不同 track ✅ | 同 track ⚠️越界 | ✅ |
| interleave_seq | 不切换 ✅ | 切换 ⚠️越界 | ✅ |
| uaf_seq / lifecycle_seq | 不重建 ✅ | 重建（未触发） | ❌（触发依赖媒体格式，见下） |

**源 A（协议语义，无需漏洞库）**，4 候选（自环 + 生命周期）：

| 候选 | 判定 |
|---|---|
| SETUP 自环 legal（单次 SETUP） | LEGAL ✅边界 |
| SETUP 自环 illegal（重复 SETUP） | ILLEGAL ⚠️越界 |
| 生命周期 legal（不重建） | LEGAL ✅边界 |
| 生命周期 illegal（重建） | LEGAL（未触发，依赖媒体格式） |

✅ **源 A 仅从状态机自环 `Ready--SETUP-->Ready` 推导出「单次 vs 重复」的边界，无需任何漏洞先验。**

**边界回写知识中枢（闭环）**：oracle 探测到的边界，回写为 `legal_boundary` fact（subject=method,
value={dim, legal, illegal, trigger}），落到 `derived/model/per_source/semantic/facts/boundary_probe.jsonl`，
后续种子生成可直接复用，无需重新探测。源 B 回写 5 条（track_number ×2 + transport_switch ×3）、
源 A 回写 1 条（self-loop）。

## 六、过程中的关键发现

1. **字段值的精确性是边界的组成部分**：触发 matroska UAF 的关键是 Session 值 `000022B8`
   （=8888，即崩溃栈 `clientSessionId=8888`），占位符解析的 `12345678` 不触发。对照实验证实：
   +User-Agent 不触发，+Session 000022B8 触发。
2. **边界类型分层**：序列结构型漏洞（double_setup/interleave_seq）可用序列边界表达；媒体格式/
   字段特定型漏洞（RTSP-046 ADTS UAF 需 Matroska 嵌 AAC 轨）需要候选构造器感知更细条件。
3. **隐蔽 bug**：`"LEGAL" in "ILLEGAL"` 返回 True（子串包含），导致所有 illegal 误判——已改为精确匹配。

## 七、落地难点

1. oracle 成本：每次判定启动服务器 ~1.5s，需缓存 + 并行。
2. 概率性崩溃污染 oracle：UAF 时序依赖，单次重放不复现，需多次重放取多数。

## 八、问题解决进度（对应 review 的 8 个问题）

| # | 问题 | 状态 | 方案 |
|---|---|---|---|
| 1 | 触发值硬编码 | ✅ 已解决 | `search_trigger_value`：从真实流量模板提取 Session 候选 + oracle 验证（AFL dictionary 思想） |
| 2 | 闭环断裂 | ✅ 已解决 | `assemble_bundle` 提取 `legal_boundary` → `bundle["legal_boundary"]` |
| 3 | probe_boundary 无二分 | ✅ 已解决 | `binary_search_boundary`（ddmin 二分思想） |
| 4 | 媒体格式依赖 | ⚠️ 能力边界 | 边界探针对「序列型」漏洞有效；「媒体格式型」（ADTS UAF 需 Matroska 嵌 AAC）需额外媒体文件准备，已在文档标注 |
| 5 | oracle 外部耦合 | ✅ 已解决 | 批量判定（1 次 ssh 替代 N 次，25s 完成源 A） |
| 6 | 无单元测试 | ✅ 已解决 | `test_boundary_probe.py` 9 个测试（oracle mock） |
| 7 | 字段取值域边界 | ✅ 已加 | `derive_field_candidates`（数值字段合法 vs 边界值） |
| 8 | 最终价值未验证 | ⏳ 待做 | 一轮「边界种子 vs 普通种子」fuzz 对比 |

## 九、下一步

1. ⏳ 问题 8：边界种子 vs 普通种子的 fuzz 对比（12h，最终验收）。
2. 扩展字段候选构造器感知媒体格式/认证上下文（彻底解决 uaf_seq/lifecycle_seq）。
3. 源 A + 源 B 融合，验证多协议低成本迁移。
