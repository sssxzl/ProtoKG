"""conftest — shared pytest root for ProtoKG tests.

2026-10-09 清理：v1 代码已退役，原 _ensure_registry_builtins（依赖 v1 的
core.classifier / core.extractors / core.registry）与 kb_driven_spec_graph
（依赖 v1 的 core.spec_graph）均已删除。现仅保留 sys.path 设置，让
tests/<层>/ 能 `import core.fused.*`。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


#: ★ 需要 LLM 抽取通道的测试模块（**无 key 时 skip 而不是 fail**）
#:
#: ★ 为什么：这些用例会**内部调用 LLM 抽取**（rfc 的状态机 / 方法集 / 规范值…）
#:   ⇒ 无 ``DEEPSEEK_API_KEY`` 时必然抛 ``ValueError`` ⇒ 计入失败集合
#:   ⇒ 造成「**本地（有 key）11 条 / CI（无 key）39 条**」两套基线 ⇒ 护栏两边都判红。
#: ⇒ 正确做法：**分类**（LLM 集成测试）⇒ 无 key ⇒ **skip**（不计入失败）
#:   ⇒ 有 key ⇒ 正常跑（本地覆盖不丢）⇒ **本地与 CI 基线一致**。
LLM_MODULES = {
    "tests/extraction/test_batch3_message_list_and_backfill.py",
    "tests/extraction/test_multifile_and_table_rows.py",
    "tests/extraction/test_norm_outcome_content.py",
    "tests/extraction/test_rfc_channel_e_and_llm_transitions.py",
    "tests/extraction/test_rfc_extractor_a1.py",
    "tests/extraction/test_rfc_extractor_abnf.py",
    "tests/extraction/test_rfc_extractor_p1_fixes.py",
    "tests/extraction/test_rfc_quality_gate_toc.py",
    "tests/hub/test_build_hub_gate_order.py",
    "tests/hub/test_single_protocol_single_source.py",
}


def pytest_collection_modifyitems(config, items):
    """无 ``DEEPSEEK_API_KEY`` ⇒ 跳过 LLM 集成测试（而不是让它们失败）。"""
    import os
    if os.environ.get("DEEPSEEK_API_KEY"):
        return
    skip_llm = pytest.mark.skip(reason="需要 DEEPSEEK_API_KEY（LLM 抽取通道）")
    for item in items:
        try:
            rel = str(item.path.relative_to(config.rootpath)).replace("\\", "/")
        except (ValueError, AttributeError):
            continue
        if rel in LLM_MODULES:
            item.add_marker(skip_llm)
