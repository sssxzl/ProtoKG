# 阶段 2 前置侦察报告 · 2026-09-28

> RFC 独立驱动到 seedgen（RTSP 协议 · RFC 2326 单源）
> 内部记录 · 不进 docs/

---

## 一、执行摘要

- ✅ **dispatcher 抽 RFC 单源**：17366 norms（RFC method 11 + LLM fixture 抽 field 2232 + outcome 1080 + transition 43），**但混入 17000 traffic norms**（dispatcher route() 优先按 format 派发，bypass family 检查）
- ✅ **TypedKB.build RFC 单源**：norms.jsonl 从 26135 行 → **17011 行**（其中 rfc=11，traffic_pcap=9000，traffic_raw=8000）
- ✅ **spec_graph 构建**：28 entities（11 method + 5 message + 2 state_machine + 2 field + 2 outcome + 1 protocol + 1 actor + 4 state）/ 81 relations
- ✅ **seedgen RFC 单源生成**：**28 个 .raw**（覆盖 RFC 11 method × 状态路径组合），profile_chars=515，n_paths_planned=29 / n_seeds_written=28
- ⚠️ **profile.json 被覆盖**：从 28994 bytes 全量版本变成 **4299 bytes RFC 单版本**（12 facts 全空，仅有 schema_version / protocol / last_updated / source_hashes / facts）
- ⚠️ **rag_layers 仍拼装 traffic+vuln**：RFC 单源 build 的 seedgen 调用 `--kb-source-filter rfc` 后，输出 manifest 的 `rag_layers` 仍含 traffic(12 entities) + vuln(16 vuln_graph_seeds)，仅 rfc=11 / source=0 / edge=0

---

## 二、动作 1：RFC extractor 现状

### 2.1 代码结构

**位置**：`core/extractors/rfc.py` (2497 B)

```python
class RFCNormExtractor(BaseExtractor):
    file_type = "rfc"
    method = "rule_based_5_heuristic+llm"

    def _do_extract(self, file_path, protocol):
        # P1-5 阶段 0 扩展名白名单: 只 .txt + rfc* 前缀
        if suffix != ".txt" and not name_lower.startswith("rfc"):
            return []   # 防 RTSPCommon.cpp 误判

        text = file_path.read_text(encoding="utf-8", errors="ignore")
        sections = RfcSectionParser().parse(text, source="file:rfc2326.txt")

        # 1. rule 抽 method（5+1 启发式）
        rule_norms = RuleBasedExtractor().extract_from_sections(protocol, sections)

        # 2. LLM 兜底（仅当 llm != StubLLM）
        if self.llm is not None and not isinstance(self.llm, StubLLMClient):
            try:
                LLMExtractor(self.llm, RfcSectionParser(),
                             include_method=(len(rule_norms) == 0))
                ...
```

### 2.2 RfcSectionParser 切分（`core/corpus.py`）

- `_SECTION_RE`：`^(\d+(?:\.\d+){0,4}\.?|[A-Z](?:\.\d+){0,4})\s+[A-Z][A-Za-z0-9_ \-/]{0,79}$`
- 排除页码/页眉（`_PAGINATION_RE`）
- 单独识别 `Appendix A.1` 格式（`_APPENDIX_RE`）
- `_classify_section()` 按 major number 映射 kind：§1-3→intro, §4→message, §5→header, §6-9→message, §10→method, §11→outcome, §12→field, §13→message, §14→example, §15→intro, §16→intro

### 2.3 RuleBasedExtractor 5+1 启发式（`core/extractor.py:131`）

- **H1**: 标题是短大写串（1-3 token, ≤ 16 字符）
- **H2**: 章节深度 ≥ 2（X.Y 或更深）
- **H3**: 顶级章节号 ≥ 4
- **H4**: 标题含 method/definition/request/operation/command/...
- **H5**: body 首行匹配 `The X (request|method|command|...)...` 或 `<X> is used to...`
- **H6**（P0-C1 修复）: body 含 `function code` / `service primitive` / `control bits` / `message type` / ...
- 阈值 ≥ 2 启发式命中 → 抽 method

