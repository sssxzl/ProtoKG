# D4 隔离 Hub 构建与稳定读回

| 项 | 值 |
|---|---|
| 隔离目录 | `mkdtemp`，构建两次 |
| Fact 读回 | 4（D4 syntax/definition + H2 syntax/definition） |
| 实体 | 2 |
| fact_id 两次一致 | 是 |
| Claim→Evidence | 4/4 可读 |
| 与侧车关联 | 按 claim_id 反查成功 |

## 边界

官方 Hub 仍只存 `evidence_summary`，完整 quote 在侧车，经 `claim_id` 关联。未声称原生支持。
