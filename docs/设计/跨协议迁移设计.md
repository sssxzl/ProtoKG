# 跨协议迁移能力设计

> 目标：更换协议知识库（即使仅含 5 类知识源的部分类别）时，无需重新训练或大幅改动即可正常使用。
> 参考：AFLNet（`-P <protocol>` 的 parser 抽象）、ChatAFL（LLM 从 RFC 自动提取协议语法）。

---

## 一、现有架构的迁移现状（诚实差距）

**已协议无关（迁移时不动）**：
- Layer 0 六元组知识原子 `⟨Subject, Aspect, Condition, Value, Epistemic, Evidence⟩`
- Layer 1 三注册表**机制**（subject_type/aspect/epistemic registry）
- `assemble_bundle` 分桶（**按 aspect 分桶，与协议无关**）
- `SeedCorpus/SeedMessage` 消息模型（method + headers + body + url，通用）
- `selector` 编排、RAG 检索、LLM 调用框架

**协议相关（迁移障碍，硬编码 RTSP）**：

| 位置 | 硬编码内容 |
|---|---|
| `strategy.py` | `_STREAM_HINT_MAP`（RTSP 流名）、`_ACTION_GUIDANCE`（SETUP/PLAY…）、`_CWE_ACTION` |
| `generic_danger.py` | `_NUMERIC_HEADER_NAMES`（CSeq…）、`_HEADER_DEFAULTS`（Transport/Session…） |
| `edge_cover.py` | `_HEADER_DEFAULTS` |
| `boundary_probe.py` | `_ACTION_BOUNDARY`、`_build_baseline`（DESCRIBE/SETUP…）、`_TRIGGER_SESSION`、`_setup_msg` |
| `raw_writers.py` | RTSP 序列化（`\r\n`、URL、方法特定头） |
| `rag_seedgen.py` | `render_seed_prompt` 硬编码示例（DESCRIBE/SETUP…） |
| `run_seedgen_e2e.py` | `_apply_stream_urls`（track1/尾斜杠） |

---

## 二、架构设计：三层分离 + ProtocolProfile

```
┌───────────────────────────────────────────────┐
│ 引擎层（协议无关，迁移时【零改动】）           │
│   selector / RAG / LLM / edge_cover /          │
│   generic_danger / boundary_probe /            │
│   assemble_bundle（按 aspect 分桶）            │
├───────────────────────────────────────────────┤
│ 协议适配层（协议相关，迁移时【仅换配置】）     │
│   ProtocolProfile:                            │
│     - 方法白名单     ← 从 facts 动态，无则 fallback │
│     - 头默认值       ← 从 required_headers 动态     │
│     - URL 模板       ← 从 url_template 动态         │
│     - 流名映射       ← 从 traffic facts 动态        │
│     - 消息序列化器   ← raw_writers 的协议适配器     │
│     - 危险 action 映射 ← _ACTION_GUIDANCE（可缺省） │
├───────────────────────────────────────────────┤
│ 知识层（协议无关，迁移时【换 facts】）         │
│   六元组 facts + 注册表 + 抽取(Layer 2，       │
│   协议相关但输出统一为六元组)                  │
└───────────────────────────────────────────────┘
```

**核心原则**：协议相关的一切（方法/头/URL/流名/序列化）都从**知识中枢动态推导**，引擎层不硬编码。硬编码只作为"知识源缺失时的 fallback 默认值"，且集中在一个 `ProtocolProfile` 里。

---

## 三、知识源抽象

1. **六元组协议无关**（已实现）：Subject/Aspect 用类型名（method/header/state），不绑定具体协议。
2. **抽取层协议相关、输出统一**：Layer 2 五源各自的抽取器是协议相关的（如 RFC 里 SETUP 的语法），但都输出六元组 facts。
3. **部分知识源降级**（关键）：
   - 无 `vuln` 源 → 漏洞层（③）跳过，`classify_vuln` 返回空；
   - 无 `traffic` 源 → 无流名映射，用 URL 模板默认；
   - 无 `semantic` 源 → 无 precondition/session_header，`generic_danger` 退化为纯状态机推导；
   - `assemble_bundle` 对缺失 aspect **天然容错**（返回空 dict），下游已有降级逻辑。

---

## 四、模型输入输出层面

- **输入**：facts（六元组）→ `assemble_bundle` → bundle（methods/headers/transitions/...），全程按 aspect 分桶，协议无关。
- **输出**：`SeedCorpus`（协议无关消息模型）→ `.raw`（协议相关）。**序列化器按协议抽象**：RTSP 用 `\r\n` + 空行分隔，换协议（如 SIP 也用 `\r\n`、DNS 用二进制）换序列化器即可。
- **LLM prompt**：知识区段（方法/字段/状态机/会话语义）协议无关；示例消息（DESCRIBE/SETUP…）应从 `ProtocolProfile` 动态生成，而非硬编码。

---

## 五、验证迁移性的测试方案

**测试协议**：SIP（状态机 + 文本协议 + 与 RTSP 结构相似但字段不同），仅提供 **rfc + traffic 两源**（故意缺 vuln/expert_note/semantic，验证"部分知识源"降级）。

**测试步骤**（断言核心引擎零改动）：

1. **知识层替换**：准备 SIP 的 facts（rfc/traffic 两源），替换 `derived/model/per_source/`；
2. **分桶验证**：`assemble_bundle` 能正常产出 methods/headers/transitions（协议无关，无需改动）；
3. **种子生成验证**：`select_seeds` 在无 vuln/semantic 源时降级（仅 ①②规则层），产出 SIP 种子，不报错；
4. **序列化验证**：`seedcorpus_to_raw` 产出 SIP 格式 .raw（换 SIP 序列化器）；
5. **fuzz 冒烟测试**：SIP 目标上能跑通 dry run（复用 ChatAFL `-P SIP` 的 parser）。

**可复现断言**：
```python
# 换协议后，以下代码应零改动跑通（只需换 facts 目录）
bundle = assemble_bundle(load_fact_views(sip_facts_root))
seeds = select_seeds(bundle)  # 无 vuln/semantic 自动降级
raw = seedcorpus_to_raw(seeds[0])  # 协议序列化器适配
```

---

## 六、实施优先级

1. **ProtocolProfile 骨架**：把 `raw_writers` 的序列化、`run_seedgen_e2e` 的 URL 补充、`render_seed_prompt` 的示例抽成 Profile（迁移时唯一需配置处）。
2. **消除引擎层硬编码**：`generic_danger`/`edge_cover`/`boundary_probe` 的头默认值、方法名改为从 bundle 动态取（已有 precondition/session_header/url_template 是雏形）。
3. **SIP 冒烟测试**：准备 SIP 两源 facts，跑通上面的断言。

> 注：当前字典对比实验仍在跑（至 14:50），本设计的**实施**建议在实验结束后进行；本文件先固化方案。
