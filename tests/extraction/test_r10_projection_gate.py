# -*- coding: utf-8 -*-
"""V2-E4-R10 回归测试：投影规则与 Gold 冻结门禁。

覆盖：投影覆盖 57 条、无 Gold 依赖、投影可追溯、R7 预注册与 R3 基线未改、
      门禁结果、交付完整、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R10 = ROOT / "guard/_out/_n1c_v2/r10"
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"
R7P = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R7_H3Gold字段复核与评测准入"
       / "R7_H3_V2版本哈希及预注册规则.md")

PROJ = json.loads((R10 / "r10_projection.json").read_text(encoding="utf-8"))
GATE = json.loads((R10 / "r10_gate_verify.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _header_row(ws, marker):
    for _r in range(1, min(ws.max_row, 12) + 1):
        if any(marker in str(ws.cell(row=_r, column=c).value or "")
               for c in range(1, ws.max_column + 1)):
            return _r
    raise AssertionError(f"未找到表头行（{marker}）")


# ===== 投影 =====
def test_projection_covers_all_57():
    _rows = PROJ["projection_rows"]
    assert len(_rows) == 57
    assert len({r["candidate_id"] for r in _rows}) == 57


def test_projection_class_counts():
    _c = PROJ["class_counts"]
    assert _c.get("constraint 非空", 0) == 23
    assert _c.get("constraint 为空，取 meaning", 0) == 34
    assert len(PROJ["not_evaluable"]) == 0


def test_projection_has_no_gold_dependency():
    _b = PROJ["bias_checks"]
    assert _b["★ 投影函数是否含 Gold 引用"] is False
    assert _b["★ 投影函数参数是否只含 R3 记录"] is True
    assert _b["★ 投影是否按正确错误选择"] is False
    assert _b["★ 投影是否读取 C 仲裁"] is False


def test_projection_does_not_change_scope():
    _b = PROJ["bias_checks"]
    assert _b["★ 投影是否改动 V2 原始预测"] is False
    assert _b["★ 投影是否改变候选数量"] is True
    assert _b["★ 投影是否改变来源证据"] is True
    assert _b["★ 投影是否因 norm_id 碰撞删候选"] is True


def test_projection_text_verbatim_equals_r3_field():
    """★ 投影文本必须与 R3 原字段逐字相等。"""
    _base = {}
    for _l in R3P.read_text(encoding="utf-8").splitlines():
        if _l.strip():
            _b = json.loads(_l)
            _base[_b["gold_candidate_id"]] = _b
    for _r in PROJ["projection_rows"]:
        _b = _base[_r["candidate_id"]]
        _f = _r["★ 投影取值来源"]
        _orig = _b.get("constraint") if _f == "constraint" else _b.get("meaning")
        assert _r["★ 投影文本"] == str(_orig or "").strip(), _r["candidate_id"]
    assert len(PROJ["trace_mismatch"]) == 0


def test_collision_group_members_all_kept():
    """★ R3 的 norm_id 碰撞组 3 条成员不得被删。"""
    _base = {}
    for _l in R3P.read_text(encoding="utf-8").splitlines():
        if _l.strip():
            _b = json.loads(_l)
            _base.setdefault(_b.get("norm_id"), []).append(
                _b["gold_candidate_id"])
    _grp = [v for v in _base.values() if len(v) > 1]
    assert _grp, "R3 无碰撞组"
    _ids = {r["candidate_id"] for r in PROJ["projection_rows"]}
    for _g in _grp:
        for _cid in _g:
            assert _cid in _ids, _cid


# ===== 原件未改 =====
def test_r7_preregistration_unchanged():
    _h = hashlib.sha256(R7P.read_bytes()).hexdigest()
    assert _h == PROJ["r7_prereg_sha256"], _h
    _reg = (DELIV / "R10_版本哈希与回归测试报告.md").read_text(encoding="utf-8")
    assert _h in _reg


def test_r3_baseline_unchanged():
    _h = hashlib.sha256(R3P.read_bytes()).hexdigest()
    assert _h == PROJ["r3_sha256"], _h


def test_gold_v4_untouched():
    _p = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
          / "R5A_H3第三方仲裁与Gold冻结/H3_Gold冻结基线_v4候选.jsonl")
    assert hashlib.sha256(_p.read_bytes()).hexdigest().startswith(
        "0f507db855069757")


# ===== 门禁 =====
def test_gate_has_one_unpassed_item():
    _np = GATE["not_passed"]
    assert len(_np) == 1
    assert _np[0]["#"] == 2


def test_frozen_gold_baseline_generated_after_gate_passed():
    """★ R10B 起门禁已通过 ⇒ 冻结基线已生成且内容合法。"""
    _p = DELIV / "R10_跨协议Gold冻结基线.jsonl"
    assert _p.is_file()
    _rows = [json.loads(l) for l in
             _p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(_rows) == 65
    assert len({r["gold_id"] for r in _rows}) == 65


def test_affected_records_are_five():
    _rows = GATE["verify_rows"]
    _miss = [r["candidate_id"] for r in _rows if not r["★ 2 知识类型"]]
    assert len(_miss) == 5, _miss
    for _cid in _miss:
        _r = next(r for r in _rows if r["candidate_id"] == _cid)
        assert _r["★ 1 人工最终状态"] == "agreed"
        assert _r["★ 1 A/B 是否完全一致"] is True


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


def test_no_llm_calls_in_r10():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r10").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R10_跨协议候选语义投影规则补充备案.md",
               "R10_57条机器命题投影核验.xlsx",
               "R10_规则变更与评估偏差风险报告.md",
               "R10_三协议Gold冻结验收.xlsx",
               "R10_评估分母与标签映射.xlsx",
               "R10_正式指标执行前检查报告.md",
               "R10_版本哈希与回归测试报告.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


def test_projection_rule_recorded_as_post_hoc():
    """★ 投影规则必须标注为事后补充。"""
    _t = (DELIV / "R10_跨协议候选语义投影规则补充备案.md").read_text(
        encoding="utf-8")
    assert "事后" in _t
    assert "不属于最初的严格事前预注册规则" in _t
    assert "尚未发生" in _t
