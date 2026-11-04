# B-10 绑定层修复（prompt v1 → v2）对照报告

- 生成日期：2026-11-04
- 对应任务：用户选项「先修绑定层再重跑（推荐）」的第二阶段
- 实验脚本：`scripts/exp_semantic_gain.py`
- 结果文件：`derived/exp_semantic_gain/results.json`（v2）、`local/b10_v1_results.json`（v1 备份）
- 结果文档：`docs/semantic_gain_results.md`（v2）、`local/b10_v1_results_doc.md`（v1 备份）

## 0. 结论速览

**绑定层修复在 C4（算子解析）环节确认有效，但 M1 未转正，综合判定仍为「暂不可判定」。**

1. 主因已缓解：E1 的 `operator_unresolved` 从 **73/120 降到 26/120**（-47 条）。
   E2（无 LLM 的纯规则表对照组）同类计数 **82 → 82 完全不变**，说明该下降可归因于
   LLM 输出契约修复，而非候选集、规则表或字段集漂移。
2. M1 仍未转正：`E1 − C0` 从 **-5.0000 pp** 变为 **-4.1666 pp**（+0.8334 pp），
   仍落在路线图 §4.2 的「不成立」档（门槛：+15 pp 成立 / +5 pp 部分成立）。
   分协议看，sip 由 -2.5 转为 **+2.5**（转正），smtp 由 -10.0 改善到 -5.0，
   但 rtsp 由 -2.5 **恶化到 -10.0**。
3. 瓶颈已转移：越过 C4 的候选大量卡在 **C6 字段绑定**（`field_unbound` 6 → 33）
   与 **sanitize 空主语**（`empty_subject` 0 → 17）。
4. M2 硬阻塞未解除：117 条待标、仅标注者 A、Cohen's κ 无法计算 ⇒
   F1 不可计算，**不得伪造，也不得据此宣告收益成立或不成立**。
5. **本轮不是严格单变量对照**：v1 结果与 v2 结果之间存在 3 处混杂（见 §4）。
   因此除「C4 类拒绝计数」这一项外，其余差异**不能全部归因于 prompt v2**。
   这是本报告最重要的限制，后续结论必须带这一口径。

## 1. 本轮改动范围

| 文件 | 改动 |
| --- | --- |
| `scripts/exp_semantic_gain.py` | 唯一代码改动点（+109 / -8 行）。`PROMPT_VERSION` 升到 `rfc-constraint-prompt-v2`；新增实验专用 `_PROMPT_CONSTRAINT_V2`（要求 LLM 从 `OPERATORS` 受控词表输出 `operator` + `operand`）；`CachedLLM.last_response` 支持缓存命中回填；`run_group_c0()` 内 monkeypatch `rx._PROMPT_CONSTRAINT` 并抽取 `llm_operator/llm_operand` 写入 record；`_probe_llm_fact()` 优先消费结构化算子、缺失时回退 v1 正则。**`core/` 生产侧零改动。** |
| `derived/exp_semantic_gain/llm_cache.jsonl` | 由 240 条（120 条 v1 死数据 + 120 条 v2）清理为 **120 条纯 v2 响应**，其中 **104 条带 `operator` 字段**。 |
| `derived/exp_semantic_gain/group_{C0,E1,E2}/*` | v2 三组产物重跑覆盖。 |
| `derived/exp_semantic_gain/results.json` | v2 结果（`generated_at=2026-11-04 15:01:11`，`elapsed_s=1.3`，缓存命中 120 次）。 |
| `docs/semantic_gain_results.md` | 由 `--run` 自动重写为 v2 结果。 |
| `local/b10_v1_results.json`、`local/b10_v1_results_doc.md` | 新增：v1 对照备份（`generated_at=2026-11-02 06:02:39`，`elapsed_s=139.8`，冷调用 120 次）。 |
| `local/b10_v2_run.log` | 新增：v2 首次可见重跑日志。 |

设计取舍：**保持单变量归因**。C0 的 `decidable` 判定继续走 v1 口径 `probe_operator()`，
只有 E1 阶段 B 消费 `llm_operator/llm_operand`；所有改动收敛在实验脚本内，
不触碰 `core/fused/rfc_extractor.py` 的全局 prompt，避免污染知识中枢生产链路。

## 2. 对照数据

### 2.1 M1 可执行率（TOTAL，分母同为 120 条冻结候选句）

| 指标 | v1 | v2 | 变化 |
| --- | ---: | ---: | ---: |
| C0 可判定数 | 20 | 22 | +2 |
| C0 可判定率 | 16.6667% | 18.3333% | +1.6666 pp |
| E1 可执行规则数 | 14 | 17 | +3 |
| E1 可执行率 | 11.6667% | 14.1667% | +2.5000 pp |
| E2 可执行规则数 | 7 | 2 | -5 |
| E2 可执行率 | 5.8333% | 1.6667% | -4.1666 pp |
| **E1 − C0** | **-5.0000 pp** | **-4.1666 pp** | **+0.8334 pp** |
| E2 − C0 | -10.8334 pp | -16.6666 pp | -5.8332 pp |

