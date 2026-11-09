# 多导向自适应种子生成方案（Multi-Strategy Adaptive Seed Generation）

> 目标：让种子生成不再"一刀切"（18 流名→18 个正常会话），而是根据知识中枢里**实际有哪些知识源**，自适应地选择生成导向与优先级，尤其在有漏洞信息时走「漏洞导向」，把历史漏洞翻译成针对性触发种子，从而提升漏洞发现概率、覆盖率、favored 路径与状态机边。

---

## 一、调研结论（相关工作经验）

| 工作 | 领域 | 可借鉴点 |
|---|---|---|
| **Balancing Validity and Vulnerability** (Applied Sciences 2025) | DL 库 fuzz | **多臂老虎机(MAB)**：把每个知识源构造成一个 prompt（arm），用 reward 实时反馈动态选 arm，平衡「有效性」与「漏洞发现」。最直接的"多导向自适应"先例 |
| **ChatHTTPFuzz** (arXiv 2024) | IoT HTTP fuzz | LSTE 种子模板丰富化 + STSA 双因子增益种子调度（强化学习/Thompson Sampling） |
| **SmartChat** (硕士论文) | 智能合约 fuzz | **Vulnerability-Guided Prioritization**：漏洞导向优先级算法，引导 fuzz 到可能暴露缺陷的序列 |
| **LLAMA** (IEEE TIFS 2026) | 智能合约 fuzz | 分层提示 + bandit 调度 + 多反馈引导，联合优化种子选择与变异调度 |
| **MALF** (arXiv 2025) | 工控协议 fuzz | 多 Agent（种子生成/用例生成/反馈分析）+ CoT + RAG |

**关键结论**：主流做法是把「多源知识」建模为「多个生成策略」，用 **MAB/bandit 动态调度**而非把所有知识塞进一个 prompt。这与我们当前"全量分桶一次性喂"形成对比——我们缺的是「导向选择 + 优先级」这一层。

---

## 二、五个导向的定义与优先级

按"对漏洞发现/深覆盖的贡献度"定优先级，同时区分「独立生成策略」与「贯穿性约束」两类：

| 优先级 | 导向 | 触发条件（知识库有该源） | 角色 | 生成目标 |
|---|---|---|---|---|
| **P0** | 漏洞导向 Vulnerability-Guided | vuln 源有数据 | 独立策略 | 针对漏洞字段+触发模式生成畸形/边界种子 |
| **P1** | 实例导向 Instance-Guided | source 源有资源清单 | 覆盖目标 | 覆盖全部流名（资源清单） |
| **P2** | 流量导向 Traffic-Guided | traffic 源有请求模板 | 贯穿约束 | 所有种子参照真实请求模板（Range 头/尾斜杠） |
| **P3** | 结构导向 Structure-Guided | rfc/expert_note 有数据 | 覆盖目标 | 覆盖方法/字段/取值池 |
| **P4** | 状态机导向 StateMachine-Guided | 有状态机知识 | 覆盖目标 | 覆盖状态转移路径 |

**优先级语义**：
- P0 漏洞导向是「增量生成」——有漏洞就额外产出一批攻击性种子，不替代正常种子；
- P2 流量导向是「全局约束」——无论哪个导向，生成的消息都必须满足请求真实性；
- P1/P3/P4 共同决定「正常会话种子」的覆盖维度（覆盖哪些流名 × 哪些方法 × 哪些状态路径）。

---

## 三、自适应判断逻辑（有漏洞 → 漏洞导向，无 → 其他导向）

```python
def determine_strategies(bundle, resources, request_templates, security):
    """按知识中枢实际有哪些知识源，返回激活的导向及角色。"""
    strategies = {"normal": [], "attack": [], "constraints": []}

    # 贯穿约束：请求真实性（有请求模板则启用）
    if request_templates:
        strategies["constraints"].append("traffic_guided")

    # 覆盖目标：实例 / 结构 / 状态机
    if resources:
        strategies["normal"].append("instance_guided")
    if bundle.get("methods") and bundle.get("required_headers"):
        strategies["normal"].append("structure_guided")
    if bundle.get("transitions"):
        strategies["normal"].append("state_machine_guided")

    # 独立策略：漏洞导向（最高优先级，有则激活）
    if security:
        strategies["attack"].append("vulnerability_guided")

    return strategies
```

