# T0-A 30 条 Claim 与 Evidence 关联核验

## 一、关联键

`proposition_id → fact_id → claim_id` 三级映射，`claim_id` 全局唯一（本轮实测 30 个键无重复）。

## 二、多 Claim 的 Fact

`f2_35eb41ca…` 挂 3 个 Claim（行 76/88/94），三份元数据分别对应，互不覆盖。

## 三、缺失/错误侧车的行为

若某条 claim_id 在侧车中找不到 ⇒ 读回结果为 `None`，脚本 `join_ok=False`，不会默认视为已验证。

## 四、未做

未修改 FactID/ClaimID/EvidenceID；未把验证状态写进正式 Hub Schema。
