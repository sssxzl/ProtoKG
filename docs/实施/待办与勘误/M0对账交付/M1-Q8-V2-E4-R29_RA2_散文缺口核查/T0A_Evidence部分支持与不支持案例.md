# T0-A Evidence 部分支持与不支持案例

## 一、结论分布

| 状态 | 条数 |
|---|---|
| supported | 27 |
| partially_supported | 2（p8、p13） |
| multi_source_pending | 1（p7） |
| unsupported / contradicted | 0 |

29 条已定位中，27 条为整句引用且语义对得上；2 条引用不完整。

## 二、p8：引用截在半句

命题：「服务器以 220、501 或 454 之一回复」。

模型给的 quote 只有 `…the server responds with one of the following reply codes:`，三个码在其后的 107–109 行。

- 原 quote 定位：104–105（真实存在，但不是完整证据）；
- 扩展引用：104–109，含 `220 Ready to start TLS` / `501 Syntax error` / `454 TLS not available`，`locate_quote` 返回 `exact_match`。

判定 `partially_supported`，侧车记录扩展引用。

## 三、p13：530 义务引用只剩尾巴

命题：「要求客户端先 TLS 协商的服务器，对除 NOOP、EHLO、STARTTLS、QUIT 外的每条命令应返回 530」。

原 quote 仅 58 字符：`to every command other than NOOP, EHLO, STARTTLS, or QUIT.`——没有 530，也没有条件。

原文 146–150：

```
commands.  In this case, the server SHOULD return the reply code:
530 Must issue a STARTTLS command first
to every command other than NOOP, EHLO, STARTTLS, or QUIT.  If the ...
```

扩展引用 146–150 经 `locate_quote` 验证为 `exact_match`，含回复码与例外列表。

但条件的先行词（「服务器要求先 TLS 协商」）在 143–145 行，不在该区间内。因此仍判 `partially_supported`：证据补强了，但「完整支持」需要连同 143–145 一起看。

侧车记录两条：`corrected_span` 与需一并阅读的前置区间。

## 四、其余 27 条为什么算 supported

抽查标准（逐条按同口径看）：

1. quote 是完整句子/完整列举，不是半句；
2. 主体与动作与命题一致（如 p22 server MUST discard / p23 client MUST discard 分开两条）；
3. 义务强度词与命题一致（MUST / MUST NOT / SHOULD / MAY 逐条对照）；
4. 条件与例外在 quote 内（如 p20 的 “other than a QUIT command” 在引文尾部）；
5. 未发现命题添加原文没有的保证。

这是人工逐条阅读的结论，不是 `exact_match` 自动升级。

## 五、不支持的 0 条

没有发现「引用存在但语义相反」或「完全无关」的情况。也就是说：现有 quote 没有污染知识，问题集中在 2 条引用不完整。
