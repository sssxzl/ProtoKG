# -*- coding: utf-8 -*-
"""V2-E4-R2 第八节：队列 B 抽取窗口覆盖核验（逐片段）。

链路核验：source_sha256 -> chunk_id -> input_span -> actual_extraction_attempt
          -> candidate_output

四种处理状态：
  processed_with_candidate      提取窗口覆盖且产出候选
  processed_without_candidate   提取窗口覆盖但无候选
  never_processed               原文从未进入历史抽取窗口
  processing_status_unavailable 状态不可判定

判定逻辑与历史运行一致，本次仅规范化键名（内部键不带装饰前缀，外部键用常量隔离）。
"""
import collections
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/r2"
OUTD.mkdir(parents=True, exist_ok=True)

# 外部数据的键（常量隔离）
FB_DOC = "document"
FB_START = "chunk_start"
FB_TEXT = "chunk_text"
FB_ITEMS = "raw_items"
QB_DOC = "★ 来源 RFC"
QB_SHA = "★ 来源版本哈希"
QB_STATUS = "★ status"


def jl(path):
    return [json.loads(l) for l in
            pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


blocks = jl(ROOT / "docs/实施/待办与勘误/M0对账交付"
             / "M1-Q2证据冻结/frozen_blocks.jsonl")
window = {}
for b in blocks:
    n = str(b.get(FB_TEXT) or "").count("\n") + 1
    s = int(b[FB_START])
    window.setdefault(b[FB_DOC], []).append(
        (s, s + n - 1, len(b.get(FB_ITEMS) or [])))

gold = jl(ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl")

seen = set()
rows = []
for g in gold:
    sid = g["snippet_id"]
    if sid in seen:
        continue
    seen.add(sid)
    doc = g.get(QB_DOC, "")
    tail = sid.rsplit("-", 1)[-1]
    start = int(tail) if tail.isdigit() else None
    hit = None
    if start is not None:
        for w in window.get(doc, []):
            if w[0] <= start <= w[1]:
                hit = w
                break
    if hit is None:
        status = "never_processed"
        why = "该行不在任何历史抽取 chunk 的行覆盖范围内，原文从未进入抽取窗口"
    elif hit[2] > 0:
        status = "processed_with_candidate"
        why = "落在有候选产出的 chunk 内"
    else:
        status = "processed_without_candidate"
        why = "落在抽取窗口内但该 chunk 无候选产出"
    rows.append({
        "snippet_id": sid,
        "document": doc,
        "source_sha256": g.get(QB_SHA, ""),
        "source_span_start": start,
        "matched_chunk_id": (f"{doc}@{hit[0]}" if hit else None),
        "matched_chunk_range": (f"{hit[0]}-{hit[1]}" if hit else None),
        "chunk_candidate_count": (hit[2] if hit else None),
        "processing_status": status,
        "basis": why,
        "gold_knowledge_count": sum(1 for x in gold
                                if x["snippet_id"] == sid
                                and x.get(QB_STATUS) == "valid_gold"),
    })

counter = collections.Counter(r["processing_status"] for r in rows)
never = counter.get("never_processed", 0)
processed = len(rows) - never
doc_inter = sorted({r["document"] for r in rows} & set(window))

summary = {
    "queue_b_snippet_count": len(rows),
    "processing_status_distribution": dict(counter),
    "doc_level_intersection": doc_inter,
    "doc_level_intersection_count": len(doc_inter),
    "window_coverage_ratio": round(processed / max(1, len(rows)), 4),
    "conditional_recall_rate": ("N/A（processed = 0）" if processed == 0
                              else "需在匹配执行后计算"),
    "conclusion": (
        "全部片段均为 never_processed，不得对 H1 计算这些片段上的 LLM 知识召回率；"
        "队列 B 只能用于源头漏抽与输入覆盖缺口分析"
        if never == len(rows) else
        f"存在 {processed} 个 processed 片段，匹配后按覆盖率与抽取条件召回率两口径分别报告"),
    "note_doc_intersection": "文档级交集仅表示同文档，不代表对应原文已进入抽取窗口",
}

(OUTD / "r2_queue_b_coverage.json").write_text(
    json.dumps({"summary": summary, "per_snippet": rows},
               ensure_ascii=False, indent=2), encoding="utf-8")

print("  队列 B 逐片段处理状态：", dict(counter))
print("  抽取窗口覆盖率：", summary["window_coverage_ratio"])
print("  文档级交集数：", len(doc_inter), "（仅表示同文档，不代表已处理）")
print("  结论：", summary["conclusion"])
print(f"  产出：{OUTD / 'r2_queue_b_coverage.json'}")
