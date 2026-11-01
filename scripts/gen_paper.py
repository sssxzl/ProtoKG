# -*- coding: utf-8 -*-
"""生成 ProtoRAG 顶会论文稿（英文，实验留空白）。"""
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = r"E:\科研\想法idea\rag-chatafl思路"


def set_cn(run, size=None, bold=None, italic=None):
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic


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


def para(doc, text, bold=False, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    set_cn(r, bold=bold, italic=italic)
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


doc = new_doc()

# ---- Title ----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("ProtoRAG: Structured Protocol Knowledge Extraction and RAG-Driven Seed Generation "
              "for Stateful Protocol Fuzzing")
set_cn(r, 16, True)

# ---- Abstract ----
h(doc, "Abstract", 1)
para(doc, "Stateful protocol fuzzing critically depends on high-quality initial seeds to guide the "
          "exploration of the protocol state space. Existing approaches either rely on LLM-implicit "
          "protocol knowledge (e.g., ChatAFL) or infer the state machine at runtime (e.g., AFLNet), "
          "both of which lack explicit, traceable protocol knowledge and are hard to generalize across "
          "protocols. We present ProtoRAG, a system that constructs a protocol-agnostic structured "
          "knowledge hub from five heterogeneous knowledge sources\u2014RFC specifications, expert "
          "annotations, historical vulnerabilities, real-world traffic, and protocol implementation "
          "source code\u2014and leverages retrieval-augmented generation (RAG) to guide an LLM in "
          "generating initial seeds. The hub adopts a three-layer architecture: (Layer 0) a "
          "protocol-agnostic knowledge-atom model that represents each piece of knowledge as a "
          "six-tuple (Subject, Aspect, Condition, Value, Epistemic, Evidence); (Layer 1) a per-protocol "
          "closed profile that registers the legal vocabulary (subject types, aspects, and epistemic "
          "types) with fail-closed validation; and (Layer 2) per-source mapping that transforms each of "
          "the five sources into knowledge atoms. For the RTSP protocol, ProtoRAG extracts 783 knowledge "
          "atoms across the five sources with zero validation failures. On top of the hub, we design a "
          "structured RAG consumption pipeline that buckets knowledge atoms by aspect (or retrieves a "
          "k-hop subgraph for larger protocols), renders a seed-generation prompt, and iteratively "
          "refines seeds via a ReAct self-correction loop. [Evaluation results to be completed after "
          "experiments.]")

# ---- 1. Introduction ----
h(doc, "1  Introduction", 1)
para(doc, "Network protocol fuzzing is a foundational technique for discovering vulnerabilities in "
          "network services. Stateful protocol fuzzing, as pioneered by AFLNet [1], models the protocol "
          "as a finite-state machine (FSM) and generates message sequences that traverse valid state "
          "paths, enabling deep exploration of protocol logic. The quality of the initial seed corpus "
          "directly determines how effectively the fuzzer explores the state space: seeds that violate "
          "protocol constraints are rejected early, while seeds that cover valid state transitions guide "
          "the fuzzer toward deeper logic.")
para(doc, "Recent work has shown that large language models (LLMs) can generate protocol-aware seeds by "
          "leveraging their implicit knowledge of protocol specifications (e.g., ChatAFL [2], MultiFuzz "
          "[3]). However, LLM-implicit knowledge suffers from three fundamental limitations. First, it is "
          "not traceable: the rationale behind a generated seed cannot be traced back to a specific "
          "specification clause, vulnerability, or observed behavior. Second, it is not explicit: the "
          "knowledge is buried in model weights and cannot be inspected, corrected, or extended without "
          "retraining. Third, it is not generalizable: adapting to a new protocol requires re-prompting "
          "or fine-tuning rather than adding structured knowledge.")
para(doc, "Retrieval-augmented generation (RAG) addresses these limitations by grounding LLM generation "
          "in an external knowledge base. However, existing RAG systems for protocol fuzzing retrieve "
          "unstructured text chunks from RFC documents, which suffer from fragmentation, loss of "
          "relational structure, and token inefficiency. Graph-based RAG (GraphRAG) [4] improves upon "
          "flat text retrieval by explicitly modeling entities and relations, but existing instantiations "
          "are not specialized for protocol knowledge, which is naturally structured (methods, headers, "
          "state transitions, status codes, security properties) and spans heterogeneous sources.")
