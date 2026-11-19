# T0-A v6 28 Raw → 16 Norm 逐条归因

## 一、机制

拒收发生在 `_extract_blocks` 的 span 证据校验：模型给的 span 行必须含所声称 entity（可在窗口内命中）。不命中即 `entity_not_in_span` 丢弃。

## 二、28 条去向

| 结果 | 条数 | 说明 |
|---|---|---|
| 保留 | 16 | span 命中 |
| 唯一实体 → 重锚后可保留 | 2（168→177、226→235） | 修正后 18 |
| 实体多处出现，无法确定性重锚 | 10（含 22、25） | 仍丢弃 |

12 条丢失里：

| span | entity | 出现次数 | 性质 |
|---|---|---|---|
| 22 | SMTP | 70 | Gold 候选，歧义 |
| 25 | TLS | 90 | Gold 候选，歧义 |
| 68 | STARTTLS | 33 | 歧义 |
| 180 | SMTP server | 13 | 歧义 |
| 207/229 | server | 44 | 歧义 |
| 228 | client | 49 | 歧义 |
| 285 | SMTP client and server | 3 | 歧义 |
| 306 | clients and servers | 2 | 歧义 |
| 311 | implementation | 3 | 歧义 |
| 168 | both parties | 1 | **已重锚** |
| 226 | client and the server | 1 | **已重锚** |

## 三、不是这些原因

- 不是 Norm 身份去重（16 条 norm_id 各自不同）；
- 不是 kind 分流回归（11 legal_boundary + 5 definition 分布正常）；
- 不是 quote 校验（v6 不产 quote，校验分支未触发）。

## 四、纠正一个此前的错误说法

我在上一轮写「v6 原始模型未抽出两条 Gold」——**不准确**。

v6 的 Raw 里确实有 span 22（SMTP）与 25（TLS）两条，语义就是 Gold 的两句。它们没进 Fact，是因为**模型行号错了，被我们的 span 校验拒收**。

这是程序侧拒收，不是模型遗漏。历史报告保留，此处更正。

## 五、能修到什么程度

- 唯一实体可重锚：2 条（已实现，见补丁）；
- 多处出现：不能靠 entity 猜，需要 quote 定位（第二阶段机制），本轮不跑模型，因此这 10 条维持 pending。
