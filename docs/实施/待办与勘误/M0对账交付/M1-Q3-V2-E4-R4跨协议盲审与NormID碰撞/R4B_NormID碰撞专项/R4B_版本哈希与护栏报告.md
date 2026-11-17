# R4B 版本哈希与护栏报告

## 一、已验证事实

### 1.1 本轮执行的边界

| 审批约束 | 执行情况 |
|---|---|
| 0 次新增 LLM 调用 | ✔ 本轮未调用 LLM |
| 不重新抽取或替换 R3 的 57 条候选 | ✔ 未修改 |
| 不修改 H3 的 23 条候选 | ✔ 未修改 |
| 不修改 V0/V1/V2 及现有分类判据 | ✔ 未修改 |
| 不修改正式中枢或 Seed | ✔ 逐字节一致 |
| 不修改 canonical FactID 和 21 aspects | ✔ 未修改 |
| 不修改已有人工真值 | ✔ 未修改 |
| 不使用 H3 或 R3 人工判断进行模型调优 | ✔ 未使用 |
| 不修改生产标识符生成逻辑 | ✔ 影子实现在 guard/_out/_n1c_v2/r4/shadow_norm_id.py |
| 不迁移或覆盖历史 Norm 数据 | ✔ 未改写 |
| 影子 ID 不写入正式 canonical Fact | ✔ 仅用于复算与报告 |

### 1.2 生产代码未修改的核验

本轮新增文件全部位于 `guard/_out/_n1c_v2/r4/` 与交付目录。`core/` 下无改动，`prose_semantics.py:1208` 的 norm_id 构造式保持原样，由 `test_production_norm_id_unchanged` 断言。

### 1.3 护栏

```
5 failed / 1724 passed / 231 skipped
新增 0 失败
编码卫生：达标
正式中枢与种子：逐字节一致
```

新增测试 `tests/extraction/test_r4_blind_pack_collision.py`，18 通过 4 跳过（★ 跳过项来自 conftest 的协议参数化，★ 与本轮无关）。

一处既有测试断言调整：`test_r3_controlled_extract.py` 的来源门禁断言由「accepted 恰为 8」改为「实际抽取的 8 份必须是 accepted 的子集」。★ 原因是 R4 对账把候选集补齐到 20 份后，★ rfc3848 亦满足独立性门禁但未被抽取。★ 该调整不降低任何约束。

## 二、版本哈希

基线提交：fbb7996

