# RFC 规范语义 · 人工抽样核查包

> ★ **目的**：★ **独立核实真实 RFC 抽取内容的准确性**，并发现**误拒收 / 误隔离 / 错误归并**
> ★ **数据来源**：deepseek-flash 的**真实运行缓存**（`derived/cache/source_blocks/<协议>.prose.json`）
> ⇒ ⇒ **不使用 mock、不使用手工构造的 payload**
> ★ **本包不含任何「机制验收通过 ⇒ 语义正确」的结论** ⇒ ⇒ **结论由人工填写**
> ★ 生成时间：2026-11-13

## 〇、抽样范围与构成

| 协议 | 真实条目总数 | 抽样数 |
|---|---:|---:|
| rtsp | 270 | 10 |
| sip | 216 | 10 |
| smtp | 164 | 10 |
| DHCPv4 | 176 | 10 |
| **合计** | **826** | **40** |

**每协议的抽样构成**（按类别）：

| 协议 | 已确认强度的规范规则 | 强度未知（被隔离）候选 | 含条件或例外的规则 | 跨章节引用规则 | 被 L1/L2 拒收的候选 | 发生去重或多证据归并的规则 | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） |
|---|---:|---:|---:|---:|---:|---:|---:|
| rtsp | 3 | 0 | 2 | 1 | 1 | 0 | 3 |
| sip | 3 | 2 | 2 | 1 | 1 | 0 | 1 |
| smtp | 4 | 0 | 2 | 1 | 0 | 0 | 3 |
| DHCPv4 | 3 | 1 | 2 | 1 | 1 | 0 | 2 |

## 一、逐条样本（★ 人工审阅区）

