# -*- coding: utf-8 -*-
"""V2-E4-R16 回归测试：V2-next 影子副本与原子 Gold v4。

覆盖：生产 V2 未改、V2-next 独立且为影子、合成回归无新增误判、
      根因取证结论、原子 v4 的证据补全与未决字段声明、历史版本未覆盖、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r16"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R16_V2next影子验证与原子Gold补证")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R13D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核")
R15D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R15_V2分类归因与原子Gold规范化")
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")

META = json.loads((OUTD / "r16_v2next_meta.json").read_text(encoding="utf-8"))
SYN = json.loads((OUTD / "r16_synth_regression.json").read_text(encoding="utf-8"))
ROOTC = json.loads((OUTD / "r16_rootcause.json").read_text(encoding="utf-8"))
V4 = json.loads((OUTD / "r16_v4.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 生产 V2 未改 =====
def test_production_v2_unchanged():
    assert hashlib.sha256(V2GATE.read_bytes()).hexdigest() == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")
    assert META["orig_sha256"] == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")


def test_v2next_is_separate_shadow_copy():
    _p = ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py"
    assert _p.is_file()
    assert _p.read_text(encoding="utf-8") != V2GATE.read_text(encoding="utf-8")
    _t = _p.read_text(encoding="utf-8")
    assert "不得接入生产路径" in _t
    assert hashlib.sha256(_p.read_bytes()).hexdigest() == META["next_sha256"]


def test_v2next_does_not_change_type_or_route_contract():
    """★ 未改知识类型定义、标签集合、资格契约或路由映射。"""
    _a = V2GATE.read_text(encoding="utf-8")
    _b = (ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py").read_text(
        encoding="utf-8")
    for _const in ("PROTOCOL_SYNTAX", "PROTOCOL_REGISTRY",
                   "PROTOCOL_DESCRIPTIVE", "NORMATIVE_RULE_CANDIDATE",
                   "NON_PROTOCOL_METADATA", "MIXED_OR_UNCERTAIN",
                   "ROUTE_RULE", "ROUTE_STRUCTURED", "ROUTE_METADATA",
                   "ROUTE_DESCRIPTIVE", "ROUTE_REVIEW"):
        assert _a.count(f"{_const} =") == _b.count(f"{_const} ="), _const


def test_v2next_route_of_unchanged():
    """★ route_of 函数体逐字未改。"""
    import re
    _a = V2GATE.read_text(encoding="utf-8")
    _b = (ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py").read_text(
        encoding="utf-8")

    def _fn(t):
        m = re.search(r"def route_of\(.*?(?=\ndef |\Z)", t, re.S)
        return m.group(0) if m else ""
    assert _fn(_a) == _fn(_b)


# ===== 回归结果 =====
def test_synthetic_regression_no_new_misjudgment():
    assert SYN["changed"] == 0
    assert SYN["v_ok"] == SYN["n_ok"]


def test_synthetic_covers_required_scenarios():
    _scenes = " ".join(r["场景"] for r in SYN["synthetic"])
    for _k in ("MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY",
               "跨行", "句尾", "小写", "引用", "元数据", "描述性"):
        assert _k in _scenes, _k


def test_root_cause_confirmed_on_8_samples():
    assert ROOTC["hypothesis_confirmed"] == 8
    assert ROOTC["sample_count"] == 15


def test_no_reverse_misjudgment_in_final_version():
    _dev = SYN["dev_set"]
    _brk = [c for c in _dev if c["★ V2 类型是否正确"]
            and not c["★ V2-next 类型是否正确"]]
    assert _brk == [], _brk


# ===== 原子 Gold v4 =====
def test_v4_has_6_records():
    _rows = _jl(DELIV / "R16_原子Gold新候选基线.jsonl")
    assert len(_rows) == 6
    assert V4["count"] == 6


def test_v4_two_records_have_deterministic_evidence():
    _rows = {r["gold_id"]: r for r in
             _jl(DELIV / "R16_原子Gold新候选基线.jsonl")}
    for _gid in ("SMTP-ATOM-X-smtp-rfc3461-04-a",
                 "SMTP-ATOM-X-smtp-rfc6531-01-a"):
        assert _rows[_gid].get("★ 人工复核原文"), _gid
        assert _rows[_gid].get("★ 证据补证来源"), _gid


def test_v4_declares_pending_fields():
    for _r in _jl(DELIV / "R16_原子Gold新候选基线.jsonl"):
        assert "主体" in _r["★ 未决字段"], _r["gold_id"]
        assert "动作" in _r["★ 未决字段"], _r["gold_id"]
        assert "对象" in _r["★ 未决字段"], _r["gold_id"]
        assert "未完整" in _r["★ 字段级 Gold 状态"], _r["gold_id"]


def test_field_confirmation_table_exists_and_empty():
    _p = DELIV / "R16_主体动作对象字段人工确认表.xlsx"
    assert _p.is_file()
    _wb = openpyxl.load_workbook(_p)
    _ws = _wb["待确认字段"]
    _hr = next(r for r in range(1, 15)
               if any("Gold ID" in str(_ws.cell(row=r, column=c).value or "")
                      for c in range(1, _ws.max_column + 1)))
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]
    _fill = [i for i, h in enumerate(_hdr, 1) if "待填" in h]
    assert len(_fill) == 5, _fill
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        for _ci in _fill:
            assert not str(_ws.cell(row=_r, column=_ci).value or "").strip()
    _wb.close()


def test_timezone_unavailable_recorded_not_assumed():
    _t = (DELIV / "R16_原子Gold审核元数据核验.md").read_text(encoding="utf-8")
    assert "timezone_unavailable" in _t
    assert "保留原始日期" in _t


def test_v4_does_not_claim_field_level_complete():
    _t = (DELIV / "R16_原子Gold_v4冻结前验收报告.md").read_text(encoding="utf-8")
    assert "不得宣称字段级 Gold 已完整冻结" in _t
    assert "分类级 Gold 已完整" in _t


# ===== 历史版本保护 =====
def test_all_historical_versions_unchanged():
    _h = {
        "R10_跨协议Gold冻结基线.jsonl":
            "bbce8979138605160f9af1c1c72a8c6c3b4750f31f808e9f03e2548f4b2a57eb",
        "R11_跨协议Gold冻结基线_v2候选.jsonl":
            "0f9ab8350da73359153473aeb9428001f45441828482583a1d0fed8f4f6cc38b",
        "R12_跨协议Gold冻结基线_v3候选.jsonl":
            "eb66b74533c93b931e58db73cf4b2c36268f6e2fd885042bcb9ee1cc3f4ea570",
    }
    for _n, _e in _h.items():
        assert hashlib.sha256((R10D / _n).read_bytes()).hexdigest() == _e, _n
    assert hashlib.sha256(
        (R13D / "R13_候选级评估冻结基线.jsonl").read_bytes()
    ).hexdigest() == (
        "36742b0955339edb4a1d08ef936bf1270e5c70262ea37180f5a11ff9cc960f0b")


def test_r3_and_r14_untouched():
    assert hashlib.sha256(
        (ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl")
        .read_bytes()).hexdigest() == (
        "694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a")
    for _n in ("R14_候选级分类评估结果.xlsx",
               "R14_分协议混淆矩阵与错误明细.xlsx",
               "R14_评估执行日志与环境哈希.md",
               "R14_一次性事后评估限制说明.md"):
        assert (ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R14_候选级分类一次性评估" / _n).is_file(), _n


def test_no_generalization_claim():
    _t = (DELIV / "R16_V2next最小修复源码差异报告.md").read_text(
        encoding="utf-8")
    assert "本轮未证明 V2-next 具有泛化能力" in _t
    assert "不应被表述为已解决全部 39 条" in _t


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R16_V2next最小修复源码差异报告.md",
               "R16_BCP14识别缺陷与合成回归.xlsx",
               "R16_已接触样本诊断性对照.xlsx",
               "R16_V2next独立验证准备与版本哈希.md",
               "R16_原子Gold审核元数据核验.md",
               "R16_两条来源证据补证报告.xlsx",
               "R16_主体动作对象字段人工确认表.xlsx",
               "R16_原子Gold_v4冻结前验收报告.md",
               "R16_原子Gold新候选基线.jsonl",
               "R16_版本保护与回归测试报告.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


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


def test_no_llm_calls_in_r16():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r16").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
