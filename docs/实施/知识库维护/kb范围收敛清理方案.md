# kb 收敛到 3 协议（rtsp/sip/smtp）—— 清理方案与验收报告

> **调研性质：只读调研 + 方案设计。**本文档产出过程中**未修改任何项目文件**
> （唯一写入是本文件 `docs/实施/知识库维护/kb范围收敛清理方案.md`）。
>
> **执行者注意**：方案主体（测试收敛 + 目录裁剪）已由 `software-engineer` 在
> 2026-10-31 18:07–18:22 期间落地，本文因此**同时充当「已执行状态的验收报告」**。
> 逐条实测数据见 §6。
>
> ---
>
> ## ⚠️ 2026-11-01 重大更新：项目已成为 git 仓库 + 一次破坏性 git 操作
>
> **§7「不可逆操作清单」的整个前提已失效** —— 请先读这一节再执行任何删除。
>
> | 事实 | 实测证据 |
> |---|---|
> | **项目现在是 git 仓库** | `git status` / `git log` / `git reflog` 均可用。首次入库提交 `c9295b4`（2026-11-01 13:31），随后 `493874c` merge `origin/main`（13:59） |
> | **曾发生破坏性 git 操作** | `git reflog` 显示 13:31 有 `reset: moving to HEAD~1` → 重新 commit → 大提交 → `merge origin/main`（`software-engineer-12` 报告其文档改动被清空并已重放恢复） |
> | **我的交付物安全** | `docs/实施/知识库维护/kb范围收敛清理方案.md` 已入 `c9295b4`，`git status` 干净 |
> | **6 个清理测试文件安全** | 全部已入 `c9295b4`，`git status` 无 `M` 标记 → 收敛成果**未被破坏** |
> | **`derived/per_source/` 裁剪安全** | kb/derived/targets 三处现状仍为 3 协议目标（见下表） |
> | **但 `protocol_patterns.py` 的 P0 被回滚** | 当前文件**又变回 8 个条目**（dns/dtls/ssh/tls/ftp 全回来了），且工程师补的文件头「协议范围」说明也一并丢失。`git log --all` 显示**没有任何提交含 3 条目版本** → P0 **未被提交**，故被 `reset` 抹掉且**无法从 git 恢复** |
>
> **§7 的修正**：由于 ``、`tests/`、`docs/`、`core/` 现已全部 git 跟踪，
> **对这些目录的删除已变为可逆**（`git checkout -- <path>` 即可恢复）。
> 仅 `derived/` 仍在 `.gitignore` 里（`.gitignore:39`）→ **只有 `derived/` 下的删除
> 仍是真正不可逆的**。详见 §7 修正版。
>
> **当前状态实测（2026-11-01 15:10）**：
> ```
> pytest tests/ -q  →  37 failed / 1129 passed / 20 errors
> kb/                →  rtsp  sip  smtp                        ✅
> derived/per_source/→  rtsp  sip  smtp                        ✅
> profiles/ →  ftp  rtsp  sip  smtp（+ rtsp 顶层 json）✅
> ```
>
> **git 兜底自测（11-01 14:58 实测）**：
> ```
> git checkout -- <path>            # 恢复已跟踪文件（ tests/ docs/ core/ scripts/ kb/）
> git stash push -m "说明"          # 暂存当前改动（比 reset/checkout 安全）
> git status --short                # 确认工作区状态
> ```
> ⚠️ **注意 `core.autocrlf=true`**：`git checkout --` 会把仓库里的 **LF blob 物化成 CRLF 落盘**。
> 我实测过 `rtsp_base.dict` 的 MD5（`464351f88db6c3f0bdac0de01859316b`）与
> `ftp_base.dict` 的 MD5（`87d1b84c82d94678ed2303ca7179a211`）**当前均完好**，
> 但若将来对这两个文件执行 `git checkout --`，**必须重测 MD5** ——
> 它们被 `derived/experiments/rq3/dict/DICT_FROZEN.json` + `derived/experiments/rq3/groups.json` 按字节锁定。

---

## 0. TL;DR —— 主理人最关心的 5 个问题

| 问题 | 结论 | 依据 |
|---|---|---|
| **Q1** `profiles/{dns,dtls,ssh,tls}/` 整个删还是只删 rfc_config.json？ | **整个目录删**。这 4 个目录是上一轮 A0.1/A0.2 新建的，kb 已无对应协议，profile.json 里的 `message_schema.hint` 引用的是已删除的 RFC 章节号（保留即是说谎） | §2.1；实测已删（18:16） |
| **Q2** `profiles/ftp/` 怎么处理？`ftp_base.dict` 删还是留？ | **保留 `profile.json` + `ftp_base.dict`，只删 `rfc_config.json`**（已执行）。实测：`ftp_base.dict` **未被任何 MD5 锁文件引用**（`rtsp_base.dict` 被 DICT_FROZEN + groups.json 双重锁定，ftp 没有）、两者 MD5 **互不相同**（是独立内容非副本）、`ftp/profile.json` **不含任何指向已删 kb 的悬空指针**（与 dns/dtls/ssh/tls 的 profile.json 性质不同）、**无自动发现机制**（所有读取方都是 `target_profile(<显式协议名>)` + `if not exists: return 空`）。**实测把整个 `targets/ftp/` 全删，失败集合也逐条不变** → 保留是纯语义偏好，零风险 | §2.2 |
| **Q3** `derived/per_source/{dns,dtls,ftp,ssh,tls}/` 删还是留？ | **删**（已执行）。`derived/` 在 `.gitignore` 里是再生数据目录，`ftp` 那批是**孤儿产物**（源 kb/ftp 已删，facts 无源可溯） | §2.3；实测已删 |
| **Q4** `core/fused/protocol_patterns.py` 里 dns/dtls/ssh/tls/ftp 的条目删不删？ | **曾由工程师实施 P0（收敛到 3 协议），但因未提交被 11-01 的破坏性 git 操作整体回滚 —— 当前文件又变回 8 条目，需重做或明确不做。** 技术上删除【不会】破坏 `source_fsm.py` 的 import（删的是字典条目不是函数）、【不会】破坏任何测试（tests/ 0 命中）。**我倾向重做 P0 并立即提交**（git 已提供可逆性，「不可逆成本」不再是反对理由；而 5 条僵尸条目会误导读者以为这些协议仍受支持） | §2.4 |
| **Q5** `test_real_protocol_method_counts[ftp-15]` 的 ftp 换成什么？ | **不换 —— 直接删掉这一行参数化，只保留 `rtsp`(11) 与 `smtp`(8)**。理由见 §3.3：SIP 只有 1 个 method（`OK`），拿 SIP 顶替会得到 `("sip", 1)` 这种无信息量的断言；换成 rtsp/smtp 则与已有行重复 | §3.3 + §5 风险 R1 |

**验收结论：当前仓库已达 `failed == 37 && errors == 20`，且失败集合与基线逐条一致（实测 `SETS IDENTICAL = True`）。三个目标协议的 rfc 源构建与 baseline_probe 全部通过。**

> ⚠️ **`passed` 计数不是验收指标** —— 它随并发 teammate 新增测试文件而变动
> （我调研期间实测从 644 → 662 → 702，原因是陆续新增了
> `test_rq4_target_url_normalization.py`、`test_corpus_gate.py` 等文件）。
> **稳定不变量只有两个：`failed == 37` 且 `errors == 20`，外加 failed 集合逐条一致。**
> 绝不要把 `passed` 写进验收判据。

---

## 1. 关键事实核定（实测，非采信）

### 1.1 测试基线的精确切分

我对 `pytest tests/ -q` 跑了完整基线并按「是否引用已删协议」做了机器切分：

```
裁剪前 kb=8 协议时：47 failed / 636 passed / 20 errors
  ├── NEW (引用已删协议导致)：10 个
  └── PRE (预存 rq3/下游契约脱节)：37 个
```

**这 10 个 NEW 失败**（全部由 kb 裁剪直接引起）：

