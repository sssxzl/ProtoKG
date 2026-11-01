# -*- coding: utf-8 -*-
"""生成三个 ProtoRAG 项目文档（v2 中枢架构版）。"""
from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = r"E:\科研\想法idea\rag-chatafl思路"


def set_cn(run, size=None, bold=None):
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold


def new_doc():
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    st.font.size = Pt(11)
    return doc


def h(doc, text, level=1):
    p = doc.add_heading("", level=level)
    r = p.add_run(text)
    set_cn(r, bold=True)
    return p


def para(doc, text, bold=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    set_cn(r, bold=bold)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    r = p.add_run(text)
    set_cn(r)
    return p


def table(doc, headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    for i, htxt in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(htxt)
        set_cn(r, bold=True)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(val))
            set_cn(r)
    return t


# =====================================================================
# 文档 1：RAG 对 5 类源处理方法详解
# =====================================================================
doc = new_doc()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("ProtoRAG")
set_cn(r, 26, True)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("结构化知识中枢对五类知识源的处理方法详解")
set_cn(r, 18, True)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("三层架构 · 五源映射 · fail-closed · RAG 种子生成")
set_cn(r, 12, False)

h(doc, "摘要", 1)
para(doc, "ProtoRAG 把五类异构知识源（RFC 规范 / 专家注释 / 历史漏洞 / 真实流量 / 协议实现源码）"
         "抽取为结构化的协议知识，构建「协议无关的知识中枢」，再通过检索增强生成（RAG）把知识喂给 LLM，"
         "生成 AFLNet 可消费的初始种子。中枢采用三层架构：Layer 0 定义协议无关的知识原子（六元组），"
         "Layer 1 为每协议定义封闭的 Profile 注册表，Layer 2 把五类源各自映射到 Profile。"
         "当前 RTSP 实例已跑通五源共 783 条知识原子，fail-closed 校验 0 失败。")

h(doc, "一、三层架构总览", 1)

h(doc, "1.1 Layer 0：协议无关的知识原子", 2)
para(doc, "中枢的最小知识单位是六元组知识原子：")
bullet(doc, "Subject（主体）：协议对象，支持递归嵌套（如关系型主体的 source/target/method 子主体）")
bullet(doc, "Aspect（方面）：主体的某一属性（如 existence / syntax / security_property / target_state）")
bullet(doc, "Condition（条件）：知识成立的约束（当前多用 always）")
bullet(doc, "Value（值）：12 种类型（scalar / enum / set / sequence / range / pattern / struct / ref / "
            "observation / binary / union / text）")
bullet(doc, "Epistemic（认知类型）：知识的来源权威（must / normative_unspecified / descriptive / observed）")
bullet(doc, "Evidence（证据）：知识的溯源（source_type / source_id / document / locator / quote）")
para(doc, "身份标识由哈希决定：fact_id 由 (Subject, Aspect, Condition) 决定；claim_id 由 value + epistemic "
         "哈希；evidence_id 由 source_type + source_id + locator 哈希。这保证同一知识原子在多源、多轮抽取下稳定可合并。")

h(doc, "1.2 Layer 1：协议 Profile（封闭注册表）", 2)
para(doc, "每协议一份 Profile，包含三个注册表：")
bullet(doc, "subject_type_registry：登记合法的 Subject 类型（如 method / header / state / status / relation / "
            "protocol / actor）")
bullet(doc, "aspect_registry：登记合法的 Aspect，并声明其 value_type 与适用主体")
bullet(doc, "epistemic_type_registry：登记合法的 Epistemic 类型及其 authority_rank / can_be_canonical")
para(doc, "Profile 是「封闭声明」：任何未注册的 type / aspect / epistemic 引用都会触发硬错误（fail-closed），"
         "而非静默忽略。加新协议只需新增一份 Profile JSON，不改核心代码。")

h(doc, "1.3 Layer 2：五源映射", 2)
para(doc, "五类源各自映射到 Profile，产出知识原子并落盘 derived/per_source/<source>/facts/<source>.jsonl。"
         "映射方式因源的形态而异：结构化源走「甲方案」（直接读 JSON），半结构化源走 norms 原生映射。详见第三节。")

h(doc, "二、五源映射方法", 1)

h(doc, "2.1 rfc（规范主源）：原生 norm 映射", 2)
para(doc, "输入为 kb/spec/rfc2326.txt，先经抽取器产出 366 条 norm（transition / field / outcome / method 四种 kind），"
         "再由映射器逐条转为知识原子：")
bullet(doc, "transition（from=… method=… code=… to=…）→ relation + target_state，qualifiers 保留 source/target 状态与 method")
bullet(doc, "field（语法 | 规范等级: 语义）→ header + syntax + definition（按规范等级映射 epistemic）")
bullet(doc, "outcome（含义 | when: 条件）→ status + definition")
bullet(doc, "method（方法语义定义）→ method + definition")
para(doc, "实测：366 条 norm → 597 条知识原子（v1 仅贡献 11 条），覆盖 99.7%。")

h(doc, "2.2 expert_note（专家知识）：甲方案结构化映射", 2)
para(doc, "expert_note 是 9 个结构化 JSON（methods / headers / value_pool / relations / state_machine / "
         "status_codes / security_notes 等），直接读 JSON 映射（不经过 norms），7 个维度映射：")
bullet(doc, "methods → method + state_changing（是否改变服务器状态）")
bullet(doc, "headers → header + syntax")
bullet(doc, "value_pool → header + value_enum（实测取值池）")
bullet(doc, "relations（required_headers）→ method + relation_to_other")
bullet(doc, "state_machine（transitions）→ relation + target_state")
bullet(doc, "status_codes → status + definition")
bullet(doc, "security_notes → header/method + security_property")
para(doc, "实测：122 条知识原子。")

h(doc, "2.3 vuln（历史漏洞）：scope 过滤 + 安全属性", 2)
para(doc, "输入为 kb/历史漏洞/ 的 37 个结构化漏洞 JSON。仅 scope=seedgen 的漏洞（与协议强相关）产知识原子，"
         "其余（not_rtsp_protocol / insufficient_source 等）跳过。映射：")
bullet(doc, "trigger.method.value（数组）→ method + security_property（漏洞描述为值）")
bullet(doc, "trigger.field.value（str 或数组）→ header + security_property")
para(doc, "实测：16 条 seedgen 漏洞 → 29 条知识原子（method 10 + header 19），5 条无触发对象跳过。")

h(doc, "2.4 traffic（真实流量）：去重 + 观测", 2)
para(doc, "traffic 在 norms.jsonl 有 40998 行，但同一观测被几千个抓包 capture 重复展开，去重后仅 15 个 "
         "distinct norm。按 norm_id 去重，每条产一条 observed 知识原子，evidence quote 记录「该观测出现于 "
         "N 个 capture」的统计。6 种 kind 映射：")
bullet(doc, "message（method=X occurrences=N）→ method + existence")
bullet(doc, "field（X header occurrences=N / samples=[…]）→ header + occurrence / value_enum")
bullet(doc, "state_machine（observed transitions）→ relation + target_state（相邻方法对）")
bullet(doc, "outcome（status code distribution）→ status + occurrence")
bullet(doc, "protocol（transport 分布 / server 方法集）→ protocol + value_enum")
bullet(doc, "actor（server 端口）→ actor + value_enum")
para(doc, "实测：25 条知识原子，epistemic 一律 observed（样本证据，非规范结论）。")

h(doc, "2.5 source（协议实现源码）：方法定义 + 行号溯源", 2)
para(doc, "输入为 kb/协议实现源码/ 的 live555 C++ 源码，先抽为 method norm（「liveMedia 实现接收并处理 X 方法"
         "（定义处 path:line）」），再映射为 method + definition，并把「定义处 path:line」提取为 evidence 的 "
         "locator 以精确溯源。实测：10 条知识原子。")

h(doc, "三、fail-closed 校验", 1)
para(doc, "所有知识原子落盘前必须通过 fail-closed 校验：")
bullet(doc, "Subject.type 未注册 → 抛 UnregisteredReferenceError")
bullet(doc, "Aspect 未注册 → 抛 UnregisteredAspectError")
bullet(doc, "Epistemic 未注册 → 抛 UnregisteredEpistemicError")
bullet(doc, "Value.type 与 Aspect 声明的 value_type 不一致 → 抛 ValueTypeMismatchError")
para(doc, "fail-closed 的意义：宁可抽取失败暴露问题，也不静默吞掉无法表达的引用。当前五源 783 条知识原子 "
         "校验 0 失败。")

h(doc, "四、RAG 消费通路（知识中枢 → LLM → 种子）", 1)
para(doc, "知识中枢的知识原子如何喂给 LLM 生成种子，是中枢的第一个下游消费。通路如下：")

h(doc, "4.1 分桶组装 / subgraph 检索", 2)
para(doc, "知识原子按 aspect 分桶成「种子生成知识」：方法白名单（method + existence / state_changing）、"
         "状态机转移（relation + target_state）、必填头（method + relation_to_other）、字段取值池（header + "
         "value_enum）、安全关注（security_property）。当前中枢去重后仅约 200 个独特知识原子，可直接全量分桶；"
         "当协议变大时，可按目标 method / state 做结构化 subgraph 检索（GraphRAG 范式，非向量检索），"
         "只取 k-hop 相关子图以省 token。")

h(doc, "4.2 Prompt 渲染", 2)
para(doc, "分桶后的知识渲染成 prompt 的各个 section：协议方法 / 状态机转移 / 必填字段 / 取值池 / 安全关注 / "
         "生成目标 / 输出要求。")

h(doc, "4.3 生成 + 校验 + ReAct 迭代 refine", 2)
para(doc, "LLM 生成种子后，用中枢知识做轻量校验：方法是否在白名单、必填头是否齐全、状态转移是否合法。"
         "校验失败的种子，把错误文本拼回 prompt 重新生成（ReAct / Self-RAG 的自纠正反馈环），最多迭代 3 轮。")

h(doc, "4.4 .raw 落盘", 2)
para(doc, "通过 seedcorpus_to_raw 把合法种子落盘为 ProFuzzBench 兼容的 .raw（AFLNet 可消费）。")

h(doc, "五、关键数字", 1)
table(doc, ["知识源", "知识原子数", "说明"],
      [["rfc", "597", "transition 43 + field 464 + outcome 79 + method 11"],
       ["expert_note", "122", "7 维度结构化映射"],
       ["vuln", "29", "16 seedgen × (method 10 + header 19)"],
       ["traffic", "25", "40998 行去重为 15 distinct norm"],
       ["source", "10", "10 个方法定义"],
       ["合计", "783", "fail-closed 0 失败"]])

h(doc, "六、测试基线", 1)
para(doc, "全量 pytest：120 passed / 0 failed / 0 error。"
         "scripts/build_hub.py --sources <单个源> --protocol <单个协议> 按『一次一个协议 x 一个知识源』逐次跑通五源映射。")

doc.save(OUT + r"\ProtoRAG-RAG对5类源处理方法详解.docx")

# =====================================================================
# 文档 2：设计思路与想法
# =====================================================================
doc = new_doc()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("ProtoRAG 设计思路与想法")
set_cn(r, 22, True)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("三层架构的设计哲学 · 协议通用 · fail-closed · RAG 消费")
set_cn(r, 12, False)

h(doc, "一、设计哲学", 1)

h(doc, "1.1 协议通用（Protocol-Agnostic）", 2)
para(doc, "中枢是为「网络协议」设计的通用结构，而非为某个具体协议定制。加新协议只需新增一份 Profile JSON"
         "（Layer 1 的三个注册表）和对应的 KB 数据，不改任何核心代码。RTSP 是第一个实例，用来验证通用机制，"
         "而非固化 RTSP 特化逻辑。")

h(doc, "1.2 结构化知识原子，而非文本 chunk", 2)
para(doc, "传统 RAG 检索的是「文本片段」，存在碎片化、关系丢失、token 膨胀的问题。ProtoRAG 的知识是"
         "「结构化的六元组原子」（Subject / Aspect / Condition / Value / Epistemic / Evidence），关系显式建模，"
         "因此消费时无需向量检索，直接按 subject / aspect 结构化导航，token 效率更高、可解释性更强。")

h(doc, "1.3 fail-closed：宁可失败，不静默", 2)
para(doc, "知识中枢的 Profile 是「封闭声明」。任何未注册的类型 / 方面 / 认知类型，都触发硬错误而非静默忽略。"
         "这一原则把「设计缺口」显式暴露在抽取阶段，而不是让错误的知识悄悄流入下游种子生成。")

h(doc, "1.4 源隔离", 2)
para(doc, "五类知识源独立映射、独立调试、独立收口。调试某一源只允许改该源相关文件，禁止改动其他源。"
         "这保证五源各自可替换、可 ablation，也为后续扩展新源留出清晰的边界。")

h(doc, "二、三层架构的设计决策", 1)

h(doc, "2.1 为什么 Layer 0 用六元组", 2)
para(doc, "知识的最小单位需要同时回答「是什么」（Subject）、「什么属性」（Aspect）、「在什么条件下」（Condition）、"
         "「值是多少」（Value）、「谁说的、多权威」（Epistemic）、「证据在哪」（Evidence）。六元组把「事实」和"
         "「事实的证明」绑定，使知识可追溯、可合并、可审计。身份由哈希决定，保证多源合并的稳定性。")

h(doc, "2.2 为什么 Layer 1 用封闭 Profile", 2)
para(doc, "Profile 是协议与核心结构之间的「契约」。封闭声明（未注册即报错）有两个好处：一是把每个协议的"
         "合法词汇表显式化，二是让 fail-closed 校验有据可依。这避免了「开放 schema」下下游消费时才发现"
         "未定义字段的被动。")

h(doc, "2.3 为什么 Layer 2 甲方案与 norms 双轨并存", 2)
para(doc, "结构化源（expert_note / vuln）用「甲方案」直接读 JSON 映射，避免经过 norms 中间层造成信息丢失；"
         "半结构化源（rfc / traffic / source）走 norms 原生映射，因为它们的原始形态（文本 / 流量 / 源码）需要"
         "先抽取成 norm。两条路径都汇入同一 Profile，产出统一的知识原子。")

h(doc, "三、RAG 消费的设计决策", 1)

h(doc, "3.1 全量分桶 vs subgraph 检索", 2)
para(doc, "当前中枢去重后仅约 200 个独特知识原子，规模足够小，直接全量分桶喂给 LLM 即可（几 KB token）。"
         "当协议变大、知识变多时，切换为按目标 method / state 的结构化 subgraph 检索（GraphRAG 范式），"
         "只取 k-hop 相关子图。两步都已在代码中实现（assemble_bundle 与 retrieve_subgraph），可按规模切换。")

h(doc, "3.2 ReAct 迭代 refine", 2)
para(doc, "生成 → 校验 → 失败带错重生成，是 ReAct / Self-RAG 的自纠正反馈环。相比一次性生成，迭代 refine "
         "能显著提升种子结构质量（前沿工作报告 BLEU +18%、分支覆盖显著提升）。")

h(doc, "3.3 前沿方法借鉴", 2)
para(doc, "消费通路的设计借鉴了 2025 年该领域的最新工作：GraphRAG（结构化 subgraph 检索，26–97% token 省）、"
         "Self-RAG / Corrective RAG（自纠正反馈环）、RAG-ReAct + CoT（协议 FSM 推断与种子生成）、MultiFuzz"
         "（dense retrieval + 多 agent）。")

h(doc, "四、设计权衡", 1)
table(doc, ["权衡点", "选择", "理由"],
      [["知识形态", "结构化六元组 vs 文本 chunk", "结构化支持关系显式建模、token 高效、可解释"],
       ["校验策略", "fail-closed vs 静默忽略", "设计缺口显式暴露，不污染下游"],
       ["消费方式", "全量分桶 → subgraph 检索", "小规模全量简单，大规模检索省 token，可按需切换"],
       ["生成流程", "ReAct 迭代 vs 一次性生成", "迭代 refine 显著提升结构质量"],
       ["映射路径", "甲方案 + norms 双轨", "结构化源直读，半结构化源经 norm，统一汇入 Profile"]])

h(doc, "五、论文贡献对应", 1)
bullet(doc, "贡献 1：协议无关的结构化知识中枢（三层架构），加新协议只加 Profile JSON")
bullet(doc, "贡献 2：五源异构知识的统一结构化抽取（783 知识原子，fail-closed 0 失败）")
bullet(doc, "贡献 3：面向种子生成的结构化 RAG 消费通路（分桶 / subgraph 检索 / ReAct refine）")
bullet(doc, "贡献 4：协议模糊测试种子的可追溯生成（六元组 + evidence 溯源）")

doc.save(OUT + r"\ProtoRAG-设计思路与想法.docx")

# =====================================================================
# 文档 3：项目介绍书
# =====================================================================
doc = new_doc()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("ProtoRAG")
set_cn(r, 26, True)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("结构化知识中枢 + RAG 的协议模糊测试种子生成器")
set_cn(r, 16, True)

h(doc, "一、项目定位", 1)
para(doc, "ProtoRAG 是一个面向协议模糊测试（protocol fuzzing）的种子生成系统。它从五类异构知识源"
         "（RFC 规范 / 专家注释 / 历史漏洞 / 真实流量 / 协议实现源码）中抽取结构化的协议知识，构建"
         "「协议无关的知识中枢」，再通过检索增强生成（RAG）把知识喂给 LLM，生成 AFLNet 可消费的初始种子，"
         "让模糊测试从「碰运气」变成「按状态机走」。")

h(doc, "二、核心特征", 1)
bullet(doc, "协议通用：加新协议只需新增 Profile JSON（Layer 1），不改核心代码")
bullet(doc, "结构化知识原子：六元组（Subject / Aspect / Condition / Value / Epistemic / Evidence）建模协议知识")
bullet(doc, "fail-closed：未注册的类型 / 方面 / 认知类型触发硬错误，不静默忽略")
bullet(doc, "五源独立抽取：五类知识源各自映射、独立调试、可 ablation")
bullet(doc, "RAG 种子生成：知识中枢 → 分桶 / subgraph 检索 → prompt → LLM → 校验 → ReAct refine → .raw")
bullet(doc, "可追溯：每条知识原子带 evidence 溯源（source_type / source_id / document / locator）")

h(doc, "三、架构总览", 1)
para(doc, "ProtoRAG 采用三层架构 + RAG 消费通路：")
bullet(doc, "Layer 0（协议无关元结构）：六元组知识原子，12 种 ValueType，哈希身份")
bullet(doc, "Layer 1（协议 Profile）：每协议三个封闭注册表（subject_type / aspect / epistemic_type）")
bullet(doc, "Layer 2（五源映射）：rfc / expert_note / vuln / traffic / source 各自映射到 Profile")
bullet(doc, "RAG 消费：知识原子分桶 / subgraph 检索 → prompt 渲染 → LLM 生成 → 校验 → ReAct refine → .raw")

h(doc, "四、五源抽取结果", 1)
table(doc, ["知识源", "知识原子数"],
      [["rfc", "597"], ["expert_note", "122"], ["vuln", "29"], ["traffic", "25"], ["source", "10"],
       ["合计", "783（fail-closed 0 失败）"]])

h(doc, "五、核心创新点", 1)
h(doc, "5.1 协议无关的结构化知识中枢", 2)
para(doc, "三层架构把「协议知识」与「协议实例」解耦。Layer 0 是协议无关的元结构，Layer 1 用封闭 Profile "
         "声明每协议的合法词汇表，Layer 2 把五源映射进来。加新协议只加 Profile JSON。")
h(doc, "5.2 五源异构知识的统一结构化抽取", 2)
para(doc, "五类形态迥异的知识源（文本 / JSON / 流量 / 漏洞 / 源码）统一映射为结构化的六元组知识原子，"
         "并用 fail-closed 校验保证一致性。")
h(doc, "5.3 面向种子生成的结构化 RAG 消费", 2)
para(doc, "结构化知识原子使 RAG 消费无需向量检索，直接按 subject / aspect 分桶或 subgraph 导航，"
         "配合 ReAct 迭代 refine，生成高质量、可校验的协议种子。")
h(doc, "5.4 可追溯的种子生成", 2)
para(doc, "每条知识原子绑定 evidence 溯源，生成种子的依据可回溯到具体规范条款 / 漏洞 / 流量样本，"
         "可解释、可审计。")

h(doc, "六、与现有工作的差异", 1)
table(doc, ["对比项", "ChatAFL", "AFLNet", "ProtoRAG"],
      [["知识来源", "LLM 隐式知识", "响应反推", "五源显式结构化抽取"],
       ["状态机", "LLM 生成", "运行时反推", "规范 + 专家 + 流量结构化抽取"],
       ["种子生成", "grammar 派生", "响应 replay", "状态机引导 + 结构化 RAG + LLM"],
       ["协议迁移", "改 prompt", "改 fuzzer 代码", "加 Profile JSON（0 行核心代码）"],
       ["可追溯", "弱", "弱", "强（evidence 溯源）"]])

h(doc, "七、当前状态", 1)
bullet(doc, "五源抽取：783 知识原子，fail-closed 0 失败")
bullet(doc, "RAG 消费通路：分桶 / subgraph / ReAct / .raw 落盘已跑通")
bullet(doc, "测试：120 passed / 0 failed")
bullet(doc, "实验评估：待进行（后续做实验填数据）")

doc.save(OUT + r"\ProtoRAG-项目介绍书.docx")

print("三个文档已生成到", OUT)
