"""conftest — shared pytest root for ProtoKG tests.

2026-10-09 清理：v1 代码已退役，原 _ensure_registry_builtins（依赖 v1 的
core.classifier / core.extractors / core.registry）与 kb_driven_spec_graph
（依赖 v1 的 core.spec_graph）均已删除。现仅保留 sys.path 设置，让
tests/<层>/ 能 `import core.fused.*`。
"""
import pathlib
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


#: ★ 2026-11-18（R24C）：★ **断言所需源**与**中枢实际源集合**的映射
#:
#: ★ 为什么：★ 有些断言**显式要求**中枢含某个源（★ 如 ``source`` 源）；
#: ★   CI 的中枢只建**确定性四源**（★ rfc / traffic / expert_note / vuln），
#: ★   **不带 source 源**（★ source 走 AutoSeeder 的 LLM 路径 ⇒ CI 无凭据）
#: ★   ⇒ 这些断言在 CI 上**必然失败**，★ 但那是**源集合不同**，★ 不是代码回归
#: ★   ⇒ 与既有的 E7 规则（★ 协议不匹配 ⇒ skip）同类。
#:
#: ★ 判定：★ 断言的源码里显式出现该源名（★ 如 ``"source"``）且中枢不含该源 ⇒ skip。
#:
#: ★ ★ 覆盖边界必须如实披露：★ 这些测试在公开 CI 上是 **not_run**，★ 不是 passed。
REQUIRED_SOURCE_BY_ASSERTION = {
    "test_load_fact_views_has_all_five_sources": "source",
    "test_all_sources_state_machines": "source",
}


def _current_hub_sources(root: Path) -> set:
    """读当前中枢的源集合（★ 空集 = 未构建）。"""
    import json
    mf = root / "derived" / "hub" / "sources.json"
    if not mf.is_file():
        return set()
    try:
        _d = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    _out = set()
    for _k in ("sources", "source_set"):
        _v = _d.get(_k)
        if isinstance(_v, list):
            _out |= {str(x).strip().lower() for x in _v}
    if not _out:
        # ★ 兜底：★ 从中枢的 per_source 目录反推
        _ps = root / "derived" / "per_source"
        for _p in _ps.glob("*/facts/*.jsonl"):
            _out.add(_p.parent.parent.name)
    return _out


#: ★ 2026-11-18（R24C）：**依赖历史实验产物**的审计测试模块
#:
#: ★ 为什么：这些用例审计的是**历史实验批次**的冻结产物
#:   （``guard/_out/_n1c_v2/r2``、``r3``、``r10``、``r11``、``r12`` …）
#:   ⇒ 该目录被 ``.gitignore`` 排除 ⇒ **干净 checkout 里不存在**
#:   ⇒ 它们在**模块顶层**就访问这些路径 ⇒ **收集期 import/读取即失败**
#:   ⇒ 计入 errors 集合 ⇒ 护栏判红。
#:
#: ★ 为什么不能入库：★ 那些产物含**人工审核材料与冻结 Gold**
#:   ⇒ 不适合推送公开仓库（★ 且体积大）。
#:
#: ★ 正确做法（★ 与既有的两条 skip 规则同范式）：
#:   缺历史产物 ⇒ **skip**（★ 不计入失败集合，★ 也不计入通过）
#:   ⇒ 护栏判据仍只针对**真实失败**。
#:   ⇒ **★ 这些测试在公开 CI 上是 not_run，★ 不是 passed**
#:   ⇒ 报告必须如实披露该覆盖缺口。
#:
#: ★ 判据：★ 模块源码里出现 ``guard/_out/_n1c_v2/<批次>`` 形式的路径常量
#:   ⇒ 该模块归入本类；★ 目录存在 ⇒ 不 skip（★ 本地照常跑）。
#: ★ 判定依据：★ 源码里出现 ``guard/_out/`` 形式的路径（★ 指向历史实验产物目录）
#:
#: ★ 为什么用**前缀**而不是逐个列举批次目录：★ 实测（2026-11-18）逐个列举会漏判
#: ★ 二十余个模块（★ 它们的路径写法与列举形式不同，★ 但同样指向 gitignored 目录）
#: ★ ⇒ 漏判的模块在干净 checkout 上会因 FileNotFoundError 计入失败集合。
HISTORICAL_ARTIFACT_MARKERS = (
    "guard/_out/",          # ★ 任何指向 guard/_out 的路径
)