| # | 用例 | 引用 | 失败原因 |
|---|---|---|---|
| 1 | `test_expert_note.py::test_expert_note_to_facts_non_empty` | `protocol="dns"` | `kb/dns/expert_note` 不存在 → `facts=[]` |
| 2 | `test_expert_note.py::test_hotspots_map_security_property_by_target_type` | `protocol="dns"` | 同上 |
| 3 | `test_expert_note.py::test_design_weaknesses_map_protocol_subject` | `protocol="dns"` | 同上 |
| 4 | `test_expert_note.py::test_implicit_constraints_map_header_subject` | `protocol="dns"` | 同上 |
| 5 | `test_expert_note.py::test_all_protocols_pass_fail_closed` | 8 协议全遍历 | 遍历到 dns 即 assert 失败 |
| 6 | `test_rfc_extractor.py::test_extract_constraint_candidates_non_empty` | `extract_constraint_candidates("dns")` | `kb/dns/spec` 不存在 → `cands=[]` |
| 7 | `test_rfc_extractor.py::test_infer_constraints_with_stub` | `infer_constraints("dns", llm=stub)` | 候选为空 → 直接 `return []` |
| 8 | `test_rfc_extractor_a1.py::test_quality_report_passes_for_real_protocol` | 遍历 `sip/rtsp/ftp/smtp` | ftp 抽 0 norm → 质量闸 `抽取结果为空` 阻断 |
| 9 | `test_rfc_extractor_a1.py::test_real_protocol_method_counts[ftp-15]` | `("ftp", 15)` | `extract_rfc_norms("ftp")` → `[]` |
| 10 | `test_rfc_extractor_a1.py::test_real_ssh_has_data_type_fields` | `extract_rfc_norms("ssh")` | 同上 |

**剩余 37 个 PRE 失败**与 kb 裁剪**完全无关**，是 rq3 语料/字典/manifest 与下游 seedgen 的预存契约脱节：
`test_edge_cover` ×1、`test_rag_seedgen` ×2、`test_rag_seedgen_step2` ×2、
`test_rq3_dict` ×3、`test_rq3_focus_group` ×19、`test_rq3_manifest` ×6、
`test_strategy` ×1。

### 1.2 `derived/per_source/` 与 `kb/` 的对应关系（孤儿产物确认）

kb 裁剪后 `derived/per_source/` 里 5 个非目标协议的目录状态：

| 协议 | 裁剪前源目录 | 产物 | 性质 |
|---|---|---|---|
| `dns`/`dtls`/`ssh`/`tls` | 仅 `rfc`（上一轮我方新建） | `rfc/facts/rfc.jsonl` 各 4–28 KB | 孤儿（源已删） |
| `ftp` | 五源齐全 | 197 KB，含 expert_note/rfc/source/traffic/vuln | **孤儿产物**（源 `kb/ftp` 已删，facts 无法溯源） |

### 1.3 三个目标协议的 rfc 抽取实测指标（方案 §3 数字依据）

| 协议 | norm 数 | method | field | outcome | 质量闸 | `extract_constraint_candidates` |
|---|---|---|---|---|---|---|
| rtsp | 71 | 11 | 45 | 15 | 通过 | 80 |
| sip | 100 | **1** | 49 | 50 | 通过 | 80 |
| smtp | 21 | 10 | 11 | 0 | 通过 | 273 |

> **SIP 只有 1 个 method（`OK`）** —— 这是 §3.3 决策的关键依据。
> 根因：SIP 的方法定义在 §9.1–§9.15 的**缩进条目**里（如 `9.1 REGISTER`），
> 而 `kb/sip/spec/rfc3261.txt` 的正文标题形态是 `9.1 Client Behavior` /
> `25.1 Basic Rules`，标题里**不含方法名**，所以 `_normalize_method_name` 拿不到。
> 这是一个**独立的抽取器质量问题**，不在本次清理范围内（见 §5 风险 R1）。

---

## 2. 逐文件处置表

### 2.1 `profiles/{dns,dtls,ssh,tls}/` —— **整个目录删**（已执行，18:16）

| 文件 | 处置 | 理由 |
|---|---|---|
| `profiles/dns/{profile.json,rfc_config.json}` | **删** | A0.1/A0.2 新建；`profile.json` 的 `message_schema.hint` 写死「RFC 1035 §4.1.1」等已随 kb/dns 消失的章节号 |
| `profiles/dtls/{profile.json,rfc_config.json}` | **删** | 同上（引 RFC 6347 §4.1） |
| `profiles/ssh/{profile.json,rfc_config.json}` | **删** | 同上（引 RFC 4253 §6） |
| `profiles/tls/{profile.json,rfc_config.json}` | **删** | 同上（引 RFC 8446 §5） |

**为什么整个删而不是只删 rfc_config.json**：
`rfc_config.json` 只是「rfc 抽取配置」，删它只是让 `_load_rfc_config()` 回落到
`profile.json` 的 rfc 段再回落空配置（**不报错**，只打 stderr 警告）；
但 `profile.json` 本身是**协议身份定义**，它声明的 `message_schema` 语义
（DNS 的 QNAME/QTYPE、DTLS 的 record/handshake、SSH 的 packet payload、
TLS 的 ContentType）全部指向**已不存在的 kb 源**。保留一个自称「描述 DNS 协议
怎么构造报文」却没有任何 DNS 知识可依的 profile，是**主动制造说谎配置**。

**实测影响**：删除这 4 个目录后 `pytest` 失败集合**逐条不变**（§6.3 模拟验证）。

### 2.2 `profiles/ftp/` —— **保留 profile.json + ftp_base.dict，只删 rfc_config.json**（已执行，18:16）

> **2026-10-31 19:10 复核补充**（回答主理人「ftp_base.dict 彻底没有读取方了，这个取舍请你定」）：
> **保留两者。** 实测依据：
> ① `ftp_base.dict` **未被任何 MD5 锁文件引用**（`grep -rn "ftp_base" --include=*.json --include=*.md5` → 空；
>    对比 `rtsp_base.dict` 被 `derived/experiments/rq3/dict/DICT_FROZEN.json` + `derived/experiments/rq3/groups.json` 双重锁定）
>    → 删它**不会**破坏任何冻结/校验契约；
> ② 两者 MD5 **互不相同**（`87d1b84c…` vs `464351f8…`），是**两份独立的字典内容**，
>    不是 rtsp 字典的副本 → 删掉即永久丢失 FTP 命令集 token；
> ③ `ftp/profile.json` **不含任何指向已删 kb 的悬空指针**（实测：`resources_file`/`templates_file`
>    均为 `None`；全文 grep `kb/`/`rfc959`/`spec/` → 无命中）——
>    **与 dns/dtls/ssh/tls 的 profile.json 性质不同**（后者的 `message_schema.hint` 写死了
>    「RFC 1035 §4.1.1」等**已随 kb 消失**的章节号）；
> ④ `ftp/profile.json` 的 `allowed_methods`（31 条）仍是 `scripts/response_rewriter.py:36`
>    `FTP_METHODS`（42 条）的**对齐基准注释来源**，删了会让那条注释指向空；
> ⑤ **无自动发现机制**：全仓库 grep `targets_root().iterdir/glob` → 空，
>    所有读取方都是 `paths.target_profile(<显式协议名>)` 形式
>    （`boundary_probe.py:42/626/910`、`rag_seedgen.py:122/140/162`、
>    `selector.py:109/157`、`strategy.py:277`），
>    且每处都是 `if not p.exists(): return 空` 优雅降级 → **保留无害**；
> ⑥ **实测把整个 `profiles/ftp/` 全删，失败集合仍逐条一致**（§6.4 场景 B）
>    → 保留与删除**对测试零可观测差异**，纯属语义取舍。
>
> **结论**：保留 `profile.json` + `ftp_base.dict`（仓库原有资产、不可逆、零读取风险），
> 只删 `rfc_config.json`（A0.2 新建、显式指向已删的 `kb/ftp/spec/rfc959.txt`）。
> 这也让 `profiles/` 的形态自洽：**每协议目录 = 「仓库原有的协议配置」+
> 「本轮新建的 rfc 抽取配置（已删）」**。

| 文件 | 处置 | 理由 |
|---|---|---|
| `profiles/ftp/profile.json` | **保留** | 仓库原有文件（非本轮新建）；`scripts/response_rewriter.py:36` 注释与 `FTP_METHODS`（42 个命令）声明「与 `profiles/ftp/profile.json` 的 allowed_methods 对齐」；`scripts/seedgen.py:_load_profile()` 读它。**它是 `response_rewriter` 那条独立链路的配置锚点** |
| `profiles/ftp/ftp_base.dict` | **保留** | 仓库原有文件；`load_base_dict_tokens("ftp")` 按协议名动态取 `targets/<proto>/<proto>_base.dict` —— **留着无害**（对 rtsp/sip/smtp 的调用不经过它）；删了也无引用报错。保留是**零风险**选项 |
| `profiles/ftp/rfc_config.json` | **删**（已执行） | A0.2 新建的 ftp 章节号映射（`method_sections: ["4.1","4.1.1",...]` → RFC 959），源 `kb/ftp/spec/rfc959.txt` 已删，**配置指向不存在的源** |