para(doc, "In this paper, we present ProtoRAG, a system that constructs a protocol-agnostic structured "
          "knowledge hub from five heterogeneous sources and uses structured RAG to guide seed generation. "
          "Our key insight is that protocol knowledge is inherently structured and can be modeled as a "
          "uniform six-tuple knowledge atom, which enables (i) fail-closed extraction with explicit "
          "validation, (ii) structured (graph-native) retrieval without vector indexing, and (iii) "
          "traceable seed generation where every seed is grounded in specific evidence.")
para(doc, "We make the following contributions:", bold=True)
bullet(doc, "A protocol-agnostic structured knowledge hub with a three-layer architecture (knowledge atoms, "
            "per-protocol profile, multi-source mapping) that separates protocol knowledge from protocol "
            "instances, enabling a new protocol to be supported by adding only a profile JSON.")
bullet(doc, "Unified structured extraction from five heterogeneous sources (RFC, expert notes, "
            "vulnerabilities, traffic, source code), producing 783 knowledge atoms for RTSP with zero "
            "fail-closed validation failures.")
bullet(doc, "A structured RAG consumption pipeline for seed generation that buckets knowledge atoms by "
            "aspect, retrieves k-hop subgraphs, and iteratively refines seeds through a ReAct "
            "self-correction loop.")
bullet(doc, "[An evaluation on RTSP servers demonstrating the effectiveness of ProtoRAG-generated seeds "
            "in terms of state coverage, branch coverage, and bug finding \u2014 to be completed.]")

# ---- 2. Background and Motivation ----
h(doc, "2  Background and Motivation", 1)
h(doc, "2.1  Stateful Protocol Fuzzing", 2)
para(doc, "Stateful protocol fuzzing models the target protocol as an FSM and generates message sequences "
          "that traverse valid transitions. The FSM can be derived statically from specifications or "
          "dynamically from observed traffic. AFLNet [1] derives the FSM from server responses during "
          "fuzzing and uses it to guide mutation. The initial seed corpus, which encodes representative "
          "state paths, plays a decisive role in early exploration efficiency.")
h(doc, "2.2  LLM-Based Seed Generation and Its Limits", 2)
para(doc, "ChatAFL [2] augments AFLNet with an LLM that generates protocol-aware seeds and mutations using "
          "its implicit knowledge of protocol syntax and semantics. MultiFuzz [3] further decomposes the "
          "fuzzing process into specialized agents with dense retrieval over RFC documents. While these "
          "systems improve coverage, they share a common weakness: protocol knowledge is either implicit "
          "in the LLM or retrieved as fragmented text chunks, lacking a structured, traceable, and "
          "protocol-agnostic representation.")
h(doc, "2.3  Why a Structured Knowledge Hub", 2)
para(doc, "Protocol knowledge is naturally structured: methods have required headers, headers have value "
          "pools and syntax, states are connected by method-triggered transitions, status codes have "
          "semantics, and vulnerabilities target specific methods and fields. A structured hub that "
          "explicitly models these relations enables (i) precise retrieval of relevant knowledge for a "
          "given seed, (ii) fail-closed validation that catches extraction gaps, and (iii) traceability "
          "of every generated seed to its supporting evidence.")

# ---- 3. System Design ----
h(doc, "3  System Design", 1)
h(doc, "3.1  Overview", 2)
para(doc, "ProtoRAG consists of two stages: knowledge hub construction (offline) and RAG-driven seed "
          "generation (online). The knowledge hub is built in a three-layer architecture. The offline "
          "stage extracts structured knowledge from five heterogeneous sources into the hub. The online "
          "stage consumes the hub to guide an LLM in generating seeds.")
