# R2 队列 B 召回评估前置勘误

## 一、已验证事实

逐片段核验链路 `source_sha256 -> chunk_id -> input_span -> actual_extraction_attempt -> candidate_output`，依据 `M1-Q2证据冻结/frozen_blocks.jsonl` 记录的 chunk 行覆盖范围：

| processing_status | 片段数 |
|---|---:|
| never_processed | 51 |
| processed_with_candidate | 3 |
| processed_without_candidate | 0 |

文档级交集 11 份，抽取窗口覆盖率 0.0556。

逐条数据见 `R2_队列B抽取窗口覆盖核验.xlsx` 与 `guard/_out/_n1c_v2/r2/r2_queue_b_coverage.json`。

落在已处理窗口内的 3 个片段：

| snippet_id | 文档 | 命中 chunk | chunk 行范围 | chunk 内候选数 | 人工知识条数 |
|---|---|---|---|---:|---:|
| B-rtsp-rfc2326.txt-7 | rfc2326.txt | rfc2326.txt@1 | 1-74 | 3 | 0 |
| B-sip-rfc3261.txt-7 | rfc3261.txt | rfc3261.txt@1 | 1-74 | 6 | 0 |
| B-smtp-rfc3207.txt-30 | rfc3207.txt | rfc3207.txt@1 | 1-114 | 6 | 2 |

## 二、推论

1. 文档级交集不能作为已处理的证据。11 份同源文档中，51 个片段的行根本不在任何历史 chunk 的行范围内。
2. never_processed 属输入覆盖缺口，语义上不同于 LLM 未成功抽取，不应计入抽取失败。
3. 对这 54 个片段计算 H1 的 LLM 知识召回率在方法上不成立，因为 H1 的 156 条候选从未覆盖其中 51 个片段的原文。

## 三、限制

1. 判定依据是冻结的 chunk 记录，不是历史运行的逐次调用日志。历史日志不可复算（H2 与 H3 的诊断事件缺失）。
2. 若历史运行实际处理过 chunk 记录范围以外的行，则这些片段的真实状态为 processed 而非 never_processed。现有证据不足以区分。
3. 3 个 processed_with_candidate 片段的匹配结果尚未计算，因此条件召回率暂缺。

## 四、下一步

1. 匹配执行后按两组分别报告：覆盖率（processed 片段占比）与条件召回率（processed 片段内的匹配率）。
2. 对 3 个 processed 片段单独核对 LLM 产出与人工判断的差异，作为非目标知识误入规则通道的样本。
3. 若需要完整的 LLM 抽取召回率，须在新来源上执行受控抽取，不依赖队列 B。

## 五、对评测设计的影响

按 `R2_独立评估统计与准入设计.md`，队列 B 的结果只用于源头漏抽分析，不进入 V2 分类准确率，也不作为跨协议泛化的证据。