> **注意 `ftp_base.dict` 保留的连带效应**：`scripts/seedgen.py:_write_dictionary`
> 里 `dict_kind == "base"` 会 `load_base_dict_tokens(protocol)`，若为空则
> `raise FileNotFoundError`。但这只在**显式 `--protocol ftp --dict base`** 时触发；
> ftp 已无 facts，`seedgen.main()` 在更早的 `if not views: return 1` 就退出了，
> **永远走不到那一行**。零风险。

**实测影响**：我把 `profiles/ftp/` **整个目录**模拟删除后跑全量，
失败集合依然**逐条不变**（§6.3）—— 即「删 rfc_config.json」与「整个删」对测试
**无任何区别**。保留 profile.json + ftp_base.dict 是**语义更完整**的选择。

### 2.3 `derived/per_source/{dns,dtls,ftp,ssh,tls}/` —— **整个删**（已执行，18:12）

| 目录 | 处置 | 理由 |
|---|---|---|
| `derived/per_source/dns/` | **删** | 源 `kb/dns` 已删 → facts 无源可溯；`derived/` 在 `.gitignore` 里是再生数据目录 |
| `derived/per_source/dtls/` | **删** | 同上 |
| `derived/per_source/ssh/` | **删** | 同上 |
| `derived/per_source/tls/` | **删** | 同上 |
| `derived/per_source/ftp/` | **删** | **孤儿产物**：197 KB 五源 facts，其源 `kb/ftp/{expert_note,spec,协议实现源码,历史漏洞,数据流量}` 全部已删。留着会让 `load_fact_views("ftp")` 返回 285 条**无法溯源**的 facts |
| `derived/per_source/{rtsp,sip,smtp}/` | **保留** | 三个目标协议的五源产物 |

**实测影响**：`load_fact_views("ftp")` 返回 285 → 0。**关键验证**：
`test_boundary_probe.py::test_generate_protocol_dict_protocol_specific_and_clean`
原本依赖 ftp 的 facts 产出 `RETR/STOR/SITE CPFR` token —— 我实测**在 derived/per_source/ftp
消失后该用例仍然通过**，因为该文件在 18:08 已被同步改掉了 ftp 断言块
（现为 `for proto in ("rtsp", "sip", "smtp")`）。**若两者不同步，必然回归**（见 §5 风险 R2）。

### 2.4 `core/fused/protocol_patterns.py` —— **决策：保留 dns/dtls/ssh/tls/ftp 条目，不动本文件**

> **2026-11-01 状态更新**：`software-engineer` 曾于 10-31 19:16 完成该 P0
> （收敛到 3 协议 + 补文件头「协议范围」说明，验证 `list_protocols() == ['rtsp','sip','smtp']`、
> 5 个下线协议回落 `DEFAULT_PATTERN` 不抛异常、pytest 零影响），
> **但因未提交，被 11-01 13:31 的破坏性 git 操作整体回滚**。
> 实测：当前文件**又变回 8 个条目**，文件头说明也一并丢失；
> `git log --all` 确认**无任何提交含 3 条目版本**，`git fsck` dangling 对象里也没有
> → **该成果无法从 git 恢复，需重做**。
>
> **重做时请连同「改完立即提交」一起做**（否则再被一次 reset 吞掉）。
>
> **但下面的决策建议已改为「保留、不动」** —— 理由与 10-31 19:10 那版不同，
> 因为**git 仓库的出现改变了「不可逆成本」这个关键权重**：

> **2026-10-31 19:10 复核修正**（回答主理人第 3 问「删除是否会破坏 source_fsm.py 的 import 或测试」）：
> **实测：删除条目【不会】破坏 import，【不会】破坏任何测试。**
> 但**本轮仍建议保留**，理由与「删」相反：
>
> | 检查项 | 实测结果 |
> |---|---|
> | `source_fsm.py:19` 的 `from core.fused.extraction.protocol_patterns import get_pattern` | **不受影响** —— 删的是 `PROTOCOL_PATTERNS` 的**字典条目**，不是函数/模块。`get_pattern` 照常存在 |
> | `get_pattern("dns")` 的行为 | `PROTOCOL_PATTERNS.get(key, DEFAULT_PATTERN)` → 删条目后**回落 `DEFAULT_PATTERN`，不抛异常**（`protocol_patterns.py:98`） |
> | `source_fsm.py` 的调用链 | `_extract_protocol_signals(src_dir, protocol)` → `get_pattern(protocol)`，**协议名由调用方传入**，引擎本身协议无关。删条目只影响「若真有人用 dns/dtls/ssh/tls/ftp 调它」的路径 → **那种调用本来就不该发生**（kb 已无这些协议） |
> | 测试引用 | `grep -rn "protocol_patterns\|list_protocols\|PROTOCOL_PATTERNS" tests/` → **0 命中** |
> | `PROTOCOL_PATTERNS` / `list_protocols()` 的外部调用方 | 全仓库 grep → **仅 `protocol_patterns.py` 自身**，`source_fsm.py` 只用 `get_pattern` |
> | `source_fsm.py` 自身状态 | 已标 `DEPRECATED（2026-10-19）`，`source.py:52-54` 明写「三者构成孤岛（**生产链路无调用方**）」 |
>
> **决定保留的三个理由**：
> ① **它是「协议 Profile 配置层」，不是「知识输入层」** —— 文件头 `protocol_patterns.py:9-12` 自己声明
>    「本文件属于『协议 Profile 配置层』，与 `core/fused/hub/registry`、`targets` 同类；
>    **本文件【不属于】结构化知识中枢**，因此『清空结构化知识中枢』时，**本文件不受影响，不会被清理**」。
>    本次裁剪的是 **kb 知识输入**，**不是配置层** —— 删配置层条目属于**扩大裁剪范围**，
>    会打破该文件自己声明的分层不变量。
> ② **零收益零风险**：它不被任何测试断言、不被任何生产链路调用。删了**测试数不变**（37），
>    留着也**测试数不变**。既然对验收无影响，就**不应在本轮引入额外不可逆变更**。
> ③ **它承载的是「协议知识」而非「某次实验的数据」**：dns/dtls/ssh/tls 的状态机信号正则
>    （`handleCmd_` / `byte` / `state_vars` 约定）是**可复用的协议知识**，
>    与 kb 里的 RFC 文本/漏洞库/抓包数据（已随 kb 删除）**性质完全不同**。
>    kb 删了 = 「这些协议的**知识实例**没了」；pattern 条目 = 「这些协议的**抽取规则**还在」。
>
> **若将来要做「配置层收敛」（独立议题，非本轮）**，正确做法是：
> **整文件退役**（连同 `source_fsm.py` 一起删）—— 而不是留着一个 DEPRECATED 孤岛再逐条削字典。
> 因为「DEPRECATED + 无调用方 + 无测试」的文件，唯一合理终态是删除；
> 逐条删字典条目只会产生一个「半死」的模块。
> **本轮不做，因为整文件退役会动 `source_fsm.py` 的 import（`from core.fused.extraction.protocol_patterns import get_pattern`），
> 属于超出「kb 裁剪」范围的改动。**
>
> ---
>
> **2026-11-01 决策再修正（因 git 出现，权重变了）**：
> 10-31 我主张「保留」的核心权重之一是「本轮不应引入额外**不可逆**变更」。
> 现在 `core/` 已 git 跟踪 → **这个顾虑消失了**（删错了 `git checkout --` 即可恢复）。
> 剩下两条理由仍然成立：
> - **分层不变量**：该文件自己声明它属于「协议 Profile 配置层」、**不属于结构化知识中枢**，
>   「清空知识中枢时不受影响」—— 删配置层条目 = **扩大本轮裁剪范围**；
> - **协议知识 ≠ 实验数据**：这些正则（`handleCmd_`/`byte`/`state_vars` 约定）是
>   **可复用的抽取规则**，kb 删了 = 「知识实例」没了，pattern = 「抽取规则」还在。
>
> **但工程侧已给出第三条理由，我认为它成立且应当采纳**：
> 「对应 kb 源/目标环境/语料都已删，pattern 留着就是**无人消费的僵尸知识**」——
> 本项目的**协议范围**在 `kb/` + `profiles/` 两处都有权威声明，
> `protocol_patterns.py` 不是范围声明源，留着 5 个已下线协议的条目**确实**是
> 一种「读者会误以为这些协议仍受支持」的噪音。
>
> **⇒ 最终建议（提请 team-lead 裁决，二选一）**：
> | 选项 | 动作 | 代价 |
> |---|---|---|
> | **甲（工程侧）** | 重做 P0：删 5 条目 + 补文件头说明，**并立即提交** | 需重做一遍（10 分钟）；对测试零影响（已实测） |
> | **乙（我原主张）** | 不动 | 零动作，但留下 5 条僵尸条目 |
>
> 我**倾向甲**：既然 git 已提供可逆性，「不可逆成本」不再是反对理由，
> 而「消除僵尸知识」是真实的可读性收益。**但无论选哪个，都必须立即提交**。

