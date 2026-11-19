# D4 Canonical 与 Evidence 完整闭环

## 一、链路

```
RFC 2131 第 541 行
  → structural_extract.table_rows（字段名/长度/说明）
  → field Norm（content: "4 | optional: IP address…"）
  → map_norm_to_facts
  → Fact(syntax) + Fact(definition)
  → Claim ×2 → Evidence ×2（#@541）
  → 隔离 Hub 构建 → 读回 4 Fact / 2 实体
```

## 二、Evidence 检查

| 项 | 结果 |
|---|---|
| Quote 真实存在 | 是（541 行原文） |
| 可确定性定位 | 是（行号唯一） |
| 完整支持定义 | 是（说明字段为"下一步引导服务器地址"） |
| 来源 SHA256 | `a043b705…`（RFC 2131 冻结原文） |
| quote_origin | `structural`（非模型输出） |

## 三、判定

```
structural_d4_canonical_evidence_verified
```

## 四、仍存限制

- subject 类型沿用 `header`（DHCP 字段不是邮件头，属旧通道遗留）；
- definition 文本取自表格说明列，未含字段长度以外的语义（如"可为 0"），原文表格本身也没写。
