# 里程碑 A 实施报告 —— rfc 源知识抽取改造

> 完成时间：2026-10-31
> 依据：`docs/实施/RFC源知识抽取改造方案.md` v3（§0.0 v3 修订说明 + 附录追溯表）
> 范围：A0.1 ~ A0.6 + A1.1 ~ A1.7（评审建议的「里程碑 A 编码范围锁定」）

---

## 一、总体结论

| 验收项 | 目标 | 实测 | 结论 |
|---|---|---|---|
| SIP 重复 fact_id | 68 → 0 | **0** | ✅ |
| SIP TOC 污染 outcome | 50 → 0 | **0**（50 个全部来自正文） | ✅ |
| 全 8 协议重复 fact_id | 0 | **0** | ✅ |
| 全 8 协议 TOC 污染 | 0 | **0** | ✅ |
| RTSP 方法集 | 11 个精确匹配 | **11 个精确匹配** | ✅ |
| SMTP 命令 | ≥8 | **10**（EHLO/MAIL/RCPT/DATA/RSET/VRFY/EXPN/HELP/NOOP/QUIT） | ✅ |
| FTP 命令 | ≥15 | **18** | ✅ |
| SSH 数据类型 | ≥8 | **10**（byte/boolean/uint32/uint64/string/mpint/name-list/payload/mac/cookie） | ✅ |
| TLS 字段级结构 | ≥20 | **26**（type/version/length/MAC/IV/padding/random/extensions/…） | ✅ |
| 幂等性 | 同输入两次 build 字节一致 | **md5 一致、build_id 一致** | ✅ |
| 质量闸 | 构建质量闸阻断 / 离线评测跳过 | **已实现并接入 build_hub** | ✅ |
| 测试零回归 | 失败集合与基线一致 | **非 rq3 失败逐条一致；总失败 37 < 基线 38** | ✅ |

**总测试：37 failed / 633 passed / 20 errors**（基线 38 / 596 / 20）——passed +37（新增 36 个 A1 用例），failed −1。

---

## 二、改造前后对比

### 2.1 抽取量（8 协议）

| 协议 | 改造前 norms | 改造后 norms | method | field | outcome |
|---|---|---|---|---|---|
| sip | 171（**含 50 个 TOC 垃圾**） | 100 | 1 | 49 | 50 |
| rtsp | 72 | 71 | 11 | 45 | 15 |
| tls | 21 | 28 | 2 | 26 | 0 |
| ftp | 2 | 31 | 18 | 13 | 0 |
| smtp | 13 | 21 | 10 | 11 | 0 |
| ssh | 8 | 10 | 0 | 10 | 0 |
| dns | 14 | 4 | 3 | 1 | 0 |
| dtls | 4 | 7 | 0 | 7 | 0 |

> SIP 的 171 → 100 不是「知识变少」，而是**去掉了 50 个 TOC 垃圾 + 21 个重复抽取**，且标题召回率从 25.3% 提升后补回了 49 个真实字段。
> DNS 14 → 4：旧版的 14 个 field 全部是 `algorithm`/`format` 这类**文档结构名**（来自 RFC1034 的元信息章节），改造后按语义判定正确排除，仅保留真实的 `Format`。DNS 的真正字段（QNAME/QTYPE）需 A1.6 的表格/ABNF 抽取器，属后续任务。

### 2.2 质量指标（8 协议全部达标）

| 指标 | 改造前 | 改造后 |
|---|---|---|
| 重复 fact_id | sip 68 / tls 14 / dns 4 = **86** | **0** |
| TOC 来源 outcome | sip **50** | **0** |
| 标题召回率（单词正则） | sip 25.3% / smtp 5.6% / dns 10.3% | 语义判定 + 多词识别，不再受单词正则限制 |

---

## 三、代码改动清单

### 3.1 新增/修改文件