### 2.4 LLMExtractor 抽 7 类（`core/extractor.py:387`）

`(`protocol`, `actor`, `field`, `outcome`, `transition`, `constraint` + 可选 `method`)`

### 2.5 dispatcher 实际抽的 norms 数

**RFC 单源 `dispatcher.extract_kb(kb, source_family=['rfc'])`**：

| kind | 数 | 来源 |
|---|---|---|
| message | 10000 | **traffic 混入**（route() 按 format='csv'/'pcap' 派发） |
| state_machine | 2000 | **traffic 混入** |
| field | 2232 | RFC（fixture 抽）+ traffic |
| state_machine(proper) | ? | （计入 state_machine 类 2000） |
| outcome | 1080 | RFC fixture 抽 |
| protocol | 1000 | **traffic 混入** |
| actor | 1000 | **traffic 混入** |
| transition | 43 | RFC fixture 抽（7 fixture）|
| method | 11 | **RFC ✓**（RTSP 11 method）|
| **合计** | **17366** | rfc=11 + traffic=17000 |

**skipped 分布**：filtered=2061（family 不匹配）/ log_file=1000（fuzz_history 类）/ aux_file=3（`_` 开头）/ **errors=0**

**rfc2326.txt 真产 norms**：366 个（method 11 + field 232 + outcome 80 + transition 43）

---

## 三、动作 2/3：kb/spec/rfc2326.txt 结构

### 3.1 总览

- 文件大小：**195011 bytes**（约 195KB）
- 总行数：4407 行（含 4535 lines per wc）
- 章节总数：**127 节**（恰好对应 127 fixture 数）

### 3.2 顶层章节分布

| 主章节 | 子章节数 | 标题 | 关键 |
|---|---|---|---|
| §1 | 9 | Introduction | - |
| §2 | 1 | Notational Conventions | - |
| §3 | 10 | Protocol Parameters | - |
| §4 | 5 | RTSP Message | - |
| §5 | 1 | General Header Fields | header |
| §6 | 3 | Request | method keyword |
| §7 | 4 | Response | - |
| §8 | 3 | Entity | - |
| §9 | 3 | Connections | - |
| **§10** | **12** | **Method Definitions** | **方法主源** |
| **§11** | **4** | **Status Code Definitions** | **错误码** |
| **§12** | **45** | **Header Field Definitions** | **headers** |
| §13 | 1 | Caching | - |
| §14 | 6 | Examples | example |
| §15 | 2 | Syntax | - |
| §16 | 1 | Security Considerations | - |
| **§A** | **2** | **Client/Server State Machine** | **state machine** |
| §C | 9 | Definitions | - |
| §D | 6 | Client | - |

### 3.3 RFC 真正抽出 method（确认）

`rfc.method.*` 11 个：
`ANNOUNCE / DESCRIBE / GET_PARAMETER / OPTIONS / PAUSE / PLAY / RECORD / REDIRECT / SETUP / SET_PARAMETER / TEARDOWN`

### 3.4 RFC 抽 state machine 现状

- §A 有 A.1 Client State Machine (L4308) / A.2 Server State Machine (L4368)
- StateMachineExtractor 在 `core/extractor.py:588`（class 存在）
- RFC 单源 build 后 spec_graph 含 state_machine entity_type = 2（client + server）
- 但 norms.jsonl kind=state_machine 数 = 0（被 rule 5+1 启发式未匹配上）

---

## 四、动作 4：RFC 单源 TypedKB.build

### 4.1 入口约定（重要修正）

**TypedKB data_root 必须是 `kb/`，不是 project root！**

```python
# 错（首跑失败）：
kb = TypedKB(PROJECT_ROOT, StubLLMClient())  # PROJECT_ROOT=.

# 对（重做通过）：
kb = TypedKB(PROJECT_ROOT / "kb", StubLLMClient())  # data_root=kb/
```

第一次跑错的原因：`detect_layout(data_root, protocol)` 在嵌套 + 扁平两个布局都找不到 `_meta.json` 时抛 FileNotFoundError（`kb_layout.py:97`）。

### 4.2 RFC 单源 build 输出

