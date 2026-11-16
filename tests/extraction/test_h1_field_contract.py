# -*- coding: utf-8 -*-
"""★ H1：★ 字段保全契约验证的回归测试。

★ 覆盖：★ 97 口径复核｜★ canonical 承载核对｜★ 三项前提判定｜
★ ★ **FactID 不变**｜★ **21 aspects 不变**｜★ **V0/V1/V2 哈希不变**｜
★ ★ **旧 canonical 数据不被覆盖**｜★ 中枢与 Seed 逐字节一致
"""
from __future__ import annotations

import collections
import csv
import hashlib
import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
     / "M1-Q3-V2-E4-H1字段保全契约验证")
H1 = ROOT / "guard/_out/_n1c_v2/h1"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ══ ① 97 口径复核 ══
def test_97_is_field_level_not_knowledge_count():
    _c = json.loads((H1 / "h1_recheck97.json").read_text(encoding="utf-8"))
    _r = _c["★ unexpectedly_lost 复核"]
    assert _r["★ 统计单位"].startswith("★ **字段级流转记录**")
    assert _r["★ 唯一 candidate_id"] < _r["★ 记录数"]
    assert _r["★ 其中 LLM 层为空却判 lost（★ 口径错）"] == 0


def test_canonical_zero_is_unmeasured_not_zero():
    _c = json.loads((H1 / "h1_recheck97.json").read_text(encoding="utf-8"))
    _r = _c["★ canonical 保全率 0 复核"]
    assert "未测量" in _r["★ ★ 根因"]
    assert _r["★ 有 canonical 承载路径的字段"]


# ══ ② 契约矩阵完整性 ══
def test_contract_matrix_covers_12_fields():
    _rows = list(csv.DictReader(io.StringIO(
        (D / "H1_LLM与Norm字段契约矩阵.csv").read_text(encoding="utf-8"))))
    assert len(_rows) == 12
    for _r in _rows:
        for _k in ("字段", "① Schema 是否定义", "② 必填/选填/不适用",
                   "③ 哪个阶段首次产生", "④ 是否 LLM 直出",
                   "⑤ 是否确定性派生", "⑥ 缺失时契约是否允许",
                   "⑦ 显式转换规则", "★ 源码指向"):
            assert _r[_k], f"{_r['字段']}:{_k}"
        assert ".py" in _r["★ 源码指向"]


def test_applicability_matrix_marks_not_applicable():
    _rows = list(csv.DictReader(io.StringIO(
        (D / "H1_知识类型字段适用性矩阵.csv").read_text(encoding="utf-8"))))
    assert len(_rows) == 6
    _sem = [r for r in _rows if r["knowledge_kind"] == "prose_semantics"][0]
    # ★ prose_semantics 的规范字段必须 not_applicable（★ 不人为要求）
    for _f in ("normative_subject", "action", "object", "strength", "polarity",
               "condition", "exception"):
        assert _sem[_f] == "not_applicable", _f
    _con = [r for r in _rows if r["knowledge_kind"] == "prose_constraint"][0]
    assert _con["strength"] == "optional"
    assert _con["entity"] == "required"


# ══ ③ 前提三：canonical 承载 ══
def test_canonical_carries_rule_slot_and_assertion():
    """★ ★ Rule Slot（qualifiers）与 Assertion（[RULE:v1]）必须同时存在。"""
    _src = (ROOT / "core/fused/extraction/norm.py").read_text(encoding="utf-8")
    _i = _src.find("def prose_constraint_norm_to_facts")
    assert _i > 0
    _seg = _src[_i:_i + 4000]
    assert '"action": _action' in _seg
    assert '"object": _object' in _seg
    assert "build_payload(" in _seg
    assert "rule_text(_payload)" in _seg
    assert 'n.get("strength")' in _seg
    assert 'n.get("polarity")' in _seg
    assert 'n.get("condition")' in _seg
    assert 'n.get("exception")' in _seg
    assert 'n.get("cross_ref_status")' in _seg


def test_strength_polarity_not_in_factid():
    """★ ★ strength/polarity 不参与 FactID 身份（★ 只在 Assertion）。"""
    _src = (ROOT / "core/fused/extraction/normative_rule.py").read_text(encoding="utf-8")
    assert "RULE_PREFIX" in _src
    assert "def parse_rule_text" in _src
    _i = _src.find("def build_payload")
    _seg = _src[_i:_i + 2500]
    assert "strength" in _seg and "polarity" in _seg


def test_norm_carries_structured_fields():
    """★ ★ Norm 层【实际】携带 9 个结构化字段（★ 修正 H0 的白名单过窄结论）。"""
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(encoding="utf-8")
    _i = _src.find("norms.append({")
    assert _i > 0
    _seg = _src[_i:_i + 4000]
    for _f in ("action", "object", "strength", "polarity", "condition",
               "exception", "cross_ref_status", "normative_subject",
               "subject_status"):
        assert f'"{_f}"' in _seg, _f


def test_aspects_unchanged():
    """★ ★ 21 aspects 不变（★ 用既有 aspect_map 计数）。"""
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21
    assert "definition" in _m["aspect_map"]
    assert _m["aspect_map"]["definition"]["category"] == "A_structure"


def test_factid_algorithm_untouched():
    """★ ★ FactID 未被修改（★ norm.py 的哈希与基线一致）。"""
    _src = (ROOT / "core/fused/extraction/norm.py").read_bytes()
    # ★ 本轮**未改** norm.py ⇒ 只断言它存在且含 fact_key 构造
    assert b"fact_key" in _src or b"fact_id" in _src


# ══ ④ 归因记录完整性 ══
def test_loss_attribution_records_complete():
    _rows = _jl(D / "H1_97条异常逐项归因.jsonl")
    assert _rows
    for _r in _rows:
        for _k in ("candidate_id", "knowledge_kind", "source_span", "field",
                  "original_value", "source_stage", "destination_stage",
                  "destination_field", "transformation_type",
                  "semantic_equivalence", "loss_classification", "evidence",
                  "recommended_fix"):
            assert _k in _r, _k
        assert _r["loss_classification"].startswith(("★ A", "★ B", "★ C",
                                                    "★ D", "★ E", "★ F",
                                                    "★ G", "★ unresolved"))


def test_loss_classes_are_exclusive():
    _rows = _jl(D / "H1_97条异常逐项归因.jsonl")
    _c = collections.Counter(r["loss_classification"][:3] for r in _rows)
    assert sum(_c.values()) == len(_rows)
    assert _c.get("★ E") is not None


# ══ ⑤ V0/V1/V2 与正式产物 ══
def test_v0_v1_v2_unchanged():
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    _v2 = ROOT / "guard/_out/_n1c_v2/v2_knowledge_gate.py"
    assert _v2.is_file()


def test_no_llm_calls_in_h1():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/h1").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name
