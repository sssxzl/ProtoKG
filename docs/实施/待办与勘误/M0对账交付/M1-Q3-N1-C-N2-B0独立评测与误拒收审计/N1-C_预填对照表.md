# N1-C · 预填对照表（A / B / 仲裁）

> 用途：**人工独立复核时的逐条对照**。A、B 为两次互不可见的独立判定；第三方仲裁对全部 50 条独立复核并逐条落裁定
> （本次 A/B 分歧为 0，故仲裁的作用是「三方复核」而非「消解分歧」）。
> ⚠️ 三方均由 LLM 扮演（不同上下文、互不可见）。`N1-C_人工审核发放说明.md` 第 4 条明确禁止 LLM 代填，
> 因此**本批标签不得计入人工真值、不得据此宣布 L2 语义质量达标**；仅供人工复核做参照基线。
> 执行细节见 `_prefill_backup/N1-C_预填说明.md`。

## 一、总体

| 口径 | 确认 | 拒收 | 其他 | 合计 |
|---|---:|---:|---:|---:|
| A（REV-A01） | 13 | 37 | 0 | 50 |
| B（REV-B01） | 13 | 37 | 0 | 50 |
| 冻结真值 | 13 | 37 | 0 | 50 |

- **双审一致 50/50（100%）**，分歧 **0** 条
- 第三方仲裁实际出具裁定 **50** 条；其余 0 条按 A=B 冻结
- 冻结真值的来源口径：`仲裁 > A=B > 单侧 > 未解决`（见 `scripts/p11_freeze_eval.py`）
- 协议分布：DHCPv4 15｜rtsp 16｜sip 16｜smtp 3
- 50 条锚点行已逐行回查 RFC 原文，**50/50 行号与文本一致**

## 二、逐条对照（末列留空，供你人工填写）

