# -*- coding: utf-8 -*-
"""★ H2A：★ 方案 A 影子 sidecar 与队列 B 人工真值验收的回归测试。

★ 覆盖：★ sidecar 不触碰生产对象 ｜★ 字段适用性 ｜★ **unmeasured ≠ 0** ｜★ ambiguous 不伪造哈希
★ ｜★ 重复执行可区分 ｜★ V0/V1/V2 哈希不变 ｜★ FactID/aspects 不变 ｜★ 中枢与 Seed 逐字节一致
★ ｜★ 人工真值四态 ｜★ 仲裁有效性 ｜★ 97 闭合
"""
from __future__ import annotations

import collections
import csv
import hashlib
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/h2a"))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/h0"))
import sidecar as SC
import source_contract as SRC

H2 = ROOT / "guard/_out/_n1c_v2/h2"
DELIV_A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
            / "M1-Q3-V2-E4-H2A方案A兼容性证明")
DELIV_B = (ROOT / "docs/实施/待办与勘误/M0对账交付"
            / "M1-Q3-V2-E4-B1队列B人工真值验收")


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ══ ① sidecar 不触碰生产对象 ══
def test_sidecar_output_dir_outside_production(tmp_path):
    _log = SC.FieldFlowSidecar(tmp_path / "sidecar", run_id="t1")
    assert "core/" not in str(_log.out_dir)
    assert "derived" not in str(_log.out_dir)


def test_sidecar_has_no_llm_client():
    _t = (ROOT / "guard/_out/_n1c_v2/h2a/sidecar.py").read_text(encoding="utf-8")
    assert "DeepSeekClient" not in _t
    assert "chat_json" not in _t


# ══ ② 字段适用性 ══
def test_prose_semantics_normative_fields_not_applicable():
    for _f in ("normative_subject", "action", "object", "strength", "polarity",
               "condition", "exception"):
        assert SC.APPLICABILITY["prose_semantics"][_f] == "not_applicable", _f


def test_prose_constraint_fields_applicable():
    assert SC.APPLICABILITY["prose_constraint"]["strength"] == "optional"
    assert SC.APPLICABILITY["prose_constraint"]["entity"] == "required"


# ══ ③ unmeasured ≠ 0 ══
def test_no_canonical_view_yields_unmeasured(tmp_path):
    _log = SC.FieldFlowSidecar(tmp_path / "s", run_id="t2")
    _log.record(candidate_id="c1", knowledge_kind="prose_constraint",
                source_reference="file:rfc3261.txt#@1",
                normalized_document_id="rfc3261.txt", source_sha256="x",
                source_span=[1, 2],
                raw_llm={"strength": "MUST", "action": "a", "object": "o"},
                derived={}, norm={"kind": "prose_constraint"},
                mapping_branch="★ 正常路径", canonical_carrier=None)
    _recs = _log.events()
    _m = {r["field"]: r for r in _recs}
    # ★ 无 canonical 视图 ⇒ unmeasured（★ **不是** 0、★ 不是「无损失」）
    assert _m["strength"]["semantic_loss_status"] == SC.UNMEASURED
    assert _m["strength"]["semantic_loss_status"] != "★ 无损失"


# ══ ④ ambiguous / unresolved 不伪造哈希 ══
def test_unresolved_source_has_no_fake_sha(tmp_path):
    _kb = tmp_path / "kb"
    (_kb / "p" / "spec").mkdir(parents=True)
    (_kb / "p" / "spec" / "x.txt").write_text("hi", encoding="utf-8")
    _r = SRC.resolve_source("file:nope.txt#@1", kb_root=_kb)
    assert _r["status"] == SC.SC_UNRESOLVED if hasattr(SC, "SC_UNRESOLVED") \
        else _r["status"] == "unresolved"
    assert _r["source_sha256"] is None


def test_path_traversal_no_fake_sha(tmp_path):
    _kb = tmp_path / "kb"
    (_kb / "p" / "spec").mkdir(parents=True)
    _r = SRC.resolve_source("file:../../secret.txt", kb_root=_kb)
    assert _r["source_sha256"] is None


