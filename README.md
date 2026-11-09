# ProtoKG

> **Protocol Knowledge Graph for Fuzzing Seed Generation.**
> 基于协议知识图（中枢 + GraphRAG 整理层）的模糊测试种子生成器。

★ 五源协议知识（规范 / 源码 / 流量 / 漏洞 / 专家注记）→ **按知识分类的结构化中枢**
→ **实体关系图 + 社区** → 五层种子生成。

## 设计原则

1. **协议级隔离,跨协议共享** — `kb/<协议>/<源>/` 在各协议间共享（源维度 5 档：`spec` / `协议实现源码` / `数据流量` / `历史漏洞` / `expert_note`）
2. **协议无关主程序 + per-protocol Profile** — 协议特定配置集中在 `fused_hub/targets/<协议>/profile.json`（`allowed_methods` / `transport` / `message_schema`），主程序 `core/fused/` 不含协议分支
3. **五源解耦 + 中枢 + 知识图** — 五源（spec / 协议实现源码 / 数据流量 / 历史漏洞 / expert_note）各自抽取为独立 Fact，汇聚进**按知识分类的中枢**（A~F 六分类），再投影成**实体关系图 + 社区**，供检索与种子生成
4. **fail-closed 校验** — LLM 写出的种子必须通过 `core/fused/validation.py` 七级校验，未注册引用（subject.type / aspect / epistemic_type）直接硬错误
5. **流程到"生成高价值初始种子"结束** — 种子产出 `.raw` + `<协议>.dict` 定向字典，由 `scripts/seedgen.py` 落盘

## 命名约定

| 概念 | 命名 |
|---|---|
| 中枢核心 | `core/fused/`（Layer 0）|
| 知识原子 | `Fact`（六元组 fact_key + claims + resolution）|
| 协议 Profile | `fused_hub/targets/<协议>/profile.json` |
| 注册表 | `subject_type_registry` / `aspect_registry` / `epistemic_type_registry` |
| 规范化序列化 | `canonical_serialize` + 确定性 ID（`compute_fact_id` / `compute_claim_id` / `compute_evidence_id`）|
| 语料选择器 | `core/fused/downstream/selector.py`（`select_seeds` / `prioritize_seeds` / `vuln_proximity_score`）|
| 知识维度 | **Subject.type(7) × Aspect(19) 开放注册**|

## 当前阶段（结构化知识中枢 + 知识图 + 多源种子生成）

- **五源知识抽取**：`kb/<协议>/<源>/` → `derived/model/per_source/<协议>/<源>/facts/`，覆盖 rtsp / sip / smtp / dhcpv4 四协议 × 五源
- **知识分类中枢**：`derived/model/hub/<分类>/`（A~F 六分类）+ `index/entities.jsonl`（实体主表）
- **知识图整理层**：`derived/model/graph/`（实体图 + 社区 + 社区报告）
- **五层种子**：`edge_cover`（结构覆盖）/ `generic_danger`（通用危险）/ `boundary_probe`（漏洞边界）/ `strategy`（目标聚焦）/ `action_seq`（动作序列）
- **协议无关主程序**：`core/fused/`（中枢核心 + 源映射 + 视图层）+ `core/fused/downstream/`（消费层）
- **全量回归**：**560 passed / 0 skipped / 0 failed**（2026-10-30 实测）

## 代码结构（按功能编排）

```
rag-chatafl/
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
├── fused_hub/                 # 中枢文档与配置（**人工资产**，进 git）
│   ├── schema/                # 5 个契约 JSON（知识分类/属性/图/实体/判据）
│   ├── docs/                  # 融合中枢规范与设计
│   └── targets/<协议>/        # 4 协议 profile.json + rfc_config + skeleton + 字典
├── derived/                   # 派生数据（**可重建**，不进 git）
│   └── model/                 # ★ 模型链路产物
│       ├── per_source/<协议>/<源>/facts/   # 各源中间产物
│       ├── hub/               # ★ 结构化知识中枢（按知识分类 A~F + 索引）
│       ├── graph/             # ★ GraphRAG 整理层（实体图 + 社区）
│       └── seeds/<协议>/      # 生成的种子
├── tools/guard/                  # 护栏（编码卫生 / 期望集比对 / 分布校验）
├── tests/                     # 全量测试
└── docs/                      # 文档（设计/实施/工具/图）
```

## 协议无关架构

中枢核心（`core/fused/`）协议无关，**所有协议特定配置放 `fused_hub/targets/<协议>/profile.json`**。

新加协议只需：

1. 准备 kb 数据：`kb/<新协议>/{spec,协议实现源码,数据流量,历史漏洞,expert_note}/`
2. 建 Profile：`fused_hub/targets/<新协议>/profile.json`（含 `allowed_methods` / `transport` / `message_schema`）
3. 抽取 + 生成：

```bash
python scripts/build_hub.py --sources rfc expert_note source traffic vuln --protocol <新协议>
python scripts/seedgen.py --protocol <新协议>
```

## 快速开始

```bash
cd E:\科研\想法idea\rag-chatafl

# 1. 查看 kb 中实际存在的知识源
python scripts/build_hub.py --list-sources

# 2. 五源抽取 → derived/model/per_source/<协议>/<源>/facts/<源>.jsonl
python scripts/build_hub.py --sources rfc expert_note source traffic vuln --protocol rtsp

# 3. 生成种子（--focus-group B 含漏洞边界层；--focused 启用漏洞接近度排序）
python scripts/seedgen.py --protocol rtsp --focus-group B
```

> 提示：`source` 源走 AutoSeeder（LLM 分析源码状态机），首次构建较慢且结果已按 code_blocks hash 缓存到
> `derived/model/source_blocks/<协议>.state.json`，后续构建直接命中缓存。

## 测试

```
============================= 560 passed in 28.7s =============================
```

无 skipped 用例。

## 协议 fuzzing 完整架构

| 层   | 负责                      | 关键文件                                                                             |
| --- | ----------------------- | -------------------------------------------------------------------------------- |
| LLM | 协议 prompt + JSON 输出     | `core/llm.py` + Stub/DeepSeek                                                    |
| 协议层 | per-protocol Profile 配置 | `fused_hub/targets/<协议>/profile.json`                                            |
| 抽取层 | 五源 → Fact（六元组）          | `core/fused/norm.py` + `expert_note.py` + `vuln.py` + `source.py` + `traffic.py` |
| 校验层 | fail-closed 校验 + 注册表治理  | `core/fused/validation.py` + `core/fused/registry.py`                            |
| 生成层 | 三层检索 + LLM 写 + 落盘       | `core/fused/downstream/selector.py` + `rag_seedgen.py` + `scripts/seedgen.py`    |
| 导出层 | LLM 安全接口（P10）           | `core/fused/export.py`                                                           |

## License

Apache 2.0
