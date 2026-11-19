# 跨 RFC 真实模型抽取结果（RFC 2131）

## 一、调用

| 项 | 值 |
|---|---|
| 第一阶段 | 1 次，2 块，输入 1 934 / 输出 1 997 |
| 第二阶段 | 1 次，12 条命题 |
| 失败的调用 | 0 |

## 二、抽取结果

12 条 Norm：

| 行 | 主题 |
|---|---|
| 488 / 494 | client identifier 定义 |
| 498 / 499 | client identifier MUST unique / MUST 一致 |
| 508 / 510 | siaddr 语义 |
| 1698 | ciaddr MUST be zero；requested IP MUST 填充 |
| 1712 | **servers SHOULD NOT reuse offered addresses** |
| 1716 | server identifier 总返回自身地址 |
| 1718 | server identifier MUST NOT 填；requested IP MUST 填 |

## 三、预登记 Gold 命中

| Gold | 结果 |
|---|---|
| G-A（1712 SHOULD NOT） | **命中**，强度 SHOULD NOT 保留 |
| G-B（498/499 MUST） | **命中**，两条 MUST 分别成条 |

## 四、普通知识是否漏抽

本样本 2 块内共抽 12 条，覆盖定义与规范两类；未见短定义被系统性丢弃（488/494/508/510 都保留）。

## 五、承接前文是否被误当条件

1712 条只把 `SHOULD NOT reuse offered addresses` 记为义务，未把前面的 `Therefore, the servers may not receive…` 写成条件。

## 六、限制

2 块、单一协议、样本极小。**不能**据此说 v6 已跨 RFC 泛化。
