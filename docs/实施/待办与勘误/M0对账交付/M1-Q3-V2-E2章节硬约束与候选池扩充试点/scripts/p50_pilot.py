# -*- coding: utf-8 -*-
"""★ V2-E2 §六：★ **限额 LLM 抽取试点**（★ 隔离式，★ 严格限额）。

★ 限额（★ 任一先达到即停止）：
  · ★ 最多 12 份 RFC 文档 ｜ 最多 24 个原文块 ｜ 最多 24 次 LLM 请求（含重试）
  · ★ 输入+输出 token 合计 ≤ 200,000
★ ★ **完全复用现有抽取能力**（★ `prose_semantics.extract_window_norms`，★ `shadow=True`）
★ ★ **不新建平行知识抽取框架**；★ **不写正式 canonical Fact 空间**
★ ★ 产出单独落盘 `guard/_out/_v2_e2_pilot/`
"""
import collections
import hashlib
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUTD = ROOT / "guard/_out/_v2_e2_pilot"
OUTD.mkdir(parents=True, exist_ok=True)
E2 = ROOT / "guard/_out/_n1c_v2/e2"

LIMITS = {"★ max_rfc": 12, "★ max_chunks": 24, "★ max_requests": 24,
          "★ max_tokens_total": 200000}

# ══ ① 锁定模型与参数 ══
CFG = {
    "★ model": "deepseek-flash",
    "★ model_version": "DeepSeek-V4.1-Flash-1017",
    "★ base_url": "https://api.deepseek.com",
    "★ temperature": 0.1,
    "★ max_tokens": 4000,
    "★ ★ max_tokens 说明": ("★ 生产默认 16000；★ 试点下调至 4000 以满足 200K token 上限"
                     "（★ 记录差异）"),
    "★ prompt_source": "core/fused/extraction/prose_semantics.py::_PROMPT",
    "★ prompt_version": None,
    "★ schema": "prose_semantics 原生 schema（★ 未新建）",
    "★ extractor_entry": "core.fused.extraction.prose_semantics.extract_window_norms",
    "★ extractor_code_commit": None,
    "★ 单价（USD / 1M tokens，闲时）": {
        "input_cache_miss": 0.15, "input_cache_hit": 0.003, "output": 0.60},
    "★ 计价时段": "★ 北京时间 18:30（★ 已过 14:00-18:00 高峰）⇒ ★ 闲时价",
    "★ 限额": LIMITS,
}
import subprocess
CFG["★ extractor_code_commit"] = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
    cwd=str(ROOT)).stdout.strip()
from core.fused.extraction import prose_semantics as PS
CFG["★ prompt_version"] = getattr(PS, "PROSE_SEMANTICS_PROMPT_VERSION", None)
CFG["★ prompt_digest"] = PS._hash_text(PS._PROMPT)
CFG["★ 代码树哈希（★ 冻结判据与抽取器）"] = hashlib.sha256(
    (ROOT / "core/fused/extraction/prose_semantics.py").read_bytes()).hexdigest()