| 条目 | 处置 | 理由 |
|---|---|---|
| `"rtsp"` / `"sip"` / `"smtp"` | **保留** | 目标协议 |
| `"dns"` / `"dtls"` / `"ssh"` / `"tls"` | **删** | 对应协议已出目标范围 |
| `"ftp"` | **删** | 同上 |
| `DEFAULT_PATTERN` | **保留** | `get_pattern()` 对未知协议返回它，**删条目不会抛异常** |
| `source_fsm.py` / `source.py` 的引用 | **不动** | `source_fsm.py:41` 只调 `get_pattern(protocol)`，不硬编码协议名 |
| `source_probe.py:21` / `run_boundary_probe.py:39` 的 `SSH = ["ssh", "-i", ...]` | **绝对不动** | 这是 **SSH 客户端命令**（连虚拟机的），不是协议知识 |

**为什么删是安全的（无破坏性）**：
- 唯一调用方是 `core/fused/source_fsm.py`，而 `source_fsm.py` 本身标
  `DEPRECATED（2026-10-19）：已被 source_autoseeder.py 替代`，
  `core/fused/source.py:52-54` 注释明确写：
  *「source_fsm 与 protocol_patterns 均已 DEPRECATED，三者构成孤岛（生产链路无调用方）」*；
- `get_pattern()` 用的是 `PROTOCOL_PATTERNS.get(key, DEFAULT_PATTERN)` ——
  **删条目 = 回落到兜底 pattern，不抛异常**；
- 全仓库 grep 确认 `PROTOCOL_PATTERNS` / `list_protocols()` **没有任何外部调用方**
  （只有本文件内部定义 + `source_fsm.py` 调 `get_pattern`）；
- **无测试引用** `protocol_patterns`（`grep -rn "protocol_patterns\|list_protocols" tests/` → 0 命中）。

**但请注意**：这个改动是**纯语义收敛**，对测试**零影响**（37 failed 不变），
属于「知识库一致性」而非「修 bug」。可与本次清理同批做，也可单独排期。

### 2.5 明确保留（不动）

| 文件 | 理由 |
|---|---|
| `core/fused/source_probe.py:21` `SSH = ["ssh","-i",...]` | **SSH 客户端命令**（连 VM），不是协议知识 |
| `scripts/run_boundary_probe.py:39` `SSH = [...]` | 同上 |
| `scripts/response_rewriter.py:425` `PROTO_FTP = "ftp"` | ChatAFL 富化链路的协议标签常量；`extract_ftp_messages` 有 12 个专门测试（`tests/test_response_rewriter.py` 53 passed）；**删它会打断一条独立且完整的链路** |
| `scripts/response_rewriter.py:36-45` `FTP_METHODS` | 同上，42 个 FTP 命令，与 `targets/ftp/profile.json` 的 allowed_methods 对齐 |
| `tests/fused/test_response_rewriter.py` 全部 53 个用例 | 纯函数级，不依赖 kb |

### 2.6 其它残留（**建议一并清理，非阻塞**）

| 路径 | 处置 | 理由 |
|---|---|---|
| `derived/seeds/ftp/`（138 个 .raw，2 个时间戳目录） | 建议删 | ftp 已非目标协议；`derived/` 是再生数据目录 |
| `derived/source_blocks/ftp.state.json` | 建议删 | AutoSeeder 检索缓存，ftp 的源已删，缓存无法重建 |
| `derived/experiments/chatafl_analysis/ftp_aflnet_对照/` | **建议保留** | 这是**实验结果记录**（baseline vs protorag 对照分析报告），是论文素材不是再生数据 |
| `derived/spec/{modbus,fakeproto,fakeproto2}/` | 建议删 | `modbus`/`fakeproto*` 从来不是目标协议，是历史遗留测试残留 |
| `profiles/README.md:108-110`、`README.md:28` | 建议改 | 写着「kb/ 8 协议」「4 协议（ftp/rtsp/sip/smtp）」，与现状不符 |
| `derived/per_source.bak_20261018/` | 保留（可选删） | 历史备份，非目标范围污染源 |

---

## 3. 测试收敛方案（逐文件逐行）

### 3.1 `tests/fused/test_expert_note.py` —— 5 处

| 行 | 原 | 新 | 说明 |
|---|---|---|---|
| 10 | `expert_note_to_facts(protocol="dns")` | `protocol="rtsp"` | rtsp 有 8 条 facts，实测非空 |
| 15 | `protocol="dns"` | `protocol="rtsp"` | |
| 28 | `protocol="dns"` | `protocol="rtsp"` | |
| 35 | `protocol="dns"` | `protocol="rtsp"` | |
| 43 | `for p in ["dns","dtls","ftp","rtsp","sip","smtp","ssh","tls"]` | `for p in ["rtsp","sip","smtp"]` | 遍历 3 个目标协议 |

**断言主体的改法（关键 —— 不能只换 protocol 参数）**：
原断言是 dns 专属的（`("header","QNAME")`、`("method","DNSSEC 校验")`、
`"缓存投毒"`、`"label" or "指针"`），换成 rtsp 后**这些断言全部不成立**。
必须换成 rtsp 的真实 expert_note 内容：

| 断言 | rtsp 实际值（实测自 `kb/rtsp/expert_note/`） |
|---|---|
| `("header","QNAME")` | → `("header","Transport")` |
| `("method","DNSSEC 校验")` | → `("method","SETUP")` |
| `"缓存投毒" in name` | → `"会话状态机" in name` |
| `"label" in n or "指针" in n` | → `"CSeq" in n or "Session" in n` |

**不要用「断言任意非空」来糊弄** —— 那会把「4 个维度都映射到了正确的 subject 类型」
这个真正的契约给测没了。改后仍应校验：hotspots 的 `target_type=field→header` /
`target_type=method→method` 映射、design_weaknesses 挂 protocol subject、
implicit_constraints 挂 header subject。

### 3.2 `tests/fused/test_rfc_extractor.py` —— 2 处

| 行 | 原 | 新 |
|---|---|---|
| 81 | `extract_constraint_candidates("dns")` | `extract_constraint_candidates("rtsp")` |
| 93 | `infer_constraints("dns", llm=stub, max_candidates=8)` | `infer_constraints("rtsp", llm=stub, max_candidates=8)` |

**注意**：用例 93 的 stub 返回的是 DNS 语义的 QNAME/FORMERR，
但 `infer_constraints` **只把 stub 的返回原样透传**，不校验协议一致性，
所以换成 rtsp 后 stub 仍返回 QNAME → 断言 `c["field"] == "QNAME"` 仍成立。
**改 protocol 参数即可，断言不必动**。（rtsp 实测 `cands=80` ≥ `max_candidates=8`，满足。）

行 104/135 的 `"norm_id": "dns.constraint.qname"` / `"protocol": "dns"` 是
**纯内联 dict 字面量**（不读 kb），保留即可，不影响。

### 3.3 `tests/fused/test_rfc_extractor_a1.py` —— 3 处（含主理人点名的那条）

| 行 | 原 | 新 | 说明 |
|---|---|---|---|
| 298 | `for proto in ("sip", "rtsp", "ftp", "smtp")` | `for proto in ("sip", "rtsp", "smtp")` | 删 ftp |
| 362-365 | `("rtsp",11), ("ftp",15), ("smtp",8)` | `("rtsp",11), ("smtp",8)` | **删 ftp 行** |
| 393-397 | `test_real_ssh_has_data_type_fields` | **整个函数删除** | ssh 已删，断言无从校验 |

#### ⚠️ 主理人点名问题：`test_real_protocol_method_counts[ftp-15]` 的 ftp 换成什么？

**答案：不换 —— 删掉这一行参数化，只保留 `rtsp`(11) 与 `smtp`(8)。**

三个候选逐一评估：

| 候选 | 评价 |
|---|---|
| **换成 `sip`** | ❌ **不可行**。SIP 实测只抽出 **1 个 method（`OK`）**（见 §1.3），只能写 `("sip", 1)`。断言 `len(methods) >= 1` **恒真、零信息量** —— 等于把一个测试变成永绿的空壳，**这正是「掩盖真实缺陷」** |
| **换成 `rtsp` 或 `smtp`** | ❌ 无意义。已有的 `("rtsp",11)` / `("smtp",8)` 就是这两个协议，再加一行重复覆盖 |
| **删掉 ftp 行** | ✅ **正确**。该用例的职责是「对有足够方法数的协议，锁住抽取下限」。ftp 出范围后，剩下 rtsp(11) 与 smtp(8) **两个有意义的样本**。SIP 的方法抽取不足是**独立的抽取器缺陷**（§1.3），应该**单独立 issue 修**，而不是往这个用例里塞个 `("sip",1)` 假装覆盖 |