h(doc, "3.2  Layer 0: Protocol-Agnostic Knowledge Atoms", 2)
para(doc, "The minimal unit of knowledge is a six-tuple atom (Subject, Aspect, Condition, Value, "
          "Epistemic, Evidence). Subject denotes the protocol object (method, header, state, status, "
          "relation, protocol, actor) and supports recursive nesting (e.g., a transition relation carries "
          "source/target/method sub-subjects). Aspect denotes a property of the subject (existence, "
          "syntax, definition, value_enum, security_property, target_state, etc.). Value has twelve types "
          "(scalar, enum, set, sequence, range, pattern, struct, ref, observation, binary, union, text). "
          "Epistemic denotes the epistemic status of the knowledge (must, normative_unspecified, "
          "descriptive, observed) with an authority rank. Evidence records provenance (source_type, "
          "source_id, document, locator, quote). Atom identity is content-hashed so that the same knowledge "
          "from multiple sources can be merged deterministically.")
h(doc, "3.3  Layer 1: Per-Protocol Profile", 2)
para(doc, "Each protocol has a closed profile that registers three vocabularies: subject_type_registry, "
          "aspect_registry, and epistemic_type_registry. The profile is a closed declaration: any reference "
          "to an unregistered type, aspect, or epistemic type triggers a hard error (fail-closed) rather "
          "than being silently ignored. Supporting a new protocol requires only a new profile JSON, "
          "leaving the core code unchanged.")
h(doc, "3.4  Layer 2: Multi-Source Mapping", 2)
para(doc, "Each of the five sources is mapped into the hub with a source-appropriate strategy. RFC "
          "specifications and implementation source code are first extracted into norms and then mapped "
          "natively (transitions to relation+target_state, fields to header+syntax/definition, outcomes "
          "to status+definition, methods to method+definition). Expert annotations and vulnerability "
          "reports are already structured and are mapped directly (the \u201cPlan A\u201d path) without an "
          "intermediate layer. Real traffic is deduplicated by norm identity before mapping, with observed "
          "epistemic status and capture-count statistics in the evidence quote.")
h(doc, "3.5  Structured RAG-Driven Seed Generation", 2)
para(doc, "To generate a seed, ProtoRAG first buckets the knowledge atoms by aspect into seed-generation "
          "knowledge (method whitelist, state transitions, required headers, header value pools, security "
          "concerns). For small protocols, all atoms are bucketed directly; for larger protocols, a "
          "k-hop subgraph is retrieved starting from the target methods/states (graph-native retrieval "
          "without vector indexing). The bucketed knowledge is rendered into a prompt, the LLM generates "
          "candidate seeds, and a lightweight validator checks method whitelist, required headers, and "
          "state transitions. Invalid seeds trigger a ReAct self-correction loop that feeds validation "
          "errors back into the prompt for regeneration (up to a bounded number of rounds).")

# ---- 4. Implementation ----
h(doc, "4  Implementation", 1)
para(doc, "ProtoRAG is implemented in Python. The knowledge hub (core/fused) provides the atom model, the "
          "three registries, the fail-closed validator, and per-source mappers. The hub build entry "
          "(scripts/build_hub.py) supports --list-sources to identify the five sources and --sources to "
          "selectively extract. The RAG consumption pipeline (core/fused/downstream/rag_seedgen.py) "
          "provides bucketing, subgraph retrieval, prompt rendering, generation, validation, and the "
          "ReAct loop, and writes ProFuzzBench-compatible .raw seeds via seedcorpus_to_raw. A stub LLM "
          "client enables offline testing, while a DeepSeek client (OpenAI-compatible) provides "
          "production generation. The test suite contains 120 tests covering the atom model, registries, "
          "mappers, and the seed-generation pipeline, all passing.")

# ---- 5. Evaluation ----
h(doc, "5  Evaluation", 1)
para(doc, "[Evaluation section to be completed after running experiments. The following subsections "
          "outline the planned experimental setup, research questions, and result placeholders.]")
h(doc, "5.1  Experimental Setup", 2)
para(doc, "[TODO: describe the target RTSP servers (e.g., Live555, MERCURY IP camera), the baseline "
          "fuzzers (AFLNet, ChatAFL, NSFuzz, MultiFuzz), the evaluation metrics (state coverage, branch "
          "coverage, bug count), the experimental environment (CPU/GPU, OS, time budget), and the seed "
          "corpus configuration.]")
h(doc, "5.2  Research Questions", 2)
bullet(doc, "RQ1 (Knowledge extraction): How many valid knowledge atoms does ProtoRAG extract per source, "
            "and what is the fail-closed validation failure rate?")
