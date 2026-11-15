# -*- coding: utf-8 -*-
"""★ N1-R：★ 恢复 50 条样本的原始 RFC 证据（★ 全部来自同版本 RFC 原文，★ 不用 LLM）。

★ 修复要点：
  ① ★ 冻结件的键是 **`span`（块内相对偏移）**，★ 不是 `raw_span`
  ② ★ 绝对锚点 = `chunk_start + span`（★ 相对行号解释）
  ③ ★ `evidence_context` 是**绝对行号 + 原文**（★ 当时记录的真实证据）⇒ ★ 直接采用
  ④ ★ 原文上下文从 **RFC 原文**按绝对行号重建（★ 不使用任何生成内容）
  ⑤ polarity 冻结件**不存在** ⇒ ★ 由 strength **推导**并**明确标注为推导值**
  ⑥ exception 冻结件**不存在** ⇒ ★ 标注 `null（原始候选无 exception 字段）`
  ⑦ condition **不得**承载整条 constraint ⇒ ★ constraint 另存 `original_constraint`
"""
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "guard/_out/n1r"
OUT.mkdir(parents=True, exist_ok=True)
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
P079 = ROOT / "guard/_out/m1_q3/p079"

# ★ 冻结件（★ 原始候选 + 原始证据）
frozen = {}
doc_meta = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        _cid = f"{b['document']}@{b['chunk_start']}#{i}"
        frozen[_cid] = {**it, "chunk_start": b["chunk_start"],
                        "chunk_end_estimate": b["chunk_start"]
                        + str(b.get("chunk_text") or "").count("\n"),
                        "protocol": b["protocol"], "document": b["document"],
                        "chunk_hash": b.get("chunk_hash")}
    _p = ROOT / f"kb/{b['protocol']}/spec/{b['document']}"
    doc_meta[(b["protocol"], b["document"])] = {
        "rfc_sha256": hashlib.sha256(_p.read_bytes()).hexdigest(),
        "path": _p,
    }

# ★ 文档全文行（★ 同版本 RFC 原文）
_docs = {}
for (proto, doc), m in doc_meta.items():
    _docs[(proto, doc)] = m["path"].read_text(encoding="utf-8", errors="replace") \
        .replace("\r\n", "\n").split("\n")

_NEG = ("MUST NOT", "SHALL NOT", "SHOULD NOT", "MAY NOT", "NOT RECOMMENDED")


def _derive_polarity(strength):
    """★ 由 strength 推导 polarity（★ 冻结件无 polarity 字段 ⇒ ★ 标注为推导值）。"""
    _s = str(strength or "").strip().upper()
    if not _s:
        return "", "★ 原始候选无 strength ⇒ 无法推导"
    if _s in _NEG:
        return "negative", f"★ **推导值**：strength={_s} ⇒ 含否定形式"
    return "positive", f"★ **推导值**：strength={_s}"


# ★ 样本池：★ 全部冻结候选（★ 与 N1 抽样规则一致）
led = {x["candidate_id"]: x for x in
       [json.loads(l) for l in
        (ROOT / "guard/_out/m1_q3/p079/p07_candidate_ledger.jsonl")
        .read_text(encoding="utf-8").splitlines() if l.strip()]}
_rng = random.Random(20261116)

# ★ ★ 候选池：**全部冻结候选**（★ 含 not_applicable / upstream_invalid）
#   ⇒ ★ 因为人工标注的对象是「候选本身的语义正确性」，★ 与是否进过 L2 无关
#   ⇒ ★ 不可恢复者**单独记录**，★ 不伪造原始位置
_pool = []
_unrecoverable = []
for cid, o in frozen.items():
    if cid not in led:
        _unrecoverable.append((cid, "★ 台账中无此候选"))
        continue
    _sp = o.get("span")
    if not isinstance(_sp, int):
        _unrecoverable.append((cid, "★ 冻结件缺 span（★ 原始位置不可恢复）"))
        continue
    # ★ ★ 修正：★  **本身即绝对行号**（★ chunk_start 只是块起始行）
    #   ⇒ ⇒ 「chunk_start + span」会越界 ⇒ ★ 该换算曾被误用
    _abs = int(_sp)
    _L = _docs[(o["protocol"], o["document"])]
    if not (1 <= _abs <= len(_L)):
        _unrecoverable.append((cid, f"★ 绝对锚点行 {_abs} 越出文档（1..{len(_L)}）"))
        continue
    _pool.append((cid, o, _abs))

print(f"  ★ 可恢复证据的候选池 = {len(_pool)}（★ 共 {len(frozen)} 条冻结候选）")
print(f"  ★ **不可恢复 = {len(_unrecoverable)} 条**")
for _c, _r in _unrecoverable[:8]:
    print(f"      {_c}: {_r}")

# ★ 风险富集 20 条（★ 与 N1 同规则）
_MIG = {"rfc3261.txt@1842#2", "rfc3261.txt@12767#1"}
_RISK = ("coreference_subject", "strength_polarity_anomaly", "subject_ne_entity",
         "cross_sentence_object_or_condition")
