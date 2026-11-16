# -*- coding: utf-8 -*-
"""★ N1-C：★ 生成盲审标注包（A / B / 仲裁）+ 审核说明 + 样本冻结清单。

★ ★ 盲审文件只含：★ 候选字段 + ★ 真实 RFC 原文证据（★ 绝对行号、锚点行、证据句、上下文）
★ ★ **不含**：★ 模型状态 / 前一轮错误归因 / 建议结论 / 任何 L2 结果
★ ★ 标签契约与 N1-A **完全一致**（★ 十项）⇒ ★ 保证两批可比
"""
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction.normative_extract import entity_in_span

OUTD = ROOT / "guard/_out/n1c"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
DELIV.mkdir(parents=True, exist_ok=True)
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

manifest = json.loads((OUTD / "n1c_freeze_manifest.json").read_text(encoding="utf-8"))
_ids = [r["sample_id"] for r in manifest["★ 样本逐条"]]
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


_NEG = ("MUST NOT", "SHALL NOT", "SHOULD NOT", "MAY NOT", "NOT RECOMMENDED")
BLIND_FIELDS = [
    ("subject", "义务承担者（★ 指代须写出解析后的实际承担者）"),
    ("action", "行为动词"),
    ("object", "行为对象（★ 跨行须完整）"),
    ("strength", "MUST/MUST NOT/SHOULD/SHOULD NOT/MAY/…"),
    ("polarity", "positive / negative"),
    ("condition", "★ 原文中的条件；★ 无则 null；★ **不得**填整条 constraint"),
    ("exception", "★ 原文中的例外；★ 无则 null"),
    ("evidence_support", "supported / partially_supported / contradicted / evidence_insufficient"),
    ("truth_label", "★ **独立语义真值**：valid_confirmed / valid_rejection / "
              "pending_insufficient_evidence / uncertain_requires_human"),
    ("review_note", "★ 独立审核理由（★ 必填或说明依据）"),
]
HEAD_BASE = [
    "sample_id", "protocol", "document", "rfc_sha256", "chunk_id",
    "chunk_start", "chunk_end", "★ raw_span", "★ resolved_span", "★ span_mode",
    "★ matched_evidence_lines",
    "★ entity（LLM 候选）", "★ normative_subject（LLM 候选）",
    "★ action（LLM 候选）", "★ object（LLM 候选）", "★ strength（LLM 候选）",
    "★ polarity（LLM 候选，★ 原始无此字段）",
    "★ condition（LLM 候选，★ 原始无此字段）",
    "★ exception（LLM 候选，★ 原始无此字段）",
    "★ LLM meaning（★ 生成文本，★ 非 RFC 原文）",
    "★ LLM constraint（★ 生成文本，★ 非 RFC 原文）",
    "★ 推导 polarity（★ 供核对）",
    "★ 锚点行原文（★ 合法可为空）", "★ 锚点行是否空白",
    "★ 证据句（含 entity 的非空行）",
    "★ RFC 原文上下文（锚点 ±6 行）",
]


