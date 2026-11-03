# 「只靠 RFC 源行不行？」—— 与 FlowFSM / SpecGPT / SemFuzz 的口径对比与改进路线

> 批次 2.4。核实时间：2026-11-03
> 对标对象：FlowFSM（arXiv 2507.11222）、SpecGPT（arXiv 2510.14348）、SemFuzz（arXiv 2603.05989）
> 所有数字均标注来源链接；查不到确切来源的一律标「未确认」，**不猜**

---

## 0. 一句话回答

**别人的工作「效果好」，但他们测的和我们测的不是同一件事。**
他们报的是**「知识抽取准确率」**（转换级 P/R/F1）与**「测试用例语法可发送率」**；
我们报的是**「种子覆盖广度」**（能生成多少条、能覆盖多少状态机边）。
⇒ **不是我们不行，是我们在用不同的尺子量不同的东西，而且我们从没量过他们那把尺子。**

⇒ 我们真正的短板不是「覆盖率腰斩」，而是**没有「抽取准确率」这个评测维度**
（没有人工标注的 ground truth ⇒ 算不出 P/R/F1 ⇒ 无法与任何前人对话）。

---

## 1. 三篇的**确切**指标口径（逐篇核实）

### 1.1 FlowFSM（IEEE IMSA 2025，DOI 10.1109/IMSA65733.2025.11166906）