> ★ **判定栏**：`正确 / 部分正确 / 错误 / 无法判断` ⇒ ★ 请在**「人工判定」**列填写，并在**错误原因**/**修改建议**列写明


### 协议 rtsp

#### S01 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

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
  "meaning": "呈现描述必须包含至少一个 RTSP URI。",
  "constraint": "呈现描述必须包含至少一个 RTSP URI。",
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
| 章节 | 3.8.1 Registering New Option Tags with IANA |
| 原始行号 | 第 **1000** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     997|    be provided:
     998| 
     999|      * Name and description of option. The name may be of any length,
>>  1000|        but SHOULD be no more than twenty characters long. The name MUST
    1001|        not contain any spaces, control characters or periods.
    1002|      * Indication of who has change control over the option (for
    1003|        example, IETF, ISO, ITU-T, other international standardization
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "name",
  "meaning": "选项名称不得包含任何空格、控制字符或句点。",
  "constraint": "MUST not contain any spaces, control characters or periods",
  "span": 1000,
  "action": "contain",
  "object": "any spaces, control characters or periods",
  "strength": "MUST",
  "polarity": "negative",
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
  "subject": "name",
  "action": "contain",
  "object": "any spaces, control characters or periods",
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
  "object": "any spaces, control characters or periods",
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

#### S04 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.4 Protocol Properties |
| 原始行号 | 第 **536** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `If a client can start a stream` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

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
  "meaning": "If a client can start a stream, it must be able to stop a stream.",
  "constraint": "If a client can start a stream, it must be able to stop a stream.",
  "span": 536,
  "action": "be able to stop",
  "object": "a stream",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "If a client can start a stream",
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
  "action": "be able to stop",
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
  "action": "be able to stop",
  "object": "a stream",
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

#### S05 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 1.4 Protocol Properties |
| 原始行号 | 第 **546** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `If basic features are disabled` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     543| 
     544|    Capability negotiation:
     545|           If basic features are disabled, there must be some clean
>>   546|           mechanism for the client to determine which methods are not
     547|           going to be implemented. This allows clients to present the
     548|           appropriate user interface. For example, if seeking is not
     549|           allowed, the user interface must be able to disallow moving a
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "client",
  "meaning": "If basic features are disabled, there must be some clean mechanism for the client to determine which methods are not going to be implemented.",
  "constraint": "If basic features are disabled, there must be some clean mechanism for the client to determine which methods are not going to be implemented.",
  "span": 546,
  "action": "determine",
  "object": "which methods are not going to be implemented",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "must",
  "condition": "If basic features are disabled",
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
  "action": "determine",
  "object": "which methods are not going to be implemented",
  "condition": "If basic features are disabled",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MUST",
  "polarity": "positive",
  "condition": "If basic features are disabled",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "determine",
  "object": "which methods are not going to be implemented",
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

#### S06 ｜ 跨章节引用规则 ｜ 最终状态：**待审**

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
  "meaning": "A server SHOULD implement all header fields described in Section 12.",
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

#### S07 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | 3.6 Normal Play Time |
| 原始行号 | 第 **923** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Negative values」（该行：The beginning of a presentation corresponds to 0.0 seconds. Negative） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     920|    in either seconds or hours, minutes, and seconds. The part right of
     921|    the decimal point measures fractions of a second.
     922| 
>>   923|    The beginning of a presentation corresponds to 0.0 seconds. Negative
     924|    values are not defined. The special constant now is defined as the
     925|    current instant of a live event. It may be used only for live events.
     926| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "Negative values",
  "meaning": "负值未被定义。",
  "constraint": "Negative values are not defined",
  "span": 923,
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
  "protocol": "rtsp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "Negative values",
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
  "action": "Negative values",
  "object": "Negative values",
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

#### S08 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **63** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      60| RFC 2326              Real Time Streaming Protocol            April 1998
      61| 
      62| 
>>    63|         + 3.2 RTSP URL .............................................. 14
      64|         + 3.3 Conference Identifiers ................................ 16
      65|         + 3.4 Session Identifiers ................................... 16
      66|         + 3.5 SMPTE Relative Timestamps ............................. 16
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "RTSP URL",
  "meaning": "文档 3.2 节标题，介绍 RTSP URL 的章节",
  "constraint": "",
  "span": 63,
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
  "subject": "RTSP URL",
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
  "action": "RTSP URL",
  "object": "RTSP URL",
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

#### S09 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **64** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      61| 
      62| 
      63|         + 3.2 RTSP URL .............................................. 14
>>    64|         + 3.3 Conference Identifiers ................................ 16
      65|         + 3.4 Session Identifiers ................................... 16
      66|         + 3.5 SMPTE Relative Timestamps ............................. 16
      67|         + 3.6 Normal Play Time ...................................... 17
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "Conference Identifiers",
  "meaning": "文档 3.3 节标题，介绍会议标识符的章节",
  "constraint": "",
  "span": 64,
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
  "subject": "Conference Identifiers",
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
  "action": "Conference Identifiers",
  "object": "Conference Identifiers",
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

#### S10 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `rtsp` / `rfc2326.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **65** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      62| 
      63|         + 3.2 RTSP URL .............................................. 14
      64|         + 3.3 Conference Identifiers ................................ 16
>>    65|         + 3.4 Session Identifiers ................................... 16
      66|         + 3.5 SMPTE Relative Timestamps ............................. 16
      67|         + 3.6 Normal Play Time ...................................... 17
      68|         + 3.7 Absolute Time ......................................... 18
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc2326.txt",
  "entity": "Session Identifiers",
  "meaning": "文档 3.4 节标题，介绍会话标识符的章节",
  "constraint": "",
  "span": 65,
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
  "subject": "Session Identifiers",
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
  "action": "Session Identifiers",
  "object": "Session Identifiers",
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
  "constraint": "The start-line, each message-header line, and the empty line MUST be terminated by a carriage-return line-feed sequence (CRLF)",
  "span": 1480,
  "action": "be terminated by",
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
  "action": "be terminated by",
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
  "action": "be terminated by",
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

#### S12 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

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
  "meaning": "实现必须发送大写的 SIP-Version 字符串。",
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

#### S13 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7.3.1 Header Field Format |
| 原始行号 | 第 **1691** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1688|    their grammar does not follow the general form listed in Section 7.3,
    1689|    they MUST NOT be combined into a single header field row.
    1690| 
>>  1691|    Implementations MUST be able to process multiple header field rows
    1692|    with the same name in any combination of the single-value-per-line or
    1693|    comma-separated value forms.
    1694| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "Implementations",
  "meaning": "实现必须能处理同名且任意混合使用单值每行与逗号分隔值形式的多个头域行",
  "constraint": "MUST be able to process multiple header field rows with the same name in any combination of the single-value-per-line or comma-separated value forms",
  "span": 1691,
  "action": "process",
  "object": "multiple header field rows with the same name in any combination of the single-value-per-line or comma-separated value forms",
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
  "subject": "Implementations",
  "action": "process",
  "object": "multiple header field rows with the same name in any combination of the single-value-per-line or comma-separated value forms",
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
  "action": "process",
  "object": "multiple header field rows with the same name in any combination of the single-value-per-line or comma-separated value forms",
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
| 章节 | 7.1 Requests |
| 原始行号 | 第 **1498** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性为 negative，但证据文本里没有否定词 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1495|    protocol version separated by a single space (SP) character.
    1496| 
    1497|    The Request-Line ends with CRLF.  No CR or LF are allowed except in
>>  1498|    the end-of-line CRLF sequence.  No linear whitespace (LWS) is allowed
    1499|    in any of the elements.
    1500| 
    1501|          Request-Line  =  Method SP Request-URI SP SIP-Version CRLF
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "LWS",
  "meaning": "线性空白（LWS）在请求行各元素中都不允许出现。",
  "constraint": "No linear whitespace (LWS) is allowed in any of the elements.",
  "span": 1498,
  "action": "be allowed",
  "object": "linear whitespace (LWS) in any of the elements",
  "strength": "",
  "polarity": "negative",
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
  "subject": "LWS",
  "action": "be allowed",
  "object": "linear whitespace (LWS) in any of the elements",
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
  "action": "be allowed",
  "object": "linear whitespace (LWS) in any of the elements",
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
| 章节 | 7.2 Responses |
| 原始行号 | 第 **1559** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；规范强度未知 ⇒ 不得凭推测赋值 ⇒ 待审 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1556|    Reason-Phrase is intended to give a short textual description of the
    1557|    Status-Code.  The Status-Code is intended for use by automata,
    1558|    whereas the Reason-Phrase is intended for the human user.  A client
>>  1559|    is not required to examine or display the Reason-Phrase.
    1560| 
    1561|    While this specification suggests specific wording for the reason
    1562|    phrase, implementations MAY choose other text, for example, in the
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "client",
  "meaning": "A client is not required to examine or display the Reason-Phrase.",
  "constraint": "A client is not required to examine or display the Reason-Phrase.",
  "span": 1559,
  "action": "examine or display",
  "object": "Reason-Phrase",
  "strength": "",
  "polarity": "negative",
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
  "constraint": "the empty line MUST be present even if the message-body is not",
  "span": 1482,
  "action": "be present",
  "object": "the empty line",
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

#### S17 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `sip` / `rfc3261.txt` |
| 章节 | 7.1 Requests |
| 原始行号 | 第 **1497** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `except in the end-of-line CRLF sequence` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性为 negative，但证据文本里没有否定词 |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
    1494|    line.  A Request-Line contains a method name, a Request-URI, and the
    1495|    protocol version separated by a single space (SP) character.
    1496| 
>>  1497|    The Request-Line ends with CRLF.  No CR or LF are allowed except in
    1498|    the end-of-line CRLF sequence.  No linear whitespace (LWS) is allowed
    1499|    in any of the elements.
    1500| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3261.txt",
  "entity": "Request-Line",
  "meaning": "请求行以 CRLF 结尾，且除行尾 CRLF 序列外不得包含 CR 或 LF，元素中不得出现线性空白（LWS）。",
  "constraint": "No CR or LF are allowed except in the end-of-line CRLF sequence. No linear whitespace (LWS) is allowed in any of the elements.",
  "span": 1497,
  "action": "contain",
  "object": "CR or LF",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "",
  "condition": "",
  "exception": "except in the end-of-line CRLF sequence",
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
  "subject": "Request-Line",
  "action": "contain",
  "object": "CR or LF",
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
  "exception": "except in the end-of-line CRLF sequence",
  "exception_status": "stated",
  "scope": null,
  "action": "contain",
  "object": "CR or LF",
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
  "entity": "Multiple header field rows",
  "meaning": "Multiple header field rows with the same field-name MAY be present in a message if and only if the entire field-value for that header field is defined as a comma-separated list following the grammar in Section 7.3.",
  "constraint": "may be present only if the entire field-value is defined as a comma-separated list",
  "span": 1670,
  "action": "be present in a message",
  "object": "Multiple header field rows with the same field-name",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "MAY",
  "condition": "if and only if the entire field-value for that header field is defined as a comma-separated list (that is, if follows the grammar defined in Section 7.3)",
  "exception": "",
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
  "subject": "Multiple header field rows",
  "action": "be present in a message",
  "object": "Multiple header field rows with the same field-name",
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
  "object": "Multiple header field rows with the same field-name",
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
| 章节 | 1 Introduction |
| 原始行号 | 第 **446** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Session Initiation Protocol (SIP)」（该行：Initiation Protocol (SIP) works in concert with these protocols by） |

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
  "entity": "Session Initiation Protocol (SIP)",
  "meaning": "Session Initiation Protocol (SIP) 与承载实时多媒体会话数据的其他协议协同工作",
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
  "cross_ref_status": "unknown"
}
```

**③ 规范化 Rule Slot（身份）**

```json
{
  "protocol": "sip",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "Session Initiation Protocol (SIP)",
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
  "action": "Session Initiation Protocol (SIP)",
  "object": "Session Initiation Protocol (SIP)",
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
  "meaning": "片段将 session 描述为参与者关联之间的一次数据交换",
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
  "cross_ref_status": "unknown"
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
  "meaning": "客户端与服务器都必须知道当前是否有活动的 TLS 会话。",
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

#### S22 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 4.3 STARTTLS on the Submission Port |
| 原始行号 | 第 **292** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

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
  "meaning": "SMTP 客户端与服务器都必须检查 TLS 协商结果，以确认是否达到可接受的认证与隐私程度。",
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
| 协议 / 文件 | `smtp` / `rfc4954.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **247** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     244|           "AAA=BBB" are not allowed).
     245| 
     246|           Note that these [BASE64] strings can be much longer than
>>   247|           normal SMTP commands.  Clients and servers MUST be able to
     248|           handle the maximum encoded size of challenges and responses
     249|           generated by their supported authentication mechanisms.  This
     250|           requirement is independent of any line length limitations the
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc4954.txt",
  "entity": "Clients and servers",
  "meaning": "Clients and servers must handle the maximum encoded size of challenges and responses generated by their supported authentication mechanisms.",
  "constraint": "MUST be able to handle the maximum encoded size of challenges and responses generated by their supported authentication mechanisms",
  "span": 247,
  "action": "handle",
  "object": "the maximum encoded size of challenges and responses generated by their supported authentication mechanisms",
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
  "subject": "Clients and servers",
  "action": "handle",
  "object": "the maximum encoded size of challenges and responses generated by their supported authentication mechanisms",
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
  "action": "handle",
  "object": "the maximum encoded size of challenges and responses generated by their supported authentication mechanisms",
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

#### S24 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

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
  "entity": "client",
  "meaning": "Upon receiving a 454 response, the client must decide whether or not to continue the SMTP session.",
  "constraint": "must decide whether or not to continue the SMTP session",
  "span": 119,
  "action": "decide whether or not to continue",
  "object": "the SMTP session",
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
  "subject": "client",
  "action": "decide whether or not to continue",
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
  "action": "decide whether or not to continue",
  "object": "the SMTP session",
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

#### S25 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **139** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`may`）|
| 条件 / 例外 | `that is not publicly referenced` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'may' |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     136|    address.
     137| 
     138|    Any SMTP server may refuse to accept messages for relay based on
>>   139|    authentication supplied during the TLS negotiation.  An SMTP server
     140|    that is not publicly referenced may refuse to accept any messages for
     141|    relay or local delivery based on authentication supplied during the
     142|    TLS negotiation.
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "SMTP server",
  "meaning": "An SMTP server that is not publicly referenced may refuse to accept any messages for relay or local delivery based on authentication supplied during TLS negotiation.",
  "constraint": "may refuse to accept any messages for relay or local delivery based on authentication supplied during the TLS negotiation",
  "span": 139,
  "action": "refuse",
  "object": "to accept any messages for relay or local delivery based on authentication supplied during the TLS negotiation",
  "strength": "MAY",
  "polarity": "positive",
  "keyword_raw": "may",
  "condition": "that is not publicly referenced",
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
  "subject": "SMTP server",
  "action": "refuse",
  "object": "to accept any messages for relay or local delivery based on authentication supplied during the TLS negotiation",
  "condition": "that is not publicly referenced",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": "MAY",
  "polarity": "positive",
  "condition": "that is not publicly referenced",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "refuse",
  "object": "to accept any messages for relay or local delivery based on authentication supplied during the TLS negotiation",
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
  "meaning": "initial-response 是可选的初始客户端响应。",
  "constraint": "If present, this response MUST be encoded as described in Section 4 of [BASE64] or contain a single character \"=\".",
  "span": 147,
  "action": "encoded as described in Section 4 of [BASE64] or contain a single character \"=\"",
  "object": "initial-response",
  "strength": "MUST",
  "polarity": "positive",
  "keyword_raw": "MUST",
  "condition": "If present",
  "exception": "",
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
  "action": "encoded as described in Section 4 of [BASE64] or contain a single character \"=\"",
  "object": "initial-response",
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
  "action": "encoded as described in Section 4 of [BASE64] or contain a single character \"=\"",
  "object": "initial-response",
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

#### S27 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

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
  "meaning": "SMTP response code indicating readiness to start TLS.",
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
  "cross_ref_status": ""
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

#### S28 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

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
  "meaning": "SMTP response code for a syntax error with no parameters allowed.",
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
  "cross_ref_status": ""
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

#### S29 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **109** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
     106| 
     107|    220 Ready to start TLS
     108|    501 Syntax error (no parameters allowed)
>>   109|    454 TLS not available due to temporary reason
     110| 
     111| 
     112| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc3207.txt",
  "entity": "454",
  "meaning": "SMTP response code indicating TLS is not available due to a temporary reason.",
  "constraint": "",
  "span": 109,
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
  "protocol": "smtp",
  "version": "1.0",
  "kind": "normative_rule",
  "subject": "454",
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
  "action": "454",
  "object": "454",
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

#### S30 ｜ 已确认强度的规范规则 ｜ 最终状态：**确认**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `smtp` / `rfc3207.txt` |
| 章节 | 454 TLS not available due to temporary reason |
| 原始行号 | 第 **129** 行 |
| 强度 / 极性 | `MUST` / `negative`（原文等级措辞：`MUST NOT`）|
| 条件 / 例外 | `（无）` / `（无）` |
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
  "meaning": "A publicly-referenced SMTP server is prohibited from requiring STARTTLS to deliver mail locally.",
  "constraint": "MUST NOT require use of the STARTTLS extension in order to deliver mail locally",
  "span": 129,
  "action": "require",
  "object": "use of the STARTTLS extension in order to deliver mail locally",
  "strength": "MUST",
  "polarity": "negative",
  "keyword_raw": "MUST NOT",
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
  "subject": "publicly-referenced SMTP server",
  "action": "require",
  "object": "use of the STARTTLS extension in order to deliver mail locally",
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
  "action": "require",
  "object": "use of the STARTTLS extension in order to deliver mail locally",
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

#### S31 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

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
  "meaning": "允许 DHCP 服务器返回自动地址的决定必须由系统管理员掌控。",
  "constraint": "the decision to allow a DHCP server to return automatic addresses must be under the control of the system administrator",
  "span": 86,
  "action": "be under the control of",
  "object": "the decision to allow a DHCP server to return automatic addresses",
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
  "object": "the decision to allow a DHCP server to return automatic addresses",
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
  "object": "the decision to allow a DHCP server to return automatic addresses",
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

#### S32 ｜ 已确认强度的规范规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **89** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`must`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 关键词无法归一：'must' |

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
  "entity": "feature",
  "meaning": "启用该特性必须是系统管理员主动决定的结果。",
  "constraint": "Enabling of the feature must be the result of an active decision by the system administrator",
  "span": 89,
  "action": "be the result of an active decision by the system administrator",
  "object": "Enabling of the feature",
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
  "subject": "feature",
  "action": "be the result of an active decision by the system administrator",
  "object": "Enabling of the feature",
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
  "action": "be the result of an active decision by the system administrator",
  "object": "Enabling of the feature",
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
| 原始行号 | 第 **100** 行 |
| 强度 / 极性 | `MUST` / `positive`（原文等级措辞：`MUST`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **confirmed** ｜  |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      97|    The local system administrator may choose to manually release network
      98|    addresses assigned to BOOTP clients.
      99| 
>>   100|    A DHCP server that supports BOOTP clients MUST interact with BOOTP
     101|    clients according to the BOOTP protocol.  The server MUST formulate a
     102|    BOOTP BOOTREPLY message rather than a DHCP DHCPOFFER message (i.e.,
     103|    the server MUST NOT include the 'DHCP message type' option and MUST
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "DHCP server",
  "meaning": "支持 BOOTP 客户端的 DHCP 服务器必须按 BOOTP 协议与 BOOTP 客户端交互。",
  "constraint": "支持 BOOTP 客户端的 DHCP 服务器必须按 BOOTP 协议与 BOOTP 客户端交互",
  "span": 100,
  "action": "interact",
  "object": "BOOTP clients",
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
  "subject": "DHCP server",
  "action": "interact",
  "object": "BOOTP clients",
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
  "action": "interact",
  "object": "BOOTP clients",
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
  "entity": "server",
  "meaning": "分配给 BOOTP 客户端的此类网络地址不能被服务器自动重新分配。",
  "constraint": "Such network addresses cannot be automatically reassigned by the server",
  "span": 96,
  "action": "be automatically reassigned by the server",
  "object": "Such network addresses",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "cannot",
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
  "subject": "server",
  "action": "be automatically reassigned by the server",
  "object": "Such network addresses",
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
  "action": "be automatically reassigned by the server",
  "object": "Such network addresses",
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

#### S35 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **74** 行 |
| 强度 / 极性 | `None` / `negative`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `If a DHCP server that is not configured to support BOOTP clients receives a BOOTREQUEST message from a BOOTP client` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性为 negative，但证据文本里没有否定词 |

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
  "meaning": "BOOTP 客户端发来的请求报文，未配置支持 BOOTP 客户端的 DHCP 服务器收到后会静默丢弃它。",
  "constraint": "that server silently discards the BOOTREQUEST message",
  "span": 74,
  "action": "silently discards",
  "object": "the BOOTREQUEST message",
  "strength": "",
  "polarity": "negative",
  "keyword_raw": "",
  "condition": "If a DHCP server that is not configured to support BOOTP clients receives a BOOTREQUEST message from a BOOTP client",
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
  "subject": "BOOTREQUEST",
  "action": "silently discards",
  "object": "the BOOTREQUEST message",
  "condition": "If a DHCP server that is not configured to support BOOTP clients receives a BOOTREQUEST message from a BOOTP client",
  "scope": null
}
```

**④ 规范化 Assertion（声明内容）**

```json
{
  "kind": "normative_rule",
  "strength": null,
  "polarity": "negative",
  "condition": "If a DHCP server that is not configured to support BOOTP clients receives a BOOTREQUEST message from a BOOTP client",
  "condition_status": "stated",
  "exception": null,
  "exception_status": "unknown",
  "scope": null,
  "action": "silently discards",
  "object": "the BOOTREQUEST message",
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

#### S36 ｜ 含条件或例外的规则 ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **77** 行 |
| 强度 / 极性 | `MAY` / `positive`（原文等级措辞：`may`）|
| 条件 / 例外 | `If a DHCP server is configured to support BOOTP clients` / `（无）` |
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
  "meaning": "已配置支持 BOOTP 客户端的 DHCP 服务器，可以被配置为提供静态地址、自动地址或两者。",
  "constraint": "it may be configured to supply static addresses, automatic addresses or both",
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
  "meaning": "The consistency checks specified in Section 2.1 should be performed by the relay agent.",
  "constraint": "SHOULD be performed by the relay agent",
  "span": 773,
  "action": "performed",
  "object": "The consistency checks specified in Section 2.1",
  "strength": "SHOULD",
  "polarity": "positive",
  "keyword_raw": "SHOULD",
  "condition": "",
  "exception": "",
  "cross_ref": "Section 2.1",
  "cross_ref_status": "unresolved"
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

#### S38 ｜ 被 L1/L2 拒收的候选 ｜ 最终状态：**拒收**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1542.txt` |
| 章节 | 5.4 Strategy for Delivery of BOOTREPLY Messages................. 20 |
| 原始行号 | 第 **93** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | （未进入 L1：已被拒收） |
| 拒收原因 | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「BOOTP relay agents」（该行：agents formerly called "BOOTP forwarding agents") was not clearly） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      90| 
      91|    Unfortunately, the original BOOTP specification [1] left some issues
      92|    of the protocol open to question.  The exact behavior of BOOTP relay
>>    93|    agents formerly called "BOOTP forwarding agents") was not clearly
      94|    specified.  Some parts of the overall protocol specification actually
      95|    conflict, while other parts have been subject to misinterpretation,
      96|    indicating that clarification is needed.  This memo addresses these
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1542.txt",
  "entity": "BOOTP relay agents",
  "meaning": "原 BOOTP 规范未明确规定该类中继代理的精确行为。",
  "constraint": "",
  "span": 93,
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
  "subject": "BOOTP relay agents",
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
  "action": "BOOTP relay agents",
  "object": "BOOTP relay agents",
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

#### S39 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

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
  "meaning": "动态主机配置协议，提供一种使用 TCP/IP 协议族向主机传送配置参数的机制。",
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

#### S40 ｜ ★ 描述性（不成规则：动作/对象缺失或为主体名占位） ｜ 最终状态：**待审**

| 项 | 内容 |
|---|---|
| 协议 / 文件 | `DHCPv4` / `rfc1534.txt` |
| 章节 | （未定位到章节标题） |
| 原始行号 | 第 **33** 行 |
| 强度 / 极性 | `None` / `None`（原文等级措辞：`（无）`）|
| 条件 / 例外 | `（无）` / `（无）` |
| 作用域 | `（无）` |
| 跨章节引用 | （无）|
| L1 验证 | **pending** ｜ 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**① RFC 原文证据 + 前后上下文**（`>>` 为抽取所在行）

```
      30|    The Dynamic Host Configuration Protocol (DHCP) provides a mechanism
      31|    for transmitting configuration parameters to hosts using the TCP/IP
      32|    protocol suite.  The format of DHCP messages is based on the format
>>    33|    of BOOTP messages, so that, in certain circumstances, DHCP and BOOTP
      34|    participants may exchange messages.  This document specifies the ways
      35|    in which DHCP and BOOTP participants may interoperate.
      36| 
```

**② LLM 原始抽取结果**

```json
{
  "doc": "rfc1534.txt",
  "entity": "BOOTP",
  "meaning": "其报文格式被 DHCP 报文格式所基于的协议，从而使 DHCP 与 BOOTP 参与方在特定情形下可以交换报文。",
  "constraint": "",
  "span": 33,
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
  "subject": "BOOTP",
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
  "action": "BOOTP",
  "object": "BOOTP",
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


## 二、专项统计

### A. 强度未知分析

**总量**：强度未知 **495** 条（已确认强度 320 条）

| 原因分类 | 条数 | 占比 |
|---|---:|---:|
| ★ 证据行未见等级词（★ 不等于原文无强度 ⇒ **待人工重判**） | 436 | 88.1% |
| ★ 证据行含等级词但**模型漏抽**（真缺陷） | 58 | 11.7% |
| 原文为**小写**等级词（★ RFC 8174：普通英语 ⇒ **不构成**规范强度） | 1 | 0.2% |

> ★ **结论**：绝大多数强度未知是「**原文确实没有明确规范强度**」⇒ ⇒ **不是抽取缺陷**
> ⇒ ⇒ ★ **不得**为提高正式入库率而**强行补充强度**

**每类的真实样例（各 3 条）**

**★ 证据行未见等级词（★ 不等于原文无强度 ⇒ **待人工重判**）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 63 | RTSP URL | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 64 | Conference Identifiers | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 65 | Session Identifiers | `（无）` | False | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**★ 证据行含等级词但**模型漏抽**（真缺陷）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| rtsp | rfc2326.txt | 302 | parties in the conference | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 310 | RTSP requests | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |
| rtsp | rfc2326.txt | 315 | key words | `（无）` | True | 规范强度未定（不得凭推测赋值）；极性未定（不得凭推测赋值） |

**原文为**小写**等级词（★ RFC 8174：普通英语 ⇒ **不构成**规范强度）**

| 协议 | 文件 | 行 | 实体 | 原文等级措辞 | 证据行含等级词 | L1 原因 |
|---|---|---:|---|---|---|---|
| DHCPv4 | rfc1534.txt | 96 | server | `cannot` | False | 规范强度未定（不得凭推测赋值）；关键词无法归一：'cannot' |

### B. 拒收质量分析

**总拒收**：11 条

| 拒收原因分类 | 条数 | 判定 |
|---|---:|---|
| 按 span **单行**同现未命中（★ 跨行是否真无支持**待人工重判**） | 11 | ⚠ **可能是误拒收**（需人工判断） |

**全部拒收样本（供逐条判断是否误拒收）**

| 协议 | 文件 | 行 | 实体 | 拒收原因 |
|---|---|---:|---|---|
| rtsp | rfc2326.txt | 923 | Negative values | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Negative values」（该行：The beginning of a presentation corresponds to 0.0 seconds. Negative） |
| rtsp | rfc2326.txt | 1610 | New methods | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「New methods」（该行：methods may be defined in the future. Method names may not start with） |
| sip | rfc3261.txt | 446 | Session Initiation Protocol (SIP) | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Session Initiation Protocol (SIP)」（该行：Initiation Protocol (SIP) works in concert with these  |
| sip | rfc3261.txt | 1114 | B2BUA | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「B2BUA」（该行：it has established.  Since it is a concatenation of a UAC and） |
| sip | rfc3261.txt | 1749 | field values, parameter names, and parameter values | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「field values, parameter names, and parameter values」（该行：particular header field, field value |
| DHCPv4 | rfc1542.txt | 93 | BOOTP relay agents | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「BOOTP relay agents」（该行：agents formerly called "BOOTP forwarding agents") was not clearly） |
| DHCPv4 | rfc1542.txt | 106 | Dynamic Host Configuration Protocol (DHCP) | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Dynamic Host Configuration Protocol (DHCP)」（该行：document also apply to extensions to BOOTP su |
| DHCPv4 | rfc1542.txt | 725 | Any Internet host or router which provides BOOTP relay-agent capability | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「Any Internet host or router which provides BOOTP relay-agent capability」（该行：Any Internet hos |
| DHCPv4 | rfc1542.txt | 746 | unicast datagram with an IP destination not matching any of the router's IP addresses | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「unicast datagram with an IP destination not matching any of the router's IP addresses」（该行：In |
| DHCPv4 | rfc1542.txt | 754 | hosts or routers which support a BOOTP relay agent | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「hosts or routers which support a BOOTP relay agent」（该行：Hosts and routers are usually require |
| DHCPv4 | rfc1542.txt | 754 | BOOTREQUEST messages from legal IP source addresses | ★ 可核对闸：**证据跨度（±3 行）内**不含实体名「BOOTREQUEST messages from legal IP source addresses」（该行：Hosts and routers are usually requir |

### C. 归并正确性

#### C1 · 同一 Rule Slot 的多声明（真实）

> ★ **N/A**：★ 在「**占位禁止 + 描述分流**」生效后，真实数据里**不存在**同一 Rule Slot 的多条声明
> ⇒ ⇒ 此前统计到的 61 组归并，**主要是占位式 Rule Slot 造成的假归并**
> ⇒ ⇒ **不人工制造样本**（★ 按要求）

| 协议 | 主体 | 动作 | 对象 | 条件 | 同槽位声明数 | 行号 |
|---|---|---|---|---|---:|---|
| （无） | — | — | — | — | 0 | — |

#### C2 · 相反极性声明（同一槽位）

> ★ **本次真实运行中未出现**「同一槽位 + 相反极性」的组合 ⇒ ⇒ 标 **N/A**（**不人工制造**）


## 三、专项核查：跨章节引用定位失败（全部）

| 协议 | 文件 | 行 | 实体 | 引用 | 原文 |
|---|---|---:|---|---|---|
| rtsp | rfc2326.txt | 1024 | ISO 10646 | `RFC 2279` | >>  1024|    RTSP is a text-based protocol and uses the ISO 10646 character set in |
| smtp | rfc4954.txt | 147 | initial-response | `Section 4 of [BASE64]` | >>   147|           initial-response: An optional initial client response.  If |
| smtp | rfc4954.txt | 202 | server | `Section 5.1 of [SASL]` | >>   202|           an initial client response, the server MUST proceed as defined |
| smtp | rfc4954.txt | 211 | client | `Section 5.1 of [SASL]` | >>   211|           the client MUST NOT use the initial response parameter (and |
| DHCPv4 | rfc1542.txt | 816 | relay agent | `[1] (Section 8, sixth paragraph)` | >>   816|    NOT be modified.  The relay agent MUST NOT, under any circumstances, |

## 四、专项核查：代词主体隔离（全部）

| 协议 | 文件 | 行 | 实体 | 发布闸 | L1 |
|---|---|---:|---|---|---|
| smtp | rfc4954.txt | 517 | it | 隔离 （主体不可靠（it）；校验结论非已证实（pending））| pending |

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
| S01 | rtsp | 已确认强度的规范规则 | 待审 |  |  |
| S02 | rtsp | 已确认强度的规范规则 | 确认 |  |  |
| S03 | rtsp | 已确认强度的规范规则 | 确认 |  |  |
| S04 | rtsp | 含条件或例外的规则 | 待审 |  |  |
| S05 | rtsp | 含条件或例外的规则 | 待审 |  |  |
| S06 | rtsp | 跨章节引用规则 | 待审 |  |  |
| S07 | rtsp | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S08 | rtsp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S09 | rtsp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S10 | rtsp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S11 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S12 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S13 | sip | 已确认强度的规范规则 | 确认 |  |  |
| S14 | sip | 强度未知（被隔离）候选 | 待审 |  |  |
| S15 | sip | 强度未知（被隔离）候选 | 待审 |  |  |
| S16 | sip | 含条件或例外的规则 | 确认 |  |  |
| S17 | sip | 含条件或例外的规则 | 待审 |  |  |
| S18 | sip | 跨章节引用规则 | 待审 |  |  |
| S19 | sip | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S20 | sip | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S21 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S22 | smtp | 已确认强度的规范规则 | 待审 |  |  |
| S23 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S24 | smtp | 含条件或例外的规则 | 待审 |  |  |
| S25 | smtp | 含条件或例外的规则 | 待审 |  |  |
| S26 | smtp | 跨章节引用规则 | 待审 |  |  |
| S27 | smtp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S28 | smtp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S29 | smtp | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S30 | smtp | 已确认强度的规范规则 | 确认 |  |  |
| S31 | DHCPv4 | 已确认强度的规范规则 | 待审 |  |  |
| S32 | DHCPv4 | 已确认强度的规范规则 | 待审 |  |  |
| S33 | DHCPv4 | 已确认强度的规范规则 | 确认 |  |  |
| S34 | DHCPv4 | 强度未知（被隔离）候选 | 待审 |  |  |
| S35 | DHCPv4 | 含条件或例外的规则 | 待审 |  |  |
| S36 | DHCPv4 | 含条件或例外的规则 | 待审 |  |  |
| S37 | DHCPv4 | 跨章节引用规则 | 待审 |  |  |
| S38 | DHCPv4 | 被 L1/L2 拒收的候选 | 拒收 |  |  |
| S39 | DHCPv4 | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
| S40 | DHCPv4 | ★ 描述性（不成规则：动作/对象缺失或为主体名占位） | 待审 |  |  |
