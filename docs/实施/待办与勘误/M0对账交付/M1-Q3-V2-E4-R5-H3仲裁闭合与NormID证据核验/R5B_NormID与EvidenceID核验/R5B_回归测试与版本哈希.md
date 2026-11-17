# R5B 回归测试与版本哈希

## 一、已验证事实

### 1.1 本轮执行的边界

| 审批约束 | 执行情况 |
|---|---|
| 0 次新增 LLM 调用 | ✔ 本轮未调用 LLM |
| 不修改生产 norm_id 生成函数 | ✔ `prose_semantics.py:1208` 保持原样，★ 由测试断言 |
| 不自动生成第三方人工判断 | ✔ 仲裁包全部仲裁列留空，★ 由测试断言 |
| 不自动修改历史 Norm ID | ✔ 未改写 |
| 不合入生产身份修复 | ✔ 影子实现仅在 `guard/_out/_n1c_v2/r4/shadow_norm_id.py` |
| 不更改冻结 V2 | ✔ 未修改 |
| 不修改已有人工真值 | ✔ A/B 原件只读，★ SHA256 已登记 |
| 不写入 Evidence / Fact / FactID / Seed | ✔ 只读复算 |

### 1.2 回归测试

`tests/extraction/test_r5_evidence_chain.py`，15 个用例全部通过。

| 覆盖 | 用例数 |
|---|---:|
| 仲裁列全空、Gold 未冻结 | 2 |
| 仲裁包覆盖 44 行逐字段差异与 23 条候选 | 2 |
| 未决项登记 | 1 |
| 证据链计数与碰撞传导 | 2 |
| 口径闭合（156 - 116 = 40） | 1 |
| 碰撞组语义载荷互异 | 1 |
| 真实错链风险识别 | 1 |
| 复合索引唯一性与稳定性 | 1 |
| evidence_id 复算与生产函数一致 | 1 |
| 生产代码未改、冻结记录不变、V0/V1/V2 不变、0 次 LLM | 4 |

### 1.3 护栏

见提交记录。基线为 5 failed / 1724 passed。

## 二、版本哈希

基线提交：d7b727f

| 文件 | SHA256 |
|---|---|
| R5A_H3第三方仲裁与Gold冻结/H3_Gold冻结门禁报告.md | `4e71a937a2525904b4c989df6e8c11e88d4311e56b859e0e4c91882757e6164a` |
| R5A_H3第三方仲裁与Gold冻结/H3_第三方人工仲裁回收核验.xlsx | `8d13df3ee5cf5d9a97d2ddf43dcee864c31588d2220339e042b9ca0b4e9c5783` |
| R5B_NormID与EvidenceID核验/R5B_NormID与EvidenceID关联核验.xlsx | `9721743aae5cd16bdad8a376d42ba17f37ed36afe632f2e12d0478c73343b256` |
| R5B_NormID与EvidenceID核验/R5B_实际引用歧义与错链风险报告.md | `2d410c436d47ce0fc0a68e297feb708a209cf0085636eb85d599e10aff85ba45` |
| R5B_NormID与EvidenceID核验/R5B_方案C复合索引影子证明.md | `3b7dfd5c8c4408d570d262902efc75f7d68efbb57435efa9c8ca1c00c18bd331` |
| R5B_NormID与EvidenceID核验/R5B_碰撞分组明细.xlsx | `0e46154fdc4eac450a6d2cd0c22db2a715a2ace5d1354edf93f9ba6b3750770f` |
| R5B_NormID与EvidenceID核验/R5B_碰撞统计口径勘误.md | `95b330301383db703919cb6404bae2be324ac25dad0dc7b2750740482e0bc758` |
| tests/extraction/test_r5_evidence_chain.py | `14e68996c028acb72b6d2826c380cd05bb555114e10f2e798a1370955c2bc860` |

## 三、限制

1. 真实 canonical 视图未取得，★ 关于实际错链是否已发生的结论保持 unmeasured。
2. 复合索引的唯一性与稳定性结论基于 R3 的 57 条与 H1 的 156 条。

## 四、状态

Norm ID / Evidence ID 影子核验完成，生产兼容修复待审批。
