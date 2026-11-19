# T0-A 实执放行记录与凭据阻断

## 一、审批已收到

| 项 | 内容 |
|---|---|
| 审批结论 | 同意一次性受限试验 |
| 基准提交 | `9a3e6d1` |
| 分支 | `r28/pilot-prep` |
| 范围 | SMTP / rfc3207 / deepseek-flash / 非思考模式 |
| 上限 | CNY ¥0.15、2 次请求、7 500 输入 token、单次 4 000 输出 |
| 重试 | 禁止；超时即停 |
| 生产合入 | 未批准 |

## 二、执行前核查结果

| 检查 | 结果 |
|---|---|
| 执行器门禁与隔离 | 通过（43 项离线测试） |
| 隔离根策略 | 仅临时目录或 `T0A_WORKSPACE` |
| 费用上限写入运行时 | 0.15 元，最坏估算 0.038 元 |
| API 凭据 | **缺失** |
| 账户费用授权 | 审批单注明「由账户责任人确认」，尚未确认 |

凭据核查证据（本轮实际执行）：

```
$ echo $DEEPSEEK_API_KEY      → 空
$ ls .env                     → 不存在
```

## 三、结论：未能执行，未产生任何调用

```
T0_A_live_execution_blocked_no_credentials
```

- 本轮真实请求：0 次
- 本轮扣费：0 元
- 未生成任何隔离运行目录
- 未写入正式 `derived/`、Hub、Seed

按任务要求「任一请求失败/门禁触发即停止」，凭据缺失属于执行前阻断，不应伪造结果或改用 Stub 冒充真实试验。

## 四、凭据到位后的执行方式

```bash
# 1) 设置凭据与预算开关（二者缺一不可）
export DEEPSEEK_API_KEY=...
export T0A_BUDGET_APPROVED=1

# 2) 新建空白隔离目录
export T0A_OUT=$(mktemp -d /tmp/t0a_run.XXXXXX)

# 3) 执行（最多 2 次请求，失败不重试）
python scripts/t0a_executor.py --execute --out "$T0A_OUT"
```

执行器会自动完成：门禁 → 2 批请求 → Norm → Fact/Claim/Evidence → Canonical → 隔离 Hub → 读回；并落 `evidence/result.json`、`evidence/guard.json`。

## 五、执行后将提交的证据

1. 四段状态：`llm_call_success` / `norm_validation_success` / `canonical_validation_success` / `hub_integration_success`；
2. 实际请求次数与逐次 usage；
3. 费用对账（按实际 token × 单价，与 ¥0.15 对照）；
4. 原始响应 SHA256 与截断/解析分类；
5. Norm / Fact / Evidence 明细与来源行号；
6. 隔离 Hub 读回结果；
7. `-30-1`、`-30-2` 两条 Gold 的 hit / partial / miss 观察（仅为观察，不作指标）。

## 六、限制

若账户责任人只授权技术方案而未授权实际扣费，仍不应执行；本记录不构成费用授权。
