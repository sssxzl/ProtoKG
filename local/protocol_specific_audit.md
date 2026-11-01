# 阶段 0.5 协议无关化盘点 (v2.3.1 P1-5)

**生成日期**: 2026-09-27
**目的**: 盘点代码中协议特化 (RTSP / TCP / DNS) 的硬编码，输出动作清单 (DELETE / REFACTOR / KEEP) 和工作量估算。

**背景**: 用户质问"代码针对具体协议的工作都无意义"——`protocols/rtsp.py` / `tcp.py` / `dns.py` + 相关 test_protocol_adapter.py 是历史遗留（恰好写过这 3 个协议），不属于 ProtoRAG 论文贡献 (1)。下一步应该**真正协议无关化**，让 KB / dispatcher / raw_writer 完全协议无关，新增协议 = 新建 KB 即可，**不需要写 Python 代码**。

---

## 1. 文件总览（行数 = 有效代码行）

| 文件 | 行数 | 性质 |
|---|---|---|
| `protocols/rtsp.py` | 69 | 协议特化 (KB shim) |
| `protocols/tcp.py` | 88 | 协议特化 (KB shim + frame parser) |
| `protocols/dns.py` | 109 | 协议特化 (KB shim + frame parser) |
| `core/raw_writers.py` | 470 | **混合**：协议无关入口 + 4 个协议特化 writer + RTSP reverse parser |
| `core/protocol_adapter.py` | 139 | **混合**：BaseProtocolAdapter 通用 + RTSPAdapter shim |
| `core/registry.py` | 231 | **混合**：通用 registry + 协议特化 register_adapter/frame_parser |
| `tests/test_protocol_adapter.py` | 251 | 协议特化测试 (40 个：RTSP/TCP/DNS Adapter) |
| `tests/integration/test_rtsp_kb_pipeline.py` | 337 | RTSP 数据相关 (KB 抽 norm), **KEEP** |
| `tests/integration/test_kb_adapter.py` | 261 | KB adapter 测试 (阶段 0 改完, 15/15 PASS) |
| `tests/integration/test_joint_constraint_kb.py` | 49 | JointConstraint KB 入口 (2/2 PASS) |

---

## 2. 协议特化代码定位 (来自 ripgrep)

### 2.1 protocols/*.py (3 文件 / 266 lines)

| 位置 | 形式 | 动作 | 工作量 |
|---|---|---|---|
| `protocols/rtsp.py:28` | `@register_frame_parser(protocol="RTSP")` | DELETE | 0.5h |
| `protocols/rtsp.py:69` | `@register_adapter(protocol="RTSP")` | DELETE | 同上 |
| `protocols/rtsp.py:78` | `protocol = "RTSP"` | DELETE | 同上 |
| `protocols/tcp.py:47` | `@register_frame_parser(protocol="TCP")` | DELETE | 0.5h |
| `protocols/tcp.py:85` | `@register_adapter(protocol="TCP")` | DELETE | 同上 |
| `protocols/tcp.py:93` | `protocol = "TCP"` | DELETE | 同上 |
| `protocols/dns.py:44` | `@register_frame_parser(protocol="DNS")` | DELETE | 0.5h |
| `protocols/dns.py:106` | `@register_adapter(protocol="DNS")` | DELETE | 同上 |
| `protocols/dns.py:114` | `protocol = "DNS"` | DELETE | 同上 |

**说明** (P1-5 收紧 3 后): `protocols/*.py` 每个文件结构拆 2 类：

| 类 | 形式 | 行数估算 | 动作 |
|---|---|---|---|
| **Frame parser** (二进制字节解析) | tcp.py L48-83 (`parse_tcp_frames`), dns.py L45-104 (`parse_dns_frames`), + 辅助函数 `_flags_to_method` / `_decode_qname` | ~96 行 | **MOVE → `core/extractors/parsers/tcp.py` / `core/extractors/parsers/dns.py`**（重新分类为"通用二进制解析能力"） |
| **Adapter shim** (KB shim) | `class ProtocolAdapter(KBProtocolAdapter): __init__(load_kb_adapter)` | tcp.py ~19 行 + dns.py ~22 行 | **DELETE** |

**注册入口改造**: `@register_frame_parser("TCP")` / `@register_frame_parser("DNS")` **改成 KB-driven**——启动时从 `kb/<proto>/_meta.json` 读 frame_parser 字段名，自动从 `core/extractors/parsers/<proto>.py` 调 `parse_<proto>_frames()`。

