# H2 request-line 的 Canonical 适配性

## 一、能表达

| 项 | 值 |
|---|---|
| syntax | `f2_f5d4a14e…`，pattern = `method SP request-target SP HTTP-version CRLF` |
| definition | `f2_0732306f…`，text = 中文释义 |
| Evidence | `file:rfc9112.txt#@261` |

组成元素与顺序完整保留，未添加 MUST/SHOULD。

## 二、不能无损表达的部分

1. **没有语法类 aspect**：借用 `syntax`（原为字段模式设计）；
2. **subject 是 header**：请求行不是头字段；
3. **definition 的释义是人工写的**，不是 RFC 原文——ABNF 本身没有自然语言解释，这属于"结构化来源 + 人工释义"，必须在侧车标明。

## 三、判定

```
H2_syntax_carried
H2_definition_needs_human_prose
canonical_mapping_partial
```

不判 blocked（语法本体进去了），但**不是无损**：类型借位 + 释义非原文。

## 四、契约缺口

真正无损需要一个"产生式规则"知识类型（规则名 + 表达式 + 可选官方释义），本轮不批。
