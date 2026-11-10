# ProtoKG

> **Heterogeneous Protocol Knowledge Alignment for Fuzzing Seed Generation.**
> 异构协议知识的**对齐**与模糊测试种子生成。

规范 / 源码 / 抓包 / 漏洞 / 专家注记 —— 五种形态与证据强度迥异的协议知识，
**逐条对齐**到统一事实空间（带消解留痕与证据链）→ 按知识分类的结构化中枢
→ 实体关系图 + 社区 → 五层种子生成。

```
异构五源 ──抽取──▶ 源隔离事实（per_source/）
                        │
                        ▼  ★ 对齐层：统一事实空间 + claim 级消解 + 证据链
                 按知识分类的中枢（hub/）
                        │
                        ▼  ★ 知识图是「对齐之后」的下游投影
                 实体关系图 + 社区（graph/）
                        │
                        ▼
                 五层种子生成（seeds/）
```

## 为什么需要「对齐」

协议知识天然异构：规范给**约束**，源码给**实现**，抓包给**观测**，漏洞给**历史**，
专家注记给**判断**。它们的形态、粒度与证据强度都不同：

| 源 | 形态 | 证据强度（`epistemic_type`） |
|---|---|---|
| 规范 `spec` | 方法 / 头 / 状态 / 取值域 | `must` / `normative_unspecified` |
| 协议实现源码 | 方法签名 / 分支 / 字段用法 | `observed` |
| 数据流量 | 真实报文序列 | `observed` |
| 历史漏洞 | 触发条件 / 后果 | `observed`（带漏洞锚点） |
| 专家注记 | 人工逆向的结构与判断 | `descriptive` |

ProtoKG 的做法**不是**把它们压平成一种表示，而是：

1. **对齐到统一事实空间** — 五源各自的抽取结果归一到同一 `fact_key`
   （protocol / version / subject / aspect / condition），异构在此收敛；
2. **消解留痕** — 同一事实的多源陈述**保留为多条 claim**，并记录 `resolution`
   （`single_source` / `consensus` + winner + reason）⇒「谁说的、谁赢了、为什么」可审计；
3. **证据强度不降级** — `must`（规范强制）与 `observed`（实测观测）始终可区分，
   下游按强度分别使用；
4. **按知识性质落位** — 对齐后的事实按 A~F 六分类落位，
   从「**按源组织**」切换到「**按知识性质组织**」。

⇒ 知识图只是对齐之后的**关系视图**，不是起点。

## 设计原则

1. **协议级隔离,跨协议共享** — `kb/<协议>/<源>/` 在各协议间共享（源维度 5 档：`spec` / `协议实现源码` / `数据流量` / `历史漏洞` / `expert_note`）
2. **协议无关主程序 + per-protocol Profile** — 协议特定配置集中在 `profiles/<协议>/profile.json`（`allowed_methods` / `transport` / `message_schema`），主程序 `core/fused/` 不含协议分支
3. **五源解耦 + 中枢 + 知识图** — 五源（spec / 协议实现源码 / 数据流量 / 历史漏洞 / expert_note）各自抽取为独立 Fact，汇聚进**按知识分类的中枢**（A~F 六分类），再投影成**实体关系图 + 社区**，供检索与种子生成
4. **fail-closed 校验** — LLM 写出的种子必须通过 `core/fused/validation.py` 七级校验，未注册引用（subject.type / aspect / epistemic_type）直接硬错误
5. **流程到"生成高价值初始种子"结束** — 种子产出 `.raw` + `<协议>.dict` 定向字典，由 `scripts/seedgen.py` 落盘

## 命名约定

| 概念 | 命名 |
|---|---|
| 中枢核心 | `core/fused/`（Layer 0）|
| 知识原子 | `Fact`（六元组 fact_key + claims + resolution）|
| 协议 Profile | `profiles/<协议>/profile.json` |
| 注册表 | `subject_type_registry` / `aspect_registry` / `epistemic_type_registry` |
| 规范化序列化 | `canonical_serialize` + 确定性 ID（`compute_fact_id` / `compute_claim_id` / `compute_evidence_id`）|
| 语料选择器 | `core/fused/downstream/selector.py`（`select_seeds` / `prioritize_seeds` / `vuln_proximity_score`）|
| 知识维度 | **Subject.type(7) × Aspect(19) 开放注册**|

