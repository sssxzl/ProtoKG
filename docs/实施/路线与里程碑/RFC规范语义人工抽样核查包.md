# RFC 规范语义 · 人工抽样核查包

> ★ **目的**：★ **独立核实真实 RFC 抽取内容的准确性**，并发现**误拒收 / 误隔离 / 错误归并**
> ★ **数据来源**：deepseek-flash 的**真实运行缓存**（`derived/cache/source_blocks/<协议>.prose.json`）
> ⇒ ⇒ **不使用 mock、不使用手工构造的 payload**
> ★ **本包不含任何「机制验收通过 ⇒ 语义正确」的结论** ⇒ ⇒ **结论由人工填写**
> ★ 生成时间：2026-11-13

## 〇、抽样范围与构成

| 协议 | 真实条目总数 | 抽样数 |
|---|---:|---:|
| rtsp | 224 | 10 |
| sip | 205 | 10 |
| smtp | 177 | 10 |
| DHCPv4 | 188 | 10 |
| **合计** | **794** | **40** |

**每协议的抽样构成**（按类别）：

| 协议 | 已确认强度的规范规则 | 强度未知（被隔离）候选 | 含条件或例外的规则 | 跨章节引用规则 | 被 L1/L2 拒收的候选 | 发生去重或多证据归并的规则 |
|---|---:|---:|---:|---:|---:|---:|
| rtsp | 3 | 2 | 2 | 1 | 1 | 1 |
| sip | 3 | 2 | 2 | 1 | 1 | 1 |
| smtp | 3 | 2 | 2 | 1 | 1 | 1 |
| DHCPv4 | 3 | 2 | 2 | 1 | 1 | 1 |

## 一、逐条样本（★ 人工审阅区）

