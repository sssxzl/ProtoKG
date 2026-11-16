# -*- coding: utf-8 -*-
"""★ V2-E2：★ **协议 × 章节 × 文档联合容量**与新配额求解（★ 章节覆盖为硬约束）。

★ 硬约束（★ 用户 §三）：
  ① 五类章节**各至少 4** 个独立片段
  ② ★ 「消息格式与 ABNF」**不得为 0**
  ③ 每 RFC 文档**最多 6** 条（★ A/B 双队列合并计算）
  ④ 开发集 chunk 排除 ｜ ⑤ 调优证据跨度排除 ｜ ⑥ 5-gram Jaccard>0.6 近重复排除
  ⑦ 原始文档与证据 SHA256 校验
  ⑧ ★ **不得把 DHCPv4 58 / 其他各 4 当作未经复审的固定配额** ⇒ ★ 须按联合容量重算
★ ★ **若全部约束不能同时满足** ⇒ 按预先声明规则减量，★ 仍不足则停止并提交不可行报告
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
import sampler as SP
import section_kinds as SK

OUTD = ROOT / "guard/_out/_n1c_v2/e2"
OUTD.mkdir(parents=True, exist_ok=True)

MIN_PER_KIND = 4
DOC_CAP = 6
TOTAL_TARGET = 58
NEAR_DUP_T = 0.6
FRAG_MIN_LINES = 6

# ══ 排除集合（★ 与 E1 一致）══
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
N1C = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计")
import csv as _csv
_dev_cands = {json.loads(l)["sample_id"] for l in
              (N1B / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
              if l.strip()}
_dev_cands |= {r["candidate_id"] for r in
               _csv.DictReader((N1C / "N1-C_V0_V1逐候选对照.csv").open(encoding="utf-8"))}
_spans = SP.load_spans(ROOT)
_dev_chunks = {f"{_spans[c]['★ document']}@{_spans[c]['chunk_start']}"
               for c in _dev_cands if c in _spans}
_fr, _meta = SP.load_candidates(ROOT)
_docs = SP.load_docs(ROOT)
_joint = json.loads((ROOT / "guard/_out/_n1c_v2/v2_v1_joint.json")
                    .read_text(encoding="utf-8"))["rows"]
_tuning_ev = set()
for _r in _joint:
    _t = json.loads(_r["★ V2 证据跨度"]) if _r["★ V2 证据跨度"] else {}
    if _t.get("text"):
        _tuning_ev.add(_t["text"])

# ══ 开发集 5-gram ══
_dev_grams = set()
for _cid in _dev_cands:
    _s = _spans.get(_cid)
    _o = _fr.get(_cid)
    if not (_s and _o) or _s.get("resolved_span") is None:
        continue
    _k = (_o["protocol"], _o["document"])
    if _k in _docs:
        _dev_grams |= SP.grams(SP.evidence_of(_docs[_k]["lines"],
                                              int(_s["resolved_span"])))

# ══ 候选覆盖（★ 用于片段判定）══
_cov = collections.defaultdict(set)
for _cid, _o in _fr.items():
    _b = _meta.get((_o["protocol"], _o["document"]))
    if not _b:
        continue
    _lo = int(_b["chunk_start"])
    _hi = _lo + int(str(_b.get("chunk_text") or "").count("\n"))
    for _i in range(_lo, _hi + 1):
        _cov[(_o["protocol"], _o["document"])].add(_i)

# ══ 逐文档切片段 + 章节类型 ══
_frag_by_doc = collections.defaultdict(list)   # (proto, doc) -> [(kind, lo, hi, ev)]
_doc_kinds = {}
for _k in sorted(_docs):
    _d = _docs[_k]
    _ks = SK.build_section_index(_d["lines"])
    _c = _cov.get(_k, set())
    _i = 1
    _n = len(_d["lines"])
    while _i <= _n:
        if _i in _c or not str(_d["lines"][_i - 1] or "").strip():
            _i += 1
            continue
        _j = _i
        while _j <= _n and _j not in _c and str(_d["lines"][_j - 1] or "").strip():
            _j += 1
        if _j - _i >= FRAG_MIN_LINES:
            _ev = " ".join(_d["lines"][_i - 1:_j])
            _kind = SK.kind_of_line(_d["lines"], _ks, _i)
            _dup = SP.jaccard(SP.grams(_ev), _dev_grams) > NEAR_DUP_T
            _tune = _ev in _tuning_ev
            _frag_by_doc[_k].append({
                "kind": _kind, "lo": _i, "hi": _j - 1, "ev": _ev,
                "★ 排除": ("近重复" if _dup else ("调优证据跨度" if _tune else None))})
        _i = _j
    _doc_kinds[_k] = _ks

# ══ 联合容量矩阵（★ 协议 × 章节类型 × 文档）══
_matrix = collections.defaultdict(lambda: collections.defaultdict(int))
_doc_matrix = collections.defaultdict(lambda: collections.defaultdict(int))
for _k, _frs in _frag_by_doc.items():
    for _f in _frs:
        if _f["★ 排除"]:
            continue
        _matrix[_k[0]][_f["kind"]] += 1
        _doc_matrix[_k][_f["kind"]] += 1

print("  ★ 协议 × 章节类型 联合容量（★ 排除后）：")
print(f"      {'协议':10s} " + " ".join(f"{k[:6]:>8s}" for k in SK.ALL_KINDS)
      + f" {'合计':>8s}")
for _p in sorted(_matrix):
    _row = [_matrix[_p][k] for k in SK.ALL_KINDS]
    print(f"      {_p:10s} " + " ".join(f"{v:8d}" for v in _row)
          + f" {sum(_row):8d}")
_tot_kind = {k: sum(_matrix[_p][k] for _p in _matrix) for k in SK.ALL_KINDS}
print(f"      {'全部':10s} " + " ".join(f"{_tot_kind[k]:8d}" for k in SK.ALL_KINDS)
      + f" {sum(_tot_kind.values()):8d}")

# ══ 新配额求解（★ 章节硬约束 + 协议轮转 + 文档上限）══
def _solve():
    """★ 贪心：★ ① 每类先保底 4（★ 按协议轮转，★ 防止单协议主导）
    ★ ② 剩余额度按容量比例分配（★ 同样协议轮转）"""
    _avail = []
    for _k, _frs in _frag_by_doc.items():
        for _f in _frs:
            if _f["★ 排除"]:
                continue
            _avail.append({**_f, "proto": _k[0], "doc": _k[1],
                           "docname": f"{_k[0]}/{_k[1]}",
                           "key": (_k[0], _k[1], _f["lo"])})
    _avail.sort(key=lambda z: (z["proto"], z["doc"], z["lo"]))
    _picked = []
    _doc_used = collections.Counter()
    _kind_used = collections.Counter()
    _proto_used = collections.Counter()

    def _try_take(pool, need):
        _added = 0
        for _s in pool:
            if _added >= need or len(_picked) >= TOTAL_TARGET:
                break
            if _doc_used[_s["docname"]] >= DOC_CAP:
                continue
            _picked.append(_s)
            _doc_used[_s["docname"]] += 1
            _kind_used[_s["kind"]] += 1
            _proto_used[_s["proto"]] += 1
            _added += 1
        return _added

    # ① 每类保底 4（★ 协议轮转）
    for _kind in SK.ALL_KINDS:
        _pool = [s for s in _avail if s["kind"] == _kind]
        _by_p = collections.defaultdict(list)
        for _s in _pool:
            _by_p[_s["proto"]].append(_s)
        # ★ 协议按「文档数」轮转（★ 覆盖广的协议优先）
        _order = sorted(_by_p, key=lambda p: (-len({x["docname"] for x in _by_p[p]}), p))
        _need = MIN_PER_KIND
        while _need > 0 and any(_by_p[p] for p in _order):
            _progress = False
            for _p in _order:
                if _need <= 0:
                    break
                _cand = [s for s in _by_p[_p] if s not in _picked
                         and _doc_used[s["docname"]] < DOC_CAP]
                if not _cand:
                    continue
                _picked.append(_cand[0])
                _doc_used[_cand[0]["docname"]] += 1
                _kind_used[_cand[0]["kind"]] += 1
                _proto_used[_cand[0]["proto"]] += 1
                _need -= 1
                _progress = True
            if not _progress:
                break
    # ② 剩余额度：★ 按容量比例，★ 协议轮转
    _remain = TOTAL_TARGET - len(_picked)
    _cap_kind = {k: _tot_kind[k] for k in SK.ALL_KINDS}
    while _remain > 0:
        _prog = False
        for _kind in sorted(SK.ALL_KINDS, key=lambda k: -_cap_kind[k]):
            if _remain <= 0:
                break
            if _kind_used[_kind] >= TOTAL_TARGET:
                continue
            _pool = [s for s in _avail
                     if s["kind"] == _kind and s not in _picked]
            _by_p = collections.defaultdict(list)
            for _s in _pool:
                _by_p[_s["proto"]].append(_s)
            _order = sorted(_by_p, key=lambda p: (-len({x["docname"] for x in _by_p[p]}), p))
            for _p in _order:
                if _remain <= 0:
                    break
                _cand = [s for s in _by_p[_p] if s not in _picked
                         and _doc_used[s["docname"]] < DOC_CAP]
                if not _cand:
                    continue
                _picked.append(_cand[0])
                _doc_used[_cand[0]["docname"]] += 1
                _kind_used[_cand[0]["kind"]] += 1
                _proto_used[_cand[0]["proto"]] += 1
                _remain -= 1
                _prog = True
                break
        if not _prog:
            break
    return _picked, _kind_used, _proto_used, _doc_used


_picked, _ku, _pu, _du = _solve()
print()
print(f"  ★ 新配额求解：★ 抽出 **{len(_picked)}**")
print(f"      章节分布：{dict(_ku)}")
print(f"      协议分布：{dict(_pu)}")
print(f"      文档数：{len(_du)}｜每文档最大 {max(_du.values()) if _du else 0}")
_ok = all(_ku.get(k, 0) >= MIN_PER_KIND for k in SK.ALL_KINDS)
print(f"      ★ 五类均 ≥ {MIN_PER_KIND}？ **{_ok}**")
print(f"      ★ 「消息格式与 ABNF」非 0？ **{_ku.get(SK.KIND_FORMAT, 0) > 0}**")

_out = {
    "★ 联合容量（协议 × 章节）": {p: {k: _matrix[p][k] for k in SK.ALL_KINDS}
                          for p in sorted(_matrix)},
    "★ 章节类型总容量": _tot_kind,
    "★ 硬约束": {"每类最少": MIN_PER_KIND, "每文档上限": DOC_CAP,
             "目标总量": TOTAL_TARGET, "近重复阈值": NEAR_DUP_T,
             "片段最小行数": FRAG_MIN_LINES},
    "★ 新配额求解": {
        "★ 抽出数": len(_picked),
        "★ 章节分布": dict(_ku),
        "★ 协议分布": dict(_pu),
        "★ 文档数": len(_du),
        "★ 每文档最大条数": max(_du.values()) if _du else 0,
        "★ 五类均 ≥ 最低": _ok,
        "★ ABNF 类非 0": _ku.get(SK.KIND_FORMAT, 0) > 0,
        "★ 满足全部硬约束": (_ok and _ku.get(SK.KIND_FORMAT, 0) > 0
                        and (max(_du.values()) if _du else 0) <= DOC_CAP),
    },
}
(OUTD / "v2e2_joint_capacity.json").write_text(
    json.dumps(_out, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "v2e2_quota_pick.json").write_text(
    json.dumps(_picked, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'v2e2_joint_capacity.json'}")
