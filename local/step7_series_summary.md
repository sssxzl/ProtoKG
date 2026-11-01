# Step 7 系列总结 — 字段约束一等公民化 (v2.3.1)

## 时间: 2026-09-24 ~ 2026-09-26
## 起因: 12h ChatAFL 实测 ProtoRAG 种子稳定性 3.16% vs ChatAFL 10.57%

## 4 步修复链路

| Step | 问题 | 修法 | 文件 | 验收 |
|---|---|---|---|---|
| **7 预算** | [5.] 段 5 子段被 `_trim(2000)` 一刀切, 字段约束段只剩 92 chars (Version + truncated) | rag_context.py 加 EDGE_SEGMENT_BUDGETS dict (5 子段分段预算); path_prompts.py:466 不再 trim edge_context | `rag/rag_context.py`, `pipeline/seedgen/path_prompts.py` | payload user 9050 → 13759 chars (+4500) |
| **7b 强制轮转** | LLM 只从 KB 选 2/6 User-Agent, 1/3 Accept (LLM 选最典型值, 不按分布) | path_prompts.py 加 _extract_field_candidates + _render_field_rotation_block; build_path_seed 接 spec_graph+path_index; prompt 末尾追加 rotation_block | `pipeline/seedgen/path_prompts.py`, `pipeline/seedgen/path_builder.py` | User-Agent 2 → 6, Accept 1 → 3 (45 paths 完整轮转) |
| **7c 强制写 header** | 含 DESCRIBE 的 5 个种子 Accept 仅 1/4 出现 (LLM 看到 application/sdp 是 "默认值" 跳过) | rotation_block 开头加 ⚠️ 强制规则: "必填 header 即使是默认值也必须显式写" | `pipeline/seedgen/path_prompts.py` (_render_field_rotation_block 开头) | 含 DESCRIBE 5/5 全部 Accept |
| **7d URL 去硬编码** | `_rtsp_to_raw` 默认 `url="rtsp://localhost/seed"`, URL distinct = 1 | KB URL constraint_raw 改 `{{target_host}}:{{target_port}}` 占位符; build_path_seed 按 path_index 选 KB URL 候选; `seed.selected_url` 注入; write_seed_batch 读 selected_url 传给 seedcorpus_to_raw | `kb/spec/rtsp/expert_note/field_constraints.json`, `pipeline/seedgen/path_prompts.py` (_extract_url_candidates), `pipeline/seedgen/path_builder.py`, `pipeline/seedgen/path_writer.py`, `core/rtsp_raw.py` | URL distinct 1 → 3 |

## 最终验收 (Step 7d batch-pathgen-20260926_012323)

| # | 项目 | 期望 | 实际 |
|---|---|---|---|
| 1 | User-Agent distinct | ≥ 3 | **6** (K=6 全轮转) ✅ |
| 2 | Accept distinct | ≥ 2 | **2** (rtsl + */*, 含 DESCRIBE 5/5) ✅ |
| 3 | URL distinct | ≥ 1 | **3** (KB 候选轮转) ✅ |
| 4 | Session 4/4 hex | 4/4 | ✅ (stub `12345678` 保持) |
| 5 | Date HTTP-date | OK | ✅ |
| 6 | 自造 header | 0 | **0** ✅ |
| 7 | 占位符残留 (白名单外) | 0 | **0** ✅ |
| 8 | n_seeds_written | ≥ 30 | **42** (n_paths_planned 43, n_skipped_no_messages 1) |

## pytest

```
================ 521 passed, 1 skipped, 2 deselected in 49.01s ================
```

(基线 520 → 521, +1 新测试 test_seedcorpus_to_raw_uses_selected_url_override)

## 影响

1. **12h ChatAFL baseline 要重跑** (URL 变化 + 字段多样性提升, 旧 batch 对比失效)
   - 旧 batch URL: `rtsp://localhost/seed` (host 不存在, server 立刻 404)
   - 新 batch URL: `rtsp://127.0.0.1:8554/mp3AudioTest/...` (live555 默认地址)
   - 详见 `local/todo_url_change_baseline_impact.md`

2. **论文 §5 字段多样性表数据要更新**:
   - 字段 distinct counts 之前低估 (Step 7 之前)
   - 论文写作时引用 Step 7d 数据为准

3. **Step 7 之前的 KB 编辑可以重新审计**:
   - field_constraints.json 10985 bytes, 18 条约束
   - Step 7 系列保证每条约束在 prompt 中保原格式

## 关键文件

- `local/todo_url_change_baseline_impact.md` (URL 变化 + baseline)
- `local/todo_accept_coverage_low.md` (Accept 5/5 但 distinct=2 是巧合)
- `local/todo_dump_script_message_iteration.md` (dump 脚本遍历所有 message)
- `local/todo_field_rotation_retry.md` (retry 时 path_index 不变)
- `local/todo_url_template_hardcoded.md` (P0-2 之前, 已被 Step 7d 修)
- `local/todo_field_constraint_subtype.md` (未来引入 sub_type 字段)
- `local/todo_kb_source_types_dual_naming.md` (expert_note 单/复数)

## 未修 (本轮范围外)

- **P0-3**: `_RTSP_TRANSITIONS` 硬编码 10 条 (line 33-44) — KB 已有 27 条, 跟 KB 走双轨
- **Accept 100% 覆盖** (K=3 完整轮转) — 当前 2/3 是 path 枚举巧合, 不阻塞主线

## 总结

字段约束从 KB 一等公民化, 全链路保原格式 ([5. 段从 92 chars → 9684 chars], [User-Agent 2 → 6], [URL 1 → 3]).
字段多样性达到设计目标 (User-Agent 6/6, URL 3/3).
论文 §5 数据可更新为 Step 7d 验收结果.