# -*- coding: utf-8 -*-
"""生成 ProtoRAG 顶会论文稿（中文版，实验数据留空白）。"""
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = r"E:\科研\想法idea\rag-chatafl思路"


def set_font(run, size=None, bold=None, italic=None, east="宋体", west="Times New Roman"):
    run.font.name = west
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic


def new_doc():
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    st.font.size = Pt(11)
    return doc


def h(doc, text, level=1):
    p = doc.add_heading("", level=level)
    r = p.add_run(text)
    set_font(r, bold=True, east="黑体", west="Times New Roman")
    return p


def para(doc, text, bold=False, italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(22)
    r = p.add_run(text)
    set_font(r, bold=bold, italic=italic)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    r = p.add_run(text)
    set_font(r)
    return p


def table(doc, headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    for i, htxt in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(htxt)
        set_font(r, bold=True, east="黑体")
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(val))
            set_font(r)
    return t


doc = new_doc()

# ---- 标题 ----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("ProtoRAG：面向有状态协议模糊测试的结构化协议知识抽取\n与检索增强生成（RAG）驱动的初始种子生成")
set_font(r, 16, True, east="黑体")
p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r2 = p2.add_run("ProtoRAG: Structured Protocol Knowledge Extraction and RAG-Driven Seed Generation "
                "for Stateful Protocol Fuzzing")
set_font(r2, 12, True, east="黑体")

# ---- 摘要 ----
h(doc, "摘要", 1)
para(doc, "有状态协议模糊测试的探测效率，高度依赖于初始种子语料库的质量：高质量的初始种子能够覆盖协议状态机中的合法转移路径，从而引导模糊测试器深入协议逻辑；而违反协议约束的种子则会在早期被服务端拒绝。现有方法要么依赖大语言模型（LLM）内隐的协议知识（如 ChatAFL），要么在运行时动态推断状态机（如 AFLNet），二者均缺乏显式、可溯源、可跨协议泛化的结构化协议知识。本文提出 ProtoRAG，一个从五类异构知识源（RFC 规范、专家标注、历史漏洞、真实流量、协议实现源码）构建协议无关结构化知识中枢，并通过检索增强生成（RAG）引导 LLM 生成初始种子的系统。知识中枢采用三层架构：（第 0 层）协议无关的知识原子模型，将每一条知识统一表示为六元组（Subject、Aspect、Condition、Value、Epistemic、Evidence）；（第 1 层）每协议封闭的 Profile，注册合法词汇表（主体类型、方面类型、认知类型）并进行 fail-closed 校验；（第 2 层）逐源映射，将五类源分别转换为知识原子。在 RTSP 协议上，ProtoRAG 从五类源共抽取 783 条知识原子，校验零失败。在知识中枢之上，本文设计了一条结构化 RAG 消费通路：按方面（aspect）对知识原子分桶（对更大规模的协议则检索 k 跳子图），渲染种子生成提示词，并通过 ReAct 自校正循环迭代精化种子。[实验结果待补充。]")
para(doc, "关键词：协议模糊测试；检索增强生成；知识抽取；种子生成；状态机；大语言模型", bold=True)

# ---- 1. 引言 ----
h(doc, "1  引言", 1)
para(doc, "网络协议模糊测试是发现网络服务漏洞的基础性技术。有状态协议模糊测试以 AFLNet [1] 为先驱，将协议建模为有限状态机（FSM），生成能够穿越合法状态路径的消息序列，从而实现对协议逻辑的深度探索。初始种子语料库的质量直接决定了模糊测试器探索状态空间的有效性：违反协议约束的种子会在早期被拒绝，而覆盖合法状态转移的种子则能引导模糊测试器触及更深层的逻辑。")
para(doc, "近年来，大量工作表明大语言模型（LLM）可以利用其对协议规范的内隐知识来生成具备协议感知能力的种子（如 ChatAFL [2]、MultiFuzz [3]）。然而，LLM 内隐知识存在三个根本性局限。其一，不可溯源：一条生成种子的依据无法回溯到具体的规范条款、漏洞描述或观测行为。其二，不可显式化：知识被埋藏在模型权重中，无法在不重新训练的前提下被检查、修正或扩展。其三，不可泛化：适配一个新协议需要重新设计提示词或微调，而非增量式地补充结构化知识。")
para(doc, "检索增强生成（RAG）通过将 LLM 的生成锚定在外部知识库上，从而缓解上述局限。然而，现有面向协议模糊测试的 RAG 系统大多从 RFC 文档中检索非结构化的文本片段，存在语义碎片化、关系结构丢失以及 token 效率低下等问题。基于图的 RAG（GraphRAG）[4] 通过显式建模实体与关系来改进平面文本检索，但现有实例化方案并非面向协议知识这一天然结构化的领域——协议知识本质上由方法、头部字段、状态转移、状态码、安全属性等结构化要素及其关系构成，并横跨异构来源。")
para(doc, "本文提出 ProtoRAG，一个从五类异构源构建协议无关结构化知识中枢、并利用结构化 RAG 引导种子生成的系统。其核心洞察在于：协议知识本质上具备结构化特征，可统一建模为六元组知识原子，从而支撑（i）带显式校验的 fail-closed 抽取、（ii）无需向量索引的结构化（图原生）检索、以及（iii）每条种子均可溯源至具体证据的可追溯生成。")
para(doc, "本文的主要贡献如下：", bold=True)
bullet(doc, "提出一个协议无关的结构化知识中枢，采用三层架构（知识原子、每协议 Profile、多源映射），将协议知识与其具体实例解耦，使得支持一个新协议只需新增一个 Profile JSON 文件。")
bullet(doc, "实现对五类异构源（RFC、专家标注、漏洞、流量、源码）的统一结构化抽取，在 RTSP 上共产出 783 条知识原子，且 fail-closed 校验零失败。")
bullet(doc, "设计一条面向种子生成的结构化 RAG 消费通路：按方面（aspect）对知识原子分桶、检索 k 跳子图，并通过 ReAct 自校正循环迭代精化种子。")
bullet(doc, "[在 RTSP 服务器上验证 ProtoRAG 生成种子在状态覆盖、分支覆盖与漏洞发现等方面的有效性——待补充。]")

# ---- 2. 背景与动机 ----
h(doc, "2  背景与动机", 1)
h(doc, "2.1  有状态协议模糊测试", 2)
para(doc, "有状态协议模糊测试将目标协议建模为有限状态机，并生成能够穿越合法转移的消息序列。状态机既可从规范中静态导出，也可从观测流量中动态推断。AFLNet [1] 在模糊测试过程中根据服务器响应动态推导状态机，并据此引导变异。作为编码代表性状态路径的初始种子语料库，在早期探索效率上起着决定性作用。")
h(doc, "2.2  基于 LLM 的种子生成及其局限", 2)
para(doc, "ChatAFL [2] 通过 LLM 利用其对协议语法与语义的内隐知识，为 AFLNet 补充协议感知的种子与变异；MultiFuzz [3] 则将模糊测试过程分解为多个专用智能体，并在 RFC 文档上进行稠密检索。这些系统虽然提升了覆盖能力，却共享同一弱点：协议知识要么内隐于 LLM，要么以碎片化文本片段的形式被检索，缺乏结构化、可溯源、协议无关的统一表示。")
h(doc, "2.3  为何需要一个结构化知识中枢", 2)
para(doc, "协议知识天然具有结构：方法具备必需头部字段，头部字段具备取值池与语法，状态之间由方法触发的转移相互连接，状态码具有语义，漏洞则针对特定的方法与字段。一个显式建模这些关系的结构化中枢，能够支撑（i）面向特定种子的相关知识精确检索、（ii）能够捕获抽取缺漏的 fail-closed 校验、以及（iii）每条生成种子到其支撑证据的可追溯性。")

# ---- 3. 系统设计 ----
h(doc, "3  系统设计", 1)
h(doc, "3.1  总体架构", 2)
para(doc, "ProtoRAG 由两个阶段构成：知识中枢构建（离线）与 RAG 驱动的种子生成（在线）。知识中枢采用三层架构构建：离线阶段将五类异构源的结构化知识抽取入中枢；在线阶段消费中枢，引导 LLM 生成种子。")
h(doc, "3.2  第 0 层：协议无关的知识原子", 2)
para(doc, "知识的最小单位为六元组原子（Subject、Aspect、Condition、Value、Epistemic、Evidence）。Subject 表示协议对象（method、header、state、status、relation、protocol、actor），并支持递归嵌套（例如转移关系携带 source/target/method 子主体）。Aspect 表示主体的属性（existence、syntax、definition、value_enum、security_property、target_state、occurrence 等）。Value 具有十二种类型（scalar、enum、set、sequence、range、pattern、struct、ref、observation、binary、union、text）。Epistemic 表示知识的认知状态（must、normative_unspecified、descriptive、observed），并携带权威等级（authority rank）。Evidence 记录来源出处（source_type、source_id、document、locator、quote）。原子身份采用内容哈希，使来自多源的同一条知识得以确定性地归并。")
h(doc, "3.3  第 1 层：每协议 Profile", 2)
para(doc, "每个协议拥有一个封闭的 Profile，注册三套词汇表：subject_type_registry、aspect_registry 与 epistemic_type_registry。Profile 是封闭声明：对任何未注册 type、aspect 或 epistemic 类型的引用，将触发硬错误（fail-closed），而非被静默忽略。支持新协议仅需新增一个 Profile JSON 文件，核心代码保持不变。")
h(doc, "3.4  第 2 层：多源映射", 2)
para(doc, "五类源各自以适配其特性的策略映射入中枢。RFC 规范与实现源码先被抽取为规范（norm）再原生映射（转移映射为 relation+target_state、字段映射为 header+syntax/definition、结果映射为 status+definition、方法映射为 method+definition）。专家标注与漏洞报告本身已结构化，直接映射（“甲方案”路径），无需中间层。真实流量在映射前按 norm 身份去重，采用 observed 认知状态，并在 evidence 的 quote 中记录捕获次数统计。")
h(doc, "3.5  结构化 RAG 驱动的种子生成", 2)
para(doc, "为生成种子，ProtoRAG 首先将知识原子按方面（aspect）分桶为种子生成知识（方法白名单、状态转移、必需头部字段、头部字段取值池、安全关切）。对较小协议，直接对全部原子分桶；对更大规模协议，则从目标方法/状态出发检索 k 跳子图（图原生检索，无需向量索引）。分桶后的知识被渲染为提示词，LLM 生成候选种子，随后由轻量校验器检查方法白名单、必需头部字段与状态转移。非法种子触发 ReAct 自校正循环，将校验错误反馈回提示词以重新生成（迭代轮数有上界）。")

# ---- 4. 实现 ----
h(doc, "4  实现", 1)
para(doc, "ProtoRAG 以 Python 实现。知识中枢（core/fused）提供原子模型、三套注册表、fail-closed 校验器与逐源映射器。中枢构建入口（scripts/build_hub.py）支持 --list-sources 识别五类源、--sources 选择性抽取。RAG 消费通路（core/fused/downstream/rag_seedgen.py）提供分桶、子图检索、提示词渲染、生成、校验与 ReAct 循环，并通过 seedcorpus_to_raw 写出兼容 ProFuzzBench 的 .raw 种子。Stub LLM 客户端支撑离线测试，DeepSeek 客户端（OpenAI 兼容）提供生产环境的生成能力。测试套件包含 120 个测试用例，覆盖原子模型、注册表、映射器与种子生成通路，全部通过。")

# ---- 5. 评估 ----
h(doc, "5  评估", 1)
para(doc, "[评估部分待实验完成后补充。以下各小节给出拟定的实验设置、研究问题与结果占位。]")
h(doc, "5.1  实验设置", 2)
para(doc, "[待填：说明目标 RTSP 服务器（如 Live555、MERCURY 网络摄像头）、基线模糊测试器（AFLNet、ChatAFL、NSFuzz、MultiFuzz）、评估指标（状态覆盖、分支覆盖、漏洞数量）、实验环境（CPU/GPU、操作系统、时间预算）以及种子语料库配置。]")
h(doc, "5.2  研究问题", 2)
bullet(doc, "RQ1（知识抽取）：ProtoRAG 从每类源抽取多少条有效知识原子？fail-closed 校验失败率如何？")
bullet(doc, "RQ2（种子质量）：以 ProtoRAG 生成种子作为初始语料库，其状态/分支覆盖是否高于基线？")
bullet(doc, "RQ3（消融）：五类源各自以及 ReAct 精化循环对种子质量的贡献如何？")
bullet(doc, "RQ4（可泛化性）：支持一个新协议所需的工作量如何（仅需 Profile JSON，还是需要改动代码）？")
h(doc, "5.3  结果", 2)
para(doc, "[待填：实验完成后插入以下表格/图]")
table(doc, ["指标", "AFLNet", "ChatAFL", "MultiFuzz", "ProtoRAG"],
      [["状态覆盖", "[待填]", "[待填]", "[待填]", "[待填]"],
       ["分支覆盖", "[待填]", "[待填]", "[待填]", "[待填]"],
       ["发现漏洞数", "[待填]", "[待填]", "[待填]", "[待填]"],
       ["种子有效率", "[待填]", "[待填]", "[待填]", "[待填]"]])
para(doc, "[待填：插入逐源贡献与 ReAct 循环贡献的消融表；插入新协议支持工作量的可泛化性表。]")

# ---- 6. 相关工作 ----
h(doc, "6  相关工作", 1)
bullet(doc, "有状态协议模糊测试：AFLNet [1] 根据服务器响应推导状态机并引导变异；NSFuzz 等进一步改进状态选择与种子调度。")
bullet(doc, "基于 LLM 的协议模糊测试：ChatAFL [2] 以 LLM 生成的种子与变异增强 AFLNet；MultiFuzz [3] 将模糊测试分解为在 RFC 上进行稠密检索的多个智能体。")
bullet(doc, "面向协议的 FSM 抽取与 RAG：RAG-ReAct [5] 利用检索与思维链进行协议状态机推断与种子生成；SpecGPT 与 FlowFSM 通过提示链与集成投票从规范中抽取状态机。")
bullet(doc, "GraphRAG 与智能体式 RAG：GraphRAG [4] 检索结构化子图以获得 token 高效、可解释的生成；Self-RAG 与 Corrective RAG 引入自校正循环，迭代评估并精化检索与生成。")
para(doc, "ProtoRAG 与此前工作的区别在于：将五类异构协议知识源统一为协议无关的结构化中枢并施加 fail-closed 校验，且通过结构化（图原生）RAG 结合 ReAct 精化循环来消费该中枢。")

# ---- 7. 讨论与局限 ----
h(doc, "7  讨论与局限", 1)
bullet(doc, "评估范围：当前抽取在 RTSP 上实例化；对其他协议的可泛化性由设计论证，未来工作将进行经验验证。")
bullet(doc, "多源冲突：当同一知识原子被多源断言时，当前通路取首条 claim；权威排序共识等原则性消解策略留待未来工作。")
bullet(doc, "LLM 依赖：种子生成质量依赖底层 LLM；结构化中枢为生成提供锚定但无法完全消除 LLM 幻觉，ReAct 循环只能缓解而非根除。")

# ---- 8. 结论 ----
h(doc, "8  结论", 1)
para(doc, "本文提出了 ProtoRAG，一个从五类异构源构建协议无关结构化知识中枢、并通过结构化 RAG 消费该中枢以引导 LLM 生成有状态协议模糊测试初始种子的系统。三层中枢架构、fail-closed 校验与 ReAct 精化循环共同提供了可溯源、可泛化、高质量的初始种子。[后续计划完成评估，以验证其相对最先进模糊测试器的有效性。]")

# ---- 参考文献 ----
h(doc, "参考文献", 1)
refs = [
    "[1] Pham, V.-T., Böhme, M., and Roychoudhury, A. AFLNet: A Greybox Fuzzer for Network Protocols. "
    "In IEEE International Conference on Software Testing (ICST), 2020.",
    "[2] Meng, R., et al. ChatAFL: Large Language Model-Based Protocol Fuzzing. In Network and Distributed "
    "System Security Symposium (NDSS), 2024.",
    "[3] Maklad, Y., Wael, F., Hamdi, A., et al. MultiFuzz: A Dense Retrieval-Based Multi-Agent System for "
    "Network Protocol Fuzzing. In IEEE/ACS AICCSA, 2025.",
    "[4] Zhang, Q., Chen, S., Bei, Y., et al. A Survey of Graph Retrieval-Augmented Generation for "
    "Customized Large Language Models. arXiv:2501.13958, 2025.",
    "[5] Maklad, Y., Wael, F., Elsersy, W., and Hamdi, A. Retrieval Augmented Generation Based LLM "
    "Evaluation for Protocol State Machine Inference with Chain-of-Thought Reasoning. arXiv:2502.15727, "
    "2025.",
]
for r_ in refs:
    para(doc, r_)

out_path = OUT + r"\ProtoRAG-论文稿-中文.docx"
doc.save(out_path)
print("中文论文已生成到", out_path)
