# R15 mixed_or_uncertain 专项分析

> ★ 本文件属**已接触数据的诊断**，★ 不是独立验证
> ★ R14 首次评估结果保持冻结，★ 未重算

---

## 一、已验证事实

### 1.1 数量

| 项 | 值 |
|---|---:|
| 机器预测为 `mixed_or_uncertain` | **15 条** |
| 其中 Gold 为 `normative_rule_candidate` | **12 条** |
| 其中 Gold 为其他类型 | 3 条 |
| Gold 侧为 `mixed_or_uncertain` | 0 条 |

### 1.2 逐条核查（★ 八项检查）

| candidate_id | 协议 | 跨度 | 机器 meaning | 机器 constraint | 原文含 BCP14 | meaning 承载 | constraint 承载 | 预测类型 | Gold 类型 | Gold 资格 | 判据理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| X-rtsp-rfc7826-01 | RTSP | 5388-5388 | 请求被建议只包含单个参数，以便客户端判断某个请求失败的原因 | 请求仅包含单个参数（RECOMMENDED） | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-rtsp-rfc7826-03 | RTSP | 5392-5392 | 允许（可以）禁止改变参数值 | 可以禁止改变参数值 | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-rtsp-rfc7826-06 | RTSP | 5397-5397 | 响应体必须只包含出错的参数 | 响应体只含出错参数 | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-rtsp-rfc7826-07 | RTSP | 5398-5398 | 否则不得返回响应体 | 否则不返回 body | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-sip-rfc2543-05 | SIP | 1829-1829 | 客户端可以通过在请求的 Expires 头中指明时间，来请求注册生命周期。 | Clients MAY request a registration lifetime by indicating the time in an Expires | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-sip-rfc3428-01 | SIP | 766-766 | 一种 SIP 请求类型，其签名请求与响应须携带被消息签名覆盖的 Date 头字段 | all signed MESSAGE requests and responses MUST contain a Date header field cover | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-sip-rfc3428-02 | SIP | 770-770 | 用来表示日期或时间不正确的 SIP 响应码 | Any message with a date older than several minutes in the past, or which is more | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-sip-rfc3428-03 | SIP | 772-772 | 在消息反复来自同一来源的情况下，允许不发送响应而直接丢弃消息 | in which case they MAY be discarded without sending a response | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-smtp-rfc3461-03 | SMTP | 1090-1090 | 传输 DSN 时可使用但其值必须为 NEVER 的 SMTP 参数 | its value MUST be NEVER | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-smtp-rfc3461-04 | SMTP | 1091-1091 | 可携带新生成的 envelope-id 使用的 SMTP 参数 |  | 是 | 有 | 无 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-smtp-rfc3461-05 | SMTP | 1092-1092 | 可与 ENVID 一同使用的 SMTP 参数 |  | 是 | 有 | 无 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |
| X-smtp-rfc6531-01 | SMTP | 139-139 | 术语“UTF-8 string”用于指代 UTF-8 编码的 Unicode 字符（可能是也可能不是 ASCII 子集成员）。 |  | 否 | 有 | 无 | mixed_or_uncertain | protocol_descriptive_semantics | ineligible | ★ 含义务动词但无大写 BCP14 强度词且缺协议主体 ⇒ ★ **不确定**（★ 不得直接归为描述性） |
| X-smtp-rfc6531-02 | SMTP | 141-141 | UTF-8 所引用的标准 Unicode 编码形式规范文档。 |  | 否 | 有 | 无 | mixed_or_uncertain | non_protocol_metadata | not_applicable | ★ 含义务动词但无大写 BCP14 强度词且缺协议主体 ⇒ ★ **不确定**（★ 不得直接归为描述性） |
| X-smtp-rfc8098-02 | SMTP | 2010-2010 | 折叠空白语法元素，原文陈述现在的 ABNF 在若干处规定了 FWS 和 CFWS |  | 否 | 有 | 无 | mixed_or_uncertain | non_protocol_metadata | not_applicable | ★ 含义务动词但无大写 BCP14 强度词且缺协议主体 ⇒ ★ **不确定**（★ 不得直接归为描述性） |
| X-smtp-rfc8098-04 | SMTP | 494-494 | 解析 MDN 消息的实现，原文要求其必须将 OWS 解析为 "[CFWS]" | MDN parsers MUST parse it as "[CFWS]" | 是 | 有 | 有 | mixed_or_uncertain | normative_rule_candidate | eligible | ★ 含强度词但义务主体或行为不明确 ⇒ ★ 混合/不确定⇒ ★ 交人工复核 |

