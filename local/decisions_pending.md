local/decisions_pending.md

定位：本文件记录待用户拍板项。agent 遇到决策点时追加一条，用户批复后移到 local/decisions_resolved.md。
格式：一条目编号 D<数字>。提出时间。提出 agent 与 Step。问题描述。候选方案（至少两个：甲、agent 倾向与理由、当前阻塞的后续动作）。

D4 / D5 / D6 / D7 / D8 / P8 / D10 / D11 / D12 / D13 全部已拍板并移入 local/decisions_resolved.md。
D9（traffic 观测口径）**已定案**：traffic D9 设计 §0–§13 Final Frozen
（`local/traffic_d9_design.md`，§6.5 BLOCKED 等 M3 外部输入，§6.6-C1.x PENDING）。
实测数据存档在 resolved。后续 D14–D19 为 Lane A 判定链，同样已全部落盘。

当前待拍板项：**D20**（语义四库在批次清空时的默认处置，见下）。

## D20（批次 2.3）—— 中枢清空时**语义四库**（`semantic/`）的默认处置

提出时间：2026-11-03。提出：team-lead（批次 2.3 消融实验期间实测踩到）。

**问题**：`scripts/build_hub.py` 的批次清空（`_purge_hub_for_batch`）会**删掉各源的
`semantic/`（语义四库）**，只备份到**仓库外**（`SEMANTIC_BACKUP_ROOT`）、**无自动恢复路径**。
而语义规则**不能从 kb 重建**（需 LLM）⇒ 单源重建中枢会静默丢掉 ③ 层
（vuln_boundary）的 6 条约束边界候选 ⇒ rtsp/B 由 **85 条掉到 79 条**
⇒ `local/baseline_p0_seeds.md5` 失效。

**实测证据**（本轮）：
- 第一次消融跑完 ⇒ rtsp/B = 79 条（③ 层 0 条），基线 = 85 条（③ 层 6 条）。
- 中枢 facts **逐字节相同** ⇒ 差异不在知识，而在 `semantic/` 被删。
- 从仓库外备份恢复 `semantic/` 后 ⇒ **85 条，逐条 MD5 与基线 85/85 一致** ⇒ 根因坐实。
- 默认路径**已有显式告警**（"需要时请加 --with-rules"），`--with-rules` 可重发布（需 LLM）。

**候选方案**：
- **甲（agent 倾向）**：purge 默认**保留** `semantic/`，只有显式 `--with-rules` 才清空重发布。
  - 理由：① 与 `--with-rules` 的既有语义一致（该开关的存在前提就是「默认不清」）；
    ② 不可再生资产不该被默认销毁；③ 不改任何现有产物的字节（只改「清不清」）。
  - 代价：中枢里可能残留**与本次事实不匹配**的旧规则 ⇒ 需要在构建日志里提示。
  - 阻塞：改默认行为要重跑护栏 + 复核基线是否仍 85/85。
- **乙**：保持默认删除，但**新增 `--restore-semantic-from-backup`** 开关，
  构建后从仓库外备份自动恢复。
  - 理由：改动更小、不动默认语义。
  - 代价：使用者需要知道要加这个开关（否则默认路径仍然静默丢规则）。
- **丙**：不改代码，靠流程纪律（每次重建后手工恢复）。
  - 理由：零风险。
  - 代价：**本轮已证明它必然被忘**（我自己就踩了，且差点让绝对数全部失真）。

**当前状态**：本轮**未改默认行为**（避免在消融任务里叠加变量），改用消融脚本内的
「构建后立即恢复」保障三档同态（见 `tools/qa/ablation/run_ablation.sh` 的
`restore_semantic`）。等待拍板后再动默认行为。


阶段 4.8a / 4.8b / 4.8c / 4.8d / 4.8e 检查点（**历史快照**，2026-10-04 标注）：
  专项 tests/fused/  1920 passed / 3 skipped / 0 failed
  全量               2531 passed / 8 skipped / 0 failed
  kb/ 指纹           6061 files，SHA256 A86C71E0…DEDE24，与基线逐字节一致 → UNCHANGED
  derived/           per_source/rfc 13 + per_source/expert_note 13 + fused 13 文件
                     verify_layout(.) = 0 violation
  ruff               本轮改动文件全清；scripts/ 整目录全清

  ⚠ 本块为**当时口径**的历史记录，不是当前值。当前 canonical 值见
    `local/project_handoff.md` §6 / §7。其中 kb 指纹 `A86C71E0…DEDE24`
    经后续复核**无已知可复现方法，不适用于 aggregate 对比**，已被 aggregate v1
    口径（`sha256:bcc1bd3f…`，6061 files）取代。