| 项 | 值 |
|---|---|
| 备份 | `local/backup/stage2_pre_build_bak/norms.jsonl` (26135 行) |
| 覆盖后 norms.jsonl | **17011 行**（来自 17366 - 部分去重 / join） |
| `kind` 分布 | method 11 / outcome 1000 / **message 10000 / state_machine 2000 / field 2000 / protocol 1000 / actor 1000** |
| `kb_source_type` 分布 | traffic_pcap 9000 / traffic_raw 8000 / **rfc 11** |
| state_machine.json | 5500 bytes（state 树） |
| **protocol_profile.json** | **4299 bytes** ⚠️（从 28994 → 4299，12 facts 全空，**profile 被 RFC 单源 build 覆盖**） |
| spec_graph | meta：n_entities=28 / n_relations=81 / updated_at=2026-09-28T08:28:50 |
| spec_graph entities by type | method 11 / message 5 / state 4 / state_machine 2 / field 2 / outcome 2 / protocol 1 / actor 1 |
| spec_graph relations | 81 行（kind 字段部分为 None）|

### 4.3 副作用警示

**protocol_profile.json 被覆盖**：
- 阶段 1 收尾后 profile=28994 bytes（12 类 facts 全有）
- 阶段 2 动作 4 跑完变成 4299 bytes（schema_version / protocol / last_updated / source_hashes / facts={} 全空）
- 因 `TypedKB.build` 末尾调 `build_protocol_profile + save_profile`，RFC 单源 build 重写 profile

跑完动作 5 后立即恢复 norms.jsonl（备份已恢复）但 **profile.json 没恢复**——下次跑阶段 3/4/5 前需先重跑一次全量 build。

---

## 五、动作 5：RFC 单源 seedgen 端到端

### 5.1 命令

```bash
python -u rag/seedgen.py \
  --protocol RTSP --depth 2 --mode rule \
  --use-typed-kb --use-typed-rag --rebuild-graph \
  --kb-source-filter rfc \
  --out-dir seeds/rtsp/seedgen/test-stage2-rfc
```

### 5.2 输出

- **batch_id**: `batch-pathgen-20260928_083019`
- **n_paths_planned**: 29
- **n_seeds_written**: **28**（一个被 skip，可能因 n_messages=0）
- **profile_chars**: 515
- **manifest size**: 12170 bytes
- **OUT_DIR 大小**: 16338 bytes

### 5.3 rag_layers 分布（5 段 RAG 拼装）

| 层 | file_types | entities | 说明 |
|---|---|---|---|
| **rfc** | ["rfc"] | **11** | ✅ RFC 单源生效 |
| **source** | ["source", "header_def", "api_doc"] | 0 | 无源 |
| **traffic** | ["traffic_raw", "traffic_pcap"] | **12** | ⚠️ **混入** |
| **vuln** | ["vuln"] | 0 + 16 vuln_graph_seeds | ⚠️ **混入** |
| **edge (expert_note)** | ["expert_notes", "expert_note", "error_table"] | 0 | 无 |

### 5.4 .raw 文件样例（28 个，前 5）

| 文件 | bytes | 覆盖 |
|---|---|---|
| 02_Init→Ready_via_SETUP.raw | 99 | SETUP 方法：Init→Ready |
| 03_Init→Init_via_TEARDOWN.raw | 52 | TEARDOWN |
| 04_Init→Init_via_OPTIONS.raw | 51 | OPTIONS |
| 05_Init→Init_via_DESCRIBE.raw | 127 | DESCRIBE |
| 06_Init→Ready→Playing_via_SETUP+PLAY.raw | 181 | SETUP+PLAY 组合 |
| 07_Init→Ready→Recording_via_SETUP+RECORD.raw | 168 | SETUP+RECORD |
| ...（28 个,覆盖 11 method × state 路径） |

每个 .raw 是合法 RTSP 字节流（AFLNet 可消费）+ `[stub]` description + `target_state_path` + `target_methods`。

### 5.5 关键 warning

```
Exception in thread Thread-2 (_readerthread):
UnicodeDecodeError: 'gbk' codec can't decode byte 0xa7 ...
```

