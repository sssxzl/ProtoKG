# B 阶段人工标注集 · 现状报告

> **一句话结论**：**候选已冻结（120 条）、训练/holdout 已分离、A 轮标注已完成（120 条，含 48 条 `uncertain`）；
> κ 尚未计算 —— 因为还没有真人标注者 B。**
>
> 本报告对应的规范：`docs/rfc_source_bcd_roadmap.md` §4.6（人工标注集怎么建）、§4.2（落盘位置）。
> 标注指南：`docs/annotation_guide.md`。

---

## 0. 状态一览

| 项目 | 状态 | 说明 |
|---|---|---|
| 候选句冻结 | ✅ **已完成** | 120 条（rtsp/sip/smtp 各 40），md5 可复现，span 100% 可逐字核对 |
| 四类主体覆盖 | ✅ **已完成** | method 34 / field 30 / status 9 / message_type 47，**三协议各自四类均非空** |
| 训练/holdout 分离 | ✅ **已完成** | train 100 / holdout 20，holdout 按协议分层（7/7/6） |
| 标注指南 | ✅ **已完成** | `docs/annotation_guide.md`，**零答案泄漏**（有机械闸可证） |
| 标注工具 + 校验器 | ✅ **已完成** | `scripts/annotate_candidates.py`，10 条校验规则 |
| κ 计算脚本 | ✅ **已完成** | `scripts/calc_cohen_kappa.py`，已用两组构造数据实测 |
| **A 轮标注（标注者 A）** | ✅ **已完成** | 120 条，其中 **48 条标记 `uncertain`** |
| **B 轮标注（真人标注者 B）** | ❌ **未开始** | ⬅ **当前唯一阻塞项** |
| **Cohen's κ** | ❌ **无法计算** | ⬅ 依赖 B 轮；**不得伪造** |
| 第三人仲裁 | ⬜ 未开始 | 依赖 κ 结果 |
| 标注集定稿冻结 | ❌ 未冻结 | 依赖 κ ≥ 0.6 与仲裁完成 |

---

## 1. 冻结候选的实测分布

### 1.1 总量与分层

```
总数: 120        按协议: {'rtsp': 40, 'sip': 40, 'smtp': 40}
按主体: {'method': 34, 'field': 30, 'status': 9, 'message_type': 47}
带 span 的: 120 / 120
```

**协议 × 主体 交叉表**（每格非空 ⇒ 四类主体在三协议各自都有覆盖）：

| 协议 | method | field | status | message_type | 合计 |
|---|---|---|---|---|---|
| rtsp | 12 | 5 | 4 | 19 | 40 |
| sip | 3 | 21 | 2 | 14 | 40 |
| smtp | 19 | 4 | 3 | 14 | 40 |
| **合计** | **34** | **30** | **9** | **47** | **120** |

**切分**（train / holdout，按协议分层）：

| 协议 | train | holdout | 合计 |
|---|---|---|---|
| rtsp | 33 | 7 | 40 |
| sip | 33 | 7 | 40 |
| smtp | 34 | 6 | 40 |
| **合计** | **100** | **20** | **120** |

### 1.2 数据质量实测

| 检查项 | 结果 |
|---|---|
| span 逐字核对（`src[span_start:span_end] == text`） | **120 / 120 完全一致**（0 处不符） |
| candidate_id 唯一性 | ✅ 无重复 |
| 必需字段齐全（`candidate_id`/`protocol`/`text`/`span_start`/`span_end`/`source`/`section_path`/`spec_version`） | ✅ 120/120 齐全 |
| 冻结可复现性 | ✅ 两次运行 **md5 相同**（`b24b59287ff258b64b028c0559660cdd`） |

### 1.3 抽样策略（为什么这样分层）

- **确定性**：抽样**完全不用随机数发生器**，而是「**稳定哈希置换（SHA-256）+ 等距取点**」。
  刻意不用 `random.Random(seed).sample()` —— 其实现细节随 CPython 版本漂移，
  「固定种子」只在同一解释器版本下可复现，不足以当实验基线。
  哈希置换与 Python 版本、运行顺序、字典序全部无关。
- **四类主体全覆盖**：先按**最大余数法**把每协议 40 个名额分给四类主体，
  **每个非空层保底 1 个**（`min_one=True`），再按层内比例分配其余名额。
  层内选点用等距取点而非随机，避免「全挤在同一小节」。
- **分层依据不含任何方法/字段白名单**：主体分类只读
  `fused_hub/targets/<p>/rfc_config.json` 的**章节号前缀**（`method_sections`/
  `field_sections`/`status_sections`）+ RFC **章节标题措辞**。
  **不读 `profile.json` 的 `allowed_methods`** —— 见 §5 防泄漏说明。

---

## 2. A 轮标注的实测统计

### 2.1 按协议

| 协议 | 条数 | 含规范要求 | 占本协议 | `uncertain` | 占比 |
|---|---|---|---|---|---|
| rtsp | 40 | 24 | 60.0% | 11 | 27.5% |
| sip | 40 | 29 | 72.5% | 16 | 40.0% |
| smtp | 40 | 30 | 75.0% | 21 | 52.5% |
| **合计** | **120** | **83** | **69.2%** | **48** | **40.0%** |