五源进度（逐源单源处理，融合留到五源全完之后；**2026-10-04 复核**）：
  rfc          ✅ 11 norm  → 11 Facts   derived/per_source/rfc/
  expert_note  ✅ 89 norm  → 49 Facts   derived/per_source/expert_note/
                          （规则集消费 50/89；39 条按设计文档 §8「刻意不实现」）
  vuln         ✅ 37 norm  → 14 Claims → 5 Facts   derived/per_source/vuln/
                          （37 个 RTSP-xxx.json 中 7 个产出 claim，
                            claim 合并为 5 个 fact；其余 30 个计数为 0。
                            ⚠ 原写「规则集未覆盖，需先设计规则」已过时——vuln 已入 Hub）
  traffic      ⏳ 25998 norm；D9 §0–§13 已 Final Frozen（§6.5 BLOCKED）、
                          Traffic Metadata Recon + Q1 已 PASS；
                          Lane A **三份设计文档全部 Final Frozen**
                          （Rule Set / Provenance Interface / Implementation Proposal）；
                          **阶段 I / II / III 已完成**，Lane A 代码实现落地：
                          core/lane_a/ 10 个模块 + tests/lane_a/ 68 项测试，
                          derived/lane_a/ 500 unit × 25000 observation
                          （insufficient 11000 / no_target 14000），
                          全量 pytest 2752 passed / 8 skipped / 0 failed。
                          （⚠ 原写「★ 等 D9 口径（3000 个 capture 是否互相独立）」
                            已过时：口径已裁定为 **1000 nominal / 500 effective**，
                            「3000」这一数字在任何冻结文档中均无对应）
  source       ⏳ 无 source extractor（待阶段 5）

★ derived/fused/ 当前含 **三源**：rfc + expert_note + vuln
  （**65 Facts / 75 Claims**；rfc 11 + expert_note 49 + vuln 5；
   build_fingerprint `sha256:5017304a833d3f6c7d111c53c2288c5b83f2de2c9d2993b5149cb69270550b7b`；
   最后构建 2026-10-01 19:38:59）。
  ⚠ 原写「两源 60 Facts / 54 entities / 473 returns_code / 61 lineage，
  build_fingerprint sha256:b2f70f0c…」已过时——那是一个已被后续构建替换的中间态。
  源归属须按 `claims[].evidence[].source_type` 统计（`fact_key` 内无 source 字段）。
  这仍不是五源最终产物 —— traffic / source 未入，五源全跑完后需重跑一次。

下一步候选（2026-10-04 更新）：
  a) traffic 源：**Lane A 阶段 IV** —— G5 / G7（当前 NO_TARGET_PENDING_EXTRACTION，
     缺口在 Hub Contract 侧）；以及 Lane A 产出接入下游读出口的真实消费方验证
  b) traffic 源：Traffic Single-source Hub Build
     （⚠ 注意 §3.2 裁定不做 validator invariant，故 traffic 入 Hub 不受阻）
  c) source 源：待阶段 5 设计 extractor
  d) 五源跑完后：统一做融合与冲突检测
  e) 其他

已裁定但需用户知悉（2026-10-04，非待拍板项）：
  · proposal §3.2 validator invariant = **不做**（ERRATA-1 已闭合与
    provenance_interface §5.5 的冲突）。
  · 阶段 III 契约矛盾裁定 = **丙-a + 组粒度精确化**：
    Lane A 纯 json 读 derived/fused/facts/ 建 target index（不 import Hub 代码）；
    「组」精确到 (group, header) 级。**§2.4 与 §3.4 原文均未改写**
    （见 provenance_interface §3.5 + ERRATA-2）。
  · 接口文档 §2 / §3 / §4 已转 Final Frozen；**§5 / §6 保留 Frozen Candidate**
    （ERRATA-2 授权范围只含前三节）。
  · `derived/fused_status.txt` 的 vuln status 描述已过时（实测
    3 resolved + 2 unresolved/peer_conflict，非「全部 unresolved」）。
    因位于 derived/、未获授权写该目录，仅登记未修。
