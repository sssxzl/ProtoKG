# H2 request-line 的 Canonical 适配性

## 一、能表达的部分

ABNF 规则被映射为 `syntax` aspect，pattern 承载表达式：

| 项 | 值 |
|---|---|
| fact_id | `f2_f5d4a14ef8f136cf` |
| aspect | syntax |
| subject | header / request-line |
| Evidence | `rfc:@file:rfc9112.txt#@261` |

`request-line = method SP request-target SP HTTP-version CRLF` 的**组成与顺序**保住了。

## 二、不能表达的部分

1. **没有"语法"类 aspect**：现在只能借用 `syntax`（原为字段模式设计），语义上勉强；
2. **subject 类型是 header**：请求行不是头字段，这是沿用了散文通道的老问题；
3. **definition 缺失**：ABNF 本身不含自然语言释义，若强行写 definition 就是编造。

## 三、判定

```
H2_syntax_carried_partially
canonical_mapping_partial
```

不算 `canonical_mapping_blocked`（语法本体进去了），但也不能说"无损表达"——`syntax` 是借来的类型。

## 四、要真正无损需要什么

一个能表达"产生式规则"的类型（规则名 + 表达式 + 可选释义），属于契约扩展，本轮不批。
