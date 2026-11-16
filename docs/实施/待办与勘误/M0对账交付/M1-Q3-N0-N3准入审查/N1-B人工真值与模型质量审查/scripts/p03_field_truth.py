# -*- coding: utf-8 -*-
"""★ N1-B 第 3 步：★ 七字段**等价性归一化** + **第二层：候选语义字段完整性**。

★ 用户指定的两层：
  第一层 = 规范义务**存在性**（★ 已在 p01 冻结为 truth_label）
  第二层 = 候选**语义字段完整性**（★ 本步骤）

★ 第二层五分类：
  ① 原文存在规范义务，候选字段全部正确
  ② 原文存在规范义务，但候选缺少条件或主体等关键字段
  ③ 原文存在规范义务，但候选部分字段错误
  ④ 原文并不支持候选所声称的规范义务
  ⑤ 证据不足，无法形成确定结论
★ ★ **valid_confirmed ≠ fully_supported**

★ 归一化要求（★ 用户给定）：
  · 允许无损的语义等价表达
  · 区分合法缺省与遗漏
  · 区分规范要求的主体和语法主语（★ 见下）
  · 区分肯定/否定极性与 strength（★ MUST+negative ≡ MUST NOT）
  · 区分跨句继承的条件和无条件义务
  · 无法确定的字段保持待审（★ **不输出该字段准确率**）
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")
WORK = OUTD / "work_utf8"

EMPTY = {"", "null", "none", "无", "n/a", "-", "na"}
FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception"]
# ★ 关键字段（★ 缺失即降级为第②类）
KEY_FIELDS = {"subject", "action", "object", "strength"}
# ★ RFC 8174：★ SHALL ≡ MUST；★ SHALL NOT ≡ MUST NOT（★ 强度等价）
_STR_EQ = [("shall not", "must not"), ("shall", "must"),
           ("required", "must"), ("recommended", "should"),
           ("not recommended", "should not")]
# ★ 极性词 ⇒ 归一到 positive/negative
_NEGWORDS = ("not", "never", "prohibit", "forbid")


def _is_empty(v):
    return str(v or "").strip().lower() in EMPTY


def _norm(f, v):
    """★ 字段等价性归一化（★ 无损等价才合并）。"""
    if _is_empty(v):
        return "<EMPTY>"
    _s = str(v).strip().lower()
    if f == "polarity":
        if _s in ("positive", "pos", "affirmative", "肯定"):
            return "positive"
        if _s in ("negative", "neg", "否定"):
            return "negative"
        for _w in _NEGWORDS:
            if _w in _s:
                return "negative"
        return _s
    _s = re.sub(r"[^a-z0-9 ]+", " ", _s)
    _s = re.sub(r"\s+", " ", _s).strip()
    if f == "strength":
        for _a, _b in _STR_EQ:
            _s = _s.replace(_a, _b)
        _s = re.sub(r"\b(must not|should not|may not|shall not)\b",
                    lambda m: m.group(1).replace("shall", "must"), _s)
        return _s.strip()
    # ★ 去冠词/虚词（★ 主体区分：★ **保留** 全部实词 ⇒ ★ 语法主语 vs 规范主体 仍可分辨）
    _s = re.sub(r"\b(the|a|an|of|in|for|to|is|are|be|its|it)\b", " ", _s)
    return re.sub(r"\s+", " ", _s).strip()


def _strength_polarity_key(strength, polarity):
    """★ 强度+极性的组合键（★ MUST+negative ≡ MUST NOT）。"""
    _st = _norm("strength", strength)
    _po = _norm("polarity", polarity)
    if _st == "<EMPTY>" or _po == "<EMPTY>":
        return f"{_st}|{_po}"
    if _po == "negative" and "not" not in _st:
        _st = _st + " not"
    return f"{_st}|{_po}"


def _read(p):
    return list(csv.DictReader(pathlib.Path(p).read_text(encoding="utf-8").splitlines()))


import csv  # noqa: E402

A = {r["sample_id"]: r for r in _read(WORK / "N1_盲审标注表_A.csv")}
B = {r["sample_id"]: r for r in _read(WORK / "N1_盲审标注表_B.csv")}
frozen = [json.loads(l) for l in
          (OUTD / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]

rows = []
for fr in frozen:
    _sid = fr["sample_id"]
    _a = A[_sid]
    _b = B[_sid]
    _truth = fr["★ ★ 冻结规范真值"]
    # ★ LLM 原始候选字段（★ 待核对的「候选」）
    _cand = {
        "subject": (_a.get("★ normative_subject（LLM 候选）") or "").strip(),
        "action": (_a.get("★ action（LLM 候选）") or "").strip(),
        "object": (_a.get("★ object（LLM 候选）") or "").strip(),
        "strength": (_a.get("★ strength（LLM 候选）") or "").strip(),
        # ★ 候选 polarity 取**推导列**（★ 原始候选无 polarity 字段 ⇒ 按 strength 推导）
        "polarity": (_a.get("★ 推导 polarity（★ 供核对）") or "").strip(),
        "condition": (_a.get("★ condition（LLM 候选，★ 原始无此字段）") or "").strip(),
        "exception": (_a.get("★ exception（LLM 候选，★ 原始无此字段）") or "").strip(),
    }
    _cand_entity = (_a.get("★ entity（LLM 候选）") or "").strip()
    # ★ 逐字段：A/B 归一化后是否等价
    _fa, _fb = {}, {}
    for f in FIELDS:
        _fa[f] = (_a.get(f"★ A:{f}") or "").strip()
        _fb[f] = (_b.get(f"★ B:{f}") or "").strip()
    _field_rows = []
    _resolved = {}
    for f in FIELDS:
        _na, _nb = _norm(f, _fa[f]), _norm(f, _fb[f])
        if _na == _nb:
            _state = "resolved"
            _val = _fa[f] if not _is_empty(_fa[f]) else _fb[f]
        else:
            # ★ 区分「合法缺省 vs 遗漏」与「实质不同」
            _a_empty, _b_empty = _na == "<EMPTY>", _nb == "<EMPTY>"
            if _a_empty != _b_empty:
                _state = "expressional_diff_empty_vs_filled"
            else:
                _state = "substantive_diff"
            _val = None
        # ★ 候选字段 vs 人工参考真值（★ 仅在字段已 resolve 时可比）
        _cand_n = _norm(f, _cand[f])
        _human_n = _norm(f, _val) if _val is not None else None
        _match = None
        if _state == "resolved" and _human_n is not None:
            if _cand_n == "<EMPTY>" and _human_n == "<EMPTY>":
                # ★ ★ 双方**均缺省** ⇒ ★ **不判 match**（★ 不算正确，★ 也不算错）
                #   ⇒ ★ 归类「双方均缺省（一致）」⇒ ★ **不进入准确率分母**
                _match = None
            elif _cand_n == "<EMPTY>" or _human_n == "<EMPTY>":
                # ★ ★ 候选**本身无此字段**而人工有值 ⇒ ★ **候选抽取缺失**
                #   ⇒ ★ **不可判**（★ 不判 mismatch，★ 避免把「候选缺字段」误算成模型错误）
                _match = None
            else:
                _match = (_cand_n == _human_n)
        _resolved[f] = {"state": _state, "human": _val,
                        "norm_a": _na, "norm_b": _nb,
                        "cand": _cand[f], "cand_norm": _cand_n,
                        "match": _match}
        _field_rows.append({"field": f, "A": _fa[f], "B": _fb[f],
                            "norm_A": _na, "norm_B": _nb,
                            "★ 归一化后状态": _state,
                            "★ LLM 候选": _cand[f],
                            "★ 候选是否匹配": _match})
    # ★ 第二层五分类
    _missing_key = [f for f in KEY_FIELDS
                    if _resolved[f]["cand_norm"] == "<EMPTY>"]
    _wrong = [f for f in KEY_FIELDS
              if _resolved[f]["match"] is False]
    _undecided = [f for f in FIELDS if _resolved[f]["state"] != "resolved"]
    if _truth == "valid_rejection":
        _cat = "④ 原文并不支持候选所声称的规范义务"
    elif _truth in ("pending_insufficient_evidence", "uncertain_requires_human"):
        _cat = "⑤ 证据不足，无法形成确定结论"
    elif _missing_key:
        _cat = "② 原文存在规范义务，但候选缺少条件或主体等关键字段"
    elif _wrong:
        _cat = "③ 原文存在规范义务，但候选部分字段错误"
    else:
        _cat = "① 原文存在规范义务，候选字段全部正确"
    rows.append({
        "sample_id": _sid, "分组": fr["分组"], "protocol": fr["protocol"],
        "document": fr["document"],
        "★ 第一层 规范义务存在性": _truth,
        "★ evidence_support": fr["★ 冻结 evidence_support"],
        "★ 第二层 候选字段完整性": _cat,
        "★ 关键字段缺失": _missing_key, "★ 关键字段错误": _wrong,
        "★ 字段级待仲裁字段": _undecided,
        "★ 候选实体": _cand_entity,
        "★ 字段明细": _field_rows,
    })

_c2 = collections.Counter(r["★ 第二层 候选字段完整性"] for r in rows)
_cf = collections.Counter(r["★ 第一层 规范义务存在性"] for r in rows)
# ★ 字段级：可判 vs 待仲裁
_field_state = {f: collections.Counter() for f in FIELDS}
_field_match = {f: {"match": 0, "mismatch": 0, "undetermined": 0} for f in FIELDS}
for r in rows:
    for fr_ in r["★ 字段明细"]:
        _field_state[fr_["field"]][fr_["★ 归一化后状态"]] += 1
        if fr_["★ 候选是否匹配"] is True:
            _field_match[fr_["field"]]["match"] += 1
        elif fr_["★ 候选是否匹配"] is False:
            _field_match[fr_["field"]]["mismatch"] += 1
        else:
            _field_match[fr_["field"]]["undetermined"] += 1

summary = {
    "★ 第一层 规范义务存在性": dict(_cf),
    "★ 第二层 候选字段完整性": dict(_c2),
    "★ 逐字段归一化状态": {f: dict(_field_state[f]) for f in FIELDS},
    "★ 逐字段候选匹配（★ 仅 resolved 字段可判）": {
        f: {**v,
            "★ 匹配率": (round(v["match"] / (v["match"] + v["mismatch"]), 4)
                       if (v["match"] + v["mismatch"]) else "N/A")}
        for f, v in _field_match.items()},
    "★ ★ 口径说明": [
        "★ **valid_confirmed ≠ fully_supported**",
        "★ 字段准确率**只对归一化后已 resolve 的字段**计算；★ 其余列为**字段级仲裁待办**",
        "★ 「A 填 null / B 填值」判为 `expressional_diff_empty_vs_filled` ⇒ ★ 不算实质分歧",
        "★ 极性：★ MUST + negative ≡ MUST NOT（★ 强度等价归一）",
        "★ 强度：★ SHALL ≡ MUST、SHALL NOT ≡ MUST NOT（★ RFC 8174）、REQUIRED≡MUST、RECOMMENDED≡SHOULD",
    ],
}
(OUTD / "N1-B_字段真值与第二层分类.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "N1-B_字段级明细.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

print("  ★ 第一层 规范义务存在性：", dict(_cf))
print("  ★ 第二层 候选字段完整性：")
for k, v in sorted(_c2.items()):
    print(f"      {k[:44]:46s} {v:3d}")
print("  ★ 逐字段候选匹配：")
for f in FIELDS:
    _v = _field_match[f]
    print(f"      {f:11s} match {_v['match']:2d}｜mismatch {_v['mismatch']:2d}"
          f"｜待仲裁 {_v['undetermined']:2d}｜归一化状态 {dict(_field_state[f])}")
print(f"\n  ⇒ {OUTD/'N1-B_字段真值与第二层分类.json'}")
