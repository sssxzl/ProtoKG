# R25 Norm 到 Canonical 的兼容映射报告

> ★ **未改变 Canonical 结构、★ 21 aspects、★ FactID 与 EvidenceID 契约**

---

## 一、★ D1 要求的 11 个字段的逐项核对

| 字段 | 是否适用 | 原始来源 | 是否派生 | 最终承载位置 | 能否从 Canonical 重建 |
|---|---|---|---|---|---|
| ★ entity | ★ 适用（★ prose 通道） | ★ LLM 抽取的 `entity` | ★ 是（★ Rule Slot 的 subject 用**义务主体** `normative_subject`，★ 非 entity） | ★ `fact_key.subject.name` | ★ **能**（★ 主体名直接可读） |
| ★ meaning | ★ 适用 | ★ LLM 的 `meaning` | ★ 是 | ★ claim 的 value（★ 普通 definition 路径） | ★ **能** |
| ★ constraint | ★ 适用 | ★ LLM 的 `constraint` | ★ 是 | ★ claim 的 value（★ `[RULE:v1]` 文本内） | ★ **能**（★ 归一化 JSON） |
| ★ normative_subject | ★ 适用 | ★ LLM 的 `normative_subject` | ★ 是 | ★ `fact_key.subject.name`（★ 优先于 entity） | ★ **能** |
| ★ action | ★ 适用 | ★ LLM 的 `action` | ★ 否 | ★ `fact_key.subject.qualifiers.action` | ★ **能** |
| ★ object | ★ 适用 | ★ LLM 的 `object` | ★ 否 | ★ `fact_key.subject.qualifiers.object` | ★ **能** |
| ★ strength | ★ 适用 | ★ LLM 的 `strength` | ★ 否 | ★ **Assertion**（★ claim 的 value 内） | ★ **能** |
| ★ polarity | ★ 适用 | ★ LLM 的 `polarity` | ★ 否 | ★ **Assertion** | ★ **能** |
| ★ condition | ★ 适用 | ★ LLM 的 `condition` | ★ 否 | ★ **Assertion** | ★ **能** |
| ★ exception | ★ 适用 | ★ LLM 的 `exception` | ★ 否 | ★ **Assertion** | ★ **能**（★ Rule Slot 的**身份槽位**不含它，★ 但 Assertion 含） |
| ★ evidence_span | ★ 适用 | ★ 抽取器的 `span` / 行号 | ★ 是 | ★ claim 的 `evidence`（★ `evidence_summary`） | ★ **部分**（★ 39/86 有行号，★ 47 条只有锚点） |

★ ★ **★ 确定性通道（★ method/field/outcome/transition 等）：★ 11 个字段全部「不适用」**
★ ★ ★ ★ ★ —— 它们没有散文语义，★ 只有 kind/name/content/source。
★ ★ ★ ★ ★ ⇒ ★ **确定性路径上不存在「字段意外丢失」**。

---

## 二、★ D2 规范知识承载（★ 沿用已确认的既有方案）

| 项 | 实现 | 实测 |
|---|---|---|
| ★ 散文规范规则使用 definition aspect | ★ `prose_constraint_norm_to_facts` | ★ **20/20** |
| ★ Rule Slot / qualifiers 表达规范规则 | ★ `qualifiers = {action, object, kind: normative_rule}` | ★ **20/20** |
| ★ `[RULE:v1]` 标识 | ★ `normative_rule.rule_text` | ★ **20/20** |
| ★ strength/polarity 位于 Assertion | ★ `build_payload` | ★ **20/20** |
| ★ **不新增 aspect** | ★ 复用 `definition` | ★ 确认 |
| ★ **不改变 FactID 身份** | ★ `compute_fact_id(fact_key)` | ★ 确认（★ 影子中枢重算一致） |

★ **★ 条件与例外未丢失**：★ condition 8 条、exception 2 条均进 Assertion。

---

## 三、★ D3 语义等价验证（★ 九类的实测分布）

| 类别 | 实测 |
|---|---|
| ★ 原字段直接保留 | ★ entity/meaning/constraint（★ 普通 definition 路径） |
| ★ 字段改名 | ★ entity ⇒ subject.name；★ normative_subject ⇒ subject.name（★ 优先） |
| ★ 字段合并 | ★ 无 |
| ★ 进入规范文本 | ★ strength/polarity/condition/exception ⇒ `[RULE:v1]` JSON |
| ★ 进入 qualifiers | ★ action/object/kind |
| ★ 进入 Assertion | ★ 同「进入规范文本」 |
| ★ 进入 provenance | ★ keyword_raw ⇒ evidence.quote（★ **不进 value**） |
| ★ 合法缺省 | ★ 75 条描述性抽取的 strength/polarity/condition/exception |
| ★ **真正意外丢失** | ★ **0**（★ Norm→Canonical 映射 262/262 成功；★ 20 条 Rule Slot 的四字段全含） |

★ ★ **★ 唯一未闭合项**：★ **evidence_span 的行级定位**（★ 47/86 只有锚点）
★ ★ ★ ★ —— 这不是字段丢失，★ 而是**定位精度不足**，★ 属抽取层缺口。

---

## 四、★ 映射统计

| smtp | 63 | 82 | 0 | 82 | {'definition': 55, 'syntax': 19, 'value_enum_spec': 8} |
| rtsp | 107 | 152 | 0 | 152 | {'syntax': 45, 'definition': 71, 'existence': 4, 'target_state': 14, 'value_enum_spec': 16, 'required_header_global': 1, 'required_header_by_method': 1} |
| DHCPv4 | 92 | 99 | 0 | 99 | {'definition': 15, 'syntax': 13, 'target_state': 19, 'binary_layout': 15, 'option_layout': 37} |

★ ★ **★ 映射失败 0；★ FactID 全部可用既有 `compute_fact_id` 重算。**
