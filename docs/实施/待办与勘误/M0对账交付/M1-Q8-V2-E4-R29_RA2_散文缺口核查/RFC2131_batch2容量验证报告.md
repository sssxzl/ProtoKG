# RFC 2131 batch=2 容量验证

| 项 | 值 |
|---|---|
| 批大小 | 2 块 |
| 首批范围 | 行 1–200（1 块，3 664 输入 token） |
| 结果 | `completed`，3 Norm，输出 1 938 token |
| 输出余量 | 1 938 / 8 000，远低于 6 400 警戒线 |
| 证据 | `evidence/b1-200.json`（原子写） |

结论：`rfc2131_batch2_capacity_verified`。批大小 5 会截断（历史记录），2 可行。
