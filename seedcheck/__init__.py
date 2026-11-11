# -*- coding: utf-8 -*-
"""seedcheck —— **种子校验层**（⑥）：**只**检查生成种子的质量。

★ 与代码审查的分工（刻意分开）
  · ``guard/``    ⇒ **代码审查**：查代码 / 契约 / 文档（改代码后跑）
  · ``seedcheck/`` ⇒ **产物审查**：查种子质量（生成种子后跑）
  ⇒ 两者互不依赖；``seedcheck`` **不 import** ``core.fused.downstream``
    （护栏会检查这条 ⇒ 防止反向耦合）。

★ 核心原则
  1. **校验 ≠ 过滤**：只有 V1（格式必假）阻断；V2~V4（协议越界）只**打标**
     ⇒ 因为「违反协议」恰恰是 fuzzing 最有价值的输入面。
  2. **判据只来自中枢**：校验器自己一条硬编码都不该有 ⇒ 协议知识一变，口径自动跟着变。
  3. **可追溯**：每条违规都带 ``evidence``（判据来源）。

★ 分层
  · V1 格式必假（协议无关最小集）        ⇒ 🔴 阻断
  · V2 知识一致（中枢 6 维度）            ⇒ 🟢 打标
  · V3 环境适配（目标环境可播集）          ⇒ 🟢 打标
  · V4 状态机边（target_state）           ⇒ 🟢 打标
  · V5 结构多样性（本次运行统计 + 阈值）   ⇒ 🟡 告警
  · V6 语义合理性（LLM，只报告）          ⇒ ⚪ 只报告

★ 用法：``python seedcheck/run.py --protocol rtsp --seed-dir derived/seeds/rtsp/<ts>``
"""
from __future__ import annotations

__all__ = ["model", "knowledge", "v1_format", "v2_knowledge", "v3_env",
           "v4_fsm", "v5_diversity", "v6_llm"]