- [arXiv abs](https://arxiv.org/abs/2507.11222) · [arXiv HTML](https://arxiv.org/html/2507.11222v1) · [IEEE Xplore](https://ieeexplore.ieee.org/document/11166906)
- 对象：**FTP（RFC 959）+ RTSP**，**只从 RFC 文本抽状态机，不涉实现**
- 指标：**状态转换级** TP/FP/FN，人工核对 RFC 判定正确
  - `Precision = TP/(TP+FP)`，`Recall = TP/(TP+FN)`，`F1 = 2PR/(P+R)`
  - FTP：TP 90 / FP 18 / FN 12 ⇒ **P 83.33 / R 88.24 / F1 85.71**
  - RTSP：TP 18 / FP 4 / FN 3 ⇒ **P 81.82 / R 85.71 / F1 83.72**
  - 可推算（非原话）：FTP 有效转换 102 条、RTSP 21 条
- **没有自测基线**（PROSPER / Hermes / RFCNLP 的数字全是转述）
- **没有消融**
- 人工：人工核对 RFC；**人数/工时/一致性未报告**
- LLM：仅抽取（llama3.3-70b / deepseek-r1-distill-llama-70b / llama3-70b）
- **没有做 fuzzing**（fuzzing 是 future work）⇒ **无覆盖率、无 crash、无漏洞**
- 状态数：**从不报告**
- 开源 ✅ `github.com/YoussefMaklad/FlowFSM`

### 1.2 SpecGPT（arXiv v1 + SECON 2026 poster）

- [arXiv abs](https://arxiv.org/abs/2510.14348) · [arXiv HTML](https://arxiv.org/html/2510.14348v1) · [DBLP](https://dblp.org/pid/237/8451.html?view=bibtex)
- 对象：**5G NAS（TS 24.501）/ NGAP（TS 38.413）/ PFCP（TS 29.244）**，Release 17（另用 NAS R15 做泛化）
- Ground truth：**NAS = 18 states / 179 transitions**（唯一明确给出的规模）；**NGAP、PFCP 数量未确认**
- 指标：**状态转换四元组** `(S_init, A, C, S_next)`，匹配规则 =
  **状态严格相等 + action/condition 的 span 重叠 ≥ 0.75**
- 结果：
  - NAS **5 模型集成**：P 91.86 / R 90.43 / **F1 91.14**（单模型 F1 68.77–85.29）
  - PFCP-all 87.80 / NGAP-all 69.31
  - ⚠ **论文内部数据瑕疵**：PFCP-association 行 P 85.71、R 84.04，按其自身公式 F1 应 ≈84.87，表中却写 80.00
- 基线：Hermes（**论文自己声明 ground truth 不同，非严格对比**）、NEUTREX、naive prompting（**F1 仅 14.87%**）
- **没有消融**（仅单模型 vs 集成）
- 人工：**>210 人时**、多位领域专家、交叉验证 + 同行评审；**人数与 kappa 未报告**
- LLM：仅抽取，5 模型集成投票（GPT 4o / DeepSeek V3 / Qwen Turbo / Claude Sonnet 4 / Gemini 2.5 Pro，temp 0.2）；成本 NAS ≈$2.7/次
- **没有做 fuzzing** ⇒ 无覆盖率、无漏洞
- 开源 **未确认**

### 1.3 SemFuzz（**WWW 2026 主会**，DOI 10.1145/3774904.3792541，pp. 3251–3262，Dubai）

- [arXiv abs](https://arxiv.org/abs/2603.05989) · [arXiv HTML](https://arxiv.org/html/2603.05989v1) · [Crossref](https://api.crossref.org/works/10.1145/3774904.3792541) · [ACM DL](https://dl.acm.org/doi/10.1145/3774904.3792541)
- 对象：**7 个真实实现** —— Dns.exe / Tcpip.sys / Schannel.dll / Http.sys（Win Server 2022+2016）+ OpenSSL 3.1.3 / LibreSSL 3.4.0 / Nginx 1.27.2（Ubuntu 20.04）；协议 DNS(1035) / IPv6(8200) / TLS1.3(8446) / HTTP1.1(7230)
- 规模：**语义规则 1,721 条**（624/540/298/259）、RFC 段落 1,318、生成 **5,940** 条策略与测试用例、IANA 手工挑 **44** 种消息类型（~20 分钟）
- 指标**三套，彼此不同**：
  1. 规则抽取 P/R/F1（严格 message + field name 一致）：均值 **.80/.88/.84**
  2. mutation strategy 正确性（人工判定）
  3. **测试用例准确率 = 语法可编码 + 可成功发送**（原文："a test case is deemed correct if it can be properly encoded and successfully sent"）：**宏平均 87%**，平均 **1,271** 条
  4. 漏洞 oracle = 实际响应 ≠ 预期响应
- ★ **「36% → 87%」的确切含义**（消融 Table 5 + §4.4 原文）：
  > "When this module is disabled (w/oAction), the system produces only 534 correct cases, and the accuracy drops sharply to 36%."
  - 对比双方：**完整 SemFuzz vs w/oAction**（关掉「高层 action sequence 生成」模块 ⇒ LLM 直接改写 seed message），**不是**两种 mutation strategy 互比
  - 数据集：全部 4 个协议，**宏平均**
  - 指标含义：**测试用例的语法可发送率** —— **不是**协议符合率、**不是**覆盖率、**不是**漏洞检出率
  - **绝对 +51 个百分点；相对 +141.7%**（论文引言的 "increasing test accuracy by 142%" 是**相对**口径）
  - 增益高度不均：TLS 1.3 **79→6**、IPv6 **91→22** 崩塌最狠；HTTP/1.1 仅 88→70
- 漏洞：**16 potential → 10 confirmed（检测准确率 62.5%）**，5 个此前未知，**4 个 CVE**（CVE-2021-24074 / CVE-2022-34718 / CVE-2023-28233 / CVE-2023-28234）
- 基线（Table 4，漏洞数）：ChatAFL 1 / Fuzztruction-Net 0 / Hdiff 2 / **BLEEM 5** / **SemFuzz 10**（union 11）；**AFLNet 仅经 ChatAFL 体现，Fuzz4All 全文未出现**
- **明确不使用 code coverage**（原文：黑盒场景下对闭源实现插桩不可行）⇒ **无任何覆盖率指标**
- 人工：**28 小时、8 名网络安全硕士生**独立交叉标注 + 专家仲裁；**kappa 未报告**
- LLM：**三重角色** —— 抽取 + 生成测试用例与策略（GPT-4o 主，GPT-5 / Gemini 对比）；**预言机非 LLM**
- 开源 **未确认/暂无**

---

## 2. 口径可比性（**最重要的一节**）

### 2.1 绝对不可直接比较

| 不可比的两组 | 为什么 |
|---|---|
| FlowFSM **F1 85.71** vs SpecGPT **F1 91.14** | 协议域不同；**计数单位不同**（3 元组 vs 含 condition 的 4 元组 + 0.75 重叠）；ground truth 构造强度不同（210+ 人时 vs 未报告）；分母差两个数量级（102/21 条 vs 179 条及未知） |
| SemFuzz **87%** vs 任何抽取 F1 | 分母是**测试用例条数**，分子是「可编码可发送」——**门槛极低**（改一个无关字节也算通过）；与「知识抽得准不准」正交 |
| SemFuzz **62.5%** vs 另两篇的 0 | 分母是 16 个 potential vulnerability，衡量的是**厂商确认环节的精确率**；FlowFSM/SpecGPT 报告 0 漏洞是因为**根本没做安全评估** ⇒ 「4 CVE vs 0」是**范畴错误** |

### 2.2 **「状态数 / 转移边数」没有共同分母**

| 论文 | 「状态数」指什么 | 「转移/边」指什么 | 可用绝对数 |
|---|---|---|---|
| FlowFSM | **从不报告** | 人工核对过的状态转换 | 转换可推算（102/21）；状态未报告 |
| SpecGPT | 18 states（**仅 NAS**） | 四元组转移（含 condition） | NAS 179 转换；NGAP/PFCP 未确认 |
| SemFuzz | **完全不用 FSM 状态** | 无状态机边 | 规则 1,721 条 / 消息类型 44 / 用例 5,940；状态边数**不适用** |

⇒ 任何「谁的模型更大/更全」的比较都**没有共同度量基础**。

### 2.3 我们与他们的尺度差在哪

| 维度 | 前人报什么 | 我们报什么 | 可比吗 |
|---|---|---|---|
| 知识抽取**准确性** | 转换级 P/R/F1（人工标注真值） | **没有**（无 ground truth ⇒ 算不出） | ❌ **我们缺这一维** |
| 抽取**覆盖广度** | NAS 179 转换 / FTP 102 转换 | 骨架 145 facts、RFC 自己 12–14 转换 | ⚠ 单位不同（fact ≠ 转换） |
| 生成物**质量** | test-case validity 87%（可编码+可发送） | G1 端点正确率、G2 不可播会话占比 | ❌ 不同维度 |
| 生成物**数量** | 5,940 用例 / 4 协议 | 85 条 / 1 协议 | ⚠ 可比（同为「条数」），但绝对量受协议规模支配 |
| **漏洞** | SemFuzz 10 confirmed / 4 CVE | 未做（我们还没到那一步） | — |
| **覆盖率** | **三篇都没有** | 我们有 G1/G2（但口径不同） | ⚠ 我们反而有他们没有的 |

---

## 3. 所以「为什么我们不行」？—— 三个真实原因（不是「效果差」）

### 原因 1：我们量的是「覆盖广度」，他们量的是「抽取准确率」⇒ **不可比，不是差**
我们的 85 → 43 说的是「能生成多少条种子」；SemFuzz 的 87% 说的是「生成的用例有多少能发出去」。
⇒ **要对话，必须补上「抽取准确率」这一维**。

### 原因 2：我们**从未测过「纯 RFC」的准确率**，所以「覆盖率腰斩」里有多少是「抽得不准」、多少是「规范本身就少」，**分不清**
- 纯 RFC 档 43 条里，只有 **12 条状态机**（RFC 自己抽的）—— RTSP 客户端状态机在 RFC 2326 里本来就是有限的
- 但**我们不知道这 12 条里有多少是对的** ⇒ 缺 ground truth
- ⇒ **这是我们最大的短板**，也是最该补的一块

### 原因 3：我们的「消融」比他们多了一层，但**没有把他们的方法吃进来**
- SemFuzz 的核心创新 = **「高层 action sequence 生成」模块**（把「什么动作序列能违反哪条语义规则」显式建模），**关掉它 87%→36%**
- ⇒ **我们的 ⑤ 层 action_seq 正是同一个思路**（从语义规则派生动作序列）
- ⚠ 但我们的批次 1 结论是「**价值指标（G2 / SemFuzz「36%→87%」）未兑现**」⇒
  **那是因为我们拿 G2（不可播会话占比）去对标 SemFuzz 的 test-case validity（可编码可发送率）—— 口径错配！**
  ⇒ 这不是「我们的机制无效」，而是「**我们用错了尺子**」。

---

## 4. 改进路线（按「能否与前人对话」排序）

### P0 —— 补「抽取准确率」评测（**没有这个，一切对比都是空谈**）
1. **建 ground truth**：人工标注 RTSP 状态机（照 SpecGPT 口径：初态/动作/条件/目标态四元组）。
   - 规模参照：SpecGPT 的 NAS 是 **18 状态 / 179 转换、210+ 人时**；
     我们可先做**子集**（如 RFC 2326 附录 A.1 的客户端状态机，实测确定性抽取已能抽 14 条，与原文逐条一致）⇒
     **用确定性抽取做初版真值，人工只做复核** ⇒ 工时可压到人时级。
2. **对齐匹配规则**（SpecGPT 口径）：状态严格相等 + action/condition span 重叠 ≥ 0.75
   ⇒ 报 **转换级 P/R/F1**，与 FlowFSM / SpecGPT **同族可比**。
3. ⚠ **先修跨协议污染**（审计 P0-2：RTSP 规则库里 3/5 条是 SIP 的 RFC 3261）⇒ 否则算出来的 F1 是错的。

### P1 —— 把指标口径补齐到 SemFuzz 那一层（**让「36%→87%」可比**）
- **报 test-case validity**：种子「可编码 + 可成功发送」的比例（SemFuzz 的 87% 口径）
  ⇒ 我们现在只有 G1（端点正确）/ G2（可播会话）⇒ **新增一个「可发送率」**即可与 SemFuzz 对齐。
- ★ 我们的 ⑤ 层已经有现成机制（`action_seq`）⇒ 只需加一个判定器
  （尝试把每条种子编码成协议报文并发送/解析 ⇒ 成功即有效）。
- ⇒ 这样就能复现「关掉 action_seq 模块会掉多少」的消融 ⇒ 与 SemFuzz 同口径。

### P2 —— 补 SemFuzz 的「规则驱动预言机」
SemFuzz 的漏洞判据是**规则驱动**（实际响应 ≠ 预期响应），**不是 LLM 判定**。
⇒ 我们已有 `rfc/semantic/rules.jsonl`（规则）+ `response_expectation` 投影 ⇒ **基础设施已在**
⇒ 只差把规则库按协议过滤（P0-2）并接上响应比对。

### P3 —— 用上「5 模型集成」（SpecGPT 的实证增益）
SpecGPT：单模型 F1 68.77–85.29 ⇒ **5 模型集成 91.14**（+6pp 以上）。
⇒ 我们的 P1b（LLM 状态机）目前**单模型**⇒ 集成投票是低成本高回报的改进。
（SpecGPT 未明示最少票数，按 5 模型常规理解 ≥3 票，**原文未确认**。）

### P4 —— 保留并强化我们**比他们多**的东西
- **消融轴**：规范 / +实现 / +观测 三档（前人**都没有**这个轴；SemFuzz 只做了单系统的模块消融）
  ⇒ 我们的**多源异构知识增强**定位在 related work 里是**空位**。
- **可审计的语料准入闸**（G1/G2/G5 + 分层比率）：SemFuzz **明确不用覆盖率**，只认「可验证漏洞」
  ⇒ 我们的闸门体系是**另一条独立贡献线**，但必须把口径写清楚（否则被误读成覆盖率）。
- **确定性优先**：SpecGPT / FlowFSM 都靠 LLM 抽状态机；我们的**确定性表抽取 + LLM 兜底**
  （RTSP A.1 表抽取与原文逐条一致）⇒ **可复现性**是卖点，应写进论文。

---

## 5. 论文定位建议（一句话版）

> **不要**和 FlowFSM/SpecGPT 比「谁的 F1 高」（我们还没做 F1，也不需要比 —— 它们的 ground truth 与我们不可通约）；
> **也不要**和 SemFuzz 比「谁挖的漏洞多」（我们还没到那一步）。
> **要**做的是：**把「规范知识 → 可审计语料准入」这条链做深，并诚实地报出「规范单源能覆盖什么、不能覆盖什么」** ——
> 这恰恰是前人三篇都**没有回答**的问题（它们都不做消融、不报覆盖广度、不区分知识来源）。

⚠ 对应到我们已产出的数据：**「真·纯净 RFC 只有 10 条种子被纯 RFC 知识支撑」**
这个结论**本身就是论文的一个诚实、可量化、且前人没有的发现** ——
它直接量化了「规范知识的边界」，比再报一个 F1 更有信息量。

---

## 6. 参考文献（全部带来源链接）

1. FlowFSM — arXiv:2507.11222 · https://arxiv.org/abs/2507.11222
   · IEEE IMSA 2025: https://ieeexplore.ieee.org/document/11166906
   · 代码: https://github.com/YoussefMaklad/FlowFSM
2. SpecGPT — arXiv:2510.14348 · https://arxiv.org/abs/2510.14348
   · DBLP: https://dblp.org/pid/237/8451.html?view=bibtex
3. SemFuzz — arXiv:2603.05989 · https://arxiv.org/abs/2603.05989
   · WWW '26: https://dl.acm.org/doi/10.1145/3774904.3792541
   · Crossref: https://api.crossref.org/works/10.1145/3774904.3792541