**判断规则一句话**：`security`（vuln 源）非空 → 走漏洞导向（额外生成攻击种子）；为空 → 退化为纯覆盖导向（正常种子）。

---

## 四、组合策略（不止单源导向）

种子生成分两路产出，多源在每路内**融合**而非单选：

```
┌─ 正常种子路（覆盖导向，P1×P3×P4，受 P2 约束）────────────┐
│  instance_guided(选流名) × structure_guided(选方法/字段)    │
│  × state_machine_guided(选路径) → 生成合法真实会话         │
│  （所有消息必须满足 traffic_guided 的请求模板）             │
└──────────────────────────────────────────────────────────┘

┌─ 攻击种子路（漏洞导向，P0，受 P2 约束）──────────────────┐
│  对每条漏洞(字段+触发模式+后果) → 生成针对性畸形种子       │
│  例：Transport 空值 / Authorization 超长 / interleaved→非  │
│      interleaved SETUP 序列 / 大量 client_port            │
└──────────────────────────────────────────────────────────┘
```

- 正常种子路 = 当前已有逻辑（分桶 + 资源清单 + 请求模板），保证覆盖；
- 攻击种子路 = 新增逻辑，把 security 桶的漏洞翻译成畸形种子，保证攻击性；
- 两路种子合并写入语料库，fuzzer 同时获得「覆盖面」与「攻击性」。

---

## 五、漏洞信息如何翻译成种子（P0 核心）

security 桶里每条是 `(subject_type, field, desc)`，desc 里已含「字段 + 触发方式 + 后果」。翻译规则（规则抽取，不靠 LLM 猜）：

| 漏洞描述关键词 | 翻译成的种子动作 |
|---|---|
| "空值 / NULL 指针解引用" | 该字段置空或缺失 |
| "超长 / 栈缓冲区溢出 / strcpy" | 该字段填超长值（>1000 字节） |
| "不递增 / 重放" | 连续两条相同 CSeq |
| "大量 client_port" | Transport 填 N 个 client_port 参数 |
| "interleaved → 非 interleaved" | 先 `RTP/AVP/TCP;interleaved=0-1` SETUP，再普通 SETUP |

**实现方式**：写一个 `classify_vuln(desc)` 规则函数，从 desc 匹配关键词 → 输出「字段 + 动作」，再交给 LLM 生成具体畸形消息（或直接规则生成，不依赖 LLM）。

---

## 六、代码实现设计

```
core/fused/downstream/
├── rag_seedgen.py          # 现有：分桶 + 渲染 + 生成 + 校验
└── strategy.py  (新增)      # 导向判定 + 漏洞翻译
    ├── determine_strategies(bundle, resources, templates, security) -> dict
    ├── classify_vuln(desc) -> (field, action)        # 漏洞→动作翻译
    └── render_attack_prompt(security, templates)      # 漏洞导向 prompt
scripts/run_seedgen_e2e.py  # 集成：先判定策略，再分路生成
```

生成流程改造：

```
1. determine_strategies() 判定激活哪些导向
2. 正常种子路：generate_seeds_react(资源清单+请求模板+分桶)   # 现有逻辑
3. 攻击种子路：若 vulnerability_guided 激活 → generate_attack_seeds(漏洞)  # 新增
4. 合并两路 → write_seeds
```

---

## 六·实现状态（2026-10-13 已完成第一步「漏洞导向合法种子生成」）

> 本设计的第一步（P0 漏洞导向）已落地，具体实现与设计文档略有出入，记录如下，供后续接手者对照。

**已实现（与设计一致的部分）：**

