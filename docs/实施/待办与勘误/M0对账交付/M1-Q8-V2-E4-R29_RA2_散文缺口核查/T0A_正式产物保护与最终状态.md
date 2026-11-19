# T0-A 正式产物保护与最终状态

## 一、前后对照

| 项 | 值 | 状态 |
|---|---|---|
| SMTP / RTSP / DHCPv4 Norm | 63 / 107 / 92 | 未变 |
| SMTP / RTSP / DHCPv4 Fact | 82 / 152 / 99 | 未变 |
| `derived/per_source` + `derived/hub` 文件数 | 190 | 未变 |
| 二者哈希合并摘要 | `6ace9d32…` | 未变 |
| 历史散文缓存 | `558767f2…`，76 条 | 未变 |

## 二、执行边界

- 本轮 0 次 LLM、0 次网络；
- 未修改 profile、未推送 main、未写正式 `derived/`；
- 所有执行器测试用 `mkdtemp`，退出即弃。

## 三、状态

```
T0_A_live_runner_engineering_verified
real_llm_output_pending_validation
production_merge_not_approved
```

## 四、仍需注意

1. 「工程验证」指门禁、隔离、链路、状态机在 Stub 下成立，不含真实模型输出质量；
2. 单进程假设，未验证并发；
3. 真实调用前仍需项目方费用授权。
