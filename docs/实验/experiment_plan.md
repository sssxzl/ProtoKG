# ProtoRAG 实验计划（RQ1-RQ3，第 5 章数据）

> 更新：2026-10-18 20:50。本文件是第五章实验数据的执行蓝图。

## 一、实验环境

- **Windows 端**：`E:\科研\想法idea\rag-chatafl`（种子生成）
- **虚拟机 Ubuntu 22.04**：`zxy@192.168.37.130`（免密 `~/.ssh/vm_ubuntu_zxy`）
- **Docker**：`chatafl-live555:latest` 镜像，10 容器并行（ctl-1~5 对照 / my-1~5 实验）
- **目标程序**：testOnDemandRTSPServer（live555），端口 8560-8569
- **fuzzer 命令模板**（参数必须一致，仅 -i/-o/-N 端口不同）：
  `afl-fuzz -d -i <种子> -x rtsp.dict -o <out> -N tcp://127.0.0.1/<port> -P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 1000 -- ./testOnDemandRTSPServer <port>`
- **实验规格**：24h / 组，同配置 5 组取平均

## 二、RQ 矩阵

### RQ1 总体有效性（ProtoRAG vs 基线）

| 配置 | 种子 | 状态 |
|---|---|---|
| ProtoRAG 五源完整种子 | `derived/model/seeds/rtsp/20261018_205014/`（70 种子） | ✅ 已生成，待启动 |
| 基线：AFLNet 原始种子 | `/home/zxy/aflnet/tutorials/live555/in-rtsp` | 已有 |
| 基线：ChatAFL 自带种子 | `in-rtsp-safe`（容器 `/opt/seeds/in-rtsp-safe`） | 已有 |
| 基线：NSFuzz | 需下载（若不开源用 StateAFL 替代） | 待确认 |
| 基线：ProtocolGPT | 未开源 | 跳过 |

### RQ2 多源融合价值（单源/双源/五源消融）

| 配置 | 生成方式 |
|---|---|
| 五源（rfc+expert_note+traffic+vuln+source） | ✅ 已有（205014） |
| 单源 source | `build_hub --sources source` + 三层选择器 |
| 单源 rfc | `build_hub --sources rfc` + 三层选择器 |
| 双源 rfc+source | `build_hub --sources rfc source` + 三层选择器 |

### RQ3 知识表示与冲突消解（A/B/C 三路）

| 路 | 知识表示 | 生成方式 |
|---|---|---|
| A 可溯源（ProtoRAG） | 六元组 + 冲突显式化 | `run_seedgen_e2e --three-layer`（含冲突段） |
| B 浅层（PSG 式） | 结构化无 provenance | `compare/run_ablation --mode shallow_kb` |
| C 向量 RAG（MultiFuzz 式） | 原文 chunk 检索 | `compare/run_ablation --mode vector_rag` |

> ⚠️ RQ3 三路需统一生成机制（都用 LLM 生成、同 LLM 参数），当前 A 路是三层选择器（规则+漏洞）而 B/C 是 LLM 直接生成，需后续对齐。

## 三、当前实验状态（2026-10-18 20:50）

**在跑**：13 多流种子(my) vs 原始种子(ctl)，24h，15:38 启动，已 5h。

| 组 | 覆盖率 | 崩溃 | 结论 |
|---|---|---|---|
| ctl | 3.90~4.00% | 121~150 | 原始真实流量种子，踩中 matroska UAF |
| my | 1.43~2.41% | 0 | 多流种子落后（种子多摊薄预算 + 太合法） |

**结论**：13 多流种子（单源码源）是负面基线。正确实验组 = 五源完整种子（已生成 70 个）。

## 四、下一步动作

1. 等当前 24h 实验跑完（约次日 15:38），收集 ctl/my 的 fuzzer_stats
2. 启动「五源完整种子(70) vs 原始种子」5 组 × 24h（复用 Docker 镜像，换种子）
3. 生成 RQ2 单源/双源种子 + RQ3 B/C 路种子
4. 逐配置跑 24h×5 组，收集数据
5. 数据充分后填第五章 + 写完文章

## 五、关键教训（务必遵守）

- 种子不是越多越好：种子多 → 摊薄变异预算（execs 减半）→ 覆盖落后
- 崩溃发现奖励「离漏洞触发点近 + 变异预算集中」，不是「知识多/种子合法」
- 对照组的真实流量种子天生踩中 matroska UAF（CVE-2021-38382/38381），很强
- 崩溃是概率性 UAF，单次重放不复现，需 ASAN + 多次重放