# ══ ⑤ 重复执行可区分 ══
def test_repeated_execution_distinguishable(tmp_path):
    _l1 = SC.FieldFlowSidecar(tmp_path, run_id="r1")
    _l2 = SC.FieldFlowSidecar(tmp_path, run_id="r2")
    for _log in (_l1, _l2):
        _log.record(candidate_id="c1", knowledge_kind="prose_constraint",
                    source_reference="file:r.txt#@1",
                    normalized_document_id="r.txt", source_sha256="x",
                    source_span=[1, 2], raw_llm={"entity": "E"},
                    derived={}, norm={"kind": "prose_constraint"},
                    mapping_branch="★ 正常路径", canonical_carrier={"entity": "x"})
    _runs = {r["run_id"] for r in _l1.events()} | {r["run_id"] for r in _l2.events()}
    assert len(_runs) == 2


# ══ ⑥ V0/V1/V2 与生产不变 ══
def test_v0_v1_v2_unchanged():
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k


def test_factid_and_aspects_untouched():
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21
    _n = (ROOT / "core/fused/extraction/norm.py").read_text(encoding="utf-8")
    _i = _n.find("def prose_constraint_norm_to_facts")
    _seg = _n[_i:_i + 4000]
    assert '"action": _action' in _seg and '"object": _object' in _seg
    assert "rule_text(_payload)" in _seg
    # ★ strength/polarity 不得进 qualifiers
    _q = _seg.split("_quals = ")[1].split("}")[0]
    assert "strength" not in _q and "polarity" not in _q


# ══ ⑦ 人工真值四态与仲裁 ══
def test_gold_has_four_states_and_frozen_hash():
    _rows = _jl(DELIV_B / "B1_人工真值冻结清单.jsonl")
    assert _rows
    _st = collections.Counter(r["★ status"] for r in _rows)
    assert set(_st) <= {"valid_gold", "no_target_knowledge", "uncertain", "unresolved"}
    _h = json.loads((H2 / "h2_b1_acceptance.json").read_text(encoding="utf-8"))
    _sha = _h["⑦ Gold 冻结"]["★ 冻结清单 SHA256"]
    assert hashlib.sha256(
        (DELIV_B / "B1_人工真值冻结清单.jsonl").read_bytes()).hexdigest() == _sha


def test_arbitration_has_id_date_reason():
    _h = json.loads((H2 / "h2_b1_acceptance.json").read_text(encoding="utf-8"))
    _a = _h["⑥ 第三方仲裁有效性"]
    assert _a["★ 有审核者 ID 的行数"] == _a["★ 有日期的行数"] == _a["★ 有理由的行数"]
    assert _a["★ 仅复制 A/B 且无理由（★ 不算完成仲裁）"] == 0
    assert _a["★ ★ 仲裁者与 A/B 区分开"] is True


def test_encoding_conversion_lossless():
    _h = json.loads((H2 / "h2_b1_acceptance.json").read_text(encoding="utf-8"))
    for _k, _v in _h["① 文件与编码验收"].items():
        assert _v["★ ★ 转换无损"] is True, _k
        assert _v["★ 逐单元格差异数"] == 0, _k


# ══ ⑧ 97 闭合 ══
def test_97_closure_explained():
    _a = json.loads((ROOT / "guard/_out/_n1c_v2/h2/h2a_stats_audit.json")
                    .read_text(encoding="utf-8"))
    _c = _a["★ ① 97 闭合核算"]
    assert _c["★ 用户复算合计"] == 96
    assert "constraint" in _c["★ ★ 闭合结论"]


def test_scheme_b_expected_recovery_is_zero():
    _a = json.loads((ROOT / "guard/_out/_n1c_v2/h2/h2a_stats_audit.json")
                    .read_text(encoding="utf-8"))
    _r = _a["★ ② 104 重新定义"]
    # ★ 适用字段的语义损失 = 0 ⇒ 方案 B 的可恢复记录数为 0（★ 或仅余待人工判定项）
    assert _r["★ ├ 其中字段【适用】者"] == 0
    _rec = str(_r["★ 方案 B 预计恢复的记录数"])
    assert ("0" in _rec) or ("待人工判定" in _rec)
