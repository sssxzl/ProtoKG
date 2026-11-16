# -*- coding: utf-8 -*-
"""★ N1-B 第 1 步：★ 人工真值**冻结** + A/B 一致性**独立复算**。

★ 复算项：
  · A/B `truth_label` 一致率与 **Cohen's Kappa**
  · A/B `evidence_support` 一致率
  · 仲裁表使用情况与仲裁后真值分布
  · ★ 仲裁者身份完整性（★ 「第三方复核」⇒ 身份/日期/独立性记录）
  · ★ **第一层：规范义务存在性**参考真值（★ 由仲裁后 truth_label 派生）
"""
import collections
import csv
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")
WORK = OUTD / "work_utf8"

TRUTH_ENUM = {"valid_confirmed", "valid_rejection",
              "pending_insufficient_evidence", "uncertain_requires_human"}
SUP_ENUM = {"supported", "partially_supported", "contradicted",
            "evidence_insufficient"}


def _read(p):
    return list(csv.DictReader(pathlib.Path(p).read_text(encoding="utf-8").splitlines()))


A = _read(WORK / "N1_盲审标注表_A.csv")
B = _read(WORK / "N1_盲审标注表_B.csv")
ARB = _read(WORK / "N1_仲裁表.csv")
_bm = {r["sample_id"]: r for r in B}
_am = {r["sample_id"]: r for r in A}
_arm = {r["sample_id"]: r for r in ARB}

ids = [r["sample_id"] for r in A]
assert len(ids) == 50 and len(set(ids)) == 50
assert set(ids) == set(_bm) == set(_arm)

# ══ A/B truth_label 一致 + Kappa ══
_pairs_t, _pairs_e = [], []
for _sid in ids:
    _a = (_am[_sid].get("★ A:truth_label") or "").strip()
    _b = (_bm[_sid].get("★ B:truth_label") or "").strip()
    _ea = (_am[_sid].get("★ A:evidence_support") or "").strip()
    _eb = (_bm[_sid].get("★ B:evidence_support") or "").strip()
    if _a and _b:
        _pairs_t.append((_a, _b))
    if _ea and _eb:
        _pairs_e.append((_ea, _eb))

_t_same = sum(1 for a, b in _pairs_t if a == b)
_e_same = sum(1 for a, b in _pairs_e if a == b)
_t_dis = [ids[i] for i, (a, b) in enumerate(_pairs_t) if a != b]


def _kappa(pairs):
    """★ Cohen's Kappa（★ 只用双标注都非空的样本）。"""
    n = len(pairs)
    if not n:
        return None
    _cats = sorted({x for p in pairs for x in p})
    _po = sum(1 for a, b in pairs if a == b) / n
    _ca = collections.Counter(a for a, _ in pairs)
    _cb = collections.Counter(b for _, b in pairs)
    _pe = sum((_ca[c] / n) * (_cb[c] / n) for c in _cats)
    if abs(1 - _pe) < 1e-12:
        return None
    return round((_po - _pe) / (1 - _pe), 4)


_kappa_t = _kappa(_pairs_t)
_kappa_e = _kappa(_pairs_e)

# ══ 仲裁表 ══
_arb_used = []
_arb_meta = []
for _sid in ids:
    _r = _arm[_sid]
    _has = bool((_r.get("★ 仲裁后 truth_label") or "").strip())
    _who = (_r.get("★ 仲裁者") or "").strip()
    _why = (_r.get("★ 仲裁理由") or "").strip()
    _when = (_r.get("★ 仲裁日期") or "").strip()
    if _has:
        _arb_used.append(_sid)
    if _who or _has:
        _arb_meta.append({"sample_id": _sid, "仲裁者": _who, "日期": _when,
                          "理由": _why[:120], "有结论": _has})