| 文件 | 改动 | 任务 |
|---|---|---|
| `core/fused/rfc_extractor.py` | **重写抽取主路径**（+约 700 行） | A1.1~A1.7, A0.4, A0.5 |
| `core/paths.py` | 新增 `target_rfc_config(protocol)` 并导出 | A0.2 |
| `scripts/build_hub.py` | 质量闸接入 + 幂等快照原子切换 | A0.4, A0.5 |
| `fused_hub/targets/*/rfc_config.json` | **8 个新建** | A0.2 |
| `fused_hub/targets/{dns,dtls,ssh,tls}/profile.json` | **4 个新建** | A0.1 |
| `fused_hub/targets/rtsp/rfc_config.json` | `field_sections` 加 `"7.1"`（Status-Line） | A1.3 |
| `scripts/rfc_baseline_probe.py` | **新建** —— 基线/回归测量工具 | 验收 |
| `scripts/rfc_config_verify.py` | **新建** —— rfc_config 章节号真实性校验 | A0.2 验证 |
| `tests/fused/test_rfc_extractor_a1.py` | **新建** —— 36 个用例 | 验收 |

### 3.2 rfc_extractor 新增/重写的函数

| 函数 | 作用 | 任务 |
|---|---|---|
| `_is_toc_line(line)` | TOC 行判定（点线引导，不误伤正文数字行） | A1.2 |
| `_parse_heading(line, line_no)` | **宽松**标题识别（多词/括号/一级无点号），排除数据行 | A1.3 |
| `SectionHead` / `SectionNode` | 标题与树节点数据结构 | A1.3/A1.4 |
| `_build_section_tree(heads, bodies)` | 按层级建树 | A1.4 |
| `MergeBudget` | 合并预算（max_depth / max_chars / dedup / cycle_guard） | A1.4 (F2) |
| `_merge_leaf_windows(roots, budget)` | 自底向上合并窗口（SpecGPT Alg.1） | A1.4 |
| `_section_kind(window, cfg)` | **语义判定**：查 rfc_config 的 *_sections（最长前缀） | A1.3 (T7) |
| `_infer_kind_from_content(window)` | 内容兜底（**已移除两条误判启发式**） | A1.3 |
| `_extract_indented_entries(text)` | 缩进**字段/数据类型**条目 | A1.5 |
| `_extract_command_entries(text)` | 缩进**命令**条目（独立识别器） | A1.5 |
| `_normalize_method_name` / `_normalize_field_name` / `_normalize_command_name` | 名字归一 | A1.3/A1.5 |
| `_extract_rfc_file(rfc_path, protocol, cfg)` | **重写**：六步流水线 | A1.1~A1.7 |
| `extract_rfc_norms(protocol)` | 加**协议级跨文件去重** | A1.3 |
| `QualityReport` / `rfc_quality_report()` | **两类检查分离**的质量报告 | A0.4 |
| `_count_toc_sourced_outcomes()` | TOC 污染检测（内容溯源口径） | A0.4 |
| `_offline_metrics(norms, truth)` | P/R/F1 离线评测 | A0.4 |
| `compute_build_id()` / `_EXTRACTOR_VERSION` | 幂等键 | A0.5 |

---

## 四、实施中实测暴露并修复的 5 个真实缺陷

这 5 个都是**实测暴露**的，不是设计推演出来的 —— 也是方案 v3 里没有预见到的部分。

### 4.1 off-by-one：body 归属错位
**症状**：SSH 字段从 8 归零；§5「Data Type Representations」拿到的是 §4.5 的正文。
**根因**：`bodies.append(cur_body)` 在**遇到标题时**就把累积内容挂给它 —— 那是标题**之前**的内容。
**修正**：body 与 head 的对应关系改为「下一个标题到来时才结算上一个 body」。

### 4.2 缩进信息被 strip 掉
**症状**：SSH/TLS 的「缩进定义条目」全部丢失。
**根因**：清洗阶段 `ln.strip()` 抹掉缩进层级，而这类条目**靠缩进识别**。
**修正**：只 `rstrip()`；窗口合并时保留行结构（不压成一行）。

### 4.3 条目名与正文之间有空行
**症状**：SSH 的 `byte` 抽不到。
**根因**：判定「下一行必须更深缩进」，但 RFC 排版是 `byte` / **空行** / 正文。
**修正**：向下查找时跳过空行再判缩进。

### 4.4 字段名归一只认大写开头
**症状**：SSH 全小写数据类型（byte/boolean/uint32/string/mpint/name-list）全被拒。
**根因**：`_RE_FIELD_NAME = ^[A-Z][A-Za-z0-9\-]*$`。
**修正**：扩展为接受「全小写单词 / 带连字符」形态。

