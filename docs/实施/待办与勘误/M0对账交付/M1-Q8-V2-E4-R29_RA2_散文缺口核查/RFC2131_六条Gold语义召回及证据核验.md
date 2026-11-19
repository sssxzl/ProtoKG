# RFC 2131 六条 Gold 语义召回与证据核验

## 一、按语义匹配（不是行号重叠）

| Gold | 预期 | 实际 | 判定 |
|---|---|---|---|
| D1 | client identifier 子网内唯一 + 后续同值 | 495「必须唯一」、497「必须使用同一标识符」 | **命中（2 条）** |
| D2 | 服务器不应复用已提供地址（Therefore 承接） | 仅 1817「SHOULD retain record of initialization parameters」，语义不同 | **未命中** |
| D3 | flags 保留位必须置 0 | 1372 只讲 BROADCAST 位检查 | **未命中** |
| D4 | siaddr 表示下一步引导服务器 | 全文 74 条中无 siaddr 相关 | **未命中** |
| D5 | ciaddr 在 DHCPREQUEST 中必须为 0 | 959「客户端不得填写 ciaddr」 | **命中（近似）** |
| D6 | DHCPDISCOVER 中不得填 server identifier | 2150「DHCPREQUEST 中 MUST NOT 含 server identifier」 | **部分（消息类型不同）** |

## 二、三层召回

| 层 | 结果 |
|---|---|
| 第一阶段 Raw 语义召回 | **2/6 命中 + 1 部分 + 3 漏** |
| Norm / Fact 保留 | 2/6（D1、D5 进入 Norm；D6 部分条目进入） |
| Evidence 已验证 | 2/6（D1 的 495/497、D5 的 959 均定位成功） |

## 三、结论

v6 在 DHCP 全文上出现了**实质性的规范义务漏抽**，不是定位问题：

- D2 承接型 SHOULD NOT 完全未出现——这与 RFC 3207 上 341 的成功形成反差；
- D3 保留位 MUST 被相邻的 BROADCAST 语义覆盖；
- D4 定义类知识整体缺失。

不得把这三条记为"Evidence 未完成"，它们根本没有 Raw 命题。

## 四、登记

```
rfc2131_gold_raw_recall 2/6（+1 部分）
rfc2131_gold_verified 2/6
```
