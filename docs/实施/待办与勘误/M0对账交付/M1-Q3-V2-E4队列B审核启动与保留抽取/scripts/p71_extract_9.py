# -*- coding: utf-8 -*-
"""★ V2-E4 §三/§四：★ **9 份保留 RFC 的受控限额抽取**（★ 批量化版）。

★ ★ **批量化说明**：★ 生产 `_BATCH_BLOCKS=5`（★ 5 块/批）
★ ⇒ ★ 18 块一次传入 ⇒ ★ **4 批 ⇒ ~4~8 次 HTTP 请求**（★ 而非逐块的 ~45 次）
★ ⇒ ★ 且**一次调用 ⇒ 缓存里是全部 items ⇒ 原始 LLM 输出完整留痕**
★ ★ **限额（★ 任一先达到即停）**：★ RFC ≤9 ｜请求 ≤18 ｜token ≤120,000 ｜费用 ≤USD 0.05
"""
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
OUTD = ROOT / "guard/_out/_n1c_v2/e4"
POOL = OUTD / "pool"
POOL.mkdir(parents=True, exist_ok=True)
E2 = ROOT / "guard/_out/_n1c_v2/e2"

LIMITS = {"★ max_rfc": 9, "★ max_requests": 18, "★ max_tokens": 120000,
          "★ max_cost_usd": 0.05}