### 4.5 ★ 形态猜测当分类依据（评审 T7 的核心被实测坐实）
**症状**：
- RTSP `3.2 RTSP URL` 被抽成 method（多出第 12 个）
- DNS `1. STATUS OF THIS MEMO` / `2. DOMAIN NAME SPACE AND RR DEFINITIONS` 被抽成 method
- 「正文含 ABNF 语法块 → method」误判 RTSP §3.2（`url = ...`），且让 FTP method 从 32 崩到 6

**修正**：**两条启发式全部移除**。method 只由 `rfc_config.method_sections` 语义判定；仅保留「标题含全大写缩写括号」（`MAIL (MAIL)`）这一条歧义极低的规则。
**教训**：「全大写」「含语法块」都只能说明**写法**，不能说明**它是什么** —— 这正是评审 T7「语义判定替代形态猜测」的实质。

---

## 五、质量闸与幂等（A0.4 / A0.5）

### 5.1 质量闸：两类检查分离（改进v2 问题③）

```
构建质量闸（阻断构建，不依赖真值集）
  ├─ 重复 fact_id          → sip 已从 68 → 0
  ├─ 重复 norm_id          → 跨文件去重后为 0
  ├─ TOC 污染              → 50 → 0
  └─ 空抽取结果            → 阻断

离线评测（发布准入，缺真值集则跳过而非失败）
  ├─ P / R / F1
  ├─ 章节层级准确率
  └─ 人工真值对比（kb/<协议>/rfc_truth.json，当前 8 协议均无 → 跳过）
```

实测输出：
```
[rfc] 质量闸: norms=100 facts=149 dup_fact_ids=0 toc_pollution=0 -> 通过
[rfc][提示] 无人工真值集（kb/<协议>/rfc_truth.json），离线评测跳过（不影响构建）
[rfc] build_id=rb_66d511116ea5b01b
```

### 5.2 幂等快照
- `build_id = sha256(规范内容 + 配置内容 + 抽取器版本)[:16]`，前缀 `rb_`
- 产物先写 `snapshots/<build_id>/<source>.jsonl`，再 `shutil.copy2` 复制到同目录临时文件、`os.replace` 原子切换到正式路径
  （**复制而非搬移**：直接 `os.replace(snapshot, dest)` 是搬移语义，会把快照搬空 ⇒ 快照/回滚失效；2026-11-01 已修）
- 清理（`_clean_per_source`）**保留** `facts/snapshots/` 目录，历史快照可跨构建留存
- 另存 `current_build_id.txt` 供回溯/回滚
- **实测**：SIP 连跑两次 → md5 `0c7d685e25d70ea3d35379f05e490adf` 完全一致、build_id 一致

---

## 六、rq3 契约脱节的归因（重要：避免误判为回归）

`tests/fused/test_rq3_dict.py::test_protocol_dict_unchanged_102` 断言字典为 102 token，实测 114。

**归因过程与结论**：
1. rfc 侧新旧抽取结果精确对比：field 仅差 1 个（`Recording`），method/outcome 完全一致
2. 「仅 rfc 源」时字典只有 24 个 token，且全是**流名 + 数值** → **rc 源对字典 token 贡献几乎为零**
3. **决定性实验**：把 `Recording` 塞回 headers（模拟完全恢复旧 rfc facts）→ token 数 = **115**，仍 ≠ 102

→ **rq3 的 102 token 契约脱节是预存问题，与本次 rfc 改造无关。** 差异来源是 `rtsp_streams.json` 的 14 个流名（aacAudioTest/amrAudioTest/dvVideoTest/h264ESVideoTest/h265ESVideoTest/opusFileTest/vobTest/mpeg2TransportStream* 等）+ traffic 源。

**rq3 侧唯一真实的 rfc 差异**：
- 旧版多抽 `Recording`（§14.6「ANNOUNCE 如何录制」= 状态机章节，**不是字段**）→ 改造后正确排除
- `Status-Line`（§7.1，Response 的第一行）旧版靠「单词正则 + 全文档扫描」碰巧抓到 → 改造后需在 `rfc_config.field_sections` 显式声明 `"7.1"`（**已加**）

---

## 七、遗留与建议（需决策，未擅自处理）

