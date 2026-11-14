# RFC 内容形态分类与通用抽取落地方案

> ★ **2026-11-10 更新**：英文措辞判据 `_RE_STATE_MACHINE_HINT`（`state\s+machines?`）
> **已移除**（不做并集）⇒ 现只用**实体共现**判据；实测删除对 rtsp 抽取**零影响**（仍 14 条）。

> 日期：2026-11-05
> 定位纠正：本文档取代前序「状态机抽取方法谱系与落地方案.md」中**以具体协议为中心**的表述。
> 目标：**通用型**——判据只依赖 RFC 的**排版与语法客观特征**，与协议、与章节位置**均无关**。
> 依据来源：`local/_census_rfc_forms.py（已移除）`（已移除）（形态普查，实测）+ 四篇一手核实文献。

---

## 0. 方法论纠正（先立规矩）

### 0.1 前序方案的病症

前序方案（以及更早的评审）反复出现这类表述：

- 「RTSP 的 A.1/A.2 在附录 ⇒ 需要让章节树认字母附录」
- 「sip 的 §17 是 ASCII 图」「smtp 的 RFC 无 state machine 表述」
- 「阶段 A 让 RTSP 退化 14 → 5」

⇒ 这些**都是把某个协议的特例当成了方法的一般前提**。后果是：每换一个协议就要重做一轮判断，方案无法推广。

### 0.2 三条通用性原则（本文档的硬约束）

| 原则 | 含义 | 违反后的症状 |
|---|---|---|
| **G1 位置无关** | 判据**不得**依赖"在附录/在第几章/章节号前缀" | 同一形态在附录里就认不出 ⇒ RTSP 的表格反而靠"全文扫"侥幸抽到 |
| **G2 协议无关** | 判据**不得**出现任何协议名、方法名白名单、章节号特例 | 换协议就要改代码 ⇒ 不可扩展 |
| **G3 形态驱动** | 抽取路径由**内容形态**决定，不由**位置**或**协议**决定 | 单一提示词打天下 ⇒ 该用确定性解析的用了 LLM 推断（幻觉），该给 artifact 的只给了纯文本 |

⇒ 前序「修章节树支持字母附录」的建议，本质是 **违反 G1**（用位置去解决问题）⇒ **按 G3 重写**：附录里的表格照样按表格解析、附录里的图照样按 artifact 处理 ⇒ **章节树不需要改**。

---

## 1. RFC 内容形态分类（协议无关、位置无关）

### 1.1 形态清单与判据

> 判据全部基于**排版/语法客观特征**；无协议名、无章节号、无位置假设。

| kind | 判据（块级） | 处理路径 | 依据 |
|---|---|---|---|
| `boilerplate` | 含 RFC 抬头 / `[Page N]` / 页眉页脚 / 作者地址 | **丢弃** | PROSPER 清洗规则 |
| `toc` | 连续点号 + 页码 | **丢弃** | PROSPER 明确删 TOC（避免 LLM 误判控制语句） |
| `table` | 块内 ≥60% 行含 **≥2 处 2+ 空格列分隔** | **确定性表格解析**（保留列语义） | StatePre §3.2.1 layout-aware parsing |
| `diagram` | 块内 ≥60% 行含 **≥3 种图形字符** | **artifact 提取**（原样喂 LLM + 图题） | PROSPER Artifact Miner；StatePre vector graphics |
| `abnf` | 块内 ≥50% 行匹配 ABNF 规则式（`::=` / `name = ...`） | **确定性解析**（项目已有 `kind='abnf'` 通道） | RFC 2234 / 5321 |
| `example` | 块内 ≥50% 行为「缩进 ≥2 + 全大写首词 + 参数」 | **确定性抽取 → 消息实例** | RFC 示例报文（可作字段级实例来源） |
| `normative` | 块内 ≥30% 行含 MUST/SHALL/SHOULD/REQUIRED/MAY | **LLM 推断**（带元数据 + 输出契约） | StatePre §3.2.2；PSMBENCH chunking |
| `descriptive` | 其余散文 | 不直接产状态机（可作上下文附件） | — |

⚠️ **形态必须在块级判**：行级会互相污染（表格块里每行都可能含 MUST；正文行可能含图形字符）。这是普查实测的直接教训。

### 1.2 普查实测（跨协议形态分布高度一致 ⇒ G2 成立）

`local/_census_rfc_forms.py（已移除）`（已移除） 实测（**行级**）：

| 形态 | rtsp | sip | smtp |
|---|---:|---:|---:|
| descriptive | 81.4% | 81.8% | 85.0% |
| normative | 2.3% | **6.9%** | 5.4% |
| diagram | **4.0%** | 1.8% | 1.9% |
| table | 3.6% | 1.8% | 1.8% |
| abnf | 2.2% | 2.1% | 2.1% |
| boilerplate | 3.5% | 3.5% | 3.5% |
| toc | 2.9% | 2.1% | 0.2% |

