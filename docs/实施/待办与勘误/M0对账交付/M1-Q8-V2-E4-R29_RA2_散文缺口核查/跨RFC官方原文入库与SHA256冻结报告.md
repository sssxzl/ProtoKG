# 跨 RFC 官方原文入库与 SHA256 冻结

## 一、来源与哈希

| RFC | URL | 原始字节 SHA256 | 字符数 |
|---|---|---|---|
| 9112 | `https://www.rfc-editor.org/rfc/rfc9112.txt` | `e4f426bac6206b67…`（全长 `e4f426ba…9387`） | 109 910 |
| 9293 | `https://www.rfc-editor.org/rfc/rfc9293.txt` | `6d9ac8be4b0286f8…` | 263 692 |

获取时间：2026-11-20 00:09（GMT+8）。仅使用 RFC Editor 官方 TXT，未用 HTML/PDF/镜像。

## 二、处理规则

- 保留原始文件字节（只读，`kb/_external/rfc/`），不改现有协议目录；
- 解码 UTF-8（含 BOM），`\r\n` → `\n`；
- 行号 = `split("\n")` 序号，与项目既有口径一致；
- 页眉页脚不剥离（与 RFC 3207/2131 处理一致），避免行号漂移；
- 规范化文本 SHA256 与原始字节哈希分别登记。

## 三、状态

```
cross_rfc_inputs_frozen   # 仅 9112、9293 的原文冻结
```

Gold 预登记与容量试验**未进行**（本轮预算耗尽），因此未执行这两份 RFC。
