# RFC 规范语义 · 人工抽样核查包

> ★ **目的**：★ **独立核实真实 RFC 抽取内容的准确性**，并发现**误拒收 / 误隔离 / 错误归并**
> ★ **数据来源**：deepseek-flash 的**真实运行缓存**（`derived/cache/source_blocks/<协议>.prose.json`）
> ⇒ ⇒ **不使用 mock、不使用手工构造的 payload**
> ★ **本包不含任何「机制验收通过 ⇒ 语义正确」的结论** ⇒ ⇒ **结论由人工填写**
> ★ 生成时间：2026-11-13

## 〇、抽样范围与构成

| 协议 | 真实条目总数 | 抽样数 |
|---|---:|---:|
| rtsp | 176 | 10 |
| sip | 223 | 10 |
| smtp | 154 | 10 |
| DHCPv4 | 174 | 10 |
| **合计** | **727** | **40** |

**每协议的抽样构成**（按类别）：

| 协议 | 已确认强度的规范规则 | 强度未知（被隔离）候选 | 含条件或例外的规则 | 跨章节引用规则 | 被 L1/L2 拒收的候选 | 发生去重或多证据归并的规则 | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） |
|---|---:|---:|---:|---:|---:|---:|---:|
| rtsp | 2 | 2 | 3 | 1 | 1 | 0 | 1 |
| sip | 2 | 2 | 3 | 1 | 1 | 0 | 1 |
| smtp | 1 | 0 | 4 | 1 | 1 | 0 | 3 |
| DHCPv4 | 1 | 1 | 4 | 1 | 1 | 1 | 1 |

## 一、逐条样本（★ 人工审阅区）