bullet(doc, "RQ2 (Seed quality): Do ProtoRAG-generated seeds achieve higher state/branch coverage than "
            "baselines when used as the initial corpus?")
bullet(doc, "RQ3 (Ablation): What is the contribution of each of the five sources and of the ReAct "
            "refinement loop to seed quality?")
bullet(doc, "RQ4 (Generalizability): How much effort is required to support a new protocol (profile JSON "
            "only vs. code changes)?")
h(doc, "5.3  Results", 2)
para(doc, "[TODO: insert the following tables/figures after experiments]")
table(doc, ["Metric", "AFLNet", "ChatAFL", "MultiFuzz", "ProtoRAG"],
      [["State coverage", "[TBD]", "[TBD]", "[TBD]", "[TBD]"],
       ["Branch coverage", "[TBD]", "[TBD]", "[TBD]", "[TBD]"],
       ["Bugs found", "[TBD]", "[TBD]", "[TBD]", "[TBD]"],
       ["Seed validity rate", "[TBD]", "[TBD]", "[TBD]", "[TBD]"]])
para(doc, "[TODO: insert ablation table for per-source contribution and ReAct loop contribution; "
          "insert generalizability table for new-protocol support effort.]")

# ---- 6. Related Work ----
h(doc, "6  Related Work", 1)
bullet(doc, "Stateful protocol fuzzing: AFLNet [1] derives the FSM from server responses and guides "
            "mutation; NSFuzz and others improve state selection and seed scheduling.")
bullet(doc, "LLM-based protocol fuzzing: ChatAFL [2] augments AFLNet with LLM-generated seeds and "
            "mutations; MultiFuzz [3] decomposes fuzzing into agents with dense retrieval over RFCs.")
bullet(doc, "FSM extraction and RAG for protocols: RAG-ReAct [5] uses retrieval and chain-of-thought for "
            "protocol FSM inference and seed generation; SpecGPT and FlowFSM extract FSMs from "
            "specifications with prompt chaining and ensemble voting.")
bullet(doc, "GraphRAG and agentic RAG: GraphRAG [4] retrieves structured subgraphs for token-efficient and "
            "interpretable generation; Self-RAG and Corrective RAG introduce self-correction loops that "
            "evaluate and refine retrieval/generation iteratively.")
para(doc, "ProtoRAG differs from prior work by unifying five heterogeneous protocol knowledge sources into "
          "a protocol-agnostic structured hub with fail-closed validation, and by consuming the hub "
          "through structured (graph-native) RAG with a ReAct refinement loop.")

# ---- 7. Discussion and Limitations ----
h(doc, "7  Discussion and Limitations", 1)
bullet(doc, "Scope of evaluation: the current extraction is instantiated on RTSP; generalizability to other "
            "protocols is argued by design and will be empirically validated in future work.")
bullet(doc, "Multi-source conflicts: the current pipeline takes the first claim when the same knowledge atom "
            "is asserted by multiple sources; a principled resolution policy (e.g., authority-ranked "
            "consensus) is left for future work.")
bullet(doc, "LLM dependency: seed generation quality depends on the underlying LLM; the structured hub "
            "grounds generation but does not eliminate LLM hallucination, which the ReAct loop mitigates "
            "rather than removes.")

# ---- 8. Conclusion ----
h(doc, "8  Conclusion", 1)
para(doc, "We presented ProtoRAG, a system that builds a protocol-agnostic structured knowledge hub from "
          "five heterogeneous sources and consumes it through structured RAG to guide LLM-based seed "
          "generation for stateful protocol fuzzing. The three-layer hub architecture, fail-closed "
          "validation, and ReAct refinement loop together provide traceable, generalizable, and "
          "high-quality initial seeds. [We plan to complete the evaluation to demonstrate its effectiveness "
          "against state-of-the-art fuzzers.]")

# ---- References ----
h(doc, "References", 1)
refs = [
    "[1] Pham, V.-T., B\u00f6hme, M., and Roychoudhury, A. AFLNet: A Greybox Fuzzer for Network Protocols. "
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

doc.save(OUT + r"\ProtoRAG-论文稿.docx")
print("论文已生成到", OUT)
