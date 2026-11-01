# compare/ —— 三路知识表示消融实验

验证主张：**可溯源、带认识论状态与冲突消解的知识表示（A 路），比向量 RAG（C 路）和
浅层知识库（B 路）带来更好的下游覆盖 / 漏洞发现。**

## 三路代号

| 路 | 名称 | 知识表示 | 实现位置 |
|---|---|---|---|
| **A** | ProtoRAG（可溯源） | 六元组 + Epistemic + Evidence + Resolution 冲突消解 | `scripts/run_seedgen_e2e.py`（现有框架，不动） |
| **B** | 浅层知识库 | 结构化，但**无 provenance**、冲突抹平 | `compare/shallow_kb.py` |
| **C** | 向量 RAG | 原文 chunk + embedding + 语义检索 | `compare/vector_rag.py` |

**三路唯一变量 = 知识表示层**，其余（同一份五源知识、同一 DeepSeek、同一 LLM 参数、
同一 .raw 落盘）全部共用。

## 目录

```
compare/
├── config.py          # 三路共享配置（LLM/temperature/种子数/路径，强制共用）
├── interface.py       # KnowledgeRepresentation 抽象接口
├── shallow_kb.py      # B 路
├── vector_rag.py      # C 路（chunk/embedding/检索目前为 dummy，见 TODO）
├── run_ablation.py    # 统一入口 --mode {shallow_kb, vector_rag}
└── out/<mode>/rtsp/<时间戳>/   # B/C 路种子（A 路种子在 derived/seeds/）
```

## 运行

```bash
# B 路：浅层知识库
python compare/run_ablation.py --mode shallow_kb --n-seeds 20

# C 路：向量 RAG
python compare/run_ablation.py --mode vector_rag --n-seeds 20

# 只测流程不调真实 LLM
python compare/run_ablation.py --mode shallow_kb --no-llm
```

A 路沿用 `python scripts/run_seedgen_e2e.py --three-layer ...`（不在此仓库改动）。

## ⚠️ 关键改造点（A 路调试前必须先做）

**当前 A 路实际上已经退化成 B 路了**：`rag_seedgen.assemble_bundle` 只取
`all_claims[0].value`，`render_seed_prompt` 也没有渲染 `Epistemic / Evidence /
Resolution`。这意味着 A 路的 prompt 里**没有**认识论状态、没有冲突消解信息，
多源冲突在组装时已被静默抹平。

要真正体现「可溯源知识表示」的价值，A 路需补一步：**把 conflict + epistemic
渲染进 prompt**。目标效果：

> CSeq 字段存在冲突：规范要求必须递增（must，权威），但流量观测到重复
> （observed）——这是值得探索的边界，建议生成重复 CSeq 的种子。

否则 A == B，三路消融测不出差异，创新点无法被实验支撑。这是「调试 A 路」的
第一优先级事项。

## TODO（骨架 → 可跑）

- [ ] **A 路**：`render_seed_prompt` 增加 provenance 渲染（冲突 + 认识论），见上
- [ ] **C 路**：真实 embedding（sentence-transformers / bge，装隔离环境）+ 向量索引 + 真实检索（替换 `_dummy_embed` / `_dot`）
- [ ] **C 路**：chunk 策略调优（当前固定 800 字符，应改成按段落/语义切分）
- [ ] `conflict_bench.py`：冲突采信基准（中间指标，构造冲突样本 + 评测三路采信准确率）
- [ ] 统一 fuzz 评测脚本：三路种子喂同一 ChatAFL 环境，产出覆盖/状态/崩溃对比
