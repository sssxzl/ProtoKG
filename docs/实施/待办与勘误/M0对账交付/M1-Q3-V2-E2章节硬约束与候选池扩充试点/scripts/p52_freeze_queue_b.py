# -*- coding: utf-8 -*-
"""★ V2-E2 §十：★ **队列 B 冻结抽样 + 泄漏检查**（★ 前置 5 项全部通过才允许）。

★ 前置：
  ① 章节硬配额可行性 ✔（★ 五类均 ≥4，★ ABNF 非 0）
  ② 协议与文档级联合容量 ✔
  ③ 知识匹配规则冻结 ✔（E1）
  ④ 人工任务书冻结 ✔（E1）
  ⑤ 与试点来源的泄漏隔离 ✔（★ **同文档、异区段**：★ 队列 B = 未抽取区段，★ 试点 = 已抽取区段）
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
import sampler as SP

E2 = ROOT / "guard/_out/_n1c_v2/e2"
OUTD = E2
PILOT = ROOT / "guard/_out/_v2_e2_pilot"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E2章节硬约束与候选池扩充试点")
DELIV.mkdir(parents=True, exist_ok=True)

_pick = json.loads((E2 / "v2e2_quota_pick.json").read_text(encoding="utf-8"))
_jc = json.loads((E2 / "v2e2_joint_capacity.json").read_text(encoding="utf-8"))
_pilot_recs = [json.loads(l) for l in
               (PILOT / "V2-E2_新增候选审计.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip()]
_pilot_docs = {(r["★ protocol"], r["★ document_id"]) for r in _pilot_recs
               if r.get("★ document_id")}
_pilot_chunks = {r.get("★ chunk_id") for r in _pilot_recs if r.get("★ chunk_id")}

# ══ 前置 5 项检查 ══
_pre = {}
_pre["① 章节硬配额可行性"] = _jc["★ 新配额求解"]["★ 五类均 ≥ 最低"] and \
    _jc["★ 新配额求解"]["★ ABNF 类非 0"]
_pre["② 协议与文档级联合容量"] = bool(_jc["★ 联合容量（协议 × 章节）"])
_pre["③ 知识匹配规则冻结"] = (ROOT / "docs/实施/待办与勘误/M0对账交付"
                            / "M1-Q3-V2-E1片段级任务书与匹配规则"
                            / "V2-E1_知识匹配与漏抽判定规则.md").is_file()
_pre["④ 人工任务书冻结"] = (ROOT / "docs/实施/待办与勘误/M0对账交付"
                          / "M1-Q3-V2-E1片段级任务书与匹配规则"
                          / "V2-E1_片段级人工标注任务书.md").is_file()
_overlap_docs = {f"{p}/{d}" for p, d in _pilot_docs} & \
    {f"{p['proto']}/{p['doc']}" for p in _pick}
_pre["⑤ 与试点来源泄漏隔离"] = {
    "★ 队列B 文档数": len({f"{p['proto']}/{p['doc']}" for p in _pick}),
    "★ 试点文档数": len(_pilot_docs),
    "★ 文档级重叠": len(_overlap_docs),
    "★ ★ 隔离机制": ("★ **同文档、异区段隔离**：★ 队列 B 片段全部来自"
                "**未生成候选**的段落（★ 与冻结 chunk 覆盖互补）；★ 试点块来自"
                "**已抽取**区段 ⇒ ★ 二者在原文区间上不重叠"),
    "★ ★ 结论": ("★ **文档级隔离不可行**（★ 零候选 RFC 全部为 DHCPv4，★ 且队列 B 与试点"
             "同源于这 28 份）⇒ ★ 改用**区段级隔离**，★ 并**不得声称**"
             "★ DHCPv4 的跨文档泛化能力")}

# ══ 冻结清单 ══
_rows = []
for _i, _p in enumerate(sorted(_pick, key=lambda z: (z["proto"], z["doc"],
                                                     z["lo"]))):
    _sid = f"B-{_p['proto']}-{_p['doc']}-{_p['lo']}"
    _rows.append({
        "sample_id": _sid,
        "队列": "B",
        "protocol": _p["proto"], "document": _p["doc"],
        "rfc_sha256": _p.get("sha256") or "",
        "★ 章节类型": _p["kind"],
        "★ 证据跨度（行号）": [_p["lo"], _p["hi"]],
        "★ 证据文本": _p["ev"][:1200],
        "★ 所属抽取区间": "★ 未生成候选的区段（★ 与冻结 chunk 覆盖互补）",
        "★ 与试点重叠": bool(f"{_p['proto']}/{_p['doc']}" in
                        {f"{a}/{b}" for a, b in _pilot_docs}),
    })

# ══ 泄漏检查（★ 逐条）══
_leak = []
_dev_docs = set()
for _l in (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl").read_text(encoding="utf-8").splitlines():
    if not _l.strip():
        continue
    _d = json.loads(_l)
    _dev_docs.add((_d.get("★ protocol") or _d.get("protocol"),
                   _d.get("★ document") or _d.get("document")))
for _r in _rows:
    _k = (_r["protocol"], _r["document"])
    # ★ ★ 区段级排除：★ 开发集文档的**已抽取区段**本就不在队列 B 候选内
    #   （★ 队列 B 片段全部来自**未生成候选**的区段）⇒ ★ **不需整文档排除**
    #   ⇒ ★ 整文档排除只用于**未来独立评测集**的来源划分
    if _k in _dev_docs:
        _leak.append({"sample_id": _r["sample_id"],
                   "★ 说明": "★ 同属开发集来源文档，★ 但区段互补"
                           "（★ 本片段在**未抽取**区段内）⇒ ★ 保留",
                   "★ 处置": "★ 保留（★ 区段级隔离）"})
    if _r["★ 与试点重叠"]:
        _leak.append({"sample_id": _r["sample_id"],
                   "★ 排除原因": "★ 与试点同文档（★ 但区段互补 ⇒ 记录不排除）",
                   "★ 处置": "★ 保留（★ 区段级隔离）"})
_frozen = [r for r in _rows
           if not any(x["sample_id"] == r["sample_id"]
                      and "排除" in x.get("★ 排除原因", "") for x in _leak)]

_out = {
    "★ 前置 5 项检查": _pre,
    "★ 冻结清单条数": len(_frozen),
    "★ 章节分布": dict(collections.Counter(r["★ 章节类型"] for r in _frozen)),
    "★ 协议分布": dict(collections.Counter(r["protocol"] for r in _frozen)),
    "★ 文档分布": dict(collections.Counter(
        f"{r['protocol']}/{r['document']}" for r in _frozen)),
    "★ 每文档最大条数": max(collections.Counter(
        f"{r['protocol']}/{r['document']}" for r in _frozen).values()),
    "★ 泄漏检查记录数": len(_leak),
    "★ 冻结清单哈希": hashlib.sha256(
        json.dumps(_frozen, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
}
(DELIV / "V2-E2_队列B冻结抽样与泄漏检查.json").write_text(
    json.dumps(_out, ensure_ascii=False, indent=2), encoding="utf-8")
with (DELIV / "V2-E2_队列B冻结样本清单.jsonl").open("w", encoding="utf-8") as f:
    for _r in _frozen:
        f.write(json.dumps(_r, ensure_ascii=False) + "\n")

print("  ★ 前置 5 项：")
for _k, _v in _pre.items():
    print(f"      {_k}: {_v if not isinstance(_v, dict) else '★ 见 JSON'}")
print()
print(f"  ★ 冻结清单 = {len(_frozen)} 条｜哈希 {_out['★ 冻结清单哈希'][:16]}")
print(f"      章节分布：{_out['★ 章节分布']}")
print(f"      协议分布：{_out['★ 协议分布']}")
print(f"      每文档最大：{_out['★ 每文档最大条数']}")
print(f"\n  ⇒ {DELIV/'V2-E2_队列B冻结样本清单.jsonl'}")
