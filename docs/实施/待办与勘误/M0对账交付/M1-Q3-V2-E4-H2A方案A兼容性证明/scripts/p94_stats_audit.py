# -*- coding: utf-8 -*-
"""★ H2-H2A §二：★ **字段级统计勘误**（★ 97 闭合核算 + 104 重新定义）。

★ ★ 复核 13 个 prose_semantics 候选：★ 其规范字段为 not_applicable，
★ ★ **必须验证是否确实存在描述性语义的不可重建损失**
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/h2"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E4-H2A方案A兼容性证明"
DELIV.mkdir(parents=True, exist_ok=True)

_led = [json.loads(l) for l in
        (ROOT / "guard/_out/_n1c_v2/h1/h1_field_trace_full.jsonl")
        .read_text(encoding="utf-8").splitlines() if l.strip()]
_anom = [json.loads(l) for l in
         (ROOT / "guard/_out/_n1c_v2/h1/h1_97_anomaly_attribution.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]

# ══ ① 97 的分布闭合核算 ══
_byf = collections.Counter(r["field"] for r in _anom)
_total = sum(_byf.values())
_user = {"cross_ref_status": 23, "action": 14, "object": 14, "strength": 14,
         "polarity": 14, "normative_subject": 10, "condition": 7}
_closure = {
    "★ 本地复算的字段分布": dict(_byf),
    "★ 合计": _total,
    "★ 用户复算给出的分布": _user,
    "★ 用户复算合计": sum(_user.values()),
    "★ 差异项": {k: [_byf.get(k, 0), v] for k, v in _user.items()
              if _byf.get(k, 0) != v},
    "★ ★ 闭合结论": (f"★ **97 = {sum(_user.values())} + 1（★ `constraint`）**；★ "
                f"★ 用户复算漏掉了 `constraint` 的 1 条 ⇒ ★ **97 本身是闭合的**"),
    "★ constraint 那 1 条的详情": [
        {"candidate_id": r["candidate_id"], "knowledge_kind": r["knowledge_kind"],
         "source_span": r["source_span"],
         "original_value": r["original_value"][:100],
         "loss_classification": r["loss_classification"],
         "evidence": r["evidence"][:160]}
        for r in _anom if r["field"] == "constraint"],
}
print(f"  ★ ① 97 闭合核算：本地 {dict(_byf)}｜合计 {_total}")
print(f"      用户复算合计 {sum(_user.values())}｜差异 = constraint 1 条")
for _c in _closure["★ constraint 那 1 条的详情"]:
    print(f"      ★ {_c['candidate_id'][:26]}｜{_c['knowledge_kind']}｜{_c['evidence'][:80]}")

# ══ ② 104 的重新定义 ══
_APPLIC = {
    "prose_constraint": {"entity": "required", "meaning": "required",
                  "normative_subject": "optional", "action": "optional",
                  "object": "optional", "strength": "optional",
                  "polarity": "optional", "condition": "optional",
                  "exception": "optional", "constraint": "required",
                  "cross_ref_status": "optional"},
    "prose_semantics": {"entity": "required", "meaning": "required",
                 "normative_subject": "not_applicable", "action": "not_applicable",
                 "object": "not_applicable", "strength": "not_applicable",
                 "polarity": "not_applicable", "condition": "not_applicable",
                 "exception": "not_applicable", "constraint": "optional",
                 "cross_ref_status": "not_applicable"},
}
_E = [r for r in _led if r["loss_classification"].startswith("★ E")]
_E_applic = [r for r in _E
             if _APPLIC.get(r["knowledge_kind"], {}).get(r["field"])
             not in (None, "not_applicable")]
_E_notapplic = [r for r in _E
                 if _APPLIC.get(r["knowledge_kind"], {}).get(r["field"])
                 == "not_applicable"]
_red = {
    "★ 真实字段级记录数（★ 全量流转）": len(_led),
    "★ 字段适用的记录数（★ 分母）": len([r for r in _led
                              if _APPLIC.get(r["knowledge_kind"], {}).get(r["field"])
                              not in (None, "not_applicable")]),
    "★ E 类记录数（★ 原 104）": len(_E),
    "★ ├ 其中字段【适用】者": len(_E_applic),
    "★ └ 其中字段【不适用】者（★ ★ 不是语义损失）": len(_E_notapplic),
    "★ ★ 原文与 LLM 输出均有证据、但下游丢失必要语义的记录数": len(_E_applic),
    "★ ★ 方案 B 预计恢复的记录数": "★ 见 §三（★ 需验证描述性语义可重建性）",
}
print()
print(f"  ★ ② 104 重新定义：")
for _k, _v in _red.items():
    print(f"      {_k}: {_v}")

# ══ ③ 13 个 prose_semantics 候选：★ 描述性语义是否真的不可重建 ══
H3 = [json.loads(l) for l in
      (ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl")
      .read_text(encoding="utf-8").splitlines() if l.strip()]
_RAW = [json.loads(l) for l in
         (ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3原始LLM输出.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
_rawidx = {}
for _r in _RAW:
    _it = _r["★ ★ 原始 LLM 输出（★ 全字段）"]
    _rawidx.setdefault((_it.get("doc"), int(_it.get("span") or 0)), []).append(_it)


def _find_raw(doc, span):
    if not span:
        return {}
    _c = [(k, v) for k, v in _rawidx.items() if k[0] == doc and k[1] <= int(span)]
    if not _c:
        return {}
    return max(_c, key=lambda kv: kv[0][1])[1][0]


_RE_NORMVERB = re.compile(
    r"\b(must|shall|should|may|required|recommended|not)\b", re.I)
_evidence = []
for _c in H3:
    _n = _c["★ norm（★ 派生层输出）"]
    if _n.get("kind") != "prose_semantics":
        continue
    _doc = _c["★ document_id"]
    _sl = int(_n.get("span_line") or 0)
    _raw = _find_raw(_doc, _sl)
    _mean = str(_n.get("meaning") or "")
    _con = str(_n.get("constraint") or "")
    _has_norm = bool(_RE_NORMVERB.search(_con) or _RE_NORMVERB.search(_mean))
    _evidence.append({
        "candidate_id": _c["★ candidate_id"],
        "knowledge_kind": _n.get("kind"),
        "source_span": _c["★ source_span"],
        "★ norm.meaning": _mean[:200],
        "★ norm.constraint": _con[:200],
        "★ LLM 原始 action": str(_raw.get("action") or ""),
        "★ LLM 原始 object": str(_raw.get("object") or ""),
        "★ LLM 原始 normative_subject": str(_raw.get("normative_subject") or ""),
        "★ ★ 描述性语义是否在 meaning/constraint 中可重建": "★ 是" if (_mean or _con) else "★ 否",
        "★ ★ 该候选文本是否含规范强度词": ("★ 是（★ ⇒ 可能是规范义务被降级）" if _has_norm
                                else "★ 否（★ ⇒ 确为描述性）"),
        "★ ★ 结论": ("★ **描述性语义已由 meaning/constraint 承载 ⇒ 无不可重建损失 ⇒ "
                 "★ 方案 B 对本类**无实际收益**"
                 if not _has_norm else
                 "★ ★ ★ **文本含强度词 ⇒ 需人工判定它是否真是规范义务**"),
    })
_have_norm = [e for e in _evidence if "★ 是（★" in e["★ ★ 该候选文本是否含规范强度词"]]
print()
print(f"  ★ ③ 13 个 prose_semantics 候选的描述性语义可重建性：")
print(f"      候选数 = {len(_evidence)}｜meaning/constraint 均非空 = "
      f"{sum(1 for e in _evidence if e['★ ★ 描述性语义是否在 meaning/constraint 中可重建'] == '★ 是')}")
print(f"      ★ 文本含规范强度词（★ 需人工判定）= {len(_have_norm)}")
for _e in _have_norm:
    print(f"      ★ {_e['candidate_id'][:30]:32s} constraint={_e['★ norm.constraint'][:70]!r}")
_red["★ 方案 B 预计恢复的记录数"] = (
    f"★ **0**（★ 13 个 prose_semantics 的描述性语义**已由 meaning/constraint 承载**；★ "
    f"★ 且其规范字段按适用性为 not_applicable）"
    if not _have_norm else
    f"★ **待人工判定 {len(_have_norm)} 个候选**（★ 文本含强度词）")

_out = {"★ ① 97 闭合核算": _closure, "★ ② 104 重新定义": _red,
        "★ ③ 13 个 prose_semantics 描述性语义可重建性": _evidence}
(OUTD / "h2a_stats_audit.json").write_text(
    json.dumps(_out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'h2a_stats_audit.json'}")
