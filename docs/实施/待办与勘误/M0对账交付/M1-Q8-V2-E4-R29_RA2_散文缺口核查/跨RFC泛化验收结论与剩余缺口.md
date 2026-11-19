# 跨 RFC 泛化验收结论与剩余缺口

## 一、结论

本轮**未完成**，不登记任何泛化通过状态。

```
cross_rfc_fulltext_blocked_missing_inputs
cross_rfc_fulltext_blocked_batch_capacity
```

## 二、阻断项

| # | 阻断 | 证据 |
|---|---|---|
| 1 | RFC 9112 / 9293 原文不在 `kb/` | 目录仅有 DHCPv4/rtsp/sip/smtp |
| 2 | RFC 2131 5 块/批超出 8000 输出 | 第 1 批 `finish_reason=length` |
| 3 | 失败运行未落证据 | 临时脚本未写 result/guard |

## 三、需要的批准

1. 允许把 RFC 9112、9293 入库（下载 + 登记 SHA256），或改选已在库的协议（rtsp/sip）；
2. 允许 RFC 2131 改为 2 块/批（17 次请求）；
3. 后续一律走 `t0a_executor.py`，保证异常留证。

## 四、已完成的可复用部分

- Gold 预登记（6 条，含承接型、条件型、例外型）；
- RFC 2131 全文块映射与 token 估算；
- 批大小不可跨文档沿用的实证（3207 两批成功 vs 2131 首批截断）。

## 五、边界

本轮 1 次真实请求，0 条新知识进入任何集合；未改 Prompt、未改 main。
