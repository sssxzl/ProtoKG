# ABNF / 表格 / 位域逐项解析结果

## 一、RFC 2131

| 目标 | 结果 | 证据 |
|---|---|---|
| D3 flags 保留位 MUST 0 | **恢复** | 587 行 `reserved for future use. They MUST be set to zero`；另有 MBZ 图例 594/599 |
| D4 siaddr 定义 | **恢复** | 541 行 `siaddr  4  IP address of next server to use in bootstrap` |

误报：2 条附录参考文献被当成 ABNF 规则（`MTU`、`RD`），属形态误判，需过滤。

## 二、RFC 9112

| 目标 | 结果 | 规则名 |
|---|---|---|
| H1 消息结构 | **恢复** | `HTTP-message`（同时抽到 `message-body`） |
| H2 请求行 | **恢复** | `request-line`（另有 `start-line`） |
| H3 字段名空白 | **恢复** | `field-name` |
| H5 chunked 语法 | **恢复** | `chunked-body` / `chunk` / `chunk-size` / `last-chunk` 等 10 条 |

## 三、误报与限制

- 2131 的 2 条附录误报需要白名单过滤；
- 9112 的 81 条含重复定义（同一规则分节重述），需按规则名去重；
- 表格识别依赖固定列宽，对变宽表格会漏；
- 位域仅识别文字中含 MBZ/zero 的行，纯图例行需另行处理。
