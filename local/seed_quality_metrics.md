# local/seed_quality_metrics.md — 初始种子质量衡量指标调研

> 定位：Phase 5（fuzz 结果反馈 → 定向再生成）的**反馈指标选型依据**。
> 回答「哪些指标最能衡量生成种子的质量」，供闭环「解析反馈 → 决定再生成」选对信号。
>
> 落盘日期：2026-10-20
> 调研对象：协议 fuzzing + LLM 种子生成方向的同类型论文（GLMFuzz / MALF / LLM4Fuzz / SyzGPT / SeedMind / PSG / ChatAFL）

---

## 一、核心结论（一句话）

**协议 fuzzing 的「种子质量」公认由三层指标构成，从基础到终极：合法性（能不能被接受）→ 多样性（取值够不够散）→ 有效性（让 fuzzer 跑出多少状态覆盖/崩溃）。其中「状态转移/状态覆盖」是协议 fuzzing 最受重视、最能体现种子质量的指标，应作为 Phase 5 主反馈信号；代码覆盖只是辅助。**

---

## 二、三层指标框架总览

| 层 | 指标族 | 衡量什么 | 是否需跑 fuzz |
|---|---|---|---|
| ① 合法性 | Validity / 接受率 | 种子能不能被目标接受（不崩、不拒） | 否（dry-run 重放即可） |
| ② 多样性 | Shannon Entropy / 组合覆盖 | 种子取值够不够分散 | 否（静态统计） |
| ③ 有效性 | 状态覆盖 + 代码覆盖 + 漏洞发现 | 种子让 fuzzer 跑出多少覆盖/崩溃 | 是（跑 fuzz 后） |

---

## 三、第一层：合法性（种子本身质量的第一道门槛）

LLM 生成种子最痛的短板是「合法率低」（Fuzz4All 合法率显著偏低、FuzzGPT 仅 27.43% / 17.41%），故「合法性」被所有论文单列为种子质量第一指标。

| 指标 | 定义式 | 出处 |
|---|---|---|
| **Validity Rate** | 语法+语义有效种子数 / 总种子数 | LLM4Fuzz 愿景（arXiv 2503.00795） |
| **TCPR / TCAR（接受率）** | TCPR = #(passed) / #(total)，被 SUT 接受的用例比例 | MALF（arXiv 2510.02694） |
| **SVR（语法有效率）** | SVR = N_syn / N_total，通过语法检查的程序占比 | SyzGPT（ISSTA 2025） |

**实测量级**：MALF TCPR 88–92% > NCMFuzzer 83% > ChatAFL 81% > Peach 74%。

**本项目映射**：已具备 —— `oracle` dry-run 重放（`probe_boundary` / `run_boundary_probe.py`），重放不崩 = 合法，即论文的 Validity/TCPR。

---

## 四、第二层：多样性（合法之外，还要「散」）

「合法但单一」的种子无法支撑 fuzzer 变异探索，故「多样性」被 MALF / SyzGPT 单列为种子质量第二指标。

| 指标 | 定义式 | 出处 |
|---|---|---|
| **Shannon Entropy** | H(X) = −Σ p(x_i)·log₂ p(x_i)，字段取值的香农熵 | MALF（2510.02694） |
| **Field-value Combo 覆盖** | 覆盖的「字段-取值」组合数 / 规范定义的总组合数 | MALF（2510.02694） |
| **Program Diversity** | 平均程序长度 + 平均 syscall 数 | SyzGPT（ISSTA 2025） |

**实测量级**：MALF 香农熵 4.45 bits > Fuzz4All 4.0 > MARLFuzz 3.8。

**本项目映射**：**缺失** —— 目前没有量化「种子取值是否多样」。建议补：对种子语料的字段取值计算香农熵，防「合法但规整、离崩溃边界远」的种子（对应 memory「合法种子变异效率低」的另一种表述）。

---

## 五、第三层：有效性（种子对 fuzz 的终极贡献）

