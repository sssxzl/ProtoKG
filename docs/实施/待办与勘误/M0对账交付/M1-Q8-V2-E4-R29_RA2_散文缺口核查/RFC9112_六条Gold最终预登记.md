# RFC 9112 六条 Gold 最终预登记

| 编号 | 分层 | 命题 | 类型 |
|---|---|---|---|
| H1 | 消息格式 | HTTP 消息 = start-line + 字段 + CRLF CRLF + 可选 body | ABNF |
| H2 | 请求行 | method SP request-target SP HTTP-version | ABNF |
| H3 | 字段 | 字段名不得含空白 | 语法限制 |
| H4 | 消息体 | Transfer-Encoding 与 Content-Length 并存时的优先级 | 条件型 |
| H5 | 传输编码 | chunked 的帧格式与终止块 | 语法 |
| H6 | 连接 | 持久连接与 Connection: close 的处理 | 规范 |

评估：Raw 语义召回 / Norm 保留 / Evidence 定位三层分别统计，不按行号重叠判。