**RTSP 文本协议**: `protocols/rtsp.py` 没有 frame parser（RTSP 走文本解析），整个文件删除。

**总工作量**: protocols/ 全部协议特化改造 — **2.5h**（MOVE 2 个 frame parser 0.5h + DELETE 3 个 shim 0.5h + 改 register 入口 1h + 验证 0.5h）

### 2.2 core/raw_writers.py (470 lines / ~200 lines 是协议特化)

| 位置 | 形式 | 动作 | 工作量 |
|---|---|---|---|
| line 58 | `from protocols.rtsp import ProtocolAdapter` (KB shim 引用) | DELETE 依赖 | — |
| line 68-103 | `parse_rtsp_raw()` RTSP-specific reverse parser | DELETE | 0.5h |
| line 105-128 | `_infer_state_path()` RTSP-specific state machine | DELETE | 0.3h |
| line 131-176 | `raw_to_seedcorpus()` 含 RTSP-specific 部分 | REFACTOR → 通用 reverse parser | 1h |
| line 179-222 | `_load_request_format_from_kb()` KB-driven 加载器 | **KEEP** | — |
| line 224-275 | `_generic_to_raw()` 协议无关通用 writer | **KEEP** | — |
| line 277-352 | `seedcorpus_to_raw()` 协议无关入口 | **KEEP** | — |
| line 355-450 | 注释 + 部分常量 (`RTSP-001 setup header` 等) | 删 RTSP-specific 注释 | 0.2h |
| line 459-491 | `_rtsp_to_raw()` RTSP 文本格式 writer | DELETE (KB-driven `_generic_to_raw` 替代) | 1h |
| line 493-550 | `_tcp_to_raw()` TCP binary writer | DELETE / KEEP 二选一 (见说明) | 1h |
| line 553-595 | `_dns_to_raw()` DNS binary writer | DELETE / KEEP 二选一 | 1h |
| line 599-621 | `_http_to_raw()` HTTP writer (历史, 可能 unused) | DELETE (验证没人调) | 0.2h |

**说明** (P1-5 收紧 2 后): `_tcp_to_raw` / `_dns_to_raw` / `_rtsp_to_raw` / `_http_to_raw` 是否 KB 化，需要回答 3 个问题：

**Q1: TCP flag/seq/ack 编码能否用 KB 描述？**
- TCP header 20B：sport(2) + dport(2) + seq(4) + ack(4) + data_offset/flags(2) + window(2) + checksum(2) + urgent(2)
- KB 描述需要：字段名 + offset + 长度 + 类型(u8/u16be/u32be) + 默认值或表达式
- **结论**: **A 可行但复杂**（需要 binary schema 描述语言）

**Q2: DNS TLV 格式能否用 KB 描述？**
- DNS header(12B) + QNAME(变长 labels 用长度前缀编码) + QTYPE/QCLASS(2B) + 可能压缩指针
- 变长 labels + 压缩指针 + 嵌套指针让 KB 描述极复杂
- **结论**: **A 不可行**

**Q3: 是否承认"二进制协议需要 writer，但 writer 是通用能力不是协议特化"？**
- 类比：JSON serializer 是通用能力（不针对具体协议，但能序列化任意 dict）
- 类比：compression 是通用能力（zlib 不针对具体数据格式）
- **结论**: 是的——**binary serializer 是通用能力**，不算"协议特化代码"

**3 个方案选择**：

| 方案 | A: 全部 KB 化 | B: 通用 binary serializer | C: 通用 binary schema + serializer |
|---|---|---|---|
| KB 描述 | `request_format.json` + `binary_format.json` | `binary_format` 字段名 + 默认 writer | 完整 binary schema 描述语言 |
| 代码 | `_rtsp_to_raw` 等删，仅 `_generic_to_raw` | 加 `_binary_to_raw(spec, seed) -> bytes` | 加通用 binary serializer (~300 行) |
| RTSP | A 走 `_generic_to_raw`（文本） | B 走 `_generic_to_raw`（文本） | C 走通用 serializer |
| TCP | A 需要 KB 描述 bit 位 | B 用通用 `_binary_to_raw` 处理 spec | C 用通用 serializer |
| DNS | A **不可行**（变长 labels） | B 用通用 `_binary_to_raw` 处理 spec | C 用通用 serializer |
| 工作量 | 4h（写 KB 不算代码工作量） | **3h**（加 `_binary_to_raw` + KB 字段） | 12h（写通用 serializer） |
| 风险 | DNS / 复杂二进制协议 KB 难维护 | 中（需设计 binary_format spec 格式） | 低（最强通用） |