### 2.2 按主体类型

| 主体 | 条数 | 含规范要求 | `uncertain` |
|---|---|---|---|
| method | 34 | 24 | 14 |
| field | 30 | 24 | 14 |
| status | 9 | 5 | 2 |
| message_type | 47 | 30 | 18 |

> `status` 层只有 9 条 —— 因为 RFC 里的状态码**表**多数落在 `status_sections` 章节，
> 而表行本身不是规范性要求；该层候选天然偏少。这是候选池的客观属性，不是抽样偏差。

### 2.3 `modality` 分布

| 取值 | 条数 | 占比 |
|---|---|---|
| `MUST` | 56 | 46.7% |
| `无` | 37 | 30.8% |
| `SHOULD` | 25 | 20.8% |
| `MAY` | 2 | 1.7% |

`MUST NOT` / `SHOULD NOT` 按指南归入各自的正向强度（方向由 `operator` 的
`absent`/`ne` 表达，不由 `modality` 表达）。

### 2.4 `operator` 分布

| 取值 | 条数 | 占比 |
|---|---|---|
| `不可` | 88 | 73.3% |
| `present` | 11 | 9.2% |
| `eq` | 9 | 7.5% |
| `absent` | 7 | 5.8% |
| `le` | 2 | 1.7% |
| `ge` | 1 | 0.8% |
| `range` | 1 | 0.8% |
| `in` | 1 | 0.8% |

**「不可」占 73.3% 是本轮标注最重要的实测结论**，原因有二，且都写进了指南：

1. **抽取器按行切句造成大量半句**（120 条里 52 条不含大写 RFC 2119 关键词，
   相当一部分是被截断的片段）⇒ 缺操作数/缺被约束对象 ⇒ 不可执行。
2. **RFC 里的规范性要求有很大比例是「行为/顺序/状态」而非「取值」**
   （如「MUST 先 SETUP 后 PLAY」「MUST NOT be retransmitted」）⇒ 无单值比较可言。

> 这直接影响下游指标 M1「可执行率」的**期望值**：
> 在这 120 条上，人工标注给出的**可执行率上界是 32/120 = 26.7%**。
> 换言之 E1 的可执行率若超过 ~27%（加上 C0 的差距），说明**它在把不可执行的候选也算成规则**。
> 这个基线数应当写进 B-10 实验的预登记。

### 2.5 `expected_response_class` 分布

| 取值 | 条数 | 占比 |
|---|---|---|
| `null` | 114 | 95.0% |
| `protocol_error` | 6 | 5.0% |
| `success` / `application_error` / `silence` | 0 | 0% |

**95% 是 `null`，这是符合预期的**：RFC 的规范性条款绝大多数只规定「发送方必须做什么」，
不说「接收方不这么做会怎样」。指南明确要求**不从协议常识倒推** ——
倒推出来的标注会让 F1 虚高，是这份标注集最需要防的污染。

---

## 3. 不确定条目清单与原因分类

**48 / 120 条（40.0%）标记为 `uncertain`**，全部进入**待仲裁清单**。

### 3.1 原因分类

| 分类代号 | 条数 | 占比 | 含义 |
|---|---|---|---|
| `truncated-constraint` | 26 | 54.2% | **约束内容被截断** —— 被约束对象/谓语/操作数落在 `text` 之外 |
| `descriptive-vs-normative` | 9 | 18.8% | 描述性 vs 规范性的边界（小写 `must`/`should`/`may` 在散文里） |
| `operator-boundary` | 7 | 14.6% | 算子选择边界（`absent` / `ne` / `不可` 三者皆可辩） |
| `modal-outside-span` | 2 | 4.2% | 规范动词落在 span 之外（抽取切句造成） |
| `meta-statement` | 2 | 4.2% | 元叙述 / 显式声明「非规范」 |
| `response-boundary` | 2 | 4.2% | 响应类别边界（`protocol_error` vs `application_error`） |

### 3.2 根因分析（这一条对 B 阶段很重要）

**「截断」贡献了 54.2% 的不确定条目** —— 这**不是标注者能力问题**，
而是**候选抽取粒度问题**。

> ★ **明确归因（供 B-10 设计者读）**：
> **这 26 条 `truncated-constraint` 的根因在抽取侧，不在标注侧。**
> 具体机制：`core/fused/rfc_extractor.py:1875` 的
> `_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")`
> —— 其 **`\n+` 分支把「每一个换行」都当成句界**。
> 而 RFC 原文是**折行排版**的（正文通常每行 ~72 字符硬折行），
> 一个逻辑句常跨 3~5 行 ⇒ 每个折行点都被误切一刀 ⇒ 产出大量**半句**候选。
>
> **量化证据**（见 §3.4 的影响分析）：
> **120 条候选里只有 1 条是「完整逻辑句」**（113/114 条散文候选全是半句），
> 6 条结构性行（表格/ABNF/报文字段）因不参与折行而不受影响。
>
> ⇒ **结论**：A 轮标注的 48 条 `uncertain`（40%）**不应被读作「标注质量差」**，
> 而应读作「**抽取粒度问题的体检报告**」。等粒度修正后重标，这批不确定会自然消失。