> **SIP 方法抽取不足的处理建议**（不在本次清理范围，但请记 issue）：
> 根因是 SIP RFC3261 的方法名在**缩进条目**（`9.1 REGISTER`）而非**章节标题**里，
> 而正文标题形态是 `9.1 Client Behavior`。修法有两条路：
> (a) 修 `kb/sip/spec/rfc3261.txt` 的标题形态（改数据，成本高）；
> (b) 在 `rfc_config.json` 的 sip 段加 `method_excludes` / 改 `method_sections`
> 并让 `_extract_rfc_file` 支持「从缩进条目提方法」（改代码，与 A1.5 通道 A 同源）。
> **推荐 (b)** —— A1.5 的 `_extract_command_entries` 已经实现了「全称（缩写）」形态，
> SIP 的 `9.1 REGISTER` 若写成 `REGISTER (REGISTER)` 形态即可被复用。

#### `test_real_ssh_has_data_type_fields` 的删除留痕

**不要静默删除** —— 保留一段注释说明为何删除（否则后人又会加回来）：
```
# ssh 已于 2026-10-31 从目标协议范围移除（kb 裁剪），故删除本用例
# （原 test_real_ssh_has_data_type_fields 校验 SSH §5/§6 的 byte/boolean/uint32
#   数据类型字段，ssh 的 kb/spec 已不存在，该断言已无从校验）
```

### 3.4 `tests/fused/test_boundary_probe.py` —— 1 处

| 行 | 原 | 新 |
|---|---|---|
| 153-156 | `# ftp：含空格命令（SITE CPFR）` / `ftp = _toks("ftp")` / `assert {"RETR","STOR","SITE CPFR","PASV"} <= set(ftp)` | **整块删除** |
| 159 | `for proto in ("rtsp", "sip", "smtp", "ftp")` | `for proto in ("rtsp", "sip", "smtp")` |

**关键依赖链**（务必与 §2.3 同步）：
`derived/per_source/ftp/` 删掉后，`load_fact_views("ftp")` 返回空 →
`generate_protocol_dict` 对 ftp 只产出 13 个 token（实测：
`['-1','0','1','2147483647','4294967295','65535','CDUP','CWD','PASS','PASV','PORT','TYPE','USER']`），
**缺 `RETR` / `STOR` / `SITE CPFR`** → 上述 ftp 断言**必然失败**。
**只删 derived 不改测试 = 从 37 failed 变 38 failed。**

### 3.5 `tests/fused/test_vuln.py` —— 1 处（**已由 QA 复核确认修好，本节仅留档**）

| 行 | 原 | 现（已落地并验证） |
|---|---|---|
| 82-84 | `facts = vuln_to_facts(protocol="ftp")` + `if facts:` 软断言 | `for protocol in ("rtsp", "smtp")` + **硬断言** `assert facts, f"{protocol} 应有漏洞库"` |

> **2026-11-01 QA 复核结论（撤回我 10-31 的「永绿空壳」判断）**：QA 用清理前备份做了直接 diff，
> 证明**当前版本已是硬断言**，`grep 'if facts' test_vuln.py` → **0 命中**。
> 实测 `vuln_to_facts`：rtsp=76 / smtp=101 / sip=45 / ftp=0；该用例 **1 passed**。
> **我的原结论已过期 —— 该测试现在写法正确，无需再改。**
>
> （历史留档：原代码的 `if facts:` 确实是真 bug —— kb/ftp 删除后 `facts=[]` 会让整个断言块
> 被跳过。**好在它已被修掉。**）

### 3.6 `tests/fused/test_source_retrieval.py` —— 1 处（**保留原样，仅加注释**）

| 行 | 原 | 处置 |
|---|---|---|
| 50 | `for proto in ("rtsp", "smtp", "ftp", "sip", "http", "dns")` | **保留这 6 个名字**，加注释说明 |

**理由**：这个用例断言的是 `proto not in joined`（**协议名不应出现在 query 里**），
是**负向断言**。把 ftp/dns 从列表里删掉，等于**削弱检出能力**（将来 query 里
混入 "ftp" 硬编码就再也测不出来了）。正确做法是**保留协议名并加注释**：
```
# 因此 dns/ftp 等已移出目标范围的协议名仍需保留在黑名单里（否则将来
# query 里混入 "ftp" 之类的硬编码将失去检出能力）；"http" 同理——它本来
# 就不是目标协议
```

### 3.7 `tests/fused/test_rq3_focus_group.py` —— **不动**

| 行 | 内容 | 处置 |
|---|---|---|
| 261 | `"ftp": {"A": (29,32), ...}` | **保留** |
| 283 | `@pytest.mark.parametrize("protocol", ["ftp", "sip", "smtp"])` | **保留** |

**理由**：该文件的失败是**预存**的 rq3 契约脱节（`ftp/A: 期望 29，实际 55`），
与本次清理**无关**（主理人已确认）。且 **`test_focus_group_protocol_calibration[ftp]`
必须在 37 failed 里** —— 它是基线 37 的一部分，删掉会让失败数掉到 36，
**直接违反「37 failed 逐条一致」的验收标准**。

⚠️ **但要知道它的失败原因会变**：现在 `derived/per_source/ftp/` 已删 →
`seedgen.main()` 在 `if not views: return 1` 处退出 → 失败信息从
`种子数不符: 期望 29，实际 55` 变成 **`!! 无 facts（协议 ftp）`**。
**失败用例集合不变（仍是 37，集合逐条一致），但断言点变了。**
这是**可接受的**（用例仍 fail，仍在集合里），但必须记录 —— 见 §5 风险 R4。

---

## 4. 实施顺序（有依赖关系）

```
阶段 0（前置，只读）：固化基线快照
    ├─ 跑 pytest 存 37 failed 的完整清单到 docs/实施/知识库维护/kb范围收敛清理方案.md §1.1
    └─ 跑 rfc_baseline_probe × 3 存指标（§1.3 表）
       ↓
阶段 1（可并行，互不依赖）：
    ├─ 1A 改测试：test_expert_note.py(5) + test_rfc_extractor.py(2)
    │           + test_rfc_extractor_a1.py(3) + test_vuln.py(1)
    │           + test_source_retrieval.py(仅注释)          【§3.1/3.2/3.3/3.5/3.6】
    └─ 1B 改测试：test_boundary_probe.py(2)                 【§3.4】
       ↓
阶段 2（依赖 1B，**必须同批**）：
    删 derived/per_source/{dns,dtls,ftp,ssh,tls}/
    ⚠️ 与 1B 顺序无所谓，但**必须同时完成**，否则中间态是 38 failed
       ↓
阶段 3（依赖阶段 2 跑绿）：删 profiles/{dns,dtls,ssh,tls}/
    └─ profiles/ftp/ 只删 rfc_config.json（保留 profile.json + ftp_base.dict）
       ↓
阶段 4（**本轮不做**）：`core/fused/protocol_patterns.py` —— 保留不动（见 §2.4）。
    └─ 若将来做「配置层收敛」，应连同 `source_fsm.py` 整文件退役，而非逐条削字典
       ↓
阶段 5（可选）：清 derived/seeds/ftp、derived/source_blocks/ftp.state.json、
    derived/spec/{modbus,fakeproto,fakeproto2}；更新 README.md:28、
    profiles/README.md:108-110 的协议清单
```

**并行度说明**：阶段 1A 与 1B 可并行（改不同文件）；
阶段 2 与阶段 1 的**代码改动**无依赖，但**必须在阶段 1 完成后跑一次全量**才能确认；
阶段 3 必须等阶段 2 完成（否则 `derived/per_source/ftp` 已删但 `targets/ftp/profile.json`
还在，`seedgen --protocol ftp` 的失败点会变）。

---

## 5. 风险清单

