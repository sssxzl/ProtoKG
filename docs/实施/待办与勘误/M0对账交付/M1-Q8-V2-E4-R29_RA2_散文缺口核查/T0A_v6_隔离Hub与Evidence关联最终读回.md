# T0-A v6 隔离 Hub 与 Evidence 关联最终读回

## 一、读回

隔离目录重建后：

| 项 | 值 |
|---|---|
| Fact | 28 |
| Claim | 28 |
| 唯一 FactID | 25 |
| 实体 | 13 |
| 每条 Claim 的 Evidence | 均有 verified_span（30–355 区间） |

## 二、四 Claim 的 Fact

`f2_35eb41ca…`：80（名称）、82（关键字）、89（动词）、234（Submission 端口有效性）。

第四条 234 原来的引用是 server MUST NOT return，现已改为 4.3 节首句。四条 Claim 各自独立，不是身份碰撞。

## 三、侧车字段

保留 `model_span`、`verified_span`、`quote_origin`（27 model / 4 corrected，其中本轮新增 5 条改配计入 corrected）。

缺侧车时读回为 None，不会被当作已验证。

## 四、边界

官方 Hub 仍只存 evidence_summary，完整 quote 在侧车。