这是「种子质量」的最终验证，分覆盖率类 + 漏洞发现类。

### 5.1 覆盖率类

| 指标 | 定义 | 出处 |
|---|---|---|
| **状态转移（State Transitions）** | 触发的状态转移数 | **GLMFuzz（QRS 2025）** |
| **状态覆盖（State Coverage）** | 覆盖的协议状态比例 | GLMFuzz / MALF（ISKG-defined state coverage） |
| **分支/代码覆盖（Branch/Code Coverage）** | 分支/代码行覆盖 | SeedMind（2411.18143）/ PSG |
| **路径覆盖（Path Coverage）** | 触发的不同执行路径数 | LLM4Fuzz 愿景 |

**★协议 fuzzing 的关键事实**：GLMFuzz 三项指标中「状态转移」提升最大（对 ChatAFL +16.48%、对 AFLNet +54.18%），「状态覆盖」次之（+4.97% / +14.57%），「代码覆盖」最小（+7.01% / +10.61%）。**原因是协议是有状态的——种子的本质价值是「能把你带到多深的协议状态」，而非单纯刷代码行覆盖。**

### 5.2 漏洞发现类

| 指标 | 定义 | 出处 |
|---|---|---|
| **Vulnerability Discovery Rate** | 发现的唯一漏洞数（按严重度分类） | LLM4Fuzz 愿景 |
| **ETN（Exception Triggers Number）** | 崩溃数（ETNᵢ = cycle i 的 crash 数） | MALF |
| **Time-to-Reach / Time-to-Trigger** | 到达 / 触发 bug 的时间 | SeedMind（MAGMA 基准） |

---

## 六、本项目落地映射

| 优先级 | 指标 | 本项目现状 | 落地动作 |
|---|---|---|---|
| ★主指标 | **状态转移 / 状态覆盖**（n_edges） | ✅ 已有（98.4 vs 83.2 反超） | Phase 5 用它当主反馈信号，替代代码覆盖「停滞」 |
| ★基础门槛 | **合法性**（oracle dry-run 接受率） | ✅ 已有 | 保持「绝对合法」铁律，oracle 把关 |
| ⭐待补 | **多样性**（字段值 Shannon Entropy） | ❌ 缺 | 加一个静态统计：对种子语料字段取值算香农熵 |
| 辅助 | 崩溃数 / 崩溃归因 | ✅ 有雏形（之前手动做过崩溃根因去重） | 自动化 + 回写 vuln_pattern（差异化卖点） |

---

## 七、对 Phase 5 的直接指导

1. **主反馈信号用「状态覆盖缺口」而非「代码覆盖率停滞」**：
   - 对比知识中枢状态机（`bundle["transitions"]` 的边）与 fuzzer 实际覆盖的状态，找「可达但未覆盖」的边 → 定向补。
   - 「停滞」是模糊信号（可能是目标探索完了），「具体哪些边没走到」是可操作信号。

2. **合法性作「再生成」的硬约束**：定向再生成的种子仍须过 oracle dry-run，守住「接近但不触发」。

3. **补「多样性」量化**：对每轮种子语料算字段值香农熵，作为「是否该换策略」的辅助判据（熵长期偏低 → 种子太单一 → 增加多样性生成）。

---

## 八、参考文献

1. Zhu, Gan, Wang, Nan. **GLMFuzz: Vulnerability Knowledge Guided Prompting for Efficient Network Protocol Fuzzing**. QRS 2025.
2. **MALF: A Multi-Agent LLM Framework for Intelligent Fuzzing of Industrial Control Protocols**. arXiv 2510.02694.
3. **Towards Reliable LLM-Driven Fuzz Testing: Vision and Road Ahead**. arXiv 2503.00795.
4. **Unlocking Low Frequency Syscalls in Kernel Fuzzing with Dependency-Based RAG (SyzGPT)**. ISSTA 2025.
5. **Harnessing Large Language Models for Seed Generation in Greybox Fuzzing (SeedMind)**. arXiv 2411.18143.