| # | 风险 | 触发条件 | 影响 | 缓解 |
|---|---|---|---|---|
| **R1** | **SIP 方法抽取只有 1 个（`OK`）** | SIP 的方法名在缩进条目而非章节标题里 | `test_real_protocol_method_counts` 若加 `("sip", N)`，N 只能=1 → 断言恒真、变成空壳 | **不要用 sip 顶替 ftp**（§3.3）。SIP 抽取不足单独立 issue 修（推荐改 `_extract_rfc_file` 复用 A1.5 通道 A） |
| **R2** | **derived/per_source/ftp 删除后 `test_boundary_probe` 必然失败** | 删 derived 不同步改测试 | 从 37 failed → **38 failed**，直接违反验收 | **§3.4 与 §2.3 必须同批**。实测 ftp facts 消失后字典只剩 13 token，缺 `RETR`/`STOR`/`SITE CPFR` |
| **R3** | **删 `protocol_patterns.py` 条目** | 有人以为 `source_fsm.py` 会因 KeyError 挂掉 | 实际**不会**：`get_pattern()` 用 `.get(key, DEFAULT_PATTERN)` 兜底；删的是字典条目，**不是**函数/模块，`source_fsm.py:19` 的 import 不受影响；tests/ 0 引用 | **本轮决策：保留不动**（§2.4）。若将来做，删条目会让 `get_pattern("dns")` 静默回落 `DEFAULT_PATTERN`（泛化结果），而正确做法是**整文件连同 `source_fsm.py` 退役** |
| **R4** | **`test_focus_group_protocol_calibration[ftp]` 失败原因变了** | `derived/per_source/ftp/` 删除后 seedgen 提前 `return 1` | 失败**集合不变**（37 逐条一致），但断言点从「种子数 29≠55」变成「无 facts」 | **接受**（用例仍 fail、仍在集合内，符合验收）。但若主理人要求「失败原因也逐条一致」，则**必须保留 `derived/per_source/ftp/`** —— 见 §6.4 的两难 |
| **R5** | **`paths.target_profile` 报错** | 删 `targets/<p>/profile.json` 后调 `_load_profile()` | **不会抛异常**：`_load_profile` 用 `if not p.exists(): return {}`（scripts/seedgen.py:98-100）；`rfc_extractor._load_rfc_config` 走 `if not prof.exists(): 打印警告; return cfg` | 安全。但 `_load_profile` 返回 `{}` 后 `seedgen` 会在更早处（无 facts）退出。已实测：删 `targets/ftp` 整目录后失败集合逐条不变 |
| **R6** | **`profiles/ftp/ftp_base.dict` 被误删** | 有人按「ftp 出范围」把整个 ftp 目录清掉 | `load_base_dict_tokens("ftp")` 返回空集；`seedgen --dict base --protocol ftp` 会 `FileNotFoundError` —— 但**永远走不到**（无 facts 提前退出）。**且该文件未被任何 MD5 锁引用、MD5 与 rtsp 字典互不相同 → 删了就是永久丢失一份独立的 FTP 命令集** | 实测**删整个 `targets/ftp/` 目录后失败集合也逐条不变**（§6.4 场景 B）→ 保留零风险。**本轮决策：保留**（§2.2） |
| **R7** | **`scripts/rq3_build_corpus.py:132` 硬编码 `targets_root()/protocol/f"{protocol}_base.dict`** | 该脚本只跑 rtsp（`cfg["protocol"]`） | 不受影响 | 保持 rtsp 即可；无需改 |
| **R8** | **`derived/` 被 `.gitignore` 忽略 = 无版本回退** | 项目**不是 git 仓库**（`git status` → fatal: not a git repository） | **删除不可逆** | **不可逆操作清单**（§7）：① `derived/per_source/{dns,dtls,ftp,ssh,tls}` ② `profiles/{dns,dtls,ssh,tls}` ③ `profiles/ftp/rfc_config.json` ④ `core/fused/protocol_patterns.py` 的 5 个条目 ⑤（可选）`derived/seeds/ftp` 等。**建议先 `cp -r` 到 `$TEMP` 备份**再删 |
| **R9** | **并发编辑事故** | 本次调研期间（18:07–18:22）`software-engineer` **正在同时改同一批测试文件** | 若本方案基于旧快照执行，会覆盖对方的改动 | **本方案基于 18:22 的实测现状编写**；执行前必须重跑 §6.1 确认当前失败集合 |
| **R10** | **`derived/per_source/rtsp/rfc/` 被 `build_hub.py` 重建覆盖** | 跑 `build_hub.py --sources rfc --protocol rtsp` 会 `_clean_per_source` 清空并重建 | 若重建产物与原产物不同，rq3 相关失败数可能变化 | 实测跑完三次 build_hub 后 pytest **仍是 37 failed**，**重建是幂等的**（build_id `rb_172d0daf0029e9c0` 稳定） |
| **R11** | **失败数偶发变 38 —— 已定位为并发编辑，非本方案引入** | **并发 teammate 在改 `core/fused/downstream/target_env.py` + `scripts/seedgen.py`** | 偶发多出 1 个失败。两次捕获到的分别是：① `test_rq4_target_url_normalization.py::test_pipeline_uses_only_profile_and_allow_list`（该测试文件 18:45:33 新建，被测模块 18:55:10 仍在改）② `test_rq3_manifest.py::test_cli_no_manifest_without_flag`（`scripts/seedgen.py` 18:59:06 被改，**第 303 行残留字面量 `/n` 导致 SyntaxError**，19:00:23 teammate 修好后即恢复 37） | **与 kb 裁剪完全无关**。稳定后连跑 6 次均 37 failed、集合逐条一致。**验收必须避开并发编辑窗口**；建议加一道前置闸：`python -c "import ast; ast.parse(open('scripts/seedgen.py',encoding='utf-8').read())"` 通过后再跑 pytest |
| **R12** | **`derived/per_source/*/rfc/facts/snapshots/<build_id>/` 目录残留** | 跑 `build_hub.py` 会写快照目录（`scripts/build_hub.py:290`） | `load_fact_views()` 用 `root.glob("*/facts/*.jsonl")` —— **`snapshots/<id>/*.jsonl` 不会被匹配**（多一层目录），**无污染**。但目录会累积 | 实测：跑完 build_hub 后 `load_fact_views("rtsp")` 仍为 359 条（与裁剪前一致）。可择机清理 |

---

## 6. 验收标准（可自动验证）

### 6.1 主验收：失败数回到 37 且集合逐条一致

```bash
cd "E:/科研/想法idea/rag-chatafl"
E:/app/Anaconda3/python.exe -m pytest tests/ -q --tb=no -p no:cacheprovider
# 期望：failed == 37，errors == 20（passed 不固定，随并发新增测试文件变动，勿作判据）
```
> 注：`pytest.ini` 已有 `addopts = -v --tb=short -m "not llm"`，加 `-q` 抑制 verbose。

**逐条一致校验**（集合比对，非仅计数）：
```bash
# 1) 存当前失败清单
E:/app/Anaconda3/python.exe -m pytest tests/ -q --tb=no -p no:cacheprovider 2>&1 \
  | grep "^FAILED" | sort > "$TEMP/failed_final.txt"
# 2) 与基线 37 清单比对（集合相等，且双向差集为空）
E:/app/Anaconda3/python.exe -c "
import os
d=os.environ['TEMP']
base=set(l.strip() for l in open(os.path.join(d,'failed_base37.txt'),encoding='utf-8'))
now =set(l.strip() for l in open(os.path.join(d,'failed_final.txt'),encoding='utf-8'))
print('count', len(base), len(now), 'IDENTICAL =', base==now)
print('only base:', base-now); print('only now:', now-base)
"
```
**实测结果**：`37 37 IDENTICAL = True`，双向差集均为空集。

> ⚠️ **必须用「集合比对」而非仅计数**：并发 teammate 的在途改动会让失败数偶发 +1
> （见 §5 风险 R11）。仅看计数会误判为「清理引入回归」。

**并发安全提示**：本仓库**不是 git 仓库**，多人同时改同一文件会互相覆盖。
验收前请确认无并发写入 —— 建议先跑一道**语法闸**：

```bash
E:/app/Anaconda3/python.exe -c "
import ast
for f in ('scripts/seedgen.py','core/fused/downstream/target_env.py'):
    ast.parse(open(f,encoding='utf-8').read()); print(f,'OK')
"
```
（本次调研期间实测：`scripts/seedgen.py` 曾因并发编辑残留字面量 `/n` 而 SyntaxError，
导致 pytest 多出 1 个失败 —— 详见 §5 风险 R11。）

### 6.2 三个目标协议的 rfc 源构建

```bash
for p in rtsp sip smtp; do
  E:/app/Anaconda3/python.exe scripts/build_hub.py --sources rfc --protocol $p
done
```
**期望**（实测全部通过）：
| 协议 | 质量闸 | norms | facts | build_id |
|---|---|---|---|---|
| rtsp | 通过（dup_fact_ids=0, toc_pollution=0） | 71 | 116 | `rb_172d0daf0029e9c0` |
| sip | 通过 | 100 | 149 | `rb_66d511116ea5b01b` |
| smtp | 通过 | 21 | 32 | `rb_e0aeda91794fcdef` |

