# T0-A v6 Gold 原始输出与错误锚点复核

## 一、Raw 内容

| span | entity | meaning（摘要） | constraint |
|---|---|---|---|
| 22 | SMTP | 文档描述一个 SMTP 服务扩展，允许用 TLS 提供私密认证通信 | 空 |
| 25 | TLS | TLS 使 SMTP 代理能保护通信免受窃听 | 空 |

两条与 Gold `-30-1`（30–33）、`-30-2`（33–35）语义一致。

## 二、为什么没进 Fact

第 22 行原文是 `and status of this protocol. Distribution of this memo is unlimited.`，第 25 行是空行——都不含 SMTP/TLS 作为实体锚点（22 行实际有 SMTP？复核：该行为样板句，无 SMTP）。

`entity_not_in_span` 触发，两条被拒。

## 三、能否用两阶段机制恢复

能，但没有执行：需要对这两条命题做一次 Evidence 对齐（给 quote），再用 `locate_quote` 得到 30/33，然后重建 Norm。

本轮禁止新调用，所以：

- 这两条维持 `evidence_pending`；
- **不能**直接把 22 改成 30、25 改成 33；
- 也**不能**把 v4 的 quote 冒充成 v6 本轮对齐结果（v4 的 30/33 可作为对照，但来源标 cross-run）。

## 四、结论

v6 的 Gold 缺口属于「程序拒收」，可通过 quote 对齐恢复；恢复需要一次第二阶段调用，待批。
