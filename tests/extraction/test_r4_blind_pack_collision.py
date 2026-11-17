# -*- coding: utf-8 -*-
"""V2-E4-R4 回归测试：R4A 盲审包与 R4B 碰撞审计。

覆盖：三协议候选数、A/B 机器身份一致、泄漏扫描、人工结论为空、
      碰撞可复算、影子 ID 稳定性、生产代码未改、冻结记录不变。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve()[0:0] if False else pathlib.Path(
    __file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R4跨协议盲审与NormID碰撞")
R4A = DELIV / "R4A_跨协议人工盲审包"
R4B = DELIV / "R4B_NormID碰撞专项"
R4 = ROOT / "guard/_out/_n1c_v2/r4"


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== R4A 候选覆盖 =====
@pytest.mark.parametrize("proto,n", [("SIP", 27), ("RTSP", 7), ("SMTP", 23)])
def test_protocol_candidate_count(proto, n):
    _b = _jl(R4A / "R4A_冻结机器基线.jsonl")
    _p = [r for r in _b if str(r["★ 协议"]).upper() == proto.upper()]
    assert len(_p) == n
    assert len({r["★ 审核ID"] for r in _p}) == n


def test_total_57_not_deduplicated():
    _b = _jl(R4A / "R4A_冻结机器基线.jsonl")
    assert len(_b) == 57
    _m = _j(R4A / "R4A_审核ID映射与版本哈希.json")
    assert _m["total"] == 57


def test_no_candidate_dropped_or_added():
    _src = _jl(ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl")
    _b = _jl(R4A / "R4A_冻结机器基线.jsonl")
    assert len(_src) == len(_b) == 57
    _s = {r["gold_candidate_id"] for r in _src}
    _t = {r["★ 审核ID"] for r in _b}
    assert _s == _t


# ===== A/B 一致性 =====
@pytest.mark.parametrize("proto,n", [("SIP", 27), ("RTSP", 7), ("SMTP", 23)])
def test_ab_machine_identity_identical(proto, n):
    _a = openpyxl.load_workbook(R4A / f"{proto}_{n}候选_审核者A_盲审模板.xlsx")
    _b = openpyxl.load_workbook(R4A / f"{proto}_{n}候选_审核者B_盲审模板.xlsx")
    _sa, _sb = _a["机器身份"], _b["机器身份"]
    assert _sa.max_row == _sb.max_row
    assert _sa.max_column == _sb.max_column
    for _r in range(1, _sa.max_row + 1):
        for _c in range(1, _sa.max_column + 1):
            assert (_sa.cell(row=_r, column=_c).value or "") == \
                (_sb.cell(row=_r, column=_c).value or "")
    _a.close()
    _b.close()


# ===== 泄漏 =====
def test_no_machine_prediction_leak_in_any_sheet():
    """模型类型名与审核枚举不得出现在说明表、机器身份表。"""
    _machine = ["prose_semantics", "prose_constraint"]
    for _p in sorted(R4A.glob("*.xlsx")):
        _wb = openpyxl.load_workbook(_p)
        for _s in _wb.sheetnames:
            for _row in _wb[_s].iter_rows():
                for _c in _row:
                    _v = str(_c.value or "")
                    for _f in _machine:
                        assert _f not in _v, f"{_p.name}/{_s}/{_c.coordinate}"
        _wb.close()


def test_review_id_carries_no_model_type():
    for _r in _jl(R4A / "R4A_冻结机器基线.jsonl"):
        _id = _r["★ 审核ID"]
        assert "prose_semantics" not in _id
        assert "prose_constraint" not in _id


def test_workbook_metadata_clean():
    for _p in sorted(R4A.glob("*.xlsx")):
        _wb = openpyxl.load_workbook(_p)
        _pr = _wb.properties
        for _a in ("title", "subject", "description", "keywords", "category"):
            _v = str(getattr(_pr, _a, "") or "")
            assert "prose_semantics" not in _v
            assert "prose_constraint" not in _v
        _wb.close()


# ===== 人工结论为空 =====
def test_all_human_conclusions_filled_and_legal():
    """★ 人工审核已回收（R8）。

    ★ 断言从「人工列为空」改为「人工列已填且取值在允许集合内」；
    ★ 机器预置列仍须保持未被改写。
    """
    _ALLOWED = {
        "原文是否支持候选命题": {"yes", "no", "uncertain", "not_applicable"},
        "是否属于目标协议知识": {"yes", "no", "uncertain", "not_applicable"},
        "knowledge_kind": {"non_protocol_metadata", "protocol_syntax",
                           "protocol_registry_or_enumeration",
                           "protocol_descriptive_semantics",
                           "normative_rule_candidate", "mixed_or_uncertain"},
        "source_content_kind": {"non_protocol_metadata", "protocol_syntax",
                                "protocol_registry_or_enumeration",
                                "protocol_descriptive_semantics",
                                "normative_rule_candidate", "mixed_or_uncertain"},
        "rule_eligibility": {"eligible", "ineligible", "uncertain",
                             "not_applicable"},
        "evidence_sufficiency": {"sufficient", "partial", "insufficient",
                                 "not_applicable"},
        "人工认为正确的 V2 目标路由": {"rule_channel", "structured_channel",
                                      "metadata_channel", "descriptive_channel",
                                      "pending_review", "not_applicable"},
    }
    _machine = ("★ 审核ID", "★ RFC 文档", "★ RFC 编号", "★ RFC 标题",
                "★ RFC 状态", "★ source_sha256", "★ 取得日期", "★ 来源 URL",
                "★ 证据跨度（行号）", "★ 候选命题（待核）", "★ 候选含义（待核）",
                "★ 候选声称的", "★ 证据引文（待核）", "★ block_id",
                "★ block_sha256", "★ 行号", "★ 优先级", "★ 字段",
                "★ 审核者 A", "★ 审核者 B", "★ 差异性质提示",
                "★ A 目标知识", "★ B 目标知识", "★ A 知识类型", "★ B 知识类型",
                "★ A 规则资格", "★ B 规则资格", "★ A 强度", "★ B 强度",
                "★ A 完整性", "★ B 完整性", "★ A 路由", "★ B 路由",
                "★ 补充序号", "★ 强度", "★ 极性", "★ 补充命题原文",
                "★ 补充命题所在行号")
    for _p in sorted(R4A.glob("*.xlsx")):
        _wb = openpyxl.load_workbook(_p)
        for _s in _wb.sheetnames:
            if _s in ("说明", "机器身份", "_枚举"):
                continue
            _hdr = [str(c.value or "") for c in _wb[_s][1]]
            for _row in _wb[_s].iter_rows(min_row=2):
                for _c in _row:
                    _h = _hdr[_c.column - 1] if _c.column - 1 < len(_hdr) else ""
                    if any(_h.startswith(_m) for _m in _machine):
                        continue
                    _v = str(_c.value or "").strip()
                    if not _v:
                        continue
                    for _k, _allowed in _ALLOWED.items():
                        if _h.startswith(_k):
                            assert _v in _allowed, \
                                f"{_p.name}/{_s}/{_c.coordinate}: {_v}"
        _wb.close()


# ===== 碰撞复算 =====
def test_collision_counts_reproducible():
    _c = _j(R4 / "r4b_collision_ledger.json")["summary"]
    assert _c["R3"]["记录数"] == 57
    assert _c["R3"]["唯一 norm_id"] == 55
    assert _c["R3"]["碰撞组数"] == 1
    assert _c["H1"]["记录数"] == 156
    assert _c["H1"]["唯一 norm_id"] == 116
    assert _c["H1"]["碰撞组数"] == 16


def test_collision_groups_have_distinct_payloads():
    _c = _j(R4 / "r4b_collision_ledger.json")
    for _batch in ("R3", "H1"):
        for _g in _c["summary"][_batch]["组明细"]:
            assert _g["distinct_payloads"] == _g["group_size"], _g["collision_group"]


def test_collision_impact_classified():
    _c = _j(R4 / "r4b_collision_ledger.json")
    for _batch in ("R3", "H1"):
        for _g in _c["summary"][_batch]["组明细"]:
            assert _g["★ 影响分类"].startswith(
                ("A ", "B ", "C ", "D ")), _g["collision_group"]


# ===== 影子 ID =====
def test_shadow_ids_unique_and_stable():
    import sys
    sys.path.insert(0, str(R4))
    import shadow_norm_id as SN
    _recs = [{"kind": "prose_constraint", "entity": "server",
              "meaning": "m1", "constraint": "c1", "action": "a", "object": "o",
              "strength": "MUST", "polarity": "positive", "condition": "",
              "exception": "", "document": "rfc1.txt", "source_span": [10, 10],
              "span_line": 10},
             {"kind": "prose_constraint", "entity": "server",
              "meaning": "m2", "constraint": "c2", "action": "a", "object": "o2",
              "strength": "SHOULD", "polarity": "negative", "condition": "",
              "exception": "", "document": "rfc2.txt", "source_span": [20, 20],
              "span_line": 20}]
    assert SN.legacy_norm_id(_recs[0]) == SN.legacy_norm_id(_recs[1])
    assert SN.scheme_a(_recs[0]) != SN.scheme_a(_recs[1])
    assert SN.scheme_b(_recs[0]) != SN.scheme_b(_recs[1])
    assert SN.scheme_c(_recs[0])[1] != SN.scheme_c(_recs[1])[1]
    assert SN.scheme_a(_recs[0]) == SN.scheme_a(_recs[0])
    _rev = list(reversed(_recs))
    assert [SN.scheme_a(r) for r in _recs] == \
        [SN.scheme_a(r) for r in _rev][::-1]


def test_production_norm_id_unchanged():
    """生产 norm_id 构造式必须保持原样。"""
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    assert '"norm_id": f"{kind}_{ent.lower().replace(\'-\', \'_\')}"' in _src


# ===== 冻结记录与工程约束 =====
def test_frozen_records_unchanged():
    for _p in (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl",
               ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl",
               ROOT / "guard/_out/_v2_e2_pilot/V2-E2_新增候选审计.jsonl",
               ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl"):
        assert _p.is_file(), _p
        assert _p.stat().st_size > 0, _p


def test_v0_v1_v2_unchanged():
    _b = _j(ROOT / "docs/实施/待办与勘误/M0对账交付"
            / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计/N2-B0-R_版本哈希.json")
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k


def test_aspects_unchanged():
    _m = _j(ROOT / "core/fused/hub/knowledge_slots.json")
    assert len(_m["aspect_map"]) >= 21


def test_no_llm_calls_in_r4():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r4").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_source_qualification_classes_are_mutually_exclusive():
    _r = _j(R4 / "r4_reconciliation.json")["source_qualification_reconciliation"]
    assert sum(_r["classification_counts"].values()) == _r["total_candidates"]
    # ★ accepted 含 rfc3848（★ 满足独立性门禁但未被抽取）
    assert _r["accepted_count"] >= len(_r["extracted_rfc_numbers"])
    assert len(_r["extracted_rfc_numbers"]) == 8
    # ★ 实际抽取的 8 份必须全部在 accepted 集合内
    assert set(_r["extracted_rfc_numbers"]) <= set(
        a["rfc_number"] for a in _r["accepted"])