**块级**（块 = 连续非空行段）：

| 形态 | rtsp | sip | smtp |
|---|---:|---:|---:|
| descriptive | 536 | 1334 | 868 |
| normative | 26 | 285 | 114 |
| table | 14 | 22 | 6 |
| diagram | 5 | 1 | 2 |
| abnf / example | 16 / 14 | 54 / 43 | 20 / 36 |

⇒ **三个协议的形态分布形状一致**（散文 ~45-50%、规范性 2.5-9.7%、表 0.3-1.3%、图 0.1-0.5%）
⇒ ⇒ **按形态分流是协议无关的**，这是通用定位的**经验基础**。

### 1.3 普查暴露的两个实现要点（必须写进实现，否则分类器不可靠）

1. ★ **图形字符集必须收紧**：初版含 `/ = # * { } v` ⇒ 正文 `HTTP/1.1 [2]` 被误判为图。
   ⇒ 收紧为 `+-|<>^[]`，且要求**块内 ≥60% 行**同时满足；
2. ★ **块切分不能只按空行**：ASCII 图内部常有空行 ⇒ 按空行切会把图切碎
   （实测 SIP 只剩 1 个 diagram 块，而 SIP §17 是 ASCII 状态图）
   ⇒ **需形态感知的合并**（见 §2.2）。

---

## 2. 具体代码调整

### 2.1 新增模块 `core/fused/extraction/rfc_forms.py`（协议无关的形态层）

```python
"""core/fused/extraction/rfc_forms.py —— RFC 内容形态分类（协议无关 / 位置无关）。

★ 依据：local/_census_rfc_forms.py（已移除） 实测形态分布跨协议一致
  ⇒ 形态可作为**通用分流依据**（G3）。
★ 硬约束（G1/G2）：本模块**不得**出现任何协议名、章节号特例或位置假设。
"""

FORM_KINDS: tuple[str, ...] = (
    "boilerplate", "toc", "table", "diagram", "abnf",
    "example", "normative", "descriptive",
)

@dataclass
class FormBlock:
    kind: str            # FORM_KINDS 之一
    text: str            # 块文本（形态合并后的完整块）
    line_start: int      # 源文件真实行号（1-based）
    line_end: int
    refs: list[tuple[int, str]]   # (行号, 行文本) ⇒ 溯源到原文

def split_form_blocks(lines: list[str], file_no: int = 0) -> list[FormBlock]:
    """切块 + 形态分类。★ 形态感知合并（见 §2.2 规则 M1/M2）。"""

def classify_form(block_lines: list[str]) -> str:
    """块级形态判定（§1.1 判据表）。"""
```

### 2.2 块切分规则（含普查暴露的合并规则）

| 规则 | 内容 | 理由 |
|---|---|---|
| **B1 基础切分** | 连续非空行 = 一个基础块 | 段落边界 |
| **M1 同类合并** | 相邻且形态同类（`table`/`diagram`/`abnf`/`example`）的基础块**合并** | RFC 的表格/图常被空行分段（如 RTSP A.1 表中间有空行） |
| **M2 图形窗口合并** | 若某块被判为 `diagram`，则**向前后扩展**，吸收相邻仍含 ≥3 种图形字符的行（即使被空行隔开） | ASCII 图内部常有空行 ⇒ B1 会切碎它 |
| **M3 噪声丢弃** | `boilerplate` / `toc` 直接丢弃，不进候选 | PROSPER 清洗 |

### 2.3 改造 `core/fused/extraction/rfc_extractor.py`：候选生成按形态分派

> ⚠️ **保留**现有 `_RE_STATE_MACHINE_HINT` 定位作为**兜底**（不删 ⇒ 零回归风险），
> 但它不再是主路径。

```python
def extract_transition_candidates(protocol: str) -> list[dict]:
    """状态机候选生成（形态驱动，协议无关）。

    ★ 改造前：扫含 "state machine" 的行 → 取前后 60 行（G1 违规：位置假设）
    ★ 改造后：形态切块 → 按 kind 分派（表格腿/图腿/散文腿）
    ⇒ 每条候选带 `kind`，供提示词分套与溯源
    """
    blocks = _form_blocks_for_protocol(protocol)      # 复用 rfc_forms
    out: list[dict] = []
    for b in blocks:
        if b.kind == "table":
            out.append(_table_candidate(b))           # 确定性，不调 LLM
        elif b.kind == "diagram":
            out.append(_diagram_candidate(b))         # artifact，原样文本
        elif b.kind == "normative":
            out.append(_prose_candidate(b))            # 带元数据
    # 兜底：现有关键词扫描（保留，去重后并入）
    for c in _legacy_keyword_candidates(protocol):
        if c["hash"] not in {x["hash"] for x in out}:
            out.append(c)
    return out
```

