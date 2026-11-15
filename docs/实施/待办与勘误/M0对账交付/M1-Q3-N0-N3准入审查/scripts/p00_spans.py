# -*- coding: utf-8 -*-
"""★ N1-R2 第 1 步：★ 重新核实**全部 156 条**冻结候选的跨度定位。

★ ★ **不再假设 span 是绝对行号** ⇒ ★ **直接复用 M1-Q2 的 `resolve_span_evidence` 契约**：
  ① 绝对优先（entity_in_span ±3 命中）② 未命中才试相对 = chunk_start + (raw_span - 1)
  ③ 相对须落在 chunk 内 ④ 两者都命中 ⇒ 歧义不放行

★ 输出台账字段（★ 用户指定）：
  sample_id / raw_span / resolved_span / span_mode / chunk_start / within_chunk /
  evidence_supported / reason
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction.normative_extract import (
    resolve_span_evidence, entity_in_span,
)

OUT = ROOT / "guard/_out/n1r2"
OUT.mkdir(parents=True, exist_ok=True)
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

# ★ 冻结件
frozen, docs = {}, {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        _cid = f"{b['document']}@{b['chunk_start']}#{i}"
        frozen[_cid] = {**it, "chunk_start": b["chunk_start"],
                        "chunk_end": b["chunk_start"]
                        + str(b.get("chunk_text") or "").count("\n"),
                        "protocol": b["protocol"], "document": b["document"],
                        "chunk_hash": b.get("chunk_hash")}
    _k = (b["protocol"], b["document"])
    if _k not in docs:
        _p = ROOT / f"kb/{b['protocol']}/spec/{b['document']}"
        docs[_k] = {
            "lines": _p.read_text(encoding="utf-8", errors="replace")
            .replace("\r\n", "\n").split("\n"),
            "rfc_sha256": hashlib.sha256(_p.read_bytes()).hexdigest(),
        }

rows = []
for cid, o in sorted(frozen.items()):
    _k = (o["protocol"], o["document"])
    _L = docs[_k]["lines"]
    _cs, _ce = o["chunk_start"], o["chunk_end"]
    _sp = o.get("span")
    _ent = o.get("entity") or ""
    _ev = resolve_span_evidence(_L, _sp, _ent, chunk_start=_cs, chunk_end=_ce)
    _rs = _ev.get("resolved_span")
    _within = (bool(_rs) and _cs <= _rs <= _ce)
    # ★ 证据是否被原文支持：★ 锚点行非空 **且** entity 在锚点 ±3 内出现
    _anchor_text = _L[_rs - 1] if (_rs and 1 <= _rs <= len(_L)) else ""
    _entity_hit = entity_in_span(_L, _rs, _ent, window=3) if _rs else None
    _supported = bool(_rs) and bool(_entity_hit) and bool(_anchor_text.strip())
    rows.append({
        "sample_id": cid, "raw_span": _sp,
        "resolved_span": _rs, "span_mode": _ev.get("span_mode"),
        "chunk_start": _cs, "chunk_end": _ce,
        "within_chunk": _within,
        "evidence_supported": _supported,
        "reason": _ev.get("reason"),
        "★ 绝对命中": _ev.get("absolute_match"),
        "★ 相对命中": _ev.get("relative_match"),
        "★ matched_evidence_lines": _ev.get("matched_evidence_lines"),
        "★ entity": _ent,
        "★ 锚点行原文": _anchor_text,
        "★ 锚点行是否空白": (not _anchor_text.strip()) if _anchor_text != "" else None,
        "★ protocol": o["protocol"], "★ document": o["document"],
        "★ rfc_sha256": docs[_k]["rfc_sha256"],
    })

import collections
_m = collections.Counter(r["span_mode"] for r in rows)
_wc = sum(1 for r in rows if r["within_chunk"])
_sup = sum(1 for r in rows if r["evidence_supported"])
_blank = sum(1 for r in rows if r["★ 锚点行是否空白"])
print(f"  ★ 复核 {len(rows)} 条")
print(f"  ★ span_mode 分布: {dict(_m)}")
print(f"  ★ 落在 chunk 内 = {_wc}/{len(rows)}")
print(f"  ★ evidence_supported = {_sup}/{len(rows)}")
print(f"  ★ 锚点行为空白 = {_blank}")
print()
for cid in ("rfc3261.txt@10452#3", "rfc3261.txt@10452#4"):
    for r in rows:
        if r["sample_id"] == cid:
            print(f"  ★★ {cid}: raw={r['raw_span']} → resolved={r['resolved_span']} "
                  f"mode={r['span_mode']} within={r['within_chunk']} "
                  f"sup={r['evidence_supported']}")
            print(f"      entity={r['★ entity']!r}｜锚点原文={r['★ 锚点行原文'][:80]!r}")
            print(f"      reason={r['reason']}")

(OUT / "n1r2_span_ledger.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
    encoding="utf-8")
print(f"\n  ⇒ {OUT/'n1r2_span_ledger.jsonl'}")