| # | sample_id | 协议 | 锚点行 | A | B | 仲裁后 | 判定要点（冻结依据） | ★ 人工 |
|---:|---|---|---:|---|---|---|---|---|
| 1 | `rfc1534.txt@1#1` | DHCPv4 | 38 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 1534:38-39 的 “vendor extensions” 字段在 BOOTP 中更名为 “options” 一句为被动… |  |
| 2 | `rfc1534.txt@1#2` | DHCPv4 | 48 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 1534:46-49 “will be referred to as a DHCPDISCOVER message” 是本文命… |  |
| 3 | `rfc1542.txt@1#1` | DHCPv4 | 27 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 1542:26-28 称原规范对 relay agent 行为仅给出 “only a general description”… |  |
| 4 | `rfc1542.txt@1#2` | DHCPv4 | 28 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 1542:28-29 “originally called BOOTP forwarding agents” 只是旧称括注（术… |  |
| 5 | `rfc1542.txt@1#3` | DHCPv4 | 31 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 1542:31-33 “this memo is reissued as RFC 1542” 为文档出版沿革说明，与协议行为义… |  |
| 6 | `rfc2131.txt@1#4` | DHCPv4 | 22 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点即 2131:22 “Abstract” 标题行，24-30 行 “provides a framework”“DHCP cap… |  |
| 7 | `rfc2132.txt@1#2` | DHCPv4 | 28 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2132:28-30 “The data items themselves are also called options” … |  |
| 8 | `rfc2326.txt@1#2` | rtsp | 36 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:36-39 “is intended to control…provide a means for choosing… |  |
| 9 | `rfc2326.txt@1309#0` | rtsp | 1309 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:1309 位于 1295 行起 Status-Code ABNF 枚举，“404 ; Not Found” 仅代码与… |  |
| 10 | `rfc2326.txt@1309#1` | rtsp | 1310 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:1310 仍属 1295 行起 Status-Code ABNF 枚举，“405 ; Method Not Allo… |  |
| 11 | `rfc2326.txt@1309#3` | rtsp | 1312 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:1312 属 Status-Code ABNF 枚举，“407 ; Proxy Authentication Req… |  |
| 12 | `rfc2326.txt@1309#5` | rtsp | 1314 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:1314 属 Status-Code ABNF 枚举，“410 ; Gone” 仅登记代码与助记名，不构成义务。 |  |
| 13 | `rfc2326.txt@2030#0` | rtsp | 2034 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:2033-2036 “a PLAY would still resume…as it is assumed that… |  |
| 14 | `rfc2326.txt@2030#3` | rtsp | 2056 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:2056-2059 “The GET_PARAMETER request retrieves the value o… |  |
| 15 | `rfc2326.txt@2030#4` | rtsp | 2092 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:2092 是标题 “10.9 SET_PARAMETER”，2094-2095 “This method reque… |  |
| 16 | `rfc2326.txt@2747#3` | rtsp | 2832 | ✅确认 | ✅确认 | ✅确认 | 锚点 2326:2834-2835 “servers should not send Expires dates more than… |  |
| 17 | `rfc2326.txt@2747#4` | rtsp | 2828 | ✅确认 | ✅确认 | ✅确认 | 锚点 2326:2830-2831 “an origin server should use an Expires date tha… |  |
| 18 | `rfc2326.txt@3499#0` | rtsp | 3505 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:3504-3506 “The following examples are not to be used as a … |  |
| 19 | `rfc2326.txt@5115#0` | rtsp | 5117 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:5117-5118 在 5103 行起 Full Copyright Statement 内，“procedures… |  |
| 20 | `rfc2326.txt@5115#1` | rtsp | 5122 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:5121-5122 “perpetual and will not be revoked by the Intern… |  |
| 21 | `rfc2326.txt@587#1` | rtsp | 600 | ✅确认 | ✅确认 | ✅确认 | 锚点 2326:598-601 “If the recipient…does not understand the request…… |  |
| 22 | `rfc2326.txt@587#3` | rtsp | 602 | ✅确认 | ✅确认 | ✅确认 | 锚点 2326:602-603 “The server SHOULD list the methods it supports us… |  |
| 23 | `rfc2326.txt@587#5` | rtsp | 610 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2326:610 “may be identified by an RTSP URL” 小写 may 表可能性、被动无主体，属… |  |
| 24 | `rfc2563.txt@1#0` | DHCPv4 | 29 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2563:28-31 “Operating Systems are now attempting…some OS's are … |  |
| 25 | `rfc2563.txt@1#1` | DHCPv4 | 32 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2563:32-34 “will not allow the OS to communicate with anything … |  |
| 26 | `rfc2563.txt@1#2` | DHCPv4 | 34 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2563:36-38 “DHCP servers are able to tell clients…” 是能力描述。 |  |
| 27 | `rfc2939.txt@1#1` | DHCPv4 | 30 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2939:29-33 摘要 “provides a framework for passing configuration i… |  |
| 28 | `rfc2939.txt@1#2` | DHCPv4 | 31 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2939:34 “The data items themselves are also called options” 为术语… |  |
| 29 | `rfc2939.txt@1#3` | DHCPv4 | 33 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2939:36-38 “messages are identified by the DHCP Message Type op… |  |
| 30 | `rfc2939.txt@1#4` | DHCPv4 | 34 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 2939:37 “option (option code 51)” 为选项编号登记性注解，与 34 行定义同属定义性文本。 |  |
| 31 | `rfc3004.txt@1#5` | DHCPv4 | 63 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3004:63 是标题 “2. Requirements Terminology”，65-67 “key words…are … |  |
| 32 | `rfc3261.txt@1#4` | sip | 50 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:47-54 “SIP invitations…carry session descriptions”“SIP run… |  |
| 33 | `rfc3261.txt@10452#0` | sip | 10456 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:10456 是标题 “21.4.14 416 Unsupported URI Scheme”，10458-10459… |  |
| 34 | `rfc3261.txt@10452#5` | sip | 10487 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:10487-10490 “if a desirable extension is not listed…server… |  |
| 35 | `rfc3261.txt@12767#0` | sip | 12772 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:12775 “disp-param = handling-param / generic-param” 属 1276… |  |
| 36 | `rfc3261.txt@12767#2` | sip | 12776 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:12776-12778 “handling-param = handling EQUAL ( optional / … |  |
| 37 | `rfc3261.txt@12767#3` | sip | 12777 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:12780 “disp-extension-token = token” 是 ABNF 子产生式定义，无主体与强度词… |  |
| 38 | `rfc3261.txt@12767#4` | sip | 12779 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:12782-12783 “Content-Encoding = ( Content-Encoding / e ) H… |  |
| 39 | `rfc3261.txt@12767#5` | sip | 12782 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 3261:12785-12786 “Content-Language = … language-tag *(COMMA lan… |  |
| 40 | `rfc3261.txt@3893#2` | sip | 3902 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:3902-3903 “UAs MUST assign values to the dialog ID compone… |  |
| 41 | `rfc3261.txt@3893#4` | sip | 3911 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:3908-3912 “MUST copy all Record-Route…and MUST maintain th… |  |
| 42 | `rfc3261.txt@3893#5` | sip | 3912 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:3912-3913 “The UAS MUST add a Contact header field to the … |  |
| 43 | `rfc3261.txt@5893#0` | sip | 5899 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:5899-5900 “The request method MUST NOT be included in the … |  |
| 44 | `rfc3261.txt@5893#2` | sip | 5910 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:5908-5911 “If…the copy contains no Content-Length header f… |  |
| 45 | `rfc3261.txt@5893#3` | sip | 5915 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:5915-5918 “A stateful proxy MUST create a new client trans… |  |
| 46 | `rfc3261.txt@5893#5` | sip | 5925 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:5924-5926 “Timer C MUST be set…The timer MUST be larger th… |  |
| 47 | `rfc3261.txt@8085#3` | sip | 8100 | ✅确认 | ✅确认 | ✅确认 | 锚点 3261:8099-8101 “This parameter MUST contain the source address … |  |
| 48 | `rfc4954.txt@1091#1` | smtp | 1096 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 4954:1095-1096 在 1087 行起 Intellectual Property 节内，“Information … |  |
| 49 | `rfc4954.txt@1091#2` | smtp | 1098 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 4954:1098-1103 “Copies of IPR disclosures made to the IETF Secr… |  |
| 50 | `rfc4954.txt@1091#3` | smtp | 1102 | ❌拒收 | ❌拒收 | ❌拒收 | 锚点 4954:1102-1103 “can be obtained from the IETF on-line IPR repos… |  |

## 四、13 条 confirmed 的字段缺陷

| 缺陷 | 条数 | 说明 |
|---|---:|---|
| 候选 `normative_subject` 为空 | 2 | 被动句未解析承担者 |
| 候选 `strength` 为空 | 0 | 原文无 2119 关键词或候选未抽 |
| 原文带明确条件、候选 `condition` 为空 | 7 | 条件抽取缺口 |
| 候选 `condition` 已填 | 0 | 50 条中仅此数 |

