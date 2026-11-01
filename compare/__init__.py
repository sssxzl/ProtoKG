# -*- coding: utf-8 -*-
"""compare —— 三路知识表示消融实验（A/B/C）。

    A 路 ProtoRAG（可溯源知识表示）：沿用 scripts/run_seedgen_e2e.py，不在此实现。
    B 路 浅层知识库（PSG/RTSGen 式）：shallow_kb.py
    C 路 向量 RAG（MultiFuzz 式）：vector_rag.py

    三路共用：同一份五源知识 + 同一个 LLM(DeepSeek) + 同一 fuzz 评测。
    唯一变量 = 知识表示层。
"""
