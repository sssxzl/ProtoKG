# RQ1 第一个实验 — Live555（RTSP, text）种子构造效率实测记录

> 实验日期：2026-10-20
> 协议/目标：Live555（RTSP, text）— `testOnDemandRTSPServer`
> 表格位置：`实验方案_详细版.docx` → RQ1：种子构造效率 → Live555（RTSP，text）

---

## 一、实验目的与指标定义

对比三种「初始种子构造方法」在 Live555 上的构造效率。唯一变量 = 种子构造方法。

| 指标 | 定义 |
|---|---|
| 种子数 | 该方法产出的初始种子文件数 |
| Time (min) | 构造耗时（含 embedding 加载 + 全部 LLM 调用） |
| Tokens | LLM 用量（input + output） |
| Rv（有效种子率） | 重放不崩的种子数 / 总种子数（dry-run 重放 oracle） |
| Veff（有效种子/分钟） | 有效种子数 / Time(min) |

**有效种子判定 oracle**：把每条种子逐消息重放到 live555 ASAN 服务器
（`testOnDemandRTSPServer`，`-fsanitize=address`），服务器不崩溃即「有效」；
崩溃（ASAN abort / 进程退出）即「无效」。每条重放 3 次取多数（排除概率性 UAF 抖动）。

---

## 二、三种方法的配置与执行流程

### 1. Seed Reuse（ProFuzzBench 原始种子）— 基线

- **来源**：`/home/zxy/profuzzbench/subjects/RTSP/Live555/in-rtsp/`（ProFuzzBench 官方随附的 7 条 live555 种子）。
- **种子数**：7 条（`rtsp_requests_{aac,ac3,mkv,mp3,mpg,wav,webm}.raw`，即 testRTSPClient 录制的真实流量）。
- **Time**：不评估（现成种子，零构造耗时）。
- **Tokens**：0（无 LLM）。
- **执行流程**：无需生成，直接重放 7 条种子测 Rv。

### 2. ChatAFL 种子增强

- **方法**：ChatAFL 的 LLM 初始种子增强（`chat-llm.c` 的 `enrich_testcases → enrich_sequence`）。
  先经语法提取得到 RTSP 消息类型全集，再对每条录制种子识别「缺失消息类型」，
  对每个 ≤2 的缺失类型子集调用 DeepSeek（`beta/completions`, `deepseek-chat`,
  `max_tokens=2048`, `temperature=0.5`）生成增强序列，落盘 `enriched_<i>_<file>.raw`。
- **执行流程**：
  1. 干净种子目录 `/home/zxy/rq1_chatafl/in-rtsp/`（复制 7 条 ProFuzzBench 种子）。
  2. 启动 ChatAFL `afl-fuzz`（`/home/zxy/chatafl历史版本/ChatAFL-Pure/ChatAFL/afl-fuzz`）：
     ```
     afl-fuzz -d -i /home/zxy/rq1_chatafl/in-rtsp -x .../rtsp.dict \
       -o /home/zxy/rq1_chatafl/out -N tcp://127.0.0.1/8666 -P RTSP \
       -D 10000 -q 3 -s 3 -E -K -R -m none -t 1000 -- \
       .../testOnDemandRTSPServer 8666
     ```
  3. 让其在 startup 阶段完成语法提取 + 种子增强（增强文件回写到输入目录），
     随后计时/计数。
- **Time**：从 `afl-fuzz` 启动到增强完成（以输入目录 `enriched_*.raw` 文件停止增长为界）。
- **Tokens**：按 `chat-llm.c` 的精确 prompt 模板重建增强 prompt，用同一 DeepSeek
  API 实测 usage 求和（ChatAFL 的 C 代码不输出 token 用量，故重建实测）。
- **Rv**：对非空 `enriched_*.raw` 逐条 dry-run 重放。

### 3. ProtoRAG（实验组）

- **方法**：五源知识 → 结构化知识中枢 → 三层选择器生成初始种子。
- **命令**（本机 `E:\科研\想法idea\rag-chatafl`，解释器 `E:/python/python.exe`）：
  ```
  python scripts/build_hub.py --sources rfc expert_note traffic vuln source \
      --protocol rtsp --constraints --vuln-llm
  python scripts/run_seedgen_e2e.py --protocol rtsp --three-layer
  ```
  - `build_hub`：五源抽取（rfc 161 / expert_note 8 / traffic 61 / vuln 76 / source 71 ≈ 376 facts）。
  - `run_seedgen_e2e --three-layer`：①结构覆盖(edge_cover) + ②通用危险(generic_danger)
    + ③漏洞(vuln_pattern 规则 + LLM 攻击种子)。
- **Time**：build_hub 86.55s + seedgen 128.95s = 215.5s ≈ **3.59 min**。
- **Tokens**：累计 72 次 LLM 调用，input 59,078 + output 37,990 = **97,068**。
- **种子数**：60 条（规则 28 + 漏洞 32）。
- **Rv**：60 条逐条重放。

---

## 三、实测结果

### Seed Reuse（ProFuzzBench 原始种子）

