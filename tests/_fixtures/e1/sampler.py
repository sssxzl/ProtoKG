# -*- coding: utf-8 -*-
"""★ V2-E1：★ **双队列抽样器**（★ 支持 dry-run 与 freeze 两模式）。

★ 特性：
  · ★ 固定随机种子（★ 配置 JSON 声明）
  · ★ 稳定输入排序（★ 按 (protocol, document, 锚点行, id) 排序）
  · ★ RFC 文本 SHA256 校验（★ 输入一致性）
  · ★ 分层配额（★ 队列 B 以**章节类型**为主、★ 协议为辅）
  · ★ 文档级容量约束（★ 每 RFC ≤ 6，★ A/B 双队列**合并**计算）
  · ★ chunk 级排除 + ★ **原文证据跨度排除** + ★ 近重复（5-gram Jaccard）
  · ★ 已生成候选与未生成候选原文片段**分别抽样**
  · ★ 稳定 sample_id
  · ★ 输入 / 配置 / 输出哈希
  · ★ **dry-run 与 freeze 两模式**；★ 同一输入+配置+种子 ⇒ **逐字节一致的清单**
★ ★ **不调用 LLM**；★ **不生成人工标签**
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import random
import re

FREEZE = "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

# ══ 排除原因码 ══
EXCL_DEV_CANDIDATE = "dev_set_candidate_id"
EXCL_DEV_CHUNK = "dev_set_chunk"
EXCL_DEV_EVIDENCE = "dev_set_evidence_span"
EXCL_TUNING_EVIDENCE = "v2_tuning_special_case"
EXCL_NEAR_DUP = "near_duplicate_5gram"
EXCL_UNRESOLVED = "span_unresolved"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def grams(text, n=5):
    _w = re.findall(r"[a-z0-9]+", str(text).lower())
    return {tuple(_w[i:i + n]) for i in range(max(0, len(_w) - n + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def load_docs(root):
    _out = {}
    for _proto in ("rtsp", "sip", "smtp", "DHCPv4"):
        _d = pathlib.Path(root) / "kb" / _proto / "spec"
        if not _d.is_dir():
            continue
        for _f in sorted(_d.glob("*.txt")):
            _b = _f.read_bytes()
            _txt = _b.decode("utf-8", errors="replace").replace("\r\n", "\n")
            _out[(_proto, _f.name)] = {
                "lines": _txt.split("\n"), "sha256": sha256_bytes(_b),
                "path": str(_f.relative_to(root))}
    return _out


def load_candidates(root):
    _fr, _meta = {}, {}
    for l in (pathlib.Path(root) / FREEZE / "frozen_blocks.jsonl") \
            .read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        b = json.loads(l)
        _meta[(b["protocol"], b["document"])] = b
        for i, it in enumerate(b["raw_items"]):
            _fr[f"{b['document']}@{b['chunk_start']}#{i}"] = {
                **it, "protocol": b["protocol"], "document": b["document"],
                "chunk_start": b["chunk_start"]}
    return _fr, _meta


def load_spans(root):
    _p = pathlib.Path(root) / "guard/_out/n1r2/n1r2_span_ledger.jsonl"
    return {json.loads(l)["sample_id"]: json.loads(l)
            for l in _p.read_text(encoding="utf-8").splitlines() if l.strip()}


def build_exclusions(root, dev_candidates, dev_chunks, tuning_evidence):
    """★ 构建排除集合（★ 逐条记录原因）。"""
    _excl = {}
    for _cid in dev_candidates:
        _excl[_cid] = EXCL_DEV_CANDIDATE
    for _ck in dev_chunks:
        _excl.setdefault(f"chunk::{_ck}", EXCL_DEV_CHUNK)
    for _ev in tuning_evidence:
        _excl.setdefault(f"evidence::{_ev}", EXCL_TUNING_EVIDENCE)
    return _excl


def evidence_of(doc_lines, anchor, window=6):
    _lo = max(0, anchor - 1 - window)
    _hi = min(len(doc_lines), anchor + window)
    return " ".join(doc_lines[_lo:_hi])


def sample(root, cfg, mode="dry-run"):
    """★ 抽样主函数（★ mode ∈ {dry-run, freeze}）。"""
    _docs = load_docs(root)
    _fr, _meta = load_candidates(root)
    _spans = load_spans(root)
    _dev_cands = set(cfg["★ 开发集排除"]["candidate_ids"])
    _dev_chunks = set(cfg["★ 开发集排除"]["chunk_ids"])
    _tuning_ev = set(cfg["★ 开发集排除"]["tuning_evidence_spans"])
    _dev_grams = set()
    for _cid in _dev_cands:
        _s = _spans.get(_cid)
        if not _s or _s.get("resolved_span") is None:
            continue
        _k = (_s["★ protocol"], _s["★ document"])
        if _k in _docs:
            _dev_grams |= grams(evidence_of(_docs[_k]["lines"],
                                           int(_s["resolved_span"])))
    _excl = build_exclusions(root, _dev_cands, _dev_chunks, _tuning_ev)

    # ── 队列 A：已生成候选（★ 排除后）──
    _qa = []
    for _cid, _o in sorted(_fr.items()):
        _why = None
        if _cid in _dev_cands:
            _why = EXCL_DEV_CANDIDATE
        elif f"{_o['document']}@{_o['chunk_start']}" in _dev_chunks:
            _why = EXCL_DEV_CHUNK
        _s = _spans.get(_cid)
        if _why is None and (not _s or _s.get("resolved_span") is None):
            _why = EXCL_UNRESOLVED
        _ev = ""
        if _why is None:
            _k = (_o["protocol"], _o["document"])
            _rs = int(_spans[_cid]["resolved_span"])
            _ev = evidence_of(_docs[_k]["lines"], _rs)
            if _ev in _tuning_ev:
                _why = EXCL_TUNING_EVIDENCE
            elif jaccard(grams(_ev), _dev_grams) > cfg["★ 近重复阈值"]:
                _why = EXCL_NEAR_DUP
        if _why:
            continue
        _k = (_o["protocol"], _o["document"])
        _rs = int(_spans[_cid]["resolved_span"])
        _qa.append({
            "sample_id": f"A-{_cid.replace(':', '_').replace('#', '_').replace('@', '_')}",
            "队列": "A", "candidate_id": _cid,
            "protocol": _o["protocol"], "document": _o["document"],
            "chunk_id": f"{_o['document']}@{_o['chunk_start']}",
            "rfc_sha256": _docs[_k]["sha256"],
            "source_span": [_rs, _rs], "evidence_span": [max(1, _rs - 6), min(len(_docs[_k]["lines"]), _rs + 6)],
            "★ 章节类型": cfg.get("_kinds", {}).get(_cid),
        })

    # ── 队列 B：未生成候选的原文片段 ──
    _cov = collections.defaultdict(set)
    for _cid, _o in _fr.items():
        _b = _meta.get((_o["protocol"], _o["document"]))
        if not _b:
            continue
        _lo = int(_b["chunk_start"])
        _hi = _lo + int(str(_b.get("chunk_text") or "").count("\n"))
        for _i in range(_lo, _hi + 1):
            _cov[(_o["protocol"], _o["document"])].add(_i)
    _kinds_map = cfg.get("_section_kinds", {})
    _qb = []
    for _k in sorted(_docs):
        _d = _docs[_k]
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
            _frag = (_i, _j - 1)
            if _j - _i >= cfg["★ 片段最小行数"]:
                _ev = " ".join(_d["lines"][_i - 1:_j])
                _why = None
                if _ev in _tuning_ev:
                    _why = EXCL_TUNING_EVIDENCE
                elif jaccard(grams(_ev), _dev_grams) > cfg["★ 近重复阈值"]:
                    _why = EXCL_NEAR_DUP
                if _why is None:
                    _kind = _kinds_map.get(f"{_k[0]}/{_k[1]}:{_i}", "⑤ 附录、元数据及其他")
                    _qb.append({
                        "sample_id": f"B-{_k[0]}-{_k[1]}-{_i}",
                        "队列": "B", "protocol": _k[0], "document": _k[1],
                        "chunk_id": None, "rfc_sha256": _d["sha256"],
                        "source_span": [_i, _j - 1],
                        "evidence_span": [_i, _j - 1],
                        "★ 章节类型": _kind,
                        "★ 证据文本": _ev[:1200],
                    })
            _i = _j

    # ── 分层配额抽样（★ **协议硬配额优先**（★ 防单协议主导）→ 协议内按章节类型）
    _rng = random.Random(cfg["★ 随机种子"])
    _doc_used = collections.Counter()
    _picked = []
    _proto_quota = cfg.get("★ 协议配额", {})
    for _q in (_qa, _qb):
        _q_tag = _q[0]["队列"] if _q else None
        # ① 先按协议配额切分
        _by_proto = collections.defaultdict(list)
        for _s in _q:
            _by_proto[_s["protocol"]].append(_s)
        _proto_need = {}
        for _p, _lst in _by_proto.items():
            _proto_need[_p] = _proto_quota.get(_p, 0) if _proto_quota else len(_lst)
        # ② 每个协议内再按章节类型配额
        for _p in sorted(_by_proto):
            _by_kind = collections.defaultdict(list)
            for _s in _by_proto[_p]:
                _by_kind[_s["★ 章节类型"]].append(_s)
            _kinds = [k for k in cfg["★ 分层配额"] if cfg["★ 分层配额"][k] > 0]
            _tot_kind = sum(cfg["★ 分层配额"][k] for k in _kinds) or 1
            _p_need = _proto_need.get(_p, 0)
            _used = 0
            for _kind in _kinds:
                _lst = sorted(_by_kind.get(_kind, []),
                              key=lambda z: (z["protocol"], z["document"],
                                             z["source_span"][0], z["sample_id"]))
                _share = int(round(_p_need * cfg["★ 分层配额"][_kind] / _tot_kind))
                for _s in _lst:
                    if len(_picked) >= cfg["★ 目标总量"]:
                        break
                    if _share <= 0 or _used >= _p_need:
                        continue
                    _doc = (_s["protocol"], _s["document"])
                    if _doc_used[_doc] >= cfg["★ 每文档上限"]:
                        continue
                    _picked.append(_s)
                    _doc_used[_doc] += 1
                    _used += 1
                    _share -= 1
            # ★ 协议内配额未用满 ⇒ 用该协议剩余候选补齐（★ 仍受每文档上限约束）
            if _used < _p_need:
                for _kind in _kinds:
                    _lst = sorted(_by_kind.get(_kind, []),
                                  key=lambda z: (z["protocol"], z["document"],
                                                 z["source_span"][0], z["sample_id"]))
                    for _s in _lst:
                        if len(_picked) >= cfg["★ 目标总量"]:
                            break
                        if _used >= _p_need:
                            break
                        if _s in _picked:
                            continue
                        _doc = (_s["protocol"], _s["document"])
                        if _doc_used[_doc] >= cfg["★ 每文档上限"]:
                            continue
                        _picked.append(_s)
                        _doc_used[_doc] += 1
                        _used += 1
    _picked.sort(key=lambda z: (z["队列"], z["protocol"], z["document"],
                                z["source_span"][0], z["sample_id"]))
    _out = {
        "★ 模式": mode,
        "★ 配置哈希": sha256_file(cfg["★ 配置路径"]) if cfg.get("★ 配置路径") else None,
        "★ 输入文档哈希": {f"{k[0]}/{k[1]}": v["sha256"] for k, v in sorted(_docs.items())},
        "★ 随机种子": cfg["★ 随机种子"],
        "★ 队列A 可用（★ 排除后）": len(_qa),
        "★ 队列B 可用（★ 排除后）": len(_qb),
        "★ 实际抽出": len(_picked),
        "★ 抽出分布": dict(collections.Counter(s["★ 章节类型"] for s in _picked)),
        "★ 协议分布": dict(collections.Counter(s["protocol"] for s in _picked)),
        "★ 文档分布": dict(collections.Counter(
            f"{s['protocol']}/{s['document']}" for s in _picked)),
        "★ 样本": _picked,
    }
    _out["★ 输出哈希"] = sha256_bytes(
        json.dumps(_picked, ensure_ascii=False, sort_keys=True).encode())
    return _out