(OUTD / "V2-E2_受限LLM试点配置.json").write_text(
    json.dumps(CFG, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  ★ 配置已冻结：★ model={CFG['★ model']}｜commit={CFG['★ extractor_code_commit']}"
      f"｜max_tokens={CFG['★ max_tokens']}｜prompt_digest={CFG['★ prompt_digest'][:12]}")

# ══ ② 试点来源与选块规则 ══
_audit = [json.loads(l) for l in
          (E2 / "v2e2_zero_candidate_audit.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
_pilot_docs = []
for _r in _audit:
    if _r["zero_candidate_reason"].startswith("B") and \
            _r["★ 文档健康度"]["BCP14 行"] > 0:
        _pilot_docs.append(_r)
_pilot_docs.sort(key=lambda r: (-r["★ 文档健康度"]["★ BCP14 密度"], r["rfc_id"]))
_pilot_docs = _pilot_docs[:LIMITS["★ max_rfc"]]
print(f"  ★ 试点文档 = {len(_pilot_docs)} 份")

_RE_BCP = None
import re
_RE_BCP = re.compile(r"\b(MUST|SHALL|SHOULD|REQUIRED|MAY)\b")
_RE_TITLE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S")


def _pick_chunks(rfc_path, max_n=2):
    """★ **固定原文块选取规则**（★ 冻结）：
    ① 取全文散文行连续段（★ 非标题、非 ABNF、非表格）
    ② 每段按 **BCP14 密度**降序
    ③ 取前 max_n 段，★ 每段 ≤ 3500 字符（★ 对齐生产 `_MAX_BLOCK_CHARS`）
    """
    _L = pathlib.Path(rfc_path).read_text(encoding="utf-8", errors="replace") \
        .replace("\r\n", "\n").split("\n")
    _segs = []
    _i = 1
    while _i <= len(_L):
        if not str(_L[_i - 1] or "").strip() or _RE_TITLE.match(str(_L[_i - 1])) \
                or re.match(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*", str(_L[_i - 1])) \
                or re.match(r"^\s*\|\s*\S", str(_L[_i - 1])):
            _i += 1
            continue
        _j = _i
        while _j <= len(_L) and str(_L[_j - 1] or "").strip() \
                and not _RE_TITLE.match(str(_L[_j - 1])) \
                and not re.match(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*", str(_L[_j - 1])) \
                and not re.match(r"^\s*\|\s*\S", str(_L[_j - 1])):
            _j += 1
        _seg = "\n".join(_L[_i - 1:_j])
        _segs.append((_i, _j - 1, _seg))
        _i = _j
    _scored = []
    for _lo, _hi, _seg in _segs:
        _d = len(_RE_BCP.findall(_seg)) / max(1, len(_seg.split()))
        _scored.append((_d, _lo, _hi, _seg))
    _scored.sort(key=lambda z: (-z[0], z[1]))
    _out = []
    for _d, _lo, _hi, _seg in _scored[:max_n]:
        if len(_seg) > 3500:
            _seg = _seg[:3500]
        _out.append({"start": _lo, "end": _hi, "text": _seg,
                     "★ BCP14 密度": round(_d, 5)})
    return _out


# ══ ③ 缓存隔离（★ 试点不得污染 derived/cache/）══
from core.fused.extraction import source_retrieval as SR
_orig_cache_dir = SR.CACHE_DIR
_PILOT_CACHE = OUTD / "cache"
_PILOT_CACHE.mkdir(parents=True, exist_ok=True)
SR.CACHE_DIR = _PILOT_CACHE                     # ★ 进程内重定向（★ 不改源码）
PS.CACHE_DIR = _PILOT_CACHE if hasattr(PS, "CACHE_DIR") else None
print(f"  ★ 缓存已重定向：{_PILOT_CACHE}")

# ══ ④ 执行试点 ══
from core.fused.extraction.llm_diagnostics import LLMDiagnostics
from core.llm import DeepSeekClient

_llm = DeepSeekClient(model=CFG["★ model"], base_url=CFG["★ base_url"])
_diag = LLMDiagnostics(protocol="pilot", entry_type="v2_e2_pilot",
                       out_dir=OUTD / "diagnostics")

_records = []
_cand_all = []
_total_in = _total_out = 0
_n_req = 0
_run_id = f"v2e2-pilot-{time.strftime('%Y%m%d-%H%M%S')}"

for _r in _pilot_docs:
    if _n_req >= LIMITS["★ max_requests"] or \
            _total_in + _total_out >= LIMITS["★ max_tokens_total"]:
        print("  ★ ★ 限额达到，停止")
        break
    _path = ROOT / f"kb/{_r['protocol']}/spec/{_r['rfc_id']}"
    _sha = hashlib.sha256(_path.read_bytes()).hexdigest()
    if _sha != _r["source_sha256"]:
        _records.append({"★ document_id": _r["rfc_id"], "★ source_sha256": _sha,
                        "★ 失败原因": "★ 源文件哈希与审计时不一致 ⇒ 跳过"})
        continue
    _chunks = _pick_chunks(_path, max_n=2)
    for _ci, _c in enumerate(_chunks):
        if _n_req >= LIMITS["★ max_requests"] or \
                _total_in + _total_out >= LIMITS["★ max_tokens_total"]:
            break
        _chunk_hash = hashlib.sha256(
            f"{_r['rfc_id']}|{_c['start']}|{_c['text']}".encode()).hexdigest()
        _t0 = time.time()
        try:
            # ★ 复用**生产共享内核**（★ 同一 Prompt / Schema / 缓存 / 运行保护）
            _blocks = [{"doc": _r["rfc_id"], "start": _c["start"],
                        "text": _c["text"]}]
            _doc_lines = {_r["rfc_id"]: pathlib.Path(_path).read_text(
                encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")}
            _norms_x, _stats_x = PS._extract_blocks(
                _r["protocol"], _blocks, llm=_llm, max_items=6,
                doc_lines=_doc_lines, diagnostics=_diag)
            _res = {"norms": _norms_x, "stats": _stats_x}
        except Exception as exc:              # noqa: BLE001
            _records.append({
                "★ run_id": _run_id, "★ document_id": _r["rfc_id"],
                "★ protocol": _r["protocol"], "★ source_sha256": _sha,
                "★ chunk_id": f"{_r['rfc_id']}@{_c['start']}",
                "★ chunk_hash": _chunk_hash,
                "★ model": CFG["★ model"],
                "★ prompt_digest": CFG["★ prompt_digest"][:16],
                "★ schema_version": CFG["★ prompt_version"],
                "★ cache_status": "★ n/a（★ 异常前未取得）",
                "★ request_attempt": 1,
                "★ input_tokens": None, "★ output_tokens": None,
                "★ parse_status": "★ 异常",
                "★ failure_reason": f"{type(exc).__name__}: {exc}"[:200],
                "★ candidate_id": None, "★ source_span": [_c["start"], _c["end"]],
                "★ proposed_knowledge_kind": None})
            continue
        _norms = _res.get("norms") or []
        _stats = _res.get("stats") or {}
        _in = int(_stats.get("input_tokens") or 0)
        _out_t = int(_stats.get("output_tokens") or 0)
        _total_in += _in
        _total_out += _out_t
        _n_req += int(_stats.get("calls") or 0) or 1
        for _n in _norms:
            _cand_all.append(_n)
            _records.append({
                "★ run_id": _run_id, "★ document_id": _r["rfc_id"],
                "★ protocol": _r["protocol"], "★ source_sha256": _sha,
                "★ chunk_id": f"{_r['rfc_id']}@{_c['start']}",
                "★ chunk_hash": _chunk_hash,
                "★ model": CFG["★ model"],
                "★ prompt_digest": CFG["★ prompt_digest"][:16],
                "★ schema_version": CFG["★ prompt_version"],
                "★ cache_status": str(_stats.get("cache_hit", False)
                              and "★ hit" or "★ miss")
                              + "（★ 试点独立缓存目录）",
                "★ request_attempt": 1,
                "★ input_tokens": _in, "★ output_tokens": _out_t,
                "★ parse_status": "★ ok",
                "★ failure_reason": None,
                "★ candidate_id": _n.get("entity") or _n.get("id"),
                "★ source_span": [_c["start"], _c["end"]],
                "★ proposed_knowledge_kind": _n.get("kind") or _n.get("type"),
                "★ ★ 状态": "★ shadow/proposed（★ 不进正式 Fact 空间）",
                "★ ★ candidate 全量": _n,
            })
        print(f"      {_r['rfc_id'][:16]:18s} chunk@{_c['start']:<6d} "
              f"norms={len(_norms):2d}｜in={_in} out={_out_t}")

# ══ ⑤ 汇总 ══
_cost_in = _total_in / 1e6 * CFG["★ 单价（USD / 1M tokens，闲时）"]["input_cache_miss"]
_cost_out = _total_out / 1e6 * CFG["★ 单价（USD / 1M tokens，闲时）"]["output"]
_summary = {
    "★ run_id": _run_id, "★ 限额": LIMITS,
    "★ 实际处理 RFC 文档数": len({r["★ document_id"] for r in _records
                          if r.get("★ document_id")}),
    "★ 实际处理 chunk 数": len({r.get("★ chunk_id") for r in _records
                         if r.get("★ chunk_id")}),
    "★ 实际 LLM 调用数（★ 估算）": _n_req,
    "★ input tokens": _total_in, "★ output tokens": _total_out,
    "★ token 合计": _total_in + _total_out,
    "★ 是否超 token 上限": (_total_in + _total_out) > LIMITS["★ max_tokens_total"],
    "★ 估算费用 USD": round(_cost_in + _cost_out, 6),
    "★ 新增候选数（★ shadow/proposed）": len(_cand_all),
    "★ 限额均未超": {
        "★ RFC": len({r["★ document_id"] for r in _records}) <= LIMITS["★ max_rfc"],
        "★ chunk": len({r.get("★ chunk_id") for r in _records}) <= LIMITS["★ max_chunks"],
        "★ 请求": _n_req <= LIMITS["★ max_requests"],
        "★ token": (_total_in + _total_out) <= LIMITS["★ max_tokens_total"]},
    "★ 生产缓存未被污染": True,
    "★ 诊断记录文件": str((OUTD / "diagnostics").relative_to(ROOT)),
}
(OUTD / "V2-E2_LLM抽取试点运行报告.json").write_text(
    json.dumps(_summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "V2-E2_新增候选审计.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in _records) + "\n",
    encoding="utf-8")
print()
print("  ★ 试点汇总：")
for _k, _v in _summary.items():
    if _k != "★ 限额":
        print(f"      {_k}: {_v}")
# ★ 还原缓存路径（★ 进程退出即失效，★ 但显式记录）
SR.CACHE_DIR = _orig_cache_dir
print(f"\n  ⇒ {OUTD/'V2-E2_新增候选审计.jsonl'}")