**推荐 B**：
- `_rtsp_to_raw` / `_tcp_to_raw` / `_dns_to_raw` / `_http_to_raw` **DELETE**
- 加 `_binary_to_raw(seed, binary_format_spec) -> bytes` 通用函数（类似 `json.dumps` 通用能力）
- KB `request_format.json` 加 `binary_format` 字段，描述 binary 协议布局
- TCP / DNS KB 在阶段 0.5 之后写 `binary_format` spec（不动 KB，由用户纪律决定是否写）
- 现在可以写 KB TCP/DNS 数据（**违反用户纪律**，暂不写），先在 KB schema 里定义 `binary_format` 字段格式

**B 方案剩余风险**:
- binary_format spec 设计要复杂（flags bit 位、变长字段、嵌套结构）
- 用户可能觉得"又写了一份 DSL"
- 但 B 是**唯一真正协议无关**的方案

**总工作量**: raw_writers.py 协议特化清理 (B 方案) — **3h**（4 个 writer 删除 0.5h + `_binary_to_raw` 设计 + 实现 2h + 集成 + 验证 0.5h）

### 2.3 core/protocol_adapter.py (139 lines / 0 处真实协议特化)

**审计 bug (P1-5 收紧后修正)**:
- 原 audit 写"`line 9 @register_adapter("RTSP")` + `line 11-72 RTSPAdapter shim`" → **实际是 docstring 示例代码，不是真装饰器/类定义**
- 真实 `core/protocol_adapter.py` 只有 2 个 class:
  - line 29 `BaseProtocolAdapter`（KEEP，协议无关基类）
  - line 158 `GenericAdapter`（KEEP，未注册协议兜底）

| 位置 | 形式 | 动作 | 工作量 |
|---|---|---|---|
| 无真实协议特化代码 | — | **KEEP** | 0h |

**说明**: RTSPAdapter shim 不在 `protocol_adapter.py`，而是在 `protocols/rtsp.py`（Step 3 处理）。原审计误判 → **Step 1 跳过**。

**总工作量**: protocol_adapter.py — **0h**（无协议特化）

### 2.4 core/registry.py (231 lines / 3 处 register_adapter + 3 处 register_frame_parser)

| 位置 | 形式 | 动作 | 工作量 |
|---|---|---|---|
| line 208 | `@register_adapter(protocol="RTSP")` | DELETE / REFACTOR → KB-driven | — |
| line 210 | `protocol = "RTSP"` | DELETE | — |
| line ~80 | `@register_frame_parser(protocol="RTSP")` (估计) | DELETE / REFACTOR → KB-driven | — |
| line ~120 | `@register_frame_parser(protocol="TCP")` (估计) | DELETE / REFACTOR | — |
| line ~140 | `@register_frame_parser(protocol="DNS")` (估计) | DELETE / REFACTOR | — |

**说明**: registry 的协议特化注册入口应该改成 **KB-driven**：
- 启动时从 `kb/registry.json` (或每个协议 KB 里的 `_meta.json`) 读所有协议名
- 自动调 `register_adapter(protocol=name)` / `register_frame_parser(protocol=name)` 用 KBProtocolAdapter + 协议特化 frame parser (如果有)
- **不再硬编码** "RTSP" / "TCP" / "DNS"

**总工作量**: registry.py 改 KB-driven — **2h**

### 2.5 tests/test_protocol_adapter.py (251 lines / 40 个测试)

**P1-5 收紧 (诊断 2)**:

