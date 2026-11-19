# Value.type 清点审计

## 一、文档声明（`models.py:17` 注释）

12 种：`scalar / enum / set / sequence / range / pattern / struct / ref / observation / binary / union / text`。

## 二、代码实际使用（`grep Value(type=`）

`text / struct / set / scalar / pattern` —— 只占 12 种的一半。

## 三、历史持久化实测（`derived/per_source/**/*.jsonl`，逐条 `all_claims[].value.type`）

| 类型 | 条数 | 是否在声明表 |
|---|---|---|
| text | 3 676 | 是 |
| struct | 815 | 是 |
| pattern | 656 | 是 |
| set | 348 | 是 |
| **str** | **74** | **否** |
| scalar | 64 | 是 |

## 四、关键发现：`str` 是未声明但真实存在的类型

样本：`derived/per_source/smtp/expert_note/facts/expert_note.jsonl`，subject `method/BDAT`。

含义：直接采用"12 种"注册表会**拒绝 74 条历史知识**。因此注册表必须把 `str` 列为 legacy 允许值，并在文档标注"未在声明表、但历史存在"。

## 五、未知类型可写入的入口

`Value.type` 是 `str`，`canonical_serialize` 不做类型检查，`models.Value` 无校验 ⇒ 任何构造点都能写入任意字符串。

## 六、建议注册表

12 种 + `str`（legacy）= 13 个允许值。与历史集合完全覆盖，无遗漏。
