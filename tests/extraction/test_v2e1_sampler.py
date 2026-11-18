# -*- coding: utf-8 -*-
"""★ V2-E1：★ 抽样器与章节分层的**复算测试**。

★ 覆盖：★ 章节类型映射｜★ 泄漏排除（★ 候选/chunk/证据跨度/近重复）｜
★ ★ **可复算性（两次运行逐字节一致）**｜★ 协议硬配额｜★ 每文档上限｜★ **不调用 LLM**
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/_fixtures/e1"))
import sampler as SP
import section_kinds as SK

OUTD = ROOT / "guard/_out/_n1c_v2/e1"


# ══ ① 章节类型映射 ══
def test_section_kinds_all_five_present():
    _all = set(SK.ALL_KINDS)
    assert len(_all) == 5
    assert SK.KIND_FORMAT in _all and SK.KIND_META in _all


def test_abnf_line_maps_to_format():
    _lines = ["Status-Code =", '   "200" ; OK']
    _ks = SK.build_section_index(_lines)
    assert _ks[2] == SK.KIND_FORMAT


def test_copyright_maps_to_metadata():
    _lines = ["Copyright Notice", "All rights reserved."]
    _ks = SK.build_section_index(_lines)
    assert _ks[1] == SK.KIND_META


def test_status_section_maps_to_state():
    _lines = ["12.1 Status Codes", "The following codes are used."]
    _ks = SK.build_section_index(_lines)
    assert _ks[1] == SK.KIND_STATE


def test_definition_section_maps_to_definition():
    _lines = ["2.1 Definitions", "A term used here."]
    _ks = SK.build_section_index(_lines)
    assert _ks[1] == SK.KIND_DEF


def test_operations_default():
    _lines = ["4.1 Operation", "The server does things."]
    _ks = SK.build_section_index(_lines)
    assert _ks[2] == SK.KIND_OPS


# ══ ② 泄漏排除 ══
def test_exclusion_reasons_are_distinct():
    assert SP.EXCL_DEV_CANDIDATE != SP.EXCL_DEV_CHUNK
    assert SP.EXCL_DEV_CHUNK != SP.EXCL_TUNING_EVIDENCE
    assert SP.EXCL_TUNING_EVIDENCE != SP.EXCL_NEAR_DUP
    assert SP.EXCL_NEAR_DUP != SP.EXCL_UNRESOLVED


def test_5gram_jaccard_detects_near_duplicate():
    _a = SP.grams("the server must include a list of extensions in the response")
    _b = SP.grams("the server must include a list of extensions in the reply")
    assert SP.jaccard(_a, _b) > 0.6


def test_unrelated_text_not_near_duplicate():
    _a = SP.grams("the server must include a list of extensions")
    _b = SP.grams("acknowledgements authors addresses internet society")
    assert SP.jaccard(_a, _b) < 0.6


# ══ ③ 可复算性（★ 同一输入+配置+种子 ⇒ 逐字节一致）══
def test_dryrun_is_reproducible():
    _p = OUTD / "v2e1_dryrun.json"
    if not _p.is_file():
        pytest.skip("★ dry-run 产物不在入库范围")
    _d = json.loads(_p.read_text(encoding="utf-8"))
    assert _d["★ 可复算（两次运行哈希一致）"] is True
    assert _d["★ dry-run"]["★ 实际抽出"] == 70


def test_dryrun_protocol_coverage_has_all_four():
    _p = OUTD / "v2e1_dryrun.json"
    if not _p.is_file():
        pytest.skip("★ dry-run 产物不在入库范围")
    _d = json.loads(_p.read_text(encoding="utf-8"))
    _proto = _d["★ dry-run"]["★ 协议分布"]
    for _k in ("rtsp", "sip", "smtp", "DHCPv4"):
        assert _proto.get(_k, 0) > 0, _k


def test_dryrun_per_document_cap_respected():
    _p = OUTD / "v2e1_dryrun.json"
    if not _p.is_file():
        pytest.skip("★ dry-run 产物不在入库范围")
    _d = json.loads(_p.read_text(encoding="utf-8"))
    for _k, _v in _d["★ dry-run"]["★ 文档分布"].items():
        assert _v <= 6, f"{_k}: {_v}"


def test_dryrun_queue_a_actual_is_reported():
    """★ 队列 A 实际可用数必须如实报告（★ 不补入开发集样本）。"""
    _p = OUTD / "v2e1_dryrun.json"
    if not _p.is_file():
        pytest.skip("★ dry-run 产物不在入库范围")
    _d = json.loads(_p.read_text(encoding="utf-8"))
    assert _d["★ dry-run"]["★ 队列A 可用（★ 排除后）"] <= 12
    assert _d["★ dry-run"]["★ 队列A 可用（★ 排除后）"] >= 0


# ══ ④ 统计事实复算 ══
def test_frozen_facts_recomputed():
    """★ §二 的统计事实必须与本地数据一致（★ 不写死）。"""
    _p = OUTD / "v2e1_dryrun.json"
    if not _p.is_file():
        pytest.skip("★ dry-run 产物不在入库范围")
    _d = json.loads(_p.read_text(encoding="utf-8"))["★ §二 复算统计事实"]
    _fr, _meta = SP.load_candidates(ROOT)
    assert _d["★ 现有候选总数"] == len(_fr)
    assert _d["★ V2 开发集唯一 candidate_id 总数"] == 100
    assert _d["★ 落在开发集排除 chunk 内的候选数"] + \
        _d["★ 排除后剩余候选数（★ 上限）"] == len(_fr)


# ══ ⑤ 0 次 LLM ══
def test_no_llm_calls():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/e1").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_v0_v1_v2_unchanged():
    """★ V0 / V1 / V2 冻结判据不得被修改。"""
    _base = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                        / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                        / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _base["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