### 3.3 逐条清单

| candidate_id | 协议 | 主体 | split | 标注 | 原因 |
|---|---|---|---|---|---|
| `rtsp-000dfca9bee6` | rtsp | message_type | train | MUST/ge/null | truncated: 被约束对象(session identifier)在 text 外，但 at least eight octets 明确 |
| `rtsp-229ffd339f0d` | rtsp | method | train | MUST/eq/protocol_error | truncated: 主语(it=server)被截断；eq(501) 与「对响应码的约束不可落字段」可辩 |
| `rtsp-3fa065e28080` | rtsp | method | holdout | 无/不可/null | descriptive-vs-normative: 描述 Range time 参数语义，playback should start 是语义说明还是行为要求 |
| `rtsp-689ea830b36e` | rtsp | message_type | train | MUST/不可/null | truncated: 约束内容(NOT be retransmitted)在 text 外 |
| `rtsp-77e94828b4a0` | rtsp | status | train | MUST/不可/null | operator-boundary: 「不得被缓存」是缓存状态而非字段存在性；absent 与不可可辩 |
| `rtsp-821aa86d2970` | rtsp | message_type | train | 无/不可/null | modal-outside-span: text 内无规范动词，但上下文(requires the presence of)表明是要求；严格按 text 判否 |
| `rtsp-9470f2c3f51c` | rtsp | message_type | train | MUST/不可/null | truncated: 约束内容(至少含一个 RTSP URI)在 text 外 |
| `rtsp-9a4c0ee82d93` | rtsp | field | holdout | MUST/不可/null | truncated: 真正的约束(in the same order)在 text 外 |
| `rtsp-bde467734520` | rtsp | field | train | SHOULD/le/null | truncated: 被约束对象(The name)在 text 外，但 no more than 与操作数(20)明确 |
| `rtsp-c3f5ab9d9635` | rtsp | method | train | MUST/不可/null | truncated: until SETUP 被确认 的时序条件被截断；absent 与「纯顺序约束不可」可辩 |
| `rtsp-e7e733bc9f01` | rtsp | method | train | MUST/不可/null | truncated: 主语(Method names)与前半约束被截断 |
| `sip-0d5a3015881b` | sip | field | train | SHOULD/eq/null | truncated: 被约束对象(Max-Forwards 值)在 text 外，但 eq(70) 明确 |
| `sip-1cf8f7b16c97` | sip | field | train | MUST/eq/null | truncated: 被约束字段(protocol name / version)在 text 外，且一句约束两个字段两个取值 |
| `sip-1e3f31dd449d` | sip | field | train | MUST/不可/null | truncated: 截断于 MUST 之后，谓语与操作数不在 text 内 |
| `sip-226ea2acd06f` | sip | message_type | train | MUST/不可/null | truncated: 被约束对象(alternate destinations)在 text 外；TLS 是传输方式还是可落字段的取值未定 |
| `sip-4f40f60ba5d6` | sip | field | train | SHOULD/eq/null | truncated: 操作数是字段引用(the URI in the To field)，引用对象在 text 外 |
| `sip-59c051a73079` | sip | field | holdout | MUST/不可/null | truncated: 约束内容在 text 外 |
| `sip-5fada95585f9` | sip | field | holdout | 无/不可/null | descriptive-vs-normative: 小写 should 描述域名角色，非对实现的要求 |
| `sip-645150405362` | sip | message_type | holdout | MUST/in/null | truncated: 集合成员(standards-track RFCs)在 text 外 |
| `sip-76dab8acba77` | sip | field | train | SHOULD/不可/null | descriptive-vs-normative: 小写 should 出现在劝告性散文中 |
| `sip-8693fa68fba0` | sip | field | train | MAY/不可/null | descriptive-vs-normative: 小写 may 在让步从句中；真正的要求在 text 外 |
| `sip-9a5dd33e6127` | sip | message_type | train | MUST/不可/null | truncated: 约束内容在 text 外 |
| `sip-c2805d005259` | sip | message_type | train | 无/不可/null | descriptive-vs-normative: 小写 must 位于 Route Set 的定义句中，属定义而非要求 |
| `sip-c8861d595909` | sip | message_type | train | MUST/eq/null | truncated: 操作数为字段引用(Content-Type)，引用对象在 text 外 |
| `sip-dd5616ae8b94` | sip | field | train | MUST/range/null | truncated: 上界(less than 2**31)在 text 外；按 text 应为 range，完整句为 lt |
| `sip-e32335d890d1` | sip | message_type | holdout | MUST/不可/null | truncated: 谓语与操作数(CRLF)在 text 外 |
| `sip-f86340bae301` | sip | field | train | MUST/eq/null | truncated: 被约束对象(It=Call-ID)与比较基准均在 text 外 |
| `smtp-1e18c593f99a` | smtp | method | train | 无/不可/null | meta-statement: 句子在讨论规范级别本身(requirement to MUST)，非对实现的要求 |
| `smtp-2e3e7c680c60` | smtp | method | train | MUST/不可/protocol_error | response-boundary: 原文未给具体码；permanent failure 按 5xx 归 protocol_error，但 permanent mailbox 拒绝也可能是 application_error |
| `smtp-4504948f1aef` | smtp | message_type | train | 无/不可/null | meta-statement: 「illustrative examples ... should not actually be used」是显式非规范声明还是劝阻性表述 |
| `smtp-520018cc3ab6` | smtp | message_type | train | MUST/eq/null | truncated: 操作数是字段引用(打开连接时用的主机名)，跨字段比较的落点存疑 |
| `smtp-71f20f164758` | smtp | message_type | train | SHOULD/不可/null | operator-boundary: 否定的是标识取值(ne)还是字段存在(absent) |
| `smtp-765b44eb7da0` | smtp | message_type | train | SHOULD/不可/null | descriptive-vs-normative: 小写 should not be stripped indiscriminately |
| `smtp-8101f38a5bae` | smtp | method | train | MUST/不可/null | truncated: 约束内容在 text 外 |
| `smtp-8cbe56740f00` | smtp | method | train | SHOULD/eq/protocol_error | response-boundary: 5.7.0 属 5xx 按指南为 protocol_error，但归 application_error 亦可辩 |
| `smtp-8e517f6ef5bb` | smtp | status | train | SHOULD/不可/protocol_error | operator-boundary: 词表无「不属于某集合」的否定；530 的归类兼有 application_error 之辩 |
| `smtp-8ff09eb8e832` | smtp | method | train | MUST/不可/null | operator-boundary: 「MUST discard any knowledge」是服务器状态而非字段存在性 |
| `smtp-93cc9da7cc23` | smtp | message_type | train | MUST/不可/null | operator-boundary: 大小写敏感属比较语义，词表无对应算子；eq 是否可表达 |
| `smtp-98ec1d7295ee` | smtp | method | holdout | MUST/present/null | operator-boundary: AUTH=<> 是「必须带 AUTH 参数且值为空」(present) 还是 eq(空值) |
| `smtp-a40ad31c4a77` | smtp | field | holdout | MUST/absent/null | operator-boundary: 「MUST NOT offer ... keyword values」否定的是「提供该取值」还是「字段存在」 |
| `smtp-bbf599fa2cf2` | smtp | method | train | MUST/不可/null | descriptive-vs-normative: 小写 must be evaluated carefully 是规范性要求还是实现者提示 |
| `smtp-c1b19b271572` | smtp | method | train | MUST/eq/protocol_error | truncated: 约束对象是响应码而非请求字段，eq(501) 的落点存疑 |
| `smtp-e05666e0e753` | smtp | message_type | train | MUST/不可/null | truncated: 谓语(attempt to authenticate)在 text 外 |
| `smtp-e438bf3334cb` | smtp | method | train | 无/不可/null | modal-outside-span: text 内无规范动词，但上下文为 MUST be able to handle；严格按 text 判否 |
| `smtp-ec27db39eee6` | smtp | message_type | holdout | SHOULD/不可/null | descriptive-vs-normative: 小写 should note carefully |
| `smtp-ef6155d5cfb1` | smtp | method | holdout | MUST/不可/protocol_error | truncated: 谓语(be rejected with a 503 reply)被截断，operator 与响应类别均依赖 text 外内容 |
| `smtp-fe6e6630a675` | smtp | message_type | train | MAY/不可/null | descriptive-vs-normative: 小写 may 描述扩展可放宽限制 |
| `smtp-ff5e23a83f54` | smtp | field | train | MUST/absent/null | truncated: 谓语(be used in a registered service extension)被截断 |

