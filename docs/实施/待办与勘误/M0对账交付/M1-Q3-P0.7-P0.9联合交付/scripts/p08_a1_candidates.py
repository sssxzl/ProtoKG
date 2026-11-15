# -*- coding: utf-8 -*-
"""★ P0.8 第 1 步：★ 同块抽取基线（★ 候选生成与 kind 分类稳定性）。

★ 预算：**API ≤ 12 次**（★ 严格上限）｜token ≤ 150,000（★ 执行前校验）
★ 样本：★ 复用 P0.5 / M1-Q1 / P0 的**真实记录**优先；★ 新抽仅覆盖缺口
★ 块类型覆盖：规范义务块 / 状态转换块 / 描述定义块 / ★ 历史 kind 翻转块
★             / ★ `sip/rfc3261.txt@10452`（证据定位回归样本）
★ ★ **缓存关闭**；★ 保存**三次原始结果**而不只最终 norm
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import (OUTROOT, ROOT, Budget, git_commit, load_jsonl, save_json,
                  save_jsonl)
from core import paths
from core.fused.extraction import prose_semantics as ps
from core.fused.extraction.llm_diagnostics import LLMDiagnostics
from core.fused.extraction.normative_rule import parse_rule_text

MAX_ATTEMPTS = 12
MAX_TOKENS = 150_000
PROTO = "sip"

# ★ 目标块（★ 覆盖不同类型）
TARGETS = [
    ("T-A 规范义务块", "rfc3261.txt", 10452),      # ★ 证据定位回归样本
    ("T-B 规范义务块", "rfc3261.txt", 10486),      # SHOULD NOT / SHOULD 相邻
    ("T-C 状态/响应块", "rfc3261.txt", 10479),      # 421 Extension Required
    ("T-D 描述定义块", "rfc3261.txt", 1),           # 文档开头（历史 kind 翻转区）
    ("T-E 描述定义块", "rfc3261.txt", 7187),       # P0.5 曾出现 kind 翻转的块
]


def _split_all(path):
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")
    out, cur, start = [], [], 1
    for i, ln in enumerate(lines, start=1):
        if not cur:
            start = i
        cur.append(ln)
        if sum(len(x) + 1 for x in cur) >= ps._MAX_BLOCK_CHARS:
            out.append((start, "\n".join(cur)))
            cur = []
    if cur:
        out.append((start, "\n".join(cur)))
    return out


_doc = ROOT / f"kb/{PROTO}/spec/rfc3261.txt"
_lines = _doc.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
_all = _split_all(_doc)
_by_start = {s: t for s, t in _all}

_commit = git_commit()
blocks = []
for _why, _doc_name, _start in TARGETS:
    _p = ROOT / f"kb/{PROTO}/spec/{_doc_name}"
    _t = _p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    _L = _t.split("\n")
    if _doc_name == _doc.name:
        _b = _by_start.get(_start)
    else:
        _b = None
        for s, tx in _split_all(_p):
            if s == _start:
                _b = tx
                break
    if _b is None:
        print(f"  ★ 跳过 {_why}（★ 块起始行 {_start} 不存在）")
        continue
    blocks.append({"stratum": _why, "document": _doc_name, "start": _start,
                   "text": _b, "lines": _L,
                   "rfc_sha256": __import__("hashlib").sha256(
                       _p.read_bytes()).hexdigest(),
                   "chunk_hash": __import__("hashlib").sha256(
                       f"{_doc_name}|{_start}|{_b}".encode("utf-8")).hexdigest()})

print(f"  ★ 目标块 = {len(blocks)}｜每块 3 次 ⇒ 需 {len(blocks)*3} 次 API"
      f"（★ 上限 {MAX_ATTEMPTS}）")

# ══ 执行（★ 缓存关闭：★ 独立缓存目录且每轮不同 ⇒ 必然不命中）══
b = Budget("P0.8-同块抽取", MAX_ATTEMPTS, MAX_TOKENS, None)
runs = []
for blk in blocks:
    for rep in (1, 2, 3):
        if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
            break
        _diag = LLMDiagnostics(protocol=PROTO, entry_type="document",
                               out_dir=OUTROOT / "p08_diag" / f"{blk['start']}_r{rep}")
        _orig = ps._cache_path
        ps._cache_path = lambda p, _r=rep: OUTROOT / f"__p08cache_{_r}__" / f"{p}.json"
        try:
            _norms, _stats = ps._extract_blocks(
                PROTO, [{"doc": blk["document"], "start": blk["start"],
                         "text": blk["text"]}],
                entities=[], diagnostics=_diag, doc_lines={blk["document"]: blk["lines"]},
                llm=b)
        finally:
            ps._cache_path = _orig
        _diag.flush()
        _items = []
        for n in _norms:
            _pl = parse_rule_text(str(n.get("rule_text") or "")) or {}
            _items.append({
                "kind": n.get("kind"), "span_line": n.get("span_line"),
                "span_mode": n.get("span_mode"),
                "matched_evidence_line": n.get("span_matched_line"),
                "entity": n.get("mentioned_entity"),
                "subject": n.get("normative_subject"),
                "action": _pl.get("action"), "object": _pl.get("object"),
                "strength": _pl.get("strength"), "polarity": _pl.get("polarity"),
                "condition": _pl.get("condition"),
                "final_state": n.get("final_state"),
                "rule_text": str(n.get("rule_text") or "")[:160],
            })
        _sum = _diag.summary()
        runs.append({
            "stratum": blk["stratum"], "document": blk["document"],
            "chunk_start": blk["start"], "chunk_hash": blk["chunk_hash"],
            "rfc_sha256": blk["rfc_sha256"], "repeat_index": rep,
            "code_commit": _commit,
            "model": os.environ.get("LLM_MODEL"),
            "temperature": 0.1, "max_tokens": ps._MAX_TOKENS,
            "api_attempts": _sum["counters"]["llm_calls"],
            "★ 计量 api_attempts": b.attempts,
            "parse_failures": _sum["counters"]["parse_failed"],
            "input_tokens": _sum["counters"].get("input_tokens"),
            "output_tokens": _sum["counters"].get("output_tokens"),
            "raw_items": _stats.get("raw_items"), "norms": len(_norms),
            "kind_counts": dict(collections.Counter(i["kind"] for i in _items)),
            "★ items": _items,
        })
        print(f"  · {blk['stratum']:18s} @{blk['start']:<6d} #{rep} ⇒ "
              f"raw={_stats.get('raw_items')} norms={len(_norms)} "
              f"kinds={runs[-1]['kind_counts']}")
    if b.attempts >= MAX_ATTEMPTS or b.stop_reason:
        break

save_jsonl(OUTROOT / "p08_candidate_stability.jsonl", runs)
save_json(OUTROOT / "p08_a1_budget.json", b.summary())
print(f"\n  ★ API {b.attempts}/{MAX_ATTEMPTS}｜token {b.in_tok + b.out_tok:,}")
print(f"  ⇒ {OUTROOT/'p08_candidate_stability.jsonl'}")
