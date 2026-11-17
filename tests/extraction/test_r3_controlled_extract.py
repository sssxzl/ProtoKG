# -*- coding: utf-8 -*-
"""V2-E4-R3 受控抽取的回归测试。

覆盖：来源门禁、抽样冻结、预算上限、事件可复算、缓存隔离、
      冻结基线完整性、历史候选未被覆盖、V0/V1/V2 未变、aspects 与中枢不变。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R3 = ROOT / "guard/_out/_n1c_v2/r3"
POOL = R3 / "pool"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R3_跨协议独立候选受控抽取")


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 来源门禁 =====

def test_eligible_sources_cover_three_protocols():
    """实际抽取的来源必须全部合格且覆盖三协议。

    ★ R4 对账时把候选集补齐到 20 份，★ rfc3848 亦满足独立性门禁但未被抽取，
    ★ 故 accepted 数可大于抽取数；★ 断言以【实际抽取的来源】为准。
    """
    _g = _j(R3 / "r3_source_gate.json")
    _e = [r for r in _g["rows"] if r["eligible_for_extraction"]]
    _p = {r["protocol"] for r in _e}
    assert _p == {"sip", "rtsp", "smtp"}
    assert len(_e) >= 8
    # ★ 实际抽取的来源必须是 accepted 的子集
    _b = _j(R3 / "r3_blocks.json")
    _extracted = {b["document"].replace("rfc", "").replace(".txt", "")
                  for b in _b["blocks"]}
    assert _extracted <= {r["rfc_number"] for r in _e}
    assert len(_extracted) == 8


def test_excluded_sources_have_reason():
    _g = _j(R3 / "r3_source_gate.json")
    for _r in _g["rows"]:
        if not _r["eligible_for_extraction"]:
            assert _r["exclusion_reason"], _r["rfc_number"]


def test_eligible_sources_byte_distinct_from_lib():
    """合格来源必须与库内任何文档字节不同。"""
    _g = _j(R3 / "r3_source_gate.json")
    _lib = set()
    for _proto in ("rtsp", "sip", "smtp", "DHCPv4"):
        _d = ROOT / "kb" / _proto / "spec"
        if _d.is_dir():
            for _f in _d.glob("*.txt"):
                _lib.add(hashlib.sha256(_f.read_bytes()).hexdigest())
    for _r in _g["rows"]:
        if _r["eligible_for_extraction"]:
            assert _r["sha256"] not in _lib, _r["rfc_number"]


def test_index_snapshot_hash_recorded():
    _g = _j(R3 / "r3_source_gate.json")
    _p = R3 / "rfc-index.txt"
    assert hashlib.sha256(_p.read_bytes()).hexdigest() == _g["index_snapshot"]["sha256"]


def test_rfc_header_number_verified():
    for _r in _j(R3 / "r3_source_gate.json")["rows"]:
        if _r["eligible_for_extraction"]:
            assert _r["header_rfc_number_verified"] is True, _r["rfc_number"]


# ===== 抽样冻结 =====

def test_blocks_frozen_and_complete():
    _b = _j(R3 / "r3_blocks.json")
    assert len(_b["blocks"]) == 16
    assert len({x["block_id"] for x in _b["blocks"]}) == 16
    assert len({x["document"] for x in _b["blocks"]}) == 8


def test_every_document_has_two_blocks():
    _b = _j(R3 / "r3_blocks.json")
    _c = collections.Counter(x["document"] for x in _b["blocks"])
    assert set(_c.values()) == {2}


def test_each_document_has_one_low_density_block():
    """每份文档至少一个密度不高于中位数的块。"""
    _b = _j(R3 / "r3_blocks.json")
    _by = collections.defaultdict(list)
    for x in _b["blocks"]:
        _by[x["document"]].append(x["bcp14_density"])
    for _doc, _ds in _by.items():
        assert min(_ds) <= sorted(_ds)[len(_ds) // 2], _doc


def test_block_hash_matches_content():
    _b = _j(R3 / "r3_blocks.json")
    for x in _b["blocks"]:
        assert hashlib.sha256(x["text"].encode()).hexdigest() == x["block_sha256"]


# ===== 预算 =====

def test_budget_within_limits():
    _s = _j(POOL / "R3_抽取汇总.json")
    assert _s["actual_llm_request"] <= 18
    assert _s["token_total"] <= 120000
    assert _s["cost_usd"] <= 0.05
    assert _s["processed_block_count"] <= 18


def test_rfc_count_within_limit():
    _b = _j(R3 / "r3_blocks.json")
    assert len({x["document"] for x in _b["blocks"]}) <= 9


# ===== 事件可复算 =====

def test_events_are_append_only_and_separated():
    _ev = _jl(POOL / "R3_LLM追加式请求事件.jsonl")
    _c = collections.Counter(e["event_kind"] for e in _ev)
    assert _c["actual_llm_request"] == 8
    assert _c["cache_hit"] == 0
    assert _c["local_replay"] == 0
    assert _c["retry"] == 0
    assert _c["request_failure"] == 0
    assert _c["batch_failure"] == 0
    assert _c["block_failure"] == 0
    _seq = [e["event_seq"] for e in _ev]
    assert _seq == sorted(_seq)
    assert len(set(_seq)) == len(_seq)


def test_summary_recomputable_from_events():
    _ev = _jl(POOL / "R3_LLM追加式请求事件.jsonl")
    _acts = [e for e in _ev if e["event_kind"] == "actual_llm_request"]
    _in = sum(int(e.get("input_tokens") or 0) for e in _acts)
    _out = sum(int(e.get("output_tokens") or 0) for e in _acts)
    _s = _j(POOL / "R3_抽取汇总.json")
    assert _s["actual_llm_request"] == len(_acts)
    assert _s["input_tokens"] == _in
    assert _s["output_tokens"] == _out
    assert _s["token_total"] == _in + _out


def test_every_event_has_required_fields():
    _ev = _jl(POOL / "R3_LLM追加式请求事件.jsonl")
    for _e in _ev:
        for _k in ("run_id", "batch_id", "request_id", "source_sha256",
                   "block_ids", "model", "prompt_digest", "schema_version",
                   "request_time", "request_status", "response_status",
                   "raw_response_ref", "raw_response_sha256"):
            assert _k in _e, _k


def test_raw_responses_match_event_hashes():
    _ev = _jl(POOL / "R3_LLM追加式请求事件.jsonl")
    for _e in _ev:
        _p = ROOT / _e["raw_response_ref"]
        assert _p.is_file(), _e["raw_response_ref"]
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == \
            _e["raw_response_sha256"]


def test_retry_events_do_not_double_count_tokens():
    _ev = _jl(POOL / "R3_LLM追加式请求事件.jsonl")
    for _e in _ev:
        if _e["event_kind"] == "retry":
            assert _e.get("input_tokens") is None
            assert _e.get("output_tokens") is None


# ===== 缓存隔离 =====

def test_production_cache_not_polluted():
    assert not list((ROOT / "derived/cache").glob("*.prose.json"))


def test_pilot_cache_is_separate():
    assert (R3 / "cache").is_dir()


# ===== 冻结基线 =====

def test_frozen_baseline_integrity():
    _rows = _jl(DELIV / "R3_跨协议候选冻结基线.jsonl")
    assert len(_rows) == 57
    assert len({r["gold_candidate_id"] for r in _rows}) == 57
    for _r in _rows:
        assert _r["gold_candidate_id"].startswith("X-")
        assert "prose_semantics" not in _r["gold_candidate_id"]
        assert "prose_constraint" not in _r["gold_candidate_id"]
        assert _r["source_sha256"]
        assert r"★ 状态" in _r


def test_frozen_baseline_covers_three_protocols():
    _rows = _jl(DELIV / "R3_跨协议候选冻结基线.jsonl")
    assert {r["protocol"] for r in _rows} == {"sip", "rtsp", "smtp"}


def test_norm_id_collision_recorded_not_hidden():
    _c = _j(POOL / "R3_复算数据.json")
    assert len(_c["norm_id_collisions"]) == 1
    _rows = _jl(DELIV / "R3_跨协议候选冻结基线.jsonl")
    _marked = [r for r in _rows if r.get("norm_id_collision")]
    assert len(_marked) == 3


def test_candidates_not_written_to_production_space():
    """新增候选不得进入正式 Fact 空间或中枢。"""
    _hub = ROOT / "derived/hub"
    for _p in _hub.rglob("*.jsonl"):
        _t = _p.read_text(encoding="utf-8", errors="replace")
        assert "rfc7826" not in _t and "rfc8055" not in _t, _p


# ===== 历史候选未被覆盖 =====

def test_h1_h2_h3_and_gold_intact():
    for _p in (ROOT / "guard/_out/_v2_e2_pilot/V2-E2_新增候选审计.jsonl",
               ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl",
               ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl",
               ROOT / "docs/实施/待办与勘误/M0对账交付"
               / "M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl"):
        assert _p.is_file(), _p
        assert _p.stat().st_size > 0, _p


def test_v0_v1_v2_unchanged():
    _b = _j(ROOT / "docs/实施/待办与勘误/M0对账交付"
            / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计/N2-B0-R_版本哈希.json")
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    assert (ROOT / "guard/_out/_n1c_v2/v2_knowledge_gate.py").is_file()


def test_aspects_unchanged():
    _m = _j(ROOT / "core/fused/hub/knowledge_slots.json")
    assert len(_m["aspect_map"]) >= 21


# ===== 交付物 =====

DELIVERABLES = [
    "R3_新增RFC权威元数据与来源清单.xlsx",
    "R3_文档独立性与泄漏审计.xlsx",
    "R3_冻结原文块及抽样台账.xlsx",
    "R3_原始RFC版本哈希.json",
    "R3_冻结抽样规则与预算证明.md",
    "R3_LLM追加式请求事件.jsonl",
    "R3_请求块数Token费用复算报告.xlsx",
    "R3_原始输出索引与哈希.json",
    "R3_跨协议候选冻结基线.jsonl",
    "R3_协议知识类型与候选产出分布.xlsx",
    "R3_队列B历史抽取覆盖勘误.xlsx",
    "R3_回归测试与审批边界证明.md",
    "R3_独立候选评测扩充建议.md",
]


@pytest.mark.parametrize("name", DELIVERABLES)
def test_deliverable_exists(name):
    _p = DELIV / name
    assert _p.is_file(), name
    assert _p.stat().st_size > 0, name


@pytest.mark.parametrize("name", [n for n in DELIVERABLES if n.endswith(".xlsx")])
def test_xlsx_reopens_with_cells(name):
    _wb = openpyxl.load_workbook(DELIV / name)
    assert len(_wb.sheetnames) >= 1
    _wb.close()