**候选结构**（新增 `kind` 与 `meta`）：

```python
{
  "kind": "table" | "diagram" | "prose",
  "text": "...",
  "hash": "<sha256>",                 # 缓存键的一部分
  "source": "file:xxx.txt#@N",        # 溯源锚点
  "meta": {                           # StatePre §3.2.2 的元数据
      "spec_version": "RFC 2326",
      "section_path": ["A.1"],        # 若该块落在章节窗口内（可为空）
      "critical_verbs": {"MUST": 3, "SHALL": 1},
      "columns": ["state", "message sent", "next state"],   # 仅 table
  },
}
```

### 2.4 三腿抽取器（按 kind 分套提示词）

| 腿 | kind | 抽取方式 | 提示词 | 依据 |
|---|---|---|---|---|
| ① 表格腿 | `table` | **确定性解析**（不调 LLM） | — | StatePre §3.2.1；项目已有 `_extract_transition_table` 可升级 |
| ② 图腿 | `diagram` | **artifact**：ASCII 图原文 + 图题 → LLM | `_PROMPT_TRANSITION_DIAGRAM` | PROSPER Artifact Miner；StatePre vector graphics |
| ③ 散文腿 | `normative` | LLM 推断（带元数据） | `_PROMPT_TRANSITION_PROSE` | StatePre §3.2.2；PSMBENCH |

⚠️ **表格腿升级要点**（StatePre）：现 `_extract_transition_table` 只认「三列定宽 + 状态名继承」这一种形态。
⇒ 升级为**保留列语义**的通用表格解析：识别表头列名（如 `state` / `message sent` / `next state`），
按**列角色**取值（起态列 / 触发列 / 目标列），而不是按固定列号
⇒ ⇒ 这样不同协议的表格列名不同也能解析（**G2 成立**）。

### 2.5 输出契约与消歧（对所有腿统一）

**输出契约**（对齐 StatePre Listing 3）：

```json
{"transitions": [{
   "from": "<状态>", "method": "<方法/命令>",
   "to": "<状态>",
   "allowed_commands": ["..."],          // 该状态下允许发的方法集（StatePre）
   "evidence_kind": "native" | "inferred"   // 规范原文 vs 推断（RFCNLP 口径）
}]}
```

**消歧后处理**（对应 PSMBENCH 三大挑战之二）：

| 挑战 | 措施 | 依据 |
|---|---|---|
| action/event 消歧 | ① prompt 注入**已知命令集**（由 `methods` 桶提供，**数据驱动、不硬编码**）；② 触发条件非方法（响应码/计时器/事件）⇒ 不抽；③ **后置过滤**：`method ∉ 已知命令集` 的条目丢弃并计数 | PSMBENCH；StatePre `Allowed commands` |
| alias resolution | 状态名归一（`Title Case` + 去修饰后缀 `(changed transport)`），**原始写法保留在 evidence** | PSMBENCH |
| 幻觉抑制 | `evidence_kind=inferred` 显式标记 + 溯源到块行号 | RFCNLP（"no canonical FSM"）；StatePre cross-validation |

⚠️ 我已实测该消歧的有效性：加上「method ∈ 已知命令集」约束后，
SMTP 的垃圾 method（`CONNECT` / `TLSHandshake` / `.`）**从 4/14 降到 0**。

### 2.6 新增跨块合并（PSMBENCH 流程第 ③ 步）

```python
def merge_partial_psms(partials: list[list[dict]], *, known_commands: set[str]) -> list[dict]:
    """跨块 PSM 合并（去重 + 冲突消解 + 消歧后处理）。

    ★ 依据：PSMBENCH 的 "PSM Combination"（第二次提示合并部分 PSM）；
      ProtocolGPT「one-shot 不可靠 ⇒ 必须分步」。
    ★ 当前实现是各块结果直接 union ⇒ 缺这一步。
    """
```

- 去重键：`(from, method, to)`（已归一）
- 冲突消解：同 `(from, method)` 不同 `to` ⇒ 优先 `native`；仍冲突则**标记并保留两条**（不静默丢弃）
- 消歧：`method ∉ known_commands` ⇒ 丢弃（计数上报）

### 2.7 缓存键并入 `prompt_version`

```python
block_hash = sha256(json.dumps([
    [c["kind"], c["hash"], PROMPT_VERSION] for c in candidates
]))
```

⇒ 改提示词 ⇒ 缓存自动失效（当前实现的已知坑：改动静默不生效）。

### 2.8 `rfc_config.json` 的角色收敛