> ★ **判定栏**：`正确 / 部分正确 / 错误 / 无法判断` ⇒ ★ 请在**「人工判定」**列填写，并在**错误原因**/**修改建议**列写明


### 协议 rtsp

#### S01 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 10 Method Definitions |
| 原始行号 | 第 **1651** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `If a server does not support a particular method` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1648|    Notes on Table 2: PAUSE is recommended, but not required in that a
    1649|    fully functional server can be built that does not support this
    1650|    method, for example, for live feeds. If a server does not support a
>>  1651|    particular method, it MUST return "501 Not Implemented" and a client
    1652|    SHOULD not try this method again for this server.
    1653| 
    1654| 10.1 OPTIONS
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "501 Not Implemented",
  "meaning": "当服务器不支持某方法时，必须返回状态码 \"501 Not Implemented\"。",
  "constraint": "MUST return \"501 Not Implemented\"",
  "span": 1651,
  "action": "return",
  "object": "\"501 Not Implemented\"",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "If a server does not support a particular method",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "server",
  "subject_span": 1650
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "501 Not Implemented",
  "action": "return",
  "object": "\"501 Not Implemented\"",
  "condition": "If a server does not support a particular method",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If a server does not support a particular method",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "return",
  "object": "\"501 Not Implemented\"",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S02 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.3 Terminology |
| 原始行号 | 第 **359** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     356| 
     357|    Continuous media:
     358|           Data where there is a timing relationship between source and
>>   359|           sink; that is, the sink must reproduce the timing relationship
     360|           that existed at the source. The most common examples of
     361|           continuous media are audio and motion video. Continuous media
     362|           can be real-time (interactive), where there is a "tight"
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "sink",
  "meaning": "The sink must reproduce the timing relationship that existed at the source.",
  "constraint": "the sink must reproduce the timing relationship that existed at the source",
  "span": 359,
  "action": "reproduce",
  "object": "the timing relationship that existed at the source",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "sink",
  "subject_span": 359
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "sink",
  "action": "reproduce",
  "object": "the timing relationship that existed at the source",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "reproduce",
  "object": "the timing relationship that existed at the source",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S03 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.4 Protocol Properties |
| 原始行号 | 第 **518** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     515|    Presentation description neutral:
     516|           The protocol does not impose a particular presentation
     517|           description or metafile format and can convey the type of
>>   518|           format to be used. However, the presentation description must
     519|           contain at least one RTSP URI.
     520| 
     521|    Proxy and firewall friendly:
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "presentation description",
  "meaning": "呈现描述必须至少包含一个 RTSP URI。",
  "constraint": "the presentation description must contain at least one RTSP URI",
  "span": 518,
  "action": "contain",
  "object": "at least one RTSP URI",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "presentation description",
  "subject_span": 518
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "presentation description",
  "action": "contain",
  "object": "at least one RTSP URI",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "contain",
  "object": "at least one RTSP URI",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S04 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 7.1.1 Status Code and Reason Phrase |
| 原始行号 | 第 **1229** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`is not required to`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；关键词无法归一：'is not required to' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1226|    defined in Section 11. The Reason-Phrase is intended to give a short
    1227|    textual description of the Status-Code. The Status-Code is intended
    1228|    for use by automata and the Reason-Phrase is intended for the human
>>  1229|    user. The client is not required to examine or display the Reason-
    1230|    Phrase.
    1231| 
    1232| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "client",
  "meaning": "客户端无须检查或显示 Reason-Phrase",
  "constraint": "The client is not required to examine or display the Reason-Phrase",
  "span": 1229,
  "action": "examine or display",
  "object": "Reason-Phrase",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "is not required to",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "client",
  "subject_span": 1229
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "client",
  "action": "examine or display",
  "object": "Reason-Phrase",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "negative",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "examine or display",
  "object": "Reason-Phrase",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S05 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 10.2 DESCRIBE |
| 原始行号 | 第 **1760** 行 |
| 强度 / 极性 | `None` / `positive`（原文等级措辞：`highly recommended`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；关键词无法归一：'highly recommended' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1757|        initialization format).
    1758| 
    1759|      In the interest of practical interoperability, it is highly
>>  1760|      recommended that minimal servers support the DESCRIBE method, and
    1761|      highly recommended that minimal clients support the ability to act
    1762|      as a "helper application" that accepts a media initialization file
    1763|      from standard input, command line, and/or other means that are
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "DESCRIBE",
  "meaning": "DESCRIBE 方法（用于请求媒体初始化信息）",
  "constraint": "强烈建议最小服务器支持 DESCRIBE 方法",
  "span": 1760,
  "action": "support the DESCRIBE method",
  "object": "the DESCRIBE method",
  "strength": "",
  "polarity": "positive",
  "keyword_raw": "highly recommended",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "minimal servers",
  "subject_span": 1760
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "DESCRIBE",
  "action": "support the DESCRIBE method",
  "object": "the DESCRIBE method",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "support the DESCRIBE method",
  "object": "the DESCRIBE method",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S06 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.3 Terminology |
| 原始行号 | 第 **326** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`may`）|
| 条件 / 例外 | `For audio/video feeds` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'may' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     323| 
     324|    Aggregate control:
     325|           The control of the multiple streams using a single timeline by
>>   326|           the server. For audio/video feeds, this means that the client
     327|           may issue a single play or pause message to control both the
     328|           audio and video feeds.
     329| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "client",
  "meaning": "For audio/video feeds, the client may issue a single play or pause message to control both the audio and video feeds.",
  "constraint": "client may issue a single play or pause message to control both audio and video feeds",
  "span": 326,
  "action": "issue",
  "object": "a single play or pause message",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "may",
  "condition": "For audio/video feeds",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "client",
  "subject_span": 326
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "client",
  "action": "issue",
  "object": "a single play or pause message",
  "condition": "For audio/video feeds",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "For audio/video feeds",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "issue",
  "object": "a single play or pause message",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S07 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.4 Protocol Properties |
| 原始行号 | 第 **536** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must be able to`）|
| 条件 / 例外 | `If a client can start a stream` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must be able to' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     533|           continuous media requires server state in most cases.
     534| 
     535|    Appropriate server control:
>>   536|           If a client can start a stream, it must be able to stop a
     537|           stream. Servers should not start streaming to clients in such
     538|           a way that clients cannot stop the stream.
     539| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "client",
  "meaning": "能启动流的客户端必须能够停止该流。",
  "constraint": "If a client can start a stream, it must be able to stop a stream.",
  "span": 536,
  "action": "stop",
  "object": "a stream",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must be able to",
  "condition": "If a client can start a stream",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "client",
  "action": "stop",
  "object": "a stream",
  "condition": "If a client can start a stream",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If a client can start a stream",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "stop",
  "object": "a stream",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S08 ｜ 跨章节引用规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.5 Extending RTSP |
| 原始行号 | 第 **582** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`SHOULD`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section 12` ⇒ 定位 **resolved**（章节 `12`）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     579|      * Some servers may not support setting stream parameters and thus
     580|        not support GET_PARAMETER and SET_PARAMETER.
     581| 
>>   582|    A server SHOULD implement all header fields described in Section 12.
     583| 
     584|    It is up to the creators of presentation descriptions not to ask the
     585|    impossible of a server. This situation is similar in HTTP/1.1 [2],
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "server",
  "meaning": "服务器应当实现 Section 12 描述的所有头部字段。",
  "constraint": "A server SHOULD implement all header fields described in Section 12.",
  "span": 582,
  "action": "implement",
  "object": "all header fields described in Section 12",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "",
  "exception": "",
  "cross_ref": "Section 12",
  "cross_ref_status": "resolved",
  "normative_subject": "A server",
  "subject_span": 582
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "server",
  "action": "implement",
  "object": "all header fields described in Section 12",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "SHOULD",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "implement",
  "object": "all header fields described in Section 12",
  "cross_ref": "Section 12",
  "cross_ref_status": "resolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S09 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.4 Protocol Properties |
| 原始行号 | 第 **498** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「conference initiation protocol」（该行：initiation protocol either provides or can be used to create a） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     495|    Separation of stream control and conference initiation:
     496|           Stream control is divorced from inviting a media server to a
     497|           conference. The only requirement is that the conference
>>   498|           initiation protocol either provides or can be used to create a
     499|           unique conference identifier. In particular, SIP [12] or H.323
     500|           [13] may be used to invite a server to a conference.
     501| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "conference initiation protocol",
  "meaning": "唯一要求是会议发起协议要提供或能用来创建唯一的会议标识符。",
  "constraint": "conference initiation protocol either provides or can be used to create a unique conference identifier",
  "span": 498,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "conference initiation protocol",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "conference initiation protocol",
  "object": "conference initiation protocol",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S10 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.1 Purpose |
| 原始行号 | 第 **235** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     232| 
     233| 1.1 Purpose
     234| 
>>   235|    The Real-Time Streaming Protocol (RTSP) establishes and controls
     236|    either a single or several time-synchronized streams of continuous
     237|    media such as audio and video. It does not typically deliver the
     238|    continuous streams itself, although interleaving of the continuous
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "RTSP",
  "meaning": "establishes and controls either a single or several time-synchronized streams of continuous media such as audio and video, and does not typically deliver the continuous streams itself",
  "constraint": "",
  "span": 235,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "RTSP",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "RTSP",
  "object": "RTSP",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
  "manifest": {
    "key": "f7d2ac2b993f3836ac0f1f29a5d0044767a8182dfbecf3afb15aa6a132904eec",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |


### 协议 sip

#### S11 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7 SIP Messages |
| 原始行号 | 第 **1482** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `even if the message-body is not` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1479| 
    1480|    The start-line, each message-header line, and the empty line MUST be
    1481|    terminated by a carriage-return line-feed sequence (CRLF).  Note that
>>  1482|    the empty line MUST be present even if the message-body is not.
    1483| 
    1484|    Except for the above difference in character sets, much of SIP's
    1485|    message and header field syntax is identical to HTTP/1.1.  Rather
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "empty line",
  "meaning": "即使没有消息体，空行也必须存在",
  "constraint": "空行必须存在",
  "span": 1482,
  "action": "be present",
  "object": "the empty line",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "even if the message-body is not",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "the empty line",
  "subject_span": 1482
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "empty line",
  "action": "be present",
  "object": "the empty line",
  "condition": "even if the message-body is not",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "even if the message-body is not",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "be present",
  "object": "the empty line",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S12 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 6 Definitions |
| 原始行号 | 第 **1112** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1109|          logical entity that receives a request and processes it as a
    1110|          user agent server (UAS).  In order to determine how the request
    1111|          should be answered, it acts as a user agent client (UAC) and
>>  1112|          generates requests.  Unlike a proxy server, it maintains dialog
    1113|          state and must participate in all requests sent on the dialogs
    1114|          it has established.  Since it is a concatenation of a UAC and
    1115|          UAS, no explicit definitions are needed for its behavior.
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "proxy server",
  "meaning": "文中作为对比的代理服务器：与它不同，B2BUA 维护 dialog 状态并须参与其建立的 dialog 上的所有请求",
  "constraint": "it maintains dialog state and must participate in all requests sent on the dialogs it has established",
  "span": 1112,
  "action": "participate in",
  "object": "all requests sent on the dialogs it has established",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "proxy server",
  "action": "participate in",
  "object": "all requests sent on the dialogs it has established",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "participate in",
  "object": "all requests sent on the dialogs it has established",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S13 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7 SIP Messages |
| 原始行号 | 第 **1480** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1477|                              [ message-body ]
    1478|          start-line       =  Request-Line / Status-Line
    1479| 
>>  1480|    The start-line, each message-header line, and the empty line MUST be
    1481|    terminated by a carriage-return line-feed sequence (CRLF).  Note that
    1482|    the empty line MUST be present even if the message-body is not.
    1483| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "start-line",
  "meaning": "起始行必须以回车换行序列 CRLF 结束",
  "constraint": "起始行必须以 CRLF 结尾",
  "span": 1480,
  "action": "be terminated by a carriage-return line-feed sequence (CRLF)",
  "object": "The start-line, each message-header line, and the empty line",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "The start-line, each message-header line, and the empty line",
  "subject_span": 1480
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "start-line",
  "action": "be terminated by a carriage-return line-feed sequence (CRLF)",
  "object": "The start-line, each message-header line, and the empty line",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "be terminated by a carriage-return line-feed sequence (CRLF)",
  "object": "The start-line, each message-header line, and the empty line",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S14 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7.2 Responses |
| 原始行号 | 第 **1558** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`is not required`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；关键词无法归一：'is not required' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1555|    outcome of an attempt to understand and satisfy a request.  The
    1556|    Reason-Phrase is intended to give a short textual description of the
    1557|    Status-Code.  The Status-Code is intended for use by automata,
>>  1558|    whereas the Reason-Phrase is intended for the human user.  A client
    1559|    is not required to examine or display the Reason-Phrase.
    1560| 
    1561|    While this specification suggests specific wording for the reason
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "Reason-Phrase",
  "meaning": "A client is not required to examine or display the Reason-Phrase.",
  "constraint": "A client is not required to examine or display the Reason-Phrase.",
  "span": 1558,
  "action": "examine or display",
  "object": "Reason-Phrase",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "is not required",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "A client",
  "subject_span": 1558
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "Reason-Phrase",
  "action": "examine or display",
  "object": "Reason-Phrase",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "negative",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "examine or display",
  "object": "Reason-Phrase",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S15 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 8.1.1.3 From |
| 原始行号 | 第 **2030** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`it is very important that ... not`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；关键词无法归一：'it is very important that ... not' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    2027|    header field, it contains a URI and optionally a display name.  It is
    2028|    used by SIP elements to determine which processing rules to apply to
    2029|    a request (for example, automatic call rejection).  As such, it is
>>  2030|    very important that the From URI not contain IP addresses or the FQDN
    2031|    of the host on which the UA is running, since these are not logical
    2032|    names.
    2033| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "From URI",
  "meaning": "From 头域中的 URI，用于表明请求发起方的逻辑身份。",
  "constraint": "it is very important that the From URI not contain IP addresses or the FQDN of the host on which the UA is running",
  "span": 2030,
  "action": "contain",
  "object": "IP addresses or the FQDN of the host on which the UA is running",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "it is very important that ... not",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "From URI",
  "subject_span": 2030
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "From URI",
  "action": "contain",
  "object": "IP addresses or the FQDN of the host on which the UA is running",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "negative",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "contain",
  "object": "IP addresses or the FQDN of the host on which the UA is running",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S16 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 6 Definitions |
| 原始行号 | 第 **1314** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `when sending a particular request` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1311|          alerted (ringing).
    1312| 
    1313|       Route Set: A route set is a collection of ordered SIP or SIPS URI
>>  1314|          which represent a list of proxies that must be traversed when
    1315|          sending a particular request.  A route set can be learned,
    1316|          through headers like Record-Route, or it can be configured.
    1317| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "proxies",
  "meaning": "Proxies in a route set must be traversed when sending a particular request.",
  "constraint": "must be traversed when sending a particular request",
  "span": 1314,
  "action": "traversed",
  "object": "proxies",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "when sending a particular request",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "proxies",
  "action": "traversed",
  "object": "proxies",
  "condition": "when sending a particular request",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "when sending a particular request",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "traversed",
  "object": "proxies",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S17 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7.1 Requests |
| 原始行号 | 第 **1536** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `To be compliant with this specification` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1533|            by SIP, and HTTP/1.1 replaced by SIP/2.0) regarding version
    1534|            ordering, compliance requirements, and upgrading of version
    1535|            numbers.  To be compliant with this specification,
>>  1536|            applications sending SIP messages MUST include a SIP-Version
    1537|            of "SIP/2.0".  The SIP-Version string is case-insensitive,
    1538|            but implementations MUST send upper-case.
    1539| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "SIP-Version",
  "meaning": "请求和响应消息中包含的 SIP 版本",
  "constraint": "applications sending SIP messages MUST include a SIP-Version of \"SIP/2.0\"",
  "span": 1536,
  "action": "include a SIP-Version of \"SIP/2.0\"",
  "object": "a SIP-Version of \"SIP/2.0\"",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "To be compliant with this specification",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "applications sending SIP messages",
  "subject_span": 1536
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "SIP-Version",
  "action": "include a SIP-Version of \"SIP/2.0\"",
  "object": "a SIP-Version of \"SIP/2.0\"",
  "condition": "To be compliant with this specification",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "To be compliant with this specification",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "include a SIP-Version of \"SIP/2.0\"",
  "object": "a SIP-Version of \"SIP/2.0\"",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S18 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7.3.1 Header Field Format |
| 原始行号 | 第 **1670** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`MAY`）|
| 条件 / 例外 | `if and only if the entire field-value for that header field is defined as a comma-separated list (that is, if follows the grammar defined in Section 7.3)` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section 7.3` ⇒ 定位 **resolved**（章节 `7.3`）|
| L1 验证 | **pending** ｜ 存在跨节引用但无法定位 ⇒ 待审 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1667|    Max-Forwards, and Proxy-Authorization, for example) appear towards
    1668|    the top of the message to facilitate rapid parsing.  The relative
    1669|    order of header field rows with the same field name is important.
>>  1670|    Multiple header field rows with the same field-name MAY be present in
    1671|    a message if and only if the entire field-value for that header field
    1672|    is defined as a comma-separated list (that is, if follows the grammar
    1673|    defined in Section 7.3).  It MUST be possible to combine the multiple
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "header field rows",
  "meaning": "Multiple header field rows with the same field-name MAY be present if and only if the entire field-value is defined as a comma-separated list following the grammar in Section 7.3.",
  "constraint": "only if the entire field-value is a comma-separated list following Section 7.3",
  "span": 1670,
  "action": "be present in a message",
  "object": "multiple header field rows with the same field-name",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "MAY",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list (that is, if follows the grammar defined in Section 7.3)",
  "exception": "",
  "cross_ref": "Section 7.3",
  "cross_ref_status": "unresolved",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "header field rows",
  "action": "be present in a message",
  "object": "multiple header field rows with the same field-name",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list (that is, if follows the grammar defined in Section 7.3)",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list (that is, if follows the grammar defined in Section 7.3)",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "be present in a message",
  "object": "multiple header field rows with the same field-name",
  "cross_ref": "Section 7.3",
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S19 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 4 Overview of Operation |
| 原始行号 | 第 **775** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「180 (Ringing) response」（该行：that is, Bob's phone rings.  Bob's SIP phone indicates this in a 180） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     772| 
     773|    Bob's SIP phone receives the INVITE and alerts Bob to the incoming
     774|    call from Alice so that Bob can decide whether to answer the call,
>>   775|    that is, Bob's phone rings.  Bob's SIP phone indicates this in a 180
     776|    (Ringing) response, which is routed back through the two proxies in
     777|    the reverse direction.  Each proxy uses the Via header field to
     778|    determine where to send the response and removes its own address from
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "180 (Ringing) response",
  "meaning": "Bob 的 SIP 电话用 180 (Ringing) 响应表示正在振铃，该响应沿反向经两个代理路由回主叫",
  "constraint": "",
  "span": 775,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "180 (Ringing) response",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "180 (Ringing) response",
  "object": "180 (Ringing) response",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S20 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 1 Introduction |
| 原始行号 | 第 **438** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     435| 1 Introduction
     436| 
     437|    There are many applications of the Internet that require the creation
>>   438|    and management of a session, where a session is considered an
     439|    exchange of data between an association of participants.  The
     440|    implementation of these applications is complicated by the practices
     441|    of participants: users may move between endpoints, they may be
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "session",
  "meaning": "会话被定义为一组参与者之间的数据交换",
  "constraint": "",
  "span": 438,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "session",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "session",
  "object": "session",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
  "manifest": {
    "key": "35792997d2f6578c41a2771669f9b80c5bda4125a25c939b46cc2e78b9301526",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |


### 协议 smtp

#### S21 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **119** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `If the client receives the 454 response` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     116| RFC 3207     SMTP Service Extension - Secure SMTP over TLS February 2002
     117| 
     118| 
>>   119|    If the client receives the 454 response, the client must decide
     120|    whether or not to continue the SMTP session.  Such a decision is
     121|    based on local policy.  For instance, if TLS was being used for
     122|    client authentication, the client might try to continue the session,
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "454",
  "meaning": "当客户端收到 454 响应时，它必须决定是否继续 SMTP 会话；该决定基于本地策略。",
  "constraint": "若客户端收到 454 响应，则必须决定是否继续 SMTP 会话",
  "span": 119,
  "action": "decide whether or not to continue the SMTP session",
  "object": "the SMTP session",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "If the client receives the 454 response",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "the client",
  "subject_span": 119
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "454",
  "action": "decide whether or not to continue the SMTP session",
  "object": "the SMTP session",
  "condition": "If the client receives the 454 response",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If the client receives the 454 response",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "decide whether or not to continue the SMTP session",
  "object": "the SMTP session",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S22 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc4954.txt` |
| 章节 | 12288 octets is considered to be a sufficient line length |
| 原始行号 | 第 **350** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`MAY`）|
| 条件 / 例外 | `In order to ensure interoperability with deployed software` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     347| 
     348|    Note that many existing client and server implementations implement
     349|    CRAM-MD5 [CRAM-MD5] SASL mechanism.  In order to ensure
>>   350|    interoperability with deployed software, new implementations MAY
     351|    implement it; however, implementations should be aware that this SASL
     352|    mechanism doesn't provide any server authentication.  Note that at
     353|    the time of writing of this document the SASL Working Group is
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc4954.txt",
  "entity": "new implementations",
  "meaning": "新实现可以选择实现 CRAM-MD5 SASL 机制，以与已部署软件互操作",
  "constraint": "新实现 MAY 实现 CRAM-MD5 SASL 机制；实现方应知悉该机制不提供服务器认证",
  "span": 350,
  "action": "implement",
  "object": "CRAM-MD5 SASL mechanism",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "MAY",
  "condition": "In order to ensure interoperability with deployed software",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "new implementations",
  "subject_span": 350
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "new implementations",
  "action": "implement",
  "object": "CRAM-MD5 SASL mechanism",
  "condition": "In order to ensure interoperability with deployed software",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "In order to ensure interoperability with deployed software",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "implement",
  "object": "CRAM-MD5 SASL mechanism",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S23 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 4.2 Result of the STARTTLS Command |
| 原始行号 | 第 **235** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     232|    [SASL] unless a client has sent an appropriate client certificate
     233|    during a TLS handshake.
     234| 
>>   235|    Both the client and the server MUST know if there is a TLS session
     236|    active.  A client MUST NOT attempt to start a TLS session if a TLS
     237|    session is already active.  A server MUST NOT return the STARTTLS
     238|    extension in response to an EHLO command received after a TLS
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "client",
  "meaning": "Both the client and the server must know whether a TLS session is active.",
  "constraint": "MUST know if there is a TLS session active",
  "span": 235,
  "action": "know",
  "object": "if there is a TLS session active",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "Both the client and the server",
  "subject_span": 235
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "client",
  "action": "know",
  "object": "if there is a TLS session active",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "know",
  "object": "if there is a TLS session active",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S24 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **144** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`SHOULD`）|
| 条件 / 例外 | `A SMTP server that is not publicly referenced may choose to require that the client perform a TLS negotiation before accepting any commands. In this case` / `other than NOOP, EHLO, STARTTLS, or QUIT` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     141|    relay or local delivery based on authentication supplied during the
     142|    TLS negotiation.
     143| 
>>   144|    A SMTP server that is not publicly referenced may choose to require
     145|    that the client perform a TLS negotiation before accepting any
     146|    commands.  In this case, the server SHOULD return the reply code:
     147| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "SMTP server",
  "meaning": "A SMTP server that is not publicly referenced may require TLS negotiation before accepting any commands; in that case it SHOULD return reply code 530 to every command other than NOOP, EHLO, STARTTLS, or QUIT",
  "constraint": "SHOULD return reply code 530 to every command other than NOOP, EHLO, STARTTLS, or QUIT",
  "span": 144,
  "action": "return",
  "object": "the reply code",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "A SMTP server that is not publicly referenced may choose to require that the client perform a TLS negotiation before accepting any commands. In this case",
  "exception": "other than NOOP, EHLO, STARTTLS, or QUIT",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "server",
  "subject_span": 146
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "SMTP server",
  "action": "return",
  "object": "the reply code",
  "condition": "A SMTP server that is not publicly referenced may choose to require that the client perform a TLS negotiation before accepting any commands. In this case",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "SHOULD",
  "polarity": "positive",
  "condition": "A SMTP server that is not publicly referenced may choose to require that the client perform a TLS negotiation before accepting any commands. In this case",
  "condition_status": "stated",
  "exception": "other than NOOP, EHLO, STARTTLS, or QUIT",
  "exception_status": "stated",
  "scope": null,
  "action": "return",
  "object": "the reply code",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S25 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 530 Must issue a STARTTLS command first |
| 原始行号 | 第 **151** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`SHOULD`）|
| 条件 / 例外 | `If the client and server are using the ENHANCEDSTATUSCODES ESMTP extension [RFC2034]` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     148|    530 Must issue a STARTTLS command first
     149| 
     150|    to every command other than NOOP, EHLO, STARTTLS, or QUIT.  If the
>>   151|    client and server are using the ENHANCEDSTATUSCODES ESMTP extension
     152|    [RFC2034], the status code to be returned SHOULD be 5.7.0.
     153| 
     154|    After receiving a 220 response to a STARTTLS command, the client MUST
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "ENHANCEDSTATUSCODES",
  "meaning": "ESMTP extension (RFC2034) that, when used by client and server, means the returned status code SHOULD be 5.7.0",
  "constraint": "SHOULD return status code 5.7.0",
  "span": 151,
  "action": "return",
  "object": "status code 5.7.0",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "If the client and server are using the ENHANCEDSTATUSCODES ESMTP extension [RFC2034]",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "ENHANCEDSTATUSCODES",
  "action": "return",
  "object": "status code 5.7.0",
  "condition": "If the client and server are using the ENHANCEDSTATUSCODES ESMTP extension [RFC2034]",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "SHOULD",
  "polarity": "positive",
  "condition": "If the client and server are using the ENHANCEDSTATUSCODES ESMTP extension [RFC2034]",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "return",
  "object": "status code 5.7.0",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S26 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc4954.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **147** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `If present` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section 4 of [BASE64]` ⇒ 定位 **unresolved**（章节 `None`）|
| L1 验证 | **pending** ｜ 存在跨节引用但无法定位 ⇒ 待审 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     144|           mechanism: A string identifying a [SASL] authentication
     145|           mechanism.
     146| 
>>   147|           initial-response: An optional initial client response.  If
     148|           present, this response MUST be encoded as described in Section
     149|           4 of [BASE64] or contain a single character "=".
     150| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc4954.txt",
  "entity": "initial-response",
  "meaning": "initial-response 是可选的初始客户端响应，若存在则必须按 [BASE64] 第 4 节编码或包含单个字符 \"=\"。",
  "constraint": "若存在，必须以 [BASE64] 第 4 节所述方式编码，或包含单个字符 \"=\"",
  "span": 147,
  "action": "encoded",
  "object": "this response",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "If present",
  "exception": "",
  "cross_ref": "Section 4 of [BASE64]",
  "cross_ref_status": "unresolved",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "initial-response",
  "action": "encoded",
  "object": "this response",
  "condition": "If present",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If present",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "encoded",
  "object": "this response",
  "cross_ref": "Section 4 of [BASE64]",
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S27 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 4.2 Result of the STARTTLS Command |
| 原始行号 | 第 **221** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`MAY`）|
| 条件 / 例外 | `received after the TLS handshake` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「EHLO command」（该行：command received after the TLS handshake MAY be different than the） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     218|    first command after a successful TLS negotiation.
     219| 
     220|    The list of SMTP service extensions returned in response to an EHLO
>>   221|    command received after the TLS handshake MAY be different than the
     222|    list returned before the TLS handshake.  For example, an SMTP server
     223| 
     224| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "EHLO command",
  "meaning": "TLS 握手后响应 EHLO 返回的 SMTP 服务扩展列表可以不同于握手前返回的列表",
  "constraint": "",
  "span": 221,
  "action": "be different than",
  "object": "the list returned before the TLS handshake",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "MAY",
  "condition": "received after the TLS handshake",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "EHLO command",
  "action": "",
  "object": "",
  "condition": "received after the TLS handshake",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "received after the TLS handshake",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "be different than",
  "object": "the list returned before the TLS handshake",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S28 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 1.1 Terminology |
| 原始行号 | 第 **72** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      69| 
      70| 1.1 Terminology
      71| 
>>    72|    The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
      73|    "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
      74|    document are to be interpreted as described in [RFC2119].
      75| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "MUST",
  "meaning": "RFC 2119 的关键词之一，本文档中的这些关键词须按 [RFC2119] 中的规定解释。",
  "constraint": "本文档中的关键词须按 [RFC2119] 中的规定解释",
  "span": 72,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "MUST",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "MUST",
  "object": "MUST",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S29 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 220 Ready to start TLS |
| 原始行号 | 第 **107** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     104|    After the client gives the STARTTLS command, the server responds with
     105|    one of the following reply codes:
     106| 
>>   107|    220 Ready to start TLS
     108|    501 Syntax error (no parameters allowed)
     109|    454 TLS not available due to temporary reason
     110| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "220",
  "meaning": "SMTP 响应码 220，表示准备开始 TLS。",
  "constraint": "",
  "span": 107,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "220",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "220",
  "object": "220",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S30 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 501 Syntax error (no parameters allowed) |
| 原始行号 | 第 **108** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     105|    one of the following reply codes:
     106| 
     107|    220 Ready to start TLS
>>   108|    501 Syntax error (no parameters allowed)
     109|    454 TLS not available due to temporary reason
     110| 
     111| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "501",
  "meaning": "SMTP 响应码 501，表示语法错误，即不允许带参数。",
  "constraint": "",
  "span": 108,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "501",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "501",
  "object": "501",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
  "manifest": {
    "key": "39eb817f94771e1c29df32dffd46c222f6d6e4e302c3a0709da9649fff169f08",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |


### 协议 DHCPv4

#### S31 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 2.3 Bit Ordering of Hardware Addresses |
| 原始行号 | 第 **383** 行 |
| 强度 / 极性 | `MUST` / `negative`（原文等级措辞：`MUST NOT`）|
| 条件 / 例外 | `（无）` / `even if it happens to be relaying a BOOTREQUEST between two networks which use different bit orderings` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     380|    defined for that network).
     381| 
     382|    The 'chaddr' field MUST be preserved as it was specified by the BOOTP
>>   383|    client.  A relay agent MUST NOT reverse the bit ordering of the
     384|    'chaddr' field even if it happens to be relaying a BOOTREQUEST
     385|    between two networks which use different bit orderings.
     386| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "relay agent",
  "meaning": "转发 BOOTREQUEST 的中继代理",
  "constraint": "中继代理不得翻转 chaddr 字段的比特顺序",
  "span": 383,
  "action": "reverse the bit ordering of the 'chaddr' field",
  "object": "the bit ordering of the 'chaddr' field",
  "strength": "MUST",
  "polarity": "negative",
  "keyword_raw": "MUST NOT",
  "condition": "",
  "exception": "even if it happens to be relaying a BOOTREQUEST between two networks which use different bit orderings",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "relay agent",
  "subject_span": 383
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "relay agent",
  "action": "reverse the bit ordering of the 'chaddr' field",
  "object": "the bit ordering of the 'chaddr' field",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "negative",
  "condition": null,
  "condition_status": "unknown",
  "exception": "even if it happens to be relaying a BOOTREQUEST between two networks which use different bit orderings",
  "exception_status": "stated",
  "scope": null,
  "action": "reverse the bit ordering of the 'chaddr' field",
  "object": "the bit ordering of the 'chaddr' field",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S32 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 3.5 Vendor information "magic cookie" |
| 原始行号 | 第 **665** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`SHOULD`）|
| 条件 / 例外 | `even if it has no special information to communicate to the BOOTP server using the vend field` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     662| 
     663|    It is RECOMMENDED that a BOOTP client always fill the first four
     664|    octets of the 'vend' (vendor information) field of a BOOTREQUEST with
>>   665|    a four-octet identifier called a "magic cookie."  A BOOTP client
     666|    SHOULD do this even if it has no special information to communicate
     667|    to the BOOTP server using the 'vend' field.  This aids the BOOTP
     668|    server in determining what vendor information format it should use in
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "BOOTP client",
  "meaning": "A BOOTP client SHOULD do this even if it has no special information to communicate to the BOOTP server using the vend field.",
  "constraint": "A BOOTP client SHOULD do this even if it has no special information to communicate to the BOOTP server using the vend field.",
  "span": 665,
  "action": "do this",
  "object": "this (the magic-cookie use in the vend field)",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "even if it has no special information to communicate to the BOOTP server using the vend field",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "BOOTP client",
  "subject_span": 665
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "BOOTP client",
  "action": "do this",
  "object": "this (the magic-cookie use in the vend field)",
  "condition": "even if it has no special information to communicate to the BOOTP server using the vend field",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "SHOULD",
  "polarity": "positive",
  "condition": "even if it has no special information to communicate to the BOOTP server using the vend field",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "do this",
  "object": "this (the magic-cookie use in the vend field)",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S33 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **86** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      83| 
      84|    Since BOOTP clients may not be prepared to receive automatic
      85|    addresses, the decision to allow a DHCP server to return automatic
>>    86|    addresses must be under the control of the system administrator.  If
      87|    a DHCP server supports supplying automatic addresses to BOOTP
      88|    clients, this feature must be configurable, and the feature must
      89|    default off.  Enabling of the feature must be the result of an active
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "system administrator",
  "meaning": "系统管理员；是否允许 DHCP 服务器返回自动地址这一决定必须由该管理员控制。",
  "constraint": "允许 DHCP 服务器返回自动地址的决定必须由系统管理员控制。",
  "span": 86,
  "action": "控制允许 DHCP 服务器返回自动地址的决定",
  "object": "允许 DHCP 服务器返回自动地址的决定",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "system administrator",
  "subject_span": 86
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "system administrator",
  "action": "控制允许 DHCP 服务器返回自动地址的决定",
  "object": "允许 DHCP 服务器返回自动地址的决定",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "控制允许 DHCP 服务器返回自动地址的决定",
  "object": "允许 DHCP 服务器返回自动地址的决定",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S34 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **96** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`cannot`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；关键词无法归一：'cannot' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      93|    not be aware of the DHCP lease mechanism for network address
      94|    assignment.  Thus the DHCP server must assign an infinite lease
      95|    duration to for automatic addresses assigned to BOOTP clients.  Such
>>    96|    network addresses cannot be automatically reassigned by the server.
      97|    The local system administrator may choose to manually release network
      98|    addresses assigned to BOOTP clients.
      99| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "network addresses",
  "meaning": "分配给 BOOTP 客户端的网络地址；服务器不能自动重新分配这些地址。",
  "constraint": "这些网络地址不能被服务器自动重新分配。",
  "span": 96,
  "action": "自动重新分配",
  "object": "此类网络地址",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "cannot",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "server",
  "subject_span": 96
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "network addresses",
  "action": "自动重新分配",
  "object": "此类网络地址",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "negative",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "自动重新分配",
  "object": "此类网络地址",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S35 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **74** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`silently discards`）|
| 条件 / 例外 | `如果未配置为支持 BOOTP 客户端的 DHCP 服务器收到来自 BOOTP 客户端的 BOOTREQUEST 消息` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；关键词无法归一：'silently discards' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      71|    of BOOTP clients by a DHCP server is optional at the discretion of
      72|    the local system administrator.  If a DHCP server that is not
      73|    configured to support BOOTP clients receives a BOOTREQUEST message
>>    74|    from a BOOTP client, that server silently discards the BOOTREQUEST
      75|    message.
      76| 
      77|    If a DHCP server is configured to support BOOTP clients, it may be
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "BOOTREQUEST",
  "meaning": "BOOTP 客户端发出的 BOOTREQUEST 消息；如果 DHCP 服务器未配置为支持 BOOTP 客户端，它会静默丢弃该消息。",
  "constraint": "未配置为支持 BOOTP 客户端的 DHCP 服务器会静默丢弃来自 BOOTP 客户端的 BOOTREQUEST 消息。",
  "span": 74,
  "action": "静默丢弃",
  "object": "BOOTREQUEST 消息",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "silently discards",
  "condition": "如果未配置为支持 BOOTP 客户端的 DHCP 服务器收到来自 BOOTP 客户端的 BOOTREQUEST 消息",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "DHCP server",
  "subject_span": 72
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "BOOTREQUEST",
  "action": "静默丢弃",
  "object": "BOOTREQUEST 消息",
  "condition": "如果未配置为支持 BOOTP 客户端的 DHCP 服务器收到来自 BOOTP 客户端的 BOOTREQUEST 消息",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "negative",
  "condition": "如果未配置为支持 BOOTP 客户端的 DHCP 服务器收到来自 BOOTP 客户端的 BOOTREQUEST 消息",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "静默丢弃",
  "object": "BOOTREQUEST 消息",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S36 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **77** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`may`）|
| 条件 / 例外 | `如果 DHCP 服务器已配置为支持 BOOTP 客户端` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'may' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      74|    from a BOOTP client, that server silently discards the BOOTREQUEST
      75|    message.
      76| 
>>    77|    If a DHCP server is configured to support BOOTP clients, it may be
      78|    configured to supply static addresses, automatic addresses or both.
      79|    Static addresses are those that have been previously assigned by a
      80|    system administrator and are stored in a database available to the
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "DHCP server",
  "meaning": "已配置为支持 BOOTP 客户端的 DHCP 服务器，可被配置为提供静态地址、自动地址或两者兼有。",
  "constraint": "已支持 BOOTP 客户端的 DHCP 服务器可被配置为提供静态地址、自动地址或两者。",
  "span": 77,
  "action": "被配置为提供",
  "object": "静态地址、自动地址或二者",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "may",
  "condition": "如果 DHCP 服务器已配置为支持 BOOTP 客户端",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "DHCP server",
  "subject_span": 77
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "DHCP server",
  "action": "被配置为提供",
  "object": "静态地址、自动地址或二者",
  "condition": "如果 DHCP 服务器已配置为支持 BOOTP 客户端",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "如果 DHCP 服务器已配置为支持 BOOTP 客户端",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "被配置为提供",
  "object": "静态地址、自动地址或二者",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S37 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 4.1 General BOOTP Processing for Relay Agents |
| 原始行号 | 第 **773** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`SHOULD`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section 2.1` ⇒ 定位 **resolved**（章节 `2.1`）|
| L1 验证 | **pending** ｜ 存在跨节引用但无法定位 ⇒ 待审 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     770|          BOOTP specification [1] will show this.  Nevertheless, some
     771|          relay agent implementations incorrectly relay such messages.
     772| 
>>   773|    The consistency checks specified in Section 2.1 SHOULD be performed
     774|    by the relay agent.  BOOTP messages not meeting these consistency
     775|    checks MUST be silently discarded.
     776| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "consistency checks",
  "meaning": "第 2.1 节规定的完整性检查应由中继代理执行。",
  "constraint": "The consistency checks specified in Section 2.1 SHOULD be performed by the relay agent.",
  "span": 773,
  "action": "performed",
  "object": "The consistency checks specified in Section 2.1",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "",
  "exception": "",
  "cross_ref": "Section 2.1",
  "cross_ref_status": "unresolved",
  "normative_subject": "relay agent",
  "subject_span": 774
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "consistency checks",
  "action": "performed",
  "object": "The consistency checks specified in Section 2.1",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "SHOULD",
  "polarity": "positive",
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "performed",
  "object": "The consistency checks specified in Section 2.1",
  "cross_ref": "Section 2.1",
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S38 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 4.1.2 BOOTREPLY Messages |
| 原始行号 | 第 **923** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `If the content of the 'giaddr' field does not match one of the relay agent's directly-connected logical interfaces` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「BOOTREPLY message」（该行：directly-connected logical interfaces, the BOOTREPLY messsage MUST be） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     920|    which the reply must be sent (i.e., the host or router interface
     921|    connected to the same network as the BOOTP client).  If the content
     922|    of the 'giaddr' field does not match one of the relay agent's
>>   923|    directly-connected logical interfaces, the BOOTREPLY messsage MUST be
     924|    silently discarded.
     925| 
     926|    The 'htype', 'hlen', and 'chaddr' fields supply the link-layer
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "BOOTREPLY message",
  "meaning": "relay agent 转发给 client 的 BOOTREPLY 消息",
  "constraint": "若 giaddr 内容不匹配 relay agent 直连的逻辑接口之一，BOOTREPLY 消息必须被静默丢弃",
  "span": 923,
  "action": "discard",
  "object": "BOOTREPLY message",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "If the content of the 'giaddr' field does not match one of the relay agent's directly-connected logical interfaces",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "relay agent",
  "subject_span": 922
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "BOOTREPLY message",
  "action": "discard",
  "object": "BOOTREPLY message",
  "condition": "If the content of the 'giaddr' field does not match one of the relay agent's directly-connected logical interfaces",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If the content of the 'giaddr' field does not match one of the relay agent's directly-connected logical interfaces",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "discard",
  "object": "BOOTREPLY message",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S39 ｜ 发生去重或多证据归并的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 2.1 General BOOTP Processing |
| 原始行号 | 第 **255** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `not meeting these consistency checks` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     252|       o The 'op' (opcode) field of the message must contain either the
     253|         code for a BOOTREQUEST (1) or the code for a BOOTREPLY (2).
     254| 
>>   255|    BOOTP messages not meeting these consistency checks MUST be silently
     256|    discarded.
     257| 
     258| 2.2 Definition of the 'flags' Field
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "BOOTP messages",
  "meaning": "不满足一致性检查的 BOOTP 消息",
  "constraint": "不满足一致性检查的 BOOTP 消息必须被静默丢弃",
  "span": 255,
  "action": "silently discarded",
  "object": "BOOTP messages not meeting these consistency checks",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "not meeting these consistency checks",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "BOOTP messages",
  "action": "silently discarded",
  "object": "BOOTP messages not meeting these consistency checks",
  "condition": "not meeting these consistency checks",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "not meeting these consistency checks",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "silently discarded",
  "object": "BOOTP messages not meeting these consistency checks",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |

#### S40 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **30** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| 归并前 | 槽位 `BOOTP messages | silently discarded | BOOTP messages not meeting these consistency checks | not meeting these consistency checks`，同槽位 **2** 条声明 |
| 归并后 | `method=consensus`；采纳 `1` 条；保留（superseded）`1` 条 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      27| 
      28| 1. Introduction
      29| 
>>    30|    The Dynamic Host Configuration Protocol (DHCP) provides a mechanism
      31|    for transmitting configuration parameters to hosts using the TCP/IP
      32|    protocol suite.  The format of DHCP messages is based on the format
      33|    of BOOTP messages, so that, in certain circumstances, DHCP and BOOTP
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "DHCP",
  "meaning": "动态主机配置协议（DHCP），提供一种使用 TCP/IP 协议套件向主机传输配置参数的机制。",
  "constraint": "",
  "span": 30,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown",
  "normative_subject": "",
  "subject_span": 0
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "DHCP",
  "action": "",
  "object": "",
  "condition": null,
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": null,
  "condition_status": "unknown",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "DHCP",
  "object": "DHCP",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑤ 去重/归并前后**

```json
{
  "slot_key": "BOOTP messages | silently discarded | BOOTP messages not meeting these consistency checks | not meeting these consistency checks",
  "group_size": 2,
  "members": [
    {
      "doc": "rfc1542.txt",
      "span": 255,
      "entity": "BOOTP messages",
      "strength": "MUST",
      "polarity": "positive",
      "keyword_raw": "MUST",
      "evidence": "     252|       o The 'op' (opcode) field of the message must contain either the\n     253|         code for a BOOTREQUEST (1) or the code for a BOOTREPLY (2).\n     254| \n>>   255|    BOOTP messages not meeting these consistency checks MUST be silently\n     256|    discarded.\n     257| \n     258| 2.2 Definition of the 'flags' Field"
    },
    {
      "doc": "rfc1542.txt",
      "span": 1025,
      "entity": "BOOTP messages",
      "strength": "MUST",
      "polarity": "positive",
      "keyword_raw": "MUST",
      "evidence": "    1022|          BOOTP specification [1] will show this.\n    1023| \n    1024|          The consistency checks specified in Section 2.1 SHOULD be\n>>  1025|          performed by the BOOTP server.  BOOTP messages not meeting\n    1026|          these consistency checks MUST be silently discarded.\n    1027| \n    1028| 5.2 Use of the 'secs' field"
    }
  ],
  "resolver": {
    "method": "consensus",
    "value": "[RULE:v1] {\"action\":\"silently discarded\",\"condition\":\"not meeting these consistency checks\",\"condition_status\":\"unknown\",\"cross_ref\":null,\"cross_ref_status\":\"unknown\",\"exception\":null,\"exception_status\":\"unknown\",\"kind\":\"normative_rule\",\"object\":\"BOOTP messages not meeting these consistency checks\",\"polarity\":\"positive\",\"scope\":null,\"strength\":\"MUST\"}",
    "epistemic": "normative_unspecified",
    "authority": "rfc",
    "basis_claim_ids": [
      "c2_c47f2193d366128d"
    ],
    "superseded": [
      "c2_c47f2193d366128d"
    ]
  }
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
  "manifest": {
    "key": "32f033b491bcfc1bf6b3a6163d90caa8226edbf0b382397266b9143ecdc98c29",
    "parser_version": "rfc-parser-v1",
    "schema_version": "rfc-norm-schema-v1",
    "verifier_version": "normative-verifier-v1",
    "model": "deepseek-flash",
    "note": "★ 「缓存命中时产物可复现」可保证；★ 「重新调用同一模型能否逐字节相同」**不一定成立**"
  },
  "extraction_channel": "通道 J（窗口级散文补漏 · 段落粒度）"
}
```

| ★ 人工判定 | 错误原因 | 修改建议 |
|---|---|---|
| ☐ 正确 ☐ 部分正确 ☐ 错误 ☐ 无法判断 |  |  |


## 二、专项统计

### A. 强度未知分析

**总量**：强度未知 **391** 条（已确认强度 331 条）

| 原因分类 | 条数 | 占比 |
|---|---:|---:|
| ★ 证据行未见等级词（★ 不等于原文无强度 ⇒ **待人工重判**） | 341 | 87.2% |
| ★ 证据行含等级词但**模型漏抽**（真缺陷） | 42 | 10.7% |
| 原文为**小写**等级词（★ RFC 8174：普通英语 ⇒ **不构成**规范强度） | 8 | 2.0% |

> ★ **结论**：绝大多数强度未知是「**原文确实没有明确规范强度**」⇒ ⇒ **不是抽取缺陷**
> ⇒ ⇒ ★ **不得**为提高正式入库率而**强行补充强度**

**每类的真实样例（各 3 条）**

**★ 证据行未见等级词（★ 不等于原文无强度 ⇒ **待人工重判**）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 235 | RTSP | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 240 | RTSP | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 247 | RTSP connection | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**★ 证据行含等级词但**模型漏抽**（真缺陷）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 250 | RTSP client | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 255 | RTP | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 310 | proxies | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**原文为**小写**等级词（★ RFC 8174：普通英语 ⇒ **不构成**规范强度）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 1229 | client | `is not required to` | True | 规范强度未定（不得凭推测赋值）；关键词无法归一：'is not required to' |
| rtsp | rfc2326.txt | 1760 | DESCRIBE | `highly recommended` | True | 规范强度未定（不得凭推测赋值）；关键词无法归一：'highly recommended' |
| rtsp | rfc2326.txt | 1761 | minimal clients | `highly recommended` | True | 规范强度未定（不得凭推测赋值）；关键词无法归一：'highly recommended' |

### B. 拒收质量分析

**总拒收**：5 条

| 拒收原因分类 | 条数 | 判定 |
|---|---:|---|
| 按 span **单行**同现未命中（★ 跨行是否真无支持**待人工重判**） | 5 | ⚠ **可能是误拒收**（需人工判断） |

**全部拒收样本（供逐条判断是否误拒收）**

| 协议 | 文件 | 行 | 实体 | 拒收原因 |
|---|---|---:|---|---|
| rtsp | rfc2326.txt | 498 | conference initiation protocol | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「conference initiation protocol」（该行：initiation protocol either provides or can be used to cre |
| sip | rfc3261.txt | 775 | 180 (Ringing) response | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「180 (Ringing) response」（该行：that is, Bob's phone rings.  Bob's SIP phone indicates this in a  |
| smtp | rfc3207.txt | 221 | EHLO command | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「EHLO command」（该行：command received after the TLS handshake MAY be different than the） |
| smtp | rfc4954.txt | 819 | Authentication SMTP service extension | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Authentication SMTP service extension」（该行：IANA updated the registration of the Authenticatio |
| DHCPv4 | rfc1542.txt | 923 | BOOTREPLY message | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「BOOTREPLY message」（该行：directly-connected logical interfaces, the BOOTREPLY messsage MUST be） |

### C. 归并正确性

#### C1 · 同一 Rule Slot 的多声明（真实）

| 协议 | 主体 | 动作 | 对象 | 条件 | 同槽位声明数 | 行号 |
|---|---|---|---|---|---:|---|
| DHCPv4 | BOOTP messages | silently discarded | BOOTP messages not meeting these consistency checks | not meeting these consistency checks | 2 | 255, 1025 |
| DHCPv4 | BOOTPC | set | UDP destination port to BOOTPC (68) | — | 2 | 982, 1079 |

#### C2 · 相反极性声明（同一槽位）

> ★ **本次真实运行中未出现**「同一槽位 + 相反极性」的组合 ⇒ ⇒ 标 **N/A**（**不人工制造**）


## 三、专项核查：跨章节引用定位失败（全部）

| 协议 | 文件 | 行 | 实体 | 引用 | 原文 |
|---|---|---:|---|---|---|
| rtsp | rfc2326.txt | 1656 | OPTIONS | `[H9.2]` | >>  1656|    The behavior is equivalent to that described in [H9.2]. An OPTIONS |
| sip | rfc3261.txt | 1862 | CRLF | `[H4.1]` | >>  1862|    Implementations processing SIP messages over stream-oriented |
| smtp | rfc4954.txt | 147 | initial-response | `Section 4 of [BASE64]` | >>   147|           initial-response: An optional initial client response.  If |
| smtp | rfc4954.txt | 202 | server | `Section 5.1 of [SASL]` | >>   202|           an initial client response, the server MUST proceed as defined |
| smtp | rfc4954.txt | 211 | client | `Section 5.1 of [SASL]` | >>   211|           the client MUST NOT use the initial response parameter (and |
| smtp | rfc4954.txt | 662 | Received: | `Section 4.4 of [SMTP]` | >>   662|    "Received:" header field at the beginning of the message content. |

## 四、专项核查：代词主体隔离（全部）

> （本次无）

## 五、运行配置与可追溯性

| 协议 | 缓存文件 | 缓存键（前 16） | 模型 | 解析器版本 | 校验器版本 |
|---|---|---|---|---|---|
| rtsp | `derived/cache/source_blocks/rtsp.prose.json` | `f7d2ac2b993f3836` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |
| sip | `derived/cache/source_blocks/sip.prose.json` | `35792997d2f6578c` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |
| smtp | `derived/cache/source_blocks/smtp.prose.json` | `39eb817f94771e1c` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |
| DHCPv4 | `derived/cache/source_blocks/DHCPv4.prose.json` | `32f033b491bcfc1b` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |

> ★ **复现**：同缓存键 ⇒ 命中缓存 ⇒ 不调 LLM ⇒ 逐字节可复现
> ⇒ ⇒ 本包所有样本均可回溯到上表的缓存文件与缓存键

## 六、人工判定汇总（★ 待填）

| 样本 | 协议 | 类别 | 最终状态 | 人工判定 | 错误原因 / 修改建议 |
|---|---|---|---|---|---|
| S01 | rtsp | 含条件或例外的规则 | 确认 |  |  |
| S02 | rtsp | 已确认强度的规范规则 | 待审 |  |  |
| S03 | rtsp | 已确认强度的规范规则 | 待审 |  |  |
| S04 | rtsp | 强度未知（被隔离）候选 | 待审 |  |  |
| S05 | rtsp | 强度未知（被隔离）候选 | 待审 |  |  |
| S06 | rtsp | 含条件或例外的规则 | 待审 |  |  |
| S07 | rtsp | 含条件或例外的规则 | 待审 |  |  |
| S08 | rtsp | 跨章节引用规则 | 确认 |  |  |
| S09 | rtsp | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S10 | rtsp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S11 | sip | 含条件或例外的规则 | 确认 |  |  |
| S12 | sip | 已确认强度的规范规则 | 待审 |  |  |
| S13 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S14 | sip | 强度未知（被隔离）候选 | 待审 |  |  |
| S15 | sip | 强度未知（被隔离）候选 | 待审 |  |  |
| S16 | sip | 含条件或例外的规则 | 待审 |  |  |
| S17 | sip | 含条件或例外的规则 | 确认 |  |  |
| S18 | sip | 跨章节引用规则 | 待审 |  |  |
| S19 | sip | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S20 | sip | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S21 | smtp | 含条件或例外的规则 | 待审 |  |  |
| S22 | smtp | 含条件或例外的规则 | 确认 |  |  |
| S23 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S24 | smtp | 含条件或例外的规则 | 确认 |  |  |
| S25 | smtp | 含条件或例外的规则 | 确认 |  |  |
| S26 | smtp | 跨章节引用规则 | 待审 |  |  |
| S27 | smtp | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S28 | smtp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S29 | smtp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S30 | smtp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S31 | DHCPv4 | 含条件或例外的规则 | 确认 |  |  |
| S32 | DHCPv4 | 含条件或例外的规则 | 确认 |  |  |
| S33 | DHCPv4 | 已确认强度的规范规则 | 待审 |  |  |
| S34 | DHCPv4 | 强度未知（被隔离）候选 | 待审 |  |  |
| S35 | DHCPv4 | 含条件或例外的规则 | 待审 |  |  |
| S36 | DHCPv4 | 含条件或例外的规则 | 待审 |  |  |
| S37 | DHCPv4 | 跨章节引用规则 | 待审 |  |  |
| S38 | DHCPv4 | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S39 | DHCPv4 | 发生去重或多证据归并的规则 | 确认 |  |  |
| S40 | DHCPv4 | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