按协议的 `E1 − C0`：

| 协议 | v1 | v2 | 变化 |
| --- | ---: | ---: | ---: |
| rtsp | -2.5 | -10.0 | -7.5（恶化） |
| sip | -2.5 | +2.5 | +5.0（转正） |
| smtp | -10.0 | -5.0 | +5.0（改善） |

E2 规则数 7 → 2 **不是** prompt v2 造成的，见 §4.1。

### 2.2 M7 拒绝原因直方图

E1（规则表 + LLM 兜底）：

| 原因 | v1 | v2 | 变化 |
| --- | ---: | ---: | ---: |
| `operator_unresolved` | 73 | 26 | **-47** |
| `field_unbound` | 6 | 33 | +27 |
| `empty_subject` | 0 | 17 | +17 |
| `non_normative_kind` | 23 | 23 | 0 |
| `optional_modality` | 4 | 4 | 0 |
| 合计被拒 | 106 | 103 | -3 |

E2（只跑规则表，无 LLM）：

| 原因 | v1 | v2 | 变化 |
| --- | ---: | ---: | ---: |
| `operator_unresolved` | 82 | 82 | 0 |
| `field_unbound` | 4 | 4 | 0 |
| `non_normative_kind` | 23 | 23 | 0 |
| `optional_modality` | 4 | 4 | 0 |
| `empty_subject` | 0 | 5 | +5 |
| 合计被拒 | 113 | 118 | +5 |

E2 前四类逐项完全一致，只有 `empty_subject` 新增 5 条、对应 5 条规则被降级。
这同时是「C4 归因干净」和「sanitize 口径漂移」两条结论的证据。

### 2.3 M3 / M4 / M5（E1 TOTAL）

| 指标 | v1 | v2 |
| --- | ---: | ---: |
| M3 证据可核验率 | 100.0% | 100.0% |
| M4 显式性纯度 | 100.0% | 100.0% |
| M4 大写 MUST 纯度 | 80.0% | 90.9091% |
| M5 may 误提升率（硬闸） | 0.0% | 0.0% |
| M5 may token 率（宽松口径） | 0.0% | 5.8824%（rtsp 1/5） |

硬闸 M3/M4/M5 未被破坏（M5 硬闸两轮均为 0）。

### 2.4 判定、幂等性与抖动

- `verdict.composite` 两轮均为 **暂不可判定**，`m1_delta_pp_e1_minus_c0` 为 -5.0 → -4.1666。
- M6 幂等性：两轮 E2 三次重复抽取 `all_identical=true`。
- 运行抖动：v2 为缓存命中复跑，`delta_e1_minus_c0_pp = 0.0`；
  v1 为冷调用，`run_variance` 记录同 prompt 两次冷跑抖动 0.8334 pp（温度 0.2 非确定性）。

### 2.5 全量护栏（回归验收）

```
E:/app/Anaconda3/python.exe tools/qa/run_guarded_pytest.py --out-dir qa/b10v2
```

| 项 | 结果 |
| --- | --- |
| 结论 | **可采信** |
| 计数 | 41 failed / 1572 passed / 20 errors / 1 skipped |
| FAILED 集比对 | 期望 32 / 实测 41，**新增 0 / 消失 0**（另有 9 条窄化数据态豁免） |
| ERROR 集比对 | 期望 20 / 实测 20，**新增 0 / 消失 0** |
| 树静止 / summary 行 | `tree_stable=true` / `summary_present=true` |

与 F9 后的权威基线 `qa/f9b/_guarded_result.json` 逐项一致 ⇒
**prompt v2 改动未引入任何 pytest 回归**。改动只落在实验脚本，生产链路零影响。

## 3. 绑定层修复的直接证据链

| 环节 | 观测 | 说明 |
| --- | --- | --- |
| LLM 响应缓存 | 120 条 v2 响应，104 条含 `operator` | v1 缓存 113 条 constraint 全无该字段 |
| C0 `items.jsonl` | **82/120** 提取到受控词表内算子 | 分布：`present` 33、`eq` 16、`absent` 16、`in` 7、`le/ge` 各 3、`ne/range` 各 2 |
| 留空回退 | 38 条 `llm_operator` 为空 | LLM 未给合法算子或有参算子缺 operand，按设计回退 v1 正则 |
| E1 `stage_b_reason` | `llm_operator_unresolved` = 38 | 与上一行 38 条吻合，回退也未命中的部分 |
| E2 对照组 | `operator_unresolved` 82 → 82 | 阶段 A 规则表、候选集、字段绑定口径在两次运行间对该类别无漂移 |

结论：**73 → 26 的下降可以干净地归因于「LLM 现在直接给结构化算子」**，
而不是候选句改写、规则表变化或字段集变化。修复目标（解开 C4 阻塞）达成。

## 4. 混杂变量（本轮对照的限制，必须随结论引用）

### 4.1 sanitize_rule 接入时间差（影响最大）