### 7.1 多 RFC 协议的章节号前缀无法区分不同 RFC（**结构性限制**）
- SMTP 4 份 RFC 的 §4 分别是：STARTTLS Command（RFC3207）/ The AUTH Command（RFC4954）/ …
- TLS 的 §6 在 RFC8446 是 Alert、在 RFC5246 是 Record Layer
- 当前用「更长子节优先」消歧，但**根治需要 per-file 覆盖机制**（`rfc_config` 支持 `files: {<文件名>: {...}}`）
- 直接后果：SMTP 的 field_sections（2.2/3.6/4.4）跨 RFC 冲突 → SMTP 的 field 里混进了方法名（DATA/EXPN/HELP/MAIL/NOOP/QUIT/RCPT/RSET/VRFY）

### 7.2 DNS 字段只抽到 1 个
DNS 的字段（QNAME/QTYPE/QCLASS/RDLENGTH）是**表格 + ABNF 形态**，需 A1.6（`_extract_status_table`）与 A1.5 的 ABNF 分支（**必须区分协议命令 / 语法非终结符 / 字段名**，评审 T7 的原话）才能抽到。

### 7.3 rq3 的 102 token / 38-50 种子契约
属**研究契约**，改动会动基线。建议由用户决定：同步契约（更新断言与 profile 期望值）还是回退资源清单。**本次未擅自改动。**

### 7.4 操作提醒
`build_hub.py --sources rfc` 会**清空该协议的五源 facts**（`_clean_per_source` 删五源）。重建时必须用
`--sources source expert_note vuln traffic rfc`，否则依赖其他源的测试会连带失败。

> ★ **该问题已于 2026-10-31 修复**（见第九节「一次一个协议 × 一个知识源」契约改造）：
> 现在 `--sources rfc` **只清 rfc 一个源**，其他四源不再被连带删除。

---

## 九、一次一个协议 × 一个知识源（契约改造）

### 9.1 约束来源
用户明确（2026-10-31）：

> 「我这个模型，一次只对一个知识库进行处理，目标是一个知识源，不是一批把所有知识库都解决。
> 对 rfc 的识别上面，利用 `--<目标协议>` 单次对一个协议进行处理。」

### 9.2 改造前的问题（实测发现，非推测）

| # | 违反点 | 证据 |
|---|---|---|
| 1 | `--sources` 用 `nargs="+"`，允许一次多源 | 契约不允许 |
| 2 | **`_clean_per_source` 清空该协议的五源** | ★ 实测踩坑：`build_hub.py --sources rfc --protocol rtsp` 会把 rtsp 的 source/expert_note/vuln/traffic **一起删掉** → 依赖这些源的 **22 个测试连带失败**、下游 seedgen 失效 |
| 3 | `--protocol` 默认 `rtsp` | 不传就静默跑 RTSP，存在隐式误跑/批量风险 |
| 4 | 新增的 `rfc_baseline_probe.py` / `rfc_config_verify.py` 默认遍历全部 8 协议 | 工具侧同样违反约束 |

### 9.3 改造内容

**`scripts/build_hub.py`**
- `--sources` → **单值**（`default="rfc"`，`choices` 限五源）；传多个会被 argparse 拒绝
- `--protocol` → **`required=True`**，不再有隐式默认；协议不存在时报错并 `return 2`
- `_clean_per_source(protocol, sources=[...])` → **只清本次指定的源**；`sources=None` 时仍清五源（保留全量重建场景的旧行为）
- 输出显式标注「本次处理: 协议=X 知识源=Y（单协议 x 单源）」

**`scripts/rfc_baseline_probe.py` / `scripts/rfc_config_verify.py`**
- `--protocol` 改为**单值**；不传且不加 `--all-protocols` → `ap.error` 退出
- 新增 `--all-protocols`：**显式**批量（仅用于跨协议回归对比），并打印「[批量模式]」提示

**新增 `tests/fused/test_single_protocol_single_source.py`**（13 个用例）
把约束固化为可自动验证的测试：
- CLI：多源被拒 / `--protocol` 必填 / 未知协议 exit 2 / 非法源被拒
- 清理范围：只清指定源，其他源文件**必须仍在**（核心回归）
- 产物范围：只写 `derived/per_source/<protocol>/<source>/`
- 工具脚本：默认必须单协议；单协议模式输出里**不得出现**其他协议
- rfc 抽取隔离：SIP 配置判 RTSP §12 → 不是 field；RTSP 配置判 SIP §20 → 不是 field；两协议 norm_id 集合**不相交**

### 9.4 实测验证