def _needs_historical_artifacts(path: Path) -> bool:
    """★ 该模块是否依赖历史实验产物（★ 且产物当前不存在）。"""
    try:
        _src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for _m in HISTORICAL_ARTIFACT_MARKERS:
        if _m in _src:
            # ★ 提取模块里出现的**具体** guard/_out 子目录，★ 逐个检查是否存在
            _found = set()
            import re as _re
            for _hit in _re.findall(r"guard/_out/[A-Za-z0-9_./\-]+", _src):
                _found.add(_hit.rstrip("/\"'"))
            if _found and not any((ROOT / _d).exists() for _d in _found):
                return True
            if not _found and not (ROOT / "guard/_out").exists():
                return True
    return False


#: ★ R24C：★ **收集前**排除依赖历史实验产物的模块。
#:
#: ★ 为什么不能用 ``pytest_collection_modifyitems``：★ 该钩子在**模块导入之后**
#:   才运行；★ 而这些模块在**模块顶层**就读取历史产物路径 ⇒ 收集期已崩
#:   ⇒ 加 skip marker 也来不及。
#: ★ ⇒ 必须用 ``pytest_ignore_collect``（★ 导入前）。
#:
#: ★ 语义：★ 排除**不是** skip，★ 因此 pytest 会把它计入 **not_run** 而非 passed；
#: ★ ★ 护栏的 failed/errors 集合不含它们（★ 它们根本没被收集）。
#: ★ ★ **★ 报告必须如实披露：★ 这些测试在公开 CI 上是 not_run。**
_HIST_EXCLUDE_CACHE = {}


def pytest_ignore_collect(collection_path, config):
    """★ 收集前排除依赖历史实验产物的测试模块（★ 干净 checkout 无产物）。"""
    try:
        _p = pathlib.Path(str(collection_path))
    except (TypeError, ValueError):
        return None
    if _p.suffix != ".py":
        return None
    _key = str(_p)
    if _key not in _HIST_EXCLUDE_CACHE:
        _HIST_EXCLUDE_CACHE[_key] = _needs_historical_artifacts(_p)
    if _HIST_EXCLUDE_CACHE[_key]:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    """① 无 ``DEEPSEEK_API_KEY`` ⇒ 跳过 LLM 集成测试（而不是让它们失败）。
    ② ★ **中枢协议不匹配的协议相关断言 ⇒ skip**（E7）。
    ③ ★ **依赖历史实验产物且产物缺失 ⇒ skip**（★ R24C；★ not_run 而非 passed）。
    """
    import os
    hub_proto = _current_hub_protocol(ROOT).lower()
    hub_sources = _current_hub_sources(ROOT)
    skip_llm = pytest.mark.skip(reason="需要 DEEPSEEK_API_KEY（LLM 抽取通道）")
    skip_proto = pytest.mark.skip(
        reason=f"中枢协议不是本断言所属协议（当前 {hub_proto or '未构建'}）")
    skip_hist = pytest.mark.skip(
        reason="依赖历史实验产物（★ guard/_out 下的历史批次，★ 干净 checkout 无）"
               "⇒ not_run，★ 不是 passed")
    _hist_cache = {}
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
        # ★ R24C：依赖历史实验产物且缺失 ⇒ skip（not_run）
        _key = str(item.path)
        if _key not in _hist_cache:
            _hist_cache[_key] = _needs_historical_artifacts(item.path)
        if _hist_cache[_key]:
            item.add_marker(skip_hist)
            continue
        # ★ R24C：断言所需源不在中枢源集合 ⇒ skip（not_run）
        _node = item.name
        _need_src = REQUIRED_SOURCE_BY_ASSERTION.get(_node)
        if _need_src and hub_sources and _need_src not in hub_sources:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"断言需要中枢含 {_need_src} 源，"
                           f"当前中枢源集合为 {sorted(hub_sources)}"))