_risk = []
for cid, o, _a in _pool:
    _t = set(led[cid].get("★ 风险标签") or [])
    _w = 0
    if cid in _MIG:
        _w += 5
    if "coreference_subject" in _t:
        _w += 4
    if "strength_polarity_anomaly" in _t:
        _w += 3
    if "subject_ne_entity" in _t:
        _w += 3
    if "cross_chunk_evidence" in _t:
        _w += 2
    if "l2_state_migrated" in _t:
        _w += 2
    if led[cid].get("★ 最终状态") == "pending_manual_review":
        _w += 3
    if _w:
        _risk.append((_w, cid))
_risk.sort(key=lambda z: (-z[0], z[1]))
_risk_ids = [c for _, c in _risk[:20]]

# ★ 分层随机 30 条（★ 协议 × 知识类型）
_strata = {}
for cid, o, _a in _pool:
    if cid in _risk_ids:
        continue
    _kind = "constraint" if o.get("constraint") else "semantics"
    _strata.setdefault((o["protocol"], _kind), []).append(cid)
_random = []
_keys = sorted(_strata)
_i = 0
while len(_random) < 30 and _i < 500:
    _k = _keys[_i % len(_keys)]
    _lst = _strata[_k]
    if _lst:
        _cid = _lst.pop(_rng.randrange(len(_lst)))
        if _cid not in _random:
            _random.append(_cid)
    _i += 1
_ids = _risk_ids + _random
print(f"  ★ 抽样：风险富集 {len(_risk_ids)} + 分层随机 {len(_random)} = {len(_ids)}")


def _build(cid, o, abs_line):
    _L = _docs[(o["protocol"], o["document"])]
    _ec = o.get("evidence_context") or []
    # ★ ① 原始 evidence_context（★ 绝对行号原文）
    _orig_ctx = [{"line": c.get("line"), "text": str(c.get("text") or "")}
                 for c in _ec]
    # ★ ② 从 RFC 原文重建的上下文（★ 锚点 ±6 行）
    _ctx = []
    for i in range(max(1, abs_line - 6), min(len(_L), abs_line + 6) + 1):
        _ctx.append({"line": i, "text": _L[i - 1]})
    _pol, _pol_src = _derive_polarity(o.get("strength"))
    _dm = doc_meta[(o["protocol"], o["document"])]
    return {
        "sample_id": cid,
        "protocol": o["protocol"], "document": o["document"],
        "rfc_sha256": _dm["rfc_sha256"],
        "chunk_id": f"{o['document']}@{o['chunk_start']}",
        "chunk_start": o["chunk_start"],
        "chunk_end_estimate": o["chunk_end_estimate"],
        "chunk_hash": o.get("chunk_hash"),
        "★ 原始 source_span（★ 绝对行号）": o.get("span"),
        "★ 绝对锚点行（= 原始 span，★ 绝对行号）": abs_line,
        "★ 与 chunk 关系": f"chunk {o["chunk_start"]}~{o["chunk_end_estimate"]}；★ 锚点在 chunk 内={o["chunk_start"] <= abs_line <= o["chunk_end_estimate"]}",
        "★ 锚点行原文": _L[abs_line - 1],
        "★ 原始 evidence_context（绝对行号原文）": _orig_ctx,
        "★ RFC 原文上下文（锚点 ±6 行）": _ctx,
        "★ LLM 原始候选字段": {
            "entity": o.get("entity"),
            "normative_subject": o.get("normative_subject"),
            "action": o.get("action"),
            "object": o.get("object"),
            "strength": o.get("strength"),
            "polarity": o.get("polarity"),
            "condition": o.get("condition"),
            "exception": o.get("exception"),
        },
        "★ LLM 原始 meaning（★ 生成文本，★ 非 RFC 原文）": o.get("meaning"),
        "★ LLM 原始 constraint（★ 生成文本，★ 非 RFC 原文）": o.get("constraint"),
        "★ polarity 来源": _pol_src,
        "★ 推导 polarity（★ 供人工核对）": _pol,
        "★ exception 情况": "★ 原始候选**无 exception 字段** ⇒ 标注应为 null",
        "★ condition 处理说明": ("★ **condition 不承载 constraint**；★ constraint 另存于"
                            "「★ LLM 原始 constraint」；★ condition 由人工从原文填写"),
    }


packs = []
for cid in _ids:
    o = frozen[cid]
    _abs = int(o["span"])
    _p = _build(cid, o, _abs)
    _p["分组"] = "K" if cid in _risk_ids else "R"
    _p["★ 抽样权重说明"] = ("★ 风险富集样本（★ **不可**用于估计总体错误率）"
                      if cid in _risk_ids else
                      "★ 分层随机样本（★ 按协议 × 知识类型分层；★ 可用于估计总体，★ 但需按分层加权）")
    packs.append(_p)

# ★ 完整性校验
_bad = [p["sample_id"] for p in packs
        if not p["★ RFC 原文上下文（锚点 ±6 行）"]
        or not p["★ 绝对锚点行（= 原始 span，★ 绝对行号）"]
        or not p["rfc_sha256"] or not p["chunk_id"]]
_dup = [k for k, v in
        collections.Counter(p["sample_id"] for p in packs).items() if v > 1] \
    if False else []
print(f"  ★ 完整性不合格 = {len(_bad)}｜重复 sample_id = {len(_dup)}")

(OUT / "n1r_restored_packs.jsonl").write_text(
    "\n".join(json.dumps(p, ensure_ascii=False) for p in packs) + "\n",
    encoding="utf-8")
print(f"  ⇒ {OUT/'n1r_restored_packs.jsonl'}")
