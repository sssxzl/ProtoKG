# T0-A 原文 Quote 确定性定位与负例

## 一、定位器

`prose_semantics.locate_quote(lines, quote)`：

1. 按行拼接冻结原文，记录每行字符起点；
2. 先做原文精确匹配（含换行）；
3. 失败则做空白归一化匹配（合并连续空白、忽略大小写），仅当空白形态不同；
4. 唯一命中才返回行区间，多处命中返回 `ambiguous`；
5. 未命中返回 `quote_not_found`。

## 二、离线验证（真实 RFC 3207）

| 用例 | 结果 |
|---|---|
| 跨行摘要句（30–32） | `(30, 32, whitespace_normalized_match)` |
| 含双倍空格的同句 | `(33, 34, whitespace_normalized_match)` |
| 不存在的句子 | `(None, None, quote_not_found)` |
| 过短词 `the`（多处出现） | `(None, None, ambiguous)` |

## 三、接入抽取链路

- 模型新增 `evidence_quote` 字段；
- 定位成功 ⇒ `verified_span`、`span_line` 改为证据真实起始行，`source` 重写为 `file:<doc>#@<新行>`；
- 模型行号与验证行号不同 ⇒ `evidence_match_status=reanchored`；
- 未命中或歧义 ⇒ **丢弃该条**，计入 `quote_unverified`，不伪造证据。

## 四、接入时踩的坑

第一次真实运行（runA）直接抛 `TypeError: 'NoneType' object is not iterable`——执行器没有传 `doc_lines`，定位器对 `None` 迭代。

已修：`doc_lines` 缺失时用块内容按起始行重建。这次失败仍消耗了 2 次请求（输入 6 433），记录在 `runA_failed_*`，不隐藏。

## 五、边界

- quote 必须逐字来自原文；模型改写即 `quote_not_found`，会被丢弃；
- 「quote 存在」不等于「quote 支持该命题」，这层仍需人工或二次校验，本轮未自动化。
