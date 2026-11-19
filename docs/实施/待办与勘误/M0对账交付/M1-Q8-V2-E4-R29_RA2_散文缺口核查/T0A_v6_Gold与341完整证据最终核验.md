# T0-A v6 Gold 与 341 完整证据最终核验

## 一、三条独立核验

| 对象 | 主体 | 强度 | 动作/对象 | 时点/条件 | 结论 |
|---|---|---|---|---|---|
| `-30-1` | SMTP server and client | — | use TLS for private authenticated communication | — | supported |
| `-30-2` | SMTP agents | — | protect communications from eavesdroppers/attackers | — | supported |
| 341 | clients and servers | MUST | discard knowledge obtained prior to handshake | upon completion of handshake | supported |

原文 341–343：`For this reason, clients and servers MUST discard any knowledge obtained prior to the start of the TLS handshake upon completion of the TLS handshake.`（跨行）

## 二、207 与 341 必须分开

| 条 | 主体 | 知识范围 |
|---|---|---|
| 207/212 | server | 从 **client** 获得、非 TLS 协商所得 |
| 341 | clients and servers | 握手**开始前**获得的知识 |

两者都含 discard knowledge，但主体与范围不同，**不得合并**。本轮 Norm/Fact 中它们是两条（fact_id 不同），符合要求。

## 三、结论

三条均获得完整、可定位、可回溯的 Evidence，且来自同一份 v6 Raw。这是 T0-A 首次达成。