---

## 3.4 ⚠️ 粒度修正后的失效清单（供 team-lead 评估重标成本）

**背景**：抽取粒度修正（合并 RFC 折行 → 按逻辑句切）会**改变候选文本** ⇒
`candidate_id` 变化 ⇒ **本轮 120 条标注会与新候选池失联**。

**工具**：`scripts/annotate_candidates.py impact`（**只读**，不改标注、不写文件）
```bash
$PY scripts/annotate_candidates.py impact \
    --annotations derived/exp_semantic/truth/*.annotated.json \
                 derived/exp_semantic/truth/*.holdout.json --json
```
> ★ 该工具**不依赖** `core/fused/rfc_extractor.py` 的任何实现
> （那正是被改动的一层 ⇒ 依赖它会让结论与「被评估对象」耦合）。
> 它只依据 **RFC 原文的行结构**，独立算出「合并折行后该句本来应该是什么样」。

### 实测结果

> ★ **本节数据已被实测验证**：engineer-13 的粒度修正在 2026-11-01 15:32 落地后，
> 本工具对「哪些条目会失效」的预测与**真实抽取器**逐条对照：
> **召回率 100%（111/111，零漏报）**、**精确率 99.1%**（多报 1 条，
> 该条实际实现保留了独立单元、未跨行合并 ⇒ 只需多复核一次，不会漏标）。
> ⇒ **该清单可直接用于评估重标成本。**