def _norm(s):
    return str(s or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ⏎ ")


def _polarity(strength):
    _s = str(strength or "").strip().upper()
    if not _s:
        return "", "★ 原始候选无 strength ⇒ 无法推导"
    if _s in _NEG:
        return "negative", f"★ **推导值**：strength={_s} ⇒ 含否定形式"
    return "positive", f"★ **推导值**：strength={_s}"


packs = []
for cid in _ids:
    _sp = spans[cid]
    _o = FR.get(cid, {})
    _L = _lines(_sp["★ protocol"], _sp["★ document"])
    _rs = _sp["resolved_span"]
    _ent = _sp["★ entity"]
    _ctx = [{"line": i, "text": _L[i - 1]}
            for i in range(max(1, _rs - 6), min(len(_L), _rs + 6) + 1)]
    _ev = None
    for i in range(max(1, _rs - 3), min(len(_L), _rs + 3) + 1):
        if _ent and _ent.lower() in _L[i - 1].lower() and _L[i - 1].strip():
            _ev = {"line": i, "text": _L[i - 1]}
            break
    _pol, _pol_src = _polarity(_o.get("strength"))
    packs.append({
        "sample_id": cid, "protocol": _sp["★ protocol"],
        "document": _sp["★ document"], "rfc_sha256": _sp["★ rfc_sha256"],
        "chunk_id": f"{_sp['★ document']}@{_sp['chunk_start']}",
        "chunk_start": _sp["chunk_start"], "chunk_end": _sp["chunk_end"],
        "★ raw_span": _sp["raw_span"], "★ resolved_span": _rs,
        "★ span_mode": _sp["span_mode"],
        "★ matched_evidence_lines": _sp["★ matched_evidence_lines"],
        "★ 锚点行原文（★ 合法可为空）": _L[_rs - 1],
        "★ 锚点行是否空白": (not _L[_rs - 1].strip()),
        "★ 证据句（含 entity 的非空行）": _ev,
        "★ RFC 原文上下文（锚点 ±6 行）": _ctx,
        "★ LLM 原始候选字段": {
            "entity": _o.get("entity"), "normative_subject": _o.get("normative_subject"),
            "action": _o.get("action"), "object": _o.get("object"),
            "strength": _o.get("strength"), "polarity": _o.get("polarity"),
            "condition": _o.get("condition"), "exception": _o.get("exception")},
        "★ LLM meaning（★ 生成文本，★ 非 RFC 原文）": _o.get("meaning"),
        "★ LLM constraint（★ 生成文本，★ 非 RFC 原文）": _o.get("constraint"),
        "★ 推导 polarity（★ 供核对）": _pol, "★ polarity 来源": _pol_src,
    })


def _row(p, tag):
    _f = p["★ LLM 原始候选字段"]
    _ctx = " ⏎ ".join(f"{c['line']}: {_norm(c['text'])}"
                      for c in p["★ RFC 原文上下文（锚点 ±6 行）"])
    _ev = p["★ 证据句（含 entity 的非空行）"]
    _ev_s = (f"{_ev['line']}: {_norm(_ev['text'])}" if _ev else "")
    _base = [
        p["sample_id"], p["protocol"], p["document"], p["rfc_sha256"],
        p["chunk_id"], p["chunk_start"], p["chunk_end"],
        p["★ raw_span"], p["★ resolved_span"], p["★ span_mode"],
        p["★ matched_evidence_lines"],
        _f["entity"], _f["normative_subject"], _f["action"], _f["object"],
        _f["strength"], _f["polarity"] or "", _f["condition"] or "",
        _f["exception"] or "",
        p["★ LLM meaning（★ 生成文本，★ 非 RFC 原文）"],
        p["★ LLM constraint（★ 生成文本，★ 非 RFC 原文）"],
        p["★ 推导 polarity（★ 供核对）"],
        p["★ 锚点行原文（★ 合法可为空）"], p["★ 锚点行是否空白"], _ev_s, _ctx,
    ]
    _base = [_norm(_v) if isinstance(_v, str) else _v for _v in _base]
    return _base + [""] * len(BLIND_FIELDS) + [""]


HEAD_A = HEAD_BASE + [f"★ A:{c}" for c, _ in BLIND_FIELDS] + ["★ A:审核者"]
HEAD_B = HEAD_BASE + [f"★ B:{c}" for c, _ in BLIND_FIELDS] + ["★ B:审核者"]

for _tag, _head, _name in (("A", HEAD_A, "N1-C_盲审标注表_A.csv"),
                           ("B", HEAD_B, "N1-C_盲审标注表_B.csv")):
    with (DELIV / _name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(_head)
        for p in packs:
            w.writerow(_row(p, _tag))
    print(f"  ★ {_name}：{len(packs)} 行 × {len(_head)} 列")

with (DELIV / "N1-C_仲裁表.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["sample_id", "★ A:truth_label", "★ B:truth_label",
                "★ 是否分歧", "★ 仲裁后 truth_label",
                "★ 仲裁者 ID（★ 匿名编号）", "★ 审核日期", "★ 仲裁理由"])
    for p in packs:
        w.writerow([p["sample_id"], "", "", "", "", "", "", ""])

# ★ 样本冻结清单（★ 机器可读）
with (DELIV / "N1-C_样本冻结清单.jsonl").open("w", encoding="utf-8") as f:
    for p in packs:
        f.write(json.dumps({
            "sample_id": p["sample_id"], "protocol": p["protocol"],
            "document": p["document"], "rfc_sha256": p["rfc_sha256"],
            "chunk_id": p["chunk_id"], "chunk_start": p["chunk_start"],
            "chunk_end": p["chunk_end"], "raw_span": p["★ raw_span"],
            "resolved_span": p["★ resolved_span"], "span_mode": p["★ span_mode"],
            "matched_evidence_lines": p["★ matched_evidence_lines"],
            "evidence_line": (p["★ 证据句（含 entity 的非空行）"] or {}).get("line"),
            "anchor_blank": p["★ 锚点行是否空白"],
            "★ 抽取方式": "★ 机械提取：population.jsonl 的 not_sampled_in_frame 全集",
        }, ensure_ascii=False) + "\n")

# ★ ★ 泄漏检查（★ 逐列名）
_LEAK = ("L2", "verdict", "final_state", "模型状态", "误确认", "误拒",
         "错误归因", "人工真值", "truth_label", "review_note", "批次", "batch")
_bad = []
for _name, _head in (("N1-C_盲审标注表_A.csv", HEAD_A),
                      ("N1-C_盲审标注表_B.csv", HEAD_B)):
    for _h in _head:
        for _w in _LEAK:
            if _w in _h and not _h.startswith(("★ A:", "★ B:")):
                _bad.append((_name, _h))
print(f"  ★ ★ 泄漏检查（★ 非标签列）：{_bad or '★ 无泄漏'}")
print(f"  ★ 样本冻结清单：{len(packs)} 条")
