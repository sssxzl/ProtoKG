# R6 core/ 与 scripts/ 装饰标记只读核查

> ★ 本轮只核查，★ **未做任何修改** ｜★ 用户已确认本轮不清理

---

## 一、已验证事实

### 1.1 总体分布

| 位置 | 标记数 | 文件数 |
|---|---:|---:|
| 注释（`#` 行） | 5592 | —— |
| docstring（函数与模块说明） | 7007 | —— |
| **可安全清理小计** | **12599** | —— |
| 字符串字面量（★ 含 docstring 误判） | 9178 | 272 |

按目录：

| 目录 | 文件数 | 注释 | docstring | 字符串字面量 |
|---|---:|---:|---:|---:|
| core | 64 | 2331 | 2074 | 241 |
| scripts | 15 | 551 | 286 | 84 |
| guard | 242 | 2058 | 2396 | 8337 |
| tests | 107 | 652 | 2251 | 516 |

★ 标识符命中：**0 处**（★ 无变量名或属性名含标记，★ 不存在命名约束）

### 1.2 最高风险项：LLM 提示词模板

**事实**：`core/fused/extraction/prose_semantics.py` 的 `_PROMPT` 有 5 份完全相同的副本，★ 每份含 17 处 `★` 标记；`rfc_extractor.py` 的两个提示词模板另含 3 处。

| 文件 | 行 | 标记数 |
|---|---|---:|
| core/fused/extraction/prose_semantics.py | 51、166、276、386、496 | 17 × 5 |
| core/fused/extraction/rfc_extractor.py | 2837 | 1 |
| core/fused/extraction/rfc_extractor.py | 2859 | 2 |

**已量化的后果**（只读计算，未执行修改）：

| 项 | 值 |
|---|---|
| `_PROMPT` 副本数 | 5（★ 内容完全相同，★ 长度均 1371） |
| 当前 digest | `d97fbe611ac9aa61` |
| 移除标记后的 digest | `1c6b368b28e5b4f3` |
| 是否相同 | **否** |
| digest 参与位置 | `prose_semantics.py:898`、`prose_semantics.py:983` 的 `prompt_digest=_hash_text(_PROMPT)` |
| 缓存键消费位置 | `core/fused/extraction/cache_key.py:66` 的 `cache_key()`，★ 第 84 行把 `prompt_digest` 纳入键的输入 |
| core/fused/extraction/prose_semantics.py | 51 | 21 |
| core/fused/extraction/prose_semantics.py | 166 | 21 |
| core/fused/extraction/prose_semantics.py | 276 | 21 |
| core/fused/extraction/prose_semantics.py | 386 | 21 |
| core/fused/extraction/prose_semantics.py | 496 | 21 |
| core/fused/extraction/rfc_extractor.py | 2837 | 1 |
| core/fused/extraction/rfc_extractor.py | 2859 | 2 |

★ **推论**：★ 项目铁律第 12 条要求「改模型时种子必须逐字节不变」（★ 否则既有语料不可比）。
★ 提示词字符串参与 `prompt_digest` 与缓存键计算（★ `prose_semantics.py:944` 的 `_dedup_key`）。
★ **因此清理这些字符串会改变 prompt_digest，★ 使既有缓存条目全部失效，★ 且新抽取产物与历史产物不可比**。

### 1.3 ★ 其余字符串字面量

**事实**：core 与 scripts 中除提示词模板外，★ 带标记的字符串字面量共 122 处。