| 指标 | 实测值 |
|---|---|
| 标注总数 | 120 |
| **候选文本会变 ⇒ 必须重标** | **112** |
| 　└ 散文行（受粒度修正影响） | 112 / 114 |
| 　└ 结构性行（表格/ABNF/报文，**不受影响**） | 6（不计入失效） |
| 候选文本不变 ⇒ 标注可复用 | 8 |
| **合并后新出现规范动词 ⇒ 原结论可能翻转** | **2** |
| 已标 `uncertain` 的 48 条中失效 | **48 / 48（全部）** |
| **已标 confident 但文本会变（重标成本主要来源）** | **64** |

**按协议 × 切分分布（失效条目）**：

| 协议 | train | holdout | 合计 |
|---|---|---|---|
| rtsp | 30 | 6 | 36 |
| sip | 32 | 7 | 39 |
| smtp | 32 | 6 | 38 |
| **合计** | **94** | **19** | **113** |

> ⚠ 上表按**本工具的预测**统计（含 1 条多报）；与真实抽取器逐条对照的口径是
> **实际失效 111 条 / 预测命中 111 条**（差 1 条为「预测变、实际未变」的结构性行）。

### ★ 两条「结论会翻转」的条目（合并后新出现规范动词）

| candidate_id | 协议 | 原标注 | 合并后的完整句 | 为什么翻转 |
|---|---|---|---|---|
| `smtp-e438bf3334cb` | smtp | 否 / 无 / 不可 | `Clients and servers MUST be able to handle the maximum encoded size of challenges and responses generated by their supported authentication mechanisms.` | **`MUST` 原本在 span 外** ⇒ 合并后出现 ⇒ 应为「是 / MUST」 |
| `rtsp-f53ef6ccb860` | rtsp | 否 / 无 / 不可 | `They can contain any octet value. The conference identifier MUST be globally unique.` | **`MUST` 原本在 span 外** ⇒ 合并后出现 ⇒ 应为「是 / MUST」 |

> ★ 另有一条 `sip-8693fa68fba0`（我原标 `MAY`）：合并后出现 **`MUST NOT`**
> （`any given parameter-name MUST NOT appear more than once`）⇒ `MAY` 判定被推翻。
> 它已被本工具标为 `uncertain`（原因 `descriptive-vs-normative`）⇒ 属**已知争议点**，不计入「意外翻转」。
>
> 这几条**恰好印证了 A 轮标注的谨慎是必要的**：我按「只依据 text」判定，
> 而 text 恰好切掉了规范动词。**若当时按上下文补全，就会引入信息泄漏**（holdout 同口径要求）。
> ⇒ 指南「只依据 text」的口径是对的，**错的是抽取粒度**，不是标注。

### 前瞻说明（供 B-10 设计者读）

1. **粒度修正后必须重冻结 + 重标注**。当前 120 条标注**只对当前的候选池有效**。
2. **重标成本可估**：112 条文本会变 ⇒ 需重标 112 条；
   其中 48 条是**已标 uncertain** 的（重标时争议点已知，难度低）；
   **64 条是已标 confident 的**（文本变但结论大概率不变 —— 因为合并只是把
   周边上下文补进来，**不改变那句话本身的规范性**；只有上述 2~3 条结论真会翻转）。
   ⇒ **实际需要逐条重新审视的可能只有 ~3~10 条**，其余多为「文本更新、结论平移」。
3. **M1 可执行率上界会随之变化**。当前标注实测上界 **26.7%**（32/120）；
   粒度修正后更多候选能拿到明确操作数 ⇒ **该上界会抬高** ⇒
   **B-10 的预登记必须用「粒度修正后」的候选池重算，不能沿用 26.7%**。
4. **本工具在粒度修正落地后应重跑一次**（命令见上），
   它会给出**新候选池**下的失效清单 ⇒ 用于核验重标是否做全。

### 3.5 一个必须保留的护栏

`calc_cohen_kappa.py` 的「κ < 0.6 ⇒ 只报告、不修改」在重标流程中同样成立：
重标时**不得**为了让 κ 好看而调标注。粒度修正后的 κ 若是低，
**先查是不是指南需要按新的候选形态修订**，而不是动标注。

---

## 4. ⚠️ κ 未计算的说明（**必须如实记录**）

### 4.1 为什么现在没有 κ

**Cohen's κ 的定义要求两个独立标注者在同一批样本上的标注。**
目前只有**一份**标注（标注者 A = 本任务的 AI 执行轮，署名 `annotator: "A"`）。

- 本任务的执行者是 **AI，不是人类标注者**。
- **AI 不能冒充第二名独立人类标注者** —— 若由同一个模型在同一批候选上再标一遍，
  得到的「一致率」衡量的是**模型的自洽性**，不是**标注的客观可靠性**。
  拿它当 κ 会**严重高估**标注集的可信度，直接违反 roadmap §4.6 第 3 条的立法意图
  与评审 R12 的要求。
