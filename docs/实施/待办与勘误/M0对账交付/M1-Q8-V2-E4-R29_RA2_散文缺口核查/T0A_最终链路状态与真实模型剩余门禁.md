# T0-A 最终链路状态与真实模型剩余门禁

## 一、当前状态

```
T0_A_offline_end_to_end_verified
T0_A_hub_isolation_verified
real_llm_output_pending_validation
production_merge_not_approved
```

说明：`offline_end_to_end_verified` 仅代表确定性 Stub 下工程链路通过，**不代表真实模型的知识抽取准确率已验证**。

## 二、已验证到哪

| 节点 | 状态 |
|---|---|
| RFC 读取 / 切块 / 抽取 | 通过 |
| Norm / Fact / Claim / Evidence | 通过（既有函数） |
| 隔离 Fact 落盘与读回 | 通过（fact_id 一致） |
| 实体索引（中枢最小段） | 通过（落盘可读回） |
| 完整中枢（sources/社区/图） | 未验证 |
| Seed / GraphRAG | 未验证 |
| 语义去重 | 未通过（能力边界：只按 fact_id） |

## 三、真实模型剩余门禁

| 编号 | 门禁 | 现状 |
|---|---|---|
| G1 | 每次网络调用前强制校验请求数与 token 阈值 | 运行器已改走链路，但阈值检查在旧循环里，需重接 |
| G2 | 证明所有缓存与产物写入隔离路径 | 部分证明（缓存可注入），产物路径未注入 |
| G3 | 运行器把 Norm 继续转成 Fact / Canonical | 未实现（当前只到 Norm） |
| G4 | 异常停止后的退出码与证据落盘 | 未闭合（目前只打印） |
| G5 | 真实输出与 Stub 的行为差异评估 | 无数据 |

G1–G4 都是代码问题，属下一轮工程范围；G5 只能等真实调用。

## 四、不建议现在做的事

不要因为离线链路通了就发起真实调用：G1/G4 未闭合时，一旦异常停止可能没有证据、也可能多发请求。
