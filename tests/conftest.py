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


#: ★ 2026-11-12（E7）：**协议相关断言**的协议名
#:
#: ★ 为什么：中枢**一次只有一个协议**（``derived/hub/sources.json`` 的 protocol）
#:   ⇒ 有些断言读的是**特定协议**的数据（如 smtp 的字典、sip 的必填头、
#:   某协议的图）⇒ 中枢不是那个协议时 ⇒ 断言**必然失败** ⇒ 那是
#:   **数据状态**，不是**代码回归** ⇒ ⇒ 混进护栏的失败集合 ⇒ 每次换协议
#:   都要重新标定基线 ⇒ ⇒ 不可持续。
#:
#: ★ 做法：断言的 nodeid 里**含协议名** ⇒ 且中枢协议 ≠ 该协议 ⇒ **skip**
#:   ⇒ skip 不计入失败集合 ⇒ ⇒ 护栏在**任意协议的中枢下都成立**
#:   ⇒ ⇒ 「测什么建什么」与护栏**不再冲突**。
#:
#: ★ 判据：**nodeid 含协议名（小写不敏感）** ⇒ 归到该协议
PROTO_NAMES = ("rtsp", "sip", "smtp", "dhcpv4")


def _current_hub_protocol(root: Path) -> str:
    """读当前中枢的协议名（``derived/hub/sources.json``）；读不到 ⇒ 空串。"""
    import json
    mf = root / "derived" / "hub" / "sources.json"
    if not mf.is_file():
        return ""
    try:
        return str(json.loads(mf.read_text(encoding="utf-8")).get("protocol") or "")
    except (OSError, ValueError):
        return ""


def pytest_collection_modifyitems(config, items):
    """① 无 ``DEEPSEEK_API_KEY`` ⇒ 跳过 LLM 集成测试（而不是让它们失败）。
    ② ★ **中枢协议不匹配的协议相关断言 ⇒ skip**（E7）。
    """
    import os
    hub_proto = _current_hub_protocol(ROOT).lower()
    skip_llm = pytest.mark.skip(reason="需要 DEEPSEEK_API_KEY（LLM 抽取通道）")
    skip_proto = pytest.mark.skip(
        reason=f"中枢协议不是本断言所属协议（当前 {hub_proto or '未构建'}）")
    for item in items:
        try:
            rel = str(item.path.relative_to(config.rootpath)).replace("\\", "/")
        except (ValueError, AttributeError):
            rel = ""
        if not os.environ.get("DEEPSEEK_API_KEY") and rel in LLM_MODULES:
            item.add_marker(skip_llm)
        # ★ E7：协议相关断言 ⇒ 中枢协议不匹配 ⇒ skip
        if hub_proto:
            node = item.nodeid.lower()
            for _p in PROTO_NAMES:
                if _p in node and _p != hub_proto:
                    item.add_marker(skip_proto)
                    break
