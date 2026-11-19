# T0-A Claim 证据关联与隔离知识状态核验

## 一、关联方式

审查侧车以 `p<index>` 为键，与原 Fact 通过 `fact_id`、`claim_id` 关联。原始 FactID / ClaimID 未变，侧车只加审查结论，不改身份。

## 二、多 Claim 的 Fact

v4 的 30 条 Fact 中，`f2_35eb41ca…`（STARTTLS 定义）挂 3 个 Claim（76/88/94 行）。逐条检查：

| Claim | 证据 | 结论 |
|---|---|---|
| c2_07cdd1ea… | `(1) the name of the SMTP service defined here is STARTTLS;` | supported |
| c2_7ce53bed… | `(2) the EHLO keyword value … is STARTTLS;` | supported |
| c2_94b41a5d… | `(3) the STARTTLS keyword has no parameters;` | supported |

同一 Fact 下三个 Claim 证据分别有效，没有互相覆盖。

## 三、未通过证据的知识是否污染集合

| 项 | 处理 |
|---|---|
| p7（multi_source） | 留在待核验区，不进已验证集合 |
| p8 / p13（partially） | 同上，侧车记录扩展引用 |
| 已验证集合 | 27 条，均有整句证据 |

隔离 Hub 的「已验证」状态以侧车为准，不是以「有 Fact」为准。本轮未重跑 Hub 写入，因此不声称 Hub 内已验证计数为 27——那是下一步接入时才生效的事。

## 四、未做的事

- 未修改 FactID / ClaimID / EvidenceID；
- 未把 `exact_match` 当 `supported`；
- 未重跑双阶段真实调用；
- 未启动 341 行调优。