### 1.3 逐条结论的分类

★ 全部 15 条的 V2 判据理由均为同一模式：
★ 「陈述式规范句（条件从句 + 协议行为动词 + 协议参与方主体，★ 但无 BCP14 强度词）
★ ⇒ 适用规范规则通道，★ strength = unknown（★ 不擅自提升为 MUST）」

★ 因此判据**并非**完全无法识别规范语义：★ 它已判定「适用规范规则通道」，
★ 但因 `strength=unknown` 而最终归入 `mixed_or_uncertain`。

## 二、★ 专项结论（★ 不预设 12 条全为判据缺陷）

### 2.1 分类结果

| 子类 | 条数 | 判据 |
|---|---:|---|
| ★ **原文确含 BCP14 关键词，★ 但判据未识别** | 12 | ★ **A 类：规范强度词依赖过强**（★ 判据缺陷） |
| ★ 原文无 BCP14，★ 判据与 Gold 的规范义务理解不同 | 0 | ★ **E 类：分类契约不一致**（★ 需澄清） |
| ★ Gold 非规范义务类 | 3 | ★ 判 mixed 合理，★ 不算错误 |

### 2.2 三条可分别确认的事实

1. ★ **输入适配不是主因**：★ 这 15 条的机器 meaning 与 constraint 均已存在
   （★ 见上表「meaning 承载」「constraint 承载」两列），★ 判据有输入可用。
   ★ **排除 D 类作为这批错误的主因**。

2. ★ **判据的 strength 逻辑确实存在矛盾**：★ 判据已判「适用规范规则通道」
   （★ 即认定它是规范义务），★ 却因强度未知而归入 `mixed_or_uncertain`。
   ★ **若强度未知只意味着不能定级、★ 而非不是规范义务，★ 则该归类自相矛盾。**
   ★ 这是可核查的规则内部不一致，★ 不依赖对 Gold 的信任。

3. ★ **Gold 与判据的契约差异确实存在**：★ 原文无 BCP14 的那些候选，
   ★ 人工仍判为规范义务（★ 依据是行为义务而非关键词强度）。
   ★ **这属于「陈述式规范句是否算规范义务」的定义分歧，★ 不是判据的 bug。**

### 2.3 ★ 潜在误判反例（★ 必须一并考虑）

★ 若把「strength=unknown 的陈述式规范句」一律升级为 `normative_rule_candidate`，
★ 则以下情形会产生**反向误判**：

| 反例类型 | 说明 | 证据来源 |
|---|---|---|
| ★ 真正的描述性陈述句 | ★ 「X 表示某种标识符」类句子，★ 无行为义务 | ★ R3 基线中 `proposed_knowledge_kind=prose_semantics` 的 48 条 |
| ★ 元数据陈述句 | ★ 出版类别、作者、日期等 | ★ Gold 中的 `non_protocol_metadata` 8 条 |
| ★ 语法定义句 | ★ ABNF 与字段定义 | ★ Gold 中的 `protocol_syntax` 10 条 |

★ **本次 57 条中，★ 确实存在被判为 `mixed_or_uncertain` 而 Gold 属描述性或元数据类的情形**
（★ 见上表 Gold 非规范义务类部分），★ 这说明「一律升级」会引入反向错误。

## 三、限制

1. ★ 本专项基于已接触的 57 条，★ 只能作为诊断证据，★ **不能作为调参集之外的独立验证**。
2. ★ 未做逐条的原文语义重判，★ 只依据已有字段与判据理由。
3. ★ 未修改 V2 判据，★ 未重算 R14。

## 四、下一步

★ 改进方案见《R15_V2最小兼容改进方案.md》；★ 独立验证设计见
★ 《R15_新协议独立验证设计.md》。
