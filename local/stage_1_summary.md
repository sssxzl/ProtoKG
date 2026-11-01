# 阶段 1 收尾快照 · 2026-09-28

> 内部记录 · 不进 docs/。后续阶段 2-5 实施时参照本文。
> 本快照只汇总信息，不重跑测试。

> **2026-09-28 Step 2.0.2 变更记录**：把两个变体目录从 kb/ 顶层迁至 `local/kb_reference/`，kb/ 顶层恢复 5 目录结构（`expert_note / spec / 历史漏洞 / 数据流量 / 协议实现源码`）。kb/derived 空目录已删除。kb/ fingerprint 由 6078 行降为 6061 行（少 17 文件：14 template + 3 minimal）。原始路径记录保留未改，便于回溯。

---

## 一、阶段 1 时间线

| Step | 完成日期 | 关键动作（1 行） |
|---|---|---|
| Step 1a | 2026-09-27 | 链路验证：现有 6 文件 KB → dispatcher → TypedKB → seedgen 全跑通（链路 22 → 22 → 27）|
| Step 1b-1a | 2026-09-27 | KB 结构变更：6 文件 → 13 文件 + field_constraints.json 18 条加 scope 字段 |
| Step 1b-1b | 2026-09-27 | 代码：8 个新 extractor（7 个 + field_constraints scope）+ dispatcher 路由表 + 测试 |
| Step 1b-2 | 2026-09-27 | protocol_profile.json 中枢：12 类 facts 聚合 + seedgen `[0.] 协议画像` 段 + manifest profile_chars |
| Step 1c | 2026-09-28 | 模板化：kb/expert_note_template/（14 文件）+ kb/expert_note_minimal/（3 文件）|
> 注：2026-09-28 Step 2.0.2 已迁出 kb/ 到 local/kb_reference/expert_note_template/ 与 local/kb_reference/expert_note_minimal/，kb/ 顶层恢复 5 目录。|
| Step 1b-2.1 | 2026-09-28 | 诊断 pytest"假挂"：实为慢测试（611 passed in 7.2min），进度条假象 |

---

## 二、KB 结构变更

### 2.1 `kb/expert_note/`：6 → 13 文件

| # | 文件 | 大小 | norm kind |
|---|---|---|---|
| 1 | `_meta.json` | 366 B | AUX_FILE（v2.1.3 skip）|
| 2 | `methods.json` | 863 B | constraint |
| 3 | `required_headers.json` | 518 B | constraint |
| 4 | `state_machine.json` | 2282 B | constraint |
| 5 | `header_naming.json` | 560 B | constraint |
| 6 | `field_constraints.json` | 11516 B | field_constraint（★ 加 scope 字段，18 条）|
| 7 | `body_format.json` ★ | 1302 B | body_format |
| 8 | `value_pool.json` ★ | 1104 B | value_pool |
| 9 | `session_rules.json` ★ | 526 B | session_rule |
| 10 | `timing.json` ★ | 373 B | timing |
| 11 | `error_codes.json` ★ | 1652 B | error_code |
| 12 | `samples.json` ★ | 2614 B | sample |
| 13 | `security_notes.json` ★ | 2844 B | security_note |

合计：25.9 KB / 13 文件

★ = Step 1b-1a 新增 7 文件 + 改 1（field_constraints.json scope 字段）

### 2.2 `kb/expert_note_template/`：13 JSON + README

13 JSON 空白模板（顶层 schema 不变 + 数据字段全空 + `_comment` 字段说明）+ README.md 使用说明。

合计：7.8 KB / 14 文件

> 注：2026-09-28 Step 2.0.2 已迁出到 `local/kb_reference/expert_note_template/`（14 文件 / 7936 B），原始路径记录保留。

### 2.3 `kb/expert_note_minimal/`：3 必填文件

`_meta.json`（minimalproto）+ `methods.json`（PING + RESET）+ `state_machine.json`（Init ↔ Ready）。

合计：0.9 KB / 3 文件

> 注：2026-09-28 Step 2.0.2 已迁出到 `local/kb_reference/expert_note_minimal/`（3 文件 / 930 B），原始路径记录保留。

### 2.4 KB 总文件数（fingerprint）

| 状态 | 行数 | 时间点 |
|---|---|---|
| stage1_locked（6 文件 KB 起点）| 6054 | Step 1a 前 |
| after_step_1b1（13 文件 KB）| 6061 | Step 1b-1 后（+7 net）|
| after_step_1c_final（含 template + minimal）| 6078 | Step 1c 后（+17）|

---

## 三、代码变更（按文件）

### 3.1 新建（M）

