# R29 RA-1 D1 ABNF 知识类型兼容分析

## 一、结论

**现有契约不能无损承载 ABNF 语法产生式。** 影子可以产出候选 Norm，但不能正式映射到 Canonical：要么新增知识身份（kind + subject type），要么把产生式伪装成 header 字段（语义错），两者都不属于「复用既有契约」。

因此本轮停在影子验证，不申请直接合入。

## 二、现有承载面

| 检查项 | 事实 |
|---|---|
| Norm.kind 合法取值 | `RFC_KIND_MAP` 只有 5 类：transition / field / field_value / outcome / method（另有 prose_semantics） |
| 未知 kind 的后果 | `map_norm_to_facts()` 返回 `[]`，事实被静默丢弃（`norm.py:628-637`） |
| field 的映射 | `field_norm_to_facts()` 固定 `subject=_qualified_subject("header", name)`，aspect 为 `syntax` 与 `definition` |
| aspect 数量 | 21 个，`aspect_registry.json` 冻结 |
| 身份 | NormID = `protocol.kind.name`；FactID/EvidenceID 由 `compute_*` 从 subject/aspect/value 派生 |

## 三、三条候选承载路径与判定

| 路径 | 做法 | 结果 |
|---|---|---|
| P1 复用 `field` | 把 `npt-range = ...` 记成 header 字段 | 语义错：`npt-range` 不是头字段，会污染 headers 桶，且 subject 类型变 header |
| P2 新增 kind `syntax_production` + 新 subject type | 语义正确 | 需要动身份契约（新 kind、新 subject type），属正式变更 |
| P3 新增 kind 但复用 `header` subject | 折中 | 仍把语法规则标成头字段，语义不成立 |

判据：任务书要求「不得直接增加正式 Norm.kind、Canonical aspect 或第二套知识身份」。P2 触碰身份，P1/P3 语义错。**没有第四条路。**

## 四、影子怎么做的

- 新增 `kind="syntax_production"`（仅影子标签），content 保留 `<name> = <rhs>`。
- **不接线映射**：`map_norm_to_facts` 未改，因此 0 Fact、0 Evidence。
- 证据：影子跑完三协议 Facts 仍是 82 / 152 / 99，与 main 完全一致。

## 五、若要正式化，需要的最小契约变更

| 变更 | 内容 | 影响 |
|---|---|---|
| 新 kind | `syntax_production` | Norm 层新增一类，需在 RFC_KIND_MAP 注册 |
| 新 subject type | `syntax_rule`（否则只能塞 header） | 影响 FactID 的命名空间；旧 Fact 不受影响，但需声明新身份类 |
| aspect | 复用既有 `syntax`（pattern 值） | 不新增 aspect，21 个不变 |
| 去重 | 与 field/method 同名时丢弃产生式 | 已在影子实现 |

这三条都不是「实现细节」，需要项目方批准后另起变更。

## 六、限制

1. 本轮只验证到 Norm 级，没有做 Canonical 语义验证（无映射）。
2. `syntax` aspect 的既有语义是「头字段语法」，用于语法产生式是否合适，需要设计确认，不是工程能定的。
