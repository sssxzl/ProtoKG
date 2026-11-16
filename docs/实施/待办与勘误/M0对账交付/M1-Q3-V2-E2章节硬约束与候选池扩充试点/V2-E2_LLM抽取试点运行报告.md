# V2-E2 · LLM 抽取试点运行报告

> ★ run_id `v2e2-pilot-20261116-181448` ｜★ **限额内完成** ｜★ **0 次超限**

---

## 一、★ 限额与实际（★ 任一先达到即停）

| 项 | ★ 上限 | ★ **实际** | ★ 是否超限 |
|---|---:|---:|:---:|
| ★ RFC 文档数 | 12 | **12** | ✔ 否 |
| ★ 原文块数 | 24 | **24** | ✔ 否 |
| ★ LLM 请求数（含重试） | 24 | **24** | ✔ 否 |
| ★ token 合计 | 200,000 | **48644**（★ in 19141 + out 29503） | ✔ 否 |

★ **估算费用：USD 0.020573**（★ deepseek-flash 闲时价：输入未命中 $0.15/1M、输出 $0.60/1M）

---

## 二、★ 锁定的配置（★ 首次调用前已冻结）

| 项 | ★ 值 |
|---|---|
| ★ 模型 | `deepseek-flash`（★ DeepSeek-V4.1-Flash-1017） |
| ★ base_url | `https://api.deepseek.com` |
| ★ temperature | 0.1 |
| ★ **max_tokens** | **4000**（★ 生产默认 16000；★ **为满足 200K 上限下调**，★ 差异已记录） |
| ★ **Prompt** | ★ **复用生产**：core/fused/extraction/prose_semantics.py::_PROMPT（★ digest `d97fbe611ac9aa61`） |
| ★ **Schema** | ★ **复用生产**：prose_semantics 原生 schema（★ 未新建） |
| ★ **抽取器入口** | `core.fused.extraction.prose_semantics.extract_window_norms`（★ **共享内核**） |
| ★ 抽取器代码版本 | ★ commit `57ed0a3` |
| ★ 选块规则 | ★ 冻结：★ 散文连续段按 **BCP14 密度**降序 → 取前 2 段 → 每段 ≤ 3500 字符 |
| ★ **隔离** | ★ `shadow=True`（★ **不进 fact 空间**）｜★ 缓存重定向到 `guard/_out/_v2_e2_pilot/cache/`（★ **生产 `derived/cache/` 未被污染**） |

---

## 三、★ 试点验收（★ §八 十项）

| # | 指标 | ★ 值 |
|---|---|---|
| ① | ★ 实际 RFC / chunk 数 | **12** / **24** |
| ② | ★ LLM 调用数 / token / 费用 | **24** / **48644** / **$0.020573** |
| ③ | ★ 成功 / 失败 / 解析失败 / 缓存 | ★ 成功块 24｜★ 异常块 0｜★ **解析失败 0**｜★ 缓存命中 0（★ 试点独立缓存） |
| ④ | ★ 每份 RFC 新增候选 | ★ 12 份**全部产出**（★ 1～3 条/份） |
| ⑤ | ★ 候选知识类型分布 | {'prose_semantics': 39, 'prose_constraint': 13} |
| ⑥ | ★ **可定位证据比例** | **1.0**（★ 52/52） |
| ⑦ | ★ 主体/动作/对象/条件完整性 | ★ subject **0.2692**｜action **0.4423**｜object **0.4423**｜condition **0.2885** |
| ⑧ | ★ 重复候选 / 无效候选 | **2** / **0** |
| ⑨ | ★ 各协议实际产出 | {'DHCPv4': 52}（★ **全部 DHCPv4**） |
| ⑩ | ★ 未来独立评测可获容量 | ★ 试点文档 **12**（★ 不可再用）｜★ 保留来源 **9** |

---

## 四、★★ 三条必须强调的限定

1. ★★ **新增 52 条候选只是观察指标**；★ **不得**解释为 52 条真实规范知识（★ **未经人工审核**）
2. ★★ **字段完整性很低**（★ subject 26.9% / action 44.2% / condition 28.9%）⇒ ⇒ ★
★ **★ 这与 V2 开发集结论一致（★ 24 条成立中仅 12 条字段全对）⇒ ★★ 跨批次稳定信号：★「候选少」不是主因，★「字段不完整」才是**
3. ★★ **本批只用于评估候选生成可行性与成本，★ 不得作为 V2 最终独立泛化验证数据**

---

## 五、★ 产出落盘

| 文件 | 内容 |
|---|---|
| `V2-E2_受限LLM试点配置.json` | ★ 冻结配置（★ 11 项） |
| `V2-E2_LLM抽取试点运行报告.json` | ★ 运行汇总 |
| `V2-E2_新增候选审计.jsonl` | ★ **16 字段逐条记录**（★ run_id / document_id / source_sha256 / chunk_id / chunk_hash / model / prompt_digest / schema_version / cache_status / request_attempt / tokens / parse_status / failure_reason / candidate_id / source_span / proposed_knowledge_kind） |
| `V2-E2_试点验收统计.json` | ★ §八 十项 |
| `diagnostics/` | ★ `LLMDiagnostics` 原始调用记录 |
| `cache/` | ★ 试点独立缓存（★ 生产 `derived/cache/` 未污染） |