| 设计项 | 落地文件/函数 | 说明 |
|---|---|---|
| determine_strategies | `strategy.py::determine_strategies` | 按 resources/templates/bundle/vulns 自适应判定 normal/attack/constraints |
| classify_vuln | `strategy.py::classify_vuln` + `classify_all` | CWE 编号 → 动作（第一层），触发条件关键词 → 更具体的序列型动作（第二层，优先级更高） |
| render_attack_prompt | `strategy.py::render_attack_prompt` | 复用分桶知识 + 追加漏洞需求，硬规则与正常种子一致 |
| generate_attack_seeds | `strategy.py::generate_attack_seeds` | 生成→校验→带错重生成（复用 validate_seed） |
| 集成 | `scripts/run_seedgen_e2e.py` | 新增 `--attack` / `--attack-only` 开关 |

**与设计的关键出入（更贴合「绝对合法」原则）：**

1. **漏洞信息源换成了结构化 KB**：设计 §五 原写「从 security 桶的 desc 文本匹配关键词」，
   实际改为直接读 `kb/历史漏洞/*.json` 的**结构化 trigger**（`trigger.method.value` /
   `trigger.field.value` / `trigger.condition.value` / `cwe_avd`），比 security 桶
   （只有 description_raw 文本）信息更丰富、更可翻译。49 条 CVE 全量解析。

2. **漏洞翻译动作分类**：设计 §五 的 5 条关键词表扩充为 15 种动作
   （empty_edge / long_value / int_edge / uaf_seq / lifecycle_seq / assert_seq /
   many_params / replay_seq / path_edge / auth_edge / inject_edge / double_setup /
   interleave_seq / abs_time_seek / multi_session / default），CWE 与条件关键词双层分类。

3. **去重 + 分批**：49 条 CVE 常共享同一漏洞模式（如多个「认证头超长溢出」），
   `dedupe_reqs` 按 (action, methods, fields) 去重为 31 个「漏洞模式」，
   每个模式产一个合法边界种子，避免逐条 CVE 生成导致 prompt 过长 / 种子冗余。

4. **字段值长度上限 256 字符**：实测发现 LLM 会因「超长」指引生成 6 万字符的 AAAA…
   填充串，导致输出被 max_tokens 截断 → JSON 解析失败。已在所有 long_value 指引与
   prompt 硬规则中显式约束「单字段值 ≤256 字符，边界由 fuzzer 变异探索」。

5. **`_render_vuln_guidance` 已接入正常种子路**：`rag_seedgen.py::render_seed_prompt`
   现在除原始「[安全关注]」段外，额外输出「[漏洞导向生成要求]」段（漏洞相关方法/字段
   → 合法覆盖指引），让正常种子也优先覆盖漏洞相关字段/序列。

**端到端验证（真 DeepSeek）**：
- `--attack-only`：49 CVE → 31 漏洞模式 → 31 条合法攻击种子（100% 通过 validate_seed）
- `--attack --n-seeds 6`：6 正常 + 24 攻击 = 30 条（LLM 非确定性下个别批次 0 条，
  由 max_rounds 重试兜底）
- 攻击种子正确覆盖序列型（SETUP+SETUP 双 SETUP、SETUP+TEARDOWN+SETUP 生命周期、
  interleaved→普通 SETUP）与字段型（空 Digest 认证、偏长 Authorization）边界。
- 全量 pytest：135 passed。

**剩余（二期，见 §七）**：MAB 动态调度、漏洞种子高潜力标记、跨协议漏洞迁移。

---

## 七、演进方向（可选，二期）

1. **MAB 动态调度**：仿「Balancing Validity and Vulnerability」，把每个导向做成一个 arm，用 fuzzer 反馈（新增覆盖/崩溃）作为 reward，动态分配各导向的生成配额，替代静态优先级。
2. **漏洞导向 + 变异调度联动**：把漏洞种子标记为「高潜力」，交 fuzzer 优先变异（呼应 ChatHTTPFuzz 的 STSA）。
3. **跨协议漏洞迁移**：仿 DL 库那篇的「同 API 漏洞可迁移」思路，把 RTSP 某字段的漏洞模式迁移到结构相似的协议字段。