- 因此本轮**没有**产生任何 κ 数字，**也没有**生成「标注者 B」的文件。

### 4.2 因此当前状态是

> **A 轮标注已完成（120 条，含 48 条标记 `uncertain`）；κ 待真人标注者 B 完成后计算。**

### 4.3 κ 计算流程（真人 B 到位后的执行步骤）

```bash
PY="C:/Users/13594/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# ① 生成 B 的空白模板（B 看不到 A 的标注）
$PY scripts/annotate_candidates.py template --out-dir derived/exp_semantic/truth_b --annotator B

# ② B 独立标注后，校验 B 的文件（每个协议 train+holdout 一起校验）
$PY scripts/annotate_candidates.py validate \
    --annotations derived/exp_semantic/truth_b/rtsp.annotated.json \
    --include    derived/exp_semantic/truth_b/rtsp.holdout.json

# ③ 算 κ + 分歧率（逐协议 + 整体），并打印分歧明细供仲裁
$PY scripts/calc_cohen_kappa.py \
    --a derived/exp_semantic/truth/rtsp.annotated.json \
    --b derived/exp_semantic/truth_b/rtsp.annotated.json \
    --show-disagreements
```

**流程约束（务必遵守）**：

1. **B 必须独立标注** —— B 不得看到 A 的任何标注文件。
   指南里**不含任何一条候选的答案**（有机械闸可证，见 §5），所以 B 靠指南即可。
2. **κ < 0.6 ⇒ 不要自行"修正"标注**。
   `scripts/calc_cohen_kappa.py` **只报告、不修改**；是否重标、是否修订指南，
   由项目负责人裁决（roadmap §4.6 第 3 条）。
3. **分歧由第三人仲裁** —— 48 条 `uncertain` 条目已在 §3.3 列出，
   是仲裁清单的第一批素材。
4. **κ 与分歧率必须写进最终报告**（roadmap §4.7 / 评审 R12）——
   `calc_cohen_kappa.py` 的输出可直接粘贴。

### 4.4 一个必须报告的**预期风险**

**A 轮的 48 条 `uncertain`（40%）是一个偏高的不确定率。**
主因是候选句被切成半句（54.2% 的不确定条目因此而来）。
这意味着 **A 轮标注本身不宜作为「最终标准答案」**，它的定位是：

> **标注指南的可用性探针 + 争议点清单 + 仲裁素材**，而非可直接采信的标准答案。

κ 出来之后，若某字段 κ 偏低，**大概率不是标注者水平问题，而是指南需要按 §3.1 的六类
根因修订**（尤其 `truncated-constraint` 一类，其解法在抽取侧而非标注侧）。

---

## 5. 防信息泄漏：已落实的措施与可证事实

### 5.1 标注参照隔离

| 风险 | 措施 | 可证事实 |
|---|---|---|
| 用 `profile.json` 的 `allowed_methods` 当参照 | 主体分类**只读** `rfc_config.json` 的**章节号前缀** + RFC 章节标题；`profile.json` **从未被读取** | 冻结脚本源码中无 `profile` / `allowed_methods` 引用 |
| 指南泄漏待标注条目的答案 | 指南示例**全部取自非冻结候选池**；提供机械闸 `check-guide` | `check-guide` 实测：**0 处泄漏**（覆盖率阈值 50%，候选长度下限 45） |
| 标注者看实现产出 | 指南明确禁止参考 `derived/per_source/` 与 `core/fused/` 的规则表 | 指南 §8 已写明 |
| holdout 被提前看到 | holdout 单独落盘、单独标注，模式表迭代期不喂 | `candidates_holdout.jsonl` 与 `truth/*.holdout.json` 独立 |

### 5.2 `check-guide` 的判定逻辑

泄漏判据用**覆盖率**而非绝对长度：

```
L1 逐字泄漏：指南含某冻结候选的完整归一化原文        ⇒ 泄漏（必须为 0）
L2 近似泄漏：最长公共子串 / 候选长度 ≥ 50%  且 候选长度 ≥ 45  ⇒ 泄漏
```

短候选（状态码表行、片段）单列 `[note]`，不阻断 ——
因为指南举了 `| "411" ; Length Required` 作表格行示例，
冻结集里的 `411 Length Required all` 是**同一张表的另一行**，
两者共享 `Length Required` 纯属表格词汇重合，**不是答案泄漏**。

实测输出：

```
[OK] 指南无泄漏（检查 120 条冻结候选，覆盖率阈值 50%，候选长度下限 45）
```

---

## 6. 落盘位置（⚠️ 含一条必须裁决的持久化问题）

### 6.1 实际落盘

```
derived/exp_semantic/
├── candidates_frozen.jsonl      # 120 条全集（C0/E1/E2 共用同一批候选）
├── candidates_train.jsonl        # 100 条训练集（模式表迭代只喂这个）
├── candidates_holdout.jsonl      # 20 条 holdout（单独落盘，最终评测用一次）
└── truth/
    ├── rtsp.annotated.json       # 33 条（A 轮，训练集部分）
    ├── rtsp.holdout.json         #  7 条（A 轮，holdout 部分）
    ├── sip.annotated.json        # 33 条
    ├── sip.holdout.json          #  7 条
    ├── smtp.annotated.json       # 34 条
    └── smtp.holdout.json         #  6 条
```