`git log` 显示 `a46212b feat(b10): 批次 2 的 M7 分布正式复测（sanitize 接入 B-10 + 基线对照）`
提交于 **2026-11-03 15:28:36**，而 v1 结果生成于 **2026-11-02 06:02:39**。
即 **v1 是在 `sanitize_rule` 接入 `run_group_two_layer` 之前跑出来的**。

推论：

- E2 规则数 7 → 2、`empty_subject` 0 → 5 **完全由 sanitize 接入引起**，与 prompt v2 无关；
  证据是 E2 其余四类拒绝计数逐项完全一致。
- E1 的 17 条 `empty_subject` 中，至少与 E2 同源的 5 条属于口径差异，
  不能算作「瓶颈转移到 sanitize」的净效果。
- 因此 **E1/E2 的规则数、`empty_subject`、M1 绝对值都不构成 v1/v2 的同口径对照**。

### 4.2 中枢字段集漂移

`known_fields` 从 `rtsp=45 / sip=46 / smtp=0`（v1）变为 `rtsp=45 / sip=46 / smtp=19`（v2）。
`fused_hub/targets/smtp/skeleton.json` 的修改时间为 2026-11-04 13:23，晚于 v1、早于 v2。
smtp 字段集从 0 变为 19 会直接影响 C6 字段绑定 ⇒ smtp 的 E1 规则数 1 → 4
**至少部分来自中枢状态变化**，不是 prompt v2 的净效果。

### 4.3 冷调用 vs 缓存命中

v1：真实调用 120 次、139.8 秒；v2：缓存命中 120 次、1.3 秒。
缓存键含 `prompt_version`，v1 响应不可能被 v2 命中；v2 的 120 条是 v2 prompt 下的真实 LLM 输出，
确定性复用不构成分布偏差。但 v1 存在温度 0.2 的非确定性（实测同 prompt 冷跑抖动 0.8334 pp），
这一量级与 M1 的改善幅度（0.8334 pp）**同阶**，因此也不能把 +0.8334 pp 当作显著改善。

### 4.4 归因边界

- 可干净归因于 prompt v2 的：**C4 类拒绝计数**（`operator_unresolved` 73 → 26）。
- 不可干净归因的：M1 净变化、E1/E2 规则数、`empty_subject`、`field_unbound` 的增量部分。
- 综合判定不受影响：M2 本就不可计算，两轮都只能是「暂不可判定」。

## 5. 判定

| 判据 | 结果 |
| --- | --- |
| 修复目标：解开 73 条 `operator_unresolved` | **达成**（降到 26，归因干净） |
| 里程碑闸门：M1 ≥ C0 + 15 pp（成立）/ +5 pp（部分） | **未达成**（-4.1666 pp，不成立档） |
| M2 规则 P/R/F1 与 Cohen's κ | **不可计算**（117 条待标 + 缺标注者 B） |
| 综合判定 | **暂不可判定** |

不宣告「语义增益成立」，也不宣告「语义增益不成立」——后者同样需要 M2。
本轮的准确定位：**修好了 C4 的解析契约，暴露出下一道瓶颈（C6 字段绑定），
且发现现有 v1 基线已因代码与中枢漂移而失去严格可比性。**

## 6. 下一步建议（按性价比）

1. **补一次严格单变量 A/B**：给 `scripts/exp_semantic_gain.py` 增加
   `--prompt-version {v1,v2}` 开关，在**同一代码、同一中枢、同一 sanitize 口径**下
   各跑一次冷调用。前置修复：`CachedLLM._flush()` 目前用当前模块常量
   `PROMPT_VERSION` 重写所有缓存行的标签，导致 v1/v2 缓存无法在同一文件共存，
   需改为按行保留各自的 `prompt_version`。这是本轮唯一能给出「prompt v2 净收益」的办法。
2. **解 M2 硬阻塞**：117 条重标 + 引入第二名真人标注者，否则任何收益结论都出不了闸门。
3. **攻 C6**：让 LLM 直接给出 `target_field` 并建字段别名表，把 33 条 `field_unbound` 压下去；
   同时处理 `empty_subject`（补 subject 推断）。
4. **rtsp 回归排查**：rtsp 是唯一恶化的协议（-2.5 → -10.0），
   需逐条看 `m1_decomposition.c0_only_detail`，确认是 C0 幻觉规范力上升还是 E1 规则丢失。

## 7. 产物清单与复现

```bash
# 确定性复跑（缓存命中，不消耗 API）
E:/app/Anaconda3/python.exe scripts/exp_semantic_gain.py --run

# 定向测试
E:/app/Anaconda3/python.exe -m pytest tests/fused/test_exp_semantic_gain.py -q

# 全量护栏
E:/app/Anaconda3/python.exe tools/qa/run_guarded_pytest.py --out-dir qa/b10v2
```

v1 备份：`local/b10_v1_results.json`、`local/b10_v1_results_doc.md`。
v2 日志：`local/b10_v2_run.log`。
护栏结果：`qa/b10v2/_guarded_result.json`。