# ══ 仲裁后真值（★ 第一层：规范义务存在性参考真值）══
_frozen = []
for _sid in ids:
    _a = (_am[_sid].get("★ A:truth_label") or "").strip()
    _b = (_bm[_sid].get("★ B:truth_label") or "").strip()
    _arb_t = (_arm[_sid].get("★ 仲裁后 truth_label") or "").strip()
    if _arb_t:
        _final = _arb_t
        _src = "arbitration"
    elif _a and _b and _a == _b:
        _final = _a
        _src = "A=B"
    elif _a and _b:
        _final = None
        _src = "disagreement_unresolved"
    elif _a or _b:
        _final = _a or _b
        _src = "single_reviewer"
    else:
        _final = None
        _src = "unlabeled"
    _ea = (_am[_sid].get("★ A:evidence_support") or "").strip()
    _eb = (_bm[_sid].get("★ B:evidence_support") or "").strip()
    _es = _ea if (_ea and _ea == _eb) else (_ea or _eb)
    _frozen.append({
        "sample_id": _sid,
        "分组": _am[_sid].get("分组", ""),
        "protocol": _am[_sid].get("protocol", ""),
        "document": _am[_sid].get("document", ""),
        "★ A truth_label": _a, "★ B truth_label": _b,
        "★ 仲裁 truth_label": _arb_t,
        "★ ★ 冻结规范真值": _final,
        "★ 真值来源": _src,
        "★ A evidence_support": _ea, "★ B evidence_support": _eb,
        "★ 冻结 evidence_support": _es,
        "★ A 字段（供字段级仲裁）": {
            k: (_am[_sid].get(f"★ A:{k}") or "").strip()
            for k in ("subject", "action", "object", "strength", "polarity",
                      "condition", "exception")},
        "★ B 字段（供字段级仲裁）": {
            k: (_bm[_sid].get(f"★ B:{k}") or "").strip()
            for k in ("subject", "action", "object", "strength", "polarity",
                      "condition", "exception")},
        "★ A review_note": (_am[_sid].get("★ A:review_note") or "").strip(),
        "★ B review_note": (_bm[_sid].get("★ B:review_note") or "").strip(),
    })

_cf = collections.Counter(r["★ ★ 冻结规范真值"] for r in _frozen)
_csrc = collections.Counter(r["★ 真值来源"] for r in _frozen)
_ces = collections.Counter(r["★ 冻结 evidence_support"] for r in _frozen)
_unres = [r["sample_id"] for r in _frozen if r["★ 真值来源"] == "disagreement_unresolved"]

# ══ 仲裁者身份完整性（★ 用户要求补全或标记待核实）══
_ident = []
for _m in _arb_meta:
    _ident.append({
        "sample_id": _m["sample_id"], "★ 仲裁者标识": _m["仲裁者"],
        "★ 是否为具名人类审核者": bool(_m["仲裁者"]
                                 and _m["仲裁者"] not in ("第三方复核", "", "待定")),
        "★ 审核日期": _m["日期"] or "★ **缺失**",
        "★ 独立性记录": "★ **缺失**（★ 未提供与 A/B 的独立性声明）",
        "★ 结论": ("★ **身份/日期/独立性记录不完整 ⇒ 仲裁来源待核实**"
                 if not _m["仲裁者"] or _m["仲裁者"] == "第三方复核"
                 else "★ 标识非泛称，★ 但日期/独立性记录仍缺失"),
    })

summary = {
    "★ 输入": {"A": 50, "B": 50, "仲裁": 50, "★ sample_id 三方一致": True},
    "★ A/B truth_label": {
        "★ 双标注均非空的样本数": len(_pairs_t),
        "★ 一致数": _t_same,
        "★ 一致率": round(_t_same / len(_pairs_t), 4) if _pairs_t else None,
        "★ Cohen's Kappa": _kappa_t,
        "★ 分歧样本": _t_dis,
    },
    "★ A/B evidence_support": {
        "★ 双标注均非空的样本数": len(_pairs_e),
        "★ 一致数": _e_same,
        "★ 一致率": round(_e_same / len(_pairs_e), 4) if _pairs_e else None,
        "★ Cohen's Kappa": _kappa_e,
    },
    "★ 仲裁表": {
        "★ 使用仲裁的样本数": len(_arb_used),
        "★ 仲裁样本": _arb_used,
        "★ 仲裁者身份完整性": _ident,
        "★ ★ 审计完备性": "★ **仲裁来源待核实**（★ 标识为「第三方复核」，★ 日期与独立性记录缺失）",
    },
    "★ 冻结规范真值（★ 第一层：规范义务存在性）": {
        "★ 分布": dict(_cf),
        "★ 真值来源分布": dict(_csrc),
        "★ 未解决分歧": _unres,
        "★ 冻结 evidence_support 分布": dict(_ces),
    },
}
(OUTD / "N1-B_人工真值冻结.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "N1-B_冻结人工真值.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in _frozen) + "\n",
    encoding="utf-8")

print("  ★ A/B truth_label：一致 %d/%d = %.4f｜Kappa = %s"
      % (_t_same, len(_pairs_t), _t_same / len(_pairs_t), _kappa_t))
print("  ★ 分歧样本：", _t_dis)
print("  ★ A/B evidence_support：一致 %d/%d = %.4f｜Kappa = %s"
      % (_e_same, len(_pairs_e), _e_same / len(_pairs_e), _kappa_e))
print("  ★ 仲裁使用样本：", _arb_used)
print("  ★ 冻结真值分布：", dict(_cf))
print("  ★ 真值来源：", dict(_csrc))
print("  ★ 冻结 evidence_support：", dict(_ces))
print("  ★ 未解决分歧：", _unres)
print("  ★ 仲裁者身份：", _ident[:3])
print(f"\n  ⇒ {OUTD/'N1-B_人工真值冻结.json'}")