| 文件 | 行 | 文本 |
|---|---|---|
| core/fused/downstream/action_seq.py | 984 | "expected_class: 无可用词表 ⇒ 必须留空" |
| core/fused/downstream/boundary_probe.py | 688 | "[boundary_probe] %s 中枢无 required_headers/methods ⇒ " |
| core/fused/downstream/seed_manifest.py | 193 | "★ 批次 2.5 F5：⑤ 层底料校验用" |
| core/fused/extraction/cache_key.py | 114 | "★ 「缓存命中时产物可复现」可保证；" |
| core/fused/extraction/cache_key.py | 115 | "★ 「重新调用同一模型能否逐字节相同」**不一定成立**" |
| core/fused/extraction/coreference.py | 109 | "主要证据中无指代表达 ⇒ 主体明确" |
| core/fused/extraction/coverage_ledger.py | 200 | "★ 独立抽样检查（未触发 LLM 的段落）⇒ 用于调整触发规则；" |
| core/fused/extraction/coverage_ledger.py | 201 | "★ 不要求全量调用 LLM" |
| core/fused/extraction/doc_registry.py | 81 | "★ 「文档自述状态」≠「当前生效状态」⇒ 跨文档效力核查" |
| core/fused/extraction/doc_registry.py | 82 | "（Updates/Obsoletes 的实际影响）**本轮未做**⇒ " |
| core/fused/extraction/doc_registry.py | 181 | "★ 本表只登记**文档自述**信息（Category / Updates / Obsoletes）" |
| core/fused/extraction/doc_registry.py | 182 | "⇒ ★ **不表示「当前生效」**⇒ 跨文档效力核查**未做**" |
| core/fused/extraction/normative_extract.py | 295 | "绝对未命中；缺 chunk 起始行 ⇒ 不做相对换算" |
| core/fused/extraction/normative_extract.py | 312 | "相对换算与绝对同值 ⇒ 仍无法定位" |
| core/fused/extraction/normative_extract.py | 598 | "锚点行及其邻近均非散文行 ⇒ 无法构造证据" |
| core/fused/extraction/normative_extract.py | 655 | "逻辑行内无任何一句包含实体 ⇒ 保守用锚点句" |
| core/fused/extraction/normative_extract.py | 656 | "（★ 不外扩、不猜测）" |
| core/fused/extraction/normative_extract.py | 681 | "锚点落在句间缝隙 ⇒ 改取含实体的句/锚点行所在句" |
| core/fused/extraction/normative_extract.py | 686 | "锚点未能定位到完整句 ⇒ 保守取逻辑行首句" |
| core/fused/extraction/normative_extract.py | 710 | "★ 锚点行含上一句句末 ⇒ 取下一句" |
| core/fused/extraction/normative_extract.py | 731 | "★ **辅助证据，未并入主要 quote** ⇒ 不得据此认定跨句义务成立" |
| core/fused/extraction/normative_verify.py | 178 | "证据仅含引用/元话语，未陈述行为本身 ⇒ 不足确认" |
| core/fused/extraction/normative_verify.py | 185 | "主体为空 ⇒ 无法确定行为主体" |
| core/fused/extraction/normative_verify.py | 195 | "规范强度未知 ⇒ 不得凭推测赋值 ⇒ 待审" |

★ 其中多为**面向人的提示文案与诊断说明**（★ 写进日志或诊断输出），★ 少数为断言文本。

## 二、限制

1. ★ ast 与 tokenize 的 docstring 识别仍有遗漏：★ 大量多行 docstring 被归入字符串字面量类，★ 故上表的字符串字面量计数**偏高**，★ 真实的数据内容占比更低。
2. ★ guard/_out/ 下的临时脚本（含 242 个文件）不在生产路径，★ 但仍在仓库内。

## 三、★ 若将来清理，★ 必须遵守的边界

| 边界 | 理由 |
|---|---|
| **禁止改动 LLM 提示词模板** | ★ 会改 prompt_digest 与缓存键，★ 破坏既有语料可比性（★ 铁律第 12 条） |
| **禁止改动断言文本与基线期望集** | ★ 会改护栏期望匹配（★ 铁律第 2、3 条） |
| **禁止改动数据文件中的标记** | ★ 规范第 7 条要求原始数据特殊字符完整保留 |
| 只清理注释与 docstring | ★ 无产物影响 |
| 清理后必须跑全量护栏 | ★ 确认「新增 0 / 消失 0」 |
| 清理后必须核对中枢与 Seed 逐字节一致 | ★ 确认无产物影响 |

## 四、推论

1. ★ 约 12599 处标记位于注释与 docstring，★ 清理无产物影响，★ 但 diff 规模大（★ 涉及约 400 个文件）。
2. ★ 少量标记位于提示词模板与断言文本，★ **属于不可动区域**。
3. ★ 用 AST 定位 docstring 并只替换注释与 docstring 节点，★ 可精确避开所有字符串字面量。

## 五、下一步

★ 当前不清理。★ 若将来决定清理，★ 建议单独立一个提交，★ 只替换注释与 docstring 节点，★ 跳过全部字符串字面量与标识符，★ 清理后跑全量护栏并核对中枢与 Seed 逐字节一致。

## 六、产出

| 文件 | 内容 |
|---|---|
| `guard/_out/_n1c_v2/r6/r6_mark_audit_exact.json` | 逐目录、逐文件的精确分类结果 |
| `guard/_out/_n1c_v2/r6/audit_marks2.py` | 分类脚本（★ 只读） |
