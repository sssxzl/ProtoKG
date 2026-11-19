# T0-A p7 / p8 / p13 完整 Evidence 收口

## 一、三条全部升级为 supported，且都是连续单段引用

| 命题 | 原引用 | 修正后区间 | 定位 | 覆盖了什么 |
|---|---|---|---|---|
| p7 STARTTLS 命令格式且无参数 | 无（multi_source） | **98–102** | exact_match | `The format for the STARTTLS command is:` + `STARTTLS` + `with no parameters.` |
| p8 服务器回复 220/501/454 | 104–105（止于冒号） | **104–109** | exact_match | 引导句 + 三条回复码 |
| p13 条件性 530 义务 | 150（仅尾巴） | **144–150** | exact_match | 非公开引用服务器前提 + SHOULD + 530 + NOOP/EHLO/STARTTLS/QUIT 例外 |

## 二、p7：不需要拆 Schema

原文第 4 节 98–102 行本身就是一句连续描述：格式、命令字、无参数三段在同一段里。之前模型返回 `multi_source`，是因为它按"两条独立要求"组织输出，而不是原文真的分散。

因此无需改 Evidence 契约，单段引用即可支持复合命题。

## 三、p13：条件没有被扩大

144–150 的原文是：

```
A SMTP server that is not publicly referenced may choose to require
that the client perform a TLS negotiation before accepting any
commands.  In this case, the server SHOULD return the reply code:
530 Must issue a STARTTLS command first
to every command other than NOOP, EHLO, STARTTLS, or QUIT.
```

四要素齐备：适用范围（非公开引用）、条件（要求先 TLS）、强度（SHOULD）、例外列表。

**没有**把它读成「所有服务器必须返回 530」——原文是 SHOULD，且限定对象。命题文本本身也没这么写。

## 四、p8

104–109 包含 220 / 501 / 454 三条码，与命题「以 220、501、454 之一回复」逐项对应。

## 五、修正性质

三条都属于「人工审查 + 确定性扩展」，不是模型自己给的 quote。侧车 v2 分别记录：`model_quote`、`model_span`、`corrected_quote`、`corrected_span`、`match`、`origin`。

原始 v4 输出与第一轮回填结果未被覆盖。
