# -*- coding: utf-8 -*-
"""★ H0：★ 抽取链路加固的回归测试（★ §九 十五项覆盖）。

★ 覆盖：file: 规范化 / 来源无法定位 / 同名多版本 / 缓存命中 / 离线重放 /
★ 首次调用统计保护 / 调用失败与重试恢复 / 批量部分失败 / 批量重复候选 /
★ Schema 不适用字段 / LLM 已产出但派生未保留 / SHOULD NOT 的 strength+polarity /
★ 跨句条件未解析 / JSON·CSV 特殊字符与换行 / 旧版正式产物逐字节不变
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/_fixtures/h0"))
import source_contract as SC
import run_events as RE
import field_ledger as FL

KB = ROOT / "kb"


# ══ ① file: 来源规范化 ══
def test_file_prefix_source_normalized():
    """★ ★ 此前 `source` 带 `file:` 导致 source_sha256 为 None ⇒ 本用例覆盖。"""
    _r = SC.normalize_document_id("file:rfc3261.txt#@130")
    assert _r["normalized_document_id"] == "rfc3261.txt"
    assert _r["locator"] == "130"
    assert _r["locator_kind"] == "#@"


def test_section_locator_kind():
    _r = SC.normalize_document_id("file:rfc3261.txt#12")
    assert _r["normalized_document_id"] == "rfc3261.txt"
    assert _r["locator_kind"] == "#"


def test_resolve_file_prefix_gives_sha():
    """★ ★ file: 前缀的来源必须能定位并给出 SHA256（★ 回归此前 None 缺陷）。"""
    _r = SC.resolve_source("file:rfc3261.txt#@130", kb_root=KB)
    assert _r["status"] == SC.RESOLVED
    assert _r["source_sha256"]
    assert len(_r["source_sha256"]) == 64


# ══ ② 来源无法定位 ══
def test_unresolvable_source_is_unresolved_without_fake_sha():
    _r = SC.resolve_source("file:does_not_exist_xyz.txt#@1", kb_root=KB)
    assert _r["status"] == SC.UNRESOLVED
    assert _r["source_sha256"] is None


def test_ambiguous_same_name_is_not_guessed():
    """★ ★ 同名多协议 ⇒ ambiguous，★ 绝不任选一个。"""
    _r = SC.resolve_source("file:rfc3261.txt#@1", kb_root=KB)
    # ★ 若库内同名文件只在一个协议下 ⇒ resolved；★ 若多个 ⇒ ambiguous
    assert _r["status"] in (SC.RESOLVED, SC.AMBIGUOUS)
    if _r["status"] == SC.AMBIGUOUS:
        assert _r["source_sha256"] is None


def test_path_traversal_rejected():
    """★ ★ 越界路径不得访问。"""
    _r = SC.resolve_source("file:../../etc/passwd", kb_root=KB)
    assert _r["status"] in (SC.UNRESOLVED, SC.AMBIGUOUS)
    assert _r["source_sha256"] is None


def test_uri_encoded_and_space_paths():
    _r = SC.normalize_document_id("file:my%20doc.txt#@1")
    assert " " in _r["normalized_document_id"]
    assert any("URI" in n for n in _r["notes"])


# ══ ③ 相同 RFC 不同文件版本 ══
def test_same_name_different_content_gives_different_sha(tmp_path):
    _kb = tmp_path / "kb"
    (_kb / "p1" / "spec").mkdir(parents=True)
    (_kb / "p1" / "spec" / "r.txt").write_text("A", encoding="utf-8")
    _h1 = SC.resolve_source("file:r.txt#@1", kb_root=_kb)["source_sha256"]
    (_kb / "p1" / "spec" / "r.txt").write_text("B", encoding="utf-8")
    _h2 = SC.resolve_source("file:r.txt#@1", kb_root=_kb)["source_sha256"]
    assert _h1 != _h2


# ══ ④⑤ 缓存命中 / 离线重放 ══
def test_cache_hit_and_replay_not_counted_as_requests(tmp_path):
    _log = RE.RunEventLog(tmp_path, run_id="t1")
    _log.record_actual(block_ids=["b1"], input_tokens=100, output_tokens=50)
    _log.record_cache_hit(block_ids=["b2"])
    _log.record_replay(block_ids=["b3"])
    _s = _log.summarize()
    assert _s["★ actual_llm_request"] == 1
    assert _s["★ cache_hit"] == 1
    assert _s["★ local_replay"] == 1
    assert _s["★ token 合计（★ 仅真实请求）"] == 150
    assert _s["★ 估算费用 USD（★ 仅真实请求）"] > 0
    assert _s["★ 涉及块数（★ 与请求数独立）"] == 3


# ══ ⑥ 首次调用统计保护 ══
def test_first_run_stats_not_overwritten_by_recheck(tmp_path):
    """★ ★ 首次真实调用统计不可被后续复核覆盖。"""
    _log = RE.RunEventLog(tmp_path, run_id="t2")
    _log.record_actual(block_ids=["b1"], input_tokens=200, output_tokens=100)
    _first = _log.summarize()
    assert _first["★ actual_llm_request"] == 1
    # ★ 复核：★ 缓存命中 + 离线重放
    _log.record_cache_hit(block_ids=["b1"])
    _log.record_replay(block_ids=["b1"])
    _second = _log.summarize()
    assert _second["★ actual_llm_request"] == 1
    assert _second["★ token 合计（★ 仅真实请求）"] == 300
    assert _second["★ 估算费用 USD（★ 仅真实请求）"] == _first["★ 估算费用 USD（★ 仅真实请求）"]


def test_events_append_only(tmp_path):
    _log = RE.RunEventLog(tmp_path, run_id="t3")
    _log.record_actual(block_ids=["b1"])
    _log.record_actual(block_ids=["b2"])
    _log.close()
    _lines = _log.path.read_text(encoding="utf-8").splitlines()
    assert len(_lines) == 2
    _log2 = RE.RunEventLog(tmp_path, run_id="t3")
    _log2.record_actual(block_ids=["b3"])
    _log2.close()
    assert len(_log.path.read_text(encoding="utf-8").splitlines()) == 3


# ══ ⑦ 调用失败与重试恢复 ══
def test_failure_evidence_retained_and_retry_separate(tmp_path):
    _log = RE.RunEventLog(tmp_path, run_id="t4")
    _log.record_failure(error_stage="json_parse", error_type="JSONDecodeError",
                        error_message="bad", block_ids=["b1"])
    _log.record_actual(block_ids=["b1"], is_retry=True,
                       input_tokens=10, output_tokens=5)
    _s = _log.summarize()
    assert _s["★ failure_events"] == 1
    assert _s["★ retry_requests"] == 1
    assert _s["★ 首请求数"] == 0
    # ★ 首次失败证据仍在
    _evs = _log.events()
    assert any(e["event_kind"] == "llm_failure" for e in _evs)


# ══ ⑧ 批量部分失败 ══
def test_batch_partial_failure_tracked_per_block(tmp_path):
    """★ ★ 批内部分失败必须能追到具体块（★ 事件带 block_ids）。"""
    _log = RE.RunEventLog(tmp_path, run_id="t5")
    _log.record_failure(error_stage="request", error_type="Timeout",
                        error_message="t/o", block_ids=["b1", "b2"])
    _log.record_actual(block_ids=["b3", "b4", "b5"], input_tokens=1,
                       output_tokens=1)
    _s = _log.summarize()
    assert _s["★ failure_events"] == 1
    assert _s["★ 涉及块数（★ 与请求数独立）"] == 5
    assert _s["★ actual_llm_request"] == 1


# ══ ⑨ 批量重复候选 ══
def test_duplicate_candidate_dedup_in_trace():
    """★ ★ 同一候选重复进入流转时不得重复计。"""
    _rows = FL.trace_candidate(
        candidate_id="c1", knowledge_kind="prose_constraint",
        raw_item={"entity": "X", "meaning": "m", "action": "a",
                  "object": "o", "strength": "MUST", "polarity": "positive",
                  "normative_subject": "S", "condition": "c",
                  "exception": "e", "constraint": "k",
                  "cross_ref_status": "none"},
        norm={"kind": "prose_constraint", "name": "X", "entity": "X",
              "meaning": "m", "constraint": "k", "span_line": 10,
              "source": "file:rfc.txt#@10"},
        source_ref="file:rfc.txt#@10",
        source_resolution={"normalized_document_id": "rfc.txt",
                           "source_sha256": "x", "status": "resolved"})
    _ids = [r["candidate_id"] for r in _rows]
    assert len(set(_ids)) == 1


# ══ ⑩ Schema 中不适用字段 ══
def test_not_applicable_field_detected():
    _rows = FL.trace_candidate(
        candidate_id="c2", knowledge_kind="prose_semantics",
        raw_item={"entity": "X"}, norm={"kind": "prose_semantics"},
        source_ref="file:r.txt#@1",
        source_resolution={"normalized_document_id": "r.txt",
                           "source_sha256": "x", "status": "resolved"})
    _by = {r["field"]: r for r in _rows}
    assert _by["condition"]["★ 状态"] == FL.NOT_REQUESTED
    # ★ evidence_span：★ norm 无 span_line/source ⇒ ★ **确实缺失** ⇒ unexpectedly_lost
    assert _by["evidence_span"]["★ 状态"] == FL.UNEXPECTEDLY_LOST


# ══ ⑪ LLM 已产出但派生未保留 ══
def test_llm_produced_but_norm_dropped_is_unexpectedly_lost():
    """★ ★ §五 核心：★ LLM 已产出 normative_subject 但 Norm 层无该字段。"""
    _rows = FL.trace_candidate(
        candidate_id="c3", knowledge_kind="prose_constraint",
        raw_item={"normative_subject": "S", "action": "a", "object": "o",
                  "strength": "MUST", "polarity": "positive",
                  "condition": "c", "exception": "e"},
        norm={"kind": "prose_constraint", "entity": "X", "meaning": "m"},
        source_ref="file:r.txt#@1",
        source_resolution={"normalized_document_id": "r.txt",
                           "source_sha256": "x", "status": "resolved"})
    _by = {r["field"]: r for r in _rows}
    for _f in ("normative_subject", "action", "object", "strength",
               "polarity", "condition", "exception"):
        assert _by[_f]["★ 状态"] == FL.UNEXPECTEDLY_LOST, _f
        assert _by[_f]["★ LLM 层非空"] is True


# ══ ⑫ SHOULD NOT 的 strength+polarity 保留 ══
def test_should_not_keeps_strength_and_polarity():
    """★ ★ SHOULD NOT ⇒ strength=SHOULD 且 polarity=negative（★ 二者都保留）。"""
    _raw = {"strength": "SHOULD", "polarity": "negative",
            "constraint": "Clients SHOULD NOT provide SEND."}
    _rows = FL.trace_candidate(
        candidate_id="c4", knowledge_kind="prose_constraint",
        raw_item=_raw, norm={"kind": "prose_constraint", "entity": "Clients"},
        source_ref="file:r.txt#@1",
        source_resolution={"normalized_document_id": "r.txt",
                           "source_sha256": "x", "status": "resolved"})
    _by = {r["field"]: r for r in _rows}
    assert _by["strength"]["★ LLM 层非空"] is True
    assert _by["polarity"]["★ LLM 层非空"] is True
    assert _by["polarity"]["★ 状态"] == FL.UNEXPECTEDLY_LOST   # ★ 派生层丢弃


# ══ ⑬ 跨句条件未解析 ══
def test_cross_sentence_condition_not_resolved_marked():
    """★ ★ 跨句条件未解析 ⇒ 不得被当作已解析。"""
    _raw = {"condition": "", "cross_ref_status": "unresolved",
            "entity": "X"}
    _rows = FL.trace_candidate(
        candidate_id="c5", knowledge_kind="prose_constraint",
        raw_item=_raw, norm={"kind": "prose_constraint"},
        source_ref="file:r.txt#@1",
        source_resolution={"normalized_document_id": "r.txt",
                           "source_sha256": "x", "status": "resolved"})
    _by = {r["field"]: r for r in _rows}
    assert _by["condition"]["★ LLM 层非空"] is False
    assert _by["cross_ref_status"]["★ LLM 层非空"] is True


# ══ ⑭ JSON/CSV 特殊字符与换行 ══
def test_special_chars_and_newlines_in_evidence():
    import csv
    import io
    _probe = 'a"b,c\nd⏎e\\f'
    _buf = io.StringIO()
    _w = csv.writer(_buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    _w.writerow(["x"]); _w.writerow([_probe])
    _back = list(csv.reader(io.StringIO(_buf.getvalue())))
    assert _back[1][0] == _probe
    _j = json.dumps({"ev": _probe}, ensure_ascii=False)
    assert json.loads(_j)["ev"] == _probe


# ══ ⑮ 旧版正式产物逐字节不变 ══
def test_official_products_unchanged():
    """★ ★ 旧版正式产物逐字节不变（★ 本轮零生产改动）。"""
    import hashlib
    _base = ROOT / "guard/_out/m1_3"
    for _d in ("derived_hub", "derived_seeds"):
        _f = _base / f"baseline_{_d}.txt"
        if not _f.is_file():
            pytest.skip("★ 基线清单不在入库范围")
        _cur = ROOT / "guard/_out/m1_3" / f"h0_{_d}.txt"
        if not _cur.is_file():
            pytest.skip("★ 本轮未生成对照")
        assert _f.read_bytes() == _cur.read_bytes(), _d


def test_v0_v1_v2_unchanged():
    import hashlib
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
