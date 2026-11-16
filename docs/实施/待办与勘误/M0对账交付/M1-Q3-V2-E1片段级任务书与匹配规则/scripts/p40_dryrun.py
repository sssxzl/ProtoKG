# -*- coding: utf-8 -*-
"""★ V2-E1：★ 复算统计事实 + 章节分层容量 + 泄漏检查 + ★ **dry-run**（★ 不冻结）。

★ 本脚本 **不产生正式盲审包**、★ 不生成任何人工标签。
"""
import collections
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
import section_kinds as SK
import sampler as SP

OUTD = ROOT / "guard/_out/_n1c_v2/e1"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E1片段级任务书与匹配规则"
DELIV.mkdir(parents=True, exist_ok=True)
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")
N1C = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计")

# ══ §二 复算统计事实 ══
_n1b = {json.loads(l)["sample_id"] for l in
        (N1B / "N1-B_逐样本对照.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()}
_n1c = {r["candidate_id"] for r in
        csv.DictReader((N1C / "N1-C_V0_V1逐候选对照.csv").open(encoding="utf-8"))}
_spans = SP.load_spans(ROOT)
_dev_cands = _n1b | _n1c
_dev_chunks = {f"{_spans[c]['★ document']}@{_spans[c]['chunk_start']}"
               for c in _dev_cands if c in _spans}
_fr, _meta = SP.load_candidates(ROOT)
_in_dev_chunk = [c for c, o in _fr.items()
                 if f"{o['document']}@{o['chunk_start']}" in _dev_chunks]
_docs = SP.load_docs(ROOT)
_facts = {
    "★ V2 开发集唯一 candidate_id 总数": len(_dev_cands),
    "★ N1-B 贡献": len(_n1b), "★ N1-C 贡献": len(_n1c),
    "★ 现有候选总数": len(_fr),
    "★ 落在开发集排除 chunk 内的候选数": len(_in_dev_chunk),
    "★ 排除后剩余候选数（★ 上限）": len(_fr) - len(_in_dev_chunk),
    "★ 开发集排除 chunk 数": len(_dev_chunks),
    "★ RFC 文档总数": len(_docs),
    "★ 按协议": dict(collections.Counter(k[0] for k in _docs)),
    "★ 含候选的文档数": len({(o["protocol"], o["document"]) for o in _fr.values()}),
}
# ★ 片段侧数量（★ 复算）
_cov = collections.defaultdict(set)
for _cid, _o in _fr.items():
    _b = _meta.get((_o["protocol"], _o["document"]))
    if not _b:
        continue
    _lo = int(_b["chunk_start"])
    _hi = _lo + int(str(_b.get("chunk_text") or "").count("\n"))
    for _i in range(_lo, _hi + 1):
        _cov[(_o["protocol"], _o["document"])].add(_i)
_nfrag = 0
for _k, _d in _docs.items():
    _c = _cov.get(_k, set())
    _i = 1
    while _i <= len(_d["lines"]):
        if _i in _c or not str(_d["lines"][_i - 1] or "").strip():
            _i += 1
            continue
        _j = _i
        while _j <= len(_d["lines"]) and _j not in _c \
                and str(_d["lines"][_j - 1] or "").strip():
            _j += 1
        if _j - _i >= 6:
            _nfrag += 1
        _i = _j
_facts["★ 片段侧可用原文片段数（★ 未生成候选）"] = _nfrag
print("  ★ §二 复算统计事实：")
for _k, _v in _facts.items():
    print(f"      {_k}: {_v}")

# ══ §八 章节类型分层 ══
_kinds_map = {}
_doc_kind_hist = collections.defaultdict(collections.Counter)
for _k, _d in _docs.items():
    _ks = SK.build_section_index(_d["lines"])
    for _i in range(1, len(_ks)):
        _kinds_map[f"{_k[0]}/{_k[1]}:{_i}"] = _ks[_i]
    # ★ 片段级章节类型
    _c = _cov.get(_k, set())
    _i = 1
    while _i <= len(_d["lines"]):
        if _i in _c or not str(_d["lines"][_i - 1] or "").strip():
            _i += 1
            continue
        _j = _i
        while _j <= len(_d["lines"]) and _j not in _c \
                and str(_d["lines"][_j - 1] or "").strip():
            _j += 1
        if _j - _i >= 6:
            _doc_kind_hist[_k][SK.kind_of_line(_d["lines"], _ks, _i)] += 1
        _i = _j
_cap_by_kind = collections.Counter()
for _k, _c in _doc_kind_hist.items():
    for _kk, _v in _c.items():
        _cap_by_kind[_kk] += _v
print()
print("  ★ §八 章节类型容量（★ 片段侧，★ 排除开发集 chunk 前）：")
for _k in SK.ALL_KINDS:
    print(f"      {_k}: {_cap_by_kind.get(_k, 0)}")

# ══ §九 泄漏排除（★ 含原文证据跨度）══
_tuning_ev = set()
# ★ V2 六轮调优中作为判据设计实例的特殊样本（★ 从 V2 联合影子产物读取）
_joint = json.loads((ROOT / "guard/_out/_n1c_v2/v2_v1_joint.json")
                    .read_text(encoding="utf-8"))["rows"]
for _r in _joint:
    _t = json.loads(_r["★ V2 证据跨度"]) if _r["★ V2 证据跨度"] else {}
    if _t.get("text"):
        _tuning_ev.add(_t["text"])
print(f"  ★ §九 泄漏排除：★ 开发集候选 {len(_dev_cands)}｜chunk {len(_dev_chunks)}"
      f"｜调优特殊证据跨度 {len(_tuning_ev)}")

# ══ 配置 ══
_cfg = {
    "★ 配置路径": None,
    "★ 随机种子": 20261116,
    "★ 目标总量": 70,
    "★ 每文档上限": 6,
    "★ 近重复阈值": 0.6,
    "★ 片段最小行数": 6,
    "★ 队列A 目标": 12,
    "★ 队列B 目标": 58,
    "★ 分层配额": {k: 0 for k in SK.ALL_KINDS},
    "★ 开发集排除": {"candidate_ids": sorted(_dev_cands),
                 "chunk_ids": sorted(_dev_chunks),
                 "tuning_evidence_spans": sorted(_tuning_ev)},
}
# ★ 队列 B 配额：★ 章节类型为主（★ 按容量比例分配 58）
_tot = sum(_cap_by_kind.values())
_alloc = {}
_remain = 58
for _k in SK.ALL_KINDS:
    _n = int(round(58 * _cap_by_kind.get(_k, 0) / _tot)) if _tot else 0
    _alloc[_k] = _n
    _remain -= _n
# ★ 余数按容量从大到小补
for _k in sorted(SK.ALL_KINDS, key=lambda z: -_cap_by_kind.get(z, 0)):
    if _remain <= 0:
        break
    _alloc[_k] += 1
    _remain -= 1
_cfg["★ 分层配额"] = _alloc
# ★ §八 协议硬配额（★ 防 DHCPv4 主导）
_cfg["★ 协议配额"] = {"rtsp": 4, "sip": 4, "smtp": 4, "DHCPv4": 58}
_cfg["_kinds"] = {}
_cfg["_section_kinds"] = _kinds_map
print(f"  ★ 队列 B 分层配额（★ 按容量比例）：{_alloc}")

# ══ dry-run ══
_cfg["_kinds"] = {}
for _cid, _o in _fr.items():
    _s = _spans.get(_cid)
    if _s and _s.get("resolved_span") is not None:
        _k = (_o["protocol"], _o["document"])
        _ks = SK.build_section_index(_docs[_k]["lines"])
        _cfg["_kinds"][_cid] = SK.kind_of_line(_docs[_k]["lines"], _ks,
                                        int(_s["resolved_span"]))
_res = SP.sample(ROOT, _cfg, mode="dry-run")
print()
print(f"  ★ dry-run：★ 队列A 可用 {_res['★ 队列A 可用（★ 排除后）']}"
      f"｜★ 队列B 可用 {_res['★ 队列B 可用（★ 排除后）']}"
      f"｜★ 实际抽出 {_res['★ 实际抽出']}")
print(f"      章节分布：{_res['★ 抽出分布']}")
print(f"      协议分布：{_res['★ 协议分布']}")
print(f"      文档分布（★ 每文档 ≤6）：{_res['★ 文档分布']}")

# ══ 可复算性（★ 两次运行一致）══
_res2 = SP.sample(ROOT, _cfg, mode="dry-run")
_reproducible = (_res["★ 输出哈希"] == _res2["★ 输出哈希"])
print(f"      ★ 两次运行输出哈希一致 = {_reproducible}")

_report = {
    "★ §二 复算统计事实": _facts,
    "★ §八 章节类型容量": dict(_cap_by_kind),
    "★ §九 泄漏排除": {"开发集候选": len(_dev_cands), "chunk": len(_dev_chunks),
                   "调优特殊证据跨度": len(_tuning_ev)},
    "★ 队列 B 分层配额": _alloc,
    "★ dry-run": {k: v for k, v in _res.items() if k != "★ 样本"},
    "★ 可复算（两次运行哈希一致）": _reproducible,
}
(OUTD / "v2e1_dryrun.json").write_text(
    json.dumps(_report, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "v2e1_dryrun_samples.json").write_text(
    json.dumps(_res["★ 样本"], ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'v2e1_dryrun.json'}")