```
【1】SIP 的 rfc 源
  [清理] 已清空 sip 的 1 个源 facts: rfc        ← 只清 1 个，不是五源
  [rfc] 质量闸: norms=100 facts=149 dup_fact_ids=0 toc_pollution=0 -> 通过

【2】SIP 的 traffic 源
  [清理] 已清空 sip 的 1 个源 facts: traffic    ← rfc 未被牵连
  [traffic] 映射 67 Facts / fail-closed 失败 0

【3】SMTP 的 rfc 源
  [清理] 已清空 smtp 的 1 个源 facts: rfc       ← SIP 未被牵连
  [rfc] 质量闸: norms=21 facts=32 ... -> 通过
```

四协议（rtsp/sip/ftp/smtp）五源完整性全部 ✅，下游 `seedgen.py --protocol rtsp` 正常出种子。

### 9.5 未受影响的显式设计
`core/fused/vuln_vector.py` 的**跨协议漏洞迁移**（`migrate_vuln_patterns` / `retrieve_cross_protocol`）保持不变 —— 那是**显式 opt-in 的知识迁移能力**（新协议无漏洞库时从其他协议迁移），调用者必须显式传 protocols 列表，主路径（build_hub / seedgen）不触及。它与「一次处理一个协议 × 一个源」不冲突：前者是**知识检索**，后者是**知识抽取**。

### 9.6 契约文档同步
- `fused_hub/README.md`：入口改为单协议单源写法
- `scripts/gen_docs.py`、`scripts/seedgen.py` 的提示文案同步
- 新增 `docs/设计/单协议单源契约.md` 作为契约的独立说明

---

## 八、验收命令（可复算）

```bash
# 1) 基线/回归测量（**单协议**；跨协议批量需显式 --all-protocols）
python scripts/rfc_baseline_probe.py --protocol sip
python scripts/rfc_baseline_probe.py --all-protocols      # 显式批量

# 2) rfc_config 章节号真实性校验（**单协议**）
python scripts/rfc_config_verify.py --protocol sip

# 3) 端到端构建（**一次一个协议 × 一个知识源**；每个源单独跑一次）
python scripts/build_hub.py --sources rfc --protocol sip
python scripts/build_hub.py --sources traffic --protocol sip
#    每次只清该协议该源的旧 facts，其他源不受影响

# 4) 幂等性
python scripts/build_hub.py --sources rfc --protocol sip
md5sum derived/per_source/sip/rfc/facts/rfc.jsonl   # 两次应一致

# 5) 测试
python -m pytest tests/ -q      # 37 failed / 646 passed / 20 errors（失败全为预存）
python -m pytest tests/fused/test_rfc_extractor_a1.py -q            # 36 passed
python -m pytest tests/fused/test_single_protocol_single_source.py -q  # 13 passed
```

---

## 十、知识库收敛到 3 个目标协议（2026-10-31 追加）

### 10.1 背景

用户把 `kb/` 从 8 个协议裁剪到只剩 **rtsp / sip / smtp**（实验只用到这三个）。
但 `fused_hub/targets/` 与 `derived/per_source/` 仍留着另外 5 个协议（dns/dtls/ftp/ssh/tls）
的配置与产物，且测试仍引用它们 → 失败数从裁剪前的 **37 failed** 涨到 **47 failed**。

### 10.2 处置

**删除**（不可逆，配置已备份至 `qa/backup_targets_scope_trim/`）：

| 位置 | 理由 |
|---|---|
| `fused_hub/targets/{dns,dtls,ssh,tls}/` | 上一轮 A0.1/A0.2 新建的，kb 已无对应协议 → 纯死配置 |
| `fused_hub/targets/ftp/rfc_config.json` | 上一轮 A0.2 新建 |
| `derived/per_source/{dns,dtls,ftp,ssh,tls}/` | `derived/` 是再生目录；rq3/rq4 脚本只用 3 个目标协议，无人引用 |

**保留**（并已实测确认无副作用）：

