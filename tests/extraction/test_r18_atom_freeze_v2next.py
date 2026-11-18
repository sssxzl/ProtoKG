# -*- coding: utf-8 -*-
"""V2-E4-R18 回归测试：原子 Gold v5 冻结门禁与 V2-next 影子锁定。

覆盖：门禁 9/10 且未生成冻结基线、最小补充表仅 1 条、R16 错误描述已撤销、
      区分性回归的盲区已披露、预注册草案的隔离条件、历史版本未覆盖、生产隔离。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r18"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R18_原子Goldv5冻结与V2next验证准备")
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R13D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核")
R17D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R17_V2next定版核验与原子Gold字段回收")
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")
V2NEXT = ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py"

GATE = json.loads((OUTD / "r18_freeze_gate.json").read_text(encoding="utf-8"))
S2 = json.loads((OUTD / "r18_synth2.json").read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ===== 冻结门禁 =====
def test_gate_nine_of_ten_passed():
    _pass = sum(1 for c in GATE["gate"] if c["结果"] == "通过")
    assert _pass == 9
    assert GATE["all_pass"] is False


def test_open_item_is_strength_polarity():
    _open = [c for c in GATE["gate"] if c["结果"] != "通过"]
    assert len(_open) == 1
    assert _open[0]["#"] == 5
    assert "7826-05-1" in _open[0]["依据"]


def test_no_frozen_baseline_generated():
    """★ 门禁未全通过 ⇒ 不得生成冻结基线。"""
    assert not (DELIV / "R18_原子Gold_v5冻结基线.jsonl").exists()


def test_supplement_table_filled_by_reviewer_d():
    """★ 人工已回填（R19 接收）：★ 1 条填写完整，★ 审核者为 D，★ 日期含时区。"""
    _p = DELIV / "R18_原子Gold_v5强度极性最小补充确认表.xlsx"
    assert _p.is_file()
    _wb = openpyxl.load_workbook(_p)
    _ws = _wb["待补充确认"]
    _hr = next(r for r in range(1, 15)
               if any("Gold ID" in str(_ws.cell(row=r, column=c).value or "")
                      for c in range(1, _ws.max_column + 1)))
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]
    _fill = [i for i, h in enumerate(_hdr, 1) if "待填" in h]
    assert len(_fill) >= 5, _fill
    _i_who = next(i for i, h in enumerate(_hdr, 1) if "审核者" in h)
    _i_date = next(i for i, h in enumerate(_hdr, 1) if "审核日期" in h)
    _n = 0
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        _n += 1
        for _ci in _fill:
            assert str(_ws.cell(row=_r, column=_ci).value or "").strip(), _r
        assert str(_ws.cell(row=_r, column=_i_who).value or "").strip() == "D"
        _d = str(_ws.cell(row=_r, column=_i_date).value or "")
        assert "UTC" in _d or "Asia" in _d, _d
    _wb.close()
    assert _n == 1, _n


def test_exclusion_chain_recomputable():
    """★ v1/v2 各 8 条 → R12 排除 2 条 → v3/v5 各 6 条。"""
    _v1 = {r["gold_id"] for r in _jl(R10D / "R10_跨协议Gold冻结基线.jsonl")
           if r.get("gold_level") == "atom"}
    _v3 = {r["gold_id"] for r in _jl(R10D / "R12_跨协议Gold冻结基线_v3候选.jsonl")
           if r.get("gold_level") == "atom"}
    _v5 = {r["gold_id"] for r in _jl(R17D / "R17_原子Gold新候选基线.jsonl")}
    assert len(_v1) == 8
    assert len(_v3) == 6
    assert len(_v5) == 6
    assert _v3 == _v5
    assert _v1 - _v3 == {"SMTP-ATOM-X-smtp-rfc3461-04-b",
                         "SMTP-ATOM-X-smtp-rfc6531-01-b"}


# ===== R16 错误描述已撤销 =====
def test_r16_claims_revoked():
    _t = (DELIV / "R18_V2next影子版本冻结说明.md").read_text(encoding="utf-8")
    assert "予以撤销" in _t
    assert "不覆盖 R16 原始审计报告" in _t
    assert "实际改动登记" in _t
    assert "不得称为独立泛化提升" in _t


def test_four_changes_registered():
    _t = (DELIV / "R18_V2next影子版本冻结说明.md").read_text(encoding="utf-8")
    assert "4 条" in _t
    assert "未被当前方案修复" in _t


# ===== 区分性回归 =====
def test_discriminating_synthetic_no_new_misjudgment():
    assert S2["reverse"] == 0


def test_blind_spot_disclosed():
    _t = (DELIV / "R18_V2next区分性合成回归报告.md").read_text(encoding="utf-8")
    assert "空操作" in _t
    assert "D-01" in _t


# ===== 预注册草案 =====
def test_prereg_isolation_conditions():
    _t = (DELIV / "R18_新RFC独立验证预注册草案.md").read_text(encoding="utf-8")
    assert "未参与 R14～R17 的任何调试" in _t
    assert "不参与模型选择与调参" in _t
    assert "事前" in _t
    assert "预算申请" in _t


def test_prereg_discloses_blind_spot():
    _t = (DELIV / "R18_新RFC独立验证预注册草案.md").read_text(encoding="utf-8")
    assert "已知盲区" in _t
    assert "空操作" in _t


# ===== 影子版本锁定 =====
def test_v2next_hash_locked():
    _t = (DELIV / "R18_V2next影子版本冻结说明.md").read_text(encoding="utf-8")
    assert hashlib.sha256(V2NEXT.read_bytes()).hexdigest() in _t


def test_production_v2_unchanged():
    assert hashlib.sha256(V2GATE.read_bytes()).hexdigest() == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")


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
               "R14_评估执行日志与环境哈希.md"):
        assert (ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R14_候选级分类一次性评估" / _n).is_file(), _n


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R18_原子Gold_v5最终冻结验收报告.md",
               "R18_Gold版本谱系与差异报告.xlsx",
               "R18_V2next影子版本冻结说明.md",
               "R18_V2next区分性合成回归报告.md",
               "R18_新RFC独立验证预注册草案.md",
               "R18_版本哈希与回归测试报告.md",
               "R18_原子Gold_v5强度极性最小补充确认表.xlsx"):
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


def test_no_llm_calls_in_r18():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r18").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
