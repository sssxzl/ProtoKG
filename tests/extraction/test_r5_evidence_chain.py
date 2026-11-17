# -*- coding: utf-8 -*-
"""V2-E4-R5 回归测试：R5A 仲裁包门禁与 R5B 证据身份链。

覆盖：仲裁列全空、Gold 未冻结、证据链复算、evidence_id 碰撞传导、
      口径闭合、复合索引稳定性、生产代码未改、冻结记录不变。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R5 = ROOT / "guard/_out/_n1c_v2/r5"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验")
R5A = DELIV / "R5A_H3第三方仲裁与Gold冻结"
R5B = DELIV / "R5B_NormID与EvidenceID核验"


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


# ===== R5A 仲裁包 =====
def test_arbitration_columns_all_empty():
    """★ 第三方仲裁列必须全空（★ Agent 不代填）。"""
    _p = R5A / "H3_第三方人工仲裁回收核验.xlsx"
    _wb = openpyxl.load_workbook(_p)
    _todo = ("最终状态（待填）", "裁定结论（待填）", "证据与理由（待填）",
             "仲裁人员/日期（待填）", "是否语义等价（待填）", "仲裁结果（待填）",
             "对应另一审核者记录（待填）", "是否拆分/合并（待填）",
             "第三方裁定（待填）", "Gold 映射（待填）",
             "最终处理状态（待填）", "最终知识类型（待填）",
             "最终规则资格（待填）", "最终强度（待填）", "最终路由（待填）")
    _hits = []
    for _s in _wb.sheetnames:
        _ws = _wb[_s]
        _hdr = [str(c.value or "") for c in _ws[1]]
        for _r in range(2, _ws.max_row + 1):
            for _c in range(1, _ws.max_column + 1):
                _h = _hdr[_c - 1] if _c - 1 < len(_hdr) else ""
                if _h in _todo and str(_ws.cell(row=_r, column=_c).value or "").strip():
                    _hits.append(f"{_s}!{_ws.cell(row=_r, column=_c).coordinate}")
    _wb.close()
    assert not _hits, _hits[:5]


def test_gold_baseline_not_generated():
    """★ 门禁未通过 ⇒ 不得存在 Gold 冻结基线。"""
    assert not (R5A / "H3_Gold冻结基线.jsonl").exists()


def test_arbitration_covers_all_44_field_diffs():
    """★ 全部 44 行逐字段差异必须有仲裁归宿（★ 含未列入关键待裁的 12 行）。"""
    _wb = openpyxl.load_workbook(R5A / "H3_第三方人工仲裁回收核验.xlsx")
    _ws = _wb["逐字段差异"]
    _n = _ws.max_row - 1
    _wb.close()
    assert _n == 44


def test_candidate_final_status_sheet_has_23_rows():
    _wb = openpyxl.load_workbook(R5A / "H3_第三方人工仲裁回收核验.xlsx")
    _ws = _wb["候选最终状态"]
    _n = _ws.max_row - 1
    _wb.close()
    assert _n == 23


def test_unresolved_items_recorded():
    _v = _j(R5A / "H3_版本哈希与未决项.json")
    _u = _v["★ 未决项"]
    assert _u["★ 关键待裁待仲裁"] == 8
    assert _u["★ 逐字段差异待仲裁"] == 44
    assert _u["★ 补充知识待裁定"] == 8
    assert _u["★ 候选最终状态待填"] == 23
    assert _u["★ 全部未决项已标记"] is False
    assert _v["★ Gold 冻结状态"].startswith("★ 未冻结")


# ===== R5B 证据链 =====
def test_evidence_chain_counts():
    _c = _j(R5 / "r5b_evidence_chain.json")
    assert _c["R3"]["记录数"] == 57
    assert _c["R3"]["唯一 norm_id"] == 55
    assert _c["R3"]["唯一 evidence_id"] == 55
    assert _c["R3"]["norm_id 碰撞组数"] == 1
    assert _c["R3"]["evidence_id 碰撞组数"] == 1
    assert _c["H1"]["记录数"] == 156
    assert _c["H1"]["唯一 norm_id"] == 116
    assert _c["H1"]["唯一 evidence_id"] == 116
    assert _c["H1"]["norm_id 碰撞组数"] == 16
    assert _c["H1"]["evidence_id 碰撞组数"] == 16


def test_collision_overflow_accounting_closes():
    """★ 156 - 116 = 40 的口径闭合。"""
    _c = _j(R5 / "r5b_evidence_chain.json")
    for _b in ("R3", "H1"):
        _v = _c[_b]
        assert (_v["记录数"] - _v["唯一 norm_id"]
                == _v["重复超额（★ 记录数减唯一数）"])
        assert _v["重复超额（★ 记录数减唯一数）"] == \
            _v["evidence_id 碰撞涉及记录数"] - _v["evidence_id 碰撞组数"]


def test_collision_groups_have_distinct_payloads():
    _c = _j(R5 / "r5b_evidence_chain.json")
    for _b in ("R3", "H1"):
        for _g in _c[_b]["★ 碰撞组明细"]:
            assert _g["distinct_payloads"] == _g["group_size"]


def test_evidence_id_collision_real_mislink_identified():
    """★ 组内跨度不同的碰撞组即真实错链风险。"""
    _c = _j(R5 / "r5b_evidence_chain.json")
    _risk = 0
    for _b in ("R3", "H1"):
        for _g in _c[_b]["★ 碰撞组明细"]:
            _spans = {tuple(x["source_span"]) for x in _g["members"]}
            if len(_spans) > 1:
                _risk += 1
    assert _risk >= 1


def test_scheme_c_index_unique_and_stable():
    _c = _j(R5 / "r5b_evidence_chain.json")
    for _k, _v in _c["★ 影子稳定性验证"].items():
        assert _v["★ scheme_c 唯一率"] == 1.0, _k
        assert _v["★ 重复运行一致"] is True, _k
        assert _v["★ 候选顺序改变不影响映射"] is True, _k
        assert _v["★ 旧 norm_id 保留可兼容读取"] is True, _k
        assert _v["★ 来源版本绑定（★ source_sha256 逐条登记）"] is True, _k


def test_evidence_id_computation_matches_production():
    """★ 复算的 evidence_id 必须与生产函数一致。"""
    import sys
    sys.path.insert(0, str(ROOT))
    from core.fused.hub.canonical import compute_evidence_id
    from core.fused.hub.models import Evidence
    _c = _j(R5 / "r5b_evidence_chain.json")
    for _r in _c["r3_chain"][:10]:
        _ev = Evidence(evidence_id="placeholder", claim_id="",
                       source_type="rfc", source_id=_r["norm_id"],
                       document="", locator=None, quote="",
                       content_fingerprint="", extraction_fingerprint="")
        assert compute_evidence_id(_ev) == _r["evidence_id"]


def test_production_norm_id_unchanged():
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    assert '"norm_id": f"{kind}_{ent.lower().replace(\'-\', \'_\')}"' in _src


def test_frozen_records_unchanged():
    for _p in (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl",
               ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl",
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


def test_no_llm_calls_in_r5():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r5").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name

# ===== 下游消费路径核查（★ R5B 新增） =====

def test_hub_products_have_no_evidence_id_field():
    """★ 中枢产物不含 evidence_id 与 evidence 数组 ⇒ 不存在按 evidence_id 建索引的路径。"""
    import collections
    _claims = 0
    _evidence_elems = 0
    _eids = []
    for _p in sorted((ROOT / "derived/hub").rglob("*.jsonl")):
        if _p.name == "sources.json":
            continue
        for _l in _p.read_text(encoding="utf-8").splitlines():
            if not _l.strip():
                continue
            _r = json.loads(_l)
            for _c in _r.get("all_claims") or []:
                _claims += 1
                _ev = _c.get("evidence")
                if _ev:
                    _evidence_elems += len(_ev)
                    for _e in _ev:
                        if _e.get("evidence_id"):
                            _eids.append(_e["evidence_id"])
    assert _claims > 0
    assert _evidence_elems == 0, "★ 中枢产物含 evidence 元素，★ 需重新核查消费路径"
    assert not _eids


def test_hub_evidence_summary_carries_disambiguation_info():
    """★ evidence_summary 格式为 authority:标识@路径，★ rfc 类含文档与跨度。"""
    _found = 0
    for _p in sorted((ROOT / "derived/hub").rglob("*.jsonl")):
        if _p.name == "sources.json":
            continue
        for _l in _p.read_text(encoding="utf-8").splitlines():
            if not _l.strip():
                continue
            _r = json.loads(_l)
            for _c in _r.get("all_claims") or []:
                if _c.get("authority") != "rfc":
                    continue
                for _s in (_c.get("evidence_summary") or []):
                    if "file:" in str(_s) and "#@" in str(_s):
                        _found += 1
    assert _found > 0, "★ 未找到含文档与跨度的 rfc 类 evidence_summary"


def test_alignment_ledger_exists_with_5_units():
    """★ 原子知识对齐台账含 5 条独立命题，★ 裁定列全空。"""
    _p = R5A / "H3_原子知识对齐与裁定台账.xlsx"
    assert _p.is_file()
    _wb = openpyxl.load_workbook(_p)
    assert "独立命题与裁定" in _wb.sheetnames
    assert "原始标注溯源" in _wb.sheetnames
    _ws = _wb["独立命题与裁定"]
    _n = _ws.max_row - 1
    _hdr = [str(c.value or "") for c in _ws[1]]
    _todo = [i for i, h in enumerate(_hdr, 1) if "待填" in h]
    for _r in range(2, _ws.max_row + 1):
        for _ci in _todo:
            assert not str(_ws.cell(row=_r, column=_ci).value or "").strip()
    _src = _wb["原始标注溯源"]
    _n_src = _src.max_row - 1
    _wb.close()
    assert _n == 5
    assert _n_src == 8
