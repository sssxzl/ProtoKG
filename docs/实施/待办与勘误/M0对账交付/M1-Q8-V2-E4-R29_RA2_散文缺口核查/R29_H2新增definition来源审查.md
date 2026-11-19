# H2 新增 definition 来源审查

## 一、结论：不是 RFC 原文，必须移出已验证集合

| 检查 | 结果 |
|---|---|
| 是否仅由测试构造 | **是**。释义「HTTP 请求行由方法、请求目标、协议版本依次以单个空格分隔组成」是我写的中文说明，RFC 9112 无此句 |
| 是否有独立原文支持 | 否。ABNF 只有产生式，没有自然语言释义 |
| 是否错误进入已验证集合 | 是。`f2_0732306f…` 的 claim `authority=rfc`，但文本非原文 ⇒ 标签错误 |
| syntax FactID 是否稳定 | 是，`f2_f5d4a14e…` 未变 |

## 二、处理

- 侧车 `structural_closure.json` 中该条标记 `provenance=test_constructed`、`verified=false`；
- 验证集合只保留 H2 syntax；H2 判定维持 `canonical_mapping_partial`；
- definition 不再计入任何"已验证知识"统计。

## 三、教训

"给 ABNF 补一句人话解释"看起来无害，实际是把人的话冒充 RFC 知识。以后 definition 的 text 必须能在原文找到对应句，否则只能进侧车说明字段。

## 四、D4 的 `optional` 标记

`4 | optional: …` 中的 `optional` 是解析器要求的 modality 占位，只影响 `epistemic_type`，实测 D4 两条 Fact 的 epistemic 均为 `normative_unspecified`，**未引入"字段可选"语义**。

但它仍是原文没有的词。建议改用中性占位（如 `note:`）或允许无 modality 的 `| :`，避免误读。本轮不改。