### 6.2 ✅ 持久化问题（**已解决**）

**初稿状态**：`derived/` 曾被 `.gitignore` 第 39 行整目录排除（`git check-ignore` 实测确认），
⇒ 标注集与冻结候选集**都不在版本库里**。

这个设计对 `derived/per_source/`（可由 `kb/` 重建的中间产物）是正确的，
但对**人工标注集**是**错的**：标注集是**不可重建的**（人的判断 + 仲裁结论，
没有任何脚本能重新生成），且它正是 roadmap §4.6 说的「评测集本身不可靠 ⇒ 结论不可信」
的那个「评测集」—— 它必须能被审计、能被追溯「这一版标注是什么时候、由谁做的」。

**已采纳方案 A 并落实**（提交 `7ca6002`）：

```diff
- derived/
+ derived/*                    # ★ 用 derived/* 而非 derived/ —— git 不会进入被排除的目录，
+ !derived/exp_semantic/       #    写 derived/ 的话下面的 ! 例外对里面的文件无效
+ derived/exp_semantic/*
+ !derived/exp_semantic/candidates_frozen.jsonl
+ !derived/exp_semantic/candidates_train.jsonl
+ !derived/exp_semantic/candidates_holdout.jsonl
+ !derived/exp_semantic/truth/
```

⇒ 实测 `git check-ignore` 已**不再命中**；`git ls-files derived/exp_semantic/` 列出
**9 个文件全部入库**（3 个 jsonl + 6 个标注 json）。

**效果**：标注集与冻结候选集**已在版本库内**，可审计、可 diff、可追溯。
副作用是**定稿后不可再改** —— 这恰好符合 §4.6 第 5 条「定稿即冻结」，是特性不是缺陷。

**⚠️ 仓外仍保留一份备份**（`C:/Users/13594/WorkBuddy/qa/_BACKUP_annotation_20261101/`，
15 个文件 md5 逐一核对一致）。原因：`git clean -xfd` 会连**已入库**的文件一起删，
而 `derived/exp_semantic/` 现在**不受 gitignore 保护** ⇒ 备份是唯一能防这一手的东西。

---

## 7. 工具自身的回归测试

`tests/fused/test_annotation_tools.py`（**84 条，全绿**）把「标注基础设施不能被悄悄破坏」
固化成可执行断言：

| 测试类 | 覆盖 |
|---|---|
| `TestFreezeDeterminism` | 稳定哈希键是纯函数（换 salt / 换协议必变）、等距取点确定且有界 |
| `TestAllocate` | 最大余数法：每非空层保底 1 个、分配量不超池容量、结果确定 |
| `TestSubjectClassifier` | 四类主体的判定、无未知返回值、**可执行代码里不出现 profile.json / allowed_methods** |
| `TestFreezeEndToEnd` | 120 条 / 每协议 40 / train 100 + holdout 20 / holdout 按协议分层 / **四类主体在每协议均非空** / id 唯一 / 必需字段齐全 / **span 120 条全部可逐字核对** / 两次冻结完全相同 / **CLI 两次运行 md5 相同** |
| `TestValidator` | 10 条规则逐一必须被拦下（含 **R4 `operator='BAD'`**）、合法值必须被接受、**CLI 对非法文件退出码非 0** |
| `TestTemplate` | 模板**只给题面、绝不带答案**、保留溯源字段、split 过滤生效 |
| `TestGuideLeak` | 逐字泄漏必被拦、干净指南放行、**短候选词汇重合只提示不阻断**、**对真实冻结集跑零泄漏** |
| `TestKappa` | 完全一致 ⇒ κ=1.0、50% 一致 ⇒ κ 显著 < 0.6、**类别分布退化必须显式报告**、长度不匹配报错 |
| `TestCompare` | 逐字段 κ、分歧明细列出、只比较共同 id、整条一致率、**CLI 报告 κ**、**κ 脚本不修改输入文件** |
| `TestGranularityImpact` | 清洗判据与 rfc_extractor **逐条相等**（含「空分支会匹配一切」的坑）、结构性行判定、折行散文合并、表格行**不跨行合并**、**已以句末标点结尾的候选不并入下一句**、真实冻结集上「半句占绝大多数」、结论翻转可检出、**工具只读**、**预测 vs 真实抽取器对照（召回率须 100%）** |
| `TestVocabulary` | OPERATORS 与 roadmap §3.1 逐项相等、modality 词表、**期望响应类别与三协议 rfc_config 一致**、κ 阈值 = 0.6 |
| `TestCRLFRobustness` | **把交付物物化成 CRLF 后行为完全不变**：冻结产出 md5 一致、校验器结论一致、κ 结论一致、泄漏闸结论一致；且冻结产物按 LF 落盘 |