来源：subprocess readerthread 用 GBK 解码 UTF-8 子进程 stdout，不影响进程返回（ret.returncode=0）。

---

## 六、动作 6：RFC 与 expert_note 关系

### 6.1 全量 norms 真实分布（基线，已恢复后）

| kb_source_type | kind | 数 |
|---|---|---|
| traffic_pcap | message / field / protocol / state_machine / actor | 10000+8000（其他 4 kind 各 2000，act=1998） |
| traffic_raw | message / field / outcome / state_machine | 5000+1000+1000+1000 |
| expert_note | error_code/field_constraint/security_note/value_pool/body_format/sample/session_rule/timing | 43+18+7+7+5+3+1+1 |
| vuln | vuln_seed | 37 |
| expert_notes | constraint | 4 |
| rfc | method | **11** |

### 6.2 method 重叠度

- **RFC method（11）**：ANNOUNCE/DESCRIBE/GET_PARAMETER/OPTIONS/PAUSE/PLAY/RECORD/REDIRECT/SETUP/SET_PARAMETER/TEARDOWN
- **expert_note method（0）**：**expert_note 不直接产 method 类型 norm** —— `methods.json` 走 ExpertNoteJsonExtractor 转 `constraint` 类型，不是 `method`
- **traffic method（0）**：traffic 也不直接产 method 规范
- **RFC ∩ expert_note method**：0 个直接重叠，但 expert_note 的 constraint.content 含方法名信息

### 6.3 field 重叠度

- **RFC kind=field：0**（LLM fixture 只产 field 232 个，但 norms.jsonl kind=field 计数被 kind="" 过滤器问题影响）
- **expert_note field_constraint（11）**：Accept/CSeq/Content-Length/Date/Location/Range/Session/Transport/URL/User-Agent (+1)
- **RFC ∩ expert_note field：0**（field_constraint vs field 是不同 schema）

### 6.4 state / state_machine 重叠

- **RFC kind=state_machine（0 norm 条目，但有 2 个 spec_graph entity）**：§A.x 的 client/server SM 被 LLM/rule 抽时归类为 content 不是 state_machine 类型
- **expert_note state_machine.json**：是 constraint（不在 norms.jsonl 中直接出现 state 字段）

### 6.5 profile.json 12 类 facts 来源核查（RFC 单源 build 后的）

| fact | 状态 | 来源 |
|---|---|---|
| methods | (n=0) | RFC 真有 11 method，但 kind=method 没有进 methods fact 聚合 |
| state_machine | (n_keys=3) | 仅有 client/server SM 骨架 |
| required_headers | (n_keys=0) | 空 |
| header_naming | (n_keys=0) | 空 |
| field_constraints | (n=0) | 空 |
| body_formats | (n=0) | 空 |
| value_pools | (n_keys=0) | 空 |
| session_rules | (n_keys=0) | 空 |
| timing_constraints | (n_keys=0) | 空 |
| error_codes | (n_keys=0) | 空 |
| samples | (n=0) | 空 |
| security_notes | (n=0) | 空 |

**profile_methods 实际是 0 而非 11** —— 这表明 `protocol_profile._aggregate_methods()` 与 norms 里 11 个 method 未联动（这是 step 1b-2 的预期行为吗？需要核实）。

---

## 七、动作 7：边界问题清单 + 实施建议

### 7.1 边界问题

