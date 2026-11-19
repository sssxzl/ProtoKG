# 跨 RFC 小样本试验设计与预登记

## 一、样本

| 项 | 值 |
|---|---|
| RFC | RFC 2131（DHCP），与 SMTP 不同协议 |
| 原文 SHA256 | 见 `T0A_跨RFC_20261119/SHA256清单.json` |
| 块 | 2 块：行 480–530（普通规范），行 1690–1720（承接型） |
| 模型 / 参数 | deepseek-flash，thinking=disabled，max_tokens=8000 |
| Prompt | v6，不改 |
| 请求计划 | 第一阶段 1 次（2 块同批）、第二阶段 1 次 |

## 二、预登记 Gold（运行前固定）

| 编号 | 行 | 内容 | 类型 |
|---|---|---|---|
| G-A | 1711–1712 | `servers SHOULD NOT reuse offered addresses`（句首 Therefore 承接） | 承接型规范义务 |
| G-B | 498–501 | `client identifier … MUST be unique … MUST use that same identifier` | 普通规范句 |

评估标准：Raw 是否产出该命题；主体/动作/对象/强度/条件是否正确；是否有短定义漏抽；承接前文是否被误当条件。
