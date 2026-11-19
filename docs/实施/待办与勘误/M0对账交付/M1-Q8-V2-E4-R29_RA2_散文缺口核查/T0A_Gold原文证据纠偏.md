# T0-A Gold 原文证据纠偏

## 一、纠偏结论

上一份 `T0_执行前核对` 里的两条 Gold ID **是错的**：

| 旧报告 | 实际 |
|---|---|
| GK-B-smtp-rfc3207.txt-404-1 | 不存在 |
| GK-B-smtp-rfc3207.txt-405-1 | 不存在 |
| — | 实际为 `GK-B-smtp-rfc3207.txt-30-1`（span 30-33）与 `-30-2`（span 33-35） |

`-404-0` 确实存在，但它是 `status=no_target_knowledge` 的无目标记录，`evidence_span` 为空，不能当命中分母。

## 二、错误是怎么产生的

1. 我把 Gold ID 末段（`-404-1`）当成了行号，再据此编出 `-404-1`、`-405-1` 两个 ID。
2. 预检脚本判断「Gold 是否落在块内」时用了 `block.start <= 行号 <= block.start + 字符数`，把**行号与字符数混算**，任何行号都能被判定为「在块内」，于是 3/3 覆盖的结论是假阳性。

两处都已修：Gold 以 B1 冻结清单为准，块覆盖改为「块的起始行 + 块内换行数 = 结束行」的区间判断。

## 三、正确的证据

| Gold ID | span | 原文（首 160 字） | 所在块 |
|---|---|---|---|
| GK-B-smtp-rfc3207.txt-30-1 | 30-33 | `This document describes an extension to the SMTP ...` | 块 1（行 1-114） |
| GK-B-smtp-rfc3207.txt-30-2 | 33-35 | `This gives SMTP agents the ability to protect ...` | 块 1（行 1-114） |

两条都属于 `protocol_descriptive_semantics`、`strength=unknown`。

## 四、行号基准

- 一律用 `text.split("\n")`，与 `documents.json`、R28-C 对齐；
- 文件 SHA256 见 `scripts/t0a_evidence.json` 的 `src_sha256`；
- 块边界由 `_split_blocks` 产出，块的结束行 = 起始行 + 块内 `\n` 个数。

## 五、第三条（rfc4954）

`GK-B-smtp-rfc4954.txt-704-1`（span 704-708）不在 T0-A 范围，标 `not_in_scope`，不计入命中分母。

## 六、是否可重建

两条均可从冻结原文重建，行号与文本一致。判定：**gold_source_mapping_ok**，不触发 `gold_source_mapping_blocked`。