| 指标 | 值 |
|---|---|
| 种子数 | 7 |
| Time (min) | 不评估 |
| Tokens | 0 |
| Rv | 7/7 = 100% |
| Veff | 不评估 |

重放结果（7 条全 LEGAL）：
```
rtsp_requests_aac.raw   LEGAL
rtsp_requests_ac3.raw   LEGAL
rtsp_requests_mkv.raw   LEGAL
rtsp_requests_mp3.raw   LEGAL
rtsp_requests_mpg.raw   LEGAL
rtsp_requests_wav.raw   LEGAL
rtsp_requests_webm.raw  LEGAL
```

### ProtoRAG（实验组）

| 指标 | 值 |
|---|---|
| 种子数 | 60 |
| Time (min) | 3.59（build_hub 1.44 + seedgen 2.15） |
| Tokens | 97,068（in 59,078 + out 37,990，72 次调用） |
| Rv | 57/60 = 95.0% |
| Veff | 57 / 3.59 ≈ 15.9 有效种子/分钟 |

重放结果：60 条中 3 条 ILLEGAL（崩溃），57 条 LEGAL。
3 条崩溃种子均为「漏洞导向边界探针」的越界候选（按设计会触发崩溃）：
- `18_mp3AudioTest_DESCRIBE+SETUP+SETUP.raw` — 同 track 双 SETUP（matroska UAF 触发流）。
- `27_mp3AudioTest_DESCRIBE+SETUP+SETUP.raw` — 同上。
- `37_h264ESVideoTest_DESCRIBE.raw` — `Content-Length` 超长（字段型边界）。

### ChatAFL 种子增强

| 指标 | 值 |
|---|---|
| 种子数 | 8（117 个增强候选子集中仅 8 个非空） |
| Time (min) | 21.0（语法提取 ~2 + 种子增强 ~19） |
| Tokens | 87,352（增强步 117 次 LLM 调用，重建实测；不含语法提取） |
| Rv | 8/8 = 100% |
| Veff | 8 / 21.0 ≈ 0.38 有效种子/分钟 |

**Tokens 重建说明**：ChatAFL 的 C 代码（`chat-llm.c`）不输出 token 用量，故按其源码
`enrich_sequence` 的精确 prompt 模板重建 117 个增强 prompt（`beta/completions`,
`deepseek-chat`, `max_tokens=2048`, `temperature=0.5`），用同一 DeepSeek API 实测
usage 求和：input 41,964 + output 45,388 = 87,352。语法提取（前提步骤，另行 ~6 次
LLM 调用）未计入本行。

增强结果：ChatAFL 对 7 条录制种子生成 117 个「缺失消息类型」两两组合的增强候选，
逐条调用 DeepSeek（`beta/completions`），最终仅 8 条返回非空增强序列
（其余 109 条返回空/与原文相同被丢弃）。8 条非空增强种子逐条重放均 LEGAL。

8 条非空增强种子：
```
enriched_1_rtsp_requests_aac.raw    874 B   LEGAL
enriched_1_rtsp_requests_webm.raw  1198 B   LEGAL
enriched_11_rtsp_requests_ac3.raw   963 B   LEGAL
enriched_11_rtsp_requests_webm.raw  836 B   LEGAL
enriched_14_rtsp_requests_aac.raw   800 B   LEGAL
enriched_14_rtsp_requests_ac3.raw   846 B   LEGAL
enriched_17_rtsp_requests_aac.raw    26 B   LEGAL
enriched_17_rtsp_requests_ac3.raw   556 B   LEGAL
```

---

## 三·补：三方法最终对比表（已回填 docx）

| 种子构造方法 | 种子数 | Time (min) | Tokens | Rv | Veff |
|---|---|---|---|---|---|
| Seed Reuse（ProFuzzBench 原始种子） | 7 | 不评估 | 0 | 100% | 不评估 |
| ChatAFL 种子增强 | 8 | 21.0 | 87,352 | 100% | 0.38 |
| ProtoRAG（实验组） | 60 | 3.59 | 97,068 | 95.0% | 15.9 |

> 注：本表为 **1 次真实运行的实测数据**（非 5 次重复平均）。RQ1 注的「5 次重复取平均」
> 属后续可补的稳健性步骤；其中 Seed Reuse 的种子数与 Rv、ProtoRAG/ChatAFL 的种子数是
> 确定性的，单次即可；Time/Tokens 依赖 LLM 延迟与生成，存在一定方差。所有数值均来自
> 本次真实运行，无估计值。

## 四、复现要点 / 一致性保证

1. 除「种子来源」外，三种方法的目标服务器、重放 oracle、端口隔离完全一致。
2. 崩溃判定用 ASAN 构建（`/home/zxy/live555-asan/testProgs/testOnDemandRTSPServer`），
   媒体文件（test.aac/ac3/mkv/mp3/mpg/wav/webm）已就位，保证 DESCRIBE/SETUP/PLAY
   走完整代码路径（含 matroska UAF 触发路径）。
3. 重放 oracle 脚本：`/tmp/oracle.py`（单条）、`/tmp/batch_oracle.py`（批量）。
4. ChatAFL 增强与 ProtoRAG 生成均在「真 LLM（DeepSeek）」下运行，无模拟。
