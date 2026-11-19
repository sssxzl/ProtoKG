# T0-A 归档修正与完整引用侧车

## 一、82/89 两条改配

| span | 原引用 | 命题 | 改配引用 | 定位 |
|---|---|---|---|---|
| 82 | `(2) the EHLO keyword value … is STARTTLS` | 关键字告知客户端服务器能协商 TLS | `The STARTTLS keyword is used to tell the SMTP client that the SMTP server is currently able to negotiate the use of TLS.` | 92–93 |
| 89 | `(4) a new SMTP verb … is defined` | 命令不带参数 | `The format for the STARTTLS command is: STARTTLS with no parameters.` | 98–102 |

原引用保留在旧 CSV，身份未动。

## 二、120 字符截断的定性

确认是**报告生成时切片**（`quote[:120]`），不是侧车缺数据。

新增 `T0A_v6_Evidence完整引用侧车.json`：28 条全部为完整引用，最短 58 字符，无截断。

## 三、来源台账（可重叠，不求和）

| 维度 | 条数 |
|---|---|
| 第一阶段模型原始命题 | 28 |
| 模型/二阶段原始 Quote | 10 |
| 由 span 行文本补全 | 16 |
| 确定性重锚（168→177、226→235） | 2 |
| 人工改配引用 | 8（210/213/234/310/353/82/89/341） |
| 空白/大小写归一化 | 2（210、285） |
| 最终 supported | 28 |

**这些数不能相加**：一条可以同时是「原始命题 + 人工改配 + 归一化」。上一版文档的 27+4、20+2+5+5 就是混了口径，此处作废。

## 四、关闭

```
T0_A_v6_semantic_support_28_28_verified
T0_A_single_rfc_closed
single_reviewer_only
cross_rfc_generalization_not_verified
```
