# T0-A RFC 341 行 Raw 召回逐层归因

## 一、原文

```
For this reason, clients and servers MUST discard any knowledge
obtained prior to the start of the TLS handshake upon completion of
```

跨 341–343 行，前有 337–340 的页脚与页眉（`Hoffman Standards Track [Page 6]` / `RFC 3207 SMTP Service Extension…`）。

## 二、逐层

| 层 | 结论 | 依据 |
|---|---|---|
| 1 原文 | 存在，341 行起句 | 冻结文本 |
| 2 切块 | 属于块 4（278–347） | `_split_blocks` 结果 |
| 3 请求 | 块 4 在第一批（块 1–5）内，确实发给模型 | 批大小 5 |
| 4 原始响应 | v4 的 30 条 item 中，span 335–350 区间 **0 条**，无 "discard" 相关命题 | `cache.json` 检索 |
| 5 Norm/Fact | 无输入即无输出，不是过滤造成 | — |
| 6 跨页影响 | 句子被页脚/页眉打断（341 前是 337–340） | 原文 |

## 三、归因

**model_omission**，且发生在跨页位置。

可能的成因（按可能性排序）：

1. 句首 `For this reason,` 是承接前文的指代，模型在块内看不到完整上文（前一段在 325–336 附近），选择跳过；
2. 页脚/页眉噪声让模型把 341–343 当作版面文字；
3. 该句没有独立小标题，属于"承接型规范句"，比带小节的规范句更容易被漏。

三条都是推测，没有逐条验证。

## 四、不是这些原因

- 不是块未覆盖（341 在块 4 内）；
- 不是 Norm/Fact 过滤（Raw 里就没有）；
- 不是 Prompt 缺"规范义务"要求（同块内 352 行的 MAY 句被抽到了）。

## 五、最小下一步（需批准，本轮不执行）

只针对"承接型规范句"做最小调优：

1. Prompt 增加一句：以 `For this reason` / `Therefore` / `In this case` 开头的句子，若含 MUST/SHOULD，仍需抽取，并在 `condition` 中记录其承接对象；
2. 或在切块时避免页脚/页眉进入块文本（属于切块层改动，风险更高，需单独评估）。

不建议为此改 Schema 或注入知识。

## 六、边界

v5 的 Raw 缓存未归档（只存了 Fact），因此无法核验 v5 是否也漏。这属于归档缺口，已记录。
