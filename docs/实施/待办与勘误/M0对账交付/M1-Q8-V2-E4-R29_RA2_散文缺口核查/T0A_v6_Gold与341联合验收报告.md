# T0-A v6 Gold 与 341 联合验收

## 一、同一份 v6 Raw

| 对象 | 命题来源 | Evidence | 结论 |
|---|---|---|---|
| Gold `-30-1` | v6 Raw span 22 | quote 定位于 [30,33] | 语义与证据一致 |
| Gold `-30-2` | v6 Raw span 25 | quote 定位于 [33,35] | 语义与证据一致 |
| 341 行 | v6 Raw span 341 | 原文 341–343 | 主体/动作/条件保留 |

三条全部来自 v6 自己抽出的命题，未从 v4 借用。

## 二、341 义务复核

原文：`For this reason, clients and servers MUST discard any knowledge obtained prior to the start of the TLS handshake upon completion of...`

v6 产出：`action=discard any knowledge obtained prior to the start of the TLS handshake`，`condition=upon [completion of the TLS handshake]`。

主体（clients and servers）、MUST、对象均保留，条件取自原文，未扩大。

## 三、285 强度与 306 条件

| 项 | 检查 |
|---|---|
| 285 | 原文 `Both the SMTP client and server must check...` — 强度是 must（原文小写），命题按 MUST 记录，一致 |
| 306 | 原文 311–315 以 `In order to defend against such attacks` 开头，属**目的**而非适用条件；命题未把它写成 condition |

## 四、验收判定

Gold 2/2、341 命中，且证据可定位——三条在同一份 v6 Raw 中同时成立。这是首次。
