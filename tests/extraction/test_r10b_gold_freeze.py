# -*- coding: utf-8 -*-
"""V2-E4-R10B 回归测试：跨协议 Gold 最终冻结。

覆盖：5 条共识确认接收、SC-03 不重复计数、原子增量口径为 8 条、
      冻结基线枚举合法与 ID 唯一、原件未改、生产隔离。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
FIX = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R8_人工审核回收核验/R8_跨协议仲裁结构修复")
R10A = ROOT / "guard/_out/_n1c_v2/r10a"
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"
R7P = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R7_H3Gold字段复核与评测准入"
       / "R7_H3_V2版本哈希及预注册规则.md")

GOLD = DELIV / "R10_跨协议Gold冻结基线.jsonl"
FREEZE = json.loads((R10A / "r10b_freeze_meta.json").read_text(
    encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 5 条共识确认 =====
def test_five_consensus_confirmed():
    _rows = [r for r in _jl(GOLD) if r["gold_level"] == "candidate"]
    _target = {"X-rtsp-rfc7826-07", "X-sip-rfc2543-01", "X-sip-rfc3428-03",
               "X-sip-rfc3428-04", "X-smtp-rfc8098-04"}
    _got = {r["candidate_id"] for r in _rows
            if r["★ 人工来源"] == "R10A 共识裁定补录"}
    assert _got == _target, _got
    for _r in _rows:
        if _r["candidate_id"] in _target:
            assert _r["status"] == "confirmed", _r["candidate_id"]
            assert _r["★ 仲裁者"] == "F"
            assert _r["knowledge_kind"]
            assert _r["rule_eligibility"]
            assert _r["target_route"]


def test_denominator_back_to_57():
    _rows = [r for r in _jl(GOLD) if r["gold_level"] == "candidate"]
    assert len(_rows) == 57
    _in = [r for r in _rows if r["★ 计入分类主分母"]]
    assert len(_in) == 57
    _p = collections.Counter(r["protocol"] for r in _in)
    assert _p["SIP"] == 27 and _p["RTSP"] == 7 and _p["SMTP"] == 23


# ===== 原子增量 =====
def test_atom_count_is_8():
    _atoms = [r for r in _jl(GOLD) if r["gold_level"] == "atom"]
    assert len(_atoms) == 8


def test_sc03_not_new_entry():
    """★ SC-03 归并至候选 7826-07，★ 不得新增原子条目。"""
    _atoms = [r for r in _jl(GOLD) if r["gold_level"] == "atom"]
    _ids = [r["gold_id"] for r in _atoms]
    assert not any("7826-06" in i for i in _ids), _ids
    # ★ 7826-07 仍是候选级条目
    _cand = [r for r in _jl(GOLD) if r["gold_level"] == "candidate"]
    assert any(r["candidate_id"] == "X-rtsp-rfc7826-07" for r in _cand)


def test_sc01_merged_into_existing():
    """★ SC-01 归并进已有 RTSP 补充知识，★ 不新增。"""
    _atoms = [r for r in _jl(GOLD) if r["gold_level"] == "atom"]
    _sc01 = [r for r in _atoms if r["candidate_id"] == "X-rtsp-rfc7826-03"]
    assert len(_sc01) == 1
    assert "SC-01" in str(_sc01[0].get("★ 去重说明", ""))


def test_sc05_sc06_each_two_atoms():
    _atoms = [r for r in _jl(GOLD) if r["gold_level"] == "atom"]
    for _cid in ("X-smtp-rfc3461-04", "X-smtp-rfc6531-01"):
        _g = [r for r in _atoms if r["candidate_id"] == _cid]
        assert len(_g) == 2, (_cid, len(_g))
        assert any(r["gold_id"].endswith("-a") for r in _g)
        assert any(r["gold_id"].endswith("-b") for r in _g)


def test_no_duplicate_gold_ids():
    _ids = [r["gold_id"] for r in _jl(GOLD)]
    assert len(_ids) == len(set(_ids))


def test_all_gold_fields_have_human_source():
    for _r in _jl(GOLD):
        assert _r.get("★ 人工来源"), _r["gold_id"]
        assert _r.get("★ 仲裁者"), _r["gold_id"]


# ===== 枚举与机器隔离 =====
def test_enumerations_legal():
    _K = {"non_protocol_metadata", "protocol_syntax",
          "protocol_registry_or_enumeration", "protocol_descriptive_semantics",
          "normative_rule_candidate", "mixed_or_uncertain"}
    _E = {"eligible", "ineligible", "uncertain", "not_applicable"}
    _R = {"rule_channel", "structured_channel", "metadata_channel",
          "descriptive_channel", "pending_review", "not_applicable"}
    _C = {"not_applicable", "cross_sentence_missing", "cross_section_missing",
          "partial", "full", "unavailable"}
    for _r in _jl(GOLD):
        assert _r["knowledge_kind"] in _K, _r["gold_id"]
        assert _r["rule_eligibility"] in _E, _r["gold_id"]
        assert _r["target_route"] in _R, _r["gold_id"]
        assert _r["extract_completeness"] in _C, _r["gold_id"]


def test_machine_projection_verbatim():
    """★ 机器命题投影必须与 R3 原字段逐字相等。"""
    _base = {}
    for _l in R3P.read_text(encoding="utf-8").splitlines():
        if _l.strip():
            _b = json.loads(_l)
            _base[_b["gold_candidate_id"]] = _b
    for _r in _jl(GOLD):
        if _r["gold_level"] != "candidate":
            continue
        _b = _base[_r["candidate_id"]]
        _src = _r["★ machine_proposition 来源"]
        _orig = _b.get("constraint") if _src == "constraint" else _b.get("meaning")
        assert _r["★ machine_original_proposition"] == str(_orig or "").strip()


def test_candidate_polarity_unavailable():
    for _r in _jl(GOLD):
        if _r["gold_level"] == "candidate":
            assert _r["polarity"] == "unavailable"


# ===== 原件未改 =====
def test_r3_and_r7_unchanged():
    assert hashlib.sha256(R3P.read_bytes()).hexdigest() == \
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a"
    assert hashlib.sha256(R7P.read_bytes()).hexdigest() == \
        "7cfa8430c4a1d07748bfbcc1fdb29fe12fdd034b2baa78c06bc4e73b40838a91"


def test_h3_gold_v4_untouched():
    _p = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
          / "R5A_H3第三方仲裁与Gold冻结/H3_Gold冻结基线_v4候选.jsonl")
    assert hashlib.sha256(_p.read_bytes()).hexdigest().startswith(
        "0f507db855069757")


def test_old_versions_retained():
    """★ 旧版本全部保留。"""
    for _n in ("R10_5条共识待确认.xlsx", "R10_57条候选去向对账.xlsx",
               "R10_评估分母与标签映射.xlsx"):
        assert (DELIV / _n).is_file(), _n
    assert (ROOT / "guard/_out/_n1c_v2/r9").is_dir()
    assert (ROOT / "guard/_out/_n1c_v2/r10").is_dir()


# ===== 生产隔离 =====
def test_production_unchanged():
    import ast
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    for _n in ast.walk(ast.parse(_src)):
        if isinstance(_n, ast.Assign) and getattr(_n.targets[0], "id", "") \
                == "_PROMPT":
            assert hashlib.sha256(
                _n.value.value.encode()).hexdigest()[:16] \
                == "d97fbe611ac9aa61"
            break
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21


def test_no_llm_calls_in_r10a():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r10a").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
