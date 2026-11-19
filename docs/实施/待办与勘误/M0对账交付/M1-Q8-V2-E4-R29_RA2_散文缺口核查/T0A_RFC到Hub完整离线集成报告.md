# T0-A RFC → Hub 完整离线集成报告

一次脚本、一条链路，没有拼接多个互不相连的 Stub。

## 一、链路与产物

| 环节 | 调用 | 实测 |
|---|---|---|
| RFC 读取 | `rfc3207.txt` | 508 行，SHA256 记录在脚本输出 |
| 切块 | `_split_blocks` | 6 块，100% 覆盖 |
| 抽取 | `_extract_blocks(protocol, blocks, llm=Stub)` | 1 条 prose_semantics Norm |
| Fact | `map_norm_to_facts` | 1 条，aspect=definition |
| 序列化 | `dataclasses.asdict` | 写入隔离 `per_source/smtp/facts/definition.jsonl` |
| 读回 | `load_facts`（路径注入） | 1 条，`fact_id` 与输入一致 |
| 实体索引 | `build_entity_index` + `write_entity_index` | 1 个实体，落盘后可读回 |

## 二、身份一致性

`fact_id` 由 `compute_fact_id` 生成，读回后与写入时逐字段相同，说明序列化没有破坏身份。EvidenceID 同理（`e2_…`）。

## 三、Evidence 回溯

`document = file:rfc3207.txt#@80`，脚本按行号取原文第 80 行，确认包含 `STARTTLS`。因此证据可回到真实原文位置，而不是只有文件名。

## 四、未验证

- 未调用 `build_hub.main`（会清理正式目录）；
- 未构建完整中枢（sources.json、社区、图），只验证「Fact → 实体索引」这一段；
- 未接入 Seed/GraphRAG。

## 五、结论

`RFC → Norm → Fact/Evidence → 隔离索引` 已通；`→ 完整中枢` 仅完成最小可用段（实体主表），不等同于全中枢构建。
