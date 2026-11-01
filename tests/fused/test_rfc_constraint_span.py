"""tests/fused/test_rfc_constraint_span.py —— B-3（约束候选带 span）+ B-4（norm_id 冲突修复）。

B-3 验收（对应 docs/rfc_source_bcd_roadmap.md §3.8 任务表）：
  ① 候选含 `span_start` / `span_end` / `section_path` / `spec_version`；
  ② **span 覆盖率 100%**，且每个 span 能在源文件里**逐字定位**
     （`raw[span_start:span_end] == candidate["text"]`）；
  ③ **TOC 污染实测归零** —— 用**独立**判据 `_independent_toc_lines`
     回查候选的来源行（**不复用** `_is_toc_line`：那会与被检查对象自证）；
  ④ `source` 格式统一为 `file:<name>#@<真实行号>` —— **两种 anchor 语义
     不再并存**（不再出现裸 `file:<name>`，也不出现 `#@abnf`）。

B-4 验收：
  ① 同字段多条约束 → `norm_id` 唯一（`dup_norm_ids == 0`）；
  ② 该场景下 `rfc_quality_report(...).passed == True`（不再阻断构建）；
  ③ `norm_id` **稳定可复现**：跨进程（不同 PYTHONHASHSEED）一致，
     且**不依赖 LLM 自由措辞**（`expected_behavior`）。
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

from core.fused.norm import constraint_identity_digest, map_norm_to_facts
from core.fused.rfc_extractor import (
    _independent_toc_lines,
    extract_constraint_candidates,
    extract_constraint_norms,
    rfc_quality_report,
)
from core.llm import StubLLMClient

PROTOCOLS = ("rtsp", "sip", "smtp")
ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 候选 `source` 的**唯一**形态：file:<name>#@<真实行号>
_RE_SOURCE = re.compile(r"^file:(?P<name>[^#]+)#@(?P<line>\d+)$")


# ===========================================================================
# B-3　约束候选带 span
# ===========================================================================

@pytest.fixture(scope="module")
def candidates() -> dict:
    """三协议的约束候选（模块级缓存 —— 抽取要读全文，重复调用很慢）。"""
    return {p: extract_constraint_candidates(p) for p in PROTOCOLS}


@pytest.fixture(scope="module")
def spec_texts() -> dict:
    """{protocol: {文件名: 原文}}"""
    out: dict = {}
    for p in PROTOCOLS:
        out[p] = {f.name: f.read_text(encoding="utf-8", errors="ignore")
                  for f in sorted((ROOT / "kb" / p / "spec").glob("*.txt"))}
    return out


def test_candidates_carry_span_and_provenance(candidates):
    """① 候选必须带 span / 章节路径 / 规范版本；span 覆盖率 100%。"""
    for p in PROTOCOLS:
        cs = candidates[p]
        assert cs, f"{p} 应抽到约束候选"
        with_span = [c for c in cs if c.get("span_start") is not None
                     and c.get("span_end") is not None]
        assert len(with_span) == len(cs), (
            f"{p}: span 覆盖率 {len(with_span)}/{len(cs)} ≠ 100%")
        for c in cs:
            assert isinstance(c["span_start"], int)
            assert isinstance(c["span_end"], int)
            assert 0 <= c["span_start"] < c["span_end"]
            assert isinstance(c["section_path"], list) and c["section_path"], (
                f"{p}: 候选缺 section_path")
            assert all(isinstance(x, str) and x for x in c["section_path"])
            assert c.get("spec_version", "").startswith("RFC "), (
                f"{p}: 候选缺规范版本：{c.get('spec_version')!r}")


def test_span_locates_source_text_exactly(candidates, spec_texts):
    """② span 必须能在源文件里**逐字定位**（B-2「先验证区间」的物理前提）。"""
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m, f"{p}: source 格式不合法：{c['source']!r}"
            raw = spec_texts[p][m.group("name")]
            assert raw[c["span_start"]:c["span_end"]] == c["text"], (
                f"{p}: span 与原文不一致：{c['source']}")


def test_source_anchor_is_unified_real_line_number(candidates):
    """④ source 统一为 `file:<name>#@<真实行号>`（两种 anchor 语义不再并存）。"""
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m, (
                f"{p}: source 必须形如 file:<name>#@<行号>，实得 {c['source']!r}")
            assert int(m.group("line")) >= 1
            assert "#@abnf" not in c["source"]


def test_toc_contamination_is_zero(candidates, spec_texts):
    """③ TOC 污染实测归零（用**独立**判据回查候选的来源行）。"""
    for p in PROTOCOLS:
        lines_cache = {name: raw.splitlines()
                       for name, raw in spec_texts[p].items()}
        contaminated = []
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m
            lines = lines_cache[m.group("name")]
            lineno = int(m.group("line"))
            assert 1 <= lineno <= len(lines), f"{p}: 行号越界 {lineno}"
            raw_line = lines[lineno - 1]
            # ★ 用**独立**的形态判据（不复用 _is_toc_line —— 那会自证）
            if _independent_toc_lines([raw_line]):
                contaminated.append((c["source"], raw_line[:80]))
        assert not contaminated, (
            f"{p}: TOC 污染候选 {len(contaminated)} 条：{contaminated[:3]}")


def test_candidates_are_in_document_order(candidates):
    """候选按文档顺序产出（章节窗口 DFS 前序 ⇒ 源行号单调不减）。"""
    for p in PROTOCOLS:
        by_file: dict = {}
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m
            by_file.setdefault(m.group("name"), []).append(int(m.group("line")))
        for name, lines in by_file.items():
            assert lines == sorted(lines), (
                f"{p}/{name}: 候选未按文档顺序产出")


def test_candidates_come_from_section_bodies_not_preamble(candidates, spec_texts):
    """候选**不**来自「首个章节标题之前」的抬头/摘要/目录区（P1-2 语义）。"""
    from core.fused.rfc_extractor import (
        _doc_content_lines, _split_heads_bodies,
    )
    for p in PROTOCOLS:
        first_head: dict = {}
        for name, raw in spec_texts[p].items():
            content = _doc_content_lines(raw.splitlines())
            heads, _bodies, _nos = _split_heads_bodies(content)
            first_head[name] = heads[0].line if heads else 0
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert int(m.group("line")) >= first_head[m.group("name")], (
                f"{p}: 候选来自首标题前的抬头区：{c['source']}")


# ===========================================================================
# B-4　norm_id 冲突修复
# ===========================================================================

def _three_same_field_constraints() -> StubLLMClient:
    """Stub LLM：同一字段（QNAME）的 **3 条不同约束**。"""
    return StubLLMClient(response={"constraints": [
        {"field": "QNAME", "constraint": "单 label 长度 <= 63 字节",
         "violation": "label 长度字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
        {"field": "QNAME", "constraint": "QNAME 整体长度 <= 255 字节",
         "violation": "整体长度字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
        {"field": "QNAME", "constraint": "label 数量 <= 127",
         "violation": "label 数量字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
    ]})


@pytest.fixture(scope="module")
def same_field_norms() -> list:
    return extract_constraint_norms("rtsp", llm=_three_same_field_constraints(),
                                    max_candidates=8)


def test_same_field_constraints_get_unique_norm_ids(same_field_norms):
    """① 同字段多条约束 → norm_id 唯一（`dup_norm_ids == 0`）。"""
    ids = [n["norm_id"] for n in same_field_norms]
    assert len(same_field_norms) == 3
    assert len(set(ids)) == len(ids), f"norm_id 仍冲突：{ids}"
    # 判别位后缀存在，且不是裸的 field 键
    for n in same_field_norms:
        assert n["norm_id"].startswith("rtsp.constraint.qname.")
        assert len(n["norm_id"].rsplit(".", 1)[1]) == 10


def test_same_field_constraints_pass_quality_gate(same_field_norms):
    """② 该场景下质量闸**不阻断**构建（`passed == True`）。"""
    facts = []
    for n in same_field_norms:
        facts.extend(map_norm_to_facts(n))
    rep = rfc_quality_report("rtsp", facts=facts, norms=same_field_norms)
    assert rep.dup_norm_ids == 0
    assert rep.dup_fact_ids == 0, "同字段多约束仍产出重复 fact_id"
    assert rep.passed, f"质量闸仍阻断：{rep.blocking_issues}"


def test_same_field_constraints_produce_distinct_facts(same_field_norms):
    """同字段多约束 → 每个 fact 的 fact_id 互不相同（事实身份可区分）。"""
    facts = []
    for n in same_field_norms:
        facts.extend(map_norm_to_facts(n))
    assert len(facts) == 6          # 3 条约束 × (legal_boundary + response_expectation)
    assert len({f.fact_id for f in facts}) == len(facts)
    # subject.name 仍是字段名（下游 bundle 按 name 分桶，行为不变）
    assert all(f.fact_key.subject.name == "QNAME" for f in facts)
    assert all(f.fact_key.subject.type == "header" for f in facts)


def test_identity_digest_ignores_free_text_behavior():
    """③ 判别位**不用 LLM 自由措辞**：同一语义不同措辞 → 同一摘要。"""
    a = constraint_identity_digest("QNAME", "单 label <= 63", "x", "1")
    b = constraint_identity_digest("QNAME", "单 label <= 63", "x", "1")
    assert a == b
    # 内容不同 → 摘要不同
    assert a != constraint_identity_digest("QNAME", "整体 <= 255", "x", "1")
    assert a != constraint_identity_digest("QNAME", "单 label <= 63", "y", "1")
    # 排版差异（大小写/空白）不应改变摘要
    assert a == constraint_identity_digest("qname", "  单  label   <= 63 ", "x", "1")


def _digest_with_hash_seed(hashseed: str) -> str:
    """在**独立子进程**里算摘要（PYTHONHASHSEED 不同 ⇒ `hash()` 会漂移）。"""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    env["PYTHONPATH"] = str(ROOT)
    code = ("from core.fused.norm import constraint_identity_digest as d;"
            "print(d('QNAME', '单 label <= 63', 'x', '1'))")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, f"子进程失败：{out.stderr}"
    return out.stdout.strip()


def test_identity_digest_is_reproducible_across_processes():
    """③ norm_id 判别位**跨进程稳定**（证明没用随机化的 `hash()`）。"""
    a = _digest_with_hash_seed("0")
    b = _digest_with_hash_seed("1")
    c = _digest_with_hash_seed("12345")
    assert a == b == c, f"摘要跨进程不一致：{a} / {b} / {c}"
    assert a == constraint_identity_digest("QNAME", "单 label <= 63", "x", "1")


def test_constraint_norms_carry_span_provenance(same_field_norms):
    """B-3 的 span / 章节 / 版本随约束 norm 一起下沉（可回溯到原文）。"""
    for n in same_field_norms:
        assert n["source"].startswith("file:")
        assert "#@" in n["source"]
        assert isinstance(n["span_start"], int)
        assert isinstance(n["span_end"], int)
        assert n["span_start"] < n["span_end"]
        assert n["spec_version"].startswith("RFC ")
        assert isinstance(n["section_path"], list)