**幂等性**：重复跑，build_id 不变，pytest 仍 37 failed（实测）。

### 6.3 rfc_baseline_probe

```bash
for p in rtsp sip smtp; do
  E:/app/Anaconda3/python.exe scripts/rfc_baseline_probe.py --protocol $p; echo "exit=$?"
done
```
**期望**：三协议 **exit=0**（实测全部 0）。
| 协议 | norm_count | norm_kinds | dup_fact_ids | toc_sourced_outcomes |
|---|---|---|---|---|
| rtsp | 71 | field:45, method:11, outcome:15 | 0 | 0 |
| sip | 100 | field:49, method:1, outcome:50 | 0 | 0 |
| smtp | 21 | field:11, method:10 | 0 | 0 |

### 6.4 删除安全性模拟（本次调研实际做的验证）

我用 pytest 插件**不改任何文件**地模拟了三种删除组合，各跑全量测试比对失败集合：

| 模拟场景 | 失败数 | 与基线 37 集合比对 |
|---|---|---|
| A. 删 `targets/{dns,dtls,ssh,tls}` + `per_source/{dns,dtls,ftp,ssh,tls}` | 37 | **逐条一致** ✅ |
| B. 额外**整个**删 `targets/ftp/`（含 profile.json + ftp_base.dict） | 37 | **逐条一致** ✅ |
| C. 仅删 `per_source/ftp/`（`targets/ftp` 保留） | 37 | **逐条一致** ✅ |

> 场景 B 证明：**「删整个 `targets/ftp/`」与「只删 `rfc_config.json`」对测试
> 无任何可观测差异**。因此保留 `profile.json` + `ftp_base.dict` 是**纯粹的语义偏好**，
> 零风险。

### 6.5 稳定性复测（对抗并发编辑干扰）

为排除「偶发回归」，我在**无并发编辑窗口**内连跑 **6 次**全量：

```
run 1: 37 failed   run 2: 37 failed   run 3: 37 failed
run 4: 37 failed   run 5: 37 failed   run 6: 37 failed
diff run1..run6 → 全部无差异（集合逐条一致）
```

另有 8 次连跑中出现 2 次 38 —— 经集合比对定位到唯一多出的用例。
两次捕获到的多出项**各不相同**，且都指向并发 teammate 的在途改动：

| 多出的失败用例 | 根因 | 时间线 |
|---|---|---|
| `test_rq4_target_url_normalization.py::test_pipeline_uses_only_profile_and_allow_list` | 该测试文件 18:45:33 **新建**，被测的 `core/fused/downstream/target_env.py` 18:55:10 仍在改 —— 测试与被测模块处于「不同步快照」 | 测试文件稳定后单独跑 **18 passed** |
| `test_rq3_manifest.py::test_cli_no_manifest_without_flag` | `scripts/seedgen.py` 18:59:06 被改，**第 303 行残留字面量 `/n`** → `SyntaxError: invalid syntax`（`if do_endpoint:/n                msg.url = ...`） | teammate 于 **19:00:23 修好**，随即恢复 37 |

两者与「协议范围裁剪」毫无关系（一个是 RQ4 种子 URL 归一化功能，一个是 seedgen 语法错误）。
teammate 修好后重跑：**37 failed，集合与基线逐条一致（IDENTICAL = True）**。详见 §5 风险 R11。

---

## 6.6 QA 复核后的验收标准增强（2026-11-01）

> `software-qa-engineer` 独立复核了本方案，**主体成立**，但提出 3 条对验收标准的**实质性增强** +
> 1 条对我结论的**过期纠正**。以下为合并后的最终版验收标准。

### 增强① 「跑超时」会导致**假性归零**（QA 实测踩到）

QA 初版脚本报了 `failed=0`（3 次全 0）—— **是脚本错误，不是项目状态**。
根因：全量套件现在要 ~380s，QA 给的 timeout 500s×3 轮 ⇒ **pytest 被 kill 在打印 summary 之前**
⇒ `grep '^FAILED'` 拿到**空集** ⇒ 差点据此断言「全绿」。

**⇒ 验收脚本必须先断言「拿到 summary 行」再取数**，没有 summary 就判「本次运行无效」，
绝不能当成「0 失败」：

```bash
E:/app/Anaconda3/python.exe -m pytest tests/ -q --tb=no -p no:cacheprovider > "$TEMP/pt.txt" 2>&1
# ① 先确认拿到 summary
grep -qE "=+ .* failed, .* passed, .* errors" "$TEMP/pt.txt" \
  || { echo "运行无效（未拿到 summary，多半是超时被杀）—— 作废重跑"; exit 1; }
# ② 再取失败清单做集合比对
grep "^FAILED" "$TEMP/pt.txt" | sort > "$TEMP/failed_now.txt"
```

### 增强② 「语法闸」挡不住**语法合法的半成品**（QA 实测漂移到 43）

QA 复现到 **43 failed**（比我的 38 更大），多出的 6 条全落在
`tests/fused/test_rq4_target_url_normalization.py`（19:05 新建）——
**该文件在被写半成品的状态下被 collect**。**语法合法，但内容不完整**。

**⇒ 语法闸不够，要加「mtime 快照闸」**：

```bash
# 跑前：记录 tests/ 的 mtime 快照
find tests/ -name "*.py" -newermt "1970-01-01" -printf "%T@ %p\n" 2>/dev/null | sort > "$TEMP/tests_before.txt"
# 跑 pytest …
# 跑后：比对快照
find tests/ -name "*.py" -newermt "1970-01-01" -printf "%T@ %p\n" 2>/dev/null | sort > "$TEMP/tests_after.txt"
diff "$TEMP/tests_before.txt" "$TEMP/tests_after.txt" \
  || { echo "测试文件在本次运行期间被改动 —— 本次结果作废，重跑"; }
```
（Windows 上若无 `-printf`，用 `Get-ChildItem -Recurse tests\ -Filter *.py | Select-Object FullName, LastWriteTimeUtc`。）

> **2026-11-01 15:20 实测修正：根因比「半成品文件」更精确 —— 是「共享固定路径 fixture + 并发 pytest」的竞争。**
>
> 我复现了这个漂移（单跑该文件 81 passed ✅，并发跑两个进程 → 各 1 failed + 1 error ❌）：
>
> ```python
> # tests/fused/test_annotation_tools.py:651-662
> @pytest.fixture(scope="class")
> def repo_crlf_probe(self, tmp_path_factory):
>     probe = ROOT / "_crlf_probe_tmp"     # ← 仓根下的【固定路径】，不是 tmp_path！
>     probe.mkdir(exist_ok=True)
>     ...
>     yield probe
>     for f in probe.iterdir(): f.unlink()
>     probe.rmdir()                        # ← A 进程的 teardown 删掉了 B 进程正在用的目录
> ```
>
> **两个并发 pytest 进程共用同一个 `_crlf_probe_tmp/`** → A 的 teardown 把 B 正在用的
> 文件删了 → B 的子进程调用失败 → B 报失败。
> **同理** `derived/experiments/annotation/candidates_frozen.jsonl`（**不在 `.gitignore` 里**）
> 被两进程同时读写 → `test_frozen_jsonl_is_lf_on_disk` 偶发报 CRLF。
>
> **⇒ 修正后的闸（在 mtime 快照之外再加两条）**：
> ```bash
> # ① 绝对不要并发跑两个 pytest（同一仓库）
> # ② 跑前确认没有别的 pytest 在跑
> tasklist 2>/dev/null | grep -i python || ps aux | grep -c "[p]ytest"
> # ③ 跑前清掉残留的共享临时目录
> rm -rf "_crlf_probe_tmp"
> # ④ 保留 mtime 快照闸（挡「别人正在写测试文件」）
> ```
> **根因修复建议（给该文件作者）**：把 `ROOT / "_crlf_probe_tmp"` 改成
> 带 `uuid`/pid 隔离的目录名，或用 `tmp_path_factory` 造仓内路径（需 `import core` 才放仓内），
> 让并发进程互不干扰。

### 增强③ 我的「坑③」结论已过期 —— 撤回

我 10-31 报告「`test_vuln.py` 的 `if facts:` 软断言是永绿空壳」——
QA 用清理前备份做了直接 diff，证明**当前版本已是硬断言**：
```python
for protocol in ("rtsp", "smtp"):
    facts = vuln_to_facts(protocol=protocol)
    assert facts, f"{protocol} 应有漏洞库"      # ← 硬断言
    assert all(f.fact_key.protocol == protocol for f in facts)
```
`grep 'if facts' test_vuln.py` → **0 命中**。实测 `vuln_to_facts`：
rtsp=76 / smtp=101 / sip=45 / ftp=0，且该用例 **1 passed**。
**⇒ 撤回「唯一还在骗人的测试」这条结论。它已是正确写法。**