| 类别 | 数量 | 状态 | 动作 |
|---|---|---|---|
| BaseAdapter 通用 (`test_baserequires_*`, `test_base_adapter_*`) | 5 | PASS | **KEEP** |
| GenericAdapter 通用 (`test_generic_adapter_*`) | 5 | PASS | **KEEP** |
| from_protocol 未知/大小写/or_none | 3 | PASS | **KEEP** |
| from_protocol RTSP/TCP/DNS (`test_from_protocol_rtsp/tcp/dns_returns_*_adapter`) | 3 | RTSP PASS / TCP+DNS FAIL | **DELETE** |
| RTSP known/required/transitions/canonical (`test_rtsp_*`) | 7 | PASS | **DELETE** (测 RTSPAdapter shim) |
| TCP (`test_tcp_*`) | 5 | FAIL | **DELETE** (测 TCPAdapter shim) |
| DNS (`test_dns_*`) | 5 | FAIL | **DELETE** (测 DNSAdapter shim) |
| all_adapters_returns_3 / get_adapter_returns_spec | 2 | PASS | **DELETE** (依赖 shim 注册) |
| get_adapter_unknown_returns_none | 1 | PASS | **KEEP** |
| JointConstraint RTSP/TCP (`test_jointconstraint_uses_rtsp/tcp_adapter`) | 2 | RTSP PASS / TCP FAIL | **DELETE** (依赖 shim) |
| JointConstraint unknown/explicit | 2 | PASS | **KEEP** |

**总**: KEEP 16 + DELETE 24 = 40（**之前 audit 估 30 个偏少，实际 24 个该删**）

**说明**: RTSPAdapter shim 测试如果 RTSPAdapter 删除就一起删。TCP/DNS 10 个 fail 测试本来就要删（用户 todo 已知）。

**总工作量**: 删 24 个 shim 测试 + 3 行 import — **0.3h**

### 2.6 tests/integration/test_rtsp_kb_pipeline.py (337 lines)

**收紧 1 (P1-5 阶段 0.5)**:

| 旧 | 新 |
|---|---|
| 文件名 `test_rtsp_kb_pipeline.py` | `test_kb_pipeline.py` (RENAME) |
| Class `TestRtspTrafficExtraction` 等硬编码 RTSP | `TestKbPipelineTrafficExtraction` + `@pytest.mark.parametrize("protocol, kb_root", [("RTSP", Path("kb")), ("FAKEPROTO", Path("tests/fixtures/kb"))])` |
| fixture `udp_0001_dir = PROJECT_ROOT/kb/spec/rtsp/数据流量/...` | fixture 参数化按 protocol 算路径 (RTSP 走扁平 `kb/数据流量`, FAKEPROTO 走嵌套 `tests/fixtures/kb/spec/fakeproto/...`) |
| Line 459 CLI 文档示例 `--kb-root kb/spec/rtsp` | 改成 `--kb-root kb` (跟实际一致) |

**动作**: **RENAME + PARAMETRIZE**

**工作量**: 0.5h

**说明**: RTSP 改成 KB pipeline 通用测试后，新增协议只需加一行 parametrize，不需要写新测试文件。

---

## 3. 总工作量估算 (P1-5 收紧 + 诊断 1+2+3 后)