## 当前阶段（结构化知识中枢 + 知识图 + 多源种子生成）

- **五源知识抽取**：`kb/<协议>/<源>/` → `derived/per_source/<协议>/<源>/facts/`，覆盖 rtsp / sip / smtp / dhcpv4 四协议 × 五源
- **知识分类中枢**：`derived/hub/<分类>/`（A~F 六分类）+ `index/entities.jsonl`（实体主表）
- **知识图整理层**：`derived/graph/`（实体图 + 社区 + 社区报告）
- **五层种子**：`edge_cover`（结构覆盖）/ `generic_danger`（通用危险）/ `boundary_probe`（漏洞边界）/ `strategy`（目标聚焦）/ `action_seq`（动作序列）
- **协议无关主程序**：`core/fused/`（中枢核心 + 源映射 + 视图层）+ `core/fused/downstream/`（消费层）
- **全量回归**：**560 passed / 0 skipped / 0 failed**（2026-10-30 实测）

## 代码结构（按功能编排）

```
ProtoKG/
├── core/                      # 协议无关核心
│   ├── llm.py                 # LLM 客户端（DeepSeek + Stub）+ 传输层
│   ├── models.py              # 数据模型（SeedMessage / SeedCorpus / ...）
│   ├── paths.py               # 路径常量 + SOURCE_DIRS 五源→kb 子目录映射
│   ├── raw_writers.py         # ProFuzzBench 兼容 .raw writer
│   └── fused/                 # 结构化知识中枢（33 个 .py）
│       ├── models.py          # Layer 0 数据结构（26 dataclass）
│       ├── canonical.py       # canonical 序列化 + 确定性 ID
│       ├── registry.py        # 加载 3 个注册表（fail-closed）
│       ├── validation.py      # 7 个 validate_* 函数
│       ├── export.py          # LLM 安全接口（P10）
│       ├── norm.py / expert_note.py / vuln.py / source.py / traffic.py   # Layer 2 五源→Fact
│       ├── compat.py          # fact → Fact 双轨映射
│       ├── traffic_extractor.py     # traffic 源抽取（含 packets.ndjson 真实字段）
│       ├── source_autoseeder.py     # AutoSeeder 状态机分析（source 源）
│       └── downstream/        # 11 个下游消费模块
│           ├── edge_cover.py         # ① 结构覆盖层
│           ├── generic_danger.py     # ② 通用危险层
│           ├── boundary_probe.py     # ③ 漏洞导向边界探针 + 定向字典
│           ├── rag_seedgen.py        # 中枢 → RAG → LLM → 种子
│           ├── selector.py           # 三层语料选择器 + 降级
│           ├── resolver.py           # claim 冲突消解
│           ├── source_availability.py / source_retrieval.py
│           └── seed_manifest.py / strategy.py / target_env.py
├── scripts/                   # 构建脚本（模型链路）
│   ├── build_hub.py           # 中枢构建入口
│   ├── build_graph.py         # GraphRAG 整理层构建入口
│   ├── seedgen.py             # 种子生成 CLI
│   ├── run_pipeline.py        # ★ 统一入口：识别协议 → 建模 → 出种子
│   └── seed_oracle_filter.py  # SIP 响应码 oracle 过滤
├── kb/<协议>/<源>/             # 五源知识库（read-only）
│   └── spec/协议实现源码/数据流量/历史漏洞/expert_note
├──                  # 中枢文档与配置（**人工资产**，进 git）
│   ├── schema/                # 5 个契约 JSON（知识分类/属性/图/实体/判据）
│   ├── docs/                  # 融合中枢规范与设计
│   └── targets/<协议>/        # 4 协议 profile.json + rfc_config + skeleton + 字典
├── derived/                   # 派生数据（**可重建**，不进 git）
│   └── model/                 # ★ 模型链路产物
│       ├── per_source/<协议>/<源>/facts/   # 各源中间产物
│       ├── hub/               # ★ 结构化知识中枢（按知识分类 A~F + 索引）
│       ├── graph/             # ★ GraphRAG 整理层（实体图 + 社区）
│       └── seeds/<协议>/      # 生成的种子
├── guard/                  # 护栏（编码卫生 / 期望集比对 / 分布校验）
├── tests/                     # 全量测试
└── docs/                      # 文档（设计/实施/工具/图）
```

