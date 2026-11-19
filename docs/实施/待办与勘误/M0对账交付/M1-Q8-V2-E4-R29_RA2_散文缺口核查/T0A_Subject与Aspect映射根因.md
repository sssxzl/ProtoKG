# T0-A Subject 与 Aspect 映射根因

## 一、Subject 误标：不是模型的问题

根因在 `core/fused/extraction/norm.py` 的三个散文映射函数里，`Subject(type="header", ...)` 是**硬编码**的：

| 函数 | 原代码 | 位置 |
|---|---|---|
| `prose_semantics_norm_to_facts` | `Subject(type="header", name=name)` | 约 535 行 |
| `prose_constraint_norm_to_facts`（未解析主体分支） | 同上 | 约 573 / 584 行 |
| `prose_constraint_norm_to_facts`（Rule Slot 分支） | 同上 | 约 626 行 |

注释写明「复用已有类型 ⇒ 不新增主体类型」，代价是把 `client`、`both parties`、`implementation` 全标成邮件头。

## 二、Aspect 单一：兜底分支写死 definition

`prose_constraint_norm_to_facts` 在「主体未解析」时返回 `definition`；在「action/object 缺失」时也返回 `definition`。本次 13 条真实 Fact 全部走兜底，所以清一色 definition——**不是模型没给 action/object**（22 条 item 里 18 条有），而是主体未解析把约束打回 definition。

## 三、最小修正

复用既有类型，不新增 Subject 类型、不改 FactID 算法：

| 改动 | 内容 |
|---|---|
| 新增 `_prose_subject_type(name, norm)` | 参与方词（client/server/parties/user/implementation/agent…）⇒ `actor`；其余 ⇒ `protocol`；仅当 `entity_type == "header"` 才保留 `header` |
| 约束兜底分支 | `definition` ⇒ `legal_boundary` |
| Rule Slot 分支 | 主体类型改用上述函数，aspect 仍 `legal_boundary` |

## 四、验证（真实缓存离线回放）

| 项 | 修正前（真实运行） | 修正后（回放） |
|---|---|---|
| Subject 分布 | header 13 | actor 9 / protocol 4 |
| Aspect 分布 | definition 13 | legal_boundary 8 / definition 5 |
| Fact 数 | 13 | 13 |
| 真 Header 知识 | — | 字段 Norm 仍为 `header` + `syntax`（单独验证通过） |

## 五、边界

- 这修正的是**映射层**，不改变模型输出；
- 不重算历史知识，不批量重建中枢；
- `actor` / `protocol` 是既有类型（仓库内其它映射已在用），未新增枚举。