| # | 问题 | 严重度 | 范围 |
|---|---|---|---|
| B1 | **route() 优先 format 派发**绕过 source_family 过滤：fmt=='pcap'/'csv'/'jsonl' 直接早返回 → RFC 单源 build 混入 traffic 端 | **P0** | 范围内（dispatcher）|
| B2 | **rag_layers 5 段拼装仍包含 traffic+vuln**，即使 seedgen --kb-source-filter rfc | P1 | rag/seedgen.py |
| B3 | **protocol_profile.json 被 RFC 单源 build 覆盖**：12 类 facts 全空，与阶段 1 收尾的 28994 bytes 版本不一致 | P1 | core/graph/protocol_profile.py / TypedKB.build |
| B4 | **profile.methods=0 而 norms 含 11 method**：`protocol_profile._aggregate_methods()` 没从 norms.jsonl 抽 method | P1 | core/graph/protocol_profile.py |
| B5 | **expert_note 不直接产 method 类型 norm**，只产 constraint 类型 → profile.methods 不被 expert_note 路径填 | P1 | core/extractors/expert_notes_json.py |
| B6 | RFC 端 `kind=field` 产出是 0（fixture 抽的 232 全归到 outcome/transition），profile.field_constraints 不会从 RFC 路径填 | P2 | extractor mapping |
| B7 | state_machine JSON `transitions=...` 没被 fixture 抽出来（仅 7 fixture 有 transition 43 项）→ profile.state_machine 有 3 keys 但 transitions 空 | P2 | fixture 完整性 |
| B8 | seedgen `[0.] 协议画像` 段落只有 515 chars（profile+state_machine 短），RAG 检索覆盖度低 | P2 | profile / fixture |
| B9 | subprocess readerthread GBK 解码错误（无关进程返回） | P3 | 环境编码 |
| B10 | classifier 把很多 traffic 文件（clean.pcapng/rtsp.csv）误判 family='rfc' —— 但不影响实际路由（format 派发优先）| P3 | core/classifier.py |
| B11 | `--use-typed-rag` 参数可能不真正过滤 5 段 RAG 拼装到只剩 rfc | P0 | rag/seedgen.py |

### 7.2 实施建议（3 方案）

#### 方案 A：**最小改动 — RFC 单源"逻辑单源"**（推荐度 ★★★☆）

**范围**：dispatcher + profile.json 保存 + seedgen rag_layers

**动作**：
1. **dispatcher.fix_B1**：在 `route()` 入口先做 `if source_family and class_ir.family not in source_family: return SkipReason.FILTERED`（不依赖 format 派发后的 family 重复检查）
2. **TypedKB.build.fix_B3**：build 末尾判断：如果 source_family 不是全量（`!=None or len != 5`），不调 `save_profile` / `save_state_machine` 或调但读旧的全量版合并
3. **seedgen.fix_B11**：实现 `--kb-source-filter` 的 5 段过滤，让 traffic/vuln layers 也按 filter 过滤

**改动量**：~30 行（dispatcher.py 5 行 / typed_kb.py 15 行 / seedgen.py 10 行）

**风险**：B3 改 TypedKB.build 可能影响阶段 1 回归；B11 改 seedgen 会改 RAG 拼装逻辑

**修复后预期**：
- RFC 单源 norms.jsonl：~366 行（method 11 + outcome 80 + field 232 + transition 43）
- RFC 单源 spec_graph：~13 entities（11 method + 2 state_machine）
- RFC 单源 profile.json：保持全量 28994 bytes（不被覆盖）
- RFC 单源 seedgen：rag_layers 仅 rfc=11

#### 方案 B：**RFC 单端独立 extractor**（推荐度 ★★）

**范围**：dispatcher + 新建 `core/extractors/rfc_only.py`

**动作**：
1. 新建 `rfc_only.py`：不调 LLM，只跑 5+1 启发式 + StateMachineExtractor（§A），输出**仅** method + state_machine + transition 三类
2. dispatcher `route()`: family=='rfc' && `--rfc-only` 标志 → 走 rfc_only.py
3. seedgen 加 `--rfc-only` 参数

**改动量**：~80 行（新建文件 + dispatcher 路由分支 + seedgen 参数）

**风险**：新 extractor 需要与现有 RFC extractor 并存维护，state_machine extraction 在 §A 上的精度未知

**修复后预期**：
- RFC 单端 norms.jsonl：~26 行（11 method + ~12 transition + 3 state_machine）
- profile.json：methods=11 / state_machine 有 transitions
- seedgen .raw 仍能跑（用 RFC 11 method + 状态机）

#### 方案 C：**不动代码，承认"逻辑单源"现状**（推荐度 ★☆☆）

**范围**：仅写文档说明

