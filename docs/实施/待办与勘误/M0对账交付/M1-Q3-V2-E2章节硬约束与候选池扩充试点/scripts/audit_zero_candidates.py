# -*- coding: utf-8 -*-
"""★ V2-E2：★ **28 份零候选 RFC 的根因审计**（★ A~G 七类）。

★ 输出字段：★ rfc_id / protocol / source_sha256 / available_chunks /
★           old_run_status / zero_candidate_reason / eligible_for_pilot
★ ★ **零候选不能直接视为「原文没有知识」；★ 也不能直接认定重跑 LLM 就会增加有效候选**
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
import sampler as SP

OUTD = ROOT / "guard/_out/_n1c_v2/e2"

# ══ 冻结候选与 chunk 覆盖 ══
_fr, _meta = SP.load_candidates(ROOT)
_docs = SP.load_docs(ROOT)
_cand_docs = {(o["protocol"], o["document"]) for o in _fr.values()}
_chunk_docs = set(_meta.keys())
_zero_docs = sorted(set(_docs) - _cand_docs)
print(f"  ★ RFC 文档总数 = {len(_docs)}｜含候选文档 = {len(_cand_docs)}"
      f"｜零候选文档 = **{len(_zero_docs)}**")

# ══ 覆盖率台账（★ 若存在）══
_ledger = {}
for _p in ROOT.rglob("coverage_ledger*.json*"):
    try:
        if _p.suffix == ".jsonl":
            for _l in _p.read_text(encoding="utf-8").splitlines():
                if _l.strip():
                    _d = json.loads(_l)
                    _ledger[_d.get("document") or _d.get("doc")] = _d
        else:
            _d = json.loads(_p.read_text(encoding="utf-8"))
            _ledger[_d.get("document") or _d.get("doc")] = _d
    except Exception:
        pass

# ══ 历史 LLM 调用记录（★ 逐候选）══
_llm_seen = collections.defaultdict(list)
for _p in (ROOT / "guard/_out/n2/n2_records.jsonl",
           ROOT / "guard/_out/n3/n3_recall_records.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a5_p1_rows.jsonl",
           ROOT / "guard/_out/m1_q3/p079/p07_a4_p0_rows.jsonl",
           ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
           ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl"):
    if not _p.is_file():
        continue
    for _l in _p.read_text(encoding="utf-8").splitlines():
        if not _l.strip():
            continue
        _d = json.loads(_l)
        if _d.get("candidate_id"):
            _llm_seen[_d["candidate_id"]].append(_d)

# ══ 解析健康度（★ 散文行比例 / 空文档 / 章节数）══
_RE_TITLE = None
import re
_RE_TITLE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S")
_RE_ABNF = re.compile(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*")
_RE_BCP = re.compile(r"\b(MUST|SHALL|SHOULD|REQUIRED|MAY)\b")


def _doc_health(k):
    _d = _docs[k]
    _L = _d["lines"]
    _nonempty = [x for x in _L if str(x).strip()]
    _prose = [x for x in _nonempty
              if not _RE_TITLE.match(str(x)) and not _RE_ABNF.match(str(x))]
    _bcp = sum(1 for x in _prose if _RE_BCP.search(str(x)))
    _titles = sum(1 for x in _nonempty if _RE_TITLE.match(str(x)))
    return {"总行数": len(_L), "非空行": len(_nonempty), "散文行": len(_prose),
            "BCP14 行": _bcp, "章节标题": _titles,
            "★ 散文占比": round(len(_prose) / max(1, len(_nonempty)), 4),
            "★ BCP14 密度": round(_bcp / max(1, len(_prose)), 4)}


# ══ 逐份审计 ══
_rows = []
for _k in _zero_docs:
    _h = _doc_health(_k)
    _bcp = _h["BCP14 行"]
    _bcp_in_prose = sum(1 for x in _docs[_k]["lines"]
                        if str(x).strip() and _RE_BCP.search(str(x))
                        and not _RE_TITLE.match(str(x))
                        and not _RE_ABNF.match(str(x)))
    _led = _ledger.get(_k[1])
    _old_status = "★ 无历史覆盖率台账"
    if _led:
        _old_status = json.dumps(_led, ensure_ascii=False)[:300]
    # ── 归因（★ A~G）──
    if _h["散文行"] < 30:
        _reason = "F 文档格式或解析失败（★ 散文行过少）"
        _eligible = False
    elif _bcp_in_prose == 0:
        _reason = "A 原文确实没有被当前候选规则捕获的知识（★ 散文段内无 BCP14 强度词）"
        _eligible = "★ 待定（★ 需人工确认是否有陈述式规范句）"
    elif _h["★ BCP14 密度"] < 0.01:
        _reason = "C 候选触发器没有命中（★ 有强度词但密度过低，★ 未达抽取阈值）"
        _eligible = "★ 可能（★ 需确认阈值与窗口设置）"
    elif not _led:
        _reason = ("B RFC 切块或窗口覆盖不足（★ 该文档未进入任何冻结 chunk）"
                   "★ **且**无覆盖率台账记录")
        _eligible = "★ 可能（★ 需先确认切块规则）"
    else:
        _reason = "G 当前知识类型通道不适用"
        _eligible = "★ 可能"
    _rows.append({
        "rfc_id": _k[1], "protocol": _k[0],
        "source_sha256": _docs[_k]["sha256"],
        "available_chunks": 0,
        "old_run_status": _old_status,
        "zero_candidate_reason": _reason,
        "eligible_for_pilot": _eligible,
        "★ 文档健康度": _h,
        "★ 历史 LLM 调用记录数": 0,
    })

_dist = collections.Counter(r["zero_candidate_reason"].split("（")[0].split("，")[0]
                            for r in _rows)
print()
print("  ★ 零候选归因分布：")
for _k, _v in sorted(_dist.items(), key=lambda z: -z[1]):
    print(f"      {_k}: {_v}")
print()
print("  ★ 逐份（★ 前 12）：")
for _r in _rows[:12]:
    print(f"      {_r['rfc_id'][:18]:20s} {_r['protocol']:8s} "
          f"BCP14行={_r['★ 文档健康度']['BCP14 行']:4d} "
          f"散文行={_r['★ 文档健康度']['散文行']:5d} "
          f"｜{_r['zero_candidate_reason'][:52]}")
print(f"      …… 共 {len(_rows)} 份")

(OUTD / "v2e2_zero_candidate_audit.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in _rows) + "\n",
    encoding="utf-8")
print(f"\n  ⇒ {OUTD/'v2e2_zero_candidate_audit.jsonl'}")
