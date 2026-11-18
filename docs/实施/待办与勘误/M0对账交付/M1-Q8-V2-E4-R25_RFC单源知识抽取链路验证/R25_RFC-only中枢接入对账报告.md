# R25 RFC-only 中枢接入对账报告

> ★ **影子中枢建在隔离工作区副本**；★ 正式中枢未被覆盖

---

## 一、★ 八项验证的逐条回答

| # | 验证项 | 结论 | 证据 |
|---|---|---|---|
| 1 | ★ RFC-only 输入可以完整构建 | ★ **可以** | ★ `build_hub.py --protocol smtp --sources rfc` 返回码 0；★ 82 facts → 2 个分类文件 |
| 2 | ★ Norm 到 Canonical 映射没有非法字段 | ★ **是** | ★ 映射零失败（★ 三协议 262/262） |
| 3 | ★ FactID 身份规则保持不变 | ★ **是** | ★ 用既有 `compute_fact_id` 重算；★ 未改 `canonical.py` |
| 4 | ★ Evidence 关联可追溯 | ★ **部分** | ★ 文档级 100%；★ 行级 40.7% |
| 5 | ★ 同一知识的多来源支持得到保留 | ★ **机制支持** | ★ `evidence_summary` 是数组；★ 真实语料零多来源实例 |
| 6 | ★ 不同语义知识没有错误合并 | ★ **是** | ★ 同 norm_id 多来源实例 0 组；★ 身份冲突 0 条 |
| 7 | ★ 旧中枢数据没有被覆盖 | ★ **是** | ★ 正式中枢 hub 与 per_source 的文件指纹**前后完全一致** |
| 8 | ★ 中枢与 Seed 的既有发布机制不变 | ★ **是** | ★ 未运行 seedgen；★ 未改任何发布脚本 |

---

## 二、★ 逐条对账链

★ 完整逐条记录见 `R25_来源实例身份与去重对账.jsonl`（★ 262 行），★ 每行含：

```
★ protocol
★ source_reference / normalized_document_id / source_file / source_sha256
★ source_class / generator / generator_version / locator / source_span
★ original_record / original_norm_id / kind
★ source_instance_key
★ production_retained / shadow_retained / retained_or_dropped
★ evidence_carrier / canonical_carrier
```

★ ★ **★ 四种身份严格区分**：

| 身份 | 载体 | 例 |
|---|---|---|
| ★ RFC 文档身份 | ★ source_file + source_sha256 | ★ rfc5322.txt + 其 SHA256 |
| ★ 知识命题身份 | ★ original_norm_id | ★ smtp.field.from |
| ★ 来源证据身份 | ★ evidence_summary（★ 含文档与行号/锚点） | ★ rfc:smtp.field.from@file:rfc5322.txt#@1814 |
| ★ 抽取实例身份 | ★ source_instance_key | ★ file_source\|rfc5322.txt\|<sha16>\|\|1814\|field.from |

---

## 三、★ 无法完成映射的记录的分类

| 分类 | 条数 | 说明 |
|---|---:|---|
| ★ unresolved | ★ 0 | —— |
| ★ unsupported_by_schema | ★ 0 | ★ **不需要**（★ 现有 Canonical 能承载全部语义） |
| ★ invalid_mapping | ★ 0 | —— |
| ★ evidence_missing | ★ **0**（★ 文档级）；★ **47**（★ 行级定位不足） | ★ 锚点级 ⇒ 精度不足而非缺失 |
| ★ legitimate_not_applicable | ★ 75 | ★ 描述性知识无规范字段 |

★ ⇒ ★ **★ 接入率 100%（★ 86/86 fact 有文档级证据），★ 行级精度 40.7%。**

---

## 四、★ 影子中枢的产物清单

| 项 | 值 |
|---|---|
| ★ 构建命令 | ★ `python scripts/build_hub.py --protocol smtp --sources rfc --no-purge`（★ **无 LLM 凭据**） |
| ★ 工作区 | ★ 隔离副本 `guard/_out/_n1c_v2/r25/_ci_work`（★ **不写正式 derived**） |
| ★ 产出 | ★ 82 facts → 2 个分类文件；★ 语义四库重发布 4 条权威规则 |
| ★ 正式中枢影响 | ★ **零**（★ 前后指纹一致） |

---

## 五、★ 限制

1. ★ 只对 SMTP 做了完整影子接入；★ RTSP 与 DHCPv4 只做了 Norm 级映射验证。
2. ★ 「不带 source 源」是因为 source 源走 AutoSeeder 的 LLM 路径；★ CI 无凭据。
3. ★ 未运行 seedgen，★ 故未验证「中枢 → Seed」链路（★ 本轮不改 Seed）。