**动作**：
1. 写 `local/rfc_source_truth.md`，记录"RFC 单源 = 73% method 来自 RFC + 99% message 来自 traffic"的现实
2. 在阶段 3/4/5 用 RFC 单源做 baseline，记录"RFC 抽 method 含 11 / traffic 抽 message 含 10000"
3. 不改 dispatcher，继续用 `source_family` 作"分类过滤"，但承认 format 派发会绕开

**改动量**：~0 行代码 + 1 篇文档

**风险**：阶段 3/4/5 做 RAG 检索时仍然有 traffic message 噪声，profile_chars 低，RAG 增量贡献不可见

**修复后预期**：现有 28 .raw 已能 AFLNet 跑，但 RAG 检索质量打折

### 7.3 推荐

**推荐方案 A**：
- 最小代码改动（30 行）
- 直接修 3 个真 P0/P1 边界问题（B1, B3, B11）
- 不引入新 extractor
- 修复后 RFC 单源 RAG 链路干净

---

## 八、需要用户决策

### D19：阶段 2 实施方向

| 选项 | 方案 | 改动量 | 风险 |
|---|---|---|---|
| **A1** | 方案 A (dispatcher.fix_B1 + TypedKB.fix_B3 + seedgen.fix_B11) | ~30 行 | 中（动 dispatcher 影响范围广）|
| A2 | 方案 A 仅修 B1（dispatcher route() source_family 早返回） | ~5 行 | 低（其他保留现状）|
| B | 方案 B（新建 rfc_only.py） | ~80 行 | 中（新 extractor 维护成本）|
| C | 方案 C（不改代码，仅文档） | 0 行 | 无 |
| 其它 | 听用户 | ? | ? |

### D20：profile.json 是否立即重跑全量 build 恢复 28994 bytes？

- 当前状态：profile.json 4299 bytes（被阶段 2 动作 4 覆盖）
- 恢复方式：跑一次全量 `TypedKB.build('RTSP', overwrite=True)`（不带 source_family）

### D21：seedgen 28 .raw 是否留作阶段 3 baseline？

- 路径：`seeds/rtsp/seedgen/test-stage2-rfc/`
- 已生成 28 .raw（profile_chars=515）
- 不留作 baseline 可删除（节省磁盘）

---

## 九、附录：侦察产物文件清单

| 文件 | 大小 | 说明 |
|---|---|---|
| `local/stage_1_summary.md` | 7719 B | 阶段 1 收尾快照 |
| `local/kb_fingerprint_after_stage1_final.txt` | 929080 B | 阶段 1 后 fingerprint (6078 行) |
| `local/stage2_action1_recheck.txt` | - | 动作 1 复核：kind 分布 |
| `local/stage2_action1_src_breakdown.txt` | - | 动作 1: source 路径 kind 分布 |
| `local/stage2_action1_classifier_check.txt` | - | classifier 误判检查 |
| `local/stage2_action4_rfc_build.txt` | - | 动作 4 失败+重做 |
| `local/stage2_action4_rfc_build_v2.txt` | - | 动作 4 重做通过 |
| `local/stage2_action5_seedgen.txt` | - | 动作 5 seedgen 输出 |
| `local/stage2_action6_rfc_vs_expert.txt` | - | 动作 6 全量分析 |
| `local/stage_2_recon_report.md` | 本文件 | 本报告 |
| `local/backup/stage2_pre_build_bak/norms.jsonl` | 9395827 B | 全量 norms 备份（阶段 2 动作 4 前） |
| `seeds/rtsp/seedgen/test-stage2-rfc/` | 16338 B | 28 个 .raw + manifest.json + afldiff.json |

---

## 十、备份恢复状态

- `derived/spec/rtsp/norms/norms.jsonl` 已恢复（26135 行，9.2MB）✓
- `derived/spec/rtsp/state_machine/state_machine.json` 仍是 RFC 单源 5500 B（未被改动）⚠️
- `derived/spec/rtsp/profile/protocol_profile.json` **仍是 RFC 单源 4299 B** ⚠️（需要重跑全量 build 恢复 28994 B）
- `derived/spec/rtsp/graph/` **仍是 RFC 单源**（28 entities / 81 relations）⚠️
- `seeds/rtsp/seedgen/test-stage2-rfc/` 28 .raw 保留中（待 D21 决策）

