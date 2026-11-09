# -*- coding: utf-8 -*-
"""tests/fused/test_norm_outcome_content.py —— outcome content 的「含义 | when: 条件」解析。

★ P1-1（2026-11-01，QA 独立复核发现）
--------------------------------------------
`core/fused/norm.py:parse_outcome_content` 的正则**缺 `re.DOTALL`** ⇒ `.` 不匹配换行
⇒ 只要 ``| when:`` 之后有换行（RFC 正文必然多行），整条正则**匹配失败** ⇒
   `condition` 为空，且 `meaning` 里混入完整的 ``| when: ...`` 文本。

实测影响：三协议 65 个 outcome 里 **52 个（80%）condition 丢失**
（rtsp 13/15 = 87%、sip 39/50 = 78%）—— 语义层数据是错的
（``aspect=definition`` 的值里混进了条件文本，而 condition 字段全空）。

本文件锁住修复，防止回归。

★ P2-3（同批 QA 发现）协议级去重键与 norm_id 不同源
--------------------------------------------
`norm_id` 大小写不敏感（``rfc_extractor._norm()``：
``f"{protocol}.{kind}.{name.lower().replace(' ', '_')}"``），
而 `extract_rfc_norms` 的**协议级**去重键用大小写敏感的 ``(kind, name)``
⇒ 跨文件的 ``Accept`` / ``accept`` 既躲过去重、又撞了同一个 ``norm_id``
⇒ ``dup_norm_ids = 1`` ⇒ 质量闸把**合法语料**判成重复并**阻断构建**。

★ 该修复**必须落在 `core/fused/rfc_extractor.py`（协议级去重键那一行）**，
  不在 `core/fused/norm.py` 的职责范围内。

★ **已修复（2026-11-01）**：`extract_rfc_norms` 的协议级去重键已改为
  ``key = norm["norm_id"]``（与 norm_id 生成规则同源：大小写不敏感 + 空格转下划线）。
  本文件原有的 ``xfail(strict=True)`` 标记已摘除，该用例转为**常绿护栏**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.extraction.norm import parse_outcome_content  # noqa: E402
from core.fused.extraction.rfc_extractor import extract_rfc_norms  # noqa: E402


# ===========================================================================
# 基本形态
# ===========================================================================

def test_single_line_condition_parsed():
    """单行 content → (含义, 条件)。"""
    meaning, condition = parse_outcome_content("Trying | when: single line condition")
    assert meaning == "Trying"
    assert condition == "single line condition"


def test_multiline_condition_parsed():
    """★ 多行 content → 条件**跨行**完整解析（修前整体匹配失败）。"""
    content = ("Trying | when: This response indicates that the request has been "
               "received by the\n   next-hop server and that it is proceeding.")
    meaning, condition = parse_outcome_content(content)
    assert meaning == "Trying", meaning
    assert condition.startswith("This response indicates")
    assert "next-hop server" in condition


def test_meaning_does_not_leak_condition():
    """★ meaning 不得含 ``| when:`` 或条件文本（修前混入了整段）。"""
    content = "Trying | when: cond line1\n line2"
    meaning, condition = parse_outcome_content(content)
    assert "when:" not in meaning
    assert "cond" not in meaning
    assert condition.strip() == "cond line1\n line2".strip()


def test_condition_has_no_when_prefix():
    """★ condition 不得含 ``| when:`` 前缀（修前 meaning/condition 边界是坏的）。"""
    _meaning, condition = parse_outcome_content("Trying | when: cond line1\n line2")
    assert "| when:" not in condition
    assert not condition.lstrip().lower().startswith("when:")


def test_no_when_clause():
    """无 ``| when:`` → 整串作为 meaning、condition 为空。"""
    meaning, condition = parse_outcome_content("Just a reason phrase")
    assert meaning == "Just a reason phrase"
    assert condition == ""


def test_no_when_clause_multiline_keeps_whole_text():
    """无 ``| when:`` 的**多行** content → 整串作为 meaning、condition 仍为空。"""
    content = "Reason phrase\n   continued body text"
    meaning, condition = parse_outcome_content(content)
    assert meaning == content
    assert condition == ""


def test_empty_content():
    """空 content → 不抛异常。"""
    meaning, condition = parse_outcome_content("")
    assert meaning == ""
    assert condition == ""


def test_empty_when_clause():
    """``| when:`` 后为空 → condition 为空、meaning 仍正确。"""
    meaning, condition = parse_outcome_content("OK | when: ")
    assert meaning == "OK"
    assert condition == ""


# ===========================================================================
# 三协议真实语料：condition 解析失败数必须为 0
# ===========================================================================

@pytest.mark.parametrize("protocol", ["rtsp", "sip", "smtp"])
def test_real_corpus_has_no_condition_parse_failure(protocol):
    """★ 三协议真实语料里，condition 解析失败数必须为 0（修前 52/65）。"""
    outs = [n for n in extract_rfc_norms(protocol) if n["kind"] == "outcome"]
    failed = [
        n for n in outs
        if not parse_outcome_content(n.get("content", ""))[1]
        and "| when:" in (n.get("content") or "")
    ]
    assert not failed, \
        f"{protocol} 有 {len(failed)} 个 outcome 的 condition 未被解析（修前共 52 个）"


def test_real_corpus_meaning_has_no_when_marker():
    """真实语料里 meaning 不得含 ``| when:`` 残留（修前普遍混入）。"""
    for protocol in ("rtsp", "sip", "smtp"):
        outs = [n for n in extract_rfc_norms(protocol) if n["kind"] == "outcome"]
        for n in outs:
            meaning, _cond = parse_outcome_content(n.get("content", ""))
            assert "| when:" not in meaning, \
                f"{protocol}.{n.get('name')} 的 meaning 混入了条件文本: {meaning[:80]!r}"


def test_real_corpus_total_outcomes_all_parsed():
    """★ 合计口径：三协议 outcome 总数 89，condition 解析失败数 = 0（修前 52/65）。

    逐协议断言（上面的参数化用例）之外，再加一条**合计**断言 ——
    防止「某个协议被整体漏检」这类逐协议用例看不出的回归。

    ★ 65 → 89（2026-11-06，P1-2）：smtp 由 **0 → 24**。原因是两个缺陷叠加：
      ① ``fused_hub/targets/smtp/rfc_config.json`` 的 ``4.2`` 同时列在
         ``method_sections`` 与 ``status_sections``，而 ``_section_kind``
         旧实现是**固定 method 优先** ⇒ 整章「SMTP Replies」被判成 method；
      ② 状态码通道只认**章节标题**形态（``^\\d{3}\\s+title``），
         而 RFC 5321 §4.2.3 是**缩进表格** ⇒ 即使判对类型也抽不出。
      现由「跨类别最长前缀 + status 优先破平局」+「通道 C 缩进码表」共同修复。
    """
    per_protocol: dict[str, int] = {}
    failed = 0
    for protocol in ("rtsp", "sip", "smtp"):
        for n in extract_rfc_norms(protocol):
            if n["kind"] != "outcome":
                continue
            per_protocol[protocol] = per_protocol.get(protocol, 0) + 1
            content = n.get("content", "") or ""
            _meaning, condition = parse_outcome_content(content)
            if "| when:" in content and not condition:
                failed += 1
    total = sum(per_protocol.values())
    assert per_protocol.get("smtp") == 24, \
        f"smtp 状态码应为 24 条（RFC 5321 §4.2.3），实测 {per_protocol.get('smtp')}"
    assert total == 89, f"三协议 outcome 总数变了：{total}（预期 89）"
    assert failed == 0, f"共 {failed} 个 outcome 的 condition 未被解析（修前 52）"


# ===========================================================================
# P2-3　协议级去重键必须与 norm_id 同源（大小写不敏感）
# ===========================================================================

def test_case_variants_share_one_norm_id():
    """★ ``Accept`` 与 ``accept`` 必须产出**同一个** norm_id。

    这是 P2-3 的根因：norm_id 大小写不敏感，而协议级去重键大小写敏感
    ⇒ 两者既躲过去重、又撞了 norm_id ⇒ ``dup_norm_ids > 0`` ⇒ 质量闸
    误判「合法语料重复」并**阻断构建**。
    """
    from core.fused.extraction.rfc_extractor import _norm
    a = _norm("field", "Accept", "", "rtsp", "rfcA.txt", "@1")
    b = _norm("field", "accept", "", "rtsp", "rfcB.txt", "@1")
    assert a["norm_id"] == b["norm_id"] == "rtsp.field.accept"


def test_distinct_entities_are_not_merged():
    """★ 大小写折叠**不得**误合并真正不同的实体。

    ``Content-Length`` 与 ``content_length`` 的 norm_id 不同
    （连字符 vs 下划线），故是不同实体 —— 归一化不能把它们混为一谈。
    """
    from core.fused.extraction.rfc_extractor import _norm
    a = _norm("field", "Content-Length", "", "rtsp", "rfcA.txt", "@1")
    b = _norm("field", "content_length", "", "rtsp", "rfcB.txt", "@1")
    assert a["norm_id"] != b["norm_id"]


def test_protocol_level_dedup_keeps_one_of_case_variants(tmp_path, monkeypatch):
    """★ 跨文件的 ``Accept`` / ``accept`` ⇒ 只保留 1 条，且质量闸不报重复。

    合成跨文件语料（合法语料），复现 QA 的 P2-3 场景：
      修复前 ⇒ 2 条同名 norm、norm_id 相同 ⇒ dup_norm_ids=1 ⇒ passed=False
      修复后 ⇒ 只保留首个（按文件名排序）⇒ dup_norm_ids=0 ⇒ passed=True
    """
    from core.fused.extraction import rfc_extractor as rx

    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "rfcA.txt").write_text(
        "5.1 Accept\n   The Accept request-header field.\n", encoding="utf-8")
    (spec / "rfcB.txt").write_text(
        "5.1 accept\n   The accept request-header field.\n", encoding="utf-8")
    cfg = {"method_sections": [], "field_sections": ["5.1"],
           "status_sections": [], "method_excludes": [], "numeric_bounds": []}

    monkeypatch.setattr(rx.paths, "kb_source_dir", lambda p, s: spec)
    monkeypatch.setattr(rx, "_load_rfc_config", lambda p: cfg)

    norms = rx.extract_rfc_norms("fake")
    ids = [n["norm_id"] for n in norms]
    assert len(ids) == len(set(ids)), f"仍有重复 norm_id：{ids}"
    assert len(norms) == 1, f"大小写变体应只保留 1 条，实得 {len(norms)}"
    assert norms[0]["name"] == "Accept"          # 保留首个（rfcA.txt 在前）
    assert norms[0]["source"].startswith("file:rfcA.txt")

    report = rx.rfc_quality_report("fake", facts=None, norms=norms)
    assert report.dup_norm_ids == 0
    assert report.passed, f"合法语料不该被质量闸阻断：{report.blocking_issues}"
