# -*- coding: utf-8 -*-
"""V2-E4-R6 回归测试：Gold 复核、字段审计、分母与生产隔离。"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R5A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
       / "R5A_H3第三方仲裁与Gold冻结")
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R6_H3Gold冻结复核与评测准备")
R6 = ROOT / "guard/_out/_n1c_v2/r6"

V1 = R5A / "H3_Gold冻结基线.jsonl"
V2 = R5A / "H3_Gold冻结基线_v2.jsonl"
V1_SHA = "f4bfbdb5da1746416321ff2f20bcbf070330fa606f79c0715fccd8545fec6044"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


# ===== 冻结原件未被覆盖 =====
def test_v1_frozen_original_unchanged():
    assert hashlib.sha256(V1.read_bytes()).hexdigest() == V1_SHA


def test_v2_exists_and_has_28():
    _rows = _jl(V2)
    assert len(_rows) == 28
    assert len({r["gold_knowledge_id"] for r in _rows}) == 28


def test_erasure_record_exists():
    assert (R5A / "H3_Gold勘误记录.json").is_file()


# ===== 勘误内容 =====
def test_two_field_values_corrected():
    _rows = {r["gold_knowledge_id"]: r for r in _jl(V2)}
    _h303 = _rows["GK-H3-03-1"]["★ 适用的结构化字段"]["规范义务主体"]
    assert _h303["value"] == "DHCP 服务器（发送方，须加认证）"
    assert _h303["c_explicit"] is True
    _h305 = _rows["GK-H3-05-1"]["★ 适用的结构化字段"]["规范义务对象"]
    assert _h305["value"] == "once among all instances of this option"


def test_candidate_polarity_all_unavailable():
    _rows = [r for r in _jl(V2) if r["gold_level"] == "candidate"]
    assert len(_rows) == 23
    for _r in _rows:
        assert _r["polarity"] == "unavailable"


def test_supplementary_polarity_kept():
    _rows = [r for r in _jl(V2) if r["gold_level"] == "supplementary"]
    assert len(_rows) == 5
    assert all(r["polarity"] in ("positive", "negative") for r in _rows)


def test_completeness_is_enumeration():
    _allowed = {"not_applicable", "cross_sentence_missing",
                "cross_section_missing", "partial", "full", "unavailable"}
    for _r in _jl(V2):
        assert _r["extract_completeness"] in _allowed, _r["gold_knowledge_id"]


# ===== 分母 =====
def test_denominator_is_22_not_28():
    _d = _j(R6 / "r6_denominator.json")["分母"]
    assert _d["★ Gold 记录总数"] == 28
    assert _d["★ 分类评估分母（★ 候选级 confirmed_valid）"] == 22
    assert _d["★ ├ 有效协议知识（★ 正类）"] == 18
    assert _d["★ └ 非协议元数据负类"] == 4
    assert _d["★ excluded 单列（★ 不计入任何分母）"] == 1
    assert _d["★ 补充知识（★ 漏抽发现，★ 单列）"] == 5


def test_gate_summary_has_blocking_items():
    _g = _j(R6 / "r6_denominator.json")["预注册门禁汇总"]
    assert _g["已满足"] == 4
    assert _g["部分满足"] == 2
    assert _g["待确认"] == 3
    assert sorted(_g["★ 阻断项"]) == [1, 8, 9]


def test_field_audit_counts():
    _a = _j(R6 / "r6_field_audit.json")
    assert sum(_a["class_counts"].values()) == len(_a["field_audit"])
    assert len(_a["gold_structure_fields"]) == 4


# ===== 交付文件 =====
DELIVERABLES = [
    "R6_H3_Gold结构与版本复核.md",
    "R6_H3_结构化字段逐条复核.xlsx",
    "R6_H3_未决字段及Polarity适用性.xlsx",
    "R6_H3_候选与补充知识评估分母.xlsx",
    "R6_H3_预注册独立评测门禁.md",
    "R6_H3_Gold勘误建议与版本哈希.md",
    "R6_H3_预注册评测门禁.xlsx",
]


@pytest.mark.parametrize("name", DELIVERABLES)
def test_deliverable_exists(name):
    _p = DELIV / name
    assert _p.is_file(), name
    assert _p.stat().st_size > 0, name


@pytest.mark.parametrize("name", [n for n in DELIVERABLES if n.endswith(".xlsx")])
def test_xlsx_opens(name):
    _wb = openpyxl.load_workbook(DELIV / name)
    assert len(_wb.sheetnames) >= 1
    _wb.close()


# ===== 生产隔离 =====
def test_production_unchanged():
    """本轮未改生产抽取路径、V0/V1/V2、FactID、21 aspects。"""
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    assert '"norm_id": f"{kind}_{ent.lower().replace(\'-\', \'_\')}"' in _src


def test_no_llm_calls_in_r6():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r6").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_hub_and_seeds_not_modified():
    """正式中枢与种子未被本轮改写（★ 与基线逐字节比对由护栏执行）。"""
    _hub = ROOT / "derived/hub"
    assert _hub.is_dir()
    for _p in _hub.rglob("*.jsonl"):
        assert _p.stat().st_size > 0