| 位置 | 保留理由 |
|---|---|
| `fused_hub/targets/ftp/{profile.json, ftp_base.dict}` | **仓库原有文件**（非本次新建）；`load_base_dict_tokens` 按协议名**动态查找**，留着零成本零风险；项目非 git 仓库，删除不可逆 |
| `core/fused/protocol_patterns.py` 的 8 协议条目 | 属**协议知识层、不依赖 kb 存在**；删除会破坏 `source_fsm.py` 的 import |
| `core/fused/source_probe.py` / `scripts/run_boundary_probe.py` 的 `SSH = ["ssh","-i",...]` | 那是**连接虚拟机的 SSH 客户端命令**，不是协议知识 |
| `kb/sip/_bak_pjproject`（51MB） | 用户自留的 pjproject 备份；所有扫描锚定 `kb/<协议>/<源目录>/`，**不参与抽取、不污染结果** |

**测试收敛**（11 处引用 → 收敛到 3 个目标协议）：详见 `tests/fused/` 下 5 个文件的改动。

### 10.3 终态验收

| 项 | 裁剪后（未清理） | 终态（已清理） |
|---|---|---|
| failed | 47 | **37** |
| passed | 636 | **644** |
| errors | 20 | **20** |

- **A 类 10 条全部消失**（`test_expert_note.py`×5、`test_rfc_extractor.py`×2、`test_rfc_extractor_a1.py`×3）
- **B 类 37 条一条不多一条不少**（`comm` 三组 diff 全空）
- 三目标协议健康度：rtsp 71 norms(45/11/15)、sip 100(49/1/50)、smtp 21(11/10/0)，
  **全部 `dup_fact_ids=0`、`toc_sourced_outcomes=0`**
- `rfc_config` 章节号命中：rtsp 7/0、sip 14/0、smtp 12/0（**0 未命中**）

### 10.4 ★ 契约漂移的根因裁决（重要）

`focus_group` 种子数契约（rtsp 50 / sip 25 / smtp 78）与当前实际重生成（65/20/61）失配。

**根因不是 rfc 源改造。** 逐一剔除法实测（focus_group B，rtsp）：

| 剔除的源 | 条数 | 内容 md5 | 结论 |
|---|---|---|---|
| 全五源 | 65 | 65ce7314 | 基线 |
| **rfc** | 65 | **相同** | **零影响** |
| expert_note | 65 | 相同 | 零影响 |
| **source** | **0** | — | **决定性驱动** |
| vuln | 52 | 不同 | +13（vuln_boundary 层） |
| traffic | 64 | 不同 | +1（URL 观测值） |

⇒ 真正的根因是 **source 源**引入 LIVE555 源码的**真实状态名**
（Idle/Invited/Confirmed/Registered/Paused/Terminated），取代了 expert_note v3 时代的
**虚构状态名**（Init/Ready）→ 状态机层与种子序列全变 → 契约漂移。
这与 B:state-model 6 个失败、B:seed-count-contract 28 个失败**同源**。

**已发表结果不受影响**：`derived/seeds/<协议>/rq4_B/` 的语料（39/25/78）带
`MANIFEST.md5` + `manifest.json`，`md5sum -c` **全部 OK、0 失败**。

**两条不可行的回退路径（已实测排除）**：
- 「用 `rtsp_base.dict` 重建得 39 条」→ 实测 `--dict base` 得 **37** 条
  （且 `--dict base` 与 `--dict protocol` 条数相同，dict_kind 不是驱动因素），
  差异在**多资源覆盖的消息序列构成**。
- 「回退 rfc facts 到 10-29 状态」→ **10-29 的快照不存在**；
  `derived/per_source.bak_20261018/rfc/facts/rfc.jsonl` 是 10-18 的 **v1 格式**
  （597 条含 `all_claims`），与当前 v2 格式不可比。

### 10.5 遗留（待用户决策，未擅自处理）

1. **rq3/rq4 契约同步**：需用户选「同步契约 + 重跑」还是「回退资源清单」
2. **RTSP URL 污染**：当前 facts 重生成 group B → 46.5% 不可播、目标主机正确率仅 40.5%。
   根因：traffic facts 含摄像机 uri（`rtsp://10.11.26.98:554/isapi/...`），
   `scripts/seedgen.py:273` 的兜底条件 `if not msg.url or "localhost/seed" in msg.url:`
   不命中 → 原样透传。**已发表 rq4_B 语料是干净的**（0% 污染、100% 正确），
   受影响的只是「从仓库重建语料」这条路径。
3. **VM 磁盘 95%（仅剩 5GB）**：需用户过目目录清单后授权
4. `test_rq3_focus_group.py` 残留的 ftp 校准数据：属 B 类，保持不动以维持基线可比
