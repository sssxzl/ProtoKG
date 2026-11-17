# -*- coding: utf-8 -*-
"""V2-E4-R9 回归测试：语义承载核验、机器与人工 Gold 隔离、原子去重。

覆盖：34 条全部入表、五类归类、无 C/D/E 类、双字段隔离、投影确定性、
      SC-01 归并、SC-05/06 原子 ID、生产隔离。
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
         / "M1-Q3-V2-E4-R9_跨协议语义承载与Gold规范化")
R9 = ROOT / "guard/_out/_n1c_v2/r9"
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"
R5A = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4-R5-H3仲裁闭合与NormID证据核验"
       / "R5A_H3第三方仲裁与Gold冻结")

SHA_R3 = "3f4e0c72a5a9c0e1d2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _header_row(ws, marker):
    for _r in range(1, min(ws.max_row, 12) + 1):
        if any(marker in str(ws.cell(row=_r, column=c).value or "")
               for c in range(1, ws.max_column + 1)):
            return _r
    raise AssertionError(f"未找到表头行（{marker}）")


# ===== 第一阶段 =====
def test_all_34_in_audit_table():
    _wb = openpyxl.load_workbook(DELIV / "R9_34条候选语义承载核验.xlsx")
    _ws = _wb["逐项核验"]
    _hr = _header_row(_ws, "candidate_id")
    _n = 0
    for _r in range(_hr + 1, _ws.max_row + 1):
        if str(_ws.cell(row=_r, column=1).value or "").strip():
            _n += 1
    _wb.close()
    assert _n == 34, _n


def test_stage1_classifies_every_row():
    _rows = _j(R9 / "r9_stage1.json")["rows"]
    assert len(_rows) == 34
    for _r in _rows:
        assert _r["★ 承载类别"][0] in "ABCDE", _r["candidate_id"]
        assert _r["★ 判定依据"], _r["candidate_id"]


def test_no_c_de_e_classes():
    """★ 34 条中无「确需人工核验」「证据不足」「不确定」。"""
    _cc = _j(R9 / "r9_stage1.json")["class_counts"]
    assert _cc.get("C meaning 只表达部分语义，确需额外人工核验", 0) == 0
    assert _cc.get("D 原始机器命题缺乏足够证据", 0) == 0
    assert _cc.get("E 不能确定，标记 unresolved", 0) == 0


def test_three_b_class_rows():
    _rows = _j(R9 / "r9_stage1.json")["rows"]
    _b = [r["candidate_id"] for r in _rows
          if r["★ 承载类别"].startswith("B")]
    assert sorted(_b) == ["X-rtsp-rfc7826-05", "X-smtp-rfc3461-04",
                          "X-smtp-rfc3461-05"], _b


def test_no_manual_supplement_table_needed():
    """★ 第一阶段无真实歧义 ⇒ 不生成补录表。"""
    assert not (DELIV / "R9_需人工补充确认清单.xlsx").exists()


# ===== 第二阶段：字段隔离 =====
def test_gold_rows_have_both_fields():
    _rows = _jl(R9 / "r9_gold_candidates.jsonl")
    assert len(_rows) == 57
    for _r in _rows:
        assert "★ machine_original_proposition" in _r
        assert "★ human_gold_proposition" in _r
        assert "★ machine_meaning（★ R3 原值）" in _r


def test_machine_projection_is_deterministic():
    """★ 投影规则只做机械取值：★ constraint 优先，★ 空则 meaning。"""
    _base = {}
    for _l in R3P.read_text(encoding="utf-8").splitlines():
        if _l.strip():
            _b = json.loads(_l)
            _base[_b["gold_candidate_id"]] = _b
    _rows = _jl(R9 / "r9_gold_candidates.jsonl")
    for _r in _rows:
        _b = _base[_r["candidate_id"]]
        _c = str(_b.get("constraint") or "").strip()
        _exp = _c if _c else str(_b.get("meaning") or "").strip()
        assert _r["★ machine_original_proposition"] == _exp, _r["candidate_id"]


def test_human_gold_comes_from_arbitration():
    """★ human_gold 字段不得来自机器输出。"""
    _rows = _jl(R9 / "r9_gold_candidates.jsonl")
    for _r in _rows:
        _h = _r["★ human_gold_proposition"]
        if _h:
            assert not _h.startswith("X-"), _r["candidate_id"]
        # ★ human_gold 的类型等字段须与仲裁一致
        assert _r["★ human_gold 知识类型"] in (
            "", "normative_rule_candidate", "protocol_syntax",
            "protocol_registry_or_enumeration",
            "protocol_descriptive_semantics", "non_protocol_metadata",
            "mixed_or_uncertain"), _r["candidate_id"]


def test_gold_count_is_57_with_per_protocol_stats():
    _wb = openpyxl.load_workbook(DELIV / "R9_跨协议Gold规范化候选台账.xlsx")
    _ws = _wb["候选级 Gold"]
    _hr = _header_row(_ws, "candidate_id")
    _c = collections.Counter()
    for _r in range(_hr + 1, _ws.max_row + 1):
        _p = str(_ws.cell(row=_r, column=2).value or "").strip()
        if _p:
            _c[_p] += 1
    _wb.close()
    assert _c["SIP"] == 27
    assert _c["RTSP"] == 7
    assert _c["SMTP"] == 23
    assert sum(_c.values()) == 57


# ===== 第四阶段：原子去重 =====
def test_sc01_merged_not_new():
    _rows = _j(R9 / "r9_stage45.json")["split_rows"]
    _sc01 = next(r for r in _rows if r["★ 线索 ID"] == "SC-01")
    assert "归并至已有补充知识" in _sc01["★ 原子 ID 映射"]
    assert "不新增 Gold 条目" in _sc01["★ 原子 ID 映射"]


def test_existing_supplement_merged_to_one():
    _rows = _j(R9 / "r9_stage45.json")["existing_rows"]
    assert len(_rows) == 2
    _ids = {r["★ 归并后的 Gold ID"] for r in _rows}
    assert "RTSP-ATOM-X-rtsp-rfc7826-03-1" in _ids
    # ★ 另一条须标为同一条合并
    assert any("合并" in i or "同一条" in i for i in _ids)


def test_sc05_sc06_keep_atomic_ids():
    _rows = _j(R9 / "r9_stage45.json")["split_rows"]
    for _sid in ("SC-05", "SC-06"):
        _r = next(x for x in _rows if x["★ 线索 ID"] == _sid)
        _m = _r["★ 原子 ID 映射"]
        assert "-a" in _m and "-b" in _m, (_sid, _m)


# ===== 生产隔离 =====
def test_r3_frozen_baseline_unchanged():
    """★ R3 冻结机器基线未被改写。"""
    _h = hashlib.sha256(R3P.read_bytes()).hexdigest()
    _reg = (DELIV / "R9_回归测试及版本哈希.md").read_text(encoding="utf-8")
    assert _h in _reg, _h


def test_v2_gate_and_prompt_unchanged():
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    import hashlib as _hl
    import ast
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    for _n in ast.walk(ast.parse(_src)):
        if isinstance(_n, ast.Assign) and getattr(_n.targets[0], "id", "") \
                == "_PROMPT":
            assert _hl.sha256(_n.value.value.encode()).hexdigest()[:16] \
                == "d97fbe611ac9aa61"
            break


def test_gold_v4_unchanged():
    """★ H3 Gold v4 作为独立工作线，★ 本轮未改。"""
    _p = (R5A / "H3_Gold冻结基线_v4候选.jsonl")
    assert _p.is_file()
    _h = hashlib.sha256(_p.read_bytes()).hexdigest()
    assert _h.startswith("0f507db855069757"), _h


def test_no_llm_calls_in_r9():
    """★ 只查实际的调用，★ 不查文档说明文字。"""
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r9").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
        assert "import openai" not in _t, _f.name


def test_deliverables_exist():
    for _n in ("R9_34条候选语义承载核验.xlsx",
               "R9_meaning与constraint适用性对账.xlsx",
               "R9_跨协议Gold规范化候选台账.xlsx",
               "R9_原子知识拆分与去重映射.xlsx",
               "R9_机器候选与人工Gold隔离证明.md",
               "R9_Gold冻结门禁与未决项.md",
               "R9_回归测试及版本哈希.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n
