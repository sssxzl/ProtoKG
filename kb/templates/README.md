# local/kb_reference/

**2026-09-28 Step 2.0.2 建立**：本目录存放不属于 `kb/` 主扫描路径的 schema 参考与 fixture。

> kb/ dispatcher.extract_kb() 只扫 `kb/` 直接子目录（`expert_note / spec / 历史漏洞 / 数据流量 / 协议实现源码`）。
> 本目录 `local/kb_reference/` 由项目本地代理维护，**不被 dispatcher 扫描**，仅作仓库内的辅助参考。

---

## 子目录

### `expert_note_template/`

13 个 JSON 空白模板 + README，共 14 文件。

- 用途：挂新协议 KB 时，复制本目录到 `kb/spec/<proto>/expert_note/`，然后按文件填空
- 来源：`Step 1c`（2026-09-28 08:06:12）写入 `kb/expert_note_template/`
- 2026-09-28 Step 2.0.2 整体迁出 `kb/` 到本目录
- 顶层 schema 不变（每个文件含 `schema_version: 1` + `protocol: "PROTOCOL_PLACEHOLDER"`），数据字段全空，`_comment` 字段说明用途
- 不被 `dispatcher` / classifier / 测试 直接引用

### `expert_note_minimal/`

3 个文件：`_meta.json` + `methods.json` + `state_machine.json`（minimalproto fixture）。

- 用途：compatibility testing（兼容性测试 fixture）
- 来源：`Step 1c`（2026-09-28 08:06:44）写入 `kb/expert_note_minimal/`
- 2026-09-28 Step 2.0.2 整体迁出 `kb/` 到本目录
- protocol: minimalproto，含 PING/RESET 2 method + Init/Ready 2 state + 3 transitions
- 不被 `tests/` / dispatcher / classifier 直接引用

---

## 维护说明

- 本目录属项目本地运营产物，**不属于 kb/**。
- 任何向 `kb/` 写文件的操作仍受阶段授权窗口约束。
- 若要恢复 dispatcher 扫描路径，请移动回 `kb/expert_note_template/` 与 `kb/expert_note_minimal/`。