## 协议无关架构

中枢核心（`core/fused/`）协议无关，**所有协议特定配置放 `profiles/<协议>/profile.json`**。

新加协议只需：

1. 准备 kb 数据：`kb/<新协议>/{spec,协议实现源码,数据流量,历史漏洞,expert_note}/`
2. 建 Profile：`profiles/<新协议>/profile.json`（含 `allowed_methods` / `transport` / `message_schema`）
3. 抽取 + 生成：

```bash
python scripts/build_hub.py --sources rfc expert_note source traffic vuln --protocol <新协议>
python scripts/seedgen.py --protocol <新协议>
```

## 快速开始

```bash
cd E://科研//想法idea//ProtoKG

# 1. 查看 kb 中实际存在的知识源
python scripts/build_hub.py --list-sources

# 2. 五源抽取 → derived/per_source/<协议>/<源>/facts/<源>.jsonl
#    （source 源走 AutoSeeder，需 LLM ⇒ 见下方「LLM 配置」）
python scripts/build_hub.py --sources rfc expert_note source traffic vuln --protocol rtsp \
       --api-key sk-xxx --model deepseek-chat --base-url https://api.deepseek.com

# 3. 生成种子（--focus-group B 含漏洞边界层；--focused 启用漏洞接近度排序）
python scripts/seedgen.py --protocol rtsp --focus-group B
```

### LLM 配置（`source` 源与语义规则抽取需要）

本项目的 LLM 通道走 **OpenAI 兼容协议** ⇒ **换厂商/模型只改三个变量**：

| 变量 | CLI 参数 | 环境变量 | 默认 |
|---|---|---|---|
| 凭据 | `--api-key` | `LLM_API_KEY` | 无（必填） |
| 模型 | `--model` | `LLM_MODEL` | `deepseek-chat` |
| endpoint | `--base-url` | `LLM_BASE_URL` | `https://api.deepseek.com` |

**优先级**：CLI 显式传入 > 环境变量 > 项目根 `.env` > `DEEPSEEK_*`（兼容别名）。

**三种传法**（任选其一）：

```bash
# A. 命令行（优先级最高，临时最方便）
python scripts/build_hub.py --protocol rtsp --api-key sk-xxx \
       --model gpt-4o-mini --base-url https://api.openai.com/v1

# B. 环境变量
export LLM_API_KEY=sk-xxx
export LLM_MODEL=qwen-max
export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# C. 项目根 .env（复制 .env.example 改三个值即可；.env 不入库）
```

**支持的厂商**（任何 OpenAI 兼容服务）：DeepSeek · 阿里云百炼（qwen）· OpenAI ·
本地 ollama / vLLM。

> 提示：`source` 源走 AutoSeeder（LLM 分析源码状态机），首次构建较慢且结果已按 code_blocks hash 缓存到
> `derived/source_blocks/<协议>.state.json`，后续构建直接命中缓存。

## 测试

```
============================= 560 passed in 28.7s =============================
```

无 skipped 用例。

## 协议 fuzzing 完整架构

| 层   | 负责                      | 关键文件                                                                             |
| --- | ----------------------- | -------------------------------------------------------------------------------- |
| LLM | 协议 prompt + JSON 输出     | `core/llm.py` + Stub/DeepSeek                                                    |
| 协议层 | per-protocol Profile 配置 | `profiles/<协议>/profile.json`                                            |
| 抽取层 | 五源 → Fact（六元组）          | `core/fused/norm.py` + `expert_note.py` + `vuln.py` + `source.py` + `traffic.py` |
| 校验层 | fail-closed 校验 + 注册表治理  | `core/fused/validation.py` + `core/fused/registry.py`                            |
| 生成层 | 三层检索 + LLM 写 + 落盘       | `core/fused/downstream/selector.py` + `rag_seedgen.py` + `scripts/seedgen.py`    |
| 导出层 | LLM 安全接口（P10）           | `core/fused/export.py`                                                           |

## License

Apache 2.0