- `transition_sections`（已存在）⇒ **降级为「补充提示」**（给章节路径元数据），**不再是候选来源**
  ⇒ ⇒ **配置里写协议特例章节号的时代结束**（G2）
- `method_sections` / `field_sections` / `status_sections` ⇒ **保持不变**（它们是**语义角色声明**，不是形态判据，
  与 G3 不冲突：形态决定**走哪条路**，角色声明决定**这节是什么语义**）

---

## 3. 落地顺序与验收

| 步骤 | 内容 | 验收（可量化、协议无关） |
|---|---|---|
| **S0** | 新增 `core/fused/extraction/rfc_forms.py`（形态层）+ 单元测试 | 三协议形态分布与普查脚本一致；`table`/`diagram` 块能覆盖 RTSP 的表格与 ASCII 图（**人工各抽 3 块核对**） |
| **S1** | 候选生成改为形态分派（保留旧路径兜底） | 候选 `kind` 分布可审计；**任一协议**的 `table`/`diagram` 块数 ≥ 1（旧路径可能为 0） |
| **S2** | 表格腿升级为**按列角色**解析（不按列号） | 同一份代码在**三个协议**上都能解析出转移（或明确报告"该协议无表格型状态机"） |
| **S3** | 图腿：artifact 提示词 + 图形块合并 | ASCII 图块不再被空行切碎（SIP §17 形态下 `diagram` 块数 ≥ 1） |
| **S4** | 散文腿：元数据 + `Allowed commands` + 已知命令集注入 + `evidence_kind` | `method ∉ 已知命令集` 的条目数 = **0**；状态名 RFC 原文命中率 ≥ 90%（可按协议豁免） |
| **S5** | 跨块合并 | 合并前后差异有日志；rtsp 合并后仍 14 条且状态名 4/4 命中 |
| **S6** | 缓存键并入 `prompt_version` | 改提示词后缓存**自动**失效（当前会静默命中） |
| **S7** | 评测（本地 MiniLM + 三条零依赖硬判据） | 状态级/转移级双 F1；native/inferred 分组 |

⇒ **门禁 v2**（逐维度 × 逐协议，每档独立通过/豁免，豁免须写入「已知边界」清单）
⇒ **不再有「必须先修章节树」这种前置**：形态层不依赖章节树 ⇒ G1 成立。

---

## 4. 与前序方案的关系

| 前序条目 | 本文档处置 |
|---|---|
| 「前置修复：扩展章节树支持字母附录」 | ❌ **取消**（违反 G1/G3）⇒ 形态层按内容判，A.1 的表格由**表格腿**覆盖，不依赖章节树 |
| 「阶段 A：候选定位扩展（关键词+章节树）」 | ✅ **重写**为形态分派（§2.3）；关键词扫描降级为兜底 |
| 「阶段 B：语义块 = 整节 + 元数据」 | ⚠️ **部分保留**：元数据（协议版本/关键动词）保留；"整节"改为**形态块 + 章节路径可选附加** |
| 「阶段 C：允许推断 + 方法白名单」 | ✅ **保留并加强**：加 `Allowed commands` + `evidence_kind` + 后置过滤（§2.5） |
| 「阶段 D：语义模糊匹配评测」 | ✅ 保留；判据本地化（PSMBENCH 同款本地句向量） |
| 「阶段 E：缓存失效」 | ✅ 保留；改为缓存键并入 `prompt_version`（§2.7） |
| 「新增 PSM 合并步」 | ✅ 保留（§2.6） |
| 门禁 一刀切 | ❌ 作废 ⇒ 门禁（逐维度 × 逐协议 + 显式豁免） |
| P0-3 措辞 | ✅ 改为「删骨架**暴露** RFC 源能力不足」（非「造成损害」） |

---

## 5. 不可计算 / 未覆盖项（诚实声明）

- ★ **形态分类器的准确率尚未测量**：本轮只做了**分布普查**与样例核对，**未**做标注集上的 P/R；
  ⇒ 分类判据的阈值（60% / 50% / 30%）是**依据形态普查的分布形态选的经验值**，**未**经标注验证；
- ★ **表格腿的"按列角色解析"未实现**：本轮只给出设计与升级方向，尚未落地，故未验证其跨协议通用性；
- ★ **ASCII 图 artifact 的抽取收益未实测**：图腿的依据来自 PROSPER / StatePre，**非**本项目实测；
- **状态级/转移级 F1 仍不可计算**：RFC 侧无人工真值（120 条 truth 集已标 3 条）；
  可借 PSMBENCH 的 **RFC2PSM**（含 SIP 真值）做部分外部对照，但该数据集**不含 RTSP/SMTP**；
- 本轮**未修改任何生产代码** ⇒ 护栏基线（35 failed / 1578 passed / 20 errors / 1 skipped）未受影响。