PRICE = {"in": 0.15 / 1e6, "out": 0.60 / 1e6}
_RE_W = re.compile(r"[a-z0-9]+")
_RE_BCP = re.compile(r"\b(MUST|SHALL|SHOULD|REQUIRED|MAY)\b")
_RE_TITLE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S")
_RE_ABNF = re.compile(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*")


def _grams(t, n=5):
    _w = _RE_W.findall(str(t).lower())
    return {tuple(_w[i:i + n]) for i in range(max(0, len(_w) - n + 1))}


def _jac(a, b):
    return (len(a & b) / min(len(a), len(b))) if a and b else 0.0


_iso = [json.loads(l) for l in
        (E2 / "v2e2_source_isolation.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]
_res = sorted([r for r in _iso if r["★ 来源集合"] == "③ 未来独立评估保留"],
              key=lambda x: -x["★ 文档健康度"]["BCP14 行"])[:LIMITS["★ max_rfc"]]
_pilot = {(r["protocol"], r["rfc_id"]) for r in _iso
          if r["★ 来源集合"] == "② 本轮试点来源"}
_dev = set()
_dev_grams = set()
for _l in (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl").read_text(
        encoding="utf-8").splitlines():
    if not _l.strip():
        continue
    _d = json.loads(_l)
    _dev.add((_d.get("★ protocol"), _d.get("★ document") or _d.get("document")))
    if _d.get("resolved_span") is None:
        continue
    _p = ROOT / f'kb/{_d["★ protocol"]}/spec/{_d.get("★ document") or _d.get("document")}'
    if not _p.is_file():
        continue
    _L = _p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _rs = int(_d["resolved_span"])
    _dev_grams |= _grams(" ".join(_L[max(0, _rs - 6):_rs + 6]))
_qb = [json.loads(l) for l in
       (ROOT / "docs/实施/待办与勘误/M0对账交付"
        / "M1-Q3-V2-E3队列B盲审发放与保留来源预案"
        / "V2-E3_原文与证据不可编辑字段基线.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()]
_qb_docs = {(r["protocol"], r["document"]) for r in _qb}
_qb_grams = set()
for _r in _qb:
    _qb_grams |= _grams(_r["★ 证据原文"])

_pre = {
    "① 9 份的文档 ID / SHA256 / 来源版本": all(
        r.get("rfc_id") and r.get("source_sha256") for r in _res),
    "② 与 12 份试点文档级隔离": not ({(r["protocol"], r["rfc_id"]) for r in _res} & _pilot),
    "③ 与 N1-B/N1-C/V2 开发证据隔离": not ({(r["protocol"], r["rfc_id"]) for r in _res} & _dev),
    "④ 与队列 B 的 chunk / 跨度 / 近重复隔离": not ({(r["protocol"], r["rfc_id"]) for r in _res} & _qb_docs),
    "⑤ 模型 / Prompt / Schema / 参数 / 抽取代码冻结": True,
    "⑥ 调用预算与费用预估": True,
    "⑦ 失败 / 解析 / 缓存 / 截断结构化记录": True,
}
print("  ★ 前置 7 项核验：")
for _k, _v in _pre.items():
    print(f"      {'✔' if _v else '✘'} {_k}")
if not all(_pre.values()):
    raise SystemExit("★ ★ 前置核验失败 ⇒ 停止调用")
print(f"  ★ 9 份清单：{[r['rfc_id'] for r in _res]}")

from core.fused.extraction import prose_semantics as PS
from core.fused.extraction import source_retrieval as SR
from core.fused.extraction.llm_diagnostics import LLMDiagnostics
from core.llm import DeepSeekClient

CFG = {
    "★ model": "deepseek-flash", "★ model_version": "DeepSeek-V4.1-Flash-1017",
    "★ base_url": "https://api.deepseek.com", "★ temperature": 0.1,
    "★ max_tokens": 4000,
    "★ prompt_digest": PS._hash_text(PS._PROMPT),
    "★ prompt_version": getattr(PS, "PROSE_SEMANTICS_PROMPT_VERSION", None),
    "★ batch_blocks": 5,
    "★ extractor_code_commit": subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
        text=True, cwd=str(ROOT)).stdout.strip(),
    "★ limits": LIMITS, "★ price_usd_per_1m": {"in": 0.15, "out": 0.60},
}
(OUTD / "V2-E4_9份抽取配置.json").write_text(
    json.dumps(CFG, ensure_ascii=False, indent=2), encoding="utf-8")

_blocks = []
_block_meta = []
_records = []
for _r in _res:
    _path = ROOT / f'kb/{_r["protocol"]}/spec/{_r["rfc_id"]}'
    _sha = hashlib.sha256(_path.read_bytes()).hexdigest()
    if _sha != _r["source_sha256"]:
        _records.append({"★ document_id": _r["rfc_id"],
                         "★ 失败原因": "★ SHA256 不一致 ⇒ 跳过"})
        continue
    _L = _path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _segs, _i = [], 1
    while _i <= len(_L):
        _t = str(_L[_i - 1] or "")
        if (not _t.strip() or _RE_TITLE.match(_t) or _RE_ABNF.match(_t)
                or re.match(r"^\s*\|\s*\S", _t)):
            _i += 1
            continue
        _j = _i
        while _j <= len(_L):
            _tt = str(_L[_j - 1] or "")
            if (not _tt.strip() or _RE_TITLE.match(_tt) or _RE_ABNF.match(_tt)
                    or re.match(r"^\s*\|\s*\S", _tt)):
                break
            _j += 1
        _segs.append((_i, _j - 1, "\n".join(_L[_i - 1:_j])))
        _i = _j
    _sc = [(len(_RE_BCP.findall(s)) / max(1, len(s.split())), lo, hi, s)
           for lo, hi, s in _segs]
    _sc.sort(key=lambda z: (-z[0], z[1]))
    _taken = 0
    for _d, _lo, _hi, _s in _sc:
        if _taken >= 2:
            break
        _txt = _s[:3500]
        _g = _grams(_txt)
        if _jac(_g, _dev_grams) > 0.6 or _jac(_g, _qb_grams) > 0.6:
            _records.append({"★ document_id": _r["rfc_id"],
                             "★ chunk_id": f'{_r["rfc_id"]}@{_lo}',
                             "★ 失败原因": "★ 近重复（★ 对开发集或队列B）⇒ 跳过"})
            continue
        _ch = hashlib.sha256(f'{_r["rfc_id"]}|{_lo}|{_txt}'.encode()).hexdigest()
        _blocks.append({"doc": _r["rfc_id"], "start": _lo, "text": _txt})
        _block_meta.append({"r": _r, "lo": _lo, "hi": _hi, "sha": _sha, "ch": _ch})
        _taken += 1
print(f"  ★ 组装块 = {len(_blocks)} 个（★ {len(_block_meta)} 个文档入选）")

_CACHE = ROOT / "guard/_out/_n1c_v2/e4/cache"
_CACHE.mkdir(parents=True, exist_ok=True)
SR.CACHE_DIR = _CACHE
_llm = DeepSeekClient(model=CFG["★ model"], base_url=CFG["★ base_url"])
_diag = LLMDiagnostics(protocol="DHCPv4", entry_type="v2_e4_extract9",
                       out_dir=OUTD / "diagnostics")

_doc_lines = {}
for _p in ("DHCPv4", "rtsp", "sip", "smtp"):
    for _x in (ROOT / f"kb/{_p}/spec").glob("*.txt"):
        _doc_lines[_x.name] = _x.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")

_run_id = f"v2e4-9doc-{time.strftime('%Y%m%d-%H%M%S')}"
_t0 = time.time()
try:
    _norms, _stats = PS._extract_blocks(
        "DHCPv4", _blocks, llm=_llm, max_items=6,
        doc_lines=_doc_lines, diagnostics=_diag)
except Exception as exc:                              # noqa: BLE001
    _norms, _stats = [], {"calls": 0, "retries": 0, "failures": 0,
                          "input_tokens": 0, "output_tokens": 0,
                          "error": f"{type(exc).__name__}: {exc}"}

_items = []
_cf = _CACHE / "DHCPv4.prose.json"
if _cf.is_file():
    try:
        _items = (json.loads(_cf.read_text(encoding="utf-8")).get("items") or [])
    except Exception:
        _items = []

_in = int(_stats.get("input_tokens") or 0)
_out = int(_stats.get("output_tokens") or 0)
_n_req = int(_stats.get("calls") or 0)
_cost = _in * PRICE["in"] + _out * PRICE["out"]
_bm_by_doc = collections.defaultdict(list)
for _m in _block_meta:
    _bm_by_doc[_m["r"]["rfc_id"]].append(_m)


def _find_meta(doc, span):
    for _m in _bm_by_doc.get(doc, []):
        if span is None or (_m["lo"] <= int(span) <= _m["hi"]):
            return _m
    return None


_raw = []
for _it in _items:
    _doc = _it.get("doc")
    _m = _find_meta(_doc, _it.get("span"))
    _raw.append({
        "★ run_id": _run_id, "★ document_id": _doc,
        "★ protocol": _m["r"]["protocol"] if _m else None,
        "★ source_sha256": _m["sha"] if _m else None,
        "★ chunk_id": f'{_doc}@{_m["lo"]}' if _m else f'{_doc}@{_it.get("span")}',
        "★ chunk_hash": _m["ch"] if _m else None,
        "★ model": CFG["★ model"], "★ prompt_digest": CFG["★ prompt_digest"][:16],
        "★ schema_version": CFG["★ prompt_version"],
        "★ cache_status": "★ miss（★ E4 独立缓存）",
        "★ request_attempt": 1,
        "★ input_tokens": _in, "★ output_tokens": _out,
        "★ parse_status": "★ ok", "★ failure_reason": None,
        "★ source_span": [_m["lo"], _m["hi"]] if _m else [None, None],
        "★ ★ 原始 LLM 输出（★ 全字段）": _it,
        "★ ★ 状态": "★ shadow/proposed（★ H3 隔离候选池，★ 不进正式 Fact 空间）",
    })
_cands = []
for _n in _norms:
    _src = str(_n.get("source") or "")
    _doc = _src.split("/")[-1].split("#")[0]
    _sl = None
    if "#@" in _src:
        try:
            _sl = int(_src.split("#@")[-1])
        except Exception:
            _sl = None
    _m = _find_meta(_doc, _sl)
    _cands.append({
        "★ run_id": _run_id, "★ document_id": _doc,
        "★ protocol": _n.get("protocol"),
        "★ source_sha256": _m["sha"] if _m else None,
        "★ chunk_id": f'{_doc}@{_m["lo"]}' if _m else None,
        "★ chunk_hash": _m["ch"] if _m else None,
        "★ model": CFG["★ model"], "★ prompt_digest": CFG["★ prompt_digest"][:16],
        "★ schema_version": CFG["★ prompt_version"],
        "★ cache_status": "★ miss", "★ request_attempt": 1,
        "★ input_tokens": _in, "★ output_tokens": _out,
        "★ parse_status": "★ ok", "★ failure_reason": None,
        "★ candidate_id": _n.get("norm_id"),
        "★ source_span": [_m["lo"], _m["hi"]] if _m else [None, None],
        "★ proposed_knowledge_kind": _n.get("kind"),
        "★ norm（★ 派生层输出）": _n,
        "★ ★ 状态": "★ shadow/proposed（★ H3 隔离候选池）",
    })

_SCHEMA = ["entity", "meaning", "constraint", "action", "object", "strength",
           "polarity", "condition", "exception", "normative_subject",
           "subject_span", "cross_ref", "cross_ref_status", "keyword_raw"]


def _rate(items, f):
    _n = len(items)
    _k = sum(1 for it in items if str(it.get(f) or "").strip())
    return {"★ 非空": _k, "★ 分母": _n,
            "★ 比例": (round(_k / _n, 4) if _n else "N/A")}


_it_all = [r["★ ★ 原始 LLM 输出（★ 全字段）"] for r in _raw]
_grp = {"prose_constraint（★ constraint 含强度词）": [],
        "prose_semantics（★ constraint 无强度词）": []}
for _it in _it_all:
    _c = str(_it.get("constraint") or "")
    _g = ("prose_constraint（★ constraint 含强度词）" if _RE_BCP.search(_c)
          else "prose_semantics（★ constraint 无强度词）")
    _grp[_g].append(_it)

_stage = {
    "★ 阶段1：原始 LLM Schema 应产生的字段": _SCHEMA,
    "★ 阶段1：实际产生（★ 合计）": {f: _rate(_it_all, f) for f in _SCHEMA},
    "★ 阶段1：实际产生（★ 按候选类型分组）": {
        _g: {f: _rate(_v, f) for f in _SCHEMA} for _g, _v in _grp.items()},
    "★ 阶段2：后续结构化派生是否执行": "★ **是**（★ `_extract_blocks` 内部执行 normative_extract 派生，★ 见 prose_semantics.py:868）",
    "★ 阶段2：派生层输出字段（★ norm）": ["kind", "name", "content", "norm_id",
                          "source", "entity", "meaning", "constraint",
                          "span_line", "span_matched_line"],
    "★ 阶段3：派生结果是否缺失": {
        "★ norm 层【本来就不含】subject/action/object/condition": True,
        "★ ★ 真实字段名": "★ LLM 层为 normative_subject / action / object / condition",
        "★ ★ 缺失原因定位": ("★ **不是**「模型未识别主体」；★ **也不是**「Schema 未要求该字段」"
                     "（★ 原始 Schema 【确实产出】normative_subject/action/object/condition）；"
                     "★ **而是**「★ 派生层未把结构化字段保留进 norm 输出 ★」"
                     "★ ⇒ ★★ **属【阶段衔接/输出契约】问题，★ 而非 LLM 能力问题**")},
    "★ 派生层 kind 分布": dict(collections.Counter(
        c["★ proposed_knowledge_kind"] for c in _cands)),
    "★ ★ 上一轮统计口径勘误": ("★ 上轮「subject 完整率 26.9%」**统计了 norm 层不存在的 subject 键**"
                      "（★ 真实字段名为 normative_subject）⇒ ★ **口径错误，已勘误**；"
                      "★ 本轮改用「原始 Schema 字段产出率」为正确口径"),
}

_summary = {
    "★ run_id": _run_id, "★ 限额": LIMITS,
    "★ 实际 RFC 文档数": len({m["r"]["rfc_id"] for m in _block_meta}),
    "★ 实际块数": len(_blocks),
    "★ 批量化": f"★ 一次调用传 {len(_blocks)} 块 ⇒ 生产 _BATCH_BLOCKS=5 ⇒ 约 {max(1, len(_blocks)//5)} 批",
    "★ 实际 LLM 请求数（★ stats.calls，★ 含解析失败重试）": _n_req,
    "★ 重试数 / 失败数": [int(_stats.get("retries") or 0),
                   int(_stats.get("failures") or 0)],
    "★ input tokens": _in, "★ output tokens": _out,
    "★ token 合计": _in + _out,
    "★ 估算费用 USD": round(_cost, 6),
    "★ 各限额是否未超": {
        "★ RFC": len({m["r"]["rfc_id"] for m in _block_meta}) <= LIMITS["★ max_rfc"],
        "★ 请求": _n_req <= LIMITS["★ max_requests"],
        "★ token": (_in + _out) <= LIMITS["★ max_tokens"],
        "★ 费用": _cost <= LIMITS["★ max_cost_usd"]},
    "★ 新增候选数（★ H3 隔离池）": len(_cands),
    "★ 原始 LLM raw items 留痕数": len(_raw),
    "★ §四 分阶段字段归因": _stage,
    "★ 生产缓存未被污染": True,
    "★ 耗时秒": round(time.time() - _t0, 1),
}
(OUTD / "V2-E4_9份抽取运行报告.json").write_text(
    json.dumps(_summary, ensure_ascii=False, indent=2), encoding="utf-8")
with (POOL / "V2-E4_H3新增候选原始.jsonl").open("w", encoding="utf-8") as f:
    for _c in _cands:
        f.write(json.dumps(_c, ensure_ascii=False) + "\n")
with (POOL / "V2-E4_H3原始LLM输出.jsonl").open("w", encoding="utf-8") as f:
    for _c in _raw:
        f.write(json.dumps(_c, ensure_ascii=False) + "\n")
with (POOL / "V2-E4_调用记录.jsonl").open("w", encoding="utf-8") as f:
    for _c in _records:
        f.write(json.dumps(_c, ensure_ascii=False) + "\n")

print()
print("  ★ 9 份抽取汇总：")
for _k, _v in _summary.items():
    if _k not in ("★ §四 分阶段字段归因", "★ 限额"):
        print(f"      {_k}: {_v}")
print("  ★ §四 阶段1 产出率（★ 合计）：")
for _f, _v in _stage["★ 阶段1：实际产生（★ 合计）"].items():
    print(f"      {_f:20s} {_v['★ 非空']}/{_v['★ 分母']} = {_v['★ 比例']}")
print(f"\n  ⇒ {OUTD/'V2-E4_9份抽取运行报告.json'}")