| 文件 | 行数 | 用途 |
|---|---|---|
| `core/extractors/body_format.py` | 76 | body_format.json 抽取 |
| `core/extractors/value_pool.py` | 60 | value_pool.json 抽取 |
| `core/extractors/session_rules.py` | 56 | session_rules.json 抽取 |
| `core/extractors/timing.py` | 53 | timing.json 抽取 |
| `core/extractors/error_codes.py` | 65 | error_codes.json 抽取 |
| `core/extractors/samples.py` | 56 | samples.json 抽取 |
| `core/extractors/security_notes.py` | 61 | security_notes.json 抽取 |
| `core/graph/protocol_profile.py` | ~410 | 12 类 facts 聚合 + save/load + source_hashes |
| `rag/profile_query.py` | ~280 | 12 段 markdown 渲染 + DC4 预算裁剪 |
| `tests/graph/test_protocol_profile.py` | 18 用例 | 单测 |
| `tests/integration/test_profile_in_seedgen.py` | 4 用例 | e2e（含 subprocess）|
| `tests/integration/test_expert_note_13files.py` | 6 用例 | 13 文件 e2e（含 _meta AUX_FILE 验证）|
| `tests/extractors/test_*_extractor.py` × 7 | 21 用例 | 7 个新 extractor 单测（3 用例/文件）|
| `docs/expert_note_schema.md` | ~14000 B | 13 文件 schema 参考 |
| `docs/protocol_profile_schema.md` | ~9700 B | protocol_profile.json schema 参考 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `core/extractors/field_constraints.py` | 加 scope 字段读取（facets 含 `scope:{value}`）|
| `core/extractor_dispatcher.py` | 加 7 个 import + EXPERT_NOTE_STEM_TO_EXTRACTOR 表 +7 行 |
| `core/stores.py` | JsonlProtocolNormStore 加 profile_path / save_profile / load_profile 3 方法 |
| `core/graph/typed_kb.py` | build() 末尾调 build_protocol_profile + save_profile |
| `pipeline/seedgen/path_prompts.py` | render_path_construction_prompt_typed 加 protocol_facts 参数 + _format_protocol_facts helper |
| `pipeline/seedgen/path_builder.py` | build_path_seed 加 protocol_facts + build_all_path_seeds 调 query_protocol_facts |
| `pipeline/seedgen/path_writer.py` | write_seed_batch 加 profile_chars 参数 + manifest 写入 |
| `rag/seedgen.py` | --use-typed-rag 时 load profile + 传 build_all_path_seeds + 传 write_seed_batch |
| `tests/integration/_norm_schema.py` | KINDS_8 → KINDS_15（含 7 新 kind）|

---

## 四、测试基线

| 阶段 | passed | failed | errors | skipped | deselected | 总时长 |
|---|---|---|---|---|---|---|
| Step 8.2 收尾（前置）| 562 | 0 | 0 | 5 | 2 | - |
| Step 1b-1b 收尾 | 589 | 0 | 0 | 5 | 2 | - |
| **阶段 1 收尾** | **611** | **0** | **0** | **5** | **2** | **7.2 min** |

passed 增量 +49（阶段 1）：
- Step 1b-1a：+21（21 个新 extractor 单测）
- Step 1b-1b：+6（6 个 13-files e2e）
- Step 1b-2：+18（18 个 profile 单测）+ 4（4 个 profile e2e）
- 合计：+49 ✓

（注：阶段 1 总增 611-562=49 测试，符合）

---

## 五、KB fingerprint 状态

```
stage1_locked:  6054 行（6 文件 KB baseline）
after_1b1:      6061 行（+7 net: 7 新 + 1 改）
after_1c:       6078 行（+17: 14 template + 3 minimal）
```

**kb/expert_note/ 现有 13 文件 UNCHANGED**（fingerprint 与 after_1b1 一致）。

指纹操作规范（每阶段）：
```
python local/kb_fingerprint.py kb > local/kb_fingerprint_after_<step>.txt
python -c "<diff>"  # 验证新增/删除/修改行
```

---

## 六、阶段 1 遗留项（记录不改）

### 6.1 norms.jsonl 路径差异

- 文档预期：`derived/rtsp/norms/norms.jsonl`
- 实际：`derived/spec/rtsp/norms/norms.jsonl`
- 链路正常通（代码层面有正确处理）
- **不修**

### 6.2 对照实验

完整 KB vs 最小 KB vs 全空白 —— 用户已明确延后

### 6.3 永久 skip 测试

- `tests/test_step2b_endtoend.py::test_discovery_mymodbus_generated_file_exists` —— 永久 skip（mymodbus 不在 KB 中）
- 不动

### 6.4 baseline 测试修复（已处理）

- Step 1b-2 修 `tests/integration/_norm_schema.py`：`KINDS_8` → `KINDS_15`（含 7 新 kind）
- 修前 1 个 test_existing_rfc_norms_pass_schema 失败，修后 18 passed

### 6.5 pytest "假挂" 现象

- `tests/conftest.py` 的 `_protect_derived` autouse fixture 每次 test 复制 derived/ → snapshot
- 全量 pytest 跑完需 6-8 分钟（非 hang 是慢测试）
- 进度条只在 file 边界更新，容易误判
- 详见 Step 1b-2.1 诊断报告

---

## 七、阶段 1 KB 授权窗口已关闭

| 阶段 | 授权窗口 |
|---|---|
| 阶段 0.5（前置）| kb/ 全程 read-only |
| Step 1b-1 | 写 kb/expert_note/（补 13 文件）|
| Step 1c | 新建 kb/expert_note_template/ + kb/expert_note_minimal/ |
| **阶段 1 收尾后** | **kb/ 回到 read-only** |
| 阶段 2-5 | 各阶段各自有授权窗口，未到阶段不允许写 kb/ |

---

## 八、阶段 2 入口

阶段 2 目标：RFC（spec）独立驱动到 seedgen 生成 .raw。

- 输入：`kb/spec/rfc2326.txt`（RTSP RFC 2326 全文）
- 验收：dispatcher 识别 rfc family → rfc extractor 抽 norm → TypedKB.build → seedgen 单源 → .raw AFLNet 可消费
- 当前：阶段 2 前置侦察中