# Compatibility Mapping 早期 → 当前（2026-10-08）

> 状态：Draft｜实现见 `core/fused/compat.py`（`convert_v1_fact`）
>
> 旧 fact_key (v1) → 新 FactKey.subject / Aspect（v2）
> 本文不重构旧事实，只定义**映射规则**，供 `core/fused/compat.py` 的 `convert_v1_fact` 实现。

## 映射表

| 旧 `kind` | 旧 `subject` | 旧 `property` | → 新 Subject | → 新 Aspect | → 旧 actor 处理 |
|---|---|---|---|---|---|
| `method` | `<M>` | `existence` | `{type:"method", name:"<M>"}` | `"existence"` | client/server→qualifiers; both/not_applicable→丢弃 |
| `method` | `<M>` | `security_condition` | `{type:"method", name:"<M>"}` | `"security_property"` | 同上 |
| `method` | `<M>` | `security_consequence` | `{type:"method", name:"<M>"}` | `"security_property"` | 同上 |
| `method` | `<M>` | `relation_to_other_field` | `{type:"method", name:"<M>"}` | `"relation_to_other"` | 同上 |
| `method` | `<M>` | `occurrence` | `{type:"method", name:"<M>"}` | `"occurrence"` | 同上 |
| `header` | `<H>` | `existence` | `{type:"header", name:"<H>"}` | `"existence"` | 同上 |
| `header` | `<H>` | `security_condition` | `{type:"header", name:"<H>"}` | `"security_property"` | 同上 |
| `header` | `<H>` | `security_consequence` | `{type:"header", name:"<H>"}` | `"security_property"` | 同上 |
| `header` | `<H>` | `value_type` / `value_range` / `default_value` / `case_sensitivity` / `relation_to_other_field` | `{type:"header", name:"<H>"}` | 同名 property → aspect name | 同上 |
| `header` | `<H>` | `observed_presence_rate` / `observed_co_occurrence` / `observed_occurrence_rate` | `{type:"header", name:"<H>"}` | 同名 | 同上 |
| `state` | `<S>` | `existence` | `{type:"state", name:"<S>"}` | `"existence"` | server→qualifiers |
| `state` | `<S>` | `target_state` / `relation_to_other_field` | `{type:"state", name:"<S>"}` | 同名 | server→qualifiers |
| `constraint` | `status.<NNN>` | `value_type` | `{type:"status", name:"<NNN>"}` | `"value_type"` | server→qualifiers |
| `transition` | (见下) | (任意) | `{type:"relation", name:"transitions_to", qualifiers:{source,target}}` | (property → aspect) | server→qualifiers |
| `packet_role_pair` | `<P>` | (任意) | ❌ v2 未注册 `packet_role` 类型——记入错误清单 | — | — |
| **未识别** | (任意) | (任意) | ❌ 未识别——记入错误清单返回 | — | — |

> 备注: `kind="packet_role_pair"` 是 v1 hub 曾加入的扩展 kind（不在 v1 基础 5 类枚举内），但现有 131 Facts **不涉及**（实测 kind 分布：constraint 43 / method 52 / header 11 / state 4 / transition 21，packet_role_pair 计数 0；详见 `local/five_source_audit.md`）。

> 备注: `property="security_consequence"` 在 v1 实测存在 2 条（`method.SETUP` 与 `header.authorization`），v2 **已映射** —— `core/fused/compat.py` 的 `_PROPERTY_TO_ASPECT` 将其归入 `"security_property"` 桶（与 `security_condition` 同桶），不记入错误清单。v1 实测 property 分布共 8 个值：`value_type` 43 / `existence` 25 / `relation_to_other_field` 22 / `target_state` 21 / `security_condition` 9 / `occurrence` 6 / `case_sensitivity` 3 / `security_consequence` 2。

> 备注: `packet_role` 未在 v2 注册表（v2 只注册 method/header/state/status/relation/protocol/actor），故 `packet_role_pair` 走到 fail-closed 分支：即使 v1 出现该 kind，也会因目标 subject type 未注册而被拒。

## Subject.type 的最终映射（v1 kind → v2 type）

```
v1 kind              v2 Subject.type
─────────────────────────────────────
method               method
header               header
state                state
constraint / status.NNN / actor   status
  (or method/header 看具体 subkind)
transition           relation   (name="transitions_to")
packet_role_pair     packet_role   ⚠ v2 注册表未注册 packet_role
```

> 上表描述 `core/fused/compat.py` 的 `_KIND_TO_TYPE` 映射（`packet_role_pair → packet_role`
> 在代码中确实如此），但 v2 注册表只含 method / header / state / status / relation /
> protocol / actor —— `packet_role` 未注册，走 fail-closed 分支记入错误清单。

## Actor 处理细则

- `client` / `server` → 进 `Subject.qualifiers["actor"]`
- `both` / `not_applicable` → 丢弃（无语义增量）
- 缺失 / null → 不写 `actor` key

## 无法映射清单的处理

`convert_v1_fact` 对无法映射的 fact：

- **不抛错**（双轨阶段，向后兼容优先）
- 单条入口 `convert_v1_fact(v1_fact_json) -> Fact | str`：无法映射时**返回错误描述字符串**
  （如 `"unmapped kind='...'"` / `"unmapped property='...'"`），不抛异常
- 批量入口 `convert_v1_fact_jsonl(path) -> (list[Fact], list[dict])`：错误登记进返回的
  errors 列表，条目形如 `{line, reason}`（解析/单条失败）或
  `{canonical_key, reason, group_size}`（同 canonical key 合并失败）
- 调用方负责处理错误清单；compat 模块本身只读 `derived/fused/facts/`，不写任何文件

## 不动 v1

本文仅定义**映射规则**与**实现入口**。
旧 fact 的物理格式（derived/fused/facts/*.jsonl）**完全不动**；
新结构（v2 core/）与 v1 共存；v1 的裁决链 / validation chain 所在的 `core/fused/runtime/`、`reader.py`、`writer.py` 已于 2026-10-09 随 架构退役移除，不存在「不修改 v1 代码链」这一约束。
切换发生在用户**明确迁移**时（早期 → 当前 的语义化切换由后续决策触发）。