> ★ **判定栏**：`正确 / 部分正确 / 错误 / 无法判断` ⇒ ★ 请在**「人工判定」**列填写，并在**错误原因**/**修改建议**列写明


### 协议 rtsp

#### S01 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.4 Protocol Properties |
| 原始行号 | 第 **518** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

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
  "meaning": "The presentation description must contain at least one RTSP URI.",
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
  "cross_ref_status": "unknown"
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
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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

#### S02 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 3.3 Conference Identifiers |
| 原始行号 | 第 **858** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     855| 
     856|    Conference identifiers are opaque to RTSP and are encoded using
     857|    standard URI encoding methods (i.e., LWS is escaped with %). They can
>>   858|    contain any octet value. The conference identifier MUST be globally
     859|    unique. For H.323, the conferenceID value is to be used.
     860| 
     861|  conference-id =   1*xchar
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "conference identifier",
  "meaning": "The conference identifier must be globally unique.",
  "constraint": "The conference identifier MUST be globally unique.",
  "span": 858,
  "action": "be globally unique",
  "object": "conference identifier",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "conference identifier",
  "action": "be globally unique",
  "object": "conference identifier",
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
  "action": "be globally unique",
  "object": "conference identifier",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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

#### S03 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 3.4 Session Identifiers |
| 原始行号 | 第 **874** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     871| 3.4 Session Identifiers
     872| 
     873|    Session identifiers are opaque strings of arbitrary length. Linear
>>   874|    white space must be URL-escaped. A session identifier MUST be chosen
     875|    randomly and MUST be at least eight octets long to make guessing it
     876|    more difficult. (See Section 16.)
     877| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "white space",
  "meaning": "线性空白必须做 URL 转义。",
  "constraint": "Linear white space must be URL-escaped",
  "span": 874,
  "action": "URL-escaped",
  "object": "Linear white space",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "white space",
  "action": "URL-escaped",
  "object": "Linear white space",
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
  "action": "URL-escaped",
  "object": "Linear white space",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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
| 章节 | 1.1 Purpose |
| 原始行号 | 第 **238** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     235|    The Real-Time Streaming Protocol (RTSP) establishes and controls
     236|    either a single or several time-synchronized streams of continuous
     237|    media such as audio and video. It does not typically deliver the
>>   238|    continuous streams itself, although interleaving of the continuous
     239|    media stream with the control stream is possible (see Section 10.12).
     240|    In other words, RTSP acts as a "network remote control" for
     241|    multimedia servers.
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "interleaving",
  "meaning": "Interleaving of the continuous media stream with the control stream is possible.",
  "constraint": "",
  "span": 238,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "interleaving",
  "action": "interleaving",
  "object": "interleaving",
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
  "action": "interleaving",
  "object": "interleaving",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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
| 章节 | 1.1 Purpose |
| 原始行号 | 第 **247** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     244|    description. This memorandum does not define a format for a
     245|    presentation description.
     246| 
>>   247|    There is no notion of an RTSP connection; instead, a server maintains
     248|    a session labeled by an identifier. An RTSP session is in no way tied
     249|    to a transport-level connection such as a TCP connection. During an
     250|    RTSP session, an RTSP client may open and close many reliable
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "RTSP connection",
  "meaning": "There is no notion of an RTSP connection.",
  "constraint": "",
  "span": 247,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "RTSP connection",
  "action": "RTSP connection",
  "object": "RTSP connection",
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
  "action": "RTSP connection",
  "object": "RTSP connection",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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
| 章节 | 1.1 Purpose |
| 原始行号 | 第 **294** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `If the presentation is to be sent only to the client via unicast` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     291|           some other method. If the presentation is being multicast, the
     292|           presentation description contains the multicast addresses and
     293|           ports to be used for the continuous media. If the presentation
>>   294|           is to be sent only to the client via unicast, the client
     295|           provides the destination for security reasons.
     296| 
     297|    Invitation of a media server to a conference:
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "client",
  "meaning": "当呈现仅以单播方式发送给客户端时，客户端出于安全原因提供目的地址。",
  "constraint": "",
  "span": 294,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "If the presentation is to be sent only to the client via unicast",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "client",
  "action": "client",
  "object": "client",
  "condition": "If the presentation is to be sent only to the client via unicast",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": "If the presentation is to be sent only to the client via unicast",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "client",
  "object": "client",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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
| 章节 | 1.1 Purpose |
| 原始行号 | 第 **307** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `Particularly for live presentations` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     304| 
     305|    Addition of media to an existing presentation:
     306|           Particularly for live presentations, it is useful if the
>>   307|           server can tell the client about additional media becoming
     308|           available.
     309| 
     310|    RTSP requests may be handled by proxies, tunnels and caches as in
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "server",
  "meaning": "特别是在直播呈现中，服务器能够告知客户端有额外媒体变为可用是有用的。",
  "constraint": "",
  "span": 307,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "Particularly for live presentations",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "server",
  "action": "server",
  "object": "server",
  "condition": "Particularly for live presentations",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": null,
  "condition": "Particularly for live presentations",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "server",
  "object": "server",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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

#### S08 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.5 Extending RTSP |
| 原始行号 | 第 **582** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`SHOULD`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section 12` ⇒ 定位 **resolved**（章节 `12`）|
| L1 验证 | **pending** ｜ 存在跨节引用但无法定位 ⇒ 待审 |

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
  "meaning": "服务器应当实现第 12 节描述的所有头字段",
  "constraint": "A server SHOULD implement all header fields described in Section 12",
  "span": 582,
  "action": "implement",
  "object": "all header fields described in Section 12",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "",
  "exception": "",
  "cross_ref": "Section 12",
  "cross_ref_status": "unresolved"
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
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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
| 章节 | 1.7 RTSP States |
| 原始行号 | 第 **683** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section A` ⇒ 定位 **unresolved**（章节 `None`）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：span 所在行**不含**实体名「state transitions」（该行：transitions are described in Section A.） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     680|    controlled by RTSP requests issued sequentially on different TCP
     681|    connections. Therefore, the server needs to maintain "session state"
     682|    to be able to correlate RTSP requests with a stream. The state
>>   683|    transitions are described in Section A.
     684| 
     685|    Many methods in RTSP do not contribute to state. However, the
     686|    following play a central role in defining the allocation and usage of
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "state transitions",
  "meaning": "状态转换在 Section A 中描述。",
  "constraint": "",
  "span": 683,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "Section A",
  "cross_ref_status": "unresolved"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "state transitions",
  "action": "state transitions",
  "object": "state transitions",
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
  "action": "state transitions",
  "object": "state transitions",
  "cross_ref": "Section A",
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/rtsp.prose.json",
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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

#### S10 ｜ 发生去重或多证据归并的规则 ｜ 最终状态：**待审**

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
  "meaning": "RTSP establishes and controls either a single or several time-synchronized streams of continuous media such as audio and video.",
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
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "RTSP",
  "action": "RTSP",
  "object": "RTSP",
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
  "cache_key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
  "manifest": {
    "key": "1709ccbd179a5c40eaea5902deadfffe6c74cd94588d3c0dfc8c18a39020cd32",
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

#### S11 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 6 Definitions |
| 原始行号 | 第 **1113** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1110|          user agent server (UAS).  In order to determine how the request
    1111|          should be answered, it acts as a user agent client (UAC) and
    1112|          generates requests.  Unlike a proxy server, it maintains dialog
>>  1113|          state and must participate in all requests sent on the dialogs
    1114|          it has established.  Since it is a concatenation of a UAC and
    1115|          UAS, no explicit definitions are needed for its behavior.
    1116| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "dialogs",
  "meaning": "B2BUA 必须参与它已建立的 dialog 上发送的所有请求",
  "constraint": "B2BUA 必须参与它已建立的 dialog 上发送的所有请求",
  "span": 1113,
  "action": "participate in",
  "object": "all requests sent on the dialogs it has established",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "dialogs",
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
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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

#### S12 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

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
  "meaning": "The start-line, each message-header line, and the empty line MUST be terminated by a carriage-return line-feed sequence (CRLF).",
  "constraint": "MUST be terminated by a carriage-return line-feed sequence (CRLF)",
  "span": 1480,
  "action": "terminated by",
  "object": "carriage-return line-feed sequence (CRLF)",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "start-line",
  "action": "terminated by",
  "object": "carriage-return line-feed sequence (CRLF)",
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
  "action": "terminated by",
  "object": "carriage-return line-feed sequence (CRLF)",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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
| 章节 | 7.1 Requests |
| 原始行号 | 第 **1538** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1535|            numbers.  To be compliant with this specification,
    1536|            applications sending SIP messages MUST include a SIP-Version
    1537|            of "SIP/2.0".  The SIP-Version string is case-insensitive,
>>  1538|            but implementations MUST send upper-case.
    1539| 
    1540|            Unlike HTTP/1.1, SIP treats the version number as a literal
    1541|            string.  In practice, this should make no difference.
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "implementations",
  "meaning": "实现必须发送大写的 SIP-Version。",
  "constraint": "implementations MUST send upper-case.",
  "span": 1538,
  "action": "send",
  "object": "upper-case",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "implementations",
  "action": "send",
  "object": "upper-case",
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
  "action": "send",
  "object": "upper-case",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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
| 章节 | 2 Overview of SIP Functionality |
| 原始行号 | 第 **511** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     508| RFC 3261            SIP: Session Initiation Protocol           June 2002
     509| 
     510| 
>>   511|    Gateway Control Protocol (MEGACO) (RFC 3015 [30]) for controlling
     512|    gateways to the Public Switched Telephone Network (PSTN), and the
     513|    Session Description Protocol (SDP) (RFC 2327 [1]) for describing
     514|    multimedia sessions.  Therefore, SIP should be used in conjunction
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "MEGACO",
  "meaning": "Gateway Control Protocol used for controlling gateways to the PSTN.",
  "constraint": "",
  "span": 511,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "MEGACO",
  "action": "MEGACO",
  "object": "MEGACO",
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
  "action": "MEGACO",
  "object": "MEGACO",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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
| 章节 | 2 Overview of SIP Functionality |
| 原始行号 | 第 **526** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     523|    SDP, for instance, the endpoints can agree on the parameters of a
     524|    session.  If the same primitive is used to deliver a photo of the
     525|    caller as well as the session description, a "caller ID" service can
>>   526|    be easily implemented.  As this example shows, a single primitive is
     527|    typically used to provide several different services.
     528| 
     529|    SIP does not offer conference control services such as floor control
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "primitive",
  "meaning": "A single primitive is typically used to provide several different services.",
  "constraint": "",
  "span": 526,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "primitive",
  "action": "primitive",
  "object": "primitive",
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
  "action": "primitive",
  "object": "primitive",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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

#### S16 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

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
  "meaning": "The empty line MUST be present even if the message-body is not.",
  "constraint": "MUST be present even if the message-body is not",
  "span": 1482,
  "action": "be present",
  "object": "empty line",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "even if the message-body is not",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
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
  "object": "empty line",
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
  "object": "empty line",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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
| 原始行号 | 第 **1507** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`may`）|
| 条件 / 例外 | `documented in standards track RFCs` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1504|            registering contact information, INVITE, ACK, and CANCEL for
    1505|            setting up sessions, BYE for terminating sessions, and
    1506|            OPTIONS for querying servers about their capabilities.  SIP
>>  1507|            extensions, documented in standards track RFCs, may define
    1508|            additional methods.
    1509| 
    1510| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "extensions",
  "meaning": "记录在标准轨道 RFC 中的 SIP 扩展可以定义额外的方法。",
  "constraint": "",
  "span": 1507,
  "action": "define",
  "object": "additional methods",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "may",
  "condition": "documented in standards track RFCs",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "extensions",
  "action": "define",
  "object": "additional methods",
  "condition": "documented in standards track RFCs",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "documented in standards track RFCs",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "define",
  "object": "additional methods",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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
| 条件 / 例外 | `if and only if the entire field-value for that header field is defined as a comma-separated list` / `WWW-Authenticate, Authorization, Proxy-Authenticate, and Proxy-Authorization header fields` |
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
  "meaning": "Multiple header field rows with the same field-name MAY be present in a message if and only if the entire field-value for that header field is defined as a comma-separated list.",
  "constraint": "Multiple header field rows with the same field-name MAY be present in a message if and only if the entire field-value for that header field is defined as a comma-separated list.",
  "span": 1670,
  "action": "be present",
  "object": "in a message",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "MAY",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list",
  "exception": "WWW-Authenticate, Authorization, Proxy-Authenticate, and Proxy-Authorization header fields",
  "cross_ref": "Section 7.3",
  "cross_ref_status": "unresolved"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "header field rows",
  "action": "be present",
  "object": "in a message",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list",
  "condition_status": "stated",
  "exception": "WWW-Authenticate, Authorization, Proxy-Authenticate, and Proxy-Authorization header fields",
  "exception_status": "stated",
  "scope": null,
  "action": "be present",
  "object": "in a message",
  "cross_ref": "Section 7.3",
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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
| 章节 | 5 Structure of the Protocol |
| 原始行号 | 第 **1072** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：span 所在行**不含**实体名「dialog」（该行：peer-to-peer SIP relationship between two user agents that persists） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1069| 
    1070| 
    1071|    Certain other requests are sent within a dialog.  A dialog is a
>>  1072|    peer-to-peer SIP relationship between two user agents that persists
    1073|    for some time.  The dialog facilitates sequencing of messages and
    1074|    proper routing of requests between the user agents.  The INVITE
    1075|    method is the only way defined in this specification to establish a
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "dialog",
  "meaning": "dialog 是两个用户代理之间点对点的 SIP 关系，并会持续一段时间",
  "constraint": "",
  "span": 1072,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "dialog",
  "action": "dialog",
  "object": "dialog",
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
  "action": "dialog",
  "object": "dialog",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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

#### S20 ｜ 发生去重或多证据归并的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 1 Introduction |
| 原始行号 | 第 **446** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     443|    different media - sometimes simultaneously.  Numerous protocols have
     444|    been authored that carry various forms of real-time multimedia
     445|    session data such as voice, video, or text messages.  The Session
>>   446|    Initiation Protocol (SIP) works in concert with these protocols by
     447| 
     448| 
     449| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "SIP",
  "meaning": "SIP works in concert with protocols that carry real-time multimedia session data such as voice, video, or text messages.",
  "constraint": "",
  "span": 446,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "SIP",
  "action": "SIP",
  "object": "SIP",
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
  "action": "SIP",
  "object": "SIP",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/sip.prose.json",
  "cache_key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
  "manifest": {
    "key": "0dbd6a25bf72ddc41ebb56fe3f9deed124d3c813aba8d2c627e327bd92b62c66",
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

#### S21 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

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
  "meaning": "The client and server MUST know whether a TLS session is active.",
  "constraint": "Both the client and the server MUST know if there is a TLS session active.",
  "span": 235,
  "action": "know",
  "object": "if there is a TLS session active",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
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
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S22 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 4.3 STARTTLS on the Submission Port |
| 原始行号 | 第 **292** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     289|    SMTP client, it does not mean that the mail from the SMTP client was
     290|    authenticated by the SMTP client when the client received it.
     291| 
>>   292|    Both the SMTP client and server must check the result of the TLS
     293|    negotiation to see whether an acceptable degree of authentication and
     294|    privacy was achieved.  Ignoring this step completely invalidates
     295|    using TLS for security.  The decision about whether acceptable
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "SMTP client",
  "meaning": "The SMTP client and server must check the result of TLS negotiation to see whether an acceptable degree of authentication and privacy was achieved.",
  "constraint": "Both the SMTP client and server must check the result of the TLS negotiation to see whether an acceptable degree of authentication and privacy was achieved.",
  "span": 292,
  "action": "check",
  "object": "the result of the TLS negotiation",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "SMTP client",
  "action": "check",
  "object": "the result of the TLS negotiation",
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
  "action": "check",
  "object": "the result of the TLS negotiation",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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
| 章节 | 4.3 STARTTLS on the Submission Port |
| 原始行号 | 第 **313** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     310|    to allow the server to announce its STARTTLS capability, but to alter
     311|    the client's request to start TLS and the server's response.  In
     312|    order to defend against such attacks both clients and servers MUST be
>>   313|    able to be configured to require successful TLS negotiation of an
     314|    appropriate cipher suite for selected hosts before messages can be
     315|    successfully transferred.  The additional option of using TLS when
     316|    possible SHOULD also be provided.  An implementation MAY provide the
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "TLS negotiation",
  "meaning": "为防御此类攻击，客户端与服务器必须能够被配置为：在消息成功传输前，要求对选定主机完成适当密码套件的成功 TLS 协商",
  "constraint": "both clients and servers MUST be able to be configured to require successful TLS negotiation of an appropriate cipher suite for selected hosts before messages can be successfully transferred",
  "span": 313,
  "action": "be able to be configured to require",
  "object": "successful TLS negotiation of an appropriate cipher suite for selected hosts before messages can be successfully transferred",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "TLS negotiation",
  "action": "be able to be configured to require",
  "object": "successful TLS negotiation of an appropriate cipher suite for selected hosts before messages can be successfully transferred",
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
  "action": "be able to be configured to require",
  "object": "successful TLS negotiation of an appropriate cipher suite for selected hosts before messages can be successfully transferred",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S24 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

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
  "meaning": "220 响应表示已准备好开始 TLS。",
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
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "220",
  "action": "220",
  "object": "220",
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
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S25 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

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
  "meaning": "501 响应表示语法错误，且不允许携带参数。",
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
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "501",
  "action": "501",
  "object": "501",
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
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S26 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **119** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `If the client receives the 454 response` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

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
  "meaning": "如果客户端收到 454 响应，客户端必须决定是否继续 SMTP 会话。",
  "constraint": "客户端必须决定是否继续 SMTP 会话。",
  "span": 119,
  "action": "决定是否继续",
  "object": "SMTP 会话",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "If the client receives the 454 response",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "454",
  "action": "决定是否继续",
  "object": "SMTP 会话",
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
  "action": "决定是否继续",
  "object": "SMTP 会话",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S27 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **129** 行 |
| 强度 / 极性 | `MUST` / `negative`（原文等级措辞：`MUST NOT`）|
| 条件 / 例外 | `in order to deliver mail locally` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     126|    TLS encryption, whether to wait and try again later, or whether to
     127|    give up and notify the sender of the error.
     128| 
>>   129|    A publicly-referenced SMTP server MUST NOT require use of the
     130|    STARTTLS extension in order to deliver mail locally.  This rule
     131|    prevents the STARTTLS extension from damaging the interoperability of
     132|    the Internet's SMTP infrastructure.  A publicly-referenced SMTP
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "publicly-referenced SMTP server",
  "meaning": "面向公众引用的 SMTP 服务器不得要求使用 STARTTLS 扩展才能在本地投递邮件。",
  "constraint": "不得要求使用 STARTTLS 扩展才能在本地投递邮件。",
  "span": 129,
  "action": "要求使用",
  "object": "STARTTLS 扩展以便在本地投递邮件",
  "strength": "MUST",
  "polarity": "negative",
  "keyword_raw": "MUST NOT",
  "condition": "in order to deliver mail locally",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "publicly-referenced SMTP server",
  "action": "要求使用",
  "object": "STARTTLS 扩展以便在本地投递邮件",
  "condition": "in order to deliver mail locally",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "negative",
  "condition": "in order to deliver mail locally",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "要求使用",
  "object": "STARTTLS 扩展以便在本地投递邮件",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S28 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc4954.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **147** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `If present` / `or contain a single character "="` |
| 作用域 | `（无）` |
| 跨章节引用 | `Section 4 of [BASE64]` ⇒ 定位 **resolved**（章节 `4`）|
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
  "meaning": "可选的客户端初始响应；若存在，则必须按 [BASE64] 第 4 节所述编码，或包含单个字符 \"=\"。",
  "constraint": "若存在，该响应 MUST 按 [BASE64] Section 4 编码，或包含单个字符 \"=\"",
  "span": 147,
  "action": "encoded",
  "object": "this response",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "If present",
  "exception": "or contain a single character \"=\"",
  "cross_ref": "Section 4 of [BASE64]",
  "cross_ref_status": "unresolved"
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
  "exception": "or contain a single character \"=\"",
  "exception_status": "stated",
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
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S29 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 4.3 STARTTLS on the Submission Port |
| 原始行号 | 第 **299** 行 |
| 强度 / 极性 | `SHOULD` / `positive`（原文等级措辞：`should`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：span 所在行**不含**实体名「TLS negotiation」（该行：The SMTP client and server should note carefully the result of the） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     296|    authentication or privacy was achieved is made locally, is
     297|    implementation-dependent, and is beyond the scope of this document.
     298| 
>>   299|    The SMTP client and server should note carefully the result of the
     300|    TLS negotiation.  If the negotiation results in no privacy, or if it
     301|    results in privacy using algorithms or key lengths that are deemed
     302|    not strong enough, or if the authentication is not good enough for
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "TLS negotiation",
  "meaning": "SMTP 客户端与服务器应当仔细注意 TLS 协商的结果",
  "constraint": "The SMTP client and server should note carefully the result of the TLS negotiation.",
  "span": 299,
  "action": "note carefully",
  "object": "the result of the TLS negotiation",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "should",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "TLS negotiation",
  "action": "note carefully",
  "object": "the result of the TLS negotiation",
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
  "action": "note carefully",
  "object": "the result of the TLS negotiation",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/smtp.prose.json",
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S30 ｜ 发生去重或多证据归并的规则 ｜ 最终状态：**待审**

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
  "meaning": "关键词 MUST 应按 RFC2119 中的描述解释。",
  "constraint": "",
  "span": 72,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "MUST",
  "action": "MUST",
  "object": "MUST",
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
  "cache_key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
  "manifest": {
    "key": "9b2395036ca84d0953de16034216422ed34e04e0ac83f7d920550f65e8ec9139",
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

#### S31 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **86** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

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
  "meaning": "The decision to allow a DHCP server to return automatic addresses must be under the control of the system administrator.",
  "constraint": "the decision to allow a DHCP server to return automatic addresses must be under the control of the system administrator",
  "span": 86,
  "action": "be under the control of",
  "object": "the system administrator",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "system administrator",
  "action": "be under the control of",
  "object": "the system administrator",
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
  "action": "be under the control of",
  "object": "the system administrator",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S32 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **89** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      86|    addresses must be under the control of the system administrator.  If
      87|    a DHCP server supports supplying automatic addresses to BOOTP
      88|    clients, this feature must be configurable, and the feature must
>>    89|    default off.  Enabling of the feature must be the result of an active
      90|    decision by the system administrator.
      91| 
      92|    If a DHCP server returns a automatic address, the BOOTP client will
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "Enabling of the feature",
  "meaning": "Enabling of the feature must be the result of an active decision by the system administrator.",
  "constraint": "Enabling of the feature must be the result of an active decision by the system administrator",
  "span": 89,
  "action": "be the result of an active decision by",
  "object": "the system administrator",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "Enabling of the feature",
  "action": "be the result of an active decision by",
  "object": "the system administrator",
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
  "action": "be the result of an active decision by",
  "object": "the system administrator",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S33 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **102** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      99| 
     100|    A DHCP server that supports BOOTP clients MUST interact with BOOTP
     101|    clients according to the BOOTP protocol.  The server MUST formulate a
>>   102|    BOOTP BOOTREPLY message rather than a DHCP DHCPOFFER message (i.e.,
     103|    the server MUST NOT include the 'DHCP message type' option and MUST
     104|    NOT exceed the size limit for BOOTREPLY messages).  The server marks
     105|    a binding for a BOOTP client as BOUND after sending the BOOTP
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "BOOTP BOOTREPLY message",
  "meaning": "服务器必须构造 BOOTP BOOTREPLY 消息而不是 DHCP DHCPOFFER 消息。",
  "constraint": "服务器 MUST 构造 BOOTP BOOTREPLY 消息而非 DHCP DHCPOFFER 消息",
  "span": 102,
  "action": "formulate",
  "object": "BOOTP BOOTREPLY message rather than a DHCP DHCPOFFER message",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "BOOTP BOOTREPLY message",
  "action": "formulate",
  "object": "BOOTP BOOTREPLY message rather than a DHCP DHCPOFFER message",
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
  "action": "formulate",
  "object": "BOOTP BOOTREPLY message rather than a DHCP DHCPOFFER message",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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
| 原始行号 | 第 **30** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

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
  "meaning": "DHCP provides a mechanism for transmitting configuration parameters to hosts using the TCP/IP protocol suite.",
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
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "DHCP",
  "action": "DHCP",
  "object": "DHCP",
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

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S35 ｜ 强度未知（被隔离）候选 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **34** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      31|    for transmitting configuration parameters to hosts using the TCP/IP
      32|    protocol suite.  The format of DHCP messages is based on the format
      33|    of BOOTP messages, so that, in certain circumstances, DHCP and BOOTP
>>    34|    participants may exchange messages.  This document specifies the ways
      35|    in which DHCP and BOOTP participants may interoperate.
      36| 
      37|    DHCP introduces a small change in terminology intended to clarify the
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "participants",
  "meaning": "DHCP and BOOTP participants may exchange messages in certain circumstances.",
  "constraint": "",
  "span": 34,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "participants",
  "action": "participants",
  "object": "participants",
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
  "action": "participants",
  "object": "participants",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S36 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **77** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`may`）|
| 条件 / 例外 | `If a DHCP server is configured to support BOOTP clients` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

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
  "meaning": "If a DHCP server is configured to support BOOTP clients, it may be configured to supply static addresses, automatic addresses or both.",
  "constraint": "may be configured to supply static addresses, automatic addresses or both",
  "span": 77,
  "action": "be configured to supply",
  "object": "static addresses, automatic addresses or both",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "may",
  "condition": "If a DHCP server is configured to support BOOTP clients",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "DHCP server",
  "action": "be configured to supply",
  "object": "static addresses, automatic addresses or both",
  "condition": "If a DHCP server is configured to support BOOTP clients",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "If a DHCP server is configured to support BOOTP clients",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "be configured to supply",
  "object": "static addresses, automatic addresses or both",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S37 ｜ 含条件或例外的规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **88** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `If a DHCP server supports supplying automatic addresses to BOOTP clients` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      85|    addresses, the decision to allow a DHCP server to return automatic
      86|    addresses must be under the control of the system administrator.  If
      87|    a DHCP server supports supplying automatic addresses to BOOTP
>>    88|    clients, this feature must be configurable, and the feature must
      89|    default off.  Enabling of the feature must be the result of an active
      90|    decision by the system administrator.
      91| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "feature",
  "meaning": "If a DHCP server supports supplying automatic addresses to BOOTP clients, this feature must be configurable.",
  "constraint": "this feature must be configurable",
  "span": 88,
  "action": "be configurable",
  "object": "this feature",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "If a DHCP server supports supplying automatic addresses to BOOTP clients",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "feature",
  "action": "be configurable",
  "object": "this feature",
  "condition": "If a DHCP server supports supplying automatic addresses to BOOTP clients",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If a DHCP server supports supplying automatic addresses to BOOTP clients",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "be configurable",
  "object": "this feature",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S38 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 4.1.1 BOOTREQUEST Messages |
| 原始行号 | 第 **816** 行 |
| 强度 / 极性 | `MUST` / `negative`（原文等级措辞：`MUST NOT`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | `[1] (Section 8, sixth paragraph)` ⇒ 定位 **resolved**（章节 `1`）|
| L1 验证 | **pending** ｜ 存在跨节引用但无法定位 ⇒ 待审 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     813|    agent SHOULD choose one IP address associated with that interface and
     814|    use it consistently for all BOOTP messages it relays.  If the
     815|    'giaddr' field contains some non-zero value, the 'giaddr' field MUST
>>   816|    NOT be modified.  The relay agent MUST NOT, under any circumstances,
     817|    fill the 'giaddr' field with a broadcast address as is suggested in
     818|    [1] (Section 8, sixth paragraph).
     819| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "relay agent",
  "meaning": "中继代理在任何情况下都不得用广播地址填充 'giaddr' 字段。",
  "constraint": "不得用广播地址填充 giaddr",
  "span": 816,
  "action": "fill",
  "object": "the 'giaddr' field with a broadcast address",
  "strength": "MUST",
  "polarity": "negative",
  "keyword_raw": "MUST NOT",
  "condition": "",
  "exception": "",
  "cross_ref": "[1] (Section 8, sixth paragraph)",
  "cross_ref_status": "unresolved"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "relay agent",
  "action": "fill",
  "object": "the 'giaddr' field with a broadcast address",
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
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "fill",
  "object": "the 'giaddr' field with a broadcast address",
  "cross_ref": "[1] (Section 8, sixth paragraph)",
  "cross_ref_status": "unresolved"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S39 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 3.3 Use of the 'ciaddr' and 'yiaddr' fields |
| 原始行号 | 第 **594** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：span 所在行**不含**实体名「ciaddr」（该行：The last interpretation is incorrect as it may prevent the） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     591|          never used that address before or is not currently using that
     592|          address.
     593| 
>>   594|          The last interpretation is incorrect as it may prevent the
     595|          BOOTREPLY from reaching the client.  The server will usually
     596|          unicast the reply to the address given in 'ciaddr' but the
     597|          client may not be listening on that address yet, or the client
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "ciaddr",
  "meaning": "把 'ciaddr' 用于表达从未使用或当前未使用的期望地址的解释是错误的，可能使 BOOTREPLY 无法到达客户端；服务器通常将回复单播到 'ciaddr' 给出的地址",
  "constraint": "",
  "span": 594,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "ciaddr",
  "action": "ciaddr",
  "object": "ciaddr",
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
  "action": "ciaddr",
  "object": "ciaddr",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

#### S40 ｜ 发生去重或多证据归并的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **32** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| 归并前 | 槽位 `DHCP messages | DHCP messages | DHCP messages | None`，同槽位 **2** 条声明 |
| 归并后 | `method=consensus`；采纳 `1` 条；保留（superseded）`1` 条 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      29| 
      30|    The Dynamic Host Configuration Protocol (DHCP) provides a mechanism
      31|    for transmitting configuration parameters to hosts using the TCP/IP
>>    32|    protocol suite.  The format of DHCP messages is based on the format
      33|    of BOOTP messages, so that, in certain circumstances, DHCP and BOOTP
      34|    participants may exchange messages.  This document specifies the ways
      35|    in which DHCP and BOOTP participants may interoperate.
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "DHCP messages",
  "meaning": "The format of DHCP messages is based on the format of BOOTP messages.",
  "constraint": "",
  "span": 32,
  "action": "",
  "object": "",
  "strength": "",
  "polarity": "",
  "keyword_raw": "",
  "condition": "",
  "exception": "",
  "cross_ref": "",
  "cross_ref_status": ""
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "DHCPv4",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "DHCP messages",
  "action": "DHCP messages",
  "object": "DHCP messages",
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
  "action": "DHCP messages",
  "object": "DHCP messages",
  "cross_ref": null,
  "cross_ref_status": "unknown"
}
```

**⑤ 去重/归并前后**

```json
{
  "slot_key": "DHCP messages | DHCP messages | DHCP messages | None",
  "group_size": 2,
  "members": [
    {
      "doc": "rfc1534.txt",
      "span": 32,
      "entity": "DHCP messages",
      "strength": null,
      "polarity": null,
      "keyword_raw": "",
      "evidence": "      29| \n      30|    The Dynamic Host Configuration Protocol (DHCP) provides a mechanism\n      31|    for transmitting configuration parameters to hosts using the TCP/IP\n>>    32|    protocol suite.  The format of DHCP messages is based on the format\n      33|    of BOOTP messages, so that, in certain circumstances, DHCP and BOOTP\n      34|    participants may exchange messages.  This document specifies the ways\n      35|    in which DHCP and BOOTP participants may interoperate."
    },
    {
      "doc": "rfc1534.txt",
      "span": 65,
      "entity": "DHCP messages",
      "strength": null,
      "polarity": null,
      "keyword_raw": "",
      "evidence": "      62| \n      63| 2. BOOTP clients and DHCP servers\n      64| \n>>    65|    The format of DHCP messages is defined to be compatible with the\n      66|    format of BOOTP messages, so that existing BOOTP clients can\n      67|    interoperate with DHCP servers.  Any message received by a DHCP\n      68|    server that includes a 'DHCP message type' (51) option is assumed to"
    }
  ],
  "resolver": {
    "method": "consensus",
    "value": {
      "meaning": "The format of DHCP messages is based on the format of BOOTP messages."
    },
    "epistemic": "normative_unspecified",
    "authority": "rfc",
    "basis_claim_ids": [
      "c2_4ccb61795c6fecbe"
    ],
    "superseded": [
      "c2_44ffd86e5ffc2cbc"
    ]
  }
}
```

**⑥ 样本来源（可追溯）**

```json
{
  "cache_file": "derived/cache/source_blocks/DHCPv4.prose.json",
  "cache_key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
  "manifest": {
    "key": "9991c94c8ac812ee066d303f19ff0085012aac5fb5f8a274441c2c44e087628d",
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

**总量**：强度未知 **436** 条（已确认强度 314 条）

| 原因分类 | 条数 | 占比 |
|---|---:|---:|
| ★ 原文确实没有明确规范强度（非抽取缺陷） | 376 | 86.2% |
| 原文有等级词但**模型漏抽**（证据行有等级词） | 58 | 13.3% |
| 原文有等级词但**模型漏抽** | 2 | 0.5% |

> ★ **结论**：绝大多数强度未知是「**原文确实没有明确规范强度**」⇒ ⇒ **不是抽取缺陷**
> ⇒ ⇒ ★ **不得**为提高正式入库率而**强行补充强度**

**每类的真实样例（各 3 条）**

**★ 原文确实没有明确规范强度（非抽取缺陷）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 235 | RTSP | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 238 | interleaving | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 247 | RTSP connection | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**原文有等级词但**模型漏抽**（证据行有等级词）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 250 | RTSP client | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 252 | connectionless transport protocol | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 255 | RTSP | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**原文有等级词但**模型漏抽****

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 1188 | Request-URI | `is only allowed` | False | 规范强度未定（不得凭推测赋值）；关键词无法归一：'is only allowed' |
| sip | rfc3261.txt | 1550 | CR | `No CR or LF is allowed` | False | 规范强度未定（不得凭推测赋值）；关键词无法归一：'No CR or LF is allowed' |

### B. 拒收质量分析

**总拒收**：44 条

| 拒收原因分类 | 条数 | 判定 |
|---|---:|---|
| ★ 真无证据支持（span 行不含实体名） | 44 | ★ 真无证据支持（**正确拒收**） |

**全部拒收样本（供逐条判断是否误拒收）**

| 协议 | 文件 | 行 | 实体 | 拒收原因 |
|---|---|---:|---|---|
| rtsp | rfc2326.txt | 683 | state transitions | ★ 可核对闸：span 所在行**不含**实体名「state transitions」（该行：transitions are described in Section A.） |
| rtsp | rfc2326.txt | 806 | rtspu | ★ 可核对闸：span 所在行**不含**实体名「rtspu」（该行：server listening for TCP (scheme "rtsp") connections or UDP (scheme） |
| rtsp | rfc2326.txt | 875 | session identifier | ★ 可核对闸：span 所在行**不含**实体名「session identifier」（该行：randomly and MUST be at least eight octets long to make guessing it） |
| rtsp | rfc2326.txt | 905 | smpte-time | ★ 可核对闸：span 所在行**不含**实体名「smpte-time」（该行：; other timecodes may be added） |
| rtsp | rfc2326.txt | 1217 | Status-Line | ★ 可核对闸：span 所在行**不含**实体名「Status-Line」（该行：separated by SP characters. No CR or LF is allowed except in the） |
| rtsp | rfc2326.txt | 1229 | Reason-Phrase | ★ 可核对闸：span 所在行**不含**实体名「Reason-Phrase」（该行：user. The client is not required to examine or display the Reason-） |
| rtsp | rfc2326.txt | 1245 | 3xx | ★ 可核对闸：span 所在行**不含**实体名「3xx」（该行：and accepted） |
| rtsp | rfc2326.txt | 1246 | 4xx | ★ 可核对闸：span 所在行**不含**实体名「4xx」（该行：* 3xx: Redirection - Further action must be taken in order to） |
| rtsp | rfc2326.txt | 1247 | 5xx | ★ 可核对闸：span 所在行**不含**实体名「5xx」（该行：complete the request） |
| rtsp | rfc2326.txt | 1358 | unrecognized response | ★ 可核对闸：span 所在行**不含**实体名「unrecognized response」（该行：understand the class of any status code, as indicated by the first） |
| rtsp | rfc2326.txt | 1509 | Unrecognized header fields | ★ 可核对闸：span 所在行**不含**实体名「Unrecognized header fields」（该行：fields SHOULD be ignored by the recipient and forwarded by proxi |
| rtsp | rfc2326.txt | 1657 | OPTIONS | ★ 可核对闸：span 所在行**不含**实体名「OPTIONS」（该行：request may be issued at any time, e.g., if the client is about to） |
| rtsp | rfc2326.txt | 1690 | Accept header | ★ 可核对闸：span 所在行**不含**实体名「Accept header」（该行：media object identified by the request URL from a server. It may use） |
| rtsp | rfc2326.txt | 1732 | DESCRIBE | ★ 可核对闸：span 所在行**不含**实体名「DESCRIBE」（该行：Clear ground rules need to be established so that clients have an） |
| rtsp | rfc2326.txt | 1748 | DESCRIBE | ★ 可核对闸：span 所在行**不含**实体名「DESCRIBE」（该行：Media initialization is a requirement for any RTSP-based system,） |
| rtsp | rfc2326.txt | 1759 | DESCRIBE | ★ 可核对闸：span 所在行**不含**实体名「DESCRIBE」（该行：In the interest of practical interoperability, it is highly） |
| sip | rfc3261.txt | 1072 | dialog | ★ 可核对闸：span 所在行**不含**实体名「dialog」（该行：peer-to-peer SIP relationship between two user agents that persists） |
| sip | rfc3261.txt | 1075 | INVITE | ★ 可核对闸：span 所在行**不含**实体名「INVITE」（该行：method is the only way defined in this specification to establish a） |
| sip | rfc3261.txt | 1523 | Request-URI | ★ 可核对闸：span 所在行**不含**实体名「Request-URI」（该行：characters and MUST NOT be enclosed in "<>".） |
| sip | rfc3261.txt | 1748 | field values | ★ 可核对闸：span 所在行**不含**实体名「field values」（该行：insensitive.  Unless otherwise stated in the definition of a） |
| sip | rfc3261.txt | 1748 | parameter names | ★ 可核对闸：span 所在行**不含**实体名「parameter names」（该行：insensitive.  Unless otherwise stated in the definition of a） |
| sip | rfc3261.txt | 1749 | Tokens | ★ 可核对闸：span 所在行**不含**实体名「Tokens」（该行：particular header field, field values, parameter names, and parameter） |
| sip | rfc3261.txt | 1750 | quoted strings | ★ 可核对闸：span 所在行**不含**实体名「quoted strings」（该行：values are case-insensitive.  Tokens are always case-insensitive.） |
| sip | rfc3261.txt | 1789 | compact form | ★ 可核对闸：span 所在行**不含**实体名「compact form」（该行：form MAY be substituted for the longer form of a header field name at） |
| sip | rfc3261.txt | 2061 | Call-ID header field | ★ 可核对闸：span 所在行**不含**实体名「Call-ID header field」（该行：together a series of messages.  It MUST be the same for all requests） |
| sip | rfc3261.txt | 2062 | Call-ID header field | ★ 可核对闸：span 所在行**不含**实体名「Call-ID header field」（该行：and responses sent by either UA in a dialog.  It SHOULD be the same） |
| sip | rfc3261.txt | 2065 | Call-ID header field | ★ 可核对闸：span 所在行**不含**实体名「Call-ID header field」（该行：In a new request created by a UAC outside of any dialog, the Call-ID） |
| smtp | rfc3207.txt | 299 | TLS negotiation | ★ 可核对闸：span 所在行**不含**实体名「TLS negotiation」（该行：The SMTP client and server should note carefully the result of the） |
| smtp | rfc4954.txt | 161 | AUTH | ★ 可核对闸：span 所在行**不含**实体名「AUTH」（该行：Discussion:） |
| smtp | rfc4954.txt | 241 | BASE64 characters | ★ 可核对闸：span 所在行**不含**实体名「BASE64 characters」（该行：allowed by the BASE64 alphabet, and MUST reject any sequence） |
| smtp | rfc4954.txt | 268 | server | ★ 可核对闸：span 所在行**不含**实体名「server」（该行：MUST fail the authentication.） |
| smtp | rfc4954.txt | 276 | SMTP server | ★ 可核对闸：span 所在行**不含**实体名「SMTP server」（该行：is appropriate.  Should the client successfully complete the） |
| smtp | rfc4954.txt | 331 | Server sites | ★ 可核对闸：span 所在行**不含**实体名「Server sites」（该行：permits a plaintext password mechanism without such a protection） |
| smtp | rfc4954.txt | 819 | Authentication SMTP service extension | ★ 可核对闸：span 所在行**不含**实体名「Authentication SMTP service extension」（该行：IANA updated the registration of the Authentication S |
| smtp | rfc4954.txt | 942 | SASL PLAIN | ★ 可核对闸：span 所在行**不含**实体名「SASL PLAIN」（该行：man-in-the-middle attacks.  If the match fails, the client MUST NOT） |
| DHCPv4 | rfc1542.txt | 594 | ciaddr | ★ 可核对闸：span 所在行**不含**实体名「ciaddr」（该行：The last interpretation is incorrect as it may prevent the） |
| DHCPv4 | rfc1542.txt | 643 | giaddr | ★ 可核对闸：span 所在行**不含**实体名「giaddr」（该行：relay agent that is not itself an IP router (according to [1],） |
| DHCPv4 | rfc1542.txt | 773 | relay agent | ★ 可核对闸：span 所在行**不含**实体名「relay agent」（该行：The consistency checks specified in Section 2.1 SHOULD be performed） |
| DHCPv4 | rfc1542.txt | 889 | BOOTREQUEST | ★ 可核对闸：span 所在行**不含**实体名「BOOTREQUEST」（该行：preferable to use the decremented TTL from the original） |
| DHCPv4 | rfc1542.txt | 933 | BROADCAST flag | ★ 可核对闸：span 所在行**不含**实体名「BROADCAST flag」（该行：Sections 2.2 and 3.1.1 for more information).  If this flag is set to） |
| DHCPv4 | rfc1542.txt | 965 | BROADCAST flag | ★ 可核对闸：span 所在行**不含**实体名「BROADCAST flag」（该行：implementations must nevertheless be considered.  If an old） |
| DHCPv4 | rfc1542.txt | 979 | relay agent | ★ 可核对闸：span 所在行**不含**实体名「relay agent」（该行：MUST NOT modify any BOOTP field of the BOOTREPLY message when） |
| DHCPv4 | rfc1542.txt | 1024 | BOOTP server | ★ 可核对闸：span 所在行**不含**实体名「BOOTP server」（该行：The consistency checks specified in Section 2.1 SHOULD be） |
| DHCPv4 | rfc1542.txt | 1026 | BOOTP messages | ★ 可核对闸：span 所在行**不含**实体名「BOOTP messages」（该行：these consistency checks MUST be silently discarded.） |

### C. 归并正确性

#### C1 · 同一 Rule Slot 的多声明（真实）

| 协议 | 主体 | 动作 | 对象 | 条件 | 同槽位声明数 | 行号 |
|---|---|---|---|---|---:|---|
| rtsp | RTSP | RTSP | RTSP | — | 13 | 235, 255, 256, 259, 667, 711, 724, 805, 1024, 1580, 1595, 1598, 1602 |
| rtsp | media server | media server | media server | — | 3 | 298, 624, 1049 |
| rtsp | RTSP requests | RTSP requests | RTSP requests | — | 3 | 310, 670, 725 |
| rtsp | presentation description | presentation description | presentation description | — | 5 | 612, 626, 716, 835, 837 |
| rtsp | TCP | TCP | TCP | — | 2 | 669, 1563 |
| rtsp | Requests | Requests | Requests | — | 2 | 1046, 1552 |
| rtsp | Status-Code | Status-Code | Status-Code | — | 2 | 1224, 1295 |
| rtsp | DESCRIBE | DESCRIBE | DESCRIBE | — | 2 | 1632, 1689 |
| rtsp | ANNOUNCE | ANNOUNCE | ANNOUNCE | — | 2 | 1633, 1770 |
| rtsp | PAUSE | PAUSE | PAUSE | — | 2 | 1637, 1648 |
| sip | SIP | SIP | SIP | — | 9 | 446, 514, 516, 519, 520, 751, 986, 1468, 1540 |
| sip | SDP | SDP | SDP | — | 3 | 513, 523, 802 |

#### C2 · 相反极性声明（同一槽位）

> ★ **本次真实运行中未出现**「同一槽位 + 相反极性」的组合 ⇒ ⇒ 标 **N/A**（**不人工制造**）


## 三、专项核查：跨章节引用定位失败（全部）

| 协议 | 文件 | 行 | 实体 | 引用 | 原文 |
|---|---|---:|---|---|---|
| rtsp | rfc2326.txt | 683 | state transitions | `Section A` | >>   683|    transitions are described in Section A. |
| sip | rfc3261.txt | 1531 | SIP-Version | `[H3.1]` | >>  1531|       SIP-Version: Both request and response messages include the |
| sip | rfc3261.txt | 1863 | CRLF | `[H4.1]` | >>  1863|    transports MUST ignore any CRLF appearing before the start-line |

## 四、专项核查：代词主体隔离（全部）

| 协议 | 文件 | 行 | 实体 | 发布闸 | L1 |
|---|---|---:|---|---|---|
| smtp | rfc4954.txt | 772 | they | 隔离 （主体不可靠（they）；校验结论非已证实（pending））| pending |

## 五、运行配置与可追溯性

| 协议 | 缓存文件 | 缓存键（前 16） | 模型 | 解析器版本 | 校验器版本 |
|---|---|---|---|---|---|
| rtsp | `derived/cache/source_blocks/rtsp.prose.json` | `1709ccbd179a5c40` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |
| sip | `derived/cache/source_blocks/sip.prose.json` | `0dbd6a25bf72ddc4` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |
| smtp | `derived/cache/source_blocks/smtp.prose.json` | `9b2395036ca84d09` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |
| DHCPv4 | `derived/cache/source_blocks/DHCPv4.prose.json` | `9991c94c8ac812ee` | deepseek-flash | rfc-parser-v1 | normative-verifier-v1 |

> ★ **复现**：同缓存键 ⇒ 命中缓存 ⇒ 不调 LLM ⇒ 逐字节可复现
> ⇒ ⇒ 本包所有样本均可回溯到上表的缓存文件与缓存键

## 六、人工判定汇总（★ 待填）

| 样本 | 协议 | 类别 | 最终状态 | 人工判定 | 错误原因 / 修改建议 |
|---|---|---|---|---|---|
| S01 | rtsp | 已确认强度的规范规则 | 确认 |  |  |
| S02 | rtsp | 已确认强度的规范规则 | 确认 |  |  |
| S03 | rtsp | 已确认强度的规范规则 | 确认 |  |  |
| S04 | rtsp | 强度未知（被隔离）候选 | 待审 |  |  |
| S05 | rtsp | 强度未知（被隔离）候选 | 待审 |  |  |
| S06 | rtsp | 含条件或例外的规则 | 待审 |  |  |
| S07 | rtsp | 含条件或例外的规则 | 待审 |  |  |
| S08 | rtsp | 跨章节引用规则 | 待审 |  |  |
| S09 | rtsp | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S10 | rtsp | 发生去重或多证据归并的规则 | 待审 |  |  |
| S11 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S12 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S13 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S14 | sip | 强度未知（被隔离）候选 | 待审 |  |  |
| S15 | sip | 强度未知（被隔离）候选 | 待审 |  |  |
| S16 | sip | 含条件或例外的规则 | 确认 |  |  |
| S17 | sip | 含条件或例外的规则 | 确认 |  |  |
| S18 | sip | 跨章节引用规则 | 待审 |  |  |
| S19 | sip | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S20 | sip | 发生去重或多证据归并的规则 | 待审 |  |  |
| S21 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S22 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S23 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S24 | smtp | 强度未知（被隔离）候选 | 待审 |  |  |
| S25 | smtp | 强度未知（被隔离）候选 | 待审 |  |  |
| S26 | smtp | 含条件或例外的规则 | 确认 |  |  |
| S27 | smtp | 含条件或例外的规则 | 确认 |  |  |
| S28 | smtp | 跨章节引用规则 | 待审 |  |  |
| S29 | smtp | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S30 | smtp | 发生去重或多证据归并的规则 | 待审 |  |  |
| S31 | DHCPv4 | 已确认强度的规范规则 | 确认 |  |  |
| S32 | DHCPv4 | 已确认强度的规范规则 | 确认 |  |  |
| S33 | DHCPv4 | 已确认强度的规范规则 | 确认 |  |  |
| S34 | DHCPv4 | 强度未知（被隔离）候选 | 待审 |  |  |
| S35 | DHCPv4 | 强度未知（被隔离）候选 | 待审 |  |  |
| S36 | DHCPv4 | 含条件或例外的规则 | 确认 |  |  |
| S37 | DHCPv4 | 含条件或例外的规则 | 确认 |  |  |
| S38 | DHCPv4 | 跨章节引用规则 | 待审 |  |  |
| S39 | DHCPv4 | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S40 | DHCPv4 | 发生去重或多证据归并的规则 | 待审 |  |  |
