# expert_note_template · 协议 KB 模板

> 用途：**挂新协议 KB 时复制本目录到 `kb/spec/<proto>/expert_note/`** 然后按文件填空。
> 模板本身**不被 dispatcher 抽取**（不在 kb/ 主路径下），仅作 schema 参考 + 占位。

---

## 1. 13 文件清单 + 用途

| # | 文件 | 必填？ | 用途（1 行） |
|---|---|---|---|
| 1 | `_meta.json` | ★★★ | KB 元信息（protocol / display_name / sources / maintainer）|
| 2 | `methods.json` | ★★★ | method 白名单（每个 verb 一个 entry）|
| 3 | `state_machine.json` | ★★★ | 状态机（states / initial_state / transitions）|
| 4 | `required_headers.json` | ★★ | 每个 method 必填 header 列表 |
| 5 | `header_naming.json` | ★★ | header 命名规范（标准集 / 大小写不敏感 / 特殊映射）|
| 6 | `field_constraints.json` | ★★ | header 字段格式约束（ABNF / 语义 / 观测值）|
| 7 | `body_format.json` | ★ | method 的 body 格式（MIME / schema_ref）|
| 8 | `value_pool.json` | ★ | 字段候选值池（有限候选值的 header/URL）|
| 9 | `session_rules.json` | ○ | session 生命周期规则（无 session 协议可省略）|
| 10 | `timing.json` | ○ | 时序约束（超时 / 重试 / keepalive）|
| 11 | `error_codes.json` | ○ | 错误码列表（按 class 分组）|
| 12 | `samples.json` | ○ | 真实报文样例（RFC 例子或抓包）|
| 13 | `security_notes.json` | ○ | 历史漏洞注记（CVE 触发条件 + 缓解措施）|

★★★ = 必填（KB 协议级最小可运行集）
★★ = 推荐填（让 seedgen + RAG 5 段正常生成）
★ = 选填但强烈推荐
○ = 选填（协议特性无则省略）

---

## 2. 必填文件 3 个

`_meta.json` / `methods.json` / `state_machine.json` —— 缺这 3 个 dispatcher 不会抽取该协议。

---

## 3. 空白表达方式

- **缺字段**：完全不写该字段（不要 `null`），除非是显式语义空（如 `timing.inter_request_gap_ms: null` 表示"无约束"）
- **空列表 / 空 dict**：保留字段但写 `[]` 或 `{}`（schema 完整 + 未来扩展便利）
- **缺失条目**：不写，不允许占位符字符串（如 `"TBD"`）

---

## 4. 使用方式

```bash
# 1. 复制整个目录
cp -r kb/expert_note_template kb/spec/mqtt/expert_note

# 2. 替换 PROTOCOL_PLACEHOLDER 为小写协议名 (e.g. 'mqtt', 'sip', 'coap')
#    修改 _meta.json 的 display_name / last_updated / sources / maintainer

# 3. 填空：按上面 13 文件清单填实际协议知识

# 4. 验证：
pytest tests/integration/test_expert_note_13files.py
```

---

## 5. 最小协议模板（如果只需要 3 必填文件）

参考 `kb/expert_note_minimal/` 目录 —— 只含 `_meta.json` / `methods.json` / `state_machine.json` 3 文件，可直接用于陌生 KB 兼容性测试。

---

## 6. 详细 schema 参考

详见 `docs/expert_note_schema.md`（Step 1b-1b 建），包含每个文件的完整字段表 + 示例 JSON。

---

## 7. dispatcher 抽取规则（参考，非模板内容）

- 文件名 `*.json` + 路径含 `expert_note/` → `source_family: expert_note`
- `path.stem` 在 `EXPERT_NOTE_STEM_TO_EXTRACTOR` 表中 → 走专用 extractor
- 其他 → `ExpertNoteJsonExtractor` 兜底（整 JSON 作为 1 个 norm）

7 新 extractor（Step 1b-1）：
- `body_format` / `value_pool` / `session_rules` / `timing` / `error_codes` / `samples` / `security_notes`

`field_constraints` 走专用 extractor，每个 entry 1 个 norm；其他 5 文件（`_meta` / `methods` / `required_headers` / `state_machine` / `header_naming`）走兜底，每文件 1 个 norm。