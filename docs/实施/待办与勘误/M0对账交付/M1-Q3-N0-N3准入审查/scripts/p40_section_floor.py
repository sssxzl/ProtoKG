# -*- coding: utf-8 -*-
"""★ P0.9 后续：★ S4 章节保底改进的**离线同预算比较**（★ 0 次 API）。

★ 复核项：
  ① 16 块预算下 SIP 章节覆盖为何仅 6.12%
  ② 章节多样性约束是否实际生效
  ③ 非 BCP14 20% 保留配额是否覆盖有价值的非规范知识
  ④ 块级 token 估算是否遗漏 Prompt、输出与重试开销
★ 新增：**S5 = S4 + 受预算约束的章节保底**
★ ★ **章节数量超过块预算时 ⇒ 不得声称可以每章节至少选一块**
"""
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_p079"))
from _lib import OUTROOT, load_jsonl, save_json

PROTOS = ("rtsp", "sip", "smtp", "DHCPv4")
_BCP = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|"
                  r"REQUIRED|RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")
_RE_SEC = re.compile(r"^\s{0,3}(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9 /\-()]{3,70})\s*$")

index = load_jsonl(OUTROOT / "p09_block_scores.jsonl")
_docs = {}
for r in index:
    _k = (r["protocol"], r["document_id"])
    if _k not in _docs:
        p = ROOT / f"kb/{r['protocol']}/spec/{r['document_id']}"
        _docs[_k] = p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")


def coverage(proto, selected):
    _sel = collections.defaultdict(set)
    for r in selected:
        _sel[(r["protocol"], r["document_id"])].add(tuple(r["★ 原始行号范围"]))
    _cl = _tl = _cb = _tb = _cs = _ts = 0
    for (pr, doc), L in _docs.items():
        if pr != proto:
            continue
        _tl += len(L)
        _tb += sum(1 for ln in L if _BCP.search(ln))
        _ts += sum(1 for ln in L if _RE_SEC.match(ln))
        _cov = set()
        for (a, b) in _sel.get((pr, doc), ()):
            for i in range(a, b + 1):
                _cov.add(i)
        _cl += len(_cov)
        _cb += sum(1 for i, ln in enumerate(L, 1)
                   if i in _cov and _BCP.search(ln))
        _cs += sum(1 for i, ln in enumerate(L, 1) if i in _cov and _RE_SEC.match(ln))
    return {"blocks": len(selected),
            "source_line_coverage": round(_cl / max(1, _tl), 4),
            "normative_line_coverage": round(_cb / max(1, _tb), 4),
            "section_coverage": round(_cs / max(1, _ts), 4)}


def _sec_key(r):
    return (str((r["★ 章节归属"] or {}).get("num") or "_"),
            str(r["document_id"]), int(r["★ 原始行号范围"][0]))


def select_s5(proto, budget, section_floor_ratio=0.5):
    """★ S5 = 块级密度 + 文档保底 + **章节保底** + 非 BCP14 保留。"""
    _rs = [r for r in index if r["protocol"] == proto]
    _out, _left = [], int(budget)
    if _left <= 0:
        return _out
    # ★ ① 章节保底（★ **受预算约束**：★ 章节数 > 预算时 ⇒ 只按预算取最高分章节）
    _bysec = collections.defaultdict(list)
    for r in _rs:
        _bysec[_sec_key(r)].append(r)
    _floor_cap = max(1, int(budget * section_floor_ratio))
    _sec_order = sorted(_bysec.keys(),
                        key=lambda k: (-max(x["★ 价值评分"] for x in _bysec[k]), k))
    for _k in _sec_order:
        if _left <= 0 or len(_out) >= _floor_cap:
            break
        _best = max(_bysec[_k], key=lambda r: (r["★ 价值评分"],
                                               -r["★ 原始行号范围"][0]))
        _out.append(_best)
        _left -= 1
    # ★ ② 文档保底（★ ≤ 剩余额度的一半）
    _doc_cap = max(1, int(budget * 0.25))
    _seen_doc = {r["document_id"] for r in _out}
    for r in sorted(_rs, key=lambda x: (-x["★ 价值评分"], x["document_id"])):
        if _left <= 0 or len(_out) >= _floor_cap + _doc_cap:
            break
        if r["document_id"] in _seen_doc:
            continue
        _out.append(r)
        _seen_doc.add(r["document_id"])
        _left -= 1
    # ★ ③ 非 BCP14 保留（20%）
    _quota = max(1, int(round(budget * 0.20)))
    _added = 0
    for r in sorted(_rs, key=lambda x: (-x["★ 价值评分"], x["document_id"])):
        if _added >= _quota or _left <= 0:
            break
        if r in _out or _BCP.search(r.get("★ 评分组成") and "" or ""):
            pass
        if r in _out:
            continue
        _out.append(r)
        _added += 1
        _left -= 1
    # ★ ④ 密度补齐
    for r in sorted(_rs, key=lambda x: (-x["★ 价值评分"], x["document_id"])):
        if _left <= 0:
            break
        if r in _out:
            continue
        _out.append(r)
        _left -= 1
    return _out[:budget]


# ★ 复用 P0.9 的 S1~S4
_prev = json.loads((OUTROOT / "p09_strategy_comparison.json").read_text(encoding="utf-8"))

out = {}
for proto in PROTOS:
    _total = len([r for r in index if r["protocol"] == proto])
    _nsec = len({_sec_key(r) for r in index if r["protocol"] == proto})
    out[proto] = {"total_blocks": _total, "total_sections": _nsec,
                  "★ 章节数 > 预算 ⇒ 不能每章节一块": {}}
    for budget in (16, 36, 64):
        _s5 = select_s5(proto, budget)
        _c = coverage(proto, _s5)
        _prev_b = [x for x in _prev[proto]["by_strategy"].get("S4 块级密度+保底+章节多样", [])
                   if x["budget"] == budget]
        out[proto]["★ 章节数 > 预算 ⇒ 不能每章节一块"][str(budget)] = {
            "sections": _nsec, "budget": budget,
            "★ 每章节一块是否可行": _nsec <= budget,
        }
        out[proto].setdefault("by_strategy", {}).setdefault("S5 章节保底", []).append(
            {"budget": budget, **_c})
        if _prev_b:
            out[proto].setdefault("by_strategy", {}) \
                .setdefault("_S4 对照", []).append({"budget": budget, **_prev_b[0]})

print("  ★ 同预算比较（★ 规范义务行 / 章节 / 行）：")
for proto in PROTOS:
    _row = []
    for strat in ("S1 每文档固定", "S4 块级密度+保底+章节多样", "S5 章节保底"):
        _e = [x for x in out[proto]["by_strategy"].get(strat, []) if x["budget"] == 16]
        if _e:
            _row.append(f"{strat.split()[0]}: 规范 {_e[0]['normative_line_coverage']*100:.1f}% "
                        f"/章节 {_e[0]['section_coverage']*100:.1f}% "
                        f"/行 {_e[0]['source_line_coverage']*100:.1f}%")
    print(f"    {proto:8s} " + " ｜ ".join(_row))
    _f = out[proto]["★ 章节数 > 预算 ⇒ 不能每章节一块"]
    print(f"             ★ 章节数 {out[proto]['total_sections']}｜"
          f"16 块可行={_f['16']['★ 每章节一块是否可行']}｜"
          f"64 块可行={_f['64']['★ 每章节一块是否可行']}")

save_json(OUTROOT / "p09b_s5_section_floor.json", out)
print(f"\n  ⇒ {OUTROOT/'p09b_s5_section_floor.json'}")
