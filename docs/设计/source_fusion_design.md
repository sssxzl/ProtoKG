# 五源融合传导方案（source_fusion_design）v16

> 日期：2026-10-20。本文档是「五源分工真正传导到下游」的设计真源，经 16 轮迭代收敛。

## 一、背景与目标

**问题**：五源（source/rfc/expert_note/traffic/vuln）各有分工，通过 `epistemic_type`（认识论类型）+ `authority`（知识权威）显式编码在 fact 里，但下游 `assemble_bundle` 分桶时只读 `subject/aspect/value`，**丢掉了来源与认识论**，导致：

1. 分工信息是死数据，五源 fact 混在一起分不清谁是谁；
2. RQ4 消融实验「去源」和「不去源」下游产出几乎一样，消融是空的；
3. 被迫在 profile.json 手配 `allowed_methods`（本该由知识自动给）。

**目标**（不变）：让五源分工真正传导到种子生成；有源则用、无源则退化；RQ4 消融产生可测退化；**协议无关**。

**架构约束**（不变）：五知识源 → 结构化知识中枢（六元组）→ 生成初始种子，RAG 与 LLM 参与其中。

## 二、整体架构

```
五源 extractor（source/rfc/expert_note/traffic/vuln）
   │  各自产 fact（epistemic_type + authority + evidence，可溯源）
   ▼
[处理管线] ①命名对齐(profile.method_normalizer) → ②脱敏 → ③证据强度计算
   ▼
[结构化知识中枢] 六元组 fact + provenance + 消解(单一引擎)
   ▼
[消费层] source_availability 决策 → 方法白名单 / 冲突消解 / 拓扑序（声明式降级链）
   ▼
[生成层] edge_cover + generic_danger + canonical_flow → 种子
   │   LLM 参与：traffic 字段语义标注 / 语义冲突消解 / 跨源语义归一
   ▼
seedgen 生成 .raw 种子
```

## 三、核心机制

### 1. 统一消解引擎

```python
def resolve(subject, aspect, claims):
    """按声明式 source_priority 取最高优先级来源的值；被覆盖 claim 保留 superseded。"""
```

- 方法存在性、字段值、状态转移等所有 aspect 共用这一个引擎；
- 四级白名单链 = 「方法存在性」这个 aspect 的消解实例。

### 2. 声明式配置（profile 驱动，协议无关）

```json
{
  "method_normalizer": "first_token",
  "source_priority": ["observed", "normative", "descriptive"],
  "announce_signal": "public_header",
  "evidence_strength": {"min_runs": 2, "accept_single_impl": true}
}
```

### 3. 方法白名单 = 方法存在性的消解（四级降级链）

```
[server_announce] → [source_cmd_table] → [observed_called] → [rfc_fullset]
缺哪级跳哪级；终点=空 → 不生成种子 + 告警
```

- `server_announce` 载体按 profile 配：RTSP=`public_header`、SMTP=`ehlo_capabilities`、FTP=`feat_response`。

### 4. 证据强度（observed 采信门槛）

```
多 run 一致          → high
单 run 但独立实现    → medium（仍高于 descriptive）
单 run 无独立佐证    → 降级为 descriptive 同级
```

### 5. LLM 三处参与

| 位置 | 任务 | 触发 |
|---|---|---|
| traffic 字段语义 | 标字段含义（CSeq=序列号） | `-m llm` |
| 语义冲突消解 | 值不同但语义等价的冲突 | 规则消解无法判定时 |
| 跨源语义归一 | 不同源表述差异对齐 | 同概念多表述时 |

### 6. 优雅降级

所有消费点问 `source_availability`，有源则用、无源则退回基线；退化即消融证据。

## 四、分层实施

- **P0**：`assemble_bundle` 分桶保留 provenance（`declared_by`/`observed_by`/`source_values`/`available_sources`）。
- **P1**：方法白名单四级降级链（替代手配 allowed_methods）。
- **P2a**：冲突消解（统一消解引擎 + 证据强度）。
- **P2b**：precondition 拓扑序（traffic 序列，降级字典序）。

## 五、边界与防御

| 场景 | 行为 |
|---|---|
| 全空 | 白名单=空 → 不生成种子 + 告警 |
| 单源（仅 source） | 链退到 source_cmd_table |
| 有序列无声明 | 链退到 observed_called |
| 旧 fact 无 provenance | 兼容层按单一 descriptive 源兜底 |
| provenance 字段缺失 | fail-closed 告警 |

## 六、已知限制

1. 消解引擎是「优先级取最高」，不做语义融合（真实值+约束的融合是未来方向）。
2. LLM 三处参与准确率未验证，需 `-m llm` 隔离 + 评测。
3. 证据强度阈值是经验值，需标定。
4. 方法白名单隐含「方法/命令」概念，纯二进制协议需映射为消息类型。
5. 脱敏是规则式，非隐私保护级。