> ★ `TestCRLFRobustness` 针对的是 2026-11-01 实测到的真实场景：本仓
> `core.autocrlf=true`，`git checkout` 会把仓库里存的 LF blob **物化成 CRLF 落盘**
> （实测 `scripts/build_hub.py` 是 `i/lf w/crlf`）。若按字节读文件的校验不抗 CRLF，
> 一次 git 操作就能让「按字节核对」类断言静默失真。该类测试把这条路径固化成回归。

> ★ 其中「κ 脚本不修改输入文件」与「κ 脚本**不因 κ 低而返回非 0**」是刻意设计的：
> 「为了让 κ 好看而调整标注」正是这份标注集最需要防的失败模式。
> 若要接 CI 闸，用 `--fail-below` 显式开启。

**回归护栏**：全量 pytest 实测 **37 failed / 1129 passed / 20 errors**，
`failed == 37 && errors == 20` 与基线**完全一致**（passed 由 819 增至 1129，
增量来自本文件 84 条 + 其他工程师并行新增的测试）。
本任务的三个脚本**不被任何既有测试 import**，且只依赖标准库，
对既有测试**零影响**（已实测核对）。

---

## 8. 冻结状态声明

1. **候选句已冻结**：`derived/exp_semantic/candidates_frozen.jsonl`（120 条），
   由 `scripts/freeze_annotation_candidates.py` 确定性生成，
   **同一 kb/ 输入 ⇒ 同一份输出**（md5 `b24b59287ff258b64b028c0559660cdd`，两次运行已验证）。
2. **holdout 已分离**：20 条（rtsp 7 / sip 7 / smtp 6），
   单独落盘于 `candidates_holdout.jsonl` 与 `truth/*.holdout.json`，
   **模式表迭代阶段只喂 `candidates_train.jsonl`**。
3. **标注集尚未定稿**：A 轮完成（120 条，48 条 `uncertain`），
   **等真人 B 轮 + κ 检验 + 第三人仲裁后**方可定稿冻结。
4. **定稿后不可改**：定稿即冻结；模式表迭代不得再看标注集（roadmap §4.6 第 5 条）。

---

## 8. 交付物清单

| 类别 | 路径 | 说明 |
|---|---|---|
| 指南 | `docs/annotation_guide.md` | 4 字段判定标准 + 正反例 + 边界规则；**零答案泄漏** |
| 报告 | `docs/annotation_status.md` | 本文件 |
| 脚本 | `scripts/freeze_annotation_candidates.py` | 冻结 + 分层抽样（确定性） |
| 脚本 | `scripts/annotate_candidates.py` | 模板生成 / 校验器 / 指南泄漏自检 / 统计 / **粒度影响分析** |
| 脚本 | `scripts/calc_cohen_kappa.py` | Cohen's κ + 分歧率（只算不改） |
| 测试 | `tests/fused/test_annotation_tools.py` | **84 条回归测试**，覆盖确定性/分层/10 条校验规则/κ 两个场景/泄漏闸/词表一致性/**CRLF 鲁棒性**/**粒度影响分析** |
| 产物 | `derived/exp_semantic/candidates_frozen.jsonl` | 120 条全集 |
| 产物 | `derived/exp_semantic/candidates_train.jsonl` | 100 条 |
| 产物 | `derived/exp_semantic/candidates_holdout.jsonl` | 20 条 |
| 产物 | `derived/exp_semantic/truth/*.json` | A 轮标注 120 条（6 个文件） |

> ★ **全部 9 个产物文件已在版本库内**（提交 `7ca6002`）—— `.gitignore` 已按 §6.2
> 为标注集开例外。仓外另有 md5 一致的备份（防 `git clean -xfd`）。

---

## 9. 验收实测输出（全部实测，非预期值）

| # | 验收项 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | 冻结脚本可复现性（跑两次 md5 相同） | 两次 md5 均为 `b24b59287ff258b64b028c0559660cdd` | ✅ |
| 2 | 抽样规模与分层 | 总数 120；按协议 `{rtsp:40, sip:40, smtp:40}`；按主体 `{method:34, field:30, status:9, message_type:47}`；带 span `120/120` | ✅ |
| 3 | 校验器拒绝非法值（`operator='BAD'`） | `[FAIL] bad_op.json: 120 个问题`，**退出码 1** | ✅ |
| 4 | κ：完全一致 ⇒ 1.0 | 四字段 κ 全 = 1.000 | ✅ |
| 4 | κ：50% 一致 ⇒ 显著 < 0.6 | `operator: κ = 0.000 < 0.6`，整条分歧率 0.500 | ✅ |
| 5 | ruff | `All checks passed!`（4 个新文件，含测试） | ✅ |
| 6 | 全量 pytest 回归 | `37 failed, 1129 passed, 20 errors` | ✅ 护栏 `failed==37 && errors==20` 成立 |
| + | 指南零泄漏自检 | `[OK] 指南无泄漏（检查 120 条冻结候选，覆盖率阈值 50%，候选长度下限 45）` | ✅ |
| + | 标注集校验 | 三协议 train+holdout 合并校验，40/40/40 条全部通过 | ✅ |
| + | 工具自身回归 | `69 passed` | ✅ |
