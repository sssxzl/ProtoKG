# -*- coding: utf-8 -*-
"""V2-E4-R13 回归测试：审核者身份核验、候选级分层冻结、评估脚本自检。

覆盖：R11 独立性不足的判定、4 条待核验数量、候选级基线 57 条且不含原子、
      历史版本未覆盖、评估脚本合成样本自检通过、原件与生产隔离。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import sys

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R11_跨协议Gold原子边界复核与评估准入")
OUTD = ROOT / "guard/_out/_n1c_v2/r13"
R10D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R10_跨协议评估规则补充与Gold冻结")
R13D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核")
R3P = ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl"
REVIEW = DELIV / "R11_SC05SC06原子知识边界复核.xlsx"

FROZEN = R13D / "R13_候选级评估冻结基线.jsonl"
EVAL = OUTD / "eval_candidate_level.py"

SHA_V1 = "bbce8979138605160f9af1c1c72a8c6c3b4750f31f808e9f03e2548f4b2a57eb"
SHA_V2 = "0f9ab8350da73359153473aeb9428001f45441828482583a1d0fed8f4f6cc38b"


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _header_row(ws, marker):
    for _r in range(1, min(ws.max_row, 20) + 1):
        if any(marker in str(ws.cell(row=_r, column=c).value or "")
               for c in range(1, ws.max_column + 1)):
            return _r
    raise AssertionError(f"未找到表头行（{marker}）")


# ===== 审核者身份 =====
def test_identity_concluded_independent_requirement_not_met():
    _d = _j(OUTD / "r13_identity_evid.json")
    _i = _d["identity"]
    assert "不满足" in _i["★ 是否满足独立审核要求"]
    assert "不可" in _i["★ 匿名编号不同即可推定独立"]
    assert "同一人" in _i["★ R11 审核者是否为 R4A 的 A"]


def test_identity_evidence_lists_rcpt_origin():
    _d = _j(OUTD / "r13_identity_evid.json")
    _txt = " ".join(_d["identity"]["★ 决定性旁证"])
    assert "RCPT" in _txt
    assert len(_d["identity"]["★ 决定性旁证"]) >= 3


def test_reviewer_spectrum_lists_f_and_c():
    _d = _j(OUTD / "r13_identity_evid.json")
    _who = " ".join(x["审核者"]
                    for x in _d["identity"]["★ 审核者编号谱系"])
    for _w in ("A", "B", "C", "D", "F"):
        assert _w in _who, _w


# ===== 待核验数量 =====
def test_four_pending_atoms():
    _d = _j(OUTD / "r13_identity_evid.json")
    assert len(_d["evidence"]) == 4
    _ids = sorted(e["gold_id"] for e in _d["evidence"])
    assert _ids == ["RTSP-ATOM-X-rtsp-rfc7826-03-1",
                    "RTSP-ATOM-X-rtsp-rfc7826-05-1",
                    "SMTP-ATOM-X-smtp-rfc3461-03-1",
                    "SMTP-ATOM-X-smtp-rfc8098-03-1"], _ids


# ===== 候选级冻结 =====
def test_frozen_baseline_has_57_candidates_only():
    _rows = _jl(FROZEN)
    assert len(_rows) == 57
    assert all(r["gold_level"] == "candidate" for r in _rows)


def test_frozen_baseline_ids_unique():
    _ids = [r["gold_id"] for r in _jl(FROZEN)]
    assert len(_ids) == len(set(_ids))


def test_frozen_baseline_matches_r3_candidate_set():
    _r3 = {json.loads(l)["gold_candidate_id"]
           for l in R3P.read_text(encoding="utf-8").splitlines() if l.strip()}
    _f = {r["candidate_id"] for r in _jl(FROZEN)}
    assert len(_f) == 57
    assert _f == _r3


def test_frozen_baseline_enumerations_legal():
    _K = {"non_protocol_metadata", "protocol_syntax",
          "protocol_registry_or_enumeration", "protocol_descriptive_semantics",
          "normative_rule_candidate", "mixed_or_uncertain"}
    _E = {"eligible", "ineligible", "uncertain", "not_applicable"}
    _R = {"rule_channel", "structured_channel", "metadata_channel",
          "descriptive_channel", "pending_review", "not_applicable"}
    for _r in _jl(FROZEN):
        assert _r["knowledge_kind"] in _K, _r["gold_id"]
        assert _r["rule_eligibility"] in _E, _r["gold_id"]
        assert _r["target_route"] in _R, _r["gold_id"]


def test_frozen_baseline_per_protocol_counts():
    _c = collections.Counter(r["protocol"] for r in _jl(FROZEN))
    assert _c["SIP"] == 27
    assert _c["RTSP"] == 7
    assert _c["SMTP"] == 23


def test_frozen_baseline_has_human_source():
    for _r in _jl(FROZEN):
        assert _r.get("★ 人工来源"), _r["gold_id"]
        assert _r.get("★ 仲裁者"), _r["gold_id"]


# ===== 历史版本保护 =====
def test_v1_and_v2_unchanged():
    assert hashlib.sha256(
        (R10D / "R10_跨协议Gold冻结基线.jsonl").read_bytes()
    ).hexdigest() == SHA_V1
    assert hashlib.sha256(
        (R10D / "R11_跨协议Gold冻结基线_v2候选.jsonl").read_bytes()
    ).hexdigest() == SHA_V2


def test_r12_v3_still_candidate_not_frozen():
    for _r in _jl(R10D / "R12_跨协议Gold冻结基线_v3候选.jsonl"):
        assert "v3 候选" in _r.get("★ 版本", ""), _r["gold_id"]


# ===== 评估脚本 =====
def test_eval_script_selfcheck_passes():
    sys.path.insert(0, str(OUTD))
    import importlib
    import eval_candidate_level
    importlib.reload(eval_candidate_level)
    _r = eval_candidate_level.selfcheck()
    assert _r["★ 合成样本条数"] == 4
    assert _r["★ 完全匹配"] == 3
    assert abs(_r["★ 准确率"] - 0.75) < 1e-9


def test_eval_script_does_not_touch_formal_data():
    """★ 脚本本身不应包含本批候选 ID（★ 正式评分不得预置）。"""
    _t = EVAL.read_text(encoding="utf-8")
    for _cid in ("X-sip-rfc", "X-rtsp-rfc", "X-smtp-rfc"):
        assert _cid not in _t, _cid


def test_eval_script_declares_posthoc():
    _t = EVAL.read_text(encoding="utf-8")
    assert "事后" in _t
    assert "R10-P1" in _t


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R13_R12审核者身份与日期核验报告.md",
               "R13_4条剩余原子知识证据核验.xlsx",
               "R13_必要人工补充复核表.xlsx",
               "R13_57条候选级Gold冻结验收报告.md",
               "R13_候选级评估冻结基线.jsonl",
               "R13_原子知识Gold待确认状态及版本差异.xlsx",
               "R13_评估脚本冻结与SHA256报告.md"):
        _p = R13D / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


def test_supplement_review_has_empty_fill_columns():
    _wb = openpyxl.load_workbook(R13D / "R13_必要人工补充复核表.xlsx")
    _ws = _wb["待补充确认"]
    _hr = _header_row(_ws, "Gold ID")
    _hdr = [str(_ws.cell(row=_hr, column=c).value or "").strip()
            for c in range(1, _ws.max_column + 1)]
    _fill = [i for i, h in enumerate(_hdr, 1) if "待填" in h]
    assert len(_fill) == 13, _fill
    for _r in range(_hr + 1, _ws.max_row + 1):
        if not str(_ws.cell(row=_r, column=1).value or "").strip():
            continue
        for _ci in _fill:
            assert not str(_ws.cell(row=_r, column=_ci).value or "").strip()
    _wb.close()


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


def test_no_llm_calls_in_r13():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r13").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