### QA 新增的两条实测项（超出本清理范围，但影响验收）

| # | 发现 | 影响 | 建议 |
|---|---|---|---|
| **①** | **`scripts/rq3_build_corpus.py` 首组失败即 `return 4` 中止** | B/C/D 组**永远不会被重新生成** —— 实测 `derived/experiments/rq3/A/seeds` mtime=11-01 15:05（被 pytest 触发重写），而 B/C/D 仍是 10-31 03:24 的旧产物 | 即使修好 host 归一化，**磁盘上的 B/C/D 旧语料仍带 50 个摄像机 host + 52 个不可播会话名**。建议改成「继续构建其余组 + 汇总失败」 |
| **②** | **rq3 是协议级语料（无 `--target-env`）⇒ `allowed_resources` 为空 ⇒ `normalize_seed_resource` 不生效** | 当前污染实测：A 组 bad_sess=226（**100%**）、B/C/D bad_host=139 / bad_sess=100；`derived/seeds/rtsp/rq4_B` 干净（150/150） | 要清会话轴，**协议级语料也必须绑定目标环境**（`--target-env rq2-live555`），否则会话轴永远清不掉 |

> 这两条属于**语料质量**议题，与「kb 收敛清理」正交，但会影响「rq3 语料是否可用」的判断。
> QA 已同步给 team-lead 决策。

---

## 7. 不可逆操作清单（**2026-11-01 修正：项目已成为 git 仓库**）

> **前提已变**：原判断「项目不是 git 仓库 → 删除不可逆」**已失效**。
> 2026-11-01 13:31 项目完成首次入库（`c9295b4`），随后 13:59 merge `origin/main`（`493874c`）。
>
> ### 7.1 现在的可逆性分级
>
> | 目录 | git 跟踪状态 | 删除可逆性 |
> |---|---|---|
> | ``、`tests/`、`docs/`、`core/`、`scripts/`、`kb/` | **已跟踪**（实测 `git ls-files` 确认） | ✅ **可逆** —— `git checkout -- <path>` 即可恢复 |
> | `derived/` | **仍被 `.gitignore:39` 忽略** | ❌ **真正不可逆** —— 唯一需要备份的对象 |
>
> ### 7.2 真正不可逆的只剩这几项
>
> ```bash
> # 只有 derived/ 下的删除需要备份（其余已 git 保护）
> cp -r derived/per_source/ftp          "$TEMP/backup_derived_per_source_ftp"   # 若尚未删
> cp -r derived/seeds/ftp                "$TEMP/backup_derived_seeds_ftp"
> cp    derived/source_blocks/ftp.state.json "$TEMP/backup_ftp_state.json"
> ```
>
> | # | 操作 | 状态 | 可逆性（修正后） | 备注 |
> |---|---|---|---|---|
> | 1 | 删 `derived/per_source/{dns,dtls,ftp,ssh,tls}/` | **已执行 10-31 18:12** | ❌ **不可逆**（`derived/` 被 ignore） | 且 ftp 那 197 KB facts 的**源 `kb/ftp/` 已永久删除 → 即使备份也无法重建**。这是全案**唯一真正不可逆**的操作 |
> | 2 | 删 `profiles/{dns,dtls,ssh,tls}/` | **已执行 10-31 18:16** | ✅ **已可逆**（已入 `c9295b4`，`git checkout` 可恢复） | 内容是 A0.1/A0.2 新建，本可重建 |
> | 3 | 删 `profiles/ftp/rfc_config.json` | **已执行 10-31 18:16** | ✅ **已可逆**（同上） | 同上 |
> | 4 | `profiles/ftp/{profile.json,ftp_base.dict}` | **决策：保留** | 保留即无风险 | 已入 git，删除也可逆 —— 但**语义上仍建议保留**（§2.2） |
> | 5 | 删 `derived/seeds/ftp/`（138 .raw） | 待定 | ❌ **不可逆** —— 这是**实验语料**不是再生数据，**必须先备份** | |
> | 6 | 删 `derived/source_blocks/ftp.state.json` | 待定 | ❌ **不可逆** —— ftp 源已删 → 缓存**无法重建** | 建议备份 |
> | 7 | 删 `derived/spec/{modbus,fakeproto,fakeproto2}/` | 待定 | ❌ 不可逆（`derived/`） | 历史测试残留，优先级低 |
> | 8 | 改 `core/fused/protocol_patterns.py` | **P0 曾执行，已被破坏性 git 操作回滚** | ✅ 可逆（已跟踪） | 见 §2.4 —— **需重做或明确不做** |

### 7.3 新增风险：破坏性 git 操作会静默吞掉未提交的工作

**实测教训**：工程师 10-31 19:16 完成的 `protocol_patterns.py` P0（收敛到 3 协议 +
补文件头说明）**从未提交**，13:31 的 `git reset HEAD~1` → 大提交 → merge 序列把它
**连同文件头注释一起抹掉**了。`git log --all` 确认：**没有任何提交含 3 条目版本**，
`git fsck` 的 dangling 对象里也没有 → **该成果无法从 git 恢复**。

**⇒ 强制纪律（建议 team-lead 采纳）**：
1. **改动完成即提交**。本项目无分支，**提交是唯一可靠的保险**（`software-engineer-12` 已在其文档中践行）。
2. **禁止在飞期间执行 `git reset --hard` / `git checkout -- .` / 强制 merge**；
   如确需，用 `git stash push -m "说明"` 代替（至少带说明且不覆盖工作区）。
3. **每次破坏性操作前后跑一次失败集合比对**（§6.1）—— 本次正是靠这个发现 P0 被吞。



## 8. 遗留问题（不在本次清理范围，建议单独立 issue）

| # | 问题 | 严重度 | 建议 |
|---|---|---|---|
| **L1** | **SIP rfc 抽取只有 1 个 method（`OK`）** | **高** | SIP 是三大目标协议之一，方法知识近乎为零，直接影响 SIP 的种子生成质量与 fuzzing 覆盖。修法见 §3.3 的 (b) |
| **L2** | **SIP 抽出垃圾 field**：`become` / `not` / `or`（来自 `rfc3261.txt#@249` 的 URI 示例行） | 中 | `_extract_indented_entries` 把 URI 示例的单词当成了缩进条目。需加「条目名不得为常见虚词」的过滤 |
| **L3** | **SMTP 把方法名当 field**：`MAIL`/`RCPT`/`DATA`/`RSET`/`VRFY`/`EXPN`/`HELP`/`NOOP`/`QUIT` 同时出现在 field 与 method | 中 | SMTP 的方法在 §4.1 缩进条目里（通道 A），但也被 `_extract_indented_entries`（通道 B）重复收为 field。需让通道 B 排除已识别的命令条目 |
| **L4** | **RTSP 抽出截断 field `WWW-Authentica`** | 低 | `kb/rtsp/spec/rfc2326.txt:3445` 原文即 `12.44 WWW-Authentica`（**源文件本身截断**，非抽取器 bug） |
| **L5** | **RTSP/SIP/SMTP 三协议 rfc 抽取指标未做横向对齐** | 中 | rtsp method:11 / sip method:1 / smtp method:10 —— 差距主要来自**各协议 RFC 的标题形态不同**，而非抽取器能力差异。建议做一次「三协议标题形态对照表」，把 A1.3 的形态判定补齐 |
| **L6** | `README.md:28`、`profiles/README.md:108-110` 仍写「8 协议」「4 协议（ftp/rtsp/sip/smtp）」 | 低 | 阶段 5 一并更新 |

---

## 9. 本文档的实测方法说明（可复现）

```bash
# 解释器（无 pytest，仅标准库）
C:/Users/13594/.workbuddy/binaries/python/versions/3.13.12/python.exe
# pytest 环境（pytest 8.4.2）
E:/app/Anaconda3/python.exe
```

- **基线测量**：`E:/app/Anaconda3/python.exe -m pytest tests/ -q --tb=no -p no:cacheprovider`，
  捕获 `^FAILED` 行做集合比对；
- **删除模拟**：写 pytest 插件（`-p <plugin>`）在 `pytest_configure` 里
  **monkeypatch `core.paths` 的 `target_profile` / `target_rfc_config` / `per_source_root`**
  指向空目录，**不改任何项目文件**，从而在不删盘的前提下测出删除影响；
- **产物指标**：`E:/app/Anaconda3/python.exe -c "..."` 直接调
  `core.fused.rfc_extractor.extract_rfc_norms` / `rfc_quality_report` /
  `extract_constraint_candidates` 与 `core.fused.downstream.rag_seedgen.load_fact_views`。
