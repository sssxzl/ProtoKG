# 跨 RFC Evidence 逐条支持审查

## 一、定位

12/12 条获得唯一引用，`verified_span` 全部落在原文：

| 模型行 | 验证行 |
|---|---|
| 488 | 489–490 |
| 494 | 493–497 |
| 498 | 497–499 |
| 499 | 499–501 |
| 1712 | 1712 附近（含 SHOULD NOT 句） |

## 二、语义抽查

- 498：命题「MUST be unique within the subnet」，引用同句，主体 client identifier，一致；
- 1712：命题「SHOULD NOT reuse offered addresses」，引用同句，主体 servers，强度 SHOULD NOT，一致。

## 三、未做

未逐条做 28 条那样的完整语义审查——样本 12 条中我核了 4 条，其余标 `pending_review`，不在本轮宣称全部通过。

## 四、结论

定位机制在 DHCP 文本上同样有效（12/12），没有出现 SMTP 特有的失败。