| 任务 | 工作量 |
|---|---|
| ~~protocol_adapter.py 删 RTSPAdapter~~ (审计误判, 跳过) | **0h** |
| DELETE tests/test_protocol_adapter.py 24 个 shim 测试 + 3 行 import | **0.3h** |
| DELETE protocols/*.py (3 文件 / 266 lines, 含 2 个 frame parser MOVE 到 core/extractors/parsers/) | **2h** |
| REFACTOR test_constraint.py (4 处 import 改 KB-driven, 用 KBProtocolAdapter 替代硬编码常量) | **0.5h** |
| REFACTOR rag/seedgen.py 删 3 行 import + core/raw_writers.py L58 删依赖 | **0.3h** |
| REFACTOR core/registry.py (改 KB-driven 注册 + frame parser 动态加载) | **2h** |
| REFACTOR core/raw_writers.py (B 方案精简: 删 _tcp/_dns/_http writer, 保留 _rtsp + _generic) | **1h** |
| REFACTOR tests/test_protocols.py (3 处 import 改 core.extractors.parsers.* 路径) | **0.3h** |
| RENAME + PARAMETRIZE tests/integration/test_rtsp_kb_pipeline.py → test_kb_pipeline.py | **0.5h** |
| pytest 验证 | **1h** |
| **总计** | **7.9h** (≈ 1.5 个工作日) |

### 不在本阶段范围（未来阶段）

- `rag/protocol_discovery.py` (470 lines): 自动生成 `protocols/<proto>.py` 的 LLM 工具
  - 阶段 0.5 后设计过时（KB-driven 后不需要 Python 代码）
  - **未来阶段**: 改为"自动生成 KB 协议描述"或"废弃整个文件"
  - 暂不动

### 修改测试 fixture 影响

- `tests/test_constraint.py:22-28` 用了 `RTSPAdapter.KNOWN_METHODS` 等硬编码常量
  - 改法: 改用 `load_kb_adapter("kb", "RTSP")._methods` 等 KB-driven
  - 工作量已算入 Step 3.5

---

## 3. 总工作量估算

| 任务 | 工作量 |
|---|---|
| DELETE protocols/*.py (3 文件 / 266 lines) | **2h** |
| REFACTOR core/raw_writers.py 协议特化清理 (~200 lines) | **4h** |
| REFACTOR core/protocol_adapter.py (RTSPAdapter shim 删) | **0.5h** |
| REFACTOR core/registry.py (改 KB-driven 注册) | **2h** |
| DELETE tests/test_protocol_adapter.py 30 个 shim 测试 | **0.5h** |
| **总计** | **9h** (≈ 1.5 个工作日) |

---

## 4. 动作清单 (按依赖顺序, P1-5 收紧 + 诊断 1+2+3 后)

1. ~~**Step 1** 删 protocol_adapter.py 里 RTSPAdapter shim~~ → **审计误判, 跳过** (0h)
2. **Step 2** (0.3h): `tests/test_protocol_adapter.py` 删 24 个 shim 测试 + 3 行 import
3. **Step 3** (2h): `protocols/*.py` 删 3 文件 + 2 个 frame parser MOVE 到 `core/extractors/parsers/` + 改 `tests/test_protocols.py` import 路径 (0.3h)
4. **Step 3.5** (0.5h): `tests/test_constraint.py` 4 处 import + 硬编码常量改 KB-driven
5. **Step 3.6** (0.3h): `rag/seedgen.py` 删 3 行 import + `core/raw_writers.py` L58 删依赖
6. **Step 4** (2h): `core/registry.py` 改 KB-driven 注册 + frame parser 从 `core/extractors/parsers/` 动态加载
7. **Step 5** (1h): `core/raw_writers.py` 删 _tcp_to_raw / _dns_to_raw / _http_to_raw (3 个 writer); 保留 _rtsp_to_raw + _generic_to_raw
8. **Step 6** (0.5h): `tests/integration/test_rtsp_kb_pipeline.py` RENAME → `test_kb_pipeline.py` + `@pytest.mark.parametrize` 改造
9. **Step 7** (1h): pytest 全套验证 — 期望 502 passed + 4 skipped + 2 deselected

---

## 5. 不做（用户纪律）

- 不修 TCP/DNS 10 个测试 (本就是 shim 代码的产物)
- 不假装 512 passed 是"完成"
- 不继续 Step 2.8 的 pytest 全绿目标（剩下的 10 fail 是协议特化的证据）
- 不在本阶段写 KB（KB 永久不动，KB 是 single source of truth）

---

## 6. 风险与依赖

- **风险 1**: protocols/*.py 删除后，`protocols/rtsp.py:KB shim` 引用的 `_rtsp_to_raw` / `parse_rtsp_raw` 链路需要从 raw_writers.py 删干净
- **风险 2**: registry.py 改 KB-driven 后，启动流程需要在 `core/` 初始化时显式调 `load_registry_from_kb()`
- **风险 3**: 用户 RTSP 测试还在跑 (RTSPAdapter 测试虽然删了，但 RTSP data flow 测试在 test_rtsp_kb_pipeline.py 保留)

---

## 7. 给用户建议

**下一步**: 阶段 0.5 按动作清单分 5 步走，每步独立 commit，pytest 验证。

**预期**:
- 阶段 0.5 完成后: `protocols/*.py` 文件不存在（或只剩 frame parser 工具），`raw_writers.py` 协议无关化，新增协议 = 新建 KB，**0 行 Python 代码**
- pytest 期望: 502 passed + 4 skipped + 2 deselected (比当前少 10 个 TCP/DNS fail + 30 个 shim 测试删了)
- 论文贡献 (1) 真正实现: "协议无关 main + KB 驱动"

**不做**:
- 阶段 1-5 (单源调试) 等阶段 0.5 完成后才能进 (因为涉及修改 raw_writers.py 协议无关部分)
- 改 KB 内容 (用户纪律)
- 改业务逻辑 (只改路径解析 + 删协议特化)