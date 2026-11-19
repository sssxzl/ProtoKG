# get_fact_view 与 Hub 导出读回核验

| 路径 | grammar 处理 |
|---|---|
| `get_fact_view` | `{"type": "grammar", "data": {...}}` 原样输出 |
| JSONL 写入 | `json.dumps(ensure_ascii=False)`，无过滤 |
| `load_facts` | `json.loads` 逐行，无校验 |
| `build_entity_index` | 只读 `fact_key.subject`，不碰 value |
| `write_entity_index` | 输出实体表，与 value 无关 |

## 结论

从 view 到 Hub 再读回，rule/expr/deps 一字未改。

## 边界

- 官方 Hub 的 `evidence_summary` 仍只存证据摘要，不含 grammar；
- 本轮测试对象写在临时目录，未进正式 `derived/`。
