# T0-A 真实 Gold 漏抽逐层归因

## 一、结论

两条 Gold 都停在 **model_omission**：原文完整进入请求，模型输出里没有该命题。

```
input_ok → model_omission → (parser/norm/canonical 未参与)
```

## 二、逐层证据

| 层 | 检查 | 结果 |
|---|---|---|
| 1 原文 | 第 30-35 行内容 | “This document describes an extension to the SMTP service that allows…protect some or all of their communications…” |
| 2 切块 | 块 1 覆盖 1-114 行 | 30-35 在块 1 内 |
| 3 请求 | 块 1 进入第 1 批 | 是（批 1 = 块 1-5） |
| 4 原始响应 | 22 条 item 的 span 分布 | 76、88、94、127、146、155、158、172、183、186、211、214、217、220、230、231、232、309、313、315、341、352 |
| 5 Norm | 13 条 Norm | 全部来自上述 item，无 30-35 |
| 6 Fact | 13 条 | 同源，无 30-35 |
| 7 Gold 匹配 | 锚点是否偏移 | 最近锚点 76，与 30-35 相距 41 行以上 |

## 三、判断

- 模型输出的**最小 span 是 76 行**，整段 Introduction（30-35）没有任何条目。
- 模型确实产出了 STARTTLS 相关知识，但内容是「服务扩展名称、EHLO 关键字值」，锚在 76 行的章节标题处，**不是** 30-33 行那句「本文件描述一个扩展，允许 SMTP 保护通信」。
- 因此不能算「锚点偏移导致漏判」：命题不同，不是同一句话换了行号。

## 四、Gold 判定

| Gold | 结论 | 依据 |
|---|---|---|
| `-30-1`（30-33） | model_omission | 无对应语义条目，最近 76 行讲的是名称与关键字 |
| `-30-2`（33-35） | model_omission | 无「protect communications from eavesdroppers」类条目 |

## 五、待改 Prompt 的最小建议（未执行）

1. 现有 prompt 要求按块抽「定义/约束」，但块的头部是章节标题，模型倾向从标题句开始；
2. 建议在 prompt 中明确「包含 Abstract/Introduction 中的规范性陈述，不要只抽章节标题后的内容」；
3. 下次真实验证观察点：30-35 是否出现 span ≤ 35 的条目，以及 meaning 是否含 “protect/eavesdrop”。

本轮不发起调用，不把人工补写的 Gold 当模型成果。
