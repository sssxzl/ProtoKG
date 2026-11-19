# T0-A 22 条 Raw → Fact / Claim 无损回放

## 一、总量

| 指标 | 修正前 | 修正后 |
|---|---|---|
| Norm | 22 | 22 |
| Fact | 22 | 22 |
| 唯一 fact_id | 19 | **20** |
| legal_boundary | 14 | 18 |
| definition | 8 | 4 |
| prose_constraint / prose_semantics | 14 / 8 | 18 / 4 |
| Claim 总数 | 22 | 22 |

## 二、127 / 146 已分开

| span | fact_id | aspect | qualifiers | 证据 |
|---|---|---|---|---|
| 127 | `f2_8d53f721…` | legal_boundary | action=require use of STARTTLS…, object=STARTTLS extension | `file:rfc3207.txt#@127` |
| 146 | `f2_394d4bd0…` | legal_boundary | action=return the reply code 530, object=every command other than NOOP/EHLO/STARTTLS/QUIT | `file:rfc3207.txt#@146` |

两条的 MUST NOT / SHOULD、条件、动作、对象分别保留，证据各自指向原文行号。

## 三、76/88/94 共用 FactID 但 Claim 独立

| span | fact_id | claim_id | 证据 |
|---|---|---|---|
| 76 | `f2_35eb41ca…` | `c2_07cdd1ea…` | #@76 |
| 88 | 同上 | `c2_7ce53bed…` | #@88 |
| 94 | 同上 | `c2_94b41a5d…` | #@94 |

三条是同一实体（STARTTLS）的定义型知识，共用 Fact 身份符合「一个事实多个 claim」的既有设计；各自 claim 与来源都在，没有静默丢源。

## 四、其余 17 条

全部一一对应到 Norm → Fact → Claim，逐条见 `T0A_身份修正_逐条去向.csv`。没有「减少但无原因」的条目。

## 五、稳定性

同一份缓存连跑两次，Fact 序列与 id 完全一致（`stable ids: True`）。

## 六、155 未回归

`MUST start the TLS negotiation` 仍为 prose_constraint + legal_boundary，证据 #@155。