| 文件 | SHA256 |
|---|---|
| R4A_跨协议人工盲审包/R4A_XLSX单元格保全回归报告.md | `fe31d0b2048c3148c8444d4c6ea1b6de6fb0651cfa60d55b1588d44fca7eeb43` |
| R4A_跨协议人工盲审包/R4A_冻结机器基线.jsonl | `dfc9ed0d51bdf14bdcccfa6f319a3cbf0f6571ba4cbc8362d8fd87294f56815f` |
| R4A_跨协议人工盲审包/R4A_审核ID映射与版本哈希.json | `d1b2fcb643774c7eee736ee9ac48675111d0ea4fbe0fff1281607122ff8fadc1` |
| R4A_跨协议人工盲审包/R4A_盲审独立性与泄漏验收报告.md | `246d0862c81505a5b90a5a2829d4af002a43a573687cc86add9d28097714bf1b` |
| R4A_跨协议人工盲审包/RTSP_7候选_只读RFC证据包.html | `b184cd81c3d8dbbc1ae93d9e19a6cf5fa33294fc171f3f719e4c467710fec5c5` |
| R4A_跨协议人工盲审包/RTSP_7候选_审核者A_盲审模板.xlsx | `d08350fc0960b754633462e3243f0db733687349b8581ac65f5ada9ae9d733fe` |
| R4A_跨协议人工盲审包/RTSP_7候选_审核者B_盲审模板.xlsx | `d08350fc0960b754633462e3243f0db733687349b8581ac65f5ada9ae9d733fe` |
| R4A_跨协议人工盲审包/RTSP_7候选_第三方仲裁模板.xlsx | `f230a58e2e0e9e4390eaa5a839640a581d51f2fcfb8a19c7a83c2f4fbe9caa97` |
| R4A_跨协议人工盲审包/SIP_27候选_只读RFC证据包.html | `26e14e0d0d8fbcbda32cbecd3c56557854c659fe1310d1e383efa343d8002363` |
| R4A_跨协议人工盲审包/SIP_27候选_审核者A_盲审模板.xlsx | `774d6d4537d5cad51373d7d99ccda8f550696e114f03b6c67cac5a7152490d24` |
| R4A_跨协议人工盲审包/SIP_27候选_审核者B_盲审模板.xlsx | `774d6d4537d5cad51373d7d99ccda8f550696e114f03b6c67cac5a7152490d24` |
| R4A_跨协议人工盲审包/SIP_27候选_第三方仲裁模板.xlsx | `4d6eeaa392ddead36e84da114b151e1e3ed6feb3ef2ca25171502720c2276aa9` |
| R4A_跨协议人工盲审包/SMTP_23候选_只读RFC证据包.html | `fd1af964ab2aff9316e41a87702f8484814555b0be6e84a49101d2ee97a2a9b3` |
| R4A_跨协议人工盲审包/SMTP_23候选_审核者A_盲审模板.xlsx | `c27051194c34cb2d5834e165841bda97eb54808f61ea7257f1140966417ce90f` |
| R4A_跨协议人工盲审包/SMTP_23候选_审核者B_盲审模板.xlsx | `c27051194c34cb2d5834e165841bda97eb54808f61ea7257f1140966417ce90f` |
| R4A_跨协议人工盲审包/SMTP_23候选_第三方仲裁模板.xlsx | `a99b9b564bd0435e305606460f7e03dc36cba9b250d9a6af3bcbd2ac577654e8` |
| R4B_NormID碰撞专项/R4B_NormID碰撞与影响台账.xlsx | `fbab39b8ce59bde0db16a0a767935cbd791b205bc59af2f3282107f99acc96bc` |
| R4B_NormID碰撞专项/R4B_R3交付对账台账.xlsx | `3b9ce98864b021c172662d8b1fa075930551c713338c1764d1bdeff3d7988e3c` |
| R4B_NormID碰撞专项/R4B_三类兼容修复提案.md | `34e6458ef61f7f8ed1d09fc8ac616bcf13b25cf12333896e103df4377ffd27f2` |
| R4B_NormID碰撞专项/R4B_历史数据兼容及回滚方案.md | `9d54e33f290e6e5376f42fd6c6f644883019e7de7fe8e7d5eca12d47c2133b7c` |
| R4B_NormID碰撞专项/R4B_影子ID稳定性与回归证明.md | `0b59a41af75c5165dbd381bb100addec636eec92afae8b127ca150c3a70ee89a` |
| R4B_NormID碰撞专项/R4B_生产代码与下游引用分析.md | `9300d032c3d5b446beab6e2f5110c105698a1aa2c829beb70e43b818a5fc4ba4` |
| tests/extraction/test_r3_controlled_extract.py | `ae4973c5112db1c6a095289803122b1c3d5ac6c9bb033a28866e236645680b15` |
| tests/extraction/test_r4_blind_pack_collision.py | `607d82b5303954c1afaf59848b58b9973c92fb506e122d0c67cd76b4e82b2be4` |

## 三、限制

1. 碰撞审计未取得真实 canonical 视图，★ 不能声明 canonical 无损或损坏。
2. 影子 ID 的唯一性与稳定性结论基于 R3 的 57 条与 H1 的 156 条，★ 未在其他数据集验证。
3. R3 的 rfc3848 满足独立性门禁但未被抽取，★ 抽样清单已在调用前冻结，★ 本轮不改写。

## 四、状态

V2-E4-R4B Norm ID 碰撞影响审计及兼容修复方案完成，生产修改待审批。
