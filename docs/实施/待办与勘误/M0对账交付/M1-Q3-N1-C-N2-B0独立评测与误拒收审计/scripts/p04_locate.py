# -*- coding: utf-8 -*-
"""★ N2-B0：★ 精确定位 semantic_support 的匹配失败原因（★ 只读）。

★ 对每条 deterministic 前置拒收样本，★ 回答：
  · 动作词/对象词/强度词**是否真的不在证据窗口内**？
  · 若在，★ **在哪一行**？⇒ ⇒ **说明是「窗口过窄」还是「真缺失」
  · 精确匹配 vs 词根匹配 vs 子串匹配 ⇒ ⇒ **各自的命中情况**
★ ★ 同时对「L2/LLM 阶段拒收」的样本，★ 读历史记录的 reason（★ 不重跑 LLM）
"""
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

OUTD = ROOT / "guard/_out/n1c"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
trace = [json.loads(l) for l in
         (OUTD / "n2b0_blocking_trace.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()]
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}
FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = it
_docs = {}


def _lines(proto, doc):
    _k = (proto, doc)
    if _k not in _docs:
        _p = ROOT / f"kb/{proto}/spec/{doc}"
        _docs[_k] = _p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")
    return _docs[_k]


def _norm(s):
    return " ".join(str(s or "").lower().replace("_", " ").split())


def _find(flat, term):
    """★ 返回 term 在 flat 中命中的位置（★ 词级）。"""
    _t = _norm(term)
    if not _t:
        return []
    _words = flat.split()
    _tw = _t.split()
    _hits = []
    for i in range(len(_words) - len(_tw) + 1):
        if _words[i:i + len(_tw)] == _tw:
            _hits.append(i)
    return _hits


out = []
for t in trace:
    cid = t["candidate_id"]
    _sp = spans[cid]
    _o = FR.get(cid, {})
    _L = _lines(_sp["★ protocol"], _sp["★ document"])
    _rs = _sp["resolved_span"]
    _anchor = _L[_rs - 1]
    _chunk_lines = _L[_sp["chunk_start"] - 1:_sp["chunk_end"]]
    _chunk_flat = " ".join(_chunk_lines).lower()
    _win_flat = " ".join(_L[max(0, _rs - 4):min(len(_L), _rs + 4)]).lower()
    _det = {"candidate_id": cid,
            "★ first_blocking_stage": t["first_blocking_stage"],
            "★ blocking_reason": t["blocking_reason"]}
    for _name, _val in (("action", _o.get("action")),
                        ("object", _o.get("object")),
                        ("strength", _o.get("strength"))):
        if not _val:
            continue
        _n = _norm(_val)
        _in_anchor = _n in _norm(_anchor)
        _in_window = _n in _win_flat
        _in_chunk = _n in _chunk_flat
        _stem = _n[:-1] if _n.endswith("e") else _n
        _stem_in_chunk = bool(_stem) and _stem in _chunk_flat
        # ★ 该词在 chunk 内的**行号**
        _lines_hit = [i + 1 for i, ln in enumerate(_chunk_lines)
                      if _n in ln.lower()]
        _det[_name] = {
            "★ 值": _val,
            "★ 在锚点行": _in_anchor,
            "★ 在±4窗口": _in_window,
            "★ 在整个chunk": _in_chunk,
            "★ 词根在chunk": _stem_in_chunk,
            "★ 命中行号（chunk 内相对）": _lines_hit[:5],
            "★ 命中行号（绝对）": [_sp["chunk_start"] - 1 + x for x in _lines_hit[:5]],
            "★ 判定": ("★ **窗口过窄**（★ chunk 内有、★ 锚点行/窗口无）"
                   if _in_chunk and not _in_window else
                   ("★ **锚点行即命中**" if _in_anchor else
                    ("★ **chunk 内也无**（★ 真缺失）" if not _in_chunk else "★ 其他"))),
        }
    out.append(_det)

print("  ★ 逐条定位：")
for d in out:
    _stag = "★DET" if "semantic_support" in d["★ first_blocking_stage"] else "★LLM"
    print(f"      {d['candidate_id'][:24]:26s} {_stag}")
    for _k in ("action", "object", "strength"):
        if _k in d:
            _v = d[_k]
            print(f"          {_k:9s} {_v['★ 判定'][:22]:24s} 行{_v['★ 命中行号（绝对）'][:3]}"
                  f"｜值={str(_v['★ 值'])[:52]}")

# ★ 汇总
_cnt = collections.Counter()
for d in out:
    for _k in ("action", "object", "strength"):
        if _k in d:
            _cnt[(_k, d[_k]["★ 判定"])] += 1
print()
print("  ★ 判定分布：")
for (k, v), n in sorted(_cnt.items()):
    print(f"      {k:10s} {v[:34]:36s} {n}")

(OUTD / "n2b0_match_localization.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n2b0_match_localization.json'}")
